"""Consistency check: a number printed in a doc's Results must agree with the backtest record of the same version.

The docs are history (nothing above "Results" is ever edited) and the record is data. This reads the
tables the docs print and compares them with the record, to the precision the doc printed. A doc that
drifts from the record, or a record regenerated with other numbers, is listed here instead of going unnoticed.
Checks are declared in docs/thesis/manifest.yaml (`checks:`); a declared check that cannot run is a failure.
"""

import re
from dataclasses import dataclass, field

from .blocks import _norm, extract_section
from .markup import MINUS, split_row
from .sources import Sources, version_key

_NUMBER = re.compile(r"[+−-]?\d+(?:\.\d+)?%?")


@dataclass
class Report:
    ok: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.problems


def parse_numbers(cell: str) -> list[tuple[float, int, bool]]:
    """(value, decimals printed, is percent) for each number in a table cell; 'missed' has none."""
    out = []
    for token in _NUMBER.findall(cell.replace("**", "")):
        pct = token.endswith("%")
        body = token.rstrip("%").replace(MINUS, "-")
        decimals = len(body.split(".")[1]) if "." in body else 0
        out.append((float(body), decimals, pct))
    return out


def agrees(printed: float, decimals: int, pct: bool, record_value: float) -> bool:
    """The record, shown to the doc's precision, equals what the doc printed (half a unit in the last place)."""
    value = record_value * 100 if pct else record_value
    return abs(value - printed) <= 0.5 * 10 ** (-decimals) + 1e-9


def read_table(section: str, index: int = 0) -> tuple[list[str], list[list[str]]]:
    """The `index`-th pipe table of a section (0 = the first): header cells and body rows."""
    lines = section.split("\n")
    seen = -1
    for i in range(len(lines) - 1):
        if lines[i].lstrip().startswith("|") and re.match(r"\|?\s*:?-{2,}", lines[i + 1].strip()):
            if i > 0 and lines[i - 1].lstrip().startswith("|"):
                continue  # inside a table already counted
            seen += 1
            if seen != index:
                continue
            head = [c.replace("**", "").strip() for c in split_row(lines[i])]
            rows = []
            for line in lines[i + 2 :]:
                if not line.lstrip().startswith("|"):
                    break
                rows.append(split_row(line))
            return head, rows
    raise ValueError(f"no table number {index + 1} in this section")


def _section(src: Sources, doc: str, path: str) -> str:
    return extract_section((src.docs_dir / doc).read_text(encoding="utf-8"), path)


def run_checks(src: Sources, checks: list[dict]) -> Report:
    report = Report()
    for spec in checks:
        cid = spec.get("id", spec.get("doc", "?"))
        try:
            rec = src.backtest(version_key(spec["version"]))
            body = _section(src, spec["doc"], spec["section"])
            head, rows = read_table(body, spec.get("table", 0))
        except (KeyError, ValueError, FileNotFoundError) as exc:
            report.problems.append(f"{cid}: cannot run: {exc.args[0] if exc.args else exc}")
            continue
        where = f"{spec['doc']} › {spec['section'].split(' > ')[-1]}"
        if "rows" in spec:
            _check_rows(src, report, spec, rec, head, rows, where)
        if "episodes" in spec:
            _check_episodes(report, spec, rec, head, rows, where)
    return report


def column_index(head: list[str], name: str) -> int:
    want = _norm(name)
    for i, h in enumerate(head):
        if _norm(h) == want:
            return i
    raise KeyError(f"no column '{name}' (columns: {', '.join(head)})")


def _check_rows(src: Sources, report: Report, spec: dict, rec: dict, head, rows, where: str) -> None:
    try:
        col = column_index(head, spec["column"])
    except KeyError as exc:
        report.problems.append(f"{spec.get('id')}: {exc.args[0]}")
        return
    for label, paths in spec["rows"].items():
        match = [r for r in rows if _norm(r[0]).startswith(_norm(label))]
        if len(match) != 1:
            report.problems.append(f"{where}: row '{label}' {'not found' if not match else 'ambiguous'}")
            continue
        numbers = parse_numbers(match[0][col])
        for n, path in enumerate(paths):
            if path is None:
                continue
            if n >= len(numbers):
                report.problems.append(f"{where}, '{label}': expected a number at position {n + 1} in '{match[0][col]}'")
                continue
            printed, decimals, pct = numbers[n]
            node = rec
            for token in path.split("."):
                node = node[token]
            if node is None or not agrees(printed, decimals, pct, node):
                shown = "null" if node is None else f"{node:.4f}".rstrip("0").rstrip(".")
                report.problems.append(
                    f"{where}, '{label}' ({spec['column']}): doc prints {printed:g}{'%' if pct else ''}, "
                    f"record {spec['version']} has {path} = {shown}"
                )
            else:
                report.ok.append(f"{where}, '{label}': {path} agrees ({printed:g}{'%' if pct else ''})")


def _check_episodes(report: Report, spec: dict, rec: dict, head, rows, where: str) -> None:
    cols = spec["episodes"]
    try:
        c_start, c_dd, c_lat = (column_index(head, cols[k]) for k in ("start", "drawdown", "latency"))
    except KeyError as exc:
        report.problems.append(f"{spec.get('id')}: {exc.args[0]}")
        return
    by_start = {e["start"]: e for e in rec["episodes"]}
    seen = set()
    for r in rows:
        start = r[c_start].strip()
        ep = by_start.get(start)
        if ep is None:
            report.problems.append(f"{where}: episode {start} is not in record {spec['version']}")
            continue
        seen.add(start)
        printed_lat = r[c_lat].replace("**", "").strip()
        lat = ep["latency_days"]
        if printed_lat.lower() == "missed" or lat is None:
            same = printed_lat.lower() == "missed" and lat is None
        else:
            nums = parse_numbers(printed_lat)
            same = bool(nums) and int(nums[0][0]) == lat
        dd = parse_numbers(r[c_dd])
        dd_ok = bool(dd) and agrees(dd[0][0], dd[0][1], dd[0][2], ep["max_drawdown"])
        if not same:
            report.problems.append(f"{where}, {start}: doc prints delay '{printed_lat}', record {spec['version']} has {lat}")
        if not dd_ok:
            report.problems.append(f"{where}, {start}: doc prints drawdown '{r[c_dd]}', record has {ep['max_drawdown']:.4f}")
        if same and dd_ok:
            report.ok.append(f"{where}, {start}: delay and drawdown agree")
    for start in sorted(set(by_start) - seen):
        report.problems.append(f"{where}: record {spec['version']} has episode {start} that the doc table lacks")
