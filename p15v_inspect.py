"""P15V physical verification helper (read-only inspection).

This helper only inspects the live Chrome session over CDP. It never
closes anything, never navigates, never uploads, and never publishes.
"""

from __future__ import annotations

import json
import sys

from playwright.sync_api import sync_playwright

import poster


def inspect(port: int) -> dict:
    """Report browser, context, page, and account state for a CDP endpoint."""
    playwright = sync_playwright().start()
    try:
        browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        contexts = browser.contexts
        report = {
            "context_count": len(contexts),
            "pages": [],
            "account": "",
            "logged_in": False,
            "robot_check": "",
        }
        for context in contexts:
            for page in context.pages:
                entry = {"url": str(page.url), "title": page.title()}
                try:
                    entry["account"] = poster.logged_in_account(page, "v.quc.on")
                except Exception as exc:
                    entry["account"] = f"<error {type(exc).__name__}>"
                report["pages"].append(entry)
        if contexts and contexts[0].pages:
            page = contexts[0].pages[0]
            report["logged_in"] = poster.is_logged_in(page)
            report["robot_check"] = poster.detect_robot_check(page) or ""
        return report
    finally:
        # Detaching the driver must not close the user's Chrome. The browser
        # was started outside this process, so it owns its own lifetime.
        playwright.stop()


if __name__ == "__main__":
    target_port = int(sys.argv[1]) if len(sys.argv) > 1 else 9333
    print(json.dumps(inspect(target_port), indent=2))
