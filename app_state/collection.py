"""Your Collection tracks, read from session state.

The only place that reads session_state to decide where tracks come from. The
YC record normalization itself lives in core/tracks.py. This module never
touches the database: with no enriched collection the loaders return an empty
frame (see `_EMPTY_COLUMNS`).
"""
import pandas as pd
import streamlit as st

from core.tracks import yc_tracks_frame

# Columns of the frame returned when there is no enriched collection, so callers
# that index these columns get an empty result instead of a KeyError.
_EMPTY_COLUMNS = ["track_id", "track_name", "artist_name", "artist_display",
                  "album_name", "playlist_name"]


def _yc_active() -> bool:
    """True when the user's own collection (with enriched tracks) is available."""
    return bool(st.session_state.get("uc_active")
                and st.session_state.get("uc_enriched"))


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=_EMPTY_COLUMNS)


def get_all_tracks() -> pd.DataFrame:
    """
    Universal loader for ALL tracks including those without audio features.
    Use this for Overview, Playlist Detail, Comparison — anywhere counts/stats matter.
    Use get_tracks() only where audio features are required (Audio DNA, Clusters).
    Built from session state (enriched + skipped + failed), so a collection where
    no track got audio features still shows its tracks. With no tracks at all it
    returns an empty frame and never touches the database.
    """
    enriched = st.session_state.get("uc_enriched") or []
    skipped  = st.session_state.get("uc_skipped") or []
    failed   = st.session_state.get("uc_failed") or []
    if st.session_state.get("uc_active") and (enriched or skipped or failed):
        return yc_tracks_frame(enriched, skipped, failed, include_unenriched=True)
    return _empty_frame()


def get_tracks() -> pd.DataFrame:
    """
    Enriched tracks (with audio features) from session state.
    All pages should call this instead of querying the database.
    With no enriched collection it returns an empty frame and never touches
    the database.
    """
    if _yc_active():
        return yc_tracks_frame(st.session_state["uc_enriched"], include_unenriched=False)
    return _empty_frame()
