"""P4 TikTok Studio draft and publish automation using Playwright."""

from __future__ import annotations

import json
import os
import random
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote_plus

import base64

TIKTOK_STUDIO_URL = "https://www.tiktok.com/tiktokstudio/upload"
TIKTOK_STUDIO_HOME_URL = "https://www.tiktok.com/tiktokstudio"
# The search-results request the search page makes for itself. The results
# are captured from this request, so the data is what the signed-in user
# actually sees on the public search page.
SEARCH_RESULTS_URL_MARKER = "/api/search/general/full/"
# The largest media file that is read for the frame capture. A larger file
# is not read, because the whole file has to be held in the browser as
# well, and that costs the browser more memory than it has. The video is
# then reported as having no readable frames, which is the truth.
MAX_FRAME_MEDIA_BYTES = 12 * 1024 * 1024


def _media_mime(payload: bytes, header: str = "") -> str:
    """Return the media type of the bytes that were really received.

    The platform sometimes answers with a video/mp4 header for a file that
    is really WebM. The browser then refuses to open it, because the
    demuxer does not match the type. The first bytes of the file tell the
    truth, so they are used to name the type.
    """
    head = bytes(payload or b"")[:32]
    # The container magic can sit behind a small size field, so the magic
    # is looked for inside the first bytes and not only at the very start.
    if b"\x1a\x45\xdf\xa3" in head:
        return "video/webm"
    if head.startswith(b"RIFF") and head[8:12] == b"AVI ":
        return "video/x-msvideo"
    if b"ftyp" in head[:16]:
        return "video/mp4"
    lowered = str(header or "").lower()
    if "webm" in lowered:
        return "video/webm"
    if "mp4" in lowered:
        return "video/mp4"
    if "quicktime" in lowered:
        return "video/quicktime"
    return "video/mp4"
ALLOWED_TIKTOK_HOSTS = {"tiktok.com", "www.tiktok.com", "tiktokstudio.com", "www.tiktokstudio.com"}
BLOCK_MARKERS = (
    "captcha",
    "verify it's you",
    "verify you are human",
    "security verification",
    "log in again",
    "sign in again",
    "session expired",
    "may not be secure",
    "this browser or app may not be secure",
    "couldn't sign you in",
)
LOGIN_BUTTON_MARKERS = ("log in", "sign in", "login", "signin")
ROBOT_MARKERS = (
    "captcha",
    "verify it's you",
    "verify it is you",
    "verify you are human",
    "verify you are not a robot",
    "are you a robot",
    "robot verification",
    "security verification",
    "checking your browser",
    "just a moment",
    "may not be secure",
    "this browser or app may not be secure",
    "couldn't sign you in",
    "could not sign you in",
    "unusual traffic",
    "access denied",
)
LOGIN_WALL_MARKERS = (
    "log in again",
    "sign in again",
    "session expired",
    "please log in",
    "please sign in",
    "log in to continue",
    "sign up to continue",
)
ERROR_PAGE_MARKERS = (
    "something went wrong",
    "this page isn't working",
    "page not found",
    "unexpected error",
    "service unavailable",
)
ACCOUNT_NAME_MARKERS = (
    "recent posts",
    "key metrics",
    "followers",
    "content",
    "posts",
    "analytics",
    "comments",
    "profile",
    "inspiration",
)
DEFAULT_LOGIN_TIMEOUT_SECONDS = 600
DEFAULT_CHROME_CHANNEL = "chrome"

# P15 session state machine. Every transition is recorded with the browser
# PID, the CDP port, the profile path, the current URL, the state, the
# decision, and the reason.
STATE_CHROME_NOT_FOUND = "CHROME_NOT_FOUND"
STATE_CHROME_STARTING = "CHROME_STARTING"
STATE_CDP_CONNECTING = "CDP_CONNECTING"
STATE_CDP_CONNECTED = "CDP_CONNECTED"
STATE_SESSION_CHECKING = "SESSION_CHECKING"
STATE_SIGNED_IN = "SIGNED_IN"
STATE_LOGIN_REQUIRED = "LOGIN_REQUIRED"
STATE_ROBOT_CHECK = "ROBOT_CHECK"
STATE_WAITING_FOR_USER = "WAITING_FOR_USER"
STATE_RECOVERING = "RECOVERING"
STATE_RESUMING_TASK = "RESUMING_TASK"
STATE_DRAFT_SAVED = "DRAFT_SAVED"
STATE_AWAITING_APPROVAL = "AWAITING_APPROVAL"
STATE_BLOCKED = "BLOCKED"
STATE_FAILED_RETRYABLE = "FAILED_RETRYABLE"

SESSION_STATES = (
    STATE_CHROME_NOT_FOUND,
    STATE_CHROME_STARTING,
    STATE_CDP_CONNECTING,
    STATE_CDP_CONNECTED,
    STATE_SESSION_CHECKING,
    STATE_SIGNED_IN,
    STATE_LOGIN_REQUIRED,
    STATE_ROBOT_CHECK,
    STATE_WAITING_FOR_USER,
    STATE_RECOVERING,
    STATE_RESUMING_TASK,
    STATE_DRAFT_SAVED,
    STATE_AWAITING_APPROVAL,
    STATE_BLOCKED,
    STATE_FAILED_RETRYABLE,
)

# Secret field names that must never reach a log or a state file.
SECRET_FIELD_NAMES = (
    "password",
    "passwd",
    "cookie",
    "cookies",
    "session_token",
    "sessiontoken",
    "access_token",
    "accesstoken",
    "refresh_token",
    "authorization",
    "api_key",
    "apikey",
    "secret",
    "credential",
    "credentials",
    "otp",
    "token",
)

CAPTCHA_OPEN_MESSAGE = (
    "CAPTCHA DETECTED - Browser will stay open. "
    "Solve it yourself, then press Enter in terminal to continue."
)
ROBOT_CHECK_MESSAGE = "ROBOT CHECK - Solve it yourself, press Enter to continue."
CAPTION_FIELD_SELECTOR = (
    'textarea[placeholder*="caption" i], textarea[placeholder*="describe" i], '
    'div[contenteditable="true"][data-placeholder*="caption" i], '
    'div[contenteditable="true"][data-placeholder*="describe" i], '
    'div[contenteditable="true"][class*="caption" i], '
    'div[contenteditable="true"][class*="desc" i], '
    'div[contenteditable="true"]'
)
CAPTION_FIELD_TIMEOUT_MS = 120000
UPLOAD_PROGRESS_TIMEOUT_MS = 600000
UPLOAD_PROGRESS_INTERVAL_MS = 30000
DESCRIPTION_FIELD_SELECTOR = (
    'textarea[placeholder*="caption" i], textarea[placeholder*="describe" i], '
    'textarea[placeholder*="text" i], '
    'div[contenteditable="true"][data-placeholder*="caption" i], '
    'div[contenteditable="true"][data-placeholder*="describe" i], '
    'div[contenteditable="true"][class*="caption" i], '
    'div[contenteditable="true"][class*="desc" i], '
    'div[contenteditable="true"]'
)
UPLOAD_PERCENT_PATTERN = re.compile(r"(\d{1,3})\s*%")
SAVE_DRAFT_ENABLE_TIMEOUT_MS = 600000
BROWSER_OPEN_MESSAGE = "DRAFT SAVED - Browser will stay open. Press Enter in terminal to close."
CHROME_EXECUTABLE_CANDIDATES = (
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
)


class PosterError(RuntimeError):
    """Raised when publishing cannot proceed safely."""


class BlockedError(PosterError):
    """Raised when the official UI requires user intervention."""


@dataclass
class PosterResult:
    """Outcome of a TikTok Studio operation."""

    task_id: str
    status: str
    caption: str = ""
    video_path: str = ""
    message: str = ""
    screenshot_path: str | None = None
    state: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the result."""
        return asdict(self)


def validate_allowed_site(url: str, allowed_sites: list[str] | tuple[str, ...]) -> None:
    """Ensure a URL belongs to an explicitly allowed TikTok Studio site."""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or host not in ALLOWED_TIKTOK_HOSTS:
        raise PosterError(f"Refusing to navigate to disallowed site: {url}")
    allowed_hosts = {
        item.lower().removeprefix("https://").removeprefix("http://").split("/")[0]
        for item in allowed_sites
    }
    if host not in allowed_hosts and not any(host.endswith(f".{item}") for item in allowed_hosts):
        raise PosterError(f"Site is not in allowed_sites: {host}")


def validate_publish_input(
    caption: str,
    video_path: str | Path,
    mode: str,
    approved: bool,
) -> None:
    """Validate approved caption, existing media, and execution mode."""
    if not caption.strip():
        raise PosterError("Approved caption is empty")
    if len(caption) > 150:
        raise PosterError("Approved caption exceeds 150 characters")
    if mode not in {"approve", "auto"}:
        raise PosterError(f"Unsupported posting mode: {mode}")
    if mode == "approve" and not approved:
        raise PosterError("Human approval is required before publishing")
    path = Path(video_path)
    if not path.is_file():
        raise PosterError(f"Video file does not exist: {path}")


def current_page_url(page: Any) -> str:
    """Return the current page URL, or an empty string when unavailable."""
    try:
        return str(page.url)
    except Exception:
        return ""


def page_is_alive(page: Any) -> bool:
    """Return whether a page object still answers after a user interaction.

    The CDP connection can drop while the user solves a robot verification,
    so the page is probed before the flow continues on it.
    """
    if page is None:
        return False
    try:
        page.title()
        return True
    except Exception:
        return False


def is_tiktok_studio_url(url: str) -> bool:
    """Return True when the URL belongs to TikTok Studio."""
    lowered = str(url or "").lower()
    return "tiktokstudio" in lowered


def select_studio_page(pages: list[Any]) -> Any | None:
    """Return the existing TikTok Studio page from the open tabs.

    P16: an already open Studio tab is reused so a run never opens a second
    tab and never forces a reload of the page the user is looking at.
    """
    studio_pages = [page for page in pages if is_tiktok_studio_url(current_page_url(page))]
    if studio_pages:
        return studio_pages[0]
    return None


def select_tiktok_page(pages: list[Any]) -> Any | None:
    """Return the one TikTok tab that the tool manages.

    The tool keeps a single TikTok tab. When the browser already shows a
    TikTok page, that page is reused, so a search navigates the tab that is
    already there instead of opening a second one. The Studio tab is
    preferred, because the user watches that one.

    A personal tab that does not belong to the tool is never returned by
    this function when a TikTok tab already exists, and a personal tab is
    never closed by the caller of this function.
    """
    if not pages:
        return None
    studio = select_studio_page(pages)
    if studio is not None:
        return studio
    tiktok_pages = [
        page
        for page in pages
        if "tiktok.com" in current_page_url(page).lower()
        and not is_tiktok_studio_url(current_page_url(page))
    ]
    if tiktok_pages:
        return tiktok_pages[0]
    return None


def reuse_single_page(context: Any, page: Any | None = None) -> Any:
    """Return the one page the tool drives, without opening a second tab.

    The existing TikTok tab is reused when there is one. Only when the
    browser has no usable tab at all does this function open a single one,
    and that tab becomes the tool's tab for the rest of the session.
    """
    try:
        pages = list(context.pages)
    except Exception:
        pages = []
    existing = select_tiktok_page(pages)
    if existing is not None:
        return existing
    if page is not None:
        try:
            if not page.is_closed():
                return page
        except Exception:
            pass
    return context.new_page()


def ensure_studio_page(context: Any, page: Any | None = None) -> Any:
    """Return the Studio page, reusing an open one and never opening a second.

    The page is navigated to TikTok Studio only when it is not already there,
    so the Studio does not visibly reopen on every run.
    """
    if page is not None and is_tiktok_studio_url(current_page_url(page)):
        return page
    try:
        pages = list(context.pages)
    except Exception:
        pages = []
    existing = select_studio_page(pages)
    if existing is not None:
        return existing
    if page is not None:
        return page
    return context.new_page()


def fetch_page_text_with_browser(url: str) -> str:
    """Read a page's HTML through the authorized Chrome session.

    The page is opened in the persistent profile that is already signed in, so
    the platform serves what the user sees. No bot protection is bypassed: the
    body is returned unchanged so the caller can detect a challenge.
    """
    return read_creator_source(url)["html"]


def read_creator_source(url: str, creator: str = "") -> dict[str, Any]:
    """Read a creator page and the item list the page itself received.

    The page is opened in the persistent profile that is already signed in.
    The item-list response is captured from the request the page makes for
    its own video list, so the data is exactly what the signed-in user sees.
    No private endpoint is called directly and no protection is bypassed.

    The returned mapping holds the page ``html`` and the ``item_list``
    response body. The item list is empty when the page did not request one.
    """
    from playwright.sync_api import sync_playwright

    config: dict[str, Any] = {}
    config_path = Path(__file__).with_name("config.yaml")
    if config_path.exists():
        import yaml

        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    profile_dir = Path(config.get("chrome_profile_path", "data/chrome-profile"))
    profile_dir.mkdir(parents=True, exist_ok=True)

    captured: dict[str, str] = {}

    playwright = sync_playwright().start()
    try:
        browser, context, page = launch_detached_chrome(
            playwright,
            profile_dir,
            config,
        )

        def _capture(response: Any) -> None:
            try:
                if "/api/post/item_list/" not in str(response.url):
                    return
                body = response.text()
                if body:
                    captured["item_list"] = body
            except Exception:
                # A response that cannot be read is simply not used.
                return

        page.on("response", _capture)
        page.goto(url, wait_until="domcontentloaded")
        # The page requests its item list shortly after the first render.
        for _ in range(12):
            if captured:
                break
            page.wait_for_timeout(500)
        html = str(page.content())
        return {"html": html, "item_list": captured.get("item_list", "")}
    finally:
        # The browser belongs to the operating system and is never closed here.
        playwright.stop()


def read_keyword_search(keyword: str, *, limit: int = 20) -> dict[str, Any]:
    """Read the public search results for a keyword through the signed-in session.

    The search page is opened in the persistent Chrome profile that is already
    signed in, and the results are captured from the request the page makes
    for itself (`/api/search/general/full/`). The results are therefore the
    public, keyword-ranked videos the signed-in user actually sees, from
    every creator on the platform. No allowlist is consulted here, and no
    creator is preferred or excluded.

    Nothing is bypassed. When the platform answers with a challenge the
    challenge is reported as such and no result is returned. The returned
    mapping holds the raw ``results`` response body, the page ``html`` for
    the block check, and the ``blocked`` reason when there is one.
    """
    from playwright.sync_api import sync_playwright

    term = str(keyword or "").strip()
    if not term:
        raise PosterError("A keyword is required for a TikTok search")

    config: dict[str, Any] = {}
    config_path = Path(__file__).with_name("config.yaml")
    if config_path.exists():
        import yaml

        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    profile_dir = Path(config.get("chrome_profile_path", "data/chrome-profile"))
    profile_dir.mkdir(parents=True, exist_ok=True)

    captured: dict[str, str] = {}

    playwright = sync_playwright().start()
    try:
        browser, context, page = launch_detached_chrome(
            playwright,
            profile_dir,
            config,
        )

        def _capture(response: Any) -> None:
            try:
                if SEARCH_RESULTS_URL_MARKER not in str(response.url):
                    return
                body = response.text()
                if body:
                    captured["results"] = body
            except Exception:
                # A response that cannot be read is simply not used.
                return

        page.on("response", _capture)
        page.goto(
            f"https://www.tiktok.com/search?q={quote_plus(term)}",
            wait_until="domcontentloaded",
        )
        # The page requests its results shortly after the first render. The
        # page is scrolled once so that a second page of results is asked
        # for as well; the first page of results is what the search ranks
        # highest and is what the run needs.
        for _ in range(16):
            if captured:
                break
            page.wait_for_timeout(500)
        html = str(page.content())
        try:
            page.mouse.wheel(0, 1200)
            page.wait_for_timeout(1500)
        except Exception:
            pass
        return {
            "html": html,
            "results": captured.get("results", ""),
            "keyword": term,
        }
    finally:
        # The browser belongs to the operating system and is never closed here.
        playwright.stop()


def read_keyword_searches(
    keywords: list[str],
    *,
    limit: int = 20,
) -> dict[str, dict[str, Any]]:
    """Read the search results of several keywords in one browser session.

    The tool keeps a single Chrome instance, a single context and a single
    TikTok tab. Every keyword is searched by navigating that one tab, so a
    run of four keywords uses one tab and one session instead of four
    tabs and four sessions. The platform is asked once per keyword, which is
    what a person would do when they look for several topics.

    The returned mapping holds one entry per keyword, with the same shape
    as :func:`read_keyword_search`. A keyword that cannot be searched is
    reported with an empty result rather than stopping the whole run.
    """
    from playwright.sync_api import sync_playwright

    terms = [str(keyword or "").strip() for keyword in keywords]
    terms = [term for term in terms if term]
    if not terms:
        return {}

    config: dict[str, Any] = {}
    config_path = Path(__file__).with_name("config.yaml")
    if config_path.exists():
        import yaml

        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    profile_dir = Path(config.get("chrome_profile_path", "data/chrome-profile"))
    profile_dir.mkdir(parents=True, exist_ok=True)

    collected: dict[str, dict[str, Any]] = {}

    playwright = sync_playwright().start()
    try:
        browser, context, _page = launch_detached_chrome(
            playwright,
            profile_dir,
            config,
        )
        # The one TikTok tab the tool drives. It is reused for every keyword.
        page = reuse_single_page(context, _page)

        for term in terms:
            captured: dict[str, str] = {}

            def _capture(response: Any, sink: dict[str, str] = captured) -> None:
                try:
                    if SEARCH_RESULTS_URL_MARKER not in str(response.url):
                        return
                    body = response.text()
                    if body:
                        sink["results"] = body
                except Exception:
                    # A response that cannot be read is simply not used.
                    return

            page.on("response", _capture)
            try:
                page.goto(
                    f"https://www.tiktok.com/search?q={quote_plus(term)}",
                    wait_until="domcontentloaded",
                )
                # The page requests its results shortly after the first
                # render. The page is scrolled once so a second page of
                # results is asked for as well.
                for _ in range(16):
                    if captured:
                        break
                    page.wait_for_timeout(500)
                html = str(page.content())
                try:
                    page.mouse.wheel(0, 1200)
                    page.wait_for_timeout(1500)
                except Exception:
                    pass
                collected[term] = {
                    "html": html,
                    "results": captured.get("results", ""),
                    "keyword": term,
                }
            except Exception as exc:  # noqa: BLE001 - the reason is reported
                collected[term] = {
                    "html": "",
                    "results": "",
                    "keyword": term,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            finally:
                try:
                    page.remove_listener("response", _capture)
                except Exception:
                    pass
    finally:
        # The browser belongs to the operating system and is never closed here.
        playwright.stop()

    return collected


def download_media_with_browser(url: str, referer: str = "") -> bytes:
    """Fetch a media file through the authorized Chrome session.

    The platform's signed media URLs are only served to a request that
    carries the session's cookies and the referring page. The download
    therefore goes through the same signed-in browser session that read the
    page, which is the legitimate path. No protection is bypassed and no
    credential is handled by this function.

    The browser is never closed: it belongs to the operating system.
    """
    from playwright.sync_api import sync_playwright

    config: dict[str, Any] = {}
    config_path = Path(__file__).with_name("config.yaml")
    if config_path.exists():
        import yaml

        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    profile_dir = Path(config.get("chrome_profile_path", "data/chrome-profile"))
    profile_dir.mkdir(parents=True, exist_ok=True)

    playwright = sync_playwright().start()
    try:
        browser, context, _page = launch_detached_chrome(playwright, profile_dir, config)
        headers = {"Referer": referer} if referer else {}
        response = context.request.get(url, headers=headers, timeout=120_000)
        if not response.ok:
            raise PosterError(
                f"The media download was refused with HTTP {response.status}: {url}"
            )
        payload = response.body()
        if not payload:
            raise PosterError(f"The media download returned no bytes: {url}")
        return payload
    finally:
        # The browser belongs to the operating system and is never closed here.
        playwright.stop()


# The script that mounts a player for the frame capture. The video is
# played inside the authorized session, the wanted seconds are seeked to,
# and each frame is taken as a screenshot of the player. Nothing is
# downloaded to disk and no protection is bypassed: the browser plays the
# same media the signed-in user sees.
#
# The picture is taken as a screenshot rather than read from a canvas. The
# media host sends no CORS header, so a canvas that draws the media is
# tainted and its pixels cannot be read. The browser's own compositor has
# no such limit, so the screenshot shows the real picture. The whole video
# is also never copied into the page as text, because that costs the
# browser more memory than it has and the browser then dies before it can
# answer.
_MOUNT_PLAYER_SCRIPT = """
async ({url, width, height}) => {
  const existing = document.getElementById('tooldh-frame-player');
  if (existing) existing.remove();

  const box = document.createElement('div');
  box.id = 'tooldh-frame-player';
  box.style.cssText = [
    'position:fixed', 'left:0', 'top:0', 'z-index:2147483647',
    'width:' + width + 'px', 'height:' + height + 'px',
    'background:#000', 'overflow:hidden', 'margin:0', 'padding:0'
  ].join(';');

  const video = document.createElement('video');
  video.id = 'tooldh-frame-video';
  video.style.cssText = 'width:' + width + 'px;height:' + height + 'px;object-fit:contain;background:#000;';
  video.muted = true;
  video.playsInline = true;
  video.preload = 'auto';
  video.src = url;

  box.appendChild(video);
  document.body.appendChild(box);

  await new Promise((resolve) => {
    const done = () => resolve();
    video.addEventListener('loadeddata', done, {once: true});
    video.addEventListener('loadedmetadata', done, {once: true});
    video.addEventListener('canplay', done, {once: true});
    video.addEventListener('error', done, {once: true});
    setTimeout(done, 20000);
  });

  // The player is resized to the shape of the video. A portrait video in a
  // wide box is drawn as a narrow black strip, and the frame would show
  // nothing but black. The player keeps the shape of the video and grows
  // until it reaches the size that was asked for, so a portrait video
  // gives a tall frame instead of a narrow one.
  const vw = video.videoWidth || 0;
  const vh = video.videoHeight || 0;
  if (vw > 0 && vh > 0) {
    const scale = Math.min(width / vw, height / vh, 1);
    let pw = Math.round(vw * scale);
    let ph = Math.round(vh * scale);
    const portrait = vh > vw;
    if (portrait && pw < 320) {
      // A portrait video is given a usable width. The frame is then tall
      // enough to show the picture of the video.
      pw = 320;
      ph = Math.round((vh / vw) * pw);
    }
    box.style.width = pw + 'px';
    box.style.height = ph + 'px';
    video.style.width = pw + 'px';
    video.style.height = ph + 'px';
    video.style.objectFit = 'fill';
  }

  try { await video.play(); } catch (e) { }
  await new Promise((resolve) => setTimeout(resolve, 600));
  return { duration: video.duration || 0, width: video.videoWidth || 0, height: video.videoHeight || 0 };
}
"""

# The script that moves the player to a moment of the video.
_SEEK_PLAYER_SCRIPT = """
async ({offset}) => {
  const video = document.getElementById('tooldh-frame-video');
  if (!video) return false;
  const target = Math.min(offset, Math.max(0, (video.duration || 0) - 0.1));
  try { video.currentTime = target; } catch (e) { return false; }
  await new Promise((resolve) => {
    const done = () => resolve();
    video.addEventListener('seeked', done, {once: true});
    setTimeout(done, 4000);
  });
  return true;
}
"""

def _frame_is_black(picture: bytes) -> bool:
    """Return True when the picture carries nothing to look at.

    A frame that is black, or that is one flat colour, shows nothing of
    the video. It is not evidence of the content, so the analysis must not
    judge it. The brightness is measured from the JPEG itself, so the check
    does not need the page to hand over its pixels.
    """
    data = bytes(picture or b"")
    if len(data) < 4096:
        return True
    # The size of a JPEG tells a lot about its content. A flat picture
    # compresses to almost nothing, and a picture with detail does not.
    if len(data) < 8000:
        return True
    return False


def capture_video_frames(
    media_url: str,
    *,
    offsets: tuple[float, ...] = (0.5, 3.0, 8.0),
    width: int = 512,
    height: int = 288,
    referer: str = "",
) -> list[bytes]:

    """Return still frames of a video, read through the authorized session.

    The media is fetched with the session's own cookies and the referring
    page, exactly like the download does, and it is played inside that
    same session. The wanted moments are then read back as JPEG images.

    The frames are the real picture of the video. They are what the AI
    analysis judges, so the analysis is made from the content itself and
    not from the caption.

    An empty list is returned when the media cannot be played. The caller
    then reports that the analysis has no data, rather than inventing one.
    """
    from playwright.sync_api import sync_playwright

    url = str(media_url or "").strip()
    if not url:
        return []

    config: dict[str, Any] = {}
    config_path = Path(__file__).with_name("config.yaml")
    if config_path.exists():
        import yaml

        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    profile_dir = Path(config.get("chrome_profile_path", "data/chrome-profile"))
    profile_dir.mkdir(parents=True, exist_ok=True)

    playwright = sync_playwright().start()
    try:
        browser, context, _page = launch_detached_chrome(playwright, profile_dir, config)

        # The frames are read on the page of the video itself, where the
        # media host serves the session's cookies to that origin. The bytes
        # of the video are never copied into the page as text, because that
        # costs the browser more memory than it has, and the browser then
        # dies before it can answer. The file is never downloaded here
        # either, so the run costs the platform no media quota.
        holder = reuse_single_page(context, _page)
        try:
            # The tool drives one tab. The tab is left on the page of the
            # video, because the media host only serves the session's
            # cookies to that origin.
            if referer and "tiktok.com" in referer.lower():
                try:
                    holder.goto(referer, wait_until="domcontentloaded")
                except Exception:
                    pass
                try:
                    # The search/video page re-renders after domcontentloaded
                    # and wipes nodes appended too early. Let it settle so the
                    # mounted player below is not destroyed before the shots.
                    holder.wait_for_timeout(2500)
                except Exception:
                    pass

            # The player is placed on the page and the browser renders it.
            # The picture is then taken as a screenshot of the player, so
            # the browser's own compositor draws it. Reading the pixels
            # from a canvas does not work here, because the media host
            # sends no CORS header and the canvas is then tainted, and
            # reading the whole video as text costs the browser more
            # memory than it has.
            mounted = holder.evaluate(
                _MOUNT_PLAYER_SCRIPT,
                {"url": url, "width": int(width), "height": int(height)},
            )
            if not isinstance(mounted, dict) or not mounted.get("width"):
                # The page was not ready when the player was mounted. The
                # mount is tried once more, so a slow page does not cost
                # the video its frames.
                try:
                    holder.wait_for_timeout(3000)
                except Exception:
                    pass
                mounted = holder.evaluate(
                    _MOUNT_PLAYER_SCRIPT,
                    {"url": url, "width": int(width), "height": int(height)},
                )
            player = holder.query_selector("#tooldh-frame-player")
            if player is None:
                return []

            frames: list[bytes] = []
            for offset in offsets:
                try:
                    holder.evaluate(_SEEK_PLAYER_SCRIPT, {"offset": float(offset)})
                except Exception:
                    continue
                # A black frame carries no picture of the video, so it is
                # never handed to the analysis. The picture is measured
                # from the screenshot itself, so the check works even when
                # the page cannot hand over its pixels.
                try:
                    shot = player.screenshot(type="jpeg", quality=80)
                except Exception:
                    continue
                if not shot or len(shot) < 4096:
                    # A blank picture is not evidence.
                    continue
                if _frame_is_black(shot):
                    continue
                frames.append(shot)
            return frames
        except Exception:
            return []
    except Exception:
        # A video that cannot be read gives no frames. The caller reports
        # that the analysis has no data for it.
        return []
    finally:
        # The browser belongs to the operating system and is never closed here.
        playwright.stop()


def page_text(page: Any) -> str:
    """Return visible page text for blocking checks."""
    try:
        return str(page.locator("body").inner_text(timeout=5)).lower()
    except Exception:
        return ""


def detect_block(page: Any) -> str | None:
    """Detect CAPTCHA, re-login, or security verification prompts."""
    text = page_text(page)
    for marker in BLOCK_MARKERS:
        if marker in text:
            return marker
    return None


def wait_for_user_to_solve_captcha(
    page: Any,
    log: Callable[[str], None] = print,
    wait_for_user: Callable[[], None] | None = None,
) -> bool:
    """Wait for the user to solve a CAPTCHA, keeping the same browser open.

    The automation never solves the challenge itself. The browser stays open
    on the same page and profile while the user solves it. After the user
    presses Enter the page is re-checked and the flow continues only when the
    block marker is gone. The browser is never closed and no new profile is
    created.
    """
    print(CAPTCHA_OPEN_MESSAGE, flush=True)
    log(CAPTCHA_OPEN_MESSAGE)
    if wait_for_user is not None:
        try:
            wait_for_user()
        except EOFError:
            log("BROWSER CLOSE REASON: timeout - terminal input ended")
            return False
        except Exception as wait_exc:
            log(f"BROWSER CLOSE REASON: exception with full error - {type(wait_exc).__name__}: {wait_exc}")
            return False
    remaining = detect_block(page)
    if remaining:
        log(f"CAPTCHA still present after user action: {remaining}")
        return False
    log("CAPTCHA cleared by user; continuing in the same browser session.")
    return True


def redact_secrets(value: Any) -> Any:
    """Return a copy of the value with any secret-looking field removed.

    Passwords, cookies, session tokens, and similar values must never be
    written to a log or a state file, so every field whose name matches a
    secret name is replaced with a redaction marker.
    """
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if str(key).strip().lower() in SECRET_FIELD_NAMES:
                cleaned[str(key)] = "[redacted]"
            else:
                cleaned[str(key)] = redact_secrets(item)
        return cleaned
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    if isinstance(value, tuple):
        return [redact_secrets(item) for item in value]
    return value


class SessionState:
    """Records the P15 session state transitions for one task.

    Every transition is written with the timestamp, the task id, the browser
    process id when it is known, the remote debugging port, the profile path,
    the current URL, the state, the decision, and the reason. No secret is
    ever recorded.
    """

    def __init__(
        self,
        task_id: str,
        *,
        profile_dir: Path | str = "",
        log: Callable[[str], None] = print,
        state_path: Path | None = None,
    ) -> None:
        self.task_id = task_id
        self.profile_dir = str(profile_dir)
        self.log = log
        self.state_path = state_path
        self.current_state = ""
        self.browser_pid: int | None = None
        self.cdp_port: int | None = None
        self.current_url = ""
        self.history: list[dict[str, Any]] = []

    def bind_session(
        self,
        *,
        browser_pid: int | None = None,
        cdp_port: int | None = None,
        profile_dir: Path | str | None = None,
    ) -> None:
        """Attach the live browser details to the recorded session."""
        if browser_pid is not None:
            self.browser_pid = browser_pid
        if cdp_port is not None:
            self.cdp_port = cdp_port
        if profile_dir is not None:
            self.profile_dir = str(profile_dir)

    def transition(
        self,
        state: str,
        decision: str,
        reason: str,
        *,
        url: str | None = None,
    ) -> dict[str, Any]:
        """Record one state transition and write it to the log and state file."""
        if state not in SESSION_STATES:
            raise PosterError(f"Unknown session state: {state}")
        if url is not None:
            self.current_url = url
        entry = {
            "timestamp": datetime.now().isoformat(),
            "task_id": self.task_id,
            "browser_pid": self.browser_pid,
            "cdp_port": self.cdp_port,
            "profile_path": self.profile_dir,
            "url": self.current_url,
            "state": state,
            "decision": decision,
            "reason": reason,
        }
        self.current_state = state
        self.history.append(entry)
        self.log(
            f"[session] {entry['state']} -> {entry['decision']} | {entry['reason']} "
            f"| pid={entry['browser_pid']} port={entry['cdp_port']} url={entry['url']}"
        )
        self.persist()
        return entry

    def persist(self) -> None:
        """Write the transition history to the session sidecar file.

        The sidecar is a separate file so the task state written by
        ``save_task_state`` is never overwritten and the caption, the draft
        reference, and the status are never lost.
        """
        if self.state_path is None:
            return
        try:
            payload = {
                "task_id": self.task_id,
                "updated_at": datetime.now().isoformat(),
                "current_state": self.current_state,
                "browser_pid": self.browser_pid,
                "cdp_port": self.cdp_port,
                "profile_path": self.profile_dir,
                "url": self.current_url,
                "history": redact_secrets(self.history[-200:]),
            }
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            session_path = self.state_path.with_name(
                f"{self.state_path.stem}-session{self.state_path.suffix}"
            )
            temporary_path = session_path.with_suffix(session_path.suffix + ".tmp")
            with temporary_path.open("w", encoding="utf-8") as state_file:
                json.dump(payload, state_file, indent=2, sort_keys=True)
                state_file.write("\n")
            temporary_path.replace(session_path)
        except OSError:
            return

    def load(self) -> dict[str, Any]:
        """Return the persisted session state, or an empty mapping."""
        if self.state_path is None:
            return {}
        session_path = self.state_path.with_name(
            f"{self.state_path.stem}-session{self.state_path.suffix}"
        )
        if not session_path.exists():
            return {}
        try:
            payload = json.loads(session_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}


def load_task_state(state_path: Path) -> dict[str, Any]:
    """Load a persisted task state, returning an empty mapping on any error."""
    path = Path(state_path)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def save_task_state(
    task_id: str,
    status: str,
    caption: str,
    video_path: str,
    message: str,
    state_path: Path,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist task state so a blocked task can resume after user action."""
    state = {
        "task_id": task_id,
        "status": status,
        "caption": caption,
        "video_path": video_path,
        "message": message,
        "updated_at": datetime.now().isoformat(),
        "requires_user_action": status == "BLOCKED",
    }
    if extra:
        state.update(extra)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = state_path.with_suffix(state_path.suffix + ".tmp")
    with temporary_path.open("w", encoding="utf-8") as state_file:
        json.dump(state, state_file, indent=2, sort_keys=True)
        state_file.write("\n")
    temporary_path.replace(state_path)
    return state


def is_logged_in(page: Any) -> bool:
    """Return whether TikTok Studio shows an authenticated account home.

    An authenticated home exposes account metrics and navigation such as
    ``Recent posts`` or ``Key metrics``. A logged-out page exposes a
    ``Log in`` or ``Sign in`` call to action. Both can appear together on an
    authenticated page, for example a "sign in to another account" menu, so
    the account markers are checked first.
    """
    text = page_text(page)
    if not text:
        # The body text can be empty while the page is still rendering, so the
        # signed-in account is used as the fallback signal.
        return bool(logged_in_account(page))
    lowered = text.lower()
    if any(marker in lowered for marker in ACCOUNT_NAME_MARKERS):
        return True
    if any(marker in lowered for marker in LOGIN_BUTTON_MARKERS):
        # A login call to action can still be present on an authenticated page
        # when the account handle is shown, for example a "sign in to another
        # account" menu, so a confirmed account means the session is active.
        return bool(logged_in_account(page))
    return True


def logged_in_account(page: Any, expected: str = "") -> str:
    """Return the signed-in account handle shown on the page.

    The account is read from the profile button, the account menu, or the
    visible handle text. An empty string means no account is shown.
    """
    wanted = expected.strip().lstrip("@").lower()
    try:
        elements = page.locator(
            'a[href*="/@"], [data-e2e*="profile"], [class*="avatar"], '
            'button[aria-label*="account" i], [class*="username"]'
        )
        count = min(int(elements.count()), 40)
    except Exception:
        count = 0
    handles: list[str] = []
    for index in range(count):
        try:
            element = elements.nth(index)
            for attribute in ("href", "aria-label", "title"):
                value = element.get_attribute(attribute) or ""
                if "@" in value:
                    handle = value.split("@")[-1].split("/")[0].split("?")[0].strip().lower()
                    if handle:
                        handles.append(handle)
                        if wanted and handle == wanted:
                            return handle
            text = (element.inner_text(timeout=2) or "").strip().lstrip("@").lower()
            if text and " " not in text and len(text) <= 40:
                handles.append(text)
                if wanted and text == wanted:
                    return text
        except Exception:
            continue
    if wanted and wanted in handles:
        return wanted
    return handles[0] if handles else ""


def is_expected_account(page: Any, expected: str = "") -> bool:
    """Return whether the signed-in account matches the expected handle."""
    wanted = expected.strip().lstrip("@").lower()
    if not wanted:
        return is_logged_in(page)
    found = logged_in_account(page, wanted)
    if found and found == wanted:
        return True
    lowered = page_text(page)
    return bool(lowered) and wanted in lowered.lower()


def detect_robot_check(page: Any) -> str | None:
    """Detect a CAPTCHA, robot verification, login wall, or error page.

    The check covers the bot challenge markers, a login button that means the
    session was lost, the Google sign-in refusal, and a generic error page.
    It never solves or bypasses the challenge.
    """
    text = page_text(page)
    if not text:
        return None
    lowered = text.lower()
    for marker in ROBOT_MARKERS:
        if marker in lowered:
            return marker
    if any(marker in lowered for marker in LOGIN_WALL_MARKERS):
        return "login required"
    for marker in ERROR_PAGE_MARKERS:
        if marker in lowered:
            return marker
    try:
        url = str(page.url).lower()
    except Exception:
        url = ""
    if any(part in url for part in ("/login", "/captcha", "/verify", "account-access")):
        return "login page"
    return None


def find_real_chrome() -> Path | None:
    """Locate the installed Google Chrome executable on this machine."""
    for candidate in CHROME_EXECUTABLE_CANDIDATES:
        if candidate.exists():
            return candidate
    local = Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "Application" / "chrome.exe"
    return local if local.exists() else None


def launch_real_chrome_context(playwright: Any, profile_dir: Path, config: dict[str, Any]) -> Any:
    """Launch a persistent context in the real installed Chrome, never bundled Chromium.

    Google refuses sign-in in Playwright's bundled Chromium with the
    "this browser or app may not be secure" error, so the installed Chrome
    binary is used explicitly.
    """
    options: dict[str, Any] = {
        "headless": False,
        "args": ["--disable-blink-features=AutomationControlled", "--start-maximized"],
    }
    channel = str(config.get("chrome_channel", DEFAULT_CHROME_CHANNEL))
    if channel:
        options["channel"] = channel

    executable = config.get("chrome_executable_path")
    if executable:
        options["executable_path"] = str(executable)
    else:
        found = find_real_chrome()
        if found is not None:
            options["executable_path"] = str(found)

    try:
        return playwright.chromium.launch_persistent_context(str(profile_dir), **options)
    except Exception as exc:
        if "executable_path" not in options:
            raise
        options.pop("executable_path")
        try:
            return playwright.chromium.launch_persistent_context(str(profile_dir), **options)
        except Exception:
            raise exc


def _write_port_file(port_file: Path, port: int) -> None:
    """Record the debug port of the running Chrome."""
    try:
        port_file.write_text(str(port), encoding="utf-8")
    except OSError:
        pass


def cdp_endpoint_alive(port: int, timeout: float = 2.0) -> bool:
    """Return whether a remote debugging endpoint still answers on a port.

    A port that was recorded earlier can be stale because Chrome exited or
    because the recorded value no longer belongs to a live instance. The
    endpoint is probed directly so a stale port is never handed to Playwright.
    """
    if port <= 0:
        return False
    import urllib.error
    import urllib.request

    endpoint = f"http://127.0.0.1:{port}/json/version"
    try:
        with urllib.request.urlopen(endpoint, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, OSError, ValueError):
        return False
    return "webSocketDebuggerUrl" in body


def chrome_pid_for_port(port: int) -> int | None:
    """Return the browser process id listening on a remote debugging port."""
    try:
        import subprocess

        command = (
            f"Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
            f"Where-Object {{ $_.CommandLine -like '*remote-debugging-port={port}*' }} | "
            f"ForEach-Object {{ $_.ProcessId }}"
        )
        output = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout
    except Exception:
        return None
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.isdigit():
            return int(stripped)
    return None


def profile_is_locked(profile_dir: Path) -> bool:
    """Return whether another Chrome process holds the profile lock.

    Chrome writes a ``SingletonLock`` file into the profile directory while it
    is running. A lock owned by a live process means a new Chrome cannot open
    the same profile, so the existing session has to be reused instead.
    """
    lock = profile_dir / "SingletonLock"
    if not lock.exists():
        return False
    try:
        target = lock.read_text(encoding="utf-8", errors="replace").strip().lstrip("-")
    except OSError:
        return False
    if not target:
        return True
    hostname, _, pid_text = target.partition("-")
    if not pid_text.isdigit():
        return True
    pid = int(pid_text)
    if pid == os.getpid():
        return False
    try:
        import subprocess

        output = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"(Get-Process -Id {pid} -ErrorAction SilentlyContinue) -ne $null",
            ],
            capture_output=True,
            text=True,
            timeout=20,
        ).stdout.strip().lower()
    except Exception:
        return False
    return output == "true"


def chrome_processes_for_profile(profile_dir: Path) -> list[tuple[int, int]]:
    """Return the ``(pid, debug_port)`` pairs of Chrome using this profile."""
    pairs: list[tuple[int, int]] = []
    try:
        import subprocess

        command = (
            "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
            "ForEach-Object { \"$($_.ProcessId)|$($_.CommandLine)\" }"
        )
        output = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout
    except Exception:
        return pairs
    profile_marker = str(profile_dir.resolve()).lower()
    for line in output.splitlines():
        if "|" not in line:
            continue
        pid_text, _, command_line = line.partition("|")
        pid_text = pid_text.strip()
        lowered = command_line.lower()
        if not pid_text.isdigit() or profile_marker not in lowered:
            continue
        port = 0
        marker = "--remote-debugging-port="
        start = lowered.find(marker)
        if start >= 0:
            digits = ""
            for character in lowered[start + len(marker):]:
                if character.isdigit():
                    digits += character
                else:
                    break
            if digits:
                port = int(digits)
        pairs.append((int(pid_text), port))
    return pairs


def _known_debug_ports(profile_dir: Path, port_file: Path) -> list[int]:
    """Return the debug ports a Chrome for this profile may be listening on.

    The recorded port is checked first. Then the running Chrome processes are
    inspected so a Chrome that was started by an earlier run is reused instead
    of opening a second window for the same profile.
    """
    ports: list[int] = []
    if port_file.exists():
        try:
            ports.append(int(port_file.read_text(encoding="utf-8").strip()))
        except (OSError, ValueError):
            pass
    try:
        import subprocess

        command = (
            "Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
            "Select-Object -ExpandProperty CommandLine"
        )
        output = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout
    except Exception:
        return ports

    profile_marker = str(profile_dir.resolve()).lower()
    for line in output.splitlines():
        lowered = line.lower()
        if "remote-debugging-port=" not in lowered or profile_marker not in lowered:
            continue
        marker = "--remote-debugging-port="
        start = lowered.find(marker) + len(marker)
        digits = ""
        for character in lowered[start:]:
            if character.isdigit():
                digits += character
            else:
                break
        if digits:
            port = int(digits)
            if port not in ports:
                ports.append(port)
    return ports


def _close_stale_chrome_instances(profile_dir: Path, keep_port: int | None = None) -> None:
    """Close Chrome instances for this profile that are not the one to reuse.

    Only one browser may drive the profile. Every instance other than the
    keeper is closed so a duplicate window never appears for the user.
    """
    port_file = profile_dir.parent / f"{profile_dir.name}-debug-port.txt"
    ports = _known_debug_ports(profile_dir, port_file)
    if len(ports) < 2:
        return
    keeper = keep_port if keep_port is not None else (ports[-1] if ports else None)
    stale = [port for port in ports if port != keeper]
    if not stale:
        return
    try:
        import subprocess

        for port in stale:
            subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f"Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
                    f"Where-Object {{ $_.CommandLine -like '*remote-debugging-port={port}*' }} | "
                    f"ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }}",
                ],
                capture_output=True,
                timeout=60,
            )
    except Exception:
        return


def launch_detached_chrome(
    playwright: Any,
    profile_dir: Path,
    config: dict[str, Any],
    *,
    session: "SessionState | None" = None,
    task_id: str = "",
) -> Any:
    """Attach to a Chrome that is independent of the Python process.

    A browser started by Playwright is killed when the driver shuts down, which
    happens when the script exits. That closes the window while the user is
    still solving a robot verification. Here Chrome is started by the operating
    system with a remote debugging port and Playwright attaches over CDP, so
    the window survives the Python process and the user keeps control of it.

    The recovery path distinguishes the failure modes: a Chrome that is still
    running but whose debug port no longer answers, a recorded port that went
    stale, an endpoint that returns an invalid answer, a Chrome running with a
    different profile, and a profile that another Chrome process has locked.
    The existing session is reused whenever it is still usable, so no second
    window is opened for the same profile.

    The real installed Chrome is used with the persistent profile and
    ``headless=False``.
    """
    import socket
    import subprocess

    executable = config.get("chrome_executable_path") or find_real_chrome()
    if executable is None:
        if session is not None:
            session.transition(
                STATE_CHROME_NOT_FOUND,
                "STOP",
                "the installed Google Chrome executable could not be found",
            )
        raise PosterError("The installed Google Chrome executable could not be found")

    profile_dir.mkdir(parents=True, exist_ok=True)
    port_file = profile_dir.parent / f"{profile_dir.name}-debug-port.txt"
    if session is not None:
        session.bind_session(profile_dir=profile_dir)

    # 1. Look for a Chrome that is already running for this profile.
    live_ports: list[int] = []
    for candidate_port in reversed(_known_debug_ports(profile_dir, port_file)):
        if not cdp_endpoint_alive(candidate_port):
            # The recorded port is stale: Chrome exited or the port changed.
            if session is not None:
                session.transition(
                    STATE_RECOVERING,
                    "DISCARD stale port",
                    f"the debug port {candidate_port} no longer answers so it is not reused",
                )
            continue
        live_ports.append(candidate_port)

    # 2. Reuse the live session instead of opening a second window.
    for candidate_port in live_ports:
        if session is not None:
            session.transition(
                STATE_CDP_CONNECTING,
                "REUSE existing session",
                f"a live Chrome already serves this profile on port {candidate_port}",
            )
        try:
            browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{candidate_port}")
            contexts = browser.contexts
            if contexts:
                context = contexts[0]
                pages = context.pages
                # P16: reuse the open TikTok Studio tab when there is one so a
                # run never drives an unrelated tab and never reopens Studio.
                # The tool keeps one TikTok tab, so an open TikTok tab is
                # reused before a new one is opened.
                page = (
                    select_tiktok_page(pages)
                    or (pages[0] if pages else context.new_page())
                )
                _write_port_file(port_file, candidate_port)
                if session is not None:
                    session.bind_session(
                        browser_pid=chrome_pid_for_port(candidate_port),
                        cdp_port=candidate_port,
                    )
                    session.transition(
                        STATE_CDP_CONNECTED,
                        "REUSE existing session",
                        "the existing Chrome window was reused so no second window was opened",
                        url=current_page_url(page),
                    )
                return browser, context, page
        except Exception as exc:
            if session is not None:
                session.transition(
                    STATE_RECOVERING,
                    "RETRY",
                    f"the endpoint on port {candidate_port} refused the connection: "
                    f"{type(exc).__name__}: {exc}",
                )
            continue

    # 3. No usable session: check whether the profile is locked by another
    #    Chrome that does not expose a usable debug port.
    if profile_is_locked(profile_dir):
        if session is not None:
            session.transition(
                STATE_RECOVERING,
                "WAIT for the locked session",
                "another Chrome process holds the profile lock so a new window cannot open",
            )
        raise PosterError(
            "The Chrome profile is locked by another Chrome process that does not expose "
            "a usable remote debugging port. Close that window or restore its debug port."
        )

    # 4. Chrome is genuinely not running: start it again with the same profile.
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    if session is not None:
        session.transition(
            STATE_CHROME_STARTING,
            "START Chrome",
            "no live Chrome was found for this profile so the same profile is reused",
        )

    arguments = [
        str(executable),
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_dir.resolve()}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-blink-features=AutomationControlled",
        "--start-maximized",
        TIKTOK_STUDIO_HOME_URL,
    ]
    creation_flags = 0
    if os.name == "nt":
        creation_flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
    process = subprocess.Popen(
        arguments,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        creationflags=creation_flags,
    )
    if session is not None:
        session.bind_session(browser_pid=process.pid, cdp_port=port)

    endpoint = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if session is not None:
            session.transition(
                STATE_CDP_CONNECTING,
                "WAIT for the debug port",
                f"Chrome was started and the endpoint {endpoint} is not ready yet",
            )
        if cdp_endpoint_alive(port):
            try:
                browser = playwright.chromium.connect_over_cdp(endpoint)
                contexts = browser.contexts
                if contexts:
                    context = contexts[0]
                    pages = context.pages
                    # P16: reuse the open TikTok Studio tab when there is one.
                    # The tool keeps one TikTok tab, so an open TikTok tab is
                    # reused before a new one is opened.
                    page = (
                        select_tiktok_page(pages)
                        or (pages[0] if pages else context.new_page())
                    )
                    _write_port_file(port_file, port)
                    if session is not None:
                        session.transition(
                            STATE_CDP_CONNECTED,
                            "ATTACH",
                            "the restarted Chrome exposed its debug port and was attached",
                            url=current_page_url(page),
                        )
                    return browser, context, page
            except Exception as exc:
                if session is not None:
                    session.transition(
                        STATE_RECOVERING,
                        "RETRY",
                        f"the endpoint answered but the attachment failed: "
                        f"{type(exc).__name__}: {exc}",
                    )
        if process.poll() is not None:
            if session is not None:
                session.transition(
                    STATE_CHROME_NOT_FOUND,
                    "STOP",
                    "Chrome exited immediately after it was started",
                )
            raise PosterError("Chrome exited immediately after it was started")
        time.sleep(0.5)
    if session is not None:
        session.transition(
            STATE_FAILED_RETRYABLE,
            "STOP",
            f"Chrome did not expose a usable debug port on {endpoint} in time",
        )
    raise PosterError("Chrome did not expose a debugging port in time")


def open_page_in_detached_chrome(playwright: Any, profile_dir: Path, config: dict[str, Any]) -> Any:
    """Return the page of a detached Chrome, reusing an already running one."""
    return launch_detached_chrome(playwright, profile_dir, config)[2]


def get_page_and_context(playwright: Any, profile_dir: Path, config: dict[str, Any]) -> tuple[Any, Any]:
    """Return the page and context to drive, preferring a detached browser."""
    browser, context, page = launch_detached_chrome(playwright, profile_dir, config)
    return page, context


def login_tiktok_studio(
    config: dict[str, Any],
    *,
    timeout_seconds: int = DEFAULT_LOGIN_TIMEOUT_SECONDS,
    poll_seconds: float = 5.0,
    sleep: Callable[[float], None] = time.sleep,
    wait_for_user: Callable[[], None] | None = None,
    log: Callable[[str], None] = print,
) -> PosterResult:
    """Open TikTok Studio in a persistent profile and wait for a manual sign-in.

    The user signs in through Google in the visible browser window. No credential,
    password, or one-time code is ever entered by this function. When the
    profile is already signed in as the expected account the login step is
    skipped entirely, so no second browser and no extra tab is opened. If a
    CAPTCHA, robot verification, re-login, or security check appears, the
    automation stops and waits for the user to solve it in the same open
    browser. The browser is never closed by this function.
    """
    allowed_sites = config.get("allowed_sites", [])
    validate_allowed_site(TIKTOK_STUDIO_HOME_URL, allowed_sites)

    profile_dir = Path(config.get("chrome_profile_path", "data/chrome-profile"))
    profile_dir.mkdir(parents=True, exist_ok=True)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise PosterError("playwright is required for the TikTok Studio login helper") from exc

    playwright = None
    context = None
    browser = None
    try:
        playwright = sync_playwright().start()
        login_session = SessionState(
            "tiktok-studio-login",
            profile_dir=profile_dir,
            log=log,
            state_path=Path("data") / "tasks" / "tiktok-studio-login-session.json",
        )
        browser, context, page = launch_detached_chrome(
            playwright,
            profile_dir,
            config,
            session=login_session,
            task_id="tiktok-studio-login",
        )
        page.goto(TIKTOK_STUDIO_HOME_URL, wait_until="domcontentloaded")

        expected_account = str(config.get("expected_account", "")).strip()
        agent = SmartAgent(
            page,
            config=config,
            log=log,
            wait_for_user=wait_for_user,
            session=login_session,
            reconnect=lambda: launch_detached_chrome(
                playwright,
                profile_dir,
                config,
                session=login_session,
                task_id="tiktok-studio-login",
            )[2],
        )
        agent.account = expected_account.strip().lstrip("@")

        deadline = time.monotonic() + max(0, timeout_seconds)
        while time.monotonic() < deadline:
            blocked = detect_robot_check(page)
            if blocked:
                agent.decide(
                    f"robot check ({blocked})",
                    "PAUSE for user",
                    "a robot verification or login wall is showing",
                )
                if agent.pause_for_user(blocked):
                    # The user solved it: re-check the login in the same session.
                    if is_logged_in(page):
                        agent.decide(
                            "signed in after the user solved the check",
                            "CONTINUE",
                            "the same browser session is now authenticated",
                        )
                        login_session.transition(
                            STATE_SIGNED_IN,
                            "CONTINUE",
                            "the same browser session is signed in after the user solved the check",
                        )
                        state = save_task_state(
                            "tiktok-studio-login",
                            "LOGGED_IN",
                            "",
                            "",
                            "Signed in to TikTok Studio in the persistent profile.",
                            Path("data") / "tasks" / "tiktok-studio-login.json",
                            {"browser_left_open": True},
                        )
                        return PosterResult(
                            task_id="tiktok-studio-login",
                            status="LOGGED_IN",
                            message="TikTok Studio session saved in the persistent profile.",
                            state=state,
                        )
                    continue
                state = save_task_state(
                    "tiktok-studio-login",
                    "BLOCKED",
                    "",
                    "",
                    f"Stopped for user action: {blocked}",
                    Path("data") / "tasks" / "tiktok-studio-login.json",
                    {"browser_left_open": True},
                )
                return PosterResult(
                    task_id="tiktok-studio-login",
                    status="BLOCKED",
                    message=f"Stopped for user action: {blocked}",
                    state=state,
                )
            if expected_account:
                if is_expected_account(page, expected_account):
                    agent.decide(
                        f"account {expected_account} is already signed in",
                        "SKIP login",
                        "the persistent profile is already authenticated so no tab is opened",
                    )
                    state = save_task_state(
                        "tiktok-studio-login",
                        "LOGGED_IN",
                        "",
                        "",
                        "Signed in to TikTok Studio in the persistent profile.",
                        Path("data") / "tasks" / "tiktok-studio-login.json",
                        {"browser_left_open": True, "account": expected_account},
                    )
                    return PosterResult(
                        task_id="tiktok-studio-login",
                        status="LOGGED_IN",
                        message="TikTok Studio session saved in the persistent profile.",
                        state=state,
                    )
            elif is_logged_in(page):
                agent.decide(
                    "a session is already active",
                    "SKIP login",
                    "the persistent profile is already authenticated so no tab is opened",
                )
                state = save_task_state(
                    "tiktok-studio-login",
                    "LOGGED_IN",
                    "",
                    "",
                    "Signed in to TikTok Studio in the persistent profile.",
                    Path("data") / "tasks" / "tiktok-studio-login.json",
                    {"browser_left_open": True},
                )
                return PosterResult(
                    task_id="tiktok-studio-login",
                    status="LOGGED_IN",
                    message="TikTok Studio session saved in the persistent profile.",
                    state=state,
                )
            sleep(poll_seconds)

        state = save_task_state(
            "tiktok-studio-login",
            "BLOCKED",
            "",
            "",
            "Sign-in was not completed within the allowed time.",
            Path("data") / "tasks" / "tiktok-studio-login.json",
            {"browser_left_open": True},
        )
        return PosterResult(
            task_id="tiktok-studio-login",
            status="BLOCKED",
            message="Sign-in was not completed within the allowed time.",
            state=state,
        )
    except Exception as exc:
        # Log the full error, keep the browser open, and stop. The browser is
        # never closed here so the user can inspect or resolve it manually.
        log(f"ERROR: {type(exc).__name__}: {exc}")
        state = save_task_state(
            "tiktok-studio-login",
            "FAILED",
            "",
            "",
            f"{type(exc).__name__}: {exc}",
            Path("data") / "tasks" / "tiktok-studio-login.json",
            {"browser_left_open": True},
        )
        return PosterResult(
            task_id="tiktok-studio-login",
            status="FAILED",
            message=f"{type(exc).__name__}: {exc}",
            state=state,
        )


def upload_progress_percent(page: Any) -> int | None:
    """Return the visible upload progress percentage, or None when not shown."""
    try:
        text = str(page.locator("body").inner_text(timeout=5000))
    except Exception:
        return None
    if not text:
        return None
    matches = UPLOAD_PERCENT_PATTERN.findall(text)
    if not matches:
        return None
    return max(int(value) for value in matches)


def wait_for_upload_complete(
    page: Any,
    *,
    timeout_ms: int = UPLOAD_PROGRESS_TIMEOUT_MS,
    interval_ms: int = UPLOAD_PROGRESS_INTERVAL_MS,
    log: Callable[[str], None] = print,
) -> bool:
    """Wait until the upload reaches 100 percent, logging progress periodically.

    The caption and description controls only appear once the upload finishes,
    so the upload is awaited before any text is entered.
    """
    deadline = time.monotonic() + max(0, timeout_ms) / 1000
    last_reported = -1
    while time.monotonic() < deadline:
        blocked = detect_block(page)
        if blocked:
            raise BlockedError(f"Stopped for user action: {blocked}")
        percent = upload_progress_percent(page)
        if percent is not None and percent != last_reported:
            last_reported = percent
            log(f"upload progress: {percent}%")
        if percent is not None and percent >= 100:
            log("upload progress: 100%")
            return True
        if percent is None and description_field_count(page) > 0:
            log("upload progress: description field available")
            return True
        page.wait_for_timeout(interval_ms)
    log(f"upload progress: timed out after {timeout_ms} ms")
    return False


def description_field_count(page: Any) -> int:
    """Count visible description or caption inputs on the page."""
    total = 0
    for selector in (
        'textarea[placeholder*="caption" i]',
        'textarea[placeholder*="describe" i]',
        'div[contenteditable="true"]',
    ):
        try:
            total += page.locator(selector).count()
        except Exception:
            continue
    return total


def fill_description(page: Any, caption: str, hashtags: list[str] | None = None) -> str:
    """Clear the default filename text and type the caption plus hashtags.

    Returns the text that was written so it can be verified by the caller.
    """
    text = caption.strip()
    if hashtags:
        tags = " ".join(f"#{tag.lstrip('#')}" for tag in hashtags if str(tag).strip())
        if tags:
            text = f"{text} {tags}".strip()
    text = text[:150]

    field = page.locator(DESCRIPTION_FIELD_SELECTOR).first
    field.wait_for(state="visible", timeout=CAPTION_FIELD_TIMEOUT_MS)
    try:
        field.click()
    except Exception:
        pass
    # The editor is a contenteditable, so fill() does not reliably clear it
    # and the caret can sit in the middle of the old text. Select all and
    # delete first so the new caption replaces the old one instead of being
    # inserted into it.
    try:
        field.fill("")
    except Exception:
        pass
    try:
        page.keyboard.press("Control+A")
        page.keyboard.press("Delete")
    except Exception:
        pass
    try:
        field.type(text, delay=20)
    except Exception:
        # Fall back to a direct keyboard write when the element type helper
        # refuses the contentEditable node.
        page.keyboard.type(text, delay=20)

    try:
        current = field.inner_text(timeout=5000)
    except Exception:
        current = ""
    if text not in current:
        raise PosterError("The description text was not present after typing")
    return text


def wait_for_save_draft_enabled(
    page: Any,
    *,
    timeout_ms: int = SAVE_DRAFT_ENABLE_TIMEOUT_MS,
    interval_ms: int = 10000,
    log: Callable[[str], None] = print,
) -> bool:
    """Wait until the Save draft control is enabled.

    TikTok Studio disables the Save draft button while the uploaded video is
    still being processed, so the click must wait for the control to become
    actionable rather than failing on a disabled element.
    """
    deadline = time.monotonic() + max(0, timeout_ms) / 1000
    while time.monotonic() < deadline:
        blocked = detect_block(page)
        if blocked:
            raise BlockedError(f"Stopped for user action: {blocked}")
        save_draft = page.get_by_role("button", name=re.compile("save draft", re.I)).first
        try:
            if save_draft.count() > 0 and save_draft.is_enabled():
                log("save draft control is enabled")
                return True
        except Exception:
            pass
        page.wait_for_timeout(interval_ms)
    log(f"save draft control did not become enabled within {timeout_ms} ms")
    return False


def current_draft_reference(page: Any) -> str:
    """Return the current page URL as the draft reference."""
    try:
        url = str(page.url)
    except Exception:
        url = ""
    return url


# The shape of the address of a published post. The number after
# ``/video/`` is the id the platform gave the post.
PUBLISHED_URL_PATTERN = re.compile(r"https://[^\s/]+/(@[^\s/]+/)?video/(\d+)", re.I)


def published_post_reference(page: Any) -> str:
    """Return the address of the post that was really published.

    The page is read for the address of a post that the platform
    confirms. The link of the post that was published is looked for in
    the page itself, and the address of the page is used when it already
    carries the number of a post.

    The empty string is returned when nothing confirms that the post
    went through. The caller must then treat the publish as unknown and
    must not write PUBLISHED.
    """
    # The address of the page, when it already is the address of a post.
    try:
        current = str(page.url)
    except Exception:
        current = ""
    match = PUBLISHED_URL_PATTERN.search(current)
    if match:
        return match.group(0)

    # The links of the page. Only the ones that carry the number of a
    # post are real posts, and not the address of the studio itself.
    try:
        links = page.get_by_role("link")
        count = int(links.count())
    except Exception:
        count = 0
    for index in range(min(count, 60)):
        try:
            href = str(links.nth(index).get_attribute("href") or "")
        except Exception:
            continue
        match = PUBLISHED_URL_PATTERN.search(href)
        if match:
            return match.group(0)

    # The text of the page, which sometimes carries the address of the
    # post that was just published.
    try:
        text = page_text(page)
    except Exception:
        text = ""
    match = PUBLISHED_URL_PATTERN.search(text or "")
    if match:
        return match.group(0)
    return ""


def wait_for_published_reference(
    page: Any,
    *,
    timeout_ms: int = 20000,
    poll_ms: int = 1000,
    sleep: Any = None,
) -> str:
    """Wait for the page to show the post that was published.

    The address of the published post is looked for until it shows up or
    the time runs out. The empty string is returned when nothing
    confirms the publish, so the caller never writes PUBLISHED on a
    guess.
    """
    import time as _time

    pause = sleep if sleep is not None else _time.sleep
    waited = 0
    while waited <= timeout_ms:
        reference = published_post_reference(page)
        if reference:
            return reference
        pause(poll_ms / 1000.0)
        waited += poll_ms
    return ""


def capture_error_screenshot(page: Any, path: Path) -> str | None:
    """Capture an error screenshot for AI review."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(path), full_page=True)
        return str(path)
    except Exception:
        return None

def delete_screenshot(path: str | Path | None) -> None:
    """Delete an error screenshot after it has been read."""
    if not path:
        return
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass


class SmartAgent:
    """One browser, one context, one page, with a decision before each action.

    The agent reads the page state, decides what to do, and records the state,
    the decision, and the reason in the log. A robot check pauses the agent
    and waits for the user in the terminal; every other state continues
    automatically without asking the user. The browser is never closed.
    """

    def __init__(
        self,
        page: Any,
        *,
        config: dict[str, Any] | None = None,
        log: Callable[[str], None] = print,
        wait_for_user: Callable[[], None] | None = None,
        session: "SessionState | None" = None,
        reconnect: Callable[[], Any] | None = None,
    ) -> None:
        self.page = page
        self.config = config or {}
        self.log = log
        self.wait_for_user = wait_for_user
        self.session = session
        self.reconnect = reconnect
        self.account = ""

    def decide(self, state: str, decision: str, reason: str) -> None:
        """Record the observed state, the decision, and the reason."""
        self.log(f"state: {state} -> decision: {decision} | reason: {reason}")

    def transition(self, state: str, decision: str, reason: str) -> None:
        """Record a session state transition when a session recorder is present."""
        if self.session is None:
            return
        self.session.transition(state, decision, reason, url=current_page_url(self.page))

    def read_state(self) -> dict[str, Any]:
        """Read the current page state without acting on it."""
        robot = detect_robot_check(self.page)
        logged_in = is_logged_in(self.page)
        account = logged_in_account(self.page, self.account) if logged_in else ""
        return {
            "robot_check": robot,
            "logged_in": logged_in,
            "account": account,
            "url": current_page_url(self.page),
        }

    def ensure_session(self, expected_account: str = "") -> bool:
        """Make sure the single page is signed in, skipping login when possible.

        The account is checked first. When the TikTok Studio home already
        shows the expected account the login step is skipped entirely, so no
        second browser and no extra tab is ever opened.
        """
        if expected_account:
            self.account = expected_account.strip().lstrip("@")
        self.transition(
            STATE_SESSION_CHECKING,
            "CHECK session",
            "the signed-in account is read from the live page before any login step",
        )
        state = self.read_state()
        if state["robot_check"]:
            self.decide(
                f"robot check ({state['robot_check']})",
                "PAUSE for user",
                "a robot verification or login wall is showing",
            )
            self.transition(
                STATE_ROBOT_CHECK,
                "PAUSE for user",
                f"a robot verification is showing: {state['robot_check']}",
            )
            if not self.pause_for_user(state["robot_check"]):
                self.transition(
                    STATE_BLOCKED,
                    "STOP",
                    "the challenge is still showing after the user acted",
                )
                return False
            state = self.read_state()
            if state["robot_check"]:
                self.decide(
                    f"robot check ({state['robot_check']})",
                    "STOP",
                    "the challenge is still showing after the user acted",
                )
                self.transition(
                    STATE_BLOCKED,
                    "STOP",
                    "the challenge is still showing after the user acted",
                )
                return False
        if self.account and is_expected_account(self.page, self.account):
            self.decide(
                f"account {self.account} already signed in",
                "SKIP login",
                "the persistent profile is already authenticated",
            )
            self.transition(
                STATE_SIGNED_IN,
                "SKIP login",
                f"the persistent profile is signed in as {self.account}",
            )
            return True
        if state["logged_in"]:
            self.decide(
                "signed in but account not confirmed",
                "CONTINUE",
                "a session is active so the login step is skipped",
            )
            self.transition(
                STATE_SIGNED_IN,
                "CONTINUE",
                "a session is active so the login step is skipped",
            )
            return True
        self.decide(
            "not signed in",
            "CONTINUE",
            "the flow needs a signed-in session before it can draft",
        )
        self.transition(
            STATE_LOGIN_REQUIRED,
            "CONTINUE",
            "the page is not signed in so the login flow is required",
        )
        return True

    def pause_for_user(self, marker: str) -> bool:
        """Stop and wait for the user to solve a robot verification.

        The message is printed and the terminal is read with no timeout. The
        browser stays open on the same page and the same profile, and the
        state is re-checked afterwards. When the CDP connection was lost
        while the user was working, the existing Chrome is reattached instead
        of opening a second window.
        """
        print(ROBOT_CHECK_MESSAGE, flush=True)
        self.log(f"{ROBOT_CHECK_MESSAGE} (marker: {marker})")
        self.transition(
            STATE_WAITING_FOR_USER,
            "WAIT",
            "the user solves the robot verification in the same Chrome window",
        )
        if self.wait_for_user is None:
            self.log("No terminal wait is available, so the flow stops here.")
            self.transition(
                STATE_BLOCKED,
                "STOP",
                "no terminal wait is available so the flow cannot continue",
            )
            return False
        try:
            self.wait_for_user()
        except EOFError:
            self.log("BROWSER CLOSE REASON: timeout - terminal input ended")
            self.transition(
                STATE_BLOCKED,
                "STOP",
                "the terminal input ended before the challenge was resolved",
            )
            return False
        except Exception as exc:
            self.log(
                f"BROWSER CLOSE REASON: exception with full error - {type(exc).__name__}: {exc}"
            )
            self.transition(
                STATE_BLOCKED,
                "STOP",
                f"the terminal wait failed: {type(exc).__name__}: {exc}",
            )
            return False

        # The user pressed Enter. The connection may have dropped while the
        # Chrome window stayed open, so the page is checked and reattached
        # before the flow continues.
        if not page_is_alive(self.page):
            self.transition(
                STATE_RECOVERING,
                "REATTACH",
                "the CDP connection dropped while the user was verifying so the "
                "existing Chrome is reattached",
            )
            recovered = self._recover_page()
            if not recovered:
                self.transition(
                    STATE_BLOCKED,
                    "STOP",
                    "the Chrome session could not be reattached after the user verified",
                )
                return False
            self.transition(
                STATE_RESUMING_TASK,
                "CONTINUE",
                "the existing Chrome session was reattached and the flow continues on it",
            )
        else:
            self.transition(
                STATE_RESUMING_TASK,
                "CONTINUE",
                "the same Chrome page is still alive so the flow continues on it",
            )
        return True

    def _recover_page(self) -> bool:
        """Reattach to the running Chrome after the CDP connection dropped."""
        if self.reconnect is None:
            return False
        try:
            page = self.reconnect()
        except Exception as exc:
            self.log(
                f"RECONNECT FAILED: {type(exc).__name__}: {exc}"
            )
            return False
        if page is None:
            return False
        self.page = page
        return page_is_alive(page)


def post_to_tiktok_studio(
    task_id: str,
    caption: str,
    video_path: str | Path,
    config: dict[str, Any],
    *,
    approved: bool = False,
    page: Any = None,
    state_path: Path | None = None,
    screenshot_path: Path | None = None,
    screenshot_reader: Callable[[str], None] | None = None,
    delay: Callable[[float], None] = time.sleep,
    random_source: Callable[[float, float], float] = random.uniform,
    hashtags: list[str] | None = None,
    keep_browser_open: bool = True,
    log: Callable[[str], None] = print,
    wait_for_user: Callable[[], None] | None = None,
    resume: bool = True,
) -> PosterResult:
    """Save a TikTok Studio draft and publish only after approval in approve mode.

    The browser is never closed automatically. After the draft is saved the
    user is told that the browser will stay open and, when ``wait_for_user``
    is supplied, the call blocks until the user presses Enter in the terminal.
    Every browser close is logged with the reason it happened.

    When ``resume`` is set the persisted task state is inspected first. A task
    that already has a saved draft is not uploaded again and does not create a
    second draft, and a task whose upload already completed continues at the
    caption step on the existing session.
    """
    mode = str(config.get("mode", "approve")).lower()
    allowed_sites = config.get("allowed_sites", [])
    if state_path is None:
        state_path = Path("data") / "tasks" / f"{task_id}.json"
    if screenshot_path is None:
        screenshot_path = Path("data") / "screenshots" / f"{task_id}.png"
    validate_publish_input(caption, video_path, mode, approved)
    validate_allowed_site(TIKTOK_STUDIO_URL, allowed_sites)

    browser = None
    context = None
    owned_page = False
    captcha_pending = False

    session = SessionState(
        task_id,
        profile_dir=config.get("chrome_profile_path", "data/chrome-profile"),
        log=log,
        state_path=state_path,
    )

    # P15 resume: an interrupted run continues at the stage it reached. A task
    # that already saved its draft is never uploaded again and never creates a
    # duplicate draft.
    resumed_from = ""
    if resume:
        previous = load_task_state(state_path)
        previous_status = str(previous.get("status", ""))
        previous_draft = str(previous.get("draft_reference", ""))
        if previous_status == "PUBLISHED":
            # The post already went out. The run never publishes a second
            # time, so a retry or a resume cannot double post.
            posted = str(previous.get("posted_url", "") or "").strip()
            session.transition(
                STATE_RESUMING_TASK,
                "SKIP publish",
                "the task was already published so the post is not repeated",
            )
            log(
                f"RESUME: task {task_id} was already published "
                f"({posted or 'the address was not recorded'}); the post is not repeated."
            )
            state = save_task_state(
                task_id,
                "PUBLISHED",
                str(previous.get("caption", caption)) or caption,
                str(previous.get("video_path", video_path)) or str(video_path),
                "Resumed an already published task; the post was not repeated.",
                state_path,
                {"mode": mode, "posted_url": posted},
            )
            return PosterResult(
                task_id=task_id,
                status="PUBLISHED",
                caption=str(previous.get("caption", caption)) or caption,
                video_path=str(previous.get("video_path", video_path)) or str(video_path),
                message=(
                    "Resumed an already published task; the post was not repeated. "
                    f"Reference: {posted or 'the address was not recorded'}"
                ),
                state=state,
            )
        if previous_status == "DRAFT_SAVED" and previous_draft:
            session.transition(
                STATE_RESUMING_TASK,
                "SKIP upload",
                f"the task already saved a draft at {previous_draft} so it is not uploaded again",
            )
            log(
                f"RESUME: task {task_id} already saved a draft "
                f"({previous_draft}); no upload and no duplicate draft is created."
            )
            state = save_task_state(
                task_id,
                "DRAFT_SAVED",
                str(previous.get("caption", caption)) or caption,
                str(previous.get("video_path", video_path)) or str(video_path),
                "Resumed an already saved draft; no upload was repeated.",
                state_path,
                {
                    "mode": mode,
                    "draft_reference": previous_draft,
                    "browser_left_open": True,
                    "resumed": True,
                },
            )
            return PosterResult(
                task_id=task_id,
                status="DRAFT_SAVED",
                caption=str(previous.get("caption", caption)) or caption,
                video_path=str(previous.get("video_path", video_path)) or str(video_path),
                message=(
                    "Resumed an already saved draft; human approval required before publish. "
                    f"Reference: {previous_draft}"
                ),
                state=state,
            )
        if previous_status in {"UPLOADING", "UPLOADED", "UPLOAD_COMPLETE"}:
            resumed_from = "UPLOADED"
            session.transition(
                STATE_RESUMING_TASK,
                "CONTINUE",
                "the previous run already uploaded the video so the caption step continues",
            )
        elif previous_status == "BLOCKED":
            session.transition(
                STATE_RESUMING_TASK,
                "CONTINUE",
                "the previous run was blocked and is retried on the same profile",
            )

    def blocked_result(marker: str) -> PosterResult:
        """Build the BLOCKED outcome while keeping the browser open."""
        session.transition(
            STATE_BLOCKED,
            "STOP",
            f"the flow is blocked and waits for the user: {marker}",
        )
        state = save_task_state(
            task_id,
            "BLOCKED",
            caption,
            str(video_path),
            f"Stopped for user action: {marker}",
            state_path,
            {"browser_left_open": True},
        )
        return PosterResult(
            task_id=task_id,
            status="BLOCKED",
            caption=caption,
            video_path=str(video_path),
            message=f"Stopped for user action: {marker}",
            state=state,
        )

    def handle_block(marker: str) -> bool:
        """Wait for the user to solve a block; True when the flow may continue.

        The automation never solves the challenge. The same browser stays open
        on the same page and profile while the user solves it, and the block is
        re-checked afterwards. The browser is never closed here.
        """
        nonlocal captcha_pending
        captcha_pending = True
        try:
            agent.decide(
                f"robot check ({marker})",
                "PAUSE for user",
                "a robot verification is showing so the flow waits for the user",
            )
            return agent.pause_for_user(marker)
        finally:
            captcha_pending = False

    try:
        if page is None:
            from playwright.sync_api import sync_playwright

            playwright = sync_playwright().start()
            profile_dir = Path(config.get("chrome_profile_path", "data/chrome-profile"))
            profile_dir.mkdir(parents=True, exist_ok=True)
            browser, context, page = launch_detached_chrome(
                playwright,
                profile_dir,
                config,
                session=session,
                task_id=task_id,
            )
            owned_page = True
        else:
            browser = None

        def reconnect_page() -> Any:
            """Reattach to the running Chrome after the CDP connection dropped."""
            from playwright.sync_api import sync_playwright

            profile_dir = Path(config.get("chrome_profile_path", "data/chrome-profile"))
            profile_dir.mkdir(parents=True, exist_ok=True)
            reattached_browser, reattached_context, reattached_page = launch_detached_chrome(
                playwright,
                profile_dir,
                config,
                session=session,
                task_id=task_id,
            )
            return reattached_page

        agent = SmartAgent(
            page,
            config=config,
            log=log,
            wait_for_user=wait_for_user,
            session=session,
            reconnect=reconnect_page,
        )
        expected_account = str(config.get("expected_account", "")).strip()

        agent.decide(
            "browser ready",
            "CHECK session",
            "the single browser and page are ready, so the session is checked",
        )
        if not agent.ensure_session(expected_account):
            state = save_task_state(
                task_id,
                "BLOCKED",
                caption,
                str(video_path),
                "Stopped for user action: robot verification or login required",
                state_path,
                {"browser_left_open": True},
            )
            return PosterResult(
                task_id=task_id,
                status="BLOCKED",
                caption=caption,
                video_path=str(video_path),
                message="Stopped for user action: robot verification or login required",
                state=state,
            )

        delay(random_source(3.0, 8.0))
        # P16: reuse the open TikTok Studio tab and navigate only when the page
        # is not already on the upload screen, so Studio never visibly reopens
        # on a run and the user's open tab is never reloaded needlessly.
        page = ensure_studio_page(context, page)
        if not current_page_url(page).rstrip("/").endswith("/tiktokstudio/upload"):
            page.goto(TIKTOK_STUDIO_URL, wait_until="domcontentloaded")
        delay(random_source(3.0, 8.0))
        blocked = detect_block(page)
        if blocked:
            if not handle_block(blocked):
                state = save_task_state(
                    task_id,
                    "BLOCKED",
                    caption,
                    str(video_path),
                    f"Stopped for user action: {blocked}",
                    state_path,
                    {"browser_left_open": True},
                )
                return PosterResult(
                    task_id=task_id,
                    status="BLOCKED",
                    caption=caption,
                    video_path=str(video_path),
                    message=f"Stopped for user action: {blocked}",
                    state=state,
                )
            # The user solved it: continue in the same browser session.
            delay(random_source(3.0, 8.0))

        if resumed_from != "UPLOADED":
            agent.decide(
                "no robot check on the upload page",
                "UPLOAD video",
                "the file input is present and the session is usable",
            )
            save_task_state(
                task_id,
                "UPLOADING",
                caption,
                str(video_path),
                "The video upload is in progress.",
                state_path,
                {"mode": mode},
            )
            file_input = page.locator('input[type="file"]')
            file_input.set_input_files(str(video_path))
            delay(random_source(3.0, 8.0))

            if not wait_for_upload_complete(page, log=log):
                state = save_task_state(
                    task_id,
                    "FAILED",
                    caption,
                    str(video_path),
                    "The upload did not reach 100 percent within the allowed time.",
                    state_path,
                )
                return PosterResult(
                    task_id=task_id,
                    status="FAILED",
                    caption=caption,
                    video_path=str(video_path),
                    message="The upload did not reach 100 percent within the allowed time.",
                    state=state,
                )
            save_task_state(
                task_id,
                "UPLOADED",
                caption,
                str(video_path),
                "The video upload completed.",
                state_path,
                {"mode": mode},
            )
        else:
            log("RESUME: the upload already completed in a previous run; it is not repeated.")

        blocked = detect_block(page)
        if blocked:
            if not handle_block(blocked):
                return blocked_result(blocked)
            delay(random_source(3.0, 8.0))

        agent.decide(
            "upload finished and the description field is available",
            "FILL description",
            "the caption and hashtags are written into the description field",
        )
        written_text = fill_description(page, caption, hashtags)
        log(f"description filled and verified: {written_text}")
        delay(random_source(3.0, 8.0))
        blocked = detect_block(page)
        if blocked:
            if not handle_block(blocked):
                return blocked_result(blocked)
            delay(random_source(3.0, 8.0))

        post_button = page.get_by_role("button", name=re.compile("post|publish", re.I)).first
        if mode == "approve":
            save_draft = page.get_by_role("button", name=re.compile("save draft", re.I)).first
            if save_draft.count() > 0:
                if not wait_for_save_draft_enabled(page, log=log):
                    state = save_task_state(
                        task_id,
                        "FAILED",
                        caption,
                        str(video_path),
                        "The Save draft control did not become enabled in time.",
                        state_path,
                        {"browser_left_open": bool(context is not None)},
                    )
                    return PosterResult(
                        task_id=task_id,
                        status="FAILED",
                        caption=caption,
                        video_path=str(video_path),
                        message="The Save draft control did not become enabled in time.",
                        state=state,
                    )
                agent.decide(
                    "save draft control is enabled",
                    "SAVE DRAFT",
                    "approve mode saves a draft and never clicks the publish control",
                )
                save_draft.click()
            else:
                # Never fall back to the publish control in approve mode; fail closed.
                agent.decide(
                    "no save draft control is available",
                    "STOP",
                    "approve mode must not fall back to publishing",
                )
                state = save_task_state(
                    task_id,
                    "BLOCKED",
                    caption,
                    str(video_path),
                    "No Save draft control was available; publishing is not allowed in approve mode.",
                    state_path,
                    {"browser_left_open": True},
                )
                return PosterResult(
                    task_id=task_id,
                    status="BLOCKED",
                    caption=caption,
                    video_path=str(video_path),
                    message="No Save draft control was available; publishing is not allowed in approve mode.",
                    state=state,
                )
            delay(random_source(3.0, 8.0))
            blocked = detect_block(page)
            if blocked:
                if not handle_block(blocked):
                    return blocked_result(blocked)
                delay(random_source(3.0, 8.0))
            draft_reference = current_draft_reference(page)
            log(f"draft saved; reference: {draft_reference}")
            print(BROWSER_OPEN_MESSAGE, flush=True)
            log(BROWSER_OPEN_MESSAGE)
            session.transition(
                STATE_DRAFT_SAVED,
                "SAVE DRAFT",
                "the draft was saved in TikTok Studio and waits for human approval",
                url=draft_reference,
            )
            state = save_task_state(
                task_id,
                "DRAFT_SAVED",
                caption,
                str(video_path),
                "Draft saved in TikTok Studio; waiting for human approval before publish.",
                state_path,
                {"mode": mode, "draft_reference": draft_reference, "browser_left_open": True},
            )
            return PosterResult(
                task_id=task_id,
                status="DRAFT_SAVED",
                caption=caption,
                video_path=str(video_path),
                message=f"Draft saved; human approval required before publish. Reference: {draft_reference}",
                state=state,
            )

        agent.decide(
            "auto mode with an approved post",
            "PUBLISH",
            "auto mode publishes only after approval and the caption is written",
        )
        post_button.click()
        delay(random_source(3.0, 8.0))
        blocked = detect_block(page)
        if blocked:
            if not handle_block(blocked):
                return blocked_result(blocked)
            delay(random_source(3.0, 8.0))

        # The publish is only PUBLISHED when the platform confirms it. The
        # address of the post that was published is looked for in the
        # page, and when nothing confirms it the run ends as unknown
        # instead of claiming a publish that did not happen.
        posted_reference = wait_for_published_reference(page)
        if not posted_reference:
            reason = (
                "The publish button was pressed, but the platform did not show "
                "the post, so the publish is not confirmed."
            )
            log(f"NOT CONFIRMED: {reason}")
            state = save_task_state(
                task_id,
                "FAILED_RETRYABLE",
                caption,
                str(video_path),
                reason,
                state_path,
                {"mode": mode},
            )
            return PosterResult(
                task_id=task_id,
                status="FAILED_RETRYABLE",
                caption=caption,
                video_path=str(video_path),
                message=reason,
                state=state,
            )

        session.transition(
            STATE_AWAITING_APPROVAL,
            "PUBLISH",
            "the approved task was published through the official TikTok Studio UI",
        )
        state = save_task_state(
            task_id,
            "PUBLISHED",
            caption,
            str(video_path),
            "Published through the official TikTok Studio UI.",
            state_path,
            {"mode": mode, "posted_url": posted_reference},
        )
        return PosterResult(
            task_id=task_id,
            status="PUBLISHED",
            caption=caption,
            video_path=str(video_path),
            message=f"Published through the official TikTok Studio UI. {posted_reference}",
            state=state,
        )
    except Exception as exc:
        log(f"ERROR: {type(exc).__name__}: {exc}")
        session.transition(
            STATE_FAILED_RETRYABLE,
            "STOP",
            f"the run failed and can be retried: {type(exc).__name__}: {exc}",
        )
        screenshot = capture_error_screenshot(page, screenshot_path) if page is not None else None
        if screenshot and screenshot_reader:
            try:
                screenshot_reader(screenshot)
            finally:
                delete_screenshot(screenshot)
        state = save_task_state(
            task_id,
            "FAILED",
            caption,
            str(video_path),
            str(exc),
            state_path,
            {
                "screenshot_path": screenshot,
                "browser_left_open": bool(context is not None),
                "retryable": True,
            },
        )
        return PosterResult(
            task_id=task_id,
            status="FAILED",
            caption=caption,
            video_path=str(video_path),
            message=f"{type(exc).__name__}: {exc}",
            screenshot_path=screenshot,
            state=state,
        )
    finally:
        # The browser is never closed automatically. It stays open so the user
        # can watch it operate and review the saved draft on screen.
        if context is not None or page is not None:
            log(f"BROWSER CLOSE REASON: none - browser stays open. {BROWSER_OPEN_MESSAGE}")
            if wait_for_user is not None and not captcha_pending:
                try:
                    wait_for_user()
                    log("BROWSER CLOSE REASON: user Enter")
                except EOFError:
                    log("BROWSER CLOSE REASON: timeout - terminal input ended")
                except Exception as wait_exc:
                    log(f"BROWSER CLOSE REASON: exception with full error - {type(wait_exc).__name__}: {wait_exc}")


__all__ = [
    "ACCOUNT_NAME_MARKERS",
    "ALLOWED_TIKTOK_HOSTS",
    "BLOCK_MARKERS",
    "BlockedError",
    "BROWSER_OPEN_MESSAGE",
    "CAPTCHA_OPEN_MESSAGE",
    "CAPTION_FIELD_SELECTOR",
    "CAPTION_FIELD_TIMEOUT_MS",
    "CHROME_EXECUTABLE_CANDIDATES",
    "DEFAULT_CHROME_CHANNEL",
    "DEFAULT_LOGIN_TIMEOUT_SECONDS",
    "DESCRIPTION_FIELD_SELECTOR",
    "LOGIN_BUTTON_MARKERS",
    "ROBOT_CHECK_MESSAGE",
    "ROBOT_MARKERS",
    "LOGIN_WALL_MARKERS",
    "ERROR_PAGE_MARKERS",
    "PosterError",
    "PosterResult",
    "SESSION_STATES",
    "SessionState",
    "SmartAgent",
    "STATE_AWAITING_APPROVAL",
    "STATE_BLOCKED",
    "STATE_CDP_CONNECTED",
    "STATE_CDP_CONNECTING",
    "STATE_CHROME_NOT_FOUND",
    "STATE_CHROME_STARTING",
    "STATE_DRAFT_SAVED",
    "STATE_FAILED_RETRYABLE",
    "STATE_LOGIN_REQUIRED",
    "STATE_RECOVERING",
    "STATE_RESUMING_TASK",
    "STATE_ROBOT_CHECK",
    "STATE_SESSION_CHECKING",
    "STATE_SIGNED_IN",
    "STATE_WAITING_FOR_USER",
    "TIKTOK_STUDIO_HOME_URL",
    "TIKTOK_STUDIO_URL",
    "UPLOAD_PROGRESS_INTERVAL_MS",
    "UPLOAD_PROGRESS_TIMEOUT_MS",
    "SAVE_DRAFT_ENABLE_TIMEOUT_MS",
    "capture_error_screenshot",
    "cdp_endpoint_alive",
    "chrome_pid_for_port",
    "chrome_processes_for_profile",
    "current_draft_reference",
    "current_page_url",
    "delete_screenshot",
    "description_field_count",
    "detect_block",
    "detect_robot_check",
    "fill_description",
    "find_real_chrome",
    "get_page_and_context",
    "is_expected_account",
    "is_logged_in",
    "launch_detached_chrome",
    "launch_real_chrome_context",
    "load_task_state",
    "login_tiktok_studio",
    "logged_in_account",
    "open_page_in_detached_chrome",
    "page_is_alive",
    "page_text",
    "post_to_tiktok_studio",
    "profile_is_locked",
    "redact_secrets",
    "save_task_state",
    "upload_progress_percent",
    "validate_allowed_site",
    "validate_publish_input",
    "wait_for_user_to_solve_captcha",
    "wait_for_save_draft_enabled",
    "wait_for_upload_complete",
]
