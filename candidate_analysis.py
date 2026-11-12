"""D1.3 AI analysis of the discovered candidates.

Every candidate of a discovery run is analysed on its own, with the same
seven dimensions, and every dimension keeps the reason it gave its points.
The candidates are then ranked, so the run can show the score of all of
them and name the one that is best.

The analysis is made from the real content of the video, not from its
caption. The real frames are read through the authorised session and the
AI provider judges them. The picture decides the visual quality, whether
the video is AI-made, the pull of the first three seconds, and the match
between the sound and the picture. The published metrics only add the
auxiliary signals, and they never stand in for the content itself.

The analysis never invents a fact. A dimension the content does not allow
to decide is marked as not enough data and keeps no points, and such a
candidate is not ranked. The result of the content analysis is cached by
the identity of the video, so the same video is never sent to the AI
twice.

Nothing here downloads a video into the library, publishes anything, or
decides on rights.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

from discover import DiscoveredVideo

# The seven dimensions the candidates are judged on, with the points each
# one can contribute. The weights add up to 100, as the product requires.
DIMENSION_AI_FIT = "ai_music_fit"
DIMENSION_MUSIC = "music_quality"
DIMENSION_VISUAL = "visual_quality"
DIMENSION_HOOK = "hook_retention"
DIMENSION_VIRAL = "engagement_virality"
DIMENSION_CREATIVITY = "creativity"
DIMENSION_CHANNEL = "channel_fit"

DIMENSION_POINTS = {
    DIMENSION_AI_FIT: 20,
    DIMENSION_MUSIC: 20,
    DIMENSION_VISUAL: 15,
    DIMENSION_HOOK: 15,
    DIMENSION_VIRAL: 15,
    DIMENSION_CREATIVITY: 10,
    DIMENSION_CHANNEL: 5,
}

# The label the dashboard shows when the content could not be read. It is
# shown to the admin instead of a guessed score.
INSUFFICIENT_DATA = "CHƯA ĐỦ DỮ LIỆU"

# The cache of the content analysis. The key is the identity of the video,
# so a video is sent to the AI only once.
CACHE_PATH = Path("data") / "state" / "ai_analysis_cache.json"

# The words that show a video is about the AI music market in a strong way.
# They are read from the caption of the candidate, which the platform
# published, so they are real facts and not an assumption.
_STRONG_TOPIC_WORDS = (
    "ai music", "aimusic", "ai song", "aisong", "ai cover", "aicover",
    "ai remix", "airemix", "suno", "udio", "booga", "ai generated music",
    "ai tạo nhạc", "nhạc ai", "bài hát ai", "ai melody", "aimelody",
    "voice clone", "ai beat", "aibeat", "ai instrumental",
)

# The words that show a video suits a channel that republishes music.
_TARGET_CHANNEL_WORDS = (
    "music", "song", "nhạc", "bài hát", "cover", "remix", "beat", "sound",
    "audio", "instrumental", "mashup", "lofi", "edm", "cinematic",
)

# The prompt that asks the provider to judge the real content. The provider
# is told to answer only from the frames it is given and to leave a
# dimension empty when the frames do not allow it to decide.
_CONTENT_PROMPT = (
    "You are judging a short video for an AI music channel. The frames below "
    "are real still frames taken from the video at different moments. "
    "Judge ONLY from what the frames show and what the metadata states. "
    "Never guess from the caption alone and never invent a fact.\n"
    "The caption is NOT evidence. A video whose caption merely contains the "
    "word AI is not an AI music video. You must see the evidence in the "
    "frames: an AI music tool on screen (Suno, Udio, Booga), an AI music "
    "label or watermark, an AI-generated music visual, an AI animation or "
    "cinematic, or the frames clearly showing a music performance or music "
    "production.\n"
    "A video that shows cars, a meme, a face filter, a recipe, a workout, "
    "a product, a real person talking with no music content, or a "
    "conversation is NOT an AI music video. Give ai_music_fit 0 and set "
    "ai_music_fit_known to true for such a video, so it is rejected.\n"
    "For every dimension below return a score from 0 to the given maximum, a "
    "short reason written in Vietnamese, and set 'known' to false when the "
    "frames are not enough to decide that dimension.\n"
    "1. ai_music_fit (max 20): is the music presented as AI-made, or does the "
    "video visibly show an AI music workflow? A caption keyword alone is not "
    "enough. If the frames show nothing about how the music was made and the "
    "frames are not enough to rule it out, set known to false. If the frames "
    "clearly show the video is not AI music content, give 0 and set known to "
    "true.\n"
    "2. music_quality (max 20): the melody, the sound fidelity and the "
    "addiction potential that the frames and the metadata support. The frames "
    "cannot carry the sound itself, so judge only what is really observable "
    "and set known to false when nothing about the sound can be seen.\n"
    "3. visual_quality (max 15): the production quality of the picture, and "
    "whether it looks AI-generated or AI-assisted, with the confidence you "
    "have.\n"
    "4. hook_retention (max 15): the pull of the first three seconds, and the "
    "reason a viewer would stay. Judge from the first frame.\n"
    "5. engagement_virality (max 15): the shareability and the creativity "
    "the content shows. The published metrics are auxiliary only; a high "
    "view count alone does not mean a high potential.\n"
    "6. creativity (max 10): how original the concept and the visual "
    "treatment are.\n"
    "7. channel_fit (max 5): the fit with an AI music channel.\n"
    "Also return 'content_summary': one sentence in Vietnamese that says what "
    "the video really shows, 'content_ai_visual': true, false, or null when it "
    "cannot be decided, and 'content_is_ai_music': true when the frames show "
    "this really is AI music content, false when the frames show it is not "
    "(a car, a meme, a face filter, a recipe, an ordinary talking video, an "
    "advertisement, or any other content that is not AI music). Set "
    "'content_is_ai_music' to false only when you are sure from the frames; "
    "when the frames do not settle it, leave 'ai_music_fit_known' false "
    "instead. Return JSON only."
)

# The structured output the provider is asked for.
_CONTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "ai_music_fit": {"type": "integer"},
        "ai_music_fit_reason": {"type": "string"},
        "ai_music_fit_known": {"type": "boolean"},
        "music_quality": {"type": "integer"},
        "music_quality_reason": {"type": "string"},
        "music_quality_known": {"type": "boolean"},
        "visual_quality": {"type": "integer"},
        "visual_quality_reason": {"type": "string"},
        "visual_quality_known": {"type": "boolean"},
        "hook_retention": {"type": "integer"},
        "hook_retention_reason": {"type": "string"},
        "hook_retention_known": {"type": "boolean"},
        "engagement_virality": {"type": "integer"},
        "engagement_virality_reason": {"type": "string"},
        "engagement_virality_known": {"type": "boolean"},
        "creativity": {"type": "integer"},
        "creativity_reason": {"type": "string"},
        "creativity_known": {"type": "boolean"},
        "channel_fit": {"type": "integer"},
        "channel_fit_reason": {"type": "string"},
        "channel_fit_known": {"type": "boolean"},
        "content_summary": {"type": "string"},
        "content_ai_visual": {"type": "boolean"},
        "content_is_ai_music": {"type": "boolean"},
    },
    "required": ["content_summary"],
}


@dataclass
class Dimension:
    """One judged dimension of one candidate."""

    name: str
    label: str
    points: int = 0
    max_points: int = 0
    detail: str = ""
    known: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CandidateAnalysis:
    """The analysis of one candidate, with its total score and reasons."""

    source_url: str
    creator: str
    title: str
    score: int = 0
    rank: int = 0
    dimensions: list[Dimension] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    summary: str = ""
    provider: str = ""
    model: str = ""
    # True when the content was really read and judged.
    content_analyzed: bool = False
    # The number of real frames the content analysis was made from.
    frame_count: int = 0
    # The real metrics the analysis was made from.
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    duration_seconds: float = 0.0
    posted_at: str = ""
    engagement_rate: float = 0.0
    ai_generated_label: bool | None = None
    # True when the candidate was left out of the ranking because the
    # content did not give enough data to judge it.
    ranked: bool = True
    insufficient_reason: str = ""
    # The content-based verdict on whether the video really is AI Music
    # content. The caption never sets this; only the judged frames do.
    content_relevant: bool | None = None
    content_relevance_reason: str = ""
    # What the local vision analyzer really saw in the frames, and what it
    # measured. The two are kept apart inside it.
    local_vision: dict[str, Any] = field(default_factory=dict)
    # What the machine is missing to measure the sound, when it is.
    local_audio_dependency_missing: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["dimensions"] = [item.to_dict() for item in self.dimensions]
        return payload


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


def _text(video: DiscoveredVideo) -> str:
    """Return the searchable text of a candidate."""
    return f"{video.title} {video.topic} {video.source_name}".lower()


def engagement_rate(video: DiscoveredVideo) -> float:
    """Return the real engagement rate of the video.

    The rate is the total engagement over the views. A video with no
    published views has no rate, and the rate is reported as zero rather
    than as a made-up number.
    """
    views = int(video.views or 0)
    if views <= 0:
        return 0.0
    total = int(video.likes or 0) + int(video.comments or 0) + int(video.shares or 0)
    return total / views


def _auxiliary_signal(video: DiscoveredVideo) -> str:
    """Return the auxiliary signal the published metrics give.

    The signal is a fact of the platform. It never decides a dimension on
    its own, and it is never presented as the quality of the content.
    """
    views = int(video.views or 0)
    if not video.metrics_known or views <= 0:
        return "không có số liệu tương tác đã công bố"
    rate = engagement_rate(video)
    posted = _posted_date(video.posted_at)
    age = (date.today() - posted).days if posted else None
    parts = [f"{views:,} lượt xem", f"tương tác {rate:.1%}"]
    if age is not None:
        parts.append(f"đăng {age} ngày trước")
    return ", ".join(parts) + " — tín hiệu bổ trợ, không phải chất lượng nội dung"


# ---------------------------------------------------------------------------
# The cache of the content analysis
# ---------------------------------------------------------------------------

def _video_id_from_url(source_url: str) -> str:
    """Return the platform's own id of a video, taken from its address.

    The id in the address never changes, while the caption, the creator
    name and the media address can. The id is therefore the one identity
    that lets a later run find the frames it already read.
    """
    text = str(source_url or "").strip()
    if not text:
        return ""
    match = re.search(r"/video/(\d+)", text)
    if match:
        return match.group(1)
    match = re.search(r"[?&]v=(\d+)", text)
    if match:
        return match.group(1)
    return ""


def _cache_key(video: DiscoveredVideo) -> str:
    """Return the stable identity of a video for the cache.

    The key is the platform's own video id, which never changes. The
    caption and the creator name of a video can change between two runs,
    so they are not part of the key. A key that included them would miss
    the cache and make every run download the same media again.
    """
    video_id = str(getattr(video, "video_id", "") or "").strip()
    if not video_id:
        video_id = _video_id_from_url(video.source_url)
    if video_id:
        return video_id
    raw = str(video.source_url or "").strip().lower()
    if raw:
        return hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()[:32]
    fallback = f"{video.source_url}|{video.title}|{video.creator}".lower()
    return hashlib.sha256(fallback.encode("utf-8", "replace")).hexdigest()[:32]


def load_cache(path: Path = CACHE_PATH) -> dict[str, Any]:
    """Load the cache of the content analysis."""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def save_cache(cache: dict[str, Any], path: Path = CACHE_PATH) -> None:
    """Write the cache of the content analysis."""
    target = Path(path)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(cache, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    except OSError:
        # A cache that cannot be written only costs another AI call later.
        pass


# ---------------------------------------------------------------------------
# The content analysis
# ---------------------------------------------------------------------------

def _frames_digest(frames: list[bytes]) -> str:
    """Return a digest of the frames, used to keep the cache honest."""
    digest = hashlib.sha256()
    for frame in frames:
        digest.update(len(frame).to_bytes(4, "big"))
        digest.update(frame)
    return digest.hexdigest()[:24]


def _encode_frames(frames: list[bytes]) -> list[str]:
    """Encode the frames so they can be written in the cache file.

    The cache is a text file, so the frames are stored as base64. The
    frames are the evidence of the analysis, and keeping them lets the
    dashboard show what the AI judged.
    """
    encoded: list[str] = []
    for frame in frames:
        try:
            encoded.append(base64.b64encode(frame).decode("ascii"))
        except (ValueError, TypeError):
            continue
    return encoded


def _decode_frames(items: list[Any]) -> list[bytes]:
    """Read the frames back from the cache file."""
    frames: list[bytes] = []
    for item in items:
        if isinstance(item, bytes):
            frames.append(item)
            continue
        if not isinstance(item, str) or not item:
            continue
        try:
            frames.append(base64.b64decode(item))
        except (ValueError, TypeError):
            continue
    return frames


def request_local_analysis(
    frames: list[bytes],
    metadata: dict[str, Any],
    *,
    model: str = "",
    media_path: str = "",
) -> dict[str, Any]:
    """Judge the real frames of a video on this machine.

    The judgement is made by the local analyzer. No paid API is called and
    no AI token is spent. The result carries the same shape the rest of
    the pipeline already understands, so the scoring, the ranking and the
    dashboard need no rewrite.

    The analyzer states how sure it is about every dimension. A dimension
    it could not decide is marked as not known and keeps no points, so a
    missing measurement never becomes a guessed score.
    """
    from local_analyzer import analyze_locally

    result = analyze_locally(frames, metadata, media_path=media_path)
    return local_result_to_payload(result)


def local_result_to_payload(result: Any) -> dict[str, Any]:
    """Turn a local analysis into the payload the pipeline understands.

    The payload uses the names the existing dimension mapping already
    knows, so the same code reads a local result and a provider result.
    """
    from local_analyzer import EVIDENCE, POSSIBILITY, score_local

    total, strengths, weaknesses = score_local(result)
    payload: dict[str, Any] = {
        "content_summary": result.summary,
        "content_is_ai_music": result.content_is_ai_music,
        "content_ai_visual": result.content_ai_visual,
        "local_analyzer_version": result.analyzer_version,
        "local_total": total,
        "local_strengths": strengths,
        "local_weaknesses": weaknesses,
        "local_tools": dict(result.tools),
        "local_audio_dependency_missing": result.audio_dependency_missing,
        # What the local vision analyzer really saw, kept apart from the
        # measurements of the pixels.
        "local_vision": result.vision.to_dict() if result.vision else {},
    }

    # The local findings are mapped onto the seven dimensions the product
    # asks for. The two that the local analyzer does not measure are the
    # ones that need a sound and a creative judgement the machine cannot
    # make, so they are marked as not known.
    from local_analyzer import FINDING_LABELS, _FINDING_MAX

    for finding_key, finding in result.findings.items():
        maximum = _FINDING_MAX.get(finding_key, 0)
        certainty = finding.certainty
        known = certainty in (EVIDENCE, POSSIBILITY)
        points = int(round(finding.points))
        payload[finding_key] = points
        payload[f"{finding_key}_reason"] = finding.reason
        payload[f"{finding_key}_known"] = known
        payload[f"{finding_key}_max"] = int(maximum)

    # The seven dimensions the dashboard shows. The weights are the ones
    # the product asks for, so they add up to 100:
    # topic 25, picture 15, sound 15, hook 15, engagement 20, channel 10.
    # Creativity has no points, because the machine has no model that can
    # measure it, and an empty dimension keeps no points.
    payload["ai_music_fit"] = payload.get("topic_fit", 0)
    payload["ai_music_fit_reason"] = payload.get("topic_fit_reason", "")
    payload["ai_music_fit_known"] = payload.get("topic_fit_known", False)
    payload["ai_music_fit_max"] = 25

    payload["music_quality"] = payload.get("music_quality", 0)
    payload["music_quality_reason"] = payload.get("music_quality_reason", "")
    payload["music_quality_known"] = payload.get("music_quality_known", False)
    payload["music_quality_max"] = 15

    payload["visual_quality"] = payload.get("visual_quality", 0)
    payload["visual_quality_reason"] = payload.get("visual_quality_reason", "")
    payload["visual_quality_known"] = payload.get("visual_quality_known", False)
    payload["visual_quality_max"] = 15

    payload["hook_retention"] = payload.get("hook_retention", 0)
    payload["hook_retention_reason"] = payload.get("hook_retention_reason", "")
    payload["hook_retention_known"] = payload.get("hook_retention_known", False)
    payload["hook_retention_max"] = 15

    payload["engagement_virality"] = payload.get("engagement_virality", 0)
    payload["engagement_virality_reason"] = payload.get(
        "engagement_virality_reason", ""
    )
    payload["engagement_virality_known"] = payload.get(
        "engagement_virality_known", False
    )
    payload["engagement_virality_max"] = 20

    # Creativity cannot be measured from the pixels without a model, so it
    # stays empty rather than being guessed.
    payload["creativity"] = 0
    payload["creativity_reason"] = (
        "máy chưa có mô hình đo tính sáng tạo; cần bổ sung model ảnh qua adapter"
    )
    payload["creativity_known"] = False
    payload["creativity_max"] = 0

    payload["channel_fit"] = payload.get("channel_fit", 0)
    payload["channel_fit_reason"] = payload.get("channel_fit_reason", "")
    payload["channel_fit_known"] = payload.get("channel_fit_known", False)
    payload["channel_fit_max"] = 10

    return payload


# The provider the content analysis uses. The local analyzer is the
# default, because it runs on this machine, costs nothing and sends
# nothing off it. The name can be set to "gemini" to use the paid
# provider instead, which is the only way the paid provider is reached.
ANALYZER_PROVIDER = os.getenv("TOOLTDH_ANALYZER", "local").strip().lower() or "local"


def request_content_analysis(
    frames: list[bytes],
    metadata: dict[str, Any],
    *,
    model: str = "",
    provider: str = "",
    media_path: str = "",
) -> dict[str, Any]:
    """Judge the real frames of a video with the configured provider.

    The local analyzer is the default. It runs on this machine and spends
    no AI token. The paid provider is used only when it is asked for by
    name, and it then needs its own key.

    The media path is only used by the local analyzer, and only when the
    file is really on the machine. It lets the sound be measured instead
    of being left unknown.
    """
    chosen = str(provider or ANALYZER_PROVIDER).strip().lower()
    if chosen in ("local", "local-analyzer", "local_analyzer"):
        return request_local_analysis(
            frames, metadata, model=model, media_path=media_path
        )
    if chosen == "gemini":
        return request_gemini_analysis(frames, metadata, model=model)
    raise RuntimeError(
        f"không có bộ phân tích nào mang tên '{chosen}'; dùng 'local' hoặc 'gemini'"
    )


def request_gemini_analysis(
    frames: list[bytes],
    metadata: dict[str, Any],
    *,
    model: str = "",
) -> dict[str, Any]:
    """Ask the Gemini provider to judge the real frames of a video.

    The provider that answers is the one the project already uses. The
    request carries the real frames, so the judgement is made from the
    content. The call is not repeated for the same video because the
    caller checks the cache first.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:  # pragma: no cover - depends on the host
        raise RuntimeError("google-genai is required for the content analysis") from exc

    from brain import DEFAULT_MODEL

    client = genai.Client(api_key=api_key)
    parts: list[Any] = [types.Part.from_text(text=_CONTENT_PROMPT)]
    for frame in frames:
        parts.append(types.Part.from_bytes(data=frame, mime_type="image/jpeg"))
    parts.append(
        types.Part.from_text(
            text="Metadata: " + json.dumps(metadata, ensure_ascii=False, default=str)
        )
    )
    response = client.models.generate_content(
        model=model or DEFAULT_MODEL,
        contents=[types.Content(role="user", parts=parts)],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=_CONTENT_SCHEMA,
        ),
    )
    text = getattr(response, "text", None)
    if not text:
        raise RuntimeError("the AI provider returned no analysis text")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("the AI provider returned malformed JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("the AI provider returned an invalid analysis object")
    return payload


def _media_path_for(
    video: DiscoveredVideo,
    resolver: Callable[[DiscoveredVideo], str] | None,
) -> str:
    """Return the path of the media file of a candidate, if it is there.

    The file is only used when it really exists on the machine. Nothing
    is downloaded here, so the sound is measured only for a video the
    admin already approved and that is already on the disk.
    """
    if resolver is None:
        return ""
    try:
        path = str(resolver(video) or "").strip()
    except Exception:
        return ""
    if not path:
        return ""
    try:
        if Path(path).is_file():
            return path
    except OSError:
        return ""
    return ""


def _analyzer_version(provider: str) -> str:
    """Return the version of the analyzer that runs under a provider name.

    The local analyzer has a version of its own. The paid provider has
    none here, because its version is in the model name it was given.
    """
    name = str(provider or "").strip().lower()
    if name in ("local", "local-analyzer", "local_analyzer"):
        try:
            from local_analyzer import ANALYZER_VERSION

            return ANALYZER_VERSION
        except Exception:
            return "local-v1"
    return ""


def _cache_key_prefix(provider: str) -> str:
    """Return the prefix of the cache key of a provider.

    The prefix carries the provider and the version of its analyzer, so a
    result made by one analyzer is never reused by another one, and the
    frames that were read are still found under the plain key.
    """
    name = str(provider or "").strip().lower()
    if name in ("local", "local-analyzer", "local_analyzer"):
        return f"local:{_analyzer_version(name)}"
    return name


def _clamp_points(value: Any, maximum: int) -> int:
    """Return a score of the provider inside the allowed range."""
    try:
        points = int(round(float(value)))
    except (TypeError, ValueError):
        return 0
    return max(0, min(maximum, points))


def _dimension_from_content(
    name: str,
    label: str,
    payload: dict[str, Any],
) -> Dimension:
    """Build one dimension from the answer of the provider."""
    # The provider may carry its own weight for a dimension. The local
    # analyzer uses the weights the product asks for, and they are not the
    # same as the ones of the paid provider. A weight of zero is a real
    # weight, so it is read as it is and never replaced by the default.
    if f"{name}_max" in payload:
        maximum = int(payload.get(f"{name}_max") or 0)
    else:
        maximum = DIMENSION_POINTS[name]
    known = bool(payload.get(f"{name}_known", True))
    reason = str(payload.get(f"{name}_reason", "") or "").strip()
    if not known:
        return Dimension(
            name=name,
            label=label,
            points=0,
            max_points=maximum,
            detail=reason or INSUFFICIENT_DATA,
            known=False,
        )
    points = _clamp_points(payload.get(name), maximum)
    detail = reason or "không có lý do do nhà cung cấp AI"
    return Dimension(
        name=name,
        label=label,
        points=points,
        max_points=maximum,
        detail=detail,
        known=True,
    )


# The dimensions the provider judges, with the label the dashboard shows.
_CONTENT_DIMENSIONS = (
    (DIMENSION_AI_FIT, "Mức độ phù hợp AI Music"),
    (DIMENSION_MUSIC, "Chất lượng nhạc"),
    (DIMENSION_VISUAL, "Chất lượng hình ảnh"),
    (DIMENSION_HOOK, "Sức hút 3 giây & giữ chân"),
    (DIMENSION_VIRAL, "Tiềm năng tương tác & lan truyền"),
    (DIMENSION_CREATIVITY, "Tính sáng tạo"),
    (DIMENSION_CHANNEL, "Phù hợp kênh đích"),
)


# The marker that says the provider did not state a verdict at all. It is
# different from ``None``, which means the provider stated that it could
# not settle the question.
_NOT_STATED = object()


def _content_relevance(payload: dict[str, Any]) -> tuple[bool | None, str]:
    """Return the content-based verdict on whether the video is AI Music.

    The verdict comes from the answer the provider gave about the real
    frames. The caption, the hashtags and the view count are not part of
    it, so a car video or a meme that only says "AI" in its caption does
    not pass.

    ``None`` is returned when the frames do not allow the question to be
    decided. Such a video is not rejected and not accepted; it is reported
    as not enough data.
    """
    if not payload:
        return None, INSUFFICIENT_DATA

    ai_visual = payload.get("content_ai_visual")
    ai_fit_known = bool(payload.get("ai_music_fit_known", False))
    ai_fit = _clamp_points(payload.get("ai_music_fit"), DIMENSION_POINTS[DIMENSION_AI_FIT])
    reason = str(payload.get("ai_music_fit_reason", "") or "").strip()
    summary = str(payload.get("content_summary", "") or "").strip()

    # The provider can state the verdict directly. When it does, that verdict
    # is used, because it is the answer to exactly this question.
    verdict = payload.get("content_is_ai_music", _NOT_STATED)
    if verdict is not _NOT_STATED:
        if isinstance(verdict, bool):
            detail = reason or (
                "nội dung thật cho thấy đây là AI Music"
                if verdict
                else "nội dung thật cho thấy đây không phải AI Music"
            )
            if summary:
                detail = f"{detail}. Nội dung: {summary}"
            return verdict, detail
        # The provider stated that it could not settle the question. The
        # video is not judged on the strength of its caption; it is
        # reported as not enough data.
        return None, reason or INSUFFICIENT_DATA

    if not ai_fit_known:
        # The provider could not decide from the frames whether the music is
        # AI-made. The video is not judged; it is reported as not enough
        # data, and it is never accepted on the strength of its caption.
        return None, reason or INSUFFICIENT_DATA

    # The video passes when the provider found the AI signal in the content
    # itself. The threshold is on the AI Music dimension, because that is
    # the dimension that answers this exact question.
    if ai_fit >= 8:
        detail = reason or "nội dung cho thấy dấu hiệu nhạc AI"
        if summary:
            detail = f"{detail}. Nội dung: {summary}"
        return True, detail

    detail = reason or "nội dung không cho thấy dấu hiệu nhạc AI"
    if summary:
        detail = f"{detail}. Nội dung: {summary}"
    return False, detail


def _strengths_weaknesses(dimensions: list[Dimension]) -> tuple[list[str], list[str]]:
    """Return the strengths and the weaknesses of a candidate.

    A dimension that reached at least 80 percent of its points is a
    strength, and one that stayed under half is a weakness. A dimension
    whose fact was unknown is neither, because a missing fact is not a
    weakness of the video.
    """
    strengths: list[str] = []
    weaknesses: list[str] = []
    for dimension in dimensions:
        if not dimension.known:
            continue
        ratio = dimension.points / dimension.max_points if dimension.max_points else 0.0
        if ratio >= 0.8:
            strengths.append(f"{dimension.label}: {dimension.detail}")
        elif ratio < 0.5:
            weaknesses.append(f"{dimension.label}: {dimension.detail}")
    return strengths, weaknesses


def _metadata_for(video: DiscoveredVideo) -> dict[str, Any]:
    """Return the real facts about a candidate that the AI may use."""
    return {
        "title": video.title,
        "creator": video.creator,
        "duration_seconds": float(video.duration_seconds or 0.0),
        "views": int(video.views or 0),
        "likes": int(video.likes or 0),
        "comments": int(video.comments or 0),
        "shares": int(video.shares or 0),
        "posted_at": str(video.posted_at or ""),
        "platform_ai_label": (
            video.is_ai_generated if video.ai_label_known else None
        ),
    }


def analyze_candidate(
    video: DiscoveredVideo,
    topic: str,
    *,
    frames: list[bytes] | None = None,
    content_payload: dict[str, Any] | None = None,
    content_error: str = "",
    provider: str = "",
    model: str = "",
) -> CandidateAnalysis:
    """Analyse one candidate on all seven dimensions.

    The dimensions come from the real content when the content was read.
    When it was not, the candidate carries the not enough data mark and
    keeps no points, so it is never ranked on a guessed score.
    """
    frames = list(frames or [])
    payload = dict(content_payload or {})

    if content_payload is not None and frames:
        dimensions = [
            _dimension_from_content(name, label, payload)
            for name, label in _CONTENT_DIMENSIONS
        ]
        content_analyzed = True
        frame_count = len(frames)
        summary = str(payload.get("content_summary", "") or "").strip()
        insufficient_reason = ""
        # The relevance of the video is decided by the content itself. The
        # caption is not part of this decision.
        content_relevant, content_relevance_reason = _content_relevance(payload)
    else:
        # The content could not be read. The dimensions stay empty and the
        # candidate is marked as not enough data.
        dimensions = [
            Dimension(
                name=name,
                label=label,
                points=0,
                max_points=DIMENSION_POINTS[name],
                detail=INSUFFICIENT_DATA,
                known=False,
            )
            for name, label in _CONTENT_DIMENSIONS
        ]
        content_analyzed = False
        # The frames were read even though the provider could not answer.
        # The count is kept, because it shows that the content of the
        # video really was looked at, and only the verdict is missing.
        frame_count = len(frames)
        summary = ""
        insufficient_reason = content_error or INSUFFICIENT_DATA
        content_relevant = None
        content_relevance_reason = insufficient_reason

    total = sum(dimension.points for dimension in dimensions)
    strengths, weaknesses = _strengths_weaknesses(dimensions)

    if content_relevant is False:
        # The content was judged and it is not AI Music. The video keeps no
        # points, so it can never be confused with a ranked candidate.
        total = 0
        strengths = []
        weaknesses = []
        summary = (
            "Nội dung thật không phải AI Music — " + content_relevance_reason
        )
    elif content_relevant is None:
        # The content was not settled, so there is no verdict to score.
        # The video keeps no points either, because a score without a
        # verdict would be a number the machine cannot stand behind.
        total = 0
        strengths = []
        weaknesses = [
            f"{dim.label}: {dim.detail or INSUFFICIENT_DATA}"
            for dim in dimensions
            if not dim.known
        ]
        summary = (
            f"{INSUFFICIENT_DATA}: {content_relevance_reason or insufficient_reason}. "
            f"Tín hiệu bổ trợ: {_auxiliary_signal(video)}."
        )
    elif content_analyzed:
        if strengths:
            summary = summary or ("Điểm mạnh: " + "; ".join(strengths[:2]))
        elif weaknesses:
            summary = summary or ("Điểm yếu: " + "; ".join(weaknesses[:2]))
        else:
            summary = summary or "Các tiêu chí ở mức trung bình, không có điểm nổi bật."
        summary = f"{summary} ({_auxiliary_signal(video)})"
    else:
        summary = (
            f"{INSUFFICIENT_DATA}: {insufficient_reason}. "
            f"Tín hiệu bổ trợ: {_auxiliary_signal(video)}."
        )

    return CandidateAnalysis(
        source_url=video.source_url,
        creator=video.creator,
        title=video.title,
        score=max(0, min(100, total)),
        dimensions=dimensions,
        strengths=strengths,
        weaknesses=weaknesses,
        summary=summary,
        provider=provider,
        model=model,
        content_analyzed=content_analyzed,
        frame_count=frame_count,
        views=int(video.views or 0),
        likes=int(video.likes or 0),
        comments=int(video.comments or 0),
        shares=int(video.shares or 0),
        duration_seconds=float(video.duration_seconds or 0.0),
        posted_at=str(video.posted_at or ""),
        engagement_rate=round(engagement_rate(video), 6),
        ai_generated_label=video.is_ai_generated if video.ai_label_known else None,
        ranked=content_analyzed,
        insufficient_reason=insufficient_reason,
        content_relevant=content_relevant,
        content_relevance_reason=content_relevance_reason,
        # What the local analyzer saw and measured. It travels with the
        # candidate, so the dashboard can show it without asking again.
        local_vision=dict(payload.get("local_vision") or {}),
        local_audio_dependency_missing=str(
            payload.get("local_audio_dependency_missing") or ""
        ),
    )


def analyze_candidates(
    videos: list[DiscoveredVideo],
    topic: str,
    *,
    frame_reader: Callable[[DiscoveredVideo], list[bytes]] | None = None,
    cache: dict[str, Any] | None = None,
    cache_path: Path = CACHE_PATH,
    model: str = "",
    provider_name: str = "",
    media_resolver: Callable[[DiscoveredVideo], str] | None = None,
) -> list[CandidateAnalysis]:
    """Analyse every candidate and rank them from the best score down.

    The frames of a candidate are read through the authorised session, or
    taken from the cache when the same video was already analysed. The
    provider is called only for a video that is not in the cache, so the
    same video is never sent to the AI twice.

    ``media_resolver`` gives the path of the media file of a candidate,
    when that file is already on the machine. The sound is only measured
    from a file that is really there; nothing is downloaded for it.

    Only the candidates whose content was really judged take part in the
    ranking. A candidate without enough data is still returned, marked as
    such, so the admin can see it and know why it was left out.
    """
    own_cache = cache is None
    store = load_cache(cache_path) if own_cache else dict(cache or {})
    changed = False
    provider = str(provider_name or ANALYZER_PROVIDER).strip().lower() or "local"
    # The cache key carries the provider and the version of the analyzer,
    # so a result made by one analyzer is never reused by another one.
    key_prefix = _cache_key_prefix(provider)

    analyses: list[CandidateAnalysis] = []
    for video in videos:
        video_key = _cache_key(video)
        key = f"{key_prefix}:{video_key}"
        entry = store.get(key)
        payload: dict[str, Any] | None = None
        frames: list[bytes] = []
        error = ""

        if entry is None and key != video_key:
            # The frames are the same whoever judges them, so the frames
            # that were read before are found under the plain key, even
            # when no verdict was ever made for them.
            entry = store.get(video_key)

        if isinstance(entry, dict):
            cached_payload = entry.get("payload")
            cached_frames = entry.get("frames")
            cached_provider = str(entry.get("provider", "") or "")
            if isinstance(cached_frames, list) and cached_frames:
                cached_decoded = _decode_frames(cached_frames)
            else:
                cached_decoded = []
            # A cached verdict is only reused when it came from a real
            # provider that matches the one that is running now. A result
            # that was never judged by the AI is never shown as if it had
            # been, and a result of another analyzer is never mixed in.
            same_provider = cached_provider.lower() == provider
            if (
                isinstance(cached_payload, dict)
                and cached_decoded
                and cached_provider
                and same_provider
            ):
                payload = cached_payload
                frames = cached_decoded
            elif cached_decoded:
                # The frames were read before but the provider did not
                # answer. The frames are reused, so the media is not
                # downloaded a second time.
                frames = cached_decoded
                error = str(entry.get("error", "") or "") or (
                    "nhà cung cấp AI chưa trả lời cho video này"
                )

        if payload is None and frame_reader is not None:
            if not frames:
                frames = list(frame_reader(video) or [])
            if frames:
                # The frames are used, whether they were just read or taken
                # from the cache. The provider is asked again, because a
                # run that was blocked by the provider must be finished
                # when the provider works.
                try:
                    payload = request_content_analysis(
                        frames,
                        _metadata_for(video),
                        model=model,
                        provider=provider,
                        media_path=_media_path_for(video, media_resolver),
                    )
                    error = ""
                except Exception as exc:
                    error = f"{type(exc).__name__}: {exc}"
                    payload = None
            else:
                error = "không đọc được khung hình hợp lệ của video"

        if payload is not None:
            store[key] = {
                "payload": payload,
                "frames": _encode_frames(frames),
                "digest": _frames_digest(frames),
                "provider": provider,
                "model": model,
                "analyzer_version": _analyzer_version(provider),
                "saved_at": datetime.now().isoformat(timespec="seconds"),
            }
            # The frames are also kept under the plain key, so the next
            # analyzer finds them without reading the media again.
            if key != video_key:
                store[video_key] = {
                    "payload": None,
                    "frames": _encode_frames(frames),
                    "digest": _frames_digest(frames),
                    "provider": "",
                    "model": model,
                    "error": "",
                    "saved_at": datetime.now().isoformat(timespec="seconds"),
                }
            changed = True
        elif frames:
            # The frames were read but the provider could not answer. The
            # frames are kept, so a later run with a working provider does
            # not download the same media again. The reason is kept too, so
            # the dashboard can report why the video has no verdict.
            store[key] = {
                "payload": None,
                "frames": _encode_frames(frames),
                "digest": _frames_digest(frames),
                "provider": "",
                "model": model,
                "error": error,
                "saved_at": datetime.now().isoformat(timespec="seconds"),
            }
            changed = True

        analyses.append(
            analyze_candidate(
                video,
                topic,
                frames=frames,
                content_payload=payload,
                content_error=error,
                provider=provider if payload is not None else "",
                model=model,
            )
        )

    if changed:
        # The cache is written in both cases. When the caller supplied the
        # store, the frames and the verdicts are written back to it, so
        # the next run finds them.
        save_cache(store, cache_path)
        if not own_cache:
            try:
                cache.update(store)  # type: ignore[union-attr]
            except Exception:
                pass

    # Only the candidates whose real content shows AI Music take part in the
    # ranking. A video whose content was judged and does not show AI Music
    # is not ranked. A video whose content could not be judged either is
    # reported as not enough data and is not ranked either. Neither is ever
    # presented as a match.
    for analysis in analyses:
        if analysis.content_relevant is False:
            analysis.ranked = False
            analysis.rank = 0
            analysis.insufficient_reason = (
                "nội dung thật không cho thấy đây là AI Music: "
                + analysis.content_relevance_reason
            )
        elif analysis.content_relevant is None:
            # The frames were read, but they do not settle whether the video
            # is AI Music. The video is not accepted and not rejected; it is
            # reported as not enough data.
            analysis.ranked = False
            analysis.rank = 0
            analysis.insufficient_reason = (
                INSUFFICIENT_DATA + ": "
                + (analysis.content_relevance_reason or "nội dung không đủ để kết luận")
            )

    ranked = [item for item in analyses if item.ranked]
    ranked.sort(key=lambda item: item.score, reverse=True)
    for position, analysis in enumerate(ranked, start=1):
        analysis.rank = position
    # The candidates without enough data keep no rank. They are returned
    # after the ranked ones so the admin sees the best video first.
    unranked = [item for item in analyses if not item.ranked]
    return ranked + unranked


def best_analysis(analyses: list[CandidateAnalysis]) -> CandidateAnalysis | None:
    """Return the best analysed candidate, or None when there is none.

    Only a candidate whose content was really judged can be the best one.
    """
    for analysis in analyses:
        if analysis.ranked:
            return analysis
    return None


__all__ = [
    "CACHE_PATH",
    "CandidateAnalysis",
    "DIMENSION_AI_FIT",
    "DIMENSION_CHANNEL",
    "DIMENSION_CREATIVITY",
    "DIMENSION_HOOK",
    "DIMENSION_MUSIC",
    "DIMENSION_POINTS",
    "DIMENSION_VIRAL",
    "DIMENSION_VISUAL",
    "Dimension",
    "INSUFFICIENT_DATA",
    "analyze_candidate",
    "analyze_candidates",
    "best_analysis",
    "engagement_rate",
    "load_cache",
    "request_content_analysis",
    "save_cache",
]
