# Le suivi en conditions réelles et l'horodatage

## Pourquoi un suivi en conditions réelles

Un backtest, aussi soigné soit-il, est calculé après coup, et les épisodes de stress sur lesquels il est évalué ont été vus. Un suivi que chacun peut auditer, écrit avant que le résultat soit connu, est la seule preuve qui ne puisse pas être produite après l'événement. Le projet en publie donc un chaque jour ouvré et le tient partout séparé du backtest.

## Comment il est produit

Chaque jour ouvré après la clôture américaine (22 h 30 UTC), une tâche planifiée tourne sur données réelles uniquement et écrit un fichier JSON dans `track_record/` : le régime et ses probabilités, l'alarme de stress (allumée ou éteinte, depuis quand, le score du détecteur qu'elle lit et son seuil), la version du modèle et l'empreinte des réglages, et la fiabilité de la probabilité de stress jusque-là. Les données simulées sont refusées. Trois mécanismes rendent l'enregistrement inviolable sans que cela se voie :

- le SHA-256 de chaque fichier est ajouté à `track_record/index.csv`, et chaque fichier porte le hachage de la veille, formant une chaîne dont la page publique montre les ruptures et sur laquelle la tâche échoue ;
- le hachage de la règle d'épisodes gelée figure dans chaque entrée ;
- une preuve **OpenTimestamps** ancre chaque fichier dans la blockchain Bitcoin, ce qu'une date de commit git ne peut pas faire (une date de commit se change facilement). Une preuve fraîche ne contient que des promesses de calendrier et est complétée par l'exécution du lendemain.

Chaque configuration de modèle reçoit aussi un enregistrement de backtest, écrit la première fois que la tâche tourne avec elle et jamais réécrit. Un nouveau modèle ou un nouveau seuil reçoit un nouveau fichier et les précédents restent : l'historique des versions fait partie de l'enregistrement.

{{table:versions}}

## Ce que contient l'enregistrement aujourd'hui

À la construction de ce document, le suivi compte {{live.days}} jour(s) publié(s), le premier le {{live.first_day|date}} et le dernier le {{live.last_day|date}}, dont {{live.anchored}} ancré(s) dans Bitcoin et {{live.pending}} en attente. La chaîne de hachage est intacte : {{live.chain_ok|yesno}}.

{{table:live}}

Chaque jour publié est évalué tel qu'il a été publié, jamais recalculé : un épisode est détecté si l'alarme publiée les soirs précédents était allumée, un jour sans publication compte comme une absence d'alarme, et une alarme ne devient une fausse alarme qu'une fois {{backtest.current.rules.lookback_days}} jours ouvrés écoulés sans début d'épisode. À la construction de ce document, l'enregistrement est bien trop court pour dire quoi que ce soit de la détection, et le rapport n'en tire aucune affirmation. Il s'allonge d'une entrée chaque jour ouvré, et ces chapitres le liront à la reconstruction du rapport.

Le suivi montre aussi que les deux sortes de preuve ne doivent pas être confondues : la page étiquette le backtest comme un indice et les jours réels comme la preuve, et elle liste chaque version du modèle avec son propre backtest et le jour où le modèle publié a changé. Les prix de marché ne sont jamais publiés, seulement des sorties de modèle, des dates d'épisodes et la baisse de chaque épisode.
