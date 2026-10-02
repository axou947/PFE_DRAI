# Les régimes sur trois dimensions

## Trois scores de dimension

Les régimes ne se lisent pas sur deux axes mais sur trois scores, chacun moyenne de z-scores croissants (seul le passé est utilisé, les publications mensuelles sont datées de leur jour de sortie). Un score élevé signifie « plus » de la dimension.

| Dimension | Indicateurs |
|---|---|
| Stress | niveau du VIX, volatilité réalisée à 21 jours, stress de crédit (HYG contre IEF, LQD avant 2007), baisse depuis le plus haut à 1 an |
| Croissance | momentum actions à 6 mois, pente de la courbe 10 ans - 2 ans, production industrielle (1 an), inscriptions au chômage (3 mois, signe inversé) |
| Inflation | CPI (1 an), niveau du point mort à 10 ans, variation du point mort (3 mois), variation du taux à 2 ans (6 mois) |

## La règle qui définit les quatre régimes

Une règle transparente sur les trois scores, fixée dans `regimes.rule`, étiquette chaque jour de l'historique. Elle s'applique dans cet ordre :

1. **Stress** si le score de stress dépasse {{config.regimes.rule.stress_threshold|1}}, quoi que fassent la croissance et l'inflation ;
2. sinon **Surchauffe inflationniste** si le score d'inflation dépasse {{config.regimes.rule.inflation_threshold|1}} ;
3. sinon **Ralentissement** si le score de croissance est inférieur à {{config.regimes.rule.growth_threshold|1}} (croissance sous sa propre médiane historique depuis la version v2.2, chapitre 7) ;
4. sinon **Expansion**.

Chaque régime est donc une région de l'espace à trois dimensions, et non un quadrant. La règle est à la fois l'étiquette que les modèles supervisés apprennent et la référence qui nomme les états des modèles non supervisés. Il en découle une conséquence rappelée dans les limites : les régimes sont définis par une règle, pas observés, et l'accord avec la règle n'est donc pas un accord avec une vérité indépendante (le Ralentissement est le seul cas confronté à une mesure extérieure, chapitre 7).

## Nommer les états des modèles non supervisés

Le modèle à sauts et k-means regroupent les jours en quatre états qui n'ont pas de nom. À chaque réajustement walk-forward, chaque état prend le nom du régime dont le centre est le plus proche du sien. Le centre d'un régime est la position moyenne, sur les trois scores, des jours d'apprentissage que la règle place dans ce régime. Pour chaque état, les éléments de preuve sont conservés : la distance, son nombre de jours d'apprentissage et la part de ces jours que la règle place dans chaque régime. La part de son propre nom est l'*accord de l'état avec la règle*, et un état sous 50 % est dit mixte. Deux états peuvent porter le même nom, et un régime absent de la fenêtre d'apprentissage ne nomme aucun état. Rien n'est fixé à la main.

## Ce que les données réelles ont montré

Le nommage a été choisi sur données simulées. Sur données réelles, un passage pré-enregistré a vérifié que la détection ne régressait pas et décrit les états.

{{quote:REGIMES.md#Results > Real data, 2026-10-01}}

Deux lectures en découlent. L'état Stress est net à chaque réajustement, ce sur quoi s'appuient les chapitres de détection. L'état Ralentissement n'est pas un groupe de jours distinct, ce qui a motivé le travail du chapitre 7.
