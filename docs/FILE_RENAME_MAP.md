# FILE RENAME MAP — Audit tên file (17/11/2026)

> Nguyên tắc: chỉ rename khi tên mới rõ ràng + đúng hơn; không rename module đang chạy chỉ để "dài hơn".
> Phương pháp: đọc docstring/dòng đầu + kiểm tra `rg` import ngược + `tooldh_portable.spec` hiddenimports.

| File cũ (giữ nguyên) | Mục đích thực tế | Đánh giá tên | Quyết định |
|---|---|---|---|
| `brain.py` | P3 AI analysis, scoring, caption, hashtag (`BrainError`, `AIUsage`, Gemini provider) | Mơ hồ — tên tốt hơn: `ai_analysis.py` | **DEFERRED (BLOCKED)** — import tại `workflow.py`, `reviewer.py`, `scripts/diagnostics/_check_publish_retention.py`, spec hiddenimports. Rename cần compat shim + update ~docs links; dời sang major version |
| `discover.py` | Discovery engine offline + trending scoring (`DiscoveredVideo`, `score_all_trending`) | Đúng | KEEP |
| `discovery_live.py` | Live TikTok search qua browser session (`discover_new_candidates`, retry, filters) | Đúng, phân biệt rõ với `discover.py` | KEEP |
| `query_planner.py` | Build query plan, `CONCEPTS`, `normalize_text`, `tokenize` | Đúng | KEEP |
| `relevance.py` | Relevance filtering (dùng `query_planner.CONCEPTS`) | Đúng | KEEP |
| `trend_scoring.py` | Trend scoring | Đúng | KEEP |
| `candidate_analysis.py` | Phân tích candidate (`DiscoveredVideo`) | Đúng | KEEP |
| `p1_pipeline.py` | P1 search pipeline | Đúng | KEEP |
| `p2_lab.py` | P2 media lab | Đúng | KEEP |
| `p3_publish.py` | P3 publish flow | Đúng | KEEP |
| `project_store.py` | SQLite project/version store (`create_run`, `get_run_by_key`) | Đúng | KEEP |
| `storage.py` | Persistence shared (`TEMP_DIR`, `sha256_file`, cleanup) | Đúng | KEEP |
| `workflow.py` | Orchestrator end-to-end (import `discover`, `brain`, `poster`, `storage`) | Đúng | KEEP |
| `scheduler.py` / `task_queue.py` | APScheduler jobs / hàng đợi tác vụ | Đúng | KEEP |
| `dashboard_server.py` / `dashboard_service.py` | HTTP server (loopback 8777) / business logic API | Đúng | KEEP |
| `poster.py` | TikTok Studio poster (`post_to_tiktok_studio`, `read_keyword_search`) | Đúng | KEEP |
| `reviewer.py` / `review_stage.py` | Review logic / review record (`format_review`, `write_review`) | Đúng | KEEP |
| `ingest.py` / `library.py` / `history.py` | Ingest / thư viện / lịch sử | Đúng | KEEP |
| `eligibility.py` / `snaptik.py` / `tiktok_metrics.py` | Rights gate / downloader / metrics | Đúng | KEEP |
| `local_analyzer.py` / `local_vision.py` | Phân tích media local / vision local | Đúng | KEEP |
| `main.py` / `tooldh_portable.py` | CLI entrypoint / portable entry | Đúng (entrypoint) | KEEP |

## Kết quả phiên này

- **Số file renamed: 0.** Không có rename nào đủ điều kiện an toàn/lợi ích.
- Không tạo compat shim, không sửa import, không sửa spec — bằng chứng: `py main.py --dry-run` = `ready`, `check_docs` 99/0 giữ nguyên.
- Migration plan cho `brain.py → ai_analysis.py` (khi làm major version): `git mv`, giữ `brain.py` shim (`from ai_analysis import *`), update `workflow.py`, `reviewer.py`, diagnostics script, spec hiddenimports, `build_hooks`, toàn bộ `docs/files/*brain*` + `FILE_INDEX.md`, chạy full regression + rebuild spec.
