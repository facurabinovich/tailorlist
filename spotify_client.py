"""
spotify_client.py
Compatibility shim — the code moved to spotify/client.py (API client),
ui/export.py (render_export_to_spotify) and db/analytics.py (log_export_event).
Removed in T28.
"""

from spotify.client import (  # noqa: F401
    _get_credentials,
    get_spotify_client,
    get_spotify_oauth_client,
    create_spotify_playlist,
    extract_playlist_id,
    get_playlist_tracks,
    enrich_tracks_live,
)
from db.analytics import log_export_event  # noqa: F401
from ui.export import render_export_to_spotify  # noqa: F401
