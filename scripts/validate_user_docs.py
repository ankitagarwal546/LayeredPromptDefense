"""Check the human-written documents against the checklist (see docs/INDEPENDENT_DOCS_GUIDE.md).

    python scripts/validate_user_docs.py [data/independent/user_documents.jsonl]

Prints each rule as pass/fail and exits 1 if anything blocks building. It never changes your file.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))  # fallback if the editable install is not importable

from injection_defense.evaluation.independent import (  # noqa: E402
    MAX_CHARS, MAX_DOCS, MAX_PER_AREA, MAX_SECURITY, MIN_AREAS, MIN_CHARS, MIN_DOCS, MIN_ORDINARY, MIN_SECURITY,
    check_documents, load_bipia, load_user_documents,
)

RULES = [
    ("count", f"{MIN_DOCS}-{MAX_DOCS} documents in total"),
    ("ordinary", f"at least {MIN_ORDINARY} ordinary documents"),
    ("security", f"{MIN_SECURITY}-{MAX_SECURITY} security-themed documents"),
    ("themes", "security-themed set covers: 2 AI, 2 cybersecurity, 2 malicious-instructions, 1 imperative-for-humans; ordinary have none"),
    ("areas", f"ordinary documents cover at least {MIN_AREAS} areas, at most {MAX_PER_AREA} per area"),
    ("length", f"every text is {MIN_CHARS}-{MAX_CHARS} characters"),
    ("key_topics", "every text mentions at least 3 of its 4 key-topic groups"),
    ("authorship", "authorship is labeled honestly (human_written: original_work true; ai_generated: original_work false, with generator and notes)"),
    ("ordinary_topic", "ordinary documents do not mention AI / assistants / prompts"),
    ("directed", "no line addressed to an AI or assistant"),
    ("cue_strings", "no text the attack checks look for (brand names, links)"),
    ("emoji", "no emoji-heavy text"),
    ("encoded", "no long encoded-looking strings"),
    ("bipia_copy", "no copied BIPIA instruction"),
    ("unique", "ids, topics and texts are unique"),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", nargs="?", default=str(ROOT / "data" / "independent" / "user_documents.jsonl"))
    args = parser.parse_args()
    path = Path(args.path)
    if not path.exists():
        print(f"{path} does not exist yet. Start from data/independent/user_documents.template.jsonl and read docs/INDEPENDENT_DOCS_GUIDE.md.")
        return 1
    try:
        docs = load_user_documents(path)
    except ValueError as exc:
        print(exc)
        return 1
    bipia = load_bipia(ROOT / "data" / "external" / "bipia")
    problems = check_documents(docs, [s for items in bipia.values() for s in items])
    errors = [p for p in problems if p.severity == "error"]
    failed = {p.rule for p in errors}
    kinds, origins = Counter(d.kind for d in docs), Counter(d.origin for d in docs)
    print(f"{len(docs)} documents ({kinds['ordinary']} ordinary, {kinds['security_themed']} security-themed); "
          f"{origins['human_written']} human-written, {origins['ai_generated']} AI-generated, "
          f"{sum(d.human_reviewed for d in docs)} human-reviewed\n")
    for rule, text in RULES:
        bad = any(rule == r or (rule == "unique" and r.startswith("unique")) for r in failed)
        print(f"  [{'FAIL' if bad else ' ok '}] {text}")
    if errors:
        print("\nTo fix:")
        for p in errors:
            print(f"  - {p.message}")
        return 1
    print("\nAll checks pass: the set can be built with scripts/build_independent_set.py")
    for p in problems:
        print(f"WARNING ({p.rule}): {p.message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
