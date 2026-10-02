# Données et discipline point-in-time

## Sources

La configuration en données réelles combine deux sources. Les séries macroéconomiques et le VIX viennent de FRED et ALFRED (Réserve fédérale de Saint-Louis) ; les prix quotidiens de quatre fonds cotés (SPY pour les actions américaines, HYG pour le crédit à haut rendement, LQD pour le crédit de qualité investissement et IEF pour les bons du Trésor) viennent de Tiingo. Douze indicateurs construits à partir d'elles alimentent trois scores de dimension (stress, croissance, inflation, chapitre 3). La source est choisie dans `config/settings.yaml` ; un fournisseur synthétique et un fournisseur CSV existent pour les tests et le travail sans clé. L'enregistrement utilisé pour les résultats de ce rapport a été produit avec le fournisseur `{{backtest.current.data_provider}}`.

## Point in time

Un backtest n'est honnête que si chaque jour ne voit que ce qui était connu ce jour-là. Trois règles l'imposent.

- **Premières publications.** Les inscriptions au chômage, la production industrielle et l'indice des prix à la consommation sont révisés après publication. Avec le fournisseur FRED, chacune de ces séries est lue dans ALFRED en *première publication*, datée du jour de sa sortie, de sorte qu'aucune révision ultérieure ne fuit vers le passé. Les observations antérieures à l'archive d'ALFRED retombent sur des délais de publication fixes (inscriptions {{config.data.publication_lag_days.claims}} jours, CPI {{config.data.publication_lag_days.cpi}} jours, production industrielle {{config.data.publication_lag_days.indpro}} jours). Lire à la place les valeurs révisées d'aujourd'hui est possible (`data.point_in_time`) et fait fuiter le futur.
- **Statistiques croissantes.** Chaque indicateur est un z-score calculé sur le passé seul, avec au moins {{config.features.zscore_min_periods}} observations, borné à ±{{config.features.zscore_clip|0}}.
- **Apprentissage walk-forward.** Les modèles sont réajustés sur une fenêtre croissante avec les seuls jours passés et prédisent la période suivante (chapitre 4).

Une limite est connue et conservée : une variation sur un an compare deux premières publications, et non le chiffre de l'an dernier tel qu'il était révisé ce jour-là.

## Couverture

L'historique est limité par la série la plus courte. HYG démarre en 2007 ; tant que sa mesure de crédit n'est pas disponible, la paire LQD contre IEF (depuis 2002), de qualité investissement, la remplace, standardisée sur son propre passé. Le point mort d'inflation à 10 ans (depuis 2003) est alors la série la plus courte, de sorte que les indicateurs en données réelles commencent en mars 2004. Les {{config.validation.min_train_days}} premiers jours ouvrés (cinq ans) servent à l'apprentissage, si bien que la première prédiction hors échantillon tombe au début de la période de l'enregistrement, le {{backtest.current.period.start|date}}, et que la crise de 2008 est dans la fenêtre d'apprentissage et n'est pas évaluée.

## Licences

Les licences de données ont orienté la conception. Le niveau du S&P 500 sur FRED est protégé par le droit d'auteur et ne commence qu'en 2016, on utilise donc SPY. Les écarts de crédit ICE BofA ne peuvent pas être redistribués et ne couvrent que des années récentes, et le BAA10Y de Moody's et les données Yahoo sont limités à un usage de recherche : aucun n'est utilisé. L'offre gratuite de Tiingo suffit pour la recherche, tandis que montrer des prix à des clients serait de la redistribution et demande un accord séparé. Pour cette raison, l'enregistrement public contient des **sorties de modèle, des dates d'épisodes et des baisses, jamais de prix de marché**, et ce rapport aussi.

## Données simulées

Le fournisseur synthétique suit une trajectoire de régimes qui reprend les principales crises depuis 2000, comble les trous par une chaîne aléatoire persistante et génère chaque série à partir de dynamiques propres à chaque régime. Le vrai régime est connu, ce qui permet de tester des conceptions là où la vérité existe. Il est aussi connu pour surestimer les modèles (le modèle à sauts en particulier, chapitre 5) : il sert donc à choisir des conceptions et jamais à revendiquer une performance. La publication quotidienne refuse les données simulées.
