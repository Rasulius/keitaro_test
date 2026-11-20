from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.routes.campaigns import router as campaigns_router
from app.api.routes.editor import router as editor_router
from app.api.routes.offers import router as offers_router
from app.api.routes.settings import router as settings_router
from app.db.base import Base
from app.db.session import engine
from app.core.config import settings

# Ensure models are imported so tables are registered
from app import models  # noqa: F401

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Keitaro Wrapper", version="0.1.0")

# Create tables (simple bootstrap; Alembic migrations are also provided)
Base.metadata.create_all(bind=engine)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "default_prefix": settings.campaign_name_prefix,
            "default_google_url": settings.google_redirect_url,
            "default_domain_id": settings.default_domain_id,
            "default_group_id": settings.default_group_id,
            "default_traffic_source_id": settings.default_traffic_source_id,
            "default_offer_id": settings.default_offer_id,
        },
    )


@app.get("/editor", response_class=HTMLResponse)
def editor_page(request: Request):
    campaign_filter = (settings.campaign_name_prefix or "").rstrip("_") or "test"
    return templates.TemplateResponse(
        request,
        "editor.html",
        {
            "default_campaign_filter": campaign_filter,
            "default_active_only": True,
        },
    )


@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request):
    return templates.TemplateResponse(request, "admin.html", {})


app.include_router(campaigns_router)
app.include_router(editor_router)
app.include_router(offers_router)
app.include_router(settings_router)
