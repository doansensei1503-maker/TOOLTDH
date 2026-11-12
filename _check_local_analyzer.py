"""Targeted checks for the local video analyzer.

The checks are small and only cover the module that was changed. They do
not touch the discovery, the browser, or the network.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
from PIL import Image, ImageDraw

import candidate_analysis as ca
import local_analyzer as la

FAILED: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"[PASS] {name}")
    else:
        print(f"[FAIL] {name} — {detail}")
        FAILED.append(name)


def _jpeg(draw_fn, size=(512, 288), colour=(20, 20, 24)) -> bytes:
    """Return a JPEG that carries the picture the callback drew."""
    image = Image.new("RGB", size, colour)
    draw_fn(ImageDraw.Draw(image))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


def _music_ui() -> bytes:
    """A picture that looks like a music production screen."""
    def draw(d: ImageDraw.ImageDraw) -> None:
        # A dark panel with bright horizontal waveform bars, the shape a
        # music editor shows.
        d.rectangle([0, 0, 512, 288], fill=(24, 24, 30))
        d.rectangle([8, 8, 504, 58], fill=(52, 52, 62))
        # The waveform itself: dense bright bars of different heights.
        for x in range(14, 498, 2):
            height = 40 + ((x * 37) % 11) * 12
            d.rectangle([x, 125 - height // 2, x + 1, 125 + height // 2],
                        fill=(120, 235, 175))
        # A row of controls and a text block.
        for y in range(185, 275, 9):
            d.rectangle([16, y, 130, y + 4], fill=(205, 205, 220))
            d.rectangle([150, y, 330, y + 4], fill=(215, 170, 95))
    return _jpeg(draw)


def _plain_scene() -> bytes:
    """A picture with no music production structure and no text."""
    def draw(d: ImageDraw.ImageDraw) -> None:
        d.rectangle([0, 0, 512, 288], fill=(90, 70, 55))
        d.ellipse([100, 60, 400, 220], fill=(140, 110, 80))
    return _jpeg(draw)


def _flat_black() -> bytes:
    """A picture that carries nothing at all."""
    return _jpeg(lambda d: None, colour=(0, 0, 0))


print("== 1. the tools and the machine are reported honestly ==")
tools = la.available_tools()
check("tool list is a dict", isinstance(tools, dict) and bool(tools))
check("numpy is detected", tools.get("numpy") is True, str(tools))
check("pillow is detected", tools.get("pillow") is True, str(tools))
check("the tool list matches the machine", "ffmpeg" in tools and "openvino" in tools)
name = la.gpu_name()
check("the adapter name is read", isinstance(name, str))

print("\n== 2. the weights are the ones the product asks for ==")
check("six findings", len(la._FINDING_MAX) == 6, str(len(la._FINDING_MAX)))
check("weights sum to 100", sum(la._FINDING_MAX.values()) == 100, str(sum(la._FINDING_MAX.values())))
check(
    "topic 25, visual 15, music 15, hook 15, engagement 20, channel 10",
    la._FINDING_MAX == {
        "topic_fit": 25.0,
        "visual_quality": 15.0,
        "music_quality": 15.0,
        "hook_retention": 15.0,
        "engagement_virality": 20.0,
        "channel_fit": 10.0,
    },
    str(la._FINDING_MAX),
)

print("\n== 3. no frames means no score and no verdict ==")
result = la.analyze_locally([], {"title": "AI music", "creator": "x"})
check("no verdict", result.content_is_ai_music is None)
check("not rankable", result.rankable is False)
total, strengths, weaknesses = la.score_local(result)
check("score is zero", total == 0, str(total))
check("every finding has no data", all(
    f.certainty == la.NO_DATA for f in result.findings.values()
))

print("\n== 4. a music production screen is evidence ==")
frames = [_music_ui(), _music_ui(), _music_ui()]
result = la.analyze_locally(
    frames,
    {"title": "khoảnh khắc của bài hát", "creator": "somebody", "source_url": "u"},
)
topic = result.findings["topic_fit"]
check("the topic is evidence", topic.certainty == la.EVIDENCE, topic.certainty)
check("the verdict is yes", result.content_is_ai_music is True)
check("the candidate is rankable", result.rankable is True)
check("the topic keeps points", topic.points > 0, str(topic.points))
check("the topic is under its maximum", topic.points <= topic.maximum)

print("\n== 5. a plain scene with an AI caption is not evidence ==")
frames = [_plain_scene(), _plain_scene(), _plain_scene()]
result = la.analyze_locally(
    frames,
    {"title": "AI music ai song suno", "creator": "somebody", "source_url": "u"},
)
topic = result.findings["topic_fit"]
check("the topic is not evidence", topic.certainty != la.EVIDENCE, topic.certainty)
check("the verdict is not a yes", result.content_is_ai_music is not True)
check(
    "the caption alone does not rank it",
    result.rankable is False,
    str(result.rankable),
)

print("\n== 6. a missing measurement keeps no points ==")
frames = [_music_ui()]
result = la.analyze_locally(
    frames,
    {"title": "x", "creator": "y", "source_url": "u", "metrics_known": False},
)
music = result.findings["music_quality"]
check("the sound has no data", music.certainty == la.NO_DATA, music.certainty)
check("the sound keeps no points", music.points == 0, str(music.points))
check(
    "the reason says the machine could not hear it",
    "ffmpeg" in music.reason or "ffprobe" in music.reason,
    music.reason,
)
engagement = result.findings["engagement_virality"]
check("the metrics have no data", engagement.certainty == la.UNDETERMINED)
check("the metrics keep no points", engagement.points == 0, str(engagement.points))

print("\n== 7. the published metrics never decide the topic ==")
frames = [_plain_scene(), _plain_scene()]
quiet = la.analyze_locally(
    frames,
    {"title": "AI music", "creator": "c", "source_url": "u",
     "views": 5_000_000, "likes": 0, "comments": 0, "shares": 0, "metrics_known": True},
)
busy = la.analyze_locally(
    frames,
    {"title": "AI music", "creator": "c", "source_url": "u",
     "views": 1000, "likes": 500, "comments": 200, "shares": 300, "metrics_known": True},
)
check(
    "the topic is the same whatever the views are",
    quiet.findings["topic_fit"].certainty == busy.findings["topic_fit"].certainty,
)
check(
    "the topic points are the same whatever the views are",
    quiet.findings["topic_fit"].points == busy.findings["topic_fit"].points,
)
check(
    "the engagement signal does move",
    busy.findings["engagement_virality"].points
    > quiet.findings["engagement_virality"].points,
)

print("\n== 8. a score is never invented for an undecided candidate ==")
frames = [_plain_scene(), _plain_scene()]
result = la.analyze_locally(
    frames,
    {"title": "AI music", "creator": "c", "source_url": "u"},
)
total, strengths, weaknesses = la.score_local(result)
if result.rankable:
    check("a ranked candidate has a score", total > 0, str(total))
else:
    check("an undecided candidate keeps no score", total == 0, str(total))
    check("its gaps are listed", bool(weaknesses), str(weaknesses))

print("\n== 9. the pipeline uses the local analyzer by default ==")
check("the default provider is local", ca.ANALYZER_PROVIDER == "local", ca.ANALYZER_PROVIDER)
payload = ca.request_local_analysis([_music_ui()], {"title": "x", "creator": "y"})
check("the payload has the seven dimensions", all(
    f"{name}_known" in payload for name in (
        "ai_music_fit", "music_quality", "visual_quality",
        "hook_retention", "engagement_virality", "creativity", "channel_fit",
    )
))
check("the payload carries the version", payload.get("local_analyzer_version") == la.ANALYZER_VERSION)
check(
    "the local weights reach the payload",
    payload.get("ai_music_fit_max") == 25
    and payload.get("music_quality_max") == 15
    and payload.get("engagement_virality_max") == 20
    and payload.get("channel_fit_max") == 10,
    str(payload.get("ai_music_fit_max")),
)
check(
    "the local dimension weights add up to 100",
    sum(
        payload.get(f"{name}_max", 0)
        for name in (
            "ai_music_fit", "music_quality", "visual_quality",
            "hook_retention", "engagement_virality", "creativity", "channel_fit",
        )
    ) == 100,
    str(
        sum(
            payload.get(f"{name}_max", 0)
            for name in (
                "ai_music_fit", "music_quality", "visual_quality",
                "hook_retention", "engagement_virality", "creativity", "channel_fit",
            )
        )
    ),
)

print("\n== 10. the cache key carries the analyzer version ==")
check(
    "the local prefix carries the version",
    ca._cache_key_prefix("local") == f"local:{la.ANALYZER_VERSION}",
    ca._cache_key_prefix("local"),
)
check("the gemini prefix is plain", ca._cache_key_prefix("gemini") == "gemini")

print("\n== 11. the paid provider is never reached by default ==")
try:
    ca.request_content_analysis([b"x"], {"title": "t", "creator": "c"})
    check("the local analyzer answered", True)
except Exception as exc:
    check("the local analyzer answered", False, f"{type(exc).__name__}: {exc}")

print("\n== 12. an unknown provider name is refused ==")
try:
    ca.request_content_analysis([b"x"], {"title": "t", "creator": "c"}, provider="nope")
    check("the unknown provider is refused", False)
except RuntimeError as exc:
    check("the unknown provider is refused", True, str(exc))

print("\n== 13. a local sound model plugs in without a rewrite ==")
measured = {"has_audio": True, "codec": "opus", "sample_rate": 48000,
            "channels": 2, "bit_rate": 128000, "duration": 42.0,
            "mean_volume_db": -9.0}


def fake_sound_model(path):
    return dict(measured)


la.register_audio_adapter(fake_sound_model)
audio = la.measure_audio("d:/does/not/exist.webm")
check("the adapter is used", audio is not None and audio.get("sample_rate") == 48000, str(audio))
result = la.analyze_locally(
    [_music_ui()], {"title": "x", "creator": "y"},
    media_path="d:/does/not/exist.webm",
)
music = result.findings["music_quality"]
check("the sound is measured", music.certainty == la.EVIDENCE, music.certainty)
check("the sound keeps points", music.points > 0, str(music.points))
check(
    "the reason names the real measurement",
    "48000" in music.reason,
    music.reason,
)
# The seam is additive, so the default behaviour is not changed.
la._AUDIO_ADAPTERS.clear()
check("the seam can be cleared", la.measure_audio("d:/nope.webm") is None)

print("\n== 14. the container of a media file is read without a tool ==")
media = Path("data/originals/p15v-clip.webm")
if media.exists():
    container = la.read_container(str(media))
    check("the container is read", container is not None, str(container))
    check("the container is named", (container or {}).get("container") == "webm")
    check(
        "the audio track is reported honestly",
        isinstance((container or {}).get("has_audio"), bool),
        str((container or {}).get("has_audio")),
    )
    measured_audio = la.measure_audio(str(media))
    check("the measurement names its source", (measured_audio or {}).get("source") in ("ffmpeg", "container"))
    check(
        "a file that was not decoded stays unknown",
        (measured_audio or {}).get("decoded", True) is False
        or (measured_audio or {}).get("source") == "ffmpeg",
        str(measured_audio),
    )
else:
    check("the media file is there", False, str(media))

print()
if FAILED:
    print(f"{len(FAILED)} CHECK(S) FAILED: " + ", ".join(FAILED))
    raise SystemExit(1)
print("ALL LOCAL ANALYZER CHECKS PASSED")
