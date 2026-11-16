# _check_p3_publish.py (công cụ kiểm thử/phụ trợ)

- Mục đích: P3 FINAL SAFETY GATE targeted test (fixture MP4 + fake publisher only).
- Hàm chính: `_v`, `_mk`, `_slow`, `_run4`, `_ok`, `_force_status`, `_expect_blocked`
- Đầu vào: tham số dòng lệnh/mặc định trong file; không chạm dữ liệu người dùng khi chạy đúng cách.
- Tác động: chỉ đọc/ghi file tạm hoặc state kiểm thử; không tải media, không đăng bài, không build EXE.
- Cách chạy: `py _check_p3_publish.py` (chỉ chạy khi nhiệm vụ yêu cầu; nhiệm vụ tài liệu KHÔNG chạy).
- Mã nguồn trên GitHub: [_check_p3_publish.py](https://github.com/doansensei1503-maker/TOOLTDH/blob/main/_check_p3_publish.py)
