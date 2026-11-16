# TECHNICAL_DECISIONS — Quyết định kiến trúc

1. Local-first, không API trả phí bắt buộc — local analyzer mặc định; Gemini chỉ khi `TOOLTDH_ANALYZER=gemini` + key.
2. Nguồn tìm kiếm công khai tách khỏi allowlist; allowlist chỉ quyết định quyền tái sử dụng.
3. Một Chrome session, một tab cho mọi query (`poster.reuse_single_page`); không mở tab theo keyword.
4. Search-job async một active/project + atomic guard + uuid job_id; terminal jobs bất biến; stale RUNNING sau restart → FAILED interrupted.
5. Batch fetch tách daemon thread để UI polling không treo.
6. Run bất biến, idempotent theo `idempotency_key`; trùng concurrent → bẫy IntegrityError trả winner.
7. Ghi JSON nguyên tử (`.tmp` + replace); worker giữ entry memory để phân biệt restart.
8. Publish cần approve + media thật + claim UPLOADING nguyên tử; chỉ `/video/<id>` xác minh mới tính PUBLISHED.
9. Không bypass captcha/bot-detection/rate-limit; fail-closed.
10. Secrets từ env; `.env.example` placeholder only; docs không chứa secrets/DB/log/media.
11. Business modules giữ top-level (không di dời vào package) — import chéo + spec hiddenimports + 34 scripts tham chiếu trực tiếp; di dời = rủi ro circular import. Gọn gàng bằng VS Code file nesting.
12. Không rename module đang chạy chỉ để "đẹp hơn" (`brain.py` giữ nguyên, defer sang major version với compat shim).
13. `core/`, `modules/`, `app/`, `models/`, `integrations/` để trống (không tracked) — không tạo package rỗng chỉ để đẹp mắt.
