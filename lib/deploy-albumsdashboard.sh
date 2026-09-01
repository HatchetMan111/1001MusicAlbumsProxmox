#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# deploy-albumsdashboard.sh
# Laeuft INNERHALB der LXC (wird von install/albumsdashboard.sh per
# `pct exec` aufgerufen). Installiert Python, klont das App-Repo,
# richtet venv + systemd-Service + Firewall ein und prueft am Ende
# ob die Web-UI antwortet.
#
# Idempotent: kann mehrfach ausgefuehrt werden (z. B. fuer Updates).
# ---------------------------------------------------------------------------
set -euo pipefail
trap 'echo; echo "[FEHLER] deploy-albumsdashboard.sh ist in Zeile $LINENO fehlgeschlagen (Exit-Code $?)."; echo "Letzter Befehl: $BASH_COMMAND"; echo "--- Journal (letzte 60 Zeilen) ---"; journalctl -u albumsdashboard --no-pager -n 60 2>/dev/null || true; exit 1' ERR

REPO_URL="${REPO_URL:-https://github.com/HatchetMan111/1001MusicAlbumsProxmox.git}"
REPO_BRANCH="${REPO_BRANCH:-main}"
APP_DIR="/opt/albumsdashboard"
APP_USER="albumsdashboard"
PORT="${PORT:-8080}"
VERBOSE="${VERBOSE:-0}"

if [[ "$VERBOSE" == "1" ]]; then
  set -x
fi

log() { echo -e "\e[1;33m[deploy]\e[0m $*"; }

log "Aktualisiere Paketquellen und installiere Abhaengigkeiten..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq --no-install-recommends \
  python3 python3-venv python3-pip git ca-certificates curl ufw sqlite3 \
  > /tmp/apt-install.log 2>&1 || { echo "--- apt-get install Log ---"; cat /tmp/apt-install.log; exit 1; }

if ! id -u "$APP_USER" >/dev/null 2>&1; then
  log "Lege Systembenutzer '$APP_USER' an..."
  useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"
fi

if [[ -d "$APP_DIR/.git" ]]; then
  log "Bestehende Installation gefunden, aktualisiere Code (git pull)..."
  # Nutzerdaten (SQLite-Fortschritt) liegen in data/ und bleiben unberuehrt.
  git -C "$APP_DIR" fetch --depth 1 origin "$REPO_BRANCH"
  git -C "$APP_DIR" reset --hard "origin/$REPO_BRANCH"
elif [[ -e "$APP_DIR" ]]; then
  # NICHT einfach loeschen: Falls hier (z. B. nach einem abgebrochenen
  # Erst-Deploy) eine Fortschritts-DB liegt, waere das ein Datenverlust.
  # Stattdessen: sichern, neu klonen, zurueckschreiben.
  log "$APP_DIR existiert ohne .git – sichere evtl. Nutzerdaten und klonne neu..."
  BACKUP_DIR=$(mktemp -d /tmp/albumsdashboard-data.XXXXXX)
  [[ -d "$APP_DIR/data" ]] && cp -a "$APP_DIR/data" "$BACKUP_DIR/"
  rm -rf "$APP_DIR"
  if ! git clone --depth 1 --branch "$REPO_BRANCH" "$REPO_URL" "$APP_DIR"; then
    cp -a "$BACKUP_DIR/data" "$APP_DIR/" 2>/dev/null || true
    echo "Klon fehlgeschlagen – gesicherte Nutzerdaten liegen in $BACKUP_DIR" >&2
    exit 1
  fi
  if [[ -d "$BACKUP_DIR/data" ]]; then
    cp -a "$BACKUP_DIR/data/." "$APP_DIR/data/"
    rm -rf "$BACKUP_DIR"
  fi
else
  log "Klone Repository $REPO_URL ..."
  git clone --depth 1 --branch "$REPO_BRANCH" "$REPO_URL" "$APP_DIR"
fi

mkdir -p "$APP_DIR/data"

log "Erstelle/aktualisiere virtuelle Umgebung..."
if [[ ! -d "$APP_DIR/venv" ]]; then
  python3 -m venv "$APP_DIR/venv"
fi
"$APP_DIR/venv/bin/pip" install --quiet --upgrade pip
"$APP_DIR/venv/bin/pip" install --quiet -r "$APP_DIR/requirements.txt" \
  || { echo "--- pip install Fehler ---"; "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"; exit 1; }

chown -R "$APP_USER":"$APP_USER" "$APP_DIR"

log "Richte systemd-Service ein..."
sed "s/:8080/:${PORT}/" "$APP_DIR/lib/albumsdashboard.service" > /etc/systemd/system/albumsdashboard.service
systemctl daemon-reload
systemctl enable albumsdashboard.service >/dev/null 2>&1

# Journal begrenzen: kein unbegrenztes Anwachsen in kleinen LXC-Containern.
mkdir -p /etc/systemd/journald.conf.d
cat > /etc/systemd/journald.conf.d/albumsdashboard.conf <<'EOF'
[Journal]
MaxRetentionSec=2week
EOF

log "Starte/aktiviere den Service neu..."
systemctl restart albumsdashboard.service

log "Oeffne Firewall-Port ${PORT}/tcp (ufw)..."
ufw allow "${PORT}/tcp" >/dev/null 2>&1 || true

log "Warte auf den Start des Dienstes..."
for _try in $(seq 1 15); do
  if systemctl is-active --quiet albumsdashboard.service; then
    break
  fi
  sleep 1
done

if ! systemctl is-active --quiet albumsdashboard.service; then
  echo "[FEHLER] Service ist nicht aktiv. Vollstaendiger Status:"
  systemctl status albumsdashboard.service --no-pager -l || true
  echo "--- journalctl -u albumsdashboard (letzte 80 Zeilen) ---"
  journalctl -u albumsdashboard --no-pager -n 80 || true
  exit 1
fi

log "Pruefe HTTP-Antwort auf localhost:${PORT} ..."
HTTP_OK=0
for _try in $(seq 1 15); do
  if curl -fsS "http://127.0.0.1:${PORT}/healthz" >/dev/null 2>&1; then
    HTTP_OK=1
    break
  fi
  sleep 1
done

if [[ "$HTTP_OK" != "1" ]]; then
  echo "[FEHLER] Web-UI antwortet nach 15s nicht auf http://127.0.0.1:${PORT}/healthz"
  echo "--- journalctl -u albumsdashboard (letzte 80 Zeilen) ---"
  journalctl -u albumsdashboard --no-pager -n 80 || true
  exit 1
fi

log "Deployment erfolgreich abgeschlossen."
