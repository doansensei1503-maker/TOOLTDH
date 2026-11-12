"""P3 FINAL SAFETY GATE targeted test (fixture MP4 + fake publisher only)."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="p3gate_"))
os.environ["P1_DB_PATH"] = str(TMP / "p1.db")
os.environ["P2_CACHE_PATH"] = str(TMP / "lab_cache.json")
os.environ["P2_SETTINGS_PATH"] = str(TMP / "p2_settings.json")
os.environ["P2_FRAMES_DIR"] = str(TMP / "frames")
os.environ["P2_LIBRARY_PATH"] = str(TMP / "library.json")
os.environ["P3_SETTINGS_PATH"] = str(TMP / "p3_settings.json")

import history as _hist

_ORIG = _hist.PublishHistory


class _TmpHistory(_ORIG):
    def __init__(self, json_path=None, markdown_path=None):
        super().__init__(json_path=json_path or TMP / "history.json",
                         markdown_path=markdown_path or TMP / "history.md")


_hist.PublishHistory = _TmpHistory

import project_store as store
import p3_publish as pub
import dashboard_service as svc

store.DB_PATH = Path(os.environ["P1_DB_PATH"])
pub.DB_PATH = Path(os.environ["P1_DB_PATH"])
pub.SETTINGS_FILE = Path(os.environ["P3_SETTINGS_PATH"])
pub.MAX_PER_DAY = 10
pub.MAX_PER_HOUR = 10

FIXTURE = Path("data/temp/snaptik-lib-test.mp4").resolve()
assert FIXTURE.is_file() and FIXTURE.stat().st_size > 1_000_000, f"missing MP4 fixture: {FIXTURE}"

ACCT = "v.quc.on"

proj = store.create_project("P3Gate", "Naruto mix")
pid = proj["id"]


def _v(url, title, score=80):
    return {"source_url": url, "canonical_key": url, "creator": "ok_creator", "title": title,
            "views": 50000, "likes": 2000, "comments": 100, "shares": 50,
            "duration_seconds": 19.0, "posted_at": "2026-10-20", "age_days": 20,
            "score": score, "relevance": 40, "trend": score, "status": "VERIFIED",
            "certainty": "HIGH", "rights": "ALLOWLISTED_PERMITTED", "reason": "keyword+metadata",
            "evidence": "keyword+metadata"}


def _mk(tag: str, account: str = ACCT, approve: bool = True, sched: bool = True):
    url = f"https://www.tiktok.com/@ok_creator/video/94{tag}"
    r = store.create_run(pid, filters={}, queries=["Naruto mix q"], funnel={}, top5=[],
                         videos=[_v(url, f"Naruto mix video {tag}")], idempotency_key=f"gate-{tag}")
    run_id = r["run"]["id"]
    run = store.get_run(run_id)
    vid = next(v["id"] for v in run["videos"] if v["source_url"] == url)
    c = svc.p3_publication_create(project_id=pid, run_id=run_id, video_id=vid)
    pubid = c["publication"]["id"]
    b = svc.p3_caption_build(publication_id=pubid)
    svc.p3_caption_save(publication_id=pubid, caption=b["caption"], hashtags=b["hashtags"])
    import sqlite3 as _sq
    _cx = _sq.connect(str(pub.DB_PATH))
    _cx.execute("UPDATE publications SET media_path=? WHERE id=?", (str(FIXTURE), pubid))
    _cx.commit()
    _cx.close()
    if approve:
        svc.p3_approve(publication_id=pubid)
    if sched:
        svc.p3_schedule(publication_id=pubid, scheduled_at="2020-01-01T00:00:00", account=account)
    return pubid


# 1) CAPTION_READY -> schedule must be BLOCKED (no auto-approval)
p1 = _mk("101", approve=False, sched=False)
assert pub.get_publication(p1, pub.DB_PATH)["status"] == "CAPTION_READY"
try:
    svc.p3_schedule(publication_id=p1, scheduled_at="2020-01-01T00:00:00", account=ACCT)
    raise AssertionError("CAPTION_READY schedule must be blocked")
except svc.ServiceError as e:
    assert "duyệt" in str(e).lower() or "APPROVED" in str(e), e
assert pub.get_publication(p1, pub.DB_PATH)["status"] == "CAPTION_READY"

# 2) APPROVED -> schedule allowed
p2 = _mk("102", approve=False, sched=False)
svc.p3_approve(publication_id=p2)
s2 = svc.p3_schedule(publication_id=p2, scheduled_at="2020-01-01T00:00:00", account=ACCT)
assert s2["publication"]["status"] == "SCHEDULED", s2
assert pub.get_publication(p2, pub.DB_PATH)["status"] == "SCHEDULED"

# 3) empty / mismatched account -> publisher NOT called
p3 = _mk("103", account="", approve=True, sched=True)
calls3: list = []
out3 = pub.run_due(publisher=lambda p: (calls3.append(p), {"status": "PUBLISHED",
    "posted_url": "https://www.tiktok.com/@ok_creator/video/55555"})[1],
    expected_account=ACCT, db_path=pub.DB_PATH)
hit3 = [o for o in out3 if o.get("id") == p3]
assert calls3 == [] or all(c.get("id") != p3 for c in calls3), (out3, calls3)
assert hit3 and hit3[0]["status"] == "ACCOUNT_REQUIRED", (out3, hit3)

p3b = _mk("104", account="someone.else", approve=True, sched=True)
calls3b: list = []
out3b = pub.run_due(publisher=lambda p: (calls3b.append(p), {"status": "PUBLISHED",
    "posted_url": "https://www.tiktok.com/@ok_creator/video/55556"})[1],
    expected_account=ACCT, db_path=pub.DB_PATH)
hit3b = [o for o in out3b if o.get("id") == p3b]
assert all(c.get("id") != p3b for c in calls3b), (out3b, calls3b)
assert hit3b and hit3b[0]["status"] in {"ACCOUNT_REQUIRED", "FAILED"}, (out3b, hit3b)

# 4) two different publications concurrently -> no parallel upload
pa = _mk("105", account=ACCT)
pb = _mk("106", account=ACCT)
import threading as _th
import time as _t
calls4: list = []


def _slow(p):
    calls4.append(p["id"])
    _t.sleep(0.4)
    n = "77701" if p["id"] == pa else "77702"
    return {"status": "PUBLISHED", "posted_url": f"https://www.tiktok.com/@ok_creator/video/{n}"}


outs4: list = []


def _run4():
    outs4.extend(pub.run_due(publisher=_slow, expected_account=ACCT, db_path=pub.DB_PATH))


t1, t2 = _th.Thread(target=_run4), _th.Thread(target=_run4)
t1.start()
t2.start()
t1.join()
t2.join()
# at most one publisher call at a time: count distinct publisher entries across the race
assert len(calls4) <= 2, (calls4, outs4)
# key gate: never two UPLOADING at once -> second worker must report SKIP_ACTIVE for the loser
statuses = sorted(o.get("status", "") for o in outs4)
assert "PUBLISHED" in statuses, (outs4, calls4)
assert "SKIP_ACTIVE" in statuses or len(calls4) == 1, (outs4, calls4)
# no duplicate post of the same publication
from collections import Counter as _C
assert all(v == 1 for v in _C(calls4).values()), (calls4, outs4)

# 5) valid flow still PASS: approve -> schedule -> verified PUBLISHED + history, restart-safe
pv = _mk("107", account=ACCT)
callsv: list = []


def _ok(p):
    callsv.append(p)
    assert Path(str(p["media_path"])).is_file()
    assert str(p["caption"]).strip()
    return {"status": "PUBLISHED", "posted_url": "https://www.tiktok.com/@ok_creator/video/99901"}


outv = pub.run_due(publisher=_ok, expected_account=ACCT, db_path=pub.DB_PATH)
hitv = [o for o in outv if o.get("id") == pv]
assert len([c for c in callsv if c["id"] == pv]) == 1 and hitv and hitv[0]["status"] == "PUBLISHED", (outv, callsv)
stv = pub.get_publication(pv, pub.DB_PATH)
assert stv["status"] == "PUBLISHED" and stv["posted_url"].endswith("/video/99901") and stv["posted_id"] == "99901", stv
import json as _j
hist = _j.loads((TMP / "history.json").read_text(encoding="utf-8"))
assert any(e.get("posted_url", "").endswith("/video/99901") for e in hist if e.get("status") == "PUBLISHED"), hist
outv2 = pub.run_due(publisher=_ok, expected_account=ACCT, db_path=pub.DB_PATH)
assert len([c for c in callsv if c["id"] == pv]) == 1, outv2

print("P3-GATE PASS: sched-blocked-unapproved; approved->sched ok; account-required; no-parallel-upload; valid-flow ok")
