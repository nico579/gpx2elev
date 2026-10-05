# gpx2elev pour Windows, Linux et macOS

Application Python de bureau, avec des bundles autonomes incluant Python, Qt et les lecteurs de modèles. **Aucune installation de Python n'est nécessaire pour les bundles.**

[Télécharger la release](https://github.com/nico579/gpx2elev/releases/tag/v0.2.1).

## Ouvrir l'application

- **Windows 10/11, x64** : décompresser `gpx2elev-0.2.1-windows-x64.zip`, puis ouvrir `gpx2elev/gpx2elev.exe`. Conserver tout le dossier avec l'exécutable.
- **Linux, x64** : extraire `gpx2elev-0.2.1-linux-x64.tar.gz`, puis lancer `./gpx2elev/gpx2elev`. Bundle construit sur Ubuntu 22.04 : Linux de bureau avec glibc 2.35 ou supérieure. Python, Qt et GDAL sont inclus ; les composants système d'affichage X11/Wayland doivent être présents.
- **macOS** : décompresser l'archive `macos-arm64` pour Apple Silicon (M1 et suivants), ou `macos-x64` pour Intel, puis ouvrir `gpx2elev.app`. Les bundles sont vérifiés sur macOS 14 pour Apple Silicon et macOS 15 pour Intel. Ils ne sont pas notarisés avec un compte développeur Apple : si macOS bloque l'ouverture, utiliser **Réglages Système → Confidentialité et sécurité → Ouvrir quand même**, conformément à l'aide Apple.

Choisir un GPX, ou le déposer dans la fenêtre. L'ouverture avec l'application accepte également un chemin GPX en argument ; macOS accepte les événements d'ouverture du Finder. Sur Windows, **Ouvrir avec → Choisir une autre application** permet de sélectionner l'exécutable. Aucune association de fichier n'est modifiée automatiquement.

Le premier calcul nécessite Internet. Le modèle, le D+, le D−, la distance, le profil lissé et les altitudes GPX brutes/filtrées sont présentés. Deux exports CSV permettent d'enregistrer les résultats et chaque position du profil. Les nombres affichés sont arrondis ; les exports conservent six décimales pour la vérification, sans prétendre à une précision physique au micromètre.

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

La dernière trace calculée et les profils sont conservés dans les données locales de gpx2elev. Les profils ont une empreinte des coordonnées et de la configuration de source et une somme SHA-256 d'intégrité. Les caches sont limités à 64 Mo de profils et 512 Mo de tuiles. La dernière trace est rouverte depuis le cache, sans réseau. Décocher **Internet autorisé** impose l'utilisation du cache.

Les coordonnées sont envoyées au service IGN pour obtenir ses altitudes. Pour les autres modèles, seules les tuiles sont téléchargées. Aucune télémétrie ; aucune trace personnelle dans les bundles ou GitHub. Le calcul n'utilise pas de clé API.

## Développement et vérification

Depuis ce dossier, avec Python 3.12 :

```text
python -m venv .venv
python -m pip install -r requirements-build.txt
python -m gpx2elev
python -m unittest discover -s tests -v
python tools/build_bundle.py
```

Activer l'environnement `.venv` avant les commandes d'installation et de lancement. Sur le poste de Nico, préfixer les commandes shell par `rtk proxy`, conformément à RTK.md. `build_bundle.py` construit pour le système courant, exécute le bundle réel, puis produit une archive, son SHA-256 et un rapport de vérification dans `release/`. Les builds GitHub utilisent quatre machines natives Windows x64, Linux x64, macOS Intel et Apple Silicon. PyInstaller ne permet pas de fabriquer les trois plateformes depuis Windows.

Les tests vérifient les extrémités, les segments, les arrêts, l'antiméridien, les altitudes manquantes, l'hystérésis, l'intégrité du cache, le repli, l'annulation, les bords des tuiles, les GeoTIFF publics et les archives ZIP64. L'interface est réellement rendue avec Qt ; le contrôle du bundle vérifie le glisser-déposer, le calcul en tâche de fond, le cache, les CSV, GDAL et WebP. La trace personnelle de référence, si elle existe localement dans les ressources Android, vérifie les 4 467 altitudes lissées et les totaux **735,128566 / 735,149565 m** ; ce test reste local et est ignoré dans GitHub.

Une utilisation sans interface est également disponible :

```text
python -m gpx2elev trace.gpx --calculate --output resultat.json --csv resultat.csv
python -m gpx2elev trace.gpx --calculate --offline --data-dir mon-cache
```

Les mêmes arguments fonctionnent avec le binaire autonome. Voir [les attributions et licences](THIRD_PARTY.md).
