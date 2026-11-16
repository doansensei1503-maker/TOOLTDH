# discovery_live.py

1. Đường dẫn mã nguồn thực tế: `discovery_live.py`
2. Nhóm chức năng: Search & Discovery
3. Mục đích tồn tại: P16.1 live discovery of real videos from a public TikTok keyword search.
4. Công việc chính: Các hàm: `is_tutorial_title`, `expand_topic_queries`, `_media_urls`, `_parse_item_list`, `_search_result_items`, `_search_count`, `parse_search_results`, `is_ai_generated_item`, `to_candidate`, `_topic_tokens`, `_contains_word`, `_hashtags`, `_carries_market`, `_carries_ai`, `topic_matches`, `apply_search_filters`, `_filter_reason`, `canonical_video_key`, `passes_strict_metadata`, `candidate_age_days`, `rights_status_of`, `language_market_note`, `build_top5_cards`, `_is_block_error`, `_fetch_query_with_retry`; Các lớp: `SearchFilters`, `DiscoveryBlockedError`
5. Các hàm và lớp quan trọng: `SearchFilters`, `DiscoveryBlockedError`, `is_tutorial_title`, `expand_topic_queries`, `_media_urls`, `_parse_item_list`, `_search_result_items`, `_search_count`, `parse_search_results`, `is_ai_generated_item`, `to_candidate`, `_topic_tokens`, `_contains_word`, `_hashtags`, `_carries_market`
6. Đầu vào và đầu ra: CHƯA XÁC MINH chi tiết — xem chữ ký hàm trong mã nguồn.
7. Module gọi file này: `_check_3fixes.py`, `_check_discovery_ai.py`, `_check_discovery_retry.py`, `_check_funnel_naruto.py`, `_check_pipeline.py`, `_check_smart_evaluation.py`, `_check_snaptik.py`, `_p1_acceptance.py`, `candidate_analysis.py`, `discovery_live.py`
8. Module mà file phụ thuộc: `__future__`, `dataclasses`, `datetime`, `discover`, `json`, `pathlib`, `re`, `tiktok_metrics`, `time`, `typing`
9. API hoặc route liên quan nếu có: CHƯA XÁC MINH / không có route riêng.
10. Dữ liệu và cấu hình liên quan: `data/state/`, `data/state/p1_projects.db`, `config.yaml`, `.env` (không ghi secrets vào tài liệu).
11. Lỗi/rủi ro đã có bằng chứng: xem `docs/TROUBLESHOOTING.md`.
12. Cách tìm nguyên nhân: đọc `failure_reason` trong `data/state/p1_search_jobs.json` (search), kiểm tra log terminal, tái hiện bằng script `_check_*.py` ngoại tuyến, không chạy LIVE TikTok.
13. Test/câu lệnh kiểm tra: `py -m py_compile discovery_live.py` (không chạy full suite trong nhiệm vụ tài liệu).
14. File cần xem khi sửa: `dashboard_service.py`, `project_store.py`.
15. Khả năng nâng cấp: CHƯA XÁC MINH — xem `docs/DEVELOPMENT_ROADMAP.md`.
16. Trạng thái hiện tại và giới hạn: đã vận hành local-first; giới hạn 8GB RAM, không GPU bắt buộc, không API trả phí.
17. Mã nguồn trên GitHub: [discovery_live.py](https://github.com/doansensei1503-maker/TOOLTDH/blob/main/discovery_live.py)
