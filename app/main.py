"""
AlbumsDashboard - lokale, eigenstaendige Checkliste zu "1001 Albums You Must
Hear Before You Die". Keine externe API, keine Cloud-Abhaengigkeit.

Start: uvicorn app.main:app --host 0.0.0.0 --port 8080
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import db
from .links import build_links

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.globals["build_links"] = build_links


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="AlbumsDashboard", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    status: str = "all",
    q: str = "",
    sort: str = "year_asc",
    page: int = 1,
    highlight: Optional[int] = None,
) -> HTMLResponse:
    page = max(page, 1)
    result = db.list_albums(status=status, query=q, sort=sort, page=page)
    highlighted = db.get_album(highlight) if highlight else None

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "stats": db.stats(),
            "result": result,
            "status": status,
            "q": q,
            "sort": sort,
            "highlighted": highlighted,
        },
    )


@app.get("/zufall")
def random_album():
    album = db.random_open_album()
    if album:
        return RedirectResponse(url=f"/?highlight={album['id']}", status_code=303)
    return RedirectResponse(url="/?status=open", status_code=303)


@app.post("/rate/{catalog_id}")
async def rate_album(
    catalog_id: int,
    request: Request,
    listened: Optional[str] = Form(None),
    rating: str = Form(""),
    note: str = Form(""),
    status: str = Form("all"),
    q: str = Form(""),
    sort: str = Form("year_asc"),
    page: int = Form(1),
):
    rating_value: Optional[int] = int(rating) if rating.isdigit() else None
    if rating_value is not None:
        rating_value = max(1, min(5, rating_value))

    db.set_progress(
        catalog_id,
        listened=bool(listened),
        rating=rating_value,
        note=note.strip(),
    )

    redirect = f"/?status={status}&q={q}&sort={sort}&page={page}"
    return RedirectResponse(url=redirect, status_code=303)
