# dashboard_service.py

1. Đường dẫn mã nguồn thực tế: `dashboard_service.py`
2. Nhóm chức năng: Application & Dashboard
3. Mục đích tồn tại: P17 dashboard service layer.
4. Công việc chính: Các hàm: `_p1_jobs_load`, `_p1_job_snapshot`, `_p1_job_new`, `_p1_job_update`, `_p1_reap_stale_file_job`, `_p1_active_job_for_project`, `_p1_filter_prefs_load`, `_validate_p1_filters`, `_read_json`, `_write_json`, `_bundle_dir`, `_load_config`, `_list_task_states`, `_production_candidates`, `_review_records`, `_history_entries`, `overview`, `_schedule_status`, `generate_caption`, `scheduler_status`, `queue_list`, `queue_enqueue`, `scheduler_start`, `scheduler_stop`, `_log`; Các lớp: `ServiceError`, `BackgroundJob`, `JobRegistry`
5. Các hàm và lớp quan trọng: `ServiceError`, `BackgroundJob`, `JobRegistry`, `_p1_jobs_load`, `_p1_job_snapshot`, `_p1_job_new`, `_p1_job_update`, `_p1_reap_stale_file_job`, `_p1_active_job_for_project`, `_p1_filter_prefs_load`, `_validate_p1_filters`, `_read_json`, `_write_json`, `_bundle_dir`, `_load_config`
6. Đầu vào và đầu ra: CHƯA XÁC MINH chi tiết — xem chữ ký hàm trong mã nguồn.
7. Module gọi file này: `_check_p2_lab.py`, `_check_p3_publish.py`, `_check_pipeline.py`, `_check_smart_gate.py`, `dashboard_server.py`
8. Module mà file phụ thuộc: `__future__`, `dataclasses`, `datetime`, `json`, `pathlib`, `scheduler`, `storage`, `threading`, `typing`, `uuid`
9. API hoặc route liên quan nếu có: dashboard_server.py routes — xem `docs/files/dashboard_server_py.md`.
10. Dữ liệu và cấu hình liên quan: `data/state/`, `data/state/p1_projects.db`, `config.yaml`, `.env` (không ghi secrets vào tài liệu).
11. Lỗi/rủi ro đã có bằng chứng: xem `docs/TROUBLESHOOTING.md`.
12. Cách tìm nguyên nhân: đọc `failure_reason` trong `data/state/p1_search_jobs.json` (search), kiểm tra log terminal, tái hiện bằng script `_check_*.py` ngoại tuyến, không chạy LIVE TikTok.
13. Test/câu lệnh kiểm tra: `py -m py_compile dashboard_service.py` (không chạy full suite trong nhiệm vụ tài liệu).
14. File cần xem khi sửa: `dashboard_server.py`, `web/app.js`, `project_store.py`, `p1_pipeline.py`.
15. Khả năng nâng cấp: CHƯA XÁC MINH — xem `docs/DEVELOPMENT_ROADMAP.md`.
16. Trạng thái hiện tại và giới hạn: đã vận hành local-first; giới hạn 8GB RAM, không GPU bắt buộc, không API trả phí.
17. Mã nguồn trên GitHub: [dashboard_service.py](https://github.com/doansensei1503-maker/TOOLTDH/blob/main/dashboard_service.py)
