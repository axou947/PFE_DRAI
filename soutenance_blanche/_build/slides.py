"""Déroulé de la soutenance : une entrée par slide, avec le texte à dire."""

SLIDES = [
    {
        "titre": "Détection de régimes de marché par IA",
        "kind": "title",
        "orateur": "Axel",
        "duree": 15,
        "script": (
            "Bonjour à tous. Nous sommes le groupe 1 : Robin, Gabriel, Amine, Titouan "
            "et moi-même, Axel. Notre projet : un outil qui détecte par IA dans quel "
            "régime se trouvent les marchés financiers, pour aider les petits gérants "
            "à réduire leur risque plus tôt. En dix minutes : le contexte, le besoin, "
            "l'état de l'art, la solution choisie et les risques qui pourraient la "
            "faire dérailler."
        ),
    },
    {
        "titre": "Contexte : les crises arrivent, les gérants réagissent trop tard",
        "kind": "image",
        "img": "01_contexte.png",
        "bullets": ["11 épisodes de stress réels depuis 2009 : de −10 % à −34 %",
                    "Délai de réaction déclaré par les gérants : 9 à 19 jours",
                    "Objectif du projet : moins de 5 jours"],
        "orateur": "Titouan",
        "duree": 45,
        "script": (
            "Depuis 2009, notre règle de datation a identifié onze épisodes de stress "
            "sur le marché américain : la dette européenne en 2011, l'été 2015, fin "
            "2018, le Covid, l'inflation en 2022, les droits de douane en 2025. À "
            "gauche, la baisse maximale à chaque fois : de moins 10 à moins 34 %. Le "
            "problème n'est pas que ces crises arrivent, c'est qu'on y réagit tard. À "
            "droite, ce que nous ont dit les gérants interrogés : entre 9 et 19 jours "
            "de bourse pour réduire leur exposition. Or quelques jours suffisent pour "
            "subir l'essentiel de la baisse. Notre objectif : moins de 5 jours."
        ),
    },
    {
        "titre": "Problématique, objectifs… et où nous en sommes",
        "kind": "statement",
        "statement": "« Les gérants de petites structures sans équipe quantitative repèrent "
                     "trop tard l'entrée des marchés en stress, et peinent à justifier "
                     "a posteriori leurs décisions de risque. »",
        "question": "Comment une IA peut-elle signaler l'entrée en stress en ≤ 5 jours de "
                    "bourse, avec ≤ 1,5 fausse alerte par an, tout en expliquant son signal "
                    "à un comité d'allocation ?",
        "kpis": [("≤ 5 j", "latence de détection", "backtest : −3 j"),
                 ("≤ 1,5", "fausse alerte / an", "backtest : 1,26"),
                 ("calibrée", "probabilité de stress", "Brier 0,100 → 0,091")],
        "orateur": "Amine",
        "duree": 50,
        "script": (
            "D'où notre problème : les gérants de petites structures, sans équipe "
            "quantitative, repèrent trop tard l'entrée en stress et peinent à justifier "
            "ensuite leurs décisions. Notre question directrice est mesurable : 5 jours "
            "de latence au plus, 1,5 fausse alerte par an au plus, et un signal "
            "expliqué. En bas, ce que donne déjà notre backtest sur données réelles "
            "2009-2026 : latence médiane de moins 3 jours, 1,26 fausse alerte par an, "
            "une probabilité calibrée. Attention : c'est un backtest sur des crises que "
            "nous connaissions. La vraie preuve, c'est le suivi en direct, on y revient."
        ),
    },
    {
        "titre": "Pour qui ? Un besoin vérifié sur le terrain",
        "kind": "persona",
        "img": "02_entretiens.png",
        "persona": ["« Claire », gérante multi-actifs",
                    "SGP de 15 personnes, 400 M€ d'encours",
                    "Comité d'allocation mensuel, pas de quant",
                    "Outils : Bloomberg ou Koyfin, Excel",
                    "Douleur : décide trop tard, justifie mal",
                    "Achète : un signal, ses raisons, un historique honnête"],
        "bullets": ["13 entretiens (gérants, family offices, CGP)",
                    "6 prêts à tester · 2 prêts à payer"],
        "orateur": "Robin",
        "duree": 50,
        "script": (
            "Notre cible, c'est Claire : gérante multi-actifs dans une société de "
            "gestion de 15 personnes, 400 millions d'encours, comité mensuel, pas de "
            "quant en interne. Pour vérifier qu'elle existe vraiment, nous avons mené 13 "
            "entretiens de 20 minutes. 9 sur 13 confirment pleinement la douleur "
            "« décider trop tard et devoir justifier », et 10 sur 13 préfèrent un "
            "rapport expliqué à un simple score. En revanche, le prix est notre "
            "hypothèse la plus fragile : seuls 4 la valident pleinement. 6 "
            "professionnels sont prêts à tester le prototype, 2 prêts à payer."
        ),
    },
    {
        "titre": "Ce que disent 54 professionnels (questionnaire en ligne)",
        "kind": "image",
        "img": "03_sondage_besoins.png",
        "bullets": ["3 douleurs majeures : consolider, justifier, réagir tôt",
                    "La note de comité PDF est la sortie n°1"],
        "orateur": "Robin",
        "duree": 30,
        "script": (
            "Nous avons complété par un questionnaire en ligne : 54 réponses. Trois "
            "douleurs ressortent nettement : consolider des signaux dispersés, "
            "justifier une décision, réagir tôt. Et sur le format, le message est "
            "clair : la note de comité en PDF arrive en tête, loin devant le tableau "
            "de bord."
        ),
    },
    {
        "titre": "État de l'art : la méthode est publique, la preuve ne l'est pas",
        "kind": "image",
        "img": "07_etat_art.png",
        "bullets": ["HMM : référence (Hamilton 1989) mais « flip-flop »",
                    "Clustering : simple, sans notion de temps",
                    "Deep learning : trop gourmand pour une dizaine de crises",
                    "Statistical Jump Model (Shu & Mulvey 2024) : régimes persistants, testé hors échantillon"],
        "orateur": "Gabriel",
        "duree": 50,
        "script": (
            "Nous avons comparé les familles de méthodes. Les modèles de Markov cachés "
            "sont la référence depuis Hamilton en 1989, mais ils changent d'état trop "
            "souvent. Le clustering est simple mais n'a aucune notion de temps. Le deep "
            "learning demande beaucoup de données, alors qu'on a une dizaine de crises "
            "en vingt ans. La méthode qui sort du lot, c'est le Statistical Jump Model, "
            "de Nystrup puis Shu et Mulvey en 2024 : il pénalise chaque changement de "
            "régime, ce qui donne des régimes stables. Notre leçon : les algorithmes "
            "sont publics, ce n'est pas la méthode qui fait la différence, c'est la "
            "preuve."
        ),
    },
    {
        "titre": "Positionnement : un espace libre pour les petits gérants",
        "kind": "image",
        "img": "06_positionnement.png",
        "bullets": ["À droite : data institutionnelle sur devis",
                    "À gauche : scores bruts gratuits",
                    "Notre espace : régime expliqué + latence publiée + historique vérifiable",
                    "Marché adressable estimé ≈ 22 M€/an (Europe)"],
        "orateur": "Gabriel",
        "duree": 30,
        "script": (
            "Côté marché : à droite, les fournisseurs de données institutionnels — "
            "JPMaQS, RavenPack, Permutable — sur devis, pour les hedge funds. À gauche, "
            "des outils gratuits qui donnent un score brut. Personne ne propose un "
            "régime expliqué, avec une latence publiée et un historique vérifiable, "
            "pour les petits gérants européens. C'est notre espace, avec un marché "
            "adressable estimé autour de 22 millions d'euros par an."
        ),
    },
    {
        "titre": "Notre solution : un signal expliqué et une preuve publique",
        "kind": "solution",
        "img": "15b_track_record_crop.png",
        "orateur": "Titouan",
        "duree": 55,
        "script": (
            "Notre solution, en deux phrases : chaque soir, l'outil indique dans quel "
            "climat se trouvent les marchés — Expansion, Surchauffe, Ralentissement ou "
            "Stress — avec une probabilité calibrée et ses raisons. Il produit une note "
            "pour le comité des risques et publie un historique que personne ne peut "
            "retoucher. Voici la vraie page publique : depuis le 1er octobre, 14 jours "
            "publiés, chacun chaîné au précédent et horodaté dans la blockchain Bitcoin, "
            "sur quatre zones. Depuis le J1, nos choix ont évolué : trois dimensions au "
            "lieu de deux, un détecteur de stress refondu, un suivi en direct lancé un "
            "mois plus tôt que prévu. Ce qui reste le plus risqué : que ça tienne en "
            "réel, et qu'un gérant change vraiment sa décision grâce à la note."
        ),
    },
    {
        "titre": "Exigences : ce que nous ferons… et ce que nous ne ferons pas",
        "kind": "moscow",
        "orateur": "Amine",
        "duree": 60,
        "script": (
            "Voici notre MoSCoW, avec l'état au 21 octobre. Les Must sont presque tous "
            "faits : données datées sans information future, régimes, détecteur, "
            "probabilité calibrée, explication, note de comité, suivi public. Il en "
            "reste un, le plus important : les tests avec au moins trois gérants. En "
            "Should, nos chantiers de Phase 3 : un régime Ralentissement fiable, "
            "l'overlay de risque promis au J1, et la couche actualité. Nous assumons "
            "aussi un écart : des Could comme la carte mondiale ont été construits "
            "avant ces Should ; nous gelons maintenant les nouvelles fonctionnalités. "
            "Et ce que nous ne ferons pas : aucun signal d'achat ou de vente, ce serait "
            "du conseil en investissement ; pas de deep learning ; pas de temps réel."
        ),
    },
    {
        "titre": "Architecture de la solution",
        "kind": "image_full",
        "img": "08_architecture.png",
        "orateur": "Axel",
        "duree": 45,
        "script": (
            "L'architecture. Des sources gratuites : FRED et ALFRED, qui donnent chaque "
            "chiffre macro tel qu'il a été publié ce jour-là, et Tiingo pour les prix. "
            "Douze indicateurs résumés en trois scores : stress, croissance, inflation. "
            "Le Statistical Jump Model nomme les régimes ; un détecteur dédié repère le "
            "début du stress ; la probabilité est ensuite calibrée. Tout est validé en "
            "walk-forward, et chaque protocole est publié avant le calcul sur données "
            "réelles. Chaque soir à 22 h 30, un job GitHub Actions publie le résultat, "
            "la note, l'application et l'API."
        ),
    },
    {
        "titre": "Arbre de choix n°1 : le détecteur de stress",
        "kind": "image_full",
        "img": "10_arbre_detection.png",
        "orateur": "Axel",
        "duree": 55,
        "script": (
            "Notre choix le plus structurant, documenté par cet arbre. Notre première "
            "version ne détectait que 5 crises sur 11. Nous avons pré-enregistré un "
            "protocole avant de toucher aux données réelles, avec cinq candidats. "
            "Premier filtre, sur une période test de 1999 à 2009 jamais utilisée : pas "
            "plus de 1,5 fausse alerte par an. Tous passent. Deuxième filtre : latence "
            "médiane de 5 jours au plus. L'ancienne version et les deux régressions "
            "logistiques tombent, à 41 et 60 jours. Les deux boostings sont à égalité : "
            "la règle écrite à l'avance prend le premier. Résultat, en un seul passage "
            "sur les onze crises réelles : onze sur onze, latence médiane de moins 3 "
            "jours. Le compromis assumé : 1,26 fausse alerte par an au lieu de 0,17."
        ),
    },
    {
        "titre": "Arbre de choix n°2 : les sources de données",
        "kind": "image_full",
        "img": "11_arbre_donnees.png",
        "orateur": "Gabriel",
        "duree": 25,
        "script": (
            "Même démarche pour les données. Bloomberg est hors budget. Les spreads de "
            "crédit ICE et le S&P 500 sur FRED ne peuvent pas être republiés. Yahoo "
            "Finance est réservé à la recherche. Nous retenons FRED et ALFRED pour la "
            "macro, et Tiingo pour les ETF, avec la licence notée série par série. Les "
            "arbres sur le modèle des régimes et sur la publication sont en annexe."
        ),
    },
    {
        "titre": "Analyse de risques : 7 risques suivis, 3 majeurs",
        "kind": "risques",
        "img": "13_risques.png",
        "orateur": "Robin",
        "duree": 60,
        "script": (
            "Les risques, identifiés avec la méthode TELOS. Nous en suivons sept ; "
            "voici les trois majeurs. R1, externe, le plus critique : nous n'avons "
            "encore fait aucun test utilisateur. Les sessions sont planifiées dès le 9 "
            "novembre, avec un protocole asynchrone de 10 minutes en secours. R2, "
            "technique : en réel, les fausses alertes pourraient dépasser 1,5 par an. "
            "Nous ne retoucherons pas le modèle après coup ; des variantes sont "
            "publiées en direct à côté, et le plan B est écrit : revenir à l'ancienne "
            "version, plus lente mais plus sobre. R3, organisationnel : le code a "
            "été écrit en grande partie avec un assistant IA et par deux personnes. "
            "Chaque membre devient propriétaire d'un module et doit pouvoir le défendre."
        ),
    },
    {
        "titre": "Prochaines étapes et retours attendus",
        "kind": "fin",
        "img": "14_planning.png",
        "orateur": "Titouan",
        "duree": 30,
        "script": (
            "Pour la Phase 3 : gel des nouvelles fonctionnalités, tests utilisateurs du "
            "9 au 20 novembre, nouvelle version du Ralentissement avec un go/no-go le "
            "13, overlay de risque et couche actualité en parallèle. En résumé : un "
            "besoin confirmé, des choix tracés et pré-enregistrés, et un plan B pour "
            "chaque risque majeur. Nous attendons vos retours sur deux points : une "
            "fausse alerte par an est-elle acceptable pour un gérant, et notre "
            "protocole de test utilisateur est-il assez exigeant ? Merci, place à vos "
            "questions."
        ),
    },
]

ANNEXES = [
    {"titre": "Annexe — Latence par épisode réel (v1 contre v2)",
     "img": "16_latence_episodes.png",
     "quand": "Question sur la latence, sur « −3 jours » ou sur l'ancienne version."},
    {"titre": "Annexe — Arbre n°3 : modèle des régimes",
     "img": "12c_arbre_modele.png",
     "quand": "Question « pourquoi pas un HMM / du deep learning ? »."},
    {"titre": "Annexe — Arbre n°4 : publication et preuve",
     "img": "12b_arbre_diffusion.png",
     "quand": "Question sur l'horodatage, la blockchain ou l'hébergement."},
    {"titre": "Annexe — Arbre prévu en Phase 3 : actualité",
     "img": "12a_arbre_news.png",
     "quand": "Question « où est l'IA sur les news ? »."},
    {"titre": "Annexe — Taille du marché (TAM / SAM / SOM)",
     "img": "05_marche.png",
     "quand": "Question sur le marché ou le modèle économique."},
    {"titre": "Annexe — Prix acceptable et facteurs de confiance",
     "img": "04_sondage_prix_confiance.png",
     "quand": "Question sur le prix ou la disposition à payer."},
    {"titre": "Annexe — Tableau complet des risques", "kind": "risk_table",
     "quand": "Question sur un risque non présenté (R4 à R7)."},
    {"titre": "Annexe — Critères de succès : objectif et résultat", "kind": "kpi_table",
     "quand": "Question « comment savez-vous que ça marche ? »."},
    {"titre": "Annexe — Budget et besoins SI", "kind": "budget",
     "quand": "Question sur le budget ou le matériel."},
    {"titre": "Annexe — État du dépôt de code", "kind": "repo",
     "quand": "Question « où en est le code ? »."},
]

CRITERES = [
    ("Latence médiane de détection", "≤ 5 jours", "−3 j (backtest réel 2009-2026)"),
    ("Fausses alertes « stress »", "≤ 1,5 / an", "1,26 / an ; 4,9 % des jours calmes"),
    ("Épisodes réels détectés", "—", "11 / 11 (v1 : 5 / 11)"),
    ("Stabilité des régimes", "Régimes persistants", "5,6 changements / an"),
    ("Calibration (Brier, ECE)", "< score brut", "Brier 0,100 → 0,091 ; ECE 0,083 → 0,042"),
    ("Ralentissement vs référence CFNAI", "> hasard (0,5)", "0,492 : non atteint"),
    ("Overlay 60/40 : drawdown max", "< buy & hold", "Non évalué"),
    ("Gain de latence lié aux news", "Mesuré et publié", "Non commencé"),
    ("Tests utilisateurs", "≥ 3 gérants", "0 : prévu du 09 au 20/11"),
    ("Publication live", "Chaque jour ouvré", "14 jours depuis le 01/10, 13 ancrés"),
]

BUDGET = [
    ("Matériel", "Aucun (projet 100 % logiciel)", "0 €"),
    ("Données", "FRED/ALFRED, Tiingo (offre gratuite, usage recherche), BoE, OCDE, BIS, BCE", "0 €"),
    ("Publication", "GitHub Actions, OpenTimestamps", "0 €"),
    ("API modèle de langage", "Tuteur GAMA et couche actualité, plafond mensuel, cache", "≈ 40 €"),
    ("Nom de domaine (vitrine)", "Optionnel, Could have", "≈ 10 €"),
    ("Total estimé", "Demande via bon de commande (besoins SI)", "≈ 50 € / 300 €"),
]
