"""KnowHub API on BigQuery (RUN_ON=BQ).

The same endpoints, cookies and JSON as the Postgres API in backend/app, so the web app
doesn't know or care which one it is talking to. Run it with `make api` (when RUN_ON=BQ)
or `make api-bq`.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.middleware import RequestLogMiddleware
from app_bq.api.v1.router import api_router
from app_bq.core.bq import get_db, schema

log = logging.getLogger("knowhub.startup")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    db = get_db()
    log.info(
        "KnowHub API starting on BigQuery: env=%s dataset=%s.%s (%s, %d tables) storage=%s ai=%s/%s",
        settings.app_env,
        db.project,
        db.dataset,
        db.location,
        len(schema()),
        settings.gcs_bucket,
        settings.provider,
        settings.ai_model or "-",
    )
    if settings.run_on != "BQ":
        log.warning(
            "RUN_ON=%s in .env, but this is the BigQuery API. `make api` starts the one RUN_ON names",
            settings.run_on,
        )
    yield
    log.info("KnowHub API stopping")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings)
    app = FastAPI(title="KnowHub API (BigQuery)", version="0.1.0", lifespan=lifespan)
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
        return {"status": "ok", "backend": "bigquery"}

    return app


app = create_app()
