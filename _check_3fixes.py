"""Targeted mock: 17s loai, 45s nhan, UNKNOWN loai, 3 truy van Naruto khong trung."""
import json, sys, time
sys.path.insert(0, "D:\\TOOLTDH")
from discover import DiscoveredVideo
from discovery_live import (SearchFilters, apply_search_filters, expand_topic_queries,
    discover_new_candidates, NARUTO_QUERIES)

f = SearchFilters(min_views=5000, min_duration=30.0, max_duration=60.0, max_days=30,
                  must_include=[], exclude=["spam", "scam"])
def V(url, dur, missing=False):
    return DiscoveredVideo(source_url=url, creator="t", title="Naruto Shippuden anime music edit fun",
        views=22100, likes=100, comments=10, shares=5, duration_seconds=dur,
        posted_at="2026-11-10", topic="Naruto Shippuden anime music edit",
        metrics_known=not missing, missing_metrics=(["duration"] if missing else []))
kept, dropped = apply_search_filters([
    V("https://www.tiktok.com/@a/video/1", 17.0),
    V("https://www.tiktok.com/@b/video/2", 45.0),
    V("https://www.tiktok.com/@c/video/3", 0.0, True),
], f)
ok_dur = (len(kept) == 1 and kept[0].source_url.endswith("/2")
          and any("17.0" in d and "ngắn hơn" in d for d in dropped)
          and any("UNKNOWN" in d for d in dropped))
qs = expand_topic_queries("Naruto Shippuden anime music edit", max_queries=6)
ok_q = (qs == list(NARUTO_QUERIES) and len(set(q.lower() for q in qs)) == 3)

def _payload():
    return json.dumps({"data": [{"type": 1, "item": {
        "id": "7706585722630753556", "desc": "Naruto Shippuden anime music edit fun",
        "author": {"uniqueId": "dj_xpominki"},
        "stats": {"playCount": 22100, "diggCount": 100, "commentCount": 10, "shareCount": 5},
        "statsV2": {}, "video": {"duration": 45},
        "createTime": 1762819200}}]})
calls = []
def mock_read(term):
    calls.append(term)
    return {"html": "<html>ok</html>", "results": _payload()}
import discovery_live as dl
orig_sleep = time.sleep
time.sleep = lambda s: None
try:
    cands, blockers = discover_new_candidates({"discovery": {}, "expected_account": "v.quc.on"},
        "Naruto Shippuden anime music edit", read_search=mock_read, stats={})
finally:
    time.sleep = orig_sleep
ok_dedup = (len(cands) == 1 and len(calls) == 3)
ok = ok_dur and ok_q and ok_dedup
print(f"dur17_loai_45_nhan_UNKNOWN_loai={ok_dur} queries={qs} dedup={ok_dedup} cands={len(cands)} calls={len(calls)}")
print("PASS 3-fixes" if ok else "FAIL 3-fixes")
sys.exit(0 if ok else 1)
