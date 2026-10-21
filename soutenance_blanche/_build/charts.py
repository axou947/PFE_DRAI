"""Génère toutes les images (PNG) du support et des documents."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch, Polygon  # noqa: E402

import content as C  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "img"
OUT.mkdir(exist_ok=True)

NAVY = "#1F3A5F"
TEAL = "#2A9D8F"
ORANGE = "#E76F51"
GOLD = "#E9C46A"
RED = "#C0392B"
GREEN = "#2E8B57"
GREY = "#6B7280"
LIGHT = "#F3F4F6"
REGIMES = {"Expansion": "#2E8B57", "Surchauffe": "#E76F51",
           "Ralentissement": "#E9C46A", "Stress / Crise": "#C0392B"}

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 11,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.titleweight": "bold",
    "axes.titlesize": 13,
})


def save(fig, name):
    fig.savefig(OUT / name, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def fictif(ax, x=0.99, y=0.01):
    ax.text(x, y, "DONNÉES FICTIVES — à remplacer", transform=ax.transAxes,
            ha="right", va="bottom", fontsize=8, color=RED, style="italic")


def box(ax, x, y, w, h, text, fc, ec=None, tc="white", fs=10, bold=False, r=0.02):
    ax.add_patch(FancyBboxPatch((x - w / 2, y - h / 2), w, h,
                                boxstyle=f"round,pad=0.005,rounding_size={r}",
                                fc=fc, ec=ec or fc, lw=1.5))
    ax.text(x, y, text, ha="center", va="center", color=tc, fontsize=fs,
            fontweight="bold" if bold else "normal", wrap=True)


def arrow(ax, x1, y1, x2, y2, color=GREY, lw=1.5, label=None):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="-|>", color=color, lw=lw))
    if label:
        ax.text((x1 + x2) / 2, (y1 + y2) / 2, label, fontsize=8, color=color,
                ha="center", va="center", backgroundcolor="white")


# ------------------------------------------------------------------ contexte
def contexte():
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(13, 4.8),
                                 gridspec_kw={"width_ratios": [1.6, 1]})
    ep = [e[0] for e in C.EPISODES_REELS]
    dd = [e[1] for e in C.EPISODES_REELS]
    a1.bar(ep, dd, color=[RED if d < -18 else ORANGE for d in dd])
    for i, d in enumerate(dd):
        a1.text(i, d - 1.5, f"{d:.0f} %", ha="center", fontsize=9, fontweight="bold")
    a1.set_ylim(-38, 0)
    a1.tick_params(axis="x", rotation=45)
    a1.set_title("11 épisodes de stress réels depuis 2009 : baisse maximale (SPY)")
    a1.set_ylabel("Drawdown max (%)")
    a1.text(0.99, 0.01, "Source : docs/DETECTION_V2.md (règle d'épisode gelée)",
            transform=a1.transAxes, ha="right", fontsize=8, color=GREY, style="italic")

    ep2 = ["2020", "2022", "2025"]
    lag = [12, 19, 9]
    a2.barh(ep2, lag, color=NAVY)
    a2.axvline(5, color=TEAL, ls="--", lw=2)
    a2.set_ylim(-0.6, 3.0)
    a2.text(5.3, 2.7, "Objectif ≤ 5 j", color=TEAL, fontweight="bold")
    for i, v in enumerate(lag):
        a2.text(v + 0.3, i, f"{v} j", va="center")
    a2.set_xlim(0, 24)
    a2.set_title("Délai médian avant réduction du risque\n(jours de bourse, gérants interrogés)")
    fictif(a2)
    fig.tight_layout()
    save(fig, "01_contexte.png")


def latence():
    fig, ax = plt.subplots(figsize=(13, 4.6))
    ep = [e[0] for e in C.EPISODES_REELS]
    v2 = [e[2] for e in C.EPISODES_REELS]
    v1 = [e[3] for e in C.EPISODES_REELS]
    x = range(len(ep))
    ax.bar([i - 0.2 for i in x], v2, width=0.4, color=TEAL, label="v2 (publiée)")
    for i, v in enumerate(v1):
        if v is None:
            ax.text(i + 0.2, 1, "manqué", rotation=90, ha="center", va="bottom", fontsize=8, color=RED)
        else:
            ax.bar(i + 0.2, v, width=0.4, color="#9CA3AF")
    from matplotlib.patches import Patch
    for i, v in enumerate(v2):
        if v == 0:
            ax.text(i - 0.2, 0.3, "0", ha="center", fontsize=9, color=TEAL, fontweight="bold")
    ax.axhline(5, color=ORANGE, ls="--", lw=1.5)
    ax.text(len(ep) - 0.5, 5.6, "objectif ≤ 5 j", color=ORANGE, ha="right", fontweight="bold")
    ax.axhline(0, color="black", lw=0.8)
    ax.set_xticks(list(x), ep)
    ax.set_ylabel("Jours de bourse après le début daté")
    ax.set_title("Latence de détection par épisode réel (hors échantillon, 2009-2026)")
    ax.legend(handles=[Patch(color=TEAL, label="v2 (publiée)"), Patch(color="#9CA3AF", label="v1 (ancienne)")], loc="lower left", frameon=False)
    ax.text(0.99, 0.01, "Négatif = alarme déjà active au début daté, pas une prévision",
            transform=ax.transAxes, ha="right", fontsize=8, color=GREY, style="italic")
    save(fig, "16_latence_episodes.png")


def track_record_crop():
    from PIL import Image
    src = OUT / "15_track_record_reel.png"
    if not src.exists():
        return
    with Image.open(src) as im:
        w, h = im.size
        im.crop((int(w * 0.11), 0, int(w * 0.89), int(h * 0.585))).save(OUT / "15b_track_record_crop.png")


# ------------------------------------------------------------------ besoin
def entretiens():
    hyp = ["H1 — Douleur « décider\ntrop tard / justifier »",
           "H2 — Rapport expliqué >\nscore brut",
           "H3 — Prêts à payer\n3 000-15 000 €/an"]
    keys = [4, 5, 6]
    counts = []
    for k in keys:
        vals = [e[k] for e in C.ENTRETIENS]
        counts.append([vals.count("V"), vals.count("P"), vals.count("X")])
    fig, ax = plt.subplots(figsize=(9, 4.2))
    left = [0] * 3
    for j, (lab, col) in enumerate([("Validée", GREEN), ("Partielle", GOLD), ("Invalidée", RED)]):
        vals = [c[j] for c in counts]
        ax.barh(hyp, vals, left=left, color=col, label=lab)
        for i, v in enumerate(vals):
            if v:
                ax.text(left[i] + v / 2, i, str(v), ha="center", va="center",
                        color="white", fontweight="bold")
        left = [a + b for a, b in zip(left, vals)]
    ax.invert_yaxis()
    ax.set_xlim(0, 13)
    ax.set_xlabel("Nombre d'entretiens (sur 13)")
    ax.set_title("Validation des hypothèses — 13 entretiens de 20 min")
    ax.legend(ncol=3, loc="lower center", bbox_to_anchor=(0.5, -0.38), frameon=False)
    fictif(ax, 1.0, -0.2)
    fig.tight_layout()
    save(fig, "02_entretiens.png")


def sondage():
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(14, 5),
                                 gridspec_kw={"width_ratios": [1.4, 1]})
    labs = [d[0] for d in C.SONDAGE_DOULEURS][::-1]
    vals = [d[1] for d in C.SONDAGE_DOULEURS][::-1]
    a1.barh(labs, vals, color=[TEAL if v >= 65 else "#9CA3AF" for v in vals])
    for i, v in enumerate(vals):
        a1.text(v + 1, i, f"{v} %", va="center", fontweight="bold")
    a1.set_xlim(0, 100)
    a1.set_title(f"Problèmes jugés importants ou très importants (n = {C.SONDAGE_N})")
    labs2 = [d[0] for d in C.SONDAGE_SORTIE]
    vals2 = [d[1] for d in C.SONDAGE_SORTIE]
    a2.bar(labs2, vals2, color=[NAVY] + ["#9CA3AF"] * 4)
    for i, v in enumerate(vals2):
        a2.text(i, v + 1, f"{v} %", ha="center", fontweight="bold")
    a2.set_title("Format de sortie préféré (1er choix)")
    a2.set_xticks(range(len(labs2)), labs2, rotation=30, ha="right")
    a2.set_ylim(0, 45)
    fictif(a2, 0.99, 0.95)
    fig.tight_layout()
    save(fig, "03_sondage_besoins.png")

    fig, (b1, b2, b3) = plt.subplots(1, 3, figsize=(15, 4.5))
    for ax, data, title, col in [
        (b1, C.WTP_GERANTS, "Gérants & family offices (n = 26)\nprix annuel acceptable", NAVY),
        (b2, C.WTP_CGP, "CGP / CIF (n = 21)\nprix mensuel acceptable", TEAL),
    ]:
        ax.bar([d[0] for d in data], [d[1] for d in data], color=col)
        for i, d in enumerate(data):
            ax.text(i, d[1] + 1, f"{d[1]} %", ha="center")
        ax.set_title(title)
        ax.set_ylim(0, 45)
    b1.text(0.5, 0.92, "Médiane ≈ 4 500 €/an", transform=b1.transAxes, ha="center",
            fontweight="bold", color=NAVY)
    b2.text(0.5, 0.92, "Médiane ≈ 55 €/mois", transform=b2.transAxes, ha="center",
            fontweight="bold", color=TEAL)
    labs3 = [d[0] for d in C.SONDAGE_CONFIANCE][::-1]
    vals3 = [d[1] for d in C.SONDAGE_CONFIANCE][::-1]
    b3.barh(labs3, vals3, color=[ORANGE if v > 60 else "#9CA3AF" for v in vals3])
    for i, v in enumerate(vals3):
        b3.text(v + 1, i, f"{v} %", va="center")
    b3.set_xlim(0, 100)
    b3.set_title("Ce qui donnerait confiance dans le signal")
    fictif(b3)
    fig.tight_layout()
    save(fig, "04_sondage_prix_confiance.png")


def marche():
    fig, ax = plt.subplots(figsize=(13, 5))
    ax.axis("off")
    widths = [0.42, 0.30, 0.18]
    cols = ["#9CA3AF", TEAL, NAVY]
    ys = [0.78, 0.48, 0.18]
    cx = 0.23
    for (lab, desc, val, src), w, c, y in zip(C.TAM_SAM_SOM, widths, cols, ys):
        ax.add_patch(Polygon([(cx - w / 2, y + 0.13), (cx + w / 2, y + 0.13),
                              (cx + w / 2 - 0.05, y - 0.13), (cx - w / 2 + 0.05, y - 0.13)],
                             closed=True, fc=c, ec="white"))
        ax.text(cx, y + 0.03, lab, ha="center", va="center", color="white",
                fontsize=13, fontweight="bold")
        ax.text(cx, y - 0.06, val, ha="center", va="center", color="white",
                fontsize=12, fontweight="bold")
        ax.text(0.47, y + 0.03, desc, ha="left", va="center", fontsize=10.5)
        ax.text(0.47, y - 0.08, src, ha="left", va="center", fontsize=9, color=GREY, style="italic")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_title("Taille du marché adressable", fontsize=14, fontweight="bold")
    fictif(ax)
    save(fig, "05_marche.png")


def positionnement():
    fig, ax = plt.subplots(figsize=(10, 6.2))
    acteurs = [
        ("JPMaQS", 9.2, 5.5, GREY), ("RavenPack", 8.6, 3.0, GREY),
        ("Permutable AI", 8.0, 4.0, GREY), ("42 Macro", 5.8, 2.5, GREY),
        ("Hedgeye", 5.0, 3.0, GREY), ("MacroMicro", 3.5, 3.8, GREY),
        ("Koyfin", 3.0, 2.0, GREY), ("Scripts TradingView", 0.8, 1.5, GREY),
        ("Notre outil", 5.0, 8.6, ORANGE),
    ]
    ax.axhline(5, color="#D1D5DB")
    ax.axvline(5, color="#D1D5DB")
    for n, x, y, c in acteurs:
        s = 900 if c == ORANGE else 350
        ax.scatter(x, y, s=s, color=c, alpha=0.9, zorder=3)
        ax.text(x, y + 0.5, n, ha="center", fontsize=11 if c == ORANGE else 9,
                fontweight="bold" if c == ORANGE else "normal")
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.set_xticks([0.5, 9.5], ["Gratuit / retail", "Sur devis / institutionnel"])
    ax.set_yticks([0.5, 9.5], ["Score brut ou\nanalyse opaque", "Expliqué + latence\net historique publiés"])
    ax.set_title("Positionnement : l'espace libre entre data institutionnelle et outils gratuits")
    ax.add_patch(FancyBboxPatch((3.2, 7.2), 3.6, 2.5, boxstyle="round,pad=0.1",
                                fc="none", ec=ORANGE, ls="--", lw=1.5))
    ax.text(0.99, 0.01, "Placement qualitatif, d'après le benchmark J1", transform=ax.transAxes,
            ha="right", fontsize=8, color=GREY, style="italic")
    save(fig, "06_positionnement.png")


def etat_art():
    fig, ax = plt.subplots(figsize=(10, 6))
    m = [("HMM / Markov-switching", 3, 6, 600), ("TVTP", 4, 5.5, 800),
         ("Statistical Jump Model", 8.5, 7.5, 600), ("k-means / GMM", 1.5, 7, 300),
         ("Wasserstein k-means", 3.5, 5, 450), ("Supervisé (boosting)", 5.5, 6.5, 700),
         ("Deep (LSTM, VAE)", 5, 2, 1500), ("NLP news (FinBERT)", 2, 4.2, 900)]
    for n, x, y, s in m:
        c = ORANGE if "Jump" in n else (TEAL if n in ("TVTP", "NLP news (FinBERT)") else NAVY)
        ax.scatter(x, y, s=s, color=c, alpha=0.75)
        ax.text(x, y + 0.55, n, ha="center", fontsize=10)
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.set_xlabel("Persistance des régimes (moins de « flip-flop ») →")
    ax.set_ylabel("Interprétabilité pour un comité →")
    ax.set_title("État de l'art : méthodes de détection de régimes\n(taille = besoin en données)")
    ax.text(0.99, 0.01, "Lecture qualitative de la littérature (J1 §1.3)", transform=ax.transAxes,
            ha="right", fontsize=8, color=GREY, style="italic")
    save(fig, "07_etat_art.png")


# ------------------------------------------------------------------ architecture
def architecture():
    fig, ax = plt.subplots(figsize=(16, 8.4))
    ax.axis("off")
    ax.set_xlim(0, 16)
    ax.set_ylim(0, 9)
    cols = [(1.3, "SOURCES (gratuites)"), (4.4, "DONNÉES & SCORES"), (7.4, "MODÈLES"),
            (10.5, "VALIDATION & EXPLICATION"), (13.9, "SORTIES")]
    for x, t in cols:
        ax.text(x, 8.6, t, ha="center", fontsize=11, fontweight="bold", color=GREY)
    src = ["FRED / ALFRED\nmacro en 1re publication,\nVIX, taux", "Tiingo\nETF : SPY, HYG,\nLQD, IEF",
           "BoE, MoF Japon,\nOCDE, BIS, BCE\n(autres zones)", "Yahoo Finance\n(recherche, test)"]
    for i, s in enumerate(src):
        box(ax, 1.3, 7.3 - i * 1.6, 2.3, 1.2, s, "#E5E7EB", tc="black", fs=8.5)
    box(ax, 4.4, 6.6, 2.6, 1.5, "data/\npoint-in-time, licence\npar série, cache", NAVY, fs=9)
    box(ax, 4.4, 3.9, 2.6, 1.9, "features/\n12 indicateurs →\n3 scores : stress,\ncroissance, inflation\n+ règle des 4 régimes", NAVY, fs=9)
    for i in range(4):
        arrow(ax, 2.45, 7.3 - i * 1.6, 3.1, 6.6 if i < 3 else 6.3, color="#9CA3AF" if i == 3 else GREY)
    arrow(ax, 4.4, 5.85, 4.4, 4.85)
    box(ax, 7.4, 7.0, 2.7, 0.9, "Statistical Jump Model\n(régimes)", ORANGE, fs=9.5, bold=True)
    box(ax, 7.4, 5.8, 2.7, 0.9, "Détecteur onset (v2)\ndébut de stress", ORANGE, fs=9.5, bold=True)
    box(ax, 7.4, 4.6, 2.7, 0.9, "Gradient boosting\nrégime à 1 semaine", "#9CA3AF", fs=9)
    box(ax, 7.4, 3.4, 2.7, 0.9, "k-means (référence)", "#9CA3AF", fs=9)
    box(ax, 7.4, 2.1, 2.7, 1.1, "combined = régimes jump\nP(stress) = max(jump,\ngbm, onset) → Platt", NAVY, fs=8.5)
    ax.text(7.4, 1.35, "models/  · challengers publiés en live à côté", ha="center", fontsize=8, color=GREY, style="italic")
    for y in (7.0, 5.8, 4.6, 3.4):
        arrow(ax, 5.7, 3.9, 6.05, y)
    box(ax, 10.5, 6.6, 2.9, 1.6, "validation/\nwalk-forward annuel\nlatence · fausses alertes\nBrier · ECE · holdout", GREEN, fs=9)
    box(ax, 10.5, 4.3, 2.9, 1.4, "explain / outlook\ncontributions, bascule,\nce qui a changé", GREEN, fs=9)
    box(ax, 10.5, 2.3, 2.9, 1.2, "Pré-enregistrement\ndocs/*.md avant\ntout calcul réel", "#374151", fs=9)
    arrow(ax, 8.75, 2.1, 9.05, 6.6)
    arrow(ax, 8.75, 2.1, 9.05, 4.3)
    outs = [("Track record public\nSHA-256 + Bitcoin", ORANGE), ("Note de comité\nPDF / HTML / MD, FR-EN", ORANGE),
            ("Application Streamlit\n7 écrans", TEAL), ("API REST FastAPI", TEAL),
            ("Alertes e-mail,\nscénarios, 4 zones", "#9CA3AF")]
    for i, (o, c) in enumerate(outs):
        y = 7.4 - i * 1.35
        box(ax, 13.9, y, 2.8, 1.05, o, c, fs=9)
        arrow(ax, 11.95, 5.0, 12.5, y)
    ax.add_patch(FancyBboxPatch((0.1, 0.15), 15.8, 0.75, boxstyle="round,pad=0.02",
                                fc=LIGHT, ec="#D1D5DB"))
    ax.text(8, 0.52, "GitHub Actions chaque jour ouvré à 22 h 30 : publish → challengers → régions → track record → "
            "alertes → contrôle de santé  ·  Python · pandas · jump-models · scikit-learn · LightGBM · "
            "Streamlit · FastAPI · pytest + ruff",
            ha="center", va="center", fontsize=8)
    save(fig, "08_architecture.png")


# ------------------------------------------------------------------ arbres
def arbre(key, fname):
    t = C.ARBRES[key]
    opts = t["options"]
    nf = len(t["filtres"])
    n = len(opts)
    W = 2.3 * n + 3.8
    H = 2.0 * nf + 4.0
    fig, ax = plt.subplots(figsize=(W * 0.82, H * 0.82))
    ax.axis("off")
    ax.set_xlim(0, W)
    ax.set_ylim(0, H)
    box(ax, W / 2 + 1.6, H - 0.65, W - 4.2, 1.0, "? " + t["question"],
        "#DBEAFE", ec="#2196F3", tc="black", fs=10, bold=True)
    xs = [4.3 + 2.3 * i for i in range(n)]
    yopt = H - 2.0
    for x, (name, _) in zip(xs, opts):
        box(ax, x, yopt, 2.0, 0.85, name, NAVY, fs=9, bold=True)
        arrow(ax, x, H - 1.15, x, yopt + 0.45, color="#93C5FD")
    for j, f in enumerate(t["filtres"]):
        y = yopt - 1.9 - j * 2.0
        ax.add_patch(Polygon([(1.4, y + 0.75), (2.75, y), (1.4, y - 0.75), (0.05, y)],
                             closed=True, fc="#FFF8E1", ec="#FFA000", lw=1.5))
        ax.text(1.4, y, f, ha="center", va="center", fontsize=7.5)
        ax.plot([2.75, W - 0.1], [y, y], color="#FDE68A", lw=0.8, ls=":", zorder=0)
    for x, (name, res) in zip(xs, opts):
        ytop = yopt - 0.45
        for j, r in enumerate(res):
            y = yopt - 1.9 - j * 2.0
            if r == "ok":
                ax.plot([x, x], [ytop, y - 0.25], color=GREEN, lw=2)
                ax.text(x + 0.12, y + 0.05, "Oui ✓", color=GREEN, fontsize=8, fontweight="bold")
                ytop = y - 0.25
            else:
                kind, reason = r
                ax.plot([x, x], [ytop, y + 0.6], color=RED if kind == "x" else GOLD, lw=2)
                fc = "#FFEBEE" if kind == "x" else "#FEF3C7"
                ec = "#FF5252" if kind == "x" else "#D97706"
                head = "✗ Écarté" if kind == "x" else "↻ Autre rôle"
                box(ax, x, y, 2.1, 1.2, f"{head}\n{reason}", fc, ec=ec, tc="black", fs=7.5)
                break
        else:
            ax.plot([x, x], [ytop, 1.25], color=GREEN, lw=2.5)
    box(ax, W / 2 + 1.6, 0.7, W - 4.2, 1.0, "✓ RETENU — " + t["retenu"], "#E8F5E9",
        ec="#4CAF50", tc="black", fs=9.5, bold=True)
    ax.set_title(t["titre"], fontsize=14, fontweight="bold", loc="left")
    save(fig, fname)


# ------------------------------------------------------------------ risques
def risques():
    lvl_p = {"Faible": 0, "Moyenne": 1, "Forte": 2}
    lvl_i = {"Faible": 0, "Moyen": 1, "Fort": 2}
    fig, ax = plt.subplots(figsize=(8.5, 6.5))
    colors = [["#D1FAE5", "#FEF3C7", "#FDE68A"], ["#FEF3C7", "#FDBA74", "#FCA5A5"],
              ["#FDE68A", "#FCA5A5", "#F87171"]]
    for i in range(3):
        for p in range(3):
            ax.add_patch(plt.Rectangle((p, i), 1, 1, fc=colors[i][p], ec="white", lw=3))
    cells = {}
    for r in C.RISQUES:
        k = (lvl_p[r[3]], lvl_i[r[4]])
        cells.setdefault(k, []).append(r[0])
    for (p, i), ids in cells.items():
        for n, rid in enumerate(ids):
            dx = (n - (len(ids) - 1) / 2) * 0.3
            ax.scatter(p + 0.5 + dx, i + 0.5, s=900, color=NAVY, zorder=3)
            ax.text(p + 0.5 + dx, i + 0.5, rid, color="white", ha="center", va="center",
                    fontweight="bold", zorder=4)
    ax.set_xlim(0, 3)
    ax.set_ylim(0, 3)
    ax.set_xticks([0.5, 1.5, 2.5], ["Faible", "Moyenne", "Forte"])
    ax.set_yticks([0.5, 1.5, 2.5], ["Faible", "Moyen", "Fort"])
    ax.set_xlabel("Probabilité", fontweight="bold")
    ax.set_ylabel("Impact", fontweight="bold")
    ax.set_title("Matrice des risques (méthode TELOS)")
    for s in ax.spines.values():
        s.set_visible(False)
    save(fig, "13_risques.png")


# ------------------------------------------------------------------ planning
def gantt():
    import datetime as dt
    tasks = [
        ("Track record live (US + 3 zones)", "2026-10-19", "2026-12-18", ORANGE, "job automatique"),
        ("Appropriation du code : 1 module / membre", "2026-10-22", "2026-11-06", GREY, "tous"),
        ("Protocole de test utilisateur", "2026-10-26", "2026-11-06", GREEN, "Robin, Amine"),
        ("Tests utilisateurs (≥ 3 gérants)", "2026-11-09", "2026-11-20", GREEN, "Robin, Amine"),
        ("Ralentissement v2.4 pré-enregistré", "2026-10-26", "2026-11-13", NAVY, "Gabriel, Axel"),
        ("Overlay de risque 60/40", "2026-11-09", "2026-11-20", NAVY, "Amine, Titouan"),
        ("Couche actualité en challenger", "2026-11-02", "2026-11-27", TEAL, "Axel, Gabriel"),
        ("Rédaction J3 (3.1 → 3.3)", "2026-11-23", "2026-11-30", GREY, "Titouan + tous"),
    ]
    fig, ax = plt.subplots(figsize=(13, 4.8))
    d0 = dt.date(2026, 10, 19)
    for i, (n, a, b, c, who) in enumerate(tasks):
        s = (dt.date.fromisoformat(a) - d0).days
        e = (dt.date.fromisoformat(b) - d0).days
        ax.barh(i, e - s, left=s, color=c, height=0.55)
        ax.text(min(e, 59) + 0.5, i, who, va="center", fontsize=8, color=GREY)
    ax.set_yticks(range(len(tasks)), [t[0] for t in tasks])
    ax.invert_yaxis()
    for lab, d, col in [("J2", "2026-10-31", RED), ("Go/no-go", "2026-11-13", ORANGE),
                        ("J3", "2026-11-30", RED)]:
        x = (dt.date.fromisoformat(d) - d0).days
        ax.axvline(x, color=col, ls="--")
        ax.text(x, -0.9, lab, color=col, ha="center", fontweight="bold", fontsize=9)
    ticks = list(range(0, 62, 7))
    ax.set_xticks(ticks, [(d0 + dt.timedelta(days=t)).strftime("%d/%m") for t in ticks])
    ax.set_xlim(0, 66)
    ax.set_title("Planning Phase 3 — gel des nouvelles fonctionnalités jusqu'aux tests (dates indicatives)", pad=30)
    save(fig, "14_planning.png")


# ------------------------------------------------------------------ maquette
def maquette():
    fig = plt.figure(figsize=(12, 6.6))
    fig.patch.set_facecolor("white")
    ax = fig.add_axes([0, 0, 1, 1])
    ax.axis("off")
    ax.add_patch(FancyBboxPatch((0.01, 0.01), 0.98, 0.98, boxstyle="round,pad=0,rounding_size=0.01",
                                fc="#FAFAFA", ec="#D1D5DB"))
    ax.text(0.03, 0.93, "Rapport de comité — semaine du 19/10/2026", fontsize=15, fontweight="bold", color=NAVY)
    ax.text(0.97, 0.93, "MAQUETTE · valeurs illustratives", fontsize=9, color=RED, ha="right", style="italic")
    box(ax, 0.17, 0.75, 0.28, 0.2, "Régime actuel\nRALENTISSEMENT\nprobabilité 62 %", REGIMES["Ralentissement"],
        tc="black", fs=13, bold=True, r=0.01)
    ax.text(0.03, 0.61, "Probabilités", fontsize=11, fontweight="bold")
    for i, (k, v) in enumerate([("Expansion", 14), ("Surchauffe", 9), ("Ralentissement", 62), ("Stress / Crise", 15)]):
        y = 0.56 - i * 0.055
        ax.text(0.03, y, k, fontsize=9, va="center")
        ax.add_patch(plt.Rectangle((0.15, y - 0.02), 0.17 * v / 62, 0.04, fc=REGIMES[k]))
        ax.text(0.155 + 0.17 * v / 62, y, f" {v} %", fontsize=9, va="center")
    a2 = fig.add_axes([0.43, 0.42, 0.24, 0.42])
    f = ["Pente 10a−3m", "VIX / VIX3M", "Spread HYG/LQD", "Cuivre / or", "Score news", "NFCI"]
    v = [0.21, 0.17, 0.12, -0.06, 0.09, 0.05]
    a2.barh(f[::-1], v[::-1], color=[ORANGE if x > 0 else TEAL for x in v[::-1]])
    a2.set_title("Facteurs qui expliquent le régime", fontsize=11)
    a2.tick_params(labelsize=8)
    a2.axvline(0, color="black", lw=0.8)
    ax.text(0.72, 0.84, "Ce qui a changé en une semaine", fontsize=11, fontweight="bold")
    for i, line in enumerate(["▲ Probabilité de stress : 7 % → 15 %",
                              "▲ VIX/VIX3M passe au-dessus de 0,95",
                              "▼ Courbe 10a−3m : −0,12 pt",
                              "= Inflation anticipée stable (2,3 %)"]):
        ax.text(0.72, 0.77 - i * 0.06, line, fontsize=9.5)
    a3 = fig.add_axes([0.04, 0.07, 0.62, 0.22])
    import numpy as np
    rng = np.random.default_rng(3)
    p = np.clip(np.convolve(rng.normal(0, 1, 260).cumsum() * 0.02 + 0.12, np.ones(5) / 5, "same"), 0, 1)
    p[-25:] = np.linspace(p[-26], 0.15, 25)
    a3.fill_between(range(260), p, color=RED, alpha=0.35)
    a3.axhline(0.5, color=RED, ls="--", lw=1)
    a3.set_title("Probabilité de stress sur 12 mois (seuil d'alerte 50 %)", fontsize=10)
    a3.set_xticks([])
    a3.tick_params(labelsize=8)
    ax.text(0.72, 0.42, "Historique de nos signaux", fontsize=11, fontweight="bold")
    for i, line in enumerate(["Publiés chaque soir depuis le 30/10/2026",
                              "Latence médiane : à mesurer (objectif ≤ 5 j)",
                              "Fausses alertes/an : à mesurer (obj. ≤ 1,5)"]):
        ax.text(0.72, 0.36 - i * 0.055, line, fontsize=9)
    ax.text(0.72, 0.12, "Information générale, identique pour tous les lecteurs.\n"
            "Ne constitue pas un conseil en investissement.\nCommentaire généré par IA puis relu.",
            fontsize=8, color=GREY, style="italic")
    save(fig, "09_maquette_rapport.png")


if __name__ == "__main__":
    contexte()
    latence()
    track_record_crop()
    entretiens()
    sondage()
    marche()
    positionnement()
    etat_art()
    architecture()
    arbre("detection", "10_arbre_detection.png")
    arbre("donnees", "11_arbre_donnees.png")
    arbre("modele", "12c_arbre_modele.png")
    arbre("diffusion", "12b_arbre_diffusion.png")
    arbre("news", "12a_arbre_news.png")
    risques()
    gantt()
    print("ok", sorted(p.name for p in OUT.iterdir()))
