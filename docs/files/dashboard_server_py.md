# dashboard_server.py

1. Đường dẫn mã nguồn thực tế: `dashboard_server.py`
2. Nhóm chức năng: Application & Dashboard
3. Mục đích tồn tại: P17 dashboard HTTP server.
4. Công việc chính: Các hàm: `_bundle_root`, `_route`, `_call_handler`, `serve`, `main`; Các lớp: `ApiError`, `DashboardHandler`
5. Các hàm và lớp quan trọng: `ApiError`, `DashboardHandler`, `_bundle_root`, `_route`, `_call_handler`, `serve`, `main`
6. Đầu vào và đầu ra: CHƯA XÁC MINH chi tiết — xem chữ ký hàm trong mã nguồn.
7. Module gọi file này: CHƯA XÁC MINH
8. Module mà file phụ thuộc: `__future__`, `dashboard_service`, `http.server`, `json`, `mimetypes`, `pathlib`, `threading`, `typing`, `urllib.parse`
9. API hoặc route liên quan nếu có: dashboard_server.py routes — xem `docs/files/dashboard_server_py.md`.
10. Dữ liệu và cấu hình liên quan: `data/state/`, `data/state/p1_projects.db`, `config.yaml`, `.env` (không ghi secrets vào tài liệu).
11. Lỗi/rủi ro đã có bằng chứng: xem `docs/TROUBLESHOOTING.md`.
12. Cách tìm nguyên nhân: đọc `failure_reason` trong `data/state/p1_search_jobs.json` (search), kiểm tra log terminal, tái hiện bằng script `_check_*.py` ngoại tuyến, không chạy LIVE TikTok.
13. Test/câu lệnh kiểm tra: `py -m py_compile dashboard_server.py` (không chạy full suite trong nhiệm vụ tài liệu).
14. File cần xem khi sửa: xem mục 7–8 và `docs/MODULE_ARCHITECTURE.md`.
15. Khả năng nâng cấp: CHƯA XÁC MINH — xem `docs/DEVELOPMENT_ROADMAP.md`.
16. Trạng thái hiện tại và giới hạn: đã vận hành local-first; giới hạn 8GB RAM, không GPU bắt buộc, không API trả phí.
17. Mã nguồn trên GitHub: [dashboard_server.py](https://github.com/doansensei1503-maker/TOOLTDH/blob/main/dashboard_server.py)
