# gpx2elev 0.3.6 — Affichage Windows corrigé / Windows layout fix

**FR**

- **Chiffres de dénivelé et de distance entièrement lisibles** après agrandissement ou maximisation de la fenêtre. Sur les écrans peu hauts, notamment avec la mise à l'échelle Windows, la page défile au lieu de comprimer les cartes et couper les chiffres.
- **Commandes du graphique séparées de la courbe et de ses axes**, sans chevauchement. Le zoom, le déplacement, le curseur, le plein écran et le changement FR/EN restent disponibles.
- Les fonctions de la 0.3.5 sont incluses : courbes terrain/GPX superposées, heure locale GPX sur l'axe horizontal, curseur vertical avec distance, heure et deux altitudes, et menu de mises à jour.

Utiliser **Mises à jour** dans l'application pour installer la **0.3.6** depuis la 0.3.4 ou la 0.3.5. Les versions plus anciennes sans ce menu nécessitent une installation manuelle. Extraire les bundles bureau avant de les lancer et conserver le nom du dossier `gpx2elev` (`gpx2elev.app` sur macOS). Les GPX et réglages sont conservés ; l'identifiant et le certificat Android restent identiques.

**EN**

- **Elevation gain, loss and distance remain fully readable** after resizing or maximizing the window. On shorter screens, including scaled Windows displays, the page scrolls instead of compressing the cards and clipping their numbers.
- **Chart controls stay separate from the curve and its axes**, without overlap. Zoom, pan, the cursor, full screen and FR/EN switching remain available.
- All 0.3.5 features are included: overlaid terrain/GPX curves, GPX local time on the horizontal axis, a vertical cursor with distance, time and both elevations, and the update menu.

Use **Updates** in the application to install **0.3.6** from 0.3.4 or 0.3.5. Older versions without that menu require a manual upgrade. Extract desktop bundles before launching and retain the folder name `gpx2elev` (`gpx2elev.app` on macOS). GPX tracks and settings are preserved; the Android identifier and signing certificate are unchanged.

**Fichiers / Assets** : APK Android, Windows x64, Linux x64, macOS Intel et Apple Silicon, tous en **0.3.6** / all at **0.3.6**. Tests, contrôles des exécutables natifs, certificat Android et SHA-256 vérifiés avant publication / tests, native executable checks, Android certificate and SHA-256 verified before publication. Rapports joints / verification reports included. Les applications macOS ne sont pas notarisées / macOS apps are not notarized.

Protocole numérique inchangé / calculation protocol unchanged : **pas 5 m / 5 m spacing, gaussienne / Gaussian σ = 20 m, hystérésis / hysteresis 2 m**.

[Audit détaillé et tests de régression / Detailed audit and regression tests](https://github.com/nico579/gpx2elev/blob/v0.3.6/AUDIT_CODE.md).
