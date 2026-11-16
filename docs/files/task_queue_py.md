# task_queue.py

1. Đường dẫn mã nguồn thực tế: `task_queue.py`
2. Nhóm chức năng: Job & Scheduler
3. Mục đích tồn tại: P4 scheduling queue for approved TikTok Studio tasks.
4. Công việc chính: CHƯA XÁC MINH; Các lớp: `QueueError`, `QueuedTask`, `PublishQueue`
5. Các hàm và lớp quan trọng: `QueueError`, `QueuedTask`, `PublishQueue`
6. Đầu vào và đầu ra: CHƯA XÁC MINH chi tiết — xem chữ ký hàm trong mã nguồn.
7. Module gọi file này: CHƯA XÁC MINH
8. Module mà file phụ thuộc: `__future__`, `dataclasses`, `datetime`, `json`, `pathlib`, `typing`
9. API hoặc route liên quan nếu có: CHƯA XÁC MINH / không có route riêng.
10. Dữ liệu và cấu hình liên quan: `data/state/`, `data/state/p1_projects.db`, `config.yaml`, `.env` (không ghi secrets vào tài liệu).
11. Lỗi/rủi ro đã có bằng chứng: xem `docs/TROUBLESHOOTING.md`.
12. Cách tìm nguyên nhân: đọc `failure_reason` trong `data/state/p1_search_jobs.json` (search), kiểm tra log terminal, tái hiện bằng script `_check_*.py` ngoại tuyến, không chạy LIVE TikTok.
13. Test/câu lệnh kiểm tra: `py -m py_compile task_queue.py` (không chạy full suite trong nhiệm vụ tài liệu).
14. File cần xem khi sửa: xem mục 7–8 và `docs/MODULE_ARCHITECTURE.md`.
15. Khả năng nâng cấp: CHƯA XÁC MINH — xem `docs/DEVELOPMENT_ROADMAP.md`.
16. Trạng thái hiện tại và giới hạn: đã vận hành local-first; giới hạn 8GB RAM, không GPU bắt buộc, không API trả phí.
17. Mã nguồn trên GitHub: [task_queue.py](https://github.com/doansensei1503-maker/TOOLTDH/blob/main/task_queue.py)
