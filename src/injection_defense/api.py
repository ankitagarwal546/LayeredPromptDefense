"""FastAPI application. Run with: uvicorn injection_defense.api:create_app --factory"""

from __future__ import annotations

import logging
from collections.abc import Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from injection_defense import __version__
from injection_defense.config import Settings, get_preset
from injection_defense.defenses.base import Detector
from injection_defense.defenses.classifier import UnavailableClassifier, create_classifier
from injection_defense.llm.base import LLMClient, LLMError, ModelNotConfiguredError
from injection_defense.llm.mock import MockLLM
from injection_defense.llm.provider import create_real_llm_client
from injection_defense.pipeline import DefensePipeline
from injection_defense.schemas import SummarizeRequest, SummarizeResponse

logger = logging.getLogger("injection_defense")


def create_app(
    settings: Settings | None = None,
    *,
    llm_factory: Callable[[Settings], LLMClient] | None = None,
    classifier_factory: Callable[[Settings], Detector] | None = None,
) -> FastAPI:
    """Factories are injectable so tests never touch the network."""
    settings = settings or Settings()
    logging.basicConfig(level=settings.log_level.upper())
    make_real_llm = llm_factory or create_real_llm_client
    make_classifier = classifier_factory or create_classifier
    app = FastAPI(title="LLM Prompt-Injection Defense Evaluation", version=__version__)

    @app.exception_handler(ModelNotConfiguredError)
    async def _not_configured(_: Request, exc: ModelNotConfiguredError) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"error": "real_model_not_configured", "message": str(exc)},
        )

    @app.exception_handler(LLMError)
    async def _llm_error(_: Request, exc: LLMError) -> JSONResponse:
        return JSONResponse(
            status_code=502, content={"error": "llm_error", "message": "The model provider call failed."}
        )

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception) -> JSONResponse:
        logger.error("unhandled error type=%s", type(exc).__name__)  # no trace, no payload
        return JSONResponse(status_code=500, content={"error": "internal_error"})

    @app.get("/health")
    def health() -> dict:
        return {
            "status": "ok",
            "version": __version__,
            "default_model_mode": settings.default_model_mode,
            "real_model_configured": _real_model_configured(settings),
            "classifier_available": not isinstance(make_classifier(settings), UnavailableClassifier),
        }

    @app.post("/summarize", response_model=SummarizeResponse)
    def summarize(request: SummarizeRequest) -> SummarizeResponse:
        mode = request.model or settings.default_model_mode
        if mode == "mock":
            llm = MockLLM()
        else:
            # Raises ModelNotConfiguredError (-> 503) rather than falling back to the mock.
            llm = make_real_llm(settings)
        config = request.defenses or get_preset(settings.default_defense_preset)
        classifier = make_classifier(settings) if config.classifier else None
        pipeline = DefensePipeline(llm, config, classifier=classifier)
        return pipeline.run(request.document_text, request.instruction)

    return app


def _real_model_configured(settings: Settings) -> bool:
    try:
        create_real_llm_client(settings)
    except ModelNotConfiguredError:
        return False
    return True
