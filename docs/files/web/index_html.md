# web/index.html

1. Đường dẫn: `web/index.html` | 2. Nhóm: Application & Dashboard | 3. Mục đích: khung UI dashboard (nav 5 mục, tabs, modal, drawer).
4. Công việc: chứa các view Overview/Project/Search/Queue/Library/Scheduler và asset link có version query chống cache.
5. Hàm/lớp: DOM ids (`#filter-grid`, `#disc-top5`, `#p2-video`, `#p3-video`), modal `[hidden]`.
6. I/O: người dùng ↔ `web/app.js` ↔ `/api/*`.
7. Gọi bởi: trình duyệt + `dashboard_server.py` (static).
8. Phụ thuộc: `web/app.js`, `web/styles.css`.
9. Route: `/` + static.
10. Dữ liệu: không lưu trực tiếp.
11. Lỗi đã biết: `[hidden]` thua `.modal{display:grid}` (đã sửa bằng `[hidden]{display:none!important}`), asset cache (đã thêm version query).
12. Chẩn đoán: kiểm tra element overlay, console lỗi fetch.
13. Kiểm tra: mở `http://127.0.0.1:8777` thủ công.
14. Liên quan: `web/app.js`, `web/styles.css`.
15-16. Nâng cấp/trạng thái: xem ROADMAP; đã ổn định acceptance.
17. GitHub: [web/index.html](https://github.com/doansensei1503-maker/TOOLTDH/blob/main/web/index.html)
