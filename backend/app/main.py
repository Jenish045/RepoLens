"""FastAPI application entry point for the RepoLens foundation."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.errors import register_error_handlers

configure_logging()
settings = get_settings()

app = FastAPI(
    title="RepoLens API",
    description="RepoLens public repository overview and analysis API.",
    version="0.2.0",
)
app.add_middleware(CORSMiddleware, allow_origins=[settings.frontend_url], allow_credentials=False, allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["Authorization", "Content-Type"])
register_error_handlers(app)
app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Process liveness endpoint; it does not imply database connectivity."""
    return {"status": "healthy"}
