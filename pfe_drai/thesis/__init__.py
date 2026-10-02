"""The thesis report: a methods and results document assembled by a command from docs/ and the records.

Chapters are Markdown files in docs/thesis/ (French and English). Numbers are placeholders resolved from
the backtest records, the settings and the live record, so prose cannot drift from data; results written
only in the pre-registration docs are quoted verbatim by section; `check` compares the two.
Nothing here touches the model, the settings or the track record, and nothing needs a network or a key.
"""

from .build import ThesisError, build, check

__all__ = ["ThesisError", "build", "check"]
