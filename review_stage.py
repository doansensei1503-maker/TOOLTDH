"""P16.1 review stage: show the discovered videos and let the user choose.

The review stage is the point where the user sees the real candidates with
their real metrics and decides which video is processed. Nothing is sent to
TikTok Studio from here. The chosen video is written to a review file that
the workflow then reads, so the choice is explicit and auditable.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from discover import DiscoveredVideo, TrendingScore

REVIEW_DIR = Path("data") / "review"


def review_file(task_id: str, directory: Path = REVIEW_DIR) -> Path:
    """Return the path of the review record for a task."""
    return Path(directory) / f"{task_id}-review.json"


def _candidate_field(candidate: Any, name: str, default: Any = None) -> Any:
    """Read one field of a candidate, whether it is an object or a record.

    The dashboard hands over the serialized candidates of the last run, while
    the terminal flow hands over the candidate objects. Both are read the
    same way, so a review record is written correctly either way.
    """
    if isinstance(candidate, dict):
        value = candidate.get(name, default)
    else:
        value = getattr(candidate, name, default)
    return default if value is None else value


def write_review(
    task_id: str,
    candidates: list[DiscoveredVideo],
    scores: list[TrendingScore],
    *,
    topic: str,
    blockers: list[str] | None = None,
    directory: Path = REVIEW_DIR,
) -> Path:
    """Write the review record with every candidate and its real metrics."""
    target = review_file(task_id, directory)
    target.parent.mkdir(parents=True, exist_ok=True)
    score_by_url = {
        score.video.source_url: score
        for score in scores
        if getattr(getattr(score, "video", None), "source_url", "")
    }
    payload: dict[str, Any] = {
        "task_id": task_id,
        "topic": topic,
        "created_at": datetime.now().isoformat(),
        "status": "AWAITING_SELECTION",
        "blockers": list(blockers or []),
        "candidates": [],
    }
    for index, candidate in enumerate(candidates, start=1):
        source_url = str(_candidate_field(candidate, "source_url", ""))
        score = score_by_url.get(source_url)
        payload["candidates"].append(
            {
                "index": index,
                "source_url": source_url,
                "creator": str(_candidate_field(candidate, "creator", "")),
                "title": str(_candidate_field(candidate, "title", "")),
                "views": int(_candidate_field(candidate, "views", 0) or 0),
                "likes": int(_candidate_field(candidate, "likes", 0) or 0),
                "comments": int(_candidate_field(candidate, "comments", 0) or 0),
                "shares": int(_candidate_field(candidate, "shares", 0) or 0),
                "duration_seconds": float(_candidate_field(candidate, "duration_seconds", 0) or 0),
                "posted_at": str(_candidate_field(candidate, "posted_at", "")),
                "is_ai_generated": bool(_candidate_field(candidate, "is_ai_generated", False)),
                "ai_label_known": bool(
                    _candidate_field(candidate, "ai_label_known", None) is not False
                ),
                "metrics_known": bool(_candidate_field(candidate, "metrics_known", False)),
                "missing_metrics": list(_candidate_field(candidate, "missing_metrics", []) or []),
                "download_url": str(_candidate_field(candidate, "download_url", "")),
                "source_name": str(_candidate_field(candidate, "source_name", "")),
                "score": score.score if score else 0,
                "decision": score.decision if score else "UNSCORED",
                "score_reason": score.reason if score else "",
            }
        )
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def format_review(payload: dict[str, Any]) -> str:
    """Return the review list as readable text for the terminal."""
    lines: list[str] = []
    topic = payload.get("topic", "")
    candidates = payload.get("candidates", []) or []
    lines.append(f"Review for topic {topic!r} ({len(candidates)} candidate(s))")
    for blocker in payload.get("blockers", []) or []:
        lines.append(f"  BLOCKER: {blocker}")
    if not candidates:
        lines.append("  No candidate is available to review.")
        return "\n".join(lines)
    for entry in candidates:
        unknown = entry.get("missing_metrics") or []
        known = "all metrics" if not unknown else f"unknown: {', '.join(unknown)}"
        duration = float(entry.get("duration_seconds", 0) or 0)
        lines.append(
            f"  [{entry['index']}] {entry['source_url']}\n"
            f"      creator={entry.get('creator', '')} score={entry.get('score', 0)} "
            f"decision={entry.get('decision', '')}\n"
            f"      views={entry.get('views', 0)} likes={entry.get('likes', 0)} "
            f"comments={entry.get('comments', 0)} shares={entry.get('shares', 0)} "
            f"duration={duration:.1f}s ({known})\n"
            f"      title={entry.get('title', '')[:80]!r}"
        )
    return "\n".join(lines)


def select_candidate(
    task_id: str,
    index: int,
    *,
    directory: Path = REVIEW_DIR,
) -> DiscoveredVideo | None:
    """Record the user's choice and return the chosen candidate.

    The choice is written back to the review record so the decision is
    auditable and a later run does not ask again.
    """
    target = review_file(task_id, directory)
    if not target.exists():
        return None
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    entries = payload.get("candidates", []) or []
    chosen = None
    for entry in entries:
        if int(entry.get("index", 0)) == index:
            chosen = entry
            break
    if chosen is None:
        return None
    payload["status"] = "SELECTED"
    payload["selected_index"] = index
    payload["selected_url"] = chosen.get("source_url", "")
    payload["selected_at"] = datetime.now().isoformat()
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return DiscoveredVideo(
        source_url=str(chosen.get("source_url", "")),
        creator=str(chosen.get("creator", "")),
        title=str(chosen.get("title", "")),
        views=int(chosen.get("views", 0) or 0),
        likes=int(chosen.get("likes", 0) or 0),
        comments=int(chosen.get("comments", 0) or 0),
        shares=int(chosen.get("shares", 0) or 0),
        download_url=str(chosen.get("download_url", "")),
        source_name=str(chosen.get("source_name", "")),
        duration_seconds=float(chosen.get("duration_seconds", 0) or 0),
        posted_at=str(chosen.get("posted_at", "")),
        is_ai_generated=bool(chosen.get("is_ai_generated", False)),
        # The AI label fact is carried through, so an unknown label is not
        # turned into a negative claim when the record is read back.
        ai_label_known=bool(
            chosen.get("ai_label_known", chosen.get("is_ai_generated") is not None)
        ),
        topic=str(payload.get("topic", "")),
        metrics_known=bool(chosen.get("metrics_known", False)),
        missing_metrics=list(chosen.get("missing_metrics", []) or []),
    )


def load_review(task_id: str, *, directory: Path = REVIEW_DIR) -> dict[str, Any]:
    """Load the review record for a task."""
    target = review_file(task_id, directory)
    if not target.exists():
        return {}
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


__all__ = [
    "REVIEW_DIR",
    "format_review",
    "load_review",
    "review_file",
    "select_candidate",
    "write_review",
]
