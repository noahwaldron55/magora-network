# System Architecture

  ## Overview

  ```
  [Pi Nodes]
      |  POST detections + ACI via HTTPS
      v
  [Supabase]  -- PostgreSQL + PostGIS
      |  REST API
      v
  [Backend API]  -- FastAPI (planned)
      |
      +--> [Web portal]  -- React (planned)
      |        Device registration
      |        Personal dashboard
      |        Live network map
      |
      +--> [Research API]  -- Darwin Core format
               GBIF-compatible occurrence export
               Bulk CSV / GeoJSON downloads
  ```

  ## Node software stack

  | Layer | Technology |
  |---|---|
  | OS | Raspberry Pi OS Lite 64-bit |
  | Detection model | BirdNET-Analyzer (Cornell Lab / TensorFlow Lite) |
  | Acoustic index | Custom ACI implementation (numpy) |
  | Sunrise timing | astral library |
  | Transport | HTTP POST via requests to Supabase REST API |
  | Service management | systemd (auto-restart, runs on boot) |

  ## Detection pipeline

  Each 15-second recording cycle:

1. `arecord` captures audio from the INMP441 via I2S
  2. ACI is calculated from the raw waveform (every cycle, regardless of bird activity)
  3. Time category is determined relative to local sunrise/sunset
  4. BirdNET analyzes the recording and returns species detections with confidence scores
  5. Non-wildlife sounds are filtered out (humans, vehicles, dogs, etc.)
  6. ACI log and any detections are POSTed to Supabase and Google Sheets
  7. Failed posts are queued locally and retried on the next cycle

  ## Database schema

  PostgreSQL 15 + PostGIS on Supabase.

  | Table | Description |
  |---|---|
  | `nodes` | Registered devices with geometry(Point) location |
  | `detections` | BirdNET results -- species, confidence, timestamp, location |
  | `aci_logs` | Continuous acoustic complexity index, every 15s recording |
    | `species` | Cornell/eBird taxonomy reference |
    | `occurrences_view` | Darwin Core materialised view for research export |

    ## Data standards

    Detections are exportable in Darwin Core format, compatible with:

    - GBIF (Global Biodiversity Information Facility)
    - iNaturalist
    - eBird
    - Any institution using standard biodiversity data pipelines

    ## Scaling considerations

    - The `detections` table is designed for monthly partitioning at scale
    - PostGIS GIST indexes support fast radius queries (all detections within 50km of a point)
    - ACI logs are kept separate from detections for clean time-series queries
