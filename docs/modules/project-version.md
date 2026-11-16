# Project & Version

- Chức năng: Project & Version.
- File:
- [`project_store.py`](../files/project_store_py.md)
- [`history.py`](../files/history_py.md)
- [`library.py`](../files/library_py.md)
- Luồng: Tạo project → create_run (idempotent retry_key) → runs/videos SQLite → replay offline.
- Input/Output: In: topic/filters/queries. Out: run version bất biến + snapshot_json.
- Dependencies: sqlite3 (stdlib).
- API: /api/p1/*, /api/project/* (qua service).
- Lỗi chú ý: FK constraint khi project chưa tồn tại; UNIQUE idempotency race (đã bẫy IntegrityError).
- Đã hoạt động: CRUD + idempotent + concurrent-safe.
- Chưa hoàn thiện: CHƯA XÁC MINH.
- Định hướng: Nền cho Knowledge Engine.
