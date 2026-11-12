"""P2 Video Lab + Auto Download Best: non-AI, offline-capable, on top of P1.

Uses project_id + run_id + video_id from P1 (project_store). No separate
task system. Analysis is ffprobe/ffmpeg measurement only; no content
invention. Cache keyed by SHA256 + analyzer version. Download reuses
ingest/Library and checks rights first.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

ANALYZER_VERSION = "p2-video-lab-v1"
import os as _os
CACHE_FILE = Path(_os.environ.get("P2_CACHE_PATH", "data/state/p2_lab_cache.json"))
SETTINGS_FILE = Path(_os.environ.get("P2_SETTINGS_PATH", "data/state/p2_settings.json"))
FRAMES_DIR = Path(_os.environ.get("P2_FRAMES_DIR", "data/state/p2_frames"))
LIBRARY_PATH = _os.environ.get("P2_LIBRARY_PATH", "")

PERMITTED_RIGHTS = {"ALLOWLISTED_PERMITTED"}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, payload: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    tmp.replace(path)


def _tools() -> dict[str, str | None]:
    from local_analyzer import _tool_paths

    try:
        return dict(_tool_paths())
    except Exception:
        return {"ffmpeg": None, "ffprobe": None}


def _fps(text: Any) -> float | None:
    try:
        s = str(text or "").strip()
        if "/" in s:
            a, b = s.split("/", 1)
            b = float(b)
            return float(a) / b if b else None
        return float(s) if s else None
    except Exception:
        return None


def ffprobe_media(path: str) -> dict[str, Any]:
    """Measure container/streams with ffprobe. Real data only, no guessing."""
    tools = _tools()
    ffprobe = tools.get("ffprobe")
    if not ffprobe:
        raise RuntimeError("BLOCKED: ffprobe not found on this machine")
    p = Path(str(path or ""))
    if not p.is_file():
        raise FileNotFoundError(f"media file not found: {path}")
    r = subprocess.run(
        [ffprobe, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(p)],
        capture_output=True, text=True, timeout=60,
    )
    if r.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {(r.stderr or '')[:300]}")
    try:
        return json.loads(r.stdout or "{}")
    except Exception as exc:
        raise RuntimeError(f"ffprobe unreadable output: {exc}") from exc


def detect_scenes(path: str, threshold: float = 0.3) -> list[float]:
    """Detect scene-change timestamps with ffmpeg scene filter (measured)."""
    tools = _tools()
    ffmpeg = tools.get("ffmpeg")
    if not ffmpeg:
        return []
    try:
        r = subprocess.run(
            [ffmpeg, "-hide_banner", "-nostats", "-i", str(path),
             "-filter:v", f"select='gt(scene,{threshold})',showinfo",
             "-f", "null", "-"],
            capture_output=True, text=True, timeout=120,
        )
        out = (r.stderr or "") + (r.stdout or "")
        times: list[float] = []
        import re as _re

        for m in _re.finditer(r"pts_time:([0-9.]+)", out):
            try:
                times.append(round(float(m.group(1)), 3))
            except Exception:
                continue
        return sorted(set(times))[:50]
    except Exception:
        return []


def make_storyboard(path: str, sha: str, duration: float, count: int = 5) -> list[dict[str, Any]]:
    """Extract evenly-spaced keyframe thumbnails (real frames, timestamped)."""
    tools = _tools()
    ffmpeg = tools.get("ffmpeg")
    if not ffmpeg or not duration or duration <= 0:
        return []
    FRAMES_DIR.mkdir(parents=True, exist_ok=True)
    stamps = [round(duration * (i + 1) / (count + 1), 3) for i in range(count)]
    boards: list[dict[str, Any]] = []
    for t in stamps:
        img = FRAMES_DIR / f"{sha[:16]}_{str(t).replace('.', 'p')}.jpg"
        if not img.exists():
            try:
                r = subprocess.run(
                    [ffmpeg, "-hide_banner", "-nostats", "-loglevel", "error",
                     "-ss", str(t), "-i", str(path), "-vframes", "1",
                     "-q:v", "4", str(img)],
                    capture_output=True, text=True, timeout=60,
                )
                if r.returncode != 0 or not img.exists():
                    continue
            except Exception:
                continue
        try:
            boards.append({"t": t, "image": str(img), "bytes": img.stat().st_size})
        except Exception:
            continue
    return boards


def analyze_media(path: str) -> dict[str, Any]:
    """Analyze one MP4 (or webm/mov) with measured data only. Cached.

    Returns dict with cache_hit flag. No scene/dialogue invention: only
    measured duration/fps/resolution/audio/scene timestamps + thumbnails.
    """
    from storage import sha256_file

    p = Path(str(path or ""))
    if not p.is_file():
        raise FileNotFoundError(f"media file not found: {path}")
    sha = sha256_file(p)
    key = f"{sha}:{ANALYZER_VERSION}"
    cache = _read_json(CACHE_FILE, {})
    if not isinstance(cache, dict):
        cache = {}
    if key in cache and isinstance(cache[key], dict):
        hit = dict(cache[key])
        hit["cache_hit"] = True
        return hit

    probe = ffprobe_media(str(p))
    vstreams = [s for s in (probe.get("streams") or []) if s.get("codec_type") == "video"]
    astreams = [s for s in (probe.get("streams") or []) if s.get("codec_type") == "audio"]
    v = vstreams[0] if vstreams else {}
    a = astreams[0] if astreams else {}
    try:
        duration = float((probe.get("format") or {}).get("duration") or 0.0)
    except Exception:
        duration = 0.0
    fps = _fps(v.get("avg_frame_rate") or v.get("r_frame_rate"))

    audio: dict[str, Any] = {"has_audio": bool(astreams)}
    try:
        from local_analyzer import measure_audio_with_tools

        measured = measure_audio_with_tools(str(p))
        if isinstance(measured, dict):
            audio.update({k: measured.get(k) for k in
                          ("codec", "sample_rate", "channels", "duration",
                           "mean_volume_db", "peak_volume_db", "decoded") if k in measured})
    except Exception:
        pass
    if not a and not audio.get("has_audio"):
        audio["has_audio"] = False

    scenes = detect_scenes(str(p))
    boards = make_storyboard(str(p), sha, duration)

    result = {
        "sha256": sha,
        "analyzer_version": ANALYZER_VERSION,
        "path": str(p),
        "size_bytes": p.stat().st_size,
        "duration": duration,
        "fps": fps,
        "width": v.get("width"),
        "height": v.get("height"),
        "vcodec": v.get("codec_name", ""),
        "acodec": a.get("codec_name", ""),
        "sample_rate": a.get("sample_rate"),
        "channels": a.get("channels"),
        "audio": audio,
        "scenes": scenes,
        "storyboard": boards,
        "measured_at": _now(),
        "cache_hit": False,
    }
    cache[key] = {k: v2 for k, v2 in result.items() if k != "cache_hit"}
    _write_json(CACHE_FILE, cache)
    return result


def get_run_videos(project_id: str, run_id: str) -> tuple[dict, list[dict]]:
    """Read P1 run + videos from SQLite only (never network)."""
    import project_store as _store

    run = _store.get_run(run_id)
    if str(run.get("project_id", "")) != str(project_id):
        raise KeyError("run does not belong to this project")
    vids = list(run.get("videos") or [])
    vids.sort(key=lambda v: (int(v.get("rank") or 999), -int(v.get("score") or 0)))
    return run, vids


def video_detail(project_id: str, run_id: str, video_id: str) -> dict[str, Any]:
    """Video Lab detail: URL/creator/metrics/score/reason/rights (offline)."""
    _, vids = get_run_videos(project_id, run_id)
    for v in vids:
        if str(v.get("id", "")) == str(video_id):
            return {
                "video_id": v.get("id", ""),
                "source_url": v.get("source_url", ""),
                "creator": v.get("creator", ""),
                "title": v.get("title", ""),
                "views": v.get("views", 0),
                "likes": v.get("likes", 0),
                "comments": v.get("comments", 0),
                "shares": v.get("shares", 0),
                "duration": v.get("duration", 0),
                "posted_at": v.get("posted_at", ""),
                "age_days": v.get("age_days"),
                "score": v.get("score", 0),
                "relevance": v.get("relevance", 0),
                "trend": v.get("trend", 0),
                "status": v.get("status", ""),
                "certainty": v.get("certainty", ""),
                "rights_status": v.get("rights", "UNKNOWN"),
                "reason": v.get("reason", ""),
                "evidence": v.get("evidence", ""),
                "rank": v.get("rank", 0),
            }
    raise KeyError("video not found in this run")


def pick_best(videos: list[dict]) -> dict[str, Any]:
    """Pick highest-score rights-permitted candidate. No random.

    Returns {"chosen": video} or {"status": "RIGHTS_REQUIRED", "skipped": [...]}.
    Never touches a non-permitted video.
    """
    ordered = sorted(list(videos or []),
                     key=lambda v: (-int(v.get("score") or 0), int(v.get("rank") or 999)))
    skipped: list[dict] = []
    for v in ordered:
        rights = str(v.get("rights", v.get("rights_status", "UNKNOWN")))
        if rights in PERMITTED_RIGHTS:
            return {"chosen": v, "skipped": skipped}
        skipped.append({"video_id": v.get("id", ""), "source_url": v.get("source_url", ""),
                        "score": v.get("score", 0), "rights": rights})
    return {"status": "RIGHTS_REQUIRED", "skipped": skipped,
            "reason": "no permitted video in TOP list"}


def _record_asset(project_id: str, run_id: str, video_id: str, local_path: str, status: str) -> dict:
    import project_store as _store
    import sqlite3

    conn = _store.connect()
    try:
        row = conn.execute(
            "SELECT * FROM media_assets WHERE video_id=?", (video_id,)).fetchone()
        if row:
            conn.execute("UPDATE media_assets SET local_path=?,status=? WHERE video_id=?",
                         (local_path, status, video_id))
        else:
            import uuid as _uuid

            conn.execute(
                "INSERT INTO media_assets(id,video_id,project_id,run_id,local_path,status,created_at)"
                " VALUES(?,?,?,?,?,?,?)",
                (f"asset_{_uuid.uuid4().hex[:12]}", video_id, project_id, run_id,
                 local_path, status, _now()))
        conn.commit()
        cur = conn.execute("SELECT * FROM media_assets WHERE video_id=?", (video_id,)).fetchone()
        return dict(cur) if cur else {}
    finally:
        conn.close()


def get_asset(video_id: str) -> dict | None:
    import project_store as _store

    conn = _store.connect()
    try:
        row = conn.execute("SELECT * FROM media_assets WHERE video_id=?", (video_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def download_video(project_id: str, run_id: str, video: dict,
                   local_source: str = "") -> dict[str, Any]:
    """Download/import one chosen video. Rights checked first; no duplicates."""
    from library import ContentLibrary
    from ingest import ingest_video, IngestError

    rights = str(video.get("rights", video.get("rights_status", "UNKNOWN")))
    if rights not in PERMITTED_RIGHTS:
        return {"status": "RIGHTS_REQUIRED", "video_id": video.get("id", ""),
                "source_url": video.get("source_url", ""),
                "reason": f"rights={rights}: no download of non-permitted video"}
    vid = str(video.get("id", ""))
    # Idempotence 1: existing asset
    existing = get_asset(vid)
    if existing and existing.get("local_path") and Path(str(existing["local_path"])).exists():
        return {"status": "ALREADY_DOWNLOADED", "video_id": vid,
                "source_url": video.get("source_url", ""),
                "local_path": existing["local_path"], "duplicate": True}
    # Idempotence 2: library already has this source
    from pathlib import Path as _P

    _lib_path = _P(LIBRARY_PATH) if LIBRARY_PATH else None
    lib = ContentLibrary(path=_lib_path) if _lib_path else ContentLibrary()
    try:
        if lib.contains_source(str(video.get("source_url", ""))):
            entry = lib.find_by_source(str(video.get("source_url", ""))) or {}
            lp = str(entry.get("path", ""))
            if lp:
                _record_asset(project_id, run_id, vid, lp, "READY")
            return {"status": "ALREADY_DOWNLOADED", "video_id": vid,
                    "source_url": video.get("source_url", ""),
                    "local_path": lp, "duplicate": True}
    except Exception:
        pass
    source = str(local_source or "").strip() or str(video.get("source_url", ""))
    import re as _re

    _safe = _re.sub(r"[^A-Za-z0-9_-]+", "-", f"{project_id}-{run_id}-{vid}").strip("-") or vid
    task_id = f"p2-{_safe}"[:80]
    try:
        meta = ingest_video(
            source, task_id,
            rights_verified=True, permission=True,
            rights_evidence=f"allowlist permit for {video.get('creator','')} ({rights})",
            library=lib,
        )
    except IngestError as exc:
        msg = str(exc)
        if "Duplicate content" in msg or "already in the library" in msg:
            entry = lib.find_by_source(str(video.get("source_url", ""))) or {}
            lp = str(entry.get("path", ""))
            if lp:
                _record_asset(project_id, run_id, vid, lp, "READY")
            return {"status": "ALREADY_DOWNLOADED", "video_id": vid,
                    "source_url": video.get("source_url", ""),
                    "local_path": lp, "duplicate": True, "note": msg[:300]}
        return {"status": "DOWNLOAD_FAILED", "video_id": vid,
                "source_url": video.get("source_url", ""), "error": msg[:500]}
    lp = str(meta.get("path", ""))
    _record_asset(project_id, run_id, vid, lp, "READY")
    return {"status": "DOWNLOADED", "video_id": vid,
            "source_url": video.get("source_url", ""), "local_path": lp,
            "sha256": meta.get("sha256", ""), "duplicate": False}


def auto_download_best(project_id: str, run_id: str,
                       media_map: dict[str, str] | None = None) -> dict[str, Any]:
    """Select best permitted video and download/import only it."""
    _, vids = get_run_videos(project_id, run_id)
    if not vids:
        return {"status": "NO_VIDEOS", "reason": "run has no videos"}
    decision = pick_best(vids)
    if "chosen" not in decision:
        return {"status": "RIGHTS_REQUIRED", "skipped": decision.get("skipped", []),
                "reason": decision.get("reason", "")}
    chosen = decision["chosen"]
    media_map = dict(media_map or {})
    local = media_map.get(str(chosen.get("source_url", "")), "")
    result = download_video(project_id, run_id, chosen, local_source=local)
    result["skipped"] = decision.get("skipped", [])
    result["chosen_score"] = chosen.get("score", 0)
    return result


def settings_get() -> dict[str, Any]:
    data = _read_json(SETTINGS_FILE, {})
    return {"auto_download_best": bool((data or {}).get("auto_download_best", False))} \
        if isinstance(data, dict) else {"auto_download_best": False}


def settings_set(enabled: bool) -> dict[str, Any]:
    _write_json(SETTINGS_FILE, {"auto_download_best": bool(enabled), "updated_at": _now()})
    return settings_get()
