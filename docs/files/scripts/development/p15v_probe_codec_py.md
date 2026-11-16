# scripts/development/p15v_probe_codec.py (công cụ kiểm thử/phụ trợ)

- Mục đích: P15V helper: diagnose why the test clip cannot be recorded.
- Hàm chính: `main`
- Đầu vào: tham số dòng lệnh/mặc định trong file; không chạm dữ liệu người dùng khi chạy đúng cách.
- Tác động: chỉ đọc/ghi file tạm hoặc state kiểm thử; không tải media, không đăng bài, không build EXE.
- Cách chạy: `py scripts/development/p15v_probe_codec.py` (chỉ chạy khi nhiệm vụ yêu cầu; nhiệm vụ tài liệu KHÔNG chạy).
- Mã nguồn trên GitHub: [p15v_probe_codec.py](https://github.com/doansensei1503-maker/TOOLTDH/blob/main/p15v_probe_codec.py)
