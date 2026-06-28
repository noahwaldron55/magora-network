"""
Magora — Listen inference worker.

Pulls jobs from the Supabase pgmq `audio_inference` queue (via the SECURITY
DEFINER RPCs in the portal repo's 20260629 migration), runs the same BirdNET
pipeline as the Pi nodes' detect.py, writes species results back onto the
mobile_detections row, deletes the temp audio, and removes the job.

Auth: service role key (bypasses RLS) over HTTPS — no direct Postgres
connection, no DB password on this box.

Deploy: Fly.io. Secrets required: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY.
"""

import os
import time
import tempfile

from supabase import create_client, Client
from birdnetlib import Recording
from birdnetlib.analyzer import Analyzer

# ── Config ────────────────────────────────────────────────────────────────────
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL_SECONDS", "5"))
VISIBILITY_TIMEOUT = int(os.environ.get("JOB_VISIBILITY_TIMEOUT", "120"))  # secs a job is hidden while we work it
MAX_ATTEMPTS = int(os.environ.get("MAX_ATTEMPTS", "5"))                    # give up after this many reads
BUCKET = "temp-audio"

# BirdNET parameters — kept identical to firmware/detect.py so mobile Listens and
# node detections are directly comparable.
MIN_CONF = 0.20
SENSITIVITY = 1.25
OVERLAP = 1.5

# Same non-ecological / false-positive filter as detect.py.
EXCLUDE = {
    "Human vocal", "Human non-vocal", "Human whistling", "Crowd",
    "Dog", "Cat",
    "Engine", "Siren", "Power tools", "Gun",
    "Fireworks", "Hand saw", "Chainsaw",
    "Car", "Truck", "Motorcycle",
    "Laysan Albatross", "Black-footed Albatross",
}
INSECT_KEYWORDS = ("Katydid", "Cricket", "Grasshopper", "Cicada")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

print("Loading BirdNET model...")
analyzer = Analyzer()  # loaded once, reused across every job
print("Model ready. Polling audio_inference queue.\n", flush=True)


# ── Inference ─────────────────────────────────────────────────────────────────
def run_birdnet(path: str) -> list[dict]:
    """Run BirdNET on an audio file, return cleaned species results (best-first)."""
    recording = Recording(
        analyzer, path,
        min_conf=MIN_CONF,
        sensitivity=SENSITIVITY,
        overlap=OVERLAP,
    )
    recording.analyze()

    best: dict[str, dict] = {}  # common_name -> best detection, deduped across windows
    for d in recording.detections:
        name = d["common_name"]
        if name in EXCLUDE:
            continue
        if any(k in name for k in INSECT_KEYWORDS):
            continue
        if name not in best or d["confidence"] > best[name]["confidence"]:
            best[name] = {
                "common_name": name,
                "scientific_name": d["scientific_name"],
                "confidence": round(float(d["confidence"]), 4),
            }

    return sorted(best.values(), key=lambda s: s["confidence"], reverse=True)


def process_job(message: dict) -> None:
    """Download → infer → write results → delete audio for a single job."""
    detection_id = message["detection_id"]
    audio_path = message["audio_path"]  # in-bucket path, e.g. {user_id}/{id}.wav

    supabase.table("mobile_detections").update(
        {"status": "processing"}
    ).eq("id", detection_id).execute()

    audio_bytes = supabase.storage.from_(BUCKET).download(audio_path)

    suffix = os.path.splitext(audio_path)[1] or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(audio_bytes)
        tmp_path = f.name
    try:
        species = run_birdnet(tmp_path)
    finally:
        os.unlink(tmp_path)

    # Write results and clear the audio pointer (audio itself deleted next).
    supabase.table("mobile_detections").update({
        "status": "complete",
        "species": species,
        "audio_path": None,
    }).eq("id", detection_id).execute()

    # Privacy-first: audio is ephemeral, never persisted past inference.
    supabase.storage.from_(BUCKET).remove([audio_path])

    print(f"  ✓ {detection_id}: {len(species)} species", flush=True)


def mark_failed(detection_id: str) -> None:
    try:
        supabase.table("mobile_detections").update(
            {"status": "failed"}
        ).eq("id", detection_id).execute()
    except Exception as ex:  # noqa: BLE001
        print(f"  could not mark {detection_id} failed: {ex}", flush=True)


# ── Poll loop ─────────────────────────────────────────────────────────────────
def poll_loop() -> None:
    while True:
        try:
            resp = supabase.rpc(
                "read_audio_jobs", {"p_qty": 1, "p_vt": VISIBILITY_TIMEOUT}
            ).execute()
            jobs = resp.data or []
        except Exception as ex:  # noqa: BLE001
            print(f"queue read error: {ex}", flush=True)
            time.sleep(POLL_INTERVAL)
            continue

        if not jobs:
            time.sleep(POLL_INTERVAL)
            continue

        job = jobs[0]
        msg_id = job["msg_id"]
        read_ct = job["read_ct"]
        message = job["message"]
        detection_id = message.get("detection_id")

        # Poison-message guard: stop retrying after MAX_ATTEMPTS.
        if read_ct > MAX_ATTEMPTS:
            print(f"  ✗ job {msg_id} exceeded {MAX_ATTEMPTS} attempts — archiving", flush=True)
            if detection_id:
                mark_failed(detection_id)
            supabase.rpc("archive_audio_job", {"p_msg_id": msg_id}).execute()
            continue

        try:
            process_job(message)
            supabase.rpc("delete_audio_job", {"p_msg_id": msg_id}).execute()
        except Exception as ex:  # noqa: BLE001
            # Leave the job in the queue; pgmq re-shows it after the visibility
            # timeout for another attempt (read_ct increments each time).
            print(f"  job {msg_id} failed (attempt {read_ct}): {ex}", flush=True)


if __name__ == "__main__":
    poll_loop()
