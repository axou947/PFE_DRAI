# PFE DRAI — détection de régimes de marché + IA

Outil de détection de régimes de marché explicable, avec stress tests conditionnés au régime
et note de comité des risques. Interface et rapports en **français et en anglais**.

> ⚠ Tant qu'aucune API n'est branchée, l'application tourne sur des **données simulées**
> (`data.provider: synthetic`). Elles reproduisent les grandes crises depuis 2000 pour que tout
> soit testable, mais ne décrivent pas le marché réel. Voir [Brancher une API](#brancher-une-vraie-source-de-données).

## Démarrer en 2 minutes

```bash
python -m venv .venv
source .venv/bin/activate          # Windows PowerShell : .venv\Scripts\Activate.ps1
pip install -e ".[app,dev]"

python -m pfe_drai app             # tableau de bord sur http://localhost:8501
```

Le premier lancement calcule le walk-forward des trois modèles (environ 30 secondes),
puis le résultat est mis en cache dans `data_cache/`.

## Ce que fait l'application

| Écran | Contenu |
|---|---|
| **Tableau de bord** | régime actuel et probabilités, les 3 dimensions (stress, croissance, inflation), ce qui a changé en une semaine, ce qui ferait basculer, moteurs du régime, historique des régimes sur l'indice actions |
| **Historique** | latence de détection par épisode, fausses alertes par an, score de Brier, calibration, comparaison des modèles, track record publié |
| **Alertes** | changement de régime, probabilité de stress, alerte précoce à 1 semaine, mouvements brusques ; filtres par type et période |
| **Scénarios et comité** | scénarios de stress historiques classés selon le régime actuel, impact sur un fonds type (pondérations modifiables), note de comité des risques en PDF / HTML / Markdown |

Dans la barre latérale : langue FR/EN, source de données, modèle, date d'analyse (pour revoir
n'importe quel jour passé) et seuil de probabilité de stress.

## Ligne de commande

```bash
python -m pfe_drai status                     # régime du jour
python -m pfe_drai --lang en backtest         # métriques hors échantillon des 3 modèles
python -m pfe_drai report --format pdf        # note de comité (md, html ou pdf)
python -m pfe_drai publish                    # entrée du jour dans track_record/
python -m pfe_drai api                        # API REST sur http://localhost:8000/docs
```

API : `GET /regime`, `/regime/history`, `/metrics`, `/scenarios`, `/report` (paramètres `lang`, `model`, `date`…).

## Méthode

- **Régimes sur 3 dimensions** : stress, croissance, inflation. 12 indicateurs point-in-time
  (z-scores sur l'historique disponible à chaque date, décalage de publication des séries mensuelles).
- **4 régimes** : Expansion, Surchauffe inflationniste, Ralentissement, Stress / crise.
  Les états des modèles non supervisés sont reliés aux régimes par des prototypes fixés dans
  `config/settings.yaml` (appariement un à un).
- **3 modèles** : k-means (référence), Statistical Jump Model (régimes persistants, filtrage causal),
  gradient boosting qui prévoit le régime à 1 semaine.
- **Validation** : walk-forward à fenêtre croissante ; épisodes de stress datés par une règle
  fixée avant les tests ; latence publiée pour chaque épisode ; fausses alertes par an ; Brier et calibration.
- **Track record** : un JSON par jour, hash SHA-256 chaîné dans `track_record/index.csv`,
  preuve OpenTimestamps si la commande `ots` est installée.

Détails : [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Brancher une vraie source de données

Tout passe par `config/settings.yaml`, sans toucher au code :

| Source | Réglage | Remarque |
|---|---|---|
| Données simulées | `provider: synthetic` | par défaut |
| Fichiers CSV | `provider: csv` | un fichier `date,value` par série dans `data_cache/csv/` |
| FRED / ALFRED | `provider: fred` + variable `FRED_API_KEY` | clé gratuite ; les ETF manquants viennent de `fred_fallback` |
| Yahoo Finance | `provider: yahoo` + `pip install -e ".[yahoo]"` | usage recherche uniquement |

Pour une nouvelle API : une classe dans `pfe_drai/data/`, héritée de `DataProvider`, décorée
par `@register`, qui renvoie les séries de `pfe_drai/data/catalog.py`. Voir la marche à suivre
dans [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#ajouter-une-source-de-données).

## Structure

```
config/        settings.yaml (tous les réglages), scenarios.yaml, funds.yaml
pfe_drai/
  data/        sources : synthetic, csv, fred, yahoo ; catalogue des séries
  features/    12 indicateurs point-in-time -> scores stress / croissance / inflation
  regimes.py   définitions, couleurs, règle d'étiquetage, prototypes
  models/      kmeans, jump, gbm (interface commune + registre)
  validation/  walk-forward, datation des épisodes, latence, fausses alertes, calibration
  scenarios/   bibliothèque de stress, sélection selon le régime, impact sur un fonds
  reporting/   note de comité FR/EN (Markdown, HTML, PDF)
  publish/     publication quotidienne horodatée
  alerts.py    règles d'alerte
  pipeline.py  enchaîne tout ; utilisé par l'app, l'API, la CLI et les tests
  i18n/        t(clé, langue) ; textes dans locales/fr.json et locales/en.json
app/           tableau de bord Streamlit
api/           API FastAPI
track_record/  publications quotidiennes
tests/         pytest
```

## Tests

```bash
pytest -q && ruff check .
```

---

Information générale sur les marchés, identique pour tous. Ne constitue pas un conseil en investissement.
