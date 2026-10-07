# gpx2elev 0.3.4 — Plein écran, mises à jour et corrections / Full screen, updates and fixes

**FR**

- **Graphique en plein écran** sur Android et ordinateur, avec retour à la fenêtre normale sans perdre le zoom ni la position. Les courbes du terrain lissé et des mesures originales du GPX restent superposées ; zoom et déplacement sont disponibles dans les deux modes.
- **Mises à jour** depuis le menu **⋮ → Mises à jour** sur Android et le bouton **Mises à jour** sur ordinateur : recherche manuelle de la dernière release stable, notes, téléchargement adapté au système et contrôle SHA-256. Android vérifie aussi l'identifiant, la version et la signature de l'APK avant d'ouvrir l'installateur système. Sur ordinateur, le nouveau bundle passe son contrôle hors connexion avant remplacement et redémarrage ; l'ancienne installation est conservée pour le retour arrière. GPX et réglages sont préservés.
- **Huit bugs corrigés** : contexte XML GPX, validation des plages HTTP, lecture en fin de raster, récupération des tuiles corrompues, conservation du dernier GPX après un import invalide, résultat conservé si le cache ne peut pas être écrit, nettoyage des fichiers temporaires et robustesse face aux altitudes extrêmes.

**Installer cette version manuellement une première fois** pour disposer du bouton de mise à jour. Les mises à jour suivantes pourront être lancées depuis l'application. Extraire les bundles avant de les lancer et conserver le nom du dossier `gpx2elev` (`gpx2elev.app` sur macOS) pour permettre leur remplacement automatique. Android conserve l'identifiant et le certificat de signature de la version 0.3.3 pour une mise à jour directe.

Les profils Android FABDEM et Copernicus sont renouvelés pour écarter les anciennes données non vérifiées ; leur premier recalcul peut nécessiter Internet.

**EN**

- **Full-screen chart** on Android and desktop, returning to the normal window without losing zoom or pan. Smoothed terrain and original GPX measurements remain overlaid; zoom and pan work in both modes.
- **Updates** through **Menu ⋮ → Updates** on Android and the desktop **Updates** button: manually check the latest stable release, read its notes, download the correct platform asset and verify SHA-256. Android also checks APK identity, version and signing certificate before opening the system installer. Desktop verifies the new bundle offline before replacing and restarting the application; the previous installation is retained for rollback. GPX tracks and settings are preserved.
- **Eight bugs fixed**: GPX XML context, HTTP range validation, reads near raster EOF, corrupted tile recovery, last-track preservation after invalid imports, valid results retained when cache writes fail, temporary-file cleanup and robustness against extreme elevations.

**Install this version manually once** to obtain the update button. Future updates can then be started from the application. Extract bundles before launching and retain the folder name `gpx2elev` (`gpx2elev.app` on macOS) for automatic replacement. Android keeps the version 0.3.3 application identifier and signing certificate for direct upgrades.

Android FABDEM and Copernicus profiles are refreshed to exclude previously unverified data; their first recalculation may need Internet access.

**Fichiers / Assets** : APK Android, Windows x64, Linux x64, macOS Intel et Apple Silicon, tous en **0.3.4** / all at **0.3.4**. Rapports de validation et SHA-256 joints / verification reports and SHA-256 checksums included. Les applications macOS ne sont pas notarisées / macOS apps are not notarized.

Protocole numérique inchangé / calculation protocol unchanged : **pas 5 m / 5 m spacing, gaussienne / Gaussian σ = 20 m, hystérésis / hysteresis 2 m**.

[Audit détaillé et tests de régression / Detailed audit and regression tests](https://github.com/nico579/gpx2elev/blob/v0.3.4/AUDIT_CODE.md).
