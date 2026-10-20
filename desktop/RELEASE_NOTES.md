# gpx2elev 0.6.4 : bibliothèque commune 0.6 / Shared library 0.6

Cette version ne change rien à l'usage, sur Android comme sur ordinateur. Elle accepte nico579-commons 0.6, la bibliothèque commune des applications de bureau, qui apporte un module grâce auquel les processus enfants meurent avec leur application, même quand celle-ci est tuée ou que sa console est fermée. hike2gpx, qui s'appuie sur le moteur de gpx2elev, en a besoin pour ne plus laisser de moteur BRouter orphelin derrière lui.

- Le moteur publié sur PyPI accepte nico579-commons de 0.5.1 à 0.6.x (`>=0.5.1,<0.7`).
- Les verrous de l'application de bureau passent à nico579-commons 0.6.0 ; aucune autre dépendance ne bouge.

---

This version changes nothing in use, on Android or desktop. It accepts nico579-commons 0.6, the library shared by the desktop applications, which adds a module that makes child processes die with their application, even when it is killed or its console is closed. hike2gpx, which builds on the gpx2elev engine, needs it so as to stop leaving orphan BRouter engines behind.

- The engine published on PyPI accepts nico579-commons 0.5.1 to 0.6.x (`>=0.5.1,<0.7`).
- The desktop application's locks move to nico579-commons 0.6.0; no other dependency changes.
