# Les marchés mondiaux

## Ce que c'est

Le modèle de régimes a besoin de données macroéconomiques américaines : il n'existe donc que pour les États-Unis. La vue des marchés mondiaux est un outil distinct et plus simple : pour 20 marchés actions nationaux, elle montre les rendements sur un horizon choisi, un état de stress propre au marché et la proximité de chaque marché avec les États-Unis. Elle est **descriptive**. Elle n'a rien de la validation des chapitres 4 à 7 : pas de délai par épisode, pas de taux de fausses alarmes, pas de probabilité.

## Données

Les niveaux d'indices officiels sont sous licence : chaque marché est donc lu à travers un ETF pays coté aux États-Unis, fourni par Tiingo (la même source que pour le modèle américain), avec SPY pour les États-Unis. Les prix sont donc en dollars et incluent le mouvement de change, les clôtures sont celles de New York (pour l'Asie et l'Australie, la séance locale était close plus tôt), les indices suivis diffèrent des références locales et les ETF démarrent à des dates différentes. Une vue en devise locale convertit avec les taux de change H.10 de la Réserve fédérale lus sur FRED, qui sont hebdomadaires : les derniers jours ne sont donc pas disponibles en devise locale.

## État de stress de marché

L'état d'un marché est calculé à partir de ses seuls prix, avec des fenêtres glissantes (sans anticipation, testé) :

- **Stress** : volatilité réalisée à 21 jours dans les {{config.world.stress.vol_percentile|pct0}} les plus hauts de ses cinq dernières années *et* baisse depuis le plus haut à 1 an au-delà de {{config.world.stress.drawdown|pct0}} ;
- **Tendu** : volatilité dans les {{config.world.elevated.vol_percentile|pct0}} les plus hauts de ses cinq dernières années ;
- **Calme** sinon.

Un nouvel état compte une fois tenu {{config.world.confirm_days}} jours de suite. Les seuils reprennent ceux de la règle d'épisodes gelée, ont été fixés le 2026-10-01 avant d'avoir regardé la moindre donnée pays réelle, sont les mêmes pour chaque marché et n'ont pas été ajustés. La volatilité est classée dans l'historique propre à chaque marché : un marché structurellement volatil n'est donc pas toujours tendu.

## Le lien avec les États-Unis

Pour chaque marché, la vue montre la corrélation et le bêta contre SPY sur des rendements à {{config.world.link.return_days}} jours qui se chevauchent, sur des fenêtres de {{config.world.link.windows.0}} et {{config.world.link.windows.1}} jours ouvrés, la corrélation les jours où les États-Unis sont en stress contre les autres jours, et des termes d'avance et de retard partiels. Ces réglages ont été fixés le 2026-10-02 avant d'avoir regardé un seul chiffre réel.

## Vérifications sur données réelles

Les seules vérifications sur données réelles sont des contrôles de vraisemblance, lancés une fois chacun et publiés tels qu'ils sont sortis.

{{quote:WORLD.md#Real-data check (2026-10-01)}}

{{quote:WORLD.md#Real-data check (2026-10-02): local currency and link to the US}}

Le premier contrôle montre le comportement attendu (tous les marchés en stress en mars 2020, le premier touché étant la Corée du Sud) et le second la hausse habituelle des corrélations en crise (la corrélation moyenne des 19 autres marchés avec les États-Unis a augmenté entre un automne 2019 calme et la chute de mars 2020). Ils montrent que la vue se comporte de façon sensée. Ce n'est pas une validation : le rapport n'affirme pas que ces états prédisent quoi que ce soit, et les colonnes d'avance et de retard se lisent en période calme, pas comme une mesure de crise.
