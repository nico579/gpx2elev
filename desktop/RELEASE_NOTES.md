# gpx2elev 0.6.3 : interdictions piétonnes et horaires / Pedestrian bans and opening hours

Cette version corrige un jugement des barrières, sur Android comme sur ordinateur. Un portail interdit aux piétons (`foot=no` ou `foot=private`) qui porte aussi des horaires d'ouverture était classé « à vérifier » : il est désormais bloquant, car les horaires disent quand le portail est ouvert, pas qui a le droit de passer.

- Une interdiction explicite ne cède plus qu'à une condition au moins aussi précise qu'elle : `foot:conditional` peut lever `foot=no`, mais ni `opening_hours` ni un `access:conditional` général. Une interdiction générale (`access=no`) reste « à vérifier » devant une condition piétonne ou générale.
- Même règle pour le vélo et les véhicules : `vehicle:conditional` ne lève pas `bicycle=no`.
- Sur ordinateur, les horaires d'ouverture de la voie elle-même rendent un passage autorisé « à vérifier », comme c'était déjà le cas sur Android.

Constat relevé par l'audit de hike2gpx, qui reprend ces règles.

---

This version fixes a barrier decision on both Android and desktop. A gate closed to pedestrians (`foot=no` or `foot=private`) that also carries opening hours was rated "to check": it now blocks, since opening hours say when the gate is open, not who may pass.

- An explicit prohibition only yields to a condition at least as specific: `foot:conditional` may lift `foot=no`, but neither `opening_hours` nor a general `access:conditional` can. A general prohibition (`access=no`) stays "to check" when a pedestrian or general condition applies.
- Same rule for bicycles and vehicles: `vehicle:conditional` does not lift `bicycle=no`.
- On desktop, opening hours on the way itself now make an allowed crossing "to check", as Android already did.

Found by the hike2gpx audit, which reuses these rules.
