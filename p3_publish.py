"""P3 Caption + Approval + Auto Publish: non-AI, on top of P1/P2 assets.

One publication_id per video, from project_id/run_id/video_id/asset_id.
Caption engine is template + metadata only (no AI/model calls).
Queue enforces: rights check, single active upload, hourly/daily caps,
no duplicate tasks. PUBLISHED only after platform confirms ID/URL.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

DB_PATH = Path(os.environ.get("P1_DB_PATH", "data/state/p1_projects.db"))
SETTINGS_FILE = Path(os.environ.get("P3_SETTINGS_PATH", "data/state/p3_settings.json"))
MAX_PER_DAY = 3
MAX_PER_HOUR = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS publications (
  id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL DEFAULT '',
  run_id TEXT NOT NULL DEFAULT '',
  video_id TEXT NOT NULL DEFAULT '',
  asset_id TEXT NOT NULL DEFAULT '',
  source_url TEXT NOT NULL DEFAULT '',
  media_path TEXT NOT NULL DEFAULT '',
  account TEXT NOT NULL DEFAULT '',
  caption TEXT NOT NULL DEFAULT '',
  hashtags_json TEXT NOT NULL DEFAULT '[]',
  rights TEXT NOT NULL DEFAULT 'UNKNOWN',
  status TEXT NOT NULL DEFAULT 'DRAFT',
  scheduled_at TEXT NOT NULL DEFAULT '',
  posted_url TEXT NOT NULL DEFAULT '',
  posted_id TEXT NOT NULL DEFAULT '',
  error TEXT NOT NULL DEFAULT '',
  attempts INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(video_id)
);
"""

VI_ERRORS = {
    "not_approved": "Bài đăng chưa được duyệt nên không đăng.",
    "rights": "Video không có quyền đăng hợp lệ nên bị từ chối (RIGHTS_REQUIRED).",
    "account": "Tài khoản TikTok đã kết nối không khớp tài khoản đích nên dừng lại.",
    "no_url": "Nền tảng không trả ID/URL xác nhận nên ghi PUBLISH_UNKNOWN, không tự đăng lại.",
    "active": "Đang có một tác vụ upload khác nên chờ lượt.",
    "limit_day": "Đã đạt giới hạn đăng trong ngày nên dừng lại.",
    "limit_hour": "Đã đạt giới hạn đăng trong giờ này nên dừng lại.",
    "future": "Chưa đến lịch đăng nên chờ.",
}


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


def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path = DB_PATH) -> Path:
    import project_store as _store

    _store.init_db(db_path)
    conn = connect(db_path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()
    return Path(db_path)


def _row_to_dict(row: Any) -> dict:
    d = dict(row)
    try:
        d["hashtags"] = json.loads(d.get("hashtags_json") or "[]")
    except Exception:
        d["hashtags"] = []
    return d


def _sync_job(conn: sqlite3.Connection, pub: dict) -> None:
    """Mirror status into P1 publication_jobs table (best effort)."""
    try:
        cur = conn.execute("SELECT * FROM publication_jobs WHERE id=?", (pub["id"],)).fetchone()
        if cur is None:
            conn.execute(
                "INSERT INTO publication_jobs(id,video_id,project_id,run_id,status,scheduled_at,created_at)"
                " VALUES(?,?,?,?,?,?,?)",
                (pub["id"], pub.get("video_id", ""), pub.get("project_id", ""),
                 pub.get("run_id", ""), pub.get("status", ""), pub.get("scheduled_at", ""), _now()),
            )
        else:
            conn.execute("UPDATE publication_jobs SET status=?,scheduled_at=? WHERE id=?",
                         (pub.get("status", ""), pub.get("scheduled_at", ""), pub["id"]))
    except Exception:
        pass


def _get_pub(conn: sqlite3.Connection, publication_id: str) -> dict:
    row = conn.execute("SELECT * FROM publications WHERE id=?", (publication_id,)).fetchone()
    if not row:
        raise KeyError("publication not found")
    return _row_to_dict(row)


def list_publications(db_path: Path = DB_PATH) -> list[dict]:
    init_db(db_path)
    conn = connect(db_path)
    try:
        rows = conn.execute("SELECT * FROM publications ORDER BY created_at ASC").fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def get_publication(publication_id: str, db_path: Path = DB_PATH) -> dict:
    conn = connect(db_path)
    try:
        return _get_pub(conn, publication_id)
    finally:
        conn.close()


def create_publication(project_id: str, run_id: str, video_id: str,
                       db_path: Path = DB_PATH) -> dict:
    """Create (or reuse) one publication per video. No duplicate tasks."""
    import project_store as _store

    init_db(db_path)
    run = _store.get_run(run_id)
    if str(run.get("project_id", "")) != str(project_id):
        raise KeyError("run does not belong to this project")
    video = next((v for v in run.get("videos", []) if str(v.get("id", "")) == str(video_id)), None)
    if video is None:
        raise KeyError("video not found in this run")
    conn = connect(db_path)
    try:
        existing = conn.execute("SELECT * FROM publications WHERE video_id=?", (video_id,)).fetchone()
        if existing:
            return {"publication": _row_to_dict(existing), "deduplicated": True}
        from p2_lab import get_asset

        asset = get_asset(video_id) or {}
        pid = f"pub_{uuid.uuid4().hex[:12]}"
        now = _now()
        conn.execute(
            "INSERT INTO publications(id,project_id,run_id,video_id,asset_id,source_url,media_path,"
            "account,caption,hashtags_json,rights,status,created_at,updated_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (pid, project_id, run_id, video_id, str(asset.get("id", "")),
             str(video.get("source_url", "")), str(asset.get("local_path", "")),
             "", "", "[]", str(video.get("rights", "UNKNOWN")), "DRAFT", now, now),
        )
        pub = _get_pub(conn, pid)
        _sync_job(conn, pub)
        conn.commit()
        return {"publication": pub, "deduplicated": False}
    finally:
        conn.close()


def _tags_for(topic: str, creator: str, title: str) -> list[str]:
    words: list[str] = []
    for token in re.split(r"[^0-9a-zA-Z_]+", f"{topic} {creator} {title}".lower()):
        token = token.strip("_")[:24]
        if len(token) >= 3 and token not in words:
            words.append(token)
        if len(words) >= 4:
            break
    tags = [f"#{w}" for w in words[:3]]
    while len(tags) < 3:
        tags.append("#tiktok")
    return tags[:5]


def build_caption(topic: str, creator: str, title: str) -> dict[str, Any]:
    """Template + metadata caption. No AI, deterministic."""
    title = re.sub(r"\s+", " ", str(title or "")).strip()[:80]
    topic = str(topic or "").strip()[:40]
    creator = str(creator or "").strip().lstrip("@")[:30]
    text = f"{title} | {topic} (via @{creator})" if title and topic else (title or topic or "Video mới")
    if len(text) > 140:
        text = text[:137] + "..."
    return {"caption": text, "hashtags": _tags_for(topic, creator, title)}


def save_caption(publication_id: str, caption: str, hashtags: list[str] | None = None,
                 db_path: Path = DB_PATH) -> dict:
    caption = str(caption or "").strip()
    if not caption:
        raise ValueError("caption rỗng")
    if len(caption) > 150:
        raise ValueError("caption vượt 150 ký tự")
    tags = [str(t).strip() for t in (hashtags or []) if str(t).strip()][:5]
    conn = connect(db_path)
    try:
        pub = _get_pub(conn, publication_id)
        if pub["status"] in {"PUBLISHED", "UPLOADING"}:
            raise ValueError("bài đã đăng/đang đăng nên không sửa caption")
        conn.execute("UPDATE publications SET caption=?,hashtags_json=?,status=?,updated_at=? WHERE id=?",
                     (caption, json.dumps(tags, ensure_ascii=False), "CAPTION_READY", _now(), publication_id))
        pub = _get_pub(conn, publication_id)
        _sync_job(conn, pub)
        conn.commit()
        return pub
    finally:
        conn.close()


def approve(publication_id: str, db_path: Path = DB_PATH) -> dict:
    """Approval binds to publication_id; approved != published."""
    conn = connect(db_path)
    try:
        pub = _get_pub(conn, publication_id)
        if not str(pub.get("caption", "")).strip():
            raise ValueError("chưa có caption nên không duyệt")
        conn.execute("UPDATE publications SET status=?,error=?,updated_at=? WHERE id=?",
                     ("APPROVED", "", _now(), publication_id))
        pub = _get_pub(conn, publication_id)
        _sync_job(conn, pub)
        conn.commit()
        return pub
    finally:
        conn.close()


def schedule(publication_id: str, scheduled_at: str = "", account: str = "",
             db_path: Path = DB_PATH) -> dict:
    conn = connect(db_path)
    try:
        pub = _get_pub(conn, publication_id)
        if pub["status"] not in {"APPROVED", "SCHEDULED", "CAPTION_READY"}:
            raise ValueError("chỉ lên lịch bài đã duyệt (hoặc đã có caption)")
        if pub["status"] == "CAPTION_READY":
            pub["status"] = "APPROVED"
        conn.execute("UPDATE publications SET status=?,scheduled_at=?,account=?,updated_at=? WHERE id=?",
                     ("SCHEDULED", str(scheduled_at or ""), str(account or "").strip(), _now(), publication_id))
        pub = _get_pub(conn, publication_id)
        _sync_job(conn, pub)
        conn.commit()
        return pub
    finally:
        conn.close()


def _counts_today_hour(pubs: list[dict], now: datetime) -> tuple[int, int]:
    day = hour = 0
    for p in pubs:
        if p.get("status") != "PUBLISHED":
            continue
        try:
            ts = datetime.fromisoformat(str(p.get("updated_at", "")))
        except Exception:
            continue
        if ts.date() == now.date():
            day += 1
            if ts.hour == now.hour:
                hour += 1
    return day, hour


def run_due(now: datetime | None = None,
            publisher: Callable[[dict], dict] | None = None,
            expected_account: str = "",
            db_path: Path = DB_PATH) -> list[dict]:
    """Worker: publish due APPROVED/SCHEDULED publications, one at a time.

    publisher(pub) -> {"posted_url":..., "posted_id":...} on success.
    No URL -> PUBLISH_UNKNOWN (no repost). Exceptions -> FAILED.
    """
    moment = now or datetime.now()
    conn = connect(db_path)
    outcomes: list[dict] = []
    try:
        rows = conn.execute("SELECT * FROM publications ORDER BY created_at ASC").fetchall()
        pubs = [_row_to_dict(r) for r in rows]
        if any(p["status"] == "UPLOADING" for p in pubs):
            return [{"status": "SKIP_ACTIVE", "reason": VI_ERRORS["active"]}]
        day, hour = _counts_today_hour(pubs, moment)
        for pub in pubs:
            if pub["status"] not in {"APPROVED", "SCHEDULED"}:
                continue
            if pub["status"] == "SCHEDULED" and str(pub.get("scheduled_at", "")).strip():
                try:
                    if datetime.fromisoformat(pub["scheduled_at"]) > moment:
                        outcomes.append({"id": pub["id"], "status": "WAIT",
                                         "reason": VI_ERRORS["future"]})
                        continue
                except Exception:
                    pass
            if str(pub.get("rights", "")) != "ALLOWLISTED_PERMITTED":
                conn.execute("UPDATE publications SET status=?,error=?,updated_at=? WHERE id=?",
                             ("RIGHTS_REQUIRED", VI_ERRORS["rights"], _now(), pub["id"]))
                _sync_job(conn, _get_pub(conn, pub["id"]))
                conn.commit()
                outcomes.append({"id": pub["id"], "status": "RIGHTS_REQUIRED",
                                 "reason": VI_ERRORS["rights"]})
                continue
            if day >= MAX_PER_DAY:
                outcomes.append({"id": pub["id"], "status": "LIMIT_DAY", "reason": VI_ERRORS["limit_day"]})
                continue
            if hour >= MAX_PER_HOUR:
                outcomes.append({"id": pub["id"], "status": "LIMIT_HOUR", "reason": VI_ERRORS["limit_hour"]})
                continue
            acct = str(pub.get("account", "") or "").strip()
            if expected_account and acct and acct != expected_account:
                conn.execute("UPDATE publications SET status=?,error=?,updated_at=? WHERE id=?",
                             ("FAILED", VI_ERRORS["account"], _now(), pub["id"]))
                _sync_job(conn, _get_pub(conn, pub["id"]))
                conn.commit()
                outcomes.append({"id": pub["id"], "status": "FAILED", "reason": VI_ERRORS["account"]})
                continue
            media = str(pub.get("media_path", ""))
            if not media or not Path(media).is_file():
                conn.execute("UPDATE publications SET status=?,error=?,updated_at=? WHERE id=?",
                             ("FAILED", "Không thấy file MediaAsset thật nên không đăng.", _now(), pub["id"]))
                _sync_job(conn, _get_pub(conn, pub["id"]))
                conn.commit()
                outcomes.append({"id": pub["id"], "status": "FAILED", "reason": "missing media asset"})
                continue
            conn.execute("UPDATE publications SET status=?,attempts=attempts+1,updated_at=? WHERE id=?",
                         ("UPLOADING", _now(), pub["id"]))
            _sync_job(conn, _get_pub(conn, pub["id"]))
            conn.commit()
            try:
                if publisher is None:
                    raise RuntimeError("chưa cấu hình publisher")
                res = publisher(pub) or {}
            except Exception as exc:
                conn.execute("UPDATE publications SET status=?,error=?,updated_at=? WHERE id=?",
                             ("FAILED", f"Lỗi đăng bài: {str(exc)[:300]}", _now(), pub["id"]))
                _sync_job(conn, _get_pub(conn, pub["id"]))
                conn.commit()
                outcomes.append({"id": pub["id"], "status": "FAILED", "reason": str(exc)[:200]})
                continue
            url = str(res.get("posted_url", "") or "").strip()
            pid_post = str(res.get("posted_id", "") or "").strip()
            if not url and not pid_post:
                conn.execute("UPDATE publications SET status=?,error=?,updated_at=? WHERE id=?",
                             ("PUBLISH_UNKNOWN", VI_ERRORS["no_url"], _now(), pub["id"]))
                _sync_job(conn, _get_pub(conn, pub["id"]))
                conn.commit()
                outcomes.append({"id": pub["id"], "status": "PUBLISH_UNKNOWN",
                                 "reason": VI_ERRORS["no_url"]})
                continue
            conn.execute("UPDATE publications SET status=?,posted_url=?,posted_id=?,error=?,updated_at=? WHERE id=?",
                         ("PUBLISHED", url, pid_post, "", _now(), pub["id"]))
            pub2 = _get_pub(conn, pub["id"])
            _sync_job(conn, pub2)
            conn.commit()
            day += 1
            hour += 1
            try:
                from history import PublishHistory

                PublishHistory().record_publish(
                    task_id=pub["id"], platform="tiktok",
                    source_url=pub.get("source_url", ""), posted_url=url,
                    caption=pub.get("caption", ""), status="PUBLISHED",
                    metadata={"publication_id": pub["id"], "hashtags": pub2.get("hashtags", [])},
                )
            except Exception:
                pass
            outcomes.append({"id": pub["id"], "status": "PUBLISHED", "posted_url": url})
        return outcomes
    finally:
        conn.close()


def settings_get(db_path: Path = DB_PATH) -> dict[str, Any]:
    _ = db_path
    data = _read_json(SETTINGS_FILE, {})
    data = data if isinstance(data, dict) else {}
    out = {"auto_publish": bool(data.get("auto_publish", False))}
    out.update({k: v for k, v in data.items() if k != "auto_publish"})
    return out


def settings_set(enabled: bool, db_path: Path = DB_PATH) -> dict[str, Any]:
    _ = db_path
    data = _read_json(SETTINGS_FILE, {})
    data = data if isinstance(data, dict) else {}
    data["auto_publish"] = bool(enabled)
    data["updated_at"] = _now()
    _write_json(SETTINGS_FILE, data)
    return settings_get()
