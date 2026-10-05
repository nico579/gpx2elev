# Données et bibliothèques

Les données sont téléchargées à la demande ; aucune trace personnelle n'est distribuée.

- IGN / Géoplateforme : données sous Licence Ouverte ; [calcul altimétrique](https://cartes.gouv.fr/aide/fr/guides-utilisateur/utiliser-les-services-de-la-geoplateforme/calcul-altimetrique/).
- Mapterhorn : [attributions des producteurs](https://mapterhorn.com/attribution/), [accès aux données](https://mapterhorn.com/data-access/). Les tuiles françaises peuvent contenir les MNT IGN LiDAR HD et RGE ALTI.
- FABDEM 1.2, Neal, Hawker et al., University of Bristol : [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/), [DOI et données](https://research-information.bris.ac.uk/en/datasets/fabdem-v1-2/).
- Copernicus DEM GLO-30 : © DLR e.V. 2010–2014 et © Airbus Defence and Space GmbH 2014–2018, données financées dans le cadre de Copernicus par l'Union européenne ; [licence et distribution](https://registry.opendata.aws/copernicus-dem/).
- SRTM : NASA/USGS, [miroir Kurviger](https://srtm.kurviger.de/).

L'application utilise Qt / PySide6 / Shiboken sous LGPLv3, NumPy et Rasterio sous BSD, Pillow sous licence HPND, Requests et defusedxml sous Apache 2.0, ainsi que leurs dépendances. Les textes fournis par les distributions et leurs versions sont copiés dans le dossier `licenses` du bundle. Le code source de l'application est disponible dans le dépôt gpx2elev ; [sources Qt](https://download.qt.io/official_releases/qt/) et [sources PySide](https://download.qt.io/official_releases/QtForPython/).

Les bibliothèques Qt sont des bibliothèques partagées dans le bundle : elles peuvent être remplacées par des versions compatibles. Le contenu de `smoke_data` est un petit jeu de rasters publics utilisé uniquement par le contrôle interne du bundle. Ses attributions sont celles des données ci-dessus.

La police Noto Sans est distribuée sous SIL Open Font License 1.1 ; son texte est fourni dans `gpx2elev/assets/OFL.txt` et `licenses/NotoSans-OFL.txt`. [Source Google Fonts](https://github.com/google/fonts/tree/main/ofl/notosans).
