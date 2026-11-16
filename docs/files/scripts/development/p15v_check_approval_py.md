# scripts/development/p15v_check_approval.py (công cụ kiểm thử/phụ trợ)

- Mục đích: P15V check 8: verify the approval gate in workflow.run_workflow.
- Hàm chính: `main`
- Đầu vào: tham số dòng lệnh/mặc định trong file; không chạm dữ liệu người dùng khi chạy đúng cách.
- Tác động: chỉ đọc/ghi file tạm hoặc state kiểm thử; không tải media, không đăng bài, không build EXE.
- Cách chạy: `py scripts/development/p15v_check_approval.py` (chỉ chạy khi nhiệm vụ yêu cầu; nhiệm vụ tài liệu KHÔNG chạy).
- Mã nguồn trên GitHub: [p15v_check_approval.py](https://github.com/doansensei1503-maker/TOOLTDH/blob/main/p15v_check_approval.py)
