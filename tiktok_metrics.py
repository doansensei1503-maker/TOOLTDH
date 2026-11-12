"""Real TikTok metrics extracted from the page's own rehydration payload.

The numbers are read from the data TikTok serves in the page. Nothing is
invented: a metric that is absent from the payload stays unknown and is
reported as unknown rather than being replaced with a made-up value.

The payload is the page's own embedded state, so reading it is the same data
the signed-in user sees. No private API is called and no protection is
bypassed.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

REHYDRATION_SCRIPT_PATTERN = re.compile(
    r'<script[^>]+id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>',
    re.DOTALL,
)

# A relative creator video link as it appears in the served HTML.
RELATIVE_VIDEO_PATTERN = re.compile(
    r'href="/@([A-Za-z0-9_.]+)/video/(\d+)"',
    re.IGNORECASE,
)

# An absolute creator video link as it appears in the served HTML.
ABSOLUTE_VIDEO_PATTERN = re.compile(
    r'href="https?://(?:www\.)?tiktok\.com/@([A-Za-z0-9_.]+)/video/(\d+)"',
    re.IGNORECASE,
)

# The per-video metric fields TikTok uses in its payload.
METRIC_FIELDS = {
    "views": ("playCount", "play_count", "stats.playCount"),
    "likes": ("diggCount", "digg_count", "stats.diggCount"),
    "comments": ("commentCount", "comment_count", "stats.commentCount"),
    "shares": ("shareCount", "share_count", "stats.shareCount"),
}


@dataclass
class VideoMetrics:
    """The real metrics for one video, as served by the page."""

    source_url: str
    creator: str = ""
    title: str = ""
    views: int | None = None
    likes: int | None = None
    comments: int | None = None
    shares: int | None = None
    duration_seconds: float | None = None
    posted_at: str = ""
    metrics_present: bool = True
    missing_metrics: list[str] = field(default_factory=list)
    # The platform's own AI label. None means the platform published no
    # label, which is different from the video not being AI-generated.
    is_ai_generated: bool | None = None
    # The platform's own signed media URLs.
    download_url: str = ""
    play_url: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_url": self.source_url,
            "creator": self.creator,
            "title": self.title,
            "views": self.views,
            "likes": self.likes,
            "comments": self.comments,
            "shares": self.shares,
            "duration_seconds": self.duration_seconds,
            "posted_at": self.posted_at,
            "metrics_present": self.metrics_present,
            "missing_metrics": list(self.missing_metrics),
            "is_ai_generated": self.is_ai_generated,
            "download_url": self.download_url,
            "play_url": self.play_url,
        }


def extract_rehydration_payload(html: str) -> dict[str, Any] | None:
    """Return the page's embedded rehydration payload, when it has one."""
    for match in REHYDRATION_SCRIPT_PATTERN.finditer(html or ""):
        raw = match.group(1).strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _walk(payload: Any):
    """Yield every mapping inside a nested payload."""
    stack = [payload]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            yield current
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)


def _as_int(value: Any) -> int | None:
    """Convert a payload value to an integer, or return None when it is absent."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float):
        return int(value) if value >= 0 else None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            number = int(float(text))
        except ValueError:
            return None
        return number if number >= 0 else None
    return None


def _lookup(mapping: dict[str, Any], path: str) -> Any:
    """Read a dotted path from a mapping, returning None when it is absent."""
    current: Any = mapping
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def extract_video_metrics(html: str, creator: str = "") -> list[VideoMetrics]:
    """Extract the real per-video metrics from a served creator page.

    Only the videos the page itself lists are returned. A video with no metric
    in the payload is returned with ``metrics_present`` false and the missing
    metric names listed, so the caller can tell a zero from an unknown.
    """
    payload = extract_rehydration_payload(html)
    results: dict[str, VideoMetrics] = {}

    # The links in the HTML give the videos the page actually lists. A public
    # page uses absolute links and a private page uses relative ones, so both
    # forms are read.
    for pattern in (ABSOLUTE_VIDEO_PATTERN, RELATIVE_VIDEO_PATTERN):
        for handle, video_id in pattern.findall(html or ""):
            if creator and handle.lower() != creator.lower():
                continue
            url = f"https://www.tiktok.com/@{handle}/video/{video_id}"
            if url not in results:
                results[url] = VideoMetrics(source_url=url, creator=handle)

    if payload is not None:
        # The item list carries the metrics for each listed video.
        for mapping in _walk(payload):
            identifier = mapping.get("id") or mapping.get("aweme_id")
            if not isinstance(identifier, str) or not identifier.isdigit():
                continue
            module = mapping.get("author", {}) if isinstance(mapping.get("author"), dict) else {}
            handle = str(module.get("uniqueId") or module.get("unique_id") or "")
            if creator and handle.lower() != creator.lower():
                continue
            url = f"https://www.tiktok.com/@{handle}/video/{identifier}"
            entry = results.setdefault(url, VideoMetrics(source_url=url, creator=handle))
            stats = mapping.get("stats") if isinstance(mapping.get("stats"), dict) else mapping
            for metric, paths in METRIC_FIELDS.items():
                value = None
                for path in paths:
                    value = _lookup(stats, path)
                    if value is not None:
                        break
                number = _as_int(value)
                if number is not None:
                    setattr(entry, metric, number)
            duration = _as_int(stats.get("duration"))
            if duration is not None:
                entry.duration_seconds = duration / 1000.0
            created = stats.get("createTime") or stats.get("create_time")
            if isinstance(created, (int, float)) and not isinstance(created, bool):
                entry.posted_at = str(int(created))
            text = mapping.get("desc") or mapping.get("title") or ""
            if isinstance(text, str) and text.strip() and not entry.title:
                entry.title = text.strip()[:200]

    # Mark which metrics are genuinely unknown.
    for entry in results.values():
        missing = [name for name in METRIC_FIELDS if getattr(entry, name) is None]
        entry.missing_metrics = missing
        entry.metrics_present = not missing
    return list(results.values())


def extract_creator_stats(html: str) -> dict[str, Any]:
    """Return the creator-level statistics the page serves.

    These are the account's own totals, read from the account's own scope so
    a recommended creator's numbers are never reported as the account's. They
    are used to confirm that the page really belongs to the expected creator.
    """
    payload = extract_rehydration_payload(html)
    if payload is None:
        return {}
    detail = _user_detail_scope(payload)
    if detail is None:
        return {}
    found: dict[str, Any] = {}
    user_info = detail.get("userInfo")
    if isinstance(user_info, dict):
        for key in ("uniqueId", "nickname", "signature"):
            if key in user_info:
                found[key] = user_info[key]
        stats = user_info.get("stats")
        if isinstance(stats, dict):
            for key in ("followerCount", "followingCount", "heartCount", "videoCount", "diggCount"):
                if key in stats:
                    found[key] = stats[key]
    for key in ("statusCode", "statusMsg"):
        if key in detail:
            found[key] = detail[key]
    return found


def _user_detail_scope(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Return the user-detail scope, which owns the account's own status.

    Only this scope decides whether the account is private. A nested mapping
    with the same field name belongs to a recommended creator and must not be
    read as the account's own status.
    """
    default = payload.get("__DEFAULT_SCOPE__")
    if not isinstance(default, dict):
        return None
    webapp = default.get("webapp")
    if not isinstance(webapp, dict):
        return None
    detail = webapp.get("user-detail")
    return detail if isinstance(detail, dict) else None


def is_private_account(html: str) -> bool:
    """Return True when the account's own video list is not published.

    The decision comes from the account's own user-detail scope, so a
    recommended creator that appears on the page cannot be mistaken for the
    account being read.
    """
    lowered = (html or "").lower()
    if "errbizusersecret" in lowered:
        return True
    payload = extract_rehydration_payload(html)
    if payload is None:
        return False
    detail = _user_detail_scope(payload)
    if detail is None:
        return False
    status_code = detail.get("statusCode")
    status_msg = str(detail.get("statusMsg", "")).strip().lower()
    if status_code == 10222 or status_msg == "errbizusersecret":
        return True
    return False


__all__ = [
    "RELATIVE_VIDEO_PATTERN",
    "VideoMetrics",
    "extract_creator_stats",
    "extract_rehydration_payload",
    "extract_video_metrics",
    "is_private_account",
]
