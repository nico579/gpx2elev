# gpx2elev 0.4.0 : interface web pour les versions ordinateur / Desktop web interface

- Windows, Linux et macOS ouvrent une page locale dans le navigateur ; Qt est retiré des dépendances et des bundles.
- Serveur, langue FR/EN, vérificateur de version et systray nico579-commons, comme gpxsolar, blink2video, watch2notif et lidar2map. Même menu : Ouvrir, Mettre à jour, Redémarrer, Arrêter et Créer un raccourci.
- Import GPX et glisser-déposer, modèles, annulation, cache existant, CSV et mises à jour vérifiées conservés.
- Profil terrain/GPX, heures, curseur, zoom, déplacement et plein écran conservés au changement FR/EN.
- Tests HTTP et Playwright du navigateur, des mises en page et du serveur des exécutables sur les quatre plateformes.
- Protocole de calcul et application Android inchangés.

Desktop versions now use a local browser page and the common nico579-commons system tray. Calculation, cache, profiles, cursor, CSV exports, languages and verified updates are retained; Qt is removed. Browser and packaged-server regressions cover the workflows. Android and the calculation protocol are unchanged.
