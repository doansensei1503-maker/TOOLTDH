# storage.py

1. Đường dẫn mã nguồn thực tế: `storage.py`
2. Nhóm chức năng: Storage & Knowledge
3. Mục đích tồn tại: File storage helpers for ingested media.
4. Công việc chính: Các hàm: `ensure_directories`, `load_library`, `save_library`, `sha256_file`, `validate_media_file`, `move_to_temp`, `delete_temp_file`, `cleanup_temp_directory`, `cleanup_screenshots`, `cleanup_task`, `_parse_published_at`, `expired_published_tasks`, `cleanup_expired_media`, `load_task_state`, `save_task_state`, `record_hash`; Các lớp: `StorageError`
5. Các hàm và lớp quan trọng: `StorageError`, `ensure_directories`, `load_library`, `save_library`, `sha256_file`, `validate_media_file`, `move_to_temp`, `delete_temp_file`, `cleanup_temp_directory`, `cleanup_screenshots`, `cleanup_task`, `_parse_published_at`, `expired_published_tasks`, `cleanup_expired_media`, `load_task_state`
6. Đầu vào và đầu ra: CHƯA XÁC MINH chi tiết — xem chữ ký hàm trong mã nguồn.
7. Module gọi file này: `_check_p2_lab.py`, `_check_publish_retention.py`, `dashboard_service.py`, `discover.py`, `ingest.py`, `library.py`, `workflow.py`
8. Module mà file phụ thuộc: `__future__`, `datetime`, `hashlib`, `json`, `os`, `pathlib`, `shutil`, `typing`
9. API hoặc route liên quan nếu có: CHƯA XÁC MINH / không có route riêng.
10. Dữ liệu và cấu hình liên quan: `data/state/`, `data/state/p1_projects.db`, `config.yaml`, `.env` (không ghi secrets vào tài liệu).
11. Lỗi/rủi ro đã có bằng chứng: xem `docs/TROUBLESHOOTING.md`.
12. Cách tìm nguyên nhân: đọc `failure_reason` trong `data/state/p1_search_jobs.json` (search), kiểm tra log terminal, tái hiện bằng script `_check_*.py` ngoại tuyến, không chạy LIVE TikTok.
13. Test/câu lệnh kiểm tra: `py -m py_compile storage.py` (không chạy full suite trong nhiệm vụ tài liệu).
14. File cần xem khi sửa: xem mục 7–8 và `docs/MODULE_ARCHITECTURE.md`.
15. Khả năng nâng cấp: CHƯA XÁC MINH — xem `docs/DEVELOPMENT_ROADMAP.md`.
16. Trạng thái hiện tại và giới hạn: đã vận hành local-first; giới hạn 8GB RAM, không GPU bắt buộc, không API trả phí.
17. Mã nguồn trên GitHub: [storage.py](https://github.com/doansensei1503-maker/TOOLTDH/blob/main/storage.py)
