# Storage & Knowledge

- Chức năng: Storage & Knowledge.
- File:
- [`storage.py`](../files/storage_py.md)
- [`history.py`](../files/history_py.md)
- [`library.py`](../files/library_py.md)
- [`project_store.py`](../files/project_store_py.md)
- Luồng: SQLite + JSON state (atomic .tmp replace) + history append.
- Input/Output: In: runs/media/pubs. Out: DB + state files.
- Dependencies: sqlite3, WAL/timeout (CHƯA XÁC MINH đầy đủ PRAGMA).
- API: Đọc qua service.
- Lỗi chú ý: SQLite locked khi ghi đồng thời — giảm nhờ kết nối ngắn + idempotency.
- Đã hoạt động: Offline replay + atomic write.
- Chưa hoàn thiện: Knowledge Engine hằng ngày (giai đoạn 4).
- Định hướng: Giai đoạn 4.
