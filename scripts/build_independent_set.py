"""Build the independent evaluation set from the human-written documents and the BIPIA attack instructions.

    python scripts/build_independent_set.py

Refuses to run if the checklist fails or if the output already exists (the set is frozen once built).
Writes data/independent/{attacks.jsonl, benign.jsonl, MANIFEST.json, independent.sha256}.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))  # fallback if the editable install is not importable

from injection_defense.evaluation.independent import (  # noqa: E402
    BIPIA_SHA256, build_cases, check_documents, load_bipia, load_user_documents, sha256_file,
)

OUTPUTS = ("attacks.jsonl", "benign.jsonl", "MANIFEST.json", "independent.sha256")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dir", default=str(ROOT / "data" / "independent"))
    args = parser.parse_args()
    folder = Path(args.dir)
    docs_path = folder / "user_documents.jsonl"
    if not docs_path.exists():
        print(f"missing {docs_path}", file=sys.stderr)
        return 2
    if existing := [n for n in OUTPUTS if (folder / n).exists()]:
        print(f"refusing to overwrite a built set: {existing}. The independent set is frozen once built.", file=sys.stderr)
        return 2
    bipia_dir = ROOT / "data" / "external" / "bipia"
    bipia = load_bipia(bipia_dir)
    docs = load_user_documents(docs_path)
    problems = check_documents(docs, [s for items in bipia.values() for s in items])
    if problems:
        print("the checklist fails; run scripts/validate_user_docs.py", file=sys.stderr)
        return 2
    criteria = json.loads((bipia_dir / "attack_criteria.json").read_text(encoding="utf-8"))
    attacks, benign, table = build_cases(docs, bipia, criteria, source_note=f"BIPIA file sha256 {BIPIA_SHA256[:12]}")
    for name, cases in (("attacks.jsonl", attacks), ("benign.jsonl", benign)):
        (folder / name).write_text("".join(c.model_dump_json() + "\n" for c in cases), encoding="utf-8")
    manifest = {
        "bipia_file_sha256": BIPIA_SHA256,
        "attack_criteria_sha256": sha256_file(bipia_dir / "attack_criteria.json"),
        "user_documents_sha256": sha256_file(docs_path),
        "n_attacks": len(attacks), "n_benign": len(benign),
        "n_ordinary_documents": sum(d.kind == "ordinary" for d in docs),
        "n_security_themed_documents": sum(d.kind == "security_themed" for d in docs),
        "assignment": table,
        "rule": "attack i goes to ordinary document i mod N (sorted by doc_id); position = start/middle/end by (i // N + i) mod 3; deterministic, no randomness",
    }
    (folder / "MANIFEST.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    lines = [f"{sha256_file(folder / n)}  {n}" for n in ("attacks.jsonl", "benign.jsonl", "MANIFEST.json", "user_documents.jsonl")]
    (folder / "independent.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"built {len(attacks)} attack cases and {len(benign)} benign cases in {folder}\n" + "\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
