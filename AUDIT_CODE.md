# Audit du code gpx2elev — 7 octobre 2026

## Périmètre et résultat

Audit des applications Android et bureau : lecture GPX, calcul numérique, lecteurs de terrain, réseau, caches, interface et exports. Les scripts exploratoires du dossier parent ne font pas partie de cette application et ne sont pas inclus dans cet audit.

La superposition demandée est réalisée : terrain lissé en vert, observations originales du GPX en orange pointillé, échelle commune, conservation des arrêts et des mesures isolées, interruption aux altitudes absentes et entre segments. Le graphique permet le zoom sur les deux axes, le déplacement et le retour à la vue complète. Le mode **Plein écran** agrandit le graphique sur les deux plateformes ; le retour conserve zoom et position. Les commandes Android sont compactées en paysage. La sélection des points est recalculée dans la fenêtre visible pour retrouver les détails au zoom.

Les constats détaillés ci-dessous documentent la version **0.3.3** initialement auditée ; les numéros de ligne de cette section se rapportent à cette version. Les correctifs B1–B8 sont maintenant implémentés et accompagnés de tests de régression. Les optimisations proposées restent distinctes de ces corrections. Aucune fréquence de survenue en production n'est supposée.

## Correctifs implémentés

| Réf. | Correction | Régression |
| --- | --- | --- |
| B1 | Chemin XML complet et namespace identique à celui du document ; les extensions et parents étrangers sont ignorés. | `GpxParserRegressionTest` : collisions, namespaces, routes et segments. |
| B2 | Début, fin, taille totale et corps HTTP vérifiés avant utilisation ; anciennes tranches non vérifiées ignorées. | `HttpRangeRegressionTest` : vrais échanges HTTP locaux incohérents, suffixes et streaming. |
| B3 | Dernière page bornée par la taille du fichier ; une lecture réellement hors limites reste rejetée. | Même suite : fixture Copernicus et GeoTIFF valide de 938 octets. |
| B4 | Validation avant publication du WebP/GeoTIFF, invalidation ciblée et récupération unique, y compris les blocs compressés ; format non pris en charge préservé. | `RepositoryRegressionTest` : fichiers corrompus, téléchargements invalides et encodage non pris en charge. |
| B5 | Préparation complète du parcours avant remplacement de `last.gpx`, puis réutilisation de la préparation. | `ImportValidationTest` : erreurs de XML, parcours stationnaire ou trop long, et import valide. |
| B6 | Erreur de sauvegarde séparée de la lecture terrain ; profil valide conservé et avertissement FR/EN sur le hors connexion. | Dépôts Android/Python et interfaces ; cache rendu non inscriptible. |
| B7 | Nettoyage entourant toute l'écriture ; élagage des `.part` vieux de 24 h en préservant les écritures actives et récentes. | `test_cache.py` : disque plein, ancien temporaire et écriture active. |
| B8 | Comparaison GPX non exploitable rendue indisponible ; bornes graphiques finies conservées sans annuler le terrain valide. | Calcul numérique Android/Python et graphique bureau. |

Les clés de profils Android FABDEM et Copernicus sont renouvelées pour ne pas réutiliser un profil issu des anciennes tranches non vérifiées. Le premier recalcul de ces profils peut donc nécessiter Internet. Le protocole nominal, les coordonnées et les résultats de référence restent inchangés.

Le plein écran est couvert par les tests d'interface : agrandissement, zoom conservé au retour, basculement FR/EN, Échap sur ordinateur et affichage Android en portrait/paysage.

Le **menu ⋮ → Mises à jour** Android et le bouton **Mises à jour** bureau vérifient manuellement la release stable officielle. Les téléchargements sont bornés, limités aux endpoints HTTPS GitHub et validés par SHA-256. Android vérifie aussi l'identifiant, la version et le certificat de l'APK avant de demander l'autorisation système et d'ouvrir l'installateur. Un nouveau contrôle ne chevauche pas un contrôle en cours d'annulation ; rouvrir le menu actualise la release disponible.

Sur les bundles bureau, l'extraction contrôle les chemins et les liens, puis le programme téléchargé passe son contrôle hors connexion. Un auxiliaire indépendant attend la fermeture de l'application avant le remplacement et redémarre le programme ; une erreur restaure l'ancienne installation. L'environnement et la recherche des bibliothèques sont réinitialisés entre les versions. Les données restent hors du dossier remplacé. Le lancement depuis les sources fournit un bundle vérifié à ouvrir manuellement. La version 0.3.4 regroupe ces changements ; les anciennes applications demandent une première installation manuelle pour disposer du bouton.

## Défauts confirmés dans la version 0.3.3

| Réf. | Priorité | Plateforme | Conséquence |
| --- | --- | --- | --- |
| B1 | Moyenne | Android | Des extensions XML peuvent changer les altitudes ou injecter des points GPX. |
| B2 | Moyenne | Android | Une réponse HTTP correspondant à une mauvaise plage est acceptée et mise en cache. |
| B3 | Moyenne | Android | Une lecture valide proche de la fin d'un fichier raster échoue. |
| B4 | Moyenne | Android | Une tuile corrompue continue de faire échouer le modèle sans être téléchargée à nouveau. |
| B5 | Moyenne | Android | Une trace inutilisable remplace la dernière trace sauvegardée. |
| B6 | Moyenne | Bureau ; même logique Android | Une erreur de sauvegarde du cache fait rejeter un profil terrain pourtant valide. |
| B7 | Basse | Bureau | Une écriture interrompue laisse un fichier temporaire que l'élagage automatique ignore. |
| B8 | Basse, données pathologiques | Android et bureau | Des altitudes GPX extrêmes font échouer un calcul terrain valide. |

### B1 — Contexte XML incomplet dans le parseur Android

**Code :** [GpxParser.kt](app/src/main/java/com/nico/gpx2elev/core/GpxParser.kt), lignes 35, 49 et 75–78.

La pile mémorise le nom local des éléments, sans leur namespace. L'état courant du point et de son altitude n'est pas limité au chemin GPX attendu. Une balise étrangère nommée `trkpt` peut ainsi être prise pour le parent d'une altitude principale.

**Reproduction :** un point possède `<ele>100</ele>`, puis une extension `<extensions><x:trkpt xmlns:x="urn:foreign"><ele>999</ele></x:trkpt></extensions>`. Android retourne **999 m**, Python retourne **100 m**. Un `trkseg` GPX sous un parent étranger `x:trk` est également accepté par Android alors que Python le rejette.

**Impact :** comparaison GPX et courbe des observations erronées ; des collisions de structure peuvent aussi contaminer les coordonnées utilisées pour le terrain.

**Correction proposée :** suivre le namespace et le chemin complet ; traiter les données uniquement dans `gpx/trk/trkseg/trkpt` et `gpx/rte/rtept`, avec un contexte de point explicite. Les extensions doivent rester hors de ce contexte.

### B2 — Position de la plage HTTP non vérifiée

**Code :** [HttpTransport.kt](app/src/main/java/com/nico/gpx2elev/data/HttpTransport.kt), lignes 69–85 et 132–141.

`RemoteByteSource.exact()` vérifie le nombre d'octets mais pas la position annoncée par `Content-Range`. `bytes()` extrait seulement la taille totale. Le contrôle de position présent dans `consumeRange()` ne protège pas ce chemin.

**Reproduction :** requête `bytes=16384-32767`, réponse 206 avec `Content-Range: bytes 0-16383/50000`. Les 16 384 octets de la mauvaise tranche sont acceptés et enregistrés comme s'ils provenaient de la bonne position.

**Impact :** raster rejeté ou valeurs incorrectes si les octets restent décodables. Le fichier en cache prolonge le défaut.

**Correction proposée :** vérifier le début, la fin, la taille totale et la longueur de la réponse avant toute utilisation ou sauvegarde. Ajouter ce replay comme test de régression.

### B3 — Pages de lecture non bornées à la fin du fichier

**Code :** [HttpTransport.kt](app/src/main/java/com/nico/gpx2elev/data/HttpTransport.kt), lignes 145–150.

Une petite lecture charge systématiquement une page de 16 384 octets. La dernière page peut être plus courte, mais `exact()` exige malgré tout la taille complète.

**Reproduction :** sur la fixture Copernicus de **42 582 octets**, `read(42578, 4)` demande une plage contenant quatre octets existants. La page interne déborde la fin du fichier et provoque « Lecture partielle incomplète ».

Une seconde reproduction renforce le constat : un GeoTIFF valide de **938 octets**, lisible localement à 123 m, échoue dès son initialisation avec `RemoteByteSource`.

**Impact :** un raster valide peut déclencher un repli si des structures utiles sont situées dans sa dernière page. Ce constat ne signifie pas que toutes les lectures de la fixture échouent.

**Correction proposée :** mémoriser la taille totale et borner la dernière page ; à défaut, revenir à la lecture exacte de la petite plage demandée.

### B4 — Tuiles corrompues conservées sans récupération

**Code :** [ElevationRepository.kt](app/src/main/java/com/nico/gpx2elev/data/ElevationRepository.kt), lignes 168–171 et 224–250.

Mapterhorn écrit la réponse avant de la décoder. Au prochain essai, l'existence du fichier suffit pour la réutiliser. FABDEM ouvre également une tuile existante sans mécanisme d'invalidation après un échec de lecture.

**Reproduction :** une réponse HTTP 200 contenant un WebP invalide est enregistrée ; au deuxième essai, aucune requête n'est faite et la même erreur revient. Avec un fichier FABDEM vide déjà présent, deux essais échouent également sans requête et sans suppression du fichier.

**Impact :** le modèle reste inutilisable jusqu'à la suppression du cache ou son éviction. Le repli peut masquer la persistance du problème.

**Correction proposée :** décoder ou valider avant de publier un nouveau fichier en cache. Pour un fichier existant illisible, supprimer uniquement l'entrée concernée et tenter une récupération unique, en conservant la distinction entre corruption et format non pris en charge.

### B5 — Dernière trace remplacée avant validation du parcours

**Code :** [AppViewModel.kt](app/src/main/java/com/nico/gpx2elev/AppViewModel.kt), lignes 124–132.

Le GPX temporaire passe `GpxParser.parse()`, puis remplace `last.gpx`. `ElevationMath.prepare()` n'est appelé qu'après ce remplacement.

**Reproduction :** deux points aux mêmes coordonnées sont acceptés par le parseur, mais la préparation les rejette car il n'existe aucune paire de positions distinctes. L'ordre du code montre que la dernière trace a déjà été remplacée à ce moment. La reproduction porte sur parse/préparation ; elle ne constitue pas un test complet du ViewModel sur téléphone.

**Impact :** la trace précédemment utilisable n'est plus restaurable après cet import.

**Correction proposée :** préparer le parcours temporaire avant de remplacer la sauvegarde. Réutiliser le `Track` déjà parsé permet aussi d'éviter la seconde lecture XML. Définir séparément si la sauvegarde doit attendre la réussite du téléchargement des altitudes.

### B6 — Échec du cache confondu avec échec du modèle

**Code :** [providers.py](desktop/gpx2elev/providers.py), lignes 512–523 ; [ElevationRepository.kt](app/src/main/java/com/nico/gpx2elev/data/ElevationRepository.kt), lignes 82–92.

La sauvegarde du profil est dans le même bloc d'erreur que sa lecture et sa validation. Une erreur disque déclenche donc le modèle suivant alors que toutes les altitudes nécessaires sont déjà disponibles.

**Reproduction bureau :** lecteurs simulés fournissant un profil complet à 123 m ; sauvegarde simulant `ENOSPC`. Les cinq sources sont essayées, puis le calcul échoue. La logique Android est équivalente, mais ce scénario de dépôt du profil n'a pas été exécuté dans le ViewModel Android.

**Impact :** résultat perdu et requêtes supplémentaires inutiles.

**Correction proposée :** renvoyer le profil valide même si sa sauvegarde échoue, et indiquer que sa disponibilité hors connexion n'a pas pu être assurée. Conserver les erreurs de lecture des données dans le mécanisme de repli.

### B7 — Fichier temporaire laissé après une erreur d'écriture

**Code :** [providers.py](desktop/gpx2elev/providers.py), lignes 56–65 et 108–113.

Le bloc de nettoyage commence après l'écriture du fichier temporaire. Si `stream.write()` échoue, ce nettoyage n'est jamais atteint. L'élagage automatique exclut ensuite les fichiers `.part`.

**Reproduction :** une écriture simulant un disque plein laisse un `.part` de trois octets. Il subsiste après `trim_cache(..., limit=0)`.

**Impact :** des téléchargements interrompus peuvent consommer de l'espace en dehors du plafond automatique. Le bouton de suppression manuelle du cache les supprime déjà.

**Correction proposée :** entourer toute la création et l'écriture du temporaire d'un `try/finally`, puis supprimer les anciens temporaires à un moment où aucun téléchargement n'est actif.

### B8 — Débordement du GPX comparatif propagé au terrain

**Code :** [core.py](desktop/gpx2elev/core.py), lignes 185 et 293 ; [ElevationMath.kt](app/src/main/java/com/nico/gpx2elev/core/ElevationMath.kt), lignes 76–78 et 204–205.

Les altitudes `-1e308` et `1e308` sont individuellement finies et acceptées. Leur interpolation déborde, puis la comparaison GPX échoue et annule `compute()`.

**Reproduction :** terrain valide constant à 100 m, GPX avec ces deux altitudes extrêmes. Le calcul échoue sur les deux plateformes.

**Impact :** robustesse face à des fichiers mal formés ; ce cas n'est pas représentatif d'altitudes enregistrées sur le terrain.

**Correction proposée :** contrôler les valeurs après interpolation et rendre la comparaison GPX indisponible si elle n'est pas exploitable. Le terrain valide doit rester affichable. La superposition doit également ignorer une série incapable de produire des bornes finies.

## Optimisations proposées

1. **Exporter les gros CSV dans un worker bureau.** [ui.py](desktop/gpx2elev/ui.py), ligne 738, appelle l'export sur le fil de l'interface. Une mesure ponctuelle sur ce poste, pendant l'audit, donne **6,209 s** pour 300 000 lignes et **22,1 Mio**. Ce temps correspond à un blocage potentiel de l'interface. Écrire progressivement réduirait aussi les copies actuellement créées par `StringIO`, `getvalue()` puis l'encodage.
2. **Précompiler les traductions Android.** [I18n.kt](app/src/main/java/com/nico/gpx2elev/I18n.kt), lignes 35–48, reconstruit les expressions régulières à chaque appel. Les préparer dans `initialize()`, comme le fait déjà Python, évite de refaire ce travail pendant les recompositions liées au zoom.
3. **Lire le XML Python progressivement.** [core.py](desktop/gpx2elev/core.py), ligne 111, construit tout le DOM avant d'appliquer la limite de points. Une lecture progressive avec libération des éléments réduit le pic mémoire des fichiers proches de 20 Mo et permet d'arrêter plus tôt à 250 000 points. Garder le rejet des DTD et entités, les namespaces et la séparation des segments.
4. **Partager le balayage d'interpolation Kotlin.** [ElevationMath.kt](app/src/main/java/com/nico/gpx2elev/core/ElevationMath.kt), lignes 72–78, effectue des recherches binaires séparées pour latitude, longitude et altitude à chaque position. Les distances demandées étant croissantes, un index partagé permet `O(N + M)` au lieu de `O(M log N)`. Les extrémités et l'antiméridien doivent conserver exactement leur traitement actuel.
5. **Réutiliser le noyau gaussien fixe.** [ElevationMath.kt](app/src/main/java/com/nico/gpx2elev/core/ElevationMath.kt), ligne 106, reconstruit les 33 poids pour chaque segment, pour le terrain puis le GPX. Le gain est surtout attendu avec de nombreuses petites sections. Mettre en cache les poids pour les paramètres fixes, en préservant la variante paramétrable utilisée par les tests.

Les gains des propositions 2–5 n'ont pas été mesurés. Les valider avec des traces proches des limites et les références numériques avant de changer le protocole ou les structures de données.

## Autres points à examiner

- **Lecteurs Android ouverts sans plafond.** Les collections `rasters` et `opened` de [ElevationRepository.kt](app/src/main/java/com/nico/gpx2elev/data/ElevationRepository.kt) conservent tous les lecteurs TIFF/HGT jusqu'à la fin du calcul. Un LRU avec fermeture à l'éviction limiterait les descripteurs sur les traces qui traversent beaucoup de tuiles. Aucun épuisement de descripteurs n'a été reproduit.
- **Mémoire des rasters bureau.** [providers.py](desktop/gpx2elev/providers.py) lit les rasters entiers et conserve deux rasters avec des copies temporaires. Une lecture par blocs ou fenêtres limiterait la mémoire ; mesurer le pic avant de modifier l'interpolation aux frontières.
- **Fraîcheur des caches de tuiles Android.** Corrigé avec B4 : les tuiles Mapterhorn et FABDEM réutilisées actualisent leur date d'usage, utilisée par l'élagage.
- **Intégrité des tranches distantes Android.** La clé de cache utilise URL, position et longueur, sans checksum ni version HTTP. La taille seule ne détecte pas une corruption conservant le nombre d'octets ; un changement du fichier distant peut également mélanger des versions. Ce sont des risques déduits du code, pas des incidents observés sur les services publics.

## Validation locale et preuves

- Suite bureau : **45 tests**, **43 réussis et 2 ignorés** ; les deux tests ignorés nécessitent la création de liens symboliques, non autorisée sur ce Windows. Les contrôles couvrent les correctifs précédents et les mises à jour : comparaison de versions, sélection de plateforme, intégrité, annulation, extraction, remplacement, retour arrière et dialogue FR/EN.
- Android : `gradlew.bat testDebugUnitTest lintRelease assembleRelease --no-daemon` **réussi**, avec **79 tests**, **77 réussis, 2 ignorés, 0 erreur**. Le test des services publics est désactivé (`liveReaders=false`) ; le test FileProvider requiert les séparateurs de chemins Android/Linux et est exécuté sur Linux par la CI de release. Les tests locaux couvrent les versions, le transport HTTP réel, les APK corrompus, les signatures API 26/34, l'annulation sans chevauchement et les écrans FR/EN.
- Lint Debug et Release : **0 erreur**, cinq avertissements `GradleDependency` sur les versions des dépendances existantes. APK Release compilé, réduit et signé avec le certificat attendu ; permission d'installation et provider présents dans le manifeste final. La vérification des nombres de tests de publication est actualisée à 79 tests, au moins 73 exécutés sans les fixtures facultatives.
- Programme Windows natif construit et contrôlé hors connexion, y compris le dialogue de mise à jour en français et anglais. Dans une copie isolée, l'auxiliaire a attendu un vrai processus parent, remplacé l'application, redémarré le nouvel exécutable et préservé le GPX et les réglages, avec des chemins contenant des espaces. Annuler pendant la vérification native conserve l'application initiale et nettoie la préparation.
- Contrôle réel de la release Windows publique 0.3.3 : lecture de l'API officielle, téléchargement, SHA-256, extraction et vérification native réussis. Aucune installation utilisateur n'a été modifiée. Le remplacement natif n'a pas été exécuté sur Linux/macOS ni sur un téléphone physique dans cet environnement.
- Vérification du rendu bureau sur la trace personnelle de référence : 1 500 points originaux, 4 467 positions terrain ; **D+ 735,128566 m**, **D− 735,149565 m**. Les courbes sont superposées et la navigation ne modifie pas ces résultats.
- Les restrictions qui empêchaient initialement Gradle ont été levées et les tests Android complets ont maintenant été exécutés. Aucun téléphone physique n'a été testé. La CI de release reconstruit et vérifie l'APK et les quatre bundles natifs pour le tag v0.3.4 avant publication.
- Preuves exploratoires de l'audit initial, conservées dans le dossier ignoré `build/qa` : [audit_core.py](build/qa/audit_core.py), [AuditCore.java](build/qa/AuditCore.java), [ReaderAuditReplay.java](build/qa/ReaderAuditReplay.java), [desktop_reader_audit.py](build/qa/desktop_reader_audit.py), [résultats des lecteurs bureau](build/qa/desktop-reader-audit.json). Les régressions des correctifs sont dans les suites de tests versionnées.
- Aperçus bureau : [vue complète](build/qa/profil-superpose-bureau.png), [vue zoomée](build/qa/profil-superpose-bureau-zoom.png).
- Aperçus du nouveau mode : [plein écran](build/qa/profil-plein-ecran-bureau.png), [retour conservant le zoom](build/qa/profil-retour-plein-ecran-bureau.png), produits par [preview_fullscreen.py](build/qa/preview_fullscreen.py).
- Preuves de mise à jour : [rapport Windows](build/qa/native-updater-verification.json), [dialogue FR](build/qa/verification-windows-updater.updates.fr.png), [dialogue EN](build/qa/verification-windows-updater.updates.en.png), [contrôle du bundle](build/qa/verification-windows-updater.json).

Aucun défaut supplémentaire n'a été confirmé dans le calcul nominal des arrêts, des segments séparés, de l'antiméridien ou du lissage de la référence. Cela ne constitue pas une preuve d'absence de tous les bugs.

## Ajouts de la version 0.3.5

L'heure locale des points GPX est conservée sur Android et bureau et affichée sur l'axe horizontal. Le clic ou le toucher sélectionne une mesure originale et affiche un curseur vertical, la distance, l'heure et les deux altitudes. Au zoom entre des observations, la lecture interpolée est signalée. Les heures manquantes, les segments distincts et les horloges qui reculent ne sont pas reliés. Le zoom, le déplacement, le plein écran et le changement FR/EN conservent la sélection, sans changer le protocole numérique.

La validation locale des ajouts comporte **50 tests bureau (48 réussis, 2 ignorés)** et **84 tests Android (82 réussis, 2 ignorés)**, sans échec. Les quatre tests ignorés correspondent aux mêmes restrictions Windows et contrôle réseau facultatif que précédemment : deux liens symboliques côté bureau, FileProvider et services publics côté Android. Lint Release : **0 erreur** ; APK Release compilé. Les tests couvrent le parsing UTC/fuseaux, les heures absentes ou invalides, les arrêts, les segments, le passage de minuit, le curseur, le zoom entre points, le plein écran et FR/EN. Les deux catalogues partagent **257 traductions** identiques, sans valeur vide.

La CI de release reconstruit cette version pour Android et les quatre plateformes bureau. Chaque exécutable bureau distribué vérifie aussi hors connexion l'heure GPX, les deux altitudes et leur traduction dans le contrôle natif. Les rapports et empreintes sont joints à la release.

## Correctif de mise en page de la version 0.3.6

La maximisation Windows peut fournir une fenêtre large mais moins haute que la fenêtre initiale, notamment avec la mise à l'échelle de l'écran. Le contenu exigeait 805 pixels de hauteur dans la reproduction : à 1339 × 667, les valeurs de dénivelé recevaient seulement 13 pixels pour une police de 51 pixels. Les chiffres étaient coupés et les commandes du graphique se chevauchaient.

Le contenu conserve désormais sa taille minimale dans une zone défilante. Les valeurs des trois cartes gardent la hauteur requise par leur police et les colonnes partagent l'espace disponible. Une fenêtre peu haute permet d'atteindre les commandes inférieures par défilement. Le graphique est replacé dans ce même contenu après le plein écran ; ses interactions et la sélection sont conservées.

Validation locale : **51 tests bureau, 49 réussis et 2 ignorés**, sans échec. La régression vérifie les chiffres, les séparations entre libellés, l'absence de chevauchement avec le graphique, l'accès au bas de page, les redimensionnements et la maximisation, en FR et EN. Les **11 tests d'interface** passent également avec `QT_SCALE_FACTOR=1.5`. Le contrôle des exécutables natifs distribué avec chaque bundle vérifie aussi la mise en page à **1339 × 667**.

## Suite proposée

Les correctifs B1–B8 sont validés. Les travaux suivants restent les optimisations proposées : export CSV asynchrone, traductions précompilées, lecture XML progressive, puis interpolation et mémoire des rasters après mesure des gains. Ils ne sont pas inclus dans cette série de corrections.
