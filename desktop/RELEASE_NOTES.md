# gpx2elev 0.3.7 : moteur publié sur PyPI / Engine published on PyPI

**FR**

- **Le moteur de calcul est publié sur PyPI.** `pip install gpx2elev` installe le moteur seul (lecture GPX, modèles de terrain, protocole 5 m / 20 m / 2 m), sans Qt, pour qu'un autre programme comme GPX2DASH s'en serve sans en garder une copie. `pip install "gpx2elev[gui]"` ajoute l'interface de bureau.
- Aucun changement fonctionnel : l'application Android et les applications de bureau calculent et affichent exactement comme la 0.3.6.

Utiliser **Mises à jour** dans l'application pour installer la **0.3.7** depuis la 0.3.4, la 0.3.5 ou la 0.3.6. Les versions plus anciennes sans ce menu nécessitent une installation manuelle. Extraire les bundles bureau avant de les lancer et conserver le nom du dossier `gpx2elev` (`gpx2elev.app` sur macOS). Les GPX et réglages sont conservés ; l'identifiant et le certificat Android restent identiques.

**EN**

- **The calculation engine is published on PyPI.** `pip install gpx2elev` installs the engine alone (GPX reading, terrain models, 5 m / 20 m / 2 m protocol), without Qt, so that another program such as GPX2DASH can use it instead of keeping a copy. `pip install "gpx2elev[gui]"` adds the desktop interface.
- No functional change: the Android and desktop applications calculate and display exactly as in 0.3.6.

Use **Updates** in the application to install **0.3.7** from 0.3.4, 0.3.5 or 0.3.6. Older versions without that menu require a manual upgrade. Extract desktop bundles before launching and retain the folder name `gpx2elev` (`gpx2elev.app` on macOS). GPX tracks and settings are preserved; the Android identifier and signing certificate are unchanged.

**Fichiers / Assets** : APK Android, Windows x64, Linux x64, macOS Intel et Apple Silicon, tous en **0.3.7** / all at **0.3.7**. Tests, contrôles des exécutables natifs, certificat Android et SHA-256 vérifiés avant publication / tests, native executable checks, Android certificate and SHA-256 verified before publication. Rapports joints / verification reports included. Les applications macOS ne sont pas notarisées / macOS apps are not notarized.

Protocole numérique inchangé / calculation protocol unchanged : **pas 5 m / 5 m spacing, gaussienne / Gaussian σ = 20 m, hystérésis / hysteresis 2 m**.

[Audit détaillé et tests de régression / Detailed audit and regression tests](https://github.com/nico579/gpx2elev/blob/v0.3.7/AUDIT_CODE.md).
