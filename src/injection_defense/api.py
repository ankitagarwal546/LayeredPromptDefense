"""FastAPI application. Run with: uvicorn injection_defense.api:create_app --factory --app-dir src"""

from __future__ import annotations

import csv
import dataclasses
import io
import logging
import threading
import uuid
from collections.abc import Callable
from typing import Literal
from urllib.parse import urlparse

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from injection_defense import __version__
from injection_defense.config import (
    MAX_DOCUMENT_CHARS, MAX_INSTRUCTION_CHARS, PRESETS, REPO_ROOT, Settings, get_preset,
)
from injection_defense.defenses.base import Detector
from injection_defense.defenses.classifier import UnavailableClassifier, create_classifier
from injection_defense.defenses.structural import VARIANTS
from injection_defense.documents import (
    MAX_UPLOAD_BYTES, SUPPORTED_EXTENSIONS, ExtractionError, extract_text,
)
from injection_defense.evaluation import store
from injection_defense.evaluation.execute import execute_run, resolve_configs
from injection_defense.evaluation.registry import CASE_SETS, build_case_set, estimate_model_calls
from injection_defense.evaluation.report import summary_table
from injection_defense.llm.base import LLMClient, LLMError, ModelNotConfiguredError
from injection_defense.llm.mock import MockLLM
from injection_defense.llm.provider import create_real_llm_client
from injection_defense.logging_config import configure_logging
from injection_defense.pipeline import DefensePipeline
from injection_defense.schemas import SummarizeRequest, SummarizeResponse

logger = logging.getLogger("injection_defense")
FRONTEND_DIR = REPO_ROOT / "frontend"
MAX_API_EVAL_CALLS = 3000  # larger experiments belong on the CLI


class EvaluateRequest(BaseModel):
    case_set: Literal["dev", "final", "independent"] = "dev"
    experiments: list[str] = Field(default_factory=lambda: ["E0", "E1", "E2", "E4"], min_length=1, max_length=len(PRESETS))
    repetitions: int = Field(default=1, ge=1, le=5)
    model: Literal["mock", "real"] = "mock"
    # A real-model run makes external calls: the caller must acknowledge the estimate.
    confirm_external_calls: bool = False
    # "final" and "independent" use frozen test files; acknowledge that this spends them.
    final_run_acknowledged: bool = False


class _Jobs:
    """In-memory evaluation jobs; one runs at a time. State is lost on restart (runs persist on disk)."""

    def __init__(self) -> None:
        self._jobs: dict[str, dict] = {}
        self._lock = threading.Lock()

    def start(self, work: Callable[[Callable[[int], None]], str], total: int) -> dict:
        with self._lock:
            if any(j["status"] in ("queued", "running") for j in self._jobs.values()):
                raise HTTPException(409, detail={"error": "evaluation_in_progress"})
            job = {"job_id": uuid.uuid4().hex[:12], "status": "running", "run_id": None, "done": 0, "total": total, "error": None}
            self._jobs[job["job_id"]] = job

        def target() -> None:
            try:
                job["run_id"] = work(lambda n: job.__setitem__("done", n))
                job["status"] = "completed"
            except Exception as exc:  # job failures are reported generically; details go to the log
                logger.error("evaluation job failed type=%s", type(exc).__name__)
                job["status"], job["error"] = "failed", "The evaluation failed; see server log."

        threading.Thread(target=target, daemon=True).start()
        return dict(job)

    def get(self, job_id: str) -> dict | None:
        job = self._jobs.get(job_id)
        return dict(job) if job else None


def create_app(
    settings: Settings | None = None,
    *,
    llm_factory: Callable[[Settings], LLMClient] | None = None,
    classifier_factory: Callable[[Settings], Detector] | None = None,
) -> FastAPI:
    """Factories are injectable so tests never touch the network."""
    settings = settings or Settings()
    configure_logging(settings.log_level)
    make_real_llm = llm_factory or create_real_llm_client
    make_classifier = classifier_factory or create_classifier
    app = FastAPI(title="LLM Prompt-Injection Defense Evaluation", version=__version__)
    jobs = _Jobs()

    @app.exception_handler(ModelNotConfiguredError)
    async def _not_configured(_: Request, exc: ModelNotConfiguredError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"error": "real_model_not_configured", "message": str(exc)})

    @app.exception_handler(LLMError)
    async def _llm_error(_: Request, exc: LLMError) -> JSONResponse:
        return JSONResponse(status_code=502, content={"error": "llm_error", "message": "The model provider call failed."})

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception) -> JSONResponse:
        logger.error("unhandled error type=%s", type(exc).__name__)  # no trace, no payload
        return JSONResponse(status_code=500, content={"error": "internal_error"})

    def real_model_info() -> dict | None:
        try:
            llm = create_real_llm_client(settings)
        except ModelNotConfiguredError:
            return None
        host = urlparse(settings.llm_base_url).hostname or ""
        local = llm.provider == "openai_compatible" and host in ("localhost", "127.0.0.1", "::1")
        return {"provider": llm.provider, "name": llm.model_name, "is_local": local}

    @app.get("/health")
    def health() -> dict:
        return {
            "status": "ok",
            "version": __version__,
            "default_model_mode": settings.default_model_mode,
            "real_model_configured": real_model_info() is not None,
            "classifier_available": not isinstance(make_classifier(settings), UnavailableClassifier),
        }

    @app.get("/config")
    def config() -> dict:
        """Non-sensitive configuration for the UI. Never includes keys or URLs."""
        return {
            "version": __version__,
            "default_model_mode": settings.default_model_mode,
            "default_defense_preset": settings.default_defense_preset,
            "real_model": real_model_info(),
            "classifier_available": not isinstance(make_classifier(settings), UnavailableClassifier),
            "presets": {name: cfg.model_dump() for name, cfg in PRESETS.items()},
            "policies": {
                "heuristic": ["block", "sanitize", "flag_only"],
                "classifier": ["block", "flag_only"],
                "output_validation": ["withhold", "flag_only"],
            },
            "enforcement_decisions": {"allow": "nothing flagged", "warn": "processed, but flagged or a layer could not run", "block": "no summary delivered"},
            "structural_variants": sorted(VARIANTS),
            "limits": {
                "max_document_chars": MAX_DOCUMENT_CHARS,
                "max_instruction_chars": MAX_INSTRUCTION_CHARS,
                "max_upload_bytes": MAX_UPLOAD_BYTES,
                "supported_extensions": list(SUPPORTED_EXTENSIONS),
            },
            "case_sets": list(CASE_SETS),
        }

    @app.post("/extract")
    async def extract(file: UploadFile = File(...)) -> dict:
        data = await file.read(MAX_UPLOAD_BYTES + 1)
        try:
            result = extract_text(file.filename or "", data)
        except ExtractionError as exc:
            raise HTTPException(422, detail={"error": "extraction_failed", "message": str(exc)}) from None
        return {"format": result.format, "chars": result.chars, "text": result.text, "warnings": result.warnings}

    @app.post("/summarize", response_model=SummarizeResponse)
    def summarize(request: SummarizeRequest) -> SummarizeResponse:
        mode = request.model or settings.default_model_mode
        # "real" raises ModelNotConfiguredError (-> 503) rather than falling back to the mock.
        llm = MockLLM() if mode == "mock" else make_real_llm(settings)
        config = request.defenses or get_preset(settings.default_defense_preset)
        classifier = make_classifier(settings) if config.classifier else None
        return DefensePipeline(llm, config, classifier=classifier).run(request.document_text, request.instruction)

    @app.post("/evaluate", status_code=202)
    def evaluate(request: EvaluateRequest) -> dict:
        if request.case_set in ("final", "independent") and not request.final_run_acknowledged:
            raise HTTPException(422, detail={"error": "final_run_not_acknowledged",
                                             "message": "This case set uses frozen test files; set final_run_acknowledged=true to proceed."})
        try:
            configs = resolve_configs(request.experiments)
            case_set = build_case_set(request.case_set, settings.data_dir)
        except ValueError as exc:
            raise HTTPException(422, detail={"error": "invalid_evaluation", "message": str(exc)}) from None
        estimate = estimate_model_calls(configs, len(case_set.cases), request.repetitions)
        if estimate > MAX_API_EVAL_CALLS:
            raise HTTPException(422, detail={"error": "too_large", "estimated_model_calls": estimate,
                                             "message": f"Over {MAX_API_EVAL_CALLS} calls; use scripts/run_experiments.py."})
        llm = MockLLM() if request.model == "mock" else make_real_llm(settings)
        if not llm.is_mock and not request.confirm_external_calls:
            raise HTTPException(409, detail={"error": "confirmation_required", "estimated_model_calls": estimate,
                                             "message": "This run calls a real model. Resend with confirm_external_calls=true to proceed."})
        classifier = make_classifier(settings)
        total = len(case_set.cases) * request.repetitions * len(configs)

        def work(progress: Callable[[int], None]) -> str:
            folder = execute_run(case_set=case_set, experiment_names=request.experiments, llm=llm, classifier=classifier,
                                 repetitions=request.repetitions, results_dir=settings.results_dir, progress=progress)
            return folder.name

        job = jobs.start(work, total)
        return {**job, "estimated_model_calls": estimate, "model_is_mock": llm.is_mock}

    @app.get("/evaluate/{job_id}")
    def evaluation_status(job_id: str) -> dict:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(404, detail={"error": "unknown_job"})
        return job

    @app.get("/results")
    def results() -> dict:
        return {"runs": store.list_runs(settings.results_dir)}

    def load_run(run_id: str):
        if not store.valid_run_id(run_id) or not (settings.results_dir / run_id / "metadata.json").exists():
            raise HTTPException(404, detail={"error": "unknown_run"})
        folder = settings.results_dir / run_id
        import json

        return json.loads((folder / "metadata.json").read_text(encoding="utf-8")), store.load_outcomes(folder)

    def table_for(meta: dict, outcomes):
        grouped: dict[str, list] = {}
        for o in outcomes:
            grouped.setdefault(o.experiment, []).append(o)
        return summary_table(grouped, set(meta.get("heldout_families", [])))

    @app.get("/results/{run_id}")
    def result_detail(run_id: str) -> dict:
        meta, outcomes = load_run(run_id)
        return {
            "metadata": meta,
            "summary": table_for(meta, outcomes).to_dict(orient="records"),
            "pending_manual_review": len(store.pending_review(outcomes)),
        }

    @app.get("/results/{run_id}/table.csv", response_class=PlainTextResponse)
    def result_table_csv(run_id: str) -> PlainTextResponse:
        meta, outcomes = load_run(run_id)
        return PlainTextResponse(table_for(meta, outcomes).to_csv(index=False), media_type="text/csv")

    @app.get("/results/{run_id}/outcomes.csv", response_class=PlainTextResponse)
    def result_outcomes_csv(run_id: str) -> PlainTextResponse:
        """Per-case outcomes without model output text."""
        _, outcomes = load_run(run_id)
        rows = [{k: v for k, v in dataclasses.asdict(o).items() if k != "output_text"} for o in outcomes]
        buffer = io.StringIO()
        if rows:
            writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        return PlainTextResponse(buffer.getvalue(), media_type="text/csv")

    if FRONTEND_DIR.exists():
        app.mount("/app", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

        @app.get("/", include_in_schema=False)
        def root() -> RedirectResponse:
            return RedirectResponse("/app/")

    return app
