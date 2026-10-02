# Détecter le stress : de la v1 à la v2

## La version 1 et sa lenteur

Le premier modèle par défaut, `combined`, prend les régimes du modèle à sauts et fixe P(stress) au maximum du modèle à sauts et d'un modèle de gradient boosting. Il a été choisi sur données simulées. L'unique passage réel, fait après publication du choix, est cité ici tel qu'il a été publié.

{{quote:DETECTION.md#Real data (run once, 2026-10-01)}}

Sur les 11 épisodes réels hors échantillon, la version 1 en a attrapé 5, avec un délai médian de 11 jours, ce qui échoue à l'objectif de latence. Le pré-enregistrement de la version 2 en donne deux raisons, trouvées en lisant le code et non les épisodes. D'abord, les modèles apprennent un événement différent de celui sur lequel ils sont évalués : le gradient boosting apprend l'étiquette « score de stress supérieur à 1 », alors que les épisodes sont datés par une règle de baisse ou de volatilité ; une chute de 10 % peut donc survenir alors que le score de stress reste bas, et aucun modèle entraîné sur cette étiquette ne peut l'appeler. Ensuite, les entrées sont lentes et leur échelle dérive : des z-scores croissants sur un historique qui contient 2008 écrasent toutes les lectures ultérieures, et une variation de crédit sur un trimestre réagit tard par construction.

## Version 2 : un détecteur d'amorce de stress

La version 2 ajoute une troisième source de stress, un détecteur du *début* d'un épisode (`models/onset.py`), de sorte que P(stress) est le maximum des sorties du modèle à sauts, du gradient boosting et du détecteur d'amorce.

- **Cible** : les épisodes gelés eux-mêmes, pas l'étiquette de la règle. Un jour est positif si un épisode commence dans les {{config.models.onset.horizon_days}} jours ouvrés ou a commencé il y a moins de {{config.models.onset.after_start_days}} jours ouvrés.
- **Entrées** : des indicateurs de marché rapides, dans leurs propres unités, pour qu'une valeur signifie la même chose en 1998 et en 2025 : baisse depuis le plus haut, rendements et volatilités réalisées à 5, 10 et 21 jours, volatilité par rapport à la ligne de la règle gelée, le VIX, sa variation logarithmique à 5 jours et son rapport à sa moyenne sur 3 mois.
- **Maintien** : une probabilité tient {{config.models.onset.hold_days}} jours (durée minimale d'allumage), contre le scintillement autour du seuil.
- **Apprenant** : gradient boosting ou régression logistique, réajusté tous les {{config.models.onset.refit_every_days}} jours ouvrés sur le seul passé.

Par construction, la version 2 ne peut qu'augmenter P(stress) : sur n'importe quelles données, elle détecte tout épisode détecté par la version 1, pas plus tard. Ce qu'elle peut coûter, ce sont des fausses alarmes, et c'est ce que surveillait la règle de décision.

## Sélection et décision

La conception a été choisie sur données simulées. L'apprenant et ses entrées ont ensuite été choisis sur un holdout réel jamais évalué par les modèles (1999 à 2009, avant la période hors échantillon), par une règle de sélection écrite au préalable : un candidat doit à lui seul respecter les deux objectifs de fausses alarmes, le plus faible délai médian sur tous les épisodes l'emporte, et les égalités vont à celui qui a le moins de faux positifs.

{{quote:DETECTION_V2.md#Results > Step 1: holdout}}

Le détecteur retenu, un gradient boosting sur des entrées de marché, a ensuite été lancé une fois sur les 11 épisodes réels, avec la règle de décision selon laquelle la version 2 est adoptée si elle respecte les deux objectifs de fausses alarmes.

{{quote:DETECTION_V2.md#Results > Step 2: the 11 real episodes}}

La version 2 a été adoptée : chaque épisode a été attrapé à moins de quatre jours de son début daté et l'objectif de latence a été atteint pour la première fois sur données réelles.

## La version actuelle, d'après son enregistrement de backtest

Les tableaux et figures ci-dessous sont générés à partir de l'enregistrement de backtest de la version {{meta.model_version}}, la version publiée aujourd'hui. Elle porte la probabilité calibrée (chapitre 6) et le changement sur le Ralentissement (chapitre 7) ; aucun ne modifie l'alarme de stress, qui lit toujours le score du détecteur : ses délais par épisode sont donc ceux de la version 2 (le contrôle de l'annexe A le confirme avec le tableau cité plus haut).

{{table:metrics}}

{{table:episodes}}

{{figure:latency}}

{{figure:timeline}}

## Ce que cela coûte, et ce que cela ne montre pas

- **Les fausses alarmes augmentent** de {{cell:DETECTION_V2.md#Results > Step 2: the 11 real episodes | v1 (jump + gbm) | FP / yr}} à {{cell:DETECTION_V2.md#Results > Step 2: the 11 real episodes | v2 (jump + gbm + onset) | FP / yr}} par an entre les versions 1 et 2 (cité plus haut) ; l'enregistrement actuel en compte {{backtest.current.metrics.false_positives_per_year|2}} par an, près de la limite de {{backtest.current.targets.max_false_positives_per_year|1}}. Sur les {{backtest.current.metrics.n_days}} jours hors échantillon, il y a {{backtest.current.metrics.n_alarms}} alarmes, dont {{backtest.current.metrics.n_false_alarms}} fausses. Un lecteur du suivi en conditions réelles doit s'attendre à environ une fausse alarme par an.
- **Un grand délai négatif n'est pas de la prescience.** Les plus grands délais négatifs, de l'ordre de 20 jours ouvrés dans le tableau ci-dessus, signifient en général qu'une alarme issue d'un repli antérieur était encore allumée quand l'épisode a commencé.
- **Le détecteur observe le marché sur lequel la règle est construite.** Sa rapidité vient en partie de la lecture de la même baisse et de la même volatilité que celles qui datent les épisodes : un délai proche de 0 signifie « le jour où la règle date le début ». Les délais négatifs sont la part prévisionnelle, et ils sont montrés épisode par épisode.
- **{{backtest.current.metrics.n_episodes}} épisodes, c'est peu**, et une médiane bouge beaucoup avec un seul épisode. Le holdout en ajoute quelques-uns d'une autre époque, et les deux passages vont dans le même sens, mais c'est un indice et non une preuve. Les épisodes sont désormais vus : aucun nouveau réglage n'est permis sans nouveau pré-enregistrement.
