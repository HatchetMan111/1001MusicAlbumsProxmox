"""
HTTP-Integrationstest mit FastAPI TestClient: prueft die gefixten
Endpunkte gegen die echte App (Redirects, Encoding, Pagination-Grenzen,
404-Fall, HTML-Auslieferung) – ohne echten Uvicorn-Prozess.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app import db  # noqa: E402
from app.main import app  # noqa: E402


def _reset_db() -> None:
    db.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Auch WAL-Nebendateien entfernen, sonst kann ein alter WAL-Stand uebrig bleiben.
    for suffix in ("", "-wal", "-shm"):
        path = db.DB_PATH.with_name(db.DB_PATH.name + suffix)
        if path.exists():
            path.unlink()


def main() -> None:
    _reset_db()

    # 'with' nötig: nur als Context-Manager fuehrt TestClient den Lifespan
    # (und damit db.init_db()) aus.
    with TestClient(app) as client:

        # -- healthz --
        r = client.get("/healthz")
        assert r.status_code == 200 and r.json() == {"status": "ok"}

        # -- Startseite rendert --
        r = client.get("/")
        assert r.status_code == 200
        assert "gehört" in r.text
        assert "1001" in r.text

        # -- Suche mit '&': Redirect und Filter dürfen nicht brechen --
        r = client.get("/", params={"q": "AC&DC"})
        assert r.status_code == 200
        assert "Keine Alben gefunden" in r.text

        # -- Bewertung via Formular: q mit '&' wird im Redirect encodiert --
        first = db.list_albums(page_size=1)["albums"][0]
        r = client.post(
            f"/rate/{first['id']}",
            data={"listened": "on", "rating": "5", "note": "Test & mehr",
                  "status": "all", "q": "AC&DC", "sort": "year_asc", "page": "1"},
            follow_redirects=False,
        )
        assert r.status_code == 303, f"Erwartet 303, bekommen {r.status_code}"
        assert "q=AC%26DC" in r.headers["location"], f"q nicht encodiert: {r.headers['location']}"
        assert f"#album-{first['id']}" in r.headers["location"], "Redirect-Anker fehlt"

        # -- Unicode-Rating (früher 500er durch int('²')) --
        r = client.post(
            f"/rate/{first['id']}",
            data={"listened": "", "rating": "²", "note": "",
                  "status": "all", "q": "", "sort": "year_asc", "page": "1"},
            follow_redirects=False,
        )
        assert r.status_code == 303, f"Unicode-Rating darf keinen 500er geben: {r.status_code}"

        # -- Bewertung zurücksetzen --
        client.post(
            f"/rate/{first['id']}",
            data={"listened": "", "rating": "", "note": "",
                  "status": "all", "q": "", "sort": "year_asc", "page": "1"},
        )
        assert db.get_album(first["id"])["listened"] == 0

        # -- Ungültige Album-ID -> 404 --
        r = client.post("/rate/999999", data={"listened": "on"})
        assert r.status_code == 404

        # -- Seite jenseits des Maximums -> Redirect auf letzte Seite --
        r = client.get("/", params={"page": "999"}, follow_redirects=False)
        assert r.status_code == 303
        assert "page=26" in r.headers["location"], f"Erwartet Redirect auf Seite 26: {r.headers['location']}"

        r = client.get("/", params={"page": "26"})
        assert r.status_code == 200
        assert "Keine Alben" not in r.text
        assert 'aria-label="Seitennavigation"' in r.text

        # -- Zufall: Redirect auf Startseite mit highlight, Karte sichtbar --
        r = client.get("/zufall", follow_redirects=False)
        assert r.status_code == 303
        assert "highlight=" in r.headers["location"]
        r = client.get(r.headers["location"])
        assert r.status_code == 200
        assert "Vorschlag" in r.text

        # -- Sterne erscheinen nach Bewertung --
        second = db.list_albums(status="open", page_size=1)["albums"][0]
        client.post(
            f"/rate/{second['id']}",
            data={"listened": "on", "rating": "4", "note": "",
                  "status": "all", "q": "", "sort": "year_asc", "page": "1"},
        )
        r = client.get("/", params={"status": "listened"})
        assert "star-filled" in r.text, "Bewertete Sterne sollten angezeigt werden"
        client.post(
            f"/rate/{second['id']}",
            data={"listened": "", "rating": "", "note": "",
                  "status": "all", "q": "", "sort": "year_asc", "page": "1"},
        )

        # -- Autosave-JS und CSS werden ausgeliefert --
        assert client.get("/static/app.js").status_code == 200
        assert client.get("/static/style.css").status_code == 200

        # -- JSON-API des Autosave: Antwort spiegelt tatsaechlichen DB-Stand --
        r = client.post(
            f"/rate/{first['id']}",
            data={"listened": "on", "rating": "5", "note": "JSON-Test",
                  "status": "all", "q": "", "sort": "year_asc", "page": "1"},
            headers={"Accept": "application/json"},
        )
        assert r.status_code == 200
        payload = r.json()
        assert payload["ok"] is True
        assert payload["listened"] is True
        assert payload["rating"] == 5
        assert payload["note"] == "JSON-Test"
        assert payload["listened_on"] is not None, "listened_on muss nach dem Speichern gesetzt sein"
        assert payload["stats"]["listened"] >= 1

        # Persistenz-Verifikation: zweiter read-only GET sieht den Status (kein Cache-Betrug)
        r = client.get("/", params={"status": "listened"})
        assert "is-listened" in r.text
        assert "no-store" in r.headers.get("cache-control", "")

        # -- Gehört-Rubrik: eigene Seite listet gehörte Alben --
        r = client.get("/gehoert")
        assert r.status_code == 200
        assert "Gehörte Alben" in r.text
        assert first["album"] in r.text
        assert "Zuletzt gehört" in r.text

        # -- Gehört-Rubrik: Suche + Sortierung + Out-of-Range --
        r = client.get("/gehoert", params={"q": first["album"]})
        assert r.status_code == 200 and first["album"] in r.text
        r = client.get("/gehoert", params={"page": "999"}, follow_redirects=False)
        assert r.status_code == 303
        assert "page=" in r.headers["location"]

        # -- Nav-Links in der Auslieferung --
        r = client.get("/")
        assert 'href="/gehoert"' in r.text

        # -- Aufraeumen: Album 1 zurücksetzen --
        client.post(
            f"/rate/{first['id']}",
            data={"listened": "", "rating": "", "note": "",
                  "status": "all", "q": "", "sort": "year_asc", "page": "1"},
        )
        assert db.get_album(first["id"])["listened"] == 0

        print("HTTP TEST OK: Redirect-Encoding, Anker, Unicode-Rating, 404, "
              "Out-of-Range-Redirect, Zufall, Sterne-Anzeige, Static-Assets, "
              "JSON-Autosave (Persistenz), Gehört-Rubrik.")


if __name__ == "__main__":
    main()
