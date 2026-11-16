# _check_p32_publish.py (công cụ kiểm thử/phụ trợ)

- Mục đích: P3.2 targeted offline regression: exact Post control (mock page only, real business logic).
- Hàm chính: `_v`, `_mk`
- Đầu vào: tham số dòng lệnh/mặc định trong file; không chạm dữ liệu người dùng khi chạy đúng cách.
- Tác động: chỉ đọc/ghi file tạm hoặc state kiểm thử; không tải media, không đăng bài, không build EXE.
- Cách chạy: `py _check_p32_publish.py` (chỉ chạy khi nhiệm vụ yêu cầu; nhiệm vụ tài liệu KHÔNG chạy).
- Mã nguồn trên GitHub: [_check_p32_publish.py](https://github.com/doansensei1503-maker/TOOLTDH/blob/main/_check_p32_publish.py)
