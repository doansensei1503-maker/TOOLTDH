# MAINTENANCE GUIDE — Quy tắc duy trì tài liệu (bắt buộc)

> Mục tiêu: code đổi → docs đổi theo, không để `check_docs.py` đỏ.

## Quy tắc

1. **Đổi behavior/interface của module** → cập nhật guide tương ứng trong `docs/files/<path_mirror>.md`
   (mirror: `p1_pipeline.py` → `docs/files/p1_pipeline_py.md`, `web/app.js` → `docs/files/web/app_js.md`).
2. **Đổi trách nhiệm nhóm** → cập nhật `README.md` của thư mục chức năng + `docs/MODULE_ARCHITECTURE.md`.
3. **Move/rename file** → dùng `git mv`, cập nhật `docs/FILE_INDEX.md` + `docs/FILE_CATALOG.md` + mọi link liên quan.
4. **Thay đổi có ý nghĩa** → ghi `docs/CHANGELOG.md` (ngắn, từ `git log`, không bịa).
5. **Đổi test/packaging** → cập nhật `docs/modules/testing-packaging.md` + `docs/WINDOWS_PACKAGING_STATUS.md` nếu chạm spec/entrypoint.
6. **Audit rename** → cập nhật `docs/FILE_RENAME_MAP.md`; **audit cấu trúc** → `docs/RESTRUCTURE_AUDIT.md`.

## Kiểm tra nhẹ (offline, chuẩn)

```powershell
py docs/check_docs.py   # yêu cầu LINKS_BAD=0 và SRC_MISSING_DOCS=0
py main.py --dry-run    # yêu cầu: ready
```

`check_docs.py` kiểm tra: (a) mọi link `files/*.md` / `modules/*.md` / trang trung tâm tồn tại;
(b) mọi file nguồn tracked (`.py/.js/.html/.yaml/.spec/...`, trừ `docs/`) có guide mirror.
File mới → tạo guide mới rồi mới commit.
