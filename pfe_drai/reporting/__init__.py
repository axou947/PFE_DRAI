"""Reports: risk committee note (FR/EN) as Markdown, HTML or PDF."""

from .note import build_note, to_html, to_markdown, to_pdf

__all__ = ["build_note", "to_html", "to_markdown", "to_pdf"]
