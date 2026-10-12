import re as _re
import streamlit as st

_UUID_RE = _re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
    _re.IGNORECASE,
)

def read_cookie(name: str) -> str:
    """Read a cookie, tolerating Streamlit versions without st.context."""
    import streamlit as st
    try:
        return st.context.cookies.get(name) or ""
    except Exception:
        return ""


def resolve_sid() -> str:
    """The YC session id for this visitor: session_state → ?sid= → cookie.

    The cookie is what lets a bookmarked or typed URL recover a collection.
    Component iframes are sandboxed without allow-top-navigation, so JS in
    there cannot put a stored sid back into the URL — it hands it to Python
    through a cookie instead, and the caller writes it back to the URL.

    Returns "" when there is no sid, the value is malformed, the visitor
    dropped their collection (_sid_forgotten), or a lookup for it already
    failed this session (_sid_unavailable).
    """
    import streamlit as st
    candidates = [
        st.session_state.get("uc_session_id", ""),
        st.query_params.get("sid", ""),
    ]
    if not (st.session_state.get("_sid_forgotten")
            or st.session_state.get("_sid_unavailable")):
        candidates.append(read_cookie("tailorlist_sid"))
    for candidate in candidates:
        if candidate and _UUID_RE.match(candidate):
            return candidate
    return ""


def forget_uc_session():
    """Mark the YC session as intentionally dropped by the visitor.

    Stops resolve_sid() from recovering it from the cookie and makes the next
    inject_sidebar_nav() delete that cookie — otherwise a visitor who reset
    their collection would be pulled straight back into it on their next visit.
    Only for deliberate actions (reset, removing the last playlist).
    """
    import streamlit as st
    st.session_state["_sid_forgotten"] = True


def mark_uc_session_unavailable():
    """A lookup for this sid came back empty — stop retrying it this session.

    Deliberately does NOT delete the cookie: load_uc_session() returns None
    both for a genuinely expired session and for a database it could not reach,
    and destroying the visitor's only pointer to their collection over a
    transient outage would be unrecoverable. The cookie ages out on its own.
    """
    import streamlit as st
    st.session_state["_sid_unavailable"] = True


def load_uc_session(session_id: str):
    """Load a persisted YC session (thin wrapper so ui/ never imports db/)."""
    from db.queries import load_uc_session as _load
    return _load(session_id)


def needs_restore(sid: str) -> bool:
    """True when a persisted YC session should be loaded for ``sid``.

    Needs a sid and an empty page state: no active collection, no dev-collection load, and
    not in the middle of adding a playlist (which deliberately deactivates the collection).
    """
    import streamlit as st
    return bool(sid
                and not st.session_state.get("uc_active")
                and not st.session_state.get("_dev_loaded")
                and not st.session_state.get("_adding_playlist"))


def apply_restored_session(session: dict, sid: str) -> None:
    """Put a loaded YC session (as returned by load_uc_session) into session state."""
    import streamlit as st
    st.session_state["uc_enriched"]         = session["enriched"]
    st.session_state["uc_skipped"]          = session["skipped"]
    st.session_state["uc_failed"]           = session["failed"]
    st.session_state["uc_playlists"]        = session["playlists"]
    st.session_state["uc_active"]           = True
    st.session_state["uc_enrichment_state"] = "idle"
    st.session_state["uc_session_id"]       = sid
