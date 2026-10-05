# gpx2elev

**[Français](README.md) | [English](README.en.md)**

**[Release commune Android, Windows, Linux et macOS](https://github.com/nico579/gpx2elev/releases/latest)** : APK Android et [bundles Python autonomes](desktop/README.md), avec le même calcul et les mêmes sources.

**gpx2elev** estime le dénivelé positif (D+), le dénivelé négatif (D−) et le profil d'altitude d'une trace GPX. L'application Android est développée en Kotlin et Jetpack Compose.

[Télécharger l'APK Android avec les bundles Python](https://github.com/nico579/gpx2elev/releases/latest). Android et Python utilisent la même version **0.3.0**, définie dans `VERSION`. GitHub Actions construit l'APK signé et les quatre bundles sur chaque tag `v*`, vérifie les tests et les SHA-256, puis publie les cinq fichiers dans une seule release. Un contrôle bloque toute différence entre le tag et les versions. La clé Android est fournie par le secret chiffré `ANDROID_KEYSTORE_BASE64` ; elle n'est pas incluse dans Git.

## Utilisation

Android 0.3.0 utilise le nouvel identifiant `com.nico.gpx2elev`. Android l’installe comme une nouvelle application, à côté des versions 0.1/0.2 ; leurs données locales ne sont pas migrées automatiquement. Réimporter les GPX dans la nouvelle application.

Le sélecteur **FR / EN**, en haut de chaque application, change immédiatement la langue et mémorise le choix. Au premier lancement, la langue du système détermine le choix : français pour un système français, anglais sinon. Les nombres suivent la langue choisie ; les calculs et les schémas CSV restent identiques.

1. Installer l'APK sur un appareil Android 8.0 ou supérieur.
2. Toucher **Importer une trace GPX**, ou ouvrir/partager un GPX avec gpx2elev.
3. Le premier calcul récupère les altitudes par Internet. L'écran indique la progression.
4. Lire le D+, le D−, la distance et le profil d'altitude. Déplier la comparaison GPX pour consulter la somme brute des variations et le GPX filtré.
5. **Exporter le résultat en CSV** permet d'enregistrer les valeurs et les paramètres du calcul.

Dans une autre application, sélectionner le fichier GPX, toucher **Partager**, puis choisir **gpx2elev**. Le calcul démarre à la réception du fichier. Les variantes GPX, XML, texte et fichier binaire des types MIME sont reconnues ; le contenu reçu doit être un GPX valide. La réception accepte `EXTRA_STREAM`, `ClipData` ou l'URI du fichier. Voir le [mécanisme de partage Android](https://developer.android.com/develop/ui/compose/sharing/receive).

La dernière trace valide est conservée et reprise à la réouverture. Les profils complets sont mis en cache avec contrôle d'intégrité ; un calcul déjà conservé fonctionne hors connexion, tant que son profil reste dans le cache. Le cache des profils est limité à 64 Mo et celui des tuiles à 512 Mo, avec suppression des fichiers les moins récents après un calcul.

## Protocole

**Rééchantillonnage en distance : 5 m ; gaussienne spatiale : σ = 20 m ; hystérésis verticale : 2 m.** Ces valeurs sont fixes.

La gaussienne utilise un rayon de 80 m et un prolongement impair aux extrémités, répété pour les segments courts. Elle inclut la vraie extrémité de chaque segment, même hors de la grille de 5 m. L'hystérésis confirme les retournements et conserve les petites hausses successives d'une montée ; les extrémités filtrées restent incluses. Chaque segment GPX est calculé séparément.

Les coordonnées d'origine sont conservées. Le rééchantillonnage suit la polyligne GPX et ne constitue pas une correction de sa position. Les arrêts à coordonnées identiques gardent la dernière observation pour le rééchantillonnage ; toutes les altitudes originales restent dans la somme brute GPX. Les coordonnées sont déroulées lors d'un passage de l'antiméridien.

La somme brute GPX utilise les différences d'altitude successives à l'intérieur de chaque segment. Le GPX filtré utilise le même protocole que le modèle de terrain. Une absence d'altitude GPX est indiquée ; elle ne bloque pas le calcul par modèle.

## Repli entre modèles

| Rang | Modèle | Lecture |
|---:|---|---|
| 1 | IGN LiDAR HD | API Géoplateforme, ressource `ign_lidar_hd_mnt_mono_wld`, coordonnées à 7 décimales, lots de 5 000 maximum |
| 2 | Mapterhorn | Tuiles Terrarium WebP, zoom 13, parents lorsqu'une tuile est absente, interpolation bilinéaire entre centres de pixels |
| 3 | FABDEM 1.2 | GeoTIFF float32, téléchargement du seul membre utile d'une archive ZIP/ZIP64, interpolation bilinéaire |
| 4 | Copernicus GLO-30 | GeoTIFF COG float32 lus par requêtes HTTP partielles, interpolation bilinéaire |
| 5 | SRTM90 | HGT SRTM3 version 2.1 du miroir Kurviger, interpolation bilinéaire |

L'ordre provient du classement réalisé sur les traces communes en France métropolitaine. Le premier modèle qui fournit **toutes** les altitudes de la trace est retenu. Une valeur manquante ou un échec réseau déclenche l'essai du modèle suivant. Un profil provient d'un seul modèle ; les résultats affichent le modèle retenu et les raisons des replis. Les valeurs d'absence de données sont rejetées ; elles ne deviennent pas zéro. Les altitudes GPX restent une comparaison distincte.

Les lecteurs FABDEM et Copernicus prennent en charge les GeoTIFF en WGS84, float32, tuilés et compressés en Deflate, avec prédicteur 1, 2 ou 3. Ils respectent le référencement des centres des pixels (PixelIsPoint/PixelIsArea). L'interpolation peut lire les pixels d'une tuile voisine. Les blocs décompressés sont partagés dans un cache RAM de 16 Mo. Un encodage différent est signalé et déclenche le modèle suivant.

Les limites d'import sont de 20 Mo, 250 000 points et 300 000 positions rééchantillonnées. Les GPX 1.0/1.1, avec ou sans préfixe de namespace, sont acceptés ; les routes `rte` sont aussi acceptées. Les coordonnées non finies ou hors limites sont rejetées. Les fichiers XML avec DTD sont refusés.

## Construction

Les builds de release sont effectués sur GitHub par [le workflow Release](.github/workflows/release.yml). Pour une nouvelle version, mettre à jour `VERSION` et `desktop/gpx2elev/assets/version.txt`, augmenter le `versionCode` Android, puis pousser le tag correspondant. L’APK et les bundles ont toujours le même numéro de version.

Pour le développement local :

Ouvrir ce dossier dans Android Studio, ou depuis PowerShell :

```powershell
rtk proxy powershell.exe -NoProfile -ExecutionPolicy Bypass -File build.ps1
```

Le script utilise `JAVA_HOME` vers un JDK 17/21 ou, sur ce PC, `C:\Users\Nico\.jdks\jbr-21.0.11`. Le SDK est indiqué dans `local.properties`, exclu du contrôle de version. Gradle 8.7, AGP 8.5.2, Kotlin 1.9.24, Compose et SDK 34 reprennent les versions compatibles du projet OBD2 Dash. Les conseils de mise à jour de ces bibliothèques dans Lint sont attendus.

APK : `app/build/outputs/apk/release/app-release.apk`. Cette version personnelle est signée avec la clé de développement propre au projet, `app/debug.keystore` (alias et mots de passe Android standard). Conserver cette clé localement pour les mises à jour ; elle est exclue de Git. Après clonage sans cette clé, Gradle utilise sa clé de développement Android par défaut. Elle n'utilise pas la clé d'OBD2 Dash.

## Vérification

```powershell
rtk proxy powershell.exe -NoProfile -ExecutionPolicy Bypass -File build.ps1 -Mode tests
```

Ajouter `-Live` vérifie également les cinq lecteurs avec les données publiques réelles à trois positions, puis calcule le profil IGN complet de la trace de référence. Ce contrôle facultatif télécharge environ 30 Mo lors de sa première exécution. Les résultats sont dans `build/qa/modeles_en_ligne.csv` et `build/qa/verification_IGN_actuelle.json`. Les réponses IGN actuelles peuvent différer légèrement des réponses archivées ; les comparaisons du protocole utilisent toujours la référence archivée, sans la modifier.

Les tests comparent le calcul Kotlin au calcul Python audité sur la trace du 4 octobre : 1 500 points d'origine, 4 467 positions rééchantillonnées, D+ IGN 735,128566 m et D− IGN 735,149565 m. Ils comparent aussi toutes les altitudes lissées, les sommes GPX et le GPX filtré. Les autres cas portent sur les segments séparés, les arrêts, les extrémités, l'antiméridien, les données absentes, l'intégrité du cache, l'annulation et l'ordre de repli.

Des extraits des vrais GeoTIFF FABDEM/Copernicus contrôlent les prédicteurs et le géoréférencement. Des archives ZIP et ZIP64 contrôlent l'extraction et le CRC. Les tests Android sous Robolectric utilisent le rendu natif et un vrai WebP Mapterhorn : comparaison des canaux RGB, affichage jour/nuit/paysage, sélection GPX, calcul à partir du cache et lancement de l'export. Les images de vérification sont écrites dans `build/qa/`.

Les fixtures personnelles sont dans `app/src/test/resources`, **exclues de Git et de l'APK**. Après clonage, les tests qui utilisent la trace personnelle sont ignorés ; les tests synthétiques, le partage Android et les contrôles des rasters publics restent exécutés. Leur préparation locale utilise `rtk proxy python -X utf8 tools/prepare_test_fixtures.py`. Cette commande demande l'environnement Python du projet GPX parent et ses caches. Les petits extraits de données publiques fournis avec les tests ont leurs [attributions](app/src/test/resources/README.md).

La validation Android utilise Robolectric sur ce PC ; aucun téléphone physique n'a été connecté pendant cette construction.

## Données et attributions

Les coordonnées sont transmises au service IGN pour lire l'altitude. Pour les autres sources, l'application télécharge des tuiles ou blocs publics. GPX, profils et tuiles restent dans l'espace privé de l'application ; les sauvegardes cloud et transferts automatiques de ces données sont désactivés.

- [IGN / Géoplateforme](https://cartes.gouv.fr/aide/fr/guides-utilisateur/utiliser-les-services-de-la-geoplateforme/calcul-altimetrique/) : données IGN sous Licence Ouverte ; services publics de calcul altimétrique.
- [Mapterhorn, accès aux données](https://mapterhorn.com/data-access/) et [attributions des producteurs](https://mapterhorn.com/attribution/).
- [FABDEM 1.2, Neal, Hawker et al., University of Bristol](https://research-information.bris.ac.uk/en/datasets/fabdem-v1-2/) : CC BY-NC-SA 4.0 ; DOI `10.5523/bris.s5hqmjcdj8yo2ibzi9b4ew3sn`.
- [Copernicus DEM GLO-30 sur AWS](https://registry.opendata.aws/copernicus-dem/) : © DLR e.V. 2010–2014 et © Airbus Defence and Space GmbH 2014–2018, données financées dans le cadre de Copernicus par l'Union européenne ; conditions de la licence Copernicus DEM.
- [SRTM NASA/USGS, miroir Kurviger](https://srtm.kurviger.de/).

Les paramètres du protocole et les hypothèses de position déterminent l'estimation du D+. La précision horizontale reste importante, notamment près des falaises.
