# Calibration de la probabilité de stress

## Le problème

« Calibrée » signifie que les jours où le système annonce environ 30 % de stress, le stress suit environ trois fois sur dix. Le score de la version 2, maximum de trois modèles, est un bon *score de détection* mais pas une probabilité. Les probabilités du modèle à sauts oscillent entre 0 % et 100 %, le maximum de trois nombres est biaisé vers le haut quand les modèles divergent, et la plupart des jours le score est proche de zéro, y compris de nombreux jours à l'intérieur de longs épisodes qu'aucun modèle ne signale plus. Sur données simulées, le score non calibré avait un score de Brier d'environ 0,22 et une erreur de calibration d'environ 0,20 (voir le pré-enregistrement).

## Le changement

La probabilité publiée devient un étalonnage de Platt du score du détecteur,

P(stress) = sigmoïde(b + w × logit(score)),

avec deux paramètres réajustés tous les {{config.models.combined.stack.refit_every_days}} jours ouvrés sur les seuls jours passés. Le poids est maintenu positif ou nul, de sorte qu'un score plus élevé ne peut jamais abaisser la probabilité, et une pénalité de crête (force {{config.models.combined.stack.l2|1}}) le garde petit. Un calibrateur ajusté sur des prédictions dans l'échantillon apprendrait leur sur-confiance : les trois modèles commencent donc à prédire {{config.models.combined.stack.warmup_days}} jours après le début des données et le calibrateur n'apprend que sur des scores hors échantillon. L'alarme ne change pas : elle continue de lire le score du détecteur.

## La règle de décision et le résultat

La règle écrite avant l'unique passage réel était : la probabilité calibrée est conservée si, sur les mêmes jours réels hors échantillon, elle a un **score de Brier plus bas et une erreur de calibration attendue plus basse** que le score de la version 2. Sinon, on revient au maximum.

{{quote:CALIBRATION.md#Results > The one real-data run}}

Les deux conditions étaient remplies et la probabilité calibrée a été adoptée. Le contrôle que l'alarme elle-même n'avait pas changé a aussi été passé : détections, délais, fausses alarmes et temps d'alarme sont identiques à ceux de la version 2, épisode par épisode.

## La version actuelle, d'après son enregistrement de backtest

Pour la version publiée {{meta.model_version}}, l'enregistrement donne un score de Brier de {{backtest.current.metrics.brier|3}}, une erreur de calibration attendue de {{backtest.current.metrics.ece|3}}, une perte logarithmique de {{backtest.current.metrics.log_loss|3}} et un Brier skill de {{backtest.current.metrics.brier_skill|2}} par rapport à la prédiction constante de la fréquence observée ({{backtest.current.metrics.base_rate|pct1}} des jours sont dans l'événement de stress). Ils diffèrent légèrement des chiffres cités plus haut parce que le changement sur le Ralentissement (chapitre 7) a modifié le modèle après ce passage.

{{table:reliability}}

{{figure:reliability}}

## Ce que le passage a aussi montré

- Le score de la version 2 était sur-confiant en haut et sous-confiant en bas : ses jours au-dessus de 90 % ont vu du stress environ deux fois sur trois, et ses jours sous 10 % en ont vu plus de 5 % du temps.
- La probabilité calibrée est désormais trop prudente au-dessus de 30 % : les jours à 40-50 % ont vu du stress environ trois fois sur quatre. Ces tranches contiennent quelques centaines de jours issus d'une poignée de crises, une part de ce constat est donc du bruit, mais le sens est constant. En pratique, quand la probabilité passe 40 %, il faut la lire comme « stress plus probable qu'improbable ». Le poids du calibrateur est passé d'environ 0,1 à environ 0,3 à mesure que l'historique s'accumulait : le biais se réduit de lui-même.
- Le régime est plus calme : moins de changements de régime par an, avec les mêmes jours d'alarme.

## Ce que cela n'affirme pas

{{backtest.current.metrics.n_episodes}} crises, c'est peu, et les jours ne sont pas indépendants : un mois à l'intérieur d'une crise représente une vingtaine de jours corrélés, si bien que les tranches hautes du tableau de fiabilité reposent sur une poignée d'épisodes et restent bruitées. Les scores disent si la probabilité est meilleure que la précédente, pas qu'elle est exacte. La probabilité porte sur les épisodes de la règle gelée (une baisse de 10 % ou un pic de volatilité), pas sur des pertes ni sur une autre définition de la crise.
