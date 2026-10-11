"""Collection routing: Demo Collection (DB loaders) vs Your Collection (session data).

The only place that reads session_state to decide where tracks come from. The
YC record normalization itself lives in core/tracks.py.
"""
import pandas as pd
import streamlit as st

from app_state.session import MODE_YC
from core.tracks import yc_tracks_frame
from db.tracks import (
    load_tracks, load_all_tracks, load_cluster_data, load_audio_features_by_playlist,
)


def _yc_active() -> bool:
    """True when the user's own collection (with enriched tracks) is the data source."""
    return bool(st.session_state.get("mode") == MODE_YC
                and st.session_state.get("uc_active")
                and st.session_state.get("uc_enriched"))


def get_all_tracks() -> pd.DataFrame:
    """
    Universal loader for ALL tracks including those without audio features.
    Use this for Overview, Playlist Detail, Comparison — anywhere counts/stats matter.
    Use get_tracks() only where audio features are required (Audio DNA, Clusters).
    """
    if _yc_active():
        return yc_tracks_frame(
            st.session_state["uc_enriched"],
            st.session_state.get("uc_skipped", []),
            st.session_state.get("uc_failed", []),
            include_unenriched=True,
        )
    return load_all_tracks()


def get_tracks() -> pd.DataFrame:
    """
    Universal data loader. Returns enriched tracks from session state
    when user collection is active, otherwise loads from DB.
    All pages should call this instead of load_tracks().
    """
    if _yc_active():
        return yc_tracks_frame(st.session_state["uc_enriched"], include_unenriched=False)
    return load_tracks()


def get_cluster_data() -> pd.DataFrame:
    if _yc_active():
        df = get_tracks()
        cols = [c for c in ["track_id", "track_name", "artist_name", "artist_display", "playlist_name",
                            "energy", "acousticness", "valence", "tempo", "danceability"] if c in df.columns]
        return df[cols].dropna(
                   subset=["energy", "acousticness", "valence", "tempo", "danceability"])
    # Side effect preserved exactly from the pre-T12 wrapper: clears ALL st.cache_data
    # (not just this loader) on every Demo Collection call.
    st.cache_data.clear()  # bust cache when switching back to Demo Collection
    return load_cluster_data()


def get_audio_features_by_playlist() -> pd.DataFrame:
    """Routes to session state or DB based on mode."""
    if _yc_active():
        df = get_tracks()
        return df.groupby("playlist_name")[
            ["energy","acousticness","valence","tempo",
             "danceability","loudness","instrumentalness",
             "speechiness","liveness"]
        ].mean().reset_index()
    return load_audio_features_by_playlist()
