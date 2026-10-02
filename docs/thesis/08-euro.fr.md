# La zone euro : un échec pré-enregistré

## La question

La méthode se transpose-t-elle à une autre région ? La version zone euro (`--region euro`, une surcouche des réglages) conserve inchangés le pipeline, les indicateurs, les modèles, la calibration et la règle d'épisodes du modèle américain et ne remplace que les entrées : l'ETF actions de la zone euro (EZU, coté en dollars) via Tiingo, les courbes de taux souverains de la BCE, l'indice des prix à la consommation harmonisé de la BCE, et la production industrielle et le chômage d'Eurostat. Le modèle américain, sa publication quotidienne et l'empreinte de ses réglages ne sont pas touchés par ce travail.

Le pré-enregistrement a fixé les données, les seuils de régime, la procédure de sélection et **sept conditions chiffrées** avant tout passage réel sur la zone euro. Si toutes tenaient, la vue euro pouvait être publiée chaque jour. Si l'une échouait, le résultat serait publié et la vue euro resterait étiquetée expérimentale.

## Faiblesses énoncées d'emblée

Les données étaient plus faibles que les données américaines, et le pré-enregistrement le disait avant le passage :

- ni la BCE ni Eurostat n'exposent les premières publications : les séries euro sont donc datées par un délai de publication prudent, mais la production industrielle et le chômage sont révisés, et le backtest voit les valeurs révisées (le modèle américain lit les premières publications) ;
- l'ETF est coté en dollars : son prix mélange actions de la zone euro et taux euro-dollar, et peut dater un épisode que le marché de la zone euro n'a pas connu ;
- le « VIX » euro est une volatilité réalisée et non implicite, il n'y a pas de point mort d'inflation quotidien (la dimension inflation est plus mince) et le crédit est un proxy souverain, pas du crédit d'entreprise ;
- l'historique est court : le backtest compte moins d'épisodes et la crise des dettes souveraines de 2010 à 2012 n'y est qu'en partie.

## Résultats

{{quote:EURO.md#Results > Step 2: the real backtest}}

{{quote:EURO.md#Results > Decision rule applied}}

## Lire l'échec

Six des sept conditions étaient remplies. L'alarme euro détecte vite le stress : {{cell:EURO.md#Results > Step 2: the real backtest | combined (the model) | detected}} épisodes détectés sur {{cell:EURO.md#Results > Step 2: the real backtest | combined (the model) | episodes}}, un délai médian de {{cell:EURO.md#Results > Step 2: the real backtest | combined (the model) | median latency}} jours ouvrés et {{cell:EURO.md#Results > Step 2: the real backtest | combined (the model) | FP/yr}} fausses alarmes par an, le tout dans les objectifs. La condition 6 a échoué : la probabilité calibrée est mieux calibrée que le score brut mais ne vaut pas mieux que la prédiction constante de la fréquence observée ; la probabilité euro ne doit donc pas être lue comme une probabilité. Le poids du calibrateur sur le score d'alarme est resté proche de zéro, ce qui suggère que le score portait peu d'information sur l'événement de stress au-delà de ce que dit déjà la fréquence de base.

{{quote:EURO.md#Results > What this does and does not show}}

Selon la règle pré-enregistrée, les résultats restent publiés, la vue euro reste expérimentale et aucun enregistrement quotidien euro n'est produit. Les {{cell:EURO.md#Results > Step 2: the real backtest | combined (the model) | episodes}} épisodes euro sont désormais vus : tout réglage ultérieur, par exemple une série libellée en euros, exige son propre pré-enregistrement avec une raison écrite au préalable. Les deux explications avancées dans la citation (l'ETF coté en dollars et l'alarme qui persiste après la fin des épisodes) sont des hypothèses et n'ont pas été testées.

Cet échec est un résultat de la méthode autant que des données : c'est la règle écrite à l'avance qui a empêché de présenter le modèle euro comme validé.
