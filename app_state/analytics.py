"""Analytics entry points for ui/ — wraps db so ui/ never imports db/."""
import streamlit as st

from db.analytics import log_export_event  # noqa: F401  (re-exported for ui/export.py)


def track_page_view(page: str) -> None:
    """Log a page_view once per (page, visitor). Caller handles DEV_MODE and errors."""
    from db.queries import track_event
    _session    = st.session_state.get("uc_session_id", "fc_user")
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
