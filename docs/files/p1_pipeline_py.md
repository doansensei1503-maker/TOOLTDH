# p1_pipeline.py

1. Đường dẫn mã nguồn thực tế: `p1_pipeline.py`
2. Nhóm chức năng: Search & Discovery
3. Mục đích tồn tại: P1 non-AI pipeline: plan -> collect -> dedup -> filters -> relevance -> trend -> TOP5.
4. Công việc chính: Các hàm: `plan_queries`, `_classify_query_error`, `_collect_query`, `_now_iso`, `run_pipeline`, `download_plan`, `publish_plan`
5. Các hàm và lớp quan trọng: `plan_queries`, `_classify_query_error`, `_collect_query`, `_now_iso`, `run_pipeline`, `download_plan`, `publish_plan`
6. Đầu vào và đầu ra: CHƯA XÁC MINH chi tiết — xem chữ ký hàm trong mã nguồn.
7. Module gọi file này: `_check_p1_rebuild.py`, `_p1_acceptance.py`
8. Module mà file phụ thuộc: `__future__`, `typing`
9. API hoặc route liên quan nếu có: CHƯA XÁC MINH / không có route riêng.
10. Dữ liệu và cấu hình liên quan: `data/state/`, `data/state/p1_projects.db`, `config.yaml`, `.env` (không ghi secrets vào tài liệu).
11. Lỗi/rủi ro đã có bằng chứng: xem `docs/TROUBLESHOOTING.md`.
12. Cách tìm nguyên nhân: đọc `failure_reason` trong `data/state/p1_search_jobs.json` (search), kiểm tra log terminal, tái hiện bằng script `_check_*.py` ngoại tuyến, không chạy LIVE TikTok.
13. Test/câu lệnh kiểm tra: `py -m py_compile p1_pipeline.py` (không chạy full suite trong nhiệm vụ tài liệu).
14. File cần xem khi sửa: `dashboard_service.py`, `project_store.py`.
15. Khả năng nâng cấp: CHƯA XÁC MINH — xem `docs/DEVELOPMENT_ROADMAP.md`.
16. Trạng thái hiện tại và giới hạn: đã vận hành local-first; giới hạn 8GB RAM, không GPU bắt buộc, không API trả phí.
17. Mã nguồn trên GitHub: [p1_pipeline.py](https://github.com/doansensei1503-maker/TOOLTDH/blob/main/p1_pipeline.py)
