"""Hash-based content library."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from storage import (
    LIBRARY_FILE,
    StorageError,
    load_library,
    record_hash,
    save_library,
    sha256_file,
)


class ContentLibrary:
    """Track accepted media by SHA256 hash."""

    def __init__(self, path: Path = LIBRARY_FILE) -> None:
        self.path = path

    def contains_hash(self, sha256: str) -> bool:
        """Return whether a hash is already registered."""
        return sha256 in load_library(self.path)["hashes"]

    def find_by_hash(self, sha256: str) -> dict[str, Any] | None:
        """Return the library entry for a hash, if present."""
        return load_library(self.path)["hashes"].get(sha256)

    def add_file(
        self,
        path: Path,
        task_id: str,
        source: str,
        sha256: str | None = None,
    ) -> dict[str, Any]:
        """Add a validated media file and reject duplicate content."""
        digest = sha256 or sha256_file(path)
        return record_hash(digest, task_id, source, path, self.path)

    def all_entries(self) -> dict[str, Any]:
        """Return all registered hash entries."""
        return load_library(self.path)["hashes"]

    def find_by_source(self, source_url: str) -> dict[str, Any] | None:
        """Return the library entry for a source URL, if it was processed.

        This lets a run skip a video that was already downloaded and
        processed, so the same video is never downloaded and posted twice.
        """
        wanted = str(source_url or "").strip()
        if not wanted:
            return None
        for entry in load_library(self.path)["hashes"].values():
            if str(entry.get("source", "")).strip() == wanted:
                return entry
        return None

    def contains_source(self, source_url: str) -> bool:
        """Return whether the source URL was already processed."""
        return self.find_by_source(source_url) is not None

    def save(self, data: dict[str, Any]) -> None:
        """Persist library data."""
        save_library(data, self.path)


__all__ = ["ContentLibrary", "StorageError"]
