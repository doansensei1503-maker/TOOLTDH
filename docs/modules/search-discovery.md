# Search & Discovery

- Chức năng: Search & Discovery.
- File:
- [`query_planner.py`](../files/query_planner_py.md)
- [`p1_pipeline.py`](../files/p1_pipeline_py.md)
- [`discovery_live.py`](../files/discovery_live_py.md)
- [`discover.py`](../files/discover_py.md)
- [`poster.py`](../files/poster_py.md)
- [`tiktok_metrics.py`](../files/tiktok_metrics_py.md)
- [`brain.py`](../files/brain_py.md)
- Luồng: Topic → plan_queries → per-query collector (batch thread) → parse_search_results → dedup/filter/relevance/trend → TOP5 → save run.
- Input/Output: In: topic + filters. Out: funnel/top5/videos/query_outcomes + run_id.
- Dependencies: poster (Chrome/CDP), discovery_live parser, project_store.
- API: /api/p1/search|status|cancel, /api/discovery/*, POST /api/p1/search/start.
- Lỗi chú ý: Treo khi live chậm (đã tách batch thread); trùng job (atomic guard); stale RUNNING chặn search (reap FAILED); parser error → FAILED có failure_reason.
- Đã hoạt động: Thread-safe + cancel bất biến + restart recovery đã verify offline 6/6.
- Chưa hoàn thiện: Exact-VI query trả rỗng là hành vi nguồn thật, không phải bug.
- Định hướng: Trend Intelligence (giai đoạn 5).
