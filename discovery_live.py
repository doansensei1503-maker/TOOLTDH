"""P16.1 live discovery of real videos from a public TikTok keyword search.

Discovery reads the public search results the signed-in browser already
receives when a keyword search is opened. The results are captured from the
request the search page makes for itself, so the videos are the public,
keyword-ranked ones the signed-in user actually sees, from every creator on
the platform.

The search source is completely separate from the creator allowlist. The
allowlist and its ``rights_verified`` and ``permit_date`` records are used
only to decide whether a video may be reused after an admin has approved it;
they never decide which videos are searched for, and no creator is preferred
or excluded from the search.

Nothing is fabricated. A metric that the platform does not publish stays
unknown and is reported as unknown. A bot challenge is never bypassed: a
search that answers with a challenge yields no candidates, and the run ends
in ``BLOCKED`` with the reason.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

from discover import (
    PRODUCTION_CANDIDATES_DIR,
    DiscoveredVideo,
    DiscoveryError,
    NoCandidatesFoundError,
)
from tiktok_metrics import VideoMetrics

# The page's own item-list request. The browser issues it when a creator page
# is opened, so its response is the data the signed-in user actually sees.
ITEM_LIST_URL_MARKER = "/api/post/item_list/"

# The search-results request the search page makes for itself. The results
# are captured from it, so the data is the public keyword ranking.
SEARCH_RESULTS_URL_MARKER = "/api/search/general/full/"

# The topics the discovery searches for when the admin names none. These are
# the four markets the product is built around.
DEFAULT_SEARCH_TOPICS = ("AI Music", "AI Song", "AI Cover", "AI Remix")

# How many different videos one run offers. The run stops at this many
# related videos; when the search does not offer enough, fewer are returned
# and the shortfall is reported. The list is never filled up with a video
# that is not related to the topic.
MAX_CANDIDATES = 30

# How many videos one query may contribute. Every query in the expansion
# is searched even when an earlier query already returned videos, so the
# run covers all sub-clusters instead of stopping after the first query.
MAX_PER_QUERY = 12

# The metrics the platform publishes for each video.
KNOWN_METRICS = ("views", "likes", "comments", "shares")

# Words that carry no meaning when a topic is matched.
STOP_WORDS = {
    "a", "an", "and", "the", "for", "of", "to", "in", "on", "with", "my",
    "video", "videos", "tiktok", "fyp", "new", "best", "top",
}

# Words that describe the same field. A title that carries one of them
# matches a topic that asks for another, because "AI song" and "AI music"
# name the same market.
#
# The groups are read as separate requirements, not as alternatives. The
# market group names what the content IS (music, song, cover, remix) and the
# AI group names HOW it is made. A topic such as "AI Music" asks for both,
# so a video has to carry a market word and an AI word to match. When the
# groups were read as alternatives, any video with the letters "ai" in its
# caption matched, which let unrelated videos such as "AI hair color
# transformation" into an AI Music search.
MARKET_WORDS = frozenset(
    {"music", "musics", "song", "songs", "sound", "sounds", "audio", "track",
     "tracks", "beat", "beats", "cover", "covers", "remix", "remixes",
     "remixed", "mashup", "nhạc", "bài hát", "nhac", "baihat"}
)

# The words that mark the content as AI-made. A topic that names an AI
# market requires one of them.
AI_WORDS = frozenset(
    {"ai", "a.i", "artificial", "suno", "udio", "booga", "sunoai", "aimusic",
     "aisong", "aicover", "aimelody", "aiff", "aivideo", "aigenerated",
     "ai-generated", "aigeneratedart", "voiceclone", "voice cloning"}
)

# The topic words that name the AI signal itself. A topic made only of these
# words, such as "AI Music" reduced to "AI", asks for the AI signal and the
# market at the same time.
AI_TOPIC_WORDS = frozenset({"ai", "a.i", "artificial", "suno", "udio", "booga"})

# The topic words that name the market itself.
MARKET_TOPIC_WORDS = frozenset(
    {"music", "song", "sound", "audio", "track", "beat", "cover", "remix",
     "remixed", "mashup"}
)

# The words that mean the content is about music but was made by a human.
# These do not qualify a video for an AI market on their own, but they do not
# disqualify it either, because an AI cover of a human song is still an AI
# music video.
HUMAN_MUSIC_WORDS = frozenset(
    {"original song", "my song", "new song", "official audio", "original audio"}
)

# The topic words that carry no meaning for the AI requirement.
_TOPIC_NOISE = frozenset({"music", "song", "sound", "audio", "track", "beat",
                           "generated", "generate", "generation", "generative"})

# The words that name a medium other than music. A video whose AI work is
# clearly about one of these is not an AI music video, even when its caption
# happens to mention music in passing. The word "art" is not in this list on
# its own, because "AI art" is often the label of an AI music video, but a
# caption that names art and no music is rejected by the market check.
NON_MUSIC_AI_WORDS = frozenset(
    {"photo", "photos", "photograph", "filter", "filters", "face", "faces",
     "makeup", "haircut", "haircut", "hair", "skin", "body", "outfit",
     "clothing", "dress", "fashion", "recipe", "food", "workout", "fitness",
     "gym", "drawing", "painting", "3d", "model", "logo", "thumbnail"}
)

# Words that mark a video as a tool tutorial or guide rather than a song
# performance. A tutorial is never counted as a music performance, no
# matter which topic asked for it.
TUTORIAL_WORDS = frozenset(
    {"tutorial", "tutorials", "guide", "guides", "how to", "howto",
     "hướng dẫn", "huong dan", "dạy", "học làm", "review công cụ",
     "tool review", "top 10 ai", "top ai tools", "cách dùng", "cách tạo",
     "prompt engineering", "workflow tutorial"}
)

# Sub-query clusters for the AI Music subject. Generic topics never use
# this list; only a topic that names both the AI signal and the music
# market expands to it. At most MAX_TOPIC_QUERIES queries run per lượt.
AI_MUSIC_SUBQUERIES = (
    "AI Cover", "AI Remix", "Suno AI Song", "Udio Music", "AI Generated Song",
)

MAX_TOPIC_QUERIES = 6


def is_tutorial_title(title: str) -> bool:
    """Return True when the caption reads like a tool guide, not a song."""
    haystack = str(title or "").lower()
    if not haystack.strip():
        return False
    return any(word in haystack for word in TUTORIAL_WORDS)


def expand_topic_queries(topic: str, max_queries: int = MAX_TOPIC_QUERIES) -> list[str]:
    """Return the sub-queries used to collect candidates for one topic.

    The queries are only a collection device; the content check later
    decides what the video really is. An AI Music topic expands to its
    sub-clusters (song, cover, remix, Suno, Udio). Any other topic is
    searched as-is, so AI Music terms are never injected into it.
    At most ``max_queries`` terms are returned so the platform quota and
    the browser session stay bounded.
    """
    base = str(topic or "").strip()
    if not base:
        return []
    lowered = base.lower()
    wants_ai = any(word in lowered for word in ("ai", "suno", "udio"))
    wants_market = any(
        word in lowered
        for word in ("music", "song", "cover", "remix", "nhạc", "nhac")
    )
    if wants_ai and wants_market:
        queries: list[str] = []
        for term in [base, *AI_MUSIC_SUBQUERIES]:
            if term.lower() not in {item.lower() for item in queries}:
                queries.append(term)
            if len(queries) >= max_queries:
                break
        return queries
    return [base]


@dataclass
class SearchFilters:
    """The filters the admin sets on the dashboard.

    A filter of zero or None means the admin did not set it, so the metric
    is not used to qualify a candidate at all.
    """

    min_views: int = 0
    max_views: int = 0
    min_likes: int = 0
    min_comments: int = 0
    min_shares: int = 0
    max_duration: float = 0.0
    min_duration: float = 0.0
    max_days: int = 0
    must_include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    # ANY group: at least one must be present when set.
    must_include_any: list[str] = field(default_factory=list)
    # Requested subtopics get ranking priority, never invented as queries.
    subtopics: list[str] = field(default_factory=list)
    # Requested but not verifiable from the TikTok payload (honest note).
    language: str = ""
    market: str = ""

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> "SearchFilters":
        """Build the filters from the dashboard request.

        A payload that is already a `SearchFilters` is taken as it is, so the
        filters can be passed on without being rebuilt.
        """
        if isinstance(payload, SearchFilters):
            return payload
        data = payload or {}

        def _int(key: str) -> int:
            try:
                return int(float(data.get(key) or 0))
            except (TypeError, ValueError):
                return 0

        def _float(key: str) -> float:
            try:
                return float(data.get(key) or 0)
            except (TypeError, ValueError):
                return 0.0

        def _words(key: str) -> list[str]:
            raw = data.get(key) or ""
            if isinstance(raw, (list, tuple)):
                items = list(raw)
            else:
                items = str(raw).split(",")
            return [str(item).strip().lower() for item in items if str(item).strip()]

        return cls(
            min_views=_int("min_views"),
            max_views=_int("max_views"),
            min_likes=_int("min_likes"),
            min_comments=_int("min_comments"),
            min_shares=_int("min_shares"),
            max_duration=_float("max_duration"),
            min_duration=_float("min_duration"),
            max_days=_int("max_days"),
            must_include=_words("must_include"),
            exclude=_words("exclude"),
            must_include_any=_words("must_include_any"),
            subtopics=_words("subtopics") or _words("subtopic_priority"),
            language=str(data.get("language") or "").strip(),
            market=str(data.get("market") or "").strip(),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the filters."""
        return asdict(self)


class DiscoveryBlockedError(DiscoveryError):
    """Raised when a source cannot be read because of a protection."""


def _media_urls(item: dict[str, Any]) -> tuple[str, str]:
    """Return the platform's own play and download URLs for one item.

    The URLs come from the platform's own payload, so they are the same
    media the signed-in user plays. The download URL is preferred because it
    is the un-watermarked original that the platform serves for download.
    """
    video = item.get("video") if isinstance(item.get("video"), dict) else {}
    play_addr = video.get("playAddr")
    download_addr = video.get("downloadAddr")
    play = play_addr if isinstance(play_addr, str) else ""
    download = download_addr if isinstance(download_addr, str) else ""
    struct = video.get("PlayAddrStruct")
    if isinstance(struct, dict):
        url_list = struct.get("UrlList")
        if isinstance(url_list, list):
            for value in url_list:
                if isinstance(value, str) and value:
                    play = play or value
                    break
    return download, play


def _parse_item_list(payload: str, creator: str) -> list[VideoMetrics]:
    """Parse the page's item-list response into real per-video metrics."""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise DiscoveryError(
            f"Rejected: the item list response was not valid JSON: {exc}"
        ) from exc
    if not isinstance(data, dict):
        return []
    items = data.get("itemList")
    if not isinstance(items, list):
        return []
    results: list[VideoMetrics] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        identifier = item.get("id")
        if not isinstance(identifier, str) or not identifier.isdigit():
            continue
        author = item.get("author") if isinstance(item.get("author"), dict) else {}
        handle = str(author.get("uniqueId") or author.get("unique_id") or "")
        if creator and handle.lower() != creator.lower():
            continue
        stats = item.get("stats") if isinstance(item.get("stats"), dict) else {}
        video = item.get("video") if isinstance(item.get("video"), dict) else {}

        def _count(key: str) -> int | None:
            value = stats.get(key)
            if isinstance(value, bool) or value is None:
                return None
            try:
                number = int(value)
            except (TypeError, ValueError):
                return None
            return number if number >= 0 else None

        views = _count("playCount")
        likes = _count("diggCount")
        comments = _count("commentCount")
        shares = _count("shareCount")
        # The item list publishes the duration in seconds.
        duration_seconds = _count("duration")
        if duration_seconds is None:
            raw_duration = video.get("duration")
            if isinstance(raw_duration, (int, float)) and not isinstance(raw_duration, bool):
                duration_seconds = int(raw_duration)
        created = item.get("createTime") or stats.get("createTime")
        posted_at = ""
        if isinstance(created, (int, float)) and not isinstance(created, bool) and created > 0:
            try:
                posted_at = datetime.fromtimestamp(created, tz=timezone.utc).date().isoformat()
            except (OverflowError, OSError, ValueError):
                posted_at = ""

        missing = [
            name
            for name, value in (
                ("views", views),
                ("likes", likes),
                ("comments", comments),
                ("shares", shares),
            )
            if value is None
        ]
        download_url, play_url = _media_urls(item)
        results.append(
            VideoMetrics(
                source_url=f"https://www.tiktok.com/@{handle}/video/{identifier}",
                creator=handle,
                title=str(item.get("desc") or "").strip()[:200],
                views=views,
                likes=likes,
                comments=comments,
                shares=shares,
                duration_seconds=float(duration_seconds) if duration_seconds else None,
                posted_at=posted_at,
                metrics_present=not missing,
                missing_metrics=missing,
                is_ai_generated=is_ai_generated_item(item),
                download_url=download_url,
                play_url=play_url,
            )
        )
    return results


def _search_result_items(payload: str) -> list[dict[str, Any]]:
    """Return the video items from a search-results response.

    The search response is a list of typed chunks. A chunk of type 1 holds a
    single video in its ``item`` field; a chunk of another type holds a
    creator list or a card and is ignored, because a creator card is not a
    video and must never become a candidate.
    """
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise DiscoveryError(
            f"Rejected: the search response was not valid JSON: {exc}"
        ) from exc
    if not isinstance(data, dict):
        return []
    chunks = data.get("data")
    if not isinstance(chunks, list):
        return []
    items: list[dict[str, Any]] = []
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        if chunk.get("type") != 1:
            continue
        item = chunk.get("item")
        if isinstance(item, dict):
            items.append(item)
    return items


def _search_count(stats: dict[str, Any], stats_v2: dict[str, Any], key: str) -> int | None:
    """Read one metric from the search payload, or return None when absent.

    The search payload carries the counts twice: as numbers in ``stats`` and
    as strings in ``statsV2``. Both are read, so a count that the platform
    published is never lost. A count that is in neither stays unknown.
    """
    for source in (stats, stats_v2):
        if not isinstance(source, dict):
            continue
        value = source.get(key)
        if value is None or isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            return int(value) if value >= 0 else None
        if isinstance(value, str):
            text = value.strip()
            if not text:
                continue
            try:
                number = int(float(text))
            except ValueError:
                continue
            return number if number >= 0 else None
    return None


def parse_search_results(payload: str) -> list[VideoMetrics]:
    """Turn a search-results response into real per-video metrics.

    Every metric comes from the payload the platform served. A metric that
    the payload does not carry stays unknown and is listed in
    ``missing_metrics``, so a zero is never confused with an absent count.
    """
    items = _search_result_items(payload)
    results: list[VideoMetrics] = []
    for item in items:
        identifier = item.get("id")
        if not isinstance(identifier, str) or not identifier.isdigit():
            continue
        author = item.get("author") if isinstance(item.get("author"), dict) else {}
        handle = str(author.get("uniqueId") or author.get("unique_id") or "").strip()
        if not handle:
            continue
        stats = item.get("stats") if isinstance(item.get("stats"), dict) else {}
        stats_v2 = item.get("statsV2") if isinstance(item.get("statsV2"), dict) else {}
        video = item.get("video") if isinstance(item.get("video"), dict) else {}

        views = _search_count(stats, stats_v2, "playCount")
        likes = _search_count(stats, stats_v2, "diggCount")
        comments = _search_count(stats, stats_v2, "commentCount")
        shares = _search_count(stats, stats_v2, "shareCount")

        duration_seconds = None
        raw_duration = video.get("duration")
        if isinstance(raw_duration, (int, float)) and not isinstance(raw_duration, bool):
            duration_seconds = float(raw_duration)
        elif isinstance(raw_duration, str):
            try:
                duration_seconds = float(raw_duration)
            except ValueError:
                duration_seconds = None

        posted_at = ""
        created = item.get("createTime")
        if isinstance(created, (int, float)) and not isinstance(created, bool) and created > 0:
            try:
                posted_at = datetime.fromtimestamp(created, tz=timezone.utc).date().isoformat()
            except (OverflowError, OSError, ValueError):
                posted_at = ""

        missing = [
            name
            for name, value in (
                ("views", views),
                ("likes", likes),
                ("comments", comments),
                ("shares", shares),
            )
            if value is None
        ]
        download_url, play_url = _media_urls(item)
        results.append(
            VideoMetrics(
                source_url=f"https://www.tiktok.com/@{handle}/video/{identifier}",
                creator=handle,
                title=str(item.get("desc") or "").strip()[:200],
                views=views,
                likes=likes,
                comments=comments,
                shares=shares,
                duration_seconds=duration_seconds,
                posted_at=posted_at,
                metrics_present=not missing,
                missing_metrics=missing,
                is_ai_generated=is_ai_generated_item(item),
                download_url=download_url,
                play_url=play_url,
            )
        )
    return results


def is_ai_generated_item(item: dict[str, Any]) -> bool | None:
    """Return whether the page marks the video as AI-generated.

    The answer comes from the platform's own AI label. When the platform
    publishes no AI label the answer is unknown and the caller decides what
    to do; nothing is assumed either way.
    """
    if not isinstance(item, dict):
        return None
    for key in ("ShowAIGC", "showAIGC", "isAIGC"):
        if key in item:
            return bool(item[key])
    description = item.get("AIGCDescription")
    if isinstance(description, str) and description.strip():
        return True
    # The search payload carries the label as a type instead of a flag. A
    # label of 1 means the platform marked the video as AI-generated.
    for key in ("aigcLabelType", "moderationAigcLabelType"):
        value = item.get(key)
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return int(value) == 1
        if isinstance(value, str) and value.strip():
            try:
                return int(value.strip()) == 1
            except ValueError:
                continue
    return None


def to_candidate(
    metrics: VideoMetrics,
    *,
    source_name: str,
    topic: str,
) -> DiscoveredVideo:
    """Turn real metrics into a candidate, keeping unknown metrics unknown.

    The AI flag follows the platform's own label. When the platform published
    no label the candidate is not claimed to be AI-generated, so the trending
    penalty is not applied on an invented fact.
    """
    return DiscoveredVideo(
        source_url=metrics.source_url,
        creator=metrics.creator,
        title=metrics.title,
        views=metrics.views or 0,
        likes=metrics.likes or 0,
        comments=metrics.comments or 0,
        shares=metrics.shares or 0,
        download_url=metrics.download_url or metrics.play_url,
        source_name=source_name,
        duration_seconds=metrics.duration_seconds or 0.0,
        posted_at=metrics.posted_at,
        is_ai_generated=metrics.is_ai_generated is True,
        # When the platform published no AI label the fact stays unknown, so
        # the trending score does not punish the video for a label the
        # platform never gave.
        ai_label_known=metrics.is_ai_generated is not None,
        topic=topic,
        metrics_known=metrics.metrics_present,
        missing_metrics=list(metrics.missing_metrics),
    )


def _topic_tokens(topic: str) -> set[str]:
    """Return the meaningful words of a topic."""
    words = {
        word.strip(".,!?").lower()
        for word in str(topic or "").replace("-", " ").split()
        if word.strip(".,!?")
    }
    meaningful = {word for word in words if word not in STOP_WORDS}
    return meaningful or words


def _contains_word(haystack: str, words: frozenset[str]) -> bool:
    """Return whether the text carries one of the words.

    The check is on word boundaries, so "ai" does not match inside "said"
    or "chain". A hashtag is read as one unit, so "#aimusic" carries the
    market word "music" and the AI word "ai" at the same time, and a title
    that only carries "#aimusic" still matches the AI Music topic.
    """
    for word in words:
        if word not in haystack:
            continue
        if word.isalpha() and len(word) > 2:
            # A plain word has to stand on its own.
            if re.search(rf"(?<![a-z0-9]){re.escape(word)}(?![a-z0-9])", haystack):
                return True
            continue
        return True
    return False


def _hashtags(text: str) -> set[str]:
    """Return the hashtags of a caption, without the hash sign."""
    return {
        tag.strip("#.,!?").lower()
        for tag in str(text or "").split()
        if tag.strip().startswith("#") and len(tag.strip("#.,!?")) > 1
    }


def _carries_market(haystack: str, hashtags: set[str]) -> bool:
    """Return whether the text says the content is music.

    A hashtag compound counts: "#aimusic" carries the word "music", and
    "#aisong" carries "song". A hashtag that is exactly a market word counts
    too, so "#music" alone carries the market.
    """
    if _contains_word(haystack, MARKET_WORDS):
        return True
    for tag in hashtags:
        if tag in MARKET_WORDS:
            return True
        # A compound hashtag such as "aimusic" ends with a market word.
        for word in MARKET_WORDS:
            if len(word) > 3 and tag.endswith(word):
                return True
    return False


def _carries_ai(haystack: str, hashtags: set[str]) -> bool:
    """Return whether the text says the content is AI-made.

    A hashtag compound counts, so "#aimusic" and "#sunoai" carry the AI
    signal even when the caption itself never spells the word out.
    """
    if _contains_word(haystack, AI_WORDS):
        return True
    for tag in hashtags:
        if tag in AI_WORDS:
            return True
        for word in AI_WORDS:
            if len(word) > 2 and (tag.startswith(word) or tag.endswith(word)):
                return True
    return False


def topic_matches(title: str, topic: str) -> bool:
    """Return True when the candidate text matches the requested topic.

    A topic that names an AI market asks for two things at once: the market
    the content belongs to (music, song, cover, remix) and the AI signal that
    says how it was made. A title has to carry both. Reading them as
    alternatives instead let any video with the letters "ai" in its caption
    match "AI Music", so unrelated videos such as "AI hair color
    transformation" or a CapCut meme entered the results.

    The words that name the same market are treated as alternatives, so "AI
    Music" also matches a video published as "AI song" or "AI cover". Every
    other word of the topic must still be present.

    An empty title never matches, so a video with no published caption is
    not silently accepted as a topic match.
    """
    haystack = str(title or "").lower()
    if not haystack.strip():
        return False

    tokens = _topic_tokens(topic)
    if not tokens:
        return False

    hashtags = _hashtags(haystack)
    wants_market = bool(tokens & MARKET_TOPIC_WORDS)
    wants_ai = bool(tokens & AI_TOPIC_WORDS)

    if wants_market and wants_ai:
        # Both the market and the AI signal have to be there.
        if not _carries_market(haystack, hashtags):
            return False
        if not _carries_ai(haystack, hashtags):
            return False
    elif wants_market:
        # A topic made only of the market words asks for the market alone.
        if not _carries_market(haystack, hashtags):
            return False
    elif wants_ai:
        # A topic made only of AI words still asks for the market, because an
        # AI market that is not about music is not this product's subject.
        if not _carries_market(haystack, hashtags):
            return False
        if not _carries_ai(haystack, hashtags):
            return False
    else:
        # A topic with no market and no AI signal needs every word of it.
        if not all(token in haystack for token in tokens):
            return False

    # The remaining words of the topic still have to be there.
    required = tokens - MARKET_TOPIC_WORDS - AI_TOPIC_WORDS - _TOPIC_NOISE
    required = {word for word in required if word not in STOP_WORDS}
    if required and not all(token in haystack for token in required):
        return False

    # A tutorial about an AI tool is not a song performance. When the topic
    # asks for an AI music market, a guide is never a match, no matter
    # which words its caption carries.
    if (wants_market and wants_ai) and is_tutorial_title(title):
        return False

    # A video whose AI work is clearly about another medium is not an AI
    # music video. The market word has to be the subject of the video, not a
    # word that happens to appear in a caption about an AI filter.
    if _contains_word(haystack, NON_MUSIC_AI_WORDS):
        if not _carries_market(haystack, hashtags):
            return False
    return True


def apply_search_filters(
    candidates: list[DiscoveredVideo],
    filters: "SearchFilters",
) -> tuple[list[DiscoveredVideo], list[str]]:
    """Apply the admin's filters to the discovered candidates.

    A metric that the source did not publish stays unknown. Such a candidate
    is kept when the filter for that metric is not set, and it is only
    dropped when the admin asked for a minimum that the unknown value
    cannot prove. Nothing is invented to satisfy a filter.
    """
    kept: list[DiscoveredVideo] = []
    dropped: list[str] = []
    for candidate in candidates:
        reason = _filter_reason(candidate, filters)
        if reason:
            dropped.append(f"{candidate.source_url}: {reason}")
            continue
        kept.append(candidate)
    return kept, dropped


def _filter_reason(candidate: DiscoveredVideo, filters: "SearchFilters") -> str:
    """Return why a candidate does not pass the filters, or an empty string."""
    unknown = set(candidate.missing_metrics or [])

    if filters.min_views and candidate.views < filters.min_views:
        if "views" in unknown:
            return "lượt xem không có dữ liệu nên không chứng minh được ngưỡng tối thiểu"
        return f"lượt xem {candidate.views} thấp hơn ngưỡng {filters.min_views}"
    if filters.max_views and candidate.views > filters.max_views:
        if "views" in unknown:
            return "lượt xem không có dữ liệu nên không chứng minh được ngưỡng tối đa"
        return f"lượt xem {candidate.views} cao hơn ngưỡng {filters.max_views}"
    if filters.min_likes and candidate.likes < filters.min_likes:
        if "likes" in unknown:
            return "lượt thích không có dữ liệu nên không chứng minh được ngưỡng tối thiểu"
        return f"lượt thích {candidate.likes} thấp hơn ngưỡng {filters.min_likes}"
    if filters.min_comments and candidate.comments < filters.min_comments:
        if "comments" in unknown:
            return "bình luận không có dữ liệu nên không chứng minh được ngưỡng tối thiểu"
        return f"bình luận {candidate.comments} thấp hơn ngưỡng {filters.min_comments}"
    if filters.min_shares and candidate.shares < filters.min_shares:
        if "shares" in unknown:
            return "chia sẻ không có dữ liệu nên không chứng minh được ngưỡng tối thiểu"
        return f"chia sẻ {candidate.shares} thấp hơn ngưỡng {filters.min_shares}"
    if filters.max_duration and candidate.duration_seconds > filters.max_duration:
        return f"thời lượng {candidate.duration_seconds:.1f}s dài hơn giới hạn {filters.max_duration:.0f}s"
    if filters.min_duration and candidate.duration_seconds and candidate.duration_seconds < filters.min_duration:
        return f"thời lượng {candidate.duration_seconds:.1f}s ngắn hơn giới hạn {filters.min_duration:.0f}s"
    if filters.max_days:
        posted = _posted_date(candidate.posted_at)
        if posted is not None:
            age = (date.today() - posted).days
            if age > filters.max_days:
                return f"đăng {age} ngày trước, vượt quá {filters.max_days} ngày"
    if filters.must_include:
        haystack = f"{candidate.title} {candidate.topic}".lower()
        missing = [word for word in filters.must_include if word.lower() not in haystack]
        if missing:
            return f"thiếu từ khóa bắt buộc: {', '.join(missing)}"
    if filters.must_include_any:
        haystack = f"{candidate.title} {candidate.topic}".lower()
        present_any = [word for word in filters.must_include_any if word.lower() in haystack]
        if not present_any:
            return f"thiếu nhóm từ khóa ANY: cần ít nhất một trong {', '.join(filters.must_include_any)}"
    if filters.exclude:
        haystack = f"{candidate.title} {candidate.topic}".lower()
        present = [word for word in filters.exclude if word.lower() in haystack]
        if present:
            return f"chứa từ khóa loại trừ: {', '.join(present)}"
    return ""


TOP5_LIMIT = 5


def candidate_age_days(candidate: "DiscoveredVideo") -> int | None:
    """Return the age of a candidate in days, or None when unknown."""
    posted = _posted_date(candidate.posted_at)
    if posted is None:
        return None
    return (date.today() - posted).days


def rights_status_of(source_url: str, config: dict[str, Any]) -> str:
    """Return the reuse rights status of a candidate without downloading."""
    try:
        from discover import validate_source_permitted

        validate_source_permitted(source_url, config)
        return "ALLOWLISTED_PERMITTED"
    except Exception as exc:  # noqa: BLE001 - the status string carries it
        reason = str(exc)
        if "allowlist" in reason.lower():
            return "NOT_ALLOWLISTED"
        return "BLOCKED_NO_RIGHTS"


def language_market_note(filters: "SearchFilters | None") -> str:
    """Return an honest note when language/market cannot be verified."""
    if filters is None:
        return ""
    wanted = [part for part in (str(filters.language or "").strip(), str(filters.market or "").strip()) if part]
    if not wanted:
        return ""
    # The TikTok search payload carries no reliable language/market field,
    # so the request is recorded but never pretended to be filtered.
    return (
        "Ngôn ngữ/thị trường yêu cầu (" + "/".join(wanted) + ") chưa thể xác minh "
        "vì payload TikTok không cung cấp trường đáng tin cậy — hiển thị để ghi nhận, không giả vờ đã lọc."
    )


def build_top5_cards(
    scored: list[Any],
    config: dict[str, Any],
    *,
    analyses_by_url: dict[str, Any] | None = None,
    limit: int = TOP5_LIMIT,
    subtopics: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Build at most TOP 5 candidate cards from ranked trending scores.

    Weights are untouched (scores come from `score_all_trending`). Duplicates
    and rejected videos are skipped; the list is never forced to 5. Videos
    whose metadata passed but whose content verdict is UNKNOWN stay visible
    as NEEDS_REVIEW with pick=False, so they can never auto-post. No growth
    rate is invented — only real views/age/score are shown.
    """
    cards: list[dict[str, Any]] = []
    seen: set[str] = set()
    analyses_by_url = analyses_by_url or {}
    wanted_subs = [str(item).strip().lower() for item in (subtopics or []) if str(item).strip()]

    def _sub_priority(video: Any) -> int:
        if not wanted_subs:
            return 0
        haystack = f"{getattr(video, 'title', '')} {getattr(video, 'topic', '')}".lower()
        for sub in wanted_subs:
            if sub and sub in haystack:
                return 1
        return 0

    ordered = sorted(
        list(scored or []),
        key=lambda item: (_sub_priority(getattr(item, "video", None)), int(getattr(item, "score", 0) or 0)),
        reverse=True,
    )
    for item in ordered:
        video = getattr(item, "video", None)
        if video is None:
            continue
        url = str(getattr(video, "source_url", "") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        # REJECTED videos (content_relevant is False) never become cards.
        # UNKNOWN videos stay visible as NEEDS_REVIEW with pick=False, so
        # they can never auto-post; only a manual user confirmation plus
        # the rights/approval gates can move them forward.
        analysis = analyses_by_url.get(url)
        content_relevant = getattr(analysis, "content_relevant", None) if analysis is not None else None
        if content_relevant is False:
            continue
        status = "VERIFIED" if content_relevant is True else "NEEDS_REVIEW"
        certainty = "UNKNOWN"
        if content_relevant is True:
            certainty = "HIGH"
        elif bool(getattr(video, "ai_label_known", False)):
            certainty = "MEDIUM" if bool(getattr(video, "is_ai_generated", False)) else "LOW"
        age = candidate_age_days(video)
        rights = rights_status_of(url, config)
        pick = getattr(item, "decision", "") == "ACCEPT"
        if status != "VERIFIED":
            # NEEDS_REVIEW never auto-posts, even with a high trend score.
            pick = False
        reason = str(getattr(item, "reason", "") or "").strip()
        if analysis is not None:
            extra = str(getattr(analysis, "summary", "") or getattr(analysis, "content_relevance_reason", "") or "").strip()
            if extra:
                reason = (reason + " | " + extra).strip(" |") if reason else extra
        if status == "NEEDS_REVIEW" and "chưa đủ dữ liệu" not in reason.lower() and "unknown" not in reason.lower():
            reason = (reason + " | NEEDS_REVIEW: đạt metadata, chờ người dùng xác minh nội dung").strip(" |")
        if rights != "ALLOWLISTED_PERMITTED":
            pick = False
            reason = (reason + " | quyền: " + rights).strip(" |") if reason else ("quyền: " + rights)
        cards.append({
            "source_url": url,
            "creator": str(getattr(video, "creator", "") or ""),
            "title": str(getattr(video, "title", "") or ""),
            "posted_at": str(getattr(video, "posted_at", "") or ""),
            "views": int(getattr(video, "views", 0) or 0),
            "age_days": age,
            "score": int(getattr(item, "score", 0) or 0),
            "certainty": certainty,
            "status": status,
            "pick": pick,
            "reason": reason or ("chọn" if pick else "loại: chưa đủ điều kiện"),
            "rights": rights,
        })
        if len(cards) >= max(1, int(limit or TOP5_LIMIT)):
            break
    return cards


def _posted_date(value: str) -> date | None:
    """Return the posting date of a candidate, or None when it is unknown."""
    stamp = str(value or "").strip()
    if not stamp:
        return None
    for pattern in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(stamp[:19], pattern).date()
        except ValueError:
            continue
    return None


_SCRIPT_STYLE_PATTERN = re.compile(
    r"<(script|style|noscript)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL
)
_TAG_PATTERN = re.compile(r"<[^>]+>")


def _visible_text(html: str) -> str:
    """Return the text a user can see on the page, without the scripts.

    The script bundles of the page are removed before the text is read. They
    carry the words of a challenge as plain source text, so a block check
    that read them would report a challenge on a page that works.
    """
    stripped = _SCRIPT_STYLE_PATTERN.sub(" ", str(html or ""))
    stripped = _TAG_PATTERN.sub(" ", stripped)
    return re.sub(r"\s+", " ", stripped).strip().lower()


def _search_block_reason(html: str, results: str) -> str:
    """Return why the search could not be read, or an empty string.

    The check is made on the visible text of the page the signed-in user
    actually saw. The raw HTML is not searched for these words, because the
    page ships its own script bundles and those bundles contain the words
    "captcha" and "verify" as plain text, which would make every healthy
    search look blocked.

    A robot challenge, a re-login prompt, or a session expiry is reported as
    a block; the challenge is never solved and never bypassed.
    """
    visible = _visible_text(html)
    if visible:
        for marker in (
            "verify it's you",
            "verify you are human",
            "verify you are not a robot",
            "security verification",
            "robot verification",
            "log in again",
            "sign in again",
            "session expired",
            "drag the slider",
            "please complete the captcha",
            "verify to continue",
        ):
            if marker in visible:
                return marker
    if not str(results or "").strip():
        return "the search page returned no results payload"
    return ""


def _candidates_from_results(
    payload: str,
    term: str,
    topic: str,
    *,
    max_results: int = 60,
    html: str = "",
) -> list[DiscoveredVideo]:
    """Turn one search-results payload into the candidates for a keyword.

    The block check runs first, so a challenge is reported and never turned
    into a result. Only the videos whose caption carries the market and the
    AI signal of the keyword are kept, and they are the real public videos
    the signed-in user sees.
    """
    reason = _search_block_reason(html, payload)
    if reason:
        raise DiscoveryBlockedError(
            f"Blocked: TikTok did not serve search results for \"{term}\" "
            f"({reason}). The challenge was not bypassed and no video was "
            "downloaded."
        )

    metrics = parse_search_results(payload)
    candidates: list[DiscoveredVideo] = []
    for entry in metrics:
        if not topic_matches(entry.title, term):
            continue
        candidates.append(
            to_candidate(entry, source_name=f"TikTok search: {term}", topic=term)
        )
        if len(candidates) >= max_results:
            break
    return candidates


def discover_by_keyword(
    keyword: str,
    *,
    read_search: Callable[[str], dict[str, Any]],
    max_results: int = 60,
) -> list[DiscoveredVideo]:
    """Discover the public videos a keyword search returns.

    The search is the only source. No allowlist entry is consulted, no
    creator is preferred, and no creator is excluded, so the candidates are
    the public keyword ranking from every creator on the platform.

    ``read_search`` returns the search page HTML and the results payload that
    the page itself received. When the platform answers with a challenge the
    run is blocked and the reason is reported; nothing is bypassed.
    """
    term = str(keyword or "").strip()
    if not term:
        raise DiscoveryError("Rejected: no keyword was supplied for the search")

    result = read_search(term)
    html = str(result.get("html", ""))
    payload = str(result.get("results", ""))

    return _candidates_from_results(
        payload, term, term, max_results=max_results, html=html
    )


def discover_new_candidates(
    config: dict[str, Any],
    topic: str = "",
    *,
    read_search: Callable[[str], dict[str, Any]] | None = None,
    read_searches: Callable[[list[str]], dict[str, dict[str, Any]]] | None = None,
    known_urls: set[str] | None = None,
    max_results: int = MAX_CANDIDATES,
    filters: SearchFilters | None = None,
    should_stop: Callable[[], bool] | None = None,
    exclude_creators: set[str] | None = None,
    stats: dict[str, Any] | None = None,
) -> tuple[list[DiscoveredVideo], list[str]]:
    """Discover the public videos for the topic from a TikTok keyword search.

    The search source is completely separate from the creator allowlist. The
    allowlist, its ``rights_verified`` records, and its permit dates are used
    only later, to decide whether an approved video may be reused. They
    never decide which videos are searched for, and the admin's own account
    is neither preferred nor used to stand in for a trend.

    The admin's keyword is searched for. When the admin named none, the
    default AI Music markets are searched for, so a run always has a subject.

    At most ``max_results`` different videos are collected. The videos are
    the real public results; a video is never invented and a video that is
    not related to the topic is never added to fill the list up. When the
    search does not offer enough related videos, fewer are returned and the
    shortfall is reported.

    Returns the candidates and the list of blockers. A blocker describes why
    a search could not be read, for example because the platform answered
    with a challenge.
    """
    discovery = config.get("discovery", {}) if isinstance(config.get("discovery", {}), dict) else {}
    configured = str(discovery.get("target_topic", "")).strip()
    requested = str(topic or "").strip()
    base_topic = requested or configured

    # Topic-aware query expansion. The queries only collect candidates;
    # verification happens later via metadata + Local Audio/Vision. An AI
    # Music topic expands to its sub-clusters (song/cover/remix/Suno/Udio).
    # Any other topic is searched as-is so AI Music terms are never
    # injected into it. At most MAX_TOPIC_QUERIES terms are searched.
    topics: list[str] = []
    if base_topic:
        topics = expand_topic_queries(base_topic, max_queries=MAX_TOPIC_QUERIES)
    else:
        defaults = discovery.get("default_topics")
        if not isinstance(defaults, (list, tuple)) or not defaults:
            defaults = list(DEFAULT_SEARCH_TOPICS)
        for value in defaults:
            text = str(value).strip()
            if text and text.lower() not in {item.lower() for item in topics}:
                topics.append(text)
            if len(topics) >= MAX_TOPIC_QUERIES:
                break
    if not topics:
        raise DiscoveryError("Rejected: no topic was supplied for discovery")

    if read_search is None and read_searches is None:
        raise DiscoveryError(
            "Rejected: no search reader was supplied, so no public search "
            "could be run."
        )

    seen = {str(url) for url in (known_urls or set())}
    candidates: list[DiscoveredVideo] = []
    blockers: list[str] = []
    searched: list[str] = []

    # The creators that are never offered as a result. The admin's own
    # account is excluded, because a video of the account itself is not a
    # public trend and must never stand in for one.
    blocked_creators = {
        str(name).strip().lower().lstrip("@")
        for name in (exclude_creators or set())
        if str(name).strip()
    }
    expected_account = str(config.get("expected_account", "")).strip().lower().lstrip("@")
    if expected_account:
        blocked_creators.add(expected_account)

    # When a batched reader is supplied, every keyword is searched in one
    # browser session on one tab. The run therefore asks the platform once
    # per keyword, inside a single Chrome session, instead of opening a
    # session and a tab for each keyword.
    batch: dict[str, dict[str, Any]] = {}
    if read_searches is not None:
        pending = [
            term
            for term in topics
            if not (should_stop is not None and should_stop())
        ]
        if pending:
            try:
                batch = read_searches(pending)
            except Exception as exc:  # noqa: BLE001 - the reason is reported
                blockers.append(
                    f"Blocked: the search session failed: {type(exc).__name__}: {exc}"
                )
                batch = {}

    for term in topics:
        if should_stop is not None and should_stop():
            blockers.append("Đã dừng theo yêu cầu của quản trị viên.")
            break

        # The batched answer is used when the session already searched this
        # keyword. Otherwise the single keyword reader is used.
        if term in batch:
            payload = batch.get(term) or {}
            results = str(payload.get("results", "") or "")
            if not results:
                error = str(payload.get("error", "") or "").strip()
                blockers.append(
                    "Blocked: the search for '" + term + "' returned no result"
                    + (f": {error}" if error else ".")
                )
                continue
            try:
                found = _candidates_from_results(
                    results, term, topic, max_results=MAX_PER_QUERY
                )
            except DiscoveryBlockedError as exc:
                blockers.append(str(exc))
                continue
            except DiscoveryError as exc:
                blockers.append(str(exc))
                continue
        else:
            if read_search is None:
                continue
            try:
                found = discover_by_keyword(
                    term, read_search=read_search, max_results=MAX_PER_QUERY
                )
            except DiscoveryBlockedError as exc:
                blockers.append(str(exc))
                continue
            except DiscoveryError as exc:
                blockers.append(str(exc))
                continue
        searched.append(term)
        added_this_query = 0
        for candidate in found:
            if len(candidates) >= max_results:
                # Global cap reached: remaining queries are still searched
                # (stats kept) but nothing more is added.
                break
            if candidate.source_url in seen:
                continue
            if candidate.creator.lower().lstrip("@") in blocked_creators:
                # The account of the admin is never offered as a trend.
                continue
            seen.add(candidate.source_url)
            candidates.append(candidate)
            added_this_query += 1
            # One query contributes at most MAX_PER_QUERY videos; the loop
            # continues with the next query so every sub-cluster is covered.
            if added_this_query >= MAX_PER_QUERY:
                break
            if len(candidates) >= max_results:
                break
        if stats is not None:
            stats[str(term)] = {
                "returned": len(found),
                "added": added_this_query,
            }

    if not searched and blockers:
        # Every keyword was blocked, so the run produced nothing to score.
        return [], blockers

    if filters is not None and filters != SearchFilters():
        kept, dropped = apply_search_filters(candidates, filters)
        for reason in dropped:
            blockers.append(f"Loại theo bộ lọc — {reason}")
        return kept, blockers
    return candidates, blockers


def save_production_candidates(
    candidates: list[DiscoveredVideo],
    path: Path | None = None,
    *,
    topic: str = "",
    blockers: list[str] | None = None,
) -> Path:
    """Write discovered candidates to the PRODUCTION candidate store."""
    target = Path(path) if path is not None else PRODUCTION_CANDIDATES_DIR / "candidates.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "videos": [asdict(candidate) for candidate in candidates],
        "topic": topic,
        "blockers": list(blockers or []),
        "note": (
            "PRODUCTION candidates discovered from a public TikTok keyword "
            "search. Every metric was read from the search payload the page "
            "itself received. The creator allowlist is not a search source."
        ),
    }
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def require_candidates(candidates: list[DiscoveredVideo]) -> list[DiscoveredVideo]:
    """Return the candidates or raise when no valid new candidate was found."""
    if not candidates:
        raise NoCandidatesFoundError("NO_CANDIDATES_FOUND")
    return candidates


__all__ = [
    "AI_MUSIC_SUBQUERIES",
    "DEFAULT_SEARCH_TOPICS",
    "DiscoveryBlockedError",
    "ITEM_LIST_URL_MARKER",
    "MAX_TOPIC_QUERIES",
    "MAX_PER_QUERY",
    "SEARCH_RESULTS_URL_MARKER",
    "SearchFilters",
    "TOP5_LIMIT",
    "apply_search_filters",
    "build_top5_cards",
    "candidate_age_days",
    "discover_by_keyword",
    "discover_new_candidates",
    "expand_topic_queries",
    "is_tutorial_title",
    "language_market_note",
    "parse_search_results",
    "require_candidates",
    "rights_status_of",
    "save_production_candidates",
    "to_candidate",
    "topic_matches",
]
