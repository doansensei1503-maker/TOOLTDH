"""P1 non-AI pipeline: plan -> collect -> dedup -> filters -> relevance -> trend -> TOP5.

No AI, no model, no network here. The collector is injected by the caller
(live reader or offline fixture). Evidence is keyword/metadata only.

FOUR FACTS, KEPT APART ON PURPOSE
---------------------------------
1. DISCOVERY ELIGIBILITY - the candidate survived the filters the user set.
2. RELEVANCE             - it belongs to the topic (relevance.py).
3. TREND SCORE           - it is a strong reference (trend_scoring.py).
4. RIGHTS ELIGIBILITY    - it may be reused (rights_status_of).

There is NO hidden threshold anywhere in this pipeline. The only filter
that can reject a candidate is the filter the user actually set, and a
missing metric is UNKNOWN rather than zero.
"""

from __future__ import annotations

from typing import Any, Callable

TOP5_LIMIT = 5
# The number of queries one controlled run may search.
MAX_QUERIES = 6
# The hard ceiling of the planner. A plan never exceeds it.
QUERY_HARD_CEILING = 8
MAX_RETRIES = 3

# The logical run states. They map onto the existing persistence contract.
RUN_STATUS_COMPLETED_WITH_RESULTS = "COMPLETED_WITH_RESULTS"
RUN_STATUS_COMPLETED_EMPTY = "COMPLETED_EMPTY"
RUN_STATUS_PARTIAL = "PARTIAL"
RUN_STATUS_SOURCE_FAILED = "SOURCE_FAILED"
RUN_STATUS_SOURCE_BLOCKED = "SOURCE_BLOCKED"
RUN_STATUS_CANCELLED = "CANCELLED"

# The structured outcome of one query.
QUERY_SUCCESS = "QUERY_SUCCESS"
QUERY_EMPTY = "QUERY_EMPTY"
SOURCE_TIMEOUT = "SOURCE_TIMEOUT"
SOURCE_BLOCKED = "SOURCE_BLOCKED"
LOGIN_REQUIRED = "LOGIN_REQUIRED"
PARSER_ERROR = "PARSER_ERROR"
SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"

# The funnel counters. They are always present, even when they are zero.
FUNNEL_COUNTERS = (
    "RAW_RETURNED",
    "PARSED",
    "DEDUPLICATED",
    "USER_FILTER_PASSED",
    "RELEVANT",
    "NEEDS_REVIEW",
    "RANKED",
    "TOP5",
)


def plan_queries(
    topic: str,
    max_queries: int = MAX_QUERIES,
    max_retries: int = MAX_RETRIES,
) -> dict:
    """Build the deterministic query plan for one topic.

    The plan is general purpose: it recognises concepts and intents from a
    topic-independent dictionary and never injects a hardcoded subject.
    """
    from query_planner import build_query_plan

    topic = str(topic or "").strip()
    if not topic:
        raise ValueError("topic is required")
    ceiling = max(1, min(int(max_queries or MAX_QUERIES), QUERY_HARD_CEILING))
    plan = build_query_plan(topic, max_queries=ceiling, hard_ceiling=QUERY_HARD_CEILING)
    payload = plan.to_dict()
    payload["max_retries"] = min(int(max_retries or MAX_RETRIES), MAX_RETRIES)
    payload["query_count"] = len(plan.queries)
    return payload


def _classify_query_error(note: str) -> str:
    """Return the structured outcome of a failed query."""
    folded = str(note or "").lower()
    if not folded:
        return SOURCE_UNAVAILABLE
    if any(word in folded for word in ("captcha", "verify", "challenge", "blocked", "bot", "forbidden", "403")):
        return SOURCE_BLOCKED
    if any(word in folded for word in ("login", "sign in", "signin", "unauthorized", "401", "log in")):
        return LOGIN_REQUIRED
    if any(word in folded for word in ("timeout", "timed out", "deadline", "net::", "connection")):
        return SOURCE_TIMEOUT
    if any(word in folded for word in ("json", "parse", "decode", "unexpected token", "malformed")):
        return PARSER_ERROR
    return SOURCE_UNAVAILABLE


def _collect_query(
    query: str,
    collector: Callable[[str], list[dict]],
    max_retries: int,
) -> dict:
    """Run one query and return its structured outcome.

    A retry happens only for a transient failure and only inside the small
    bounded budget. A valid, non-empty result is never retried.
    """
    started = _now_iso()
    attempts = 0
    items: list[dict] = []
    note = ""
    status = QUERY_SUCCESS
    for attempt in range(1, max(1, int(max_retries or 1)) + 1):
        attempts = attempt
        try:
            items = list(collector(query) or [])
            note = ""
            if items:
                status = QUERY_SUCCESS
                break
            # A valid but empty result is not an error and is not retried
            # forever: the source answered, it simply had nothing.
            status = QUERY_EMPTY
            note = "Nguồn trả về kết quả rỗng cho truy vấn này."
            break
        except Exception as exc:  # noqa: BLE001 - the reason is classified
            note = f"{type(exc).__name__}: {exc}"
            status = _classify_query_error(note)
            if status in (SOURCE_BLOCKED, LOGIN_REQUIRED):
                # A protection never retries and is never bypassed.
                break
            if attempt >= max(1, int(max_retries or 1)):
                break
    ended = _now_iso()
    return {
        "query": query,
        "status": status,
        "attempts": attempts,
        "started_at": started,
        "ended_at": ended,
        "raw_count": len(items),
        "note": note,
        "items": items,
    }


def _now_iso() -> str:
    """Return the current timestamp in ISO format."""
    from datetime import datetime

    return datetime.now().isoformat(timespec="seconds")


def run_pipeline(
    topic: str,
    collector: Callable[[str], list[dict]],
    filters: dict | None = None,
    subtopics: list[str] | None = None,
    retry_key: str = "",
    custom_queries: list[str] | None = None,
) -> dict:
    """Full P1 pipeline on injected candidates. No network inside except collector."""
    from discovery_live import (
        SearchFilters,
        apply_search_filters,
        canonical_video_key,
        candidate_age_days,
        rights_status_of,
    )
    from discover import DiscoveredVideo
    from relevance import score_relevance
    from trend_scoring import rank_candidates

    topic = str(topic or "").strip()
    filters = dict(filters or {})
    plan = plan_queries(topic)

    # An advanced user may edit the generated plan before the run.
    if custom_queries:
        edited = [str(q).strip() for q in custom_queries if str(q).strip()]
        if edited:
            plan["queries"] = [
                {"query": q, "group": "custom", "reason": "Truy vấn do người dùng chỉnh sửa.", "intent": "", "concepts": [], "weight": 1.0}
                for q in edited[:QUERY_HARD_CEILING]
            ]
            plan["query_count"] = len(plan["queries"])
            plan["customized"] = True

    query_specs = plan.get("queries", [])
    sf = SearchFilters.from_payload(filters)

    # ---------------------------------------------------------------- collect
    raw: list[dict] = []
    query_outcomes: list[dict] = []
    origin_by_url: dict[str, float] = {}
    for spec in query_specs:
        query = str(spec.get("query", "") if isinstance(spec, dict) else spec).strip()
        if not query:
            continue
        outcome = _collect_query(query, collector, plan["max_retries"])
        outcome["group"] = spec.get("group", "") if isinstance(spec, dict) else ""
        outcome["reason"] = spec.get("reason", "") if isinstance(spec, dict) else ""
        outcome["weight"] = float(spec.get("weight", 1.0) or 1.0) if isinstance(spec, dict) else 1.0
        items = outcome.pop("items", [])
        # The query a candidate was actually found with is its origin. The
        # best (highest weighted) origin wins, so a video that several
        # queries found keeps the strongest evidence.
        for item in items:
            if not isinstance(item, dict):
                continue
            url = str(item.get("source_url", "") or "").strip()
            if not url:
                continue
            weight = float(outcome.get("weight", 1.0) or 1.0)
            if url not in origin_by_url or weight > origin_by_url[url]:
                origin_by_url[url] = weight
        raw.extend(items)
        query_outcomes.append(outcome)

    funnel_raw = len(raw)

    # -------------------------------------------- collect -> DiscoveredVideo
    cands: list[DiscoveredVideo] = []
    parsed = 0
    for item in raw:
        if not isinstance(item, dict):
            continue
        url = str(item.get("source_url", "")).strip()
        if not url:
            continue
        parsed += 1
        missing = list(item.get("missing_metrics", []) or [])
        cands.append(DiscoveredVideo(
            source_url=url,
            creator=str(item.get("creator", "") or ""),
            title=str(item.get("title", "") or "")[:300],
            views=int(item.get("views", 0) or 0),
            likes=int(item.get("likes", 0) or 0),
            comments=int(item.get("comments", 0) or 0),
            shares=int(item.get("shares", 0) or 0),
            duration_seconds=float(item.get("duration_seconds", 0) or 0.0),
            posted_at=str(item.get("posted_at", "") or ""),
            topic=topic,
            missing_metrics=missing,
        ))

    # ----------------------------------------------------------------- dedup
    seen: set[str] = set()
    deduped: list[DiscoveredVideo] = []
    deduped_keys: set[str] = set()
    for c in cands:
        try:
            key = canonical_video_key(c.source_url)
        except Exception:
            key = str(c.source_url or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped_keys.add(key)
        deduped.append(c)
    funnel_dedup = len(deduped)

    # --------------------------------------------------------------- filters
    # The user's filters are the ONLY filter. There is no hidden gate here.
    kept_ui, dropped = apply_search_filters(deduped, sf)
    # The strict preset is an explicit, opt-in compatibility mode. It is OFF
    # unless the user selected the named preset.
    if filters.get("strict_preset"):
        from discovery_live import passes_strict_metadata

        strict_kept: list[DiscoveredVideo] = []
        for c in kept_ui:
            try:
                ok, why = passes_strict_metadata(c)
            except Exception:
                ok, why = False, "strict check failed"
            if ok:
                strict_kept.append(c)
            else:
                dropped.append(f"{c.source_url}: preset nghiêm ngặt — {why}")
        kept_ui = strict_kept
    funnel_filtered = len(kept_ui)

    # ------------------------------------------------------------- relevance
    verified: list[DiscoveredVideo] = []
    review: list[DiscoveredVideo] = []
    relevance_by_url: dict[str, float] = {}
    relevance_detail: dict[str, dict] = {}
    exclude_words = list(sf.exclude or [])
    for c in kept_ui:
        origin_weight = origin_by_url.get(c.source_url, 0.0)
        origin = ""
        if origin_weight > 0:
            for outcome in query_outcomes:
                if float(outcome.get("weight", 1.0) or 1.0) == origin_weight:
                    origin = str(outcome.get("query", ""))
                    break
            if not origin:
                origin = plan.get("queries", [{}])[0].get("query", "") if plan.get("queries") else ""
        verdict = score_relevance(
            c.title,
            topic,
            query_origin=origin,
            query_weight=origin_weight,
            exclude=exclude_words,
        )
        relevance_by_url[c.source_url] = verdict.score
        relevance_detail[c.source_url] = verdict.to_dict()
        if verdict.status == "VERIFIED":
            verified.append(c)
        elif verdict.status == "NEEDS_REVIEW":
            review.append(c)

    # ----------------------------------------------------------------- score
    import dashboard_service as _svc

    try:
        config = _svc._load_config()
    except Exception:
        config = {}
    if not isinstance(config, dict):
        config = {}
    disc = dict(config.get("discovery", {}) or {})
    disc["target_topic"] = topic
    config["discovery"] = disc

    age_by_url: dict[str, int | None] = {}
    for c in kept_ui:
        try:
            age_by_url[c.source_url] = candidate_age_days(c)
        except Exception:
            age_by_url[c.source_url] = None

    ranked = rank_candidates(
        list(verified) + list(review),
        relevance_by_url=relevance_by_url,
        age_by_url=age_by_url,
    )
    funnel_ranked = len(ranked)

    # ----------------------------------------------------------------- top5
    # The list is never forced to five. A video enters only when it is
    # verified, or when it needs review and is clearly better than nothing.
    selected: list[tuple[Any, Any]] = []
    for candidate, trend in ranked:
        verdict = relevance_detail.get(candidate.source_url, {})
        if verdict.get("status") == "REJECTED":
            continue
        selected.append((candidate, trend))
        if len(selected) >= TOP5_LIMIT:
            break

    videos: list[dict] = []
    for rank, (candidate, trend) in enumerate(selected, start=1):
        verdict = relevance_detail.get(candidate.source_url, {})
        try:
            rights = rights_status_of(candidate.source_url, config)
        except Exception:
            rights = "UNKNOWN"
        videos.append({
            "source_url": candidate.source_url,
            "canonical_key": canonical_video_key(candidate.source_url),
            "creator": candidate.creator,
            "title": candidate.title,
            "views": candidate.views,
            "likes": candidate.likes,
            "comments": candidate.comments,
            "shares": candidate.shares,
            "duration_seconds": candidate.duration_seconds,
            "posted_at": candidate.posted_at,
            "age_days": age_by_url.get(candidate.source_url),
            "score": round(trend.score, 2),
            "trend": round(trend.score, 2),
            "relevance": round(float(verdict.get("score", 0.0)), 2),
            "relevance_signals": verdict.get("signals", {}),
            "relevance_reason": verdict.get("reason", ""),
            "scoring": trend.to_dict(),
            "status": verdict.get("status", "NEEDS_REVIEW"),
            "certainty": "HIGH" if verdict.get("status") == "VERIFIED" else "UNKNOWN",
            "rights": rights,
            "reason": trend.reason,
            "evidence": verdict.get("reason", ""),
            "rank": rank,
            "missing_metrics": list(candidate.missing_metrics or []),
        })

    # ------------------------------------------------- the candidate pool
    # The broader pool is preserved, not only the selected top 5.
    candidate_pool: list[dict] = []
    for candidate, trend in ranked:
        verdict = relevance_detail.get(candidate.source_url, {})
        candidate_pool.append({
            "source_url": candidate.source_url,
            "canonical_key": canonical_video_key(candidate.source_url),
            "creator": candidate.creator,
            "title": candidate.title,
            "views": candidate.views,
            "likes": candidate.likes,
            "comments": candidate.comments,
            "shares": candidate.shares,
            "duration_seconds": candidate.duration_seconds,
            "posted_at": candidate.posted_at,
            "age_days": age_by_url.get(candidate.source_url),
            "score": round(trend.score, 2),
            "relevance": round(float(verdict.get("score", 0.0)), 2),
            "relevance_signals": verdict.get("signals", {}),
            "relevance_reason": verdict.get("reason", ""),
            "status": verdict.get("status", "NEEDS_REVIEW"),
            "scoring": trend.to_dict(),
            "missing_metrics": list(candidate.missing_metrics or []),
        })

    # -------------------------------------------------------------- funnel
    funnel = {
        "RAW_RETURNED": funnel_raw,
        "PARSED": parsed,
        "DEDUPLICATED": funnel_dedup,
        "USER_FILTER_PASSED": funnel_filtered,
        "RELEVANT": len(verified),
        "NEEDS_REVIEW": len(review),
        "RANKED": funnel_ranked,
        "TOP5": len(videos),
        # The old short names are kept so the existing panels keep working.
        "raw": funnel_raw,
        "parsed": parsed,
        "dedup": funnel_dedup,
        "filtered": funnel_filtered,
        "verified": len(verified),
        "needs_review": len(review),
        "ranked": funnel_ranked,
        "top5": len(videos),
        "rejected": funnel_raw - funnel_filtered,
    }

    # --------------------------------------------------------- run status
    statuses = [str(item.get("status", "")) for item in query_outcomes]
    blocked = [s for s in statuses if s in (SOURCE_BLOCKED, LOGIN_REQUIRED)]
    failed = [s for s in statuses if s in (SOURCE_TIMEOUT, SOURCE_UNAVAILABLE, PARSER_ERROR)]
    succeeded = [s for s in statuses if s in (QUERY_SUCCESS, QUERY_EMPTY)]

    if not query_outcomes:
        status = RUN_STATUS_SOURCE_FAILED
        status_reason = "Không có truy vấn nào để chạy."
    elif len(blocked) == len(query_outcomes):
        status = RUN_STATUS_SOURCE_BLOCKED
        status_reason = "Nguồn bị chặn hoặc yêu cầu đăng nhập trên mọi truy vấn."
    elif blocked or failed:
        if videos or verified or review:
            status = RUN_STATUS_PARTIAL
        else:
            status = RUN_STATUS_SOURCE_FAILED
        status_reason = (
            f"{len(blocked)} truy vấn bị chặn, {len(failed)} truy vấn lỗi nguồn, "
            f"{len(succeeded)} truy vấn đọc được."
        )
    elif videos:
        status = RUN_STATUS_COMPLETED_WITH_RESULTS
        status_reason = f"Thu thập và phân tích xong {len(videos)} video."
    else:
        status = RUN_STATUS_COMPLETED_EMPTY
        status_reason = (
            "Nguồn đọc được nhưng không video nào đạt yêu cầu lọc và liên quan "
            "(xem kết quả từng bộ lọc)."
        )

    return {
        "topic": topic,
        "plan": plan,
        "queries": [str(spec.get("query", "") if isinstance(spec, dict) else spec) for spec in query_specs],
        "query_outcomes": query_outcomes,
        "query_stats": {
            str(item.get("query", "")): {
                "status": item.get("status"),
                "returned": item.get("raw_count", 0),
                "note": item.get("note", ""),
                "attempts": item.get("attempts", 0),
                "started_at": item.get("started_at", ""),
                "ended_at": item.get("ended_at", ""),
            }
            for item in query_outcomes
        },
        "funnel": funnel,
        "status": status,
        "status_reason": status_reason,
        "top5": videos,
        "videos": videos,
        "candidates": candidate_pool,
        "filter_decisions": dropped,
        "filters": sf.to_dict(),
        "retry_key": retry_key,
    }


def download_plan(video: dict) -> dict:
    """P2 contract (data only, no execution in P1)."""
    return {
        "video_id": video.get("id", ""),
        "source_url": video.get("source_url", ""),
        "target": f"data/temp/{(video.get('id') or 'video')}.mp4",
        "status": "PLANNED",
    }


def publish_plan(video: dict) -> dict:
    """P3 contract (data only, no execution in P1)."""
    return {
        "video_id": video.get("id", ""),
        "source_url": video.get("source_url", ""),
        "caption": "",
        "status": "PLANNED",
        "scheduled_at": "",
    }
