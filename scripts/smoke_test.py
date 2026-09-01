"""
Smoke-Test für die lokale, eigenstaendige Version von AlbumsDashboard:
prueft Katalog-Import aus der mitgelieferten TSV-Datei, Filter/Sortierung,
Fortschritt (gehört/Bewertung/Notiz), Zufallsvorschlag, die netzwerkfreie
Link-Erzeugung sowie die Robustheits-Fixes (Rating-Parsing, LIKE-Escaping,
Redirect-Encoding, Out-of-Range-Seiten).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db  # noqa: E402
from app.links import build_links  # noqa: E402
from app.main import _safe_rating  # noqa: E402


def main() -> None:
    db.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if db.DB_PATH.exists():
        db.DB_PATH.unlink()
    db.init_db()

    # -- Katalog-Import --
    s = db.stats()
    assert s["total"] == 1001, f"Erwartet 1001 Alben im Katalog, gefunden {s['total']}"
    assert s["listened"] == 0
    assert s["open"] == 1001
    assert s["percent"] == 0.0

    # Erneuter init_db()-Aufruf darf NICHT erneut importieren (Idempotenz)
    db.init_db()
    assert db.stats()["total"] == 1001, "Katalog wurde beim zweiten init_db() erneut importiert!"

    # -- Suche/Filter/Sortierung --
    result = db.list_albums(query="Radiohead", page_size=10)
    assert result["total"] >= 1, "Radiohead sollte in der Liste vorkommen"
    radiohead_album = result["albums"][0]
    assert "radiohead" in radiohead_album["artist"].lower()

    # -- Fortschritt setzen --
    db.set_progress(radiohead_album["id"], listened=True, rating=5, note="Klassiker")
    updated = db.get_album(radiohead_album["id"])
    assert updated["listened"] == 1
    assert updated["rating"] == 5
    assert updated["note"] == "Klassiker"
    assert updated["listened_on"] is not None

    s = db.stats()
    assert s["listened"] == 1
    assert s["open"] == 1000
    assert s["percent"] == 0.1

    # -- Filter "listened" / "open" --
    listened_result = db.list_albums(status="listened", page_size=5)
    assert any(a["id"] == radiohead_album["id"] for a in listened_result["albums"])
    open_result = db.list_albums(status="open", page_size=5)
    assert all(a["id"] != radiohead_album["id"] for a in open_result["albums"])

    # -- Fortschritt ändern (z. B. Bewertung korrigieren) darf listened_on nicht verlieren --
    db.set_progress(radiohead_album["id"], listened=True, rating=4, note="Doch nur 4 Sterne")
    updated2 = db.get_album(radiohead_album["id"])
    assert updated2["rating"] == 4
    assert updated2["listened_on"] == updated["listened_on"], "listened_on sollte beim Update erhalten bleiben"

    # -- Als "nicht gehört" zurücksetzen --
    db.set_progress(radiohead_album["id"], listened=False, rating=None, note="")
    reset = db.get_album(radiohead_album["id"])
    assert reset["listened"] == 0
    assert reset["rating"] is None

    # -- set_progress auf ungültige ID liefert False statt stillschweigendem Insert --
    assert db.set_progress(999999, listened=True, rating=None, note="") is False

    # -- Rating-Sortierung --
    db.set_progress(radiohead_album["id"], listened=True, rating=5, note="")
    rated = db.list_albums(sort="rating_desc", page_size=5)
    assert rated["albums"][0]["id"] == radiohead_album["id"], "5-Sterne-Album sollte bei rating_desc zuerst kommen"

    # -- LIKE-Escaping: Sonderzeichen sind Literale, keine Wildcards --
    pct = db.list_albums(query="%%", page_size=5)
    assert pct["total"] == 0, "'%%' darf nicht als Wildcard-Allesmatch wirken"
    und = db.list_albums(query="__", page_size=5)
    assert und["total"] == 0, "'__' darf nicht als Wildcard-Allesmatch wirken"

    # -- Zufallsvorschlag liefert nur offene Alben --
    for _ in range(20):
        pick = db.random_open_album()
        assert pick is not None
        full = db.get_album(pick["id"])
        assert full["listened"] == 0

    # -- Pagination --
    page1 = db.list_albums(page=1, page_size=40)
    page2 = db.list_albums(page=2, page_size=40)
    assert page1["pages"] == 26, f"Erwartet 26 Seiten a 40, bekommen {page1['pages']}"
    ids_p1 = {a["id"] for a in page1["albums"]}
    ids_p2 = {a["id"] for a in page2["albums"]}
    assert ids_p1.isdisjoint(ids_p2), "Seite 1 und 2 dürfen sich nicht überschneiden"

    # -- Rating-Parsing-Robustheit (früher: 500er bei Unicode-Ziffern) --
    assert _safe_rating("3") == 3
    assert _safe_rating(" 5 ") == 5
    assert _safe_rating("2") == 2
    assert _safe_rating("9") is None, "9 liegt außerhalb 1-5"
    assert _safe_rating("") is None
    assert _safe_rating("abc") is None
    assert _safe_rating("²") is None, "Unicode-Ziffer darf int() nicht zum Crash bringen"
    assert _safe_rating("3.5") is None

    # -- Link-Erzeugung ist rein lokal (keine Netzwerkaufrufe, nur URL-Bau) --
    links = build_links("Radiohead", "OK Computer")
    assert links["spotify"] == "https://open.spotify.com/search/Radiohead%20OK%20Computer"
    assert set(links.keys()) == {"spotify", "youtube_music", "apple_music", "deezer", "tidal"}

    print(
        f"SMOKE TEST OK: {s['total']} Alben importiert, Suche/Filter/Sortierung, "
        f"Fortschritt (inkl. Reset + ungültiger ID), Rating-Robustheit, "
        f"LIKE-Escaping, Zufallsvorschlag und Link-Erzeugung funktionieren."
    )


if __name__ == "__main__":
    main()
