"""Static-frontend checks. Interactive behavior was verified manually in a browser (see HANDOFF.md)."""

import re
from pathlib import Path

from fastapi.testclient import TestClient

from injection_defense.api import create_app

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
REQUIRED_IDS = ["doc", "file", "instruction", "model", "preset", "d-heuristic", "d-classifier", "d-structural",
                "d-output", "compare", "submit", "results", "ev-run", "runs", "run-detail",
                "pipeline", "examples", "f-gauges", "f-configs", "f-transitions", "f-categories"]


def test_frontend_is_served_and_root_redirects(settings):
    c = TestClient(create_app(settings))
    assert c.get("/", follow_redirects=False).status_code in (302, 307)
    page = c.get("/app/")
    assert page.status_code == 200 and "Prompt-Injection Defense Lab" in page.text
    assert c.get("/app/app.js").status_code == 200 and c.get("/app/styles.css").status_code == 200


def test_frontend_has_all_required_controls():
    html = (FRONTEND / "index.html").read_text()
    for element_id in REQUIRED_IDS:
        assert f'id="{element_id}"' in html, element_id


def test_frontend_never_inserts_untrusted_text_as_html():
    js = re.sub(r"//[^\n]*", "", (FRONTEND / "app.js").read_text())  # ignore comments
    assert not re.search(r"innerHTML|outerHTML|insertAdjacentHTML|document\.write|eval\(", js)


def test_frontend_labels_mock_and_calls_only_known_endpoints():
    js = (FRONTEND / "app.js").read_text()
    assert "MOCK MODEL" in js and "blocked before model" in js
    called = set(re.findall(r'["`](/(?:config|extract|summarize|evaluate|results|findings)[^"`$]*)', js))
    assert called >= {"/config", "/extract", "/summarize", "/evaluate", "/results", "/findings"}


def test_demo_examples_are_served_and_marked_demo_only(settings):
    data = TestClient(create_app(settings)).get("/app/demo_examples.json").json()
    assert "NOT part of any evaluation set" in data["_note"]
    assert {e["kind"] for e in data["examples"]} == {"attack", "benign"}
    for e in data["examples"]:
        assert e["text"] and e["what_to_look_for"] and len(e["suggested_compare"]) == 2


PREVIOUS = FRONTEND.parent / "frontend_backup_previous"


def test_previous_ui_is_served_read_only_and_matches_the_tagged_snapshot(settings):
    import shutil
    import subprocess

    c = TestClient(create_app(settings))
    page = c.get("/app-previous/")
    assert page.status_code == 200 and "Prompt-Injection Defense Lab" in page.text
    assert c.get("/app-previous/app.js").status_code == 200
    if shutil.which("git") is None:
        return
    for name in ("index.html", "app.js", "styles.css", "demo_examples.json"):
        tagged = subprocess.run(["git", "show", f"frontend-classic-2026-10-29:frontend/{name}"], cwd=FRONTEND.parent,
                                capture_output=True, check=False)
        if tagged.returncode != 0:  # tag not present (e.g. a fresh clone without tags)
            return
        assert (PREVIOUS / name).read_bytes() == tagged.stdout, name


def test_switch_frontend_round_trip(tmp_path):
    import shutil
    import subprocess
    import sys

    (tmp_path / "scripts").mkdir()
    shutil.copy(FRONTEND.parent / "scripts" / "switch_frontend.py", tmp_path / "scripts")
    shutil.copytree(PREVIOUS, tmp_path / "frontend_backup_previous")
    shutil.copytree(FRONTEND, tmp_path / "frontend")
    (tmp_path / "frontend" / "marker.txt").write_text("new ui")
    run = lambda *a: subprocess.run([sys.executable, str(tmp_path / "scripts" / "switch_frontend.py"), *a],
                                    capture_output=True, text=True, timeout=60)
    assert run("--use", "previous").returncode == 0
    assert not (tmp_path / "frontend" / "marker.txt").exists()
    assert (tmp_path / "frontend" / "app.js").read_bytes() == (PREVIOUS / "app.js").read_bytes()
    assert "previous" in run("--status").stdout
    assert run("--use", "new").returncode == 0
    assert (tmp_path / "frontend" / "marker.txt").read_text() == "new ui"
    assert (tmp_path / "frontend_backup_previous" / "app.js").read_bytes() == (PREVIOUS / "app.js").read_bytes()
