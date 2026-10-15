# gpx2elev pour Windows, Linux et macOS

**[Français](README.md) | [English](README.en.md)**

Application Python avec une interface web locale et des bundles autonomes incluant Python et les lecteurs de modèles. Serveur, langue, vérificateur de version, mise à jour automatique et systray : [nico579-commons](https://github.com/nico579/nico579-commons), comme gpxsolar, blink2video, watch2notif et lidar2map. **Aucune installation de Python n'est nécessaire pour les bundles.**

[Télécharger la release](https://github.com/nico579/gpx2elev/releases/latest).

La même release contient l'APK Android signé `gpx2elev-0.5.1.apk`, son rapport `verification-android.json` et sa somme SHA-256. Android et Python portent tous deux la version 0.5.1, construite sur GitHub Actions.

L'interface s'adapte au redimensionnement et à la maximisation. Si l'écran manque de hauteur, une barre de défilement permet d'atteindre le bas de page ; les chiffres des cartes restent entièrement visibles et les commandes ne chevauchent pas le graphique.

## Ouvrir l'application

- **Windows 10/11, x64** : décompresser `gpx2elev-windows-x86_64.zip`, puis ouvrir `gpx2elev-windows-x86_64/gpx2elev.exe`. Conserver tout le dossier avec l'exécutable ; il peut être renommé ou déplacé, de préférence dans un dossier de l'utilisateur.
- **Linux, x64** : extraire `gpx2elev-linux-x86_64.tar.gz`, puis lancer `./gpx2elev-linux-x86_64/gpx2elev`. Bundle construit sur Ubuntu 22.04 : Linux de bureau avec glibc 2.35 ou supérieure. Python et GDAL sont inclus ; un navigateur suffit pour la page.
- **macOS** : décompresser `gpx2elev-macos-arm64.zip` pour Apple Silicon (M1 et suivants), ou `gpx2elev-macos-x86_64.zip` pour Intel, puis ouvrir `gpx2elev.app`. Les bundles sont vérifiés sur macOS 14 pour Apple Silicon et macOS 15 pour Intel. Ils ne sont pas notarisés avec un compte développeur Apple : si macOS bloque l'ouverture, utiliser **Réglages Système → Confidentialité et sécurité → Ouvrir quand même**, conformément à l'aide Apple.

Le lancement ouvre le navigateur à http://127.0.0.1:8769/ (ou au premier port libre suivant). Le serveur écoute uniquement sur cet ordinateur. Un second lancement rejoint l'instance qui utilise le même dossier de données et lui transmet le GPX éventuel. L'option --new-instance crée un serveur distinct.

L'icône utilise directement nico579_commons.tray, avec le même menu : **Ouvrir**, **Mettre à jour vers…** lorsqu'une version est connue, **Redémarrer**, **Arrêter**, **Créer un raccourci sur le Bureau**. Fermer l'onglet laisse le serveur actif ; utiliser **Arrêter** dans l'icône ou la page pour quitter. Sans zone de notification, la page fonctionne aussi.

Le sélecteur **FR / EN** de l’en-tête change la langue immédiatement et mémorise le choix. Les nombres affichés suivent la langue ; les CSV gardent leur schéma et leurs valeurs.

Choisir un GPX, ou le déposer dans la page. L'application accepte aussi un chemin GPX en argument ; le bundle macOS reprend les fichiers reçus au lancement depuis le Finder. Sur Windows, **Ouvrir avec → Choisir une autre application** permet de sélectionner l'exécutable. Aucune association de fichier n'est modifiée automatiquement.

Le premier calcul nécessite Internet. Le modèle, le D+, le D−, la distance, le profil lissé et les altitudes GPX brutes/filtrées sont présentés. Deux exports CSV permettent d'enregistrer les résultats et chaque position du profil. Les nombres affichés sont arrondis ; les exports conservent six décimales pour la vérification, sans prétendre à une précision physique au micromètre.

Le graphique superpose le terrain lissé (vert) et les mesures originales du GPX (orange pointillé), avec une échelle commune. La molette zoome autour du pointeur ; glisser déplace la vue. Les boutons **Zoom +**, **Zoom −** et **Vue complète** sont aussi disponibles. Un double-clic rétablit la vue complète. Les segments restent séparés et les altitudes manquantes interrompent la courbe GPX.

**Plein écran** agrandit le graphique ; **Quitter le plein écran** ou **Échap** restaure la fenêtre normale. Le zoom et la position sont conservés. Un échec d'enregistrement du cache laisse le résultat disponible et affiche un avertissement sur son utilisation hors connexion.

L'axe horizontal affiche aussi l'**heure locale issue des points GPX**. Un clic place une barre verticale et affiche la distance, l'heure et les altitudes du terrain lissé et du GPX. Un glisser continue de déplacer la vue. La sélection reste en place au zoom, en plein écran et au changement FR/EN. Au zoom entre deux points, **GPX interpolé** identifie une valeur interpolée. Les heures absentes ou invalides apparaissent **—** ; les graduations horaires ne traversent pas les heures manquantes, les limites de segments ou les retours en arrière de l'horloge.

## Mises à jour

La mise à jour est celle de nico579-commons, la même que dans gpxsolar, lidar2map et watch2notif. Quand une version plus récente est publiée, un bandeau en haut de la page la signale et l'icône propose **Mettre à jour vers…**. **Installer** télécharge le bundle de ce système, vérifie son SHA-256 et son contenu, lui fait passer son auto-test, puis ferme gpx2elev : un assistant remplace le dossier de l'application, relance la nouvelle version et vérifie qu'elle démarre ; à la moindre défaillance, il remet l'ancienne en place. La page ouverte se recharge d'elle-même sur la nouvelle version. Les données et le dernier GPX restent dans leur dossier séparé.

Le bouton **⚙ Réglages…**, à côté de FR / EN, affiche la version installée ; **Vérifier les mises à jour** interroge GitHub tout de suite. Sinon, le vérificateur commun interroge GitHub au plus une fois par heure et conserve sa dernière réponse ; l'option --offline désactive cette veille. L'installation reste toujours une action explicite.

Seul le bundle publié se remplace lui-même : son dossier ne doit rien contenir d'autre, et le dossier parent doit être accessible en écriture. Depuis les sources Python, ou dans un dossier qui contient d'autres fichiers, le bandeau renvoie à la page de la release pour une mise à jour manuelle.

Les versions 0.3 et 0.4 passent à cette version par leur ancien bouton **Mises à jour** : la release garde pour elles les mêmes bundles sous leurs anciens noms (`gpx2elev-<version>-windows-x64.zip`…), qu'il est inutile de télécharger à la main. Leur mécanisme laissait à côté de l'application un dossier `.gpx2elev-update-…` contenant toute l'ancienne version ; la nouvelle le supprime au démarrage.

## Même protocole que l'application Android

1. Coordonnées XY du GPX conservées ; les segments restent séparés.
2. Rééchantillonnage en distance tous les **5 m**, en incluant l'extrémité réelle.
3. Altitudes du modèle, avec interpolation bilinéaire entre centres des pixels pour les rasters.
4. Gaussienne spatiale de **σ = 20 m**, rayon **80 m**, prolongement impair répété aux extrémités.
5. Hystérésis verticale de **2 m**, avec conservation des petites hausses successives et des extrémités filtrées.

Le calcul est indépendant de la durée des pauses. Le dernier point d'un arrêt à coordonnées identiques est utilisé pour le rééchantillonnage ; tous les points restent dans la somme brute GPX. Les passages de l'antiméridien sont déroulés. GPX 1.0 et 1.1, namespaces et routes `rte` sont acceptés. Les DTD et les coordonnées invalides sont refusées. Limites : 20 Mo, 250 000 points et 300 000 positions rééchantillonnées.

**Repli automatique : IGN LiDAR HD → Mapterhorn → FABDEM 1.2 → Copernicus GLO-30 → SRTM90.** Le classement provient de la comparaison sur les traces de France métropolitaine. Une source doit couvrir toute la trace ; aucune altitude d'une autre source ni du GPX ne comble ses trous. Les raisons des replis sont affichées. Un choix manuel permet d'essayer un modèle particulier.

Mapterhorn utilise le zoom 13 et les parents si une tuile manque. FABDEM est extrait par requêtes HTTP partielles dans ses archives ZIP/ZIP64 ; seule la tuile GeoTIFF nécessaire est téléchargée. Copernicus télécharge la tuile COG entière, puis l'interpole : le résultat suit le même géoréférencement que le lecteur Android. SRTM utilise les HGT SRTM3 v2.1. L'IGN utilise la même ressource `ign_lidar_hd_mnt_mono_wld`, par lots de 5 000 positions à sept décimales.

L'estimation dépend du MNT, des coordonnées XY et du filtrage ; le protocole n'est pas une mesure du « vrai » dénivelé validée sur le terrain.

## Cache et confidentialité

L'écran affiche la taille totale du cache et le détail profils/tuiles en Mio. **Vider le cache** demande confirmation, supprime les données téléchargées et actualise la taille. Le GPX, les réglages, les exports et le résultat affiché sont conservés. Les prochains calculs devront récupérer les altitudes à nouveau. Le bouton est désactivé pendant un calcul ou une suppression. Les plafonds de 64 Mio et 512 Mio sont appliqués après les calculs ; un téléchargement peut temporairement les dépasser.

La dernière trace calculée et les profils sont conservés dans les données locales de gpx2elev. Les profils ont une empreinte des coordonnées et de la configuration de source et une somme SHA-256 d'intégrité. Les caches ne se vident jamais d'eux-mêmes : ils ne sont effacés que sur demande, depuis l'interface et après confirmation. La dernière trace est rouverte depuis le cache, sans réseau. Décocher **Internet autorisé** impose l'utilisation du cache.

Les coordonnées sont envoyées au service IGN pour obtenir ses altitudes. Pour les autres modèles, seules les tuiles sont téléchargées. Aucune télémétrie ; aucune trace personnelle dans les bundles ou GitHub. Le calcul n'utilise pas de clé API.

## Moteur publié sur PyPI

Le moteur de calcul (lecture GPX, modèles de terrain et protocole 5 m / 20 m / 2 m) est publié sur PyPI sous le nom `gpx2elev`. `pip install gpx2elev` installe le moteur seul, sans Qt, pour qu'un autre programme comme [GPX2DASH](https://github.com/nico579/gpx2dash) s'en serve sans en garder une copie. `pip install "gpx2elev[gui]"` ajoute l'interface de bureau ; les bundles restent la façon la plus simple de l'utiliser.

## Développement et vérification

Depuis ce dossier, avec Python 3.12 :

```text
python -m venv .venv
python -m pip install -r requirements-build.txt
python -m gpx2elev
python -m unittest discover -s tests -v
python tools/build_bundle.py
python -m pip install -r requirements-test.txt
python -m playwright install --with-deps chromium
python tools/check_web_ui.py
```

Activer l'environnement `.venv` avant les commandes d'installation et de lancement. Sur le poste de Nico, préfixer les commandes shell par `rtk proxy`, conformément à RTK.md. `build_bundle.py` construit pour le système courant, exécute le bundle réel, puis produit les deux archives (nom commun et ancien nom), leurs SHA-256 et un rapport de vérification dans `release/` ; sur l'archive au nom commun, il rejoue ce que fait l'installateur : extraction contrôlée, puis auto-test de l'exécutable extrait. Les builds GitHub utilisent quatre machines natives Windows x64, Linux x64, macOS Intel et Apple Silicon. PyInstaller ne permet pas de fabriquer les trois plateformes depuis Windows.

Les tests vérifient les extrémités, les segments, les arrêts, l'antiméridien, les altitudes manquantes, l'hystérésis, l'intégrité du cache, le repli, l'annulation, les bords des tuiles, les GeoTIFF publics et les archives ZIP64. Le contrôle du bundle vérifie le serveur HTTP, les assets embarqués, le calcul hors connexion, le curseur, FR/EN, le cache, les CSV, GDAL et WebP. Playwright vérifie dans un vrai navigateur le choix de fichier, le glisser-déposer, le zoom, le déplacement, le plein écran, les téléchargements CSV, l'annulation, le panneau Réglages commun et les mises en page. Les bundles ne contiennent aucun Qt. La trace personnelle de référence, si elle existe localement dans les ressources Android, vérifie les 4 467 altitudes lissées et les totaux **735,128566 / 735,149565 m** ; ce test reste local et est ignoré dans GitHub.

Une utilisation sans interface est également disponible :

```text
python -m gpx2elev trace.gpx --calculate --output resultat.json --csv resultat.csv
python -m gpx2elev trace.gpx --calculate --offline --data-dir mon-cache
```

Les mêmes arguments fonctionnent avec le binaire autonome. Voir [les attributions et licences](THIRD_PARTY.md).

Les mêmes contrôles navigateur peuvent viser le binaire : python tools/check_web_ui.py --executable dist/gpx2elev/gpx2elev.exe sous Windows. Ajouter --browser-channel msedge pour utiliser Edge déjà installé. Rapports, captures et CSV synthétiques sont dans qa/web/.

Les données existantes restent dans le dossier Nico/gpx2elev de l'OS. Les options --data-dir ou GPX2ELEV_HOME choisissent un autre emplacement. Pour un service ou un essai, lancer python -m gpx2elev --serve-gui --no-browser --no-tray --port 8769.
