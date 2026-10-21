"""Génère les trois documents Word du dossier de soutenance."""

from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

import content as C
from build_pptx import MOSCOW_COURT
from slides import ANNEXES, BUDGET, CRITERES, SLIDES

ROOT = Path(__file__).resolve().parents[1]
IMG = ROOT / "img"
NAVY = RGBColor(0x1F, 0x3A, 0x5F)
ORANGE = RGBColor(0xE7, 0x6F, 0x51)
RED = RGBColor(0xC0, 0x39, 0x2B)
GREY = RGBColor(0x6B, 0x72, 0x80)


# ------------------------------------------------------------------ helpers
def new_doc(title, subtitle):
    d = Document()
    for s in d.sections:
        s.left_margin = s.right_margin = Cm(2)
        s.top_margin = s.bottom_margin = Cm(1.8)
    st = d.styles["Normal"]
    st.font.name = "Calibri"
    st.font.size = Pt(11)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), "Calibri")
    for name, size in [("Heading 1", 18), ("Heading 2", 14), ("Heading 3", 12)]:
        d.styles[name].font.color.rgb = NAVY
        d.styles[name].font.size = Pt(size)
        d.styles[name].font.name = "Calibri"
    p = d.add_paragraph()
    r = p.add_run(title)
    r.bold = True
    r.font.size = Pt(26)
    r.font.color.rgb = NAVY
    p = d.add_paragraph()
    r = p.add_run(subtitle)
    r.font.size = Pt(13)
    r.font.color.rgb = ORANGE
    d.add_paragraph(f"{C.PROJET} — {C.GROUPE} — Coach : {C.COACH}").runs[0].font.color.rgb = GREY
    return d


def shade(cell, hex_color):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tcPr.append(shd)


def para(d, txt, bold=False, italic=False, color=None, size=None, style=None):
    p = d.add_paragraph(style=style)
    r = p.add_run(txt)
    r.bold, r.italic = bold, italic
    if color:
        r.font.color.rgb = color
    if size:
        r.font.size = Pt(size)
    return p


def rich(d, parts, style=None):
    """parts = [(texte, gras)]"""
    p = d.add_paragraph(style=style)
    for t, b in parts:
        p.add_run(t).bold = b
    return p


def bullets(d, items, style="List Bullet"):
    for it in items:
        if isinstance(it, tuple):
            rich(d, [(it[0], True), (it[1], False)], style=style)
        else:
            d.add_paragraph(it, style=style)


def callout(d, title, body, fill="FEF3C7", color=ORANGE):
    t = d.add_table(rows=1, cols=1)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    c = t.cell(0, 0)
    shade(c, fill)
    p = c.paragraphs[0]
    r = p.add_run(title)
    r.bold = True
    r.font.color.rgb = color
    for line in body if isinstance(body, list) else [body]:
        c.add_paragraph(line)
    d.add_paragraph()


def table(d, header, rows, widths=None, size=9.5, header_fill="1F3A5F"):
    t = d.add_table(rows=1, cols=len(header))
    t.style = "Table Grid"
    for j, h in enumerate(header):
        c = t.rows[0].cells[j]
        c.text = ""
        r = c.paragraphs[0].add_run(h)
        r.bold = True
        r.font.size = Pt(size)
        r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        shade(c, header_fill)
    for i, row in enumerate(rows):
        cells = t.add_row().cells
        for j, v in enumerate(row):
            cells[j].text = ""
            r = cells[j].paragraphs[0].add_run(str(v))
            r.font.size = Pt(size)
            if i % 2 == 0:
                shade(cells[j], "F3F4F6")
    if widths:
        for row in t.rows:
            for j, w in enumerate(widths):
                row.cells[j].width = Cm(w)
    d.add_paragraph()
    return t


def image(d, name, width=17, caption=None):
    d.add_picture(str(IMG / name), width=Cm(width))
    d.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    if caption:
        p = para(d, caption, italic=True, color=GREY, size=9)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER


def fmt_s(s):
    return f"{s // 60} min {s % 60:02d} s" if s >= 60 else f"{s} s"


# ------------------------------------------------------------------ 1. guide
def guide():
    d = new_doc("Guide de la soutenance blanche",
                "Soutenance intermédiaire du Jalon 2 — tout ce qu'il faut savoir, dire et préparer")

    callout(d, "Comment lire ce dossier",
            ["Ce guide explique la soutenance de A à Z : ce que l'école attend, le déroulé "
             "minuté, le texte de chaque slide, les questions probables et leurs réponses, "
             "la grille d'auto-évaluation et la checklist de répétition.",
             "Il s'accompagne de 3 autres fichiers : le support PowerPoint (avec le texte "
             "dans les notes d'orateur), les chapitres J2 rédigés à intégrer au portfolio, "
             "et le dossier d'études terrain.",
             "Les résultats techniques (11/11 épisodes, −3 jours, 1,26 fausse alerte/an, "
             "Brier 0,091, track record) sont RÉELS : ils viennent du dépôt GitHub à jour "
             "(commit 8a58a17). Tout ce qui est marqué FICTIF (entretiens, sondage, marché, "
             "délais de réaction des gérants) est inventé pour l'exercice et doit être remplacé "
             "par vos vrais résultats. Ce qui est marqué [À VÉRIFIER] est plausible mais doit "
             "être confirmé par l'équipe."])

    d.add_heading("1. Ce que l'école attend de vous", 1)
    d.add_heading("Le format", 2)
    table(d, ["Étape", "Durée", "Ce qui se passe"], [
        ("Passage de votre groupe", "10 min", "Vous présentez ; le coach et deux autres équipes écoutent."),
        ("Retours oraux croisés", "10 min", "Chaque équipe donne 1 point fort et 1 point à améliorer ; le coach recadre."),
        ("Total de la session", "60 min", "3 équipes passent à la suite."),
        ("Après la session", "24 h", "Évaluation écrite des deux autres groupes sur la plateforme."),
    ], widths=[4.5, 2, 10.5])
    d.add_heading("Les 5 parties obligatoires, dans cet ordre", 2)
    bullets(d, [
        ("1. Contexte et enjeux", " — pourquoi ce sujet mérite qu'on s'y intéresse."),
        ("2. Problématique et besoin", " — pour qui, pourquoi, avec quelles preuves."),
        ("3. État de l'art", " — ce qui existe déjà et ce qui justifie votre approche."),
        ("4. Solution envisagée", " — vos grands choix et leur justification (MoSCoW, arbre de décision)."),
        ("5. Risques identifiés", " — ce qui pourrait faire dérailler le projet et votre plan de mitigation."),
    ], style="List Paragraph")
    para(d, "Vous n'avez pas à présenter de prototype ni de résultats de tests : ce n'est "
            "pas l'objet. En revanche, ces 5 parties sont exactement l'ouverture de votre "
            "soutenance finale : ce que vous rodez ici, vous le réutiliserez.", italic=True)
    d.add_heading("La note", 2)
    para(d, "La note intermédiaire ne peut que vous aider : si elle est inférieure à la "
            "finale, elle est ignorée ; si elle est égale ou supérieure, les deux sont "
            "moyennées. Exemple : 14/20 en finale et 16/20 en intermédiaire donnent 15/20.")
    d.add_heading("L'évaluation croisée", 2)
    bullets(d, ["Vous notez les deux autres groupes, critère par critère, avec une phrase de "
                "justification obligatoire (sinon la note ne compte pas).",
                "Le coach peut invalider une note incohérente avec ce qu'il a observé.",
                "Notez ce que vous avez vu, pas ce que vous espérez recevoir."])
    d.add_heading("Ce que les évaluateurs regardent en priorité (Jalon 2)", 2)
    bullets(d, [
        ("L'analyse de risques", " est bloquante : un tableau vide ou générique donne automatiquement "
         "« Validé sous réserve ». Il faut au moins un risque majeur avec une solution de secours concrète."),
        ("Les arbres de choix", " : un arbre par choix structurant, des filtres chiffrés ou binaires "
         "(jamais « trop cher » mais « > 300 €, hors budget »), une synthèse écrite."),
        ("Le MoSCoW", " : des fonctionnalités, pas des évidences techniques, et un paragraphe qui "
         "justifie chaque catégorie, surtout le Won't have."),
        ("La fonctionnalité la plus risquée", " : c'est sur elle que doit porter le prototype."),
        ("La solution en deux phrases", " compréhensible par quelqu'un qui ne connaît pas le sujet."),
    ])

    d.add_heading("2. Diagnostic de votre dossier au 21/10/2026", 1)
    d.add_heading("Ce qui est déjà solide", 2)
    bullets(d, [
        "Un cadrage J1 très complet : problème en une phrase, question directrice chiffrée, "
        "définition opérationnelle des 4 régimes, critères de succès mesurables.",
        "Un état de l'art riche et sourcé (Hamilton, Nystrup, Shu & Mulvey, López de Prado…), "
        "avec un benchmark commercial clair et un positionnement net.",
        "Une contrainte réglementaire bien identifiée (pas de conseil en investissement).",
        "Un MVP très avancé dans le dépôt GitHub : application Streamlit 7 écrans, API, 5 modèles, "
        "note de comité FR/EN, track record public quotidien horodaté dans Bitcoin depuis le 01/10.",
        "Des résultats réels déjà mesurés, avec des protocoles pré-enregistrés : détecteur v2 "
        "11/11 épisodes, latence médiane −3 jours, 1,26 fausse alerte/an ; Brier 0,100 → 0,091.",
        "Une honnêteté rare sur les échecs, publiés dans docs/ : zone euro échouée, Ralentissement "
        "au niveau du hasard, 9 améliorations testées et non adoptées. C'est un argument fort à l'oral.",
    ])
    d.add_heading("Ce qui manque ou pose problème pour le Jalon 2", 2)
    table(d, ["Élément", "État", "Ce qu'il faut faire"], [
        ("2.0 Mise à jour de la description", "Vide", "Décrire les évolutions réelles depuis J1 (proposé dans le fichier 02)."),
        ("2.1 MoSCoW", "Vide", "Tableau avec le statut de chaque ligne + un paragraphe par catégorie (proposé)."),
        ("2.2 Architecture et arbres", "Vide", "Schéma + 4 arbres + synthèses, construits à partir de docs/ (proposés)."),
        ("2.3 Analyse de risques", "Vide (bloquant)", "7 risques avec probabilité, impact, mitigation et déclencheur (proposés)."),
        ("Tests utilisateurs", "Aucun", "C'est le Must restant et l'hypothèse la plus risquée : planifier dès maintenant."),
        ("Entretiens prévus avant le 16/10", "Résultats non intégrés", "Remplacer les résultats FICTIFS du fichier 03 par les vrais."),
        ("Couche actualité IA (promise au J1)", "Non commencée", "L'assumer comme écart, la replanifier en challenger de Phase 3."),
        ("Overlay 60/40 (critère de succès J1)", "Non évalué", "Le replanifier ou le retirer explicitement des critères."),
        ("Périmètre", "Dérive (carte mondiale, pages Apprendre, 4 zones)", "Le J1 disait « pas de fonctionnalité hors MVP avant J3 » : l'assumer et annoncer un gel."),
        ("Appropriation du code", "67 commits sur 115 signés par un assistant IA", "Chaque membre doit pouvoir expliquer au moins un module (risque R3)."),
        ("« Henry » dans docs/", "Inconnu", "Les protocoles disent « exécuté par Henry » : vérifier qui c'est, le jury peut demander."),
        ("Annexe A — comptes-rendus J2", "À compiler", "Modèle de compte-rendu fourni dans le fichier 02."),
        ("Annexe B — capture Notion", "À faire le jour du dépôt", "Exporter le tableau des tâches à la date du dépôt."),
        ("Bon de commande besoins SI", "À faire", "Clé API de modèle de langage via le bon de commande."),
    ], widths=[4.5, 3.6, 8.9])
    callout(d, "Le piège de la soutenance intermédiaire avec un MVP aussi avancé",
            ["La consigne dit : « vous n'avez pas à présenter de prototype ni de résultats de tests ». "
             "Avec un produit aussi riche, la tentation est de faire une démo : ne le faites pas. "
             "Les résultats servent ici à justifier vos choix (arbres, MoSCoW), pas à faire le spectacle.",
             "Attendez-vous aussi à l'inverse : un coach qui vous demande pourquoi vous avez construit "
             "autant avant d'avoir testé avec un seul utilisateur. La réponse honnête (dérive, gel, tests "
             "planifiés) vaut mieux qu'une justification après coup."],
            fill="FDECEA", color=RED)
    callout(d, "Le piège principal de votre dossier : la densité",
            ["Votre portfolio J1 contient beaucoup de chiffres, de références et de jargon "
             "(TVTP, walk-forward, Deflated Sharpe, ARI…). En 10 minutes, devant deux équipes "
             "qui ne connaissent pas la finance, il faut trier : une idée par slide, un chiffre "
             "clé par idée, et le jargon seulement s'il est expliqué en une phrase.",
             "Le support proposé garde 14 slides principales et renvoie le reste en annexes, "
             "pour répondre aux questions."])

    d.add_heading("3. Déroulé minuté et répartition des orateurs", 1)
    rows = []
    t = 0
    for i, s in enumerate(SLIDES, 1):
        rows.append((i, s["titre"], s["orateur"], fmt_s(s["duree"]), fmt_s(t)))
        t += s["duree"]
    table(d, ["#", "Slide", "Orateur", "Durée", "Démarre à"], rows, widths=[0.8, 9.5, 2.2, 2.2, 2.3])
    para(d, f"Durée totale : {fmt_s(t)}. Objectif en répétition : 9 min 30 pour garder une "
            "marge. Si vous dépassez, coupez d'abord la slide 7 (positionnement) et la slide "
            "12 (arbre des données) — elles restent disponibles en annexe.", bold=True)
    para(d, "Temps de parole par membre :")
    per = {}
    for s in SLIDES:
        per[s["orateur"]] = per.get(s["orateur"], 0) + s["duree"]
    bullets(d, [f"{k} : {fmt_s(v)}" for k, v in per.items()])
    para(d, "Les rôles J2 indiqués (Robin Garant du besoin, Gabriel Investigateur, Amine "
            "Intégrateur, Titouan Scribe, Axel Facilitateur) sont déduits de la rotation "
            "prévue dans vos notes de positionnement. [À VÉRIFIER]", italic=True, color=GREY)
    d.add_heading("Règles de passage de parole", 2)
    bullets(d, [
        "Chaque orateur termine sa partie par une phrase de transition qui nomme le suivant "
        "(« Robin va vous montrer ce qu'en pensent les professionnels »).",
        "Pas plus de 5 changements d'orateur : regroupez les slides consécutives d'une même personne.",
        "Celui qui ne parle pas ne lit pas ses notes, il regarde le public.",
        "Un seul membre tient la télécommande ou le clavier (le Facilitateur), les autres "
        "disent « slide suivante » si besoin.",
    ])

    d.add_heading("4. Script complet, slide par slide", 1)
    para(d, "Le texte ci-dessous est aussi dans les notes d'orateur du PowerPoint. Ne "
            "l'apprenez pas par cœur mot à mot : apprenez la phrase clé et les chiffres, puis "
            "reformulez avec vos mots.", italic=True)
    t = 0
    for i, s in enumerate(SLIDES, 1):
        d.add_heading(f"Slide {i} — {s['titre']}", 2)
        para(d, f"Orateur : {s['orateur']} · {fmt_s(s['duree'])} · démarre à {fmt_s(t)}",
             color=ORANGE, bold=True)
        t += s["duree"]
        para(d, s["script"])
    d.add_heading("Si une phrase doit rester en tête du jury", 2)
    callout(d, "Le message en une phrase",
            "Nous ne vendons pas un algorithme — ils sont publics — mais la preuve : un régime "
            "expliqué, une latence mesurée et un historique live que personne ne peut "
            "retoucher, pour des gérants qui n'ont pas d'équipe quantitative.",
            fill="DBEAFE", color=NAVY)

    d.add_heading("5. Questions probables et réponses", 1)
    para(d, "Répartition conseillée : questions finance et besoin → Robin ou Amine ; "
            "méthodes et données → Axel ou Gabriel ; organisation et planning → Titouan. "
            "Le Facilitateur distribue la parole.", italic=True)
    for q, a in C.QR:
        rich(d, [("Q : ", True), (q, True)])
        rich(d, [("R : ", True), (a, False)])
    d.add_heading("La méthode pour répondre", 2)
    bullets(d, [
        ("Reformuler", " la question en une phrase (« Si je comprends bien, vous demandez… »)."),
        ("Répondre d'abord", " en une phrase, oui ou non, puis justifier."),
        ("Donner la preuve", " : un chiffre, un filtre de l'arbre, une référence."),
        ("Montrer l'annexe", " si elle existe (slides 16 à 23)."),
        ("Avouer", " ce que vous ne savez pas encore : « C'est une hypothèse que nous "
         "testerons au J3, voici comment. » C'est mieux noté qu'une réponse inventée."),
    ])
    d.add_heading("Annexes du support et quand les utiliser", 2)
    table(d, ["Annexe", "À montrer si…"], [(a["titre"].replace("Annexe — ", ""), a["quand"]) for a in ANNEXES],
          widths=[8, 9])

    d.add_heading("6. Grille d'auto-évaluation", 1)
    para(d, "La grille officielle est sur la plateforme ; celle-ci est déduite des consignes "
            "pour vous préparer. Notez-vous honnêtement après chaque répétition.", italic=True)
    table(d, ["Critère", "Insuffisant", "Attendu", "Excellent"], [
        ("Contexte et enjeux", "Sujet présenté sans enjeu chiffré", "Enjeu clair et chiffré",
         "Enjeu chiffré + lien direct avec la cible"),
        ("Problématique et besoin", "Besoin supposé, pas de preuve", "Persona + entretiens cités",
         "Hypothèses H1-H3 testées, résultats honnêtes y compris ce qui n'est pas validé"),
        ("État de l'art", "Liste de références", "Méthodes et concurrents comparés",
         "Leçons tirées qui expliquent les choix"),
        ("Solution : MoSCoW", "Évidences techniques, pas de Won't", "4 catégories justifiées",
         "Tri relié à l'hypothèse la plus risquée"),
        ("Solution : arbres de choix", "Choix affirmés sans alternatives", "1 arbre avec filtres",
         "Un arbre par choix structurant, filtres chiffrés, synthèse et compromis"),
        ("Risques", "Liste générique", "3-5 risques P/I + mitigation",
         "Risque majeur avec plan B concret et déclencheur"),
        ("Forme orale", "Lecture, dépassement de temps", "≤ 10 min, parole partagée",
         "Fluide, regard public, réponses précises aux questions"),
    ], widths=[3.6, 4.1, 4.3, 5])

    d.add_heading("7. Évaluer les deux autres équipes", 1)
    para(d, "Pendant leur passage, prenez des notes sur les 5 parties. Pour chaque critère : un "
            "niveau + une phrase factuelle. Modèles de phrases :")
    bullets(d, [
        "Point fort : « Le besoin est appuyé sur X entretiens avec des verbatims précis, ce qui "
        "rend la cible crédible. »",
        "Point fort : « L'arbre sur le choix du capteur utilise des critères chiffrés (coût, "
        "portée), on comprend pourquoi les alternatives sont écartées. »",
        "À améliorer : « Les risques présentés sont génériques (retard, maladie) ; il manque un "
        "risque technique propre au projet avec un plan B. »",
        "À améliorer : « Le MoSCoW contient des évidences (« l'application s'ouvre ») et pas de "
        "Won't have explicite. »",
        "À améliorer : « La solution n'est pas décrite en deux phrases simples ; on ne sait pas "
        "ce que fera le prototype en Phase 3. »",
    ])

    d.add_heading("8. Plan de répétition et checklist", 1)
    table(d, ["Quand", "Quoi", "Qui"], [
        ("J-7", "Remplacer les données FICTIVES par les vraies ; chaque membre relit le protocole "
                "docs/ de son module ; vérifier qui est « Henry »", "Tous"),
        ("J-6", "Relire le support : une idée par slide, un chiffre clé par idée", "Titouan"),
        ("J-5", "Répétition n°1 chronométrée, chacun avec ses notes", "Tous"),
        ("J-4", "Corriger ; répétition des questions (chacun pose 3 questions pièges aux autres)", "Tous"),
        ("J-3", "Répétition n°2 sans notes, devant un camarade extérieur au projet", "Tous"),
        ("J-2", "Répétition n°3 en conditions réelles (salle, vidéoprojecteur, télécommande)", "Tous"),
        ("J-1", "Export PDF du support + copie sur clé USB et en ligne ; dépôt du portfolio J2", "Titouan / Amine"),
        ("Jour J", "Arriver 15 min avant, tester l'affichage, eau, chronomètre visible", "Axel"),
    ], widths=[1.8, 12, 3.2])
    para(d, "Checklist du jour J :", bold=True)
    bullets(d, ["Support en .pptx ET en .pdf (si le PowerPoint de la salle déconne)",
                "Adaptateur HDMI / USB-C", "Chronomètre visible par l'orateur",
                "Arbres n°1 à n°4 imprimés ou en annexe", "Grille d'évaluation des autres équipes ouverte",
                "Une personne note tous les retours reçus (Scribe : Titouan)"], style="List Paragraph")

    d.add_heading("9. Erreurs fréquentes à éviter", 1)
    bullets(d, [
        "Lire ses slides ou ses notes : le jury décroche en 20 secondes.",
        "Présenter le projet de J1 sans dire ce qui a changé : les évaluateurs veulent voir la "
        "progression (slide 8).",
        "Défendre un chiffre inventé : si un chiffre est une estimation, dites-le.",
        "Dire « on fera attention » comme plan de mitigation : ce n'est pas un plan.",
        "Montrer du code ou un prototype : ce n'est pas l'objet de cette soutenance.",
        "Oublier le Won't have : c'est la preuve que vous savez prioriser.",
        "Répondre à plusieurs en même temps : un seul répond, les autres complètent si besoin.",
        "Dépasser les 10 minutes : vous serez coupés avant les risques, la partie la plus évaluée.",
    ])

    d.add_heading("10. À remplacer ou vérifier avant la vraie soutenance", 1)
    table(d, ["Élément", "Où", "Statut"], [
        ("Résultats des 13 entretiens (H1, H2, H3, testeurs, payeurs)", "Slides 4 et 14 ; fichier 03", "FICTIF"),
        ("Questionnaire en ligne (54 réponses)", "Slide 5, annexes ; fichier 03", "FICTIF"),
        ("Délais de réaction 9 / 12 / 19 jours", "Slide 2", "FICTIF"),
        ("TAM / SAM / SOM (22 M€, 0,4 M€)", "Slide 7, annexe ; fichier 03", "FICTIF (sauf TAM, source J1)"),
        ("Résultats de détection, calibration, holdout", "Slides 3, 11, annexes", "RÉEL (docs/ du dépôt)"),
        ("Track record (14 jours, Expansion ≈ 76 %)", "Slide 8", "RÉEL — mettre à jour la capture la veille"),
        ("Drawdowns des 11 épisodes", "Slide 2, annexe", "RÉEL (calculés par le dépôt)"),
        ("Coût Bloomberg ≈ 2 000 €/mois", "Arbre n°2", "[À VÉRIFIER] ordre de grandeur"),
        ("6 volontaires pour les tests utilisateurs", "Risque R1", "FICTIF"),
        ("Rôles J2 et dates du planning", "Slides, Gantt", "[À VÉRIFIER]"),
        ("Votes et contenus des comptes-rendus", "Fichier 02, annexe A", "FICTIF, à remplacer par vos vrais CR"),
    ], widths=[7.5, 5, 4.5])

    d.add_heading("11. Lexique pour expliquer simplement", 1)
    para(d, "Les deux autres équipes ne sont pas financières. Gardez ces définitions en tête :", italic=True)
    table(d, ["Terme", "Explication en une phrase"], [
        ("Régime de marché", "Le « climat » des marchés sur plusieurs semaines : expansion, surchauffe, ralentissement ou stress."),
        ("Latence de détection", "Le nombre de jours entre le début réel d'une crise et le moment où notre outil la signale."),
        ("Fausse alerte", "Un signal « stress » qui n'est suivi d'aucune crise."),
        ("Drawdown", "La baisse maximale entre un sommet et le creux qui suit."),
        ("Look-ahead (fuite du futur)", "Utiliser sans le vouloir une information qui n'était pas connue à la date du signal."),
        ("Point-in-time", "La donnée telle qu'elle était publiée ce jour-là, avant ses révisions."),
        ("Walk-forward", "On entraîne sur le passé, on teste sur la période suivante, et on avance : comme en conditions réelles."),
        ("Statistical Jump Model", "Un modèle qui regroupe les jours en régimes et pénalise chaque changement, pour éviter qu'il change d'avis tous les jours."),
        ("HMM", "Modèle de Markov caché : la référence historique, mais qui change de régime trop souvent."),
        ("TVTP", "Variante où la probabilité de changer de régime dépend d'une variable extérieure, ici l'actualité."),
        ("FinBERT", "Un modèle de langage spécialisé en finance qui note le ton (positif / négatif) d'un titre de presse."),
        ("Score de Brier", "Mesure si les probabilités annoncées sont justes : 70 % doit se réaliser 70 % du temps."),
        ("CGP / CIF", "Conseiller en gestion de patrimoine / conseiller en investissements financiers."),
        ("Family office", "Structure qui gère le patrimoine d'une ou de quelques familles fortunées."),
    ], widths=[4.2, 12.8])
    d.save(ROOT / "01_Guide_soutenance_blanche.docx")


# ------------------------------------------------------------------ 2. chapitres J2
def chapitres():
    d = new_doc("Chapitres du Jalon 2 — proposition rédigée",
                "Texte prêt à adapter et à intégrer dans le portfolio (2.0, 2.1, 2.2, 2.3, annexes A et B)")
    callout(d, "Avant de copier-coller",
            ["Ce texte reprend votre portfolio J1 et le prolonge. Les chiffres marqués FICTIF ou "
             "[À VÉRIFIER] doivent être remplacés. Réécrivez avec vos mots : le coach connaît votre "
             "style d'écriture du J1."])

    d.add_heading("2.0 — Mise à jour de la description du projet", 1)
    para(d, "Version J2 — octobre 2026.", italic=True)
    para(d, "Pas de pivot de cible : nous visons toujours les petites sociétés de gestion et les "
            "family offices européens, avec les CGP premium en cible secondaire. Les entretiens "
            "(13 sur 15 prévus, FICTIF) ont confirmé la douleur « décider trop tard et justifier » "
            "et placé la note de comité en sortie principale. Depuis le J1, la solution a évolué "
            "sur cinq points :")
    bullets(d, C.EVOLUTION_J1_J2)
    para(d, "En backtest, la caractéristique la plus risquée du J1 (tenir à la fois une latence "
            "≤ 5 jours et ≤ 1,5 fausse alerte par an) est atteinte : 11 épisodes réels sur 11 "
            "détectés, latence médiane −3 jours, 1,26 fausse alerte par an. Le risque se déplace "
            "donc vers le réel (le track record live) et vers l'usage (aucun test utilisateur "
            "n'a encore eu lieu).")
    para(d, "Solution en deux phrases :", bold=True)
    para(d, C.PITCH_2_PHRASES, italic=True)

    d.add_heading("2.1 — Exigences du projet (MoSCoW)", 1)
    rows = []
    for cat, items in C.MOSCOW.items():
        for f, j, st in items:
            rows.append((cat, f, j, st))
    table(d, ["Catégorie", "Fonctionnalité / caractéristique", "Justification", "Statut au 21/10"],
          rows, widths=[2.3, 6.4, 5.6, 2.7], size=9)
    d.add_heading("Pourquoi ces Must", 3)
    para(d, "Nous avons appliqué une règle simple : est un Must ce qui sert directement à tester "
            "l'hypothèse la plus risquée ou à prouver la valeur pour le gérant. Les données "
            "point-in-time et le protocole pré-enregistré sont des Must car sans eux, la latence "
            "mesurée n'a aucune valeur : un backtest contaminé par des informations futures, ou "
            "réglé après avoir vu les résultats, serait trop optimiste. La note de comité et "
            "l'explication sont des Must parce qu'un score brut ne se vend pas (10 entretiens "
            "sur 13, FICTIF). Le track record est un Must parce que chaque jour non publié est "
            "perdu définitivement : nous l'avons lancé le 01/10, avec un mois d'avance. Le seul "
            "Must restant, les tests utilisateurs, est aussi le plus important pour le J3.")
    d.add_heading("Pourquoi ces Should", 3)
    para(d, "Les Should augmentent la valeur sans conditionner le prototype. Le régime "
            "Ralentissement est affiché, mais sa qualité est aujourd'hui au niveau du hasard : "
            "nous préférons le dire que le cacher. L'overlay 60/40 traduit le signal en drawdown "
            "évité ; c'était un critère du J1, il n'est pas encore évalué. La couche actualité "
            "reste notre question scientifique, mais le produit fonctionne sans elle : elle sera "
            "publiée en challenger, testée uniquement en live.")
    d.add_heading("Pourquoi ces Could, et l'écart que nous assumons", 3)
    para(d, "Les zones hors États-Unis, les pages pédagogiques et la carte mondiale sont des "
            "vitrines utiles mais sans lien direct avec la décision du gérant. Nous reconnaissons "
            "une dérive : plusieurs Could ont été construits avant des Should, alors que notre "
            "J1 annonçait « aucune fonctionnalité hors MVP avant le J3 ». Conséquence : gel des "
            "nouvelles fonctionnalités jusqu'aux tests utilisateurs (risque R5).")
    d.add_heading("Ce que nous ne ferons pas, et pourquoi", 3)
    para(d, "Nous excluons explicitement tout signal d'achat ou de vente personnalisé : ce serait "
            "du conseil en investissement au sens de MiFID II et de la position AMF DOC-2008-23, "
            "qui exige un statut que nous n'avons pas. Nous excluons aussi les méthodes "
            "exploratoires (VAE, SOM, TDA, HDP-HMM) : avec moins de dix crises dans l'échantillon, "
            "leur nombre de paramètres les rend impossibles à valider honnêtement ; elles restent "
            "au mémoire. Le temps réel est inutile pour un comité qui décide à la semaine. Enfin, "
            "comptes, paiement et application mobile n'aident pas à prouver la valeur au J3.")
    para(d, "Cohérence avec le temps disponible : 7 Must sur 8 sont faits ; les 6 semaines "
            "restantes avant le J3 vont d'abord aux tests utilisateurs, puis au Ralentissement et "
            "à l'overlay 60/40. La couche actualité ne démarre que si les tests sont planifiés.",
            italic=True)

    d.add_heading("2.2 — Architecture et choix techniques", 1)
    d.add_heading("Description de la solution", 2)
    para(d, "Chaque soir de semaine à 22 h 30 (après la clôture américaine), une tâche "
            "GitHub Actions collecte les données du jour (FRED/ALFRED en première publication, "
            "Tiingo pour les ETF), calcule 12 indicateurs regroupés en trois scores (stress, "
            "croissance, inflation), applique le jump model et le détecteur de début d'épisode, "
            "calibre la probabilité de stress, puis publie le régime, la probabilité et les "
            "facteurs explicatifs dans le track record public : chaque jour est un fichier JSON "
            "chaîné par SHA-256 et horodaté dans Bitcoin (OpenTimestamps). Les mêmes briques, "
            "rejouées en walk-forward sur 1999-2026, produisent les mesures du backtest. "
            "Les sorties sont la note de comité (PDF, HTML, Markdown, FR/EN), une application "
            "Streamlit de 7 écrans et une API REST.")
    image(d, "08_architecture.png", 17, "Figure 1 — Architecture de la solution")
    d.add_heading("Outils et technologies", 2)
    table(d, ["Brique", "Choix", "Pourquoi"], [
        ("Langage", "Python 3.11", "Toutes les bibliothèques clés existent ; pratiqué par les 5 membres."),
        ("Données", "FRED / ALFRED, Tiingo, pandas, Parquet", "Gratuit, première publication datée, licence compatible avec la publication."),
        ("Modèles", "Statistical Jump Model, k-means, gradient boosting", "Régimes persistants ; challengers simples et standards."),
        ("Calibration", "Platt (régression logistique)", "Peu de paramètres pour une dizaine de crises."),
        ("Sorties", "Streamlit, FastAPI, note PDF", "Aucun profil front-end dans l'équipe."),
        ("Preuve", "SHA-256 chaîné + OpenTimestamps", "Horodatage vérifiable par n'importe qui, gratuit."),
        ("Orchestration", "GitHub Actions (publication + contrôle de santé)", "Gratuit, et l'historique Git sert aussi de preuve."),
        ("Qualité", "pytest (29 fichiers de tests), ruff", "Chaque règle de validation est testée."),
    ], widths=[3.5, 5.5, 8])
    d.add_heading("Arbres de choix d'architecture", 2)
    para(d, "Un arbre par choix structurant. Chaque filtre est une question mesurable ou binaire "
            "issue de nos contraintes J1 (budget 300 €, licences, une dizaine de crises seulement, "
            "compétences, absence de fuite du futur). Les chiffres viennent des protocoles "
            "pré-enregistrés du dossier docs/ du dépôt.")
    for i, (key, img) in enumerate([("detection", "10_arbre_detection.png"),
                                     ("donnees", "11_arbre_donnees.png"),
                                     ("modele", "12c_arbre_modele.png"),
                                     ("diffusion", "12b_arbre_diffusion.png"),
                                     ("news", "12a_arbre_news.png")], 2):
        a = C.ARBRES[key]
        d.add_heading(a["titre"], 3)
        image(d, img, 17, f"Figure {i} — {a['titre']}")
        rich(d, [("Synthèse : ", True), (a["synthese"], False)])

    d.add_heading("2.3 — Analyse de risques", 1)
    para(d, "Nous avons balayé les cinq dimensions de la méthode TELOS (technique, économique, "
            "légal, organisationnel, planning). Le budget (dimension économique) n'est pas un "
            "risque majeur : notre besoin est estimé à environ 50 € sur 300 €. Les risques "
            "retenus sont propres à notre projet.")
    table(d, ["ID", "Catégorie", "Risque", "Probabilité", "Impact", "Plan de mitigation", "Déclencheur"],
          [r for r in C.RISQUES], widths=[0.9, 2, 3.2, 1.7, 1.4, 5.3, 2.5], size=8.5)
    image(d, "13_risques.png", 10, "Figure 7 — Matrice probabilité / impact")
    d.add_heading("Risques majeurs et solutions de secours", 3)
    para(d, "Notre risque majeur est R1 : ne pas réussir à tester l'outil avec au moins trois "
            "gérants avant le J3. C'est le dernier Must ouvert et la seule façon de vérifier "
            "qu'une note de comité change une décision. Les sessions sont planifiées dès le "
            "09/11 ; si moins de trois sont confirmées au 06/11, nous basculons sur un protocole "
            "asynchrone (vidéo de 5 minutes et formulaire de 10 minutes) ouvert aussi aux CGP et "
            "aux alumni de l'ECE en gestion d'actifs.")
    para(d, "Le deuxième risque est R2 : nos 1,26 fausse alerte par an sont mesurées sur des "
            "épisodes que nous connaissions. En réel, elles peuvent être plus nombreuses. La "
            "règle étant pré-enregistrée, nous ne la retoucherons pas après coup ; si le track "
            "record live affiche deux fausses alertes, nous basculons sur le plan B déjà écrit : "
            "le détecteur v1, plus lent (11 jours de latence médiane) mais avec 0,17 fausse "
            "alerte par an.")
    para(d, "Le troisième est R3 : une grande partie du code a été écrite avec un assistant IA "
            "et par deux contributeurs. Chaque membre devient propriétaire d'un module, le "
            "présente aux autres en 15 minutes, et nous répétons les questions techniques avant "
            "chaque soutenance.")

    d.add_heading("Besoins matériels et SI", 1)
    para(d, "Le projet ne nécessite aucun matériel. Les besoins SI sont faibles et passeront par "
            "le bon de commande de la plateforme (rubrique Commandes, justification dans le "
            "commentaire général).")
    table(d, ["Poste", "Détail", "Coût"], BUDGET, widths=[5, 8.5, 3.5])
    para(d, "Justification de la clé API de modèle de langage : elle sert au tuteur GAMA (Could) "
            "et, si elle démarre, à la couche actualité (Should). Nous avons écarté un abonnement "
            "fixe car l'usage est ponctuel ; un plafond de dépense est configuré et les réponses "
            "sont mises en cache. Point à vérifier : l'offre gratuite Tiingo est limitée à un "
            "usage non commercial [À VÉRIFIER avant toute commercialisation].", italic=True)

    d.add_heading("Annexe A — Comptes-rendus de réunion (lot J2) — MODÈLES FICTIFS", 1)
    crs = [
        ("30/09/2026 — Réunion d'équipe (1 h, hybride)", "Les 5 membres",
         ["Retour sur le dépôt J1.", "Répartition des 15 entretiens : 3 par membre."],
         ["Guide d'entretien commun validé.",
          "Lancement du track record public le 01/10 (au lieu du 30/10).",
          "Note de comité réelle montrée en entretien."],
         [("Robin", "finaliser le guide d'entretien", "02/10"),
          ("Gabriel", "pré-enregistrer le détecteur v2", "01/10"),
          ("Tous", "3 entretiens chacun", "16/10")]),
        ("07/10/2026 — Point coach (30 min)", "Les 5 membres + F. Pandolfi",
         ["Avancement des entretiens (6 réalisés).", "Résultats du détecteur v2 (11/11)."],
         ["Le coach demande d'identifier ce qui reste le plus risqué maintenant que le backtest passe.",
          "Faire un arbre par choix structurant, pas un arbre global.",
          "Point de vigilance du coach : fonctionnalités hors MVP construites avant les tests."],
         [("Gabriel", "arbres détection et données", "14/10"),
          ("Amine", "protocole de test utilisateur", "14/10"),
          ("Robin", "première liste de risques TELOS", "14/10")]),
        ("14/10/2026 — Réunion d'équipe (1 h 30)", "Les 5 membres",
         ["Synthèse de 11 entretiens.", "Atelier MoSCoW avec statut.", "Revue des arbres n°1 et n°2."],
         ["Gel des nouvelles fonctionnalités jusqu'aux tests utilisateurs (vote 5-0).",
          "Couche actualité en challenger de Phase 3 (vote 4-1, Axel contre : souhaitait la démarrer tout de suite).",
          "Un module « propriétaire » par membre pour que chacun puisse défendre le code."],
         [("Amine", "rédaction 2.1", "21/10"), ("Axel", "rédaction 2.2", "21/10"),
          ("Robin", "rédaction 2.3", "21/10"), ("Titouan", "support de soutenance", "24/10"),
          ("Gabriel", "intégration des entretiens", "21/10")]),
    ]
    for titre, part, ordre, decisions, actions in crs:
        d.add_heading(titre, 3)
        rich(d, [("Participants : ", True), (part, False)])
        rich(d, [("Ordre du jour : ", True), (" ; ".join(ordre), False)])
        para(d, "Décisions :", bold=True)
        bullets(d, decisions)
        table(d, ["Qui", "Fait quoi", "Pour quand"], actions, widths=[3, 10, 4])

    d.add_heading("Annexe B — Preuves de gestion de projet", 1)
    para(d, "À faire le jour du dépôt : exporter ou capturer le tableau Notion. Structure "
            "conseillée pour que la capture soit lisible :")
    table(d, ["Colonne Notion", "Contenu"], [
        ("Tâche", "Formulée comme un livrable (« Arbre n°2 rédigé »), pas une activité."),
        ("Responsable + binôme", "Deux noms pour chaque tâche technique (risque R3)."),
        ("Statut", "À faire / En cours / En revue / Terminé."),
        ("Échéance", "Date ; en rouge si dépassée."),
        ("Lien MoSCoW", "Must / Should / Could : montre que vous travaillez d'abord les Must."),
        ("Jalon", "J2 / J3."),
    ], widths=[4.5, 12.5])
    d.save(ROOT / "02_Chapitres_J2_a_integrer.docx")


# ------------------------------------------------------------------ 3. études fictives
def etudes():
    d = new_doc("Études terrain et étude de marché",
                "Entretiens, questionnaire en ligne et dimensionnement du marché")
    callout(d, "⚠ DONNÉES FICTIVES",
            ["Toutes les données de ce document (personnes interrogées, réponses, pourcentages, "
             "tailles de marché hors TAM) sont inventées pour préparer la soutenance blanche. "
             "Elles sont cohérentes avec votre portfolio J1, mais ne doivent en aucun cas être "
             "présentées comme réelles. Utilisez ce document comme modèle : mêmes questions, "
             "mêmes tableaux, avec vos vraies réponses."], fill="FDECEA", color=RED)

    d.add_heading("1. Entretiens qualitatifs", 1)
    d.add_heading("Protocole", 2)
    table(d, ["Élément", "Détail"], [
        ("Objectif", "Tester H1 (douleur « décider trop tard / justifier »), H2 (rapport expliqué > score brut), H3 (prêts à payer 3 000-15 000 €/an)."),
        ("Cible", "Gérants de SGP de 5 à 50 personnes, family offices, CGP / CIF premium, fonctions risque et conformité."),
        ("Recrutement", "LinkedIn, AFG, associations de CIF, réseau de stages de l'équipe."),
        ("Format", "20 minutes, visio ou téléphone, vraie note de comité (sortie du MVP) montrée à la minute 12."),
        ("Période", "30/09 → 16/10/2026 ; 13 entretiens réalisés sur 15 prévus."),
        ("Règle", "Ne jamais présenter la solution avant d'avoir fait parler de la douleur (questions 1 à 6)."),
    ], widths=[3.5, 13.5])
    d.add_heading("Guide d'entretien (20 minutes)", 2)
    qs = [
        ("Contexte (3 min)", ["Pouvez-vous décrire votre rôle et la taille de vos encours ?",
                              "Comment se déroule votre comité d'allocation (fréquence, participants) ?"]),
        ("Douleur — H1 (6 min)", ["Racontez-moi la dernière fois que vous avez réduit le risque en urgence. Qu'est-ce qui vous a fait décider ?",
                                  "Avec le recul, combien de jours après le début de la baisse avez-vous agi ?",
                                  "Comment avez-vous justifié cette décision auprès du comité ou des clients ?",
                                  "Quels indicateurs suivez-vous, et combien de temps y passez-vous par semaine ?"]),
        ("Format — H2 (4 min)", ["Si vous receviez un seul document par semaine sur le climat de marché, que devrait-il contenir ?",
                                 "Un score de 0 à 100 vous suffirait-il ? Pourquoi ?"]),
        ("Note de comité (4 min)", ["[Montrer la note] Qu'est-ce que vous comprenez en 10 secondes ?",
                              "Qu'est-ce qui vous manque ? Qu'est-ce qui est inutile ?",
                              "À partir de combien de fausses alertes par an arrêteriez-vous de le suivre ?"]),
        ("Prix — H3 (3 min)", ["Combien dépensez-vous aujourd'hui en données et recherche ?",
                               "À quel prix ce service serait-il trop cher ? Bon marché au point d'être suspect ? (Van Westendorp)",
                               "Seriez-vous d'accord pour tester le prototype en novembre ?"]),
    ]
    for t, l in qs:
        para(d, t, bold=True, color=NAVY)
        bullets(d, l, style="List Number")
    d.add_heading("Synthèse des 13 entretiens", 2)
    lab = {"V": "Validée", "P": "Partielle", "X": "Invalidée"}
    table(d, ["#", "Profil", "Structure", "Encours", "H1", "H2", "H3", "Testeur", "Payeur"],
          [(e[0], e[1], e[2], e[3], lab[e[4]], lab[e[5]], lab[e[6]], "Oui" if e[7] else "—",
            "Oui" if e[8] else "—") for e in C.ENTRETIENS],
          widths=[1, 3.6, 2.8, 1.7, 1.6, 1.6, 1.6, 1.5, 1.5], size=8.5)
    image(d, "02_entretiens.png", 15, "Figure 1 — Validation des hypothèses (FICTIF)")
    d.add_heading("Verbatims marquants", 2)
    for e in C.ENTRETIENS:
        rich(d, [(f"{e[0]} — {e[1]}, {e[2]} : ", True), (f"« {e[9]} »", False)])
    d.add_heading("Enseignements et décisions", 2)
    table(d, ["Enseignement", "Décision"], [
        ("H1 validée par 9/13, partiellement par 3/13 : la douleur existe, surtout pour justifier a posteriori.", "Le « ce qui a changé depuis la semaine dernière » devient un Must."),
        ("H2 validée par 10/13 : personne ne veut « un score de plus ».", "Rapport de comité PDF en Must, tableau de bord en Should."),
        ("H3 fragile (4/13) : budgets data déjà pris par Bloomberg ; on veut voir un historique live avant de payer.", "Track record public en ligne depuis le 01/10 ; prix à retester au J3 pendant les tests utilisateurs."),
        ("Seuil de tolérance aux fausses alertes : 1 à 2 par an.", "Seuil de 1,5 maintenu ; seuil minimal acceptable à 2."),
        ("Conformité (E13) : vigilance sur la frontière avec le conseil.", "Avertissement sur chaque sortie, formulations relues (risque R7)."),
        ("E10 : l'inflation de 2022 n'est pas un épisode de volatilité.", "Conforte les deux axes (stress et croissance / inflation)."),
    ], widths=[9, 8])

    d.add_heading("2. Questionnaire en ligne", 1)
    d.add_heading("Protocole", 2)
    para(d, f"Questionnaire Google Forms de 12 questions (5 minutes), diffusé du 05/10 au 18/10/2026 "
            f"sur LinkedIn et dans deux groupes de CGP. {C.SONDAGE_N} réponses exploitables.")
    table(d, ["Segment", "Nombre de réponses"], C.SONDAGE_SEGMENTS + [("Total", C.SONDAGE_N)], widths=[8, 5])
    d.add_heading("Questions", 2)
    bullets(d, [
        "Q1. Quel est votre métier ? (gérant SGP / family office / CGP-CIF / risque-conformité / autre)",
        "Q2. Encours gérés par votre structure ? (< 100 M€ / 100-500 M€ / 500 M€-2 Md€ / > 2 Md€)",
        "Q3. Avez-vous une équipe quantitative en interne ? (oui / non)",
        "Q4. Fréquence de votre comité d'allocation ? (hebdo / mensuel / trimestriel / pas de comité)",
        "Q5. Importance de ces difficultés (échelle 1 à 5) : consolider les signaux ; justifier une décision ; réagir tôt en stress ; rédiger le commentaire client ; accès aux modèles quant ; coût des terminaux",
        "Q6. Lors des baisses de 2020, 2022, avril 2025 : combien de jours avant de réduire le risque ?",
        "Q7. Format préféré (1er choix) : rapport PDF / alerte e-mail / tableau de bord / commentaire client / API",
        "Q8. Qu'est-ce qui vous donnerait confiance dans un signal ? (plusieurs choix)",
        "Q9. Combien de fausses alertes par an seriez-vous prêt à tolérer ?",
        "Q10. Prix annuel (gérants) ou mensuel (CGP) jugé acceptable ?",
        "Q11. Accepteriez-vous de tester un prototype en novembre ? (oui / non)",
        "Q12. Adresse e-mail (facultatif)",
    ], style="List Paragraph")
    d.add_heading("Résultats", 2)
    image(d, "03_sondage_besoins.png", 17, "Figure 2 — Douleurs et format préféré (FICTIF)")
    image(d, "04_sondage_prix_confiance.png", 17, "Figure 3 — Prix acceptable et facteurs de confiance (FICTIF)")
    bullets(d, [
        "74 % des répondants citent un historique live publié comme premier facteur de confiance, "
        "contre 31 % pour la performance en backtest : la preuve live est un vrai différenciant.",
        "Tolérance médiane aux fausses alertes : 2 par an (Q9).",
        "41 % des répondants (22) acceptent de tester le prototype (Q11).",
        "Prix médian : environ 4 500 €/an pour les gérants, 55 €/mois pour les CGP — dans le bas de nos hypothèses J1.",
    ])

    d.add_heading("3. Étude de marché", 1)
    d.add_heading("Dimensionnement (TAM / SAM / SOM)", 2)
    image(d, "05_marche.png", 16, "Figure 4 — Taille du marché adressable")
    table(d, ["Niveau", "Périmètre", "Valeur", "Source / hypothèse"], C.TAM_SAM_SOM, widths=[1.5, 8, 2.8, 4.7])
    para(d, "Hypothèses de calcul (FICTIF, à sourcer) :", bold=True)
    bullets(d, [
        "≈ 3 500 sociétés de gestion de 5 à 50 personnes et family offices en Europe de l'Ouest "
        "(France, Luxembourg, Suisse, Belgique, Allemagne, Italie, Espagne). Sources à consulter : "
        "AMF (nombre de SGP agréées), EFAMA, annuaires de family offices.",
        "Panier moyen de 6 000 €/an : médiane du questionnaire (4 500 €) + option Europe.",
        "≈ 1 150 CGP premium en France : 15 % des 7 712 CIF (source J1), à 700 €/an (≈ 59 €/mois).",
        "SOM à 3 ans : 50 gérants (1,4 % du SAM) et 150 CGP, soit ≈ 0,4 M€/an.",
    ])
    d.add_heading("Concurrence et positionnement", 2)
    image(d, "06_positionnement.png", 15, "Figure 5 — Carte de positionnement (qualitative)")
    d.add_heading("Proposition de grille tarifaire à tester au J3", 2)
    table(d, ["Offre", "Cible", "Contenu", "Prix testé"], [
        ("Vitrine", "Particuliers, prospects", "Régime en différé d'une semaine", "Gratuit"),
        ("Conseiller", "CGP / CIF", "Régime quotidien + commentaire client", "49-69 €/mois"),
        ("Gérant", "SGP, family offices", "Rapport de comité + alertes + historique", "300-500 €/mois"),
        ("Gérant Europe", "SGP européennes", "Offre Gérant + version Europe", "600-800 €/mois"),
    ], widths=[2.8, 3.8, 6.4, 4])

    d.add_heading("4. Limites méthodologiques", 1)
    bullets(d, [
        "Échantillon de convenance (réseau, LinkedIn) : biais vers les profils intéressés par la data.",
        "13 entretiens : suffisant pour repérer une douleur, pas pour estimer un prix.",
        "Déclaratif : « prêt à payer » ne veut pas dire « paiera ». La seule preuve forte serait une lettre d'intention.",
        "Les délais de réaction déclarés (Q6) sont reconstruits de mémoire.",
        "Le SAM repose sur des hypothèses de nombre de structures à confirmer par des sources officielles.",
    ])
    para(d, "Dire ces limites à l'oral est un point fort, pas une faiblesse.", bold=True, color=NAVY)
    d.save(ROOT / "03_Etudes_terrain_et_marche_FICTIVES.docx")


if __name__ == "__main__":
    guide()
    chapitres()
    etudes()
    print("docx ok")
