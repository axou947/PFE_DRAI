"""Contenu partagé entre le support PowerPoint et les documents Word.

Les chiffres de détection, de calibration et du track record viennent du dépôt
PFE_DRAI (docs/DETECTION_V2.md, docs/CALIBRATION.md, track_record/), état au
21/10/2026. Tout ce qui est marqué FICTIF (entretiens, sondage, marché) est
illustratif et doit être remplacé par les vrais résultats de l'équipe.
"""

PROJET = "Détection de régimes de marché par IA"
GROUPE = "Groupe 1 — #PFE27-P-3549"
COACH = "Francesco Pandolfi"
EQUIPE = [
    ("Robin Lamy", "Finance", "Garant du besoin (J2)"),
    ("Gabriel Maisonnave", "Finance", "Investigateur (J2)"),
    ("Amine Amerdal", "Finance", "Intégrateur (J2)"),
    ("Titouan Andre", "Finance", "Scribe (J2)"),
    ("Axel Alacache", "Data & IA", "Facilitateur (J2)"),
]

PITCH_2_PHRASES = (
    "Chaque soir, notre outil indique aux petits gérants de fonds européens "
    "dans quel « climat » se trouvent les marchés (Expansion, Surchauffe, "
    "Ralentissement ou Stress), avec une probabilité calibrée et les raisons de "
    "ce diagnostic. Il leur fournit une note prête pour leur comité des risques "
    "et un historique public, horodaté et infalsifiable, de tous ses signaux, "
    "pour qu'ils réduisent le risque plus tôt et justifient leurs décisions."
)

HYPOTHESE_RISQUEE = (
    "En backtest, la détection tient ses objectifs. Ce qui reste incertain : "
    "(1) qu'elle les tienne en réel, sur des crises que le modèle n'a jamais "
    "vues ; (2) qu'un gérant change vraiment sa décision grâce à la note de "
    "comité. Aucun test utilisateur n'a encore eu lieu : c'est le cœur du J3."
)

EVOLUTION_J1_J2 = [
    "Régimes définis sur 3 dimensions (stress, croissance, inflation) au lieu de 2 "
    "axes : l'inflation de 2022 n'est pas un épisode de volatilité.",
    "Détection du stress refondue (v2, pré-enregistrée le 01/10) : un détecteur "
    "de début d'épisode s'ajoute au jump model ; objectifs atteints en backtest.",
    "Track record public lancé le 01/10 (au lieu du 30/10 prévu), horodaté dans "
    "Bitcoin ; 4 zones publiées (US, Royaume-Uni, Japon, émergents), la zone euro "
    "a échoué à son test et reste expérimentale.",
    "La couche news IA n'est pas commencée : elle passe en challenger de Phase 3.",
    "Cible inchangée : petits gérants et family offices, CGP en cible secondaire.",
]

RESULTATS = [
    ("11 / 11", "épisodes de stress réels détectés (2009-2026)"),
    ("−3 j", "latence médiane (objectif ≤ 5 j)"),
    ("1,26", "fausse alerte / an (limite 1,5)"),
    ("0,091", "score de Brier calibré (0,100 avant)"),
]

# ---------------------------------------------------------------- MoSCoW
# (fonctionnalité, justification, statut au 21/10)
MOSCOW = {
    "Must have": [
        ("Données point-in-time (FRED/ALFRED en première publication, Tiingo) avec "
         "licence vérifiée pour chaque série",
         "Sans données datées du jour de publication, toute latence mesurée serait "
         "trop optimiste.", "Fait"),
        ("4 régimes sur 3 dimensions par une règle transparente, Statistical Jump "
         "Model pour des régimes persistants",
         "Un comité doit pouvoir nommer chaque régime et savoir d'où il vient.", "Fait"),
        ("Détecteur de stress v2 pré-enregistré, validé une seule fois sur les 11 "
         "épisodes réels", "C'est la promesse de valeur ; arbre n°1.", "Fait"),
        ("Probabilité de stress calibrée (Platt), courbe de fiabilité publiée",
         "« 30 % » doit vouloir dire 3 fois sur 10.", "Fait"),
        ("Explication : contribution de chaque indicateur, ce qui ferait basculer, ce "
         "qui a changé en une semaine", "Un score brut ne se vend pas (10/13 "
         "entretiens, FICTIF).", "Fait"),
        ("Note de comité des risques PDF / HTML / Markdown, FR et EN",
         "Sortie n°1 attendue par les gérants (37 % du sondage, FICTIF).", "Fait"),
        ("Track record public quotidien : SHA-256 chaîné + horodatage Bitcoin",
         "La preuve live est notre différenciation et ne se rattrape pas.",
         "En ligne depuis le 01/10"),
        ("Tests utilisateurs avec au moins 3 gérants sur la note de comité",
         "Seul moyen de vérifier que l'outil change une décision : c'est "
         "l'hypothèse la plus risquée.", "À faire (J3)"),
    ],
    "Should have": [
        ("Régime Ralentissement fiable face à une référence externe (CFNAI)",
         "Aujourd'hui au niveau du hasard (0,492) : il faut le corriger ou l'afficher "
         "comme expérimental.", "En cours (v2.3 rejetée)"),
        ("Overlay de risque 60/40 après coûts (drawdown, Calmar)",
         "Critère de succès du J1, pas encore évalué : traduit le signal en euros.",
         "À faire"),
        ("Couche actualité IA (GDELT + FinBERT) publiée en challenger",
         "Question scientifique du J1 ; testée en live pour ne pas revoir le passé.",
         "À faire"),
        ("Alertes (écran + e-mail) et scénarios de stress sur un portefeuille",
         "Usage quotidien du gérant entre deux comités.", "Fait"),
        ("API REST", "Intégration dans les outils du gérant.", "Fait"),
    ],
    "Could have": [
        ("Zones Royaume-Uni, Japon, émergents (publiées) et euro (expérimentale)",
         "Différenciant pour l'Europe, mais seul le modèle US est validé en profondeur.",
         "Fait (euro échouée)"),
        ("Pages « Apprendre » et carte des marchés mondiaux",
         "Utile en vitrine, sans lien direct avec la décision du gérant.", "Fait"),
        ("Tuteur IA « GAMA »", "Cible secondaire et vitrine.", "Affiché, non actif"),
        ("Rapport de thèse généré depuis les enregistrements",
         "Garantit que les chiffres publiés sont ceux du code.", "Fait"),
    ],
    "Won't have": [
        ("Signaux d'achat/vente ou recommandation sur un portefeuille client",
         "Relèverait du conseil en investissement (MiFID II, AMF DOC-2008-23).", "—"),
        ("Vente de données brutes ; redistribution des prix de marché",
         "Interdit par les licences ; pas notre cible.", "—"),
        ("Deep learning (VAE, LSTM), SOM, TDA, HDP-HMM",
         "Trop de paramètres pour une dizaine de crises ; réservés au mémoire.", "—"),
        ("Temps réel / intraday", "Un comité décide à la semaine.", "—"),
        ("Comptes clients, paiement, application mobile",
         "N'aide pas à prouver la valeur au J3.", "—"),
    ],
}

# ---------------------------------------------------------------- Risques
# (id, catégorie, risque, probabilité, impact, mitigation, déclencheur)
RISQUES = [
    ("R1", "Externe",
     "Aucun test utilisateur réalisé : les gérants ne sont pas disponibles en novembre",
     "Forte", "Fort",
     "6 volontaires identifiés (FICTIF) : sessions planifiées dès le 09/11, protocole "
     "de 30 min sur la note de comité. Secours : protocole asynchrone (vidéo + "
     "formulaire de 10 min), CGP du réseau, alumni ECE en gestion d'actifs.",
     "Moins de 3 sessions confirmées au 06/11"),
    ("R2", "Technique",
     "En réel, les fausses alertes dépassent 1,5 par an (backtest : 1,26, sur des "
     "épisodes déjà vus)",
     "Moyenne", "Fort",
     "Aucun réglage après coup (règle pré-enregistrée). Challengers publiés en live "
     "à côté du modèle. Communication honnête : « environ une fausse alerte par an ». "
     "Plan B pré-enregistré : revenir au détecteur v1 (0,17 fausse alerte/an, plus lent).",
     "2 fausses alertes dans le track record live"),
    ("R3", "Organisationnel",
     "Appropriation du code : code écrit en grande partie avec un assistant IA et "
     "porté par 2 contributeurs ; les 5 membres doivent pouvoir le défendre",
     "Forte", "Fort",
     "Un module « propriétaire » par membre, présenté aux autres en 15 min. Revue de "
     "code obligatoire. Répétition de questions techniques avant chaque soutenance. "
     "La documentation docs/ sert de support.",
     "Un membre ne sait pas expliquer son module en répétition"),
    ("R4", "Technique",
     "Le régime Ralentissement reste au niveau du hasard face à la référence CFNAI (0,492)",
     "Forte", "Moyen",
     "Nouvelle tentative pré-enregistrée (v2.4). Si elle échoue : afficher le score de "
     "croissance (0,620) plutôt que le régime, et marquer Ralentissement comme "
     "expérimental dans la note.",
     "Échec de la v2.4 au 13/11"),
    ("R5", "Organisationnel",
     "Dispersion : des fonctionnalités hors MVP (Apprendre, carte mondiale, 4 zones) "
     "consomment le temps des Must restants",
     "Forte", "Moyen",
     "Gel des nouvelles fonctionnalités jusqu'aux tests utilisateurs. Chaque tâche "
     "Notion porte sa catégorie MoSCoW ; aucune tâche Could tant qu'un Must est ouvert.",
     "Une tâche Could démarrée avant le 20/11"),
    ("R6", "Externe",
     "Panne de la publication quotidienne ou d'une source (FRED, Tiingo, Bitcoin)",
     "Moyenne", "Moyen",
     "Contrôle de santé automatique (workflow health), jour manquant signalé, "
     "secours Tiingo pour FRED, journal des publications. Un jour manqué est montré, "
     "jamais rattrapé en douce.", "Publication en échec 2 jours de suite"),
    ("R7", "Légal",
     "Les scénarios sur le portefeuille du client glissent vers du conseil personnalisé",
     "Moyenne", "Fort",
     "Impact chiffré seulement, aucune recommandation d'ajustement ; CSV lu en mémoire, "
     "jamais conservé ; avertissement sur chaque sortie ; relecture des formulations "
     "par le Garant du besoin.", "Une formulation « réduisez / vendez » en relecture"),
]

# ---------------------------------------------------------------- Arbres
# résultat : "ok" (passe), ("x", raison) écarté, ("b", raison) gardé autrement
ARBRES = {
    "detection": {
        "titre": "Arbre n°1 — Détecteur de début de stress (protocole pré-enregistré)",
        "question": "Quel détecteur ajoute-t-on pour signaler le stress en ≤ 5 jours\n"
                    "sans dépasser 1,5 fausse alerte par an ?",
        "filtres": [
            "F1 — Holdout 1999-2009 :\n≤ 1,5 FA/an et ≤ 10 %\ndes jours calmes ?",
            "F2 — Latence médiane\n(tous épisodes) ≤ 5 j ?",
            "F3 — Gagnant du départage\npré-enregistré ?",
        ],
        "options": [
            ("v1 actuel\njump + gbm", ["ok", ("x", "Réel : 5/11 épisodes,\nlatence 60 j")]),
            ("Logistique\nmarché", ["ok", ("x", "Holdout : 3/6,\nlatence 41,5 j")]),
            ("Logistique\nmarché + crédit", ["ok", ("x", "Holdout : 3/6,\nlatence 41,5 j")]),
            ("Boosting\nmarché + crédit", ["ok", "ok", ("x", "Égalité → règle :\ncandidat antérieur")]),
            ("Boosting\nmarché", ["ok", "ok", "ok"]),
        ],
        "retenu": "Boosting / marché → v2 = max(jump, gbm, onset)\n"
                  "Réel 2009-2026 : 11/11 épisodes, −3 j, 1,26 FA/an",
        "synthese": (
            "Décision (01/10/2026, pré-enregistrée avant tout calcul sur données réelles) : "
            "le détecteur gradient boosting sur données de marché est ajouté au modèle. "
            "Sur les 11 épisodes réels hors échantillon, il les détecte tous, avec une "
            "latence médiane de −3 jours et 1,26 fausse alerte par an. Compromis assumé : "
            "les fausses alertes passent de 0,17 à 1,26 par an, proches de la limite, et "
            "les changements de régime de 3,4 à 5,6 par an. Limite : ces épisodes avaient "
            "déjà été vus ; seul le track record live est un test en aveugle."
        ),
    },
    "donnees": {
        "titre": "Arbre n°2 — Sources de données",
        "question": "Où obtenir 20 ans de données quotidiennes, sans information future,\n"
                    "dans 300 € et avec le droit de publier nos scores ?",
        "filtres": [
            "F1 — Coût total ≤ 300 €\nsur le projet ?",
            "F2 — Licence autorise la\npublication de scores dérivés ?",
            "F3 — Historique ≥ 2004 et\npremière publication ?",
        ],
        "options": [
            ("Bloomberg /\nRefinitiv", [("x", "≈ 2 000 €/mois\n[À VÉRIFIER]")]),
            ("ICE BofA\nvia FRED", ["ok", ("x", "Redistribution\ninterdite ; 3 ans\nd'historique")]),
            ("S&P 500\nvia FRED", ["ok", ("x", "Reproduction\ninterdite ;\ndébute en 2016")]),
            ("Yahoo\nFinance", ["ok", ("b", "Usage recherche\nseulement\n→ fournisseur test")]),
            ("FRED/ALFRED\n+ Tiingo (ETF)", ["ok", "ok", "ok"]),
        ],
        "retenu": "FRED/ALFRED (macro en 1re publication, VIX) + Tiingo (SPY, HYG, LQD, IEF)\n"
                  "Licence notée série par série dans data/catalog.py",
        "synthese": (
            "Décision : FRED/ALFRED pour la macro (chaque chiffre lu dans sa première "
            "publication, daté du jour de sa sortie) et Tiingo pour les prix d'ETF. "
            "Compromis assumé : les ETF remplacent les indices sous licence, et avant 2007 "
            "le crédit investment grade (LQD/IEF) remplace le high yield (HYG). Limite : "
            "l'offre gratuite de Tiingo couvre la recherche ; un usage commercial "
            "demanderait une offre payante."
        ),
    },
    "modele": {
        "titre": "Arbre n°3 — Modèle des régimes",
        "question": "Quel modèle pour produire chaque jour un régime persistant\n"
                    "et nommable par un comité ?",
        "filtres": [
            "F1 — Entraînable avec une\ndizaine de crises ?",
            "F2 — Régimes persistants\n(pas de « flip-flop ») ?",
            "F3 — Non supervisé\n(pas d'étiquettes arbitraires) ?",
        ],
        "options": [
            ("Deep learning\n(LSTM, VAE)", [("x", "Trop de paramètres ;\nprojet ING4 : Sharpe\n0,35 vs 0,63")]),
            ("HMM\ngaussien", ["ok", ("x", "Flip-flop documenté\n(Nystrup et al. 2020)")]),
            ("k-means /\nGMM", ["ok", ("b", "Sans notion\nde temps\n→ référence")]),
            ("Gradient\nboosting", ["ok", "ok", ("b", "Prévision à 1 sem.\n→ source de\nP(stress)")]),
            ("Statistical\nJump Model", ["ok", "ok", "ok"]),
        ],
        "retenu": "Statistical Jump Model pour les régimes (pénalité de saut)\n"
                  "k-means en référence, boosting comme source de P(stress)",
        "synthese": (
            "Décision : le Statistical Jump Model nomme les régimes ; chaque état prend le "
            "nom du régime de la règle dont il est le plus proche, sans réglage à la main. "
            "Compromis assumé : la persistance peut retarder un changement, d'où le "
            "détecteur de stress séparé (arbre n°1)."
        ),
    },
    "diffusion": {
        "titre": "Arbre n°4 — Publication et preuve",
        "question": "Comment publier chaque jour un régime qu'un tiers peut vérifier\n"
                    "sans nous faire confiance ?",
        "filtres": [
            "F1 — Vérifiable par un tiers,\nimpossible à antidater ?",
            "F2 — Compétences dans l'équipe\n(0 profil front-end) ?",
            "F3 — Coût ≤ 50 €\nsur le projet ?",
        ],
        "options": [
            ("Excel envoyé\npar e-mail", [("x", "Modifiable\na posteriori")]),
            ("Base SQL\nsur serveur", [("x", "Réécrivable\nsans trace")]),
            ("Commits Git\nseuls", [("x", "Dates de commit\nmodifiables")]),
            ("Front React\n+ cloud", ["ok", ("x", "0/5 profil\nfront-end")]),
            ("GitHub Actions\n+ SHA-256\n+ OpenTimestamps", ["ok", "ok", "ok"]),
        ],
        "retenu": "Job quotidien GitHub Actions à 22 h 30 : JSON chaîné par SHA-256, ancré dans Bitcoin\n"
                  "Streamlit + API FastAPI pour l'accès",
        "synthese": (
            "Décision : chaque jour ouvré, un job publie un fichier JSON chaîné à la veille "
            "par son empreinte SHA-256 et horodaté via OpenTimestamps dans Bitcoin. Un jour "
            "ne peut être ni modifié, ni supprimé, ni antidaté sans que cela se voie. "
            "État au 20/10 : 14 jours publiés, 13 déjà ancrés."
        ),
    },
    "news": {
        "titre": "Annexe — Arbre prévu pour la Phase 3 : actualité",
        "question": "Comment transformer l'actualité en variable quotidienne,\n"
                    "sans fuite du futur, dans le budget ?",
        "filtres": [
            "F1 — Coût ≤ 100 € ?",
            "F2 — Sans connaissance du futur\n(modèle figé, reproductible) ?",
            "F3 — Granularité quotidienne\ndepuis 2015 ?",
        ],
        "options": [
            ("RavenPack /\nPermutable", [("x", "Sur devis,\nhors budget")]),
            ("LLM (API) sur\ntout l'historique", ["ok", ("x", "Le LLM « connaît »\nles crises ; non\nreproductible")]),
            ("Indice EPU\n(Baker et al.)", ["ok", "ok", ("b", "US seul\n→ variable témoin")]),
            ("GDELT +\nFinBERT local", ["ok", "ok", "ok"]),
        ],
        "retenu": "Prévu : titres GDELT notés par FinBERT, publiés en challenger live\n"
                  "(non implémenté au 21/10)",
        "synthese": (
            "Prévu pour la Phase 3 : FinBERT exécuté localement sur les titres GDELT, "
            "ajouté comme challenger publié en live. Comme les crises passées ont déjà été "
            "vues, seul le live peut dire si l'actualité accélère la détection."
        ),
    },
}

EPISODES_REELS = [
    # début, drawdown max, latence v2, latence v1 (None = manqué)
    ("2010-05", -15.7, -8, None), ("2011-08", -18.6, 1, 11), ("2011-12", -10.4, -17, None),
    ("2015-08", -11.9, 4, None), ("2016-01", -13.0, -2, 18), ("2018-02", -10.1, 2, None),
    ("2018-12", -19.3, -18, 6), ("2020-02", -33.7, 0, 5), ("2022-02", -12.9, -20, None),
    ("2022-05", -24.5, -5, None), ("2025-03", -18.8, -3, 18),
]

# ---------------------------------------------------------------- Études FICTIVES
SONDAGE_N = 54
SONDAGE_SEGMENTS = [("Gérants SGP", 17), ("Family offices", 9),
                    ("CGP / CIF", 21), ("Risque / conformité", 7)]
SONDAGE_DOULEURS = [
    ("Consolider des signaux dispersés\n(VIX, spreads, taux, news)", 78),
    ("Justifier une décision d'allocation\na posteriori (comité, clients)", 72),
    ("Réagir assez tôt en phase de stress", 69),
    ("Rédiger le commentaire de marché client", 57),
    ("Accéder à des modèles quantitatifs", 44),
    ("Coût des terminaux de données", 41),
]
SONDAGE_SORTIE = [("Note de comité PDF", 37), ("Alerte e-mail", 24),
                  ("Tableau de bord", 17), ("Commentaire client IA", 15),
                  ("API", 7)]
SONDAGE_CONFIANCE = [("Historique live publié", 74), ("Facteurs explicatifs", 70),
                     ("Méthode publiée", 46), ("Performance en backtest", 31),
                     ("Marque / notoriété", 22)]
WTP_GERANTS = [("< 1 k€", 8), ("1-3 k€", 23), ("3-6 k€", 35), ("6-10 k€", 23), ("> 10 k€", 11)]
WTP_CGP = [("< 30 €", 19), ("30-60 €", 38), ("60-100 €", 29), ("> 100 €", 14)]

ENTRETIENS = [
    # code, profil, structure, encours, H1, H2, H3, test, payer, verbatim
    ("E01", "Gérante multi-actifs", "SGP 18 pers.", "520 M€", "V", "V", "V", True, True,
     "En mars 2020 on a coupé les actions avec dix jours de retard. Le plus dur, c'était d'expliquer pourquoi au comité."),
    ("E02", "CIO", "Family office", "1,1 Md€", "V", "V", "P", True, False,
     "Je ne veux pas un score de plus, je veux savoir ce qui a bougé cette semaine."),
    ("E03", "Gérant actions/obligations", "SGP 9 pers.", "180 M€", "V", "P", "P", False, False,
     "On regarde le VIX et les spreads sur Bloomberg, mais chacun a son interprétation."),
    ("E04", "Risk manager", "SGP 35 pers.", "2,3 Md€", "P", "V", "X", True, False,
     "Ce qui m'intéresse, c'est un historique que personne ne peut retoucher."),
    ("E05", "Gérant patrimonial", "Multi-family office", "650 M€", "V", "V", "V", True, True,
     "Si le rapport est propre, je le mets directement dans le pack du comité."),
    ("E06", "CGP / CIF", "Cabinet 4 pers.", "90 M€", "V", "V", "P", False, False,
     "Mes clients m'appellent quand ça baisse ; j'ai besoin d'un commentaire clair, vite."),
    ("E07", "CGP / CIF", "Cabinet 2 pers.", "40 M€", "P", "V", "V", False, False,
     "60 euros par mois, oui, si ça m'évite d'écrire ma lettre mensuelle."),
    ("E08", "Directeur des gestions", "SGP 22 pers.", "800 M€", "V", "P", "P", True, False,
     "Montrez-moi d'abord six mois de signaux en live, on en reparlera."),
    ("E09", "Gérant diversifié", "SGP 12 pers.", "300 M€", "V", "V", "X", False, False,
     "Le budget data est déjà pris par Bloomberg ; il faudrait remplacer quelque chose."),
    ("E10", "Allocataire", "Family office", "450 M€", "V", "V", "P", True, False,
     "En 2022, le vrai sujet était l'inflation, pas la volatilité : votre dimension inflation me parle."),
    ("E11", "CGP / CIF premium", "Cabinet 6 pers.", "210 M€", "V", "V", "V", False, False,
     "Je veux pouvoir montrer à mon client que le signal existait avant la baisse."),
    ("E12", "Gérant obligataire", "SGP 15 pers.", "350 M€", "X", "P", "X", False, False,
     "Notre mandat est contraint, on ne bouge pas l'allocation tous les mois."),
    ("E13", "Responsable conformité", "SGP 28 pers.", "1,4 Md€", "P", "V", "X", False, False,
     "Attention à la frontière avec le conseil : pas de « vendez », et méfiez-vous des simulations sur le portefeuille du client."),
]

TAM_SAM_SOM = [
    ("TAM", "Marché mondial de la détection de régimes par IA (2026)", "≈ 2,1 Md€", "2,28 Md USD — source J1"),
    ("SAM", "Petits gérants + family offices européens (≈ 3 500 structures × 6 000 €/an)\n+ CGP premium France (≈ 1 150 × 700 €/an)", "≈ 22 M€ / an", "FICTIF — hypothèses à sourcer"),
    ("SOM", "Objectif à 3 ans : 50 gérants + 150 CGP", "≈ 0,4 M€ / an", "FICTIF — 1,5 % du SAM gérants"),
]

# ---------------------------------------------------------------- Q&R
QR = [
    ("Vos épisodes de crise étaient connus quand vous avez conçu le détecteur : votre backtest n'est-il pas biaisé ?",
     "En partie, et nous le disons. Pour le limiter : le protocole a été pré-enregistré "
     "(publié avant tout calcul sur données réelles), le choix du détecteur s'est fait sur "
     "un holdout 1999-2009 jamais utilisé, puis un seul passage sur les 11 épisodes réels, "
     "sans réglage après coup. Le seul vrai test en aveugle, c'est le track record live "
     "lancé le 01/10, horodaté dans Bitcoin."),
    ("Une latence de −3 jours, vous prévoyez les crises ?",
     "Non. Le détecteur lit la même baisse et la même volatilité que la règle qui date les "
     "épisodes. Une latence proche de zéro veut dire « le jour où la règle date le début ». "
     "Les latences très négatives (−17 à −20 jours) viennent souvent d'une alarme d'un "
     "repli précédent encore active. Nous ne prétendons pas prévoir."),
    ("Comment définissez-vous le début d'un épisode de stress ?",
     "Par une règle gelée avant tout backtest (empreinte publiée) : baisse de 10 % depuis "
     "le plus haut sur un an, ou volatilité réalisée sur 21 jours au-dessus de son 95e "
     "centile historique. L'épisode se termine quand la baisse revient au-dessus de −5 %, "
     "avec 21 jours ouvrés minimum entre deux épisodes."),
    ("1,26 fausse alerte par an, c'est beaucoup pour un comité ?",
     "C'est proche de la limite de 1,5 fixée au J1, et nous le présentons comme un coût : "
     "environ une fausse alerte par an, courte (4,9 % des jours calmes). L'ancienne version "
     "en faisait 0,17 mais ratait 6 crises sur 11. Pour un gérant, rater une crise coûte "
     "plus cher qu'une fausse alerte : c'est à confirmer en entretien."),
    ("Où est l'IA sur l'actualité annoncée au J1 ?",
     "Pas encore implémentée, c'est un écart assumé par rapport au J1. L'IA est aujourd'hui "
     "dans les modèles (jump model, gradient boosting, calibration). La couche actualité "
     "(GDELT + FinBERT) sera publiée en challenger en Phase 3 : comme toutes les crises "
     "passées ont été vues, seul le live peut dire honnêtement si elle aide."),
    ("Au J1 vous disiez « MVP de 3 écrans, rien hors MVP avant J3 ». Pourquoi une carte mondiale et des pages pédagogiques ?",
     "C'est une dérive de périmètre et nous l'avons classée comme risque (R5). Ces écrans "
     "sont en Could have. Nous avons décidé un gel des nouvelles fonctionnalités jusqu'aux "
     "tests utilisateurs, qui sont le Must restant."),
    ("Le code a beaucoup de commits d'un assistant IA. Qui maîtrise quoi ?",
     "Nous utilisons un assistant de code, comme beaucoup d'équipes, mais chaque choix est "
     "documenté et pré-enregistré dans docs/. C'est notre risque R3 : chaque membre est "
     "propriétaire d'un module et doit pouvoir l'expliquer. [Préparer chacun une réponse "
     "sur son module.]"),
    ("Pourquoi pas du deep learning ?",
     "Une dizaine de crises en 20 ans : un réseau profond aurait des milliers de paramètres "
     "pour une poignée d'exemples. C'est le filtre F1 de l'arbre n°3. Le projet ING4 VAE-HMM "
     "de l'ECE l'illustre : plus complexe, mais Sharpe de 0,35 contre 0,63 en buy & hold."),
    ("Pourquoi 4 régimes sur 3 dimensions ?",
     "Parce qu'un comité doit pouvoir nommer chaque régime et agir dessus. Deux régimes "
     "« bull/bear » ne disent rien de l'inflation de 2022. Les trois dimensions (stress, "
     "croissance, inflation) reprennent un cadre connu des gérants (Bridgewater, Hedgeye)."),
    ("Votre régime Ralentissement est-il fiable ?",
     "Non, pas encore, et nous le publions : face à l'indice d'activité de la Fed de Chicago, "
     "le Ralentissement affiché fait 0,492, le niveau du hasard, alors que le score de "
     "croissance seul fait 0,620. Une version corrigée sera pré-enregistrée ; à défaut, il "
     "sera marqué expérimental."),
    ("Comment garantissez-vous l'absence de look-ahead ?",
     "Les séries révisées sont lues dans ALFRED en première publication, datées du jour de "
     "leur sortie. Le walk-forward réapprend chaque année sur le passé seul. Des tests "
     "vérifient que supprimer les deux dernières années ne change aucune prédiction plus "
     "ancienne."),
    ("Comment prouver que vous n'avez pas modifié le track record ?",
     "Chaque jour est un fichier JSON chaîné à la veille par son empreinte SHA-256 et "
     "horodaté via OpenTimestamps dans la blockchain Bitcoin. Modifier, supprimer ou "
     "antidater un jour casse la chaîne. Deux commandes publiques permettent à n'importe "
     "qui de le vérifier."),
    ("Qu'est-ce qui vous différencie de Permutable ou de 42 Macro ?",
     "Permutable vend une donnée de sentiment aux hedge funds ; 42 Macro vend une analyse "
     "humaine peu transparente. Nous proposons un régime expliqué, une latence publiée et "
     "un historique vérifiable par un tiers, pour un petit gérant. Personne ne combine les "
     "trois."),
    ("Avez-vous validé le besoin ?",
     "13 entretiens et 54 réponses à un questionnaire [FICTIF : remplacer par vos chiffres]. "
     "9 sur 13 confirment pleinement la douleur, 10 préfèrent un rapport expliqué à un "
     "score. Le prix reste fragile. Et surtout, aucun test utilisateur du prototype n'a "
     "encore eu lieu : c'est le Must du J3."),
    ("N'est-ce pas du conseil en investissement ?",
     "Non tant que l'information est identique pour tous. Le point sensible est l'écran de "
     "scénarios sur le portefeuille du client : il chiffre un impact, ne recommande jamais "
     "d'ajustement, et le fichier n'est jamais conservé. C'est notre risque R7."),
    ("Avez-vous évalué une stratégie, un gain en euros ?",
     "Pas encore : l'overlay 60/40 du J1 est un Should non fait. Le projet mesure aujourd'hui "
     "la détection et la qualité d'une probabilité, pas la performance d'un portefeuille."),
    ("Avez-vous besoin de matériel ? Quel budget ?",
     "Aucun matériel. Tout tourne sur des offres gratuites (FRED, Tiingo, GitHub Actions, "
     "OpenTimestamps). Seule dépense prévue : environ 40 € d'API de modèle de langage pour "
     "le tuteur et la couche actualité, via le bon de commande."),
]
