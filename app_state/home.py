"""Session-state flow of the Home page (Your Collection).

Everything here reads or writes ``st.session_state`` / ``st.query_params`` for the Home
page: restoring a collection from its sid, loading the dev collection, queueing playlists,
removing them and resetting. Pure decisions live in core/home.py; widgets and HTML stay in
pages/0_home.py.
"""
from __future__ import annotations

import json
import os

import streamlit as st

from app_state.session import (
    apply_restored_session, forget_uc_session, mark_uc_session_unavailable, needs_restore,
)
from config import is_dev_mode
from core.home import (
    dev_collection_state, missing_playlist_ids, parse_playlist_param, playlist_entry,
    playlists_query_value,
)

DEV_COLLECTION_PATH = "data/dev_collection.json"

#: Session keys cleared by a full reset ("Reset", "Start over", "Delete my session data").
RESET_KEYS = (
    "uc_playlists",
    "uc_enriched",
    "uc_failed",
    "uc_skipped",
    "uc_active",
    "uc_enrichment_state",
    "uc_enrichment_cursor",
    "uc_all_tracks",
    "_dev_loaded",
    "uc_session_id",
    "_pending_sid",
    "_adding_playlist",
)

#: Collection keys cleared when the last playlist is removed (playlists are already empty).
_LAST_PLAYLIST_KEYS = ("uc_enriched", "uc_failed", "uc_skipped",
                       "uc_active", "uc_enrichment_state",
                       "uc_enrichment_cursor", "uc_all_tracks",
                       "uc_session_id")


def adopt_pending_sid() -> None:
    """Pick up the sid the Enrich page left in ``_pending_sid`` and put it in the URL."""
    if st.session_state.get("_pending_sid"):
        st.query_params["sid"] = st.session_state.pop("_pending_sid")


def restore_from_sid(sid: str) -> None:
    """Load the persisted YC session for ``sid`` into session state (Home only).

    Same trigger as the sidebar's restore (see app_state.session.needs_restore) but, unlike
    it, a DB exception is not caught, the session is touched (last-seen) outside dev mode,
    and an empty lookup raises the one-shot ``_session_expired`` banner flag.
    """
    if needs_restore(sid):
        from db.queries import load_uc_session, touch_uc_session
        session = load_uc_session(sid)
        if session:
            apply_restored_session(session, sid)
            if not is_dev_mode():
                touch_uc_session(sid)
        else:
            st.session_state["_session_expired"] = True
            st.query_params.pop("sid", None)
            # Stop retrying this session. The cookie is deliberately left alone:
            # load_uc_session() also returns None when the DB is unreachable, and
            # deleting it then would lose the collection for good.
            mark_uc_session_unavailable()


def load_dev_collection() -> None:
    """In dev mode with an empty page, load data/dev_collection.json as the collection."""
    if (is_dev_mode()
            and not st.session_state.get("uc_active")
            and not st.session_state.get("_dev_loaded")
            and not st.session_state.get("uc_playlists")):
        if os.path.exists(DEV_COLLECTION_PATH):
            with open(DEV_COLLECTION_PATH, "r") as f:
                dev = dev_collection_state(json.load(f))
            st.session_state["uc_enriched"]         = dev["enriched"]
            st.session_state["uc_skipped"]          = dev["skipped"]
            st.session_state["uc_failed"]           = dev["failed"]
            st.session_state["uc_playlists"]        = dev["playlists"]
            st.session_state["uc_active"]           = True
            st.session_state["uc_enrichment_state"] = "idle"
            st.session_state["_dev_loaded"]         = True


def track_site_visit() -> None:
    """Record the ``site_visit`` analytics event once per visitor session (not in dev mode)."""
    if not is_dev_mode():
        _vid = st.session_state.get("visitor_id")
        if _vid and not st.session_state.get(f"_tracked_site_visit_{_vid}"):
            try:
                from db.queries import track_event as _track_event
                _mode_param = st.query_params.get("mode", "")
                _track_event(
                    event      = "site_visit",
                    page       = "Home",
                    session_id = st.session_state.get("uc_session_id", "anonymous"),
                    visitor_id = _vid,
                    properties = {"referrer": _mode_param} if _mode_param else None,
                )
            except Exception:
                pass
            st.session_state[f"_tracked_site_visit_{_vid}"] = True


def init_defaults() -> None:
    """Default values of the YC session keys, and a sane enrichment state."""
    for _k, _v in [
        ("uc_playlists",         []),
        ("uc_enriched",          []),
        ("uc_failed",            []),
        ("uc_skipped",           []),
        ("uc_active",            False),
        ("uc_enrichment_state",  "idle"),
        ("uc_url_counter",       0),
    ]:
        if _k not in st.session_state:
            st.session_state[_k] = _v

    if st.session_state["uc_enrichment_state"] not in ("idle", "confirm", "complete"):
        st.session_state["uc_enrichment_state"] = "idle"


def reset_keys() -> None:
    """Drop the collection from session and URL and stop the sid cookie restoring it.

    forget_uc_session() makes the next sidebar render delete the cookie; the script below
    also clears the browser-side copies right away.
    """
    for k in RESET_KEYS:
        st.session_state.pop(k, None)
    st.query_params.clear()
    # Stop the sid cookie from pulling this visitor back into the
    # collection they just reset (inject_sidebar_nav deletes it)
    forget_uc_session()


def queue_playlists_from_url(get_client) -> None:
    """Queue the playlists named in ``?playlists=`` that are not queued yet.

    ``get_client`` returns a Spotify client (called only when something is missing, so
    connection/timeout/runtime errors surface here for the page to report). A playlist
    that cannot be fetched is skipped silently.
    """
    param_ids = parse_playlist_param(st.query_params.get("playlists", ""))
    if param_ids:
        missing = missing_playlist_ids(param_ids, st.session_state["uc_playlists"])
        if missing:
            sp_r = get_client()
            for pid in missing:
                try:
                    info = sp_r.playlist(pid, fields="name,tracks.total,followers")
                    st.session_state["uc_playlists"].append(playlist_entry(pid, info))
                except Exception:
                    pass


def append_playlist(pid: str, info: dict) -> None:
    """Queue a playlist from its Spotify response and mirror the queue in ``?playlists=``."""
    st.session_state["uc_playlists"].append(playlist_entry(pid, info))
    st.query_params["playlists"] = playlists_query_value(st.session_state["uc_playlists"])


def remove_playlist(pl_id: str, deactivate_if_remaining: bool) -> None:
    """Remove a queued playlist and update the URL (the caller reruns).

    Removing the last one drops the whole collection (and forgets the sid). Otherwise, when
    ``deactivate_if_remaining`` is set (the "complete" view), the collection is marked
    inactive so the remaining playlists can be re-enriched.
    """
    st.session_state["uc_playlists"] = [
        p for p in st.session_state["uc_playlists"] if p["id"] != pl_id]
    remaining = [p["id"] for p in st.session_state["uc_playlists"]]
    st.query_params["playlists"] = ",".join(remaining) if remaining else ""
    if not remaining:
        st.query_params.clear()
        for k in _LAST_PLAYLIST_KEYS:
            st.session_state.pop(k, None)
        forget_uc_session()   # don't restore it from the cookie
    elif deactivate_if_remaining:
        st.session_state["uc_active"] = False
        st.session_state["uc_enrichment_state"] = "idle"


def save_dev_collection() -> int:
    """Write the current collection to data/dev_collection.json; returns the enriched count."""
    data = {
        "enriched":  st.session_state["uc_enriched"],
        "skipped":   st.session_state.get("uc_skipped", []),
        "failed":    st.session_state.get("uc_failed", []),
        "playlists": st.session_state["uc_playlists"],
    }
    with open(DEV_COLLECTION_PATH, "w") as f:
        json.dump(data, f, indent=2, default=str)
    return len(data["enriched"])


def persist_after_adding_playlist() -> None:
    """After adding a playlist to a live collection, save the new playlist list to the DB.

    Only with a session id and outside dev mode; failures are ignored.
    """
    if st.session_state.get("uc_session_id") and not is_dev_mode():
        try:
            from db.queries import save_uc_session
            save_uc_session(
                session_id = st.session_state["uc_session_id"],
                enriched   = st.session_state.get("uc_enriched", []),
                skipped    = st.session_state.get("uc_skipped", []),
                failed     = st.session_state.get("uc_failed", []),
                playlists  = st.session_state.get("uc_playlists", []),
            )
        except Exception:
            pass
