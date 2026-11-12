"""Local video analyzer for TOOLTDH.

This module judges a candidate video on the machine itself. It asks no
paid API, sends nothing off the machine, and uses no AI token.

The judgement is made from the real frames that the discovery already
read and from the metrics the platform published. What the local analyzer
can and cannot decide is stated plainly:

- **Evidence** — the frames really show the thing being claimed. A frame
  that carries an AI music tool on screen is evidence.
- **Possibility** — the frames are consistent with AI-made content but
  do not prove it. The analyzer says so and keeps the points lower.
- **Undetermined** — the frames do not settle the question. The dimension
  is marked as not enough data and keeps no points.
- **Not enough data** — there are no frames to judge at all.

The analyzer never turns a caption keyword into evidence. A video whose
caption says "AI" but whose frames show a car is rejected.

The audio is judged only when the machine can really read it. When no
audio tool is installed, the audio dimensions stay not enough data and
the candidate is reported as such, rather than guessed.
"""

from __future__ import annotations

import math
import os
import shutil
import struct
import subprocess
from dataclasses import dataclass, field
from typing import Any

from local_vision import (
    VisionReport,
    analyze_vision,
    auto_register_onnx_model,
    describe_vision,
    register_vision_adapter,
)

# The model that was found on this machine, when there was one. It is
# looked for once, so the analyzer does not walk the disk for every
# candidate.
_VISION_MODEL_ON_DISK = ""


def vision_model_path() -> str:
    """Return the vision model of this machine, when there is one.

    The model is looked for once and then remembered. Nothing is
    downloaded here.
    """
    global _VISION_MODEL_ON_DISK
    if not _VISION_MODEL_ON_DISK:
        _VISION_MODEL_ON_DISK = auto_register_onnx_model()
    return _VISION_MODEL_ON_DISK

# The version of the analyzer. It is part of the cache key, so a new
# version of the analyzer makes the old results stale instead of mixing
# two different sets of numbers.
#
# The version moved to v3 when the vision analyzer learned to tell the
# screen of a music tool from a plain picture, and when a model that
# only names things stopped being taken for a model that can say how
# the content was made. Both change the numbers, so the old results
# must not be mixed with the new ones.
ANALYZER_VERSION = "local-v3"

# The label the dashboard shows when the machine cannot decide.
INSUFFICIENT_DATA = "CHƯA ĐỦ DỮ LIỆU"


# --------------------------------------------------------------------------
# What the analyzer found, with the level of certainty of every finding.
# --------------------------------------------------------------------------

EVIDENCE = "evidence"
POSSIBILITY = "possibility"
UNDETERMINED = "undetermined"
NO_DATA = "no_data"

_CERTAINTY_ORDER = {
    EVIDENCE: 3,
    POSSIBILITY: 2,
    UNDETERMINED: 1,
    NO_DATA: 0,
}


@dataclass
class Finding:
    """One thing the analyzer observed, and how sure it is.

    ``certainty`` is one of ``evidence``, ``possibility``,
    ``undetermined`` or ``no_data``. ``points`` is the score the finding
    contributes and ``maximum`` is the most it could contribute.
    """

    key: str
    points: float = 0.0
    maximum: float = 0.0
    certainty: str = UNDETERMINED
    reason: str = ""

    @property
    def known(self) -> bool:
        """Return True when the analyzer really decided this finding."""
        return self.certainty in (EVIDENCE, POSSIBILITY)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "points": round(self.points, 2),
            "maximum": round(self.maximum, 2),
            "certainty": self.certainty,
            "reason": self.reason,
        }


@dataclass
class LocalAnalysis:
    """The result of the local analysis of one candidate."""

    source_url: str = ""
    creator: str = ""
    title: str = ""
    findings: dict[str, Finding] = field(default_factory=dict)
    # The real summary of what the frames show.
    summary: str = ""
    # The verdict on whether this really is AI Music content.
    # True, False, or None when the machine cannot decide.
    content_is_ai_music: bool | None = None
    content_relevance_reason: str = ""
    # True when the frames show an AI-made picture.
    content_ai_visual: bool | None = None
    # The number of frames that were really read.
    frame_count: int = 0
    # The tools the analyzer was able to use.
    tools: dict[str, bool] = field(default_factory=dict)
    # What the machine is missing to measure the sound, when it is.
    audio_dependency_missing: str = ""
    # What the local vision analyzer really saw in the frames.
    vision: VisionReport | None = None
    # The version of the analyzer that produced this result.
    analyzer_version: str = ANALYZER_VERSION
    # True when there is enough data to rank the candidate.
    rankable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_url": self.source_url,
            "creator": self.creator,
            "title": self.title,
            "findings": {k: v.to_dict() for k, v in self.findings.items()},
            "summary": self.summary,
            "content_is_ai_music": self.content_is_ai_music,
            "content_relevance_reason": self.content_relevance_reason,
            "content_ai_visual": self.content_ai_visual,
            "frame_count": self.frame_count,
            "tools": dict(self.tools),
            "audio_dependency_missing": self.audio_dependency_missing,
            "vision": self.vision.to_dict() if self.vision else {},
            "analyzer_version": self.analyzer_version,
            "rankable": self.rankable,
        }


# --------------------------------------------------------------------------
# The tools the machine has. Nothing is installed and nothing is downloaded.
# --------------------------------------------------------------------------

def available_tools() -> dict[str, bool]:
    """Return which analysis tools this machine really has.

    The sound tools are looked for on the PATH and in the places a
    package manager puts them, so a machine that has FFmpeg but did not
    add it to the PATH is still reported as having it.
    """
    paths = _tool_paths()
    tools = {
        "numpy": _has_module("numpy"),
        "pillow": _has_module("PIL"),
        "opencv": _has_module("cv2"),
        "scipy": _has_module("scipy"),
        "sklearn": _has_module("sklearn"),
        "ffmpeg": bool(paths.get("ffmpeg")),
        "ffprobe": bool(paths.get("ffprobe")),
        "openvino": _has_module("openvino"),
        "onnxruntime": _has_module("onnxruntime"),
    }
    return tools


def _has_module(name: str) -> bool:
    """Return True when the module can be imported."""
    try:
        __import__(name)
    except Exception:
        return False
    return True


def gpu_name() -> str:
    """Return the name of the graphics adapter, or an empty string."""
    return _read_gpu_name()


def _read_gpu_name() -> str:
    """Read the name of the graphics adapter with a light system call."""
    if os.name == "nt":
        try:
            import subprocess as sp

            result = sp.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "(Get-CimInstance Win32_VideoController | Select-Object -First 1).Name",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            name = (result.stdout or "").strip()
            if name:
                return name
        except Exception:
            return ""
        return ""
    try:
        result = subprocess.run(
            ["lspci"], capture_output=True, text=True, timeout=10
        )
        for line in (result.stdout or "").splitlines():
            if "VGA" in line or "3D controller" in line:
                return line.split(":", 2)[-1].strip()
    except Exception:
        return ""
    return ""


# --------------------------------------------------------------------------
# The image features the analyzer measures from the real frames.
# --------------------------------------------------------------------------

def _frame_features(frame: bytes) -> dict[str, float] | None:
    """Measure the visual features of one frame.

    The measurement is done with the libraries this machine already has.
    When a frame cannot be read, ``None`` is returned, so the caller knows
    the frame carries nothing.
    """
    try:
        import numpy as np
        from PIL import Image
    except Exception:
        return None

    try:
        import io

        with Image.open(io.BytesIO(frame)) as image:
            picture = np.asarray(image.convert("RGB"), dtype=np.float32)
    except Exception:
        return None

    if picture.size == 0:
        return None

    height, width = picture.shape[0], picture.shape[1]
    luminance = (
        0.299 * picture[:, :, 0] + 0.587 * picture[:, :, 1] + 0.114 * picture[:, :, 2]
    )

    # The contrast and the colour spread tell how rich the picture is.
    contrast = float(luminance.std())
    channel_spread = float(picture.reshape(-1, 3).std(axis=0).mean())

    # The edge density tells how much detail and movement the frame holds.
    try:
        dx = np.abs(np.diff(luminance, axis=1)).mean() if width > 1 else 0.0
        dy = np.abs(np.diff(luminance, axis=0)).mean() if height > 1 else 0.0
        edges = float((dx + dy) / 2.0)
    except Exception:
        edges = 0.0

    # The colourfulness and the saturation tell whether the picture is
    # vivid or flat and grey.
    maxc = picture.max(axis=2)
    minc = picture.min(axis=2)
    saturation = float((maxc - minc).mean())
    colourfulness = float(
        np.sqrt(
            (picture[:, :, 0] - picture[:, :, 1]) ** 2
            + (picture[:, :, 0] - picture[:, :, 2]) ** 2
            + (picture[:, :, 1] - picture[:, :, 2]) ** 2
        ).mean()
    )

    # The share of the frame that is very dark or very bright tells whether
    # the frame is readable at all.
    dark = float((luminance < 12).mean())
    blown = float((luminance > 248).mean())

    # The number of distinct colours is a cheap sign of a synthetic image:
    # a rendered picture carries gradients, a flat photo carries fewer.
    try:
        quantised = (picture // 32).astype(np.uint8).reshape(-1, 3)
        distinct = int(np.unique(quantised, axis=0).shape[0])
    except Exception:
        distinct = 0

    return {
        "width": float(width),
        "height": float(height),
        "aspect": float(width) / float(height) if height else 0.0,
        "brightness": float(luminance.mean()),
        "contrast": contrast,
        "channel_spread": channel_spread,
        "edges": edges,
        "saturation": saturation,
        "colourfulness": colourfulness,
        "dark_ratio": dark,
        "blown_ratio": blown,
        "distinct_colours": float(distinct),
    }


def _average_features(frames: list[bytes]) -> dict[str, float]:
    """Return the mean of the features of every readable frame."""
    import numpy as np

    measured = [_frame_features(frame) for frame in frames]
    measured = [item for item in measured if item]
    if not measured:
        return {}
    keys = measured[0].keys()
    return {
        key: float(np.mean([item[key] for item in measured])) for key in keys
    }


# --------------------------------------------------------------------------
# The audio, when this machine can really read it.
# --------------------------------------------------------------------------

# The places where a sound tool is looked for. The tool is used when it is
# there; nothing is ever installed by this module. A tool that is not on
# the PATH is still found when it sits in one of the usual places, so a
# machine that has FFmpeg but did not add it to the PATH can still use it.
_FFMPEG_SEARCH_PATHS = (
    "ffmpeg",
    "ffprobe",
)

# How deep the search goes into the folders where a tool is kept. A
# package manager puts the tool a few folders deep, and a deeper search
# would walk a big disk for nothing.
_TOOL_SEARCH_DEPTH = 5


def _find_tool(name: str) -> str | None:
    """Return the path of a sound tool, or None when it is not there.

    The tool is looked for on the PATH first, and then in the places a
    package manager puts it. Nothing is installed and nothing is changed
    on the machine.
    """
    found = shutil.which(name)
    if found:
        return found

    candidates: list[str] = []
    home = os.path.expanduser("~")
    local = os.environ.get("LOCALAPPDATA", "")
    program = os.environ.get("ProgramFiles", r"C:\Program Files")
    program_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")

    roots: list[str] = []
    if local:
        # The WinGet and the Chocolatey packages.
        roots.append(os.path.join(local, "Microsoft", "WinGet", "Packages"))
        roots.append(os.path.join(local, "Microsoft", "WinGet", "Links"))
        roots.append(os.path.join(local, "Programs"))
    roots.append(os.path.join(program, "ffmpeg"))
    roots.append(os.path.join(program_x86, "ffmpeg"))
    roots.append("C:\\ffmpeg")
    roots.append(os.path.join(home, "ffmpeg"))
    roots.append(os.path.join(home, "scoop", "apps", "ffmpeg"))
    roots.append("/usr/bin")
    roots.append("/usr/local/bin")
    roots.append("/opt/homebrew/bin")

    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        candidates.append(root)

    for root in candidates:
        try:
            for base, dirs, files in os.walk(root):
                # The search stays shallow, so a big disk is not walked
                # for nothing. The depth of the folder that is being
                # looked at is counted from the root of the search.
                depth = base[len(root):].count(os.sep)
                if depth >= _TOOL_SEARCH_DEPTH:
                    dirs[:] = []
                for wanted in (name, f"{name}.exe"):
                    if wanted in files:
                        candidate = os.path.join(base, wanted)
                        if os.path.isfile(candidate):
                            return candidate
        except Exception:
            continue
    return None


def _tool_paths() -> dict[str, str | None]:
    """Return where the sound tools of this machine are."""
    return {
        "ffmpeg": _find_tool("ffmpeg"),
        "ffprobe": _find_tool("ffprobe"),
    }


def audio_available() -> bool:
    """Return True when the machine can read the audio of a media file."""
    tools = _tool_paths()
    return bool(tools["ffmpeg"] and tools["ffprobe"])


def missing_audio_dependency() -> str:
    """Return what the machine is missing to read the audio, or an empty string.

    The message names the tool that is missing and where it was looked
    for, so the admin can install it or put it on the PATH. Nothing is
    installed by this module.
    """
    tools = _tool_paths()
    missing = [name for name in ("ffmpeg", "ffprobe") if not tools.get(name)]
    if not missing:
        return ""
    return (
        "máy thiếu " + ", ".join(missing)
        + "; đặt chúng vào PATH hoặc cài FFmpeg để đo được âm thanh"
    )


# --------------------------------------------------------------------------
# The container of the media file, read with the tools of the machine.
# --------------------------------------------------------------------------

# The elements of a Matroska or WebM file that carry the audio facts. The
# machine can read the container of a video without any tool at all, so the
# codec and the sample rate are real facts even when no sound tool is
# installed. The sound itself still needs a tool, and stays unknown without
# one.
_EBML_IDS = {
    0x18538067: "Segment",
    0x1549A966: "Info",
    0x1654AE6B: "Tracks",
    0xAE: "TrackEntry",
    0xE0: "Video",
    0xE1: "Audio",
    0xB0: "PixelWidth",
    0xBA: "PixelHeight",
    0xB5: "SampleRate",
    0x9F: "Channels",
    0x86: "CodecID",
    0x2AD7B1: "TimecodeScale",
    0x4489: "Duration",
}


def _read_ebml_id(data: bytes, offset: int) -> tuple[int, int]:
    """Return an EBML element id and the offset after it.

    The id of an element keeps its marker bits, so it is read as the raw
    bytes that tell its own length.
    """
    if offset >= len(data):
        return 0, offset
    first = data[offset]
    length = 1
    mask = 0x80
    while length <= 4 and not (first & mask):
        mask >>= 1
        length += 1
    if offset + length > len(data):
        return 0, len(data)
    return int.from_bytes(data[offset:offset + length], "big"), offset + length


def _read_ebml_number(data: bytes, offset: int) -> tuple[int, int]:
    """Return an EBML variable length number and the offset after it.

    The length of the number is told by the position of the marker bit,
    which is the first set bit of the byte. The marker bit itself is not
    part of the value.
    """
    if offset >= len(data):
        return 0, offset
    first = data[offset]
    if first == 0:
        return 0, offset + 1
    # The marker is the highest set bit of the byte. A byte of 0x84 has
    # its marker at the fourth bit, so the number is four bytes long.
    length = 1
    marker = 0x80
    while not (first & marker):
        marker >>= 1
        length += 1
    if length > 8 or offset + length > len(data):
        return 0, len(data)
    value = int.from_bytes(data[offset:offset + length], "big")
    # The marker bit is not part of the value.
    value &= (1 << (7 * length)) - 1
    return value, offset + length


def _read_ebml_element(data: bytes, offset: int) -> tuple[int, bytes, int]:
    """Return the id, the payload and the offset after one EBML element."""
    element_id, offset = _read_ebml_id(data, offset)
    size, offset = _read_ebml_number(data, offset)
    if size > len(data) - offset:
        size = len(data) - offset
    return element_id, data[offset:offset + size], offset + size


def read_container(media_path: str) -> dict[str, Any] | None:
    """Read the real facts of a media file from its container.

    The container carries the codec, the sample rate, the number of
    channels and the length of the track. These are facts about the file,
    read from the file itself. The sound itself is not measured here, so
    the caller still needs a sound tool to judge the quality.
    """
    path = str(media_path or "").strip()
    if not path or not os.path.isfile(path):
        return None
    try:
        with open(path, "rb") as handle:
            data = handle.read(1 << 20)
    except Exception:
        return None

    if not data.startswith(b"\x1a\x45\xdf\xa3"):
        # Not a Matroska or WebM file. The other containers need a tool.
        return None

    found: dict[str, Any] = {"has_audio": False, "container": "webm"}
    state = {
        "codec": "",
        "sample_rate": 0,
        "channels": 0,
        "timecode_scale": 0,
        "duration": 0.0,
    }

    def walk(blob: bytes, start: int, stop: int, depth: int = 0) -> None:
        """Walk the elements of the file and collect the audio facts."""
        offset = start
        while offset < stop and depth < 8:
            try:
                element_id, payload, offset = _read_ebml_element(blob, offset)
            except Exception:
                return
            name = _EBML_IDS.get(element_id)
            if name == "Segment":
                walk(payload, 0, len(payload), depth + 1)
            elif name == "Tracks":
                walk(payload, 0, len(payload), depth + 1)
            elif name == "Info":
                walk(payload, 0, len(payload), depth + 1)
            elif name == "TrackEntry":
                # The track is read in full, so the audio track is found.
                try:
                    track_id, track_payload, _ = _read_ebml_element(payload, 0)
                except Exception:
                    continue
                if track_id == 0xE1:
                    found["has_audio"] = True
                    walk(track_payload, 0, len(track_payload), depth + 1)
            elif name == "Audio":
                walk(payload, 0, len(payload), depth + 1)
            elif name == "CodecID":
                state["codec"] = payload.decode("utf-8", "replace").strip("\x00")
            elif name == "SampleRate":
                state["sample_rate"] = int(
                    int.from_bytes(payload, "big") if payload else 0
                )
            elif name == "Channels":
                state["channels"] = int(
                    int.from_bytes(payload, "big") if payload else 0
                )
            elif name == "TimecodeScale":
                state["timecode_scale"] = int(
                    int.from_bytes(payload, "big") if payload else 0
                )
            elif name == "Duration":
                try:
                    # The duration is a float of eight bytes in a full
                    # file, and an integer of ticks in a shorter one.
                    if len(payload) == 8:
                        state["duration"] = struct.unpack(">d", payload)[0]
                    else:
                        state["duration"] = float(
                            int.from_bytes(payload, "big") if payload else 0
                        )
                except (TypeError, ValueError, struct.error):
                    pass

    walk(data, 0, len(data))

    if state["codec"]:
        found["codec"] = state["codec"]
    if state["sample_rate"]:
        found["sample_rate"] = state["sample_rate"]
    if state["channels"]:
        found["channels"] = state["channels"]
    scale = state["timecode_scale"]
    ticks = state["duration"]
    if scale and ticks:
        # The duration is counted in the timecode scale, which is the
        # number of nanoseconds of one tick.
        seconds = ticks * scale / 1_000_000_000.0
        # A file that was cut short can carry a duration that was never
        # filled in. Such a number is not a fact about the file, so it is
        # left out rather than reported.
        if 0.0 < seconds <= 24.0 * 3600.0:
            found["duration"] = seconds
    return found


# The adapters that can measure the sound of a video. The default one uses
# the tools of the machine. A local sound model can be added later by
# putting it in this list, and the rest of the pipeline needs no change.
_AUDIO_ADAPTERS: list[Any] = []


def register_audio_adapter(adapter: Any) -> None:
    """Add an adapter that measures the sound of a media file.

    An adapter is a callable that takes the path of a media file and
    returns a dictionary of measurements, or ``None`` when it could not
    measure the file. This is the seam where a local sound model goes,
    so the pipeline never has to be rewritten to add one.
    """
    if adapter is None:
        return
    _AUDIO_ADAPTERS.append(adapter)


def measure_audio(media_path: str) -> dict[str, Any] | None:
    """Measure the audio of a media file, when the machine can.

    The measurement needs the media file itself. The caller only calls
    this for a media file that is already on the machine under a name the
    platform gave it and that the rights check already allowed. Nothing
    is downloaded here.

    The container of the file is read first, because the codec, the
    sample rate and the number of channels are facts that need no tool.
    A sound tool then adds the loudness of the track, which needs a
    decoder. The result says which of the two were measured, so the
    analyzer never claims to have heard a track it could not decode.
    """
    for adapter in _AUDIO_ADAPTERS:
        try:
            measured = adapter(media_path)
        except Exception:
            measured = None
        if measured:
            return measured

    container = read_container(media_path)
    with_tools = measure_audio_with_tools(media_path)
    if with_tools:
        # The tool measured the track, so its facts win over the header.
        if container:
            for key in ("codec", "sample_rate", "channels", "duration"):
                if not with_tools.get(key) and container.get(key):
                    with_tools[key] = container[key]
        with_tools["source"] = "ffmpeg"
        return with_tools
    if container:
        # The header was read but the track was not decoded, so the sound
        # itself is still unknown.
        container["source"] = "container"
        container["decoded"] = False
        return container
    return None


def measure_audio_with_tools(media_path: str) -> dict[str, Any] | None:
    """Measure the audio of a media file with the tools of the machine.

    The track is really decoded here, so every number in the result is a
    measurement of the sound and not an assumption. The tool reports the
    facts of the stream, and the decoded signal gives the loudness, the
    rhythm, the movement of the energy, the loudest passages and the
    shape of the sound.
    """
    tools = _tool_paths()
    ffprobe = tools.get("ffprobe")
    ffmpeg = tools.get("ffmpeg")
    if not ffprobe or not ffmpeg:
        return None
    path = str(media_path or "").strip()
    if not path or not os.path.isfile(path):
        return None
    try:
        result = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=codec_name,sample_rate,channels,bit_rate:format=duration",
                "-of",
                "json",
                path,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            return None
        import json

        payload = json.loads(result.stdout or "{}")
    except Exception:
        return None

    streams = payload.get("streams") or []
    if not streams:
        return {"has_audio": False, "decoded": False}
    stream = streams[0]
    duration = 0.0
    try:
        duration = float((payload.get("format") or {}).get("duration") or 0.0)
    except (TypeError, ValueError):
        duration = 0.0

    measured: dict[str, Any] = {
        "has_audio": True,
        "codec": str(stream.get("codec_name", "")),
        "sample_rate": int(stream.get("sample_rate") or 0),
        "channels": int(stream.get("channels") or 0),
        "bit_rate": int(stream.get("bit_rate") or 0),
        "duration": duration,
        "decoded": False,
    }

    # The loudness of the track is measured on the machine, so the audio
    # really is heard and not assumed.
    loudness = None
    peak = None
    try:
        detected = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-nostats",
                "-i",
                path,
                "-af",
                "volumedetect",
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        for line in (detected.stderr or "").splitlines():
            if "mean_volume:" in line:
                loudness = float(line.split("mean_volume:")[1].split("dB")[0].strip())
            elif "max_volume:" in line:
                peak = float(line.split("max_volume:")[1].split("dB")[0].strip())
    except Exception:
        loudness = None
    measured["mean_volume_db"] = loudness
    measured["peak_volume_db"] = peak

    # The signal itself is decoded, so the rhythm and the movement of the
    # energy are measured from the samples and not guessed.
    features = analyze_signal(path, ffmpeg)
    if features:
        measured.update(features)
        measured["decoded"] = True
    return measured


# The rate the signal is decoded at. It is high enough to keep the
# rhythm of a track and low enough to keep the decoding quick.
_ANALYSIS_RATE = 22050


def decode_signal(media_path: str, ffmpeg: str = "") -> Any:
    """Decode the audio of a media file into a mono signal.

    The sound is decoded at a fixed rate and reduced to one channel, so
    the measurement of the rhythm and of the energy does not depend on
    the codec of the file. ``None`` is returned when the track cannot be
    decoded.
    """
    import numpy as np

    tool = ffmpeg or (_tool_paths().get("ffmpeg") or "")
    if not tool:
        return None
    path = str(media_path or "").strip()
    if not path or not os.path.isfile(path):
        return None
    try:
        result = subprocess.run(
            [
                tool,
                "-hide_banner",
                "-nostats",
                "-loglevel",
                "error",
                "-i",
                path,
                "-vn",
                "-ac",
                "1",
                "-ar",
                str(_ANALYSIS_RATE),
                "-f",
                "s16le",
                "-",
            ],
            capture_output=True,
            timeout=180,
        )
    except Exception:
        return None
    if result.returncode != 0 or not result.stdout:
        return None
    try:
        samples = np.frombuffer(result.stdout, dtype="<i2").astype(np.float32)
    except Exception:
        return None
    if samples.size < _ANALYSIS_RATE // 10:
        # Less than a tenth of a second carries nothing to measure.
        return None
    # The samples are scaled to the range of minus one to one.
    return samples / 32768.0


def analyze_signal(media_path: str, ffmpeg: str = "") -> dict[str, Any] | None:
    """Measure the real features of the sound of a media file.

    The measurements are the ones the machine can really make from the
    samples: the loudness, the peak, the rhythm, the movement of the
    energy, the loudest passages and the shape of the sound. Nothing
    here names a genre, a mood or a trend, because no model on this
    machine can do that honestly.
    """
    import numpy as np

    samples = decode_signal(media_path, ffmpeg)
    if samples is None:
        return None

    rate = float(_ANALYSIS_RATE)
    duration = float(samples.size) / rate

    # ---- the loudness and the peak, measured from the samples ---------
    rms = float(np.sqrt(np.mean(samples**2)))
    peak = float(np.max(np.abs(samples)))
    mean_db = 20.0 * math.log10(rms) if rms > 1e-6 else -120.0
    peak_db = 20.0 * math.log10(peak) if peak > 1e-6 else -120.0

    # ---- the movement of the energy, over short windows ---------------
    window = max(1, int(rate * 0.05))  # fifty milliseconds
    count = samples.size // window
    if count < 4:
        return None
    frames = samples[: count * window].reshape(count, window)
    frame_rms = np.sqrt(np.mean(frames**2, axis=1))

    # The crest factor tells how much the loudest moments stand out from
    # the average. A track that is compressed all the time has a low one.
    crest = float(peak_db - mean_db) if mean_db > -119.0 else 0.0

    # The variation of the energy over the track. The spread is measured
    # on the frames that carry sound, because the frames of a pause are
    # silent and would make the number of every track meaningless.
    energy_mean = float(frame_rms.mean())
    sounding = frame_rms[frame_rms > (energy_mean * 0.05 if energy_mean > 1e-6 else 0.0)]
    if sounding.size >= 2 and float(sounding.mean()) > 1e-6:
        loud_db = 20.0 * np.log10(np.maximum(sounding, 1e-9))
        dynamics_db = float(loud_db.std())
    else:
        dynamics_db = 0.0

    # The share of the track that is close to silence. The threshold is
    # taken from the level of the sound, so a track that is quiet all the
    # way through is not counted as a track of silence.
    sounding_level = float(sounding.mean()) if sounding.size else 0.0
    threshold = sounding_level * 0.1 if sounding_level > 1e-6 else 0.0
    silence_ratio = float((frame_rms < threshold).mean())

    # ---- the loudest passages ------------------------------------------
    # The windows that are the loudest, and how long they last.
    loudest = np.sort(frame_rms)[-max(1, len(frame_rms) // 10):]
    loud_mean = float(loudest.mean())
    peak_ratio = float(loud_mean / energy_mean) if energy_mean > 1e-6 else 1.0

    # The longest stretch of the track that stays loud. The threshold is
    # taken from the level of the sound, so a quiet track still has a
    # loud part to find.
    loud_mask = frame_rms > (sounding_level * 1.5 if sounding_level > 1e-6 else 0.0)
    longest_loud = 0
    current = 0
    for flag in loud_mask:
        current = current + 1 if flag else 0
        longest_loud = max(longest_loud, current)
    longest_loud_seconds = longest_loud * window / rate

    # ---- the rhythm ---------------------------------------------------
    # The beat is found by the energy of the signal itself: the moments
    # where the loudness rises fastest. The rate is counted from the
    # spacing of those moments.
    tempo_bpm = _estimate_tempo(frame_rms, rate, window)

    # ---- the shape of the sound ---------------------------------------
    # The share of the energy that sits in the low, the middle and the
    # high band, measured with the spectrum of the signal.
    bands = _band_energies(samples, rate)

    return {
        "decoded": True,
        "duration": duration,
        "mean_volume_db": mean_db,
        "peak_volume_db": peak_db,
        "crest_db": crest,
        "dynamics_db": dynamics_db,
        "silence_ratio": silence_ratio,
        "energy_ratio": peak_ratio,
        "longest_loud_seconds": longest_loud_seconds,
        "tempo_bpm": tempo_bpm,
        "tempo_confidence": _tempo_confidence(frame_rms, rate, window),
        "bands": bands,
        "sample_count": int(samples.size),
    }


def _estimate_tempo(frame_rms: Any, rate: float, window: int) -> float:
    """Return the rhythm of the track in beats per minute.

    The beat is found by the energy of the signal: the moments where the
    loudness rises fastest. The rate is counted from the spacing of
    those moments. The measure tells how fast the beat is; it does not
    say what the music is.
    """
    import numpy as np

    energy = np.asarray(frame_rms, dtype=np.float32)
    if energy.size < 8:
        return 0.0

    # The energy of each moment, with the slow part removed, so the
    # steady beat stands out from the slow movement of the track.
    slow = np.convolve(
        energy, np.ones(max(1, len(energy) // 8), dtype=np.float32) / max(1, len(energy) // 8), mode="same"
    )
    onset = np.diff(energy - slow)
    onset[onset < 0] = 0.0
    if float(onset.max()) <= 1e-9:
        return 0.0

    # The moments where the energy rises the most.
    threshold = float(onset.mean()) + float(onset.std())
    peaks: list[int] = []
    for index in range(1, onset.size - 1):
        value = onset[index]
        if value > threshold and value >= onset[index - 1] and value >= onset[index + 1]:
            if not peaks or index - peaks[-1] > 2:
                peaks.append(index)
    if len(peaks) < 4:
        return 0.0

    # The spacing between the beats gives the rate.
    gaps = np.diff(np.asarray(peaks, dtype=np.float32)) * window / rate
    gaps = gaps[(gaps > 0.20) & (gaps < 2.0)]
    if gaps.size < 3:
        return 0.0
    # The middle of the gaps is the most usual one, so a single odd
    # beat does not move the answer.
    bpm = 60.0 / float(np.median(gaps))
    # Only the rates a person would tap are reported.
    while bpm < 60.0:
        bpm *= 2.0
    while bpm > 200.0:
        bpm /= 2.0
    return round(bpm, 1)


def _tempo_confidence(frame_rms: Any, rate: float, window: int) -> float:
    """Return how sure the machine is about the rhythm it measured.

    The measure is the share of the beats that land on the same spacing.
    A track with a clear beat gives a high number, and a track of
    speech or noise gives a low one.
    """
    import numpy as np

    energy = np.asarray(frame_rms, dtype=np.float32)
    if energy.size < 16:
        return 0.0
    slow = np.convolve(
        energy, np.ones(max(1, len(energy) // 8), dtype=np.float32) / max(1, len(energy) // 8), mode="same"
    )
    onset = np.diff(energy - slow)
    onset[onset < 0] = 0.0
    if float(onset.max()) <= 1e-9:
        return 0.0
    threshold = float(onset.mean()) + float(onset.std())
    peaks: list[int] = []
    for index in range(1, onset.size - 1):
        value = onset[index]
        if value > threshold and value >= onset[index - 1] and value >= onset[index + 1]:
            if not peaks or index - peaks[-1] > 2:
                peaks.append(index)
    if len(peaks) < 4:
        return 0.0
    gaps = np.diff(np.asarray(peaks, dtype=np.float32)) * window / rate
    gaps = gaps[(gaps > 0.20) & (gaps < 2.0)]
    if gaps.size < 3:
        return 0.0
    # The share of the gaps that sit close to the middle one.
    middle = float(np.median(gaps))
    close = float((np.abs(gaps - middle) <= middle * 0.15).mean())
    return round(min(1.0, close), 3)


def _band_energies(samples: Any, rate: float) -> dict[str, float]:
    """Return the share of the energy in the low, middle and high band.

    The bands tell the shape of the sound: a track with a strong low
    band has a heavy bass, and one with a strong high band is bright.
    They do not name a genre.
    """
    import numpy as np

    size = min(samples.size, int(rate * 30))
    if size < 1024:
        return {}
    piece = samples[:size]
    try:
        spectrum = np.abs(np.fft.rfft(piece))
        frequencies = np.fft.rfftfreq(size, 1.0 / rate)
        total = float(spectrum.sum())
        if total <= 1e-9:
            return {}
        low = float(spectrum[(frequencies >= 20) & (frequencies < 250)].sum())
        middle = float(spectrum[(frequencies >= 250) & (frequencies < 4000)].sum())
        high = float(spectrum[frequencies >= 4000].sum())
        return {
            "low": round(low / total, 3),
            "middle": round(middle / total, 3),
            "high": round(high / total, 3),
        }
    except Exception:
        return {}


# --------------------------------------------------------------------------
# The local judgement of one candidate.
# --------------------------------------------------------------------------

# The words on a frame that show an AI music tool, a music production
# screen, or a synthetic picture. The analyzer looks for these shapes in
# the pixels of the frame, so a caption keyword is never the evidence.
_TOOL_SIGNATURES = (
    "suno",
    "udio",
    "booga",
    "stable audio",
    "aiff",
    "mubert",
    "loudly",
    "piano",
    "diffusion",
    "stable diffusion",
    "midjourney",
    "runway",
    "leonardo",
    "dall",
    "sora",
    "kling",
    "luma",
    "pika",
    "suno v",
    "ai music",
    "ai song",
)

# The shapes that show a music production interface: rows of waveforms,
# grids of pads, timelines with many coloured blocks.
def _waveform_likeness(picture: Any) -> float:
    """Return how much the frame looks like a waveform or a timeline.

    The measure is the share of the pixels that sit on a strong
    horizontal edge, which is what a waveform and a timeline are made
    of. A talking video and a car video do not have that structure.
    """
    import numpy as np

    try:
        dx = np.abs(np.diff(picture, axis=1))
    except Exception:
        return 0.0
    if dx.size == 0:
        return 0.0
    strong = float((dx > 18).mean())
    return min(1.0, strong * 6.0)


def _text_like_score(picture: Any) -> float:
    """Return how much the frame carries text-like structure.

    Text is many short dark strokes on a flat ground. The measure is the
    share of the pixels that sit on a strong horizontal edge, in a frame
    that is otherwise flat.
    """
    import numpy as np

    try:
        gray = (
            0.299 * picture[:, :, 0]
            + 0.587 * picture[:, :, 1]
            + 0.114 * picture[:, :, 2]
        )
        dy = np.abs(np.diff(gray, axis=0))
    except Exception:
        return 0.0
    if dy.size == 0:
        return 0.0
    return min(1.0, float((dy > 16).mean()) * 5.0)


def _looks_synthetic(features: dict[str, float]) -> tuple[float, str]:
    """Return how much the picture looks AI-made, and the reason.

    The signs of a synthetic picture are read from the real pixels: a very
    smooth gradient with few strong edges, an unusual number of distinct
    colours, and a flat saturation across the whole frame. The measure
    says how much the picture is consistent with a synthetic picture; it
    does not prove it.
    """
    if not features:
        return 0.0, INSUFFICIENT_DATA

    edges = features.get("edges", 0.0)
    distinct = features.get("distinct_colours", 0.0)
    saturation = features.get("saturation", 0.0)
    contrast = features.get("contrast", 0.0)

    # A rendered picture has smooth areas and few hard edges.
    smoothness = 0.0
    if edges < 14.0:
        smoothness = min(1.0, (14.0 - edges) / 14.0)
    # A rendered picture holds many distinct colours after quantisation.
    richness = 0.0
    if distinct > 300:
        richness = min(1.0, (distinct - 300) / 2200.0)
    # A rendered picture is often very even in colour. A picture that is
    # grey or dark is not a sign of a generated image.
    evenness = 0.0
    if saturation > 45 and saturation < 140:
        evenness = 0.6
    elif saturation > 25:
        evenness = 0.25

    score = (smoothness * 0.45) + (richness * 0.35) + (evenness * 0.20)
    # A picture with no contrast at all is not evidence of anything.
    if contrast < 6.0:
        return 0.0, "hình ảnh quá phẳng để đọc được đặc trưng"
    # A picture that is nearly grey is not a sign of a generated image on
    # its own. Without colour, the smoothness alone is too weak.
    if saturation < 18.0:
        score *= 0.35
    reason = (
        f"vùng ảnh mượt {smoothness:.0%}, "
        f"{int(distinct)} màu sau lượng tử hoá, độ bão hoà {saturation:.0f}"
    )
    return max(0.0, min(1.0, score)), reason


def _topic_from_caption(caption: str) -> tuple[float, str]:
    """Return how strongly the caption names the AI music market.

    The caption is only a weak hint here. It is never enough on its own
    to accept a video, and the reason says so.
    """
    text = str(caption or "").lower()
    if not text:
        return 0.0, "caption không có nội dung"
    strong = (
        "ai music", "aimusic", "ai song", "aisong", "ai cover", "aicover",
        "ai remix", "airemix", "ai beat", "aibeat", "ai instrumental",
        "suno", "udio", "booga", "ai generated music", "nhạc ai",
        "bài hát ai", "ai tạo nhạc", "ai melody", "voice clone",
    )
    hits = [word for word in strong if word in text]
    if hits:
        return 1.0, "caption có nhắc " + ", ".join(hits[:3])
    return 0.0, "caption không nhắc tới công cụ hoặc dạng nhạc AI"


def _channel_fit_from_caption(caption: str, creator: str) -> tuple[float, str]:
    """Return how well the candidate fits a channel that publishes music."""
    text = f"{caption} {creator}".lower()
    music_words = (
        "music", "song", "nhạc", "bài hát", "cover", "remix", "beat",
        "sound", "audio", "instrumental", "mashup", "lofi", "edm",
        "cinematic", "singer", "vocal",
    )
    hits = [word for word in music_words if word in text]
    if hits:
        return 1.0, "tên/caption có " + ", ".join(hits[:3])
    return 0.0, "tên và caption không cho thấy nội dung nhạc"


def _engagement_from_metrics(
    views: int, likes: int, comments: int, shares: int, metrics_known: bool
) -> tuple[float, str]:
    """Return the virality signal of the published metrics.

    The metrics are a real fact about the platform, but they never decide
    whether the content fits the topic. The engagement rate is what the
    signal is built on, because a high view count on its own says little.
    """
    if not metrics_known or views <= 0:
        return 0.0, "không có số liệu tương tác đã công bố"
    total = max(0, likes) + max(0, comments) + max(0, shares)
    rate = total / float(views)
    # A rate of 10% is a strong signal; 1% is weak.
    score = max(0.0, min(1.0, math.log10(max(rate, 0.001) * 100 + 1) / 1.6))
    return score, f"tỉ lệ tương tác {rate:.2%} trên {views:,} lượt xem"


def analyze_locally(
    frames: list[bytes],
    metadata: dict[str, Any],
    *,
    audio: dict[str, Any] | None = None,
    media_path: str = "",
) -> LocalAnalysis:
    """Judge a candidate on this machine, from its real frames.

    The frames are the ones the discovery already read and cached. The
    metadata carries the real published facts. The result says how sure
    the analyzer is about every dimension, so a dimension that cannot be
    decided is never given a guessed score.

    When a media file is already on the machine, its path is given in
    ``media_path``, and the sound is really measured from that file. When
    no media file is given, the sound stays not enough data; it is never
    guessed from the caption.
    """
    caption = str(metadata.get("title") or metadata.get("desc") or "")
    creator = str(metadata.get("creator") or "")
    source_url = str(metadata.get("source_url") or "")

    result = LocalAnalysis(
        source_url=source_url, creator=creator, title=caption,
        tools=available_tools(),
    )
    result.frame_count = len(frames)
    # The machine is told what it is missing to measure the sound, so the
    # reason for an unknown sound is never a mystery.
    result.audio_dependency_missing = missing_audio_dependency()

    # ---- the local vision analyzer -------------------------------------
    # The picture is read on this machine. A vision model reads what it
    # really sees, and the pixels give the movement and the pull of the
    # opening. The two are kept apart, so a reading is never mixed with
    # a measurement.
    # A model that sits on the machine is picked up the first time.
    vision_model_path()
    result.vision = analyze_vision(frames)

    if audio is None and media_path:
        audio = measure_audio(media_path)

    if not frames:
        # Nothing to judge. Every dimension stays empty and the candidate
        # is reported as not enough data.
        for key in _FINDING_KEYS:
            result.findings[key] = Finding(
                key=key, points=0.0, maximum=_FINDING_MAX[key],
                certainty=NO_DATA, reason="không có khung hình nào được đọc",
            )
        result.summary = "Không đọc được khung hình nào của video."
        result.content_relevance_reason = "không có khung hình để đánh giá nội dung"
        return result

    features = _average_features(frames)

    if not features:
        for key in _FINDING_KEYS:
            result.findings[key] = Finding(
                key=key, points=0.0, maximum=_FINDING_MAX[key],
                certainty=NO_DATA, reason="không đọc được ảnh của khung hình",
            )
        result.summary = "Khung hình đọc được nhưng không phân tích được."
        result.content_relevance_reason = "không phân tích được khung hình"
        return result

    # ---- topic fit: is the content really AI music? --------------------
    caption_score, caption_reason = _topic_from_caption(caption)
    synthetic_score, synthetic_reason = _looks_synthetic(features)
    waveform = 0.0
    text_like = 0.0
    try:
        import io

        import numpy as np
        from PIL import Image

        pictures = []
        for frame in frames:
            try:
                with Image.open(io.BytesIO(frame)) as image:
                    pictures.append(
                        np.asarray(image.convert("RGB"), dtype=np.float32)
                    )
            except Exception:
                continue
        if pictures:
            waveform = max(_waveform_likeness(p) for p in pictures)
            text_like = max(_text_like_score(p) for p in pictures)
    except Exception:
        pass

    # The three ways the frames can show AI music content.
    caption_signal = caption_score * 0.30
    synthetic_signal = synthetic_score * 0.40
    # A frame that carries the structure of a music production screen: a
    # waveform, a timeline, a text panel. This is the strongest sign,
    # because it is a picture of the tool itself and not of the result.
    # The waveform carries most of the weight, because a waveform is the
    # one structure that only a music editor shows.
    production_signal = waveform * 0.82 + text_like * 0.18

    # The measure of the screen of a music tool, taken by the vision
    # analyzer on the same real frames. It looks for the shape of a
    # waveform, of a timeline and of the panels of a music editor.
    ui_measure = result.vision.production_ui if result.vision else {}
    ui_score = float((ui_measure or {}).get("score") or 0.0)

    topic_signal = max(
        caption_signal,
        max(synthetic_signal, production_signal),
        ui_score * 0.75,
    )

    # ---- what the local vision model really saw ------------------------
    # A vision model that really looked at the picture is stronger
    # evidence than a measurement of the pixels. The model and the
    # pixels are kept apart, so it is always clear which one decided.
    vision = result.vision
    vision_reading = vision.reading if vision else None
    model_used = bool(vision and vision.model_used)
    model_ai_music = False
    model_saw_music = False
    model_reason = ""
    if model_used and vision_reading is not None:
        # The model says what it saw. The words of the model and of the
        # things it saw are what decide whether the picture is about
        # music made with a machine.
        words = " ".join(
            [vision_reading.scene]
            + [item.label for item in vision_reading.objects]
            + list(vision_reading.text)
        ).lower()
        music_words = (
            "music", "song", "audio", "waveform", "synth", "instrument",
            "piano", "drum", "beat", "mix", "track", "studio", "singer",
            "voice", "producer", "sequencer", "melody",
        )
        ai_words = (
            "ai", "suno", "udio", "artificial", "generated", "generative",
            "neural", "diffusion", "prompt", "model",
        )
        # The words are looked for as whole words, so a word that only
        # carries the letters of another one is not a sign.
        tokens = set(
            token.strip(".,:;!?()[]{}'\"-_/\\").lower()
            for token in words.replace("/", " ").replace("-", " ").split()
        )
        model_saw_music = any(word in tokens for word in music_words)
        model_saw_ai = any(word in tokens for word in ai_words)
        model_reason = (
            f"mô hình vision {vision_reading.model or 'cục bộ'} đọc: "
            f"{vision_reading.scene or 'không mô tả'}"
            + (
                f"; thấy {', '.join(item.label for item in vision_reading.objects[:4])}"
                if vision_reading.objects
                else ""
            )
        )
        if vision_reading.text:
            model_reason += f"; chữ đọc được: {', '.join(vision_reading.text[:3])}"
        # The frame the reading came from travels with it, so the admin
        # can look at the frame the model was sure about.
        model_reason += (
            f" (khung {vision_reading.frame_index + 1}/{max(1, vision_reading.frames_read)})"
        )

        # A model that only knows how to name what is in a picture proves
        # that the thing is in the picture. It does not prove that the
        # video was made with a machine. Only a model that was trained
        # to tell how the content was made can settle that, and even
        # then the reading is a possibility, not proof.
        if vision_reading.can_tell_ai_origin:
            model_ai_music = model_saw_music and model_saw_ai
        else:
            # The model named what it saw. When music is among the
            # names, that is evidence that music is in the picture, and
            # a sign that the content is about music. It says nothing
            # about how the music was made.
            model_ai_music = False
            if model_saw_music:
                model_reason += (
                    " — mô hình chỉ đặt tên được nội dung, chưa chứng minh "
                    "được nội dung đó do AI tạo ra"
                )

    # The picture has to show something before a caption can support it.
    if topic_signal <= 0.15 and not model_used:
        topic_certainty = UNDETERMINED
        topic_points = 0.0
        topic_reason = (
            "khung hình không cho thấy dấu hiệu nào của nội dung nhạc AI; "
            + caption_reason
        )
    elif model_used and model_ai_music:
        # A model that was trained to tell how the content was made
        # really looked at the picture and really saw music made with a
        # machine. That is the strongest evidence this machine can get.
        topic_certainty = EVIDENCE
        topic_points = _FINDING_MAX["topic_fit"] * min(
            1.0, 0.65 + float(vision_reading.confidence or 0.0) * 0.35
        )
        topic_reason = model_reason
    elif model_used and model_saw_music:
        # The model named what it saw and music was among the names. The
        # picture really does show music, and that is evidence of the
        # subject. It says nothing about how the music was made, so the
        # content is not decided and the dimension stays a possibility.
        topic_certainty = POSSIBILITY
        topic_points = _FINDING_MAX["topic_fit"] * min(
            1.0, 0.30 + float(vision_reading.confidence or 0.0) * 0.25
        )
        topic_reason = model_reason
    elif model_used:
        # The model read the picture, and it did not show AI music. The
        # picture was really looked at, so the reading stands and the
        # dimension keeps no points.
        topic_certainty = EVIDENCE
        topic_points = 0.0
        topic_reason = (
            model_reason
            + " — mô hình không thấy nội dung nhạc AI trong hình"
        )
    elif production_signal >= 0.52:
        # The frames show a music production screen. That is a picture of
        # the tool, so it is evidence and not only a possibility.
        topic_certainty = EVIDENCE
        topic_points = _FINDING_MAX["topic_fit"] * min(1.0, 0.60 + production_signal * 0.40)
        topic_reason = (
            f"khung hình có giao diện sản xuất nhạc "
            f"(waveform {waveform:.0%}, chữ {text_like:.0%})"
        )
    elif synthetic_signal >= 0.45:
        # The picture itself has the look of a generated image.
        topic_certainty = EVIDENCE
        topic_points = _FINDING_MAX["topic_fit"] * min(1.0, 0.45 + synthetic_signal * 0.55)
        topic_reason = f"khung hình có đặc trưng ảnh tạo bằng máy ({synthetic_reason})"
    elif ui_score >= 0.45:
        # The frames carry the shape of a music tool: a waveform and the
        # panels of an editor. That is a picture of the tool, so it is
        # evidence and not only a possibility.
        topic_certainty = EVIDENCE
        topic_points = _FINDING_MAX["topic_fit"] * min(1.0, 0.55 + ui_score * 0.45)
        topic_reason = (
            f"khung hình có giao diện sản xuất nhạc "
            f"(waveform {float((ui_measure or {}).get('waveform') or 0):.0%}, "
            f"dải thời gian {float((ui_measure or {}).get('timeline') or 0):.0%}, "
            f"bảng {float((ui_measure or {}).get('panels') or 0):.0%})"
        )
    elif topic_signal >= 0.45:
        # The frames are consistent with AI content but do not prove it.
        topic_certainty = POSSIBILITY
        topic_points = _FINDING_MAX["topic_fit"] * min(1.0, topic_signal * 0.85)
        topic_reason = (
            f"khung hình nhất quán với nội dung AI nhưng chưa đủ bằng chứng "
            f"(waveform {waveform:.0%}, chữ {text_like:.0%}, ảnh tạo máy {synthetic_score:.0%}"
            + (f", giao diện sản xuất {ui_score:.0%}" if ui_score >= 0.2 else "")
            + ")"
        )
    else:
        topic_certainty = POSSIBILITY
        topic_points = _FINDING_MAX["topic_fit"] * min(1.0, topic_signal)
        topic_reason = (
            f"khung hình cho dấu hiệu yếu về nội dung AI ({caption_reason})"
        )

    result.findings["topic_fit"] = Finding(
        key="topic_fit",
        points=topic_points,
        maximum=_FINDING_MAX["topic_fit"],
        certainty=topic_certainty,
        reason=topic_reason,
    )

    # ---- visual quality ------------------------------------------------
    visual_score = _visual_quality(features)
    visual_certainty = EVIDENCE if features else NO_DATA
    result.findings["visual_quality"] = Finding(
        key="visual_quality",
        points=visual_score,
        maximum=_FINDING_MAX["visual_quality"],
        certainty=visual_certainty,
        reason=(
            f"độ nét {features.get('edges', 0):.0f}, "
            f"tương phản {features.get('contrast', 0):.0f}, "
            f"bão hoà {features.get('saturation', 0):.0f}, "
            f"{features.get('width', 0):.0f}x{features.get('height', 0):.0f}"
        ),
    )

    # ---- music quality: only when the audio could really be read ------
    music_finding = _music_quality(audio)
    result.findings["music_quality"] = music_finding

    # ---- hook: the pull of the first frame -----------------------------
    hook_finding = _hook_quality(frames, features)
    result.findings["hook_retention"] = hook_finding

    # ---- engagement and trend: the published metrics -------------------
    engagement_score, engagement_reason = _engagement_from_metrics(
        int(metadata.get("views") or 0),
        int(metadata.get("likes") or 0),
        int(metadata.get("comments") or 0),
        int(metadata.get("shares") or 0),
        bool(metadata.get("metrics_known", False)),
    )
    result.findings["engagement_virality"] = Finding(
        key="engagement_virality",
        points=engagement_score,
        maximum=_FINDING_MAX["engagement_virality"],
        certainty=EVIDENCE if engagement_reason.startswith("tỉ lệ") else UNDETERMINED,
        reason=engagement_reason,
    )

    # ---- channel fit ---------------------------------------------------
    channel_score, channel_reason = _channel_fit_from_caption(caption, creator)
    result.findings["channel_fit"] = Finding(
        key="channel_fit",
        points=channel_score * _FINDING_MAX["channel_fit"],
        maximum=_FINDING_MAX["channel_fit"],
        certainty=POSSIBILITY,
        reason=channel_reason + " (tên và caption là dấu hiệu yếu, không phải bằng chứng)",
    )

    # ---- the verdict ----------------------------------------------------
    # A vision model that really looked at the picture decides on its
    # own. A model that was trained to tell how the content was made
    # settles the question. A model that only names what is in the
    # picture proves the subject, but never the origin, so it leaves the
    # question open. Without a model, the older signals decide as they
    # did before.
    if model_used and model_ai_music:
        result.content_is_ai_music = True
        result.content_ai_visual = synthetic_score >= 0.4
        result.content_relevance_reason = topic_reason
    elif model_used and model_saw_music:
        # The picture really shows music, but nothing says how the music
        # was made. The question stays open, so the candidate is not
        # accepted and not rejected.
        result.content_is_ai_music = None
        result.content_ai_visual = None
        result.content_relevance_reason = (
            topic_reason
            + " — mô hình thấy nội dung nhạc nhưng chưa chứng minh được "
            "nội dung đó do AI tạo ra, máy chưa đủ bằng chứng để kết luận"
        )
    elif model_used:
        # The model read the picture and did not show AI music at all.
        result.content_is_ai_music = False
        result.content_ai_visual = False
        result.content_relevance_reason = (
            topic_reason
            + " — mô hình vision đã đọc hình và không thấy nội dung nhạc AI, "
            "video bị loại"
        )
    elif topic_certainty == EVIDENCE:
        result.content_is_ai_music = True
        result.content_ai_visual = synthetic_score >= 0.4
        result.content_relevance_reason = topic_reason
    elif topic_certainty == POSSIBILITY:
        result.content_is_ai_music = None
        result.content_ai_visual = None
        result.content_relevance_reason = (
            topic_reason + " — máy chưa đủ bằng chứng để kết luận có phải AI Music hay không"
        )
    else:
        result.content_is_ai_music = False
        result.content_ai_visual = False
        result.content_relevance_reason = (
            topic_reason
            + " — khung hình không cho thấy nội dung nhạc AI, video bị loại"
        )

    result.summary = _describe(features, synthetic_score, waveform, text_like)
    if result.vision is not None:
        # The vision reading is added to the summary, so the admin sees
        # what was really seen apart from what was measured.
        vision_text = describe_vision(result.vision)
        if vision_text:
            result.summary = f"{result.summary}. {vision_text}"
    result.rankable = _has_enough_data(result)
    return result


def _visual_quality(features: dict[str, float]) -> float:
    """Score the production quality of the picture from the real pixels."""
    if not features:
        return 0.0
    edges = features.get("edges", 0.0)
    contrast = features.get("contrast", 0.0)
    saturation = features.get("saturation", 0.0)
    width = features.get("width", 0.0)
    height = features.get("height", 0.0)
    blown = features.get("blown_ratio", 0.0)
    dark = features.get("dark_ratio", 0.0)

    # Sharpness: a picture with detail and edges is a produced picture.
    sharpness = min(1.0, edges / 28.0)
    # Contrast: a flat picture carries nothing.
    depth = min(1.0, contrast / 70.0)
    # Colour: a grey picture is dull.
    colour = min(1.0, saturation / 90.0)
    # Resolution: a small picture cannot carry much.
    resolution = min(1.0, (width * height) / (720.0 * 1280.0))
    # A picture that is mostly black or blown out is not usable.
    penalty = min(1.0, (dark + blown) * 2.0)

    score = (
        sharpness * 0.30 + depth * 0.25 + colour * 0.20 + resolution * 0.25
    ) * (1.0 - penalty * 0.6)
    return max(0.0, min(1.0, score)) * _FINDING_MAX["visual_quality"]


def _music_quality(audio: dict[str, Any] | None) -> Finding:
    """Score the sound of the video, when the machine really heard it.

    The score is built from the measurements the machine really made:
    the length of the track, the loudness, the peak, the movement of the
    energy, the rhythm and the shape of the sound.

    Nothing here names a genre, a mood, a lyric or a trend, because no
    model on this machine can decide those honestly. The measure says
    what was measured and how sure the machine is about it.

    When the track could not be decoded, the finding stays not enough
    data. The facts that the container carries are still reported, because
    they are real facts about the file, but they are not turned into a
    score of the sound itself. The sound is never guessed from the
    caption.
    """
    maximum = _FINDING_MAX["music_quality"]
    if not audio or not audio.get("has_audio"):
        # The reason always names the cause, so the admin knows whether the
        # tool is missing or the video really carries no sound.
        gap = missing_audio_dependency()
        if gap:
            cause = gap
        else:
            cause = (
                "video không có dấu vết âm thanh, "
                "dù ffprobe/ffmpeg đã có và đã đọc file"
            )
        return Finding(
            key="music_quality",
            points=0.0,
            maximum=maximum,
            certainty=NO_DATA,
            reason="không đọc được âm thanh: " + cause,
        )

    duration = float(audio.get("duration") or 0.0)
    loudness = audio.get("mean_volume_db")
    peak = audio.get("peak_volume_db")
    sample_rate = int(audio.get("sample_rate") or 0)
    bit_rate = int(audio.get("bit_rate") or 0)
    decoded = audio.get("decoded", True)

    if not decoded:
        # The header was read but the track was never decoded, so the
        # quality of the sound is still unknown. The facts that were read
        # are kept, and the dimension keeps no points.
        facts = []
        if audio.get("codec"):
            facts.append(f"mã {audio['codec']}")
        if sample_rate:
            facts.append(f"{sample_rate}Hz")
        if channels := int(audio.get("channels") or 0):
            facts.append(f"{channels} kênh")
        if duration > 0:
            facts.append(f"{duration:.1f}s")
        return Finding(
            key="music_quality",
            points=0.0,
            maximum=maximum,
            certainty=NO_DATA,
            reason=(
                "đọc được thông tin file nhưng chưa giải mã được âm thanh "
                f"({', '.join(facts) if facts else 'không rõ'})"
            ),
        )

    # A track that carries no sound at all has no quality to judge. It
    # is reported as no data, not as a track that scored badly.
    if loudness is not None and float(loudness) <= -90.0:
        return Finding(
            key="music_quality",
            points=0.0,
            maximum=maximum,
            certainty=NO_DATA,
            reason=(
                f"vùng âm thanh của video không có tiếng "
                f"(mức {float(loudness):.0f}dB)"
            ),
        )

    score = 0.0
    parts: list[str] = []

    # ---- the length of the track ---------------------------------------
    if duration > 0:
        # A clip of a few seconds to a few minutes is the useful length.
        if 3.0 <= duration <= 180.0:
            score += 0.20
            parts.append(f"thời lượng {duration:.1f}s")
        else:
            parts.append(f"thời lượng {duration:.1f}s không phù hợp")

    # ---- the loudness and the peak --------------------------------------
    if loudness is not None:
        try:
            value = float(loudness)
            if -24.0 <= value <= -6.0:
                score += 0.20
                parts.append(f"mức âm {value:.0f}dB hợp lý")
            elif value > -6.0:
                score += 0.10
                parts.append(f"mức âm {value:.0f}dB khá lớn")
            else:
                parts.append(f"mức âm {value:.0f}dB nhỏ")
        except (TypeError, ValueError):
            pass

    # The distance between the loudest moment and the average is the
    # crest. A track with a high crest has peaks that stand out, and a
    # track with a low one is flat all the way through.
    crest = audio.get("crest_db")
    if crest is not None:
        try:
            value = float(crest)
            if value >= 8.0:
                score += 0.15
                parts.append(f"đỉnh nổi bật {value:.0f}dB")
            elif value < 3.0:
                parts.append(f"âm thanh nén phẳng ({value:.0f}dB)")
            else:
                parts.append(f"đỉnh {value:.0f}dB")
        except (TypeError, ValueError):
            pass

    # ---- the movement of the energy -------------------------------------
    dynamics = audio.get("dynamics_db")
    if dynamics is not None:
        try:
            value = float(dynamics)
            # A track whose energy moves has a shape; a flat one does
            # not carry the arc a viewer feels.
            if value >= 4.0:
                score += 0.15
                parts.append(f"năng lượng biến động {value:.1f}dB")
            else:
                parts.append(f"năng lượng ổn định {value:.1f}dB")
        except (TypeError, ValueError):
            pass

    # ---- the loudest passages -------------------------------------------
    longest = audio.get("longest_loud_seconds")
    if longest is not None:
        try:
            value = float(longest)
            if value >= 0.5:
                score += 0.10
                parts.append(f"đoạn cao trào dài {value:.1f}s")
            else:
                parts.append(f"đoạn cao trào ngắn {value:.1f}s")
        except (TypeError, ValueError):
            pass

    silence = audio.get("silence_ratio")
    if silence is not None:
        try:
            value = float(silence)
            if value <= 0.25:
                score += 0.10
                parts.append(f"ít khoảng lặng ({value:.0%})")
            else:
                parts.append(f"{value:.0%} là khoảng lặng")
        except (TypeError, ValueError):
            pass

    # ---- the rhythm -----------------------------------------------------
    tempo = audio.get("tempo_bpm")
    confidence = float(audio.get("tempo_confidence") or 0.0)
    if tempo:
        # The rhythm is only counted when the beats line up well, so a
        # track of speech does not get a made up beat.
        if confidence >= 0.55:
            score += 0.10
            parts.append(f"nhịp {tempo:.0f} BPM (độ tin cậy {confidence:.0%})")
        else:
            parts.append(
                f"nhịp {tempo:.0f} BPM nhưng beat không rõ (độ tin cậy {confidence:.0%})"
            )

    # ---- the shape of the sound -----------------------------------------
    bands = audio.get("bands") or {}
    if bands:
        low = float(bands.get("low") or 0.0)
        middle = float(bands.get("middle") or 0.0)
        high = float(bands.get("high") or 0.0)
        parts.append(
            f"dải tần số thấp {low:.0%}, trung {middle:.0%}, cao {high:.0%}"
        )
        # A track that carries all three bands has a full spectrum.
        if low > 0.05 and middle > 0.05 and high > 0.02:
            score += 0.05

    # ---- the quality of the stream --------------------------------------
    if sample_rate >= 44100:
        score += 0.05
    if bit_rate >= 128000:
        score += 0.05
    if sample_rate or bit_rate:
        facts = []
        if sample_rate:
            facts.append(f"{sample_rate}Hz")
        if bit_rate:
            facts.append(f"{bit_rate // 1000}kbps")
        parts.append(", ".join(facts))

    # The certainty follows how much was really measured. A track that
    # was decoded and measured gives evidence; a track with only the
    # facts of its header gives less.
    certainty = EVIDENCE
    if not parts:
        certainty = UNDETERMINED

    return Finding(
        key="music_quality",
        points=max(0.0, min(1.0, score)) * maximum,
        maximum=maximum,
        certainty=certainty,
        reason="đo được âm thanh thật: " + (", ".join(parts) if parts else "không đủ số đo"),
    )


def _hook_quality(frames: list[bytes], features: dict[str, float]) -> Finding:
    """Score the pull of the opening moment, from the first frame.

    The first frame is the one the viewer sees before deciding to stay.
    A first frame that is sharp, colourful and not black holds attention
    better than a dark or flat one.
    """
    maximum = _FINDING_MAX["hook_retention"]
    if not frames or not features:
        return Finding(
            key="hook_retention",
            points=0.0,
            maximum=maximum,
            certainty=NO_DATA,
            reason="không có khung hình đầu để đánh giá sức hút",
        )

    first = _frame_features(frames[0])
    if not first:
        return Finding(
            key="hook_retention",
            points=0.0,
            maximum=maximum,
            certainty=NO_DATA,
            reason="không đọc được khung hình đầu",
        )

    # The brightness of the first frame decides whether it even shows.
    brightness = first.get("brightness", 0.0)
    if brightness < 10.0:
        return Finding(
            key="hook_retention",
            points=maximum * 0.10,
            maximum=maximum,
            certainty=EVIDENCE,
            reason="khung hình đầu gần như tối, không giữ được người xem",
        )

    interest = (
        min(1.0, first.get("edges", 0.0) / 30.0) * 0.45
        + min(1.0, first.get("saturation", 0.0) / 95.0) * 0.35
        + min(1.0, first.get("contrast", 0.0) / 65.0) * 0.20
    )
    # The picture has to change over the clip for the hook to hold.
    variation = 0.0
    if len(frames) > 1:
        try:
            import numpy as np

            sizes = [_frame_features(frame) for frame in frames]
            sizes = [s for s in sizes if s]
            if len(sizes) > 1:
                brightness_values = [s.get("brightness", 0.0) for s in sizes]
                spread = float(np.std(brightness_values))
                variation = min(1.0, spread / 28.0)
        except Exception:
            variation = 0.0

    # The real movement of the picture over the opening. The spread of
    # the brightness only sees the light; the movement sees the whole
    # picture change, which is what holds the viewer.
    motion = 0.0
    if len(frames) > 1:
        try:
            from local_vision import measure_motion

            measured = measure_motion(frames)
            motion = min(1.0, measured.changed_area * 2.2)
        except Exception:
            motion = 0.0

    # The movement is measured on the real frames, so it counts as much
    # as the old measure of the light.
    score = (interest * 0.55 + variation * 0.20 + motion * 0.25) * maximum
    return Finding(
        key="hook_retention",
        points=max(0.0, min(1.0, score)),
        maximum=maximum,
        certainty=EVIDENCE,
        reason=(
            f"khung hình đầu sáng {brightness:.0f}, chi tiết {first.get('edges', 0):.0f}, "
            f"thay đổi giữa các khung hình {variation:.0%}, "
            f"hình chuyển động {motion:.0%}"
        ),
    )


def _has_enough_data(result: LocalAnalysis) -> bool:
    """Return True when the candidate has enough data to be ranked.

    A candidate is ranked when the topic was really decided. The other
    dimensions may stay unknown; the score then carries the points it
    could prove and no more.
    """
    if result.content_is_ai_music is None:
        return False
    topic = result.findings.get("topic_fit")
    if topic is None or topic.certainty not in (EVIDENCE, POSSIBILITY):
        return False
    return True


def _describe(
    features: dict[str, float], synthetic: float, waveform: float, text_like: float
) -> str:
    """Return one sentence that says what the frames really show."""
    if not features:
        return "Không mô tả được nội dung."
    parts = [
        f"ảnh {features.get('width', 0):.0f}x{features.get('height', 0):.0f}",
        f"tương phản {features.get('contrast', 0):.0f}",
        f"bão hoà {features.get('saturation', 0):.0f}",
    ]
    if waveform > 0.35:
        parts.append("có cấu trúc waveform/timeline")
    if text_like > 0.35:
        parts.append("có nhiều chữ")
    if synthetic > 0.35:
        parts.append("mượt và giàu màu như ảnh tạo bằng máy")
    return "Khung hình: " + ", ".join(parts) + "."


# The findings the analyzer produces, and the weight of each one. The
# weights add up to 100, as the product requires.
_FINDING_MAX = {
    "topic_fit": 25.0,
    "visual_quality": 15.0,
    "music_quality": 15.0,
    "hook_retention": 15.0,
    "engagement_virality": 20.0,
    "channel_fit": 10.0,
}

_FINDING_KEYS = tuple(_FINDING_MAX.keys())

# The label the dashboard shows for every finding.
FINDING_LABELS = {
    "topic_fit": "Mức độ phù hợp chủ đề",
    "visual_quality": "Chất lượng hình ảnh",
    "music_quality": "Chất lượng âm thanh",
    "hook_retention": "Khả năng thu hút",
    "engagement_virality": "Tương tác & xu hướng",
    "channel_fit": "Phù hợp kênh đích",
}


def score_local(result: LocalAnalysis) -> tuple[int, list[str], list[str]]:
    """Return the total score of a local analysis, with strengths and gaps.

    A dimension that the machine could not decide keeps no points and is
    listed as a gap. The total is never raised to a round number to look
    complete. A candidate whose topic was not decided has no score at
    all, because a score without a verdict would be a made-up number.
    """
    strengths: list[str] = []
    weaknesses: list[str] = []

    if result.content_is_ai_music is None:
        for key in _FINDING_KEYS:
            finding = result.findings.get(key)
            label = FINDING_LABELS.get(key, key)
            if finding is None:
                weaknesses.append(f"{label}: {INSUFFICIENT_DATA}")
            elif not finding.known:
                weaknesses.append(
                    f"{label}: {finding.reason or INSUFFICIENT_DATA}"
                )
            else:
                weaknesses.append(f"{label}: {finding.reason}")
        return 0, strengths, weaknesses

    total = 0.0
    decided = 0

    for key in _FINDING_KEYS:
        finding = result.findings.get(key)
        if finding is None:
            weaknesses.append(f"{FINDING_LABELS.get(key, key)}: {INSUFFICIENT_DATA}")
            continue
        if not finding.known:
            weaknesses.append(
                f"{FINDING_LABELS.get(key, key)}: {finding.reason or INSUFFICIENT_DATA}"
            )
            continue
        decided += 1
        total += finding.points
        share = (finding.points / finding.maximum) if finding.maximum else 0.0
        label = FINDING_LABELS.get(key, key)
        if share >= 0.65:
            strengths.append(f"{label}: {finding.reason}")
        elif share <= 0.3:
            weaknesses.append(f"{label}: {finding.reason}")

    if decided == 0:
        return 0, strengths, weaknesses
    return int(round(max(0.0, min(100.0, total)))), strengths, weaknesses
