# Cursor Rules

## Scope

- Follow the active phase in `TASKS.md`; do not implement later phases without instruction.
- Make the smallest change that satisfies the current task.
- Preserve existing architecture, behavior, and naming conventions.
- Inspect only files directly needed for the requested work.

## Safety

- Use only official web interfaces.
- Restrict automation to `allowed_sites` in `config.yaml`.
- Never bypass CAPTCHAs, bot detection, access controls, or rate limits.
- Never remove watermarks or provenance markers to hide origin.
- Process and publish only content with rights or permission.
- Never hard-code or commit passwords, API keys, cookies, or session tokens.
- Read secrets from environment variables; never print them.
- Fail closed when rights, permission, approval, provider, or destination state is unclear.
- Do not assume undocumented APIs are usable; verify against official documentation and record the result.

## Quality

- Keep configuration in `config.yaml` and secret placeholders in `.env.example`.
- Prefer clear, testable functions and explicit failures.
- Update `PROJECT_MASTER.md` and `PROGRESS.md` when module status or verification status changes.
- Record blockers honestly and do not claim unimplemented behavior.
- Stop when the requested phase is complete.

## Documentation maintenance (TOOLTDH knowledge base)

- Khi thêm file: cập nhật `docs/FILE_INDEX.md` + tạo trang `docs/files/<path_mirrored>.md`.
- Khi sửa trách nhiệm/API: cập nhật trang file + trang module tương ứng trong `docs/modules/`.
- Khi sửa bug: bổ sung `docs/TROUBLESHOOTING.md` nếu có thông tin chẩn đoán mới.
- Khi thêm tính năng: cập nhật `docs/DEVELOPMENT_ROADMAP.md` (không ghi tương lai thành đã xong).
- Khi đổi kiến trúc: cập nhật `docs/TECHNICAL_DECISIONS.md`.
- Khi phát hành: cập nhật `docs/CHANGELOG.md` + `docs/RELEASE_CHECKLIST.md`.
- Kiểm tra định kỳ: `py docs/check_docs.py` (link + độ phủ file). Script nhẹ, idempotent, không gọi AI.
- Không đưa secrets/.env/DB/log riêng/media vào tài liệu; thông tin chưa xác minh ghi "CHƯA XÁC MINH".
