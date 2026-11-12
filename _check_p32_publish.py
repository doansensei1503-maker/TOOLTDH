"""P3.2 targeted offline regression: exact Post control (mock page only, real business logic)."""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="p32_"))
os.environ["P1_DB_PATH"] = str(TMP / "p1.db")
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
from poster import find_publish_button, confirm_publish_dialog

store.DB_PATH = Path(os.environ["P1_DB_PATH"])
pub.DB_PATH = Path(os.environ["P1_DB_PATH"])
pub.SETTINGS_FILE = Path(os.environ["P3_SETTINGS_PATH"])
pub.MAX_PER_DAY = 10
pub.MAX_PER_HOUR = 10

FIXTURE = Path("data/temp/snaptik-lib-test.mp4").resolve()
assert FIXTURE.is_file() and FIXTURE.stat().st_size > 1_000_000

# ---- Mock page (TikTok UI responses only) ----


class _El:
    def __init__(self, text, visible=True, enabled=True, log=None):
        self._text = text
        self._vis = visible
        self._ena = enabled
        self._log = log if log is not None else []
        self.clicked = False

    def inner_text(self, timeout=3000):
        return self._text

    def is_visible(self):
        return self._vis

    def is_enabled(self):
        return self._ena

    def click(self):
        self.clicked = True
        self._log.append(self._text)


class _Loc:
    def __init__(self, els):
        self._els = list(els)

    def count(self):
        return len(self._els)

    def nth(self, i):
        return self._els[i]

    @property
    def first(self):
        return self._els[0]


class _Page:
    def __init__(self, url, buttons=None, dialogs=0, log=None):
        self.url = url
        self._buttons = list(buttons or [])
        self._dialogs = dialogs
        self.click_log = log if log is not None else []

    def get_by_role(self, role, name=None):
        if role == "dialog":
            return _Loc([_El("dialog") for _ in range(self._dialogs)])
        if role == "button":
            hits = []
            for b in self._buttons:
                if name is not None and not name.search(b["text"]):
                    continue
                hits.append(_El(b["text"], b.get("visible", True), b.get("enabled", True), self.click_log))
            return _Loc(hits)
        if role == "link":
            return _Loc([])
        return _Loc([])


UPLOAD = "https://www.tiktok.com/tiktokstudio/upload"

# 2) Wrong/disabled Publish control must be detected.
p_wrong = _Page(UPLOAD, buttons=[{"text": "Posts", "visible": True, "enabled": True}])
assert find_publish_button(p_wrong) is None, "Posts tab must not match Post control"
p_dis = _Page(UPLOAD, buttons=[{"text": "Post", "visible": True, "enabled": False}])
assert find_publish_button(p_dis) is None, "disabled Post must be rejected"
p_off = _Page("https://www.tiktok.com/tiktokstudio/content?tab=post",
              buttons=[{"text": "Post", "visible": True, "enabled": True}])
assert find_publish_button(p_off) is None, "off-upload-page must be rejected"
# Exact Post wins over the Posts tab.
log_exact: list = []
p_exact = _Page(UPLOAD, buttons=[{"text": "Posts", "visible": True, "enabled": True},
                                 {"text": "Post", "visible": True, "enabled": True}], log=log_exact)
el = find_publish_button(p_exact)
assert el is not None, "exact Post must be found"
el.click()
assert log_exact == ["Post"], log_exact

# 3) Missing required confirmation must not be treated as success.
assert confirm_publish_dialog(_Page(UPLOAD, dialogs=0)) is True
log_c: list = []
assert confirm_publish_dialog(_Page(UPLOAD, dialogs=1,
                                    buttons=[{"text": "Post", "visible": True, "enabled": True}],
                                    log=log_c)) is True and log_c == ["Post"]
assert confirm_publish_dialog(_Page(UPLOAD, dialogs=1,
                                    buttons=[{"text": "Cancel", "visible": True, "enabled": True}])) is False

# ---- Real business logic: p3_publish.run_due (no mocks of business rules) ----
proj = store.create_project("P32DraftFix", "Naruto mix")
pid = proj["id"]
ACCT = "v.quc.on"


def _v(url, title):
    return {"source_url": url, "canonical_key": url, "creator": "ok_creator", "title": title,
            "views": 50000, "likes": 2000, "comments": 100, "shares": 50,
            "duration_seconds": 19.0, "posted_at": "2026-10-20", "age_days": 20,
            "score": 80, "relevance": 40, "trend": 80, "status": "VERIFIED",
            "certainty": "HIGH", "rights": "ALLOWLISTED_PERMITTED", "reason": "keyword+metadata",
            "evidence": "keyword+metadata"}


def _mk(tag):
    url = f"https://www.tiktok.com/@ok_creator/video/95{tag}"
    r = store.create_run(pid, filters={}, queries=["q"], funnel={}, top5=[],
                         videos=[_v(url, f"clip {tag}")], idempotency_key=f"p32-{tag}")
    run_id = r["run"]["id"]
    run = store.get_run(run_id)
    vid = next(v["id"] for v in run["videos"] if v["source_url"] == url)
    import dashboard_service as svc
    c = svc.p3_publication_create(project_id=pid, run_id=run_id, video_id=vid)
    pubid = c["publication"]["id"]
    b = svc.p3_caption_build(publication_id=pubid)
    svc.p3_caption_save(publication_id=pubid, caption=b["caption"], hashtags=b["hashtags"])
    import sqlite3 as _sq
    _cx = _sq.connect(str(pub.DB_PATH))
    _cx.execute("UPDATE publications SET media_path=? WHERE id=?", (str(FIXTURE), pubid))
    _cx.commit()
    _cx.close()
    svc.p3_approve(publication_id=pubid)
    svc.p3_schedule(publication_id=pubid, scheduled_at="2020-01-01T00:00:00", account=ACCT)
    return pubid


# 1) Save Draft must not become PUBLISHED.
p_draft = _mk("301")
calls_d: list = []
out_d = pub.run_due(publisher=lambda p: (calls_d.append(p), {"status": "DRAFT_SAVED", "posted_url": "",
    "posted_id": "draft-1", "draft_reference": "https://www.tiktokstudio.com/draft/x"})[1],
    expected_account=ACCT, db_path=pub.DB_PATH)
assert len(calls_d) == 1 and [o for o in out_d if o.get("id") == p_draft][0]["status"] == "PUBLISH_UNKNOWN", out_d
assert pub.get_publication(p_draft, pub.DB_PATH)["status"] == "PUBLISH_UNKNOWN"

# 5) Unverified result must remain PUBLISH_UNKNOWN.
p_unv = _mk("302")
out_u = pub.run_due(publisher=lambda p: {"status": "FAILED_RETRYABLE", "posted_url": ""},
                    expected_account=ACCT, db_path=pub.DB_PATH)
assert [o for o in out_u if o.get("id") == p_unv][0]["status"] == "PUBLISH_UNKNOWN", out_u

# 4) Real verified post URL maps to the correct publication.
p_ok = _mk("303")
calls_ok: list = []
out_ok = pub.run_due(publisher=lambda p: (calls_ok.append(p["id"]), {"status": "PUBLISHED",
    "posted_url": "https://www.tiktok.com/@ok_creator/video/88811"})[1],
    expected_account=ACCT, db_path=pub.DB_PATH)
hit = [o for o in out_ok if o.get("id") == p_ok]
assert len([c for c in calls_ok if c == p_ok]) == 1 and hit and hit[0]["status"] == "PUBLISHED", (out_ok, calls_ok)
st = pub.get_publication(p_ok, pub.DB_PATH)
assert st["posted_url"].endswith("/video/88811") and st["posted_id"] == "88811", st
import json as _j
hist = _j.loads((TMP / "history.json").read_text(encoding="utf-8"))
assert any(e.get("posted_url", "").endswith("/video/88811") and e.get("task_id") == p_ok
           for e in hist if e.get("status") == "PUBLISHED"), hist

# 6) Old publication must never be uploaded twice.
out_again = pub.run_due(publisher=lambda p: (calls_ok.append(p["id"]), {"status": "PUBLISHED",
    "posted_url": "https://www.tiktok.com/@ok_creator/video/99999"})[1],
    expected_account=ACCT, db_path=pub.DB_PATH)
assert len([c for c in calls_ok if c == p_ok]) == 1, out_again
assert pub.get_publication(p_ok, pub.DB_PATH)["status"] == "PUBLISHED"

print("P3.2 PASS: exact-post-selected; draft!=published; unverified->unknown; verified->mapped; no-reupload")
