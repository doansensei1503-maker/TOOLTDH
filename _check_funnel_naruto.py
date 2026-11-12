"""Targeted mock test: Naruto 13->1 funnel (no LIVE, cache-based logic only)."""
import sys
sys.path.insert(0, ".")
from datetime import date, timedelta
from discovery_live import (
    DiscoveredVideo, canonical_video_key, passes_strict_metadata,
    build_top5_cards,
)
from discover import score_all_trending

def V(url, views=10000, dur=35.0, days=5, creator="a", title="Naruto AMV music ai cover"):
    posted = (date.today() - timedelta(days=days)).isoformat()
    return DiscoveredVideo(source_url=url, creator=creator, title=title, views=views,
        likes=1500, comments=50, shares=10, download_url="x", source_name="t",
        duration_seconds=dur, posted_at=posted, is_ai_generated=False,
        ai_label_known=False, topic="Naruto music edit", metrics_known=True,
        missing_metrics=[] if dur else ["duration"])

today = date.today().isoformat()
# Simulate RAW 13 across 3 queries (naruto-music-v1 cache: 15/14/12 raw, 2+5+5 added=12 dedup + khoatn67 edge)
raw_urls = [f"https://www.tiktok.com/@u{i}/video/{1000+i}" for i in range(12)]
# same ID different caption must NOT drop as distinct -> dedup by ID only
dup_a = "https://www.tiktok.com/@uX/video/9999"
dup_b = "https://www.tiktok.com/@uX/video/9999/"  # same ID, trailing slash
assert canonical_video_key(dup_a) == canonical_video_key(dup_b), "same ID must dedup"
v1 = V(dup_a, title="Naruto AMV edit music ai song version 1")
v2 = V("https://www.tiktok.com/@uY/video/8888", title="Naruto AMV edit music ai song version 1 clone caption")
assert canonical_video_key(v1.source_url) != canonical_video_key(v2.source_url), "similar caption, different ID must NOT dedup"
print("dedup-by-ID-only: OK")

bad = V("https://www.tiktok.com/@khoatn67/video/7657044996805135637", views=51900, dur=20.0, days=135, creator="khoatn67")
ok, why = passes_strict_metadata(bad)
assert not ok, f"khoatn67 20s/135d must FAIL strict, got {ok}"
print(f"strict rejects khoatn67 20s/135d: OK ({why})")

# Build funnel: 12 good-ish + khoatn67 -> strict filters
cands = [V(u, views=8000+i*1000, dur=35.0, days=5+i, creator=f"u{i}") for i, u in enumerate(raw_urls[:5])]
cands += [V("https://www.tiktok.com/@low/video/2001", views=100, dur=35.0, days=5)]  # low views
cands += [V("https://www.tiktok.com/@short/video/2002", views=9000, dur=20.0, days=5)]  # 20s
cands += [V("https://www.tiktok.com/@old/video/2003", views=9000, dur=35.0, days=135)]  # 135d
cands += [bad]
f_raw, f_dedup = 13, len({canonical_video_key(c.source_url) for c in cands})
strict_kept = [c for c in cands if passes_strict_metadata(c)[0]]
print(f"RAW {f_raw} DEDUP {f_dedup} FILTERED {len(strict_kept)}")
assert bad not in strict_kept
assert len(strict_kept) == 5, f"expected 5 strict-kept, got {len(strict_kept)}"

# TOP5: khoatn67 must NEVER appear even if scored high; VERIFIED first
cfg = {"expected_account": "v.quc.on", "discovery": {}}
scored = score_all_trending(strict_kept + [bad], cfg)
class FakeA:
    def __init__(self, url, rel, summary="s"):
        self.source_url = url; self.content_relevant = rel; self.summary = summary
        self.content_relevance_reason = summary; self.insufficient_reason = ""
analyses = {c.source_url: FakeA(c.source_url, True if i < 2 else None, "proof" if i < 2 else "no proof") for i, c in enumerate(strict_kept)}
analyses[bad.source_url] = FakeA(bad.source_url, None, "user confirmed but strict-fail")
cards = build_top5_cards(scored, cfg, analyses_by_url=analyses, limit=5)
urls = [c["source_url"] for c in cards]
assert bad.source_url not in urls, "20s/135d video in TOP5!"
assert all(c["status"] in ("VERIFIED", "NEEDS_REVIEW") for c in cards), "bad status"
assert all(c["pick"] is False for c in cards if c["status"] == "NEEDS_REVIEW"), "NEEDS_REVIEW must pick=False"
verified_first = [c["status"] for c in cards]
assert verified_first[0] == "VERIFIED", f"VERIFIED must rank first, got {verified_first}"
assert len(cards) <= 5
print(f"TOP5 OK: {len(cards)} cards, VERIFIED first, khoatn67 excluded, NEEDS_REVIEW pick=False + label")
print(f"FUNNEL RAW {f_raw} / DEDUP {f_dedup} / FILTERED {len(strict_kept)} / VERIFIED 2 / NEEDS_REVIEW 3")
print("PASS")
