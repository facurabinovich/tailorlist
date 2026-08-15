"""
spotify_client.py
Spotify Client Credentials helpers — no user OAuth required.
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path

import spotipy
from dotenv import load_dotenv
from spotipy.oauth2 import SpotifyClientCredentials, SpotifyOAuth

# Load .env from the directory where this file lives (project root),
# regardless of where Streamlit is invoked from.
_HERE = Path(__file__).resolve().parent
load_dotenv(_HERE / ".env", override=True)


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
    if os.getenv("DEV_MODE", "0") != "1":
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


# ── Export logging ─────────────────────────────────────────────────────────────

def log_export_event(playlist_name: str, track_count: int) -> None:
    """
    Append an export event to export_events.json.
    Silently fails on I/O errors (e.g. read-only filesystems on Streamlit Cloud).
    """
    event = {
        "timestamp":     datetime.utcnow().isoformat(),
        "playlist_name": playlist_name,
        "track_count":   track_count,
    }
    log_file = Path("export_events.json")
    try:
        events: list = json.loads(log_file.read_text()) if log_file.exists() else []
    except (json.JSONDecodeError, OSError):
        events = []
    events.append(event)
    try:
        log_file.write_text(json.dumps(events, indent=2))
    except OSError:
        pass


# ── Spotlistr export UI ───────────────────────────────────────────────────────

def render_export_to_spotify(
    tracks: list[dict],
    playlist_name: str,
    key_prefix: str = "export",
    on_export=None,
) -> None:
    """on_export, if given, is called with n_tracks=<int> when the visitor
    downloads the CSV — lets the caller log analytics without this module
    knowing anything about them."""
    import streamlit as st
    import streamlit.components.v1 as components
    import pandas as pd

    st.subheader(f"🎵 Export: {playlist_name}")
    st.caption(f"{len(tracks)} tracks")

    # Build "Artist - Song Name" format for Spotlistr beta
    artist_song_list = "\n".join(
        f"{t.get('artists', '').split(',')[0].strip()} - {t.get('name', '')}"
        for t in tracks
    )

    # Step 1 — Copy to clipboard via JS
    st.markdown(
        "<p style='color:#B3B3B3;font-size:0.85rem;font-weight:700;margin-bottom:4px;'>"
        "Step 1 — Copy your tracks</p>",
        unsafe_allow_html=True,
    )

    import json as _json
    components.html(
        f"""
        <html><body style="margin:0;padding:0;">
        <textarea id="copydata" style="display:none">{_json.dumps(artist_song_list)}</textarea>
        <button id="copybtn"
        style="background:#333;color:#FFFFFF;border:none;border-radius:8px;
               padding:10px 20px;font-size:0.9rem;cursor:pointer;width:100%;
               transition:background 0.2s;"
        onclick="
            var text = JSON.parse(document.getElementById('copydata').value);
            navigator.clipboard.writeText(text)
                .then(function() {{
                    document.getElementById('copybtn').innerText = '✓ Copied {len(tracks)} tracks!';
                    document.getElementById('copybtn').style.background = '#1DB954';
                    setTimeout(function() {{
                        document.getElementById('copybtn').innerText = '📋 Copy {len(tracks)} tracks to clipboard';
                        document.getElementById('copybtn').style.background = '#333';
                    }}, 2500);
                }})
                .catch(function() {{
                    document.getElementById('copybtn').innerText = '⚠️ Copy failed — use text box below';
                    document.getElementById('copybtn').style.background = '#E8534A';
                }});
        ">
            📋 Copy {len(tracks)} tracks to clipboard
        </button>
        </body></html>
        """,
        height=50,
    )

    # Step 2 — Open Spotlistr beta
    st.markdown(
        "<p style='color:#B3B3B3;font-size:0.85rem;font-weight:700;"
        "margin-top:12px;margin-bottom:4px;'>Step 2 — Open Spotlistr Beta</p>",
        unsafe_allow_html=True,
    )
    st.link_button(
        "🚀 Open Spotlistr Beta",
        "https://beta.spotlistr.com/search/v2/textbox",
        type="primary",
        use_container_width=True,
    )

    # Step 3 — Instructions
    st.markdown(
        "<div style='background:#1a1a1a;border:1px solid #333;border-radius:8px;"
        "padding:10px 16px;margin-top:8px;'>"
        "<p style='color:#FFFFFF;font-size:0.85rem;margin:0 0 8px;'>"
        "<b>Step 3 — What happens on Spotlistr:</b></p>"
        "<ol style='color:#B3B3B3;font-size:0.82rem;margin:0;padding-left:18px;line-height:1.8;'>"
        "<li>Paste your tracks into the <b style='color:#FFFFFF;'>Inputs</b> box</li>"
        "<li>Sign in with your <b style='color:#FFFFFF;'>email</b> — no password needed, "
        "they send a 6-digit code</li>"
        "<li>Spotlistr searches Spotify for each track and shows <b style='color:#FFFFFF;'>"
        "confidence scores</b> — review any uncertain matches</li>"
        "<li>Click <b style='color:#1DB954;'>Create Playlist</b> — done, "
        "it appears in your Spotify account</li>"
        "</ol>"
        "</div>",
        unsafe_allow_html=True,
    )

    st.markdown(
        "<div style='background:#1a1a1a;border:1px solid #F5A623;border-radius:8px;"
        "padding:10px 16px;margin-top:8px;'>"
        "<span style='color:#B3B3B3;font-size:0.78rem;'>"
        "⏱️ <b style='color:#F5A623;'>Heads up</b> — "
        "playlists created via Spotlistr can take <b style='color:#FFFFFF;'>up to 5 minutes</b> "
        "to appear in your Spotify app. If it's not there yet, just wait a bit and refresh."
        "</span>"
        "</div>",
        unsafe_allow_html=True,
    )

    st.markdown(
        "<div style='background:#1a1a1a;border:1px solid #333;border-radius:8px;"
        "padding:10px 16px;margin-top:8px;'>"
        "<span style='color:#B3B3B3;font-size:0.78rem;'>"
        "ℹ️ <b style='color:#FFFFFF;'>Why Spotlistr?</b> "
        "Since November 2023, Spotify restricts new apps to 5 authenticated users "
        "in development mode. Until this app receives extended quota approval, "
        "playlist creation goes through Spotlistr — a free third-party service. "
        "Your Spotify login stays between you and Spotlistr — "
        "this app never sees your credentials."
        "</span>"
        "</div>",
        unsafe_allow_html=True,
    )

    # Fallback text area in case clipboard fails
    with st.expander("📋 Can't copy? Get the text here", expanded=False):
        st.text_area(
            "Paste this into Spotlistr:",
            artist_song_list,
            height=200,
            key=f"{key_prefix}_artistsong",
        )

    # Other export options
    with st.expander("Other export options", expanded=False):
        df = pd.DataFrame(tracks)
        if st.download_button(
            "📥 Download as CSV",
            df.to_csv(index=False),
            f"{playlist_name}.csv",
            "text/csv",
            use_container_width=True,
            key=f"{key_prefix}_csv_dl",
        ) and on_export:
            on_export(n_tracks=len(tracks))
        url_string = "\n".join(
            f"https://open.spotify.com/track/{t['id']}" for t in tracks
        )
        st.text_area(
            "Spotify URLs (clickable):",
            url_string,
            height=200,
            key=f"{key_prefix}_urls",
        )

    log_export_event(playlist_name, len(tracks))


# ── Live enrichment (Streamlit flow) ─────────────────────────────────────────

def enrich_tracks_live(
    tracks: list[dict],
    progress_callback=None,
) -> tuple[list[dict], list[dict]]:
    """
    Enrich a list of raw Spotify track dicts with ReccoBeats audio features.
    Calls _fetch and _map_fields from pipeline/enrich.py directly.

    Returns (enriched, failed) where:
      - enriched: list of track dicts with audio feature keys merged in
      - failed:   list of {name, artists, playlist_name} for tracks with no features

    progress_callback: optional callable(current_int, total_int) called after each track.
    Rate: 1 second per track (mirrors _RATE_LIMIT in enrich.py).
    """
    import time
    from pipeline.enrich import _fetch, _map_fields

    enriched: list[dict] = []
    failed: list[dict] = []
    total = len(tracks)

    for i, track in enumerate(tracks, start=1):
        spotify_id = track["id"]

        try:
            raw, status = _fetch(spotify_id)
        except Exception:
            failed.append({
                "name":          track.get("name", ""),
                "artists":       track.get("artists", ""),
                "playlist_name": track.get("playlist_name", ""),
            })
            time.sleep(1)
            if progress_callback:
                progress_callback(i, total)
            continue

        if status == "skip":
            # ReccoBeats doesn't have this track — not a failure, just unavailable
            time.sleep(1)
            if progress_callback:
                progress_callback(i, total)
            continue

        if status == "fail" or raw is None:
            failed.append({
                "name":          track.get("name", ""),
                "artists":       track.get("artists", ""),
                "playlist_name": track.get("playlist_name", ""),
            })
            time.sleep(1)
            if progress_callback:
                progress_callback(i, total)
            continue

        mapped = _map_fields(spotify_id, raw)
        if mapped is None:
            failed.append({
                "name":          track.get("name", ""),
                "artists":       track.get("artists", ""),
                "playlist_name": track.get("playlist_name", ""),
            })
            time.sleep(1)
            if progress_callback:
                progress_callback(i, total)
            continue

        # Merge audio features into track dict; skip spotify_id (we already have "id")
        enriched_track = {**track, **{k: v for k, v in mapped.items() if k != "spotify_id"}}
        enriched.append(enriched_track)

        time.sleep(1)
        if progress_callback:
            progress_callback(i, total)

    return enriched, failed
