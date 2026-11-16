# query_planner.py

1. Đường dẫn mã nguồn thực tế: `query_planner.py`
2. Nhóm chức năng: Search & Discovery
3. Mục đích tồn tại: General-purpose deterministic query planner for P1 research searches.
4. Công việc chính: Các hàm: `_is_generic_phrase`, `normalize_text`, `tokenize`, `analyze_intent`, `_detect_subject_phrases`, `_restore_spelling`, `_english_words`, `_intent_words`, `_is_category_concept`, `_contains_vietnamese`, `_is_mixed_language_query`, `_pick_intent_word`, `build_query_plan`, `_dimensions_of`, `plan_to_dict`, `expand_topic_queries`; Các lớp: `TopicIntent`, `PlannedQuery`, `QueryPlan`
5. Các hàm và lớp quan trọng: `TopicIntent`, `PlannedQuery`, `QueryPlan`, `_is_generic_phrase`, `normalize_text`, `tokenize`, `analyze_intent`, `_detect_subject_phrases`, `_restore_spelling`, `_english_words`, `_intent_words`, `_is_category_concept`, `_contains_vietnamese`, `_is_mixed_language_query`, `_pick_intent_word`
6. Đầu vào và đầu ra: CHƯA XÁC MINH chi tiết — xem chữ ký hàm trong mã nguồn.
7. Module gọi file này: `_p1_acceptance.py`, `relevance.py`
8. Module mà file phụ thuộc: `__future__`, `dataclasses`, `re`, `typing`, `unicodedata`
9. API hoặc route liên quan nếu có: CHƯA XÁC MINH / không có route riêng.
10. Dữ liệu và cấu hình liên quan: `data/state/`, `data/state/p1_projects.db`, `config.yaml`, `.env` (không ghi secrets vào tài liệu).
11. Lỗi/rủi ro đã có bằng chứng: xem `docs/TROUBLESHOOTING.md`.
12. Cách tìm nguyên nhân: đọc `failure_reason` trong `data/state/p1_search_jobs.json` (search), kiểm tra log terminal, tái hiện bằng script `_check_*.py` ngoại tuyến, không chạy LIVE TikTok.
13. Test/câu lệnh kiểm tra: `py -m py_compile query_planner.py` (không chạy full suite trong nhiệm vụ tài liệu).
14. File cần xem khi sửa: `dashboard_service.py`, `project_store.py`.
15. Khả năng nâng cấp: CHƯA XÁC MINH — xem `docs/DEVELOPMENT_ROADMAP.md`.
16. Trạng thái hiện tại và giới hạn: đã vận hành local-first; giới hạn 8GB RAM, không GPU bắt buộc, không API trả phí.
17. Mã nguồn trên GitHub: [query_planner.py](https://github.com/doansensei1503-maker/TOOLTDH/blob/main/query_planner.py)
