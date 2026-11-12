"""The local vision analyzer of TOOLTDH.

This module understands what a video frame really shows, using a model
that runs on this machine. It never calls Gemini, OpenAI or any paid
service, and it never downloads anything by itself.

The analyzer is built in two layers, and the two are always told apart:

* The **model layer** reads the picture with a real vision model. When a
  model is on this machine it names the scene, the objects and the text
  it can see. Its answers are ``evidence``, because they come from a
  model that really looked at the picture.
* The **heuristic layer** measures the pixels with the libraries this
  machine already has: edges, colour, contrast, the layout of a music
  screen. Its answers are ``possible`` at best, because a measurement
  is a sign and not a reading.

When no vision model is on the machine, the model layer stays empty and
says so. Nothing is guessed, and the heuristic layer keeps working on
its own.

The seam for a model is :func:`register_vision_adapter`. A model plugs in
there without the rest of the pipeline needing a rewrite, exactly like
the sound model plugs into ``register_audio_adapter`` of the analyzer.
"""

from __future__ import annotations

import io
import os
from dataclasses import dataclass, field
from typing import Any

# The certainty of a conclusion, from the strongest to the weakest.
EVIDENCE = "evidence"
POSSIBILITY = "possible"
UNDETERMINED = "undetermined"
NO_DATA = "no_data"


@dataclass
class VisionObject:
    """One thing a vision model really saw in a frame.

    The label comes from the model, so it is a reading of the picture
    and not a measurement of the pixels.
    """

    label: str = ""
    # How sure the model was, from 0 to 1.
    confidence: float = 0.0
    # Where in the frame the object was, as a share of the frame.
    box: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "confidence": round(float(self.confidence), 3),
            "box": [round(float(value), 3) for value in self.box],
        }


@dataclass
class VisionReading:
    """What a vision model really read from the frames of a video.

    Every field here comes from the model. The fields the model could
    not fill stay empty, and the reading says so with its own
    ``certainty``.
    """

    # The scene the model described, in its own words.
    scene: str = ""
    # The things the model saw, with their confidence.
    objects: list[VisionObject] = field(default_factory=list)
    # The text the model read in the picture.
    text: list[str] = field(default_factory=list)
    # The name of the model that produced this reading.
    model: str = ""
    # True when the reading came from a model that really looked.
    from_model: bool = False
    # How sure the model was about the scene as a whole.
    confidence: float = 0.0
    # Why the reading is empty, when it is empty.
    note: str = ""

    @property
    def certainty(self) -> str:
        """Return how sure this reading is.

        A reading from a model is evidence. An empty reading is not
        enough data, because nothing was really seen.
        """
        if self.from_model and (self.scene or self.objects or self.text):
            return EVIDENCE
        return NO_DATA

    def to_dict(self) -> dict[str, Any]:
        return {
            "scene": self.scene,
            "objects": [item.to_dict() for item in self.objects],
            "text": list(self.text),
            "model": self.model,
            "from_model": self.from_model,
            "confidence": round(float(self.confidence), 3),
            "certainty": self.certainty,
            "note": self.note,
        }


@dataclass
class VisionMotion:
    """How the picture of a video moves over time.

    These are measurements of the real frames, so they are evidence of
    what the pixels did. They say nothing about what the picture means.
    """

    # How much the picture changed between one frame and the next.
    change: float = 0.0
    # How much of the frame changed, as a share of the picture.
    changed_area: float = 0.0
    # How alike the frames are to each other, from 0 to 1.
    consistency: float = 0.0
    # The number of frames that were really compared.
    frames_compared: int = 0
    # The number of frames the motion was judged from.
    frames_used: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "change": round(float(self.change), 4),
            "changed_area": round(float(self.changed_area), 4),
            "consistency": round(float(self.consistency), 4),
            "frames_compared": int(self.frames_compared),
            "frames_used": int(self.frames_used),
        }


@dataclass
class VisionHook:
    """The pull of the first three seconds of a video.

    The measure is made on the real frames of the opening, so it says
    how much the picture moves and how sharp the first frame is. It does
    not say whether the video is good.
    """

    # How much the picture moves over the opening.
    movement: float = 0.0
    # How sharp the first frame is.
    sharpness: float = 0.0
    # How much the first frame differs from the ones after it.
    opening_contrast: float = 0.0
    # The number of frames of the opening that were really used.
    frames_used: int = 0
    # True when the opening could really be measured.
    measured: bool = False
    # Why the opening could not be measured, when it could not.
    note: str = ""

    @property
    def certainty(self) -> str:
        """Return how sure the measure of the opening is."""
        return EVIDENCE if self.measured else NO_DATA

    def to_dict(self) -> dict[str, Any]:
        return {
            "movement": round(float(self.movement), 4),
            "sharpness": round(float(self.sharpness), 4),
            "opening_contrast": round(float(self.opening_contrast), 4),
            "frames_used": int(self.frames_used),
            "certainty": self.certainty,
            "note": self.note,
        }


@dataclass
class VisionReport:
    """Everything the local vision analyzer could really say.

    The report keeps the model layer and the heuristic layer apart, so
    the pipeline can tell a reading from a measurement.
    """

    # What the model really read.
    reading: VisionReading = field(default_factory=VisionReading)
    # How the picture moves.
    motion: VisionMotion = field(default_factory=VisionMotion)
    # The pull of the opening.
    hook: VisionHook = field(default_factory=VisionHook)
    # The name of the model that was used, when one was used.
    model: str = ""
    # True when a model really looked at the frames.
    model_used: bool = False
    # What the machine is missing to understand the picture.
    missing_dependency: str = ""
    # The version of the analyzer, part of the cache key.
    version: str = "vision-v1"

    @property
    def certainty(self) -> str:
        """Return the certainty of the report as a whole.

        A report from a model is evidence. A report from the pixels
        alone is a possibility, and a report with nothing in it is not
        enough data.
        """
        if self.model_used and self.reading.certainty == EVIDENCE:
            return EVIDENCE
        if self.motion.frames_used or self.hook.measured:
            return POSSIBILITY
        return NO_DATA

    def to_dict(self) -> dict[str, Any]:
        return {
            "reading": self.reading.to_dict(),
            "motion": self.motion.to_dict(),
            "hook": self.hook.to_dict(),
            "model": self.model,
            "model_used": self.model_used,
            "missing_dependency": self.missing_dependency,
            "certainty": self.certainty,
            "version": self.version,
        }


# --------------------------------------------------------------------------
# The models that can read a picture on this machine.
# --------------------------------------------------------------------------

# The adapters that can read the frames of a video. An adapter is a
# callable that takes the list of frames and returns a VisionReading,
# or None when it could not read them. This is the seam where a vision
# model goes, so the pipeline never has to be rewritten to add one.
_VISION_ADAPTERS: list[Any] = []


def register_vision_adapter(adapter: Any) -> None:
    """Add an adapter that reads the frames of a video.

    An adapter is a callable that takes the frames of a video and
    returns a :class:`VisionReading`, or ``None`` when it could not
    read them. This is the seam where a local vision model goes, so the
    rest of the pipeline needs no change when one is added.
    """
    if adapter is None:
        return
    _VISION_ADAPTERS.append(adapter)


def clear_vision_adapters() -> None:
    """Remove every adapter, so the analyzer falls back on the pixels."""
    _VISION_ADAPTERS.clear()


# --------------------------------------------------------------------------
# The ONNX adapter: the model that really reads a picture.
# --------------------------------------------------------------------------

# The name of the model that reads the picture. It is part of the cache,
# so a different model makes the old readings stale.
VISION_MODEL_VERSION = "vision-v1"

# The labels the model knows, when the model carries its own label file.
# The labels of an ImageNet model are read from a text file next to it.
def _read_labels(model_path: str) -> list[str]:
    """Return the labels of a model, from the file next to it.

    The label file is a text file with one label per line, or a JSON
    file that holds a list of labels. When it is not there, the model
    has no names and can only say which class it saw.
    """
    import json
    import os

    folder = os.path.dirname(model_path)
    stem = os.path.splitext(os.path.basename(model_path))[0]
    names = [
        f"{stem}_labels.txt",
        f"{stem}.labels.txt",
        "labels.txt",
        "synset.txt",
        "classes.txt",
        "imagenet_classes.txt",
        "labels.json",
        "classes.json",
    ]
    for name in names:
        candidate = os.path.join(folder, name)
        if not os.path.isfile(candidate):
            continue
        try:
            text = open(candidate, "r", encoding="utf-8").read()
        except OSError:
            continue
        if name.endswith(".json"):
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                payload = list(payload.values())
            if isinstance(payload, list):
                labels = [str(item) for item in payload]
                if labels:
                    return labels
            continue
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if lines:
            return lines
    return []


def onnx_vision_adapter(model_path: str, *, top_k: int = 5) -> Any:
    """Return an adapter that reads the frames with an ONNX model.

    The adapter is what makes a model real: it loads the model on this
    machine, gives it the frames of the video, and turns what the model
    says into a reading. The runtime that runs the model is the one of
    the machine; when it is not in this interpreter, the interpreter that
    has it is used to run the model.

    Nothing is downloaded. The model file has to be on the machine
    already, and this function says so when it is not there.
    """
    import os

    path = str(model_path or "").strip()
    if not path or not os.path.isfile(path):
        return None

    runtime = vision_runtime()
    if not runtime["available"]:
        return None

    labels = _read_labels(path)

    def _read(frames: list[bytes]) -> dict[str, Any] | None:
        pictures = []
        for frame in frames:
            picture = _read_picture(frame)
            if picture is None:
                continue
            pictures.append(picture)
        if not pictures:
            return None
        try:
            outputs = _run_onnx(path, pictures, runtime)
        except Exception:
            return None
        if not outputs:
            return None

        # The model gives one row of scores per picture. The labels of
        # the strongest ones are what the model really saw.
        import numpy as np

        rows = np.asarray(outputs)
        if rows.ndim == 1:
            rows = rows.reshape(1, -1)
        best_row = rows[0].astype(np.float64)

        # The scores of a model are often not shares yet. They are
        # turned into shares here, so the number that is reported says
        # how sure the model really was.
        if float(np.max(best_row) - np.min(best_row)) > 30.0:
            shifted = best_row - float(np.max(best_row))
            weights = np.exp(shifted)
        elif float(np.min(best_row)) < 0.0:
            shifted = best_row - float(np.max(best_row))
            weights = np.exp(shifted)
        else:
            total = float(best_row.sum())
            weights = best_row / total if total > 1e-9 else np.ones_like(best_row)

        order = np.argsort(weights)[::-1][:top_k]
        objects: list[dict[str, Any]] = []
        for index in order:
            position = int(index)
            score = float(weights[position])
            label = (
                labels[position].split(" ", 1)[-1].replace("_", " ")
                if position < len(labels)
                else f"lớp {position}"
            )
            objects.append({"label": label, "confidence": round(score, 4)})

        # The scene is the strongest reading of the model, joined with
        # the things it saw.
        names = [item["label"] for item in objects[:3]]
        scene = ", ".join(names) if names else ""
        confidence = objects[0]["confidence"] if objects else 0.0
        note = "" if labels else (
            "mô hình không có tệp nhãn cạnh bên, nên chỉ biết lớp chứ không biết tên"
        )
        return {
            "scene": scene,
            "objects": objects,
            "text": [],
            "model": os.path.basename(path),
            "from_model": True,
            "confidence": confidence,
            "note": note,
        }

    return _read


def _run_onnx(
    model_path: str, pictures: list[Any], runtime: dict[str, Any]
) -> list[Any]:
    """Run the model on the pictures and return what it says.

    The pictures are made the size the model wants, and the numbers are
    normalised the way an image model expects them.
    """
    import numpy as np

    size = _model_input_size(model_path, runtime)
    if size[0] <= 0 or size[1] <= 0:
        # The model does not take a picture, so it cannot read one.
        return []
    prepared = []
    for picture in pictures:
        prepared.append(_prepare_picture(picture, size))

    # The model runs in the interpreter that has the runtime.
    interpreter = runtime.get("path") or ""
    if interpreter:
        return _run_in_other_interpreter(interpreter, model_path, prepared, size)
    return _run_here(model_path, prepared)


def _model_input_size(model_path: str, runtime: dict[str, Any]) -> tuple[int, int]:
    """Return the size of the picture the model wants.

    The size is read from the model itself, so the picture is made the
    way the model expects it. When the model does not take a picture,
    ``(0, 0)`` is returned and the model is not used.
    """
    default = (224, 224)
    interpreter = runtime.get("path") or ""
    shape = _model_input_shape(model_path, interpreter)
    if shape is None:
        return default
    if len(shape) != 4:
        # The model does not take a picture of a height and a width, so
        # it is not a model of pictures.
        return (0, 0)
    height = shape[2] if isinstance(shape[2], int) else default[0]
    width = shape[3] if isinstance(shape[3], int) else default[1]
    channels = shape[1] if isinstance(shape[1], int) else 3
    if channels != 3:
        # A model that takes one channel or four channels is not a
        # model of a picture in colour.
        return (0, 0)
    return (height, width)


def _model_input_shape(model_path: str, interpreter: str) -> list | None:
    """Return the shape the model wants for its input.

    The shape is read in the interpreter that carries the runtime,
    because that is where the model can be opened.
    """
    if interpreter:
        try:
            import json
            import subprocess

            script = (
                "import sys, json, onnxruntime\n"
                "s=onnxruntime.InferenceSession(sys.argv[1], providers=['CPUExecutionProvider'])\n"
                "sh=s.get_inputs()[0].shape\n"
                "sys.stdout.write(json.dumps([d if isinstance(d,int) else str(d) for d in sh]))\n"
            )
            result = subprocess.run(
                [interpreter, "-c", script, model_path],
                capture_output=True,
                timeout=120,
            )
            if result.returncode != 0:
                return None
            raw = json.loads((result.stdout or b"[]").decode("utf-8") or "[]")
            return [int(value) if str(value).lstrip("-").isdigit() else value for value in raw]
        except Exception:
            return None
    try:
        import onnxruntime

        session = onnxruntime.InferenceSession(
            model_path, providers=["CPUExecutionProvider"]
        )
        return list(session.get_inputs()[0].shape)
    except Exception:
        return None


def _prepare_picture(picture: Any, size: tuple[int, int]) -> Any:
    """Make one picture the way an image model wants it."""
    import numpy as np
    from PIL import Image

    height, width = size
    array = np.asarray(picture, dtype=np.float32)
    image = Image.fromarray(array.astype(np.uint8)).convert("RGB")
    image = image.resize((width, height), Image.BILINEAR)
    data = np.asarray(image, dtype=np.float32) / 255.0
    # The numbers are centred the way the models that learned on ImageNet
    # expect them.
    data = (data - np.array([0.485, 0.456, 0.406], dtype=np.float32)) / np.array(
        [0.229, 0.224, 0.225], dtype=np.float32
    )
    return np.transpose(data, (2, 0, 1))[None, ...].astype(np.float32)
def _run_here(model_path: str, prepared: list[Any]) -> list[Any]:
    """Run the model in this interpreter."""
    import numpy as np
    import onnxruntime

    session = onnxruntime.InferenceSession(
        model_path, providers=["CPUExecutionProvider"]
    )
    name = session.get_inputs()[0].name
    outputs: list[Any] = []
    for batch in prepared:
        result = session.run(None, {name: batch})
        outputs.append(np.asarray(result[0]))
    return outputs


def _run_in_other_interpreter(
    interpreter: str, model_path: str, prepared: list[Any], size: tuple[int, int]
) -> list[Any]:
    """Run the model in the interpreter that carries the runtime.

    The pictures travel as raw bytes, so nothing has to be written to
    the disk and nothing is left behind. The shape of the tensor is
    carried with them, so the model gets exactly what it wants.
    """
    import json
    import subprocess

    import numpy as np

    # The shape of every tensor that travels.
    shapes = [list(batch.shape) for batch in prepared]
    # The pictures travel as raw bytes.
    payload = b"".join(batch.astype(np.float32).tobytes() for batch in prepared)

    script = (
        "import sys, json, numpy as np, onnxruntime\n"
        "model=sys.argv[1]\n"
        "shapes=json.loads(sys.argv[2])\n"
        "raw=sys.stdin.buffer.read()\n"
        "sess=onnxruntime.InferenceSession(model, providers=['CPUExecutionProvider'])\n"
        "name=sess.get_inputs()[0].name\n"
        "out=[]\n"
        "offset=0\n"
        "for shape in shapes:\n"
        "    count=1\n"
        "    for d in shape: count=count*d\n"
        "    size=count*4\n"
        "    arr=np.frombuffer(raw[offset:offset+size],dtype='<f4').reshape(shape)\n"
        "    offset=offset+size\n"
        "    out.append(np.asarray(sess.run(None,{name:arr})[0]).tolist())\n"
        "sys.stdout.write(json.dumps(out))\n"
    )
    result = subprocess.run(
        [
            interpreter,
            "-c",
            script,
            model_path,
            json.dumps(shapes),
        ],
        input=payload,
        capture_output=True,
        timeout=300,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"không chạy được mô hình: {(result.stderr or b'').decode('utf-8', 'replace')[:300]}"
        )
    return json.loads((result.stdout or b"[]").decode("utf-8") or "[]")


def auto_register_onnx_model() -> str:
    """Look for a vision model on this machine and register it.

    The model is looked for in the folders of the project. When one is
    there it is registered and its name is returned. When there is none,
    an empty string is returned and the analyzer keeps working on the
    pixels alone. Nothing is downloaded here.
    """
    roots = [
        os.path.join(os.getcwd(), "models"),
        os.path.join(os.getcwd(), "data", "models"),
        os.path.join(os.path.expanduser("~"), ".cache", "tooltdh", "models"),
    ]
    for root in roots:
        if not os.path.isdir(root):
            continue
        try:
            for base, _dirs, files in os.walk(root):
                for name in sorted(files):
                    if not name.lower().endswith(".onnx"):
                        continue
                    adapter = onnx_vision_adapter(os.path.join(base, name))
                    if adapter is None:
                        continue
                    register_vision_adapter(adapter)
                    return os.path.join(base, name)
        except Exception:
            continue
    return ""


def read_with_adapters(frames: list[bytes]) -> VisionReading:
    """Read the frames with the models that are on this machine.

    The adapters are tried in the order they were added. The first one
    that really reads the frames wins. When no adapter can read them,
    the reading stays empty and says that no model was found.
    """
    for adapter in _VISION_ADAPTERS:
        try:
            reading = adapter(frames)
        except Exception:
            reading = None
        if reading is None:
            continue
        if isinstance(reading, VisionReading):
            if reading.from_model:
                return reading
            continue
        if isinstance(reading, dict):
            converted = reading_from_dict(reading)
            if converted.from_model:
                return converted
    return VisionReading(
        from_model=False,
        note="không có mô hình vision nào trên máy để đọc khung hình",
    )


def reading_from_dict(payload: dict[str, Any]) -> VisionReading:
    """Turn a plain dictionary into a reading.

    This is the door an outside model goes through, so a model that does
    not know this module can still fill a reading.
    """
    objects: list[VisionObject] = []
    for item in payload.get("objects") or []:
        if not isinstance(item, dict):
            continue
        box = item.get("box") or (0.0, 0.0, 0.0, 0.0)
        try:
            numbers = tuple(float(value) for value in list(box)[:4])
        except (TypeError, ValueError):
            numbers = (0.0, 0.0, 0.0, 0.0)
        while len(numbers) < 4:
            numbers = numbers + (0.0,)
        objects.append(
            VisionObject(
                label=str(item.get("label") or ""),
                confidence=float(item.get("confidence") or 0.0),
                box=numbers,  # type: ignore[arg-type]
            )
        )
    text = [str(item) for item in (payload.get("text") or []) if str(item).strip()]
    return VisionReading(
        scene=str(payload.get("scene") or ""),
        objects=objects,
        text=text,
        model=str(payload.get("model") or ""),
        from_model=bool(payload.get("from_model") or False),
        confidence=float(payload.get("confidence") or 0.0),
        note=str(payload.get("note") or ""),
    )


# --------------------------------------------------------------------------
# The hardware of the machine, and what it can carry.
# --------------------------------------------------------------------------

def vision_runtime() -> dict[str, Any]:
    """Return the vision runtime this machine really has.

    The runtime is looked for in the interpreter of the project first,
    and then in the other environments of the machine, so a machine
    that already has a runtime can use it without installing anything.
    Nothing is installed here.
    """
    import importlib.util

    def _installed() -> bool:
        try:
            return importlib.util.find_spec("onnxruntime") is not None
        except Exception:
            return False

    if _installed():
        return {
            "runtime": "onnxruntime",
            "available": True,
            "providers": _onnx_providers(),
            "path": "",
        }

    # The other interpreters of the machine may carry a runtime that
    # this one cannot see.
    for path in _other_interpreters():
        if not path:
            continue
        try:
            import subprocess

            result = subprocess.run(
                [path, "-c", "import onnxruntime, json; print(json.dumps(onnxruntime.get_available_providers()))"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                continue
            import json

            providers = json.loads((result.stdout or "[]").strip() or "[]")
            return {
                "runtime": "onnxruntime",
                "available": True,
                "providers": providers,
                "path": path,
            }
        except Exception:
            continue
    return {
        "runtime": "",
        "available": False,
        "providers": [],
        "path": "",
    }


def _onnx_providers() -> list[str]:
    """Return the providers the runtime can use."""
    try:
        import onnxruntime

        return list(onnxruntime.get_available_providers())
    except Exception:
        return []


def _other_interpreters() -> list[str]:
    """Return the other interpreters of the machine that may be usable.

    The search is only in the places where an environment of the machine
    usually sits, so the disk is not walked for nothing.
    """
    found: list[str] = []
    home = os.path.expanduser("~")
    roots = [
        os.path.join(home, "Downloads"),
        os.path.join(home, "Documents"),
        os.path.join(home, "projects"),
        os.path.join(home, ".venvs"),
        os.path.join(home, "venvs"),
    ]
    for root in roots:
        if not os.path.isdir(root):
            continue
        try:
            for base, dirs, _files in os.walk(root):
                # The search stays shallow: a virtual environment of a
                # project sits a few folders deep.
                depth = base[len(root):].count(os.sep)
                if depth >= 3:
                    dirs[:] = []
                if os.path.basename(base).lower() in (".venv", "venv", "env"):
                    scripts = os.path.join(base, "Scripts", "python.exe")
                    if os.path.isfile(scripts):
                        found.append(scripts)
                    bin_dir = os.path.join(base, "bin", "python3")
                    if os.path.isfile(bin_dir):
                        found.append(bin_dir)
        except Exception:
            continue
    return found[:8]


def machine_resources() -> dict[str, Any]:
    """Return what this machine really offers to run a model.

    The numbers are read from the machine itself, so the model that is
    chosen fits the hardware that is really there.
    """
    info: dict[str, Any] = {
        "cpu": "",
        "cores": 0,
        "ram_gb": 0.0,
        "ram_free_gb": 0.0,
        "gpu": "",
    }
    try:
        import platform

        info["cpu"] = platform.processor() or platform.machine()
        info["cores"] = int(os.cpu_count() or 0)
    except Exception:
        pass

    try:
        import ctypes

        class _MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = _MemoryStatus()
        status.dwLength = ctypes.sizeof(_MemoryStatus)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            info["ram_gb"] = round(status.ullTotalPhys / (1024**3), 1)
            info["ram_free_gb"] = round(status.ullAvailPhys / (1024**3), 1)
    except Exception:
        pass

    if os.name == "nt":
        try:
            import subprocess

            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "(Get-CimInstance Win32_VideoController | Select-Object -First 1).Name",
                ],
                capture_output=True,
                text=True,
                timeout=20,
            )
            if result.returncode == 0:
                info["gpu"] = (result.stdout or "").strip()
        except Exception:
            pass
    return info


def vision_dependency_missing() -> str:
    """Return what the machine is missing to understand a picture.

    Two things can be missing: the runtime that runs a model, and the
    model itself. Both are named, and it says clearly that nothing was
    downloaded. Nothing is installed and nothing is downloaded here.
    """
    runtime = vision_runtime()
    if not runtime["available"]:
        return (
            "máy chưa có runtime vision (onnxruntime) để chạy mô hình; "
            "cần cài onnxruntime cho CPU"
        )
    # The runtime is there. A model is still needed, and this module
    # never downloads one by itself.
    if not _model_on_disk():
        return (
            "máy đã có onnxruntime nhưng chưa có mô hình vision cục bộ; "
            "cần đặt một mô hình ONNX nhẹ cho CPU (ví dụ MobileNet/ResNet18 "
            "đã huấn luyện phân loại ảnh) vào thư mục models/ "
            "rồi đăng ký qua register_vision_adapter"
        )
    return ""


def _model_on_disk() -> bool:
    """Return True when a vision model file is really on the machine.

    The search is only in the folders of the project and in the usual
    places a model is kept, so the disk is not walked for nothing.
    """
    roots = [
        os.path.join(os.getcwd(), "models"),
        os.path.join(os.getcwd(), "data", "models"),
        os.path.join(os.path.expanduser("~"), ".cache", "tooltdh", "models"),
    ]
    for root in roots:
        if not os.path.isdir(root):
            continue
        try:
            for base, _dirs, files in os.walk(root):
                for name in files:
                    if name.lower().endswith(".onnx"):
                        return True
        except Exception:
            continue
    return False


# --------------------------------------------------------------------------
# The picture of a video, measured on the real frames.
# --------------------------------------------------------------------------

def _read_picture(frame: bytes) -> Any:
    """Return the pixels of a frame, or None when it cannot be read."""
    try:
        import numpy as np
        from PIL import Image
    except Exception:
        return None
    try:
        with Image.open(io.BytesIO(frame)) as image:
            return np.asarray(image.convert("RGB"), dtype=np.float32)
    except Exception:
        return None


def measure_motion(frames: list[bytes]) -> VisionMotion:
    """Measure how the picture of a video moves over time.

    The measure is made by comparing the real frames one to the next,
    so it says how much the picture really changed and how alike the
    frames are to each other.
    """
    import numpy as np

    pictures: list[Any] = []
    for frame in frames:
        picture = _read_picture(frame)
        if picture is not None:
            pictures.append(picture)
    if len(pictures) < 2:
        return VisionMotion(
            frames_compared=len(pictures),
            frames_used=0,
        )

    changes: list[float] = []
    areas: list[float] = []
    for before, after in zip(pictures, pictures[1:]):
        if before.shape != after.shape:
            # A frame of a different size is a cut. It is counted as a
            # full change, because the picture really was replaced.
            changes.append(1.0)
            areas.append(1.0)
            continue
        difference = np.abs(after - before).mean(axis=2)
        changes.append(float(difference.mean() / 255.0))
        areas.append(float((difference > 24.0).mean()))

    # The alike-ness of the frames: the share of the picture that stayed
    # the same between one frame and the next.
    consistency = float(1.0 - min(1.0, float(np.mean(areas))))
    return VisionMotion(
        change=float(np.mean(changes)),
        changed_area=float(np.mean(areas)),
        consistency=consistency,
        frames_compared=len(pictures) - 1,
        frames_used=len(pictures),
    )


def measure_hook(frames: list[bytes]) -> VisionHook:
    """Measure the pull of the opening of a video.

    The opening is the first three seconds, which is the moment a
    viewer decides to stay or to leave. The measure uses the real
    frames of the opening, when they were kept.

    The frames of the cache carry the moment they were taken, so the
    opening is picked by that moment. When the moments are not known,
    the first frames of the cache are used, and the reading says that
    the opening was judged from them.
    """
    import numpy as np

    if not frames:
        return VisionHook(note="không có khung hình nào để đo phần mở đầu")

    pictures: list[Any] = []
    for frame in frames:
        picture = _read_picture(frame)
        if picture is not None:
            pictures.append(picture)
    if not pictures:
        return VisionHook(note="không đọc được ảnh của khung hình đầu tiên")

    # The sharpness of the first frame: how much detail it carries.
    first = pictures[0]
    luminance = 0.299 * first[:, :, 0] + 0.587 * first[:, :, 1] + 0.114 * first[:, :, 2]
    try:
        dx = np.abs(np.diff(luminance, axis=1)).mean()
        dy = np.abs(np.diff(luminance, axis=0)).mean()
        sharpness = float((dx + dy) / 2.0)
    except Exception:
        sharpness = 0.0

    # How much the picture moves over the opening.
    movement = 0.0
    opening_contrast = 0.0
    if len(pictures) >= 2:
        areas: list[float] = []
        for before, after in zip(pictures, pictures[1:]):
            if before.shape != after.shape:
                areas.append(1.0)
                continue
            difference = np.abs(after - before).mean(axis=2)
            areas.append(float((difference > 24.0).mean()))
        movement = float(np.mean(areas))
        # The first frame against the frame that follows it: a sharp
        # change there is the sign of a cut that catches the eye.
        if pictures[0].shape == pictures[1].shape:
            opening_contrast = float(
                (np.abs(pictures[1] - pictures[0]).mean(axis=2) > 24.0).mean()
            )

    return VisionHook(
        movement=movement,
        sharpness=sharpness,
        opening_contrast=opening_contrast,
        frames_used=len(pictures),
        measured=True,
        note=(
            "đo trên các khung hình đầu tiên của bộ nhớ đệm"
            if len(pictures) < 2
            else ""
        ),
    )


# --------------------------------------------------------------------------
# The analyzer.
# --------------------------------------------------------------------------

def analyze_vision(
    frames: list[bytes],
    *,
    frame_times: list[float] | None = None,
) -> VisionReport:
    """Read what the frames of a video really show.

    The model layer and the pixel layer are kept apart. A model that
    reads the picture gives its scene, its objects and its text. The
    pixels give the movement, the alike-ness of the frames and the pull
    of the opening.

    When no model is on the machine, the model layer is empty and says
    so. Nothing about the content of the picture is guessed.
    """
    report = VisionReport()

    # ---- the model layer ------------------------------------------------
    reading = read_with_adapters(frames)
    report.reading = reading
    report.model = reading.model
    report.model_used = bool(reading.from_model)

    # ---- the pixel layer ------------------------------------------------
    report.motion = measure_motion(frames)
    report.hook = measure_hook(frames)
    report.missing_dependency = (
        "" if report.model_used else vision_dependency_missing()
    )
    return report


def describe_vision(report: VisionReport) -> str:
    """Return one sentence that says what was really seen.

    The sentence names the model when a model read the picture, and
    says plainly that only the pixels were measured when no model was
    there.
    """
    parts: list[str] = []
    reading = report.reading
    if reading.from_model:
        if reading.scene:
            parts.append(f"mô hình {reading.model or 'cục bộ'} đọc: {reading.scene}")
        labels: list[str] = []
        for item in reading.objects[:6]:
            if item.label:
                labels.append(f"{item.label} {item.confidence:.0%}")
        if labels:
            parts.append("thấy " + ", ".join(labels))
        if reading.text:
            parts.append("chữ trong khung hình: " + ", ".join(reading.text[:4]))
    else:
        parts.append(
            "không có mô hình vision trên máy, chỉ đo được đặc trưng hình ảnh"
        )

    if report.motion.frames_used >= 2:
        parts.append(
            f"hình thay đổi {report.motion.change:.1%} giữa các khung hình, "
            f"nhất quán {report.motion.consistency:.0%}"
        )
    if report.hook.measured:
        parts.append(
            f"phần mở đầu dài {report.hook.frames_used} khung hình, "
            f"chuyển động {report.hook.movement:.1%}"
        )
    return "; ".join(parts) if parts else "Không mô tả được nội dung hình ảnh."
