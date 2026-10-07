# gpx2elev for Windows, Linux and macOS

**[English](README.en.md) | [Français](README.md)**

A Python desktop application with standalone bundles containing Python, Qt and elevation readers. **You do not need to install Python to use a bundle.**

[Download the latest release](https://github.com/nico579/gpx2elev/releases/latest). The same release includes the signed Android APK. Android and desktop share version **0.3.3**. GitHub Actions builds all five release assets and verifies them before publication.

## Open the application

- **Windows 10/11, x64:** extract the `windows-x64.zip` archive and open `gpx2elev/gpx2elev.exe`. Keep the entire extracted folder.
- **Linux, x64:** extract `linux-x64.tar.gz` and run `./gpx2elev/gpx2elev`. Built on Ubuntu 22.04; requires glibc 2.35 or later and desktop X11/Wayland display components. Python, Qt and GDAL are included.
- **macOS:** use `macos-arm64` for Apple Silicon or `macos-x64` for Intel, extract the archive and open `gpx2elev.app`. Bundles are tested on macOS 14 (Apple Silicon) and macOS 15 (Intel). They are not notarized; if blocked, use **System Settings → Privacy & Security → Open Anyway**.

Select **FR / EN** in the header. The choice is saved and takes effect immediately without recalculating. On first launch, French is selected for a French-language system and English otherwise. Displayed numbers follow the selected language. CSV schemas and numeric values remain stable across languages.

Choose a GPX, drop it into the window or pass its path on the command line. Finder file-open events are supported. On Windows you can select the executable through **Open with → Choose another app**. File associations are not changed automatically.

The first calculation requires Internet access. The screen shows the model, ascent, descent, distance, smoothed profile and raw/filtered GPX totals. CSV exports provide summary results and the full profile. Six exported decimal places help verification; they do not represent physical accuracy to the micrometre.

The chart overlays smoothed terrain (green) and original GPX measurements (dashed orange) on a shared scale. Use the mouse wheel to zoom around the pointer and drag to pan. **Zoom +**, **Zoom −** and **Full view** buttons are also available. Double-click to restore the full view. Segments remain separate and missing elevations interrupt the GPX curve.

## Same protocol as Android

1. Preserve XY coordinates and segment boundaries.
2. Resample every **5 m**, including the actual endpoint.
3. Read model elevations with bilinear interpolation between pixel centres.
4. Apply a spatial Gaussian with **σ = 20 m**, radius **80 m**, repeated odd extension at the ends.
5. Accumulate ascent/descent with **2 m** reversal hysteresis, retaining successive small rises and filtered endpoints.

Pause duration does not affect the calculation. Repeated coordinates retain the last observation for resampling; raw GPX totals retain all points. Antimeridian crossings are unwrapped. GPX 1.0/1.1, namespaces and `rte` routes are accepted. DTD declarations and invalid coordinates are rejected. Limits: 20 MB, 250,000 points and 300,000 resampled positions.

**Automatic fallback: IGN LiDAR HD → Mapterhorn → FABDEM 1.2 → Copernicus GLO-30 → SRTM90.** The ranking comes from mainland France tracks. One source must cover the entire track; another source or GPX elevations never fill its holes. Fallback reasons are displayed. A manual selection lets you test a particular source.

Mapterhorn uses zoom 13 and parent tiles when necessary. FABDEM tiles are extracted through partial ZIP/ZIP64 requests. Desktop downloads the relevant Copernicus COG tile before interpolation. SRTM uses SRTM3 v2.1 HGT. IGN uses `ign_lidar_hd_mnt_mono_wld`, batches of at most 5,000 positions and seven decimal places.

Elevation gain is an estimate affected by the terrain model, XY coordinates and filtering, rather than a field-validated measurement of the true gain.

## Cache and privacy

The window shows the total cache size and the profile/tile breakdown in MiB. **Clear cache** asks for confirmation, removes downloaded data and updates the size. The GPX, settings, exports and displayed result are kept. Future calculations will need to fetch elevations again. Clearing is disabled during a calculation or deletion. The 64 MiB and 512 MiB limits are applied after calculations; downloads can temporarily exceed them.

The last calculated track and complete profiles are stored locally. Profiles are keyed by coordinates and source configuration and protected by SHA-256 integrity checks. Cache limits are 64 MB for profiles and 512 MB for tiles. The last track is restored offline. Uncheck **Allow Internet access** to use cached profiles only.

Coordinates are sent to IGN to obtain elevations. Other sources use downloaded tiles. There is no telemetry or API key, and no personal tracks in GitHub or the bundles.

## Development and verification

From this directory, using Python 3.12:

```text
python -m venv .venv
python -m pip install -r requirements-build.txt
python -m gpx2elev
python -m unittest discover -s tests -v
python tools/build_bundle.py
```

Activate `.venv` before installation and launch. `build_bundle.py` builds for the current platform, runs the frozen executable and generates an archive, SHA-256 checksum and verification report in `release/`. GitHub builds use native Windows, Linux and both macOS architectures.

Tests cover the numerical protocol, readers, cache, cancellation, both languages and saved language selection. The frozen executable exercises file drop, background calculation, CSV export, Qt rendering, GDAL and WebP. The personal archived reference, when available locally, compares 4,467 smoothed elevations and totals **735.128566 / 735.149565 m**. It is not distributed and is skipped on GitHub.

The shared translation catalog is maintained in `../tools/prepare_translations.py`. Regenerate both platform catalogs with `python ../tools/prepare_translations.py`; a test checks they match.

Headless calculation is also available:

```text
python -m gpx2elev track.gpx --calculate --output result.json --csv result.csv
python -m gpx2elev track.gpx --calculate --offline --data-dir my-cache
```

The standalone executable accepts the same arguments. See [attributions and licences](THIRD_PARTY.md) and the [main README](../README.en.md).
