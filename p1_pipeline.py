"""P1 non-AI pipeline: plan -> collect -> dedup -> UI filters -> relevance -> trend -> TOP5.

No AI, no model, no network here. The collector is injected by the caller
(live reader or offline fixture). Evidence is keyword/metadata only.
"""

from __future__ import annotations

from typing import Any, Callable

TOP5_LIMIT = 5
STRICT_MIN_VIEWS = 5000
STRICT_MIN_DURATION = 30.0
STRICT_MAX_DURATION = 60.0
STRICT_MAX_DAYS = 30
MAX_QUERIES = 6
MAX_RETRIES = 3


def plan_queries(topic: str, max_queries: int = MAX_QUERIES, max_retries: int = MAX_RETRIES) -> dict:
    """Grounded query plan: bounded, topic-neutral, no AI-Music injection."""
    from discovery_live import expand_topic_queries

    topic = str(topic or "").strip()
    if not topic:
        raise ValueError("topic is required")
    queries = expand_topic_queries(topic, max_queries=max(1, min(int(max_queries or MAX_QUERIES), MAX_QUERIES)))
    return {
        "topic": topic,
        "queries": queries[:MAX_QUERIES],
        "max_queries": MAX_QUERIES,
        "max_retries": min(int(max_retries or MAX_RETRIES), MAX_RETRIES),
    }


def run_pipeline(
    topic: str,
    collector: Callable[[str], list[dict]],
    filters: dict | None = None,
    subtopics: list[str] | None = None,
    retry_key: str = "",
) -> dict:
    """Full P1 pipeline on injected candidates. No network inside except collector."""
    from discovery_live import (
        SearchFilters,
        apply_search_filters,
        build_top5_cards,
        canonical_video_key,
        candidate_age_days,
        passes_strict_metadata,
        rights_status_of,
        topic_matches,
    )
    from discover import DiscoveredVideo, score_all_trending
    from types import SimpleNamespace

    filters = dict(filters or {})
    plan = plan_queries(topic)
    queries = plan["queries"]
    sf = SearchFilters.from_payload(filters)

    raw: list[dict] = []
    query_stats: dict[str, dict] = {}
    for q in queries:
        items = []
        note = ""
        for _ in range(plan["max_retries"]):
            try:
                items = list(collector(q) or [])
                break
            except Exception as exc:  # transient: one retry budget per query
                note = str(exc)
                items = []
        query_stats[q] = {"returned": len(items), "note": note}
        raw.extend(items)
    funnel_raw = len(raw)

    # collect -> DiscoveredVideo (metadata only, never invent)
    cands: list[DiscoveredVideo] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        url = str(item.get("source_url", "")).strip()
        if not url:
            continue
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
            missing_metrics=list(item.get("missing_metrics", []) or []),
        ))

    # dedup by canonical video ID
    seen: set[str] = set()
    deduped: list[DiscoveredVideo] = []
    for c in cands:
        key = canonical_video_key(c.source_url)
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(c)
    funnel_dedup = len(deduped)

    # UI filters + strict metadata gate (5k views / 30-60s / <=30d)
    kept_ui, _ = apply_search_filters(deduped, sf)
    strict_kept: list[DiscoveredVideo] = []
    for c in kept_ui:
        try:
            ok, _ = passes_strict_metadata(c)
        except Exception:
            ok = False
        if ok:
            strict_kept.append(c)
    funnel_filtered = len(strict_kept)

    # relevance (rule-based keyword match) -> trend ranking
    verified: list[DiscoveredVideo] = []
    review: list[DiscoveredVideo] = []
    for c in strict_kept:
        try:
            match = topic_matches(c.title, topic)
        except Exception:
            match = False
        (verified if match else review).append(c)

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
    scored = score_all_trending(list(verified) + list(review), config)

    # non-AI evidence map for TOP5 builder
    analyses: dict[str, Any] = {}
    for c in verified:
        analyses[c.source_url] = SimpleNamespace(
            content_relevant=True, summary="relevance: keyword match",
            content_relevance_reason="keyword match", score=0, ranked=True,
        )
    for c in review:
        analyses[c.source_url] = SimpleNamespace(
            content_relevant=None, summary="CHUA DU DU LIEU — metadata pass, needs user check",
            content_relevance_reason="metadata pass, topic-weak",
            insufficient_reason="metadata pass, topic-weak",
            score=0, ranked=False,
        )
    try:
        rights_cfg = config
    except Exception:
        rights_cfg = {}
    top5 = build_top5_cards(
        list(scored), rights_cfg, analyses_by_url=analyses,
        limit=TOP5_LIMIT, subtopics=list(subtopics or sf.subtopics or []),
    )
    # attach deterministic rank + evidence fields (stable contract)
    for i, card in enumerate(top5, start=1):
        card["rank"] = i
        if card.get("status") == "VERIFIED":
            card["evidence"] = "keyword+metadata"
            card["certainty"] = "HIGH"
        else:
            card["evidence"] = "metadata-only"
            card.setdefault("certainty", "UNKNOWN")

    funnel = {
        "raw": funnel_raw, "dedup": funnel_dedup, "filtered": funnel_filtered,
        "verified": len(verified), "needs_review": len(review),
        "rejected": funnel_raw - funnel_filtered,
    }
    videos = []
    for card in top5:
        src = next((c for c in strict_kept if c.source_url == card["source_url"]), None)
        try:
            age = candidate_age_days(src) if src is not None else card.get("age_days")
        except Exception:
            age = card.get("age_days")
        try:
            rights = rights_status_of(card["source_url"], config)
        except Exception:
            rights = card.get("rights", "UNKNOWN")
        videos.append({
            "source_url": card["source_url"],
            "canonical_key": canonical_video_key(card["source_url"]),
            "creator": card.get("creator", ""),
            "title": card.get("title", ""),
            "views": card.get("views", 0),
            "duration_seconds": card.get("duration_seconds", 0),
            "posted_at": card.get("posted_at", ""),
            "age_days": age,
            "score": card.get("score", 0),
            "relevance": 30 if card.get("status") == "VERIFIED" else 0,
            "trend": card.get("score", 0),
            "status": card.get("status", "NEEDS_REVIEW"),
            "certainty": card.get("certainty", "UNKNOWN"),
            "rights": rights,
            "reason": card.get("reason", ""),
            "evidence": card.get("evidence", ""),
        })
    return {
        "topic": topic, "queries": queries, "query_stats": query_stats,
        "funnel": funnel, "top5": top5, "videos": videos,
        "filters": sf.to_dict(), "retry_key": retry_key,
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
