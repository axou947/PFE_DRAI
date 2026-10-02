"""Assemble the report: chapters + placeholders -> one Markdown, one self-contained HTML, one PDF."""

import html
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ..i18n import fmt_date
from .blocks import CAPTIONS, FIGURES, TABLES, _norm, extract_section, quote_block, standalone_svg
from .check import Report, column_index, read_table, run_checks
from .markup import format_value, headings, slug, to_html
from .sources import Sources, ThesisError, load_sources, version_key

LANGS = ("fr", "en")
TOKEN = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
WORDS = {
    "table": {"fr": "Tableau", "en": "Table"},
    "figure": {"fr": "Figure", "en": "Figure"},
    "chapter": {"fr": "Chapitre", "en": "Chapter"},
    "appendix": {"fr": "Annexe", "en": "Appendix"},
    "contents": {"fr": "Table des matières", "en": "Contents"},
}


def load_manifest(src: Sources) -> dict:
    path = src.thesis_dir / "manifest.yaml"
    if not path.exists():
        raise ThesisError([f"{path} does not exist"])
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def validate_manifest(src: Sources, manifest: dict) -> list[str]:
    """Same chapters in both languages, each chapter file present and titled as the manifest says."""
    problems = []
    for key in ("title", "subtitle"):
        if set(manifest.get(key, {})) != set(LANGS):
            problems.append(f"manifest: '{key}' needs both languages ({', '.join(LANGS)})")
    for ch in manifest["chapters"]:
        if set(ch["title"]) != set(LANGS):
            problems.append(f"manifest: chapter '{ch['id']}' needs a title in both languages")
        for lang in LANGS:
            file = src.thesis_dir / f"{ch['file']}.{lang}.md"
            if not file.exists():
                problems.append(f"missing chapter file docs/thesis/{ch['file']}.{lang}.md")
                continue
            first = next(iter(headings(file.read_text(encoding="utf-8"))), None)
            if not first or first[0] != 1 or first[1].strip() != ch["title"][lang].strip():
                problems.append(f"{file.name}: first line must be '# {ch['title'][lang]}' (the manifest title)")
    for doc in {d for ch in manifest["chapters"] for d in ch.get("sources", [])}:
        if not (src.docs_dir / doc).exists():
            problems.append(f"manifest: source docs/{doc} does not exist")
    return problems


def tokens_of(text: str) -> list[str]:
    return TOKEN.findall(text)


@dataclass
class Renderer:
    """Resolves the placeholders of one chapter text for one language and one output target (md or html)."""

    src: Sources
    lang: str
    target: str  # md | html
    problems: list[str] = field(default_factory=list)
    figures: dict[str, str] = field(default_factory=dict)  # figure file name -> standalone svg
    raws: dict[int, str] = field(default_factory=dict)
    counters: dict[str, int] = field(default_factory=lambda: {"table": 0, "figure": 0})
    references_todo: int = 0

    def resolve(self, text: str, where: str, declared: set[str]) -> str:
        def one(m: re.Match) -> str:
            token = m.group(1)
            try:
                return self._token(token, declared)
            except ThesisError as exc:
                self.problems += [f"{where}: {p}" for p in exc.problems]
            except (KeyError, ValueError, IndexError) as exc:
                self.problems.append(f"{where}: {{{{{token}}}}}: {exc.args[0] if exc.args else exc}")
            return f"[{token}]"

        return TOKEN.sub(one, text)

    def _token(self, token: str, declared: set[str]) -> str:
        kind, sep, arg = token.partition(":")
        if sep and kind in ("table", "figure", "quote", "cell"):
            if kind == "cell":
                return self._cell(arg, declared)
            if kind == "quote":
                return "\n" + quote_block(self.src, arg.strip(), self.lang, declared) + "\n"
            return self._block(kind, arg.strip())
        if token == "repro":
            return "\n" + self._repro() + "\n"
        if token == "references":
            return "\n" + self._references() + "\n"
        ref, _, fmt = token.partition("|")
        return format_value(self.src.lookup(ref.strip()), fmt.strip() or None, self.lang)

    def _cell(self, arg: str, declared: set[str]) -> str:
        """{{cell:Doc.md#A > B | row label | column [| table number]}}: one cell of a table in a doc, as printed there."""
        parts = [p.strip() for p in arg.split("|")]
        if len(parts) not in (3, 4):
            raise ValueError("cell needs 'Doc.md#Section | row | column' (and optionally a table number)")
        where, row, column = parts[:3]
        doc, _, path = where.partition("#")
        if doc not in declared:
            raise ThesisError([f"cell of docs/{doc} but the chapter's manifest entry does not list it under 'sources'"])
        try:
            head, rows = read_table(
                extract_section((self.src.docs_dir / doc).read_text(encoding="utf-8"), path),
                int(parts[3]) - 1 if len(parts) == 4 else 0,
            )
            col = column_index(head, column)
        except (KeyError, ValueError, FileNotFoundError) as exc:
            raise ValueError(f"cell docs/{doc}: {exc.args[0] if exc.args else exc}") from exc
        match = [r for r in rows if _norm(r[0]).startswith(_norm(row))]
        if len(match) != 1:
            raise ValueError(f"cell docs/{doc}: row '{row}' {'not found' if not match else 'ambiguous'}")
        text = match[0][col].replace("**", "").strip()
        return re.sub(r"(?<=\d)\.(?=\d)", ",", text) if self.lang == "fr" else text  # decimal comma in French prose

    # -- tables and figures
    def _block(self, kind: str, arg: str) -> str:
        name, _, ver = arg.partition("@")
        registry = TABLES if kind == "table" else FIGURES
        if name not in registry:
            raise KeyError(f"unknown {kind} '{name}' ({', '.join(registry)})")
        rec = None
        if kind == "figure" or TABLES[name][1] == "rec":
            rec = self.src.backtest(version_key(ver) if ver else None)
        self.counters[kind] += 1
        number = self.counters[kind]
        version = (rec or {}).get("model_version") or "–"
        caption = CAPTIONS[f"{kind}s"][name][self.lang].format(v=version)
        label = f"{WORDS[kind][self.lang]} {number}"
        if kind == "table":
            func, needs = TABLES[name]
            table = func(rec if needs == "rec" else self.src, self.lang)
            if self.target == "md":
                return f"\n**{label}.** {caption}\n\n{table.md()}\n"
            return self._raw(
                f'<figure class="tbl"><figcaption><strong>{label}.</strong> {html.escape(caption)}</figcaption>{table.html()}</figure>'
            )
        svg = registry[name](rec, self.lang)
        if not svg:
            raise ValueError(f"figure '{name}' has no data")
        file = f"{name}{'-' + version_key(ver) if ver else ''}.svg"
        self.figures[file] = standalone_svg(svg)
        if self.target == "md":
            return f"\n![{caption}](figures/{file})\n\n*{label}.* {caption}\n"
        return self._raw(
            f'<figure><div class="chart">{svg}</div><figcaption><strong>{label}.</strong> {html.escape(caption)}</figcaption></figure>'
        )

    def _raw(self, markup: str) -> str:
        n = len(self.raws)
        self.raws[n] = markup
        return f"\n@@RAW:{n}@@\n"

    # -- appendix blocks
    def _repro(self) -> str:
        m, fr = self.src.meta, self.lang == "fr"
        rec = self.src.backtests.get(self.src.current or "", {})
        period = rec.get("period", {})
        same = m["settings_sha256"] == m["config_sha256"]
        rows = [
            ("Version du modèle" if fr else "Model version", m["model_version"] or "–"),
            ("Commit du dépôt" if fr else "Repository commit", m["commit"]),
            (
                "Commit du code qui a produit l'enregistrement" if fr else "Code commit that produced the record",
                m["record_code_version"] or "–",
            ),
            ("Données" if fr else "Data", m["data_provider"] or "–"),
            (
                "Période hors échantillon" if fr else "Out-of-sample period",
                f"{fmt_date(period['start'], self.lang)} → {fmt_date(period['end'], self.lang)}" if period else "–",
            ),
            (
                "Enregistrement généré le" if fr else "Record generated at",
                (m["record_generated_at"] or "–").replace("T", " ").replace("+00:00", " UTC"),
            ),
            (
                "Empreinte des réglages (config_sha256)" if fr else "Settings fingerprint (config_sha256)",
                m["config_sha256"] or "–",
            ),
            (
                "Les réglages actuels ont cette empreinte" if fr else "Current settings have this fingerprint",
                (format_value(same, "yesno", self.lang)) if m["config_sha256"] else "–",
            ),
            ("Règle d'épisodes gelée (sha256)" if fr else "Frozen episode rule (sha256)", m["episode_rule_sha256"] or "–"),
            (
                "Règle gelée le" if fr else "Rule frozen on",
                fmt_date(m["episode_rule_frozen"], self.lang) if m["episode_rule_frozen"] else "–",
            ),
        ]
        table = "\n".join(f"| {k} | `{v}` |" for k, v in rows)
        table = "| " + ("Élément" if fr else "Item") + " | " + ("Valeur" if fr else "Value") + " |\n| --- | --- |\n" + table
        intro = (
            "Chaque chiffre de ce document est lu dans un fichier du dépôt au moment de la construction. Identité de cette construction :"
            if fr
            else "Every number in this document is read from a file of the repository when it is built. Identity of this build:"
        )
        cmds = "\n".join(
            [
                "```powershell",
                f"python -m pfe_drai thesis --lang {self.lang} --format html --out thesis",
                "python -m pfe_drai thesis --check",
                "```",
            ]
        )
        verify_intro = (
            "Pour vérifier un jour publié (`track_record/AAAA-MM-JJ.json`), le fichier doit avoir l'empreinte de `track_record/index.csv`, et sa preuve doit être complétée puis vérifiée avec OpenTimestamps (voir `docs/TRACK_RECORD.md`) :"
            if fr
            else "To verify a published day (`track_record/YYYY-MM-DD.json`), the file must hash to the value in `track_record/index.csv`, and its proof must be upgraded and verified with OpenTimestamps (see `docs/TRACK_RECORD.md`):"
        )
        verify = "\n".join(
            [
                "```powershell",
                "Get-FileHash track_record\\2026-10-01.json -Algorithm SHA256",
                "ots upgrade track_record\\2026-10-01.json.ots",
                "ots verify track_record\\2026-10-01.json.ots",
                "```",
            ]
        )
        regen = (
            "Pour reconstruire ce document et vérifier sa cohérence avec les enregistrements :"
            if fr
            else "To rebuild this document and check it against the records:"
        )
        return f"{intro}\n\n{table}\n\n{verify_intro}\n\n{verify}\n\n{regen}\n\n{cmds}"

    def _references(self) -> str:
        path = self.src.thesis_dir / "references.md"
        if not path.exists():
            raise ThesisError(["docs/thesis/references.md does not exist"])
        body = re.sub(r"<!--.*?-->", "", path.read_text(encoding="utf-8"), flags=re.S).strip()
        body = re.sub(r"^#\s.*\n", "", body).strip()  # the chapter has its own title
        self.references_todo = len(re.findall(r"TODO", body))
        return body


def _shift_headings(md: str, by: int = 1) -> str:
    out, fenced = [], False
    for line in md.split("\n"):
        if line.startswith("```"):
            fenced = not fenced
        elif not fenced and re.match(r"#{1,5}\s", line):
            line = "#" * by + line
        out.append(line)
    return "\n".join(out)


def compile_markdown(src: Sources, manifest: dict, lang: str, target: str) -> tuple[str, Renderer]:
    """The whole report as Markdown (target md) or Markdown with RAW blocks for the HTML converter."""
    problems = validate_manifest(src, manifest)
    if problems:
        raise ThesisError(problems)
    r = Renderer(src, lang, target)
    parts = [f"# {manifest['title'][lang]}", "", f"*{manifest['subtitle'][lang]}*", ""]
    n_chapter, n_appendix = 0, 0
    for ch in manifest["chapters"]:
        text = (src.thesis_dir / f"{ch['file']}.{lang}.md").read_text(encoding="utf-8")
        text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
        declared = set(ch.get("sources", []))
        title = ch["title"][lang]
        if ch.get("kind") == "appendix":
            n_appendix += 1
            numbered = f"{WORDS['appendix'][lang]} {chr(64 + n_appendix)}. {title}"
        else:
            n_chapter += 1
            numbered = f"{n_chapter}. {title}"
        body = text.split("\n", 1)[1] if "\n" in text else ""
        body = r.resolve(_shift_headings(body, 1), f"{ch['file']}.{lang}.md", declared)
        parts += [f"## {numbered}", "", body.strip("\n"), ""]
    return "\n".join(parts), r


# ---------------------------------------------------------------- html and pdf
CSS = """
:root{--page:#fff;--surface:#fcfcfb;--ink:#161616;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;
--p:#2a78d6;--score:#898781;--band:#ecebe6;--alarm:#d03b3b;--good:#006300;--bad:#b42323;--chip:#f0efec}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);font:11pt/1.55 "Georgia","Cambria","Times New Roman",serif}
main{max-width:46rem;margin:0 auto;padding:2rem 1.2rem 4rem}
h1,h2,h3,h4{font-family:system-ui,-apple-system,"Segoe UI",Arial,sans-serif;line-height:1.25;color:var(--ink)}
h1{font-size:2rem;margin:0 0 .3rem}h2{font-size:1.5rem;margin:3rem 0 .6rem;padding-top:1rem;border-top:2px solid var(--ink)}
h3{font-size:1.15rem;margin:1.8rem 0 .4rem}h4{font-size:1rem;margin:1.2rem 0 .3rem}
p{margin:.55rem 0;text-align:justify;hyphens:auto}a{color:var(--p)}
.sub{color:var(--ink2);font-size:1.05rem;margin:0 0 1rem}
.titlepage{margin:1rem 0 2rem}.meta{color:var(--ink2);font:9.5pt system-ui,sans-serif}
nav.toc{border:1px solid var(--grid);border-radius:8px;padding:.8rem 1.2rem;margin:1.2rem 0;font:10pt/1.5 system-ui,sans-serif}
nav.toc ul{margin:.3rem 0;padding-left:0;list-style:none}nav.toc a{text-decoration:none}
blockquote{margin:1rem 0;padding:.4rem 1rem;border-left:4px solid var(--axis);background:var(--chip);font-size:10pt}
blockquote p{text-align:left}
code{font:9.5pt ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;background:var(--chip);padding:0 .25em;border-radius:3px}
pre{background:var(--chip);padding:.6rem .8rem;border-radius:6px;overflow-x:auto;font-size:9pt}pre code{background:none;padding:0}
figure{margin:1.2rem 0}figcaption{font:9.5pt/1.4 system-ui,sans-serif;color:var(--ink2);margin:.35rem 0}
figure.tbl figcaption{margin:0 0 .35rem}
.table-wrap{overflow-x:auto;margin:.6rem 0}
table{border-collapse:collapse;width:100%;font:9pt/1.35 system-ui,sans-serif}
th,td{padding:.3rem .5rem;border-bottom:1px solid var(--grid);text-align:left;vertical-align:top}
th{border-bottom:2px solid var(--ink);color:var(--ink)}td.r,th.r{text-align:right;font-variant-numeric:tabular-nums}
td.l,th.l{text-align:left}td.nw{white-space:nowrap}td.c,th.c{text-align:center}
.chart svg{width:100%;height:auto;display:block}.chart text{fill:var(--muted);font:10px system-ui,sans-serif}.chart .miss{fill:var(--bad)}
ul,ol{margin:.5rem 0;padding-left:1.5rem}li{margin:.2rem 0}
footer{margin-top:3rem;color:var(--ink2);font:9pt system-ui,sans-serif;border-top:1px solid var(--grid);padding-top:.6rem}
@page{size:A4;margin:20mm 18mm 22mm;@bottom-center{content:counter(page);font:9pt system-ui,sans-serif;color:#52514e}}
@media print{
  body{font-size:10.5pt}main{max-width:none;padding:0}
  h2{break-before:page;border-top:0;padding-top:0;margin-top:0}h2:first-of-type{break-before:auto}
  h3,h4,figcaption{break-after:avoid}figure,table,blockquote,pre{break-inside:avoid}
  nav.toc{break-after:page}a{color:inherit;text-decoration:none}
}
"""


def compile_html(src: Sources, manifest: dict, lang: str) -> tuple[str, Renderer]:
    md, r = compile_markdown(src, manifest, lang, "html")
    body = to_html(md, r.raws)
    # Contents: chapters and their sections, from the headings the converter numbered.
    toc = f"<nav class='toc'><strong>{WORDS['contents'][lang]}</strong><ul>"
    for level, text in headings(md):
        if level == 2:
            toc += f'<li><a href="#{slug(re.sub(r"[`*]", "", text))}">{html.escape(text)}</a></li>'
    toc += "</ul></nav>"
    first_h2 = body.find("<h2")
    head, rest = (body[:first_h2], body[first_h2:]) if first_h2 > 0 else (body, "")
    head = head.replace("<h1", '<h1 class="doc"', 1)
    m = src.meta
    meta = f"commit {m['commit']} · {m['model_version'] or '–'}"
    doc = (
        f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{html.escape(manifest['title'][lang])}</title><style>{CSS}</style></head><body><main>"
        f'<div class="titlepage">{head}<p class="meta">{html.escape(meta)}</p></div>{toc}{rest}'
        "<footer>"
        + (
            "Document assemblé automatiquement par <code>python -m pfe_drai thesis</code> : chaque chiffre est lu dans un enregistrement du dépôt."
            if lang == "fr"
            else "Assembled automatically by <code>python -m pfe_drai thesis</code>: every number is read from a record in the repository."
        )
        + "</footer></main></body></html>"
    )
    return doc, r


def find_browser() -> str | None:
    """A Chromium-based browser able to print to PDF: PFE_DRAI_BROWSER, then PATH, then the usual Windows/macOS/Linux places."""
    if os.environ.get("PFE_DRAI_BROWSER"):
        return os.environ["PFE_DRAI_BROWSER"]
    for name in ("msedge", "microsoft-edge", "google-chrome", "chrome", "chromium", "chromium-browser"):
        if found := shutil.which(name):
            return found
    roots = [os.environ.get(k, "") for k in ("ProgramFiles", "ProgramFiles(x86)", "LocalAppData")]
    candidates = [
        Path(root) / sub
        for root in roots
        if root
        for sub in (
            "Microsoft/Edge/Application/msedge.exe",
            "Google/Chrome/Application/chrome.exe",
        )
    ]
    candidates += [
        Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
    ]
    candidates += sorted(Path("/opt/pw-browsers").glob("chromium-*/chrome-linux*/chrome"))
    candidates += sorted(Path("/opt/pw-browsers").glob("chromium_headless_shell-*/chrome-linux*/headless_shell"))
    return next((str(c) for c in candidates if c.exists()), None)


def print_pdf(html_path: Path, pdf_path: Path) -> None:
    browser = find_browser()
    if not browser:
        raise ThesisError(
            [
                "no Chromium-based browser found to print the PDF (Edge, Chrome or Chromium). "
                "Open the .html in a browser and print it to PDF, or set PFE_DRAI_BROWSER to the browser's path."
            ]
        )

    def attempt(sandbox: bool) -> None:
        with tempfile.TemporaryDirectory() as profile:
            cmd = [
                browser,
                "--headless=new",
                "--disable-gpu",
                "--no-pdf-header-footer",
                f"--user-data-dir={profile}",
                f"--print-to-pdf={pdf_path}",
                html_path.resolve().as_uri(),
            ]
            if not sandbox:  # a container's root, or a runner without user namespaces, cannot sandbox; the page is our own file
                cmd.insert(1, "--no-sandbox")
            try:
                subprocess.run(cmd, check=False, capture_output=True, timeout=180)
            except subprocess.TimeoutExpired as exc:
                raise ThesisError([f"the browser did not finish printing the PDF within 3 minutes ({browser})"]) from exc

    pdf_path.unlink(missing_ok=True)
    attempt(sandbox=not (hasattr(os, "geteuid") and os.geteuid() == 0))
    if not pdf_path.exists():
        attempt(sandbox=False)
    if not pdf_path.exists() or pdf_path.stat().st_size < 1000:
        raise ThesisError([f"the browser ({browser}) did not produce a PDF; print the .html to PDF by hand instead"])


# ---------------------------------------------------------------- entry points
def build(
    root: Path | None = None,
    lang: str = "fr",
    formats: tuple[str, ...] = ("html",),
    out: Path | str = "thesis",
    settings: dict | None = None,
    records_dir: Path | None = None,
) -> tuple[dict[str, Path], list[str]]:
    """Build the report for one language. Returns ({format: path}, warnings). Raises ThesisError listing every problem."""
    src = load_sources(root, settings, records_dir)
    manifest = load_manifest(src)
    out = Path(out) / lang
    out.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    problems: list[str] = []
    figures: dict[str, str] = {}
    todo = 0
    if "md" in formats:
        text, r = compile_markdown(src, manifest, lang, "md")
        problems += r.problems
        figures.update(r.figures)
        todo = r.references_todo
        if not r.problems:
            (out / "thesis.md").write_text(text + "\n", encoding="utf-8")
            written["md"] = out / "thesis.md"
    if "html" in formats or "pdf" in formats:
        text, r = compile_html(src, manifest, lang)
        problems += [p for p in r.problems if p not in problems]
        figures.update(r.figures)
        todo = r.references_todo or todo
        if not r.problems:
            (out / "thesis.html").write_text(text, encoding="utf-8")
            written["html"] = out / "thesis.html"
    if problems:
        raise ThesisError(problems)
    if figures and "md" in written:
        (out / "figures").mkdir(exist_ok=True)
        for name, svg in figures.items():
            (out / "figures" / name).write_text(svg, encoding="utf-8")
    if "pdf" in formats:
        print_pdf(written["html"], out / "thesis.pdf")
        written["pdf"] = out / "thesis.pdf"
        if "html" not in formats:
            written.pop("html")
    warnings = (
        [f"references.md still has {todo} TODO marker(s): the bibliography is for the owner to verify and complete"]
        if todo
        else []
    )
    return written, warnings


def check(root: Path | None = None, settings: dict | None = None, records_dir: Path | None = None) -> Report:
    """Dry-run both languages, then compare the docs' printed results with the backtest records."""
    src = load_sources(root, settings, records_dir)
    manifest = load_manifest(src)
    report = Report()
    for lang in LANGS:
        try:
            for target in ("md", "html"):
                _, r = compile_markdown(src, manifest, lang, target)
                report.problems += [f"[{lang}/{target}] {p}" for p in r.problems]
                if r.references_todo and target == "md":
                    report.warnings.append(
                        f"[{lang}] references.md still has {r.references_todo} TODO marker(s): the bibliography is for the owner to verify and complete"
                    )
        except ThesisError as exc:
            report.problems += [f"[{lang}] {p}" for p in exc.problems]
    # The two languages must ask for the same numbers, tables and figures.
    for ch in manifest["chapters"]:
        a, b = (tokens_of((src.thesis_dir / f"{ch['file']}.{lang}.md").read_text(encoding="utf-8")) for lang in LANGS)
        if sorted(a) != sorted(b):
            diff = sorted(set(a) ^ set(b))
            report.problems.append(f"chapter '{ch['id']}': fr and en use different placeholders: {', '.join(diff[:4])}")
    sub = run_checks(src, manifest.get("checks", []))
    report.ok += sub.ok
    report.problems += sub.problems
    return report


def main_check(args) -> None:
    report = check(records_dir=Path(args.records) if args.records else None)
    for line in report.ok:
        print(f"ok    {line}")
    for line in report.warnings:
        print(f"warn  {line}")
    for line in report.problems:
        print(f"FAIL  {line}")
    print(f"\n{len(report.ok)} agreement(s), {len(report.problems)} problem(s), {len(report.warnings)} warning(s)")
    if not report.passed:
        sys.exit(1)
