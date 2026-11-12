"""P15V helper: diagnose why the test clip cannot be recorded."""

from __future__ import annotations

import json
import sys

from playwright.sync_api import sync_playwright

PROBE = """
async ({sourceUrl}) => {
  const result = { canPlay: null, readyState: -1, error: '', mediaRecorder: {}, mimeSupport: [] };
  result.mediaRecorder.exists = typeof MediaRecorder !== 'undefined';
  for (const type of ['video/webm;codecs=vp8', 'video/webm;codecs=vp9', 'video/webm', 'video/mp4']) {
    try { result.mimeSupport.push([type, MediaRecorder.isTypeSupported(type)]); } catch (e) {}
  }
  const video = document.createElement('video');
  video.src = sourceUrl;
  video.muted = true;
  result.canPlay = video.canPlayType('video/mp4');
  await new Promise((resolve) => {
    const done = () => resolve();
    video.onloadeddata = done;
    video.oncanplay = done;
    video.onerror = () => { result.error = video.error ? ('code ' + video.error.code + ' ' + video.error.message) : 'unknown'; resolve(); };
    setTimeout(done, 6000);
  });
  result.readyState = video.readyState;
  result.videoWidth = video.videoWidth;
  result.videoHeight = video.videoHeight;
  result.duration = video.duration;
  return result;
}
"""


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9333
    source_url = sys.argv[2] if len(sys.argv) > 2 else (
        "http://127.0.0.1:8765/Screen%20Recording%202026-10-21%20041802.mp4"
    )
    playwright = sync_playwright().start()
    try:
        browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        context = browser.contexts[0]
        page = context.new_page()
        page.goto("http://127.0.0.1:8765/")
        print(json.dumps(page.evaluate(PROBE, {"sourceUrl": source_url}), indent=2))
        page.close()
        return 0
    finally:
        playwright.stop()


if __name__ == "__main__":
    raise SystemExit(main())
