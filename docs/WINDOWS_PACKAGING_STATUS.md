# WINDOWS PACKAGING STATUS — Trạng thái đóng gói Portable (17/11/2026)

> Kết luận: **READY (nguồn) / NOT READY (EXE)** — chưa build EXE theo yêu cầu (chờ nghiệm thu UI).

## Đã xác minh

- Entrypoints: `tooldh_portable.py` (portable) + `main.py --dashboard` (dev, `dashboard_server.serve("127.0.0.1", 8777)`). Server đang chạy thật, `/api/overview` HTTP 200.
- Static assets: spec `datas=[('web','web'), ('config.yaml','.')]` — khớp `dashboard_server.WEB_ROOT` + `_bundle_root()` (frozen `_MEIPASS`/`_internal` vs source).
- Runtime paths: `Path(__file__).resolve().parent` + `sys.path` bootstrap cho `scripts/*`, `tests/*`; user data nằm ở `data/` (untracked, `.gitignore` chặn `data/state|tasks|review|production|*.json`, media, models, profile, `.env`).
- User data tách biệt: EXE tương lai chỉ bundle `web/` + `config.yaml`; không bundle `data/`, `chrome-profile/`, cookies, videos, SQLite. Update không xóa user data.
- `build_hooks/hook-workflow.py` tồn tại; business modules giữ top-level nên import trong spec còn đúng.

## Chưa xong (blocker trước khi build EXE)

1. **`tooldh_portable.spec` thiếu hiddenimports**: spec hiện liệt kê ~24 modules nhưng **thiếu
   `p1_pipeline`, `query_planner`, `relevance`, `trend_scoring`, `poster`** (đều được import trực tiếp:
   `p1_pipeline`/`poster` trong diagnostics, `relevance→query_planner` trong pipeline, `discover` dùng scoring).
   PyInstaller có thể bỏ sót → EXE lỗi `ModuleNotFoundError` khi chạy P1/offline. Fix: bổ sung 5 entries vào
   `hiddenimports`, chạy lại `check_docs` + `py main.py --dry-run` + smoke trên máy sạch rồi mới build.
2. Chưa build thử `--onedir` lần nào trong phiên này (cố ý dừng theo yêu cầu "STOP BEFORE BUILDING EXE").

## Lệnh build (khi được duyệt, sau khi fix §1)

```powershell
py -m PyInstaller tooldh_portable.spec
.\dist\TOOLTDH\TOOLTDH.exe
```

Kiểm sau build: mở UI, `/api/overview` 200, P1 offline replay, P2 measure cache, P3 fail-closed (không publish thật).
