# scheduler.py

1. Đường dẫn mã nguồn thực tế: `scheduler.py`
2. Nhóm chức năng: Job & Scheduler
3. Mục đích tồn tại: P16.1 scheduled orchestration with APScheduler.
4. Công việc chính: Các hàm: `parse_daily_time`, `load_schedule_state`, `save_schedule_state`, `run_scheduled_task`, `run_retention_pass`, `run_queue_pass`, `run_p3_auto_pass`, `build_scheduler`, `start_scheduler`; Các lớp: `SchedulerError`, `ScheduleSettings`
5. Các hàm và lớp quan trọng: `SchedulerError`, `ScheduleSettings`, `parse_daily_time`, `load_schedule_state`, `save_schedule_state`, `run_scheduled_task`, `run_retention_pass`, `run_queue_pass`, `run_p3_auto_pass`, `build_scheduler`, `start_scheduler`
6. Đầu vào và đầu ra: CHƯA XÁC MINH chi tiết — xem chữ ký hàm trong mã nguồn.
7. Module gọi file này: `_check_publish_retention.py`, `dashboard_service.py`
8. Module mà file phụ thuộc: `__future__`, `dataclasses`, `datetime`, `json`, `pathlib`, `typing`
9. API hoặc route liên quan nếu có: CHƯA XÁC MINH / không có route riêng.
10. Dữ liệu và cấu hình liên quan: `data/state/`, `data/state/p1_projects.db`, `config.yaml`, `.env` (không ghi secrets vào tài liệu).
11. Lỗi/rủi ro đã có bằng chứng: xem `docs/TROUBLESHOOTING.md`.
12. Cách tìm nguyên nhân: đọc `failure_reason` trong `data/state/p1_search_jobs.json` (search), kiểm tra log terminal, tái hiện bằng script `_check_*.py` ngoại tuyến, không chạy LIVE TikTok.
13. Test/câu lệnh kiểm tra: `py -m py_compile scheduler.py` (không chạy full suite trong nhiệm vụ tài liệu).
14. File cần xem khi sửa: xem mục 7–8 và `docs/MODULE_ARCHITECTURE.md`.
15. Khả năng nâng cấp: CHƯA XÁC MINH — xem `docs/DEVELOPMENT_ROADMAP.md`.
16. Trạng thái hiện tại và giới hạn: đã vận hành local-first; giới hạn 8GB RAM, không GPU bắt buộc, không API trả phí.
17. Mã nguồn trên GitHub: [scheduler.py](https://github.com/doansensei1503-maker/TOOLTDH/blob/main/scheduler.py)
