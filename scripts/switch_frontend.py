"""Switch the web UI served at /app/ between the new frontend and the previous (classic) one.

    python scripts/switch_frontend.py --status
    python scripts/switch_frontend.py --use previous   # serve the classic UI at /app/
    python scripts/switch_frontend.py --use new        # back to the new UI

Folders:
  frontend/                    what /app/ serves (edited in place by development)
  frontend_backup_previous/    byte-for-byte copy of the UI before the 2026-10-29 overhaul (git tag
                               `frontend-classic-2026-10-29`); never modified by this script; always served at /app-previous/
  frontend_backup_new/         written by `--use previous`: a copy of the new UI so `--use new` can restore it

Files are copied with their timestamps; nothing is deleted outside frontend/ and frontend_backup_new/. The server
serves files from disk, so a reload in the browser picks up the switch (no restart needed).
"""

from __future__ import annotations

import argparse
import filecmp
import hashlib
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIVE, PREVIOUS, NEW = ROOT / "frontend", ROOT / "frontend_backup_previous", ROOT / "frontend_backup_new"


def digest(folder: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(folder.rglob("*")):
        if p.is_file():
            h.update(p.relative_to(folder).as_posix().encode() + b"\0" + p.read_bytes() + b"\0")
    return h.hexdigest()[:16]


def same(a: Path, b: Path) -> bool:
    return a.is_dir() and b.is_dir() and digest(a) == digest(b)


def replace(src: Path, dst: Path) -> None:
    tmp = dst.with_name(dst.name + ".switching")
    shutil.rmtree(tmp, ignore_errors=True)
    shutil.copytree(src, tmp, copy_function=shutil.copy2)
    shutil.rmtree(dst, ignore_errors=True)
    tmp.rename(dst)


def status() -> str:
    if same(LIVE, PREVIOUS):
        return "previous"
    if NEW.is_dir() and same(LIVE, NEW):
        return "new"
    return "new (working copy)"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--use", choices=["previous", "new"])
    group.add_argument("--status", action="store_true")
    args = parser.parse_args()
    if not PREVIOUS.is_dir():
        print(f"missing {PREVIOUS.name}/: restore it with `git checkout frontend-classic-2026-10-29 -- frontend` into a copy", file=sys.stderr)
        return 2
    if args.status:
        print(f"/app/ serves: {status()}  (frontend/ {digest(LIVE)}; previous {digest(PREVIOUS)}"
              + (f"; saved new {digest(NEW)}" if NEW.is_dir() else "") + ")\n/app-previous/ always serves the previous UI")
        return 0
    if args.use == "previous":
        if same(LIVE, PREVIOUS):
            print("already serving the previous UI")
            return 0
        replace(LIVE, NEW)  # keep the new UI so it can come back
        replace(PREVIOUS, LIVE)
        assert not filecmp.dircmp(LIVE, PREVIOUS).diff_files
        print(f"/app/ now serves the previous UI; the new UI is saved in {NEW.name}/. Reload the browser.")
        return 0
    if not same(LIVE, PREVIOUS):
        print("already serving the new UI")
        return 0
    if not NEW.is_dir():
        print(f"no saved new UI in {NEW.name}/; restore it with `git checkout -- frontend`", file=sys.stderr)
        return 2
    replace(NEW, LIVE)
    print("/app/ now serves the new UI. Reload the browser.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
