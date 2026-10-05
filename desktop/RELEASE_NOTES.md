# gpx2elev 0.3.2 — Cache / cache management

**FR** : affichage de la taille totale du cache et du détail profils/tuiles ; bouton **Vider le cache** avec confirmation sur Android et bureau. Suppression en tâche de fond, désactivée pendant un calcul. GPX, réglages, exports et résultat affiché conservés. Les altitudes devront être téléchargées à nouveau. Plafonds existants : 64 Mio pour les profils, 512 Mio pour les tuiles, appliqués après les calculs.

**EN**: total cache size and profile/tile breakdown; **Clear cache** button with confirmation on Android and desktop. Background deletion, disabled during calculations. The GPX, settings, exports and displayed result are kept. Elevations will need to be downloaded again. Existing limits: 64 MiB for profiles, 512 MiB for tiles, applied after calculations.

APK Android et quatre bundles Python construits et validés sur GitHub Actions, tous en **0.3.2**. Android conserve l’identifiant et la signature de 0.3.1 : mise à jour directe. Protocole numérique inchangé : **pas 5 m, σ = 20 m, hystérésis 2 m**. Rapports de validation et SHA-256 joints.

Android APK and four standalone Python bundles built and verified by GitHub Actions, all at **0.3.2**. Same Android identifier and signing key as 0.3.1, allowing direct updates. Unchanged calculation protocol: **5 m spacing, σ = 20 m, 2 m hysteresis**. Verification reports and SHA-256 checksums included.

Windows x64, Linux x64, macOS Intel et Apple Silicon. Extraire le bundle avant de lancer l’application. Les applications macOS ne sont pas notarisées. Le D+ reste une estimation dépendant des coordonnées et du filtrage.

Windows x64, Linux x64, Intel and Apple Silicon macOS. Extract the bundle before launching. macOS apps are not notarized. Elevation gain remains an estimate affected by coordinates and filtering.
