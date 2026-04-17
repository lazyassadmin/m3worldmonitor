"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

from poliwatch.database import init_db
from poliwatch.api.routes import alerts, members, trades


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Initializing database…")
    await init_db()
    logger.info("PoliWatch API ready")
    yield
    logger.info("Shutting down PoliWatch API")


app = FastAPI(
    title="PoliWatch API",
    description="Congressional stock trade accountability dashboard API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(members.router, prefix="/members", tags=["members"])
app.include_router(trades.router, prefix="/trades", tags=["trades"])
app.include_router(alerts.router, prefix="/alerts", tags=["alerts"])


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
