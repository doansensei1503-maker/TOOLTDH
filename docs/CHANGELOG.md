# CHANGELOG — Thay đổi đã xác minh

> Từ `git log` local (không bịa ngoài lịch sử).

```
a038e4a wip: checkpoint TOOLTDH Pro P1 search and P4 UI for Codex handoff
b61a6f5 P4-A Graphite Luxury UI: 5-item nav, projects focus, tabs, stat strip
657552d P3.2: exact Post control + confirm dialog, stop draft-as-publish
1b1fec1 P3 guard: lock approve/caption on terminal states
c838775 P3 gate: block schedule-unapproved + account-required + single-upload claim
99d8d37 P3.1: fix publisher adapter + PUBLISHED verification + auto scheduler wiring
ec25974 P3: caption non-AI + approval + auto publish
c14601c P2 lab: video detail + ffprobe measure cache + best-permitted auto download + UI toggle
2ac804b P1 rebuild: projects/runs SQLite versioned, non-AI pipeline, offline replay + UI workspace
5ec4a3e Fix discovery 13->1: strict gate 5k views/30-60s/<=30d, dedup by video ID, funnel RAW/DEDUP/FILTERED/VERIFIED, TOP5 VERIFIED-first
1dd820e Discovery 3 fixes: min 30s UNKNOWN reject, 3 Naruto queries dedup, dashboard applied_filters + TOP5 duration
842e8c1 Discovery retry: max 3 attempts per query, stop on first valid video, BLOCKED never retries
```

- Gần nhất: search-job thread-safe (atomic guard, uuid job_id, terminal bất biến, stale-restart reap, SQLite IntegrityError race) + probe offline 6/6 OK.
- Trước đó: acceptance 15/15 + 5 defect UI/search (filter autosave, loader view, TOP5 tab, batch thread).
- 17/11/2026: tái cấu trúc scripts/tests (`scripts/diagnostics/`, `scripts/development/`, `tests/browser/`) + audit giữ 30 business modules tại root + `FILE_CATALOG`/`RESTRUCTURE_AUDIT`/`FILE_RENAME_MAP`/`MAINTENANCE_GUIDE`/`WINDOWS_PACKAGING_STATUS` + README thư mục; `check_docs` 123/0, `dry-run ready`, P1 acceptance 158/162 (4 lỗi planner đã biết), Dashboard 8777 trực tiếp xác minh (title + snapshot + `/api/overview` 200).
- Chi tiết đầy đủ xem `git log` và từng trang `docs/files/`.
