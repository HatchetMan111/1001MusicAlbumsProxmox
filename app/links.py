"""
Erzeugt pro Album Such-Links für gaengige Streaming-Dienste – rein lokal,
ohne jeglichen Netzwerkzugriff und ohne Abhängigkeit von einem externen
Dienst. Es werden bewusst nur Such-URLs gebaut (kein Abgleich gegen eine
Alben-Datenbank eines Drittanbieters), damit die App zur Laufzeit komplett
offline-faehig bleibt.
"""
from __future__ import annotations

import urllib.parse

SERVICES: dict[str, str] = {
    "spotify": "https://open.spotify.com/search/{q}",
    "youtube_music": "https://music.youtube.com/search?q={q}",
    "apple_music": "https://music.apple.com/search?term={q}",
    "deezer": "https://www.deezer.com/search/{q}",
    "tidal": "https://listen.tidal.com/search?q={q}",
}

LABELS: dict[str, str] = {
    "spotify": "Spotify",
    "youtube_music": "YouTube Music",
    "apple_music": "Apple Music",
    "deezer": "Deezer",
    "tidal": "Tidal",
}


def build_links(artist: str, album: str) -> dict[str, str]:
    query = urllib.parse.quote(f"{artist} {album}")
    return {service: template.format(q=query) for service, template in SERVICES.items()}


def service_label(key: str) -> str:
    """Anzeigename eines Dienstes; unbekannte Schluessel fallen auf sich selbst zurück."""
    return LABELS.get(key, key)
