# _p1_acceptance.py (công cụ kiểm thử/phụ trợ)

- Mục đích: Targeted offline integration acceptance for the P1 search reconstruction.
- Hàm chính: `check`, `section`, `make_video`, `fixture_collector`, `empty_collector`, `parser_error_collector`, `blocked_collector`, `partial_collector`
- Đầu vào: tham số dòng lệnh/mặc định trong file; không chạm dữ liệu người dùng khi chạy đúng cách.
- Tác động: chỉ đọc/ghi file tạm hoặc state kiểm thử; không tải media, không đăng bài, không build EXE.
- Cách chạy: `py _p1_acceptance.py` (chỉ chạy khi nhiệm vụ yêu cầu; nhiệm vụ tài liệu KHÔNG chạy).
- Mã nguồn trên GitHub: [_p1_acceptance.py](https://github.com/doansensei1503-maker/TOOLTDH/blob/main/_p1_acceptance.py)
