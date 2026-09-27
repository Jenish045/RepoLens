"""Structured JSON logging setup for the single-process application."""

import json
import logging
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "severity": record.levelname,
                "component": record.name,
                "message": record.getMessage(),
                **getattr(record, "context", {}),
            },
            ensure_ascii=False,
        )


class OAuthCallbackLogRedactor(logging.Filter):
    """Remove one-time OAuth codes and state values from HTTP access logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if record.name == "uvicorn.access" and isinstance(args, tuple) and len(args) >= 3:
            request_target = args[2]
            if isinstance(request_target, str) and request_target.startswith("/api/v1/auth/callback"):
                record.args = (*args[:2], request_target.split("?", 1)[0], *args[3:])
        return True


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").addFilter(OAuthCallbackLogRedactor())
