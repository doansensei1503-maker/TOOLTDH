"""P5 durable publishing history for Phase 1."""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

HISTORY_JSON = Path("data") / "history.json"
HISTORY_MARKDOWN = Path("data") / "history.md"
MAX_PUBLISH_RETRIES = 3


class HistoryError(RuntimeError):
    """Raised when history cannot be persisted safely."""


@dataclass
class HistoryEntry:
    """One auditable publishing outcome."""

    date: str
    platform: str
    source_url: str
    posted_url: str
    caption: str
    status: str
    task_id: str = ""
    reason: str = ""
    retry_count: int = 0
    state_path: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the entry."""
        return asdict(self)


class PublishHistory:
    """Append-only JSON and Markdown publishing history."""

    def __init__(
        self,
        json_path: Path = HISTORY_JSON,
        markdown_path: Path = HISTORY_MARKDOWN,
    ) -> None:
        self.json_path = json_path
        self.markdown_path = markdown_path

    def load(self) -> list[dict[str, Any]]:
        """Load history entries."""
        if not self.json_path.exists():
            return []
        try:
            with self.json_path.open("r", encoding="utf-8") as history_file:
                entries = json.load(history_file)
        except (OSError, json.JSONDecodeError) as exc:
            raise HistoryError(f"Unable to read publishing history: {exc}") from exc
        if not isinstance(entries, list):
            raise HistoryError("Publishing history has an invalid structure")
        return entries

    def add(self, entry: HistoryEntry) -> dict[str, Any]:
        """Append an entry and rebuild the Markdown history."""
        entries = self.load()
        payload = entry.to_dict()
        entries.append(payload)
        self.save_json(entries)
        self.save_markdown(entries)
        return payload

    def save_json(self, entries: list[dict[str, Any]]) -> None:
        """Persist JSON history atomically."""
        self.json_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.json_path.with_suffix(self.json_path.suffix + ".tmp")
        with temporary_path.open("w", encoding="utf-8") as history_file:
            json.dump(entries, history_file, indent=2, sort_keys=True)
            history_file.write("\n")
        os.replace(temporary_path, self.json_path)

    def save_markdown(self, entries: list[dict[str, Any]]) -> None:
        """Write human-readable Markdown history."""
        self.markdown_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# Publish History",
            "",
            "| Date | Platform | Source URL | Posted URL | Caption | Status |",
            "|---|---|---|---|---|---|",
        ]
        for entry in entries:
            fields = [
                entry.get("date", ""),
                entry.get("platform", ""),
                entry.get("source_url", ""),
                entry.get("posted_url", ""),
                entry.get("caption", ""),
                entry.get("status", ""),
            ]
            escaped = [str(field).replace("|", "\\|").replace("\n", " ") for field in fields]
            lines.append("| " + " | ".join(escaped) + " |")
        temporary_path = self.markdown_path.with_suffix(self.markdown_path.suffix + ".tmp")
        temporary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.replace(temporary_path, self.markdown_path)

    def record_publish(
        self,
        task_id: str,
        platform: str,
        source_url: str,
        posted_url: str,
        caption: str,
        status: str = "PUBLISHED",
        reason: str = "",
        retry_count: int = 0,
        state_path: str = "",
        metadata: dict[str, Any] | None = None,
        date: str | None = None,
    ) -> dict[str, Any]:
        """Record a publishing outcome with all required history fields."""
        if not posted_url.strip() and status == "PUBLISHED":
            raise HistoryError("A verified published URL is required for PUBLISHED history")
        return self.add(
            HistoryEntry(
                date=date or datetime.now().isoformat(),
                platform=platform,
                source_url=source_url,
                posted_url=posted_url,
                caption=caption,
                status=status,
                task_id=task_id,
                reason=reason,
                retry_count=retry_count,
                state_path=state_path,
                metadata=metadata or {},
            )
        )

    def record_blocked(
        self,
        task_id: str,
        platform: str,
        source_url: str,
        caption: str,
        reason: str,
        retry_count: int,
        state_path: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Record a blocked task for recovery."""
        return self.record_publish(
            task_id=task_id,
            platform=platform,
            source_url=source_url,
            posted_url="",
            caption=caption,
            status="BLOCKED",
            reason=reason,
            retry_count=retry_count,
            state_path=state_path,
            metadata=metadata,
        )


def retry_publish(
    publish: Callable[[], str],
    *,
    max_retries: int = MAX_PUBLISH_RETRIES,
    backoff_seconds: float = 1.0,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[str | None, int, str | None]:
    """Retry publishing up to three times, returning URL, retries, and error."""
    if max_retries < 0 or max_retries > MAX_PUBLISH_RETRIES:
        raise HistoryError(f"max_retries must be between 0 and {MAX_PUBLISH_RETRIES}")
    retries = 0
    last_error: str | None = None
    while retries <= max_retries:
        try:
            posted_url = publish()
            if not posted_url or not posted_url.strip():
                raise HistoryError("Publish attempt did not return a verified URL")
            return posted_url, retries, None
        except Exception as exc:
            last_error = str(exc)
            if retries >= max_retries:
                break
            retries += 1
            sleep(backoff_seconds * (2 ** (retries - 1)))
    return None, retries, last_error


__all__ = [
    "HISTORY_JSON",
    "HISTORY_MARKDOWN",
    "HistoryEntry",
    "HistoryError",
    "MAX_PUBLISH_RETRIES",
    "PublishHistory",
    "retry_publish",
]
