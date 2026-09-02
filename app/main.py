"""
AlbumsDashboard - lokale, eigenstaendige Checkliste zu "1001 Albums You Must
Hear Before You Die". Keine externe API, keine Cloud-Abhängigkeit.

Start: uvicorn app.main:app --host 0.0.0.0 --port 8080
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlencode

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import db
from .links import build_links, service_label

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.globals["build_links"] = build_links
templates.env.globals["service_label"] = service_label

VALID_STATUS = {"all", "open", "listened"}
VALID_SORTS_UI = {"year_asc", "year_desc", "artist_asc", "album_asc", "rating_desc"}
# "recent": zuletzt gehört zuerst - nur für die Gehört-Rubrik sinnvoll.
GEHOERT_SORTS = {"year_asc", "year_desc", "artist_asc", "album_asc", "rating_desc", "recent"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="AlbumsDashboard", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


def _index_params(
    status: str, q: str, sort: str, page: int, highlight: Optional[int] = None
) -> str:
    """Query-Parameter für Redirects, korrekt encodiert (&, # etc. in q sind sicher)."""
    params: dict[str, Any] = {"status": status, "q": q, "sort": sort, "page": page}
    if highlight is not None:
        params["highlight"] = highlight
    return urlencode(params)


def _safe_rating(rating: str) -> Optional[int]:
    """Robustes Rating-Parsing: '2' -> 2, '²'/'3.5'/'Muell'/'9' -> None (kein 500er)."""
    try:
        value = int(rating.strip())
    except (ValueError, AttributeError):
        return None
    return value if 1 <= value <= 5 else None


def _page_window(current: int, pages: int) -> list[Optional[int]]:
    """
    Kompakte Seitenliste für die Pagination: erste/letzte Seiten plus ein
    Fenster um die aktuelle Seite; None steht für eine Auslassung ("...").
    """
    if pages <= 7:
        return list(range(1, pages + 1))
    keep = {1, 2, pages - 1, pages}
    keep.update(p for p in range(current - 1, current + 2) if 1 <= p <= pages)
    window: list[Optional[int]] = []
    prev = 0
    for p in sorted(keep):
        if p - prev > 1:
            window.append(None)
        window.append(p)
        prev = p
    return window


def _no_store(response: HTMLResponse) -> HTMLResponse:
    """Browser-Cache für dynamische Seiten abschalten (veraltete 'Gehört'-Stände)."""
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


# --- PWA: Manifest + Service Worker aus dem Root (noetiger SW-Scope) -----

SW_PATH = BASE_DIR / "static" / "sw.js"
MANIFEST_PATH = BASE_DIR / "static" / "manifest.json"

SW_HEADERS = {
    "Cache-Control": "no-cache",
    "Service-Worker-Allowed": "/",
}


@app.get("/sw.js")
def service_worker() -> FileResponse:
    return FileResponse(SW_PATH, media_type="application/javascript", headers=SW_HEADERS)


@app.get("/manifest.webmanifest")
def manifest() -> FileResponse:
    return FileResponse(MANIFEST_PATH, media_type="application/manifest+json")


@app.get("/", response_class=HTMLResponse)
def index(
    request: Request,
    status: str = "all",
    q: str = "",
    sort: str = "year_asc",
    page: int = 1,
    highlight: Optional[int] = None,
) -> HTMLResponse:
    if status not in VALID_STATUS:
        status = "all"
    if sort not in VALID_SORTS_UI:
        sort = "year_asc"
    page = max(page, 1)

    result = db.list_albums(status=status, query=q, sort=sort, page=page)

    # Seite jenseits des Maximums (z. B. nach Filterwechsel per Zurück-Button):
    # auf die letzte gültige Seite umleiten statt eine leere Liste zu zeigen.
    if result["total"] > 0 and page > result["pages"]:
        query = _index_params(status, q, sort, result["pages"], highlight)
        return RedirectResponse(url=f"/?{query}", status_code=303)

    highlighted = db.get_album(highlight) if highlight else None

    return _no_store(templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "stats": db.stats(),
            "result": result,
            "status": status,
            "q": q,
            "sort": sort,
            "highlighted": highlighted,
            "page_window": _page_window(result["page"], result["pages"]),
        },
    ))


@app.get("/gehoert", response_class=HTMLResponse)
def gehoert_page(
    request: Request,
    q: str = "",
    sort: str = "recent",
    page: int = 1,
) -> HTMLResponse:
    """Rubrik 'Gehörte Alben': Chronologie mit Bewertung, Notiz und Gehört-Datum."""
    if sort not in GEHOERT_SORTS:
        sort = "recent"
    page = max(page, 1)

    result = db.list_albums(status="listened", query=q, sort=sort, page=page)

    if result["total"] > 0 and page > result["pages"]:
        query = urlencode({"q": q, "sort": sort, "page": result["pages"]})
        return RedirectResponse(url=f"/gehoert?{query}", status_code=303)

    return _no_store(templates.TemplateResponse(
        "gehoert.html",
        {
            "request": request,
            "stats": db.stats(),
            "result": result,
            "q": q,
            "sort": sort,
            "page_window": _page_window(result["page"], result["pages"]),
        },
    ))


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
    rating_value = _safe_rating(rating)

    if not db.set_progress(
        catalog_id,
        listened=bool(listened),
        rating=rating_value,
        note=note.strip(),
    ):
        raise HTTPException(status_code=404, detail="Album nicht gefunden")

    if status not in VALID_STATUS:
        status = "all"
    if sort not in VALID_SORTS_UI:
        sort = "year_asc"

    # JS-Autosave: JSON-Antwort mit dem tatsaechlichen DB-Stand zurückgeben,
    # damit die UI verlässlich spiegelt, was gespeichert wurde.
    if request.headers.get("accept", "").startswith("application/json"):
        album = db.get_album(catalog_id)
        return JSONResponse(
            content={
                "ok": True,
                "id": catalog_id,
                "listened": bool(album["listened"]) if album else False,
                "rating": album["rating"] if album else None,
                "note": album["note"] if album else "",
                "listened_on": album["listened_on"] if album else None,
                "stats": db.stats(),
            },
            headers={"Cache-Control": "no-store"},
        )

    query = _index_params(status, q, sort, max(page, 1))
    # Anker => Browser scrollt nach dem Speichern direkt zur gespeicherten Karte.
    return RedirectResponse(url=f"/?{query}#album-{catalog_id}", status_code=303)
