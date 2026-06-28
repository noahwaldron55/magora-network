# Magora Listen — inference worker

Server-side BirdNET worker for the portal's **Listen** feature. When someone
records a 15-second field recording on their phone, the audio lands in Supabase
Storage and a job goes onto the `audio_inference` queue. This worker pulls the
job, runs BirdNET (the same pipeline as the Pi nodes' `firmware/detect.py`),
writes the species back onto the `mobile_detections` row, and deletes the audio.

```
phone → temp-audio bucket + mobile_detections (pending) → pgmq audio_inference
            → [this worker] → mobile_detections (complete) + audio deleted
            → Supabase Realtime pushes the result back to the phone
```

## Pipeline parity with the nodes

BirdNET is run with the exact parameters from `firmware/detect.py`
(`min_conf=0.20`, `sensitivity=1.25`, `overlap=1.5`) and the same
human/vehicle/insect exclusion filter, so a mobile Listen is directly comparable
to a node detection.

**Regional filtering:** the Pi nodes use a fixed per-node eBird whitelist. Mobile
recordings have a variable location, so instead the worker passes the recording's
`lat`/`lon`/`date` to BirdNET's built-in location filter (its eBird-derived range
model), restricting results to species plausible at that place and time of year.
This is what keeps implausible IDs (e.g. a Wyoming "Black-faced Ibis") out.

> **Version note:** the Pi installs `birdnetlib` unpinned. For true result parity,
> pin `birdnetlib` here to whatever the nodes run (`pip show birdnetlib` on a Pi),
> then rebuild.

## Files

| File | Purpose |
|---|---|
| `inference_worker.py` | Poll loop + BirdNET inference |
| `requirements.txt` | Python deps |
| `Dockerfile` | Build (python:3.11-slim + ffmpeg) |
| `fly.toml` | Fly.io app config |

## Secrets

The worker authenticates with the **service role key** over HTTPS (no direct
Postgres connection). It needs:

- `SUPABASE_URL` — `https://wqxmmuwrfltpaxnuddwk.supabase.co`
- `SUPABASE_SERVICE_ROLE_KEY` — from Supabase dashboard → Project Settings → API

These are set as Fly secrets (never committed).

## Deploy (first time)

You need a [Fly.io](https://fly.io) account. Fly builds the image on a **remote
builder**, so Docker is *not* required locally.

```bash
# 1. Install the Fly CLI (Windows PowerShell):
#    iwr https://fly.io/install.ps1 -useb | iex
# 2. Sign in (opens a browser):
fly auth login

# 3. From this directory, create the app WITHOUT deploying yet:
cd worker
fly launch --no-deploy --copy-config --name magora-listen-worker --region den

# 4. Set the secrets:
fly secrets set SUPABASE_URL=https://wqxmmuwrfltpaxnuddwk.supabase.co
fly secrets set SUPABASE_SERVICE_ROLE_KEY=<paste service role key>

# 5. Deploy:
fly deploy

# 6. Watch it boot + poll:
fly logs
```

## Test end-to-end

1. Put a known bird call WAV into the bucket under a real user's folder and
   insert a matching `mobile_detections` row (or just use the Phase 3 UI once
   built).
2. `fly logs` should show the model load, then `✓ <id>: N species`.
3. The `mobile_detections` row flips `pending → processing → complete` with a
   populated `species` array, and the audio object is gone from `temp-audio`.

## Scaling

```bash
fly scale count 3   # more workers; visibility timeout prevents double-processing
fly scale memory 2048   # if BirdNET OOMs
```

## Troubleshooting

- **`tflite-runtime` wheel not found during build** — swap it for `tensorflow-cpu`
  in `requirements.txt` and bump the VM memory in `fly.toml` (TF is much larger).
- **Worker OOM-killed** — raise `memory` in `fly.toml` / `fly scale memory`.
- **Jobs retried forever** — a job is archived after `MAX_ATTEMPTS` reads and its
  row marked `failed`; check `fly logs` for the underlying error.
