# scripts/diagnostics/_make_probe_model.py (công cụ kiểm thử/phụ trợ)

- Mục đích: Build a real ONNX model by hand, without an onnx builder package.
- Hàm chính: `varint`, `tag`, `bytes_field`, `string_field`, `varint_field`, `float_field`, `float_list_field`, `tensor_proto`, `value_info`, `attribute_int`
- Đầu vào: tham số dòng lệnh/mặc định trong file; không chạm dữ liệu người dùng khi chạy đúng cách.
- Tác động: chỉ đọc/ghi file tạm hoặc state kiểm thử; không tải media, không đăng bài, không build EXE.
- Cách chạy: `py scripts/diagnostics/_make_probe_model.py` (chỉ chạy khi nhiệm vụ yêu cầu; nhiệm vụ tài liệu KHÔNG chạy).
- Mã nguồn trên GitHub: [_make_probe_model.py](https://github.com/doansensei1503-maker/TOOLTDH/blob/main/_make_probe_model.py)
