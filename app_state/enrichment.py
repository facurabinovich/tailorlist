"""Session-state flow of the Enrich page (the Your Collection enrichment run).

Reads/writes the ``uc_*`` session keys and the persistence/analytics side effects of a run.
The decisions themselves are pure and live in core/enrichment.py; the ReccoBeats and
fallback lookups live in spotify/reccobeats.py. Widgets, HTML and navigation stay in the page.

Session keys owned here:
  uc_enriched / uc_skipped / uc_failed   result lists (enriched survives runs; the other two
                                          are reset at the start of each run)
  uc_all_tracks                           tracks pending in this run
  uc_enrichment_cursor                    index of the next track to process
  _enrich_start_time                      time.time() when the run started (for the ETA)
  _enrich_run_started / _enrichment_start_tracked / _pre_enrich_snapshot   run flags
"""
from __future__ import annotations

import time

import streamlit as st

from config import is_dev_mode
from core.enrichment import (
    classify_fetch, enriched_record, pending_tracks, playlist_set_key,
    pre_enrich_snapshot, unenriched_record,
)


def track_enrichment_start() -> None:
    """Record the ``enrichment_start`` analytics event once per run (never in dev mode).

    Uses a hash of the playlist ids as session id because uc_session_id is not set yet;
    complete_enrichment() back-fills the real one. Failures are swallowed.
    """
    if not is_dev_mode() and not st.session_state.get("_enrichment_start_tracked"):
        try:
            from db.analytics import track_event
            track_event(
                event      = "enrichment_start",
                page       = "Enrich",
                session_id = playlist_set_key(st.session_state.get("uc_playlists", [])),
                visitor_id = st.session_state.get("visitor_id"),
            )
            st.session_state["_enrichment_start_tracked"] = True
        except Exception:
            pass


def init_run_state() -> None:
    """Prepare the lists for a run: keep uc_enriched, reset skipped/failed once per run."""
    if "uc_enriched" not in st.session_state:
        st.session_state["uc_enriched"] = []
    if not st.session_state.get("_enrich_run_started"):
        st.session_state["uc_skipped"]          = []
        st.session_state["uc_failed"]           = []
        st.session_state["_enrich_run_started"] = True


def set_pending_tracks(all_tracks: list[dict]) -> None:
    """Store the tracks still to enrich (see core.enrichment.pending_tracks) and start the clock."""
    st.session_state["uc_all_tracks"] = pending_tracks(
        all_tracks,
        st.session_state["uc_enriched"],
        st.session_state.get("uc_skipped", []),
    )
    st.session_state["uc_enrichment_cursor"] = 0
    st.session_state["_enrich_start_time"] = time.time()


def take_snapshot_once(to_enrich: list[dict]) -> None:
    """Store the cancel-restore snapshot the first time it is needed in this run."""
    if "_pre_enrich_snapshot" not in st.session_state:
        st.session_state["_pre_enrich_snapshot"] = pre_enrich_snapshot(
            to_enrich,
            st.session_state.get("uc_playlists", []),
            st.session_state.get("uc_enriched", []),
            st.session_state.get("uc_session_id"),
        )


def complete_enrichment() -> None:
    """Close a finished run: flags, session id, MySQL save and completion analytics.

    Afterwards the page navigates Home; ``_pending_sid`` hands the sid over to Home's URL.
    Persistence and analytics are skipped in dev mode and never raise.
    """
    st.session_state["uc_enrichment_state"] = "complete"
    st.session_state["uc_active"] = True
    st.session_state.pop("uc_all_tracks", None)
    st.session_state.pop("_enrich_run_started", None)
    st.session_state.pop("_enrichment_start_tracked", None)
    st.session_state.pop("_pre_enrich_snapshot", None)
    st.session_state.pop("_enrich_start_time", None)

    import uuid
    from db.sessions import save_uc_session

    # Generate session ID if not already set
    if not st.session_state.get("uc_session_id"):
        st.session_state["uc_session_id"] = str(uuid.uuid4())

    # Persist YC session to MySQL (skipped in DEV_MODE)
    if not is_dev_mode():
        try:
            save_uc_session(
                session_id = st.session_state["uc_session_id"],
                enriched   = st.session_state.get("uc_enriched", []),
                skipped    = st.session_state.get("uc_skipped", []),
                failed     = st.session_state.get("uc_failed", []),
                playlists  = st.session_state.get("uc_playlists", []),
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("Failed to save YC session: %s", e)

    # Track enrichment completion
    if not is_dev_mode():
        try:
            from db.analytics import track_event
            from db.analytics import backfill_enrichment_session
            _real_sid = st.session_state.get("uc_session_id")
            track_event(
                event      = "enrichment_complete",
                page       = "Enrich",
                session_id = _real_sid,
                visitor_id = st.session_state.get("visitor_id"),
            )
            # Backfill the enrichment_start row with the real session_id
            backfill_enrichment_session(
                _real_sid,
                playlist_set_key(st.session_state.get("uc_playlists", [])),
            )
        except Exception:
            pass

    st.session_state["_pending_sid"] = st.session_state["uc_session_id"]


_CANCEL_CLEAR_KEYS = (
    "uc_playlists", "uc_enriched", "uc_failed", "uc_skipped",
    "uc_active", "uc_enrichment_state", "uc_enrichment_cursor",
    "uc_all_tracks", "_enrich_run_started", "_enrichment_start_tracked",
    "uc_session_id", "_enrich_start_time",
)


def cancel_enrichment() -> None:
    """Abort the run: clear its state and restore the previously enriched collection, if any.

    Prefers reloading the previous session from the database (so skipped/failed come back
    too), else falls back to the in-memory snapshot. The page then navigates Home.
    """
    _snapshot = st.session_state.pop("_pre_enrich_snapshot", None)

    # Always clear current-run state
    for k in _CANCEL_CLEAR_KEYS:
        st.session_state.pop(k, None)
    st.query_params.clear()

    # If there was a previously-enriched collection, restore it
    _prev_enriched  = _snapshot.get("enriched")   if _snapshot else None
    _prev_playlists = _snapshot.get("playlists")  if _snapshot else None
    _prev_sid       = _snapshot.get("session_id") if _snapshot else None

    if _prev_enriched or _prev_sid:
        # Prefer reloading from DB so skipped/failed are also restored
        _restored = False
        if _prev_sid:
            try:
                from db.sessions import load_uc_session
                _db_session = load_uc_session(_prev_sid)
                if _db_session:
                    st.session_state["uc_enriched"]          = _db_session["enriched"]
                    st.session_state["uc_skipped"]           = _db_session["skipped"]
                    st.session_state["uc_failed"]            = _db_session["failed"]
                    st.session_state["uc_playlists"]         = _db_session["playlists"]
                    st.session_state["uc_session_id"]        = _prev_sid
                    st.session_state["uc_active"]            = True
                    st.session_state["uc_enrichment_state"]  = "idle"
                    st.query_params["sid"]                   = _prev_sid
                    _restored = True
            except Exception:
                pass

        if not _restored and _prev_enriched:
            # Fall back to in-memory snapshot
            st.session_state["uc_enriched"]         = _prev_enriched
            st.session_state["uc_playlists"]        = _prev_playlists or []
            st.session_state["uc_active"]           = True
            st.session_state["uc_enrichment_state"] = "idle"


def process_track(track: dict) -> None:
    """Fetch the audio features of one track and store the outcome in the session lists.

    ReccoBeats first (an exception counts as failed); on "skip" the fallback DB is tried
    before the track is recorded as skipped. The caller sleeps, advances the cursor and reruns.
    """
    from spotify.reccobeats import (
        fetch_audio_features as _fetch,
        fetch_fallback_features as _fetch_fallback,
        map_audio_features as _map_fields,
    )
    sid = track["id"]

    try:
        raw_data, status = _fetch(sid)
    except Exception:
        st.session_state["uc_failed"].append(unenriched_record(track))
        return

    outcome = classify_fetch(status, raw_data)
    if outcome == "skip":
        fallback = _fetch_fallback(sid)
        if fallback is not None:
            st.session_state["uc_enriched"].append(enriched_record(track, fallback))
        else:
            st.session_state["uc_skipped"].append(unenriched_record(track))
    elif outcome == "fail":
        st.session_state["uc_failed"].append(unenriched_record(track))
    else:
        mapped = _map_fields(sid, raw_data)
        if mapped is None:
            st.session_state["uc_failed"].append(unenriched_record(track))
        else:
            st.session_state["uc_enriched"].append(
                enriched_record(track, mapped, drop_keys=("spotify_id",)))
