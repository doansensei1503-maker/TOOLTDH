# project_store.py

1. Đường dẫn mã nguồn thực tế: `project_store.py`
2. Nhóm chức năng: Project & Version
3. Mục đích tồn tại: P1 project/run store: modular monolith, SQLite, no AI, offline replay.
4. Công việc chính: Các hàm: `_now`, `_nid`, `connect`, `init_db`, `create_project`, `list_projects`, `next_version`, `get_run_by_key`, `create_run`, `list_runs`, `get_run`
5. Các hàm và lớp quan trọng: `_now`, `_nid`, `connect`, `init_db`, `create_project`, `list_projects`, `next_version`, `get_run_by_key`, `create_run`, `list_runs`, `get_run`
6. Đầu vào và đầu ra: CHƯA XÁC MINH chi tiết — xem chữ ký hàm trong mã nguồn.
7. Module gọi file này: `_accept_p4a6.py`, `_check_p1_rebuild.py`, `_check_p2_lab.py`, `_check_p32_publish.py`, `_check_p3_publish.py`, `_p1_acceptance.py`, `candidate_analysis.py`, `discover.py`, `discovery_live.py`, `p3_publish.py`
8. Module mà file phụ thuộc: `__future__`, `datetime`, `json`, `os`, `pathlib`, `sqlite3`, `uuid`
9. API hoặc route liên quan nếu có: CHƯA XÁC MINH / không có route riêng.
10. Dữ liệu và cấu hình liên quan: `data/state/`, `data/state/p1_projects.db`, `config.yaml`, `.env` (không ghi secrets vào tài liệu).
11. Lỗi/rủi ro đã có bằng chứng: xem `docs/TROUBLESHOOTING.md`.
12. Cách tìm nguyên nhân: đọc `failure_reason` trong `data/state/p1_search_jobs.json` (search), kiểm tra log terminal, tái hiện bằng script `_check_*.py` ngoại tuyến, không chạy LIVE TikTok.
13. Test/câu lệnh kiểm tra: `py -m py_compile project_store.py` (không chạy full suite trong nhiệm vụ tài liệu).
14. File cần xem khi sửa: `dashboard_service.py`, `project_store.py`.
15. Khả năng nâng cấp: CHƯA XÁC MINH — xem `docs/DEVELOPMENT_ROADMAP.md`.
16. Trạng thái hiện tại và giới hạn: đã vận hành local-first; giới hạn 8GB RAM, không GPU bắt buộc, không API trả phí.
17. Mã nguồn trên GitHub: [project_store.py](https://github.com/doansensei1503-maker/TOOLTDH/blob/main/project_store.py)
