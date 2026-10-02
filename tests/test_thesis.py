"""The thesis report: placeholders, quotes, the consistency check, the generated blocks and the builds.

Fixtures (tests/fixtures/thesis) are a small repository of their own: one fixture doc, a synthetic backtest
record and two chapters. The last tests build the real report from the committed docs and records.
"""

import json
import shutil
from pathlib import Path

import pytest

from pfe_drai.config import ROOT, load_settings
from pfe_drai.publish.snapshot import config_fingerprint
from pfe_drai.thesis import ThesisError, build, check
from pfe_drai.thesis.blocks import extract_section
from pfe_drai.thesis.build import (
    LANGS,
    compile_markdown,
    find_browser,
    load_manifest,
    tokens_of,
    validate_manifest,
)
from pfe_drai.thesis.check import agrees, parse_numbers, read_table
from pfe_drai.thesis.markup import format_value, to_html
from pfe_drai.thesis.sources import load_sources

FIXTURE = Path(__file__).parent / "fixtures" / "thesis"


@pytest.fixture
def repo(tmp_path):
    """A writable copy of the fixture repository."""
    dest = tmp_path / "repo"
    shutil.copytree(FIXTURE, dest)
    return dest


def record_path(root: Path) -> Path:
    return next((root / "track_record" / "backtest").glob("*.json"))


# ---------------------------------------------------------------- numbers and placeholders
def test_values_are_formatted_for_each_language():
    assert format_value(1.14321, "2", "en") == "1.14"
    assert format_value(1.14321, "2", "fr") == "1,14"
    assert format_value(-3.0, "0", "en") == "−3"  # a true minus sign, as the docs print it
    assert format_value(0.0521, "pct1", "en") == "5.2%"
    assert format_value(0.0521, "pct1", "fr") == "5,2 %"
    assert format_value(3, None, "fr") == "3"
    assert format_value(3, "signed", "en") == "+3" and format_value(-0.5, "signed1", "en") == "\u22120.5"
    assert format_value("2026-10-01", "date", "fr") == "01/10/2026"
    assert format_value(True, "yesno", "fr") == "oui"


def test_a_decimal_number_without_a_format_is_an_error():
    with pytest.raises(ValueError, match="needs a format"):
        format_value(0.5, None, "en")
    with pytest.raises(ValueError, match="null"):
        format_value(None, "2", "en")


def test_the_build_resolves_placeholders_from_the_record(repo):
    written, _ = build(repo, lang="en", formats=("md",), out=repo / "out")
    text = written["md"].read_text(encoding="utf-8")
    assert "Detected 2 of 3, delay −2, Brier 0.123." in text
    assert "{{" not in text
    assert "| Current settings have this fingerprint | `" not in text or "`oui`" not in text  # no French in English


def test_changing_a_metric_in_the_record_changes_the_output(repo):
    path = record_path(repo)
    record = json.loads(path.read_text())
    record["metrics"]["brier"] = 0.2222
    path.write_text(json.dumps(record))
    written, _ = build(repo, lang="en", formats=("md",), out=repo / "out")
    assert "Brier 0.222." in written["md"].read_text(encoding="utf-8")


def test_an_unresolved_placeholder_fails_the_build_and_lists_every_one(repo):
    chapter = repo / "docs" / "thesis" / "01-one.en.md"
    chapter.write_text(
        chapter.read_text() + "\n{{backtest.current.metrics.nothing|2}} and {{table:unknown}} and {{config.no.such}}\n"
    )
    with pytest.raises(ThesisError) as exc:
        build(repo, lang="en", formats=("md",), out=repo / "out")
    assert len(exc.value.problems) == 3
    assert not (repo / "out" / "en" / "thesis.md").exists()


def test_a_chapter_that_quotes_an_undeclared_doc_fails(repo):
    manifest = repo / "docs" / "thesis" / "manifest.yaml"
    manifest.write_text(manifest.read_text().replace("sources: [FIXTURE.md]", "sources: []"))
    with pytest.raises(ThesisError, match="does not list it under 'sources'"):
        build(repo, lang="en", formats=("md",), out=repo / "out")


def test_a_chapter_title_must_match_the_manifest(repo):
    chapter = repo / "docs" / "thesis" / "01-one.fr.md"
    chapter.write_text(chapter.read_text().replace("# Un", "# Autre", 1))
    problems = validate_manifest(load_sources(repo), load_manifest(load_sources(repo)))
    assert any("first line must be" in p for p in problems)


# ---------------------------------------------------------------- quotes
DOC = """# Title

## Results

### Run one (fixture)

Body of one.

| a | b |
|---|---|
| 1 | 2 |

#### Inner

Inner text.

### Run two

Body of two.

## Other

Elsewhere.
"""


def test_extract_section_returns_the_body_up_to_the_next_heading_of_the_same_level():
    body = extract_section(DOC, "Results > Run one")
    assert body.startswith("Body of one.")
    assert "Inner text." in body and "Body of two." not in body
    assert extract_section(DOC, "Other") == "Elsewhere."


def test_extract_section_needs_exactly_one_match():
    with pytest.raises(KeyError, match="not found"):
        extract_section(DOC, "Results > Run three")
    with pytest.raises(KeyError, match="ambiguous"):
        extract_section(DOC, "Results > Run")


def test_a_quote_is_verbatim_and_carries_its_source(repo):
    written, _ = build(repo, lang="en", formats=("md",), out=repo / "out")
    text = written["md"].read_text(encoding="utf-8")
    assert "**Verbatim quote** from `docs/FIXTURE.md`" in text
    assert "> | **v-test** | 2/3 | −2.0 | 0.123 |" in text
    assert "Other results." not in text  # the next section is not quoted
    assert "Closing words." in text


def test_quoted_docs_are_never_modified(repo):
    before = (repo / "docs" / "FIXTURE.md").read_bytes()
    build(repo, lang="fr", formats=("md", "html"), out=repo / "out")
    assert (repo / "docs" / "FIXTURE.md").read_bytes() == before


# ---------------------------------------------------------------- consistency check
def test_check_passes_on_the_fixture(repo):
    report = check(repo)
    assert report.passed, report.problems
    assert any("episode" in line or "2020-01-10" in line for line in report.ok)


def test_check_lists_a_deliberately_wrong_number(repo):
    doc = repo / "docs" / "FIXTURE.md"
    doc.write_text(doc.read_text().replace("| 0.123 |", "| 0.321 |", 1).replace("| −4 |", "| −5 |"))
    report = check(repo)
    assert not report.passed
    text = "\n".join(report.problems)
    assert "doc prints 0.321" in text and "metrics.brier" in text
    assert "2020-01-10" in text and "'−5'" in text


def test_check_fails_when_the_record_is_regenerated_with_other_numbers(repo):
    path = record_path(repo)
    record = json.loads(path.read_text())
    record["metrics"]["detected"] = 3
    path.write_text(json.dumps(record))
    assert any("metrics.detected" in p for p in check(repo).problems)


def test_a_check_that_cannot_run_is_a_failure(repo):
    manifest = repo / "docs" / "thesis" / "manifest.yaml"
    manifest.write_text(manifest.read_text().replace("version: v-test\n    column: Brier", "version: v9\n    column: Brier"))
    assert any("no backtest record for version" in p for p in check(repo).problems)


def test_check_compares_to_the_printed_precision():
    assert agrees(0.090, 3, False, 0.0899)
    assert agrees(5.2, 1, True, 0.0521)
    assert not agrees(0.091, 3, False, 0.0899)
    assert [n[0] for n in parse_numbers("**11/11**, −3")] == [11, 11, -3]
    assert parse_numbers("missed") == []
    head, rows = read_table("text\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n| c |\n|---|\n| 3 |\n", 1)
    assert head == ["c"] and rows == [["3"]]


# ---------------------------------------------------------------- generated blocks
def test_tables_and_figures_come_from_the_record(repo):
    written, _ = build(repo, lang="en", formats=("md",), out=repo / "out")
    text = written["md"].read_text(encoding="utf-8")
    assert "| 2020-01-10 | 2020-02-01 | drawdown | −12.3% | 2020-01-06 | −4 |" in text
    assert "| 2020-03-10 | 2020-03-25 | drawdown | −20.0% | – | missed |" in text
    assert "![" in text and "(figures/latency.svg)" in text
    svg = (repo / "out" / "en" / "figures" / "latency.svg").read_text(encoding="utf-8")
    assert svg.startswith("<svg xmlns=") and "var(--" not in svg  # a file of its own: no CSS variables left


def test_french_and_english_have_the_same_blocks(repo):
    en, _ = compile_markdown(load_sources(repo), load_manifest(load_sources(repo)), "en", "md")
    fr, _ = compile_markdown(load_sources(repo), load_manifest(load_sources(repo)), "fr", "md")
    assert en.count("| ---") == fr.count("| ---") and en.count("![") == fr.count("![")
    assert "Tableau 1." in fr and "Table 1." in en


def test_html_is_one_self_contained_file_without_prices_or_secrets(repo, monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "SECRET-FRED-123")
    monkeypatch.setenv("TIINGO_API_KEY", "SECRET-TIINGO-456")
    written, _ = build(repo, lang="en", formats=("html",), out=repo / "out")
    page = written["html"].read_text(encoding="utf-8")
    assert "<script" not in page and 'src="http' not in page and "<link" not in page
    assert "SECRET-" not in page
    assert "<h2" in page and "<svg" in page and "<table" in page
    assert "<blockquote>" in page


def test_references_with_todo_warn(repo):
    _, warnings = build(repo, lang="en", formats=("md",), out=repo / "out")
    assert any("TODO" in w for w in warnings)
    assert any("TODO" in w for w in check(repo).warnings)


# ---------------------------------------------------------------- markdown converter
def test_markup_converts_the_markdown_the_docs_use():
    html = to_html(
        "# T\n\nA **b** and `c|d` and *e*.\n\n- one\n  - nested\n- two\n\n1. x\n2. y\n\n| a | b |\n|---|---:|\n| 1 | 2 |\n"
    )
    assert '<h1 id="t">T</h1>' in html and "<strong>b</strong>" in html and "<code>c|d</code>" in html
    assert "<em>e</em>" in html and "<ul><li>one<ul><li>nested</li></ul></li><li>two</li></ul>" in html
    assert "<ol><li>x</li><li>y</li></ol>" in html
    assert '<th class="r">b</th>' in html and '<td class="r">2</td>' in html


def test_markup_escapes_everything_and_blocks_unsafe_links():
    html = to_html("<script>alert(1)</script> [x](javascript:alert(1)) [ok](https://example.org)\n\n```\n<b>code</b>\n```\n")
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "javascript:" not in html and '<a href="https://example.org">ok</a>' in html
    assert "&lt;b&gt;code&lt;/b&gt;" in html


# ---------------------------------------------------------------- the real report
def test_manifest_has_the_same_chapters_in_both_languages():
    src = load_sources()
    manifest = load_manifest(src)
    assert validate_manifest(src, manifest) == []
    for ch in manifest["chapters"]:
        a, b = (tokens_of((src.thesis_dir / f"{ch['file']}.{lang}.md").read_text(encoding="utf-8")) for lang in LANGS)
        assert sorted(a) == sorted(b), ch["id"]


def test_the_check_passes_on_the_real_repository():
    report = check()
    assert report.passed, "\n".join(report.problems)
    assert len(report.ok) >= 19  # 8 table cells of docs/SLOWDOWN.md and 11 episodes of docs/DETECTION_V2.md


def test_the_real_report_builds_with_no_network_and_no_key(tmp_path, monkeypatch):
    for key in ("FRED_API_KEY", "TIINGO_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    for lang in LANGS:
        written, _ = build(lang=lang, formats=("md", "html"), out=tmp_path)
        page = written["html"].read_text(encoding="utf-8")
        assert page.count("<h2") == len(load_manifest(load_sources())["chapters"]) and "{{" not in page
        assert "<script" not in page
    fr = (tmp_path / "fr" / "thesis.md").read_text(encoding="utf-8")
    en = (tmp_path / "en" / "thesis.md").read_text(encoding="utf-8")
    assert fr.count("\n## ") == en.count("\n## ")
    assert fr.count("Tableau ") >= 1 and en.count("Table ") >= 1


def test_the_report_leaves_the_model_and_the_record_alone():
    settings = load_settings()
    version = settings["models"]["version"]
    records = [json.loads(p.read_text(encoding="utf-8")) for p in (ROOT / "track_record" / "backtest").glob("*.json")]
    current = [r for r in records if r.get("model_version") == version]
    if not current:
        pytest.skip(f"no backtest record for {version} yet: the daily job writes it on its next run")
    assert config_fingerprint(settings) == current[-1]["config_sha256"]  # the daily job's fingerprint did not move


@pytest.mark.skipif(find_browser() is None, reason="needs Edge, Chrome or Chromium to print a PDF")
def test_pdf_is_printed_from_the_html(repo):
    written, _ = build(repo, lang="fr", formats=("pdf",), out=repo / "out")
    pdf = written["pdf"].read_bytes()
    assert pdf.startswith(b"%PDF") and len(pdf) > 5000
