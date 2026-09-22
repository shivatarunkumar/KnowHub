import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.db import get_engine
from app.core.logging import configure_logging
from app.core.middleware import RequestLogMiddleware

log = logging.getLogger("knowhub.startup")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    log.info(
        "KnowHub API starting: env=%s db=%s storage=%s ai=%s/%s",
        settings.app_env,
        settings.database_url.rsplit("@", 1)[-1],  # host/db only: no password in the log
        settings.gcs_bucket,
        settings.provider,
        settings.ai_model or "-",
    )
    yield
    log.info("KnowHub API stopping")
    await get_engine().dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings)
    app = FastAPI(title="KnowHub API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(RequestLogMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router)

    @app.get("/healthz", tags=["health"])
    async def liveness() -> dict:
        """Liveness: the process is up (no dependency checks)."""
        return {"status": "ok"}

    return app


app = create_app()
