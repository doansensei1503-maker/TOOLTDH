# local_vision.py

1. Đường dẫn mã nguồn thực tế: `local_vision.py`
2. Nhóm chức năng: AI & Analysis
3. Mục đích tồn tại: The local vision analyzer of TOOLTDH.
4. Công việc chính: Các hàm: `register_vision_adapter`, `clear_vision_adapters`, `_read_labels`, `onnx_vision_adapter`, `_run_onnx`, `_model_input_size`, `_model_input_shape`, `_prepare_picture`, `_run_here`, `_run_in_other_interpreter`, `auto_register_onnx_model`, `read_with_adapters`, `reading_from_dict`, `vision_runtime`, `_onnx_providers`, `_other_interpreters`, `machine_resources`, `vision_dependency_missing`, `_model_on_disk`, `_read_picture`, `measure_motion`, `measure_hook`, `ocr_available`, `measure_production_ui`, `analyze_vision`; Các lớp: `VisionObject`, `VisionReading`, `VisionMotion`, `VisionHook`, `VisionReport`
5. Các hàm và lớp quan trọng: `VisionObject`, `VisionReading`, `VisionMotion`, `VisionHook`, `VisionReport`, `register_vision_adapter`, `clear_vision_adapters`, `_read_labels`, `onnx_vision_adapter`, `_run_onnx`, `_model_input_size`, `_model_input_shape`, `_prepare_picture`, `_run_here`, `_run_in_other_interpreter`
6. Đầu vào và đầu ra: CHƯA XÁC MINH chi tiết — xem chữ ký hàm trong mã nguồn.
7. Module gọi file này: `_check_local_analyzer.py`, `_check_local_audio.py`, `_check_local_vision.py`, `local_analyzer.py`, `local_vision.py`
8. Module mà file phụ thuộc: `__future__`, `dataclasses`, `io`, `os`, `shutil`, `typing`
9. API hoặc route liên quan nếu có: CHƯA XÁC MINH / không có route riêng.
10. Dữ liệu và cấu hình liên quan: `data/state/`, `data/state/p1_projects.db`, `config.yaml`, `.env` (không ghi secrets vào tài liệu).
11. Lỗi/rủi ro đã có bằng chứng: xem `docs/TROUBLESHOOTING.md`.
12. Cách tìm nguyên nhân: đọc `failure_reason` trong `data/state/p1_search_jobs.json` (search), kiểm tra log terminal, tái hiện bằng script `_check_*.py` ngoại tuyến, không chạy LIVE TikTok.
13. Test/câu lệnh kiểm tra: `py -m py_compile local_vision.py` (không chạy full suite trong nhiệm vụ tài liệu).
14. File cần xem khi sửa: xem mục 7–8 và `docs/MODULE_ARCHITECTURE.md`.
15. Khả năng nâng cấp: CHƯA XÁC MINH — xem `docs/DEVELOPMENT_ROADMAP.md`.
16. Trạng thái hiện tại và giới hạn: đã vận hành local-first; giới hạn 8GB RAM, không GPU bắt buộc, không API trả phí.
17. Mã nguồn trên GitHub: [local_vision.py](https://github.com/doansensei1503-maker/TOOLTDH/blob/main/local_vision.py)
