"""Static web client routes."""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel

from src.config import settings
from src.services.release_info import app_info

router = APIRouter()
WEB_DIR = Path(__file__).resolve().parents[2] / "web"


class AppInfoResponse(BaseModel):
    """Public release metadata for UI clients."""

    version: str
    release_channel: str
    release_importance: str
    github_url: str
    changelog_url: str
    testing_notice_enabled: bool
    testing_notice_text: str
    changes: list[str]


@router.get("/", include_in_schema=False)
async def root_redirect() -> RedirectResponse:
    """Open the web client by default."""
    return RedirectResponse(url="/web")


@router.get("/web", include_in_schema=False)
async def web_index() -> FileResponse:
    """Return the web client shell."""
    return FileResponse(WEB_DIR / "index.html")


@router.get("/app/info", response_model=AppInfoResponse)
async def app_release_info() -> AppInfoResponse:
    """Return public app version and release metadata."""
    return AppInfoResponse(**app_info(settings))


@router.get("/web/assets/{asset_name}", include_in_schema=False)
async def web_asset(asset_name: str) -> FileResponse:
    """Return a static web asset."""
    allowed = {"app.js", "styles.css"}
    if asset_name not in allowed:
        raise HTTPException(status_code=404, detail="Asset not found")
    return FileResponse(WEB_DIR / asset_name)
