# gpx2elev — EN / FR

**[English documentation](https://github.com/nico579/gpx2elev/blob/main/README.en.md) | [Documentation française](https://github.com/nico579/gpx2elev/blob/main/README.md)**

**Version commune 0.3.0 : APK Android et quatre bundles Python construits et vérifiés sur GitHub Actions.** Nouvel identifiant Android : `com.nico.gpx2elev`. Android l'installe comme une nouvelle application ; les données de 0.1/0.2 ne sont pas migrées automatiquement.

**Shared version 0.3.0: Android APK and all four Python bundles built and verified on GitHub Actions.** New Android identifier: `com.nico.gpx2elev`. Android installs it as a new application; local data from 0.1/0.2 are not automatically migrated.

Sélecteur **FR / EN** sur Android et sur le bureau : choix mémorisé, changement immédiat sans recalcul, écrans et messages traduits, nombres adaptés à la langue. README anglais et français reliés, inclus dans les bundles. Protocole et résultats numériques inchangés.

**FR / EN** selector on Android and desktop: saved choice, immediate switching without recalculation, translated screens and messages, language-specific numbers. Linked English and French README files are included in the bundles. Unchanged protocol and numerical results.

- **Android 8.0 et supérieur** : `gpx2elev-0.3.0.apk`, APK signé de la version Android 0.3.0, avec ouverture et partage des GPX vers gpx2elev.
- **Windows x64** : ZIP à extraire, puis ouvrir `gpx2elev.exe` dans son dossier.
- **Linux x64** : TAR.GZ à extraire, puis lancer `gpx2elev` ; construit sur Ubuntu 22.04.
- **macOS Intel et Apple Silicon** : deux ZIP contenant `gpx2elev.app`. Les applications ne sont pas notarisées par Apple ; la première ouverture peut demander « Ouvrir quand même » dans les réglages de confidentialité et sécurité.

Ouverture GPX par sélection, glisser-déposer et chemin de fichier. D+, D−, distance et profil d'altitude ; comparaison avec le GPX brut et filtré ; exports des résultats et du profil en CSV ; calculs en tâche de fond avec annulation et cache hors connexion.

Même protocole que l'application Android : **pas 5 m, gaussienne σ = 20 m, hystérésis 2 m**. Repli : **IGN LiDAR HD → Mapterhorn → FABDEM → Copernicus → SRTM90**. Un seul modèle couvre chaque trace.

Les builds natifs exécutent les tests du moteur, des lecteurs et de l'interface, puis un contrôle du véritable exécutable incluant Qt, GDAL/GeoTIFF et WebP. Les rapports et SHA-256 sont joints. Le contrôle local sur la trace personnelle du 4 octobre retrouve **735,128566 m / 735,149565 m** et toutes les altitudes lissées de la référence Android/Python ; aucune trace personnelle n'est publiée.

Le D+ reste une estimation dépendant des coordonnées et du filtrage. L'APK conserve la signature de la version 0.1 ; son SHA-256 et son rapport `verification-android.json` sont joints dans cette même release. L'APK et les quatre bundles portent tous la version 0.3.0.

Elevation gain is an estimate affected by coordinates and filtering. Android uses the same signing key as 0.1. The APK and standalone desktop bundles all use version 0.3.0. SHA-256 checksums and verification reports are included. macOS bundles are not notarized. The first calculation requires Internet access; complete cached profiles work offline.
