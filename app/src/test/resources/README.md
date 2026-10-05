# Données des tests

Les petits fichiers raster de ce dossier sont des extraits de données publiques ; les images, grilles de contrôle et archives ZIP servent à vérifier leur lecture.

- `copernicus.tif` et `copernicus_pixels.csv` : extrait de Copernicus DEM GLO-30, © DLR e.V. 2010–2014 et © Airbus Defence and Space GmbH 2014–2018, financé dans le cadre de Copernicus par l'Union européenne. [Source et conditions d'utilisation](https://registry.opendata.aws/copernicus-dem/).
- `fabdem.tif`, `fabdem_pixels.csv`, `test.zip` et `test64.zip` : extrait recadré et recompressé de FABDEM 1.2, Neal, Hawker et al., University of Bristol, sous [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/). [Source, DOI 10.5523/bris.s5hqmjcdj8yo2ibzi9b4ew3sn](https://research-information.bris.ac.uk/en/datasets/fabdem-v1-2/).
- `mapterhorn.webp` et `mapterhorn_pixels.csv` : tuile publique Mapterhorn en France, fondée sur les données IGN. [Accès](https://mapterhorn.com/data-access/), [attributions](https://mapterhorn.com/attribution/), données IGN sous Licence Ouverte.

Les fichiers `reference.gpx`, `reference.csv`, `reference_expected.json` et `live_expected.csv` proviennent du banc d'essai personnel et restent locaux, exclus de Git. Les tests qui en dépendent sont ignorés lorsqu'ils sont absents. Les tests synthétiques et les contrôles des rasters publics fonctionnent après clonage.

Toutes ces ressources de test sont exclues de l'APK.
