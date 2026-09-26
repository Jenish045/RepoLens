"""FastAPI application entry point for the RepoLens foundation."""

from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging

configure_logging()
settings = get_settings()

app = FastAPI(
    title="RepoLens API",
    description="Project foundation API. Repository intelligence capabilities are not implemented yet.",
    version="0.1.0",
)
app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Process liveness endpoint; it does not imply database connectivity."""
    return {"status": "healthy"}
