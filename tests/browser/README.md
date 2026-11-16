# tests/browser — Acceptance trên trình duyệt thật

`_run_browser_acceptance.py`: mở Dashboard local (http://127.0.0.1:8777), kiểm 15 điểm
(render, navigation, discovery/project workspace, P1–P4 routes, API, theme VI/EN, console, error states).
Chạy khi server đang bật: `py tests/browser/_run_browser_acceptance.py`. Chỉ đọc/mock, không publish thật.
