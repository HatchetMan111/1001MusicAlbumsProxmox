#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# AlbumsDashboard – Proxmox-Community-Script-Style Installer
#
# Einzeiler (auf dem Proxmox-Host als root ausfuehren):
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/HatchetMan111/1001MusicAlbumsProxmox/main/install/albumsdashboard.sh)"
#
# Erstellt einen unprivilegierten Debian-12-LXC-Container, installiert dort
# AlbumsDashboard und richtet einen systemd-Service ein. Erneuter Aufruf mit
# derselben CT-ID aktualisiert eine bestehende Installation (idempotent).
# ---------------------------------------------------------------------------
set -euo pipefail

REPO_URL_DEFAULT="https://github.com/HatchetMan111/1001MusicAlbumsProxmox.git"
REPO_RAW_DEFAULT="https://raw.githubusercontent.com/HatchetMan111/1001MusicAlbumsProxmox/main"

# shellcheck disable=SC2154  # "code" wird im Trap selbst per $? gesetzt
trap 'code=$?; echo; echo -e "\e[1;31m[FEHLER]\e[0m Installation abgebrochen in Zeile $LINENO (Exit-Code $code)."; echo "Letzter Befehl: $BASH_COMMAND"; echo; echo "Fuer eine ausfuehrliche Fehlerausgabe, erneut starten mit:"; echo "  DEBUG=1 bash -c \"\$(curl -fsSL ${REPO_RAW_DEFAULT}/install/albumsdashboard.sh)\""; exit $code' ERR

if [[ "${DEBUG:-0}" == "1" ]]; then
  set -x
fi

# --- Voraussetzungen -------------------------------------------------------
if [[ $EUID -ne 0 ]]; then
  echo "Bitte als root auf dem Proxmox-Host ausfuehren." >&2
  exit 1
fi
if ! command -v pct >/dev/null 2>&1; then
  echo "Dieses Script muss auf einem Proxmox-VE-Host laufen (Befehl 'pct' fehlt)." >&2
  exit 1
fi

command -v whiptail >/dev/null 2>&1 || apt-get install -y -qq whiptail >/dev/null

msg() { echo -e "\e[1;33m[AlbumsDashboard]\e[0m $*"; }

# --- Eingaben (mit sinnvollen Standardwerten, per whiptail abfragbar) ------
NEXTID=$(pvesh get /cluster/nextid 2>/dev/null || echo 200)

CTID=$(whiptail --backtitle "AlbumsDashboard Installer" --inputbox \
  "Container-ID (bestehende ID = Update einer vorhandenen Installation):" 10 60 "$NEXTID" \
  3>&1 1>&2 2>&3) || exit 1

CORES=$(whiptail --backtitle "AlbumsDashboard Installer" --inputbox "vCPU-Kerne:" 10 60 "1" 3>&1 1>&2 2>&3) || exit 1
RAM=$(whiptail --backtitle "AlbumsDashboard Installer" --inputbox "RAM in MB:" 10 60 "1024" 3>&1 1>&2 2>&3) || exit 1
DISK=$(whiptail --backtitle "AlbumsDashboard Installer" --inputbox "Disk-Groesse in GB:" 10 60 "6" 3>&1 1>&2 2>&3) || exit 1
STORAGE=$(whiptail --backtitle "AlbumsDashboard Installer" --inputbox "Proxmox-Storage fuer Root-Disk:" 10 60 "local-lvm" 3>&1 1>&2 2>&3) || exit 1
BRIDGE=$(whiptail --backtitle "AlbumsDashboard Installer" --inputbox "Netzwerk-Bridge:" 10 60 "vmbr0" 3>&1 1>&2 2>&3) || exit 1
PORT=$(whiptail --backtitle "AlbumsDashboard Installer" --inputbox "Web-UI-Port:" 10 60 "8080" 3>&1 1>&2 2>&3) || exit 1

REPO_URL="${REPO_URL:-$REPO_URL_DEFAULT}"
REPO_RAW="${REPO_RAW:-$REPO_RAW_DEFAULT}"

# --- LXC anlegen (oder bestehende fuer Update wiederverwenden) -------------
if pct status "$CTID" >/dev/null 2>&1; then
  msg "Container $CTID existiert bereits – fahre mit Update/Redeploy fort."
else
  msg "Aktualisiere LXC-Template-Liste..."
  pveam update >/dev/null

  TEMPLATE=$(pveam available --section system | awk '/debian-12-standard/ {print $2}' | sort -V | tail -n1)
  if [[ -z "$TEMPLATE" ]]; then
    echo "Kein Debian-12-Template gefunden. 'pveam available' Ausgabe:" >&2
    pveam available --section system >&2
    exit 1
  fi

  TEMPLATE_STORAGE="local"
  if ! pveam list "$TEMPLATE_STORAGE" 2>/dev/null | grep -q "$TEMPLATE"; then
    msg "Lade Template $TEMPLATE herunter..."
    pveam download "$TEMPLATE_STORAGE" "$TEMPLATE"
  fi

  msg "Erstelle LXC-Container $CTID (Debian 12, ${CORES} vCPU, ${RAM} MB RAM, ${DISK} GB Disk)..."
  pct create "$CTID" "${TEMPLATE_STORAGE}:vztmpl/${TEMPLATE}" \
    --hostname albumsdashboard \
    --cores "$CORES" \
    --memory "$RAM" \
    --swap 512 \
    --rootfs "${STORAGE}:${DISK}" \
    --net0 "name=eth0,bridge=${BRIDGE},ip=dhcp" \
    --unprivileged 1 \
    --features nesting=1 \
    --onboot 1 \
    --start 1

  msg "Warte auf Netzwerkstart des Containers..."
  for i in $(seq 1 30); do
    if pct exec "$CTID" -- getent hosts github.com >/dev/null 2>&1; then
      break
    fi
    sleep 2
    if [[ $i -eq 30 ]]; then
      echo "Container hat nach 60s keine funktionierende Netzwerkverbindung." >&2
      pct exec "$CTID" -- ip addr || true
      exit 1
    fi
  done
fi

# --- Deploy-Script in den Container laden und ausfuehren -------------------
msg "Lade Provisionierungs-Script..."
curl -fsSL "${REPO_RAW}/lib/deploy-albumsdashboard.sh" -o /tmp/deploy-albumsdashboard.sh \
  || { echo "Konnte deploy-albumsdashboard.sh nicht laden. Pruefe REPO_RAW=${REPO_RAW}"; exit 1; }
pct push "$CTID" /tmp/deploy-albumsdashboard.sh /root/deploy-albumsdashboard.sh
pct exec "$CTID" -- chmod +x /root/deploy-albumsdashboard.sh

msg "Starte Installation/Update im Container..."
pct exec "$CTID" -- env \
  REPO_URL="$REPO_URL" \
  REPO_BRANCH="main" \
  PORT="$PORT" \
  VERBOSE="${DEBUG:-0}" \
  bash /root/deploy-albumsdashboard.sh

# --- Ergebnis anzeigen -------------------------------------------------------
IP=$(pct exec "$CTID" -- hostname -I | awk '{print $1}')
echo
echo -e "\e[1;32m✔ Installation abgeschlossen.\e[0m"
echo -e "  Web-UI:      http://${IP}:${PORT}"
echo -e "  Container:   CT ${CTID} (albumsdashboard)"
echo -e "  Update:      Installer erneut mit gleicher CT-ID (${CTID}) ausfuehren."
echo -e "  Deinstall:   pct stop ${CTID} && pct destroy ${CTID}"
