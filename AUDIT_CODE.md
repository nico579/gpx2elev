# Audit du code gpx2elev — 7 octobre 2026

## Périmètre et résultat

Audit des applications Android et bureau : lecture GPX, calcul numérique, lecteurs de terrain, réseau, caches, interface et exports. Les scripts exploratoires du dossier parent ne font pas partie de cette application et ne sont pas inclus dans cet audit.

La superposition demandée est réalisée : terrain lissé en vert, observations originales du GPX en orange pointillé, échelle commune, conservation des arrêts et des mesures isolées, interruption aux altitudes absentes et entre segments. Le graphique permet le zoom sur les deux axes, le déplacement et le retour à la vue complète. La sélection des points est recalculée dans la fenêtre visible pour retrouver les détails au zoom.

Les constats ci-dessous concernent le code existant et restent à corriger. Ils sont séparés des changements du graphique. Les défauts ont été reproduits hors ligne ou établis par une reproduction du cas numérique et l'ordre des opérations dans le code ; aucune fréquence de survenue en production n'est supposée.

## Défauts confirmés

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
- **Fraîcheur des caches de tuiles Android.** Les chemins Mapterhorn et FABDEM réutilisés n'actualisent pas leur date d'usage, alors que l'élagage trie sur cette date. Actualiser cette date évite d'évincer des tuiles récemment utilisées simplement parce qu'elles ont été téléchargées il y a longtemps.
- **Intégrité des tranches distantes Android.** La clé de cache utilise URL, position et longueur, sans checksum ni version HTTP. La taille seule ne détecte pas une corruption conservant le nombre d'octets ; un changement du fichier distant peut également mélanger des versions. Ce sont des risques déduits du code, pas des incidents observés sur les services publics.

## Validation et preuves

- Suite bureau : **26 tests**, **25 réussis et 1 ignoré** ; le test ignoré nécessite la création de liens symboliques, non autorisée sur ce Windows. Les nouveaux contrôles couvrent mesures originales, arrêts, coupures, segments, échelle commune, molette, déplacement, retour à la vue complète et détail après zoom.
- Kotlin : **13 tests purs réussis** pour `ProfileChartDataTest` et `ElevationMathTest`, exécutés avec Kotlin 1.9.24 et JUnit depuis les dépendances locales.
- Toutes les sources Android actuelles, avec le plugin Compose 1.5.14, ainsi que `AndroidUiTest.kt`, ont été compilées sans erreur dans un dossier QA séparé. Le script local est [run_chart_kotlin_qa.py](build/qa/run_chart_kotlin_qa.py).
- Vérification du rendu bureau sur la trace personnelle de référence : 1 500 points originaux, 4 467 positions terrain ; **D+ 735,128566 m**, **D− 735,149565 m**. Les courbes sont superposées et la navigation ne modifie pas ces résultats.
- Les tentatives Gradle sont bloquées par l'environnement : téléchargement refusé, puis chargement des composants natifs / résolution du cache. Les tests UI Robolectric ajoutés ont été compilés, mais n'ont pas été exécutés ; aucun téléphone physique n'a été testé.
- Preuves locales, conservées dans le dossier ignoré `build/qa` : [audit_core.py](build/qa/audit_core.py), [AuditCore.java](build/qa/AuditCore.java), [ReaderAuditReplay.java](build/qa/ReaderAuditReplay.java), [desktop_reader_audit.py](build/qa/desktop_reader_audit.py), [résultats des lecteurs bureau](build/qa/desktop-reader-audit.json).
- Aperçus bureau : [vue complète](build/qa/profil-superpose-bureau.png), [vue zoomée](build/qa/profil-superpose-bureau-zoom.png).

Aucun défaut supplémentaire n'a été confirmé dans le calcul nominal des arrêts, des segments séparés, de l'antiméridien ou du lissage de la référence. Cela ne constitue pas une preuve d'absence de tous les bugs.

## Ordre de correction recommandé

1. Namespace du parseur et validation avant sauvegarde (B1, B5).
2. Validation des plages, dernière page et récupération des tuiles (B2–B4).
3. Séparer résultat et cache, puis garantir le nettoyage des temporaires (B6, B7).
4. Export asynchrone et traductions précompilées.
5. Robustesse des valeurs extrêmes (B8), puis optimisations numériques et mémoire mesurées.
