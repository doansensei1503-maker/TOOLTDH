"""P3.1 targeted offline test: critical publishing fix (fixture MP4 + fake publisher)."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="p31_"))
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

FIXTURE = Path("data/temp/snaptik-lib-test.mp4").resolve()
assert FIXTURE.is_file() and FIXTURE.stat().st_size > 1_000_000, f"missing MP4 fixture: {FIXTURE}"

src = Path("p3_publish.py").read_text(encoding="utf-8")
assert "PUBLISHED_URL_RE" in src and "_is_verified_post" in src and "_claim" in src, "verification fix missing"
assert "draft_reference" in src and 'mode"] = "auto"' in src or '["mode"] = "auto"' in src, "adapter fix missing"
sch = Path("scheduler.py").read_text(encoding="utf-8")
assert "run_p3_auto_pass" in sch and "toolt-dh-p3-auto" in sch, "scheduler wiring missing"

proj = store.create_project("P31Pub", "Naruto mix")
pid = proj["id"]


def _v(url, title, score=80):
    return {"source_url": url, "canonical_key": url, "creator": "ok_creator", "title": title,
            "views": 50000, "likes": 2000, "comments": 100, "shares": 50,
            "duration_seconds": 19.0, "posted_at": "2026-10-20", "age_days": 20,
            "score": score, "relevance": 40, "trend": score, "status": "VERIFIED",
            "certainty": "HIGH", "rights": "ALLOWLISTED_PERMITTED", "reason": "keyword+metadata",
            "evidence": "keyword+metadata"}


def _mk_pub(tag: str):
    url = f"https://www.tiktok.com/@ok_creator/video/93{tag}"
    r = store.create_run(pid, filters={}, queries=["Naruto mix q"], funnel={}, top5=[],
                         videos=[_v(url, f"Naruto mix video {tag}")], idempotency_key=f"p31-{tag}")
    run_id = r["run"]["id"]
    run = store.get_run(run_id)
    vid = next(v["id"] for v in run["videos"] if v["source_url"] == url)
    c = svc.p3_publication_create(project_id=pid, run_id=run_id, video_id=vid)
    pubid = c["publication"]["id"]
    b = svc.p3_caption_build(publication_id=pubid)
    assert b["publication_id"] == pubid and b["caption"] and 3 <= len(b["hashtags"]) <= 5
    svc.p3_caption_save(publication_id=pubid, caption=b["caption"], hashtags=b["hashtags"])
    # point at the real fixture file as the MediaAsset (offline real file)
    import sqlite3 as _sq
    _cx = _sq.connect(str(pub.DB_PATH))
    _cx.execute("UPDATE publications SET media_path=? WHERE id=?", (str(FIXTURE), pubid))
    _cx.commit()
    _cx.close()
    return pubid


def _hist_published() -> list:
    try:
        import json as _j
        data = _j.loads((TMP / "history.json").read_text(encoding="utf-8"))
        return [e for e in data if e.get("status") == "PUBLISHED"]
    except Exception:
        return []


# 4) unapproved -> publisher NOT called
p_un = _mk_pub("001")
calls_un: list = []
out_un = pub.run_due(publisher=lambda p: (calls_un.append(p), {"status": "PUBLISHED",
    "posted_url": "https://www.tiktok.com/@ok_creator/video/11111"})[1], db_path=pub.DB_PATH)
assert calls_un == [], (out_un, calls_un)
assert pub.get_publication(p_un, pub.DB_PATH)["status"] == "CAPTION_READY"

# 1) DRAFT_SAVED + draft_reference -> absolutely NOT PUBLISHED (incl. fake posted_id spoof)
p_draft = _mk_pub("002")
svc.p3_approve(publication_id=p_draft)
svc.p3_schedule(publication_id=p_draft, scheduled_at="2020-01-01T00:00:00", account="")
calls_d: list = []


def _fake_draft(p):
    calls_d.append(p)
    return {"status": "DRAFT_SAVED", "posted_url": "",
            "posted_id": "tiktokstudio-draft-123",
            "draft_reference": "https://www.tiktokstudio.com/draft/abc123",
            "message": "Draft saved; human approval required"}


out_d = pub.run_due(publisher=_fake_draft, db_path=pub.DB_PATH)
hit_d = [o for o in out_d if o.get("id") == p_draft]
assert len(calls_d) == 1 and hit_d and hit_d[0]["status"] == "PUBLISH_UNKNOWN", (out_d, calls_d)
st_d = pub.get_publication(p_draft, pub.DB_PATH)
assert st_d["status"] == "PUBLISH_UNKNOWN" and not st_d["posted_url"] and not st_d["posted_id"], st_d
assert _hist_published() == [], "draft must never write PUBLISHED history"

# 1b) PUBLISHED status but draft/studio URL evidence -> still NOT PUBLISHED
p_spoof = _mk_pub("003")
svc.p3_approve(publication_id=p_spoof)
svc.p3_schedule(publication_id=p_spoof, scheduled_at="2020-01-01T00:00:00", account="")


def _fake_spoof(p):
    return {"status": "PUBLISHED", "posted_url": "https://www.tiktokstudio.com/upload",
            "posted_id": "tiktokstudio-draft-999"}


out_s = pub.run_due(publisher=_fake_spoof, db_path=pub.DB_PATH)
hit_s = [o for o in out_s if o.get("id") == p_spoof]
assert hit_s and hit_s[0]["status"] == "PUBLISH_UNKNOWN", out_s
assert _hist_published() == [], "spoof must never write PUBLISHED history"

# 2) no URL/ID confirmation -> PUBLISH_UNKNOWN, never reposted
p_nourl = _mk_pub("004")
svc.p3_approve(publication_id=p_nourl)
svc.p3_schedule(publication_id=p_nourl, scheduled_at="2020-01-01T00:00:00", account="")
calls_n: list = []
out_n = pub.run_due(publisher=lambda p: (calls_n.append(p), {})[1], db_path=pub.DB_PATH)
hit_n = [o for o in out_n if o.get("id") == p_nourl]
assert len(calls_n) == 1 and hit_n and hit_n[0]["status"] == "PUBLISH_UNKNOWN", (out_n, calls_n)
out_n2 = pub.run_due(publisher=lambda p: (calls_n.append(p), {})[1], db_path=pub.DB_PATH)
assert len(calls_n) == 1, out_n2

# 3) verified PUBLISHED + real URL -> PUBLISHED + history (posted_id derived from URL only)
p_ok = _mk_pub("005")
svc.p3_approve(publication_id=p_ok)
svc.p3_schedule(publication_id=p_ok, scheduled_at="2020-01-01T00:00:00", account="")
calls_ok: list = []


def _fake_ok(p):
    calls_ok.append(p)
    assert Path(str(p["media_path"])).is_file()
    assert str(p["caption"]).strip()
    return {"status": "PUBLISHED",
            "posted_url": "https://www.tiktok.com/@ok_creator/video/77777",
            "posted_id": "should-be-ignored-unless-matches"}


out_ok = pub.run_due(publisher=_fake_ok, db_path=pub.DB_PATH)
hit_ok = [o for o in out_ok if o.get("id") == p_ok]
assert len(calls_ok) == 1 and hit_ok and hit_ok[0]["status"] == "PUBLISHED", (out_ok, calls_ok)
st_ok = pub.get_publication(p_ok, pub.DB_PATH)
assert st_ok["status"] == "PUBLISHED" and st_ok["posted_url"].endswith("/video/77777"), st_ok
assert st_ok["posted_id"] == "77777", st_ok  # derived from verified URL, not spoofed id
hp = _hist_published()
assert any(e.get("posted_url", "").endswith("/video/77777") for e in hp), hp

# 5+6) scheduler honors due list and Auto Publish toggle
# (raise hourly/daily caps for the remainder: earlier verified posts already count this hour)
pub.MAX_PER_DAY = 10
pub.MAX_PER_HOUR = 10
import scheduler as _sch
p_sched = _mk_pub("006")
svc.p3_approve(publication_id=p_sched)
svc.p3_schedule(publication_id=p_sched, scheduled_at="2020-01-01T00:00:00", account="")
svc.p3_settings_set(enabled=False)
calls_sch: list = []
_orig_real = pub.real_publisher
pub.real_publisher = lambda cfg: (lambda p: (calls_sch.append(p), {"status": "PUBLISHED",
    "posted_url": "https://www.tiktok.com/@ok_creator/video/88888"})[1])
try:
    r_off = _sch.run_p3_auto_pass(config={"expected_account": ""}, log=lambda m: None)
    assert r_off == "AUTO_OFF" and calls_sch == [], (r_off, calls_sch)
    svc.p3_settings_set(enabled=True)
    r_on = _sch.run_p3_auto_pass(config={"expected_account": ""}, log=lambda m: None)
    assert r_on == "OK" and len(calls_sch) == 1, (r_on, calls_sch)
    assert pub.get_publication(p_sched, pub.DB_PATH)["status"] == "PUBLISHED"
finally:
    pub.real_publisher = _orig_real
svc.p3_settings_set(enabled=False)

# 7) two concurrent runs -> publisher called exactly once
p_race = _mk_pub("007")
svc.p3_approve(publication_id=p_race)
svc.p3_schedule(publication_id=p_race, scheduled_at="2020-01-01T00:00:00", account="")
import threading as _th
calls_race: list = []
import time as _t


def _fake_slow(p):
    calls_race.append(p)
    _t.sleep(0.3)
    return {"status": "PUBLISHED", "posted_url": "https://www.tiktok.com/@ok_creator/video/66666"}


outs: list = []


def _run():
    outs.extend(pub.run_due(publisher=_fake_slow, db_path=pub.DB_PATH))


t1, t2 = _th.Thread(target=_run), _th.Thread(target=_run)
t1.start()
t2.start()
t1.join()
t2.join()
assert len(calls_race) == 1, (len(calls_race), outs)
assert pub.get_publication(p_race, pub.DB_PATH)["status"] == "PUBLISHED"

# 8) restart -> state survives, no duplicate post
outs2 = pub.run_due(publisher=_fake_slow, db_path=pub.DB_PATH)
assert len(calls_race) == 1, outs2
for _pid, _exp in [(p_ok, "PUBLISHED"), (p_draft, "PUBLISH_UNKNOWN"), (p_nourl, "PUBLISH_UNKNOWN"),
                   (p_race, "PUBLISHED"), (p_sched, "PUBLISHED"), (p_un, "CAPTION_READY")]:
    assert pub.get_publication(_pid, pub.DB_PATH)["status"] == _exp, (_pid, _exp)
lst = svc.p3_publications_list()["publications"]
by_id = {p["id"]: p for p in lst}
assert by_id[p_ok]["status"] == "PUBLISHED" and by_id[p_draft]["status"] == "PUBLISH_UNKNOWN"

print(f"P3.1 PASS: draft!=published; no-url->UNKNOWN; verified->PUBLISHED+history; "
      f"unapproved blocked; sched AUTO_OFF/ON ok; race x2->1 post; restart-safe")
