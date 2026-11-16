"""P15V helper: close only the tabs created by the P15V helper scripts.

It never touches a TikTok Studio tab and never closes the browser.
"""

from __future__ import annotations

import json
import sys

from playwright.sync_api import sync_playwright


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9333
    playwright = sync_playwright().start()
    try:
        browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        context = browser.contexts[0]
        closed = []
        for page in list(context.pages):
            url = str(page.url)
            if url.startswith("about:blank") or url.startswith("http://127.0.0.1:8765"):
                closed.append(url)
                page.close()
        print(json.dumps({"closed": closed}, indent=2))
        return 0
    finally:
        playwright.stop()


if __name__ == "__main__":
    raise SystemExit(main())
