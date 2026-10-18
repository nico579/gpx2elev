# gpx2elev 0.6.2 : bibliothèque commune 0.5 / Shared library 0.5

Cette version fait passer gpx2elev à la version 0.5.1 de nico579-commons, la bibliothèque commune déjà utilisée par gpxsolar, lidar2map, blink2video et watch2notif. Le calcul du dénivelé et l'analyse des barrières ne changent pas.

- L'assistant de mise à jour garde chaque argument au redémarrage, y compris un argument vide (correctif de nico579-commons 0.5.1).
- Les restes d'une mise à jour interrompue, à côté de l'installation, sont effacés en tâche de fond au démarrage.
- Sous Linux, l'icône de la zone de notification parle le protocole StatusNotifierItem par D-Bus (jeepney), comme dans les autres applications : son menu s'ouvre aussi sous Wayland quand le bureau a un hôte (GNOME avec l'extension AppIndicator, KDE).
- Le moteur publié sur PyPI s'installe désormais à côté des applications qui utilisent nico579-commons 0.5.

---

This version moves gpx2elev to nico579-commons 0.5.1, the shared library already used by gpxsolar, lidar2map, blink2video and watch2notif. Elevation computation and barrier analysis are unchanged.

- The update helper keeps every argument when restarting, including an empty one (nico579-commons 0.5.1 fix).
- Leftovers of an interrupted update next to the installation are removed in the background at startup.
- On Linux, the notification area icon speaks the StatusNotifierItem protocol over D-Bus (jeepney), like the other applications: its menu also opens under Wayland when the desktop has a host (GNOME with the AppIndicator extension, KDE).
- The engine published on PyPI can now be installed alongside applications that use nico579-commons 0.5.
