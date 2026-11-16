"""Kiem tra docs TOOLTDH: link ton tai + moi file nguon co tai lieu (nhe, idempotent)."""
import re
from pathlib import Path
ROOT=Path("D:/TOOLTDH"); DOCS=ROOT/"docs"
ok, bad = 0, []
mds=list(DOCS.rglob("*.md"))
for m in mds:
    t=m.read_text(encoding="utf-8")
    for link in re.findall(r"\((files/[^)]+\.md|modules/[^)]+\.md|(?:START_HERE|FILE_INDEX|TROUBLESHOOTING|MODULE_ARCHITECTURE|DEVELOPMENT_ROADMAP|CHANGELOG|TECHNICAL_DECISIONS|RELEASE_CHECKLIST)\.md)\)",t):
        target=(m.parent/link if link.startswith(("files/","modules/")) else DOCS/link)
        if target.exists(): ok+=1
        else: bad.append(f"{m.relative_to(ROOT)} -> {link}")
print(f"LINKS_OK={ok} LINKS_BAD={len(bad)}")
for b in bad[:30]: print("MISS:",b)
# coverage
import subprocess
try: tr=subprocess.run(["git","ls-files"],cwd=ROOT,capture_output=True,text=True,timeout=15).stdout.split()
except Exception: tr=[]
src=[x for x in tr if x.endswith((".py",".js",".html",".css",".yaml",".toml",".txt",".spec",".example")) and not x.startswith("docs/")]
miss=[]
for s in src:
    cand=DOCS/("files/"+s.replace(".","_")+".md"); cand2=DOCS/("files/"+s+".md")
    rel="files/"+s.replace("/","_")
    found=any((DOCS/f"files/{s.replace('/','_').replace('.','_')}.md").exists() for _ in [0])
    # mirror path check
    parts=s.split("/"); mp=DOCS.joinpath("files",*parts[:-1])/(parts[-1].replace(".","_")+".md") if len(parts)>1 else DOCS/("files/"+parts[0].replace(".","_")+".md")
    if not mp.exists(): miss.append(s)
print(f"SRC_TOTAL={len(src)} SRC_MISSING_DOCS={len(miss)}")
for m in miss[:30]: print("NODOC:",m)
