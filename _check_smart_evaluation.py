"""Targeted test: smart evaluation buckets (no TikTok, no models)."""
import types
from discovery_live import build_top5_cards

cfg = {"discovery": {"target_topic": "AI Music"}}

def mk(url, creator, views, posted):
    v = types.SimpleNamespace(source_url=url, creator=creator, title="t "+creator,
        views=views, posted_at=posted, ai_label_known=False, is_ai_generated=False)
    return v

verified = mk("https://tiktok.com/@a/video/1", "a", 500000, "2026-11-10T00:00:00")
unknown = mk("https://tiktok.com/@dillyyyy5/video/7705034764155161870", "dillyyyy5", 318700, "2026-11-06T00:00:00")
rejected = mk("https://tiktok.com/@b/video/2", "b", 900000, "2026-11-10T00:00:00")

s1 = types.SimpleNamespace(video=verified, score=85, decision="ACCEPT", reason="ACCEPT: score 85")
s2 = types.SimpleNamespace(video=unknown, score=80, decision="ACCEPT", reason="ACCEPT: score 80")
s3 = types.SimpleNamespace(video=rejected, score=90, decision="ACCEPT", reason="ACCEPT: score 90")

ana = {
    verified.source_url: types.SimpleNamespace(content_relevant=True, summary="AI music proof", content_relevance_reason="proof"),
    unknown.source_url: types.SimpleNamespace(content_relevant=None, summary="", content_relevance_reason="khung hinh cho dau hieu yeu ve noi dung AI"),
    rejected.source_url: types.SimpleNamespace(content_relevant=False, summary="", content_relevance_reason="khong phai AI"),
}

cards = build_top5_cards([s3, s1, s2], cfg, analyses_by_url=ana, limit=5)
by = {c["source_url"]: c for c in cards}
assert verified.source_url in by, "VERIFIED missing"
assert unknown.source_url in by, "NEEDS_REVIEW missing (dillyyyy5 vanished!)"
assert rejected.source_url not in by, "REJECTED leaked into TOP5"
assert by[verified.source_url]["status"] == "VERIFIED" and by[verified.source_url]["pick"] in (True, False)
assert by[unknown.source_url]["status"] == "NEEDS_REVIEW", by[unknown.source_url]
assert by[unknown.source_url]["pick"] is False, "NEEDS_REVIEW must never pick/auto-post"
assert by[unknown.source_url]["views"] == 318700
assert by[unknown.source_url].get("posted_at", "").startswith("2026-11-06")
assert isinstance(by[unknown.source_url].get("age_days"), int)
assert by[unknown.source_url]["score"] == 80, "score must stay untouched (no boost)"
assert ana[unknown.source_url].content_relevant is None, "model verdict mutated!"
print("SMART_EVAL PASS:", [(c["creator"], c["status"], c["pick"], c["score"]) for c in cards])
