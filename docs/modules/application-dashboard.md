# Application & Dashboard

- Chức năng: Application & Dashboard.
- File:
- [`main.py`](../files/main_py.md)
- [`dashboard_server.py`](../files/dashboard_server_py.md)
- [`dashboard_service.py`](../files/dashboard_service_py.md)
- [`web/app.js`](../files/web/app_js.md)
- [`web/index.html`](../files/web/index_html.md)
- [`web/styles.css`](../files/web/styles_css.md)
- [`config.yaml`](../files/config_yaml.md)
- Luồng: Người dùng → web UI → dashboard_server (HTTP /api/*) → dashboard_service (logic) → project_store/SQLite + state JSON → web render.
- Input/Output: In: thao tác UI/API. Out: JSON + DOM + SQLite/state.
- Dependencies: project_store, p1_pipeline, scheduler, p3_publish, p2_lab.
- API: /api/overview, /api/p1/*, /api/p2/*, /api/p3/*, /api/discovery/*, /api/media/*.
- Lỗi chú ý: Server không start / refused / UI không dữ liệu — xem TROUBLESHOOTING.
- Đã hoạt động: Dashboard chạy 127.0.0.1:8777; acceptance 15/15; search-job threading + cancel + restart-reap đã sửa.
- Chưa hoàn thiện: CHƯA XÁC MINH thêm.
- Định hướng: Giai đoạn 1 ổn định repo.
