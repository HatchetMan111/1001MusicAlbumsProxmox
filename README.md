# AlbumsDashboard

Eine vollstaendig lokale, eigenstaendige Checkliste zu **"1001 Albums You
Must Hear Before You Die"**: die komplette Albenliste ist fest in der App
enthalten, du markierst was du gehoert hast, vergibst eine eigene Bewertung
(1-5 Sterne) mit Notiz, und bekommst pro Album Such-Links zu Spotify,
YouTube Music, Apple Music, Deezer und Tidal.

**Keine Cloud, kein externer Dienst, kein Login.** Nach der Installation
findet zur Laufzeit kein einziger Netzwerkzugriff mehr statt – alle Daten
(Katalog + dein Fortschritt) liegen lokal in SQLite im LXC-Container.

## Installation (Proxmox-Host, als root)

```bash
bash -c "$(curl -fsSL https://cdn.jsdelivr.net/gh/HatchetMan111/1001MusicAlbumsProxmox@main/install/albumsdashboard.sh)"
```

Das Script fragt interaktiv (whiptail) nach Container-ID, Ressourcen und dem
Web-UI-Port. Danach ist das Dashboard sofort unter `http://<IP>:8080`
einsatzbereit – kein weiterer Konfigurationsschritt noetig.

> **Hinweis zur Quelle:** Der Einzeiler laedt ueber [jsDelivr](https://www.jsdelivr.com/)
> (ein unabhaengiges CDN), nicht direkt von `raw.githubusercontent.com` –
> letzteres blockiert manche IP-Bereiche mit `400 Bad Request`, obwohl die
> Verbindung technisch einwandfrei ist. Falls jsDelivr bei dir nicht
> erreichbar sein sollte, funktioniert ersatzweise:
> ```bash
> bash -c "$(curl -fsSL https://raw.githubusercontent.com/HatchetMan111/1001MusicAlbumsProxmox/main/install/albumsdashboard.sh)"
> ```
> jsDelivr cached Dateien fuer eine Weile; nach einem Update kann es bis zu
> einigen Stunden dauern, bis eine Aenderung dort ankommt (Cache laesst sich
> manuell leeren: https://www.jsdelivr.com/tools/purge).

## Update

Installer mit **derselben Container-ID** erneut ausfuehren – das Script
erkennt die bestehende LXC, zieht den neuesten Code (`git pull`) und startet
den Service neu. Dein Fortschritt (SQLite-Datenbank) bleibt dabei erhalten.

```bash
bash -c "$(curl -fsSL https://cdn.jsdelivr.net/gh/HatchetMan111/1001MusicAlbumsProxmox@main/install/albumsdashboard.sh)"
```

## Deinstallation

```bash
pct stop <CTID> && pct destroy <CTID>
```

## Fehlersuche

Ausfuehrliche Debug-Ausgabe (kompletter `bash -x`-Trace) beim Installieren:

```bash
DEBUG=1 bash -c "$(curl -fsSL https://cdn.jsdelivr.net/gh/HatchetMan111/1001MusicAlbumsProxmox@main/install/albumsdashboard.sh)"
```

Im laufenden Betrieb, direkt im Container:

```bash
pct exec <CTID> -- systemctl status albumsdashboard --no-pager -l
pct exec <CTID> -- journalctl -u albumsdashboard -n 100 --no-pager
```

## Architektur

- **Backend:** Python 3 / FastAPI, Jinja2-Templates, SQLite (`app/db.py`)
- **Katalog:** `app/data/1001_albums.tsv` – wird beim allerersten Start
  einmalig in die lokale SQLite-Datenbank importiert (1001 Eintraege: Jahr,
  Titel, Interpret). Herkunft und Lizenzhinweis siehe `app/data/SOURCE.md`
- **Fortschritt:** Gehoert-Status, Bewertung und Notiz sind rein lokale
  Nutzerdaten, unabhaengig vom Katalog
- **Links pro Album:** `app/links.py` baut ausschliesslich Such-URLs aus
  Interpret + Titel (kein API-Abgleich, keine ID-Aufloesung, keine
  Netzwerkanfrage vom Server aus) – der Klick auf einen Link oeffnet sich
  im Browser des Nutzers, nicht auf dem Server
- **Zufallsvorschlag:** `GET /zufall` waehlt zufaellig ein noch nicht
  gehoertes Album aus dem lokalen Katalog
- **Proxmox-Layer:** `install/albumsdashboard.sh` (Host, erstellt/aktualisiert
  die LXC) + `lib/deploy-albumsdashboard.sh` (laeuft im Container: Python,
  venv, systemd-Service, ufw-Regel, Health-Check)

## Robustheit

- **SQLite im WAL-Modus** mit Busy-Timeout: gleichzeitige Requests/Threads
  fuehren nicht mehr zu `database is locked`
- **Redirect-Encoding:** Suchbegriffe mit `&`, `#` usw. werden beim Speichern
  korrekt zurueck in die URL encodiert (kein zerbrochener Filter mehr)
- **Rating-Parsing robust:** ungueltige Eingaben (`²`, `3.5`, `9`, Muell)
  fuehren nicht mehr zu einem 500er, sondern werden ignoriert
- **Out-of-Range-Seiten** (z. B. Seite 999) leiten auf die letzte gueltige
  Seite um, statt eine leere Liste zu zeigen
- **Bewerten ungueltiger IDs** ergibt 404 statt stillschweigendem Insert
- **LIKE-Escaping:** `%`/`_` in der Suche sind Literale, keine Wildcards
- **Deploy ohne Datenverlust:** existiert `/opt/albumsdashboard` ohne `.git`
  (z. B. nach abgebrochenem Erst-Deploy), wird die Fortschritts-DB gesichert
  und zurueckgeschrieben, statt sie einfach zu loeschen

## UX

- **Filter-Tabs über der Liste:** „Alle / Noch offen / Gehört" mit
  Trefferzahlen – ein Klick zeigt z. B. nur die Alben, die man noch
  nicht gehört hat
- **Album-Cover** neben jeder Karte: rein clientseitig per
  iTunes-Artwork-CDN geladen (Lazy-Loading, LocalStorage-Cache,
  Noten-Platzhalter als Fallback). Der Server bleibt vollständig
  offline – er liefert keine Cover-URLs aus, der Browser lädt sie
  direkt vom CDN (genau wie die Streaming-Suchlinks)
- **Eigene Rubrik „Gehörte Alben"** (`/gehoert`): Chronologie mit
  „Zuletzt gehört zuerst", Bewertung, Notiz und Gehört-Datum, durchsuchbar
  und sortierbar – direkt über die Navigation oben erreichbar
- **Autosave ohne Reload** (Progressive Enhancement): Checkbox und Bewertung
  speichern sofort per `fetch`; die Antwort enthält den **tatsächlichen
  Datenbank-Stand**, mit dem Karte und Statistik-Leiste sofort synchronisiert
  werden – „Gespeichert" wird also erst nach Server-Bestätigung angezeigt.
  Ein abgehakter Haken einer Checkbox wird dabei ausdrücklich mitgesendet
  (Browser lassen ihn sonst weg, wodurch der Status verloren ginge).
  Ohne JavaScript funktionieren die klassischen Formulare weiterhin
- **Cache-Busting** (`?v=2`) für JS/CSS und `Cache-Control: no-store`
  für dynamische Seiten: keine veralteten Stände mehr im Browser
- **Redirect-Anker:** nach dem Speichern springt die Seite direkt zur
  bearbeiteten Karte (mit kurzem Aufleuchten)
- **Sterne-Anzeige** an jeder bewerteten Karte plus Gehört-Datum
- **Kompakte Seitenzahlen-Pagination** mit Fenstern um die aktuelle Seite
- **Filter-Dropdowns** mit Trefferzahlen und Auto-Submit, Reset-Link
- **Barrierefreiheit:** ARIA-Labels, Fokus-Ringe für Tastaturnutzer,
  Screenreader-Texte für Links, `prefers-reduced-motion`-Unterstützung
- **Sortierung nach bester Bewertung** hinzugefügt
- **Mobile:** Filter- und Notizfelder nehmen die volle Breite ein

## Was bereits getestet wurde

In dieser Umgebung ohne echten Proxmox-Host wurde folgendes verifiziert:

- `bash -n` + ShellCheck (0 Warnungen) fuer beide Shell-Skripte
- `py_compile` fuer alle Python-Module
- Funktionstest `scripts/smoke_test.py`: Katalog-Import (1001 Alben,
  idempotent bei erneutem Start), Suche/Filter/Sortierung, Fortschritt
  setzen/aendern/zuruecksetzen, Zufallsvorschlag liefert nur offene Alben,
  Pagination ohne Ueberschneidung, Link-Erzeugung, Rating-Robustheit,
  LIKE-Escaping
- Integrationstest `scripts/http_test.py` (FastAPI TestClient): Redirect-
  Encoding (`&` in der Suche), Redirect-Anker, Unicode-Rating ohne 500er,
  404 bei ungueltiger Album-ID, Out-of-Range-Redirect auf letzte Seite,
  Sterne-Anzeige, Auslieferung der Static-Assets
- WAL-Verifikation: 25 parallele Schreibzugriffe ohne `database is locked`
- Echter HTTP-Testlauf gegen den laufenden Uvicorn-Server: Startseite,
  Suche, Zufalls-Redirect, Bewertung ueber das Web-Formular, sowie eine
  gezielte Pruefung, dass im ausgelieferten HTML **keinerlei** Verweis auf
  einen externen Dienst vorkommt (Such-Links zu Streaming-Diensten sind
  bewusst Bestandteil und werden erst im Browser des Nutzers geoeffnet)

## Was du nach der Installation noch selbst verifizieren solltest

Auf deinem echten Proxmox-Host (dort habe ich keinen Zugriff):

```bash
# 1) Nach der Installation: Service-Status pruefen
pct exec <CTID> -- systemctl is-active albumsdashboard

# 2) Reboot-Test
pct reboot <CTID>
sleep 20
pct exec <CTID> -- systemctl is-active albumsdashboard
curl -fsS http://<CTID-IP>:8080/healthz
```

## Lizenz

MIT, siehe `LICENSE`. Zur Herkunft der eingebetteten Albenliste siehe
`app/data/SOURCE.md`.
