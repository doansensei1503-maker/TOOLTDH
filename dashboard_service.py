"""P17 dashboard service layer.

This module exposes the existing backend to the dashboard over a JSON API.
Every call goes to the modules that already exist, so the dashboard shows
the real state of the tool and never a fabricated one.

The rules of the project are unchanged: no protection is bypassed, no
metric is invented, nothing is published without an approval, and a task
whose rights are unclear ends in ``NEEDS_PERMISSION_REVIEW``.
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from storage import (
    LIBRARY_FILE,
    TASK_STATES_DIR,
    load_library,
    load_task_state,
)
from scheduler import ScheduleSettings

DATA_DIR = Path("data")
PRODUCTION_DIR = DATA_DIR / "production"
REVIEW_DIR = DATA_DIR / "review"
TASKS_DIR = DATA_DIR / "tasks"
STATE_DIR = DATA_DIR / "state"
SCHEDULE_STATE_FILE = STATE_DIR / "schedule.json"
SEARCH_PROFILES_FILE = DATA_DIR / "search_profiles.json"
NOTIFICATIONS_FILE = DATA_DIR / "notifications.json"
SETTINGS_FILE = DATA_DIR / "settings.json"
REJECTIONS_FILE = DATA_DIR / "state" / "discovery_rejections.json"

# The directories a preview may read a video from. Only a video that is
# already on this machine is served, and only from these directories, so a
# request can never read an arbitrary file.
PREVIEW_DIRS = (DATA_DIR / "temp", DATA_DIR / "originals", DATA_DIR / "processed")

# The status that means the rights of a video are not clear enough to act.
NEEDS_PERMISSION_REVIEW = "NEEDS_PERMISSION_REVIEW"


class ServiceError(RuntimeError):
    """Raised when a dashboard request cannot be served."""


@dataclass
class BackgroundJob:
    """One background operation started by the dashboard.

    A long operation runs in a worker thread so the dashboard stays
    responsive and the work continues after the browser tab is closed.
    """

    job_id: str
    kind: str
    task_id: str
    status: str = "RUNNING"
    started_at: str = ""
    finished_at: str = ""
    message: str = ""
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class JobRegistry:
    """Track the background jobs the dashboard started."""

    def __init__(self) -> None:
        self._jobs: dict[str, BackgroundJob] = {}
        self._lock = threading.Lock()

    def start(self, job: BackgroundJob) -> BackgroundJob:
        with self._lock:
            self._jobs[job.job_id] = job
        return job

    def get(self, job_id: str) -> BackgroundJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def all(self) -> list[BackgroundJob]:
        with self._lock:
            return sorted(
                self._jobs.values(),
                key=lambda item: item.started_at,
                reverse=True,
            )

    def update(self, job_id: str, **changes: Any) -> BackgroundJob | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            for key, value in changes.items():
                if hasattr(job, key):
                    setattr(job, key, value)
            return job


JOBS = JobRegistry()

# The discovery jobs that were asked to stop. The flag is checked between
# the sources, so a run stops at the next source and never in the middle
# of a page read.
_STOP_LOCK = threading.Lock()
_STOP_REQUESTED: set[str] = set()

# Per-query collection stats of the last discovery run (returned videos vs
# kept videos per query). Reported in the result as `query_stats`.
_LAST_QUERY_STATS: dict[str, Any] = {}


def _read_json(path: Path, default: Any) -> Any:
    """Read a JSON file, returning the default when it is missing or broken."""
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: Path, payload: Any) -> Path:
    """Write a JSON file atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )
    temporary.replace(path)
    return path


# ---------------------------------------------------------------- overview


def _load_config() -> dict[str, Any]:
    """Load the project configuration."""
    import yaml

    config_path = Path(__file__).with_name("config.yaml")
    if not config_path.exists():
        return {}
    try:
        return yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _list_task_states() -> list[dict[str, Any]]:
    """Load every persisted task state."""
    states: list[dict[str, Any]] = []
    if not TASKS_DIR.exists():
        return states
    for path in sorted(TASKS_DIR.glob("*.json")):
        payload = _read_json(path, {})
        if not isinstance(payload, dict):
            continue
        payload.setdefault("task_id", path.stem)
        states.append(payload)
    states.sort(key=lambda item: str(item.get("updated_at", "")), reverse=True)
    return states


def _production_candidates() -> dict[str, Any]:
    """Load the production candidate store."""
    payload = _read_json(PRODUCTION_DIR / "candidates.json", {})
    return payload if isinstance(payload, dict) else {}


def _review_records() -> list[dict[str, Any]]:
    """Load every review record."""
    records: list[dict[str, Any]] = []
    if not REVIEW_DIR.exists():
        return records
    for path in sorted(REVIEW_DIR.glob("*-review.json")):
        payload = _read_json(path, {})
        if not isinstance(payload, dict):
            continue
        records.append(payload)
    records.sort(key=lambda item: str(item.get("created_at", "")), reverse=True)
    return records


def _history_entries() -> list[dict[str, Any]]:
    """Load the publish history."""
    from history import PublishHistory

    try:
        return PublishHistory().load()
    except Exception:
        return []


def overview() -> dict[str, Any]:
    """Return the overview of the whole tool for the dashboard."""
    config = _load_config()
    candidates = _production_candidates()
    videos = candidates.get("videos", []) if isinstance(candidates, dict) else []
    blockers = candidates.get("blockers", []) if isinstance(candidates, dict) else []
    reviews = _review_records()
    tasks = _list_task_states()
    history = _history_entries()
    library = load_library()

    awaiting = [
        review
        for review in reviews
        if review.get("status") == "AWAITING_SELECTION"
    ]
    selected_but_not_processed = [
        review
        for review in reviews
        if review.get("status") == "SELECTED"
    ]

    return {
        "generated_at": datetime.now().isoformat(),
        "topic": str((config.get("discovery", {}) or {}).get("target_topic", "")),
        "mode": str(config.get("mode", "approve")),
        "auto_post": bool(config.get("auto_post", False)),
        "expected_account": str(config.get("expected_account", "")),
        "emergency_stop": bool(_load_settings().get("emergency_stop", False)),
        "counts": {
            "candidates": len(videos),
            "reviews": len(reviews),
            "awaiting_selection": len(awaiting),
            "selected_not_processed": len(selected_but_not_processed),
            "tasks": len(tasks),
            "published": len([item for item in history if item.get("status") == "PUBLISHED"]),
            "library": len(library.get("hashes", {})),
            "jobs_running": len([job for job in JOBS.all() if job.status == "RUNNING"]),
        },
        "blockers": list(blockers),
        "schedule": _schedule_status(),
        "recent_tasks": tasks[:10],
        "recent_reviews": [
            {
                "task_id": review.get("task_id", ""),
                "topic": review.get("topic", ""),
                "status": review.get("status", ""),
                "candidate_count": len(review.get("candidates", []) or []),
                "created_at": review.get("created_at", ""),
            }
            for review in reviews[:10]
        ],
    }


def _schedule_status() -> dict[str, Any]:
    """Return the state of the scheduler."""
    from scheduler import ScheduleSettings, parse_daily_time

    config = _load_config()
    settings = ScheduleSettings.from_config(config)
    state = _read_json(SCHEDULE_STATE_FILE, {})
    runs = state.get("runs", []) if isinstance(state, dict) else []
    queue_runs = state.get("queue_runs", []) if isinstance(state, dict) else []
    last_run = runs[0] if runs else {}
    next_run = ""
    try:
        hour, minute = parse_daily_time(settings.daily_time)
        now = datetime.now()
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= now:
            candidate = candidate + timedelta(days=1)
        next_run = candidate.isoformat()
    except Exception:
        next_run = ""
    queue_info: dict[str, Any] = {}
    try:
        from task_queue import PublishQueue

        queue = PublishQueue()
        tasks = queue.load()
        active = queue.has_active_job(tasks)
        queue_info = {
            "queued": len([t for t in tasks if t.status == "QUEUED"]),
            "active": active.task_id if active else "",
            "active_status": active.status if active else "",
            "today": queue.count_today(date.today(), tasks),
            "this_hour": queue.count_this_hour(datetime.now(), tasks),
            "last_queue_run": queue_runs[0] if queue_runs else {},
        }
    except Exception:
        queue_info = {}
    return {
        "enabled": settings.enabled,
        "daily_time": settings.daily_time,
        "topic": settings.topic,
        "next_run": next_run,
        "last_run": last_run,
        "run_count": len(runs),
        "max_per_day": settings.max_per_day,
        "max_per_hour": settings.max_per_hour,
        "check_every_hours": settings.check_every_hours,
        "queue": queue_info,
    }


# ---------------------------------------------------------------- caption


def generate_caption(task_id: str, style: str = "viral") -> dict[str, Any]:
    """Generate caption and hashtag options for the selected video.

    The caption comes from the configured AI provider, so the text is
    produced by the real backend. The reference captions that were read
    from the source are kept separate from the text the AI wrote, so the
    two are never mixed.
    """
    from brain import analyze_content, create_provider

    review = _read_json(REVIEW_DIR / f"{task_id}-review.json", None)
    if not isinstance(review, dict):
        raise ServiceError(f"No review was found for {task_id}.")

    candidates = review.get("candidates", []) or []
    selected_url = str(review.get("selected_url", ""))
    chosen = None
    for candidate in candidates:
        if str(candidate.get("source_url", "")) == selected_url:
            chosen = candidate
            break
    if chosen is None and candidates:
        chosen = candidates[0]
    if chosen is None:
        raise ServiceError(
            f"The review for {task_id} has no candidate, so no caption can be written."
        )

    config = _load_config()
    discovery = config.get("discovery", {}) if isinstance(config.get("discovery"), dict) else {}
    topic = str(review.get("topic", "") or discovery.get("target_topic", "") or "")
    if topic:
        discovery["target_topic"] = topic
        config["discovery"] = discovery

    metadata = {
        "title": str(chosen.get("title", "")),
        "description": str(chosen.get("title", "")),
        "creator": str(chosen.get("creator", "")),
        "source_url": str(chosen.get("source_url", "")),
        "duration_seconds": chosen.get("duration_seconds", 0.0),
        "views": chosen.get("views", 0),
        "likes": chosen.get("likes", 0),
        "topic": topic,
    }

    provider = create_provider(config)
    result = analyze_content(
        metadata,
        config,
        creator_credit=f"by @{chosen.get('creator', '')}" if chosen.get("creator") else "",
        provider=provider,
    )

    payload = {
        "task_id": task_id,
        "provider": result.provider or provider.name,
        "model": result.model or provider.model,
        "status": result.status,
        "caption": result.caption,
        "hashtags": list(result.hashtags),
        "title": result.title,
        "language": result.language,
        "score": result.score,
        "score_reason": result.score_reason,
        "error": result.error,
        "style": style,
        "source": {
            "url": str(chosen.get("source_url", "")),
            "title": str(chosen.get("title", "")),
            "creator": str(chosen.get("creator", "")),
            "views": chosen.get("views", 0),
            "likes": chosen.get("likes", 0),
        },
        "reference": {
            "note": (
                "Nội dung tham khảo đọc từ nguồn và nội dung AI tự tạo là hai "
                "phần riêng biệt. Bản quyền bài hát và hình ảnh thuộc về "
                "chủ sở hữu tương ứng."
            ),
            "published_title": str(chosen.get("title", "")),
        },
    }
    _write_json(REVIEW_DIR / f"{task_id}-caption.json", payload)
    return payload


# ---------------------------------------------------------------- scheduler


_SCHEDULER_LOCK = threading.Lock()
_SCHEDULER: Any = None


def scheduler_status() -> dict[str, Any]:
    """Return the state of the running scheduler.

    The scheduler runs in the server process, so a scheduled pass does not
    depend on the dashboard page staying open.
    """
    config = _load_config()
    settings = ScheduleSettings.from_config(config)
    with _SCHEDULER_LOCK:
        running = _SCHEDULER is not None and getattr(_SCHEDULER, "running", False)
        next_run = ""
        if running:
            try:
                job = _SCHEDULER.get_job("toolt-dh-scheduled-discovery")
                if job is not None and job.next_run_time:
                    next_run = job.next_run_time.isoformat()
            except Exception:
                next_run = ""
    state = _read_json(SCHEDULE_STATE_FILE, {})
    runs = state.get("runs", []) if isinstance(state, dict) else []
    queue_runs = state.get("queue_runs", []) if isinstance(state, dict) else []
    queue_info: dict[str, Any] = {}
    try:
        from task_queue import PublishQueue

        queue = PublishQueue()
        tasks = queue.load()
        active = queue.has_active_job(tasks)
        queue_info = {
            "queued": len([t for t in tasks if t.status == "QUEUED"]),
            "active": active.task_id if active else "",
            "active_status": active.status if active else "",
            "tasks": [
                {
                    "task_id": t.task_id,
                    "status": t.status,
                    "scheduled_at": t.scheduled_at,
                    "source_url": str((t.metadata or {}).get("source_url", "")),
                }
                for t in tasks[-20:]
            ],
            "last_queue_run": queue_runs[0] if queue_runs else {},
        }
    except Exception:
        queue_info = {}
    return {
        "enabled": bool(settings.enabled),
        "running": running,
        "daily_time": settings.daily_time,
        "frequency": settings.frequency,
        "days": list(settings.days),
        "daily_limit": settings.daily_limit,
        "max_per_day": settings.max_per_day,
        "max_per_hour": settings.max_per_hour,
        "check_every_hours": settings.check_every_hours,
        "topic": settings.topic,
        "min_views": str(((config.get("discovery", {}) or {}).get("filters", {}) or {}).get("min_views", "")),
        "next_run": next_run,
        "runs": runs[:20],
        "run_count": len(runs),
        "last_run": runs[0] if runs else {},
        "queue": queue_info,
    }


def queue_list() -> dict[str, Any]:
    """Return the sequential posting queue (single active job kept)."""
    from task_queue import PublishQueue

    config = _load_config()
    settings = ScheduleSettings.from_config(config)
    queue = PublishQueue()
    try:
        tasks = queue.load()
    except Exception as exc:
        raise ServiceError(f"Không đọc được hàng đợi: {exc}") from exc
    active = queue.has_active_job(tasks)
    return {
        "tasks": [
            {
                "task_id": t.task_id,
                "creator_id": t.creator_id,
                "scheduled_at": t.scheduled_at,
                "status": t.status,
                "mode": t.mode,
                "source_url": str((t.metadata or {}).get("source_url", "")),
            }
            for t in tasks
        ],
        "active_task": active.task_id if active else "",
        "max_per_day": settings.max_per_day,
        "max_per_hour": settings.max_per_hour,
        "check_every_hours": settings.check_every_hours,
        "auto_post": bool(config.get("auto_post", False)),
    }


def queue_enqueue(source_url: str = "", task_id: str = "") -> dict[str, Any]:
    """Queue one eligible video as QUEUED (no duplicate, no parallel)."""
    from datetime import timedelta as _td
    from task_queue import PublishQueue, QueuedTask

    wanted = str(source_url or "").strip()
    if not wanted:
        raise ServiceError("Không có URL video để xếp hàng.")
    result = _LAST_RESULT or _load_last_result()
    top5 = result.get("top5", []) if isinstance(result, dict) else []
    card = next((c for c in top5 if str(c.get("source_url", "")) == wanted), None)
    if card is None:
        raise ServiceError("Video không nằm trong TOP 5 đề xuất nên không xếp hàng.")
    # Safety gate: NEEDS_REVIEW never queues on model evidence alone. Only
    # a manual user confirmation (stored separately from the model verdict)
    # plus allowlisted rights can lift it to the queue; the approval gates
    # before download/publish still apply downstream.
    if str(card.get("status", "")) == "NEEDS_REVIEW" and not card.get("user_confirmed"):
        try:
            _cmap = _read_json(STATE_DIR / "discovery_content_confirm.json", {}) or {}
        except Exception:
            _cmap = {}
        _entry = _cmap.get(wanted, {}) if isinstance(_cmap, dict) else {}
        if not (isinstance(_entry, dict) and _entry.get("user_confirmed") is True):
            raise ServiceError(
                "Video NEEDS_REVIEW chưa được người dùng xác minh nội dung nên không xếp hàng. "
                f"Lý do: {card.get('reason', '')}"
            )
    if not card.get("pick"):
        # A user-confirmed NEEDS_REVIEW with allowlisted rights may queue:
        # its pick flag stays False (it never auto-posts), but the manual
        # queue action is the explicit human approval for this step.
        _confirmed = bool(card.get("user_confirmed"))
        if not _confirmed:
            try:
                _cmap2 = _read_json(STATE_DIR / "discovery_content_confirm.json", {}) or {}
            except Exception:
                _cmap2 = {}
            _e2 = _cmap2.get(wanted, {}) if isinstance(_cmap2, dict) else {}
            _confirmed = bool(isinstance(_e2, dict) and _e2.get("user_confirmed") is True)
        _rights_ok = str(card.get("rights", "")) == "ALLOWLISTED_PERMITTED"
        if not (_confirmed and _rights_ok and str(card.get("status", "")) == "NEEDS_REVIEW"):
            raise ServiceError(f"Video chưa đủ điều kiện xếp hàng: {card.get('reason', '')}")
    queue = PublishQueue()
    tasks = queue.load()
    for existing in tasks:
        if str(((existing.metadata or {}).get("source_url", ""))).strip() == wanted:
            if existing.status not in ("BLOCKED", "FAILED_RETRYABLE"):
                raise ServiceError(f"Video đã có trong hàng đợi ({existing.task_id}/{existing.status}).")
    tid = str(task_id or "").strip() or f"q-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    if queue.find(tid, tasks) is not None:
        raise ServiceError(f"Task {tid} đã có trong hàng đợi.")
    scheduled_at = (datetime.now() + _td(minutes=5)).isoformat(timespec="seconds")
    job = QueuedTask(
        task_id=tid,
        creator_id=str(card.get("creator", "") or "").lstrip("@"),
        scheduled_at=scheduled_at,
        caption=str(card.get("title", "")),
        video_path="",
        status="QUEUED",
        mode=str(_load_settings().get("mode", "approve")),
        metadata={"source_url": wanted, "score": card.get("score", 0)},
    )
    tasks = queue.add(job, tasks)
    queue.save(tasks)
    return {"task_id": tid, "status": "QUEUED", "scheduled_at": scheduled_at}


def scheduler_start() -> dict[str, Any]:
    """Start the background scheduler."""
    global _SCHEDULER
    from scheduler import start_scheduler

    config = _load_config()
    with _SCHEDULER_LOCK:
        if _SCHEDULER is not None and getattr(_SCHEDULER, "running", False):
            return scheduler_status()
        scheduler = start_scheduler(config, log=lambda message: _log(message))
        _SCHEDULER = scheduler
    return scheduler_status()


def scheduler_stop() -> dict[str, Any]:
    """Stop the background scheduler without deleting its state."""
    global _SCHEDULER
    with _SCHEDULER_LOCK:
        if _SCHEDULER is not None:
            try:
                _SCHEDULER.shutdown(wait=False)
            except Exception:
                pass
            _SCHEDULER = None
    return scheduler_status()


def _log(message: str) -> None:
    """Record a scheduler message as a notification."""
    try:
        add_notification("scheduler", str(message))
    except Exception:
        pass


# ---------------------------------------------------------------- discovery


def _discovery_request(
    topic: str = "",
    filters: dict[str, Any] | None = None,
    job_id: str = "",
    resume: bool = False,
) -> dict[str, Any]:
    """Run the live discovery, the filters and the trend scoring.

    The discovery is executed in a worker thread by the caller so a slow
    page read never blocks the dashboard.

    The discovery source is the public TikTok keyword search. The creator
    allowlist is not a search source and is never consulted here; it is
    used later, when an approved video is checked for reuse permission.

    Nothing is downloaded here. The run only reads the search results the
    signed-in session already receives and reports what it found.

    When ``resume`` is set, the candidates of the last run are reused and
    no search is made. The frames and the analysis are taken from the
    cache, so a run that was blocked by the AI provider can be finished
    without spending the platform's quota a second time.
    """
    from discovery_live import (
        DEFAULT_SEARCH_TOPICS,
        MAX_CANDIDATES,
        SearchFilters,
        discover_new_candidates,
        save_production_candidates,
    )
    from candidate_analysis import analyze_candidates
    from discover import STATUS_CANDIDATE_FOUND, filter_and_select
    from poster import read_keyword_search, read_keyword_searches

    config = _load_config()
    topic = str(topic or "").strip()
    discovery_config = dict(config.get("discovery", {}) or {})
    if topic:
        discovery_config["target_topic"] = topic
    else:
        # With no keyword from the admin, the default AI Music markets are
        # searched for. A run always has a subject.
        configured = str(discovery_config.get("target_topic", "")).strip()
        if not configured:
            configured = DEFAULT_SEARCH_TOPICS[0]
        discovery_config["target_topic"] = configured
    config["discovery"] = discovery_config

    search_filters = SearchFilters.from_payload(filters)
    funnel_raw = 0
    funnel_dedup = 0
    funnel_filtered = 0

    def _read(keyword: str) -> dict[str, Any]:
        return read_keyword_search(keyword)

    def _read_many(keywords: list[str]) -> dict[str, dict[str, Any]]:
        """Search every keyword in one Chrome session on one TikTok tab.

        The batched reader keeps the browser to a single session and a
        single tab, so the run does not open a new tab for every keyword.
        """
        return read_keyword_searches(keywords)

    def _should_stop() -> bool:
        if not job_id:
            return False
        with _STOP_LOCK:
            return job_id in _STOP_REQUESTED

    if resume:
        # The candidates of the last run are reused. No search is made, so
        # the platform's quota is not spent again and the run cannot fail
        # because of a new challenge.
        from discover import DiscoveredVideo

        stored = _load_last_result()
        stored_candidates = stored.get("all_candidates") or stored.get("candidates") or []
        if not stored_candidates:
            # The state file has no candidate list, so the production store
            # of the last run is used. It holds the full list of the run.
            try:
                from discovery_live import PRODUCTION_CANDIDATES_DIR
                import json as _json

                payload = _json.loads(
                    (PRODUCTION_CANDIDATES_DIR / "candidates.json").read_text(encoding="utf-8")
                )
                stored_candidates = payload.get("videos") or []
            except Exception:
                stored_candidates = []
        candidates = []
        for item in stored_candidates:
            if not isinstance(item, dict):
                continue
            try:
                candidates.append(DiscoveredVideo(**item))
            except TypeError:
                continue
        blockers = [
            "Tái dùng kết quả tìm kiếm đã lưu, không tìm kiếm lại TikTok."
        ]
        try:
            funnel_raw = len(candidates)
            funnel_dedup = len(candidates)
            funnel_filtered = len(candidates)
        except Exception:
            pass
    else:
        # The candidates are read without the filters here. The filter stage in
        # `filter_and_select` applies them once and records the reason for every
        # candidate it removes.
        collect_stats: dict[str, Any] = {}
        candidates, blockers = discover_new_candidates(
            config,
            topic,
            read_search=_read,
            read_searches=_read_many,
            should_stop=_should_stop,
            stats=collect_stats,
        )
        try:
            result_query_stats = dict(collect_stats)
        except Exception:
            result_query_stats = {}
        # Cheap metadata filters (views, age, keywords) run BEFORE the heavy
        # frame/Vision analysis, so a video already disqualified by views or
        # recency never costs a frame download. The later filter_and_select
        # re-applies the same filters idempotently on the content survivors.
        # Funnel: RAW = videos TikTok returned (sum raw_count),
        # DEDUP = unique videos collected (canonical ID/URL only).
        try:
            _raw_total = 0
            for _v in (result_query_stats or {}).values():
                try:
                    _raw_total += int((_v or {}).get("raw_count", 0) or 0)
                except (TypeError, ValueError):
                    continue
            funnel_raw = _raw_total
        except Exception:
            funnel_raw = 0
        funnel_dedup = len(candidates)
        # Strict gate FIRST (never lowered): views>=5000, 30-60s, age<=30d.
        # A 20s / 135d video NEVER enters FILTERED/VERIFIED/NEEDS_REVIEW/TOP5.
        try:
            from discovery_live import passes_strict_metadata as _strict_ok

            _strict_kept: list[Any] = []
            for _c in list(candidates):
                try:
                    _ok, _why = _strict_ok(_c)
                except Exception:
                    _ok, _why = False, "strict check failed"
                if _ok:
                    _strict_kept.append(_c)
                else:
                    blockers.append(
                        f"REJECTED strict — {getattr(_c, 'source_url', '')}: {_why}"
                    )
            blockers.append(
                f"Funnel RAW {funnel_raw} → DEDUP {funnel_dedup} → "
                f"FILTERED {len(_strict_kept)} (strict 5000 views/30-60s/<=30d)."
            )
            candidates = _strict_kept
        except Exception:
            pass
        try:
            from discovery_live import apply_search_filters as _prefilter

            pre_kept, pre_dropped = _prefilter(list(candidates), search_filters)
            for reason in pre_dropped:
                blockers.append(f"Loại theo bộ lọc — {reason}")
            prefilter_note = (
                f"Thu thập {len(candidates)} video từ {len(result_query_stats)} truy vấn; "
                f"lọc metadata giữ {len(pre_kept)}, loại {len(pre_dropped)} trước phân tích nội dung."
            )
            blockers.append(prefilter_note)
            candidates = pre_kept
        except Exception:
            result_query_stats = result_query_stats
        try:
            funnel_filtered = len(candidates)
        except Exception:
            funnel_filtered = 0
        try:
            global _LAST_QUERY_STATS
            _LAST_QUERY_STATS = dict(result_query_stats)
        except Exception:
            pass

    # The videos that are already in the library are not offered again.
    known_urls = set()
    try:
        from library import find_by_source

        for candidate in candidates:
            if find_by_source(candidate.source_url):
                known_urls.add(candidate.source_url)
    except Exception:
        pass

    # Every candidate is analysed on its own and the analyses are ranked, so
    # the run can show the score of all of them and explain the choice. The
    # analysis reads the real frames of every video through the authorised
    # session and asks the AI provider to judge the content itself. A
    # candidate whose content cannot be read is marked as not enough data
    # and is not ranked.
    from candidate_analysis import (
        ANALYZER_PROVIDER,
        CACHE_PATH,
        _cache_key,
        _decode_frames,
        load_cache,
        save_cache,
    )

    # One cache is shared by the frame reader and the analysis, so the
    # frames that were read are the frames the analysis judges. Nothing is
    # downloaded twice.
    frame_cache = load_cache(CACHE_PATH)

    # The frames are stored under the plain key and under the key of the
    # analyzer that read them. The reader looks at both, so a frame that
    # was read before is never read again.
    from candidate_analysis import _cache_key_prefix

    provider = str(ANALYZER_PROVIDER).strip().lower() or "local"
    key_prefix = _cache_key_prefix(provider)

    def _read_frames(candidate: Any) -> list[bytes]:
        """Read the real frames of a candidate through the authorised session.

        The frames that were read before are reused, so a run never fetches
        the same media twice and never spends the platform's quota on a
        video that was already read.
        """
        key = _cache_key(candidate)
        for lookup in (key, f"{key_prefix}:{key}"):
            entry = frame_cache.get(lookup)
            if isinstance(entry, dict):
                cached_frames = entry.get("frames")
                if isinstance(cached_frames, list):
                    frames = _decode_frames(cached_frames)
                    if frames:
                        return frames

        media_url = str(getattr(candidate, "download_url", "") or "").strip()
        if not media_url:
            return []
        referer = str(getattr(candidate, "source_url", "") or "")
        try:
            from poster import capture_video_frames

            frames = capture_video_frames(
                media_url,
                offsets=(0.5, 3.0, 8.0),
                referer=referer,
            )
        except Exception:
            return []
        if frames:
            # The frames are kept, so a later run does not download this
            # media again.
            from candidate_analysis import _encode_frames, _frames_digest

            frame_cache[key] = {
                "payload": None,
                "frames": _encode_frames(frames),
                "digest": _frames_digest(frames),
                "provider": "",
                "model": "",
                "error": "",
                "saved_at": datetime.now().isoformat(timespec="seconds"),
            }
            try:
                save_cache(frame_cache, CACHE_PATH)
            except Exception:
                pass
        return frames

    def _resolve_media(candidate: Any) -> str:
        """Return the local file of a candidate, when it is really there.

        The sound is measured only from a file that is already on the
        machine and that the rights check already allowed. Nothing is
        downloaded here.
        """
        try:
            return str(preview_path(source_url=str(getattr(candidate, "source_url", ""))))
        except Exception:
            return ""

    analyses = analyze_candidates(
        candidates,
        topic or discovery_config["target_topic"],
        frame_reader=_read_frames,
        cache=frame_cache,
        media_resolver=_resolve_media,
    )
    analysis_by_url = {item.source_url: item for item in analyses}

    # The full candidate list of the run is kept, before the content gate.
    # It is what a later resume reuses, so a run that was blocked by the AI
    # provider can be finished without searching TikTok again.
    all_candidates = list(candidates)

    # The content check is the gate. VERIFIED (content_relevant is True)
    # stays eligible for auto-select. NEEDS_REVIEW (content_relevant is
    # None) passed the metadata filters but has no content proof: it stays
    # visible and scored, but can never auto-post — only a manual user
    # confirmation plus the rights/approval gates can move it forward.
    # REJECTED (content_relevant is False, or no analysis) is dropped.
    # Captions/hashtags/"AI" text are never treated as content proof.
    relevant_urls = {
        item.source_url
        for item in analyses
        if item.content_relevant is True
    }
    from discovery_live import candidate_age_days as _age_days
    dropped: list[Any] = []
    verified_candidates: list[Any] = []
    needs_review_candidates: list[Any] = []
    needs_review_info: list[dict[str, Any]] = []
    for candidate in candidates:
        analysis = analysis_by_url.get(candidate.source_url)
        if analysis is None:
            dropped.append(candidate)
            blockers.append(
                f"REJECTED — @{candidate.creator}: không có kết quả phân tích nội dung."
            )
            continue
        if analysis.content_relevant is True:
            verified_candidates.append(candidate)
            continue
        if analysis.content_relevant is False:
            dropped.append(candidate)
            reason = (
                analysis.content_relevance_reason
                or analysis.insufficient_reason
                or "không đủ dữ liệu nội dung"
            )
            reason = "nội dung thật không phải AI Music — " + reason
            blockers.append(f"REJECTED — @{candidate.creator}: {reason}")
            continue
        # UNKNOWN: keep for NEEDS_REVIEW (metadata already passed here).
        needs_review_candidates.append(candidate)
        reason = (
            analysis.content_relevance_reason
            or analysis.insufficient_reason
            or "không đủ dữ liệu nội dung"
        )
        posted = str(getattr(candidate, "posted_at", "") or "")
        try:
            age_days = _age_days(candidate)
        except Exception:
            age_days = None
        needs_review_info.append({
            "source_url": candidate.source_url,
            "creator": str(getattr(candidate, "creator", "") or ""),
            "title": str(getattr(candidate, "title", "") or ""),
            "views": int(getattr(candidate, "views", 0) or 0),
            "posted_at": posted,
            "age_days": age_days,
            "reason": "CHƯA ĐỦ DỮ LIỆU — " + reason,
        })
        blockers.append(
            f"NEEDS_REVIEW — @{candidate.creator}: đạt metadata, {reason}. "
            "Chờ người dùng xác minh, không tự đăng."
        )

    # Only VERIFIED + NEEDS_REVIEW reach the trending scorer. Weights are
    # untouched; NEEDS_REVIEW keeps its real views/age/score for display.
    candidates = list(verified_candidates) + list(needs_review_candidates)

    selection = filter_and_select(
        candidates, config, topic=topic, filters=search_filters, known_urls=known_urls
    )
    # Safety gate: auto-select only ever considers VERIFIED content.
    # NEEDS_REVIEW keeps its real trend score for display in TOP 5 but can
    # never become `selection.selected`, so no auto-post/scheduler path can
    # pick it up. Only a manual user confirmation + rights/approval gates
    # (via discovery_approve) can move it forward.
    try:
        _verified_urls = {c.source_url for c in verified_candidates}
        if selection.selected is not None and selection.selected.source_url not in _verified_urls:
            selection.selected = None
            selection.selected_score = None
            from discover import STATUS_NO_QUALIFIED_VIDEO as _NOQ
            if selection.status != _NOQ:
                selection.status = _NOQ
    except Exception:
        pass

    # The AI content analysis decides which video is the best one. The
    # trending score that the filter stage computed stays as the secondary
    # signal, and the video the content analysis put first is the video the
    # admin is asked to approve.
    ranked_analyses = [item for item in analyses if item.ranked]
    if ranked_analyses:
        top = ranked_analyses[0]
        chosen_video = next(
            (
                candidate
                for candidate in selection.candidates
                if candidate.source_url == top.source_url
            ),
            None,
        )
        if chosen_video is None:
            # The top video was dropped by the search filters. The next
            # ranked candidate that survived the filters takes its place.
            for item in ranked_analyses[1:]:
                chosen_video = next(
                    (
                        candidate
                        for candidate in selection.candidates
                        if candidate.source_url == item.source_url
                    ),
                    None,
                )
                if chosen_video is not None:
                    top = item
                    break
        if chosen_video is not None:
            selection.selected = chosen_video
            selection.status = STATUS_CANDIDATE_FOUND
            top_score = next(
                (
                    score
                    for score in selection.scores
                    if score.video.source_url == chosen_video.source_url
                ),
                None,
            )
            if top_score is not None:
                selection.selected_score = top_score

    all_blockers = list(blockers) + list(selection.blockers)

    # The reason the AI could not judge a video is reported, so the admin
    # sees the real blocker instead of an empty result. A video that was
    # never judged by the AI is never presented as a match.
    ai_errors = sorted(
        {
            str(item.insufficient_reason or "")
            for item in analyses
            if item.content_relevant is None
            and item.insufficient_reason
            and "không đọc được khung hình" not in item.insufficient_reason
        }
    )
    for reason in ai_errors:
        all_blockers.append("AI chưa phân tích được: " + reason)

    # The full list of the run is written to the production store, so a
    # later resume has the candidates even when the content gate left none
    # of them qualified.
    save_production_candidates(
        all_candidates, topic=topic, blockers=all_blockers
    )

    result = selection.to_dict()
    result["status"] = _run_status(selection, all_blockers)
    try:
        from discovery_live import TOP5_LIMIT, build_top5_cards, language_market_note

        top5_cards = build_top5_cards(
            list(selection.scores or []),
            config,
            analyses_by_url=analysis_by_url,
            limit=TOP5_LIMIT,
            subtopics=list(search_filters.subtopics or []),
        )
        # Attach manual content-confirmation state (stored separately from
        # model evidence) so the dashboard can show it. NEEDS_REVIEW cards
        # keep pick=False: they never auto-post.
        try:
            _confirm_map = _read_json(STATE_DIR / "discovery_content_confirm.json", {}) or {}
        except Exception:
            _confirm_map = {}
        if not isinstance(_confirm_map, dict):
            _confirm_map = {}
        for card in top5_cards:
            try:
                entry = _confirm_map.get(str(card.get("source_url", "")), {})
                card["user_confirmed"] = bool(isinstance(entry, dict) and entry.get("user_confirmed") is True)
            except Exception:
                card["user_confirmed"] = False
        result["top5"] = top5_cards
        try:
            result["applied_filters"] = search_filters.to_dict()
        except Exception:
            result["applied_filters"] = {}
        note = language_market_note(search_filters)
        if note:
            result["language_market_note"] = note
            all_blockers.append(note)
        try:
            from discovery_live import MAX_TOPIC_QUERIES, expand_topic_queries as _expand_q

            result["topic_queries"] = _expand_q(topic, max_queries=MAX_TOPIC_QUERIES) or [topic]
        except Exception:
            result["topic_queries"] = [topic]
        try:
            result["query_stats"] = dict(_LAST_QUERY_STATS)
            stats_total = sum(int((v or {}).get("returned", 0)) for v in _LAST_QUERY_STATS.values())
            result["query_total_returned"] = stats_total
        except Exception:
            result["query_stats"] = {}
            result["query_total_returned"] = 0
    except Exception:
        result.setdefault("top5", [])
    result["mode"] = str(_load_settings().get("mode", config.get("mode", "approve")))
    result["downloaded"] = False
    result["eligibility"] = _eligibility_report(selection)
    result["analyses"] = [item.to_dict() for item in analyses]
    result["candidate_count"] = len(candidates)
    result["candidate_limit"] = MAX_CANDIDATES
    # Explicit verification buckets: VERIFIED can auto-advance through the
    # gates; NEEDS_REVIEW passed metadata but has no content proof and can
    # never auto-post; REJECTED failed metadata or is confirmed non-AI.
    try:
        _score_by_url = {
            s.video.source_url: int(s.score or 0)
            for s in (selection.scores or [])
            if getattr(s, "video", None) is not None
        }
    except Exception:
        _score_by_url = {}
    try:
        _confirm_map = _read_json(STATE_DIR / "discovery_content_confirm.json", {}) or {}
    except Exception:
        _confirm_map = {}
    if not isinstance(_confirm_map, dict):
        _confirm_map = {}
    try:
        from discovery_live import rights_status_of as _rights_of
        for _info in needs_review_info:
            try:
                _entry = _confirm_map.get(str(_info.get("source_url", "")), {})
                _info["user_confirmed"] = bool(isinstance(_entry, dict) and _entry.get("user_confirmed") is True)
            except Exception:
                _info["user_confirmed"] = False
            _info["trend_score"] = int(_score_by_url.get(str(_info.get("source_url", "")), 0) or 0)
            try:
                _info["rights"] = _rights_of(str(_info.get("source_url", "")), config)
            except Exception:
                _info["rights"] = "UNKNOWN"
    except Exception:
        pass
    result["needs_review"] = list(needs_review_info)
    result["verification"] = {
        "verified": len(verified_candidates),
        "needs_review": len(needs_review_candidates),
        "rejected": len(dropped),
    }
    # Funnel counts: RAW (TikTok) → DEDUP (canonical ID/URL) →
    # FILTERED (strict metadata) → VERIFIED / NEEDS_REVIEW.
    try:
        _funnel = {
            "raw": int(funnel_raw or 0),
            "dedup": int(funnel_dedup or 0),
            "filtered": int(funnel_filtered or 0),
            "verified": int(len(verified_candidates)),
            "needs_review": int(len(needs_review_candidates)),
            "rejected": int(len(dropped)),
        }
    except Exception:
        _funnel = {
            "raw": 0, "dedup": 0, "filtered": 0,
            "verified": 0, "needs_review": 0, "rejected": 0,
        }
    result["funnel"] = _funnel
    # The full list of the run is kept next to the qualified candidates, so
    # a resume can reuse it without searching TikTok again.
    result["all_candidates"] = [item.to_dict() for item in all_candidates]
    result["all_candidate_count"] = len(all_candidates)
    result["analysis_summary"] = _analysis_summary(analyses, selection, topic)
    result["ranked_count"] = len(ranked_analyses)
    result["insufficient_count"] = len(analyses) - len(ranked_analyses)
    result["dropped_count"] = len(dropped)
    result["ai_blockers"] = ai_errors
    if len(candidates) < MAX_CANDIDATES:
        result["shortfall_note"] = (
            f"TikTok trả về nhiều video hơn, nhưng chỉ {len(candidates)} video "
            f"được xác nhận là AI Music từ nội dung thật "
            f"(giới hạn {MAX_CANDIDATES}). "
            f"{len(dropped)} video bị loại do nội dung không khớp hoặc chưa đủ dữ liệu. "
            f"Không thêm video không liên quan để lấp chỗ trống."
        )
    # The chosen video carries its own analysis, so the dashboard can show
    # why it was chosen.
    if selection.selected is not None:
        chosen = analysis_by_url.get(selection.selected.source_url)
        if chosen is not None:
            result["selected_analysis"] = chosen.to_dict()

    # The result is written to the state file here, so it survives a
    # dashboard reload and a server restart. Reading the dashboard never
    # runs a search again; it only reads this file.
    _remember_result(result)
    return result


def _analysis_summary(analyses: list[Any], selection: Any, topic: str) -> str:
    """Return a short summary of the analysis for the run."""
    if not analyses:
        return "Không có video nào để phân tích."
    ranked = [item for item in analyses if getattr(item, "ranked", True)]
    rejected = [
        item for item in analyses if getattr(item, "content_relevant", None) is False
    ]
    no_data = [
        item
        for item in analyses
        if getattr(item, "content_relevant", None) is None
    ]
    if not ranked:
        return (
            f"Đã đọc nội dung thật của {len(analyses)} video nhưng không video nào "
            f"được xác nhận là AI Music: "
            f"{len(rejected)} video không phải AI Music, "
            f"{len(no_data)} video chưa đủ dữ liệu nội dung để kết luận. "
            f"Không có video nào được xếp hạng."
        )
    best = ranked[0]
    lines = [
        f"Đã phân tích nội dung thật của {len(analyses)} video; "
        f"{len(ranked)} video được xác nhận là AI Music và xếp hạng theo chủ đề '{topic}'.",
        f"Video tốt nhất: @{best.creator} — điểm {best.score}/100. {best.summary}",
    ]
    if rejected or no_data:
        lines.append(
            f"Đã loại {len(rejected)} video không phải AI Music và "
            f"{len(no_data)} video chưa đủ dữ liệu nội dung."
        )
    return "\n".join(lines)


def _run_status(selection: Any, blockers: list[str]) -> str:
    """Return the status the dashboard shows for a discovery run."""
    from discover import (
        STATUS_BLOCKED,
        STATUS_CANDIDATE_FOUND,
        STATUS_ERROR,
        STATUS_NO_QUALIFIED_VIDEO,
    )

    if selection.status == STATUS_CANDIDATE_FOUND:
        return STATUS_CANDIDATE_FOUND
    if selection.status == STATUS_NO_QUALIFIED_VIDEO:
        # A run that was blocked on every source is a block, not an empty
        # result. The reason stays visible either way.
        if blockers and not selection.candidates and all(
            "Blocked:" in str(item) for item in blockers
        ):
            return STATUS_BLOCKED
        return STATUS_NO_QUALIFIED_VIDEO
    return STATUS_ERROR


def _eligibility_report(selection: Any) -> dict[str, Any]:
    """Report the download capability and the reuse rights separately.

    The technical check says whether the media URL can be fetched. The reuse
    permission comes from the rights allowlist and is never inferred from
    the technical result, so the two are always shown apart.
    """
    from eligibility import check_candidate
    from discover import validate_source_permitted

    if selection.selected is None:
        return {
            "checked": False,
            "note": "Chưa có video nào được chọn nên chưa kiểm tra khả năng tải.",
        }

    candidate = selection.selected
    reuse_permitted = False
    reuse_reason = ""
    try:
        validate_source_permitted(candidate.source_url, _load_config())
        reuse_permitted = True
        reuse_reason = "Nguồn có quyền tái sử dụng đã được xác minh trong allowlist."
    except Exception as exc:  # noqa: BLE001 - the reason is shown
        reuse_reason = str(exc)

    result = check_candidate(
        candidate,
        media_url=candidate.download_url,
        reuse_permitted=reuse_permitted,
        reuse_reason=reuse_reason,
    )
    return {
        "checked": True,
        "source_url": candidate.source_url,
        "download_capable": result.eligible,
        "media_host": result.media_host,
        "format_ok": result.format_ok,
        "duration_ok": result.duration_ok,
        "reasons": list(result.reasons),
        "reuse_permitted": reuse_permitted,
        "reuse_reason": reuse_reason,
        "note": (
            "Khả năng tải là kiểm tra kỹ thuật. Quyền tái sử dụng là quyền pháp lý "
            "và không suy ra từ khả năng tải. File chỉ được tải sau khi được duyệt."
        ),
    }


def run_discovery_job(
    topic: str = "",
    filters: dict[str, Any] | None = None,
    resume: bool = False,
) -> BackgroundJob:
    """Start a live discovery in the background and return the job.

    With ``resume`` the candidates of the last run are reused and the
    analysis is finished from the cache. No new search is made, so a run
    that was blocked by the AI provider can be completed without spending
    the platform's quota again.
    """
    job = BackgroundJob(
        job_id=f"job-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        kind="discovery",
        task_id="",
        status="RUNNING",
        started_at=datetime.now().isoformat(),
        message="SEARCHING",
    )
    JOBS.start(job)

    def _work() -> None:
        try:
            result = _discovery_request(
                topic=topic,
                filters=filters,
                job_id=job.job_id,
                resume=resume,
            )
            status = str(result.get("status", ""))
            message = {
                "CANDIDATE_FOUND": (
                    f"Đã chọn 1 video: {result['selected']['source_url']}"
                    if result.get("selected")
                    else "CANDIDATE_FOUND"
                ),
                "NO_QUALIFIED_VIDEO": "NO_QUALIFIED_VIDEO",
                "BLOCKED": "BLOCKED",
                "ERROR": "ERROR",
            }.get(status, status)
            JOBS.update(
                job.job_id,
                status="COMPLETED",
                finished_at=datetime.now().isoformat(),
                message=message,
                detail=result,
            )
            # The result was already written to the state file by the
            # discovery request itself, so a reload of the dashboard shows
            # this run without running the search again.
            add_notification("discovery", message, {"status": status})
        except Exception as exc:  # noqa: BLE001 - the reason is shown
            JOBS.update(
                job.job_id,
                status="FAILED",
                finished_at=datetime.now().isoformat(),
                message=f"ERROR: {exc}",
                detail={"status": "ERROR", "error": str(exc)},
            )
            add_notification("discovery", f"ERROR: {exc}", {"status": "ERROR"})

    threading.Thread(target=_work, name=f"toolt-dh-{job.job_id}", daemon=True).start()
    return job


def discovery_approve(source_url: str, topic: str = "") -> dict[str, Any]:
    """Put the selected video into a review record so it can be approved.

    Nothing is downloaded here. The review record only holds the candidate
    and its real metrics, and the download starts after the admin approves
    the task in the approval centre.
    """
    from review_stage import write_review

    result = _LAST_RESULT
    if not result:
        result = _load_last_result()
    if not isinstance(result, dict) or not result:
        raise ServiceError("No discovery result is available to approve.")

    selected = result.get("selected")
    if not selected:
        raise ServiceError(
            "The last run did not select a video, so there is nothing to approve. "
            "The run ended with " + str(result.get("status", "an unknown status")) + "."
        )
    if str(selected.get("source_url", "")) != str(source_url):
        raise ServiceError(
            "That video is not the one the last run selected, so it is not approved."
        )

    topic = str(topic or result.get("topic", "")).strip()
    scores = result.get("scores", []) or []
    candidates = result.get("candidates", []) or []

    task_id = f"dash-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    write_review(
        task_id,
        candidates,
        scores,
        topic=topic,
        blockers=list(result.get("blockers", []) or []),
    )

    # The chosen video is recorded so the approval centre shows it.
    from review_stage import select_candidate

    index = None
    for position, candidate in enumerate(candidates, start=1):
        if str(candidate.get("source_url", "")) == str(source_url):
            index = position
            break
    if index is not None:
        select_candidate(task_id, index)

    return {
        "task_id": task_id,
        "source_url": source_url,
        "topic": topic,
        "downloaded": False,
        "note": "Video được chọn để duyệt. Chưa tải file nào.",
    }


def discovery_reject(source_url: str, reason: str = "") -> dict[str, Any]:
    """Record that the admin refused the video the run suggested.

    The refusal is stored with the reason the admin gave, so the choice is
    auditable. Nothing is downloaded and nothing is published; the video is
    simply not used.
    """
    result = _LAST_RESULT
    if not result:
        result = _load_last_result()
    if not isinstance(result, dict) or not result:
        raise ServiceError("No discovery result is available to reject.")

    selected = result.get("selected")
    if not selected:
        raise ServiceError(
            "The last run did not select a video, so there is nothing to reject."
        )
    if str(selected.get("source_url", "")) != str(source_url):
        raise ServiceError(
            "That video is not the one the last run selected, so it is not rejected."
        )

    note = str(reason or "").strip() or "Không có lý do được ghi."
    record = {
        "source_url": str(source_url),
        "creator": str(selected.get("creator", "")),
        "topic": str(result.get("topic", "")),
        "reason": note,
        "rejected_at": datetime.now().isoformat(),
        "downloaded": False,
    }
    _write_json(REJECTIONS_FILE, {**(_read_json(REJECTIONS_FILE, {}) or {}), str(source_url): record})
    add_notification("discovery", f"Đã từ chối video @{record['creator']}", record)

    return {
        "source_url": str(source_url),
        "creator": record["creator"],
        "reason": note,
        "downloaded": False,
        "note": "Video đã bị từ chối. Chưa tải và không đăng file nào.",
    }


def discovery_confirm_content(source_url: str = "") -> dict[str, Any]:
    """Record a manual user content confirmation for a NEEDS_REVIEW video.

    The confirmation is stored separately from model evidence: analyses
    keep content_relevant=None, while this store records user_confirmed.
    Nothing is downloaded; rights/approval gates still apply downstream.
    """
    wanted = str(source_url or "").strip()
    if not wanted:
        raise ServiceError("Không có URL video để xác nhận.")
    result = _LAST_RESULT or _load_last_result()
    if not isinstance(result, dict) or not result:
        raise ServiceError("No discovery result is available to confirm.")
    top5 = result.get("top5", []) if isinstance(result, dict) else []
    needs = result.get("needs_review", []) if isinstance(result, dict) else []
    known = {str(c.get("source_url", "")) for c in (list(top5) + list(needs))}
    if wanted not in known:
        raise ServiceError("Video không nằm trong danh sách NEEDS_REVIEW.")
    card = next((c for c in top5 if str(c.get("source_url", "")) == wanted), None)
    if card is not None and str(card.get("status", "")) == "VERIFIED":
        raise ServiceError("Video đã VERIFIED, không cần xác nhận thủ công.")
    store = STATE_DIR / "discovery_content_confirm.json"
    try:
        current = _read_json(store, {}) or {}
    except Exception:
        current = {}
    if not isinstance(current, dict):
        current = {}
    current[wanted] = {
        "source_url": wanted,
        "user_confirmed": True,
        "confirmed_at": datetime.now().isoformat(),
        "confirmed_by": "admin",
    }
    _write_json(store, current)
    # Reflect in the live result without touching model evidence.
    try:
        for c in result.get("top5", []) or []:
            if str(c.get("source_url", "")) == wanted:
                c["user_confirmed"] = True
        for n in result.get("needs_review", []) or []:
            if str(n.get("source_url", "")) == wanted:
                n["user_confirmed"] = True
        _remember_result(result)
    except Exception:
        pass
    return {"source_url": wanted, "user_confirmed": True, "downloaded": False,
            "note": "Đã ghi nhận xác minh thủ công. Vẫn cần quyền và approval trước khi tải/đăng."}


def discovery_dismiss_content(source_url: str = "", reason: str = "") -> dict[str, Any]:
    """Record a manual dismissal of a NEEDS_REVIEW video (no download)."""
    wanted = str(source_url or "").strip()
    if not wanted:
        raise ServiceError("Không có URL video để loại bỏ.")
    result = _LAST_RESULT or _load_last_result()
    if not isinstance(result, dict) or not result:
        raise ServiceError("No discovery result is available.")
    note = str(reason or "").strip() or "Người dùng loại bỏ sau khi xem NEEDS_REVIEW."
    store = STATE_DIR / "discovery_content_confirm.json"
    try:
        current = _read_json(store, {}) or {}
    except Exception:
        current = {}
    if not isinstance(current, dict):
        current = {}
    current[wanted] = {
        "source_url": wanted,
        "user_confirmed": False,
        "dismissed": True,
        "dismiss_reason": note,
        "dismissed_at": datetime.now().isoformat(),
    }
    _write_json(store, current)
    _write_json(REJECTIONS_FILE, {**(_read_json(REJECTIONS_FILE, {}) or {}), wanted: {
        "source_url": wanted, "reason": note,
        "rejected_at": datetime.now().isoformat(), "downloaded": False}})
    return {"source_url": wanted, "dismissed": True, "downloaded": False,
            "note": "Đã loại bỏ video. Chưa tải và không đăng."}


def discovery_stop(job_id: str) -> dict[str, Any]:
    """Ask a running discovery to stop.

    The flag is checked between the sources, so the run stops at the next
    source instead of in the middle of a page read.
    """
    with _STOP_LOCK:
        _STOP_REQUESTED.add(job_id)
    job = JOBS.get(job_id)
    if job is not None:
        JOBS.update(job_id, message="STOPPING")
    return {"job_id": job_id, "stop_requested": True}


# The result of the last discovery run, so the dashboard can show it again
# after a reload without running the search a second time.
_LAST_RESULT: dict[str, Any] = {}

# The result is also written to the state file, so a restart of the dashboard
# shows the last run instead of an empty page.
_LAST_RESULT_FILE = STATE_DIR / "discovery_last.json"


def _load_last_result() -> dict[str, Any]:
    """Read the last discovery result from the state file."""
    global _LAST_RESULT
    try:
        payload = _read_json(_LAST_RESULT_FILE, {})
    except Exception:
        payload = {}
    if isinstance(payload, dict) and payload.get("status"):
        _LAST_RESULT = payload
    return dict(_LAST_RESULT)


def discovery_last() -> dict[str, Any]:
    """Return the result of the last discovery run."""
    if not _LAST_RESULT:
        return _load_last_result()
    return dict(_LAST_RESULT)


def _remember_result(result: dict[str, Any]) -> None:
    """Store the last discovery result and write it to the state file."""
    global _LAST_RESULT
    _LAST_RESULT = result
    try:
        _write_json(_LAST_RESULT_FILE, result)
    except Exception:
        pass


def discovery_detail(source_url: str = "") -> dict[str, Any]:
    """Return the full detail of one candidate from the last discovery run.

    The candidate is looked up by its source URL, which is the only stable
    identifier the platform gives a video. The endpoint reports what it
    found and what is missing, so the dashboard can show a real reason
    instead of an empty panel.

    Nothing is downloaded and no candidate is chosen or approved here. The
    call only reads the result of the run that already happened.
    """
    result = _LAST_RESULT
    if not result:
        result = _load_last_result()
    if not isinstance(result, dict) or not result:
        raise ServiceError(
            "Chưa có kết quả tìm kiếm nào. Hãy chạy tìm kiếm trước khi xem chi tiết video."
        )

    wanted = str(source_url or "").strip()
    if not wanted:
        raise ServiceError("Không có URL video để xem chi tiết.")

    candidates = result.get("candidates", []) or []
    candidate = None
    for item in candidates:
        if isinstance(item, dict) and str(item.get("source_url", "")) == wanted:
            candidate = item
            break
    # NEEDS_REVIEW videos stay visible in TOP 5 / needs_review even when
    # they are not the selected candidate, so look there too.
    if candidate is None:
        for key in ("needs_review", "top5", "all_candidates"):
            for item in result.get(key, []) or []:
                if isinstance(item, dict) and str(item.get("source_url", "")) == wanted:
                    candidate = item
                    break
            if candidate is not None:
                break

    # The selected video is reported separately, so it is found even when
    # the candidate list does not carry it.
    selected = result.get("selected")
    if candidate is None and isinstance(selected, dict):
        if str(selected.get("source_url", "")) == wanted:
            candidate = selected

    if candidate is None:
        raise ServiceError(
            "Video này không có trong kết quả của lượt tìm kiếm gần nhất. "
            "Hãy chạy lại tìm kiếm rồi mở chi tiết video."
        )

    scores = result.get("scores", []) or []
    score = None
    for item in scores:
        if not isinstance(item, dict):
            continue
        video = item.get("video")
        if isinstance(video, dict) and str(video.get("source_url", "")) == wanted:
            score = item
            break

    # The download capability and the reuse rights are reported apart. The
    # check runs on the candidate that was actually selected, because the
    # eligibility check is only meaningful for the chosen video.
    eligibility = result.get("eligibility") or {}
    if isinstance(eligibility, dict) and str(eligibility.get("source_url", "")) != wanted:
        eligibility = {"checked": False, "note": "Chưa kiểm tra khả năng tải cho video này."}

    analysis = None
    for item in result.get("analyses", []) or []:
        if isinstance(item, dict) and str(item.get("source_url", "")) == wanted:
            analysis = item
            break
    verification = "REJECTED"
    try:
        for c in result.get("top5", []) or []:
            if isinstance(c, dict) and str(c.get("source_url", "")) == wanted:
                verification = str(c.get("status", "")) or verification
                break
        if verification == "REJECTED":
            for n in result.get("needs_review", []) or []:
                if isinstance(n, dict) and str(n.get("source_url", "")) == wanted:
                    verification = "NEEDS_REVIEW"
                    break
        if isinstance(analysis, dict) and analysis.get("content_relevant") is True:
            verification = "VERIFIED"
    except Exception:
        pass
    try:
        _cmap = _read_json(STATE_DIR / "discovery_content_confirm.json", {}) or {}
    except Exception:
        _cmap = {}
    _entry = _cmap.get(wanted, {}) if isinstance(_cmap, dict) else {}
    user_confirmed = bool(isinstance(_entry, dict) and _entry.get("user_confirmed") is True)
    if isinstance(candidate, dict) and not candidate.get("user_confirmed") and user_confirmed:
        candidate = {**candidate, "user_confirmed": True}

    return {
        "source_url": wanted,
        "topic": str(result.get("topic", "")),
        "run_status": str(result.get("status", "")),
        "candidate": candidate,
        "score": score,
        "analysis": analysis,
        "verification_status": verification,
        "user_confirmed": user_confirmed,
        "selected": bool(
            isinstance(selected, dict) and str(selected.get("source_url", "")) == wanted
        ),
        "eligibility": eligibility,
        "downloaded": bool(result.get("downloaded", False)),
        "mode": str(result.get("mode", "")),
        "missing_metrics": list(candidate.get("missing_metrics", []) or []),
    }


def preview_path(source_url: str = "", task_id: str = "") -> Path:
    """Return the local video file of a candidate, when there is one.

    The preview only plays a video that is already on this machine. The
    file has to live in one of the preview directories, so a request can
    never reach an arbitrary path.

    Nothing is downloaded here. A video that has not been downloaded yet has
    no preview, and the caller is told so.
    """
    wanted = str(source_url or "").strip()
    if not wanted:
        raise ServiceError("Không có URL video để xem trước.")

    roots = [root.resolve() for root in PREVIEW_DIRS if root.exists()]
    for root in roots:
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {
                ".mp4", ".webm", ".mov", ".m4v", ".mkv"
            }:
                continue
            if path.stem == "":
                continue
            metadata = path.with_suffix(".json")
            if metadata.exists():
                try:
                    payload = json.loads(metadata.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if str(payload.get("source", "")).strip() == wanted:
                    return path
            # The task id is used when the video was saved under a task name.
            if task_id and path.stem == str(task_id):
                return path
    raise ServiceError(
        "Video này chưa được tải về máy nên chưa có bản xem trước. "
        "Bản xem trước chỉ dùng được sau khi video đã tải và có quyền sử dụng hợp lệ."
    )


def preview_frames(source_url: str = "") -> bytes:
    """Return the real frames that were read from a candidate.

    The frames are the picture of the video that the analysis judged. They
    are kept in the analysis cache, so the dashboard can show the content of
    a candidate even when the video itself was not downloaded. Nothing is
    downloaded here; only the frames that were already read are returned.
    """
    wanted = str(source_url or "").strip()
    if not wanted:
        raise ServiceError("Không có URL video để xem trước.")

    from candidate_analysis import _decode_frames, _video_id_from_url, load_cache

    cache = load_cache()
    key = _video_id_from_url(wanted)
    entry = cache.get(key) if key else None
    if not isinstance(entry, dict):
        raise ServiceError(
            "Chưa có khung hình nào được đọc cho video này nên chưa có bản xem trước."
        )
    frames = _decode_frames(entry.get("frames") or [])
    if not frames:
        raise ServiceError(
            "Chưa có khung hình nào được đọc cho video này nên chưa có bản xem trước."
        )
    return frames[0]


def preview_media(source_url: str = "", task_id: str = "") -> dict[str, Any]:
    """Return the preview file of a candidate for the dashboard player.

    The path is returned so the server can stream the file. The endpoint
    downloads nothing; it only finds a file that is already on disk.
    """
    path = preview_path(source_url=source_url, task_id=task_id)
    return {
        "path": str(path),
        "name": path.name,
        "size_bytes": path.stat().st_size,
    }


def reanalyze_with_media(source_url: str = "", task_id: str = "") -> dict[str, Any]:
    """Judge a candidate again, now that its media is on the machine.

    The discovery judges the frames, because the media is not downloaded
    before the admin approved it and the rights were checked. Once the
    media is on the disk, the sound can really be measured, so the
    candidate is judged again with the sound included.

    Nothing is downloaded here. The file that is already on the machine is
    used, and the result is written back into the analysis cache, so the
    next run reuses it.
    """
    wanted = str(source_url or "").strip()
    if not wanted:
        raise ServiceError("Không có URL video để phân tích lại.")

    from candidate_analysis import (
        _cache_key_prefix,
        _decode_frames,
        _encode_frames,
        _frames_digest,
        _metadata_for,
        _video_id_from_url,
        load_cache,
        request_local_analysis,
        save_cache,
    )
    from discover import DiscoveredVideo

    path = preview_path(source_url=wanted, task_id=task_id)
    if not path.exists():
        raise ServiceError(
            "Video chưa được tải về nên chưa đo được âm thanh. "
            "Hãy duyệt tải video trước."
        )

    cache = load_cache()
    key = _video_id_from_url(wanted)
    entry = cache.get(key) if key else None
    frames = _decode_frames((entry or {}).get("frames") or [])
    if not frames:
        raise ServiceError(
            "Chưa có khung hình nào được đọc cho video này nên chưa phân tích lại được."
        )

    result = _LAST_RESULT or {}
    video = None
    for item in result.get("all_candidates") or []:
        if str(item.get("source_url", "")) == wanted:
            video = DiscoveredVideo(**item)
            break
    if video is None:
        raise ServiceError("Không tìm thấy video này trong lần tìm kiếm gần nhất.")

    metadata = _metadata_for(video)
    payload = request_local_analysis(frames, metadata, media_path=str(path))

    prefix = _cache_key_prefix("local")
    cache[f"{prefix}:{key}"] = {
        "payload": payload,
        "frames": _encode_frames(frames),
        "digest": _frames_digest(frames),
        "provider": "local",
        "model": "",
        "analyzer_version": payload.get("local_analyzer_version", ""),
        "saved_at": datetime.now().isoformat(timespec="seconds"),
    }
    save_cache(cache)

    music = payload.get("music_quality_reason", "")
    return {
        "source_url": wanted,
        "media": str(path),
        "music_quality": payload.get("music_quality", 0),
        "music_quality_known": bool(payload.get("music_quality_known")),
        "music_quality_reason": music,
        "content_is_ai_music": payload.get("content_is_ai_music"),
    }


def discovery_search(
    topic: str = "",
    filters: dict[str, Any] | None = None,
    resume: bool = False,
) -> dict[str, Any]:
    """Run a discovery and return its result.

    The run happens in a worker thread so the page stays responsive. The
    result is stored so the dashboard can show it after a reload.

    With ``resume`` the candidates of the last run are reused and no new
    search is made.
    """
    job = run_discovery_job(topic=topic, filters=filters, resume=resume)
    return job.to_dict()


# ---------------------------------------------------------------- P1 projects


def p1_projects_list() -> dict[str, Any]:
    """List P1 projects (offline, SQLite)."""
    import project_store as _store

    return {"projects": _store.list_projects()}


def p1_project_create(name: str = "", topic: str = "") -> dict[str, Any]:
    """Create one P1 project per topic (offline, SQLite)."""
    import project_store as _store

    return {"project": _store.create_project(name, topic)}


def p1_runs_list(project_id: str = "") -> dict[str, Any]:
    """List run versions of one project (offline, SQLite)."""
    import project_store as _store

    if not str(project_id or "").strip():
        raise ServiceError("project_id is required.")
    return {"project_id": project_id, "runs": _store.list_runs(project_id)}


def p1_run_get(project_id: str = "", run_id: str = "") -> dict[str, Any]:
    """Open one saved run version offline (SQLite only, never TikTok)."""
    import project_store as _store

    if not str(run_id or "").strip():
        raise ServiceError("run_id is required.")
    run = _store.get_run(run_id)
    if project_id and str(run.get("project_id", "")) != str(project_id):
        raise ServiceError("Run does not belong to this project.")
    return {"run": run}


def p1_search(
    project_id: str = "",
    topic: str = "",
    filters: dict[str, Any] | None = None,
    retry_key: str = "",
) -> dict[str, Any]:
    """Run one P1 search -> new immutable run version (collector = live TikTok).

    Pipeline: plan -> collect -> dedup -> UI filters -> relevance ->
    trend ranking -> TOP5. No AI. One call creates at most one version;
    ``retry_key`` makes retries idempotent (no duplicate versions).
    """
    import project_store as _store
    import p1_pipeline as _pipe

    if not str(project_id or "").strip():
        raise ServiceError("project_id is required.")
    topic = str(topic or "").strip()
    if not topic:
        raise ServiceError("topic is required.")
    retry_key = str(retry_key or "").strip()

    if retry_key:
        existing = _store.get_run_by_key(retry_key)
        if existing is not None:
            return {"run": existing, "deduplicated": True, "top5": existing.get("top5_json", "[]")}

    def _live_collector(query: str) -> list[dict]:
        from poster import read_keyword_search
        from discovery_live import parse_search_results

        payload = read_keyword_search(query)
        body = str((payload or {}).get("results", "") or "")
        if not body.strip():
            return []
        try:
            metrics = parse_search_results(body)
        except Exception:
            return []
        out: list[dict] = []
        for m in metrics:
            out.append({
                "source_url": m.source_url,
                "creator": m.creator,
                "title": m.title,
                "views": m.views or 0,
                "likes": m.likes or 0,
                "comments": m.comments or 0,
                "shares": m.shares or 0,
                "duration_seconds": m.duration_seconds or 0.0,
                "posted_at": m.posted_at or "",
                "missing_metrics": list(m.missing_metrics or []),
            })
        return out

    result = _pipe.run_pipeline(topic, _live_collector, filters=filters, retry_key=retry_key)
    saved = _store.create_run(
        project_id,
        filters=result["filters"],
        queries=result["queries"],
        funnel=result["funnel"],
        top5=result["top5"],
        videos=result["videos"],
        status="COMPLETED",
        idempotency_key=retry_key,
    )
    # Remember as last discovery result so the existing dashboard panels
    # (TOP5/candidates/detail) keep working with no rewrite.
    try:
        _remember_result({
            "topic": topic,
            "status": "COMPLETED",
            "top5": result["top5"],
            "funnel": result["funnel"],
            "project_id": project_id,
            "run_id": saved["run"]["id"],
            "version": saved["run"]["version"],
        })
    except Exception:
        pass
    return {"run": saved["run"], "deduplicated": bool(saved.get("deduplicated")), "top5": result["top5"],
            "funnel": result["funnel"], "queries": result["queries"]}


# ---------------------------------------------------------------- P2 video lab


def p2_video_detail(project_id: str = "", run_id: str = "", video_id: str = "") -> dict[str, Any]:
    """Video Lab detail from P1 SQLite (offline, no network)."""
    import p2_lab as _lab

    if not str(project_id or "").strip() or not str(run_id or "").strip() or not str(video_id or "").strip():
        raise ServiceError("project_id, run_id and video_id are required.")
    try:
        return {"video": _lab.video_detail(project_id, run_id, video_id)}
    except KeyError as exc:
        raise ServiceError(str(exc))


def p2_video_analyze(project_id: str = "", run_id: str = "", video_id: str = "",
                     local_path: str = "") -> dict[str, Any]:
    """Analyze one downloaded/imported MP4 (measured data, cached). No AI."""
    import p2_lab as _lab

    if not str(video_id or "").strip():
        raise ServiceError("video_id is required.")
    asset = _lab.get_asset(str(video_id))
    path = str(local_path or "").strip() or str((asset or {}).get("local_path", ""))
    if not path:
        raise ServiceError("Video chưa được tải/import nên chưa phân tích được.")
    try:
        return {"analysis": _lab.analyze_media(path)}
    except FileNotFoundError as exc:
        raise ServiceError(str(exc))
    except RuntimeError as exc:
        raise ServiceError(str(exc))


def p2_auto_download(project_id: str = "", run_id: str = "",
                     media_map: dict[str, Any] | None = None) -> dict[str, Any]:
    """Auto Download Best: pick best permitted video, download only it."""
    import p2_lab as _lab

    if not str(project_id or "").strip() or not str(run_id or "").strip():
        raise ServiceError("project_id and run_id are required.")
    mmap = {str(k): str(v) for k, v in (dict(media_map or {}).items())}
    return _lab.auto_download_best(project_id, run_id, media_map=mmap)


def p2_settings_get() -> dict[str, Any]:
    import p2_lab as _lab

    return _lab.settings_get()


def p2_settings_set(enabled: bool = False) -> dict[str, Any]:
    import p2_lab as _lab

    return _lab.settings_set(bool(enabled))


# ---------------------------------------------------------------- P3 publishing


def _p3db() -> Any:
    from pathlib import Path as _P

    import os as _os

    return _P(_os.environ.get("P1_DB_PATH", "data/state/p1_projects.db"))


def p3_publications_list() -> dict[str, Any]:
    import p3_publish as _pub

    return {"publications": _pub.list_publications(_p3db())}


def p3_publication_create(project_id: str = "", run_id: str = "", video_id: str = "") -> dict[str, Any]:
    import p3_publish as _pub

    if not str(project_id or "").strip() or not str(run_id or "").strip() or not str(video_id or "").strip():
        raise ServiceError("project_id, run_id và video_id là bắt buộc.")
    try:
        return _pub.create_publication(project_id, run_id, video_id, _p3db())
    except KeyError as exc:
        raise ServiceError(str(exc))


def p3_caption_build(publication_id: str = "") -> dict[str, Any]:
    import p3_publish as _pub

    try:
        conn_pub = _pub.get_publication(publication_id, _p3db())
    except KeyError as exc:
        raise ServiceError(str(exc))
    import project_store as _store

    run = _store.get_run(str(conn_pub.get("run_id", "")))
    video = next((v for v in run.get("videos", []) if str(v.get("id", "")) == str(conn_pub.get("video_id", ""))), {})
    topic = ""
    try:
        for _p in _store.list_projects():
            if str(_p.get("id", "")) == str(conn_pub.get("project_id", "")):
                topic = str(_p.get("topic", "") or "")
                break
    except Exception:
        topic = ""
    built = _pub.build_caption(topic, str(video.get("creator", "")), str(video.get("title", "")))
    return {"publication_id": publication_id, **built}


def p3_caption_save(publication_id: str = "", caption: str = "", hashtags: list[str] | None = None) -> dict[str, Any]:
    import p3_publish as _pub

    try:
        return {"publication": _pub.save_caption(publication_id, caption, hashtags, _p3db())}
    except KeyError as exc:
        raise ServiceError(str(exc))
    except ValueError as exc:
        raise ServiceError(str(exc))


def p3_approve(publication_id: str = "") -> dict[str, Any]:
    import p3_publish as _pub

    try:
        return {"publication": _pub.approve(publication_id, _p3db())}
    except KeyError as exc:
        raise ServiceError(str(exc))
    except ValueError as exc:
        raise ServiceError(str(exc))


def p3_schedule(publication_id: str = "", scheduled_at: str = "", account: str = "") -> dict[str, Any]:
    import p3_publish as _pub

    try:
        return {"publication": _pub.schedule(publication_id, scheduled_at, account, _p3db())}
    except KeyError as exc:
        raise ServiceError(str(exc))
    except ValueError as exc:
        raise ServiceError(str(exc))


def _p3_publisher() -> Any:
    """Return the real publisher adapter for the P3 worker (single source)."""
    import p3_publish as _pub

    return _pub.real_publisher(_load_config())


def p3_run_due() -> dict[str, Any]:
    """Worker entry: process due publications once (called by scheduler thread too)."""
    import p3_publish as _pub

    if not _pub.settings_get()["auto_publish"]:
        return {"status": "AUTO_OFF", "outcomes": [], "reason": "Auto Publish đang TẮT."}
    settings = _load_settings()
    if bool(settings.get("emergency_stop", False)):
        return {"status": "STOPPED", "outcomes": [], "reason": "Emergency stop đang bật."}
    config = _load_config()
    expected = str(config.get("expected_account", "") or "").strip().lstrip("@")
    outcomes = _pub.run_due(publisher=_p3_publisher(), expected_account=expected, db_path=_p3db())
    return {"status": "OK", "outcomes": outcomes}


def p3_settings_get() -> dict[str, Any]:
    import p3_publish as _pub

    return _pub.settings_get()


def p3_settings_set(enabled: bool = False) -> dict[str, Any]:
    import p3_publish as _pub

    return _pub.settings_set(bool(enabled))


# ---------------------------------------------------------------- review


def review_list(task_id: str = "") -> dict[str, Any]:
    """Return the review records for the dashboard."""
    records = _review_records()
    if task_id:
        records = [record for record in records if record.get("task_id") == task_id]
    return {"reviews": records}


def select_review_candidate(task_id: str, index: int) -> dict[str, Any]:
    """Record the user's choice in a review record."""
    from review_stage import select_candidate

    candidate = select_candidate(task_id, index)
    if candidate is None:
        raise ServiceError(
            f"No candidate with index {index} was found in the review for {task_id}."
        )
    return {"task_id": task_id, "selected": candidate.to_dict()}


def update_review_caption(task_id: str, caption: str, hashtags: list[str]) -> dict[str, Any]:
    """Save the user's edited caption and hashtags for a review."""
    path = REVIEW_DIR / f"{task_id}-review.json"
    payload = _read_json(path, None)
    if not isinstance(payload, dict):
        raise ServiceError(f"No review was found for {task_id}.")
    payload["caption"] = str(caption)
    payload["hashtags"] = [str(tag) for tag in hashtags]
    payload["caption_edited_at"] = datetime.now().isoformat()
    payload["status"] = "CAPTION_EDITED"
    _write_json(path, payload)
    return payload


# ---------------------------------------------------------------- tasks


def tasks_list() -> dict[str, Any]:
    """Return every persisted task state."""
    return {"tasks": _list_task_states()}


def task_detail(task_id: str) -> dict[str, Any]:
    """Return one task with its state and workflow record."""
    from workflow import load_resume_state

    state = load_task_state(task_id)
    workflow_state = _read_json(TASKS_DIR / f"{task_id}-workflow.json", {})
    review = _read_json(REVIEW_DIR / f"{task_id}-review.json", {})
    return {
        "task_id": task_id,
        "state": state,
        "workflow": workflow_state,
        "review": review,
    }


def run_task_job(task_id: str) -> BackgroundJob:
    """Start a full workflow run for a task in the background."""
    from main import load_config

    config = load_config()
    job = BackgroundJob(
        job_id=f"job-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        kind="workflow",
        task_id=task_id,
        started_at=datetime.now().isoformat(),
    )
    JOBS.start(job)

    def _work() -> None:
        try:
            from workflow import run_workflow, save_run_result

            result = run_workflow(
                config,
                PRODUCTION_DIR / "candidates.json",
                task_id,
                keep_browser_open=False,
                wait_for_user=None,
            )
            save_run_result(result, TASKS_DIR / f"{task_id}-workflow.json")
            JOBS.update(
                job.job_id,
                status="COMPLETED",
                finished_at=datetime.now().isoformat(),
                message=result.status,
                detail=result.to_dict(),
            )
        except Exception as exc:  # noqa: BLE001 - the reason is shown
            JOBS.update(
                job.job_id,
                status="FAILED",
                finished_at=datetime.now().isoformat(),
                message=str(exc),
                detail={},
            )

    threading.Thread(target=_work, name=f"toolt-dh-{job.job_id}", daemon=True).start()
    return job


def resume_task_job(task_id: str) -> BackgroundJob:
    """Start a resume of an interrupted task in the background."""
    from main import load_config

    config = load_config()
    job = BackgroundJob(
        job_id=f"job-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        kind="resume",
        task_id=task_id,
        started_at=datetime.now().isoformat(),
    )
    JOBS.start(job)

    def _work() -> None:
        try:
            from workflow import load_resume_state, record_workflow_state, run_workflow

            state = load_resume_state(task_id)
            if state and str(state.get("status", "")) == "DRAFT_SAVED":
                record_workflow_state(task_id, "AWAITING_APPROVAL", "The draft already exists.", state)
                JOBS.update(
                    job.job_id,
                    status="COMPLETED",
                    finished_at=datetime.now().isoformat(),
                    message="AWAITING_APPROVAL",
                    detail=state,
                )
                return
            result = run_workflow(
                config,
                PRODUCTION_DIR / "candidates.json",
                task_id,
                keep_browser_open=False,
                wait_for_user=None,
            )
            JOBS.update(
                job.job_id,
                status="COMPLETED",
                finished_at=datetime.now().isoformat(),
                message=result.status,
                detail=result.to_dict(),
            )
        except Exception as exc:  # noqa: BLE001 - the reason is shown
            JOBS.update(
                job.job_id,
                status="FAILED",
                finished_at=datetime.now().isoformat(),
                message=str(exc),
                detail={},
            )

    threading.Thread(target=_work, name=f"toolt-dh-{job.job_id}", daemon=True).start()
    return job


def jobs_list() -> dict[str, Any]:
    """Return the background jobs the dashboard started."""
    return {"jobs": [job.to_dict() for job in JOBS.all()]}


# ---------------------------------------------------------------- approvals


def approvals_list() -> dict[str, Any]:
    """Return the items that wait for a human decision."""
    reviews = _review_records()
    pending: list[dict[str, Any]] = []
    for review in reviews:
        if review.get("status") not in {"AWAITING_SELECTION", "CAPTION_EDITED", "SELECTED"}:
            continue
        pending.append(
            {
                "task_id": review.get("task_id", ""),
                "topic": review.get("topic", ""),
                "status": review.get("status", ""),
                "selected_url": review.get("selected_url", ""),
                "created_at": review.get("created_at", ""),
                "candidate_count": len(review.get("candidates", []) or []),
            }
        )
    tasks = _list_task_states()
    for state in tasks:
        if state.get("status") == "AWAITING_APPROVAL":
            pending.append(
                {
                    "task_id": state.get("task_id", ""),
                    "topic": "",
                    "status": "AWAITING_APPROVAL",
                    "selected_url": state.get("source_url", ""),
                    "created_at": state.get("updated_at", ""),
                    "candidate_count": 0,
                    "kind": "publish",
                }
            )
    return {"approvals": pending}


def approve_task(task_id: str) -> dict[str, Any]:
    """Record the approval that lets a task continue to the draft step.

    The approval is stored in the task state, so it survives a restart. It
    covers this task only; it is never a blanket permission.
    """
    path = TASKS_DIR / f"{task_id}.json"
    state = _read_json(path, {})
    if not isinstance(state, dict):
        state = {}
    state["download_approved"] = True
    state["approved_by"] = "admin"
    state["approved_at"] = datetime.now().isoformat()
    state["approval_scope"] = "download_and_draft"
    _write_json(path, state)
    return state


def publish_approved(task_id: str) -> dict[str, Any]:
    """Record the separate approval that allows the publish step.

    The publish permission is a different permission from the download
    approval and is never implied by it.
    """
    path = TASKS_DIR / f"{task_id}.json"
    state = _read_json(path, {})
    if not isinstance(state, dict):
        state = {}
    if not state.get("download_approved"):
        raise ServiceError(
            "The download was not approved for this task, so the publish "
            "permission cannot be granted."
        )
    state["publish_approved"] = True
    state["publish_approved_by"] = "admin"
    state["publish_approved_at"] = datetime.now().isoformat()
    _write_json(path, state)
    return state


# ---------------------------------------------------------------- library


def library_list() -> dict[str, Any]:
    """Return the video library with the duplicate records."""
    library = load_library()
    entries = library.get("hashes", {})
    rows = []
    for digest, entry in entries.items():
        rows.append(
            {
                "sha256": digest,
                "task_id": entry.get("task_id", ""),
                "source": entry.get("source", ""),
                "path": entry.get("path", ""),
            }
        )
    rows.sort(key=lambda item: str(item.get("sha256", "")))
    return {"entries": rows, "count": len(rows)}


# ---------------------------------------------------------------- history


def history_list() -> dict[str, Any]:
    """Return the publish history."""
    return {"history": _history_entries()}


def logs_list(limit: int = 200) -> dict[str, Any]:
    """Return the task states as the activity log."""
    tasks = _list_task_states()
    return {"logs": tasks[:limit]}


# ---------------------------------------------------------------- settings


def _load_settings() -> dict[str, Any]:
    """Load the dashboard settings."""
    payload = _read_json(SETTINGS_FILE, {})
    return payload if isinstance(payload, dict) else {}


def _save_settings(payload: dict[str, Any]) -> dict[str, Any]:
    """Save the dashboard settings."""
    _write_json(SETTINGS_FILE, payload)
    return payload


def settings_get() -> dict[str, Any]:
    """Return the settings and the configuration the tool is using."""
    config = _load_config()
    settings = _load_settings()
    return {
        "settings": settings,
        "config": {
            "mode": str(config.get("mode", "approve")),
            "auto_post": bool(config.get("auto_post", False)),
            "expected_account": str(config.get("expected_account", "")),
            "topic": str((config.get("discovery", {}) or {}).get("target_topic", "")),
            "schedule": config.get("schedule", {}),
            "chrome_profile_path": str(config.get("chrome_profile_path", "")),
        },
    }


def settings_update(payload: dict[str, Any]) -> dict[str, Any]:
    """Save the dashboard settings.

    The permission to publish and the schedule are stored here. The rights
    allowlist and the permit dates are not editable from the dashboard, so a
    permission can never be widened through the interface.
    """
    settings = _load_settings()
    for key in ("mode", "auto_post", "notifications", "emergency_stop", "daily_limit"):
        if key in payload:
            settings[key] = payload[key]
    if "schedule" in payload and isinstance(payload["schedule"], dict):
        schedule = dict(settings.get("schedule", {}) or {})
        schedule.update(payload["schedule"])
        settings["schedule"] = schedule
    return _save_settings(settings)


def emergency_stop() -> dict[str, Any]:
    """Stop every automation immediately.

    The flag is persisted so the automation stays stopped after a restart
    until the user starts it again.
    """
    settings = _load_settings()
    settings["emergency_stop"] = True
    settings["emergency_stop_at"] = datetime.now().isoformat()
    _save_settings(settings)
    return settings


def emergency_start() -> dict[str, Any]:
    """Allow the automation to run again."""
    settings = _load_settings()
    settings["emergency_stop"] = False
    settings["emergency_stop_at"] = ""
    _save_settings(settings)
    return settings


# ---------------------------------------------------------------- search profiles


def search_profiles_list() -> dict[str, Any]:
    """Return the saved search profiles."""
    payload = _read_json(SEARCH_PROFILES_FILE, {})
    profiles = payload.get("profiles", []) if isinstance(payload, dict) else []
    return {"profiles": profiles}


def search_profile_save(profile: dict[str, Any]) -> dict[str, Any]:
    """Save a search profile so it can be reused."""
    payload = _read_json(SEARCH_PROFILES_FILE, {})
    profiles = payload.get("profiles", []) if isinstance(payload, dict) else []
    name = str(profile.get("name", "")).strip()
    if not name:
        raise ServiceError("The search profile needs a name.")
    entry = dict(profile)
    entry["name"] = name
    entry["updated_at"] = datetime.now().isoformat()
    replaced = False
    for index, existing in enumerate(profiles):
        if str(existing.get("name", "")).lower() == name.lower():
            profiles[index] = entry
            replaced = True
            break
    if not replaced:
        entry["created_at"] = datetime.now().isoformat()
        profiles.append(entry)
    _write_json(SEARCH_PROFILES_FILE, {"profiles": profiles})
    return entry


def search_profile_delete(name: str) -> dict[str, Any]:
    """Delete a saved search profile."""
    payload = _read_json(SEARCH_PROFILES_FILE, {})
    profiles = payload.get("profiles", []) if isinstance(payload, dict) else []
    kept = [
        profile
        for profile in profiles
        if str(profile.get("name", "")).lower() != name.lower()
    ]
    _write_json(SEARCH_PROFILES_FILE, {"profiles": kept})
    return {"name": name, "deleted": len(kept) != len(profiles)}


def _allowlist_status() -> list[dict[str, Any]]:
    """Return the real allowlist and permit state of every source.

    The information comes from the configuration file. It is shown read-only
    because a permission may never be widened through the interface.
    """
    from discover import validate_source_permitted

    config = _load_config()
    discovery = config.get("discovery", {}) if isinstance(config.get("discovery"), dict) else {}
    today = date.today()
    rows: list[dict[str, Any]] = []
    for source in discovery.get("sources", []) or []:
        if not isinstance(source, dict):
            continue
        url = str(source.get("source", "")).strip()
        permit_raw = str(source.get("permit_date", "")).strip()
        permit_valid = False
        permit_reason = ""
        if not permit_raw:
            permit_reason = "Không có ngày giấy phép."
        else:
            try:
                permit_date = datetime.strptime(permit_raw, "%Y-%m-%d").date()
            except ValueError:
                permit_reason = "Ngày giấy phép không đúng định dạng."
            else:
                if permit_date < today:
                    permit_reason = f"Giấy phép đã hết hạn ngày {permit_raw}."
                else:
                    try:
                        validate_source_permitted(url, config)
                    except Exception as exc:  # noqa: BLE001 - the reason is shown
                        permit_reason = str(exc)
                    else:
                        permit_valid = True
        rows.append(
            {
                "creator": str(source.get("creator", "")),
                "source": url,
                "rights": str(source.get("rights", "")),
                "rights_verified": bool(source.get("rights_verified", False)),
                "permit_date": permit_raw,
                "permit_valid": permit_valid,
                "permit_reason": permit_reason,
                "type": str(source.get("type", "")),
            }
        )
    return rows


def permissions_list() -> dict[str, Any]:
    """Return the permission state of every configured source."""
    rows = _allowlist_status()
    return {
        "permissions": rows,
        "valid_count": len([row for row in rows if row["permit_valid"]]),
        "total_count": len(rows),
    }


# ---------------------------------------------------------------- editor


def inspect_media(path: str, start: float = 0.0, end: float = 0.0) -> dict[str, Any]:
    """Inspect a stored media file and report what the backend really sees.

    The duration and the format are measured from the file itself with the
    existing `ingest` helpers, so the editor shows the real state of the
    file rather than what its name claims.
    """
    from ingest import IngestError, detect_media_format, measure_duration

    target = Path(path)
    if not target.exists():
        raise ServiceError(f"The file was not found: {path}")
    if not target.is_file():
        raise ServiceError(f"The path is not a file: {path}")
    size = target.stat().st_size
    try:
        media_format = detect_media_format(target)
        duration = measure_duration(target, media_format)
    except IngestError as exc:
        raise ServiceError(str(exc)) from exc

    clip: dict[str, Any] = {}
    if end and end > start:
        if start < 0 or end > duration:
            raise ServiceError(
                f"The requested range {start:.1f}s to {end:.1f}s is outside the "
                f"real duration of {duration:.2f}s."
            )
        clip = {"start": start, "end": end, "length": round(end - start, 2)}
    elif start and start >= duration:
        raise ServiceError(
            f"The start point {start:.1f}s is past the real duration of {duration:.2f}s."
        )

    return {
        "path": str(target),
        "format": media_format,
        "duration_seconds": duration,
        "size_bytes": size,
        "clip": clip,
        "note": (
            "Đo bằng ffprobe và đọc chữ ký container thật. "
            "Thời lượng khai báo không được tin."
        ),
    }


# ---------------------------------------------------------------- notifications


def _load_notifications() -> list[dict[str, Any]]:
    """Load the notifications."""
    payload = _read_json(NOTIFICATIONS_FILE, {})
    items = payload.get("items", []) if isinstance(payload, dict) else []
    return items


def _save_notifications(items: list[dict[str, Any]]) -> None:
    """Save the notifications."""
    _write_json(NOTIFICATIONS_FILE, {"items": items})


def notifications_list() -> dict[str, Any]:
    """Return the notifications."""
    items = _load_notifications()
    items.sort(key=lambda item: str(item.get("at", "")), reverse=True)
    return {"notifications": items}


def add_notification(kind: str, message: str, detail: dict[str, Any] | None = None) -> dict[str, Any]:
    """Add a notification."""
    items = _load_notifications()
    entry = {
        "id": f"note-{datetime.now().strftime('%Y%m%d-%H%M%S%f')}",
        "kind": str(kind),
        "message": str(message),
        "at": datetime.now().isoformat(),
        "read": False,
        "detail": dict(detail or {}),
    }
    items.append(entry)
    _save_notifications(items[-500:])
    return entry


def notifications_read(notification_id: str) -> dict[str, Any]:
    """Mark a notification as read."""
    items = _load_notifications()
    found = False
    for item in items:
        if item.get("id") == notification_id:
            item["read"] = True
            found = True
            break
    _save_notifications(items)
    return {"id": notification_id, "updated": found}


# ---------------------------------------------------------------- analytics


def analytics() -> dict[str, Any]:
    """Return the effectiveness statistics of the tool."""
    history = _history_entries()
    reviews = _review_records()
    tasks = _list_task_states()
    library = load_library()

    published = [item for item in history if item.get("status") == "PUBLISHED"]
    views = []
    likes = []
    for item in published:
        metadata = item.get("metadata", {}) if isinstance(item.get("metadata"), dict) else {}
        for key, bucket in (("views", views), ("likes", likes)):
            value = metadata.get(key)
            if isinstance(value, (int, float)):
                bucket.append(int(value))

    def _average(values: list[int]) -> float:
        return round(sum(values) / len(values), 1) if values else 0.0

    decisions = {"ACCEPT": 0, "HOLD": 0, "REJECT": 0}
    for review in reviews:
        for candidate in review.get("candidates", []) or []:
            decision = str(candidate.get("decision", ""))
            if decision in decisions:
                decisions[decision] += 1

    return {
        "published_count": len(published),
        "average_views": _average(views),
        "average_likes": _average(likes),
        "downloaded_count": len(library.get("hashes", {})),
        "task_count": len(tasks),
        "review_count": len(reviews),
        "decisions": decisions,
        "has_data": bool(published or reviews or library.get("hashes")),
    }


__all__ = [
    "JOBS",
    "NEEDS_PERMISSION_REVIEW",
    "ServiceError",
    "add_notification",
    "analytics",
    "approvals_list",
    "approve_task",
    "emergency_start",
    "emergency_stop",
    "generate_caption",
    "history_list",
    "inspect_media",
    "jobs_list",
    "library_list",
    "logs_list",
    "notifications_list",
    "notifications_read",
    "overview",
    "permissions_list",
    "publish_approved",
    "resume_task_job",
    "review_list",
    "run_discovery_job",
    "run_task_job",
    "search_profile_delete",
    "search_profile_save",
    "search_profiles_list",
    "select_review_candidate",
    "settings_get",
    "settings_update",
    "task_detail",
    "tasks_list",
    "update_review_caption",
]
