# gpx2elev pour Windows, Linux et macOS

**[Français](README.md) | [English](README.en.md)**

Application Python de bureau, avec des bundles autonomes incluant Python, Qt et les lecteurs de modèles. **Aucune installation de Python n'est nécessaire pour les bundles.**

[Télécharger la release](https://github.com/nico579/gpx2elev/releases/latest).

La même release contient l'APK Android signé `gpx2elev-0.3.5.apk`, son rapport `verification-android.json` et sa somme SHA-256. Android et Python portent tous deux la version 0.3.5, construite sur GitHub Actions.

## Ouvrir l'application

- **Windows 10/11, x64** : décompresser `gpx2elev-0.3.5-windows-x64.zip`, puis ouvrir `gpx2elev/gpx2elev.exe`. Conserver tout le dossier avec l'exécutable.
- **Linux, x64** : extraire `gpx2elev-0.3.5-linux-x64.tar.gz`, puis lancer `./gpx2elev/gpx2elev`. Bundle construit sur Ubuntu 22.04 : Linux de bureau avec glibc 2.35 ou supérieure. Python, Qt et GDAL sont inclus ; les composants système d'affichage X11/Wayland doivent être présents.
- **macOS** : décompresser l'archive `macos-arm64` pour Apple Silicon (M1 et suivants), ou `macos-x64` pour Intel, puis ouvrir `gpx2elev.app`. Les bundles sont vérifiés sur macOS 14 pour Apple Silicon et macOS 15 pour Intel. Ils ne sont pas notarisés avec un compte développeur Apple : si macOS bloque l'ouverture, utiliser **Réglages Système → Confidentialité et sécurité → Ouvrir quand même**, conformément à l'aide Apple.

Le sélecteur **FR / EN** de l’en-tête change la langue immédiatement et mémorise le choix. Les nombres affichés suivent la langue ; les CSV gardent leur schéma et leurs valeurs.

Choisir un GPX, ou le déposer dans la fenêtre. L'ouverture avec l'application accepte également un chemin GPX en argument ; macOS accepte les événements d'ouverture du Finder. Sur Windows, **Ouvrir avec → Choisir une autre application** permet de sélectionner l'exécutable. Aucune association de fichier n'est modifiée automatiquement.

Le premier calcul nécessite Internet. Le modèle, le D+, le D−, la distance, le profil lissé et les altitudes GPX brutes/filtrées sont présentés. Deux exports CSV permettent d'enregistrer les résultats et chaque position du profil. Les nombres affichés sont arrondis ; les exports conservent six décimales pour la vérification, sans prétendre à une précision physique au micromètre.

Le graphique superpose le terrain lissé (vert) et les mesures originales du GPX (orange pointillé), avec une échelle commune. La molette zoome autour du pointeur ; glisser déplace la vue. Les boutons **Zoom +**, **Zoom −** et **Vue complète** sont aussi disponibles. Un double-clic rétablit la vue complète. Les segments restent séparés et les altitudes manquantes interrompent la courbe GPX.

**Plein écran** agrandit le graphique ; **Quitter le plein écran** ou **Échap** restaure la fenêtre normale. Le zoom et la position sont conservés. Un échec d'enregistrement du cache laisse le résultat disponible et affiche un avertissement sur son utilisation hors connexion.

L'axe horizontal affiche aussi l'**heure locale issue des points GPX**. Un clic place une barre verticale et affiche la distance, l'heure et les altitudes du terrain lissé et du GPX. Un glisser continue de déplacer la vue. La sélection reste en place au zoom, en plein écran et au changement FR/EN. Au zoom entre deux points, **GPX interpolé** identifie une valeur interpolée. Les heures absentes ou invalides apparaissent **—** ; les graduations horaires ne traversent pas les heures manquantes, les limites de segments ou les retours en arrière de l'horloge.

## Mises à jour

Le bouton **Mises à jour**, en bas de la fenêtre, recherche manuellement la dernière release stable officielle sur GitHub et affiche sa version, sa taille et ses notes. **Télécharger et installer** sélectionne le bundle Windows, Linux ou macOS correspondant à l'architecture courante, vérifie son SHA-256 et lance son contrôle hors connexion avant de modifier l'installation. **Installer et redémarrer** ferme l'application, remplace son dossier, puis la relance. Les données et le dernier GPX restent dans leur dossier séparé ; une copie de l'ancienne application est conservée et restaurée si le remplacement ou le lancement échoue.

Le dossier de l'application et son parent doivent être accessibles en écriture, et les données doivent se trouver hors du dossier de l'application. Le dossier extrait doit garder son nom `gpx2elev` (`gpx2elev.app` sur macOS). Avec un lancement depuis les sources Python ou un dossier renommé, **Télécharger** et **Ouvrir le dossier** fournissent le bundle vérifié pour une installation manuelle. Aucun contrôle n'est lancé automatiquement ; Internet est nécessaire après une demande de vérification. Les versions publiées sans ce bouton demandent une première mise à jour manuelle.

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
