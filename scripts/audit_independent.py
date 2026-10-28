"""Read-only audit of the two independent-set runs (1B and 8B): verification checks, independent recomputation of
every reported metric from the raw files, a 1B-vs-8B comparison, per-category tables and charts.

    python scripts/audit_independent.py                      # prints the checks and metric tables
    python scripts/audit_independent.py --write              # also writes docs/results/independent_audit/

It never writes to results/ or to the experiment records. Metrics are recomputed here from outcomes.jsonl,
manual_labels.jsonl and the review decisions (not by calling metrics.py), then compared with the archived CSVs.
The comparison statistics are exploratory and post hoc; they are not part of the pre-registered results.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from injection_defense.evaluation.metrics import (  # noqa: E402
    attack_level_rate, cluster_bootstrap, mcnemar_exact, sign_test,
)

RUNS = {"1B": "4da08316a2fb", "8B": "8a4c672e6307"}
ARCHIVE = {"1B": ROOT / "docs/results/independent_run_1", "8B": ROOT / "docs/results/independent_run_2"}
CONFIGS = ["E0", "E1", "E1b", "E2", "E3", "E4", "E5"]
SCORER_FILES = [
    "src/injection_defense/defenses/output_validator.py", "src/injection_defense/defenses/heuristic_rules.py",
    "src/injection_defense/defenses/heuristic.py", "src/injection_defense/defenses/classifier.py",
    "src/injection_defense/defenses/structural.py", "src/injection_defense/evaluation/attack_checks.py",
    "src/injection_defense/evaluation/runner.py", "src/injection_defense/evaluation/disruption.py",
    "src/injection_defense/pipeline.py", "src/injection_defense/config.py", "data/external/bipia/attack_criteria.json",
    "data/task_disruption_carriers.json",
]


# ---------- statistics (pure functions) ----------
def wilson(k: int, n: int) -> tuple[float, float] | None:
    if n == 0:
        return None
    z, p = 1.96, k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centre - half), min(1.0, centre + half)


def newcombe(k1: int, n1: int, k2: int, n2: int) -> tuple[float, float, float]:
    """Difference p1 - p2 with a Newcombe (hybrid Wilson) 95% interval; assumes independent observations."""
    (l1, u1), (l2, u2) = wilson(k1, n1), wilson(k2, n2)
    p1, p2 = k1 / n1, k2 / n2
    return p1 - p2, (p1 - p2) - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2), (p1 - p2) + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)


def paired_bootstrap(a: dict, b: dict, *, resamples: int = 10000, seed: int = 20261027) -> dict:
    """Cluster bootstrap over attacks. a and b map attack id -> mean success over its resolved trials (or None).
    Returns the mean paired difference mean(a) - mean(b) with a percentile 95% interval, resampling whole attacks."""
    keys = sorted(k for k in a if a[k] is not None and b.get(k) is not None)
    if not keys:
        return {"n": 0}
    diffs = [a[k] - b[k] for k in keys]
    rng = random.Random(seed)
    means = sorted(sum(rng.choice(diffs) for _ in diffs) / len(diffs) for _ in range(resamples))
    return {"n": len(keys), "diff": sum(diffs) / len(diffs), "lo": means[int(0.025 * resamples)], "hi": means[int(0.975 * resamples) - 1]}


def transitions(x: dict, y: dict) -> Counter:
    """Observation-level pairing of two configurations (same case, same trial). Keys are (case, trial) -> bool|None."""
    out: Counter = Counter()
    for k in x:
        if x[k] is None or y.get(k) is None:
            out["unresolved"] += 1
        else:
            out[("success" if x[k] else "fail") + "->" + ("success" if y[k] else "fail")] += 1
    return out


def pct(k: int, n: int) -> str:
    if n == 0:
        return "n/a (0)"
    lo, hi = wilson(k, n)
    return f"{100 * k / n:.1f}% ({k}/{n}) [{100 * lo:.0f}-{100 * hi:.0f}]"


# ---------- loading ----------
def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_run(name: str, results_dir: Path) -> dict:
    folder = results_dir / RUNS[name]
    raw = read_jsonl(folder / "outcomes.jsonl")
    labels: dict = {}
    if (folder / "manual_labels.jsonl").exists():
        for r in read_jsonl(folder / "manual_labels.jsonl"):
            labels[(r["experiment"], r["trial"], r["case_id"])] = r["attack_success"]  # last wins
    decisions = list(csv.DictReader((ARCHIVE[name] / "human_review_decisions.csv").open(encoding="utf-8")))
    return {"name": name, "folder": folder, "raw": raw, "labels": labels, "decisions": decisions,
            "meta": json.loads((folder / "metadata.json").read_text(encoding="utf-8"))}


def effective(o: dict, labels: dict):
    """Attack outcome after human review: manual label if any, else the automatic result (None if unresolved)."""
    lab = labels.get((o["experiment"], o["trial"], o["case_id"]))
    return lab if lab is not None else o["attack_success"]


# ---------- verification checks ----------
def git_show(ref: str, path: str) -> bytes | None:
    r = subprocess.run(["git", "show", f"{ref}:{path}"], cwd=ROOT, capture_output=True)
    return r.stdout if r.returncode == 0 else None


def run_checks(runs: dict) -> list[tuple[str, bool, str]]:
    from prepare_review import group_id  # the same grouping used when the reviews were prepared

    results: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        results.append((name, bool(ok), detail))

    frozen = dict(line.split()[::-1] for line in (ROOT / "data/independent/independent.sha256").read_text().splitlines() if line.strip())
    tag_commit = subprocess.run(["git", "rev-parse", "independent-freeze^{commit}"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    models = {}
    for name, run in runs.items():
        meta, raw, tag = run["meta"], run["raw"], f"[{name}]"
        models[name] = meta["model"]
        check(f"{tag} run id in metadata equals {RUNS[name]}", meta["run_id"] == RUNS[name])
        check(f"{tag} model", True, f"{meta['model']['name']} ({meta['model']['provider']}), params {meta['model']['generation_params']}, is_mock={meta['model']['is_mock']}")
        check(f"{tag} not a mock model", meta["model"]["is_mock"] is False)
        check(f"{tag} classifier is the same model", meta["classifier"].get("model") == meta["model"]["name"], str(meta["classifier"]))
        check(f"{tag} case set / repetitions / configs", meta["case_set"] == "independent" and meta["repetitions"] == 2 and list(meta["configs"]) == CONFIGS)
        check(f"{tag} code clean at run time", meta["code"]["dirty"] is False, meta["code"]["commit"][:7])
        check(f"{tag} dataset checksum equals the frozen attacks.jsonl", meta["dataset"]["sha256"] == frozen["attacks.jsonl"])
        check(f"{tag} benign file checksum equals the frozen benign.jsonl", list(meta["dataset"]["extra_files"].values())[0] == frozen["benign.jsonl"])
        # scorer / defense files identical at the run commit and at the freeze tag
        same = [f for f in SCORER_FILES if git_show(meta["code"]["commit"], f) == git_show(tag_commit, f) and git_show(tag_commit, f) is not None]
        check(f"{tag} scorer and defense files identical at run commit and freeze tag", len(same) == len(SCORER_FILES),
              f"{len(same)}/{len(SCORER_FILES)} files; differing: {sorted(set(SCORER_FILES) - set(same))}")
        keys = [(o["experiment"], o["trial"], o["case_id"]) for o in raw]
        check(f"{tag} 1,400 unique outcomes, 7 configs x 2 trials x 100 cases", len(raw) == 1400 and len(set(keys)) == 1400)
        check(f"{tag} every outcome carries this run id", {o["run_id"] for o in raw} == {RUNS[name]})
        check(f"{tag} raw outputs carry no human labels (labels are separate)", all(o["manual_label"] is None for o in raw))
        sha_file = run["folder"] / "outcomes_pre_review.sha256"
        recorded = sha_file.read_text().split()[0] if sha_file.exists() else None
        actual = hashlib.sha256((run["folder"] / "outcomes.jsonl").read_bytes()).hexdigest()
        check(f"{tag} outcomes.jsonl sha256 equals the checksum recorded before the review", recorded == actual, f"{actual[:12]}")
        # archived pre-review results preserved
        pre = ARCHIVE[name] / "pre_review" / "outcomes_no_text.csv"
        if pre.exists():
            prerows = {(r["experiment"], int(r["trial"]), r["case_id"]): r for r in csv.DictReader(pre.open(encoding="utf-8"))}
            cell = lambda v: "" if v is None else str(v)  # the CSV stores None as an empty cell
            mism = sum(1 for o in raw if (o["experiment"], o["trial"], o["case_id"]) not in prerows
                       or any(cell(o[k]) != prerows[(o["experiment"], o["trial"], o["case_id"])][k]
                              for k in ("scoring", "attack_success", "status", "blocked_by", "flagged", "task_completed", "model_calls", "detector_failures")))
            check(f"{tag} archived pre-review outcomes match the raw automatic results", len(prerows) == 1400 and mism == 0, f"{mism} mismatches")
        else:
            check(f"{tag} archived pre-review outcomes exist", False, str(pre))
        # human-review decisions applied correctly
        by_group = {r["group_id"]: r for r in run["decisions"]}
        review = [o for o in raw if o["is_attack"] and o["scoring"] == "needs_review"]
        expect: dict = {}
        unsure = 0
        unmatched = 0
        for o in review:
            g = by_group.get(group_id(RUNS[name], o["case_id"], o["output_text"] or ""))
            if g is None:
                unmatched += 1
                continue
            hl = g["human_label"].strip().lower()
            if hl in ("yes", "no"):
                expect[(o["experiment"], o["trial"], o["case_id"])] = hl == "yes"
            else:
                unsure += 1
        check(f"{tag} every needs_review outcome belongs to a decided review group", unmatched == 0, f"{len(review)} outcomes, {unmatched} unmatched")
        check(f"{tag} manual_labels.jsonl equals the decisions CSV (yes/no only)", run["labels"] == expect, f"{len(run['labels'])} labels vs {len(expect)} expected")
        check(f"{tag} labels only on needs_review outcomes", set(run["labels"]) <= {(o["experiment"], o["trial"], o["case_id"]) for o in review})
        unresolved_reviewed = [o for o in review if (o["experiment"], o["trial"], o["case_id"]) not in run["labels"]]
        check(f"{tag} UNSURE outcomes remain unresolved", len(unresolved_reviewed) == unsure and all(effective(o, run['labels']) is None for o in unresolved_reviewed),
              f"{unsure} unsure outcome(s)")
        ids = {r["human_attack"] for r in run["decisions"]}
        check(f"{tag} decisions file complete (all rows have both judgments)", all(r["human_attack"] and r["task_disrupted"] for r in run["decisions"]) and ids <= {"YES", "NO", "UNSURE"}, f"{len(run['decisions'])} groups")
    a, b = runs["1B"]["meta"], runs["8B"]["meta"]
    check("[both] identical defense configurations", a["configs"] == b["configs"])
    check("[both] identical dataset and generation parameters", a["dataset"] == b["dataset"] and a["model"]["generation_params"] == b["model"]["generation_params"])
    check("[both] different models, as intended", a["model"]["name"] != b["model"]["name"], f"{a['model']['name']} vs {b['model']['name']}")
    check("[both] same case ids in both runs", {(o["case_id"]) for o in runs["1B"]["raw"]} == {(o["case_id"]) for o in runs["8B"]["raw"]})
    check("[both] distinct run ids", RUNS["1B"] != RUNS["8B"])
    return results


# ---------- metrics ----------
def load_disruption(name: str, run: dict) -> dict:
    """Category per attack outcome: recompute with the registered rule + human overrides (re-using repo functions for the rule)."""
    from injection_defense.evaluation.disruption import classify, load_criteria, load_overrides
    from injection_defense.evaluation.registry import load_all_cases
    from injection_defense.evaluation.store import load_outcomes

    criteria = load_criteria(ROOT / "data/task_disruption_carriers.json")
    cases = load_all_cases(ROOT / "data")
    overrides = load_overrides(ARCHIVE[name] / "human_review_decisions.csv")
    outs = [o for o in load_outcomes(run["folder"]) if o.is_attack]
    return {(c.outcome.experiment, c.outcome.trial, c.outcome.case_id): c for c in (classify(o, cases[o.case_id], criteria, overrides) for o in outs)}


def metrics_for(run: dict, disruption: dict) -> dict:
    raw, labels = run["raw"], run["labels"]
    out: dict = {}
    for e in CONFIGS:
        rows = [o for o in raw if o["experiment"] == e]
        att = [o for o in rows if o["is_attack"]]
        ben = [o for o in rows if not o["is_attack"]]
        eff = [effective(o, labels) for o in att]
        known = [x for x in eff if x is not None]
        judged_a = [o for o in att if o["flagged"] is not None]
        judged_b = [o for o in ben if o["flagged"] is not None]
        cats = Counter(disruption[(e, o["trial"], o["case_id"])].category for o in att)
        decided = sum(v for c, v in cats.items() if c != "unknown")
        lat = sorted(o["latency_ms"] for o in rows if o["status"] != "error")
        out[e] = {
            "asr": (sum(known), len(known)), "asr_unresolved": len(att) - len(known),
            "asr_bounds": (sum(known) / len(att), (sum(known) + len(att) - len(known)) / len(att)),
            "unresolved_breakdown": {"model_error": sum(1 for o in att if o["status"] == "error"),
                                     "unsure_or_review": sum(1 for o, x in zip(att, eff) if x is None and o["status"] != "error")},
            "detect": (sum(1 for o in judged_a if o["flagged"]), len(judged_a)),
            "fpr": (sum(1 for o in judged_b if o["flagged"]), len(judged_b)),
            "fpr_security": (sum(1 for o in judged_b if o["flagged"] and o["case_id"] in SECURITY_BENIGN), sum(1 for o in judged_b if o["case_id"] in SECURITY_BENIGN)),
            "fpr_ordinary": (sum(1 for o in judged_b if o["flagged"] and o["case_id"] not in SECURITY_BENIGN), sum(1 for o in judged_b if o["case_id"] not in SECURITY_BENIGN)),
            "benign_blocked": (sum(1 for o in ben if o["status"] == "blocked"), len([o for o in ben if o["status"] != "error"])),
            "benign_completion": (sum(1 for o in ben if o["task_completed"]), len([o for o in ben if o["task_completed"] is not None])),
            "disrupted": (cats["disrupted"], cats["disrupted"] + cats["usable"]), "usable": (cats["usable"], decided),
            "categories": dict(cats), "blocked_attacks": sum(1 for o in att if o["status"] == "blocked"),
            "latency_mean_ms": sum(lat) / len(lat), "latency_median_ms": lat[len(lat) // 2],
            "calls": sum(o["model_calls"] for o in rows if o["status"] != "error") / len([o for o in rows if o["status"] != "error"]),
            "model_failures": sum(1 for o in rows if o["status"] == "error"), "detector_failures": sum(o["detector_failures"] or 0 for o in rows),
        }
    return out


SECURITY_BENIGN: set[str] = set()


def init_security_ids() -> None:
    """Benign cases built from the five security-themed documents (the hard negatives)."""
    for line in (ROOT / "data/independent/benign.jsonl").read_text().splitlines():
        case = json.loads(line)
        if "security-themed" in str(case.get("notes", "")):
            SECURITY_BENIGN.add(case["case_id"])


def attack_means(run: dict, config: str) -> dict:
    per: dict = defaultdict(list)
    for o in run["raw"]:
        if o["is_attack"] and o["experiment"] == config:
            x = effective(o, run["labels"])
            if x is not None:
                per[o["case_id"]].append(1.0 if x else 0.0)
    return {k: sum(v) / len(v) for k, v in per.items()}


def obs_map(run: dict, config: str) -> dict:
    return {(o["case_id"], o["trial"]): effective(o, run["labels"]) for o in run["raw"] if o["is_attack"] and o["experiment"] == config}


def family_table(run: dict, disruption: dict) -> dict:
    t: dict = {}
    for e in CONFIGS:
        fams = defaultdict(lambda: {"k": 0, "n": 0, "unres": 0, "usable": 0, "dec": 0, "disrupted": 0, "detect": 0, "judged": 0, "attacks": set()})
        for o in run["raw"]:
            if o["is_attack"] and o["experiment"] == e:
                f = fams[o["attack_family"].replace("bipia_", "")]
                f["attacks"].add(o["case_id"])
                x = effective(o, run["labels"])
                if x is None:
                    f["unres"] += 1
                else:
                    f["n"] += 1
                    f["k"] += int(x)
                c = disruption[(e, o["trial"], o["case_id"])].category
                if c != "unknown":
                    f["dec"] += 1
                    f["usable"] += c == "usable"
                f["disrupted"] += c == "disrupted"
                if o["flagged"] is not None:
                    f["judged"] += 1
                    f["detect"] += int(o["flagged"])
        t[e] = fams
    return t


def compare_archive(name: str, m: dict) -> list[str]:
    """Differences between the recomputed metrics and the archived summary/task_disruption CSVs."""
    issues: list[str] = []
    for r in csv.DictReader((ARCHIVE[name] / "summary.csv").open(encoding="utf-8")):
        e, x = r["experiment"], m[r["experiment"]]
        for key, fld in (("ASR", "asr"), ("detection_rate", "detect"), ("FPR", "fpr")):
            mm = re.match(r"([\d.]+)% \((\d+)/(\d+)\)", r[key])
            if mm and (int(mm.group(2)), int(mm.group(3))) != x[fld]:
                issues.append(f"{name} {e} {key}: archive {mm.group(2)}/{mm.group(3)} vs recomputed {x[fld]}")
        if int(r["ASR_unknown"]) != x["asr_unresolved"]:
            issues.append(f"{name} {e} unresolved: archive {r['ASR_unknown']} vs recomputed {x['asr_unresolved']}")
    for r in csv.DictReader((ARCHIVE[name] / "task_disruption.csv").open(encoding="utf-8")):
        e, x = r["experiment"], m[r["experiment"]]
        mm = re.match(r"([\d.]+)% \((\d+)/(\d+)\)", r["task_disruption"])
        if (int(mm.group(2)), int(mm.group(3))) != x["disrupted"]:
            issues.append(f"{name} {e} disruption: archive {mm.group(2)}/{mm.group(3)} vs recomputed {x['disrupted']}")
        mm = re.match(r"([\d.]+)% \((\d+)/(\d+)\)", r["usable_on_attack"])
        if (int(mm.group(2)), int(mm.group(3))) != x["usable"]:
            issues.append(f"{name} {e} usable: archive {mm.group(2)}/{mm.group(3)} vs recomputed {x['usable']}")
    return issues


def report_check(metrics: dict) -> list[str]:
    """Every archived-table value must appear in section 10.1 of the report."""
    text = (ROOT / "docs/FINAL_REPORT.md").read_text(encoding="utf-8")
    sec = text[text.index("### 10.1"):text.index("## 11.")]
    missing = []
    for name in RUNS:
        for fname, keys in (("summary.csv", ("ASR", "detection_rate", "FPR")), ("task_disruption.csv", ("task_disruption", "usable_on_attack"))):
            for r in csv.DictReader((ARCHIVE[name] / fname).open(encoding="utf-8")):
                for k in keys:
                    mm = re.match(r"[\d.]+% \(\d+/\d+\)", r[k])
                    if mm and mm.group(0) not in sec:
                        missing.append(f"{name} {r['experiment']} {k}: {mm.group(0)}")
    return missing


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--results-dir", default=str(ROOT / "results"))
    parser.add_argument("--write", action="store_true", help="write docs/results/independent_audit/ (tables, JSON, charts)")
    parser.add_argument("--resamples", type=int, default=10000)
    args = parser.parse_args()
    results_dir = Path(args.results_dir)
    init_security_ids()
    runs = {n: load_run(n, results_dir) for n in RUNS}

    print("=== 1. verification checks")
    checks = run_checks(runs)
    for name, ok, detail in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))

    disr = {n: load_disruption(n, runs[n]) for n in RUNS}
    metrics = {n: metrics_for(runs[n], disr[n]) for n in RUNS}
    print("\n=== 2. recomputed metrics vs archived CSVs / report tables")
    issues = [i for n in RUNS for i in compare_archive(n, metrics[n])]
    missing = report_check(metrics)
    print("archive discrepancies:", issues or "none")
    print("report 10.1 values missing from the report:", missing or "none")

    print("\n=== 3. metrics (numerator/denominator [95% Wilson interval, independence assumed]; unresolved counted separately)")
    for n in RUNS:
        print(f"--- {n}")
        for e in CONFIGS:
            m = metrics[n][e]
            print(f"{e}: ASR {pct(*m['asr'])} unres {m['asr_unresolved']} {m['unresolved_breakdown']} | detect {pct(*m['detect'])} | FPR {pct(*m['fpr'])} "
                  f"(security {m['fpr_security'][0]}/{m['fpr_security'][1]}, ordinary {m['fpr_ordinary'][0]}/{m['fpr_ordinary'][1]}) | benign done {pct(*m['benign_completion'])} | "
                  f"disruption {pct(*m['disrupted'])} | usable {pct(*m['usable'])} | blocked attacks {m['blocked_attacks']} | {m['latency_mean_ms']:.0f} ms, {m['calls']:.2f} calls | fail m/d {m['model_failures']}/{m['detector_failures']}")

    print("\n=== 4. natural resistance vs defense (observation-level pairing of E0 with each configuration, same case and trial)")
    trans = {}
    for n in RUNS:
        e0 = obs_map(runs[n], "E0")
        for e in CONFIGS[1:]:
            trans[(n, e)] = transitions(e0, obs_map(runs[n], e))
            t = trans[(n, e)]
            print(f"{n} {e}: E0 fail->fail {t['fail->fail']} (resisted anyway) | E0 success->fail {t['success->fail']} (prevented) | E0 fail->success {t['fail->success']} (induced) | success->success {t['success->success']} | unresolved pairs {t['unresolved']}")

    print("\n=== 5. paired cluster bootstrap over the 75 attacks (exploratory; resamples whole attacks; 95% percentile interval)")
    boot: dict = {}
    for n in RUNS:
        for a, b in (("E2", "E0"), ("E4", "E0"), ("E5", "E0"), ("E4", "E2"), ("E5", "E2"), ("E3", "E0"), ("E1", "E0")):
            boot[(n, a, b)] = paired_bootstrap(attack_means(runs[n], a), attack_means(runs[n], b), resamples=args.resamples)
            r = boot[(n, a, b)]
            print(f"{n} {a} minus {b}: {100 * r['diff']:+.1f} pts [{100 * r['lo']:+.1f}, {100 * r['hi']:+.1f}] over {r['n']} attacks")
    for e in CONFIGS:
        r = paired_bootstrap(attack_means(runs["8B"], e), attack_means(runs["1B"], e), resamples=args.resamples)
        boot[("8B-1B", e, "")] = r
        print(f"8B minus 1B, {e}: {100 * r['diff']:+.1f} pts [{100 * r['lo']:+.1f}, {100 * r['hi']:+.1f}] over {r['n']} attacks")

    print("\n=== 6. attack-level rates, exact paired tests and host-document clustering (added 2026-10-29; exploratory, not pre-registered)")
    extra = extra_statistics(runs, resamples=args.resamples)
    for n in RUNS:
        for e in CONFIGS:
            r = extra["attack_level"][n][e]
            print(f"{n} {e}: attack-level mean {100 * r['mean_rate']:.1f}% [{100 * r['lo']:.0f}-{100 * r['hi']:.0f}] over {r['attacks']} attacks "
                  f"(succeeded in any trial {r['any_trial']}, in every trial {r['all_trials']})")
    for key, r in extra["paired"].items():
        print(f"{key}: sign test {r['sign']['favours_defense']}-{r['sign']['favours_baseline']} (ties {r['sign']['ties']}) p={r['sign']['p']:.4f} | "
              f"McNemar any-trial {r['mcnemar_any']['favours_defense']}-{r['mcnemar_any']['favours_baseline']} p={r['mcnemar_any']['p']:.4f} | "
              f"diff {100 * r['diff']:+.1f} pts: attacks [{100 * r['boot_attacks']['lo']:+.1f}, {100 * r['boot_attacks']['hi']:+.1f}], "
              f"documents [{100 * r['boot_documents']['lo']:+.1f}, {100 * r['boot_documents']['hi']:+.1f}], "
              f"documents+attacks [{100 * r['boot_two_stage']['lo']:+.1f}, {100 * r['boot_two_stage']['hi']:+.1f}]")

    fam = {n: family_table(runs[n], disr[n]) for n in RUNS}
    if args.write:
        write_outputs(checks, metrics, trans, boot, fam, issues, missing, runs)
        write_extra(extra)
    return 0 if all(ok for _, ok, _ in checks) and not issues and not missing else 1


def host_documents() -> dict[str, str]:
    """Attack id -> id of the host (carrier) document it was inserted into, from the frozen case notes."""
    out = {}
    for line in (ROOT / "data/independent/attacks.jsonl").read_text(encoding="utf-8").splitlines():
        case = json.loads(line)
        m = re.search(r"carrier (\S+)", case.get("notes", ""))
        out[case["case_id"]] = m.group(1) if m else case["case_id"]
    return out


def extra_statistics(runs: dict, *, resamples: int) -> dict:
    """Trial-collapsed rates, exact sign / McNemar tests vs E0 and bootstraps clustered by host document."""
    hosts = host_documents()
    result: dict = {"attack_level": {}, "paired": {},
                    "note": ("exploratory, post hoc: no test was pre-registered; one non-blind reviewer; trials collapsed per attack "
                             "(temperature 0, near-duplicates); McNemar 'any' = attack succeeded in at least one resolved trial; "
                             "bootstrap seed 20261029; documents = resample the 20 host documents, documents+attacks = two-stage")}
    for n in RUNS:
        result["attack_level"][n] = {}
        for e in CONFIGS:
            r = attack_level_rate(attack_means(runs[n], e))
            lo, hi = r.wilson_95 or (None, None)
            result["attack_level"][n][e] = {"attacks": r.attacks, "mean_rate": r.mean_rate, "lo": lo, "hi": hi,
                                            "any_trial": r.any_trial, "all_trials": r.all_trials}
        base = attack_means(runs[n], "E0")
        for e in ("E2", "E4", "E5", "E1", "E3"):
            other = attack_means(runs[n], e)
            keys = sorted(k for k in other if k in base)
            sign = sign_test({k: other[k] for k in keys}, {k: base[k] for k in keys})
            mc = mcnemar_exact({k: other[k] > 0 for k in keys}, {k: base[k] > 0 for k in keys})
            by_doc: dict = defaultdict(list)
            for k in keys:
                by_doc[hosts.get(k, k)].append(other[k] - base[k])
            per_attack = {k: [other[k] - base[k]] for k in keys}
            result["paired"][f"{n} {e} vs E0"] = {
                "pairs": len(keys), "diff": sum(other[k] - base[k] for k in keys) / len(keys) if keys else None,
                "sign": {"favours_defense": sign.favours_first, "favours_baseline": sign.favours_second, "ties": sign.ties, "p": sign.p_value},
                "mcnemar_any": {"favours_defense": mc.favours_first, "favours_baseline": mc.favours_second, "ties": mc.ties, "p": mc.p_value},
                "boot_attacks": cluster_bootstrap(per_attack, two_stage=False, resamples=resamples),
                "boot_documents": cluster_bootstrap(by_doc, two_stage=False, resamples=resamples),
                "boot_two_stage": cluster_bootstrap(by_doc, two_stage=True, resamples=resamples),
            }
    return result


def write_extra(extra: dict) -> None:
    """New files only; the archived audit outputs written by write_outputs are not touched by this."""
    out = ROOT / "docs/results/independent_audit"
    (out / "paired_tests.json").write_text(json.dumps(extra, indent=1), encoding="utf-8")
    with (out / "attack_level.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["model", "config", "attacks", "mean_rate", "wilson_lo", "wilson_hi", "any_trial", "all_trials"])
        for n, rows in extra["attack_level"].items():
            for e, r in rows.items():
                w.writerow([n, e, r["attacks"], round(r["mean_rate"], 4), round(r["lo"], 4), round(r["hi"], 4), r["any_trial"], r["all_trials"]])
    print(f"wrote {out.relative_to(ROOT)}/paired_tests.json and attack_level.csv")


def write_outputs(checks, metrics, trans, boot, fam, issues, missing, runs) -> None:
    out = ROOT / "docs/results/independent_audit"
    (out / "figures").mkdir(parents=True, exist_ok=True)
    (out / "checks.txt").write_text("\n".join(f"[{'PASS' if ok else 'FAIL'}] {n}" + (f"  ({d})" if d else "") for n, ok, d in checks)
                                    + f"\n\narchive discrepancies: {issues or 'none'}\nreport values missing: {missing or 'none'}\n", encoding="utf-8")
    with (out / "comparison.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["model", "config", "asr_k", "asr_n", "asr_unresolved", "detect_k", "detect_n", "fpr_k", "fpr_n", "fpr_security_k", "fpr_security_n",
                    "benign_completion_k", "benign_completion_n", "disrupted_k", "disrupted_n", "usable_k", "usable_n", "blocked_attacks",
                    "latency_mean_ms", "latency_median_ms", "calls_per_request", "model_failures", "detector_failures"])
        for n in RUNS:
            for e in CONFIGS:
                m = metrics[n][e]
                w.writerow([n, e, *m["asr"], m["asr_unresolved"], *m["detect"], *m["fpr"], *m["fpr_security"], *m["benign_completion"], *m["disrupted"], *m["usable"],
                            m["blocked_attacks"], round(m["latency_mean_ms"], 1), round(m["latency_median_ms"], 1), round(m["calls"], 3), m["model_failures"], m["detector_failures"]])
    with (out / "category.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["model", "config", "family", "attacks", "successes", "decided", "unresolved", "usable", "decided_for_usable", "disrupted", "detected", "judged_for_detection"])
        for n in RUNS:
            for e in CONFIGS:
                for f, v in sorted(fam[n][e].items()):
                    w.writerow([n, e, f, len(v["attacks"]), v["k"], v["n"], v["unres"], v["usable"], v["dec"], v["disrupted"], v["detect"], v["judged"]])
    payload = {"transitions_vs_E0": {f"{n}|{e}": dict(t) for (n, e), t in trans.items()},
               "bootstrap": {"|".join(k): v for k, v in boot.items()},
               "note": "bootstrap = paired cluster bootstrap over attacks, seed 20261027; exploratory, post hoc; one non-blind reviewer"}
    (out / "paired_analysis.json").write_text(json.dumps(payload, indent=1), encoding="utf-8")
    make_charts(out / "figures", metrics, fam, boot)
    print(f"\nwrote {out.relative_to(ROOT)}/ (checks.txt, comparison.csv, category.csv, paired_analysis.json, figures/)")


def make_charts(out: Path, metrics: dict, fam: dict, boot: dict) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    colors = {"1B": "#4C78A8", "8B": "#E45756"}

    def bars(ax, key, title, ylabel):
        w = 0.38
        for i, n in enumerate(RUNS):
            vals, lo, hi = [], [], []
            for e in CONFIGS:
                k, d = metrics[n][e][key]
                p = k / d
                a, b = wilson(k, d)
                vals.append(100 * p); lo.append(100 * (p - a)); hi.append(100 * (b - p))
            ax.bar([j + (i - 0.5) * w for j in range(len(CONFIGS))], vals, w, yerr=[lo, hi], color=colors[n], label=f"{n} ({'llama3.2:1b' if n == '1B' else 'llama3.1:8b'})", capsize=2)
        ax.set_xticks(range(len(CONFIGS))); ax.set_xticklabels(CONFIGS); ax.set_ylabel(ylabel); ax.set_title(title); ax.set_ylim(0, 100); ax.legend()
        ax.figure.text(0.99, 0.005, "PRELIMINARY: 100 cases, human-reviewed, one reviewer; interval assumes independent observations (overstates precision)", ha="right", va="bottom", fontsize=6.5, color="gray")

    fig, ax = plt.subplots(figsize=(8, 4.2)); bars(ax, "asr", "Attack success rate after human review (independent set)", "% of attack observations"); fig.tight_layout(rect=(0, 0.03, 1, 1)); fig.savefig(out / "asr_by_config.png", dpi=140); plt.close(fig)
    fig, ax = plt.subplots(figsize=(8, 4.2)); bars(ax, "usable", "Attacked documents that still received a usable summary", "% of known attack outcomes"); fig.tight_layout(rect=(0, 0.03, 1, 1)); fig.savefig(out / "usable_by_config.png", dpi=140); plt.close(fig)
    fams = sorted(fam["1B"]["E0"])
    fig, axes = plt.subplots(1, 2, figsize=(11, 5), sharey=True)
    for ax, n in zip(axes, RUNS):
        for j, (e, col) in enumerate((("E0", "#999999"), ("E2", colors[n]))):
            v = [100 * fam[n][e][f]["k"] / fam[n][e][f]["n"] if fam[n][e][f]["n"] else 0 for f in fams]
            ax.barh([i + (j - 0.5) * 0.38 for i in range(len(fams))], v, 0.38, color=col, label=e)
        ax.set_yticks(range(len(fams))); ax.set_yticklabels(fams, fontsize=8); ax.set_title(f"{n}: success rate by category (10 observations each)"); ax.set_xlabel("% successful (E0 vs E2)"); ax.legend()
    fig.tight_layout(); fig.savefig(out / "category_e0_vs_e2.png", dpi=140); plt.close(fig)


if __name__ == "__main__":
    raise SystemExit(main())
