# gpx2elev

**[English](README.en.md) | [Français](README.md)**

**[Download for Android, Windows, Linux and macOS](https://github.com/nico579/gpx2elev/releases/latest)**: a signed Android APK and [standalone Python desktop bundles](desktop/README.en.md), using the same calculation protocol and elevation sources.

**gpx2elev** estimates elevation gain (D+), elevation loss (D−) and the elevation profile of a GPX track. The Android application uses Kotlin and Jetpack Compose.

## Usage

Android 0.3.1 uses the new identifier `com.nico.gpx2elev`. Android installs it as a new application alongside versions 0.1/0.2; their local data are not migrated automatically. Import your GPX tracks into the new application.

1. Install the APK on Android 8.0 or later, or extract the desktop bundle for your platform.
2. Select **EN / FR** at the top of the screen. The selection is saved. The first launch uses French on a French-language device, and English otherwise.
3. Choose a GPX track. On Android, you can also open or **share a GPX file with gpx2elev**. On desktop, you can drop it into the window.
4. The first calculation downloads elevation data. The screen shows progress, the selected source, ascent, descent, distance and the smoothed elevation profile.
5. Expand the GPX comparison to see the raw sum of elevation changes and the filtered GPX elevations. Export results as CSV.

Android accepts GPX, XML, text and binary MIME types through `EXTRA_STREAM`, `ClipData` or a file URI; the contents must be a valid GPX. See [Android's sharing documentation](https://developer.android.com/develop/ui/compose/sharing/receive).

The last valid track is restored when the app opens. Complete profiles are cached with integrity checks. Previously cached tracks can be calculated offline while their profiles remain cached. Profile and tile caches are limited to 64 MB and 512 MB respectively.

## Calculation protocol

**Distance resampling: 5 m. Spatial Gaussian: σ = 20 m. Vertical hysteresis: 2 m.** These parameters are fixed.

The Gaussian has an 80 m radius and uses odd extension at both ends, repeated for short segments. The actual endpoint is included even when it is off the 5 m grid. Hysteresis confirms direction reversals while preserving successive small rises within an ascent. Filtered endpoints remain included. Each GPX segment is calculated separately.

Original XY coordinates are preserved. Resampling follows the GPX polyline; it does not correct its position. Repeated coordinates at a stop retain the last observation for resampling, while all original elevations remain in the raw GPX sum. Longitudes are unwrapped when crossing the antimeridian.

The raw GPX total sums successive elevation changes within each segment. The filtered GPX uses the same protocol as the terrain model. Missing GPX elevations are reported and do not prevent terrain-based calculation. Changing language does not affect calculations, caches or CSV schemas.

## Model fallback

| Rank | Model | Reader |
|---:|---|---|
| 1 | IGN LiDAR HD | Géoplateforme API, `ign_lidar_hd_mnt_mono_wld`, seven decimal places, batches of at most 5,000 positions |
| 2 | Mapterhorn | Terrarium WebP tiles, zoom 13, parent tiles if needed, bilinear interpolation between pixel centres |
| 3 | FABDEM 1.2 | Float32 GeoTIFF extracted from ZIP/ZIP64 using partial HTTP requests; bilinear interpolation |
| 4 | Copernicus GLO-30 | Float32 GeoTIFF COG; bilinear interpolation |
| 5 | SRTM90 | SRTM3 v2.1 HGT files from the Kurviger mirror; bilinear interpolation |

This order comes from the comparison on common tracks in mainland France. The first model supplying **every elevation of the track** is selected. Missing data or a network failure triggers the next model. One profile uses one source throughout; missing values are never replaced with zero or filled using GPX elevations. The selected model and fallback reasons are displayed. Desktop also permits manual model selection.

Android reads Copernicus COG blocks using HTTP range requests; desktop downloads the relevant COG tile before interpolation. Android's FABDEM/Copernicus readers support WGS84 tiled Float32 GeoTIFFs with Deflate compression and predictors 1, 2 and 3. PixelIsPoint/PixelIsArea georeferencing and interpolation across tile boundaries are handled. Unsupported encodings trigger fallback.

Import limits: 20 MB, 250,000 original points and 300,000 resampled positions. GPX 1.0/1.1, namespaces and `rte` routes are accepted. Invalid coordinates and XML DTD declarations are rejected.

This is an estimate under a defined protocol, rather than a field-validated measurement of the true elevation gain. Horizontal position accuracy matters particularly near cliffs.

## Android build

Release APKs are built by GitHub Actions. For local development, open the repository in Android Studio, or run `build.ps1` with PowerShell. The script requires JDK 17 or 21 and an Android SDK configured in `local.properties`, which is excluded from Git. The project uses Gradle 8.7, AGP 8.5.2, Kotlin 1.9.24 and SDK 34.

```powershell
./build.ps1
./build.ps1 -Mode tests
```

APK output: `app/build/outputs/apk/release/app-release.apk`. Local releases use the project's development key in `app/debug.keystore`, excluded from Git. Keep that key locally for compatible updates. Clones without it use Gradle's default Android development key. The OBD2 Dash key is not used.

Android and Python share version **0.3.1**, defined in `VERSION`. The [Release workflow](.github/workflows/release.yml) builds the signed APK and all four desktop bundles on GitHub for each `v*` tag. Tests, versions, the signing certificate and SHA-256 checksums are verified before publishing one combined release. The Android key is supplied through the encrypted `ANDROID_KEYSTORE_BASE64` repository secret, never through Git.

For a new release, update `VERSION` and `desktop/gpx2elev/assets/version.txt`, increment the Android `versionCode`, and push the matching tag. Version mismatches block publication.

## Verification

The synthetic tests cover endpoints, separated segments, stops, the antimeridian, missing elevations, cache integrity, cancellation and fallback order. Real public GeoTIFF snippets and ZIP/ZIP64 archives check decoding, georeferencing and extraction. Robolectric tests render Android screens, exercise sharing, cached calculations and CSV export. Both languages and persisted language selection are tested.

The local personal reference contains 1,500 original points and 4,467 resampled positions. Its archived IGN profile gives **735.128566 m ascent / 735.149565 m descent**. Kotlin and Python compare every smoothed elevation and both GPX totals against that reference. Personal fixtures are excluded from Git and the APK; those tests are skipped after cloning when the fixtures are absent.

`build.ps1 -Live` additionally checks all five readers against current public data and calculates the reference IGN profile. This optional test downloads about 30 MB on first use. Current IGN responses may differ from archived responses; protocol regression tests preserve the archived reference. Reports and rendered screenshots are written to `build/qa/`. No physical Android phone was connected during the local build validation.

See the [desktop development instructions](desktop/README.en.md) and [public fixture attributions](app/src/test/resources/README.md).

## Privacy and data attribution

Coordinates are sent to IGN to obtain elevations. Other models use downloaded public tiles or blocks. GPX tracks, profiles and tiles remain in local application storage. Android cloud backups and automatic data transfers are disabled. No telemetry and no personal GPX tracks are included in GitHub or the bundles.

- [IGN / Géoplateforme](https://cartes.gouv.fr/aide/fr/guides-utilisateur/utiliser-les-services-de-la-geoplateforme/calcul-altimetrique/): IGN data under the French Open Licence.
- [Mapterhorn data access](https://mapterhorn.com/data-access/) and [provider attributions](https://mapterhorn.com/attribution/).
- [FABDEM 1.2, Neal, Hawker et al., University of Bristol](https://research-information.bris.ac.uk/en/datasets/fabdem-v1-2/): CC BY-NC-SA 4.0; DOI `10.5523/bris.s5hqmjcdj8yo2ibzi9b4ew3sn`.
- [Copernicus DEM GLO-30 on AWS](https://registry.opendata.aws/copernicus-dem/): © DLR e.V. 2010–2014 and © Airbus Defence and Space GmbH 2014–2018; funded by the European Union under Copernicus; Copernicus DEM licence terms apply.
- [SRTM NASA/USGS, Kurviger mirror](https://srtm.kurviger.de/).
