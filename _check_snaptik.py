"""Targeted SnapTik checks: rights gate, DOWNLOAD_FAILED, media inspection."""
import sys
from pathlib import Path

fails = []
def check(name, cond, detail=""):
    print(("PASS" if cond else "FAIL") + f" {name} {detail}")
    if not cond:
        fails.append(name)

# 1. Rights gate: non-allowlisted must reject, allowlisted must permit.
from discover import validate_source_permitted, DiscoveryError
import yaml
config = yaml.safe_load(Path("config.yaml").read_text(encoding="utf-8")) or {}
try:
    validate_source_permitted("https://www.tiktok.com/@v.quc.on/video/7293206212861054216", config)
    check("rights-allowlisted-permitted", True)
except Exception as e:
    check("rights-allowlisted-permitted", False, str(e)[:120])
try:
    validate_source_permitted("https://www.tiktok.com/@dillyyyy5/video/7566361812063993096", config)
    check("rights-nonallowlisted-blocked", False, "should have rejected")
except Exception as e:
    check("rights-nonallowlisted-blocked", "Rejected" in str(e), str(e)[:120])

# 2. SnapTik refuses bad input with DOWNLOAD_FAILED, no network needed.
from snaptik import download_snaptik, inspect_media, SnapTikError, SNAPTIK_URL
check("snaptik-url", SNAPTIK_URL == "https://vienphanmem.com/snaptik/", SNAPTIK_URL)
try:
    download_snaptik("not-a-url", "t1")
    check("snaptik-bad-url-fails", False)
except SnapTikError as e:
    check("snaptik-bad-url-fails", "DOWNLOAD_FAILED" in str(e), str(e)[:100])
try:
    download_snaptik("https://www.tiktok.com/@v.quc.on/video/1", "bad/id")
    check("snaptik-bad-task-fails", False)
except SnapTikError as e:
    check("snaptik-bad-task-fails", "DOWNLOAD_FAILED" in str(e), str(e)[:100])

# 3. Isolated session: module must not load the TikTok Chrome profile or
# pass any stored cookies/credentials into the SnapTik browser.
src = Path("snaptik.py").read_text(encoding="utf-8")
low = src.lower()
check("snaptik-isolated-session", "chrome-profile" not in low and "launch_detached_chrome" not in src and "config.yaml" not in low)
check("snaptik-no-captcha-bypass", "captcha" in src and "not bypassed" in src.lower())

# 4. Media inspection on a real local file.
sample = Path("data/originals/p15v-clip.webm")
if sample.exists():
    try:
        info = inspect_media(sample)
        ok = info["size_bytes"] > 0 and len(info["sha256"]) == 64 and info["duration_seconds"] > 0
        check("inspect-real-file", ok, f"{info['mime']} {info['size_bytes']}B {info['duration_seconds']:.2f}s {info['codec']}/{info['resolution']}")
    except Exception as e:
        check("inspect-real-file", False, str(e)[:150])
else:
    check("inspect-real-file", False, "sample missing")

# 5. Workflow wiring: rights gate before snaptik, approval/publish untouched.
wsrc = Path("workflow.py").read_text(encoding="utf-8")
check("workflow-rights-before-snaptik", wsrc.find("validate_source_permitted") < wsrc.find("download_snaptik"))
check("workflow-download-failed", "DOWNLOAD_FAILED" in wsrc or "SnapTikError" in wsrc)
check("workflow-library-keeps-source", '"source_url"' in wsrc and '"creator"' in wsrc)

sys.exit(1 if fails else 0)
