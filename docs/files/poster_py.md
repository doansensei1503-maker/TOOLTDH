# poster.py

1. Đường dẫn mã nguồn thực tế: `poster.py`
2. Nhóm chức năng: Search & Discovery
3. Mục đích tồn tại: P4 TikTok Studio draft and publish automation using Playwright.
4. Công việc chính: Các hàm: `_media_mime`, `validate_allowed_site`, `validate_publish_input`, `current_page_url`, `page_is_alive`, `is_tiktok_studio_url`, `select_studio_page`, `select_tiktok_page`, `reuse_single_page`, `ensure_studio_page`, `fetch_page_text_with_browser`, `read_creator_source`, `read_keyword_search`, `read_keyword_searches`, `download_media_with_browser`, `_frame_is_black`, `capture_video_frames`, `page_text`, `detect_block`, `wait_for_user_to_solve_captcha`, `redact_secrets`, `load_task_state`, `save_task_state`, `is_logged_in`, `logged_in_account`; Các lớp: `PosterError`, `BlockedError`, `PosterResult`, `SessionState`, `SmartAgent`
5. Các hàm và lớp quan trọng: `PosterError`, `BlockedError`, `PosterResult`, `SessionState`, `SmartAgent`, `_media_mime`, `validate_allowed_site`, `validate_publish_input`, `current_page_url`, `page_is_alive`, `is_tiktok_studio_url`, `select_studio_page`, `select_tiktok_page`, `reuse_single_page`, `ensure_studio_page`
6. Đầu vào và đầu ra: CHƯA XÁC MINH chi tiết — xem chữ ký hàm trong mã nguồn.
7. Module gọi file này: `_check_local_vision.py`, `_check_p1_rebuild.py`, `_check_p2_lab.py`, `_check_p32_publish.py`, `_check_p3_publish.py`, `_check_pipeline.py`, `_check_publish_retention.py`, `_p1_acceptance.py`, `_smoke_b1.py`, `brain.py`
8. Module mà file phụ thuộc: `__future__`, `base64`, `dataclasses`, `datetime`, `json`, `os`, `pathlib`, `random`, `re`, `time`, `typing`, `urllib.parse`
9. API hoặc route liên quan nếu có: CHƯA XÁC MINH / không có route riêng.
10. Dữ liệu và cấu hình liên quan: `data/state/`, `data/state/p1_projects.db`, `config.yaml`, `.env` (không ghi secrets vào tài liệu).
11. Lỗi/rủi ro đã có bằng chứng: xem `docs/TROUBLESHOOTING.md`.
12. Cách tìm nguyên nhân: đọc `failure_reason` trong `data/state/p1_search_jobs.json` (search), kiểm tra log terminal, tái hiện bằng script `_check_*.py` ngoại tuyến, không chạy LIVE TikTok.
13. Test/câu lệnh kiểm tra: `py -m py_compile poster.py` (không chạy full suite trong nhiệm vụ tài liệu).
14. File cần xem khi sửa: xem mục 7–8 và `docs/MODULE_ARCHITECTURE.md`.
15. Khả năng nâng cấp: CHƯA XÁC MINH — xem `docs/DEVELOPMENT_ROADMAP.md`.
16. Trạng thái hiện tại và giới hạn: đã vận hành local-first; giới hạn 8GB RAM, không GPU bắt buộc, không API trả phí.
17. Mã nguồn trên GitHub: [poster.py](https://github.com/doansensei1503-maker/TOOLTDH/blob/main/poster.py)
