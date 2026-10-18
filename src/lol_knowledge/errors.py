"""Typed errors shared by the LoL-Knowledge tooling."""

from __future__ import annotations


class LolKnowledgeError(Exception):
    """Base class for every error raised by this project."""


class NetworkError(LolKnowledgeError):
    """The source could not be reached or timed out."""


class HttpStatusError(NetworkError):
    """The source answered with a non-success HTTP status."""

    def __init__(self, status: int, url: str) -> None:
        super().__init__(f"HTTP {status} for {url}")
        self.status = status
        self.url = url


class PatchNotAvailable(LolKnowledgeError):
    """The requested patch is not published by the source."""


class PayloadError(LolKnowledgeError):
    """Downloaded data is malformed, incomplete or out of the expected ranges."""


class SnapshotError(LolKnowledgeError):
    """The snapshot could not be written or replaced safely."""
