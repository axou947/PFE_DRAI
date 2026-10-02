# Reproducibility

The report is assembled by a command from the documents in `docs/`, the chapters in `docs/thesis/`, the backtest records in `track_record/backtest/`, the live record in `track_record/` and `config/settings.yaml`. It needs no network and no API key. The documents themselves are history: nothing above the "Results" heading of a pre-registration is edited, and quoted results carry the commit of the file they come from.

{{repro}}

The consistency check lists every number printed in a document's results that the backtest record of the same version does not reproduce, to the precision the document printed. It fails if one disagrees.
