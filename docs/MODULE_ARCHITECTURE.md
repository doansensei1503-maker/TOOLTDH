# MODULE_ARCHITECTURE — Kiến trúc TOOLTDH Pro

Local-first, modular monolith: `web UI → dashboard_server (HTTP) → dashboard_service (logic) → SQLite/state JSON`.

## Sơ đồ tổng

`Topic → query_planner → p1_pipeline → poster/discovery_live (1 Chrome session, 1 tab) → parse → dedup/filter/relevance/trend → TOP5 → project_store.create_run (idempotent) → run bất biến → Video Lab (MP4 sở hữu) → local analyzer → Publishing (approve+claim) → history/scheduler/cleanup`

## Nhóm chức năng

| Nhóm | Trang |
|---|---|
| Application & Dashboard | [application-dashboard](modules/application-dashboard.md) |
| Project & Version | [project-version](modules/project-version.md) |
| Search & Discovery | [search-discovery](modules/search-discovery.md) |
| Video Lab & Media | [video-lab-media](modules/video-lab-media.md) |
| AI & Analysis | [ai-analysis](modules/ai-analysis.md) |
| Publishing | [publishing](modules/publishing.md) |
| Job & Scheduler | [job-scheduler](modules/job-scheduler.md) |
| Storage & Knowledge | [storage-knowledge](modules/storage-knowledge.md) |
| External Integrations | [external-integrations](modules/external-integrations.md) |
| Testing & Packaging | [testing-packaging](modules/testing-packaging.md) |

## Ranh giới đã chốt

- Nguồn tìm kiếm công khai tách khỏi allowlist; allowlist chỉ dùng cho quyền tái sử dụng.
- Không bypass captcha/rate-limit/access-control; fail-closed khi thiếu quyền/approval.
- Secrets chỉ từ biến môi trường; `.env.example` placeholder only.
- Ghi state JSON nguyên tử (`.tmp` + replace); terminal jobs bất biến.
