# gpx2elev 0.6.5 : bibliothèque commune jusqu'à 1.0 / Shared library up to 1.0

Cette version ne change rien à l'usage, sur Android comme sur ordinateur. Le moteur publié sur PyPI accepte maintenant nico579-commons jusqu'à la 1.0. La 0.7, qui ajoute le téléchargement commun des fonds de carte, ne touche à rien de ce que gpx2elev emploie : hike2gpx, qui s'appuie sur le moteur de gpx2elev, ne pouvait pas l'installer tant que gpx2elev la refusait.

- Le moteur publié sur PyPI accepte nico579-commons de 0.5.1 à 0.x (`>=0.5.1,<1`).
- Les verrous de l'application de bureau passent à nico579-commons 0.7.0 ; aucune autre dépendance ne bouge.

---

This version changes nothing in use, on Android or desktop. The engine published on PyPI now accepts nico579-commons up to 1.0. Version 0.7, which adds the shared map tile download, touches nothing gpx2elev uses: hike2gpx, which builds on the gpx2elev engine, could not install it while gpx2elev refused it.

- The engine published on PyPI accepts nico579-commons 0.5.1 to 0.x (`>=0.5.1,<1`).
- The desktop application's locks move to nico579-commons 0.7.0; no other dependency changes.
