"""Targeted checks for the real audio analysis of the local analyzer.

The checks use the media that is already on the machine and the cache of
the discovery. Nothing is searched on TikTok and nothing is downloaded.
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


def _frame() -> bytes:
    """Return a frame that carries the layout of a music screen."""
    image = Image.new("RGB", (512, 288), (24, 24, 30))
    draw = ImageDraw.Draw(image)
    for x in range(14, 498, 2):
        height = 40 + ((x * 37) % 11) * 12
        draw.rectangle(
            [x, 125 - height // 2, x + 1, 125 + height // 2], fill=(120, 235, 175)
        )
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


AUDIO_DIR = Path("data/temp/audio")
BEAT120 = AUDIO_DIR / "beat120.webm"
BEAT90 = AUDIO_DIR / "beat90.webm"
TONE = AUDIO_DIR / "tone.webm"
SILENCE = AUDIO_DIR / "silence.webm"
MUSIC = AUDIO_DIR / "music.webm"

print("== 1. the sound tool of the machine is found or reported ==")
tools = la._tool_paths()
check("the tool search is a dict", isinstance(tools, dict))
check(
    "the tool names are reported",
    set(tools) == {"ffmpeg", "ffprobe"},
    str(tools),
)
missing = la.missing_audio_dependency()
if la.audio_available():
    check("the sound tool is available", True)
    check("nothing is reported missing", missing == "", missing)
    check(
        "the tool is a real file",
        all(path and Path(path).is_file() for path in tools.values()),
        str(tools),
    )
else:
    check("the sound tool is available", False, missing)
    check(
        "the missing tool is named",
        "ffmpeg" in missing or "ffprobe" in missing,
        missing,
    )
check(
    "the tool report matches the machine",
    la.available_tools()["ffmpeg"] == la.audio_available(),
    str(la.available_tools()),
)

print("\n== 2. a track with a known beat is measured on its own ==")
if BEAT120.exists() and la.audio_available():
    measured = la.measure_audio(str(BEAT120))
    check("the track was measured", measured is not None)
    check("the track has sound", (measured or {}).get("has_audio") is True)
    check("the track was decoded", (measured or {}).get("decoded") is True)
    check(
        "the length is the real one",
        abs(float((measured or {}).get("duration") or 0) - 12.0) < 0.3,
        str((measured or {}).get("duration")),
    )
    check(
        "the loudness is a real number",
        (measured or {}).get("mean_volume_db") is not None
        and float((measured or {}).get("mean_volume_db")) < 0,
        str((measured or {}).get("mean_volume_db")),
    )
    check(
        "the peak is a real number",
        (measured or {}).get("peak_volume_db") is not None,
        str((measured or {}).get("peak_volume_db")),
    )
    check(
        "the rhythm of 120 BPM is found",
        abs(float((measured or {}).get("tempo_bpm") or 0) - 120.0) < 4.0,
        str((measured or {}).get("tempo_bpm")),
    )
    check(
        "the rhythm is trusted",
        float((measured or {}).get("tempo_confidence") or 0) >= 0.8,
        str((measured or {}).get("tempo_confidence")),
    )
    check(
        "the movement of the energy is measured",
        (measured or {}).get("dynamics_db") is not None,
        str((measured or {}).get("dynamics_db")),
    )
    check(
        "the loudest passage is measured",
        (measured or {}).get("longest_loud_seconds") is not None,
        str((measured or {}).get("longest_loud_seconds")),
    )
    bands = (measured or {}).get("bands") or {}
    check(
        "the shape of the sound is measured",
        set(bands) == {"low", "middle", "high"},
        str(bands),
    )
    check(
        "the shape of the sound adds up to one",
        abs(sum(bands.values()) - 1.0) < 0.02,
        str(bands),
    )
else:
    print("[SKIP] the beat track is not on this machine")

print("\n== 3. a different beat gives a different rhythm ==")
if BEAT90.exists() and BEAT120.exists() and la.audio_available():
    slow = la.measure_audio(str(BEAT90)) or {}
    fast = la.measure_audio(str(BEAT120)) or {}
    check(
        "the slow beat is found",
        abs(float(slow.get("tempo_bpm") or 0) - 90.0) < 6.0,
        str(slow.get("tempo_bpm")),
    )
    check(
        "the two rhythms are told apart",
        float(slow.get("tempo_bpm") or 0) < float(fast.get("tempo_bpm") or 0),
        f"{slow.get('tempo_bpm')} vs {fast.get('tempo_bpm')}",
    )

print("\n== 4. a steady tone has no beat and no loud peaks ==")
if TONE.exists() and la.audio_available():
    tone = la.measure_audio(str(TONE)) or {}
    check("the tone was decoded", tone.get("decoded") is True)
    check(
        "the tone has no rhythm",
        not tone.get("tempo_bpm"),
        str(tone.get("tempo_bpm")),
    )
    check(
        "the tone is not trusted for a rhythm",
        float(tone.get("tempo_confidence") or 0) < 0.5,
        str(tone.get("tempo_confidence")),
    )
    check(
        "the tone has no standing peak",
        float(tone.get("crest_db") or 0) < 8.0,
        str(tone.get("crest_db")),
    )

print("\n== 5. a silent track has no quality to judge ==")
if SILENCE.exists() and la.audio_available():
    quiet = la.measure_audio(str(SILENCE)) or {}
    finding = la._music_quality(quiet)
    check(
        "the silent track is reported as no data",
        finding.certainty == la.NO_DATA,
        finding.certainty,
    )
    check("the silent track keeps no points", finding.points == 0, str(finding.points))
    check(
        "the reason says there is no sound",
        "không có tiếng" in finding.reason,
        finding.reason,
    )

print("\n== 6. the score of the sound carries the real measurements ==")
if BEAT120.exists() and la.audio_available():
    measured = la.measure_audio(str(BEAT120))
    finding = la._music_quality(measured)
    check("the finding is evidence", finding.certainty == la.EVIDENCE, finding.certainty)
    check("the finding keeps points", finding.points > 0, str(finding.points))
    check(
        "the finding is under its maximum",
        finding.points <= finding.maximum,
        str(finding.points),
    )
    reason = finding.reason
    for expected in ("thời lượng", "mức âm", "nhịp", "dải tần số"):
        check(f"the reason names {expected}", expected in reason, reason)

print("\n== 7. the sound is never guessed when it cannot be measured ==")
no_media = la._music_quality(None)
check(
    "no file means no data",
    no_media.certainty == la.NO_DATA,
    no_media.certainty,
)
check("no file keeps no points", no_media.points == 0, str(no_media.points))
not_decoded = la._music_quality(
    {"has_audio": True, "decoded": False, "codec": "opus", "sample_rate": 48000}
)
check(
    "a file that was not decoded stays no data",
    not_decoded.certainty == la.NO_DATA,
    not_decoded.certainty,
)
check(
    "the facts of the file are still reported",
    "opus" in not_decoded.reason,
    not_decoded.reason,
)

print("\n== 8. no genre, mood or trend is ever named ==")
if BEAT120.exists() and la.audio_available():
    measured = la.measure_audio(str(BEAT120))
    reason = la._music_quality(measured).reason
    forbidden = ("pop", "rock", "rap", "edm", "lofi", "ballad", "thể loại",
                 "mood", "trend", "xu hướng", "lyric", "lời")
    found = [word for word in forbidden if word in reason.lower()]
    check("no genre or trend is named", not found, str(found))

print("\n== 9. the analyzer is wired into the pipeline ==")
check(
    "the version is raised for the new measurements",
    la.ANALYZER_VERSION != "local-v1",
    la.ANALYZER_VERSION,
)
check(
    "the cache key carries the version",
    ca._cache_key_prefix("local") == f"local:{la.ANALYZER_VERSION}",
    ca._cache_key_prefix("local"),
)
check(
    "the pipeline can be given the file of a candidate",
    "media_resolver" in ca.analyze_candidates.__code__.co_varnames,
    str(ca.analyze_candidates.__code__.co_varnames),
)
check(
    "the request takes the file of a candidate",
    "media_path" in ca.request_content_analysis.__code__.co_varnames,
    str(ca.request_content_analysis.__code__.co_varnames),
)

print("\n== 10. the audio travels through the payload ==")
if MUSIC.exists() and la.audio_available():
    payload = ca.request_local_analysis(
        [_frame()],
        {"title": "x", "creator": "y", "source_url": "u"},
        media_path=str(MUSIC),
    )
    check(
        "the sound is known in the payload",
        payload.get("music_quality_known") is True,
        str(payload.get("music_quality_known")),
    )
    check(
        "the sound keeps points in the payload",
        int(payload.get("music_quality") or 0) > 0,
        str(payload.get("music_quality")),
    )
    check(
        "the reason travels with it",
        "đo được âm thanh thật" in str(payload.get("music_quality_reason")),
        str(payload.get("music_quality_reason")),
    )
else:
    print("[SKIP] the music file is not on this machine")

print("\n== 11. the file without a sound track is reported honestly ==")
media = Path("data/originals/p15v-clip.webm")
if media.exists():
    measured = la.measure_audio(str(media))
    finding = la._music_quality(measured)
    check(
        "a file without sound is no data",
        finding.certainty == la.NO_DATA,
        finding.certainty,
    )
    check("it keeps no points", finding.points == 0, str(finding.points))

print()
if FAILED:
    print(f"{len(FAILED)} CHECK(S) FAILED: " + ", ".join(FAILED))
    raise SystemExit(1)
print("ALL AUDIO ANALYSIS CHECKS PASSED")
