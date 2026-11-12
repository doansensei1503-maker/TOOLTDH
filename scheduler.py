"""P16.1 scheduled orchestration with APScheduler.

The scheduler runs the discovery and review stage on the configured schedule
and never publishes on its own. Every scheduled run writes its own state so
an interrupted run is not repeated and no duplicate draft is created.

The scheduler is deliberately small: it triggers the same functions the
command line uses, so the scheduled path and the manual path behave
identically.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

STATE_DIR = Path("data") / "state"
SCHEDULE_STATE_FILE = STATE_DIR / "schedule.json"


class SchedulerError(RuntimeError):
    """Raised when the schedule cannot be built or run."""


@dataclass
class ScheduleSettings:
    """The schedule settings read from the configuration."""

    daily_time: str = "09:00"
    enabled: bool = False
    topic: str = ""
    task_id_prefix: str = "scheduled"
    frequency: str = "daily"
    days: list[str] = field(default_factory=list)
    daily_limit: int = 1

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "ScheduleSettings":
        """Read the schedule settings from the loaded configuration.

        The dashboard settings take precedence over the configuration file,
        so a schedule changed in the interface is the one that runs. The
        schedule can only narrow the automation: it never adds a source and
        never changes a permit.
        """
        raw = config.get("schedule")
        daily_time = "09:00"
        enabled = False
        frequency = "daily"
        days: list[str] = []
        daily_limit = 1
        if isinstance(raw, dict):
            daily_time = str(raw.get("daily_time", raw.get("time", daily_time)))
            enabled = bool(raw.get("enabled", False))
            frequency = str(raw.get("frequency", "daily"))
            days = [str(day) for day in raw.get("days", []) or []]
            daily_limit = int(raw.get("daily_limit", 1) or 1)
        elif isinstance(raw, str) and raw.strip():
            daily_time = raw.strip()

        # The dashboard settings are the runtime override.
        try:
            from dashboard_service import _load_settings

            dashboard = _load_settings()
        except Exception:
            dashboard = {}
        stored = dashboard.get("schedule")
        if isinstance(stored, dict):
            daily_time = str(stored.get("daily_time", daily_time))
            enabled = bool(stored.get("enabled", enabled))
            frequency = str(stored.get("frequency", frequency))
            days = [str(day) for day in stored.get("days", days) or []]
            daily_limit = int(stored.get("daily_limit", daily_limit) or 1)
            topic_override = str(stored.get("topic", "")).strip()
        else:
            topic_override = ""

        discovery = config.get("discovery", {}) if isinstance(config.get("discovery", {}), dict) else {}
        topic = topic_override or str(discovery.get("target_topic", "")).strip()
        return cls(
            daily_time=daily_time,
            enabled=enabled,
            topic=topic,
            task_id_prefix=str(discovery.get("task_id_prefix", "scheduled")),
            frequency=frequency,
            days=days,
            daily_limit=daily_limit,
        )


def parse_daily_time(value: str) -> tuple[int, int]:
    """Parse an ``HH:MM`` time into an hour and a minute."""
    text = str(value or "").strip()
    if not text:
        raise SchedulerError("Rejected: no schedule time was configured")
    parts = text.split(":")
    try:
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
    except (IndexError, ValueError) as exc:
        raise SchedulerError(
            f"Rejected: the schedule time {value!r} is not in the HH:MM format"
        ) from exc
    if not (0 <= hour <= 23) or not (0 <= minute <= 59):
        raise SchedulerError(f"Rejected: the schedule time {value!r} is out of range")
    return hour, minute


def load_schedule_state(path: Path = SCHEDULE_STATE_FILE) -> dict[str, Any]:
    """Load the record of the last scheduled runs."""
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def save_schedule_state(payload: dict[str, Any], path: Path = SCHEDULE_STATE_FILE) -> Path:
    """Write the record of the scheduled runs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def run_scheduled_task(
    config: dict[str, Any],
    settings: ScheduleSettings,
    *,
    log: Callable[[str], None] = print,
    state_path: Path = SCHEDULE_STATE_FILE,
) -> str:
    """Run one scheduled discovery and review pass.

    The run never publishes. It discovers the real candidates and writes the
    review list so the user chooses the video. The task id is derived from
    the date so a restart on the same day reuses the same id and the
    existing review instead of creating a second one.
    """
    from discovery_live import SearchFilters, discover_new_candidates, save_production_candidates
    from discover import filter_and_select
    from review_stage import write_review

    topic = settings.topic
    if not topic:
        log("SCHEDULED: skipped because no topic is configured.")
        return "SKIPPED"

    task_id = f"{settings.task_id_prefix}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    state = load_schedule_state(state_path)
    state.setdefault("runs", [])

    discovery_config = dict(config.get("discovery", {}) or {})
    discovery_config["target_topic"] = topic
    config["discovery"] = discovery_config

    # The scheduled run uses the same filters and the same one-best-video
    # rule as the dashboard, so both report the same outcome.
    search_filters = SearchFilters.from_payload(discovery_config.get("filters") or {})

    # The daily limit stops the automation once the configured number of
    # runs for today is reached.
    today = date.today().isoformat()
    runs_today = [
        run for run in state["runs"]
        if str(run.get("at", "")).startswith(today)
        and run.get("status") not in {"SKIPPED"}
    ]
    limit = max(1, int(settings.daily_limit or 1))
    if len(runs_today) >= limit:
        log(
            f"SCHEDULED: skipped because the daily limit of {limit} run(s) is "
            "already reached for today."
        )
        return "LIMIT_REACHED"

    def _read(keyword: str) -> dict[str, Any]:
        from poster import read_keyword_search

        return read_keyword_search(keyword)

    try:
        candidates, blockers = discover_new_candidates(config, topic, read_search=_read)
    except Exception as exc:  # noqa: BLE001 - the failure is recorded
        log(f"SCHEDULED: the discovery failed: {exc}")
        state["runs"].append(
            {"task_id": task_id, "at": datetime.now().isoformat(), "status": "FAILED", "reason": str(exc)}
        )
        save_schedule_state(state, state_path)
        return "FAILED"

    for blocker in blockers:
        log(f"SCHEDULED BLOCKER: {blocker}")

    selection = filter_and_select(
        candidates, config, topic=topic, filters=search_filters.to_dict()
    )
    all_blockers = list(blockers) + list(selection.blockers)
    save_production_candidates(selection.candidates, topic=topic, blockers=all_blockers)
    review_path = write_review(
        task_id,
        selection.candidates,
        selection.scores,
        topic=topic,
        blockers=all_blockers,
    )

    if selection.status == "CANDIDATE_FOUND" and selection.selected is not None:
        status = "AWAITING_SELECTION"
        chosen_score = selection.selected_score.score if selection.selected_score else 0
        log(
            f"SCHEDULED: {status} - one best video {selection.selected.source_url} "
            f"with score {chosen_score}, review at {review_path}"
        )
    elif selection.candidates:
        status = "AWAITING_SELECTION"
        log(f"SCHEDULED: {status} - {len(selection.candidates)} candidate(s), review at {review_path}")
    else:
        status = (
            "NO_QUALIFIED_VIDEO"
            if selection.status == "NO_QUALIFIED_VIDEO"
            else "NO_CANDIDATES_FOUND"
        )
        log(f"SCHEDULED: {status} - no candidate met the criteria, review at {review_path}")

    state["runs"].append(
        {
            "task_id": task_id,
            "at": datetime.now().isoformat(),
            "status": status,
            "topic": topic,
            "candidate_count": len(selection.candidates),
            "selected_url": selection.selected.source_url if selection.selected else "",
            "review_file": str(review_path),
            "blockers": list(all_blockers),
        }
    )
    save_schedule_state(state, state_path)
    return status


def build_scheduler(
    config: dict[str, Any],
    *,
    log: Callable[[str], None] = print,
    state_path: Path = SCHEDULE_STATE_FILE,
):
    """Build the APScheduler job that runs the scheduled pass.

    The job is created with the configured daily time. Nothing is published
    by the job.
    """
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
    except ImportError as exc:  # pragma: no cover - the dependency is required
        raise SchedulerError(
            f"Rejected: APScheduler is not installed, so the schedule cannot run: {exc}"
        ) from exc

    settings = ScheduleSettings.from_config(config)
    hour, minute = parse_daily_time(settings.daily_time)
    scheduler = BackgroundScheduler(timezone="Asia/Ho_Chi_Minh")

    # The weekdays in the week map to the numbers the cron trigger uses.
    weekday_numbers = {
        "mon": 0, "tue": 1, "wed": 2, "thu": 3,
        "fri": 4, "sat": 5, "sun": 6,
    }
    selected_days = [
        weekday_numbers[day.lower()]
        for day in settings.days
        if day.lower() in weekday_numbers
    ]
    trigger: Any = CronTrigger(hour=hour, minute=minute)
    if selected_days:
        trigger = CronTrigger(hour=hour, minute=minute, day_of_week=",".join(
            str(number) for number in sorted(selected_days)
        ))

    scheduler.add_job(
        run_scheduled_task,
        trigger=trigger,
        id="toolt-dh-scheduled-discovery",
        args=[config, settings],
        kwargs={"log": log, "state_path": state_path},
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    return scheduler


def start_scheduler(
    config: dict[str, Any],
    *,
    log: Callable[[str], None] = print,
    state_path: Path = SCHEDULE_STATE_FILE,
):
    """Start the scheduler and return it."""
    settings = ScheduleSettings.from_config(config)
    if not settings.enabled:
        log("SCHEDULE: disabled in the configuration, so nothing was scheduled.")
        return None
    scheduler = build_scheduler(config, log=log, state_path=state_path)
    scheduler.start()
    log(
        f"SCHEDULE: started, the discovery runs every day at {settings.daily_time} "
        f"for the topic {settings.topic!r}. It never publishes."
    )
    return scheduler


__all__ = [
    "SCHEDULE_STATE_FILE",
    "STATE_DIR",
    "ScheduleSettings",
    "SchedulerError",
    "build_scheduler",
    "load_schedule_state",
    "parse_daily_time",
    "run_scheduled_task",
    "save_schedule_state",
    "start_scheduler",
]
