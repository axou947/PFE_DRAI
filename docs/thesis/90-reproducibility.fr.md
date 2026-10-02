# Reproductibilité

Le rapport est assemblé par une commande à partir des documents de `docs/`, des chapitres de `docs/thesis/`, des enregistrements de backtest de `track_record/backtest/`, du suivi en conditions réelles de `track_record/` et de `config/settings.yaml`. Il n'a besoin ni de réseau ni de clé d'API. Les documents eux-mêmes sont de l'histoire : rien au-dessus du titre « Results » d'un pré-enregistrement n'est modifié, et les résultats cités portent le commit du fichier dont ils viennent.

{{repro}}

Le contrôle de cohérence liste chaque chiffre imprimé dans les résultats d'un document que l'enregistrement de backtest de la même version ne reproduit pas, à la précision imprimée par le document. Il échoue si l'un diffère.
