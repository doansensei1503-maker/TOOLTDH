# scripts/diagnostics/_check_discovery_retry.py (công cụ kiểm thử/phụ trợ)

- Mục đích: Targeted retry test: attempt 1 empty -> attempt 2 has video -> stop at 2, no attempt 3.
- Hàm chính: `_payload`, `mock_read`
- Đầu vào: tham số dòng lệnh/mặc định trong file; không chạm dữ liệu người dùng khi chạy đúng cách.
- Tác động: chỉ đọc/ghi file tạm hoặc state kiểm thử; không tải media, không đăng bài, không build EXE.
- Cách chạy: `py scripts/diagnostics/_check_discovery_retry.py` (chỉ chạy khi nhiệm vụ yêu cầu; nhiệm vụ tài liệu KHÔNG chạy).
- Mã nguồn trên GitHub: [_check_discovery_retry.py](https://github.com/doansensei1503-maker/TOOLTDH/blob/main/_check_discovery_retry.py)
