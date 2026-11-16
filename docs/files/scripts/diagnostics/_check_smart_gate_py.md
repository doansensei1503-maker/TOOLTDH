# scripts/diagnostics/_check_smart_gate.py (công cụ kiểm thử/phụ trợ)

- Mục đích: Targeted gate test: NEEDS_REVIEW cannot queue without user confirm; confirm separate from model.
- Hàm chính: chạy trực tiếp (main-level)
- Đầu vào: tham số dòng lệnh/mặc định trong file; không chạm dữ liệu người dùng khi chạy đúng cách.
- Tác động: chỉ đọc/ghi file tạm hoặc state kiểm thử; không tải media, không đăng bài, không build EXE.
- Cách chạy: `py scripts/diagnostics/_check_smart_gate.py` (chỉ chạy khi nhiệm vụ yêu cầu; nhiệm vụ tài liệu KHÔNG chạy).
- Mã nguồn trên GitHub: [_check_smart_gate.py](https://github.com/doansensei1503-maker/TOOLTDH/blob/main/_check_smart_gate.py)
