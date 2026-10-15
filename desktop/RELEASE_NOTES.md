# gpx2elev 0.5.2 : pannes passagères distinguées / Transient failures told apart

- Le moteur distingue un modèle écarté par une panne passagère (réseau coupé, délai dépassé, serveur occupé ou en panne : HTTP 429 et 5xx) d'un modèle qui ne couvre pas la trace. `Series.transient` et `MissingCoverage.transient` nomment les premiers : un programme qui traite de nombreuses traces, comme gpx2dash, peut ainsi retenter plus tard l'IGN au lieu de garder pour toujours le repli obtenu pendant une panne.
- Applications Android et ordinateur, protocole de calcul et profils en cache inchangés.

The engine now tells a model set aside by a transient failure (network down, timeout, busy or failing server: HTTP 429 and 5xx) from a model that does not cover the track. `Series.transient` and `MissingCoverage.transient` name the former, so a program processing many tracks, such as gpx2dash, can retry IGN later instead of keeping forever the fallback obtained during an outage. The Android and desktop applications, the calculation protocol and cached profiles are unchanged.
