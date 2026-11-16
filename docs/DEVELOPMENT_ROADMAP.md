# DEVELOPMENT_ROADMAP — Kế hoạch dài hạn TOOLTDH Pro

Tầm nhìn: nền tảng nghiên cứu xu hướng, quản lý tri thức, phân tích video và tự động hóa sản xuất nội dung với AI có thể thay thế và mở rộng.

Điều kiện: 8GB RAM, không bắt buộc GPU, không API trả phí, local-first, có thể nâng cấp phần cứng.

| # | Giai đoạn | Mục tiêu | Trạng thái | Phụ thuộc | Phần cứng | Nghiệm thu | Rủi ro | Bằng chứng |
|---|---|---|---|---|---|---|---|---|
| 1 | Ổn định kiến trúc & repository | Knowledge base + guard search-job + release an toàn | ĐANG LÀM (docs này) | Không | hiện tại | docs đầy đủ, link đúng, không đổi logic | đẩy kèm code chưa nghiệm thu → chỉ push docs | commit docs-only + push verified |
| 2 | Video Lab + MP4 | Import/verify/analyze MP4 sở hữu | ĐÃ HOẠT ĐỘNG CƠ BẢN | FFmpeg | hiện tại | asset READY + analysis thật | file lỗi/format lạ | acceptance 15/15 |
| 3 | AI Vision/Speech provider | Kiến trúc provider thay thế được | CHƯA LÀM | Giai đoạn 2 | RAM 8GB, GPU tùy chọn | local chạy không key; Gemini chỉ khi cấu hình | tốn RAM/token | CHƯA CÓ |
| 4 | Knowledge Engine hằng ngày | Nghiên cứu + tri thức theo lịch | CHƯA LÀM | Giai đoạn 1–2 | hiện tại | job hằng ngày + replay offline | lịch chồng job | CHƯA CÓ |
| 5 | Trend Intelligence | Học từ phản hồi, xếp hạng xu hướng | CHƯA LÀM | Giai đoạn 3–4 | hiện tại | dự báo bám dữ liệu thật | overfit tín hiệu mỏng | CHƯA CÓ |
| 6 | Tự động hóa sản xuất | Pipeline nội dung khép kín có approval | CHƯA LÀM | Giai đoạn 2–5 | tùy nâng cấp | chạy E2E có người duyệt | đăng nhầm khi thiếu guard | CHƯA CÓ |
| 7 | Remote Workers & đa nền tảng | Xử lý phân tán, nhiều nền tảng | CHƯA LÀM | Giai đoạn 6 | nâng cấp | worker xa + nhiều đích | đồng bộ/quyền | CHƯA CÓ |

Không ghi giai đoạn tương lai thành "đã hoàn thành".
