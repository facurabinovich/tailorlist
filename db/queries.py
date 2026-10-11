"""Temporary compatibility module (removed in T28).

Re-exports everything that moved to db.tracks / db.progress / db.sessions /
db.analytics, so existing `from db.queries import X` and `patch("db.queries.X")`
keep working.
"""
from db.connection import get_engine
from core.tracks import add_artist_display as _add_artist_display, parse_release_year as _parse_release_year
# Temporary reverse dependency db -> app_state (the session-aware wrappers live in
# app_state/collection.py since T12); removed in T28 together with this module.
from app_state.collection import (  # noqa: F401
    get_tracks, get_all_tracks, get_cluster_data, get_audio_features_by_playlist,
)
from db.tracks import (
    _SECONDARY_ARTISTS_SUBQUERY, _BASE_SQL, _BASE_SQL_ALL,
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
