# discover.py

1. Đường dẫn mã nguồn thực tế: `discover.py`
2. Nhóm chức năng: Search & Discovery
3. Mục đích tồn tại: P6 discovery of trending content from allowlisted TikTok sources.
4. Công việc chính: Các hàm: `allowed_sources`, `source_creator`, `url_creator`, `is_tiktok_url`, `matching_sources`, `is_allowed_source`, `validate_source_permitted`, `rank_trending`, `_threshold`, `_topic_match_score`, `_views_score`, `_engagement_score`, `_recency_score`, `_duration_match_score`, `score_trending`, `score_all_trending`, `select_trending`, `filter_and_select`, `creator_credit`, `resolve_download_link`, `download_to_temp`, `register_download`, `build_caption`, `build_history_metadata`, `discover_trending`; Các lớp: `DiscoveryError`, `NoCandidatesFoundError`, `TestDataRejectedError`, `SourceNotAllowedError`, `RightsNotPermittedError`, `DiscoveredVideo`, `DiscoveryResult`, `TrendingScore`, `TrendSelection`
5. Các hàm và lớp quan trọng: `DiscoveryError`, `NoCandidatesFoundError`, `TestDataRejectedError`, `SourceNotAllowedError`, `RightsNotPermittedError`, `DiscoveredVideo`, `DiscoveryResult`, `TrendingScore`, `TrendSelection`, `allowed_sources`, `source_creator`, `url_creator`, `is_tiktok_url`, `matching_sources`, `is_allowed_source`
6. Đầu vào và đầu ra: CHƯA XÁC MINH chi tiết — xem chữ ký hàm trong mã nguồn.
7. Module gọi file này: `_check_3fixes.py`, `_check_discovery_ai.py`, `_check_discovery_retry.py`, `_check_funnel_naruto.py`, `_check_pipeline.py`, `_check_smart_evaluation.py`, `_check_snaptik.py`, `_p1_acceptance.py`, `candidate_analysis.py`, `discovery_live.py`
8. Module mà file phụ thuộc: `__future__`, `dataclasses`, `datetime`, `json`, `library`, `pathlib`, `random`, `re`, `storage`, `typing`, `urllib.parse`
9. API hoặc route liên quan nếu có: CHƯA XÁC MINH / không có route riêng.
10. Dữ liệu và cấu hình liên quan: `data/state/`, `data/state/p1_projects.db`, `config.yaml`, `.env` (không ghi secrets vào tài liệu).
11. Lỗi/rủi ro đã có bằng chứng: xem `docs/TROUBLESHOOTING.md`.
12. Cách tìm nguyên nhân: đọc `failure_reason` trong `data/state/p1_search_jobs.json` (search), kiểm tra log terminal, tái hiện bằng script `_check_*.py` ngoại tuyến, không chạy LIVE TikTok.
13. Test/câu lệnh kiểm tra: `py -m py_compile discover.py` (không chạy full suite trong nhiệm vụ tài liệu).
14. File cần xem khi sửa: xem mục 7–8 và `docs/MODULE_ARCHITECTURE.md`.
15. Khả năng nâng cấp: CHƯA XÁC MINH — xem `docs/DEVELOPMENT_ROADMAP.md`.
16. Trạng thái hiện tại và giới hạn: đã vận hành local-first; giới hạn 8GB RAM, không GPU bắt buộc, không API trả phí.
17. Mã nguồn trên GitHub: [discover.py](https://github.com/doansensei1503-maker/TOOLTDH/blob/main/discover.py)
