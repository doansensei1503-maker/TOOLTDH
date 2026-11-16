# _check_local_analyzer.py (công cụ kiểm thử/phụ trợ)

- Mục đích: Targeted checks for the local video analyzer.
- Hàm chính: `check`, `_jpeg`, `_music_ui`, `_plain_scene`, `_flat_black`, `fake_sound_model`
- Đầu vào: tham số dòng lệnh/mặc định trong file; không chạm dữ liệu người dùng khi chạy đúng cách.
- Tác động: chỉ đọc/ghi file tạm hoặc state kiểm thử; không tải media, không đăng bài, không build EXE.
- Cách chạy: `py _check_local_analyzer.py` (chỉ chạy khi nhiệm vụ yêu cầu; nhiệm vụ tài liệu KHÔNG chạy).
- Mã nguồn trên GitHub: [_check_local_analyzer.py](https://github.com/doansensei1503-maker/TOOLTDH/blob/main/_check_local_analyzer.py)
