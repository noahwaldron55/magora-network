# Magora Network

A distributed acoustic biodiversity monitoring network for detecting and logging birds, insects, and soundscape health using low-cost hardware and open-source AI.

Each node is a Raspberry Pi Zero 2W with an INMP441 MEMS microphone running BirdNET for species identification and a continuous Acoustic Complexity Index (ACI) for insect and soundscape monitoring. All data flows into a central Supabase database with PostGIS geospatial indexing.

The goal is a community-owned network of listening stations that generates research-grade biodiversity data — accessible to citizen scientists, naturalists, and institutions alike.

---

## What it detects

- **Birds** — species identification via Cornell Lab's BirdNET, confidence-scored detections
- **Insects** — Acoustic Complexity Index as a biodiversity proxy (no additional hardware needed)
- **Soundscape health** — continuous ACI logging every 15 seconds, 24/7
- **Dawn chorus** — automatic detection of the morning chorus window relative to local sunrise

---

## Hardware

| Component | Model | Cost |
|---|---|---|
| Compute | Raspberry Pi Zero 2W | ~$15 |
| Microphone | INMP441 I2S MEMS | ~$5 |
| Storage | 32GB microSD (Class 10) | ~$8 |
| Power | USB-C 5V 2.5A adapter | ~$10 |

**Total per node: ~$38**

See [hardware/WIRING.md](hardware/WIRING.md) for full wiring instructions.

---

## Quick start

1. Flash Raspberry Pi OS Lite (64-bit) to a microSD card
2. Enable SSH and configure WiFi via the Raspberry Pi Imager
3. Wire the INMP441 microphone — see [hardware/WIRING.md](hardware/WIRING.md)
4. SSH into your Pi and run the setup script:

```bash
curl -sSL https://raw.githubusercontent.com/noahwaldron55/magora-network/main/firmware/setup.sh | bash
```

5. Edit `/home/magora/location.json` with your coordinates
6. Register your node at the Magora Network portal (coming soon)

---

## Data

All detections are logged to a central Supabase PostgreSQL database with PostGIS. The data is publicly readable and available in Darwin Core format for research use.

- **Detections:** `https://wqxmmuwrfltpaxnuddwk.supabase.co/rest/v1/detections`
- **ACI logs:** `https://wqxmmuwrfltpaxnuddwk.supabase.co/rest/v1/aci_logs`
- **Darwin Core view:** `https://wqxmmuwrfltpaxnuddwk.supabase.co/rest/v1/occurrences_view`

---

## Project structure

```
magora-network/
├── firmware/
│   ├── detect.py          # Main detection loop
│   ├── setup.sh           # One-command node setup (coming soon)
│   └── birdnet.service    # systemd service file
├── hardware/
│   └── WIRING.md          # INMP441 wiring guide
├── docs/
│   └── ARCHITECTURE.md    # System architecture
├── README.md
├── CONTRIBUTING.md
└── LICENSE
```

---

## Network map

| Node | Location | Habitat |
|---|---|---|
| birdnode1 | Southern Colorado | Montane scrub |

---

## Contributing

We welcome new nodes, code contributions, and classifier improvements. See [CONTRIBUTING.md](CONTRIBUTING.md) to get started.

---

## License

GNU General Public License v3.0 — see [LICENSE](LICENSE).

Built on [BirdNET-Analyzer](https://github.com/kahst/BirdNET-Analyzer) by the Cornell Lab of Ornithology.
