"""
spotify/client.py
Spotify Client Credentials helpers — no user OAuth required.
"""

import os
import re
from pathlib import Path

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials, SpotifyOAuth

import config  # noqa: F401  (loads .env before credentials are read)
from config import is_dev_mode

_HERE = Path(__file__).resolve().parent


# ── Auth ──────────────────────────────────────────────────────────────────────

def _get_credentials() -> tuple[str, str]:
    """
    Return (client_id, client_secret) from env vars or st.secrets.
    Raises RuntimeError with a clear message if either is missing.
    """
    client_id = os.getenv("SPOTIFY_CLIENT_ID", "").strip()
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET", "").strip()

    if not client_id or not client_secret:
        try:
            import streamlit as st
            client_id = st.secrets.get("SPOTIFY_CLIENT_ID", client_id).strip()
            client_secret = st.secrets.get("SPOTIFY_CLIENT_SECRET", client_secret).strip()
        except Exception:
            pass

    if not client_id or not client_secret:
        raise RuntimeError(
            "Spotify credentials not found. "
            "Add SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET to your .env file "
            "(project root) and restart Streamlit."
        )

    return client_id, client_secret


def get_spotify_client() -> spotipy.Spotify:
    """Return a Client Credentials Spotify client — no user login needed."""
    client_id, client_secret = _get_credentials()
    return spotipy.Spotify(
        auth_manager=SpotifyClientCredentials(
            client_id=client_id,
            client_secret=client_secret,
        )
    )


def get_spotify_oauth_client() -> spotipy.Spotify | None:
    """
    Return a user-authenticated Spotify client for playlist creation.
    Only used in DEV_MODE=1. Returns None if auth fails.
    """
    import os
    if not is_dev_mode():
        return None
    try:
        client_id, client_secret = _get_credentials()
        return spotipy.Spotify(auth_manager=SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri="http://127.0.0.1:8501",
            scope="playlist-modify-private playlist-modify-public",
            cache_path=str(Path("/tmp") / ".spotify_cache"),
            open_browser=False,
        ))
    except Exception:
        return None


def create_spotify_playlist(
    sp: spotipy.Spotify,
    playlist_name: str,
    track_ids: list[str],
) -> str | None:
    """
    Create a private Spotify playlist and add tracks in batches of 100.
    Returns the playlist URL or None on failure.
    """
    try:
        user_id = sp.current_user()["id"]
        playlist = sp.user_playlist_create(
            user=user_id,
            name=playlist_name,
            public=False,
            description=f"Created by Spotify Analytics — {len(track_ids)} tracks",
        )
        playlist_id = playlist["id"]
        # Add in batches of 100
        uris = [f"spotify:track:{tid}" for tid in track_ids]
        for i in range(0, len(uris), 100):
            sp.playlist_add_items(playlist_id, uris[i:i+100])
        return playlist["external_urls"]["spotify"]
    except Exception:
        return None


# ── URL / ID parsing ──────────────────────────────────────────────────────────

def extract_playlist_id(url_or_id: str) -> str | None:
    """
    Extract Spotify playlist ID from URL, URI, or raw ID.

    Accepts:
        https://open.spotify.com/playlist/{id}
        https://open.spotify.com/playlist/{id}?si=xxxxx
        spotify:playlist:{id}
        raw 22-char alphanumeric ID
    """
    url_or_id = url_or_id.strip()
    match = re.search(r'playlist/([a-zA-Z0-9]{22})', url_or_id)
    if match:
        return match.group(1)
    match = re.search(r'playlist:([a-zA-Z0-9]{22})', url_or_id)
    if match:
        return match.group(1)
    if re.match(r'^[a-zA-Z0-9]{22}$', url_or_id):
        return url_or_id
    return None


# ── Track fetching ─────────────────────────────────────────────────────────────

def get_playlist_tracks(playlist_id: str) -> list[dict]:
    """
    Fetch all tracks from a public playlist.
    Raises spotipy.SpotifyException on 403/404 (private/not found).
    """
    sp = get_spotify_client()
    tracks: list[dict] = []
    results = sp.playlist_tracks(playlist_id)
    while results:
        for item in results["items"]:
            track = item.get("track")
            if track and track.get("id"):
                tracks.append({
                    "id":           track["id"],
                    "name":         track["name"],
                    "artists":      ", ".join(a["name"] for a in track["artists"]),
                    "artist_ids":   [a["id"] for a in track["artists"]],  # ← new
                    "album":        track["album"]["name"],
                    "duration_ms":  track["duration_ms"],
                    "uri":          track["uri"],
                    "popularity":   track.get("popularity", 0),
                    "release_date": track["album"].get("release_date", ""),
                    "added_at":     item.get("added_at", ""),
                })
        results = sp.next(results) if results["next"] else None

    # ── Batch-fetch artist genres ─────────────────────────────────────────
    # Collect all unique artist IDs
    all_artist_ids = list({
        aid
        for track in tracks
        for aid in track.get("artist_ids", [])
        if aid
    })

    # Spotify allows max 50 per request
    artist_genres: dict[str, list[str]] = {}
    for i in range(0, len(all_artist_ids), 50):
        batch = all_artist_ids[i:i+50]
        try:
            result = sp.artists(batch)
            for artist in result["artists"]:
                if artist:
                    artist_genres[artist["id"]] = artist.get("genres", [])
        except Exception:
            pass

    # Attach genres to each track (primary artist genres)
    for track in tracks:
        primary_id = track["artist_ids"][0] if track["artist_ids"] else None
        track["artist_genres"] = ", ".join(
            artist_genres.get(primary_id, [])
        )

    return tracks
