"""P15V probe: can a large file be set through the raw CDP session?

This is read-only with respect to the browser lifecycle: it attaches over
CDP, asks the page for a DOM node id for the file input, and tries
``DOM.setFileInputFiles`` with a local path. It never closes the browser,
never navigates, and never uploads anything to a remote service.
"""

from __future__ import annotations

import json
import sys

from playwright.sync_api import sync_playwright


def probe(port: int, file_path: str) -> dict:
    playwright = sync_playwright().start()
    try:
        browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        context = browser.contexts[0]
        page = context.pages[0]
        cdp = context.new_cdp_session(page)
        document = cdp.send("DOM.getDocument", {"depth": -1, "pierce": True})
        node_id = cdp.send(
            "DOM.querySelector",
            {"nodeId": document["root"]["nodeId"], "selector": 'input[type="file"]'},
        ).get("nodeId")
        result = {"node_id": node_id, "url": str(page.url)}
        if node_id:
            cdp.send("DOM.setFileInputFiles", {"files": [file_path], "nodeId": node_id})
            result["set_file_input_files"] = "ok"
        return result
    finally:
        playwright.stop()


if __name__ == "__main__":
    target_port = int(sys.argv[1]) if len(sys.argv) > 1 else 9333
    target_file = sys.argv[2] if len(sys.argv) > 2 else r"d:\TOOLTDH\data\temp\p9-live.mp4"
    print(json.dumps(probe(target_port, target_file), indent=2))
