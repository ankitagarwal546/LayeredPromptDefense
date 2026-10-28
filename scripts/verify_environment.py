"""Check that the environment can run the project. Prints status only; never prints secrets.

    python scripts/verify_environment.py          # no network calls
    python scripts/verify_environment.py --ping   # also makes ONE tiny call to the configured real model
"""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))  # fallback if the editable install is not importable

REQUIRED = ["fastapi", "uvicorn", "pydantic", "pydantic_settings", "httpx", "pandas", "matplotlib", "pypdf", "docx", "multipart"]
OPTIONAL = ["transformers", "torch", "pytest"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ping", action="store_true", help="make one tiny real-model call")
    args = parser.parse_args()
    ok = True

    print(f"python {sys.version.split()[0]} ({'ok' if sys.version_info >= (3, 10) else 'NEEDS >= 3.10'})")
    ok &= sys.version_info >= (3, 10)
    for name in REQUIRED:
        try:
            importlib.import_module(name)
            print(f"  [ok]      {name}")
        except ImportError:
            print(f"  [MISSING] {name}   -> pip install -e '.[dev]'")
            ok = False
    for name in OPTIONAL:
        try:
            importlib.import_module(name)
            print(f"  [ok]      {name} (optional)")
        except ImportError:
            print(f"  [absent]  {name} (optional)")

    # macOS + Python 3.13: a hidden editable-install .pth breaks `import injection_defense` outside pytest; clear the flag.
    sys.path.insert(0, str(ROOT / "scripts"))
    from fix_editable_install import hidden_pth_files
    import os
    import stat
    import sysconfig
    for pth in hidden_pth_files(Path(sysconfig.get_paths()["purelib"])):
        os.chflags(pth, os.stat(pth).st_flags & ~stat.UF_HIDDEN)
        print(f"  [fixed]   cleared the macOS hidden flag on {pth.name} (Python 3.13 skips hidden .pth files)")

    try:
        from injection_defense.config import Settings
        from injection_defense.defenses.classifier import UnavailableClassifier, create_classifier
        from injection_defense.llm.base import ModelNotConfiguredError
        from injection_defense.llm.provider import create_real_llm_client
    except ImportError as exc:
        print(f"cannot import injection_defense: {exc}\n  try: PYTHONPATH=src  (see README troubleshooting)")
        return 1

    settings = Settings()
    print(f".env file: {'present' if (ROOT / '.env').exists() else 'absent (defaults: mock mode)'}")
    print(f"LLM_PROVIDER={settings.llm_provider}  default model mode={settings.default_model_mode}")
    llm = None
    try:
        llm = create_real_llm_client(settings)
        print(f"real model: configured ({llm.provider} / {llm.model_name})")
    except ModelNotConfiguredError as exc:
        print(f"real model: NOT configured ({exc}); mock mode still works")
    clf = create_classifier(settings)
    print("classifier: " + ("unavailable (" + clf.reason + ")" if isinstance(clf, UnavailableClassifier) else "configured"))
    print(f"data dir: {'ok' if (settings.data_dir / 'dev_cases.jsonl').exists() else 'MISSING dev_cases.jsonl'}")

    if args.ping:
        if llm is None:
            print("ping: skipped, no real model configured")
        else:
            from injection_defense.llm.base import LLMError, PromptBundle

            try:
                reply = llm.generate(PromptBundle("Reply with one word.", "Say OK."))
                print(f"ping: ok ({len(reply.text)} chars returned)")
            except LLMError as exc:
                print(f"ping: FAILED ({exc})")
                ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
