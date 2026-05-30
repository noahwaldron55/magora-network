# Contributing to Magora Network

Thank you for your interest in expanding the network. There are several ways to contribute.

## Adding a new node

The most valuable contribution is deploying a new listening station. Any location works —
urban gardens, rural farmland, forests, wetlands, high desert, mountain meadows.
Biodiversity data from everywhere is valuable.

Follow the [Quick start](README.md#quick-start) guide, then open an issue titled
**"New node — [your location]"** and we will add you to the network map.

## Code contributions

1. Fork the repository
2. Create a branch: `git checkout -b feature/your-feature-name`
3. Make your changes
4. Test on real hardware if possible
5. Open a pull request with a clear description of what changed and why

## Areas we need help with

- **Species classifiers** — frogs, bats, ultrasonic insects
- **Web portal** — React frontend for device registration and live map
- **Mobile app** — node monitoring and field sighting logging
- **Data visualisation** — species occurrence maps, ACI trend charts
- **Research export** — improved Darwin Core compliance, GBIF integration
- **Documentation** — setup guides, translations, video walkthroughs
- **Hardware variants** — AudioMoth integration, solar power configs

## Bug reports

Open a GitHub issue with:

- Your Pi model and OS version (`uname -a`)
- Full error output from `sudo journalctl -u birdnet.service -n 50`
- Your `location.json` (redact coordinates if you prefer)

## Data contributions

If you have existing acoustic recordings or species occurrence data from a location,
open an issue and we can discuss how to incorporate it into the database.

## Code of conduct

Be kind, be scientific, be curious. This project exists to help the natural world —
keep that as the north star in all contributions and discussions.
