"""P15V helper: produce a small test video using the live Chrome.

The project's original video is about 68.6 MB, which exceeds Playwright's
50 MB file-transfer cap for a CDP-attached browser, so a smaller test clip
is required for the upload and resume checks.

This helper loads the existing original in a local Chrome page, plays it
through a canvas, and records it with ``MediaRecorder`` at a low bitrate.
It writes the result into ``data/temp/``. It does not modify, move, or
delete the original video, and it does not publish anything.
"""

from __future__ import annotations

import base64
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

RECORD_SECONDS = 6
RECORD_SCRIPT = """
async ({seconds}) => {
  const canvas = document.createElement('canvas');
  canvas.width = 480;
  canvas.height = 270;
  const context = canvas.getContext('2d');
  const video = document.createElement('video');
  video.src = window.__sourceUrl;
  video.muted = true;
  video.crossOrigin = 'anonymous';
  await new Promise((resolve, reject) => {
    video.onloadeddata = resolve;
    video.onerror = () => reject(new Error('video load failed'));
  });
  video.currentTime = 0;
  await video.play().catch(() => {});
  const stream = canvas.captureStream(15);
  const chunks = [];
  const recorder = new MediaRecorder(stream, { mimeType: 'video/webm;codecs=vp8' });
  recorder.ondataavailable = (event) => { if (event.data.size) chunks.push(event.data); };
  recorder.start();
  const started = Date.now();
  await new Promise((resolve) => {
    const timer = setInterval(() => {
      context.drawImage(video, 0, 0, canvas.width, canvas.height);
      if (Date.now() - started > seconds * 1000) { clearInterval(timer); resolve(); }
    }, 66);
  });
  recorder.stop();
  await new Promise((resolve) => { recorder.onstop = resolve; });
  const blob = new Blob(chunks, { type: 'video/webm' });
  const buffer = await blob.arrayBuffer();
  let binary = '';
  const bytes = new Uint8Array(buffer);
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
  return btoa(binary);
}
"""


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9333
    source_url = sys.argv[2] if len(sys.argv) > 2 else (
        "http://127.0.0.1:8765/Screen%20Recording%202026-10-21%20041802.mp4"
    )
    output = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("data/temp/p15v-clip.webm")

    playwright = sync_playwright().start()
    try:
        browser = playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        context = browser.contexts[0]
        page = context.new_page()
        # The page must share the origin of the source video, otherwise the
        # browser refuses to decode it.
        origin = source_url.rsplit("/", 1)[0] + "/"
        page.goto(origin)
        page.evaluate("url => { window.__sourceUrl = url; }", source_url)
        encoded = page.evaluate(RECORD_SCRIPT, {"seconds": RECORD_SECONDS})
        payload = base64.b64decode(encoded)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(payload)
        page.close()
        print(json.dumps({
            "output": str(output),
            "bytes": len(payload),
            "kilobytes": round(len(payload) / 1024, 1),
            "source_url": source_url,
        }, indent=2))
        return 0
    finally:
        playwright.stop()


if __name__ == "__main__":
    raise SystemExit(main())
