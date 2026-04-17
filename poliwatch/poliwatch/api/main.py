"""FastAPI application entry point."""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from poliwatch import __version__
from poliwatch.api.routes import alerts as alerts_route
from poliwatch.api.routes import members as members_route
from poliwatch.api.routes import trades as trades_route
from poliwatch.config import get_settings
from poliwatch.ingestion._http import close_client

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@asynccontextmanager
async def _lifespan(app: FastAPI) -> "AsyncIterator[None]":  # noqa: D401
    del app
    logger.info("PoliWatch API starting ({})", __version__)
    try:
        yield
    finally:
        await close_client()


def create_app() -> FastAPI:
    app = FastAPI(
        title="PoliWatch API",
        version=__version__,
        description="Congressional stock-trade accountability API.",
        lifespan=_lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET"],
        allow_headers=["*"],
    )
    app.include_router(members_route.router)
    app.include_router(trades_route.router)
    app.include_router(alerts_route.router)

    @app.get("/", tags=["root"])
    def root() -> dict[str, str]:
        return {"name": "PoliWatch", "version": __version__, "docs": "/docs"}

    @app.get("/healthz", tags=["root"])
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()


def run() -> None:
    """Console-script entry point: ``poliwatch-api``."""
    import uvicorn

    settings = get_settings()
    logger.remove()
    logger.add(sys.stderr, level=settings.log_level, backtrace=False, diagnose=False)
    uvicorn.run(
        "poliwatch.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    run()
