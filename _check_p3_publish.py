"""P3 targeted offline test: Caption(non-AI) + Approval + Auto Publish (fixture MP4 + fake publisher)."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="p3_"))
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
import p2_lab as lab
import p3_publish as pub
import dashboard_service as svc

store.DB_PATH = Path(os.environ["P1_DB_PATH"])
lab.CACHE_FILE = Path(os.environ["P2_CACHE_PATH"])
lab.SETTINGS_FILE = Path(os.environ["P2_SETTINGS_PATH"])
lab.FRAMES_DIR = Path(os.environ["P2_FRAMES_DIR"])
lab.LIBRARY_PATH = os.environ["P2_LIBRARY_PATH"]
pub.DB_PATH = Path(os.environ["P1_DB_PATH"])
pub.SETTINGS_FILE = Path(os.environ["P3_SETTINGS_PATH"])

FIXTURE = Path("data/temp/snaptik-lib-test.mp4").resolve()
assert FIXTURE.is_file() and FIXTURE.stat().st_size > 1_000_000, f"missing MP4 fixture: {FIXTURE}"

# non-AI evidence: no model imports in p3 module
src = Path("p3_publish.py").read_text(encoding="utf-8").lower()
for bad in ("gemini", "openai", "gpt", "anthropic", "transformers", "torch"):
    assert bad not in src, f"AI dependency leaked: {bad}"

proj = store.create_project("P3Pub", "Naruto mix")
pid = proj["id"]
URL1 = "https://www.tiktok.com/@ok_creator/video/9100000000000000001"
URL2 = "https://www.tiktok.com/@ok_creator/video/9200000000000000002"


def _v(url, title, score, rights="ALLOWLISTED_PERMITTED"):
    return {"source_url": url, "canonical_key": url, "creator": "ok_creator", "title": title,
            "views": 50000, "likes": 2000, "comments": 100, "shares": 50,
            "duration_seconds": 19.0, "posted_at": "2026-10-20", "age_days": 20,
            "score": score, "relevance": 40, "trend": score, "status": "VERIFIED",
            "certainty": "HIGH", "rights": rights, "reason": "keyword+metadata",
            "evidence": "keyword+metadata"}


r1 = store.create_run(pid, filters={}, queries=["Naruto mix q"], funnel={},
                      top5=[], videos=[_v(URL1, "Naruto mix video one", 88)],
                      idempotency_key="p3-r1")
run_id = r1["run"]["id"]
# asset that P3 publishes: reuse P2 import (rights-checked, single best)
dl = lab.auto_download_best(pid, run_id, media_map={URL1: str(FIXTURE)})
assert dl["status"] in {"DOWNLOADED", "ALREADY_DOWNLOADED"}, dl
run = store.get_run(run_id)
vid1 = next(v["id"] for v in run["videos"] if v["source_url"] == URL1)

# 1+2) create publication + dedupe on same publication_id
c1 = svc.p3_publication_create(project_id=pid, run_id=run_id, video_id=vid1)
p1id = c1["publication"]["id"]
c1b = svc.p3_publication_create(project_id=pid, run_id=run_id, video_id=vid1)
assert c1b.get("deduplicated") is True and c1b["publication"]["id"] == p1id, (c1, c1b)

# 1) non-AI caption 3-5 hashtags, saved under same publication_id
built = svc.p3_caption_build(publication_id=p1id)
assert built["publication_id"] == p1id and built["caption"], built
assert 3 <= len(built["hashtags"]) <= 5, built
saved = svc.p3_caption_save(publication_id=p1id, caption=built["caption"], hashtags=built["hashtags"])
assert saved["publication"]["id"] == p1id and saved["publication"]["caption"] == built["caption"]

# 3) unapproved -> publisher NOT called
calls: list[dict] = []


def _fake_pub_no_url(p: dict) -> dict:
    calls.append(p)
    return {}


out0 = pub.run_due(publisher=_fake_pub_no_url, db_path=pub.DB_PATH)
assert calls == [], (out0, calls)
assert pub.get_publication(p1id, pub.DB_PATH)["status"] == "CAPTION_READY"

# 4) approve + due schedule -> publisher called exactly once
svc.p3_approve(publication_id=p1id)
svc.p3_schedule(publication_id=p1id, scheduled_at="2020-01-01T00:00:00", account="")
assert pub.get_publication(p1id, pub.DB_PATH)["status"] == "SCHEDULED"
out1 = pub.run_due(publisher=_fake_pub_no_url, db_path=pub.DB_PATH)
assert len(calls) == 1 and out1[0]["status"] == "PUBLISH_UNKNOWN", (out1, calls)

# 5) no URL -> NOT PUBLISHED (PUBLISH_UNKNOWN, no retry storm)
st = pub.get_publication(p1id, pub.DB_PATH)
assert st["status"] == "PUBLISH_UNKNOWN" and not st["posted_url"], st
out1b = pub.run_due(publisher=_fake_pub_no_url, db_path=pub.DB_PATH)
assert len(calls) == 1, out1b  # unknown never reposted

# 6) verified URL -> PUBLISHED + history
r2 = store.create_run(pid, filters={}, queries=["Naruto mix q2"], funnel={},
                      top5=[], videos=[_v(URL2, "Naruto mix video two", 77)],
                      idempotency_key="p3-r2")
run2 = r2["run"]["id"]
dl2 = lab.auto_download_best(pid, run2, media_map={URL2: str(FIXTURE)})
assert dl2["status"] in {"DOWNLOADED", "ALREADY_DOWNLOADED"}, dl2
run2v = store.get_run(run2)
vid2 = next(v["id"] for v in run2v["videos"] if v["source_url"] == URL2)
c2 = svc.p3_publication_create(project_id=pid, run_id=run2, video_id=vid2)
p2id = c2["publication"]["id"]
assert p2id != p1id
# Test-only: same MP4 fixture reused for a 2nd video dedupes in Library by SHA;
# point pub2 at the real downloaded file so the publisher uploads a real MediaAsset.
import sqlite3 as _sq

_cx = _sq.connect(str(pub.DB_PATH))
_cx.execute("UPDATE publications SET media_path=? WHERE id=?", (str(dl["local_path"]), p2id))
_cx.commit()
_cx.close()
b2 = svc.p3_caption_build(publication_id=p2id)
svc.p3_caption_save(publication_id=p2id, caption=b2["caption"], hashtags=b2["hashtags"])
svc.p3_approve(publication_id=p2id)
svc.p3_schedule(publication_id=p2id, scheduled_at="2020-01-01T00:00:00", account="")
ok_calls: list[dict] = []


def _fake_pub_ok(p: dict) -> dict:
    ok_calls.append(p)
    assert Path(str(p["media_path"])).is_file(), "must upload real MediaAsset"
    assert str(p["caption"]).strip(), "must use saved caption"
    return {"posted_url": "https://www.tiktok.com/@ok_creator/video/99999", "posted_id": "99999"}


out2 = pub.run_due(publisher=_fake_pub_ok, db_path=pub.DB_PATH)
hit = [o for o in out2 if o.get("id") == p2id]
assert len(ok_calls) == 1 and hit and hit[0]["status"] == "PUBLISHED", (out2, ok_calls)
st2 = pub.get_publication(p2id, pub.DB_PATH)
assert st2["status"] == "PUBLISHED" and "99999" in st2["posted_url"], st2
hist = (TMP / "history.json").read_text(encoding="utf-8")
assert "99999" in hist and p2id in hist, hist

# 7) restart: state survives, no duplicate post on re-run
out3 = pub.run_due(publisher=_fake_pub_ok, db_path=pub.DB_PATH)
assert len(ok_calls) == 1, out3
assert pub.get_publication(p2id, pub.DB_PATH)["status"] == "PUBLISHED"
assert pub.get_publication(p1id, pub.DB_PATH)["status"] == "PUBLISH_UNKNOWN"

# 8) UI/API surfaces match real state + auto_publish toggle independent
lst = svc.p3_publications_list()["publications"]
by_id = {p["id"]: p for p in lst}
assert by_id[p1id]["status"] == "PUBLISH_UNKNOWN" and by_id[p2id]["status"] == "PUBLISHED", lst
assert svc.p3_settings_set(enabled=True)["auto_publish"] is True
assert svc.p3_settings_get()["auto_publish"] is True
assert svc.p3_settings_set(enabled=False)["auto_publish"] is False
html = Path("web/index.html").read_text(encoding="utf-8")
js = Path("web/app.js").read_text(encoding="utf-8")
for needle in ("btn-p3-create", "btn-p3-approve", "btn-p3-schedule", "p3-auto", "p3-caption"):
    assert needle in html, needle
for needle in ("/p3/publication", "/p3/approve", "/p3/schedule", "/p3/caption/save", "/p3/settings"):
    assert needle in js, needle

print(f"P3 PASS: caption(non-AI)+approval ok; queue/dedupe ok; no-url->PUBLISH_UNKNOWN; "
      f"url->PUBLISHED+history; restart-safe; api/ui ok ({p1id[:10]}..,{p2id[:10]}..)")
