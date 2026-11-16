# RESTRUCTURE AUDIT — Kiểm chứng công việc tái cấu trúc (17/11/2026)

> Nguồn kiểm chứng: `git status`, `git diff --cached --name-only`, `git diff --name-only`,
> `py docs/check_docs.py`, `py main.py --dry-run`, cấu trúc thư mục thực tế, `rg` import.

## 1. Tuyên bố cũ — đối chiếu thực tế

| # | Tuyên bố | Kết quả kiểm chứng |
|---|---|---|
| 1 | `check_docs`: 99 OK / 0 BAD | **VERIFIED** — chạy lại: `LINKS_OK=99 LINKS_BAD=0`, `SRC_TOTAL=72 SRC_MISSING_DOCS=0` |
| 2 | Tests 70/70 | **NOT TESTED (lại)** — chưa chạy lại trong phiên này; sẽ chạy acceptance ở Phase 7 |
| 3 | ~30 business modules còn ở root | **VERIFIED** — đúng 30 file `*.py` ở root |
| 4 | Git changes staged nhưng chưa commit/push | **VERIFIED** — ~65 paths staged (moves `scripts/`, `tests/`, `docs/`); chưa commit |
| 5 | Browser `ERR_CONNECTION_REFUSED` tại `:8777/#discovery` | **VERIFIED (nguyên nhân)** — không có tiến trình nào nghe port 8777 (`netstat` trống, chỉ còn 1 tiến trình `python` idle). Server chưa được khởi động lại sau khi kill task 659574. Không phải do vỡ import. |

## 2. Phân nhóm file

| Nhóm | Vị trí | Trạng thái |
|---|---|---|
| Diagnostic scripts (20) | `scripts/diagnostics/` | VERIFIED — đã move bằng `git mv`, có bootstrap `sys.path`, docs mirror đầy đủ |
| Development scripts (13) | `scripts/development/` | VERIFIED — như trên |
| Browser runner (1) | `tests/browser/_run_browser_acceptance.py` | VERIFIED — đã chạy 15/15 PASS trước khi server tắt |
| Business modules (30) | root | VERIFIED đúng vị trí — giữ lại có lý do (xem §4) |
| Docs 72 guides + 10 modules | `docs/files/`, `docs/modules/` | VERIFIED — link check 99/0 |
| `core/`, `modules/`, `app/`, `models/`, `integrations/` | root | **INCOMPLETE** — thư mục rỗng (chỉ có `__pycache__`), được tạo trước nhưng không dùng. Xử lý: giữ chỗ, không tạo package rỗng thêm; ghi nhận ở `docs/FILE_CATALOG.md` |
| `docs/FILE_CATALOG.md`, `docs/MAINTENANCE_GUIDE.md`, `docs/WINDOWS_PACKAGING_STATUS.md`, `docs/FILE_RENAME_MAP.md` | — | **INCOMPLETE** — tạo trong phiên này |

## 3. File còn ở sai vị trí

Không có. Mọi file đã move đều đúng nhóm chức năng. 30 file root còn lại là **đúng vị trí tạm thời** (có justification), không phải "sai vị trí".

## 4. File bắt buộc ở root (tương thích)

- `main.py` — entrypoint CLI + `--dashboard` (được `tooldh_portable.py`/spec và tài liệu tham chiếu trực tiếp).
- `tooldh_portable.py` + `tooldh_portable.spec` — PyInstaller entry; spec liệt kê ~20 hiddenimports dạng top-level (`brain`, `discover`, `workflow`, ...). Chuyển package = vỡ spec + `build_hooks/hook-workflow.py`.
- 27 business modules (`dashboard_server/service`, `p1_pipeline`, `discover`, `discovery_live`, `query_planner`, `relevance`, `trend_scoring`, `candidate_analysis`, `project_store`, `storage`, `workflow`, `scheduler`, `task_queue`, `poster`, `p2_lab`, `p3_publish`, `brain`, `reviewer`, `review_stage`, `ingest`, `library`, `history`, `eligibility`, `snaptik`, `tiktok_metrics`, `local_analyzer`, `local_vision`) — import top-level chéo nhau (`workflow↔brain/poster/storage`, `discover↔storage`, `dashboard_service→scheduler/storage`, `relevance→query_planner`, ~15 scripts diagnostics/dev import trực tiếp). Di chuyển = rủi ro circular import + vỡ 34 scripts + spec. **BLOCKED cho relocation sâu; giữ tại root, gom gọn bằng `.vscode/settings.json` file nesting.**

## 5. Naming audit — kết luận nhanh

Chi tiết: `docs/FILE_RENAME_MAP.md`. Kết luận: **0 file đổi tên trong phiên này**.
Tên đã mô tả đúng (`discovery_live`, `query_planner`, `trend_scoring`, `project_store`, `task_queue`, `review_stage`...).
`brain.py` tên mơ hồ (thực chất = P3 AI analysis/scoring/caption) nhưng được import ở `workflow.py`, `reviewer.py`, `scripts/diagnostics/_check_publish_retention.py` + `hiddenimports` trong spec + ~docs links → rename = rủi ro cao, lợi ích thấp. **BLOCKED (deferred, cần compat shim + major version).**

## 6. Dashboard `ERR_CONNECTION_REFUSED`

Nguyên nhân đã xác minh: **server không chạy** (không có listener 8777). Khắc phục: `py main.py --dashboard`
(entrypoint `main.py` → `dashboard_server.serve("127.0.0.1", 8777)`), sau đó verify `/api/overview` HTTP 200
rồi mới mở browser. Chi tiết ở Phase 5 của báo cáo phiên.

## 7. Git pending

- Staged (~65 paths): refactor moves + docs mirror + `FILE_INDEX.md`, `testing-packaging.md`. An toàn, chờ commit riêng.
- Unstaged (8 paths): `dashboard_server/service`, `discovery_live`, `p1_pipeline`, `project_store`, `query_planner`, `web/app.js`, `web/index.html` (+ `brain.py`, `candidate_analysis.py`, `local_analyzer.py`, `local_vision.py`, `poster.py`, `scheduler.py`, `storage.py`, `workflow.py` modified trước đó) — thay đổi chức năng P1 reliability + UI, **không gộp chung commit refactor**.
- Untracked: `data/` — **không bao giờ commit** (user data, SQLite, media).
