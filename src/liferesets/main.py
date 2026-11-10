"""FastAPI application entry point."""

from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi import status as http_status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from liferesets.agent import router as agent_router
from liferesets.core import answer_read_only
from liferesets.database import database_is_ready, get_db
from liferesets.domain_data import router as domain_data_router
from liferesets.error_handlers import register_error_handlers
from liferesets.health import is_healthy
from liferesets.identity import router as identity_router
from liferesets.insights import router as insights_router
from liferesets.logging_config import configure_logging
from liferesets.notifications import router as notifications_router
from liferesets.planning import router as planning_router
from liferesets.rpg import router as rpg_router
from liferesets.security import AuthenticatedWithCsrf
from liferesets.settings import get_settings

settings = get_settings()
configure_logging(settings.log_level)
app = FastAPI(title=settings.app_name, version="0.1.0")
WEB_DIR = Path(__file__).parent / "web"
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
register_error_handlers(app)
app.include_router(identity_router)
app.include_router(domain_data_router)
app.include_router(planning_router)
app.include_router(rpg_router)
app.include_router(insights_router)
app.include_router(notifications_router)
app.include_router(agent_router)


@app.get("/", include_in_schema=False)
def web_app() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@app.get("/manifest.webmanifest", include_in_schema=False)
def web_manifest() -> FileResponse:
    return FileResponse(
        WEB_DIR / "manifest.webmanifest", media_type="application/manifest+json"
    )


@app.get("/sw.js", include_in_schema=False)
def service_worker() -> FileResponse:
    return FileResponse(
        WEB_DIR / "sw.js",
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/"},
    )


class CoreQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=1000)


@app.post("/api/v1/core/respond", tags=["THE CORE"])
def core_respond(
    request: CoreQuestion,
    auth: AuthenticatedWithCsrf,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    """Return a bounded, read-only answer based only on this account's context."""
    return answer_read_only(db, auth.user.id, request.question)


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
