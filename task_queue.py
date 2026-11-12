"""P4 scheduling queue for approved TikTok Studio tasks."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

DEFAULT_QUEUE_PATH = Path("data") / "queue.json"
MAX_POSTS_PER_CREATOR_PER_DAY = 15


class QueueError(RuntimeError):
    """Raised when a task cannot safely be queued."""


@dataclass
class QueuedTask:
    """A scheduled publishing task."""

    task_id: str
    creator_id: str
    scheduled_at: str
    caption: str
    video_path: str
    status: str = "SCHEDULED"
    mode: str = "approve"
    metadata: dict[str, Any] = field(default_factory=dict)

    def scheduled_datetime(self) -> datetime:
        """Parse the scheduled timestamp."""
        try:
            return datetime.fromisoformat(self.scheduled_at)
        except ValueError as exc:
            raise QueueError(f"Invalid scheduled_at for task {self.task_id}") from exc


class PublishQueue:
    """Persistent queue enforcing per-creator daily limits."""

    def __init__(self, path: Path = DEFAULT_QUEUE_PATH, max_daily_posts: int = MAX_POSTS_PER_CREATOR_PER_DAY) -> None:
        self.path = path
        self.max_daily_posts = max_daily_posts

    def load(self) -> list[QueuedTask]:
        """Load queued tasks."""
        if not self.path.exists():
            return []
        try:
            with self.path.open("r", encoding="utf-8") as queue_file:
                payload = json.load(queue_file)
        except (OSError, json.JSONDecodeError) as exc:
            raise QueueError(f"Unable to read publish queue: {exc}") from exc
        if not isinstance(payload, list):
            raise QueueError("Publish queue has an invalid structure")
        tasks: list[QueuedTask] = []
        for item in payload:
            try:
                tasks.append(QueuedTask(**item))
            except TypeError as exc:
                raise QueueError("Publish queue contains an invalid task") from exc
        return tasks

    def save(self, tasks: list[QueuedTask]) -> None:
        """Persist queued tasks atomically."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_suffix(self.path.suffix + ".tmp")
        with temporary_path.open("w", encoding="utf-8") as queue_file:
            json.dump([asdict(task) for task in tasks], queue_file, indent=2, sort_keys=True)
            queue_file.write("\n")
        temporary_path.replace(self.path)

    def scheduled_count(self, creator_id: str, day: date, tasks: list[QueuedTask] | None = None) -> int:
        """Count scheduled or published tasks for one creator on a day."""
        all_tasks = tasks if tasks is not None else self.load()
        count = 0
        for task in all_tasks:
            if task.creator_id != creator_id or task.status not in {"SCHEDULED", "APPROVED", "PUBLISHED"}:
                continue
            try:
                scheduled_day = task.scheduled_datetime().date()
            except QueueError:
                continue
            if scheduled_day == day:
                count += 1
        return count

    def add(
        self,
        task: QueuedTask,
        tasks: list[QueuedTask] | None = None,
    ) -> list[QueuedTask]:
        """Add a task while enforcing the daily creator limit."""
        scheduled = task.scheduled_datetime()
        if scheduled < datetime.now():
            raise QueueError("Scheduled time must be in the future")
        all_tasks = list(tasks if tasks is not None else self.load())
        if any(existing.task_id == task.task_id for existing in all_tasks):
            raise QueueError(f"Task {task.task_id} is already queued")
        if self.scheduled_count(task.creator_id, scheduled.date(), all_tasks) >= self.max_daily_posts:
            raise QueueError(
                f"Daily limit reached for creator {task.creator_id}: "
                f"{self.max_daily_posts} posts per day"
            )
        all_tasks.append(task)
        return all_tasks

    def find(self, task_id: str, tasks: list[QueuedTask] | None = None) -> QueuedTask | None:
        """Find a queued task by ID."""
        all_tasks = tasks if tasks is not None else self.load()
        return next((task for task in all_tasks if task.task_id == task_id), None)

    def update_status(
        self,
        task_id: str,
        status: str,
        metadata: dict[str, Any] | None = None,
        tasks: list[QueuedTask] | None = None,
    ) -> list[QueuedTask]:
        """Update a task's status and optional metadata."""
        all_tasks = list(tasks if tasks is not None else self.load())
        for task in all_tasks:
            if task.task_id == task_id:
                task.status = status
                if metadata:
                    task.metadata.update(metadata)
                return all_tasks
        raise QueueError(f"Task {task_id} is not queued")


__all__ = [
    "DEFAULT_QUEUE_PATH",
    "MAX_POSTS_PER_CREATOR_PER_DAY",
    "PublishQueue",
    "QueueError",
    "QueuedTask",
]
