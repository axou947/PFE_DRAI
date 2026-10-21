# Arbres de choix — version éditable (Mermaid)

Généré depuis `_build/content.py`. Collez un bloc dans Notion, GitHub ou [mermaid.live](https://mermaid.live) pour le modifier.

## Arbre n°1 — Détecteur de début de stress (protocole pré-enregistré)

Filtres :

- F1 — Holdout 1999-2009 : ≤ 1,5 FA/an et ≤ 10 % des jours calmes ?
- F2 — Latence médiane (tous épisodes) ≤ 5 j ?
- F3 — Gagnant du départage pré-enregistré ?

```mermaid
flowchart TD
    Q["Quel détecteur ajoute-t-on pour signaler le stress en ≤ 5 jours<br/>sans dépasser 1,5 fausse alerte par an ?"]
    Q --> O0["v1 actuel<br/>jump + gbm"]
    O0 -- "F2 — Latence médiane" --> X0_1["Écarté : Réel : 5/11 épisodes,<br/>latence 60 j"]
    class X0_1 rej
    Q --> O1["Logistique<br/>marché"]
    O1 -- "F2 — Latence médiane" --> X1_1["Écarté : Holdout : 3/6,<br/>latence 41,5 j"]
    class X1_1 rej
    Q --> O2["Logistique<br/>marché + crédit"]
    O2 -- "F2 — Latence médiane" --> X2_1["Écarté : Holdout : 3/6,<br/>latence 41,5 j"]
    class X2_1 rej
    Q --> O3["Boosting<br/>marché + crédit"]
    O3 -- "F3 — Gagnant du départage" --> X3_2["Écarté : Égalité → règle :<br/>candidat antérieur"]
    class X3_2 rej
    Q --> O4["Boosting<br/>marché"]
    O4 ==> R["✓ Boosting / marché → v2 = max(jump, gbm, onset)<br/>Réel 2009-2026 : 11/11 épisodes, −3 j, 1,26 FA/an"]
    class R ok
    classDef rej fill:#FDECEA,stroke:#C0392B
    classDef alt fill:#FEF3C7,stroke:#D97706
    classDef ok fill:#E8F5E9,stroke:#2E7D32
```

**Synthèse.** Décision (01/10/2026, pré-enregistrée avant tout calcul sur données réelles) : le détecteur gradient boosting sur données de marché est ajouté au modèle. Sur les 11 épisodes réels hors échantillon, il les détecte tous, avec une latence médiane de −3 jours et 1,26 fausse alerte par an. Compromis assumé : les fausses alertes passent de 0,17 à 1,26 par an, proches de la limite, et les changements de régime de 3,4 à 5,6 par an. Limite : ces épisodes avaient déjà été vus ; seul le track record live est un test en aveugle.

## Arbre n°2 — Sources de données

Filtres :

- F1 — Coût total ≤ 300 € sur le projet ?
- F2 — Licence autorise la publication de scores dérivés ?
- F3 — Historique ≥ 2004 et première publication ?

```mermaid
flowchart TD
    Q["Où obtenir 20 ans de données quotidiennes, sans information future,<br/>dans 300 € et avec le droit de publier nos scores ?"]
    Q --> O0["Bloomberg /<br/>Refinitiv"]
    O0 -- "F1 — Coût total ≤ 300 €" --> X0_0["Écarté : ≈ 2 000 €/mois<br/>[À VÉRIFIER]"]
    class X0_0 rej
    Q --> O1["ICE BofA<br/>via FRED"]
    O1 -- "F2 — Licence autorise la" --> X1_1["Écarté : Redistribution<br/>interdite ; 3 ans<br/>d'historique"]
    class X1_1 rej
    Q --> O2["S&P 500<br/>via FRED"]
    O2 -- "F2 — Licence autorise la" --> X2_1["Écarté : Reproduction<br/>interdite ;<br/>débute en 2016"]
    class X2_1 rej
    Q --> O3["Yahoo<br/>Finance"]
    O3 -- "F2 — Licence autorise la" --> X3_1["Gardé autrement : Usage recherche<br/>seulement<br/>→ fournisseur test"]
    class X3_1 alt
    Q --> O4["FRED/ALFRED<br/>+ Tiingo (ETF)"]
    O4 ==> R["✓ FRED/ALFRED (macro en 1re publication, VIX) + Tiingo (SPY, HYG, LQD, IEF)<br/>Licence notée série par série dans data/catalog.py"]
    class R ok
    classDef rej fill:#FDECEA,stroke:#C0392B
    classDef alt fill:#FEF3C7,stroke:#D97706
    classDef ok fill:#E8F5E9,stroke:#2E7D32
```

**Synthèse.** Décision : FRED/ALFRED pour la macro (chaque chiffre lu dans sa première publication, daté du jour de sa sortie) et Tiingo pour les prix d'ETF. Compromis assumé : les ETF remplacent les indices sous licence, et avant 2007 le crédit investment grade (LQD/IEF) remplace le high yield (HYG). Limite : l'offre gratuite de Tiingo couvre la recherche ; un usage commercial demanderait une offre payante.

## Arbre n°3 — Modèle des régimes

Filtres :

- F1 — Entraînable avec une dizaine de crises ?
- F2 — Régimes persistants (pas de « flip-flop ») ?
- F3 — Non supervisé (pas d'étiquettes arbitraires) ?

```mermaid
flowchart TD
    Q["Quel modèle pour produire chaque jour un régime persistant<br/>et nommable par un comité ?"]
    Q --> O0["Deep learning<br/>(LSTM, VAE)"]
    O0 -- "F1 — Entraînable avec une" --> X0_0["Écarté : Trop de paramètres ;<br/>projet ING4 : Sharpe<br/>0,35 vs 0,63"]
    class X0_0 rej
    Q --> O1["HMM<br/>gaussien"]
    O1 -- "F2 — Régimes persistants" --> X1_1["Écarté : Flip-flop documenté<br/>(Nystrup et al. 2020)"]
    class X1_1 rej
    Q --> O2["k-means /<br/>GMM"]
    O2 -- "F2 — Régimes persistants" --> X2_1["Gardé autrement : Sans notion<br/>de temps<br/>→ référence"]
    class X2_1 alt
    Q --> O3["Gradient<br/>boosting"]
    O3 -- "F3 — Non supervisé" --> X3_2["Gardé autrement : Prévision à 1 sem.<br/>→ source de<br/>P(stress)"]
    class X3_2 alt
    Q --> O4["Statistical<br/>Jump Model"]
    O4 ==> R["✓ Statistical Jump Model pour les régimes (pénalité de saut)<br/>k-means en référence, boosting comme source de P(stress)"]
    class R ok
    classDef rej fill:#FDECEA,stroke:#C0392B
    classDef alt fill:#FEF3C7,stroke:#D97706
    classDef ok fill:#E8F5E9,stroke:#2E7D32
```

**Synthèse.** Décision : le Statistical Jump Model nomme les régimes ; chaque état prend le nom du régime de la règle dont il est le plus proche, sans réglage à la main. Compromis assumé : la persistance peut retarder un changement, d'où le détecteur de stress séparé (arbre n°1).

## Arbre n°4 — Publication et preuve

Filtres :

- F1 — Vérifiable par un tiers, impossible à antidater ?
- F2 — Compétences dans l'équipe (0 profil front-end) ?
- F3 — Coût ≤ 50 € sur le projet ?

```mermaid
flowchart TD
    Q["Comment publier chaque jour un régime qu'un tiers peut vérifier<br/>sans nous faire confiance ?"]
    Q --> O0["Excel envoyé<br/>par e-mail"]
    O0 -- "F1 — Vérifiable par un tiers," --> X0_0["Écarté : Modifiable<br/>a posteriori"]
    class X0_0 rej
    Q --> O1["Base SQL<br/>sur serveur"]
    O1 -- "F1 — Vérifiable par un tiers," --> X1_0["Écarté : Réécrivable<br/>sans trace"]
    class X1_0 rej
    Q --> O2["Commits Git<br/>seuls"]
    O2 -- "F1 — Vérifiable par un tiers," --> X2_0["Écarté : Dates de commit<br/>modifiables"]
    class X2_0 rej
    Q --> O3["Front React<br/>+ cloud"]
    O3 -- "F2 — Compétences dans l'équipe" --> X3_1["Écarté : 0/5 profil<br/>front-end"]
    class X3_1 rej
    Q --> O4["GitHub Actions<br/>+ SHA-256<br/>+ OpenTimestamps"]
    O4 ==> R["✓ Job quotidien GitHub Actions à 22 h 30 : JSON chaîné par SHA-256, ancré dans Bitcoin<br/>Streamlit + API FastAPI pour l'accès"]
    class R ok
    classDef rej fill:#FDECEA,stroke:#C0392B
    classDef alt fill:#FEF3C7,stroke:#D97706
    classDef ok fill:#E8F5E9,stroke:#2E7D32
```

**Synthèse.** Décision : chaque jour ouvré, un job publie un fichier JSON chaîné à la veille par son empreinte SHA-256 et horodaté via OpenTimestamps dans Bitcoin. Un jour ne peut être ni modifié, ni supprimé, ni antidaté sans que cela se voie. État au 20/10 : 14 jours publiés, 13 déjà ancrés.

## Annexe — Arbre prévu pour la Phase 3 : actualité

Filtres :

- F1 — Coût ≤ 100 € ?
- F2 — Sans connaissance du futur (modèle figé, reproductible) ?
- F3 — Granularité quotidienne depuis 2015 ?

```mermaid
flowchart TD
    Q["Comment transformer l'actualité en variable quotidienne,<br/>sans fuite du futur, dans le budget ?"]
    Q --> O0["RavenPack /<br/>Permutable"]
    O0 -- "F1 — Coût ≤ 100 € ?" --> X0_0["Écarté : Sur devis,<br/>hors budget"]
    class X0_0 rej
    Q --> O1["LLM (API) sur<br/>tout l'historique"]
    O1 -- "F2 — Sans connaissance du futur" --> X1_1["Écarté : Le LLM « connaît »<br/>les crises ; non<br/>reproductible"]
    class X1_1 rej
    Q --> O2["Indice EPU<br/>(Baker et al.)"]
    O2 -- "F3 — Granularité quotidienne" --> X2_2["Gardé autrement : US seul<br/>→ variable témoin"]
    class X2_2 alt
    Q --> O3["GDELT +<br/>FinBERT local"]
    O3 ==> R["✓ Prévu : titres GDELT notés par FinBERT, publiés en challenger live<br/>(non implémenté au 21/10)"]
    class R ok
    classDef rej fill:#FDECEA,stroke:#C0392B
    classDef alt fill:#FEF3C7,stroke:#D97706
    classDef ok fill:#E8F5E9,stroke:#2E7D32
```

**Synthèse.** Prévu pour la Phase 3 : FinBERT exécuté localement sur les titres GDELT, ajouté comme challenger publié en live. Comme les crises passées ont déjà été vues, seul le live peut dire si l'actualité accélère la détection.
