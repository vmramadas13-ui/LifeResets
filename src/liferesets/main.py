"""FastAPI application entry point."""

from fastapi import FastAPI, HTTPException
from fastapi import status as http_status

from liferesets.database import database_is_ready
from liferesets.domain_data import router as domain_data_router
from liferesets.error_handlers import register_error_handlers
from liferesets.health import is_healthy
from liferesets.identity import router as identity_router
from liferesets.logging_config import configure_logging
from liferesets.settings import get_settings

settings = get_settings()
configure_logging(settings.log_level)
app = FastAPI(title=settings.app_name, version="0.1.0")
register_error_handlers(app)
app.include_router(identity_router)
app.include_router(domain_data_router)


@app.get("/health", tags=["system"])
def health_check() -> dict[str, str]:
    """Report whether the API process is alive."""
    return {"status": "ok" if is_healthy() else "unhealthy"}


@app.get("/ready", tags=["system"])
def readiness_check() -> dict[str, str]:
    """Report whether the API and its database dependency are ready."""
    if not database_is_ready():
        raise HTTPException(
            status_code=http_status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "database_unavailable",
                "message": "Database is unavailable.",
            },
        )
    return {"status": "ready"}
