# Thesis report

`python -m pfe_drai thesis` assembles a methods and results report (French and English) from this folder, the docs in
`docs/`, the backtest records in `track_record/backtest/`, the live record in `track_record/` and `config/settings.yaml`.
It needs no network and no API key, and it writes only to its output folder (`thesis/`, not committed).

```powershell
python -m pfe_drai thesis --lang fr --format html --out thesis    # one self-contained HTML file
python -m pfe_drai thesis --lang both --format all --out thesis   # fr and en: md (+ figures/), html, pdf
python -m pfe_drai thesis --check                                 # docs against records, and every placeholder
```

`--format pdf` prints the HTML with a Chromium-based browser (Edge, Chrome or Chromium; set `PFE_DRAI_BROWSER` to point to
one). No PDF library is a dependency. Without a browser, open the `.html` and print it to PDF.

## Files

| File | Role |
|---|---|
| `manifest.yaml` | Chapter order, titles in both languages, the docs each chapter may quote, and the consistency `checks` |
| `NN-name.fr.md`, `NN-name.en.md` | One chapter per language. The first line is `# <title>`, the manifest title (checked) |
| `references.md` | Names to look up, **for the owner to verify and complete**: the build warns while a `TODO` is left |

## Placeholders in a chapter

| Placeholder | Becomes |
|---|---|
| `{{backtest.current.metrics.brier\|3}}` | a number from the backtest record of the model version in `models.version` (or `{{backtest.v2_2...}}` for a given version), with an explicit format |
| `{{config.validation.targets.max_false_alarm_share\|pct0}}` | a setting from `config/settings.yaml` |
| `{{meta.commit}}`, `{{live.days}}` | the build's identity, the live record |
| `{{table:episodes}}`, `{{table:metrics}}`, `{{table:reliability}}`, `{{table:versions}}`, `{{table:rules}}`, `{{table:live}}` | a generated table (add `@v2_2` for another version) |
| `{{figure:timeline}}`, `{{figure:latency}}`, `{{figure:reliability}}` | an inline SVG figure (a file in `figures/` for Markdown) |
| `{{quote:Doc.md#Results > Section}}` | the section of `docs/Doc.md`, verbatim, with its commit |
| `{{cell:Doc.md#Results > Section \| row \| column}}` | one cell of a table in a doc, as printed there |
| `{{repro}}`, `{{references}}` | the generated reproducibility table and the bibliography |

Formats: none (integers), `0` to `4` (decimals), `pct0` to `pct4` (percent), `signed0` to `signed4`, `date`, `yesno`. A decimal
number without a format, an unknown placeholder, a quote of a doc the chapter does not list under `sources`, or a section
that no longer exists is a build error, and all of them are listed together.

## Rules

- Do not edit the docs to make a number agree: they are history. `--check` compares the tables they print with the records
  (declared under `checks` in the manifest) to the printed precision and fails on a difference.
- Report weak results as weak, name the data window and model version of every performance claim, and say whether it was
  pre-registered or chosen after seeing the episodes (they are *seen* since 2026-10-01).
- Never invent a result or a citation. A number that exists only in a doc is quoted (`quote`, `cell`), not retyped.
- A new chapter needs both languages, the same placeholders in both (a test compares them), and a manifest entry.
