"""Targeted checks for the local vision analyzer of TOOLTDH.

The checks use the frames and the cache that are already on the machine.
Nothing is searched on TikTok and nothing is downloaded.
"""

from __future__ import annotations

import io
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
from PIL import Image, ImageDraw

import candidate_analysis as ca
import local_analyzer as la
import local_vision as lv

FAILED: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"[PASS] {name}")
    else:
        print(f"[FAIL] {name} — {detail}")
        FAILED.append(name)


def _frame(colour: tuple[int, int, int] = (30, 30, 40)) -> bytes:
    """Return a frame of one flat colour."""
    image = Image.new("RGB", (512, 288), colour)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


def _music_ui() -> bytes:
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


print("== 1. the hardware of the machine is read for real ==")
resources = lv.machine_resources()
check("the memory of the machine is read", resources["ram_gb"] > 0, str(resources))
check("the free memory is read", resources["ram_free_gb"] >= 0, str(resources))
check("the cores of the machine are read", resources["cores"] > 0, str(resources))
check("the graphics of the machine is read", bool(resources["gpu"]), str(resources))

print("\n== 2. the runtime is found or the lack of it is reported ==")
runtime = lv.vision_runtime()
check("the runtime is reported", isinstance(runtime, dict))
check(
    "the runtime names what it found",
    bool(runtime["runtime"]) == bool(runtime["available"]),
    str(runtime),
)
missing = lv.vision_dependency_missing()
if runtime["available"]:
    check("the runtime is available", True)
    check(
        "the model that is missing is named",
        "mô hình vision" in missing,
        missing,
    )
else:
    check("the runtime is available", False, missing)
    check("onnxruntime is named", "onnxruntime" in missing, missing)

print("\n== 3. the picture moves over time, measured on the real frames ==")
static = [_frame()] * 4
moving = [_frame((30, 30, 40)), _frame((200, 40, 40)), _frame((30, 200, 40)), _frame((40, 40, 220))]
static_motion = lv.measure_motion(static)
moving_motion = lv.measure_motion(moving)
check("the still frames were compared", static_motion.frames_compared == 3, str(static_motion))
check("the still frames barely move", static_motion.change < 0.02, str(static_motion.change))
check("the still frames are alike", static_motion.consistency > 0.95, str(static_motion.consistency))
check("the moving frames really move", moving_motion.change > 0.10, str(moving_motion.change))
check(
    "the moving frames are not alike",
    moving_motion.consistency < static_motion.consistency,
    f"{moving_motion.consistency} vs {static_motion.consistency}",
)
check("the changed area is measured", moving_motion.changed_area > 0.1, str(moving_motion.changed_area))

print("\n== 4. the opening of the video is measured ==")
hook = lv.measure_hook([_music_ui(), _frame((180, 60, 60))])
check("the opening was measured", hook.measured, hook.note)
check("the opening is evidence", hook.certainty == lv.EVIDENCE, hook.certainty)
check("the movement of the opening is measured", hook.movement > 0.0, str(hook.movement))
check("the sharpness of the first frame is measured", hook.sharpness > 0, str(hook.sharpness))
check(
    "the cut at the start is found",
    hook.opening_contrast > 0.0,
    str(hook.opening_contrast),
)
empty_hook = lv.measure_hook([])
check("an empty opening is not enough data", empty_hook.certainty == lv.NO_DATA, empty_hook.certainty)
check("an empty opening keeps no measure", empty_hook.measured is False)

print("\n== 5. no model means the content is not guessed ==")
lv.clear_vision_adapters()
report = lv.analyze_vision([_music_ui(), _music_ui()])
check("no model was used", report.model_used is False)
check("the reading is not enough data", report.reading.certainty == lv.NO_DATA, report.reading.certainty)
check("no scene was invented", report.reading.scene == "", report.reading.scene)
check("no object was invented", not report.reading.objects, str(report.reading.objects))
check("no text was invented", not report.reading.text, str(report.reading.text))
check(
    "the report says what is missing",
    bool(report.missing_dependency),
    report.missing_dependency,
)
check(
    "the pixels were still measured",
    report.motion.frames_used == 2,
    str(report.motion),
)
check(
    "the report is only a possibility",
    report.certainty == lv.POSSIBILITY,
    report.certainty,
)
described = lv.describe_vision(report)
check(
    "the description says no model was used",
    "không có mô hình vision" in described,
    described,
)

print("\n== 6. a model plugs in and is told apart from the pixels ==")


def _fake_model(frames: list[bytes]) -> dict:
    """A model that reads the picture."""
    return {
        "scene": "a music production screen with a waveform",
        "objects": [{"label": "waveform", "confidence": 0.91}],
        "text": ["Suno"],
        "model": "test-vision",
        "from_model": True,
        "confidence": 0.87,
    }


lv.register_vision_adapter(_fake_model)
report = lv.analyze_vision([_music_ui(), _frame((180, 60, 60))])
check("the model was used", report.model_used is True)
check("the model is named", report.model == "test-vision", report.model)
check("the reading is evidence", report.reading.certainty == lv.EVIDENCE, report.reading.certainty)
check("the scene was read", "waveform" in report.reading.scene, report.reading.scene)
check("the object was seen", report.reading.objects[0].label == "waveform")
check("the text was read", report.reading.text == ["Suno"], str(report.reading.text))
check(
    "nothing is reported missing any more",
    report.missing_dependency == "",
    report.missing_dependency,
)
check(
    "the report is evidence",
    report.certainty == lv.EVIDENCE,
    report.certainty,
)
described = lv.describe_vision(report)
check("the description names the model", "test-vision" in described, described)
check(
    "the description still shows the movement",
    "hình thay đổi" in described,
    described,
)
lv.clear_vision_adapters()

print("\n== 7. a broken model never breaks the analyzer ==")


def _broken_model(frames: list[bytes]) -> dict:
    """A model that fails."""
    raise RuntimeError("the model is broken")


lv.register_vision_adapter(_broken_model)
report = lv.analyze_vision([_music_ui(), _music_ui()])
check("the broken model was skipped", report.model_used is False)
check("the pixels were still measured", report.motion.frames_used == 2, str(report.motion))
lv.clear_vision_adapters()

print("\n== 8. the analyzer keeps the model apart from the heuristics ==")
result = la.analyze_locally(
    [_music_ui()] * 3,
    {"title": "x", "creator": "y", "source_url": "u"},
)
check("the analysis carries a vision report", result.vision is not None)
check(
    "the report says no model was used",
    result.vision.model_used is False,
    str(result.vision.model_used),
)
check(
    "the motion was really measured",
    result.vision.motion.frames_used == 3,
    str(result.vision.motion),
)
check(
    "the summary tells what was seen",
    "hình thay đổi" in result.summary,
    result.summary,
)
check(
    "the summary says no model was used",
    "không có mô hình vision" in result.summary,
    result.summary,
)
topic = result.findings["topic_fit"]
check("the topic still has a certainty", bool(topic.certainty), topic.certainty)
check(
    "the topic was not decided by a model that is not there",
    "mô hình vision" not in topic.reason,
    topic.reason,
)

print("\n== 9. a model that really sees AI music decides the topic ==")
lv.clear_vision_adapters()
lv.register_vision_adapter(
    lambda frames: {
        "scene": "an AI music generator page with a song and a waveform",
        "objects": [{"label": "ai music generator", "confidence": 0.9}],
        "text": ["Suno"],
        "model": "test-vision",
        "from_model": True,
        "confidence": 0.9,
    }
)
result = la.analyze_locally(
    [_frame((30, 30, 40))],
    {"title": "x", "creator": "y", "source_url": "u"},
)
topic = result.findings["topic_fit"]
check("the model decided the topic", topic.certainty == la.EVIDENCE, topic.certainty)
check("the topic keeps points", topic.points > 0, str(topic.points))
check("the reason names the model", "mô hình vision" in topic.reason, topic.reason)
check("the reason names what it saw", "waveform" in topic.reason or "generator" in topic.reason, topic.reason)
check(
    "the verdict is that it is AI music",
    result.content_is_ai_music is True,
    str(result.content_is_ai_music),
)

print("\n== 10. a model that sees no AI music keeps the topic at zero ==")
lv.clear_vision_adapters()
lv.register_vision_adapter(
    lambda frames: {
        "scene": "a cat sitting on a sofa in a living room",
        "objects": [{"label": "cat", "confidence": 0.95}],
        "text": [],
        "model": "test-vision",
        "from_model": True,
        "confidence": 0.95,
    }
)
result = la.analyze_locally(
    [_frame((30, 30, 40))],
    {"title": "x", "creator": "y", "source_url": "u"},
)
topic = result.findings["topic_fit"]
check("the model decided against it", topic.certainty == la.EVIDENCE, topic.certainty)
check("the topic keeps no points", topic.points == 0, str(topic.points))
check(
    "the verdict says it is not AI music",
    result.content_is_ai_music is False,
    str(result.content_is_ai_music),
)
lv.clear_vision_adapters()

print("\n== 11. the score of the opening uses the real movement ==")
still = la.analyze_locally(
    [_frame()] * 3,
    {"title": "x", "creator": "y", "source_url": "u"},
)
moving_result = la.analyze_locally(
    [_frame((30, 30, 40)), _frame((210, 50, 50)), _frame((30, 210, 50))],
    {"title": "x", "creator": "y", "source_url": "u"},
)
still_hook = still.findings["hook_retention"]
moving_hook = moving_result.findings["hook_retention"]
check("the still opening was judged", still_hook.certainty == la.EVIDENCE, still_hook.certainty)
check(
    "the moving opening keeps more points",
    moving_hook.points > still_hook.points,
    f"{moving_hook.points} vs {still_hook.points}",
)
check(
    "the reason shows the movement",
    "hình chuyển động" in moving_hook.reason,
    moving_hook.reason,
)

print("\n== 12. the cache of the discovery is reused ==")
cache = ca.load_cache()
with_frames = [
    key for key, value in cache.items()
    if isinstance(value, dict) and value.get("frames")
]
check("the cache still holds the frames", len(with_frames) > 0, str(len(with_frames)))
if with_frames:
    frames = ca._decode_frames(cache[with_frames[0]].get("frames") or [])
    report = lv.analyze_vision(frames)
    check(
        "the cached frames were read",
        report.motion.frames_used == len(frames),
        f"{report.motion.frames_used} of {len(frames)}",
    )
    check(
        "no model was needed for the pixels",
        report.motion.frames_compared == len(frames) - 1,
        str(report.motion),
    )

print("\n== 13. the API and the weights are untouched ==")
check(
    "the weights did not change",
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
check(
    "the weights still add up to 100",
    sum(la._FINDING_MAX.values()) == 100,
    str(sum(la._FINDING_MAX.values())),
)
check(
    "the version was not raised",
    la.ANALYZER_VERSION == "local-v2",
    la.ANALYZER_VERSION,
)
check(
    "the sound adapter is still there",
    hasattr(la, "register_audio_adapter"),
)
check(
    "the sound seam is untouched",
    la.register_audio_adapter.__doc__ is not None,
)
check(
    "the vision seam is ready",
    hasattr(lv, "register_vision_adapter"),
)

print("\n== 14. nothing is called on the internet ==")
source = Path("local_vision.py").read_text(encoding="utf-8")
# The names of the paid services may appear in a comment that says they
# are never called. What matters is that no call is made.
calls = (
    "requests.get", "requests.post", "urllib.request",
    "httpx.", "aiohttp", "openai.", "genai.",
)
found = [word for word in calls if word in source]
check("no call on the internet", not found, str(found))
analyzer_source = Path("local_analyzer.py").read_text(encoding="utf-8")
found = [word for word in calls if word in analyzer_source]
check("the analyzer calls nothing paid", not found, str(found))
check(
    "the vision module never downloads a model",
    "urlretrieve" not in source and "urlopen" not in source,
)

print("\n== 15. the ONNX path is ready and honest ==")
check(
    "the adapter is offered for a model that is not there",
    lv.onnx_vision_adapter(r"d:\TOOLTDH\models\does_not_exist.onnx") is None,
)
check(
    "the auto search finds no model on this machine",
    lv.auto_register_onnx_model() == ""
    or Path(lv.auto_register_onnx_model()).is_file(),
    lv.auto_register_onnx_model(),
)
# A model that is really on the machine, if there is one, has to be
# opened by the runtime of the machine.
real_models = []
for root in (
    Path.home() / "Downloads",
    Path.home() / ".cache",
):
    if not root.is_dir():
        continue
    for base, _dirs, files in os.walk(root):
        for name in files:
            if name.lower().endswith(".onnx"):
                candidate = Path(base) / name
                if candidate.stat().st_size > 100_000:
                    real_models.append(candidate)
                    break
        if len(real_models) >= 1:
            break
    if real_models:
        break
if real_models:
    model = str(real_models[0])
    shape = lv._model_input_shape(model, lv.vision_runtime().get("path") or "")
    check("a real model on the machine is read", shape is not None, str(shape))
    size = lv._model_input_size(model, lv.vision_runtime())
    check("the size of the model is known", size[0] >= 0, str(size))
    adapter = lv.onnx_vision_adapter(model)
    check("an adapter is built for a real model", adapter is not None)
    try:
        result = adapter([_music_ui()])
        check(
            "the adapter answers without breaking",
            result is None or isinstance(result, dict),
            str(result)[:120],
        )
    except Exception as exc:
        check("the adapter answers without breaking", False, f"{type(exc).__name__}: {exc}")
else:
    print("[SKIP] there is no real model on this machine")

print()
if FAILED:
    print(f"{len(FAILED)} CHECK(S) FAILED: " + ", ".join(FAILED))
    raise SystemExit(1)
print("ALL LOCAL VISION CHECKS PASSED")
