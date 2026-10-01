"""Daily publication of the regime to track_record/, with an external timestamp (OpenTimestamps)."""

from .snapshot import NotLiveDataError, publish

__all__ = ["NotLiveDataError", "publish"]
