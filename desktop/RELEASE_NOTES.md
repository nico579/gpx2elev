# gpx2elev 0.3.5 — Heure GPX et curseur / GPX time and chart cursor

**FR**

- **Heure locale GPX sur l'axe horizontal**, en complément de la distance, sur Android et ordinateur. Les heures absentes ou invalides sont indiquées par **—** ; l'affichage ne relie pas des horodatages manquants, des segments distincts ou une horloge qui recule.
- **Curseur vertical au clic ou au toucher** : distance et heure sur l'axe horizontal, altitude du terrain lissé et altitude de la mesure GPX. Les arrêts conservent les mesures originales ; au zoom entre deux points, une lecture interpolée est identifiée par **GPX interpolé**.
- **Sélection conservée** au zoom, au déplacement, au passage en plein écran et au retour, ainsi qu'au changement **FR/EN**. Les libellés, nombres et dates suivent la langue choisie. Glisser continue à déplacer la vue.
- Les fonctions de la version précédente sont incluses : **courbes terrain/GPX superposées**, **zoom et déplacement**, **plein écran**, **menu de vérification et d'installation des mises à jour**, et les **huit correctifs** de l'audit.

Depuis la **0.3.4**, utiliser **Mises à jour** dans l'application pour installer cette version. Les versions plus anciennes sans ce menu nécessitent une installation manuelle. Android conserve l'identifiant `com.nico.gpx2elev` et le certificat de signature ; les GPX et réglages sont préservés lors de la mise à jour. Extraire les bundles bureau avant de les lancer et conserver le nom du dossier `gpx2elev` (`gpx2elev.app` sur macOS).

**EN**

- **GPX local time on the horizontal axis**, alongside distance, on Android and desktop. Missing or invalid times appear as **—**; time ticks do not bridge missing timestamps, separate segments or a clock reversal.
- **Vertical cursor on click or tap**: distance and time on the horizontal axis, smoothed terrain elevation and the GPX measurement. Original measurements at stops are retained; when zooming between observations, **Interpolated GPX** identifies an interpolated reading.
- **Selection survives** zooming, panning, entering and leaving full screen, and **FR/EN** changes. Labels, numbers and dates follow the selected language. Dragging continues to pan the view.
- Previous features are included: **overlaid terrain/GPX curves**, **zoom and pan**, **full screen**, **manual update checks and installation**, and the **eight audit fixes**.

From **0.3.4**, use **Updates** in the application to install this version. Older versions without that menu require a manual upgrade. Android retains the `com.nico.gpx2elev` identifier and signing certificate; GPX tracks and settings are preserved during the update. Extract desktop bundles before launching and retain the folder name `gpx2elev` (`gpx2elev.app` on macOS).

**Fichiers / Assets** : APK Android, Windows x64, Linux x64, macOS Intel et Apple Silicon, tous en **0.3.5** / all at **0.3.5**. Tests, contrôles des exécutables natifs, certificat Android et SHA-256 vérifiés avant publication / tests, native executable checks, Android certificate and SHA-256 verified before publication. Rapports joints / verification reports included. Les applications macOS ne sont pas notarisées / macOS apps are not notarized.

Protocole numérique inchangé / calculation protocol unchanged : **pas 5 m / 5 m spacing, gaussienne / Gaussian σ = 20 m, hystérésis / hysteresis 2 m**.

[Audit détaillé et tests de régression / Detailed audit and regression tests](https://github.com/nico579/gpx2elev/blob/v0.3.5/AUDIT_CODE.md).
