"""Static-frontend checks. Interactive behavior was verified manually in a browser (see HANDOFF.md)."""

import re
from pathlib import Path

from fastapi.testclient import TestClient

from injection_defense.api import create_app

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
REQUIRED_IDS = ["doc", "file", "instruction", "model", "preset", "d-heuristic", "d-classifier", "d-structural",
                "d-output", "compare", "submit", "results", "ev-run", "runs", "run-detail"]


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
    js = (FRONTEND / "app.js").read_text()
    assert not re.search(r"innerHTML|outerHTML|insertAdjacentHTML|document\.write|eval\(", js)


def test_frontend_labels_mock_and_calls_only_known_endpoints():
    js = (FRONTEND / "app.js").read_text()
    assert "MOCK MODEL" in js and "blocked before model" in js
    called = set(re.findall(r'["`](/(?:config|extract|summarize|evaluate|results)[^"`$]*)', js))
    assert called >= {"/config", "/extract", "/summarize", "/evaluate", "/results"}
