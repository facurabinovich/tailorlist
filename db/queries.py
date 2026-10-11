"""Temporary compatibility module (removed in T28).

Holds the session-aware wrappers (they move to app_state/collection.py in T12)
and re-exports everything that moved to db.tracks / db.progress / db.sessions /
db.analytics, so existing `from db.queries import X` and `patch("db.queries.X")`
keep working.
"""
import pandas as pd
import streamlit as st
from db.connection import get_engine
from app_state.session import MODE_YC
from db.tracks import (
    _SECONDARY_ARTISTS_SUBQUERY, _BASE_SQL, _BASE_SQL_ALL,
    _add_artist_display, _parse_release_year,
    load_tracks, load_all_tracks, load_tracks_deduped,
    load_playlist_track_counts, load_top_artists, load_additions_timeline,
    load_audio_features_by_playlist, load_playlist_meta, load_cluster_data,
    load_all_tracks_for_grouping, load_unmatched_tracks,
    load_top_artists_by_popularity, load_top_albums, load_tracks_added_by_month,
)
from db.progress import (
    _ensure_tables, load_cluster_progress, reset_cluster_progress,
    save_cluster_progress, save_cluster_progress_bulk,
)
from db.sessions import save_uc_session, touch_uc_session, load_uc_session
from db.analytics import _migrate_analytics_schema, track_event
from sqlalchemy import text as _text
import json as _json


def get_all_tracks() -> pd.DataFrame:
    """
    Universal loader for ALL tracks including those without audio features.
    Use this for Overview, Playlist Detail, Comparison — anywhere counts/stats matter.
    Use get_tracks() only where audio features are required (Audio DNA, Clusters).
    """
    if (st.session_state.get("mode") == MODE_YC
            and st.session_state.get("uc_active")
            and st.session_state.get("uc_enriched")):
        enriched = pd.DataFrame(st.session_state["uc_enriched"])
        skipped  = pd.DataFrame(st.session_state.get("uc_skipped", []))
        failed   = pd.DataFrame(st.session_state.get("uc_failed", []))

        # Skipped/failed tracks carry real Spotify IDs — keep them.
        # Only generate a synthetic id for rows that genuinely lack one (defensive
        # fallback for any very old session data written before id was stored).
        for _df in [skipped, failed]:
            if not _df.empty and "id" not in _df.columns:
                _df["id"] = _df["name"] + "||" + _df.get("artists", pd.Series(dtype=str)).fillna("")

        frames = [enriched]
        if not skipped.empty:
            frames.append(skipped)
        if not failed.empty:
            frames.append(failed)

        df = pd.concat(frames, ignore_index=True)

        df = df.rename(columns={
            "id":          "track_id",
            "name":        "track_name",
            "artists":     "artist_name",
            "popularity":  "popularity_raw",
            "album":       "album_name",
            "duration_ms": "duration_raw",
        })

        if "release_date" in df.columns:
            df["release_year"] = _parse_release_year(df["release_date"])
            df["decade"] = (df["release_year"] // 10 * 10).where(
                df["release_year"].notna()
            )
        return _add_artist_display(df)
    return load_all_tracks()

def get_tracks() -> pd.DataFrame:
    """
    Universal data loader. Returns enriched tracks from session state
    when user collection is active, otherwise loads from DB.
    All pages should call this instead of load_tracks().
    """
    if (st.session_state.get("mode") == MODE_YC
        and st.session_state.get("uc_active")
        and st.session_state.get("uc_enriched")):
        df = pd.DataFrame(st.session_state["uc_enriched"])
        df = df.rename(columns={
            "id":          "track_id",
            "name":        "track_name",
            "artists":     "artist_name",
            "popularity":  "popularity_raw",
            "album":       "album_name",
            "duration_ms": "duration_raw",
        })
        # Derive release_year and decade from release_date
        if "release_date" in df.columns:
            df["release_year"] = _parse_release_year(df["release_date"])
            df["decade"] = (df["release_year"] // 10 * 10).where(
                df["release_year"].notna()
            )
        return _add_artist_display(df)
    return load_tracks()
def get_cluster_data() -> pd.DataFrame:
    if (st.session_state.get("mode") == MODE_YC
            and st.session_state.get("uc_active")
            and st.session_state.get("uc_enriched")):
        df = get_tracks()
        cols = [c for c in ["track_id", "track_name", "artist_name", "artist_display", "playlist_name",
                            "energy", "acousticness", "valence", "tempo", "danceability"] if c in df.columns]
        return df[cols].dropna(
                   subset=["energy", "acousticness", "valence", "tempo", "danceability"])
    st.cache_data.clear()  # bust cache when switching back to Demo Collection
    return load_cluster_data()

def get_audio_features_by_playlist() -> pd.DataFrame:
    """Routes to session state or DB based on mode."""
    if (st.session_state.get("mode") == MODE_YC
            and st.session_state.get("uc_active")
            and st.session_state.get("uc_enriched")):
        df = get_tracks()
        return df.groupby("playlist_name")[
            ["energy","acousticness","valence","tempo",
             "danceability","loudness","instrumentalness",
             "speechiness","liveness"]
        ].mean().reset_index()
    return load_audio_features_by_playlist()
