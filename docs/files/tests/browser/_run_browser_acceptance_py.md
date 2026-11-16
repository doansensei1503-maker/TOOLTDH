# tests/browser/_run_browser_acceptance.py (công cụ phụ trợ)

- Mục đích: script hỗ trợ (khởi động lại dashboard / runner acceptance trình duyệt).
- Đầu vào: tham số dòng lệnh; chạy trên máy local, không chạm dữ liệu người dùng ngoài phạm vi test `__E2E__`.
- Tác động: chỉ điều khiển server local hoặc seed/cleanup dữ liệu test; không tải media, không đăng bài, không build EXE.
- Cách chạy: `py tests/browser/_run_browser_acceptance.py` (chỉ khi nhiệm vụ yêu cầu).
- Mã nguồn trên GitHub: [tests/browser/_run_browser_acceptance.py](https://github.com/doansensei1503-maker/TOOLTDH/blob/main/tests/browser/_run_browser_acceptance.py)
