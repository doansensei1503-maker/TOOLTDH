# scripts/diagnostics/_check_publish_retention.py (công cụ kiểm thử/phụ trợ)

- Mục đích: Targeted checks for the caption, the workflow links, the publish
- Hàm chính: `check`, `_measured_metadata`, `check_caption_uses_measured_facts`, `check_caption_never_claims_unmeasured_facts`, `check_caption_ignores_facts_that_are_not_measured`, `check_template_provider_uses_the_same_facts`, `check_analyze_content_carries_the_facts`, `check_the_credit_is_never_cut_away`, `check_a_caption_without_a_credit_still_works`, `check_published_reference_is_found`
- Đầu vào: tham số dòng lệnh/mặc định trong file; không chạm dữ liệu người dùng khi chạy đúng cách.
- Tác động: chỉ đọc/ghi file tạm hoặc state kiểm thử; không tải media, không đăng bài, không build EXE.
- Cách chạy: `py scripts/diagnostics/_check_publish_retention.py` (chỉ chạy khi nhiệm vụ yêu cầu; nhiệm vụ tài liệu KHÔNG chạy).
- Mã nguồn trên GitHub: [_check_publish_retention.py](https://github.com/doansensei1503-maker/TOOLTDH/blob/main/_check_publish_retention.py)
