# Testing & Packaging

- Chức năng: Testing & Packaging.
- File:
- [`_run_browser_acceptance.py`](../files/_run_browser_acceptance_py.md)
- [`_restart_dashboard.py`](../files/_restart_dashboard_py.md)
- [`tooldh_portable.py`](../files/tooldh_portable_py.md)
- [`tooldh_portable.spec`](../files/tooldh_portable_spec.md)
- [`requirements.txt`](../files/requirements_txt.md)
- [`build_hooks/hook-workflow.py`](../files/build_hooks/hook-workflow_py.md)
- Luồng: Runner Playwright 15 bước → seed offline → assert → cleanup; portable build đóng gói EXE.
- Input/Output: In: lệnh local. Out: PASS/FAIL + EXE.
- Dependencies: Playwright + Chrome hệ thống.
- API: Không.
- Lỗi chú ý: Thiếu Chrome binary / port 8777 bận.
- Đã hoạt động: 15/15 PASS; EXE không build trong nhiệm vụ này.
- Chưa hoàn thiện: Giữ runner tái sử dụng.
- Định hướng: Release checklist.
