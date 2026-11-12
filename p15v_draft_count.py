"""P15V helper: count TikTok Studio drafts (read-only).

It opens the Drafts view in a tab, reads the count, and closes only that
tab. It never clicks Post, never publishes, and never closes the browser.
"""

from __future__ import annotations

import json
import sys

from playwright.sync_api import sync_playwright

COUNT_SCRIPT = """
() => {
  const text = document.body ? document.body.innerText : '';
  const drafts = text.match(/Drafts\\s+(\\d+)/i);
  const posts = text.match(/Posts\\s+(\\d+)/i);
  return {
    drafts_count: drafts ? Number(drafts[1]) : null,
    posts_count: posts ? Number(posts[1]) : null,
    has_draft_heading: /\\bDrafts?\\b/i.test(text),
    text_head: text.slice(0, 600),
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
        page.wait_for_timeout(6000)
        result = page.evaluate(COUNT_SCRIPT)
        page.close()
        print(json.dumps(result, indent=2))
        return 0
    finally:
        playwright.stop()


if __name__ == "__main__":
    raise SystemExit(main())
