# gpx2elev for Windows, Linux and macOS

**[English](README.en.md) | [Français](README.md)**

A Python application with a local web interface and standalone bundles containing Python and elevation readers. Server, language, version checker, automatic updates and system tray: [nico579-commons](https://github.com/nico579/nico579-commons), like gpxsolar, blink2video, watch2notif and lidar2map. **You do not need to install Python to use a bundle.**

[Download the latest release](https://github.com/nico579/gpx2elev/releases/latest). The same release includes the signed Android APK. Android and desktop share version **0.5.0**. GitHub Actions builds all five release assets and verifies them before publication.

The interface adapts to resizing and maximizing. If the screen is too short, a scrollbar provides access to the bottom of the page; card values remain fully visible and controls do not overlap the chart.

## Open the application

- **Windows 10/11, x64:** extract `gpx2elev-windows-x86_64.zip` and open `gpx2elev-windows-x86_64/gpx2elev.exe`. Keep the entire extracted folder; you may rename or move it, preferably within your user folder.
- **Linux, x64:** extract `gpx2elev-linux-x86_64.tar.gz` and run `./gpx2elev-linux-x86_64/gpx2elev`. Built on Ubuntu 22.04; requires glibc 2.35 or later. Python and GDAL are included; the page runs in your browser.
- **macOS:** use `gpx2elev-macos-arm64.zip` for Apple Silicon or `gpx2elev-macos-x86_64.zip` for Intel, extract the archive and open `gpx2elev.app`. Bundles are tested on macOS 14 (Apple Silicon) and macOS 15 (Intel). They are not notarized; if blocked, use **System Settings → Privacy & Security → Open Anyway**.

Launching opens http://127.0.0.1:8769/ in your browser, or the next available port. The server listens only on this computer. A second launch joins the instance using the same data directory and forwards any GPX argument. The --new-instance option starts a separate server.

The icon is provided directly by nico579_commons.tray, with the same menu: **Open**, **Update to…** when a newer version is known, **Restart**, **Stop** and **Create a Desktop shortcut**. Closing the tab leaves the server running; use **Stop** in the icon or page to quit. The page also works without a notification area.

Select **FR / EN** in the header. The choice is saved and takes effect immediately without recalculating. On first launch, French is selected for a French-language system and English otherwise. Displayed numbers follow the selected language. CSV schemas and numeric values remain stable across languages.

Choose a GPX, drop it into the page or pass its path on the command line. The macOS bundle receives Finder files when launched. On Windows you can select the executable through **Open with → Choose another app**. File associations are not changed automatically.

The first calculation requires Internet access. The screen shows the model, ascent, descent, distance, smoothed profile and raw/filtered GPX totals. CSV exports provide summary results and the full profile. Six exported decimal places help verification; they do not represent physical accuracy to the micrometre.

The chart overlays smoothed terrain (green) and original GPX measurements (dashed orange) on a shared scale. Use the mouse wheel to zoom around the pointer and drag to pan. **Zoom +**, **Zoom −** and **Full view** buttons are also available. Double-click to restore the full view. Segments remain separate and missing elevations interrupt the GPX curve.

**Full screen** expands the chart; **Exit full screen** or **Escape** restores the normal window. Zoom and pan are preserved. A cache write failure keeps the result available and displays a warning about offline use.

The horizontal axis also shows **local time from GPX observations**. Click to place a vertical cursor showing distance, time, smoothed terrain elevation and GPX elevation. Dragging still pans the view. Zooming, full screen and FR/EN changes preserve the selection. When zooming between observations, **Interpolated GPX** identifies an interpolated value. Missing or invalid times appear as **—**; time ticks do not bridge missing timestamps, segment boundaries or clock reversals.

## Updates

Updates come from nico579-commons, as in gpxsolar, lidar2map and watch2notif. When a newer version is published, a banner at the top of the page announces it and the icon offers **Update to…**. **Install** downloads the bundle for this system, verifies its SHA-256 and contents, runs its self-test, then closes gpx2elev: a helper replaces the application folder, starts the new version and checks that it runs; on any failure it puts the previous version back. The open page reloads itself on the new version. Data and the last GPX remain in their separate folder.

The **⚙ Settings…** button, next to FR / EN, shows the installed version; **Check for updates** asks GitHub at once. Otherwise the common version checker asks GitHub at most once an hour and keeps its last answer; --offline disables this watcher. Installing always remains an explicit action.

Only the published bundle replaces itself: its folder must hold nothing else, and its parent folder must be writable. From Python source, or in a folder holding other files, the banner links to the release page for a manual update.

Versions 0.3 and 0.4 move to this version through their former **Updates** button: the release keeps the same bundles under their former names (`gpx2elev-<version>-windows-x64.zip`…) for them, with no need to download those by hand. Their mechanism left a `.gpx2elev-update-…` folder holding the whole previous version next to the application; the new version removes it at startup.

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

The last calculated track and complete profiles are stored locally. Profiles are keyed by coordinates and source configuration and protected by SHA-256 integrity checks. Caches are never emptied automatically: they are only cleared on request, from the interface and after confirmation. The last track is restored offline. Uncheck **Allow Internet access** to use cached profiles only.

Coordinates are sent to IGN to obtain elevations. Other sources use downloaded tiles. There is no telemetry or API key, and no personal tracks in GitHub or the bundles.

## Engine on PyPI

The calculation engine (GPX reading, terrain models and the 5 m / 20 m / 2 m protocol) is published on PyPI as `gpx2elev`. `pip install gpx2elev` installs the engine alone, without Qt, so that another program such as [GPX2DASH](https://github.com/nico579/gpx2dash) can use it instead of keeping a copy. `pip install "gpx2elev[gui]"` adds the desktop interface; bundles remain the simplest way to use it.

## Development and verification

From this directory, using Python 3.12:

```text
python -m venv .venv
python -m pip install -r requirements-build.txt
python -m gpx2elev
python -m unittest discover -s tests -v
python tools/build_bundle.py
python -m pip install -r requirements-test.txt
python -m playwright install --with-deps chromium
python tools/check_web_ui.py
```

Activate `.venv` before installation and launch. `build_bundle.py` builds for the current platform, runs the frozen executable and generates both archives (common and former names), their SHA-256 checksums and a verification report in `release/`; on the common archive it replays what the installer does: checked extraction, then the extracted executable's self-test. GitHub builds use native Windows, Linux and both macOS architectures.

Tests cover the numerical protocol, readers, cache, cancellation, both languages and saved language selection. The frozen executable checks HTTP routes, page assets, offline calculation, cursor, language, CSV export, cache, GDAL and WebP. Playwright tests real browser file selection, drop, zoom, pan, full screen, CSV downloads, cancellation, the common settings panel and responsive layouts. Qt is absent from the bundles. The personal archived reference, when available locally, compares 4,467 smoothed elevations and totals **735.128566 / 735.149565 m**. It is not distributed and is skipped on GitHub.

The shared translation catalog is maintained in `../tools/prepare_translations.py`. Regenerate both platform catalogs with `python ../tools/prepare_translations.py`; a test checks they match.

Headless calculation is also available:

```text
python -m gpx2elev track.gpx --calculate --output result.json --csv result.csv
python -m gpx2elev track.gpx --calculate --offline --data-dir my-cache
```

The standalone executable accepts the same arguments. See [attributions and licences](THIRD_PARTY.md) and the [main README](../README.en.md).

The common version checker queries GitHub at most once an hour to announce updates in the icon and page, retaining its last answer locally. Starting with --offline disables this watcher. Downloading and installing remain explicit.

To test the packaged browser server on Windows: python tools/check_web_ui.py --executable dist/gpx2elev/gpx2elev.exe. Add --browser-channel msedge to use installed Edge. Reports, screenshots and synthetic CSV exports are in qa/web/. Data remains in the OS data folder Nico/gpx2elev; --data-dir or GPX2ELEV_HOME select another location.

For a service or scripted test: python -m gpx2elev --serve-gui --no-browser --no-tray --port 8769.
