# p2_lab.py

1. Đường dẫn mã nguồn thực tế: `p2_lab.py`
2. Nhóm chức năng: Video Lab & Media
3. Mục đích tồn tại: P2 Video Lab + Auto Download Best: non-AI, offline-capable, on top of P1.
4. Công việc chính: Các hàm: `_now`, `_read_json`, `_write_json`, `_tools`, `_fps`, `ffprobe_media`, `detect_scenes`, `make_storyboard`, `analyze_media`, `get_run_videos`, `video_detail`, `pick_best`, `_record_asset`, `get_asset`, `download_video`, `auto_download_best`, `settings_get`, `settings_set`
5. Các hàm và lớp quan trọng: `_now`, `_read_json`, `_write_json`, `_tools`, `_fps`, `ffprobe_media`, `detect_scenes`, `make_storyboard`, `analyze_media`, `get_run_videos`, `video_detail`, `pick_best`, `_record_asset`, `get_asset`, `download_video`
6. Đầu vào và đầu ra: CHƯA XÁC MINH chi tiết — xem chữ ký hàm trong mã nguồn.
7. Module gọi file này: `_check_p2_lab.py`
8. Module mà file phụ thuộc: `__future__`, `datetime`, `json`, `os`, `pathlib`, `subprocess`, `typing`
9. API hoặc route liên quan nếu có: CHƯA XÁC MINH / không có route riêng.
10. Dữ liệu và cấu hình liên quan: `data/state/`, `data/state/p1_projects.db`, `config.yaml`, `.env` (không ghi secrets vào tài liệu).
11. Lỗi/rủi ro đã có bằng chứng: xem `docs/TROUBLESHOOTING.md`.
12. Cách tìm nguyên nhân: đọc `failure_reason` trong `data/state/p1_search_jobs.json` (search), kiểm tra log terminal, tái hiện bằng script `_check_*.py` ngoại tuyến, không chạy LIVE TikTok.
13. Test/câu lệnh kiểm tra: `py -m py_compile p2_lab.py` (không chạy full suite trong nhiệm vụ tài liệu).
14. File cần xem khi sửa: xem mục 7–8 và `docs/MODULE_ARCHITECTURE.md`.
15. Khả năng nâng cấp: CHƯA XÁC MINH — xem `docs/DEVELOPMENT_ROADMAP.md`.
16. Trạng thái hiện tại và giới hạn: đã vận hành local-first; giới hạn 8GB RAM, không GPU bắt buộc, không API trả phí.
17. Mã nguồn trên GitHub: [p2_lab.py](https://github.com/doansensei1503-maker/TOOLTDH/blob/main/p2_lab.py)
