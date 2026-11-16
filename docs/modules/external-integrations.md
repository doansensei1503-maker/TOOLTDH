# External Integrations

- Chức năng: External Integrations.
- File:
- [`poster.py`](../files/poster_py.md)
- [`snaptik.py`](../files/snaptik_py.md)
- [`discovery_live.py`](../files/discovery_live_py.md)
- Luồng: Chrome persistent profile + single tab → đọc /api/search/general/full/ → parser; không bypass captcha/rate-limit.
- Input/Output: In: keyword. Out: payload results/error.
- Dependencies: Playwright/Chrome.
- API: Không API trả phí.
- Lỗi chú ý: BLOCKED/challenge/login → FAILED/BLOCKED trung thực.
- Đã hoạt động: Một session một tab.
- Chưa hoàn thiện: CHƯA XÁC MINH thêm.
- Định hướng: Đa nền tảng (giai đoạn 7).
