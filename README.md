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
bash -c "$(wget -qLO - https://raw.githubusercontent.com/HatchetMan111/1001MusicAlbumsProxmox/main/install/albumsdashboard.sh)"
```

Das Script fragt interaktiv (whiptail) nach Container-ID, Ressourcen und dem
Web-UI-Port. Danach ist das Dashboard sofort unter `http://<IP>:8080`
einsatzbereit – kein weiterer Konfigurationsschritt noetig.

## Update

Installer mit **derselben Container-ID** erneut ausfuehren – das Script
erkennt die bestehende LXC, zieht den neuesten Code (`git pull`) und startet
den Service neu. Dein Fortschritt (SQLite-Datenbank) bleibt dabei erhalten.

```bash
bash -c "$(wget -qLO - https://raw.githubusercontent.com/HatchetMan111/1001MusicAlbumsProxmox/main/install/albumsdashboard.sh)"
```

## Deinstallation

```bash
pct stop <CTID> && pct destroy <CTID>
```

## Fehlersuche

Ausfuehrliche Debug-Ausgabe (kompletter `bash -x`-Trace) beim Installieren:

```bash
DEBUG=1 bash -c "$(wget -qLO - https://raw.githubusercontent.com/HatchetMan111/1001MusicAlbumsProxmox/main/install/albumsdashboard.sh)"
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

## Was bereits getestet wurde

In dieser Umgebung ohne echten Proxmox-Host wurde folgendes verifiziert:

- `bash -n` + ShellCheck (0 Warnungen) fuer beide Shell-Skripte
- `py_compile` fuer alle Python-Module
- Funktionstest `scripts/smoke_test.py`: Katalog-Import (1001 Alben,
  idempotent bei erneutem Start), Suche/Filter/Sortierung, Fortschritt
  setzen/aendern/zuruecksetzen, Zufallsvorschlag liefert nur offene Alben,
  Pagination ohne Ueberschneidung, Link-Erzeugung
- Echter HTTP-Testlauf gegen den laufenden Uvicorn-Server: Startseite,
  Suche, Zufalls-Redirect, Bewertung ueber das Web-Formular, sowie eine
  gezielte Pruefung, dass im ausgelieferten HTML **keinerlei** Verweis auf
  einen externen Dienst vorkommt

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
