"""Number formatting for placeholders, and a small Markdown to HTML converter.

The converter covers the Markdown the chapters and the quoted docs use (headings, paragraphs, lists,
pipe tables, fenced code, quotes, emphasis, code spans, links) and nothing else, so the report needs
no Markdown library. Everything is escaped; raw HTML only enters through blocks the builder made.
"""

import html
import re
import unicodedata

from ..i18n import fmt_date

MINUS = "−"
RAW_LINE = re.compile(r"@@RAW:(\d+)@@")


# ---------------------------------------------------------------- numbers
def _fixed(value: float, digits: int, lang: str, signed: bool = False) -> str:
    text = f"{abs(value):.{digits}f}"
    if lang == "fr":
        text = text.replace(".", ",")
    negative = round(value, digits) < 0
    sign = MINUS if negative else ("+" if signed and round(value, digits) > 0 else "")
    return sign + text


def format_value(value, fmt: str | None, lang: str) -> str:
    """Format a resolved placeholder. Floats need an explicit format: no silent precision."""
    if value is None:
        raise ValueError("the value is null")
    if isinstance(value, bool):
        if fmt != "yesno":
            raise ValueError("a yes/no value needs the format |yesno")
        return ("oui" if value else "non") if lang == "fr" else ("yes" if value else "no")
    if isinstance(value, str):
        if fmt == "date":
            return fmt_date(value, lang)
        if fmt:
            raise ValueError(f"format '{fmt}' does not apply to text")
        return value
    if fmt is None:
        if isinstance(value, int):
            return _fixed(value, 0, lang)
        raise ValueError("a decimal number needs a format (|0 to |4 decimals, |pct1, |signed)")
    m = re.fullmatch(r"(pct|signed)?(\d?)", fmt)
    if not m or not (m.group(1) or m.group(2)):
        raise ValueError(f"unknown format '{fmt}'")
    kind, digits = m.group(1), m.group(2)
    if kind == "pct":
        text = _fixed(value * 100, int(digits or 0), lang)
        return f"{text} %" if lang == "fr" else f"{text}%"
    return _fixed(value, int(digits or 0), lang, signed=kind == "signed")


# ---------------------------------------------------------------- inline
def slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "section"


_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITALIC = re.compile(r"(?<![\w*])\*(?![\s*])(.+?)(?<![\s*])\*(?![\w*])")


def inline(text: str) -> str:
    codes: list[str] = []

    def keep(m):
        codes.append(f"<code>{html.escape(m.group(1), quote=False)}</code>")
        return f"\x00{len(codes) - 1}\x00"

    text = re.sub(r"`([^`]+)`", keep, text)
    text = html.escape(text, quote=False)

    def link(m):
        url = html.unescape(m.group(2))
        if not re.match(r"(https?://|#|[\w./-]+$)", url):  # no javascript:, data: ...
            return m.group(1)
        return f'<a href="{html.escape(url)}">{m.group(1)}</a>'

    text = _LINK.sub(link, text)
    text = _BOLD.sub(r"<strong>\1</strong>", text)
    text = _ITALIC.sub(r"<em>\1</em>", text)
    return re.sub(r"\x00(\d+)\x00", lambda m: codes[int(m.group(1))], text)


# ---------------------------------------------------------------- blocks
_HEADING = re.compile(r"(#{1,6})\s+(.*?)\s*#*\s*$")
_ITEM = re.compile(r"(\s*)([-*]|\d+\.)\s+(.*)")
_SEPARATOR = re.compile(r"\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


def split_row(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|") and not line.endswith("\\|"):
        line = line[:-1]
    cells, cur, in_code = [], "", False
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == "\\" and i + 1 < len(line) and line[i + 1] == "|":
            cur += "|"
            i += 2
            continue
        if ch == "`":
            in_code = not in_code
        if ch == "|" and not in_code:
            cells.append(cur.strip())
            cur = ""
        else:
            cur += ch
        i += 1
    cells.append(cur.strip())
    return cells


def _is_table_start(lines: list[str], i: int) -> bool:
    return lines[i].lstrip().startswith("|") and i + 1 < len(lines) and bool(_SEPARATOR.match(lines[i + 1].strip()))


def _starts_block(lines: list[str], i: int) -> bool:
    line = lines[i]
    s = line.lstrip()
    return (
        not s
        or line.startswith("```")
        or bool(_HEADING.match(line))
        or s.startswith(">")
        or bool(_ITEM.match(line))
        or _is_table_start(lines, i)
        or bool(RAW_LINE.fullmatch(s))
    )


def _list(lines: list[str], i: int) -> tuple[str, int]:
    items: list[list] = []  # [indent, ordered, text]
    while i < len(lines):
        m = _ITEM.match(lines[i])
        if m:
            items.append([len(m.group(1)), m.group(2)[0].isdigit(), m.group(3).strip()])
            i += 1
        elif lines[i].strip() and lines[i].startswith(" ") and items and not _starts_block(lines, i):
            items[-1][2] += " " + lines[i].strip()
            i += 1
        else:
            break
    out: list[str] = []
    stack: list[tuple[int, str]] = []  # (indent, tag)
    for indent, ordered, text in items:
        tag = "ol" if ordered else "ul"
        while stack and indent < stack[-1][0]:
            out.append(f"</li></{stack.pop()[1]}>")
        if stack and indent == stack[-1][0]:
            out.append("</li>")
        elif not stack or indent > stack[-1][0]:
            out.append(f"<{tag}>")
            stack.append((indent, tag))
        out.append(f"<li>{inline(text)}")
    while stack:
        out.append(f"</li></{stack.pop()[1]}>")
    return "".join(out), i


def _table(lines: list[str], i: int) -> tuple[str, int]:
    head = split_row(lines[i])
    aligns = []
    for cell in split_row(lines[i + 1]):
        aligns.append(
            "right"
            if cell.endswith(":") and not cell.startswith(":")
            else "center"
            if cell.startswith(":") and cell.endswith(":")
            else ""
        )
    i += 2
    rows = []
    while i < len(lines) and lines[i].lstrip().startswith("|"):
        rows.append(split_row(lines[i]))
        i += 1

    def cell(tag: str, text: str, k: int) -> str:
        a = aligns[k] if k < len(aligns) and aligns[k] else ""
        classes = ([a[0]] if a else []) + (["nw"] if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text) else [])
        attr = f' class="{" ".join(classes)}"' if classes else ""
        return f"<{tag}{attr}>{inline(text)}</{tag}>"

    thead = "<tr>" + "".join(cell("th", c, k) for k, c in enumerate(head)) + "</tr>"
    body = "".join("<tr>" + "".join(cell("td", c, k) for k, c in enumerate(r)) + "</tr>" for r in rows)
    return f'<div class="table-wrap"><table><thead>{thead}</thead><tbody>{body}</tbody></table></div>', i


def to_html(md: str, raws: dict[int, str] | None = None) -> str:
    """Markdown to HTML. `@@RAW:n@@` on a line of its own is replaced by raws[n] (HTML made by the builder)."""
    raws = raws or {}
    lines = md.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    ids: dict[str, int] = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        s = line.strip()
        if not s:
            i += 1
        elif RAW_LINE.fullmatch(s):
            out.append(raws[int(RAW_LINE.fullmatch(s).group(1))])
            i += 1
        elif line.startswith("```"):
            i += 1
            code = []
            while i < len(lines) and not lines[i].startswith("```"):
                code.append(lines[i])
                i += 1
            i += 1
            out.append(f"<pre><code>{html.escape(chr(10).join(code), quote=False)}</code></pre>")
        elif _HEADING.match(line):
            m = _HEADING.match(line)
            level, text = len(m.group(1)), m.group(2)
            base = slug(re.sub(r"[`*]", "", text))
            ids[base] = ids.get(base, 0) + 1
            hid = base if ids[base] == 1 else f"{base}-{ids[base]}"
            out.append(f'<h{level} id="{hid}">{inline(text)}</h{level}>')
            i += 1
        elif s.startswith(">"):
            block = []
            while i < len(lines) and lines[i].lstrip().startswith(">"):
                block.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            out.append(f"<blockquote>{to_html(chr(10).join(block), raws)}</blockquote>")
        elif _is_table_start(lines, i):
            block, i = _table(lines, i)
            out.append(block)
        elif _ITEM.match(line):
            block, i = _list(lines, i)
            out.append(block)
        else:
            para = [s]
            i += 1
            while i < len(lines) and not _starts_block(lines, i):
                para.append(lines[i].strip())
                i += 1
            out.append(f"<p>{inline(' '.join(para))}</p>")
    return "\n".join(out)


def headings(md: str) -> list[tuple[int, str]]:
    """(level, text) of every heading outside code fences."""
    found, fenced = [], False
    for line in md.split("\n"):
        if line.startswith("```"):
            fenced = not fenced
        elif not fenced and (m := _HEADING.match(line)):
            found.append((len(m.group(1)), m.group(2)))
    return found
