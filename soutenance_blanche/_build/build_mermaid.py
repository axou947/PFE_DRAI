"""Génère arbres_mermaid.md (arbres de choix éditables) depuis content.ARBRES."""
from pathlib import Path

import content as C

ROOT = Path(__file__).resolve().parent.parent


def esc(s):
    return s.replace("\n", "<br/>").replace('"', "'")


def tree(key, a):
    lines = ["```mermaid", "flowchart TD", f'    Q["{esc(a["question"])}"]']
    for i, (name, res) in enumerate(a["options"]):
        prev = f"O{i}"
        lines.append(f'    Q --> {prev}["{esc(name)}"]')
        for j, r in enumerate(res):
            filtre = esc(a["filtres"][j].split("\n")[0])
            if r == "ok":
                continue
            kind, why = r
            node = f"X{i}_{j}"
            label = "Écarté" if kind == "x" else "Gardé autrement"
            lines.append(f'    {prev} -- "{filtre}" --> {node}["{label} : {esc(why)}"]')
            lines.append(f"    class {node} {'rej' if kind == 'x' else 'alt'}")
            break
        else:
            lines.append(f'    {prev} ==> R["✓ {esc(a["retenu"])}"]')
    lines += ["    class R ok",
              "    classDef rej fill:#FDECEA,stroke:#C0392B",
              "    classDef alt fill:#FEF3C7,stroke:#D97706",
              "    classDef ok fill:#E8F5E9,stroke:#2E7D32", "```"]
    return lines


def main():
    out = ["# Arbres de choix — version éditable (Mermaid)", "",
           "Généré depuis `_build/content.py`. Collez un bloc dans Notion, GitHub ou "
           "[mermaid.live](https://mermaid.live) pour le modifier.", ""]
    for key, a in C.ARBRES.items():
        out += [f"## {a['titre']}", "", "Filtres :", ""]
        out += [f"- {f.replace(chr(10), ' ')}" for f in a["filtres"]]
        out += [""] + tree(key, a) + ["", f"**Synthèse.** {a['synthese']}", ""]
    (ROOT / "arbres_mermaid.md").write_text("\n".join(out), encoding="utf-8")
    print("mermaid ok")


if __name__ == "__main__":
    main()
