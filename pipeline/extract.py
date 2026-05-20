"""
pipeline/extract.py
Spotify data extraction: auth, playlist metadata, tracks, and artists.
"""

import logging
import os
import time
from pathlib import Path

import pandas as pd
import yaml
import spotipy
from dotenv import load_dotenv
from spotipy.oauth2 import SpotifyOAuth

logger = logging.getLogger(__name__)


# ── Auth ──────────────────────────────────────────────────────────────────────

def authenticate_spotify(
    env_path: str | Path | None = None,
    cache_path: str | Path = ".spotify_token_cache",
) -> spotipy.Spotify:
    """
    Load credentials from .env and return an authenticated Spotify client.

    Args:
        env_path:   Path to the .env file. Defaults to the standard dotenv lookup.
        cache_path: Where to store the OAuth token cache file.

    Returns:
        Authenticated spotipy.Spotify instance.
    """
    load_dotenv(env_path)

    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI")

    if not all([client_id, client_secret, redirect_uri]):
        raise EnvironmentError(
            "Missing one or more Spotify credentials: "
            "SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REDIRECT_URI"
        )

    scope = (
        "playlist-read-private "
        "playlist-read-collaborative "
        "user-library-read "
        "user-top-read "
        "user-read-recently-played"
    )

    sp = spotipy.Spotify(
        auth_manager=SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=scope,
            cache_path=str(cache_path),
        )
    )

    user = sp.me()
    logger.info("Authenticated as %s (ID: %s)", user["display_name"], user["id"])
    return sp


# ── Config ────────────────────────────────────────────────────────────────────

def load_playlists_config(config_path: str | Path) -> dict:
    """
    Load playlist definitions from a YAML file.

    Expected YAML structure:
        playlists:
          AQ7:
            id: "6rdSUNnzcQ9NFrconkVDpT"
            market: "AR"
          ...

    Args:
        config_path: Path to the YAML config file.

    Returns:
        Dict mapping playlist key -> {"id": str, "market": str}.
    """
    config_path = Path(config_path)
    with config_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)

    # Support both top-level dict and nested under "playlists" key
    playlists = data.get("playlists", data)
    logger.info("Loaded %d playlists from %s", len(playlists), config_path)
    return playlists


# ── Playlist metadata ─────────────────────────────────────────────────────────

def extract_playlist_metadata(
    sp: spotipy.Spotify,
    playlists: dict,
) -> pd.DataFrame:
    """
    Fetch playlist-level metadata from the Spotify API.

    Args:
        sp:        Authenticated Spotify client.
        playlists: Dict mapping playlist key -> {"id": str, "market": str}.

    Returns:
        DataFrame with one row per playlist.
    """
    logger.info("Extracting playlist metadata for %d playlists", len(playlists))
    user_id = sp.me()["id"]
    records = []

    for i, (name, info) in enumerate(playlists.items()):
        playlist_id = info["id"] if isinstance(info, dict) else info
        try:
            pl = sp.playlist(playlist_id)
            records.append(
                {
                    "playlist_id": playlist_id,
                    "name": name,
                    "description": pl["description"],
                    "owner_id": pl["owner"]["id"],
                    "owner_name": pl["owner"]["display_name"],
                    "is_public": pl["public"],
                    "is_collaborative": pl["collaborative"],
                    "total_tracks": pl["tracks"]["total"],
                    "followers": pl["followers"]["total"],
                    "snapshot_id": pl["snapshot_id"],
                    "is_personal": pl["owner"]["id"] == user_id,
                }
            )
            logger.debug("[%d/%d] %s – OK", i + 1, len(playlists), name)
        except Exception:
            logger.exception("Error fetching metadata for playlist %s", name)

        if i % 5 == 4:
            time.sleep(1)  # rate-limit cushion every 5 requests

    df = pd.DataFrame(records)
    logger.info("Playlist metadata extracted: %d rows", len(df))
    return df


# ── Track / artist extraction ─────────────────────────────────────────────────

def extract_tracks_and_artists(
    sp: spotipy.Spotify,
    playlists: dict,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Extract all tracks and artist data from the given playlists.

    Args:
        sp:        Authenticated Spotify client.
        playlists: Dict mapping playlist key -> {"id": str, "market": str}.

    Returns:
        Tuple of (songs_df, bridge_df, artists_df):
          - songs_df:  One row per track occurrence (SongID is an auto-increment local key).
          - bridge_df: Song ↔ artist relationships (many-to-many bridge).
          - artists_df: Unique artists enriched with Spotify detail (genres, popularity).
    """
    logger.info("Extracting tracks from %d playlists", len(playlists))

    song_rows: list[dict] = []
    bridge_rows: list[dict] = []

    song_id_counter = 1
    artist_id_map: dict[str, int] = {}       # artist name  -> internal id
    artist_spotify_map: dict[str, str] = {}  # artist name  -> Spotify id
    next_artist_id = 1

    for pl_idx, (pl_name, pl_info) in enumerate(playlists.items()):
        if isinstance(pl_info, dict):
            pl_id = pl_info["id"]
            market = pl_info.get("market", "US")
        else:
            pl_id = pl_info
            market = "US"

        logger.info(
            "[%d/%d] Playlist %s (market=%s)",
            pl_idx + 1, len(playlists), pl_name, market,
        )

        # ── Fetch all tracks with pagination ──────────────────────────────────
        try:
            results = sp.playlist_tracks(
                pl_id,
                limit=100,
                market=market,
                fields="items(added_at,added_by,track),next,total",
            )
        except Exception:
            logger.exception("Failed to fetch tracks for playlist %s", pl_name)
            continue

        if not results:
            logger.warning("Empty response for playlist %s – skipping", pl_name)
            continue

        tracks = results.get("items", [])
        offset = 100

        while results.get("next") and offset < 1000:
            time.sleep(0.5)
            try:
                results = sp.playlist_tracks(
                    pl_id,
                    offset=offset,
                    limit=100,
                    market=market,
                    fields="items(added_at,added_by,track),next",
                )
                tracks.extend(results.get("items", []))
                offset += 100
            except Exception:
                logger.exception(
                    "Pagination error for playlist %s at offset %d", pl_name, offset
                )
                break

        logger.info("  %d tracks fetched", len(tracks))

        # ── Process each track ────────────────────────────────────────────────
        for item in tracks:
            track = item.get("track")
            if not track or not track.get("id"):
                continue

            added_by_id = None
            if item.get("added_by"):
                added_by_id = item["added_by"].get("id")

            song_rows.append(
                {
                    "SongID": song_id_counter,
                    "Playlist": pl_name,
                    "Name": track.get("name", "Unknown"),
                    "Album": track.get("album", {}).get("name", "Unknown"),
                    "ReleaseDate": track.get("album", {}).get("release_date"),
                    "Popularity": track.get("popularity", 0),
                    "Duration": round(track.get("duration_ms", 0) / 60_000, 2),
                    "SpotifyID": track.get("id"),
                    "IsLocal": track.get("is_local", False),
                    "AddedAt": item.get("added_at"),
                    "AddedBy": added_by_id,
                }
            )

            for artist_idx, artist in enumerate(track.get("artists", [])):
                a_name = artist.get("name", "Unknown Artist")
                a_spotify_id = artist.get("id")

                if a_name not in artist_spotify_map and a_spotify_id:
                    artist_spotify_map[a_name] = a_spotify_id

                if a_name not in artist_id_map:
                    artist_id_map[a_name] = next_artist_id
                    next_artist_id += 1

                bridge_rows.append(
                    {
                        "SongID": song_id_counter,
                        "ArtistID": artist_id_map[a_name],
                        "SpotifyArtistID": a_spotify_id,
                        "IsPrimary": artist_idx == 0,
                        "ArtistOrder": artist_idx + 1,
                    }
                )

            song_id_counter += 1

        time.sleep(1)  # rate-limit cushion between playlists

    if not song_rows:
        logger.error("No tracks extracted. Check playlist IDs and authentication.")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

    songs_df = pd.DataFrame(song_rows)
    bridge_df = pd.DataFrame(bridge_rows)

    # ── Fetch detailed artist info (batches of 50) ────────────────────────────
    spotify_ids = [sid for sid in artist_spotify_map.values() if sid]
    logger.info("Fetching details for %d unique artists", len(spotify_ids))

    artist_details: dict[str, dict] = {}
    for i in range(0, len(spotify_ids), 50):
        batch = spotify_ids[i : i + 50]
        try:
            resp = sp.artists(batch)
            for a in resp["artists"]:
                if a:
                    artist_details[a["id"]] = {
                        "spotify_id": a["id"],
                        "name": a["name"],
                        "popularity": a.get("popularity", 0),
                        "genres": ", ".join(a.get("genres", [])),
                    }
        except Exception:
            logger.exception(
                "Error fetching artist batch %d–%d", i, i + len(batch)
            )
        time.sleep(0.5)

    artist_rows: list[dict] = []
    for a_name, a_internal_id in artist_id_map.items():
        sp_id = artist_spotify_map.get(a_name)
        if sp_id and sp_id in artist_details:
            d = artist_details[sp_id]
            artist_rows.append(
                {
                    "ArtistID": a_internal_id,
                    "Name": d["name"],
                    "SpotifyID": d["spotify_id"],
                    "Popularity": d["popularity"],
                    "Genres": d["genres"],
                }
            )
        else:
            artist_rows.append(
                {
                    "ArtistID": a_internal_id,
                    "Name": a_name,
                    "SpotifyID": sp_id,
                    "Popularity": 0,
                    "Genres": "",
                }
            )

    artists_df = pd.DataFrame(artist_rows)

    logger.info(
        "Extraction complete: %d songs, %d bridge rows, %d unique artists",
        len(songs_df), len(bridge_df), len(artists_df),
    )
    return songs_df, bridge_df, artists_df
