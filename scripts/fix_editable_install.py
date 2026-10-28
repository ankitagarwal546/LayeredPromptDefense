"""Make the editable install importable on macOS + Python 3.13, durably.

    python scripts/fix_editable_install.py            # fix and report
    python scripts/fix_editable_install.py --check    # report only; exit 1 if the package is not importable

Python 3.13's `site` module skips `.pth` files that carry the macOS UF_HIDDEN flag, and on this machine macOS re-applies
that flag to every `.pth` file in the virtual environment within minutes (observed 2026-10-29), so clearing it does not
last. The fix links the package folder into site-packages (`site-packages/injection_defense -> src/injection_defense`):
a linked package is imported without any `.pth`, flags do not matter, and edits under src/ stay live. It also clears the
flag on the `.pth` files. pytest works regardless (`pythonpath = ["src"]` in pyproject.toml). Re-run after reinstalling.
"""

from __future__ import annotations

import argparse
import os
import stat
import sys
import sysconfig
from pathlib import Path


def hidden_pth_files(site_packages: Path) -> list[Path]:
    flag = getattr(stat, "UF_HIDDEN", 0)
    if not flag:
        return []
    return [p for p in sorted(site_packages.glob("*.pth")) if os.stat(p).st_flags & flag]


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "injection_defense"


def link_package(site_packages: Path) -> str:
    link = site_packages / PACKAGE.name
    if link.is_symlink() and link.resolve() == PACKAGE.resolve():
        return "ok"
    if link.exists():
        return f"left alone: {link} exists and is not a link to {PACKAGE}"
    link.symlink_to(PACKAGE, target_is_directory=True)
    return "linked"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    site_packages = Path(sysconfig.get_paths()["purelib"])
    hidden = hidden_pth_files(site_packages)
    link = site_packages / PACKAGE.name
    linked = link.is_symlink() and link.resolve() == PACKAGE.resolve()
    if args.check:
        print(f"package link: {'ok' if linked else 'missing'}; hidden .pth files: {', '.join(p.name for p in hidden) or 'none'}")
        return 0 if linked or not hidden else 1
    for p in hidden:
        os.chflags(p, os.stat(p).st_flags & ~stat.UF_HIDDEN)
        print(f"cleared hidden flag: {p.name} (macOS may set it again; the package link below is the durable fix)")
    print(f"package link {site_packages / PACKAGE.name} -> {PACKAGE}: {link_package(site_packages)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
