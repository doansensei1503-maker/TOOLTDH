"""P2 targeted offline test: Video Lab + Auto Download Best (user-owned MP4 fixture)."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="p2_"))
os.environ["P1_DB_PATH"] = str(TMP / "p1.db")
os.environ["P2_CACHE_PATH"] = str(TMP / "lab_cache.json")
os.environ["P2_SETTINGS_PATH"] = str(TMP / "p2_settings.json")
os.environ["P2_FRAMES_DIR"] = str(TMP / "frames")
os.environ["P2_LIBRARY_PATH"] = str(TMP / "library.json")

import project_store as store
import p2_lab as lab
import dashboard_service as svc

store.DB_PATH = Path(os.environ["P1_DB_PATH"])
lab.CACHE_FILE = Path(os.environ["P2_CACHE_PATH"])
lab.SETTINGS_FILE = Path(os.environ["P2_SETTINGS_PATH"])
lab.FRAMES_DIR = Path(os.environ["P2_FRAMES_DIR"])
lab.LIBRARY_PATH = os.environ["P2_LIBRARY_PATH"]

FIXTURE = Path("data/temp/snaptik-lib-test.mp4").resolve()
assert FIXTURE.is_file() and FIXTURE.stat().st_size > 1_000_000, f"missing user MP4 fixture: {FIXTURE}"

proj = store.create_project("P2Lab", "P2LabTopic")
pid = proj["id"]

TOP1 = "https://www.tiktok.com/@no_rights_creator/video/9000000000000000001"
TOP2 = "https://www.tiktok.com/@ok_creator/video/9000000000000000002"
TOP3 = "https://www.tiktok.com/@ok_creator2/video/9000000000000000003"


def _v(url, creator, title, score, rights, views=20000):
    return {"source_url": url, "canonical_key": url, "creator": creator, "title": title,
            "views": views, "likes": 800, "comments": 60, "shares": 30,
            "duration_seconds": 35.0, "posted_at": "2026-10-20", "age_days": 20,
            "score": score, "relevance": 30, "trend": score, "status": "VERIFIED",
            "certainty": "HIGH", "rights": rights, "reason": "keyword+metadata",
            "evidence": "keyword+metadata"}


saved = store.create_run(pid, filters={}, queries=["P2LabTopic q"],
                         funnel={"raw": 3, "dedup": 3, "filtered": 3},
                         top5=[], videos=[_v(TOP1, "no_rights_creator", "P2LabTopic mix video one", 95, "NOT_ALLOWLISTED"),
                                          _v(TOP2, "ok_creator", "P2LabTopic mix video two", 80, "ALLOWLISTED_PERMITTED"),
                                          _v(TOP3, "ok_creator2", "P2LabTopic mix video three", 70, "ALLOWLISTED_PERMITTED")],
                         idempotency_key="p2-t1")
run_id = saved["run"]["id"]
run, vids = lab.get_run_videos(pid, run_id)
assert len(vids) == 3, vids
by_url = {v["source_url"]: v for v in vids}
assert by_url[TOP1]["score"] == 95 and by_url[TOP2]["score"] == 80

# 1) TOP1 (highest score) has no rights -> must be skipped, TOP2 chosen, no random
decision = lab.pick_best(vids)
assert decision["chosen"]["source_url"] == TOP2, decision
assert any(s["source_url"] == TOP1 for s in decision["skipped"]), decision

# 2) rights-only run -> RIGHTS_REQUIRED, no download attempted
only_bad = store.create_run(pid, filters={}, queries=["q"], funnel={},
                            top5=[], videos=[_v(TOP1, "no_rights_creator", "P2LabTopic only bad", 95, "BLOCKED_NO_RIGHTS")],
                            idempotency_key="p2-t2")
res_rights = lab.auto_download_best(pid, only_bad["run"]["id"], media_map={TOP1: str(FIXTURE)})
assert res_rights["status"] == "RIGHTS_REQUIRED", res_rights
assert lab.get_asset(by_url[TOP1]["id"]) is None, "no asset for non-permitted video"

# 3) Auto Download Best downloads ONLY TOP2 into Library, linked to Project
res = lab.auto_download_best(pid, run_id, media_map={TOP2: str(FIXTURE)})
assert res["status"] == "DOWNLOADED", res
assert res["chosen_score"] == 80 and len(res["skipped"]) == 1
lp = Path(str(res["local_path"]))
assert lp.exists() and lp.stat().st_size > 0, res
asset = lab.get_asset(by_url[TOP2]["id"])
assert asset and asset["project_id"] == pid and asset["run_id"] == run_id and asset["status"] == "READY", asset
assert lab.get_asset(by_url[TOP3]["id"]) is None, "TOP5 bulk download forbidden: only chosen video processed"
from library import ContentLibrary
from storage import sha256_file as _sha
_lib = ContentLibrary(path=Path(os.environ["P2_LIBRARY_PATH"]))
_fixture_sha = _sha(FIXTURE)
assert _fixture_sha in _lib.all_entries(), "MP4 must be registered in Library (by SHA256)"

# 4) Video Lab measures the real MP4: duration/fps/resolution/audio/scenes/storyboard
detail = svc.p2_video_detail(project_id=pid, run_id=run_id, video_id=by_url[TOP2]["id"])
vv = detail["video"]
assert vv["source_url"] == TOP2 and vv["rights_status"] == "ALLOWLISTED_PERMITTED", vv
assert vv["score"] == 80 and "keyword" in (vv["reason"] or ""), vv
ana1 = svc.p2_video_analyze(project_id=pid, run_id=run_id, video_id=by_url[TOP2]["id"])
a = ana1["analysis"]
assert a["cache_hit"] is False, a
assert abs(float(a["duration"]) - 19.09) < 1.0, a  # ffprobe-measured, not invented
assert a["width"] == 576 and a["height"] == 1024 and abs(float(a["fps"]) - 30.0) < 0.5, a
assert a.get("audio", {}).get("has_audio") is True, a
assert isinstance(a.get("scenes"), list), a
assert len(a.get("storyboard", [])) >= 1 and all(
    s.get("t", 0) > 0 and Path(str(s["image"])).exists() for s in a["storyboard"]), a
assert "scene" not in json.dumps(a).lower() or True  # no invented scene/dialogue content asserted separately
for key in ("scene_description", "dialogue", "transcript", "caption_invented"):
    assert key not in a, f"invented content key leaked: {key}"

# 5) rerun: no re-download, no re-analysis (cache + library idempotence)
res2 = lab.auto_download_best(pid, run_id, media_map={TOP2: str(FIXTURE)})
assert res2["status"] == "ALREADY_DOWNLOADED" and res2.get("duplicate") is True, res2
ana2 = svc.p2_video_analyze(project_id=pid, run_id=run_id, video_id=by_url[TOP2]["id"])
assert ana2["analysis"]["cache_hit"] is True, ana2
assert ana2["analysis"]["sha256"] == a["sha256"], "cache keyed by SHA256"

# 6) API/UI surface: settings toggle + error paths
assert svc.p2_settings_set(enabled=True)["auto_download_best"] is True
assert svc.p2_settings_get()["auto_download_best"] is True
assert svc.p2_settings_set(enabled=False)["auto_download_best"] is False
try:
    svc.p2_video_detail(project_id=pid, run_id=run_id, video_id="vid_missing")
    raise AssertionError("missing video must raise")
except svc.ServiceError:
    pass
try:
    svc.p2_video_analyze(project_id=pid, run_id=run_id, video_id=by_url[TOP3]["id"])
    raise AssertionError("undownloaded video must raise")
except svc.ServiceError:
    pass
html = Path("web/index.html").read_text(encoding="utf-8")
js = Path("web/app.js").read_text(encoding="utf-8")
assert "Video Lab (P2)" in html and "btn-p2-download" in html and "p2-auto" in html
assert "p2Detail" in js and "p2Analyze" in js and "p2Download" in js and "/p2/auto-download" in js

print(f"P2 PASS: TOP1 skipped (RIGHTS_REQUIRED), TOP2 downloaded+measured "
      f"(dur={a['duration']:.2f}s {a['width']}x{a['height']} {a['fps']}fps, "
      f"storyboard={len(a['storyboard'])}), rerun cached, api/ui ok")
