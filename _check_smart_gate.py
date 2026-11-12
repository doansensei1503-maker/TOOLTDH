"""Targeted gate test: NEEDS_REVIEW cannot queue without user confirm; confirm separate from model."""
import dashboard_service as svc

URL = "https://www.tiktok.com/@dillyyyy5/video/7705034764155161870"
svc._LAST_RESULT = {
    "status": "NO_QUALIFIED_VIDEO",
    "top5": [{
        "source_url": URL, "creator": "dillyyyy5", "title": "t",
        "views": 318700, "posted_at": "2026-11-06T00:00:00", "age_days": 6,
        "score": 80, "certainty": "UNKNOWN", "status": "NEEDS_REVIEW",
        "pick": False, "reason": "NEEDS_REVIEW: dat metadata",
        "rights": "NOT_ALLOWLISTED", "user_confirmed": False,
    }],
    "needs_review": [{"source_url": URL, "creator": "dillyyyy5", "views": 318700,
        "posted_at": "2026-11-06T00:00:00", "reason": "CHUA DU DU LIEU"}],
    "analyses": [{"source_url": URL, "content_relevant": None}],
}
# 1. blocked before confirm
try:
    svc.queue_enqueue(URL)
    raise SystemExit("FAIL: queued without confirm")
except svc.ServiceError as e:
    assert "NEEDS_REVIEW" in str(e), e
# 2. confirm stored separately, model untouched
r = svc.discovery_confirm_content(URL)
assert r["user_confirmed"] is True
ana = [a for a in svc._LAST_RESULT["analyses"] if a["source_url"] == URL][0]
assert ana["content_relevant"] is None, "model verdict mutated!"
card = [c for c in svc._LAST_RESULT["top5"] if c["source_url"] == URL][0]
assert card["user_confirmed"] is True and card["pick"] is False
# 3. still blocked: rights not allowlisted (quyen gate holds)
try:
    svc.queue_enqueue(URL)
    raise SystemExit("FAIL: queued without rights")
except svc.ServiceError:
    pass
print("GATE PASS: blocked pre-confirm; confirm separate; rights gate holds")
