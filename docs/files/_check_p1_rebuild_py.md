# _check_p1_rebuild.py (công cụ kiểm thử/phụ trợ)

- Mục đích: P1 targeted offline integration test: Naruto v001/v002, Dragon Ball v001.
- Hàm chính: `vid`, `naruto_collector`, `dragon_collector`
- Đầu vào: tham số dòng lệnh/mặc định trong file; không chạm dữ liệu người dùng khi chạy đúng cách.
- Tác động: chỉ đọc/ghi file tạm hoặc state kiểm thử; không tải media, không đăng bài, không build EXE.
- Cách chạy: `py _check_p1_rebuild.py` (chỉ chạy khi nhiệm vụ yêu cầu; nhiệm vụ tài liệu KHÔNG chạy).
- Mã nguồn trên GitHub: [_check_p1_rebuild.py](https://github.com/doansensei1503-maker/TOOLTDH/blob/main/_check_p1_rebuild.py)
