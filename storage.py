"""File storage helpers for ingested media."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

DATA_DIR = Path("data")
ORIGINALS_DIR = DATA_DIR / "originals"
PROCESSED_DIR = DATA_DIR / "processed"
TEMP_DIR = DATA_DIR / "temp"
LIBRARY_FILE = DATA_DIR / "library.json"
SCREENSHOTS_DIR = DATA_DIR / "screenshots"
TASK_STATES_DIR = DATA_DIR / "tasks"
# The record of what was published. It is the proof of what was posted,
# so the retention pass never touches it.
HISTORY_FILE = DATA_DIR / "history.json"

SUPPORTED_FORMATS = {".mp4", ".mov", ".webm"}
MAX_FILE_SIZE_BYTES = 4 * 1024 * 1024 * 1024
MAX_DURATION_SECONDS = 10 * 60


class StorageError(RuntimeError):
    """Raised when media cannot be safely stored."""


def ensure_directories() -> None:
    """Create the storage directory layout."""
    for directory in (ORIGINALS_DIR, PROCESSED_DIR, TEMP_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def load_library(path: Path = LIBRARY_FILE) -> dict[str, Any]:
    """Load the hash library, treating a missing file as empty."""
    if not path.exists():
        return {"hashes": {}}
    try:
        with path.open("r", encoding="utf-8") as library_file:
            data = json.load(library_file)
    except (OSError, json.JSONDecodeError) as exc:
        raise StorageError(f"Unable to read library file: {exc}") from exc
    if not isinstance(data.get("hashes"), dict):
        raise StorageError("Library file has an invalid hashes structure")
    return data


def save_library(data: dict[str, Any], path: Path = LIBRARY_FILE) -> None:
    """Atomically persist the hash library."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    with temporary_path.open("w", encoding="utf-8") as library_file:
        json.dump(data, library_file, indent=2, sort_keys=True)
        library_file.write("\n")
    os.replace(temporary_path, path)


def sha256_file(path: Path) -> str:
    """Calculate a file's SHA256 digest in chunks."""
    digest = hashlib.sha256()
    try:
        with path.open("rb") as media_file:
            for chunk in iter(lambda: media_file.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise StorageError(f"Unable to hash media file: {exc}") from exc
    return digest.hexdigest()


def validate_media_file(path: Path, duration_seconds: float | None = None) -> None:
    """Validate format, size, and optional duration before ingestion."""
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_FORMATS:
        allowed = ", ".join(sorted(SUPPORTED_FORMATS))
        raise StorageError(f"Unsupported video format '{suffix or 'unknown'}'; allowed formats: {allowed}")
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise StorageError(f"Unable to inspect media file: {exc}") from exc
    if size <= 0:
        raise StorageError("Video file is empty")
    if size > MAX_FILE_SIZE_BYTES:
        raise StorageError("Video exceeds the 4 GB size limit")
    if duration_seconds is not None and duration_seconds > MAX_DURATION_SECONDS:
        raise StorageError("Video exceeds the 10-minute TikTok duration limit")


def move_to_temp(source: Path, task_id: str, destination_dir: Path = TEMP_DIR) -> Path:
    """Copy an ingested file into the task-specific temp path."""
    if not task_id or any(character in task_id for character in "/\\"):
        raise StorageError("Invalid task_id")
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"{task_id}.mp4"
    try:
        if source.resolve() != destination.resolve():
            shutil.copy2(str(source), str(destination))
    except OSError as exc:
        raise StorageError(f"Unable to copy media into temp storage: {exc}") from exc
    return destination


def delete_temp_file(path: Path) -> bool:
    """Delete one temporary media file, never touching the originals directory."""
    try:
        resolved = path.resolve()
        originals = ORIGINALS_DIR.resolve()
        if resolved == originals or originals in resolved.parents:
            raise StorageError("Refusing to delete a file from data/originals/")
        if not path.exists():
            return False
        path.unlink()
        return True
    except OSError as exc:
        raise StorageError(f"Unable to delete temporary media file: {exc}") from exc


def cleanup_temp_directory(
    temp_dir: Path = TEMP_DIR,
    originals_dir: Path = ORIGINALS_DIR,
) -> list[Path]:
    """Remove temporary task artefacts while preserving originals and processed files."""
    temp_dir = Path(temp_dir)
    originals_dir = Path(originals_dir)
    if not temp_dir.exists():
        return []
    removed: list[Path] = []
    try:
        resolved_temp = temp_dir.resolve()
        resolved_originals = originals_dir.resolve()
        if resolved_temp == resolved_originals or resolved_originals in resolved_temp.parents:
            raise StorageError("Refusing to clean an originals directory as temp")
        for path in sorted(temp_dir.rglob("*"), reverse=True):
            if not path.is_file():
                continue
            resolved = path.resolve()
            if resolved == resolved_originals or resolved_originals in resolved.parents:
                continue
            path.unlink()
            removed.append(path)
    except OSError as exc:
        raise StorageError(f"Unable to clean temporary directory: {exc}") from exc
    return removed


def cleanup_screenshots(
    screenshots_dir: Path = SCREENSHOTS_DIR,
    keep_recent: int = 0,
) -> list[Path]:
    """Retain at most the configured number of recent error screenshots."""
    screenshots_dir = Path(screenshots_dir)
    if keep_recent < 0:
        raise StorageError("keep_recent cannot be negative")
    if not screenshots_dir.exists():
        return []
    screenshots = sorted(
        (path for path in screenshots_dir.iterdir() if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    removed: list[Path] = []
    try:
        for path in screenshots[keep_recent:]:
            path.unlink()
            removed.append(path)
    except OSError as exc:
        raise StorageError(f"Unable to clean error screenshots: {exc}") from exc
    return removed


def cleanup_task(
    temp_path: Path | None = None,
    *,
    temp_dir: Path = TEMP_DIR,
    originals_dir: Path = ORIGINALS_DIR,
    screenshots_dir: Path = SCREENSHOTS_DIR,
    keep_screenshots: int = 0,
    delete_media: bool = True,
) -> dict[str, list[Path]]:
    """Clean task temporary files and screenshots without deleting originals."""
    removed_temp: list[Path] = []
    if delete_media and temp_path is not None:
        if delete_temp_file(Path(temp_path)):
            removed_temp.append(Path(temp_path))
    removed_temp.extend(cleanup_temp_directory(temp_dir, originals_dir))
    removed_screenshots = cleanup_screenshots(screenshots_dir, keep_screenshots)
    return {
        "temp": removed_temp,
        "screenshots": removed_screenshots,
    }


# The number of days a published video and the files that belong to it are
# kept before the retention pass may remove them.
RETENTION_DAYS = 7


def _parse_published_at(value: Any) -> datetime | None:
    """Return the moment a post was published, when it can be read."""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def expired_published_tasks(
    now: datetime | None = None,
    *,
    history_path: Path = HISTORY_FILE,
    retention_days: int = RETENTION_DAYS,
) -> list[dict[str, Any]]:
    """Return the published tasks whose retention time has run out.

    The deadline is the moment the post was published plus the number of
    days that are kept. A task that was never published, or whose
    published moment cannot be read, is never expired: the machine does
    not guess a deadline it cannot know.

    Only the tasks that carry a real published moment and a real posted
    address are returned, so a post on the platform and its record are
    never touched.
    """
    moment = now or datetime.now()
    try:
        with Path(history_path).open("r", encoding="utf-8") as history_file:
            entries = json.load(history_file)
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(entries, list):
        return []

    expired: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("status") or "").strip().upper() != "PUBLISHED":
            continue
        posted_url = str(entry.get("posted_url") or "").strip()
        if not posted_url:
            # A publish that was never confirmed is not a published post.
            continue
        published_at = _parse_published_at(entry.get("date"))
        if published_at is None:
            continue
        deadline = published_at.timestamp() + retention_days * 24 * 60 * 60
        if moment.timestamp() < deadline:
            continue
        expired.append({
            "task_id": str(entry.get("task_id") or ""),
            "posted_url": posted_url,
            "published_at": published_at.isoformat(),
            "deadline": published_at.isoformat(),
        })
    return expired


def cleanup_expired_media(
    now: datetime | None = None,
    *,
    history_path: Path = HISTORY_FILE,
    task_states_dir: Path = TASK_STATES_DIR,
    temp_dir: Path = TEMP_DIR,
    originals_dir: Path = ORIGINALS_DIR,
    processed_dir: Path = PROCESSED_DIR,
    retention_days: int = RETENTION_DAYS,
    dry_run: bool = False,
    log: Any = print,
) -> dict[str, Any]:
    """Remove the copies of the videos whose retention time has run out.

    Only the files that belong to a task whose publish was confirmed and
    whose seven days have passed are removed. The original of the video,
    the history, the record of the rights and the post on the platform
    are never touched: they are the proof of what was published and they
    stay.

    A file that another task still uses is never removed, and a file of a
    task that was never published is never removed either.

    The pass is written to the state file of the scheduler, so a restart
    of the machine does not lose the record of what was done.
    """
    moment = now or datetime.now()
    expired = expired_published_tasks(
        moment,
        history_path=history_path,
        retention_days=retention_days,
    )
    expired_task_ids = {item["task_id"] for item in expired if item["task_id"]}

    # The files that other tasks still use are never removed.
    busy: set[Path] = set()
    for state_file in sorted(Path(task_states_dir).glob("*.json")):
        try:
            payload = json.loads(state_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        owner = str(payload.get("task_id") or state_file.stem)
        if owner in expired_task_ids:
            continue
        for key in ("temp_path", "original_path", "path"):
            value = str(payload.get(key) or "").strip()
            if value:
                busy.add(Path(value).resolve())

    removed: list[str] = []
    kept: list[str] = []
    skipped: list[str] = []

    for task_id in sorted(expired_task_ids):
        state = load_task_state(task_id, task_states_dir)
        # Only a task whose publish was really confirmed may be cleaned.
        status = str(state.get("status") or "").strip().upper()
        posted = str(state.get("posted_url") or state.get("draft_reference") or "").strip()
        if status != "PUBLISHED" or not posted:
            skipped.append(f"{task_id}: chưa xác minh đăng, giữ lại")
            continue

        for key in ("temp_path", "path"):
            candidate = str(state.get(key) or "").strip()
            if not candidate:
                continue
            path = Path(candidate)
            if not path.is_file():
                continue
            resolved = path.resolve()
            # The original is the proof of what was published and stays.
            try:
                if resolved == Path(originals_dir).resolve():
                    skipped.append(f"{task_id}: bản gốc, giữ lại")
                    continue
            except OSError:
                continue
            if resolved in busy:
                skipped.append(f"{task_id}: đang dùng bởi job khác, giữ lại")
                continue
            if dry_run:
                removed.append(str(path))
                continue
            try:
                path.unlink()
                removed.append(str(path))
                log(f"cleanup: removed {path}")
            except OSError as exc:
                skipped.append(f"{task_id}: {exc}")

    result = {
        "dry_run": bool(dry_run),
        "expired_tasks": expired,
        "removed": removed,
        "skipped": skipped,
        "at": moment.isoformat(),
    }
    return result


def load_task_state(task_id: str, tasks_dir: Path = TASK_STATES_DIR) -> dict[str, Any]:
    """Load a persisted task state, returning an empty mapping on any error.

    A missing or unreadable file is not an error: the caller simply starts
    the task from the beginning. Nothing is deleted by this helper.
    """
    path = Path(tasks_dir) / f"{task_id}.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def save_task_state(
    task_id: str,
    status: str,
    payload: dict[str, Any],
    tasks_dir: Path = TASK_STATES_DIR,
) -> Path:
    """Persist a task state atomically so an interrupted run can resume.

    The file is written to a temporary path first and then replaced, so a
    crash never leaves a half written state file that would lose the caption,
    the video path, the metadata, or the draft reference.
    """
    directory = Path(tasks_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{task_id}.json"
    state = {
        "task_id": task_id,
        "status": status,
        "updated_at": datetime.now().isoformat(),
    }
    state.update(payload or {})
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    with temporary_path.open("w", encoding="utf-8") as state_file:
        json.dump(state, state_file, indent=2, sort_keys=True, default=str)
        state_file.write("\n")
    temporary_path.replace(path)
    return path


def record_hash(
    sha256: str,
    task_id: str,
    source: str,
    path: Path,
    library_path: Path = LIBRARY_FILE,
) -> dict[str, Any]:
    """Record a hash unless it is already present."""
    library = load_library(library_path)
    existing = library["hashes"].get(sha256)
    if existing is not None:
        raise StorageError(
            f"Duplicate content blocked: SHA256 {sha256} is already in the library "
            f"(task_id: {existing.get('task_id', 'unknown')})"
        )
    entry = {
        "task_id": task_id,
        "source": source,
        "path": str(path),
        "sha256": sha256,
    }
    library["hashes"][sha256] = entry
    save_library(library, library_path)
    return entry
