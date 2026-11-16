# RELEASE_CHECKLIST — Trước phát hành

- [ ] `git status` sạch theo phạm vi release; không kèm code chưa nghiệm thu.
- [ ] `py -m py_compile` các file đổi (không chạy full suite nếu không đổi logic).
- [ ] Acceptance liên quan vẫn pass (chỉ khi đổi logic; docs-only thì bỏ qua).
- [ ] Không secrets/DB/log/media trong diff (`git diff --stat` + grep `API_KEY|SECRET|TOKEN|COOKIE`).
- [ ] Link Markdown kiểm tra bằng `py docs/check_docs.py`.
- [ ] CHANGELOG + ROADMAP cập nhật đúng trạng thái (không ghi tương lai thành xong).
- [ ] Commit message rõ phạm vi; không force push; không merge/rebase ngoài phạm vi.
- [ ] Push xong xác minh commit tồn tại trên GitHub + README/MD mở được.
