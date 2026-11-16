# FILE CATALOG — Chỉ mục tra cứu trung tâm (17/11/2026)

> Hệ guide hiện hữu: `docs/files/` (72 guides, mirror theo path nguồn) = triển khai cụ thể của
> `docs/file_guides/` trong yêu cầu — không nhân đôi để tránh trùng lặp. Bảng dưới link tới cả
> source (`../*.py`) và guide (`files/*`).

## Tra cứu nhanh

| Câu hỏi | File nguồn | Guide |
|---|---|---|
| Ai điều khiển search? | [`p1_pipeline.py`](../p1_pipeline.py), [`discovery_live.py`](../discovery_live.py) | [p1_pipeline](files/p1_pipeline_py.md), [discovery_live](files/discovery_live_py.md) |
| Ai đổi query planning? | [`query_planner.py`](../query_planner.py) | [query_planner](files/query_planner_py.md) |
| Ai đổi relevance filtering? | [`relevance.py`](../relevance.py) + `discovery_live.apply_search_filters` | [relevance](files/relevance_py.md) |
| Ai đổi trend scoring? | [`trend_scoring.py`](../trend_scoring.py), [`discover.py`](../discover.py) | [trend_scoring](files/trend_scoring_py.md) |
| Ai quản lý project/version? | [`project_store.py`](../project_store.py) | [project_store](files/project_store_py.md) |
| Ai xử lý media analysis? | [`p2_lab.py`](../p2_lab.py), [`local_analyzer.py`](../local_analyzer.py), [`local_vision.py`](../local_vision.py) | [p2_lab](files/p2_lab_py.md) |
| Ai xử lý approval? | [`review_stage.py`](../review_stage.py), [`reviewer.py`](../reviewer.py) | [review_stage](files/review_stage_py.md) |
| Ai điều khiển publishing? | [`p3_publish.py`](../p3_publish.py), [`poster.py`](../poster.py), [`eligibility.py`](../eligibility.py) | [p3_publish](files/p3_publish_py.md) |
| Ai cung cấp Dashboard API? | [`dashboard_service.py`](../dashboard_service.py) qua [`dashboard_server.py`](../dashboard_server.py) | [dashboard_service](files/dashboard_service_py.md) |
| Ai đổi theme/ngôn ngữ? | [`web/app.js`](../web/app.js), [`web/index.html`](../web/index.html) | [app.js](files/web/app_js.md) |
| Ai xử lý SQLite? | [`project_store.py`](../project_store.py) (+ `storage.py` cho FS) | [project_store](files/project_store_py.md) |
| Ai điều khiển scheduler? | [`scheduler.py`](../scheduler.py), [`task_queue.py`](../task_queue.py), [`workflow.py`](../workflow.py) | [scheduler](files/scheduler_py.md) |
| Ai đóng gói Windows? | [`tooldh_portable.py`](../tooldh_portable.py), [`tooldh_portable.spec`](../tooldh_portable.spec) | [spec](files/tooldh_portable_spec.md) |

## Nhóm chức năng → thư mục

| Nhóm | Nguồn | Module doc |
|---|---|---|
| Application & Dashboard | `main.py`, `dashboard_*`, `web/`, `config.yaml` | [application-dashboard](modules/application-dashboard.md) |
| Search & Discovery | `p1_pipeline`, `discovery_live`, `discover`, `query_planner`, `relevance`, `trend_scoring`, `tiktok_metrics`, `snaptik` | [search-discovery](modules/search-discovery.md) |
| Project & Version | `project_store`, `history`, `library` | [project-version](modules/project-version.md) |
| Video Lab & Media | `p2_lab`, `ingest`, `snaptik` | [video-lab-media](modules/video-lab-media.md) |
| AI & Analysis | `brain`, `candidate_analysis`, `local_analyzer`, `local_vision`, `reviewer`, `review_stage` | [ai-analysis](modules/ai-analysis.md) |
| Publishing | `p3_publish`, `poster`, `eligibility` | [publishing](modules/publishing.md) |
| Job & Scheduler | `scheduler`, `task_queue`, `workflow` | [job-scheduler](modules/job-scheduler.md) |
| Storage & Knowledge | `storage`, `history` | [storage-knowledge](modules/storage-knowledge.md) |
| Testing & Packaging | `tooldh_portable.*`, `build_hooks/`, `scripts/`, `tests/` | [testing-packaging](modules/testing-packaging.md) |

Chi tiết kiến trúc: [MODULE_ARCHITECTURE](MODULE_ARCHITECTURE.md). Audit tái cấu trúc: [RESTRUCTURE_AUDIT](RESTRUCTURE_AUDIT.md). Rename: [FILE_RENAME_MAP](FILE_RENAME_MAP.md).
