"""Versioned API router."""

from fastapi import APIRouter

from app.api.routes.auth import router as auth_router
from app.api.routes.repositories import router as repositories_router
from app.api.routes.repository_map import router as repository_map_router
from app.api.routes.semantic import router as semantic_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(repositories_router)
api_router.include_router(repository_map_router)
api_router.include_router(semantic_router)
