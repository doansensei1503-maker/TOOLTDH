"""Targeted offline integration acceptance for the P1 search reconstruction.

ONE suite. No network. No real TikTok call. No publishing. No downloading.
The source is a safe injected fixture, so every assertion is about the
behaviour of the product and not about the reachability of a third party.

The suite covers:
  A. GENERAL QUERY PLANNING (3 unrelated topics, no leakage)
  B. FILTER CORRECTNESS (no hidden thresholds, exact limits, UNKNOWN)
  C. COLLECTION DIAGNOSTICS (success / empty / parser error / block / partial)
  D. RELEVANCE (VI/EN equivalence, negatives, weak -> NEEDS_REVIEW)
  E. RANKING (deterministic, correct order, no dupes, no invented metrics)
  F. PROJECT ISOLATION (two projects, independent runs, no leakage)
  G. RUN STATUSES (nonempty / empty / partial / failed / idempotency)
  H. FRONTEND (no misleading placeholder values, payload is empty by default)
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent))

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        PASSED.append(name)
        print(f"  [PASS] {name}")
    else:
        FAILED.append(f"{name}: {detail}")
        print(f"  [FAIL] {name} — {detail}")


def section(title: str) -> None:
    print(f"\n=== {title} ===")


# ---------------------------------------------------------------------------
# A. GENERAL QUERY PLANNING
# ---------------------------------------------------------------------------
section("A. GENERAL QUERY PLANNING")

from query_planner import build_query_plan, normalize_text

TOPICS = [
    "mẹo quay video đẹp bằng điện thoại",
    "Công thức làm bánh tại nhà",
    "Du lịch Đà Lạt",
]

LEAK_TOKENS = ("naruto", "suno", "udio", "ai cover", "ai remix", "anime")

plans = {}
for topic in TOPICS:
    plan = build_query_plan(topic)
    plans[topic] = plan
    texts = plan.query_texts()
    folded = " ".join(normalize_text(t) for t in texts)

    check(f"plan[{topic}]: >=4 queries", len(texts) >= 4, f"got {len(texts)}")
    check(f"plan[{topic}]: <=8 queries (hard ceiling)", len(texts) <= 8, f"got {len(texts)}")
    check(f"plan[{topic}]: queries are distinct", len(set(texts)) == len(texts),
          f"{texts}")
    check(f"plan[{topic}]: topic itself is query #1", texts and texts[0] == topic,
          f"got {texts[:1]}")
    check(f"plan[{topic}]: no Naruto/AI-Music leakage",
          not any(token in folded for token in LEAK_TOKENS), folded)
    check(f"plan[{topic}]: every query has a reason",
          all(q.reason for q in plan.queries), "a query has no reason")
    check(f"plan[{topic}]: every query has a group",
          all(q.group for q in plan.queries), "a query has no group")
    check(f"plan[{topic}]: has >=2 search dimensions", len(plan.dimensions) >= 2,
          f"got {plan.dimensions}")

# The three plans must differ from each other.
phone = set(normalize_text(t) for t in plans[TOPICS[0]].query_texts())
bake = set(normalize_text(t) for t in plans[TOPICS[1]].query_texts())
trip = set(normalize_text(t) for t in plans[TOPICS[2]].query_texts())
check("plans are topic-specific (phone vs bake)", not (phone & bake), f"{phone & bake}")
check("plans are topic-specific (phone vs trip)", not (phone & trip), f"{phone & trip}")
check("plans are topic-specific (bake vs trip)", not (bake & trip), f"{bake & trip}")

# The phone topic must contain the smartphone / mobile angles.
phone_queries = " ".join(plans[TOPICS[0]].query_texts()).lower()
check("phone plan covers mobile filmmaking", "mobile filmmaking" in phone_queries, phone_queries)
check("phone plan covers smartphone videography", "smartphone videography" in phone_queries, phone_queries)
check("phone plan covers a tutorial angle", "tutorial" in phone_queries, phone_queries)

# The baking topic must contain a recipe angle.
bake_queries = " ".join(plans[TOPICS[1]].query_texts()).lower()
check("bake plan covers a recipe angle", "recipe" in bake_queries, bake_queries)
check("bake plan covers home baking", "home baking" in bake_queries, bake_queries)

# The travel topic must contain an English travel angle.
trip_queries = " ".join(plans[TOPICS[2]].query_texts()).lower()
check("trip plan covers an English travel angle", "travel" in trip_queries, trip_queries)

# A plan must never contain a query that names no subject at all.
#
# "step by step guide" or a bare "review" matches almost everything on the
# source. Such a query would make the run look successful while collecting
# content that has nothing to do with the topic, so it is forbidden.
GENERIC_ONLY = (
    "step by step guide", "beginner guide", "quick tips", "review",
    "music", "tutorial", "lifestyle", "travel", "vlog", "diy", "recipe",
)
for topic, plan in plans.items():
    for query in plan.queries:
        folded_query = normalize_text(query.query).strip()
        check(f"plan[{topic}]: no generic-only query '{query.query}'",
              folded_query not in GENERIC_ONLY, folded_query)

# The compound subject of the topic must survive into the plan, so the
# queries point at the user's subject and not at half of it.
check("phone plan keeps the compound 'điện thoại'",
      any("dien thoai" in normalize_text(q) for q in plans[TOPICS[0]].query_texts()),
      plans[TOPICS[0]].query_texts())
check("trip plan keeps the compound 'Du lịch'",
      any("du lich" in normalize_text(q) for q in plans[TOPICS[2]].query_texts()),
      plans[TOPICS[2]].query_texts())

# A topic the dictionary does not know still deserves a real plan.
unknown_plan = build_query_plan("cách trồng rau tại nhà")
check("unknown topic still gets >=4 queries", len(unknown_plan.query_texts()) >= 4,
      f"got {len(unknown_plan.query_texts())}")
check("unknown topic reports a low confidence", unknown_plan.confidence == "low",
      unknown_plan.confidence)


# ---------------------------------------------------------------------------
# B. FILTER CORRECTNESS
# ---------------------------------------------------------------------------
section("B. FILTER CORRECTNESS")

from discovery_live import SearchFilters, apply_search_filters
from discover import DiscoveredVideo


def make_video(url, **kw):
    base = dict(
        source_url=url, creator="creator", title="caption",
        views=1000, likes=50, comments=10, shares=5,
        duration_seconds=45.0, posted_at="2026-01-01", topic="t",
        missing_metrics=[],
    )
    base.update(kw)
    return DiscoveredVideo(**base)


# Empty controls => no constraint at all.
empty_filters = SearchFilters.from_payload({})
check("empty filters have no min_views", empty_filters.min_views == 0)
check("empty filters have no max_days", empty_filters.max_days == 0)
check("empty filters have no duration window",
      empty_filters.min_duration == 0 and empty_filters.max_duration == 0)
check("empty filters have no market", empty_filters.market == "")
check("empty filters have no language", empty_filters.language == "")

# A video with 12 views / 8s / 900 days old passes when no filter is set.
tiny = make_video("https://www.tiktok.com/@a/video/1", views=12, duration_seconds=8.0,
                   posted_at="2020-01-01")
kept, dropped = apply_search_filters([tiny], empty_filters)
check("no hidden threshold: tiny video survives empty filters", len(kept) == 1,
      f"dropped: {dropped}")
check("no hidden threshold: nothing dropped with empty filters", not dropped, f"{dropped}")

# Explicit limits apply exactly.
explicit = SearchFilters.from_payload({"min_views": 100, "max_days": 30, "max_duration": 60})
kept, dropped = apply_search_filters([tiny], explicit)
check("explicit min_views rejects a video below it", len(kept) == 0, f"kept {len(kept)}")
check("rejection reason names the criterion", dropped and "lượt xem" in dropped[0], f"{dropped}")

# A video that passes the explicit limits is kept.
good = make_video("https://www.tiktok.com/@a/video/2", views=5000, duration_seconds=45.0,
                   posted_at="2026-11-10")
kept, dropped = apply_search_filters([good], explicit)
check("explicit limits keep a video that satisfies them", len(kept) == 1, f"dropped {dropped}")

# Unknown metrics are UNKNOWN, not zero and not an invented rejection.
unknown = make_video("https://www.tiktok.com/@a/video/3", views=0, likes=0,
                      missing_metrics=["views", "likes", "comments", "shares"])
kept, dropped = apply_search_filters([unknown], empty_filters)
check("unknown metrics survive an empty filter set", len(kept) == 1, f"dropped {dropped}")
kept, dropped = apply_search_filters([unknown], SearchFilters.from_payload({"min_views": 100}))
check("unknown metrics cannot prove a minimum (rejected honestly)", len(kept) == 0, f"{dropped}")
check("unknown rejection says the data is missing",
      dropped and "không có dữ liệu" in dropped[0], f"{dropped}")

# Numeric 0 means "no minimum".
zero = SearchFilters.from_payload({"min_views": 0, "max_days": 0})
check("numeric 0 means no constraint", zero.min_views == 0 and zero.max_days == 0)


# ---------------------------------------------------------------------------
# C. COLLECTION DIAGNOSTICS
# ---------------------------------------------------------------------------
section("C. COLLECTION DIAGNOSTICS")

import p1_pipeline as pipe

FIXTURE = {
    "source_url": "https://www.tiktok.com/@chef/video/7000000000000000001",
    "creator": "chef", "title": "công thức làm bánh tại nhà dễ nhất",
    "views": 50000, "likes": 3000, "comments": 200, "shares": 150,
    "duration_seconds": 45.0, "posted_at": "2026-11-10", "missing_metrics": [],
}


def fixture_collector(query):
    return [dict(FIXTURE)]


res_ok = pipe.run_pipeline("Công thức làm bánh tại nhà", fixture_collector)
check("success: status COMPLETED_WITH_RESULTS",
      res_ok["status"] == pipe.RUN_STATUS_COMPLETED_WITH_RESULTS, res_ok["status"])
check("success: every query reports QUERY_SUCCESS",
      all(o["status"] == pipe.QUERY_SUCCESS for o in res_ok["query_outcomes"]),
      str([o["status"] for o in res_ok["query_outcomes"]]))
check("success: funnel RAW_RETURNED counted",
      res_ok["funnel"]["RAW_RETURNED"] == len(res_ok["plan"]["queries"]),
      str(res_ok["funnel"]["RAW_RETURNED"]))
check("success: funnel TOP5 <= 5", res_ok["funnel"]["TOP5"] <= 5, str(res_ok["funnel"]["TOP5"]))
check("success: a candidate was produced", len(res_ok["candidates"]) >= 1,
      str(len(res_ok["candidates"])))


def empty_collector(query):
    return []


res_empty = pipe.run_pipeline("Công thức làm bánh tại nhà", empty_collector)
check("empty: status COMPLETED_EMPTY",
      res_empty["status"] == pipe.RUN_STATUS_COMPLETED_EMPTY, res_empty["status"])
check("empty: every query reports QUERY_EMPTY",
      all(o["status"] == pipe.QUERY_EMPTY for o in res_empty["query_outcomes"]),
      str([o["status"] for o in res_empty["query_outcomes"]]))
check("empty: no candidates", len(res_empty["candidates"]) == 0)
check("empty: the reason is explained", bool(res_empty["status_reason"]),
      res_empty["status_reason"])


def parser_error_collector(query):
    raise RuntimeError("JSONDecodeError: Expecting value line 1 column 1")


res_parser = pipe.run_pipeline("Công thức làm bánh tại nhà", parser_error_collector)
check("parser error: status SOURCE_FAILED",
      res_parser["status"] == pipe.RUN_STATUS_SOURCE_FAILED, res_parser["status"])
check("parser error: status is PARSER_ERROR",
      all(o["status"] == pipe.PARSER_ERROR for o in res_parser["query_outcomes"]),
      str([o["status"] for o in res_parser["query_outcomes"]]))
check("parser error: the reason is kept",
      any("JSONDecodeError" in (o.get("note") or "") for o in res_parser["query_outcomes"]),
      str([o.get("note") for o in res_parser["query_outcomes"]]))


def blocked_collector(query):
    raise RuntimeError("Blocked: CAPTCHA verification required")


res_blocked = pipe.run_pipeline("Công thức làm bánh tại nhà", blocked_collector)
check("block: status SOURCE_BLOCKED",
      res_blocked["status"] == pipe.RUN_STATUS_SOURCE_BLOCKED, res_blocked["status"])
check("block: status is SOURCE_BLOCKED",
      all(o["status"] == pipe.SOURCE_BLOCKED for o in res_blocked["query_outcomes"]),
      str([o["status"] for o in res_blocked["query_outcomes"]]))
check("block: no bypass attempt (1 attempt per query)",
      all(o["attempts"] == 1 for o in res_blocked["query_outcomes"]),
      str([o["attempts"] for o in res_blocked["query_outcomes"]]))


def partial_collector(query):
    if "recipe" in query.lower():
        return [dict(FIXTURE)]
    raise RuntimeError("Blocked: bot protection")


res_partial = pipe.run_pipeline("Công thức làm bánh tại nhà", partial_collector)
check("partial: status PARTIAL", res_partial["status"] == pipe.RUN_STATUS_PARTIAL,
      res_partial["status"])
check("partial: at least one query succeeded",
      any(o["status"] == pipe.QUERY_SUCCESS for o in res_partial["query_outcomes"]),
      str([o["status"] for o in res_partial["query_outcomes"]]))
check("partial: the blocked query is reported",
      any(o["status"] == pipe.SOURCE_BLOCKED for o in res_partial["query_outcomes"]),
      str([o["status"] for o in res_partial["query_outcomes"]]))


# ---------------------------------------------------------------------------
# D. RELEVANCE
# ---------------------------------------------------------------------------
section("D. RELEVANCE")

from relevance import score_relevance

# The English equivalent caption matches.
rel_vi = score_relevance("công thức làm bánh tại nhà", "Công thức làm bánh tại nhà")
rel_en = score_relevance("easy home baking recipe tutorial", "Công thức làm bánh tại nhà")
check("relevance: Vietnamese caption matches", rel_vi.status == "VERIFIED", rel_vi.reason)
check("relevance: English equivalent caption matches", rel_en.status == "VERIFIED",
      f"{rel_en.status} {rel_en.reason}")
check("relevance: the English match clears the verified threshold",
      rel_en.score >= 38.0, str(rel_en.score))
check("relevance: the English match carries the concept signal",
      rel_en.signals.get("core_concept", 0) > 0, str(rel_en.signals))
check("relevance: the English match carries the intent signal",
      rel_en.signals.get("related_intent", 0) > 0, str(rel_en.signals))

# An unrelated caption is rejected.
rel_bad = score_relevance("ai hair color transformation tutorial", "Công thức làm bánh tại nhà")
check("relevance: an unrelated caption is rejected", rel_bad.status == "REJECTED",
      f"{rel_bad.status} {rel_bad.reason}")

# A weak caption is NEEDS_REVIEW, not VERIFIED.
rel_weak = score_relevance("bánh", "Công thức làm bánh tại nhà")
check("relevance: weak metadata is NEEDS_REVIEW", rel_weak.status == "NEEDS_REVIEW",
      f"{rel_weak.status} {rel_weak.reason}")
check("relevance: the review reason is explained",
      "xác nhận" in rel_weak.reason or "yếu" in rel_weak.reason, rel_weak.reason)

# A negative keyword rejects.
rel_neg = score_relevance("easy home baking recipe", "Công thức làm bánh tại nhà",
                           exclude=["sponsored"])
check("relevance: a negative keyword can reject",
      score_relevance("sponsored easy home baking recipe", "Công thức làm bánh tại nhà",
                      exclude=["sponsored"]).status == "REJECTED", "not rejected")

# The signals are explainable.
check("relevance: the signals are reported",
      bool(rel_en.signals) and "core_concept" in rel_en.signals, str(rel_en.signals))


# ---------------------------------------------------------------------------
# E. RANKING
# ---------------------------------------------------------------------------
section("E. RANKING")

from trend_scoring import rank_candidates, score_candidate

cand_a = make_video("https://www.tiktok.com/@a/video/9000000000000000001",
                    title="công thức làm bánh tại nhà dễ nhất", views=500000,
                    likes=40000, comments=2000, shares=1500,
                    duration_seconds=45.0, posted_at="2026-11-11")
cand_b = make_video("https://www.tiktok.com/@a/video/9000000000000000002",
                    title="công thức làm bánh tại nhà", views=5000,
                    likes=100, comments=10, shares=5,
                    duration_seconds=45.0, posted_at="2026-11-11")
cand_c = make_video("https://www.tiktok.com/@a/video/9000000000000000003",
                    title="món ngon khác", views=5000000,
                    likes=500000, comments=50000, shares=50000,
                    duration_seconds=45.0, posted_at="2026-11-11")

rel_scores = {
    cand_a.source_url: 90.0,
    cand_b.source_url: 85.0,
    cand_c.source_url: 10.0,
}
age = {c.source_url: 2 for c in (cand_a, cand_b, cand_c)}
ranked = rank_candidates([cand_a, cand_b, cand_c], relevance_by_url=rel_scores, age_by_url=age)
check("ranking: the more relevant video wins", ranked[0][0].source_url == cand_a.source_url,
      ranked[0][0].source_url)
check("ranking: the order is deterministic",
      [x[0].source_url for x in ranked] == [x[0].source_url for x in
                                            rank_candidates([cand_a, cand_b, cand_c],
                                                            relevance_by_url=rel_scores,
                                                            age_by_url=age)],
      "order differs")
check("ranking: the order does not depend on the input order",
      [x[0].source_url for x in rank_candidates([cand_c, cand_b, cand_a],
                                                 relevance_by_url=rel_scores,
                                                 age_by_url=age)]
      == [x[0].source_url for x in ranked], "order differs")
check("ranking: a huge metric cannot beat the relevance",
      ranked[-1][0].source_url == cand_c.source_url, ranked[-1][0].source_url)

# The score reports every contribution.
sc = score_candidate(cand_a, relevance_score=90.0, age_days=2)
check("ranking: the contributions are documented",
      set(sc.contributions) == {"relevance", "reach", "engagement", "velocity",
                                "recency", "evidence"}, str(sc.contributions))
check("ranking: the score is inside 0..100", 0 <= sc.score <= 100, str(sc.score))
check("ranking: views/day is marked as an estimate",
      sc.details.get("views_per_day_estimated") is True, str(sc.details))

# Missing metrics never become a fabricated zero.
unknown_c = make_video("https://www.tiktok.com/@a/video/9000000000000000009",
                       views=0, likes=0, comments=0, shares=0,
                       missing_metrics=["views", "likes", "comments", "shares"])
sc_unknown = score_candidate(unknown_c, relevance_score=80.0, age_days=None)
check("ranking: unknown views stay UNKNOWN",
      sc_unknown.details.get("views") is None, str(sc_unknown.details))
check("ranking: unknown engagement is not a ratio",
      sc_unknown.details.get("engagement_rate") is None, str(sc_unknown.details))
check("ranking: unknown age means no velocity",
      sc_unknown.details.get("views_per_day") is None, str(sc_unknown.details))

# No divide by zero.
zero_views = make_video("https://www.tiktok.com/@a/video/9000000000000000010",
                        views=0, missing_metrics=[])
sc_zero = score_candidate(zero_views, relevance_score=80.0, age_days=3)
check("ranking: zero views does not divide by zero",
      sc_zero.details.get("engagement_rate") is None, str(sc_zero.details))
check("ranking: zero views still scores", sc_zero.score >= 0, str(sc_zero.score))


# ---------------------------------------------------------------------------
# F + G. PROJECT ISOLATION, PERSISTENCE AND RUN STATUSES
# ---------------------------------------------------------------------------
section("F/G. PROJECT ISOLATION, PERSISTENCE AND RUN STATUSES")

import project_store as store

with tempfile.TemporaryDirectory() as tmp:
    db = Path(tmp) / "p1_test.db"
    store.init_db(db)

    proj_a = store.create_project("Project A", "mẹo quay video đẹp bằng điện thoại", db)
    proj_b = store.create_project("Project B", "Du lịch Đà Lạt", db)

    def collector_a(query):
        return [dict(FIXTURE, source_url="https://www.tiktok.com/@chef/video/7000000000000000001",
                     title="mẹo quay video đẹp bằng điện thoại")]

    def collector_b(query):
        return [dict(FIXTURE, source_url="https://www.tiktok.com/@travel/video/7000000000000000002",
                     title="du lịch Đà Lạt mùa lễ hội")]

    res_a = pipe.run_pipeline(proj_a["topic"], collector_a)
    res_b = pipe.run_pipeline(proj_b["topic"], collector_b)

    run_a = store.create_run(proj_a["id"], filters=res_a["filters"], queries=res_a["queries"],
                             funnel=res_a["funnel"], top5=res_a["top5"], videos=res_a["videos"],
                             status=res_a["status"], idempotency_key="key-a",
                             snapshot_extra={"plan": res_a["plan"],
                                             "query_outcomes": res_a["query_outcomes"],
                                             "candidates": res_a["candidates"],
                                             "filter_decisions": res_a["filter_decisions"],
                                             "status_reason": res_a["status_reason"]},
                             db_path=db)
    run_b = store.create_run(proj_b["id"], filters=res_b["filters"], queries=res_b["queries"],
                             funnel=res_b["funnel"], top5=res_b["top5"], videos=res_b["videos"],
                             status=res_b["status"], idempotency_key="key-b",
                             snapshot_extra={"plan": res_b["plan"],
                                             "query_outcomes": res_b["query_outcomes"],
                                             "candidates": res_b["candidates"],
                                             "filter_decisions": res_b["filter_decisions"],
                                             "status_reason": res_b["status_reason"]},
                             db_path=db)

    check("isolation: the runs belong to different projects",
          run_a["run"]["project_id"] == proj_a["id"] and run_b["run"]["project_id"] == proj_b["id"],
          "wrong project")
    check("isolation: the versions are independent",
          run_a["run"]["version"] == "v001" and run_b["run"]["version"] == "v001",
          f'{run_a["run"]["version"]} / {run_b["run"]["version"]}')

    snap_a = json.loads(run_a["run"]["snapshot_json"])
    snap_b = json.loads(run_b["run"]["snapshot_json"])
    check("isolation: project A stores its own plan",
          snap_a["plan"]["topic"] == proj_a["topic"], str(snap_a["plan"].get("topic")))
    check("isolation: project B stores its own plan",
          snap_b["plan"]["topic"] == proj_b["topic"], str(snap_b["plan"].get("topic")))
    check("isolation: project A does not contain project B's topic",
          proj_b["topic"] not in json.dumps(snap_a, ensure_ascii=False), "leak")
    check("isolation: project B does not contain project A's topic",
          proj_a["topic"] not in json.dumps(snap_b, ensure_ascii=False), "leak")
    check("persistence: the candidate pool is stored", len(snap_a["candidates"]) >= 1,
          str(len(snap_a["candidates"])))
    check("persistence: the per-query diagnostics are stored",
          len(snap_a["query_outcomes"]) >= 1, str(len(snap_a["query_outcomes"])))
    check("persistence: the filter decisions are stored",
          "filter_decisions" in snap_a, "missing")

    # The version can be opened offline.
    opened = store.get_run(run_a["run"]["id"], db)
    check("isolation: the version opens offline", opened["id"] == run_a["run"]["id"])
    check("isolation: the offline version belongs to project A",
          opened["project_id"] == proj_a["id"], opened["project_id"])

    # Idempotency: the same key never creates a second run.
    again = store.create_run(proj_a["id"], filters=res_a["filters"], queries=res_a["queries"],
                             funnel=res_a["funnel"], top5=res_a["top5"], videos=res_a["videos"],
                             status=res_a["status"], idempotency_key="key-a", db_path=db)
    check("idempotency: the same key does not create a second run",
          again.get("deduplicated") is True and again["run"]["id"] == run_a["run"]["id"],
          str(again.get("deduplicated")))
    runs_a = store.list_runs(proj_a["id"], db)
    check("idempotency: project A still has exactly one run", len(runs_a) == 1, str(len(runs_a)))

    # A second, different click creates a new version of the SAME project.
    run_a2 = store.create_run(proj_a["id"], filters=res_a["filters"], queries=res_a["queries"],
                              funnel=res_a["funnel"], top5=res_a["top5"], videos=res_a["videos"],
                              status=res_a["status"], idempotency_key="key-a2", db_path=db)
    check("versions: a new click creates v002", run_a2["run"]["version"] == "v002",
          run_a2["run"]["version"])
    check("versions: project B is unaffected", len(store.list_runs(proj_b["id"], db)) == 1,
          str(len(store.list_runs(proj_b["id"], db))))

    # The status is stored as the logical outcome.
    check("status: the logical status is stored",
          run_a["run"]["status"] in (
              pipe.RUN_STATUS_COMPLETED_WITH_RESULTS, pipe.RUN_STATUS_COMPLETED_EMPTY,
              pipe.RUN_STATUS_PARTIAL, pipe.RUN_STATUS_SOURCE_FAILED,
              pipe.RUN_STATUS_SOURCE_BLOCKED, pipe.RUN_STATUS_CANCELLED),
          run_a["run"]["status"])

    # A historical run without the new fields still reads.
    legacy = store.create_run(proj_b["id"], filters={}, queries=["x"], funnel={"raw": 0},
                              top5=[], videos=[], status="COMPLETED",
                              idempotency_key="legacy-key", db_path=db)
    legacy_open = store.get_run(legacy["run"]["id"], db)
    check("history: a legacy run still reads", legacy_open["id"] == legacy["run"]["id"])


# ---------------------------------------------------------------------------
# H. FRONTEND
# ---------------------------------------------------------------------------
section("H. FRONTEND")

web_root = Path(__file__).resolve().parent / "web"
html = (web_root / "index.html").read_text(encoding="utf-8")
js = (web_root / "app.js").read_text(encoding="utf-8")

# The misleading placeholders are gone.
for bad in ('placeholder="US"', 'placeholder="7"', 'placeholder="100000"',
            'placeholder="600"', 'placeholder="AI Music"', 'placeholder="ai cover, ai remix"',
            'placeholder="suno, udio"'):
    check(f"frontend: the misleading placeholder {bad} is gone", bad not in html)

# The filter inputs carry no value attribute, so they submit an empty value.
for field_id in ("disc-min-views", "disc-max-views", "disc-min-likes",
                 "disc-min-comments", "disc-min-shares", "disc-days",
                 "disc-max-duration", "disc-min-duration"):
    marker = f'id="{field_id}"'
    start = html.find(marker)
    check(f"frontend: {field_id} exists", start >= 0, "not found")
    if start >= 0:
        end = html.find(">", start)
        tag = html[start:end]
        check(f"frontend: {field_id} has no default value", " value=" not in tag, tag)

# The empty filter payload sends 0, which means "no constraint".
check("frontend: the empty filter payload uses 0 for numbers",
      'Number(g("disc-min-views")) || 0' not in js and 'num("disc-min-views")' in js,
      "the payload builder was not updated")
check("frontend: language and market are not submitted as filters",
      'language: ""' in js and 'market: ""' in js, "language/market are still submitted")
check("frontend: the strict preset is opt-in only",
      'g("disc-preset") === "strict"' in js, "the preset is not opt-in")

# The main controls have real handlers.
for handler in ("p1Search", "p1Open", "loadP1Runs", "renderP1SearchPlan",
                "renderP1Funnel", "renderP1Diagnostics"):
    check(f"frontend: the handler {handler} exists", f"function {handler}" in js)

# The preview dropdown is hidden when there is no candidate.
check("frontend: the empty preview is handled", "disc-preview-empty" in js or
      "resetPreview" in js, "the empty preview is not handled")

# The search plan and the funnel have a place in the UI.
for element in ("p1-search-plan", "p1-funnel", "p1-diagnostics"):
    check(f"frontend: the element {element} exists", f'id="{element}"' in html)

# The status label maps the logical states.
for status in ("COMPLETED_WITH_RESULTS", "COMPLETED_EMPTY", "PARTIAL",
               "SOURCE_FAILED", "SOURCE_BLOCKED", "CANCELLED"):
    check(f"frontend: the status {status} is labelled", status in js, "missing")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print("\n" + "=" * 60)
print(f"PASSED: {len(PASSED)}   FAILED: {len(FAILED)}")
if FAILED:
    print("\nFAILURES:")
    for item in FAILED:
        print("  - " + item)
    sys.exit(1)
print("ALL OFFLINE ACCEPTANCE CHECKS PASSED")
