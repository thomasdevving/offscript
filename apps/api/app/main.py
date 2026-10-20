"""PARALLEL API entry point (FastAPI)."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from .agents.runner import ChatClientProvider
from .api import multiverse_routes, routes, ws
from .config import Settings, get_settings
from .multiverse.service import MultiverseService
from .services.analysis_service import AnalysisService
from .services.hub import EventHub
from .services.metrics import configure_logging
from .services.store import Store

log = logging.getLogger("parallel")


@dataclass
class Services:
    settings: Settings
    store: Store
    hub: EventHub
    analyses: AnalysisService
    multiverse: MultiverseService
    ready: bool = False


def _configure_telemetry(settings: Settings) -> None:
    if not settings.applicationinsights_connection_string:
        return
    try:
        from agent_framework.observability import enable_instrumentation
        from azure.monitor.opentelemetry import configure_azure_monitor

        configure_azure_monitor(connection_string=settings.applicationinsights_connection_string,
                                logger_name="parallel")
        enable_instrumentation()
        log.info("Azure Monitor / OpenTelemetry enabled")
    except Exception as exc:  # telemetry must never break the app
        log.warning("Telemetry not enabled: %s", exc)


def create_app(settings: Settings | None = None, preload: list[str] | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        _configure_telemetry(settings)
        store = Store(settings.scenarios_dir, settings.data_dir)
        hub = EventHub()
        provider = ChatClientProvider(settings)
        services = Services(settings, store, hub, AnalysisService(settings, store, hub, provider),
                            MultiverseService(settings, store, hub, provider))
        app.state.services = services
        await asyncio.to_thread(store.load, preload)
        services.ready = True
        log.info("PARALLEL ready: %d matches, agent mode %s", len(store.matches), services.analyses.provider.mode)
        yield

    app = FastAPI(
        title="PARALLEL API",
        version="1.0.0",
        description="Multi-agent counterfactual football intelligence on synthetic matches. "
                    "All counterfactual numbers are model estimates.",
        lifespan=lifespan,
    )
    app.add_middleware(GZipMiddleware, minimum_size=2048)
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=False,
                       allow_methods=["GET", "POST"], allow_headers=["*"])
    app.include_router(routes.router)
    app.include_router(ws.router)
    app.include_router(multiverse_routes.router)
    app.include_router(multiverse_routes.ws_router)
    return app


app = create_app()
