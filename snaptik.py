"""SnapTik media acquisition, separated from TikTok Discovery.

Discovery only searches, analyses and filters. This module downloads a
rights-cleared video through the public SnapTik page in an isolated
browser session that never carries TikTok cookies or credentials.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

SNAPTIK_URL = "https://vienphanmem.com/snaptik/"
DOWNLOAD_TIMEOUT_MS = 60000

# Markers that mean the page is asking for human verification. The tool
# never solves them; it reports DOWNLOAD_FAILED instead.
BLOCK_MARKERS = (
    "captcha",
    "verify you are human",
    "verify you're human",
    "are you a robot",
    "security verification",
    "checking your browser",
    "just a moment",
)


class SnapTikError(RuntimeError):
    """Raised when the SnapTik acquisition cannot complete safely."""


def _fail(reason: str) -> SnapTikError:
    return SnapTikError(f"DOWNLOAD_FAILED: {reason}")


def download_snaptik(
    source_url: str,
    task_id: str,
    *,
    page_url: str = SNAPTIK_URL,
    timeout_ms: int = DOWNLOAD_TIMEOUT_MS,
    headless: bool = True,
    destination_dir: Path = Path("data") / "temp",
) -> Path:
    """Download one TikTok video via the SnapTik page into temp storage.

    A fresh browser context is used so no TikTok session, cookie or login
    reaches SnapTik. The page is driven as a user would: fill the URL box,
    press Download, then take the Full HD link when offered. The file is
    received through Playwright's download mechanism. Any challenge,
    timeout, missing file or layout change raises SnapTikError with a
    DOWNLOAD_FAILED reason. No CAPTCHA is bypassed and no private endpoint
    is called.
    """
    wanted = str(source_url or "").strip()
    if not wanted or "tiktok.com" not in wanted.lower():
        raise _fail("the source URL is not a TikTok video URL")
    tid = str(task_id or "").strip()
    if not tid or any(c in tid for c in "/\\"):
        raise _fail("invalid task_id")

    from playwright.sync_api import sync_playwright

    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"{tid}.mp4"

    playwright = sync_playwright().start()
    browser = None
    try:
        # An isolated session: the installed Chrome binary is reused so no
        # browser bundle is downloaded, but Playwright starts it with a
        # throwaway profile — no TikTok cookies, logins or credentials.
        try:
            browser = playwright.chromium.launch(channel="chrome", headless=headless)
        except Exception:
            browser = playwright.chromium.launch(headless=headless)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        try:
            page.goto(page_url, wait_until="domcontentloaded", timeout=timeout_ms)
        except Exception as exc:
            raise _fail(f"SnapTik page did not load: {type(exc).__name__}") from exc
        # Drive the page the way a person would. The bundle is lazy
        # loaded, so scroll once to trigger it; then type the URL with
        # real keystrokes so the page enables its Download button
        # (a programmatic fill leaves it disabled).
        try:
            page.mouse.move(400, 300)
            page.mouse.wheel(0, 800)
            page.wait_for_timeout(1500)
        except Exception:
            pass
        try:
            visible = str(page.content() or "").lower()
        except Exception:
            visible = ""
        for marker in BLOCK_MARKERS:
            if marker in visible:
                raise _fail(f"SnapTik asked for verification ({marker}); not bypassed")

        try:
            box = page.locator("#url").first
            box.wait_for(state="visible", timeout=15000)
            box.click(timeout=8000)
            page.wait_for_timeout(400)
            page.keyboard.type(wanted, delay=20)
            page.wait_for_timeout(1200)
        except Exception as exc:
            raise _fail(f"SnapTik layout changed: no URL input found ({type(exc).__name__})") from exc

        try:
            btn = page.locator("#btnDownload").first
            btn.wait_for(state="visible", timeout=8000)
            if not btn.is_enabled():
                raise _fail("SnapTik Download button stayed disabled")
            btn.click(timeout=15000)
        except SnapTikError:
            raise
        except Exception as exc:
            raise _fail(f"SnapTik layout changed: no Download button found ({type(exc).__name__})") from exc

        # Wait for the result. The page renders a `.btn-download-hd`
        # button with the file URL in `data-download-url` when ready;
        # Full HD is preferred by definition.
        hd_button = None
        for _ in range(12):
            page.wait_for_timeout(5000)
            try:
                visible = str(page.content() or "").lower()
            except Exception:
                visible = ""
            for marker in BLOCK_MARKERS:
                if marker in visible:
                    raise _fail("SnapTik asked for verification after submit; not bypassed")
            try:
                cand = page.locator(".btn-download-hd").first
                cand.wait_for(state="visible", timeout=2000)
                href = str(cand.get_attribute("data-download-url") or "")
                if href.startswith("http"):
                    hd_button = cand
                    break
            except Exception:
                pass
            try:
                err_shown = page.evaluate(
                    """() => [...document.querySelectorAll('.video-not-found')]
                       .filter(e => getComputedStyle(e).display !== 'none')
                       .map(e => (e.textContent || '').trim().slice(0, 120))"""
                )
                if err_shown:
                    raise _fail(f"SnapTik reported no result: {str(err_shown)[:150]}")
            except SnapTikError:
                raise
            except Exception:
                pass
        if hd_button is None:
            raise _fail("SnapTik returned no file link (timeout or layout change)")

        try:
            with page.expect_download(timeout=timeout_ms) as download_info:
                hd_button.click(timeout=8000)
            download = download_info.value
            download.save_as(str(destination))
        except Exception as exc:
            raise _fail(f"SnapTik file download failed: {type(exc).__name__}") from exc

        try:
            if not destination.is_file() or destination.stat().st_size <= 0:
                raise _fail("SnapTik returned an empty file")
        except OSError as exc:
            raise _fail(f"cannot inspect downloaded file: {exc}") from exc
        return destination
    finally:
        try:
            if browser is not None:
                browser.close()
        except Exception:
            pass
        try:
            playwright.stop()
        except Exception:
            pass


def inspect_media(path: Path) -> dict[str, Any]:
    """Inspect a downloaded file: MIME, size, codec, duration, resolution, SHA256.

    The container bytes decide the format; ffprobe measures duration,
    codec and resolution when available. Nothing is assumed.
    """
    from ingest import detect_media_format, measure_duration
    from storage import sha256_file

    target = Path(path)
    if not target.is_file():
        raise SnapTikError(f"DOWNLOAD_FAILED: file not found: {target}")
    size = target.stat().st_size
    if size <= 0:
        raise SnapTikError("DOWNLOAD_FAILED: the downloaded file is empty")
    media_format = detect_media_format(target)
    mime = {"mp4": "video/mp4", "webm": "video/webm", "avi": "video/x-msvideo"}.get(
        media_format, "application/octet-stream"
    )
    duration = measure_duration(target, media_format)
    codec, resolution = _probe_stream(target)
    return {
        "path": str(target),
        "mime": mime,
        "format": media_format,
        "size_bytes": size,
        "codec": codec or "unknown",
        "resolution": resolution or "unknown",
        "duration_seconds": float(duration),
        "sha256": sha256_file(target),
    }


def _probe_stream(path: Path) -> tuple[str | None, str | None]:
    """Return (codec, resolution) via ffprobe, or (None, None) when unavailable."""
    import json as _json
    import shutil
    import subprocess

    if shutil.which("ffprobe") is None:
        return None, None
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=codec_name,width,height",
                "-of", "json",
                str(path),
            ],
            capture_output=True, text=True, timeout=30, check=False,
        )
    except Exception:
        return None, None
    if result.returncode != 0:
        return None, None
    try:
        streams = (_json.loads(result.stdout or "{}").get("streams") or [{}])[0]
    except Exception:
        return None, None
    codec = str(streams.get("codec_name") or "") or None
    width, height = streams.get("width"), streams.get("height")
    resolution = f"{width}x{height}" if width and height else None
    return codec, resolution


__all__ = [
    "BLOCK_MARKERS",
    "DOWNLOAD_TIMEOUT_MS",
    "SNAPTIK_URL",
    "SnapTikError",
    "download_snaptik",
    "inspect_media",
]
