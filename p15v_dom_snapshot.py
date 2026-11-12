"""P15V helper: read-only DOM snapshot of a TikTok Studio page.

It never clicks, never types, never navigates, and never closes anything.
"""

from __future__ import annotations

import json
import sys

from playwright.sync_api import sync_playwright

SNAPSHOT = """
() => {
  const out = { url: location.href, title: document.title, inputs: [], editables: [], buttons: [], text: '' };
  for (const input of document.querySelectorAll('input')) {
    out.inputs.push({ type: input.type, accept: input.accept, visible: !!(input.offsetWidth || input.offsetHeight) });
  }
  for (const el of document.querySelectorAll('[contenteditable="true"]')) {
    out.editables.push({
      tag: el.tagName,
      placeholder: el.getAttribute('data-placeholder') || '',
      cls: (el.className || '').toString().slice(0, 120),
      text: (el.innerText || '').slice(0, 200),
    });
  }
  for (const button of document.querySelectorAll('button')) {
    const label = (button.innerText || button.getAttribute('aria-label') || '').trim();
    if (label) out.buttons.push({ label: label.slice(0, 60), disabled: button.disabled });
  }
  out.text = (document.body ? document.body.innerText : '').slice(0, 1200);
  return out;
}
"""


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9333
    index = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    playwright = sync_playwright().start()
    try:
        browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        pages = browser.contexts[0].pages
        if not pages:
            print(json.dumps({"error": "no pages"}))
            return 1
        page = pages[index] if index < len(pages) else pages[0]
        print(json.dumps(page.evaluate(SNAPSHOT), indent=2))
        return 0
    finally:
        playwright.stop()


if __name__ == "__main__":
    raise SystemExit(main())
