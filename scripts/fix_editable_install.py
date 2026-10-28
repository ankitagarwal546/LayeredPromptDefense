"""Make the editable install importable on macOS + Python 3.13 (clears the "hidden" flag on .pth files).

    python scripts/fix_editable_install.py            # fix and report
    python scripts/fix_editable_install.py --check    # report only; exit 1 if a hidden .pth was found

Python 3.13's `site` module skips `.pth` files that carry the macOS UF_HIDDEN flag. macOS sometimes sets that flag on
the `__editable__...pth` file that `pip install -e .` writes, so `import injection_defense` fails outside pytest
(pytest itself works through `pythonpath = ["src"]` in pyproject.toml). This clears the flag on this virtual
environment's `.pth` files only. No effect on other systems. Re-run after reinstalling.
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    site_packages = Path(sysconfig.get_paths()["purelib"])
    hidden = hidden_pth_files(site_packages)
    if not hidden:
        print(f"ok: no hidden .pth files in {site_packages}")
        return 0
    if args.check:
        print("hidden .pth files (Python 3.13 will skip them): " + ", ".join(p.name for p in hidden))
        return 1
    for p in hidden:
        os.chflags(p, os.stat(p).st_flags & ~stat.UF_HIDDEN)
        print(f"cleared hidden flag: {p.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
