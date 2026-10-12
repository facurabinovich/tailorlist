"""Analytics entry points for ui/ — wraps db so ui/ never imports db/."""
import streamlit as st

from db.analytics import log_export_event  # noqa: F401  (re-exported for ui/export.py)


def track_event(event: str, page: str = None, session_id: str = None,
                visitor_id: str = None, properties: dict = None) -> None:
    """Log an analytics event (thin wrapper so pages never import db/)."""
    from db.analytics import track_event as _track
    _track(event, page=page, session_id=session_id,
           visitor_id=visitor_id, properties=properties)


def track_page_view(page: str) -> None:
    """Log a page_view once per (page, visitor). Caller handles DEV_MODE and errors."""
    from db.analytics import track_event
    _session    = st.session_state.get("uc_session_id", "anonymous")
    _visitor_id = st.session_state.get("visitor_id")
    _track_key  = f"_tracked_{page}_{_visitor_id}"
    if not st.session_state.get(_track_key):
        track_event(
            event      = "page_view",
            page       = page,
            session_id = _session,
            visitor_id = _visitor_id,
        )
        st.session_state[_track_key] = True
