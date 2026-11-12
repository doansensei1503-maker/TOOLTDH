"""P16.1 eligibility checks for a discovered candidate.

Two different questions are answered separately and never confused:

* **Download eligibility** - can the media be fetched and is it a usable
  video file? This is a technical question about the URL, the format, and
  the duration.
* **Reuse permission** - may the content be reused? This comes only from the
  rights allowlist and is never inferred from the technical checks.

A candidate that is downloadable is not automatically permitted, and a
candidate that is permitted is not automatically downloadable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from discover import DiscoveredVideo

# The formats the platform serves and the ingest pipeline accepts.
ALLOWED_VIDEO_SUFFIXES = (".mp4", ".mov", ".webm")

# A TikTok media URL is served from the platform's own webapp and CDN hosts.
# The signed media URLs the item list publishes use these hosts.
PLATFORM_MEDIA_HOST_SUFFIXES = (
    "tiktok.com",
    "tiktokcdn.com",
    "tiktokcdn-us.com",
    "byteoversea.com",
    "ibytedtos.com",
    "muscdn.com",
    "tiktokv.com",
    "ttwstatic.com",
    "pstatp.com",
    "ibytedap.com",
)


@dataclass
class EligibilityResult:
    """The outcome of the download-eligibility checks for one candidate."""

    source_url: str
    eligible: bool = False
    reasons: list[str] = field(default_factory=list)
    media_url: str = ""
    media_host: str = ""
    format_ok: bool = False
    duration_ok: bool = False
    duplicate: bool = False
    # The reuse permission is reported beside the technical result and is
    # never derived from it.
    reuse_permitted: bool = False
    reuse_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_url": self.source_url,
            "eligible": self.eligible,
            "reasons": list(self.reasons),
            "media_url": self.media_url,
            "media_host": self.media_host,
            "format_ok": self.format_ok,
            "duration_ok": self.duration_ok,
            "duplicate": self.duplicate,
            "reuse_permitted": self.reuse_permitted,
            "reuse_reason": self.reuse_reason,
        }


def is_platform_media_url(url: str) -> bool:
    """Return True when the URL is served by the platform's own media CDN."""
    from urllib.parse import urlparse

    host = (urlparse(url).hostname or "").lower()
    if not host:
        return False
    return any(
        host == suffix or host.endswith(f".{suffix}")
        for suffix in PLATFORM_MEDIA_HOST_SUFFIXES
    )


def check_media_url(url: str) -> tuple[bool, str, str]:
    """Check that a media URL is usable.

    Returns the result, the host, and the reason. Only a URL on the
    platform's own webapp or CDN host is accepted, so a link to an unrelated
    host is never treated as the video's media.

    The platform's signed media URLs carry the format in the ``mime_type``
    query parameter and not in the path, so both are checked.
    """
    from urllib.parse import parse_qs, urlparse

    if not url:
        return False, "", "no media URL was supplied"
    parsed = urlparse(url)
    if parsed.scheme.lower() not in {"http", "https"}:
        return False, "", f"the media URL scheme '{parsed.scheme}' is not supported"
    host = (parsed.hostname or "").lower()
    if not host:
        return False, "", "the media URL has no host"
    if not is_platform_media_url(url):
        return (
            False,
            host,
            f"the media URL is hosted on '{host}', which is not the platform's own "
            "media host",
        )
    path = parsed.path.lower()
    mime = ""
    query = parse_qs(parsed.query or "")
    for value in query.get("mime_type", []) + query.get("mimeType", []):
        mime = str(value).lower()
        break
    if mime:
        if "mp4" in mime:
            return True, host, ""
        if "webm" in mime:
            return True, host, ""
        return (
            False,
            host,
            f"the media URL declares the unsupported type '{mime}'",
        )
    if path.endswith(ALLOWED_VIDEO_SUFFIXES):
        return True, host, ""
    return (
        False,
        host,
        f"the media URL does not point at a supported video format "
        f"({', '.join(ALLOWED_VIDEO_SUFFIXES)})",
    )


def check_duration(duration_seconds: float | None, maximum: float = 600.0) -> tuple[bool, str]:
    """Check the duration against the platform limit.

    An unknown duration is not accepted, because a video that cannot be
    measured cannot be checked.
    """
    if duration_seconds is None:
        return False, "the duration is unknown, so the video cannot be checked"
    if duration_seconds <= 0:
        return False, "the reported duration is not a positive number"
    if duration_seconds > maximum:
        return (
            False,
            f"the duration of {duration_seconds:.1f}s exceeds the {maximum:.0f}s limit",
        )
    return True, ""


def check_candidate(
    candidate: DiscoveredVideo,
    *,
    media_url: str = "",
    reuse_permitted: bool = False,
    reuse_reason: str = "",
    duplicate: bool = False,
    maximum_duration: float = 600.0,
) -> EligibilityResult:
    """Run every download-eligibility check for one candidate.

    The reuse permission is only carried through. It is decided by the
    rights allowlist and is never inferred from a technical result.
    """
    result = EligibilityResult(
        source_url=candidate.source_url,
        media_url=media_url,
        reuse_permitted=reuse_permitted,
        reuse_reason=reuse_reason,
        duplicate=duplicate,
    )
    if duplicate:
        result.reasons.append("the SHA256 is already in the library")
    url_ok, host, url_reason = check_media_url(media_url)
    result.media_host = host
    result.format_ok = url_ok
    if not url_ok:
        result.reasons.append(url_reason)
    duration_ok, duration_reason = check_duration(
        candidate.duration_seconds or None, maximum_duration
    )
    result.duration_ok = duration_ok
    if not duration_ok:
        result.reasons.append(duration_reason)
    result.eligible = url_ok and duration_ok and not duplicate
    return result


def summarise(results: list[EligibilityResult]) -> str:
    """Return a one-line-per-candidate summary of the eligibility results."""
    if not results:
        return "No candidate was checked."
    lines = []
    for result in results:
        state = "ELIGIBLE" if result.eligible else "NOT ELIGIBLE"
        detail = "; ".join(result.reasons) if result.reasons else "all checks passed"
        permission = "reuse permitted" if result.reuse_permitted else "reuse not permitted"
        lines.append(f"{state} {result.source_url}: {detail} ({permission})")
    return "\n".join(lines)


__all__ = [
    "ALLOWED_VIDEO_SUFFIXES",
    "EligibilityResult",
    "PLATFORM_MEDIA_HOST_SUFFIXES",
    "check_candidate",
    "check_duration",
    "check_media_url",
    "is_platform_media_url",
    "summarise",
]
