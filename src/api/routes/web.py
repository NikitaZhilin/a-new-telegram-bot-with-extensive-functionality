"""Static web client routes."""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, RedirectResponse


router = APIRouter()
WEB_DIR = Path(__file__).resolve().parents[2] / "web"


@router.get("/", include_in_schema=False)
async def root_redirect() -> RedirectResponse:
    """Open the web client by default."""
    return RedirectResponse(url="/web")


@router.get("/web", include_in_schema=False)
async def web_index() -> FileResponse:
    """Return the web client shell."""
    return FileResponse(WEB_DIR / "index.html")


@router.get("/web/assets/{asset_name}", include_in_schema=False)
async def web_asset(asset_name: str) -> FileResponse:
    """Return a static web asset."""
    allowed = {"app.js", "styles.css"}
    if asset_name not in allowed:
        raise HTTPException(status_code=404, detail="Asset not found")
    return FileResponse(WEB_DIR / asset_name)
