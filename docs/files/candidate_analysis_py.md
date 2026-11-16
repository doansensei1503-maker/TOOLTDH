# candidate_analysis.py

1. Đường dẫn mã nguồn thực tế: `candidate_analysis.py`
2. Nhóm chức năng: AI & Analysis
3. Mục đích tồn tại: D1.3 AI analysis of the discovered candidates.
4. Công việc chính: Các hàm: `_posted_date`, `_text`, `engagement_rate`, `_auxiliary_signal`, `_video_id_from_url`, `_cache_key`, `load_cache`, `save_cache`, `_frames_digest`, `_encode_frames`, `_decode_frames`, `request_local_analysis`, `local_result_to_payload`, `request_content_analysis`, `request_gemini_analysis`, `_media_path_for`, `_analyzer_version`, `_cache_key_prefix`, `_clamp_points`, `_dimension_from_content`, `_content_relevance`, `_strengths_weaknesses`, `_metadata_for`, `analyze_candidate`, `analyze_candidates`; Các lớp: `Dimension`, `CandidateAnalysis`
5. Các hàm và lớp quan trọng: `Dimension`, `CandidateAnalysis`, `_posted_date`, `_text`, `engagement_rate`, `_auxiliary_signal`, `_video_id_from_url`, `_cache_key`, `load_cache`, `save_cache`, `_frames_digest`, `_encode_frames`, `_decode_frames`, `request_local_analysis`, `local_result_to_payload`
6. Đầu vào và đầu ra: CHƯA XÁC MINH chi tiết — xem chữ ký hàm trong mã nguồn.
7. Module gọi file này: `_check_discovery_ai.py`, `_check_local_analyzer.py`, `_check_local_audio.py`, `_check_local_vision.py`, `_check_pipeline.py`
8. Module mà file phụ thuộc: `__future__`, `base64`, `dataclasses`, `datetime`, `discover`, `hashlib`, `json`, `os`, `pathlib`, `re`, `typing`
9. API hoặc route liên quan nếu có: CHƯA XÁC MINH / không có route riêng.
10. Dữ liệu và cấu hình liên quan: `data/state/`, `data/state/p1_projects.db`, `config.yaml`, `.env` (không ghi secrets vào tài liệu).
11. Lỗi/rủi ro đã có bằng chứng: xem `docs/TROUBLESHOOTING.md`.
12. Cách tìm nguyên nhân: đọc `failure_reason` trong `data/state/p1_search_jobs.json` (search), kiểm tra log terminal, tái hiện bằng script `_check_*.py` ngoại tuyến, không chạy LIVE TikTok.
13. Test/câu lệnh kiểm tra: `py -m py_compile candidate_analysis.py` (không chạy full suite trong nhiệm vụ tài liệu).
14. File cần xem khi sửa: xem mục 7–8 và `docs/MODULE_ARCHITECTURE.md`.
15. Khả năng nâng cấp: CHƯA XÁC MINH — xem `docs/DEVELOPMENT_ROADMAP.md`.
16. Trạng thái hiện tại và giới hạn: đã vận hành local-first; giới hạn 8GB RAM, không GPU bắt buộc, không API trả phí.
17. Mã nguồn trên GitHub: [candidate_analysis.py](https://github.com/doansensei1503-maker/TOOLTDH/blob/main/candidate_analysis.py)
