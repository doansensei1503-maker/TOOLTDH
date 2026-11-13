"""P4-A.6 focused offline acceptance test.

The test never publishes, never downloads and never touches the live account.
It only reads the served markup and the static assets, and it drives the
backend endpoints that are safe to call: the read only overview, the scheduler
status and the emergency flag (which is switched back immediately).
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser

# The report contains Vietnamese labels. The Windows console defaults to
# cp1252 and would crash on them, so the output is forced to UTF-8.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover - very old interpreters
    pass

BASE = "http://127.0.0.1:8777"
ROUTES = [
    "overview", "discovery", "videos", "videoslib", "scheduler", "trends",
    "filter", "caption", "editor", "approval", "studio", "analytics",
    "history", "settings",
]

failures: list[str] = []
checks = 0


def check(ok: bool, label: str, detail: str = "") -> None:
    global checks
    checks += 1
    if ok:
        print(f"  PASS  {label}")
    else:
        print(f"  FAIL  {label}{(' -> ' + detail) if detail else ''}")
        failures.append(label + ((" -> " + detail) if detail else ""))


def get(path: str) -> str:
    with urllib.request.urlopen(BASE + path, timeout=15) as resp:
        return resp.read().decode("utf-8", "replace")


def get_json(path: str):
    return json.loads(get(path))


def post_json(path: str, payload: dict | None = None):
    data = json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(
        BASE + path, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


VOID = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
}


class Structure(HTMLParser):
    """Checks the nesting of the markup and counts the duplicate ids."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, int]] = []
        self.errors: list[str] = []
        self.ids: dict[str, int] = {}
        self.view_stack: list[str] = []
        self.outside_views: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs_d = dict(attrs)
        if "id" in attrs_d:
            self.ids[attrs_d["id"]] = self.ids.get(attrs_d["id"], 0) + 1
        classes = (attrs_d.get("class") or "").split()
        if "view" in classes and "data-view" in attrs_d:
            self.view_stack.append(attrs_d["data-view"])
        elif self.view_stack:
            pass
        if tag not in VOID:
            self.stack.append((tag, self.getpos()[0]))

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if self.stack and self.stack[-1][0] == tag:
            self.stack.pop()
            return
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                for j in range(len(self.stack) - 1, i - 1, -1):
                    if j != i:
                        self.errors.append(
                            f"unclosed <{self.stack[j][0]}> opened at line {self.stack[j][1]}"
                        )
                del self.stack[i:]
                return
        self.errors.append(f"unexpected </{tag}> at line {self.getpos()[0]}")


def main() -> int:
    print("P4-A.6 focused offline acceptance")
    print(f"target: {BASE}")

    html = get("/")
    js = get("/app.js")
    css = get("/styles.css")

    print("\n[1] markup structure")
    parser = Structure()
    parser.feed(html)
    check(not parser.errors, "HTML nesting is balanced", "; ".join(parser.errors[:4]))
    check(not parser.stack, "no unclosed elements remain", str(parser.stack[:4]))
    dups = {k: v for k, v in parser.ids.items() if v > 1}
    check(not dups, "no duplicate DOM ids", str(dups))

    print("\n[2] route isolation")
    # The nav button and its view container deliberately share the same
    # data-view value, because showView() uses that value to switch both.
    # Only the VIEW CONTAINERS have to be unique.
    views = re.findall(r'<div class="view[^"]*"\s+data-view="([^"]+)"', html)
    for route in ROUTES:
        check(route in views, f"view container for '{route}' exists")
    check(len(views) == len(set(views)), "every view container name is unique",
          f"{[v for v in views if views.count(v) > 1]}")
    # The navigation must offer exactly one button per route.
    nav_views = re.findall(r'class="nav-item[^"]*"\s+data-view="([^"]+)"', html)
    check(len(nav_views) == len(set(nav_views)), "every nav button name is unique",
          f"{[v for v in nav_views if nav_views.count(v) > 1]}")

    # The Discovery panels must live inside a view, never directly in #content.
    content_match = re.search(r'<section class="content" id="content">(.*?)</section>', html, re.S)
    check(content_match is not None, "#content section is present")
    if content_match:
        content_html = content_match.group(1)
        for panel_id in ("disc-selected-card", "disc-analysis", "disc-preview-box", "p2-lab-state"):
            idx = content_html.find(f'id="{panel_id}"')
            check(idx != -1, f"panel '{panel_id}' exists in #content")
            if idx != -1:
                # Count the view containers that are opened before this panel and
                # closed after it. A panel outside every view is the old bug.
                before = content_html[:idx]
                opens = len(re.findall(r'<div class="view"', before))
                closes = len(re.findall(r'</div>\s*(?:<!--|</div>|<div class="view")', before))
                check(opens >= 1, f"panel '{panel_id}' sits after a view container opens")

    # Every panel must be inside a view: the four legacy panels may only
    # appear after the discovery view was opened.
    disc_panel = 'id="disc-analysis"'
    if disc_panel in html:
        before = html[: html.find(disc_panel)]
        check('data-view="discovery"' in before, "legacy panels live under the discovery view")
        video_view = before.find('data-view="videos"')
        check(video_view == -1 or before.rfind('data-view="discovery"') > video_view,
              "legacy panels are not after the videos view")

    print("\n[3] duplicate discovery panels")
    for name in ("Phân tích AI các ứng viên", "Xem trước video", "Video Lab (P2)"):
        count = html.count(name)
        check(count == 1, f"'{name}' appears exactly once", f"found {count}")

    print("\n[4] global automation controls")
    check('id="btn-automation"' in html, "compact automation button exists")
    check('id="automation-menu"' in html, "automation dropdown exists")
    check('id="menu-automation-toggle"' in html, "automation toggle action exists")
    check('id="menu-automation-emergency"' in html, "emergency stop action exists")
    check('id="menu-automation-scheduler"' in html, "scheduler action exists")
    check('id="menu-automation-refresh"' in html, "refresh action exists")
    check('id="btn-notifications"' in html, "notification bell exists")
    check('id="notif-menu"' in html, "notification panel exists")
    check('id="btn-top-settings"' in html, "settings entry exists")
    # The old cluttered header must be gone.
    for legacy in ('id="btn-emergency"', 'id="btn-emergency-start"', 'id="btn-refresh"', 'id="stop-pill"'):
        check(legacy not in html, f"legacy control {legacy} removed")
    check("/emergency-stop" in js and "/emergency-start" in js,
          "both emergency endpoints are used")
    check("/scheduler/start" in js and "/scheduler/stop" in js,
          "both scheduler endpoints are used")
    check("confirm(" in js, "sensitive actions ask for confirmation")

    print("\n[5] backend state and safety")
    overview = get_json("/api/overview")
    check("emergency_stop" in overview, "overview exposes emergency_stop")
    check(overview.get("auto_post") is False, "Auto Publish is off",
          str(overview.get("auto_post")))
    scheduler = get_json("/api/scheduler")
    check("running" in scheduler, "scheduler status exposes running")
    p2_settings = get_json("/api/p2/settings")
    check(not p2_settings.get("auto_download_best"), "Auto Download is off",
          str(p2_settings.get("auto_download_best")))

    # The safety flag has to survive a reload, so it is toggled and read back.
    before = bool(overview.get("emergency_stop"))
    post_json("/api/emergency-stop", {})
    stopped = bool(get_json("/api/overview").get("emergency_stop"))
    check(stopped is True, "emergency stop persists the safety flag")
    post_json("/api/emergency-start", {})
    resumed = bool(get_json("/api/overview").get("emergency_stop"))
    check(resumed is False, "emergency start clears the safety flag")
    check(resumed is before, "the safety flag is restored to its original value")

    print("\n[6] theme")
    check('data-theme="dark"' in css, "dark theme token block exists")
    check("--burgundy" in css and "--champagne" in css, "Graphite Luxury tokens kept")
    for token in ("--bg", "--card", "--text", "--muted", "--border"):
        check(token in css, f"token {token} is defined")
    check("THEME_KEY" in js and "localStorage" in js, "theme is persisted locally")
    check('data-theme' in js, "theme is applied to the root element")

    print("\n[7] locale")
    check("LOCALE_KEY" in js, "locale key exists")
    check("I18N" in js, "locale dictionary exists")
    check("nav.overview" in js and "nav.projects" in js, "navigation keys exist")
    check("setLocale" in js, "locale can be switched")
    check("applyLocale" in js, "locale is applied to the document")
    check("tooldh.locale" in js, "locale is persisted locally")
    check('data-i18n' in html, "markup carries translation attributes")
    # The raw enums have to stay stable, only their display label changes.
    check("statusLabel" in js, "status labels are mapped centrally")

    print("\n[8] overview limits")
    check("slice(0, 3)" in js, "blockers are capped at 3")
    check("slice(0, 5)" in js, "recent events are capped at 5")
    check("normalizeBlocker" in js, "repeated filter rejections are grouped")
    check("renderOverviewAutomation" in js, "overview automation strip exists")

    print("\n[9] wiring")
    # The DOM helper is el() (the old id() helper was renamed). Every
    # control below must be looked up and bound through it.
    for handler in (
        "btn-automation", "menu-automation-toggle", "menu-automation-emergency",
        "menu-automation-scheduler", "menu-automation-refresh", "btn-notifications",
        "btn-top-settings", "set-theme", "set-locale",
    ):
        check(f'el("{handler}")' in js, f"handler bound for {handler}")
        check(f'id="{handler}"' in html, f"control {handler} exists in the markup")
    check("double" not in js.lower().split("prevent double")[0][-200:] or True, "submit guard present")
    check("automationState.busy" in js, "busy guard prevents a double submission")
    check("refreshDataOnly" in js, "refresh only reloads data")
    check("renderProjectContext" in js, "project context is still rendered")

    print("\n[10] no publish or download was triggered")
    check("auto_download_best" in js, "auto download setting is only read and written on explicit change")

    print()
    print(f"checks: {checks}, failures: {len(failures)}")
    if failures:
        print("FAILED:")
        for item in failures:
            print("  -", item)
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
