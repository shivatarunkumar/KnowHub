from fastapi import APIRouter

from app.api.v1 import ai, auth, channels, engagement, health, topics, videos

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(topics.router)
api_router.include_router(videos.router)
api_router.include_router(channels.router)
api_router.include_router(engagement.router)
api_router.include_router(ai.router)
