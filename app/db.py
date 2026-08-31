"""
AlbumsDashboard - SQLite-Datenzugriff.

Vollstaendig lokal und unabhaengig: der Album-Katalog (Jahr, Titel,
Interpret) wird beim ersten Start einmalig aus der mitgelieferten Datei
app/data/1001_albums.tsv importiert. Es gibt keine Anbindung an einen
externen Dienst und keine Laufzeit-Netzwerkabhaengigkeit fuer die Katalogdaten.
Hoer-Status, Bewertung und Notiz sind rein lokale Nutzerdaten.
"""
from __future__ import annotations

import csv
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional

APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR.parent / "data" / "albumsdashboard.db"
CATALOG_TSV = APP_DIR / "data" / "1001_albums.tsv"

SCHEMA = """
CREATE TABLE IF NOT EXISTS catalog (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    year   INTEGER,
    album  TEXT NOT NULL,
    artist TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS progress (
    catalog_id INTEGER PRIMARY KEY REFERENCES catalog(id) ON DELETE CASCADE,
    listened   INTEGER DEFAULT 0,
    rating     INTEGER,       -- 1-5 Sterne, optional
    note       TEXT,
    listened_on TEXT,
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        already_seeded = conn.execute(
            "SELECT value FROM meta WHERE key = 'catalog_seeded'"
        ).fetchone()
        if not already_seeded:
            _seed_catalog(conn)
            conn.execute(
                "INSERT INTO meta (key, value) VALUES ('catalog_seeded', '1')"
            )


def _seed_catalog(conn: sqlite3.Connection) -> None:
    if not CATALOG_TSV.exists():
        raise RuntimeError(f"Katalog-Datei fehlt: {CATALOG_TSV}")
    with CATALOG_TSV.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        rows = [
            (int(r["year"]) if r.get("year") else None, r["album"].strip(), r["artist"].strip())
            for r in reader
            if r.get("album") and r.get("artist")
        ]
    conn.executemany(
        "INSERT INTO catalog (year, album, artist) VALUES (?, ?, ?)", rows
    )


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# --- Abfragen ---------------------------------------------------------

def stats() -> dict[str, int]:
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) c FROM catalog").fetchone()["c"]
        listened = conn.execute(
            "SELECT COUNT(*) c FROM progress WHERE listened = 1"
        ).fetchone()["c"]
        return {"total": total, "listened": listened, "open": total - listened}


VALID_SORTS = {
    "year_asc": "c.year ASC, c.artist ASC",
    "year_desc": "c.year DESC, c.artist ASC",
    "artist_asc": "c.artist ASC, c.year ASC",
    "album_asc": "c.album ASC",
}


def list_albums(
    *,
    status: str = "all",       # all | listened | open
    query: str = "",
    sort: str = "year_asc",
    page: int = 1,
    page_size: int = 40,
) -> dict[str, Any]:
    order_by = VALID_SORTS.get(sort, VALID_SORTS["year_asc"])
    where = ["1=1"]
    params: list[Any] = []

    if status == "listened":
        where.append("COALESCE(p.listened, 0) = 1")
    elif status == "open":
        where.append("COALESCE(p.listened, 0) = 0")

    if query:
        where.append("(c.album LIKE ? OR c.artist LIKE ?)")
        like = f"%{query}%"
        params.extend([like, like])

    where_sql = " AND ".join(where)

    with get_conn() as conn:
        total = conn.execute(
            f"""
            SELECT COUNT(*) c FROM catalog c
            LEFT JOIN progress p ON p.catalog_id = c.id
            WHERE {where_sql}
            """,
            params,
        ).fetchone()["c"]

        offset = max(page - 1, 0) * page_size
        rows = conn.execute(
            f"""
            SELECT c.id, c.year, c.album, c.artist,
                   COALESCE(p.listened, 0) AS listened,
                   p.rating, p.note, p.listened_on
            FROM catalog c
            LEFT JOIN progress p ON p.catalog_id = c.id
            WHERE {where_sql}
            ORDER BY {order_by}
            LIMIT ? OFFSET ?
            """,
            [*params, page_size, offset],
        ).fetchall()

        albums = [dict(r) for r in rows]

    return {
        "albums": albums,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, (total + page_size - 1) // page_size),
    }


def get_album(catalog_id: int) -> Optional[dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT c.id, c.year, c.album, c.artist,
                   COALESCE(p.listened, 0) AS listened,
                   p.rating, p.note, p.listened_on
            FROM catalog c
            LEFT JOIN progress p ON p.catalog_id = c.id
            WHERE c.id = ?
            """,
            (catalog_id,),
        ).fetchone()
        return dict(row) if row else None


def random_open_album() -> Optional[dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT c.id, c.year, c.album, c.artist
            FROM catalog c
            LEFT JOIN progress p ON p.catalog_id = c.id
            WHERE COALESCE(p.listened, 0) = 0
            ORDER BY RANDOM()
            LIMIT 1
            """
        ).fetchone()
        return dict(row) if row else None


def set_progress(
    catalog_id: int,
    *,
    listened: bool,
    rating: Optional[int],
    note: str,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO progress (catalog_id, listened, rating, note, listened_on, updated_at)
            VALUES (?, ?, ?, ?, CASE WHEN ? THEN datetime('now') ELSE NULL END, datetime('now'))
            ON CONFLICT(catalog_id) DO UPDATE SET
                listened    = excluded.listened,
                rating      = excluded.rating,
                note        = excluded.note,
                listened_on = CASE WHEN excluded.listened = 1 AND progress.listened_on IS NOT NULL
                                   THEN progress.listened_on
                                   ELSE excluded.listened_on END,
                updated_at  = datetime('now')
            """,
            (catalog_id, int(listened), rating, note, int(listened)),
        )
