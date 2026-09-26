from fastapi import APIRouter

from app_bq.api.v1 import ai, auth, channels, engagement, health, teams, topics, videos

# The same routers, in the same order, as app/api/v1/router.py: the two APIs must
# expose identical paths (tests/test_contract.py checks this).
api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(topics.router)
api_router.include_router(teams.router)
api_router.include_router(videos.router)
api_router.include_router(channels.router)
api_router.include_router(engagement.router)
api_router.include_router(ai.router)
