gpx2elev est maintenant disponible en application Python de bureau, avec des bundles autonomes incluant Python.

- **Android 8.0 et supérieur** : `gpx2elev-0.1.apk`, APK signé de la version Android 0.1, avec ouverture et partage des GPX vers gpx2elev.
- **Windows x64** : ZIP à extraire, puis ouvrir `gpx2elev.exe` dans son dossier.
- **Linux x64** : TAR.GZ à extraire, puis lancer `gpx2elev` ; construit sur Ubuntu 22.04.
- **macOS Intel et Apple Silicon** : deux ZIP contenant `gpx2elev.app`. Les applications ne sont pas notarisées par Apple ; la première ouverture peut demander « Ouvrir quand même » dans les réglages de confidentialité et sécurité.

Ouverture GPX par sélection, glisser-déposer et chemin de fichier. D+, D−, distance et profil d'altitude ; comparaison avec le GPX brut et filtré ; exports des résultats et du profil en CSV ; calculs en tâche de fond avec annulation et cache hors connexion.

Même protocole que l'application Android : **pas 5 m, gaussienne σ = 20 m, hystérésis 2 m**. Repli : **IGN LiDAR HD → Mapterhorn → FABDEM → Copernicus → SRTM90**. Un seul modèle couvre chaque trace.

Les builds natifs exécutent les tests du moteur, des lecteurs et de l'interface, puis un contrôle du véritable exécutable incluant Qt, GDAL/GeoTIFF et WebP. Les rapports et SHA-256 sont joints. Le contrôle local sur la trace personnelle du 4 octobre retrouve **735,128566 m / 735,149565 m** et toutes les altitudes lissées de la référence Android/Python ; aucune trace personnelle n'est publiée.

Le D+ reste une estimation dépendant des coordonnées et du filtrage. L'APK Android conserve sa version 0.1 et sa signature ; son SHA-256 et son rapport `verification-android.json` sont joints dans cette même release. Les bundles Python portent la version 0.2.2.
