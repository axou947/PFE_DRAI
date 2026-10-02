# Le cas du Ralentissement : un résultat en partie négatif

Ce chapitre est l'exemple détaillé d'un changement qui a passé sa règle pré-enregistrée et laissé pourtant le régime le plus faible faible. Il est rapporté en entier pour cette raison.

## Le problème

La règle du chapitre 3 appelle Ralentissement un jour où le score de croissance est bas et où ni le stress ni la surchauffe ne s'appliquent. Sur données réelles, le modèle à sauts n'a jamais trouvé ces jours comme un groupe : jusqu'en 2023, l'état qu'il nommait Ralentissement ne contenait qu'une minorité de jours de Ralentissement, et à partir de fin 2023 aucun état n'était nommé Ralentissement, si bien que l'application n'en montrait plus depuis. Rien ne vérifiait si le Ralentissement de la règle correspondait à un ralentissement de l'économie.

Un diagnostic sur données simulées et sur le code a montré que le Ralentissement de la règle scintillait : il franchissait son seuil plusieurs fois par an, avec des épisodes de quelques jours, là où un ralentissement de l'économie dure des mois. Le score de croissance est la moyenne de quatre z-scores croissants (momentum actions, pente de la courbe, production industrielle et inscriptions au chômage), et une seule période extrême comme 2020 écrasait toutes les lectures suivantes.

## Le changement et sa référence extérieure

La version v2.2 change la construction du score de croissance, pas les modèles : mise à l'échelle robuste (médiane et écart interquartile croissants), moyenne sur 21 jours, et seuil de {{config.regimes.rule.growth_threshold|0}} (croissance sous sa propre médiane). Les entrées sont choisies sur un holdout réel antérieur à la période hors échantillon.

Le Ralentissement est confronté à une **référence extérieure qui n'est jamais une entrée du modèle** : l'indice d'activité nationale de la Fed de Chicago, moyenne sur 3 mois, sous zéro (croissance sous sa tendance). La règle de décision comporte neuf conditions chiffrées, écrites avant le passage réel, parmi lesquelles : le score de croissance correspond mieux à la référence qu'avant, un état Ralentissement existe dans au moins la moitié des réajustements, aucun épisode n'est perdu, l'objectif de latence tient, les objectifs de fausses alarmes tiennent, et le score de Brier et l'erreur de calibration ne se dégradent pas.

## Étape 1 : choisir les entrées de croissance sur un holdout réel

{{quote:SLOWDOWN.md#Results > Step 1: growth holdout}}

Les données simulées avaient retenu le candidat opposé. C'est la raison d'un holdout réel, et c'est pourquoi son choix, les quatre entrées avec la pente de la courbe, est celui des réglages.

## Un écart au protocole

Le protocole disait que si le gagnant de l'étape 1 n'est pas le premier candidat, ses entrées entrent dans les réglages avant l'étape 2. L'étape 2 a pourtant été lancée sur le premier candidat, juste après l'étape 1. L'écart est publié tel qu'il s'est produit et ce passage ne décide de rien :

{{quote:SLOWDOWN.md#Results > An unplanned run of step 2, on the wrong variant}}

C'est aussi pourquoi le passage suivant n'est plus aveugle : il ne diffère d'un passage déjà vu que par une entrée.

## Étape 2 sur la variante retenue

{{quote:SLOWDOWN.md#Results > Step 2 on the selected variant (run once}}

Les neuf conditions étaient remplies et la version v2.2 a été adoptée. L'enregistrement de la version {{meta.model_version}} est en accord avec ce tableau (annexe A, contrôle de cohérence).

## Un résultat en partie négatif

Ce qui est passé, et ce qui ne l'est pas :

- Le score de croissance mesure mieux la croissance : sa précision équilibrée contre la référence est passée de {{cell:SLOWDOWN.md#Results > Step 2 on the selected variant (run once | growth match with the reference (balanced accuracy) | v2.1}} à {{cell:SLOWDOWN.md#Results > Step 2 on the selected variant (run once | growth match with the reference (balanced accuracy) | v2.2}}, et le Ralentissement de la règle est maintenant un régime persistant (épisodes de Ralentissement par an et durée médiane en jours : {{cell:SLOWDOWN.md#Results > Step 2 on the selected variant (run once | rule: Slowdown spells / yr (median spell, days) | v2.2}}, contre {{cell:SLOWDOWN.md#Results > Step 2 on the selected variant (run once | rule: Slowdown spells / yr (median spell, days) | v2.1}} auparavant).
- Un état nommé Ralentissement existe désormais dans {{cell:SLOWDOWN.md#Results > Step 2 on the selected variant (run once | refits with a state named Slowdown, agreement ≥ 50% | v2.2}} des réajustements, contre {{cell:SLOWDOWN.md#Results > Step 2 on the selected variant (run once | refits with a state named Slowdown, agreement ≥ 50% | v2.1}} auparavant. La détection est intacte.
- **Ce que l'application affiche comme Ralentissement ne vaut toujours pas mieux que le hasard.** Sa précision équilibrée contre la référence est de {{cell:SLOWDOWN.md#Results > Step 2 on the selected variant (run once | displayed Slowdown vs reference (balanced accuracy) | v2.2}}, où 0,5 est le hasard ; elle était de {{cell:SLOWDOWN.md#Results > Step 2 on the selected variant (run once | displayed Slowdown vs reference (balanced accuracy) | v2.1}}. La condition 3 demandait « plus haut » et c'est plus haut, mais d'environ un centième, ce qui sur des années de jours en grande partie corrélés n'est pas la preuve d'une meilleure correspondance. Le régime affiché retrouve {{cell:SLOWDOWN.md#Results > Step 2 on the selected variant (run once | reference slowdown days found / shown days that are right | v2.2}} (part des jours de ralentissement de la référence retrouvés, part des jours affichés qui sont justes).
- La règle place désormais {{cell:SLOWDOWN.md#Results > Step 2 on the selected variant (run once | rule: days in Slowdown | v2.2}} des jours en Ralentissement, parce que son seuil est la médiane d'un historique qui commence en 2004 et que la croissance depuis 2009 est souvent en dessous, tandis que l'application affiche du Ralentissement sur {{cell:SLOWDOWN.md#Results > Step 2 on the selected variant (run once | days shown as Slowdown | v2.2}} des jours. Une partie de l'écart vient de la référence, qui est sous sa tendance de long terme {{cell:SLOWDOWN.md#Results > Step 2 on the selected variant (run once | reference: days of below-trend growth | v2.2}} des jours depuis 2009, et une partie du modèle à sauts, qui exige aussi que les dimensions de stress et d'inflation s'accordent.

La lecture honnête est que le score de croissance est devenu une meilleure mesure de la croissance, et que le Ralentissement affiché n'est pas encore une bonne correspondance avec la référence extérieure. Le Ralentissement reste le plus faible des quatre régimes. Un nouveau changement exigerait son propre pré-enregistrement, et la période réelle hors échantillon n'est plus aveugle.
