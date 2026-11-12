"""P6 discovery of trending content from allowlisted TikTok sources.

Only sources listed in the ``discovery.sources`` allowlist in ``config.yaml``
may be used. Each allowlisted source must carry rights confirmation and a
permission date. Videos outside the allowlist are rejected before any download
is attempted.

Downloads follow the SnapTik reference flow: the page is read to resolve the
media download link and the file is then saved to ``data/temp/``. No watermark
is removed and no provenance marker is hidden, so creator credit is preserved
in the generated caption.
"""

from __future__ import annotations

import json
import random
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from library import ContentLibrary
from storage import TEMP_DIR, ensure_directories, sha256_file

SNAPTIK_RESOLVER_URL = "https://snaptik.app"
ALLOWED_TIKTOK_HOST_SUFFIXES = ("tiktok.com",)
DOWNLOAD_LINK_PATTERN = re.compile(
    r"https?://[^\s\"'<>]+?\.(?:mp4|mov|webm)(?:\?[^\s\"'<>]*)?",
    re.IGNORECASE,
)
HTTP_TIMEOUT_SECONDS = 60

# P16: TEST data and PRODUCTION data are stored separately and never mixed.
# Production discovery reads only from data/production and may never fall back
# to a test fixture or to a previously downloaded local test video.
PRODUCTION_CANDIDATES_DIR = Path("data") / "production"
TEST_CANDIDATES_DIR = Path("data") / "test"
PRODUCTION_CANDIDATES_FILE = PRODUCTION_CANDIDATES_DIR / "candidates.json"
TEST_CANDIDATES_FILE = TEST_CANDIDATES_DIR / "candidates.json"
# Any path under these folders is test data and is refused in production.
TEST_DATA_MARKERS = ("test", "fixture", "sample", "p15v", "mock")
# The legacy root-level candidate file is the old fixture and is test data.
LEGACY_TEST_CANDIDATE_FILES = ("data/candidates.json", "data/p15v-candidates.json")


class DiscoveryError(RuntimeError):
    """Raised when discovery cannot proceed safely."""


class NoCandidatesFoundError(DiscoveryError):
    """Raised when production discovery finds no valid new candidate."""


class TestDataRejectedError(DiscoveryError):
    """Raised when a production run is pointed at test data."""


class SourceNotAllowedError(DiscoveryError):
    """Raised when a source is not on the configured allowlist."""


class RightsNotPermittedError(DiscoveryError):
    """Raised when an allowlisted source lacks rights or a valid permit date."""


@dataclass
class DiscoveredVideo:
    """One candidate video found on an allowlisted source."""

    source_url: str
    creator: str = ""
    title: str = ""
    views: int = 0
    likes: int = 0
    download_url: str = ""
    source_name: str = ""
    duration_seconds: float = 0.0
    posted_at: str = ""
    is_ai_generated: bool = True
    # Whether the platform published an AI label for this video at all. When
    # it did not, the label is unknown and no claim is made either way. A
    # video that the platform explicitly labelled as not AI-generated is not
    # the same as a video the platform said nothing about.
    ai_label_known: bool = True
    topic: str = ""
    comments: int = 0
    shares: int = 0
    # The metrics that the source did not publish stay unknown. A real zero
    # and an absent metric are different facts and are never confused.
    metrics_known: bool = True
    missing_metrics: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the candidate."""
        return asdict(self)


@dataclass
class DiscoveryResult:
    """Outcome of one discovery run."""

    status: str
    candidates: list[DiscoveredVideo] = field(default_factory=list)
    selected: DiscoveredVideo | None = None
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the outcome."""
        payload = asdict(self)
        return payload


def allowed_sources(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the allowlisted sources that have rights and a valid permit date."""
    discovery = config.get("discovery", {})
    if not isinstance(discovery, dict):
        return []
    sources = discovery.get("sources", [])
    if not isinstance(sources, list):
        return []
    return [source for source in sources if isinstance(source, dict)]


def source_creator(source: dict[str, Any]) -> str:
    """Return the normalised creator handle an allowlist entry applies to.

    The creator handle is read from the entry so the allowlist can be scoped
    to a single TikTok account instead of every account on the host.
    """
    for key in ("creator", "name", "source"):
        value = str(source.get(key, "")).strip()
        if not value:
            continue
        handle = value.rstrip("/").rsplit("/", 1)[-1]
        handle = handle.lstrip("@").strip()
        if handle:
            return handle.lower()
    return ""


def url_creator(url: str) -> str:
    """Return the creator handle encoded in a TikTok profile or video URL."""
    parsed = urlparse(url)
    path = parsed.path or ""
    parts = [part for part in path.split("/") if part]
    for index, part in enumerate(parts):
        if part.startswith("@") and len(part) > 1:
            return part[1:].lower()
        if part.lower() == "video" and index > 0:
            return parts[index - 1].lower()
    return ""


def is_tiktok_url(url: str) -> bool:
    """Return whether a URL points at TikTok."""
    parsed = urlparse(url)
    if parsed.scheme.lower() not in {"http", "https"}:
        return False
    host = (parsed.hostname or "").lower()
    return any(host == suffix or host.endswith(f".{suffix}") for suffix in ALLOWED_TIKTOK_HOST_SUFFIXES)


def matching_sources(url: str, config: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the allowlist entries that cover a URL.

    Only TikTok URLs are ever eligible. An entry that names a creator matches
    only that creator's own URLs, so an allowlisted account never permits a
    different creator on the same host.
    """
    if not is_tiktok_url(url):
        return []
    creator = url_creator(url)
    matches: list[dict[str, Any]] = []
    for source in allowed_sources(config):
        source_host = str(source.get("host", "")).lower()
        if source_host and source_host not in ALLOWED_TIKTOK_HOST_SUFFIXES:
            continue
        allowed_creator = source_creator(source)
        if allowed_creator and creator and allowed_creator != creator:
            continue
        if allowed_creator and not creator:
            continue
        matches.append(source)
    return matches


def is_allowed_source(url: str, config: dict[str, Any]) -> bool:
    """Return whether a URL belongs to an allowlisted source."""
    return bool(matching_sources(url, config))


def validate_source_permitted(url: str, config: dict[str, Any], today: date | None = None) -> dict[str, Any]:
    """Confirm the source is allowlisted and permitted, or raise a rejection error.

    A source outside the allowlist is rejected outright. Only TikTok URLs can
    ever be permitted. At least one allowlist entry covering the URL must
    declare verified rights and a permit date that has not expired; entries
    without rights are never usable and are skipped rather than blocking a
    creator that another entry permits.
    """
    if not is_tiktok_url(url):
        raise SourceNotAllowedError(
            f"Rejected: source is not an allowlisted TikTok URL: {url}"
        )
    matching = matching_sources(url, config)
    if not matching:
        raise SourceNotAllowedError(
            f"Rejected: source is not on the discovery allowlist: {url}"
        )
    host = (urlparse(url).hostname or "").lower()
    creator = url_creator(url)
    current = today or date.today()
    permitted: list[dict[str, Any]] = []
    for source in matching:
        if not source.get("rights_verified"):
            continue
        permit_date = str(source.get("permit_date", "")).strip()
        if not permit_date:
            continue
        try:
            expiry = datetime.strptime(permit_date, "%Y-%m-%d").date()
        except ValueError:
            continue
        if expiry < current:
            continue
        permitted.append(source)

    if not permitted:
        scope = f"@{creator}" if creator else host
        raise RightsNotPermittedError(
            f"Rejected: no allowlisted entry for {scope} has verified rights and a valid permit date"
        )
    return permitted[0]


def rank_trending(videos: list[DiscoveredVideo]) -> list[DiscoveredVideo]:
    """Rank candidates by views and then likes, highest first."""
    return sorted(videos, key=lambda video: (video.views, video.likes), reverse=True)


# Trending score weights. The formula is fixed so a decision can be explained.
TOPIC_MATCH_AI_MUSIC = 30
TOPIC_MATCH_MUSIC = 15
VIEWS_SCORE_TIERS = ((100000, 25), (10000, 20), (1000, 10))
ENGAGEMENT_TIERS = ((0.05, 20), (0.02, 10))
RECENCY_TIERS = ((7, 15), (30, 10))
DURATION_BEST = (25.0, 35.0)
DURATION_OK = (15.0, 60.0)
PENALTY_DUPLICATE = -100
PENALTY_NOT_ALLOWLISTED = -100
PENALTY_NOT_AI = -100
ACCEPT_SCORE = 70
HOLD_SCORE = 50
MUSIC_TERMS = ("music", "song", "sound", "beat", "track", "audio", "remix", "lofi")


@dataclass
class TrendingScore:
    """The scored result for one candidate with its full explanation."""

    video: DiscoveredVideo
    score: int
    decision: str
    reason: str
    topic_match: int = 0
    views_score: int = 0
    engagement: int = 0
    recency: int = 0
    duration_match: int = 0
    penalty: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize the scored result."""
        payload = asdict(self)
        payload["video"] = self.video.to_dict()
        return payload


def _threshold(scoring: dict[str, Any], key: str, default: int) -> int:
    """Return an admin-set score threshold, or the fixed default.

    The threshold has to stay inside the score range, so a value outside
    it is ignored rather than changing the meaning of the scale.
    """
    try:
        value = int(scoring.get(key, default))
    except (TypeError, ValueError):
        return default
    if value < 0 or value > 100:
        return default
    return value


def _topic_match_score(video: DiscoveredVideo, target_topic: str) -> int:
    """Score how well the video topic matches the configured target topic."""
    haystack = f"{video.topic} {video.title}".lower()
    target = target_topic.strip().lower()
    is_ai_music = "ai" in haystack and any(term in haystack for term in MUSIC_TERMS)
    is_music = any(term in haystack for term in MUSIC_TERMS)
    if target:
        target_tokens = {token for token in target.replace("-", " ").split() if token}
        haystack_tokens = set(haystack.replace("-", " ").split())
        if target_tokens and target_tokens & haystack_tokens:
            is_music = True
            if any("ai" in token for token in target_tokens):
                is_ai_music = True
    if is_ai_music:
        return TOPIC_MATCH_AI_MUSIC
    if is_music:
        return TOPIC_MATCH_MUSIC
    return 0


def _views_score(video: DiscoveredVideo) -> int:
    """Score the view count against the fixed tiers."""
    for threshold, points in VIEWS_SCORE_TIERS:
        if video.views >= threshold:
            return points
    return 0


def _engagement_score(video: DiscoveredVideo) -> int:
    """Score the engagement ratio against the fixed tiers.

    The ratio is the total real engagement (likes, comments, and shares)
    over the views. Every term is a metric the source actually published.
    A video whose views are unknown cannot be scored and returns zero.
    """
    if video.views <= 0:
        return 0
    engagement_total = video.likes + video.comments + video.shares
    ratio = engagement_total / video.views
    for threshold, points in ENGAGEMENT_TIERS:
        if ratio >= threshold:
            return points
    return 0


def _recency_score(video: DiscoveredVideo, today: date | None = None) -> int:
    """Score how recently the video was posted."""
    if not video.posted_at:
        return 0
    stamp = str(video.posted_at).strip()
    posted: date | None = None
    try:
        posted = datetime.fromisoformat(stamp.replace("Z", "+00:00")).date()
    except ValueError:
        for pattern in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%Y-%m-%d %H:%M:%S"):
            try:
                posted = datetime.strptime(stamp, pattern).date()
                break
            except ValueError:
                continue
    if posted is None:
        return 0
    age_days = (today or date.today()) - posted
    if age_days.total_seconds() < 0:
        return 0
    age = age_days.days
    for threshold, points in RECENCY_TIERS:
        if age <= threshold:
            return points
    return 0


def _duration_match_score(video: DiscoveredVideo) -> int:
    """Score the duration against the preferred window."""
    duration = float(video.duration_seconds or 0.0)
    if duration <= 0:
        return 0
    if DURATION_BEST[0] <= duration <= DURATION_BEST[1]:
        return 10
    if DURATION_OK[0] <= duration <= DURATION_OK[1]:
        return 5
    return 0


def score_trending(
    video: DiscoveredVideo,
    config: dict[str, Any],
    *,
    today: date | None = None,
    duplicate: bool = False,
    allowlisted: bool = True,
) -> TrendingScore:
    """Score one candidate with the fixed trending formula.

    The score is ``topic_match*30 + views_score*25 + engagement*20 +
    recency*15 + duration_match*10`` using the tier points for each part,
    minus any penalty. The decision is accept at 70 or above, hold for user
    review from 50 to 69, and reject below 50.

    The admin can lower or raise the accept and hold thresholds in the
    configuration under ``discovery.scoring``. The thresholds never change
    the weights, so a decision can still be explained the same way.
    """
    discovery = config.get("discovery", {}) if isinstance(config.get("discovery", {}), dict) else {}
    target_topic = str(discovery.get("target_topic", discovery.get("topic", ""))).strip()
    scoring = discovery.get("scoring", {}) if isinstance(discovery.get("scoring"), dict) else {}
    accept_score = _threshold(scoring, "accept_score", ACCEPT_SCORE)
    hold_score = _threshold(scoring, "hold_score", HOLD_SCORE)

    topic_match = _topic_match_score(video, target_topic)
    views_score = _views_score(video)
    engagement = _engagement_score(video)
    recency = _recency_score(video, today)
    duration_match = _duration_match_score(video)

    penalty = 0
    reasons: list[str] = []
    if duplicate:
        penalty += PENALTY_DUPLICATE
        reasons.append("duplicate hash (-100)")
    if not allowlisted:
        penalty += PENALTY_NOT_ALLOWLISTED
        reasons.append("outside the allowlist (-100)")
    # The AI penalty is applied only when the platform actually published a
    # label saying the video is not AI-generated. When the platform published
    # no AI label the fact is unknown, and an unknown fact is never turned
    # into a negative claim about the video.
    if video.ai_label_known and not video.is_ai_generated:
        penalty += PENALTY_NOT_AI
        reasons.append("not AI-generated (-100)")

    total = topic_match + views_score + engagement + recency + duration_match + penalty
    total = max(0, min(100, total))

    if total >= accept_score:
        decision = "ACCEPT"
    elif total >= hold_score:
        decision = "HOLD"
    else:
        decision = "REJECT"

    detail = (
        f"topic={topic_match} views={views_score} engagement={engagement} "
        f"recency={recency} duration={duration_match} penalty={penalty}"
    )
    if reasons:
        detail = f"{detail} ({', '.join(reasons)})"
    return TrendingScore(
        video=video,
        score=total,
        decision=decision,
        reason=f"{decision}: score {total} from {detail}",
        topic_match=topic_match,
        views_score=views_score,
        engagement=engagement,
        recency=recency,
        duration_match=duration_match,
        penalty=penalty,
    )


def score_all_trending(
    videos: list[DiscoveredVideo],
    config: dict[str, Any],
    *,
    today: date | None = None,
    duplicate_hashes: set[str] | None = None,
    allowed_urls: set[str] | None = None,
) -> list[TrendingScore]:
    """Score every candidate and return them from best to worst."""
    duplicates = duplicate_hashes or set()
    allowed = allowed_urls
    scored: list[TrendingScore] = []
    for video in videos:
        is_allowed = True
        if allowed is not None:
            is_allowed = video.source_url in allowed
        scored.append(
            score_trending(
                video,
                config,
                today=today,
                duplicate=video.source_url in duplicates,
                allowlisted=is_allowed,
            )
        )
    return sorted(scored, key=lambda item: item.score, reverse=True)


def select_trending(
    videos: list[DiscoveredVideo],
    config: dict[str, Any],
) -> DiscoveredVideo | None:
    """Return a single accepted candidate chosen at random.

    The trending score decides which candidates qualify. One of the accepted
    candidates is then picked at random so the same video is not always chosen.
    """
    discovery = config.get("discovery", {})
    minimum_views = int(discovery.get("min_views", 0)) if isinstance(discovery, dict) else 0
    ranked = [video for video in rank_trending(videos) if video.views >= minimum_views]
    if not ranked:
        return None
    accepted = [
        item.video for item in score_all_trending(ranked, config) if item.decision == "ACCEPT"
    ]
    if not accepted:
        return None
    return random.choice(accepted)


# The outcome statuses the dashboard shows for one discovery and filter run.
STATUS_SEARCHING = "SEARCHING"
STATUS_CANDIDATE_FOUND = "CANDIDATE_FOUND"
STATUS_NO_QUALIFIED_VIDEO = "NO_QUALIFIED_VIDEO"
STATUS_BLOCKED = "BLOCKED"
STATUS_ERROR = "ERROR"


@dataclass
class TrendSelection:
    """The outcome of one discovery and trend filtering run.

    At most one video is selected. When no candidate reaches the accept
    threshold the status is ``NO_QUALIFIED_VIDEO`` and no video is chosen,
    because a poor video is never used to fill the result.
    """

    status: str
    topic: str = ""
    selected: DiscoveredVideo | None = None
    selected_score: TrendingScore | None = None
    candidates: list[DiscoveredVideo] = field(default_factory=list)
    scores: list[TrendingScore] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    filters: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the outcome."""
        return {
            "status": self.status,
            "topic": self.topic,
            "selected": self.selected.to_dict() if self.selected else None,
            "selected_score": self.selected_score.to_dict() if self.selected_score else None,
            "candidates": [video.to_dict() for video in self.candidates],
            "scores": [score.to_dict() for score in self.scores],
            "rejected": list(self.rejected),
            "blockers": list(self.blockers),
            "filters": dict(self.filters),
            "candidate_count": len(self.candidates),
        }


def filter_and_select(
    videos: list[DiscoveredVideo],
    config: dict[str, Any],
    *,
    topic: str = "",
    filters: dict[str, Any] | None = None,
    known_urls: set[str] | None = None,
) -> TrendSelection:
    """Score the candidates and select at most one best video.

    The candidates are scored with the trending formula and ranked. The
    highest scoring candidate that reaches the accept threshold is selected,
    so one run never returns more than one video. When no candidate reaches
    the threshold the result is ``NO_QUALIFIED_VIDEO``.

    The download is never started here. In approval mode the run only shows
    the candidate so the admin can approve it.
    """
    from discovery_live import SearchFilters, apply_search_filters

    topic = str(topic or (config.get("discovery", {}) or {}).get("target_topic", "")).strip()
    search_filters = SearchFilters.from_payload(filters)
    blockers: list[str] = []

    kept, dropped = apply_search_filters(list(videos), search_filters)
    for reason in dropped:
        blockers.append(f"Loại theo bộ lọc — {reason}")

    duplicates = set(known_urls or set())
    scores = score_all_trending(kept, config, duplicate_hashes=duplicates)

    rejected: list[dict[str, Any]] = []
    for score in scores:
        if score.decision == "ACCEPT":
            continue
        rejected.append(
            {
                "source_url": score.video.source_url,
                "title": score.video.title,
                "creator": score.video.creator,
                "views": score.video.views,
                "likes": score.video.likes,
                "score": score.score,
                "decision": score.decision,
                "reason": score.reason,
            }
        )

    accepted = [score for score in scores if score.decision == "ACCEPT"]
    if not accepted:
        return TrendSelection(
            status=STATUS_NO_QUALIFIED_VIDEO,
            topic=topic,
            candidates=kept,
            scores=scores,
            rejected=rejected,
            blockers=blockers,
            filters=search_filters.to_dict(),
        )

    # Exactly one video is selected: the best scored accepted candidate.
    best = accepted[0]
    return TrendSelection(
        status=STATUS_CANDIDATE_FOUND,
        topic=topic,
        selected=best.video,
        selected_score=best,
        candidates=kept,
        scores=scores,
        rejected=rejected,
        blockers=blockers,
        filters=search_filters.to_dict(),
    )


def creator_credit(video: DiscoveredVideo) -> str:
    """Return the creator credit string that must stay in the caption."""
    creator = video.creator.strip()
    if not creator:
        return ""
    handle = creator if creator.startswith("@") else f"@{creator}"
    return f"by {handle}"


def resolve_download_link(
    page_url: str,
    fetch_text: Callable[[str], str],
) -> str:
    """Resolve the media download link for a TikTok page.

    The resolver page is read and the first direct media link is used. No
    watermark is stripped and the original creator credit is left intact.
    """
    resolved = fetch_text(page_url)
    match = DOWNLOAD_LINK_PATTERN.search(resolved)
    if not match:
        raise DiscoveryError(f"Rejected: no media download link was found for {page_url}")
    return match.group(0)


def download_to_temp(
    download_url: str,
    task_id: str,
    fetch_bytes: Callable[[str], bytes],
    destination_dir: Path = TEMP_DIR,
    referer: str = "",
) -> Path:
    """Download a resolved media link into the temp directory.

    The platform's signed media URLs are only served to a request that
    carries the session's cookies and the referring page, so a platform URL
    is fetched through the authorized browser session. Any other URL uses the
    supplied fetcher.
    """
    ensure_directories()
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"{task_id}.mp4"

    from eligibility import is_platform_media_url

    if is_platform_media_url(download_url):
        from poster import download_media_with_browser

        payload = download_media_with_browser(download_url, referer=referer)
    else:
        payload = fetch_bytes(download_url)
    if not payload:
        raise DiscoveryError("Rejected: the downloaded file was empty")
    with destination.open("wb") as media_file:
        media_file.write(payload)
    return destination


def register_download(
    path: Path,
    task_id: str,
    source_url: str,
    library: ContentLibrary | None = None,
) -> str:
    """Record the SHA256 of a downloaded file and block duplicates."""
    content_library = library or ContentLibrary()
    digest = sha256_file(path)
    if content_library.contains_hash(digest):
        existing = content_library.find_by_hash(digest) or {}
        raise DiscoveryError(
            "Duplicate content blocked: SHA256 "
            f"{digest} is already in the library "
            f"(task_id: {existing.get('task_id', 'unknown')})"
        )
    content_library.add_file(path, task_id, source_url, digest)
    return digest


def build_caption(video: DiscoveredVideo, base_caption: str) -> str:
    """Build the caption with creator credit, keeping the origin visible.

    The video title is included so the caption carries the source context, and
    the creator credit is always appended so the origin is never hidden. The
    result stays within the 150 character limit.
    """
    parts: list[str] = []
    base = base_caption.strip()
    if base:
        parts.append(base)
    title = video.title.strip()
    if title and title.lower() not in base.lower():
        parts.append(title)
    credit = creator_credit(video)
    # The credit is added once. When the analysis already carried it the
    # caption is not changed, so the origin stays visible exactly once.
    # The handle is looked for too, because the analysis and this
    # function may write the credit in a different wording.
    handle = video.creator.strip().lstrip("@").lower()
    already = bool(credit) and (
        credit.lower() in base.lower()
        or (handle and handle in base.lower())
    )
    if credit and not already:
        parts.append(credit)
    text = " - ".join(parts).strip()
    # The credit names the origin of the content, so it is never cut away.
    # When the caption is too long, the title is shortened instead.
    if len(text) > 150:
        from brain import fit_caption

        return fit_caption(text, credit)
    return text


def build_history_metadata(video: DiscoveredVideo, score: int) -> dict[str, Any]:
    """Return the audit metadata recorded with the task in history."""
    return {
        "source_url": video.source_url,
        "creator": video.creator,
        "views": video.views,
        "likes": video.likes,
        "score": score,
    }


def discover_trending(
    config: dict[str, Any],
    candidates: list[DiscoveredVideo],
    task_id: str,
    *,
    library: ContentLibrary | None = None,
) -> DiscoveryResult:
    """Select the top trending allowlisted candidate and download it to temp.

    The source is validated against the allowlist before anything is fetched.
    A duplicate hash is rejected and the file is kept for inspection.
    """
    for video in candidates:
        try:
            validate_source_permitted(video.source_url, config)
        except DiscoveryError as exc:
            return DiscoveryResult(status="REJECTED", candidates=candidates, reason=str(exc))

    selected = select_trending(candidates, config)
    if selected is None:
        return DiscoveryResult(
            status="NO_MATCH",
            candidates=candidates,
            reason="No allowlisted candidate met the discovery thresholds",
        )

    content_library = library or ContentLibrary()
    path = TEMP_DIR / f"{task_id}.mp4"
    digest = sha256_file(path) if path.exists() else ""
    if digest and content_library.contains_hash(digest):
        existing = content_library.find_by_hash(digest) or {}
        return DiscoveryResult(
            status="REJECTED",
            candidates=candidates,
            selected=selected,
            reason=(
                "Duplicate content blocked: SHA256 "
                f"{digest} is already in the library "
                f"(task_id: {existing.get('task_id', 'unknown')})"
            ),
        )
    return DiscoveryResult(
        status="READY",
        candidates=candidates,
        selected=selected,
        metadata={"sha256": digest, "library_path": str(content_library.path)},
    )


def is_test_data_path(path: Path | str) -> bool:
    """Return True when a path points at TEST data rather than production data."""
    text = str(path).replace("\\", "/").lower()
    if str(PRODUCTION_CANDIDATES_DIR).replace("\\", "/").lower() in text:
        return False
    normalised = text.lstrip("./")
    for legacy in LEGACY_TEST_CANDIDATE_FILES:
        if normalised == legacy:
            return True
    parts = [part for part in text.split("/") if part]
    for part in parts:
        for marker in TEST_DATA_MARKERS:
            if part == marker or part.startswith(f"{marker}-") or part.endswith(f"-{marker}"):
                return True
    return False


def load_candidates(path: Path, *, allow_test_data: bool = False) -> list[DiscoveredVideo]:
    """Load candidates from a JSON file of discovered videos.

    A production run refuses TEST data. The guard is explicit so a test
    fixture can never be selected by a production workflow.
    """
    path = Path(path)
    if not allow_test_data and is_test_data_path(path):
        raise TestDataRejectedError(
            f"Rejected: a production run may not read test data from {path}"
        )
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload.get("videos", payload) if isinstance(payload, dict) else payload
    candidates: list[DiscoveredVideo] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        candidates.append(
            DiscoveredVideo(
                source_url=str(item.get("source_url", "")),
                creator=str(item.get("creator", "")),
                title=str(item.get("title", "")),
                views=int(item.get("views", 0) or 0),
                likes=int(item.get("likes", 0) or 0),
                download_url=str(item.get("download_url", "")),
                source_name=str(item.get("source_name", "")),
                duration_seconds=float(item.get("duration_seconds", 0) or 0),
                posted_at=str(item.get("posted_at", "")),
                is_ai_generated=bool(
                    item.get("is_ai_generated", item.get("ai_generated", True))
                ),
                # An older record carries no AI-label fact, so the label stays
                # unknown instead of becoming a negative claim.
                ai_label_known=bool(
                    item.get("ai_label_known", item.get("is_ai_generated") is not None)
                ),
                topic=str(item.get("topic", "")),
            )
        )
    return candidates


def load_production_candidates(
    path: Path | None = None,
) -> list[DiscoveredVideo]:
    """Load candidates from the PRODUCTION candidate store only.

    Only files under ``data/production`` are accepted. Test fixtures are
    refused and the file is never searched anywhere else.
    """
    target = Path(path) if path is not None else PRODUCTION_CANDIDATES_FILE
    target = target.resolve()
    production_root = PRODUCTION_CANDIDATES_DIR.resolve()
    if production_root != target and production_root not in target.parents:
        raise TestDataRejectedError(
            f"Rejected: production discovery may only read from {production_root}"
        )
    return load_candidates(target)


__all__ = [
    "ACCEPT_SCORE",
    "DiscoveredVideo",
    "DiscoveryError",
    "DiscoveryResult",
    "HOLD_SCORE",
    "NoCandidatesFoundError",
    "PRODUCTION_CANDIDATES_DIR",
    "PRODUCTION_CANDIDATES_FILE",
    "RightsNotPermittedError",
    "SNAPTIK_RESOLVER_URL",
    "SourceNotAllowedError",
    "TEST_CANDIDATES_DIR",
    "TEST_CANDIDATES_FILE",
    "TestDataRejectedError",
    "TrendingScore",
    "allowed_sources",
    "build_caption",
    "build_history_metadata",
    "creator_credit",
    "discover_trending",
    "download_to_temp",
    "is_allowed_source",
    "is_test_data_path",
    "is_tiktok_url",
    "load_candidates",
    "load_production_candidates",
    "matching_sources",
    "rank_trending",
    "register_download",
    "resolve_download_link",
    "score_all_trending",
    "score_trending",
    "select_trending",
    "source_creator",
    "url_creator",
    "validate_source_permitted",
]
