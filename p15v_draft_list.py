"""P15V helper: list TikTok Studio drafts (read-only).

It opens the Drafts view in a tab, reads the draft list, and closes only
that tab. It never clicks Post, never publishes, and never closes the
browser.
"""

from __future__ import annotations

import json
import sys

from playwright.sync_api import sync_playwright

LIST_SCRIPT = """
() => {
  const text = document.body ? document.body.innerText : '';
  const lines = text.split('\\n').map((line) => line.trim()).filter(Boolean);
  const marker = lines.indexOf('Drafts');
  return {
    drafts_count: (text.match(/Drafts\\s+(\\d+)/i) || [null, null])[1],
    posts_count: (text.match(/Posts\\s+(\\d+)/i) || [null, null])[1],
    list_lines: marker >= 0 ? lines.slice(marker, marker + 40) : lines.slice(0, 40),
  };
}
"""


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9333
    playwright = sync_playwright().start()
    try:
        browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        context = browser.contexts[0]
        page = context.new_page()
        page.goto(
            "https://www.tiktok.com/tiktokstudio/content?tab=draft",
            wait_until="domcontentloaded",
        )
        page.wait_for_timeout(7000)
        result = page.evaluate(LIST_SCRIPT)
        page.close()
        print(json.dumps(result, indent=2))
        return 0
    finally:
        playwright.stop()


if __name__ == "__main__":
    raise SystemExit(main())
