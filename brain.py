"""P3 AI analysis, scoring, captioning, and hashtag generation."""

from __future__ import annotations

import json
import os
import random
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

DEFAULT_MODEL = "gemini-2.5-flash"
MAX_CAPTION_LENGTH = 150
MAX_HASHTAGS = 10
MAX_REVISIONS = 5
DEFAULT_MAX_CALLS = 20
TEMPLATE_PROVIDER_NAME = "template"
DEFAULT_TOPIC = "general"
DEFAULT_HASHTAGS = ["fyp", "foryou", "viral", "trending", "reels", "tiktok", "shorts", "video", "content", "creator"]
DEFAULT_BANNED_WORDS = ["spam", "scam", "hate", "slur", "nsfw"]


class BrainError(RuntimeError):
    """Base error for P3 operations."""


class ProviderUnavailableError(BrainError):
    """Raised when the selected provider cannot be used."""


class QuotaExceededError(BrainError):
    """Raised when the task's configured AI call limit is reached."""


@dataclass
class AIUsage:
    """Usage tracking for one task."""

    calls: int = 0
    estimated_cost: float = 0.0
    limit: int = DEFAULT_MAX_CALLS

    def record(self, estimated_cost: float = 0.0) -> None:
        """Record one completed provider call."""
        if self.calls >= self.limit:
            raise QuotaExceededError(
                f"AI quota exceeded: {self.calls}/{self.limit} calls used for this task"
            )
        self.calls += 1
        self.estimated_cost += max(0.0, estimated_cost)


@dataclass
class AnalysisResult:
    """Structured content produced by an AI provider."""

    title: str
    caption: str
    hashtags: list[str]
    language: str
    score: int = 0
    score_reason: str = ""
    subtitle_draft: str | None = None
    status: str = "DRAFT"
    provider: str = ""
    model: str = ""
    usage: AIUsage = field(default_factory=AIUsage)
    error: str | None = None


class AIProvider(Protocol):
    """Minimal provider contract used by the brain."""

    name: str
    model: str

    def analyze(
        self,
        metadata: dict[str, Any],
        frames: list[bytes] | None,
        instruction: str | None = None,
    ) -> dict[str, Any]:
        """Return structured analysis for the supplied media."""


class TemplateProvider:
    """Deterministic template provider used when no AI provider key is available."""

    name = TEMPLATE_PROVIDER_NAME

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        settings = config or {}
        self.model = "template-v1"
        self.topic = str(settings.get("topic", DEFAULT_TOPIC)).strip() or DEFAULT_TOPIC
        self.topic_keywords = [
            word.strip().lower()
            for word in str(settings.get("topic_keywords", "")).split(",")
            if word.strip()
        ] or [self.topic.lower()]
        raw_hashtags = settings.get("hashtags", DEFAULT_HASHTAGS)
        self.hashtags = [str(tag).strip().lstrip("#") for tag in raw_hashtags if str(tag).strip()] or list(
            DEFAULT_HASHTAGS
        )
        raw_banned = settings.get("banned_words", DEFAULT_BANNED_WORDS)
        self.banned_words = [
            str(word).strip().lower() for word in raw_banned if str(word).strip()
        ] or list(DEFAULT_BANNED_WORDS)

    def analyze(
        self,
        metadata: dict[str, Any],
        frames: list[bytes] | None,
        instruction: str | None = None,
    ) -> dict[str, Any]:
        """Build a caption, hashtags, and rule-based score without any API call."""
        source_name = _source_name(metadata)
        # The facts the local analyzers really measured come first, so
        # the caption describes the video that was measured. When nothing
        # was measured, the caption is the topic and the title.
        measured = measured_content_facts(metadata)
        caption = " - ".join(part for part in (measured, source_name, self.topic) if part).strip()
        caption = fit_caption(caption)
        hashtags = self.hashtags[:MAX_HASHTAGS]
        score, reasons = self.score(caption, hashtags, metadata)
        return {
            "title": source_name,
            "caption": caption,
            "hashtags": hashtags,
            "language": str(metadata.get("language", "unknown")).strip() or "unknown",
            "subtitle_draft": None,
            "score": score,
            "score_reason": "; ".join(reasons),
        }

    def score(
        self,
        caption: str,
        hashtags: list[str],
        metadata: dict[str, Any],
    ) -> tuple[int, list[str]]:
        """Apply the transparent five-part scoring rules."""
        score = 0
        reasons: list[str] = []
        if 50 <= len(caption) <= MAX_CAPTION_LENGTH:
            score += 20
            reasons.append("caption length between 50 and 150 characters")
        if hashtags:
            score += 20
            reasons.append("caption includes hashtags")
        lowered = caption.lower()
        if not any(word in lowered for word in self.banned_words):
            score += 20
            reasons.append("no banned word present")
        if any(keyword in lowered for keyword in self.topic_keywords):
            score += 20
            reasons.append("caption contains the topic keyword")
        duration = metadata.get("duration_seconds")
        if isinstance(duration, (int, float)) and duration < 600:
            score += 20
            reasons.append("duration under 10 minutes")
        return score, reasons


def _source_name(metadata: dict[str, Any]) -> str:
    """Derive a readable source name from metadata."""
    for key in ("title", "task_id", "path", "source"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            candidate = Path(value.strip()).stem if key in {"path", "source"} else value.strip()
            candidate = candidate.replace("_", " ").replace("-", " ").strip()
            if candidate:
                return candidate
    return "untitled clip"


# Topic signals used to describe the content in a caption.
TOPIC_SIGNALS: dict[str, tuple[str, ...]] = {
    "ai music": (
        "ai music",
        "ai generated",
        "ai-made",
        "ai song",
        "made with ai",
        "suno",
        "udio",
        "stable audio",
        "music",
        "song",
        "beat",
    ),
    "music": ("music", "song", "beat", "sound", "remix", "lofi", "instrumental"),
    "daily tips": ("tip", "tips", "how to", "tutorial", "guide", "hack", "learn"),
    "dance": ("dance", "choreography", "dancer", "dance challenge"),
    "comedy": ("comedy", "funny", "skit", "laugh", "meme"),
    "food": ("recipe", "food", "cook", "kitchen", "ingredients"),
    "fitness": ("workout", "fitness", "gym", "exercise", "training"),
}


def detect_content_topic(metadata: dict[str, Any]) -> str:
    """Return the best matching topic label for the supplied metadata."""
    haystack = " ".join(
        str(metadata.get(key, ""))
        for key in ("title", "topic", "description", "caption", "task_id", "source", "path")
    ).lower()
    best_label = ""
    best_hits = 0
    for label, signals in TOPIC_SIGNALS.items():
        hits = sum(1 for signal in signals if signal in haystack)
        if hits > best_hits:
            best_hits = hits
            best_label = label
    if best_hits == 0:
        configured = str(metadata.get("topic", "")).strip()
        return configured or DEFAULT_TOPIC
    return best_label


def topic_hashtags(topic: str, base_hashtags: list[str]) -> list[str]:
    """Return hashtags that match the detected topic, keeping the base tags.

    The topic tags are added first so a matching hashtag is always present
    even when the base list already fills the limit.
    """
    extra = {
        "ai music": ["aimusic", "aigenerated", "sunomusic", "soundontiktok"],
        "music": ["music", "newmusic", "beats"],
        "daily tips": ["dailytips", "howto", "learnontiktok"],
        "dance": ["dance", "dancetok", "choreography"],
        "comedy": ["comedy", "fypfunny"],
        "food": ["foodie", "recipe", "foodtok"],
        "fitness": ["fitness", "gymtok", "workoutmotivation"],
    }.get(topic.strip().lower(), [])
    hashtags: list[str] = []
    for tag in list(extra) + list(base_hashtags):
        clean = str(tag).strip().lstrip("#")
        if clean and clean not in hashtags:
            hashtags.append(clean)
        if len(hashtags) == MAX_HASHTAGS:
            break
    return hashtags


def build_content_caption(
    metadata: dict[str, Any],
    topic: str,
    creator_credit: str = "",
) -> str:
    """Build a caption that matches the actual content of the video.

    The caption describes the detected topic rather than a generic template,
    and it always keeps the creator credit so the origin of the content is
    never hidden. No watermark or provenance marker is removed.

    When the local analyzers measured something about the video, the
    caption says what was really measured. A fact that was not measured
    is never written down, so the caption never claims a mood, a genre or
    a lyric that the machine did not read.
    """
    source_name = _source_name(metadata)
    descriptors = {
        "ai music": "AI music",
        "music": "music",
        "daily tips": "daily tips",
        "dance": "dance",
        "comedy": "comedy",
        "food": "food",
        "fitness": "fitness",
    }
    descriptor = descriptors.get(topic.strip().lower(), topic.strip() or DEFAULT_TOPIC)

    # The facts that the local analyzers really measured are used when
    # they are there. They come first, because they say what the video
    # really shows, and the title follows.
    parts: list[str] = []
    measured = measured_content_facts(metadata)
    if measured:
        parts.append(measured)
    parts.append(source_name)
    parts.append(descriptor)
    text = " - ".join(part for part in parts if part).strip()
    if creator_credit:
        text = f"{text} - {creator_credit}"
    return fit_caption(text, creator_credit)


def fit_caption(text: str, creator_credit: str = "") -> str:
    """Cut a caption to the limit while the credit always stays in it.

    The credit names the origin of the content, so it is never cut away.
    When the caption is too long, the middle part is shortened and the
    credit and the first words stay. The measured facts stay too, so the
    caption still says what the machine really read.
    """
    text = text.strip()
    if len(text) <= MAX_CAPTION_LENGTH:
        return text

    credit = creator_credit.strip()
    if not credit:
        return text[:MAX_CAPTION_LENGTH].rstrip()

    # The credit and the measured facts are kept, and the title in the
    # middle is what gets shortened. The origin and the real content of
    # the video never get cut away.
    parts = [part.strip() for part in text.split(" - ") if part.strip()]
    if parts and parts[-1] == credit:
        parts = parts[:-1]
    else:
        # The credit is somewhere in the caption already. It is kept and
        # the other parts are shortened around it.
        parts = [part for part in parts if part != credit]
    keep = MAX_CAPTION_LENGTH - len(credit) - 3
    if keep < 0:
        return credit[:MAX_CAPTION_LENGTH].rstrip()
    body = " - ".join(parts)
    return f"{body[:keep].rstrip()} - {credit}"


def measured_content_facts(metadata: dict[str, Any]) -> str:
    """Return one short phrase that says what was really measured.

    The phrase only names a fact that the local analyzers measured on
    this machine. When nothing was measured, the phrase is empty and
    the caption falls back to the topic and the title.
    """
    facts = metadata.get("local_facts")
    if not isinstance(facts, dict):
        return ""

    pieces: list[str] = []

    # The sound, when the track was really decoded.
    sound = facts.get("sound")
    if isinstance(sound, dict) and sound.get("measured"):
        tempo = sound.get("tempo_bpm")
        loudness = sound.get("loudness_db")
        duration = sound.get("duration_seconds")
        if isinstance(tempo, (int, float)) and float(tempo) > 0:
            pieces.append(f"nhịp {int(round(float(tempo)))} BPM")
        if isinstance(loudness, (int, float)):
            pieces.append(f"âm lượng {int(round(float(loudness)))} dB")
        if isinstance(duration, (int, float)) and float(duration) > 0:
            pieces.append(f"dài {int(round(float(duration)))} giây")

    # The picture, when the frames were really read.
    vision = facts.get("vision")
    if isinstance(vision, dict):
        reading = vision.get("reading") if isinstance(vision.get("reading"), dict) else {}
        # The objects and the scene are only named when the reading came
        # from the model. A reading that was never confirmed by the
        # model stays out of the caption.
        if reading.get("from_model"):
            seen = reading.get("objects") if isinstance(reading.get("objects"), list) else []
            names: list[str] = []
            for item in seen:
                if isinstance(item, dict) and str(item.get("label") or "").strip():
                    names.append(str(item["label"]).strip())
                if len(names) >= 2:
                    break
            if names:
                pieces.append("hình có " + ", ".join(names))
            elif str(reading.get("scene") or "").strip():
                pieces.append("hình: " + str(reading["scene"]).strip())
        ui = vision.get("production_ui") if isinstance(vision.get("production_ui"), dict) else {}
        if isinstance(ui.get("score"), (int, float)) and float(ui.get("score") or 0) >= 0.45:
            pieces.append("giao diện làm nhạc")

    if not pieces:
        return ""
    return ", ".join(pieces)


def analyze_content(
    metadata: dict[str, Any],
    config: dict[str, Any],
    *,
    creator_credit: str = "",
    provider: AIProvider | None = None,
    frames: list[bytes] | None = None,
    usage: AIUsage | None = None,
) -> AnalysisResult:
    """Analyse a video and write a caption that matches its content.

    The AI provider is used when one is available. The template provider is
    used otherwise and still produces a content-matching caption with topic
    hashtags and the creator credit, so the origin of the content stays
    visible.
    """
    topic = detect_content_topic(metadata)
    enriched = dict(metadata)
    enriched["topic"] = topic

    result = analyze_media(enriched, config, provider=provider, frames=frames, usage=usage)

    caption = build_content_caption(enriched, topic, creator_credit)
    hashtags = topic_hashtags(topic, list(result.hashtags))
    if creator_credit and creator_credit.strip().lower() not in caption.lower():
        caption = build_content_caption(enriched, topic, creator_credit)
    result.caption = caption[:MAX_CAPTION_LENGTH].rstrip()
    result.hashtags = hashtags
    result.title = _source_name(enriched)
    result.language = str(enriched.get("language", result.language)).strip() or result.language
    return result


class GeminiProvider:
    """Gemini provider backed by the official google-genai SDK."""

    name = "gemini"

    def __init__(self, model: str = DEFAULT_MODEL, api_key: str | None = None) -> None:
        self.model = model
        self._api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self._api_key:
            raise ProviderUnavailableError("GEMINI_API_KEY is not configured")

    def analyze(
        self,
        metadata: dict[str, Any],
        frames: list[bytes] | None,
        instruction: str | None = None,
    ) -> dict[str, Any]:
        """Analyse metadata and available frames with Gemini."""
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise ProviderUnavailableError(
                "google-genai is required for the Gemini provider"
            ) from exc

        client = genai.Client(api_key=self._api_key)
        prompt = _build_prompt(metadata, instruction)
        parts: list[Any] = [types.Part.from_text(text=prompt)]
        for frame in frames or []:
            parts.append(types.Part.from_bytes(data=frame, mime_type="image/jpeg"))
        response = client.models.generate_content(
            model=self.model,
            contents=[types.Content(role="user", parts=parts)],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_response_schema(),
            ),
        )
        text = getattr(response, "text", None)
        if not text:
            raise BrainError("Gemini returned no analysis text")
        try:
            result = json.loads(text)
        except json.JSONDecodeError as exc:
            raise BrainError("Gemini returned malformed JSON") from exc
        if not isinstance(result, dict):
            raise BrainError("Gemini returned an invalid analysis object")
        return result


def _response_schema() -> dict[str, Any]:
    """Return the structured JSON schema requested from Gemini."""
    return {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "caption": {"type": "string"},
            "hashtags": {"type": "array", "items": {"type": "string"}},
            "language": {"type": "string"},
            "subtitle_draft": {"type": "string"},
            "score": {"type": "integer"},
            "score_reason": {"type": "string"},
        },
        "required": [
            "title",
            "caption",
            "hashtags",
            "language",
            "score",
            "score_reason",
        ],
    }


def _build_prompt(metadata: dict[str, Any], instruction: str | None) -> str:
    """Build a constrained analysis prompt without inventing missing media facts."""
    return (
        "Analyse this video's metadata and any supplied frames. "
        "Detect the spoken or visible language. Create a concise title, a caption of at "
        f"most {MAX_CAPTION_LENGTH} characters, and no more than {MAX_HASHTAGS} hashtags. "
        "Provide a subtitle draft when the media supports it. Score the content from 0 to 100 "
        "and explain the score. Do not claim facts that are not visible or supplied. "
        f"Additional instruction: {instruction or 'none'}. "
        f"Metadata: {json.dumps(metadata, ensure_ascii=False, default=str)}"
    )


def create_provider(config: dict[str, Any]) -> AIProvider:
    """Create the configured provider, falling back to the template provider."""
    provider_name = str(config.get("ai_provider", "gemini")).lower()
    providers = config.get("providers", {})
    provider_config = providers.get(provider_name, {}) if isinstance(providers, dict) else {}
    if not isinstance(provider_config, dict):
        provider_config = {}
    template_config = dict(config.get("template", {}) or {})
    # The template provider follows the discovery topic so the caption and the
    # hashtags match the topic the run was asked for, not a fixed label. The
    # topic of the run wins over the label in the configuration.
    discovery = config.get("discovery", {}) if isinstance(config.get("discovery", {}), dict) else {}
    run_topic = str(discovery.get("target_topic", "")).strip()
    if run_topic:
        template_config["topic"] = run_topic
        keywords = str(template_config.get("topic_keywords", "")).strip()
        if not keywords or run_topic.lower() not in keywords.lower():
            template_config["topic_keywords"] = run_topic

    if provider_name == TEMPLATE_PROVIDER_NAME:
        return TemplateProvider(template_config)

    if provider_name == "gemini":
        if not os.getenv("GEMINI_API_KEY"):
            if template_config.get("fallback_enabled", True):
                return TemplateProvider(template_config)
            raise ProviderUnavailableError("GEMINI_API_KEY is not configured")
        return GeminiProvider(model=str(provider_config.get("model", DEFAULT_MODEL)))

    if provider_name == "meta":
        if template_config.get("fallback_enabled", True):
            return TemplateProvider(template_config)
        raise ProviderUnavailableError(
            "Meta provider is disabled; no Meta inference connection is implemented"
        )

    if provider_config.get("enabled", False):
        raise ProviderUnavailableError(f"Unknown AI provider '{provider_name}'")
    if template_config.get("fallback_enabled", True):
        return TemplateProvider(template_config)
    raise ProviderUnavailableError(f"AI provider '{provider_name}' is disabled")


def _is_retryable(error: Exception) -> bool:
    """Identify quota, timeout, and transient provider failures."""
    message = str(error).lower()
    retryable_terms = (
        "quota",
        "rate limit",
        "resource_exhausted",
        "timeout",
        "timed out",
        "deadline",
        "temporarily unavailable",
        "service unavailable",
        "internal error",
        "overloaded",
    )
    return any(term in message for term in retryable_terms)


def normalize_hashtags(values: Any) -> list[str]:
    """Normalize and cap a hashtag list."""
    if not isinstance(values, list):
        return []
    hashtags: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        hashtag = value.strip().lstrip("#").strip()
        if hashtag and hashtag not in hashtags:
            hashtags.append(hashtag)
        if len(hashtags) == MAX_HASHTAGS:
            break
    return hashtags


def normalize_result(
    payload: dict[str, Any],
    provider: AIProvider,
    usage: AIUsage,
) -> AnalysisResult:
    """Validate and normalize provider output."""
    caption = str(payload.get("caption", "")).strip()
    if not caption:
        raise BrainError("Provider response did not include a caption")
    if len(caption) > MAX_CAPTION_LENGTH:
        caption = caption[:MAX_CAPTION_LENGTH].rstrip()
    title = str(payload.get("title", "")).strip()
    if not title:
        raise BrainError("Provider response did not include a title")
    try:
        score = int(payload.get("score", 0))
    except (TypeError, ValueError) as exc:
        raise BrainError("Provider response included an invalid score") from exc
    score = max(0, min(100, score))
    language = str(payload.get("language", "unknown")).strip() or "unknown"
    subtitle = payload.get("subtitle_draft")
    subtitle_draft = str(subtitle).strip() if isinstance(subtitle, str) and subtitle.strip() else None
    return AnalysisResult(
        title=title,
        caption=caption,
        hashtags=normalize_hashtags(payload.get("hashtags", [])),
        language=language,
        score=score,
        score_reason=str(payload.get("score_reason", "")).strip(),
        subtitle_draft=subtitle_draft,
        provider=provider.name,
        model=provider.model,
        usage=usage,
    )


def analyze_media(
    metadata: dict[str, Any],
    config: dict[str, Any],
    *,
    provider: AIProvider | None = None,
    frames: list[bytes] | None = None,
    instruction: str | None = None,
    usage: AIUsage | None = None,
    max_retries: int = 2,
    backoff_seconds: float = 1.0,
    sleep: Any = time.sleep,
) -> AnalysisResult:
    """Analyse media with retries and safe quota/timeout handling."""
    call_usage = usage or AIUsage(limit=int(config.get("ai_max_calls", DEFAULT_MAX_CALLS)))
    selected_provider = provider or create_provider(config)
    attempt = 0
    while True:
        try:
            call_usage.record()
            payload = selected_provider.analyze(metadata, frames, instruction)
            return normalize_result(payload, selected_provider, call_usage)
        except QuotaExceededError:
            raise
        except Exception as exc:
            if attempt < max_retries and _is_retryable(exc):
                attempt += 1
                sleep(backoff_seconds * (2 ** (attempt - 1)))
                continue
            if _is_retryable(exc):
                return AnalysisResult(
                    title="",
                    caption="",
                    hashtags=[],
                    language="unknown",
                    status="FAILED_RETRYABLE",
                    provider=selected_provider.name,
                    model=selected_provider.model,
                    usage=call_usage,
                    error=str(exc),
                )
            raise


def result_to_dict(result: AnalysisResult) -> dict[str, Any]:
    """Serialize an analysis result for storage or logging."""
    return asdict(result)


__all__ = [
    "AIProvider",
    "AIUsage",
    "AnalysisResult",
    "BrainError",
    "DEFAULT_MODEL",
    "GeminiProvider",
    "ProviderUnavailableError",
    "QuotaExceededError",
    "TEMPLATE_PROVIDER_NAME",
    "TOPIC_SIGNALS",
    "TemplateProvider",
    "analyze_content",
    "analyze_media",
    "build_content_caption",
    "create_provider",
    "detect_content_topic",
    "normalize_hashtags",
    "normalize_result",
    "result_to_dict",
    "topic_hashtags",
]
