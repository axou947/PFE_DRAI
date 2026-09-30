"""Daily publication of the regime to track_record/, with an external timestamp (OpenTimestamps)."""

from .snapshot import publish

__all__ = ["publish"]
