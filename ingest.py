"""P2 video ingestion with mandatory rights and permission checks."""

from __future__ import annotations

import json
import subprocess
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from library import ContentLibrary
from storage import (
    MAX_DURATION_SECONDS,
    MAX_FILE_SIZE_BYTES,
    StorageError,
    ensure_directories,
    move_to_temp,
    sha256_file,
    validate_media_file,
)

SUPPORTED_URL_SCHEMES = {"http", "https"}
MAX_PROBE_SECONDS = 30

# Container signatures used to identify the real format of a downloaded file.
# The extension on disk is not trusted: a WebM body saved as ".mp4" is common.
_MEDIA_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\x1a\x45\xdf\xa3", "webm"),
    (b"\x00\x00\x00\x18ftyp", "mp4"),
    (b"\x00\x00\x00\x20ftyp", "mp4"),
    (b"\x00\x00\x00\x1cftyp", "mp4"),
    (b"\x00\x00\x00\x1fftyp", "mp4"),
    (b"\x00\x00\x00\x14ftyp", "mp4"),
    (b"ftypqt", "mp4"),
    (b"ftypisom", "mp4"),
    (b"ftypmp42", "mp4"),
)
_MP4_BRANDS = ("isom", "mp42", "mp41", "avc1", "dash", "iso2", "M4V ", "qt  ")


class IngestError(RuntimeError):
    """Raised when an item cannot be accepted for ingestion."""


class RightsNotVerifiedError(IngestError):
    """Raised when rights or permission evidence is absent."""


def validate_rights(rights_verified: bool, permission: bool, evidence: str | None = None) -> None:
    """Require explicit rights and permission before any download."""
    if not rights_verified:
        raise RightsNotVerifiedError(
            "Rejected: content rights are not verified; provide verified rights evidence"
        )
    if not permission:
        raise RightsNotVerifiedError(
            "Rejected: permission to download and use the content is not confirmed"
        )
    if not evidence or not evidence.strip():
        raise RightsNotVerifiedError(
            "Rejected: rights and permission are confirmed but supporting evidence is missing"
        )


def _resolve_local_source(source: str, parsed: object) -> Path:
    """Resolve a local source without interpreting Windows drive letters as schemes."""
    if getattr(parsed, "scheme", "").lower() == "file":
        return Path(parsed.path).expanduser()  # type: ignore[attr-defined]
    return Path(source).expanduser()


def validate_source(source: str) -> None:
    """Validate a local path or supported remote URL."""
    parsed = urlparse(source)
    if parsed.scheme.lower() in SUPPORTED_URL_SCHEMES:
        if not parsed.netloc:
            raise IngestError("Rejected: URL has no host")
        return
    local_path = _resolve_local_source(source, parsed)
    try:
        exists = local_path.is_file()
    except OSError:
        exists = False
    if not exists:
        raise IngestError("Rejected: local source file does not exist")


def _resolve_local_source(source: str, parsed: object) -> Path:
    """Resolve a local source without interpreting Windows drive letters as schemes."""
    if getattr(parsed, "scheme", "").lower() == "file":
        return Path(parsed.path).expanduser()  # type: ignore[attr-defined]
    return Path(source).expanduser()


def detect_media_format(path: Path) -> str:
    """Return the real container format of a media file from its bytes.

    The extension on disk is never trusted because a download can save a WebM
    body under an ``.mp4`` name. The container signature decides the format.
    """
    try:
        with Path(path).open("rb") as media_file:
            header = media_file.read(64)
    except OSError as exc:
        raise IngestError(f"Rejected: unable to read the media header: {exc}") from exc
    if not header:
        raise IngestError("Rejected: the media file is empty")
    if header.startswith(b"\x1a\x45\xdf\xa3"):
        return "webm"
    if header[4:8] == b"ftyp":
        brand = header[8:12].decode("latin-1", errors="replace")
        if brand in _MP4_BRANDS or brand.isalnum():
            return "mp4"
    if header[:4] == b"RIFF" and header[8:12] == b"AVI ":
        return "avi"
    if header[:4] == b"\x00\x00\x00\x18" and header[4:8] == b"ftyp":
        return "mp4"
    raise IngestError(
        "Rejected: the downloaded file is not a supported video container "
        f"(first bytes: {header[:12].hex()})"
    )


def _ffprobe_available() -> bool:
    """Return True when the ffprobe executable can be located."""
    from shutil import which

    return which("ffprobe") is not None


def _probe_duration(path: Path) -> float | None:
    """Read the real duration of a media file with ffprobe.

    Returns ``None`` only when ffprobe is genuinely unavailable. A missing
    tool is reported to the caller so the duration is never silently unknown.
    """
    if not _ffprobe_available():
        return None
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=MAX_PROBE_SECONDS,
            check=False,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as exc:
        raise IngestError(
            f"Rejected: ffprobe could not measure the media duration: {exc}"
        ) from exc
    if result.returncode != 0:
        raise IngestError(
            "Rejected: ffprobe could not read the media duration: "
            f"{result.stderr.strip() or 'unknown ffprobe error'}"
        )
    try:
        duration = float(result.stdout.strip())
    except ValueError as exc:
        raise IngestError(
            "Rejected: ffprobe returned an unreadable duration value"
        ) from exc
    if duration <= 0:
        raise IngestError("Rejected: the media file reports a duration of zero")
    return duration


def _container_duration(path: Path, media_format: str) -> float | None:
    """Read the duration from the container itself when ffprobe is unavailable.

    This is a fallback that reads the value the container already stores, so
    the duration is still measured rather than assumed. It returns ``None``
    when the container does not expose a usable duration.
    """
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    if media_format == "mp4":
        return _mp4_duration(data)
    if media_format == "webm":
        duration = _webm_duration(data)
        if duration is not None:
            return duration
        return _webm_cluster_duration(data)
    return None


def _mp4_duration(data: bytes) -> float | None:
    """Read the duration from an MP4 ``mvhd`` box."""
    import struct

    index = data.find(b"mvhd")
    if index < 0 or index + 24 > len(data):
        return None
    version = data[index + 4]
    try:
        if version == 0:
            timescale, duration = struct.unpack(">II", data[index + 16 : index + 24])
        else:
            timescale, duration = struct.unpack(">IQ", data[index + 20 : index + 32])
    except struct.error:
        return None
    if not timescale:
        return None
    seconds = duration / timescale
    return seconds if seconds > 0 else None


def _webm_duration(data: bytes) -> float | None:
    """Read the duration from a Matroska ``Duration`` element.

    The Duration element stores a float in milliseconds. Its size is a
    variable-length integer, so the payload starts right after the size and
    holds the raw float with no extra flag byte.
    """
    import struct

    index = data.find(b"\x44\x89")
    while index >= 0 and index + 3 < len(data):
        parsed = _read_vint_size(data, index + 2)
        if parsed is None:
            index = data.find(b"\x44\x89", index + 1)
            continue
        size, body = parsed
        if size == 4 and body + 4 <= len(data):
            try:
                milliseconds = struct.unpack(">f", data[body : body + 4])[0]
            except struct.error:
                milliseconds = 0.0
            if milliseconds > 0:
                return milliseconds / 1000.0
        elif size == 8 and body + 8 <= len(data):
            try:
                milliseconds = struct.unpack(">d", data[body : body + 8])[0]
            except struct.error:
                milliseconds = 0.0
            if milliseconds > 0:
                return milliseconds / 1000.0
        index = data.find(b"\x44\x89", index + 1)
    return None


def _read_vint_size(data: bytes, offset: int) -> tuple[int, int] | None:
    """Return ``(size, next_offset)`` for a Matroska variable-length integer."""
    if offset >= len(data):
        return None
    first = data[offset]
    if first == 0:
        return None
    mask = 0x80
    length = 1
    while length <= 8 and not first & mask:
        mask >>= 1
        length += 1
    if length > 8 or offset + length > len(data):
        return None
    size = first & (mask - 1)
    for step in range(1, length):
        size = (size << 8) | data[offset + step]
    return size, offset + length


def _webm_cluster_duration(data: bytes) -> float | None:
    """Read the duration of a WebM that stores no Duration element.

    A MediaRecorder file records only cluster timecodes. The highest cluster
    timecode combined with the TimecodeScale gives the real length.
    """
    import struct

    scale_index = data.find(b"\x2a\xd7\xb1")
    timecode_scale = 1_000_000
    if scale_index >= 0:
        parsed = _read_vint_size(data, scale_index + 3)
        if parsed is not None:
            size, body = parsed
            if 0 < size <= 8 and body + size <= len(data):
                timecode_scale = int.from_bytes(data[body : body + size], "big") or 1_000_000

    highest = -1
    index = 0
    while True:
        cluster = data.find(b"\x1f\x43\xb6\x75", index)
        if cluster < 0:
            break
        index = cluster + 4
        # The cluster timecode element 0xE7 follows the cluster size.
        probe = cluster + 4
        limit = min(len(data), probe + 64)
        position = probe
        while position < limit:
            byte = data[position]
            if byte & 0x80:
                element_id = data[position : position + 1].hex()
            else:
                element_id = data[position : position + 1].hex()
            parsed = _read_vint_size(data, position + 1)
            if parsed is None:
                break
            size, body = parsed
            if element_id == "e7" and body + size <= len(data):
                value = int.from_bytes(data[body : body + size], "big", signed=False)
                if value > highest:
                    highest = value
                break
            if size == 0:
                break
            position = body + size
    if highest < 0:
        return None
    seconds = highest * timecode_scale / 1_000_000_000
    return seconds if seconds > 0 else None


def measure_duration(path: Path, media_format: str) -> float:
    """Measure the real duration of a media file.

    The duration is always measured from the file itself. A declared or
    caller-supplied duration is never trusted and an unknown duration is
    never accepted silently.
    """
    duration = _probe_duration(path)
    if duration is not None:
        return duration
    duration = _container_duration(path, media_format)
    if duration is not None:
        return duration
    raise IngestError(
        "Rejected: the real duration of the media could not be measured. "
        "Install ffprobe or use a container that stores its duration. "
        "An unknown duration is never accepted."
    )


def _download_url(source: str, destination: Path) -> None:
    """Download a remote item with yt-dlp; no CAPTCHA bypass is attempted."""
    try:
        import yt_dlp
    except ImportError as exc:
        raise IngestError("yt-dlp is required to ingest URL sources") from exc

    destination.parent.mkdir(parents=True, exist_ok=True)
    options = {
        "outtmpl": str(destination.with_suffix(".%(ext)s")),
        "format": "mp4/mov/webm/best",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "retries": 2,
        "socket_timeout": 30,
    }
    try:
        with yt_dlp.YoutubeDL(options) as downloader:
            downloader.download([source])
    except yt_dlp.utils.DownloadError as exc:
        raise IngestError(
            "Rejected: download failed. Manual download or permission resolution may be required; "
            "CAPTCHA bypass is not supported"
        ) from exc
    if not destination.exists():
        candidates = [path for path in destination.parent.glob(f"{destination.stem}.*") if path.suffix.lower() in {".mp4", ".mov", ".webm"}]
        if not candidates:
            raise IngestError("Rejected: download completed without a supported video file")
        destination = candidates[0]


def ingest_video(
    source: str,
    task_id: str | None = None,
    *,
    rights_verified: bool = False,
    permission: bool = False,
    rights_evidence: str | None = None,
    duration_seconds: float | None = None,
    library: ContentLibrary | None = None,
    discovery_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Accept a rights-cleared video, store it temporarily, hash it, and save metadata.

    When ``discovery_config`` is supplied the source must also appear on the
    discovery allowlist and carry a valid permit. A source outside the
    allowlist is rejected before any download is attempted.
    """
    validate_rights(rights_verified, permission, rights_evidence)
    validate_source(source)

    if discovery_config is not None:
        from discover import validate_source_permitted

        parsed = urlparse(source)
        if parsed.scheme.lower() in SUPPORTED_URL_SCHEMES:
            validate_source_permitted(source, discovery_config)

    assigned_task_id = task_id or str(uuid.uuid4())
    ensure_directories()
    staging = Path("data") / "temp" / f".staging-{assigned_task_id}.mp4"
    try:
        parsed = urlparse(source)
        if parsed.scheme.lower() in SUPPORTED_URL_SCHEMES:
            _download_url(source, staging)
        else:
            staging = _resolve_local_source(source, parsed).resolve()
            if not staging.is_file():
                raise IngestError("Rejected: local source file does not exist")

        # The real container decides the format and the real file decides the
        # duration. A declared duration from a candidate record is only ever a
        # cross-check, never the measured value.
        media_format = detect_media_format(staging)
        detected_duration = measure_duration(staging, media_format)
        if duration_seconds is not None and duration_seconds > 0:
            declared = float(duration_seconds)
            if detected_duration > 0 and abs(declared - detected_duration) > max(
                1.0, detected_duration * 0.25
            ):
                raise IngestError(
                    "Rejected: the declared duration "
                    f"({declared:.2f}s) does not match the measured duration "
                    f"({detected_duration:.2f}s); the declared value is not trusted"
                )
        validate_media_file(staging, detected_duration)
        digest = sha256_file(staging)

        content_library = library or ContentLibrary()
        if content_library.contains_hash(digest):
            existing = content_library.find_by_hash(digest) or {}
            raise IngestError(
                "Duplicate content blocked: SHA256 "
                f"{digest} is already in the library "
                f"(task_id: {existing.get('task_id', 'unknown')})"
            )

        final_path = move_to_temp(staging, assigned_task_id)
        # The saved file keeps the format that was actually measured, so a
        # WebM body is never stored under an .mp4 name.
        if final_path.suffix.lower() != f".{media_format}":
            renamed = final_path.with_suffix(f".{media_format}")
            if final_path.exists():
                final_path.replace(renamed)
            final_path = renamed
        try:
            entry = content_library.add_file(final_path, assigned_task_id, source, digest)
        except Exception:
            if final_path.exists():
                final_path.unlink()
            raise

        metadata = {
            "task_id": assigned_task_id,
            "source": source,
            "rights_verified": True,
            "permission": True,
            "rights_evidence": rights_evidence,
            "path": str(final_path),
            "format": media_format,
            "size_bytes": final_path.stat().st_size,
            "max_size_bytes": MAX_FILE_SIZE_BYTES,
            "duration_seconds": detected_duration,
            "duration_source": "measured",
            "max_duration_seconds": MAX_DURATION_SECONDS,
            "sha256": digest,
            "library_entry": entry,
        }
        metadata_path = final_path.with_suffix(".json")
        with metadata_path.open("w", encoding="utf-8") as metadata_file:
            json.dump(metadata, metadata_file, indent=2, sort_keys=True)
            metadata_file.write("\n")
        return metadata
    finally:
        if staging.name.startswith(".staging-") and staging.exists():
            staging.unlink()


__all__ = [
    "IngestError",
    "RightsNotVerifiedError",
    "detect_media_format",
    "ingest_video",
    "measure_duration",
    "validate_rights",
    "validate_source",
]
