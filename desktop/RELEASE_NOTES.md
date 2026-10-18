# gpx2elev 0.6.1 : barrières et passages / Barriers and access

Cette version corrige le contrôle de publication Android, qui attendait encore l'ancien nombre de tests. Les 112 tests incluent désormais la vérification des obstacles. Le paquet Python 0.6.0 était déjà disponible ; 0.6.1 réunit les applications Android et ordinateur dans la même release.

- Android et ordinateur affichent une vue du parcours avec les barrières, clôtures et restrictions d'accès répertoriées dans OpenStreetMap : blocages signalés en rouge, passages à vérifier en orange.
- Choix du déplacement à pied, à vélo ou en véhicule motorisé. L'inversion du sens du GPX recalcule les restrictions directionnelles, l'ordre des obstacles et les distances depuis le départ.
- Flèches de progression, zoom, déplacement et liste détaillée des obstacles. Les portions colorées couvrent jusqu'à 25 m de part et d'autre du franchissement, sans relier les segments GPX séparés.
- Données Overpass mises en cache pendant sept jours avant actualisation, consultables hors connexion avec indication de leur ancienneté. Une vérification indisponible est signalée et conserve le résultat d'altitude.
- Tests du moteur, du cache et des interfaces, avec contrôles des accès conditionnels, des passages répétés et des restrictions de sens.

Les environs du parcours sont transmis au service Overpass. Les données OSM sont incomplètes et peuvent ne pas refléter l'état actuel d'un portail : l'absence d'alerte ne garantit pas le passage. La vue est schématique, sans fond de carte. Données © contributeurs OpenStreetMap, ODbL.

---

This version fixes Android release validation, which still expected the previous test count. The 112 tests now include obstacle checks. Python package 0.6.0 was already available; 0.6.1 brings the Android and desktop applications together in one release.

- Android and desktop now show a route view with barriers, fences and access restrictions recorded in OpenStreetMap: reported blockages in red and crossings to check in orange.
- Walking, cycling and motor vehicle modes. Reversing the GPX direction recalculates directional restrictions, encounter order and distance from the start.
- Direction arrows, zoom, pan and obstacle details. Highlighted sections cover up to 25 m on either side of a crossing and never connect separate GPX segments.
- Overpass data are cached for seven days before refresh and remain available offline, with their age displayed. Unavailable checks are clearly identified and preserve the elevation result.
- Engine, cache and interface tests cover conditional access, repeated crossings and directional restrictions.

The route's surrounding area is sent to Overpass. OSM data are incomplete and may not reflect a gate's current state: no alert does not guarantee access. The route view is schematic, without a basemap. Data © OpenStreetMap contributors, ODbL.
