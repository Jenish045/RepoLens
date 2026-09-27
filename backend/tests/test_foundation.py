from app.core.config import Settings
from app.database.base import Base
from app.main import app, health
from app import models  # noqa: F401 - verifies model registration for Alembic


def test_app_imports_and_health_works() -> None:
    assert any(getattr(route, "path", None) == "/health" for route in app.routes)
    assert health() == {"status": "healthy"}


def test_settings_load_without_external_credentials() -> None:
    settings = Settings(_env_file=None)
    assert settings.api_v1_prefix == "/api/v1"
    assert settings.database_url is None


def test_specification_models_are_registered() -> None:
    assert set(Base.metadata.tables) == {
        "users",
        "repositories",
        "repository_intelligence",
        "modules",
        "repository_chunks",
        "reports",
        "analysis_jobs",
    }


def test_alembic_configuration_is_valid() -> None:
    from alembic.config import Config

    config = Config("alembic.ini")
    assert config.get_main_option("script_location") == "migrations"
