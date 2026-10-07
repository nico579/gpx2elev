# gpx2elev 0.3.3 — Courbes superposées et zoom / Profile overlay and zoom

**FR** : le graphique superpose le **terrain lissé en vert** et les **mesures originales du GPX en orange pointillé**, avec une échelle commune. Les arrêts, les points isolés et les segments sont conservés ; les altitudes manquantes interrompent la courbe GPX.

La navigation permet de zoomer sur les deux axes et de déplacer la vue : **molette et glisser sur ordinateur**, **pincement et glisser sur Android**. Les boutons de zoom et **Vue complète** sont disponibles. Le zoom retrouve les détails des points d'origine, avec une précision d'affichage adaptée. Le choix FR/EN conserve la vue courante.

**EN**: the chart overlays **smoothed terrain in green** and **original GPX measurements in dashed orange** on a shared scale. Stops, isolated observations and separate segments are preserved; missing elevations interrupt the GPX curve.

Zoom and pan on both axes using the **mouse wheel and dragging on desktop**, or **pinching and dragging on Android**. Zoom and **Full view** buttons are available. Zooming reveals the native observations with adaptive axis precision. Changing FR/EN keeps the current view.

APK Android et quatre bundles autonomes : **Windows x64, Linux x64, macOS Intel et Apple Silicon**, tous en **0.3.3**. Android conserve l'identifiant et la signature de 0.3.2 pour une mise à jour directe. Rapports de validation et SHA-256 joints.

Android APK and four standalone bundles: **Windows x64, Linux x64, Intel and Apple Silicon macOS**, all at **0.3.3**. The Android identifier and signing key match 0.3.2 for direct updates. Verification reports and SHA-256 checksums are included.

Protocole numérique : **pas 5 m, gaussienne σ = 20 m, hystérésis 2 m**. Le D+ reste une estimation dépendant des coordonnées et du filtrage. Extraire les bundles avant de les lancer ; les applications macOS ne sont pas notarisées.

Calculation protocol: **5 m spacing, Gaussian σ = 20 m, 2 m hysteresis**. Elevation gain remains an estimate affected by coordinates and filtering. Extract bundles before launching; macOS apps are not notarized.

L'[audit détaillé du code](https://github.com/nico579/gpx2elev/blob/main/AUDIT_CODE.md) accompagne ces changements. Les défauts qu'il recense restent à corriger ; cette release apporte la superposition et la navigation dans le graphique.

The [detailed code audit](https://github.com/nico579/gpx2elev/blob/main/AUDIT_CODE.md) accompanies these changes. Its findings remain to be fixed; this release adds profile overlay and chart navigation.
