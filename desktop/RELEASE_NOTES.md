# gpx2elev 0.4.1 : cache, ouverture des GPX et licence des bundles / Cache, GPX opening and bundle license

- Un profil déjà en cache sert avant tout appel réseau, sur ordinateur comme sur Android : une trace déjà calculée ne repart plus sur Internet.
- Sur ordinateur, le cache ne se vide jamais seul : il n'est effacé que sur demande, après confirmation. Android garde sa limite de 512 Mo.
- Un GPX illisible transmis par le système affiche son erreur au lieu d'arrêter l'application ; un dépôt pendant un calcul dit quoi faire.
- Les bundles contiennent la licence GPL-3.0-or-later de gpx2elev, en plus de celles des dépendances.
- Un dénivelé nul s'affiche « 0 m », et l'axe du graphique devient « Distance (km) · heure locale ».
- Chaque push et chaque pull request testent Android et les quatre versions ordinateur ; dépendances figées avec empreintes SHA-256, actions GitHub épinglées par SHA et suivies par Dependabot.
- Protocole de calcul inchangé.

A cached profile is now used before any network call, on desktop and Android, so a track already calculated no longer goes back to the Internet. The desktop cache is never emptied automatically, only on confirmed request; Android keeps its 512 MB limit. An unreadable GPX opened by the system shows an error instead of stopping the application, and dropping a file during a calculation explains what to do. Bundles now include the gpx2elev GPL-3.0-or-later license. A zero elevation change reads "0 m" and the chart axis reads "Distance (km) · local time". Every push and pull request tests Android and the four desktop builds; dependencies are locked with SHA-256 hashes and GitHub actions are pinned by SHA. The calculation protocol is unchanged.
