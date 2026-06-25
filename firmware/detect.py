import subprocess
import requests
import json
import os
import math
import numpy as np
from datetime import datetime, timedelta, timezone
from astral import LocationInfo
from astral.sun import sun
from birdnetlib import Recording
from birdnetlib.analyzer import Analyzer
from scipy.signal import butter, sosfilt
import scipy.io.wavfile as wavfile

SCRIPT_URL = "https://script.google.com/macros/s/AKfycbw1MS_MwASMPbl6W0nvv5ChYLnwtEcfUOkAZSeKLSJ9bmS753Vdhnhn_3wjFCSmJwqYgw/exec"
LOCATION_FILE = "/home/magora/location.json"
QUEUE_FILE = "/home/magora/retry_queue.json"
ACI_QUEUE_FILE = "/home/magora/aci_queue.json"
MIN_CONF = 0.35

SUPABASE_URL     = "https://wqxmmuwrfltpaxnuddwk.supabase.co"
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")
NODE_EMAIL       = os.environ.get("NODE_EMAIL", "")
NODE_PASSWORD    = os.environ.get("NODE_PASSWORD", "")
NODE_ID          = os.environ.get("NODE_ID", "")

_token = None

def sign_in():
    global _token
    r = requests.post(
        f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
        headers={"apikey": SUPABASE_ANON_KEY, "Content-Type": "application/json"},
        json={"email": NODE_EMAIL, "password": NODE_PASSWORD},
        timeout=15
    )
    r.raise_for_status()
    _token = r.json()["access_token"]
    print("Signed in to Supabase.")

def get_headers():
    return {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {_token}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    }

def _post_supabase(url, payload):
    r = requests.post(url, headers=get_headers(), json=payload, timeout=10)
    if r.status_code == 401:
        sign_in()
        r = requests.post(url, headers=get_headers(), json=payload, timeout=10)
    return r

def apply_highpass_filter(filename, cutoff_hz=500):
    """Remove wind noise below 500Hz before BirdNET analysis."""
    try:
        rate, data = wavfile.read(filename)
        sos = butter(4, cutoff_hz, btype='high', fs=rate, output='sos')
        if data.ndim == 1:
            filtered = sosfilt(sos, data.astype(np.float64)).astype(data.dtype)
        else:
            filtered = np.column_stack([
                sosfilt(sos, data[:, i].astype(np.float64)).astype(data.dtype)
                for i in range(data.shape[1])
            ])
        wavfile.write(filename, rate, filtered)
    except Exception as ex:
        print(f"High-pass filter error: {ex}")

EXCLUDE = {
    "Human vocal", "Human whistling", "Crowd",
    "Dog", "Cat",
    "Engine", "Siren", "Power tools", "Gun",
    "Fireworks", "Hand saw", "Chainsaw",
    "Car", "Truck", "Motorcycle"
}

def get_location():
    try:
        with open(LOCATION_FILE) as f:
            data = json.load(f)
            return data.get("lat", 43.4), data.get("lon", -110.7), data.get("name", "Jackson WY")
    except:
        return 43.4, -110.7, "Jackson WY"

def load_queue(path):
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return []

def save_queue(path, queue):
    with open(path, 'w') as f:
        json.dump(queue, f)

def post_data(data):
    requests.post(SCRIPT_URL, json=data, timeout=10)

def post_supabase_detection(name, scientific_name, confidence, lat, lon, dawn, aci, time_category, now, temporal):
    try:
        payload = {
            "node_id":             NODE_ID,
            "species_name":        name,
            "raw_label":           scientific_name,
            "confidence":          confidence,
            "detected_at":         now.isoformat(),
            "location":            f"POINT({lon} {lat})",
            "is_dawn_chorus":      temporal.get("dawn_chorus_window") or dawn,
            "minutes_from_sunrise": temporal.get("minutes_from_sunrise"),
            "dawn_chorus_window":  temporal.get("dawn_chorus_window"),
            "phenological_week":   temporal.get("phenological_week"),
            "season":              temporal.get("season"),
        }
        r = _post_supabase(f"{SUPABASE_URL}/rest/v1/detections", payload)
        if r.status_code not in (200, 201):
            print(f"  Supabase detection error: {r.status_code} {r.text}")
    except Exception as ex:
        print(f"  Supabase detection exception: {ex}")

def post_supabase_aci(aci, time_category, dawn, now):
    try:
        payload = {
            "node_id": NODE_ID,
            "recorded_at": now.isoformat(),
            "aci_score": aci,
            "time_category": time_category,
            "dawn_chorus": dawn,
            "duration_secs": 15
        }
        r = _post_supabase(f"{SUPABASE_URL}/rest/v1/aci_logs", payload)
        if r.status_code not in (200, 201):
            print(f"  Supabase ACI error: {r.status_code} {r.text}")
    except Exception as ex:
        print(f"  Supabase ACI exception: {ex}")

def flush_queue(path):
    queue = load_queue(path)
    if not queue:
        return
    remaining = []
    for item in queue:
        try:
            post_data(item)
        except:
            remaining.append(item)
    save_queue(path, remaining)
    flushed = len(queue) - len(remaining)
    if flushed > 0:
        print(f"Flushed {flushed} queued items from {os.path.basename(path)}")

def get_time_category(now_utc, lat, lon):
    now_local = now_utc.replace(tzinfo=None)
    try:
        loc = LocationInfo(latitude=lat, longitude=lon)
        s = sun(loc.observer, date=now_local.date())
        sunrise = s['sunrise'].replace(tzinfo=None)
        sunset  = s['sunset'].replace(tzinfo=None)
        dawn_start = sunrise - timedelta(minutes=30)
        dawn_end   = sunrise + timedelta(minutes=60)
        dusk_start = sunset  - timedelta(minutes=30)
        dusk_end   = sunset  + timedelta(minutes=60)

        if dawn_start <= now_local <= dawn_end:
            return "Dawn"
        elif dawn_end < now_local <= sunrise + timedelta(hours=4):
            return "Morning"
        elif sunrise + timedelta(hours=4) < now_local <= sunset - timedelta(hours=2):
            return "Midday"
        elif sunset - timedelta(hours=2) < now_local < dusk_start:
            return "Afternoon"
        elif dusk_start <= now_local <= dusk_end:
            return "Dusk"
        else:
            return "Night"
    except:
        hour = now_local.hour
        if 5 <= hour < 9:   return "Dawn"
        elif 9 <= hour < 12:  return "Morning"
        elif 12 <= hour < 16: return "Midday"
        elif 16 <= hour < 19: return "Afternoon"
        elif 19 <= hour < 21: return "Dusk"
        else:                 return "Night"

def get_temporal_context(now, lat, lon):
    """Calculate all Phase 1 temporal fields for a detection."""
    now_local = now.replace(tzinfo=None)
    try:
        loc = LocationInfo(latitude=lat, longitude=lon)
        s = sun(loc.observer, date=now_local.date())
        sunrise = s['sunrise'].replace(tzinfo=None)

        minutes_from_sunrise = int((now_local - sunrise).total_seconds() / 60)
        dawn_chorus_window   = -30 <= minutes_from_sunrise <= 120

        day_of_year      = now.timetuple().tm_yday
        phenological_week = min(52, math.ceil(day_of_year / 7))

        if phenological_week <= 10:   season = "winter"
        elif phenological_week <= 18: season = "early_spring"
        elif phenological_week <= 26: season = "breeding"
        elif phenological_week <= 34: season = "post_breeding"
        elif phenological_week <= 44: season = "fall_migration"
        else:                         season = "late_fall"

        return {
            "minutes_from_sunrise": minutes_from_sunrise,
            "dawn_chorus_window":   dawn_chorus_window,
            "phenological_week":    phenological_week,
            "season":               season,
        }
    except Exception as ex:
        print(f"  Temporal context error: {ex}")
        return {
            "minutes_from_sunrise": None,
            "dawn_chorus_window":   None,
            "phenological_week":    None,
            "season":               None,
        }

def is_dawn_chorus(time_category):
    return time_category == "Dawn"

def calculate_aci(wav_file):
    try:
        import wave
        with wave.open(wav_file, 'r') as wf:
            n_frames = wf.getnframes()
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            framerate = wf.getframerate()
            raw = wf.readframes(n_frames)

        if sampwidth == 2:
            samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
        elif sampwidth == 4:
            samples = np.frombuffer(raw, dtype=np.int32).astype(np.float32)
        else:
            return None

        if n_channels > 1:
            samples = samples[::n_channels]

        max_val = np.max(np.abs(samples))
        if max_val == 0:
            return 0.0
        samples = samples / max_val

        chunk_size = framerate // 4
        n_chunks = len(samples) // chunk_size
        if n_chunks < 2:
            return None

        aci_values = []
        for i in range(n_chunks):
            chunk = samples[i * chunk_size:(i + 1) * chunk_size]
            spectrum = np.abs(np.fft.rfft(chunk))
            if np.sum(spectrum) > 0:
                aci = np.sum(np.abs(np.diff(spectrum))) / np.sum(spectrum)
                aci_values.append(aci)

        if not aci_values:
            return None

        return round(float(np.mean(aci_values)), 3)

    except Exception as ex:
        print(f"ACI calculation error: {ex}")
        return None

def get_insect_activity_label(aci, time_category):
    if aci is None:
        return ""
    if time_category == "Night":
        if aci > 0.65: return "High insect activity"
        elif aci > 0.50: return "Moderate insect activity"
        else: return "Low insect activity"
    elif time_category in ["Dusk", "Dawn"]:
        if aci > 0.60: return "Active transition chorus"
        else: return "Quiet transition period"
    return ""

print("Loading model...")
analyzer = Analyzer()
sign_in()
print("Ready. Listening continuously. Press Ctrl+C to stop.\n")

while True:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"/home/magora/recording_{timestamp}.wav"
    now = datetime.now(timezone.utc)

    result = subprocess.run([
        "arecord", "-D", "hw:adau7002,0",
        "-c2", "-r", "48000", "-f", "S32_LE",
        "-d", "15", filename
    ], capture_output=True)

    if not os.path.exists(filename):
        print(f"Recording failed, skipping")
        continue

    apply_highpass_filter(filename)

    try:
        lat, lon, location_name = get_location()
        aci = calculate_aci(filename)
        time_category = get_time_category(now, lat, lon)
        temporal = get_temporal_context(now, lat, lon)
        dawn = temporal.get("dawn_chorus_window") or is_dawn_chorus(time_category)
        dawn_label = "Yes" if dawn else "No"
        insect_label = get_insect_activity_label(aci, time_category)

        if dawn:
            mins = temporal.get("minutes_from_sunrise")
            mins_str = f" (+{mins} min from sunrise)" if mins is not None else ""
            print(f"{now.strftime('%H:%M:%S')} DAWN CHORUS WINDOW{mins_str}")

        # ACI — post to both Sheets and Supabase
        aci_data = {
            "type": "aci",
            "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "location": location_name,
            "lat": lat,
            "lon": lon,
            "aci_score": aci if aci is not None else "",
            "time_category": time_category,
            "dawn_chorus": dawn_label
        }
        try:
            post_data(aci_data)
            if insect_label:
                print(f"{now.strftime('%H:%M:%S')} {insect_label} | ACI: {aci} | {time_category}")
        except:
            queue = load_queue(ACI_QUEUE_FILE)
            queue.append(aci_data)
            save_queue(ACI_QUEUE_FILE, queue)

        if aci is not None:
            post_supabase_aci(aci, time_category, dawn, now)

        # Bird detection — post to both Sheets and Supabase
        recording = Recording(
            analyzer,
            filename,
            lat=lat, lon=lon, date=now.date(),
            min_conf=MIN_CONF
        )
        recording.analyze()

        if recording.detections:
            for d in recording.detections:
                name = d['common_name']
                if name in EXCLUDE:
                    continue
                print(f"{now.strftime('%H:%M:%S')} {name} - {d['confidence']:.2f} | ACI: {aci} | {time_category} | Dawn: {dawn_label}")
                bird_data = {
                    "type": "bird",
                    "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "common_name": name,
                    "scientific_name": d['scientific_name'],
                    "confidence": round(d['confidence'], 2),
                    "lat": lat,
                    "lon": lon,
                    "location": location_name,
                    "dawn_chorus": dawn_label,
                    "aci_score": aci if aci is not None else ""
                }
                try:
                    post_data(bird_data)
                except:
                    queue = load_queue(QUEUE_FILE)
                    queue.append(bird_data)
                    save_queue(QUEUE_FILE, queue)
                    print(f"  Queued (no internet)")

                post_supabase_detection(
                    name, d['scientific_name'],
                    round(d['confidence'], 2),
                    lat, lon, dawn, aci, time_category, now, temporal
                )
        else:
            aci_str = f" | ACI: {aci}" if aci is not None else ""
            cat_str = f" | {time_category}"
            insect_str = f" | {insect_label}" if insect_label else ""
            print(f"{now.strftime('%H:%M:%S')} No birds detected{aci_str}{cat_str}{insect_str}")

    except Exception as ex:
        print(f"Analysis error: {ex}")
    finally:
        if os.path.exists(filename):
            os.remove(filename)

    flush_queue(QUEUE_FILE)
    flush_queue(ACI_QUEUE_FILE)
