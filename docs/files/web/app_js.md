# web/app.js

1. Đường dẫn mã nguồn thực tế: `web/app.js`
2. Nhóm chức năng: Application & Dashboard
3. Mục đích tồn tại: UI dashboard — điều hướng view, gọi API backend, render kết quả.
4. Công việc chính: quản lý project/version, search progress, filter autosave, TOP5 render, Video Lab, Publishing UI, theme/locale.
5. Các hàm quan trọng: `_p3vid`, `accepted`, `account`, `add`, `api`, `applyLocale`, `applyTheme`, `approve`, `approveCandidate`, `assistantAnswer`, `automationDotClass`, `automationFacts`, `automationLabel`, `bindEvents`, `bindP1`, `blockers`, `clearProjectFormErrors`, `closeMenus`, `closeProject`, `closeProjectCreateModal`
6. Đầu vào/đầu ra: fetch `GET/POST /api/*` → JSON → DOM.
7. Module gọi: `web/index.html`.
8. Phụ thuộc: backend `dashboard_server.py`/`dashboard_service.py`.
9. Route liên quan: `/api/overview`, `/api/p1/*`, `/api/p2/*`, `/api/p3/*`.
10. Dữ liệu/cấu hình: `data/state/p1_filter_prefs.json`, `data/state/p1_search_jobs.json`.
11. Lỗi đã có bằng chứng: filter không persist (thiếu autosave binding — đã sửa), selector rỗng khi chuyển view (đã sửa `loadP2Videos`/`loadP3Settings`), TOP5 sai tab (đã sửa).
12. Chẩn đoán: mở DevTools console, kiểm tra fetch status, đối chiếu `docs/TROUBLESHOOTING.md`.
13. Kiểm tra: `py -m py_compile` không áp dụng JS; kiểm tra thủ công trên `http://127.0.0.1:8777`.
14. File liên quan khi sửa: `web/index.html`, `web/styles.css`, `dashboard_server.py`.
15. Nâng cấp: xem ROADMAP.
16. Trạng thái/giới hạn: đã pass acceptance 15/15 local.
17. GitHub: [web/app.js](https://github.com/doansensei1503-maker/TOOLTDH/blob/main/web/app.js)
