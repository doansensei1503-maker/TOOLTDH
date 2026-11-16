# scripts/diagnostics — Chẩn đoán offline

20 scripts `_check_*`/`_p1_acceptance`/`_smoke_b1`/`_accept_p4a6`/`_make_probe_model`.
Chạy từ repo root: `py scripts/diagnostics/<ten>.py`. Cần bootstrap `sys.path` đã có sẵn trong file.
Sửa hành vi search/filter/relevance → chạy `_p1_acceptance.py` + `_smoke_b1.py` trước.
Không chạm network thật, không ghi DB production.
