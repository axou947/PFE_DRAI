# Cadre de validation

## Dater les épisodes de stress avec une règle gelée

La détection est évaluée contre des épisodes de stress qu'une règle fixe date à partir de la seule série actions (SPY). Un épisode commence au premier franchissement d'une baisse de {{config.validation.episodes.drawdown_threshold|pct0}} depuis le plus haut à 252 jours, ou lorsque la volatilité réalisée à {{config.validation.episodes.vol_window}} jours dépasse son quantile {{config.validation.episodes.vol_quantile|pct0}} calculé sur un historique croissant. Il finit quand la baisse repasse au-dessus de {{config.validation.episodes.recovery_drawdown|pct0}}, ou après {{config.validation.episodes.max_duration_days}} jours ouvrés, et au moins {{config.validation.episodes.min_gap_days}} jours ouvrés séparent la fin d'un épisode du début du suivant.

{{table:rules}}

Les paramètres sont **gelés**. Leur SHA-256, `{{config.validation.episodes.frozen.sha256}}`, a été fixé le {{config.validation.episodes.frozen.date|date}}, avant tout backtest sur données réelles, et le code refuse de tourner avec une règle dont les paramètres ne lui correspondent plus. Une nouvelle version de la règle exigerait un nouveau hachage, une date et une raison publique. La règle est volontairement indépendante des modèles : on ne peut pas ajuster les épisodes pour flatter un détecteur.

## Détection, délai et fausses alarmes

Une alarme de stress est allumée quand le score du détecteur dépasse {{backtest.current.rules.alarm_threshold|1}} pendant {{backtest.current.rules.confirm_days}} jours consécutifs. Un épisode est détecté si une alarme tombe entre {{backtest.current.rules.lookback_days}} jours ouvrés avant son début daté et {{backtest.current.rules.detection_window_days}} jours ouvrés après ; au-delà, il est manqué. Le **délai de chaque épisode** est rapporté, pas seulement la médiane, et un délai négatif signifie qu'une alarme était déjà allumée avant le début daté. Ce n'est pas toujours de la prescience : une alarme laissée allumée par un repli antérieur donne aussi un délai négatif (le chapitre 5 en montre des exemples).

Une **fausse alarme** est le déclenchement d'une alarme hors de tout épisode (élargi de la fenêtre amont). Deux mesures protègent contre une métrique qu'on pourrait tromper. Un signal qui reste allumé ne ferait presque aucun déclenchement faux, et une médiane sur les épisodes détectés s'améliore en manquant les plus difficiles. Le rapport donne donc aussi le délai médian sur *tous* les épisodes (un épisode manqué comptant pour la fin de la fenêtre de détection) et la **part des jours calmes avec l'alarme allumée**.

Les objectifs, fixés avant les tests, sont un délai médian d'au plus {{backtest.current.targets.max_median_latency_days}} jours ouvrés, au plus {{backtest.current.targets.max_false_positives_per_year|1}} fausses alarmes par an et au plus {{backtest.current.targets.max_false_alarm_share|pct0}} des jours calmes en fausse alarme.

## Évaluation walk-forward

Chaque modèle est évalué en walk-forward sur une fenêtre croissante : il est ajusté sur le passé, prédit vers l'avant et est réajusté tous les {{config.validation.refit_every_days}} jours ouvrés (tous les {{config.models.gbm.refit_every_days}} pour les modèles de gradient boosting, plus lents à ajuster), après une fenêtre d'apprentissage minimale de {{config.validation.min_train_days}} jours ouvrés. Les jours dont l'issue n'est pas encore connue sont écartés de chaque ajustement, et des tests vérifient que le filtre du modèle à sauts, le détecteur d'amorce et le calibrateur n'utilisent jamais le futur (retirer des données récentes ne modifie aucune prédiction antérieure).

## Évaluer une probabilité

La probabilité de stress est confrontée à un événement : **être dans un épisode, ou qu'un épisode commence dans les {{backtest.current.rules.calibration_horizon_days}} jours ouvrés**. Les scores sont le score de Brier, la perte logarithmique, l'erreur de calibration attendue (jours regroupés en 10 tranches de probabilité prédite, écart entre la prédiction moyenne et la fréquence observée dans chaque tranche, pondéré par les jours) et le Brier skill par rapport à la prédiction constante de la fréquence observée.

## Le protocole de pré-enregistrement

Un changement de modèle suit toujours la même séquence. Le problème, le changement et la règle de décision chiffrée, avec chaque condition, sont écrits dans un document et publiés **avant tout passage sur données réelles**. La conception est choisie sur données simulées et sur un holdout réel qui précède la période hors échantillon. Le backtest réel est ensuite lancé **une seule fois**. Les résultats sont ajoutés sous un titre « Results » quels qu'ils soient, et rien au-dessus de ce titre n'est modifié ensuite. Un changement qui échoue laisse le modèle précédent en place. Comme les épisodes réels deviennent connus du concepteur après le premier passage, le protocole consigne aussi qu'ils sont *vus* : tout nouveau réglage exige un nouveau pré-enregistrement avec une raison fixée au préalable.

Ce n'est pas une garantie contre toutes les formes de surapprentissage. Cela rend visibles les choix, l'ordre dans lequel ils ont été faits et les échecs, ce dont un lecteur a besoin pour peser les résultats.

## Indice et preuve

Trois mots sont employés de façon constante. Un choix est **pré-enregistré** quand sa règle de décision a été écrite avant le passage réel. Le backtest est un **indice** : hors échantillon, mais calculé après coup avec les épisodes vus. Le suivi en conditions réelles est la **preuve** : il est écrit chaque soir avant que le résultat soit connu (chapitre 10).
