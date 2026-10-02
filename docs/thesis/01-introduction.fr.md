# Introduction

## Le problème

Le risque d'un portefeuille dépend de l'environnement de marché dans lequel il se trouve : les mêmes positions se comportent différemment dans une expansion calme, un ralentissement, une poussée d'inflation ou une crise. Ce projet construit un détecteur qui, chaque jour ouvré, indique dans lequel de quatre régimes se trouve le marché américain (Expansion, Surchauffe inflationniste, Ralentissement, Stress), donne une probabilité de stress calibrée et déclenche une alarme de stress. Il est conçu comme un outil descriptif pour une fonction risque, avec une explication associée à chaque lecture, et non comme un signal de trading. Le système décrit l'état du marché et signale le début des épisodes de stress. Il ne prévoit pas les crises et ne donne aucun conseil en investissement.

## Ce que ce rapport affirme, et ce qu'il n'affirme pas

Les modèles sont classiques : k-means, un modèle à sauts statistique (*statistical jump model*), du gradient boosting et une calibration logistique à deux paramètres. Le projet ne prétend pas à un nouveau modèle. Ce qu'il documente, c'est une manière de travailler qui rend les résultats vérifiables :

- la règle qui date les épisodes de stress est **gelée par un hachage** avant tout backtest, et le code refuse une règle qui ne lui correspond plus ;
- chaque changement de modèle est **pré-enregistré** : le problème, le changement et la règle de décision chiffrée sont écrits et publiés avant l'unique passage sur données réelles, et les résultats sont ajoutés sous un titre « Results » quels qu'ils soient, sans jamais modifier ce qui est au-dessus ;
- le **délai de détection de chaque épisode** est publié, et pas seulement une médiane, avec les fausses alarmes par an ;
- les échecs sont publiés comme tels (chapitres 7 et 8) ;
- un **suivi en conditions réelles** est écrit chaque jour ouvré, chaîné par hachage et horodaté hors du dépôt (chapitre 10).

## Trois niveaux de preuve

Toute affirmation de performance de ce rapport nomme sa fenêtre de données et la version du modèle, et dit si le choix qui la précède était pré-enregistré ou fait après avoir vu les épisodes.

1. Les **données simulées** (un générateur qui reproduit les principales crises depuis 2000) ont servi à choisir des conceptions. Elles flattent les modèles, elles ne prouvent donc rien sur les marchés réels.
2. Le **backtest réel** est en walk-forward et hors échantillon, mais il a été calculé après coup, et depuis le 2026-10-01 ses épisodes de stress sont *vus* : tout réglage ultérieur exige une raison écrite au préalable. C'est un **indice**.
3. Le **suivi en conditions réelles** est écrit chaque soir avant que le résultat soit connu et ne peut pas être réécrit sans rompre sa chaîne de hachage. C'est la **preuve**, et elle est encore courte : à la construction de ce document, elle compte {{live.days}} jour(s) publié(s), le premier le {{live.first_day|date}} et le dernier le {{live.last_day|date}}.

## Résultat principal

Pour la version {{meta.model_version}} du modèle, sur les {{backtest.current.metrics.n_episodes}} épisodes de stress réels datés par la règle gelée entre le {{backtest.current.period.start|date}} et le {{backtest.current.period.end|date}} (hors échantillon, calculé après coup, épisodes vus) : l'alarme de stress en a détecté {{backtest.current.metrics.detected}}, avec un délai médian de {{backtest.current.metrics.median_latency|0}} jours ouvrés par rapport au début daté (un délai négatif signifie que l'alarme était déjà allumée), au prix de {{backtest.current.metrics.false_positives_per_year|2}} fausses alarmes par an. La probabilité de stress calibrée a un score de Brier de {{backtest.current.metrics.brier|3}} et une erreur de calibration attendue (ECE) de {{backtest.current.metrics.ece|3}}. Ces chiffres sont lus dans l'enregistrement du backtest à la construction du rapport ; le chapitre 5 les donne en détail, épisode par épisode.

Deux résultats sont faibles, et le rapport le dit là où ils sont présentés : le régime Ralentissement affiché par le modèle ne correspond pas mieux qu'au hasard à une mesure extérieure de l'activité (chapitre 7), et la version zone euro a échoué à sa règle de décision pré-enregistrée (chapitre 8).

## Comment lire ce rapport

Les chapitres 2 à 4 décrivent les données, les régimes et le cadre de validation. Les chapitres 5 à 7 suivent trois changements de modèle à travers le même protocole : la détection, la calibration et le régime Ralentissement. Le chapitre 8 applique le protocole à une nouvelle région et rapporte son échec. Le chapitre 9 décrit la vue des marchés mondiaux, descriptive et non validée comme le modèle américain. Le chapitre 10 présente le suivi en conditions réelles et le chapitre 11 les limites. L'annexe A donne de quoi reproduire le document.

Les tableaux, figures et chiffres de ce rapport sont générés à partir des enregistrements du dépôt, et les résultats qui n'existent que dans les documents du projet sont cités textuellement avec leur source et leur commit. La commande `python -m pfe_drai thesis --check` compare ce que les documents impriment avec les enregistrements.
