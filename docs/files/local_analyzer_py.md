# local_analyzer.py

1. Đường dẫn mã nguồn thực tế: `local_analyzer.py`
2. Nhóm chức năng: AI & Analysis
3. Mục đích tồn tại: Local video analyzer for TOOLTDH.
4. Công việc chính: Các hàm: `vision_model_path`, `available_tools`, `_has_module`, `gpu_name`, `_read_gpu_name`, `_frame_features`, `_average_features`, `_find_tool`, `_tool_paths`, `audio_available`, `missing_audio_dependency`, `_read_ebml_id`, `_read_ebml_number`, `_read_ebml_element`, `read_container`, `register_audio_adapter`, `measure_audio`, `measure_audio_with_tools`, `decode_signal`, `analyze_signal`, `_estimate_tempo`, `_tempo_confidence`, `_band_energies`, `_waveform_likeness`, `_text_like_score`; Các lớp: `Finding`, `LocalAnalysis`
5. Các hàm và lớp quan trọng: `Finding`, `LocalAnalysis`, `vision_model_path`, `available_tools`, `_has_module`, `gpu_name`, `_read_gpu_name`, `_frame_features`, `_average_features`, `_find_tool`, `_tool_paths`, `audio_available`, `missing_audio_dependency`, `_read_ebml_id`, `_read_ebml_number`
6. Đầu vào và đầu ra: CHƯA XÁC MINH chi tiết — xem chữ ký hàm trong mã nguồn.
7. Module gọi file này: `_check_local_analyzer.py`, `_check_local_audio.py`, `_check_local_vision.py`
8. Module mà file phụ thuộc: `__future__`, `dataclasses`, `local_vision`, `math`, `os`, `shutil`, `struct`, `subprocess`, `typing`
9. API hoặc route liên quan nếu có: CHƯA XÁC MINH / không có route riêng.
10. Dữ liệu và cấu hình liên quan: `data/state/`, `data/state/p1_projects.db`, `config.yaml`, `.env` (không ghi secrets vào tài liệu).
11. Lỗi/rủi ro đã có bằng chứng: xem `docs/TROUBLESHOOTING.md`.
12. Cách tìm nguyên nhân: đọc `failure_reason` trong `data/state/p1_search_jobs.json` (search), kiểm tra log terminal, tái hiện bằng script `_check_*.py` ngoại tuyến, không chạy LIVE TikTok.
13. Test/câu lệnh kiểm tra: `py -m py_compile local_analyzer.py` (không chạy full suite trong nhiệm vụ tài liệu).
14. File cần xem khi sửa: xem mục 7–8 và `docs/MODULE_ARCHITECTURE.md`.
15. Khả năng nâng cấp: CHƯA XÁC MINH — xem `docs/DEVELOPMENT_ROADMAP.md`.
16. Trạng thái hiện tại và giới hạn: đã vận hành local-first; giới hạn 8GB RAM, không GPU bắt buộc, không API trả phí.
17. Mã nguồn trên GitHub: [local_analyzer.py](https://github.com/doansensei1503-maker/TOOLTDH/blob/main/local_analyzer.py)
