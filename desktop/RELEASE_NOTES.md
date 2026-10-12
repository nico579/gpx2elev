# gpx2elev 0.4.0 : interface web pour les versions ordinateur / Desktop web interface

- Windows, Linux et macOS ouvrent une page locale dans le navigateur ; Qt est retiré des dépendances et des bundles.
- Serveur, langue FR/EN, vérificateur de version et systray nico579-commons, comme gpxsolar, blink2video, watch2notif et lidar2map. Même menu : Ouvrir, Mettre à jour, Redémarrer, Arrêter et Créer un raccourci.
- Import GPX et glisser-déposer, modèles, annulation, cache existant, CSV et mises à jour vérifiées conservés.
- Profil terrain/GPX, heures, curseur, zoom, déplacement et plein écran conservés au changement FR/EN.
- Tests HTTP et Playwright du navigateur, des mises en page et du serveur des exécutables sur les quatre plateformes.
- Un profil déjà en cache sert avant tout appel réseau, sur ordinateur comme sur Android : une trace n'est calculée qu'une fois.
- Sur ordinateur, le cache ne se vide jamais seul : il n'est effacé que sur demande, après confirmation. Android garde sa limite de 512 Mo.
- Un GPX illisible transmis par le système affiche son erreur au lieu d'arrêter l'application ; un dépôt pendant un calcul dit quoi faire.
- Dépendances figées avec empreintes SHA-256, actions GitHub épinglées par SHA et suivies par Dependabot.
- Protocole de calcul inchangé.

Desktop versions now use a local browser page and the common nico579-commons system tray. Calculation, cache, profiles, cursor, CSV exports, languages and verified updates are retained; Qt is removed. Browser and packaged-server regressions cover the workflows. A cached profile is now used before any network call, on desktop and Android; the desktop cache is never emptied automatically, only on confirmed request. An unreadable GPX opened by the system shows an error instead of stopping the application. Dependencies are locked with SHA-256 hashes; GitHub actions are pinned by SHA and tracked by Dependabot. The calculation protocol is unchanged.
