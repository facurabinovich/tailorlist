import uuid as _uuid
import streamlit as st

from config import is_dev_mode
from app_state.session import resolve_sid, mark_uc_session_unavailable, _UUID_RE, MODE_YC

# YC sessions expire server-side 7 days after creation (see load_uc_session)
_SID_COOKIE_MAX_AGE = 7 * 24 * 60 * 60


def inject_sidebar_nav(page: str = "Home"):
    import streamlit as st
    import os

    # ── Visitor ID ───────────────────────────────────────────────────────────
    # Stable across browser sessions via a first-party cookie, so analytics can
    # tell a returning visitor from a new one. The cookie is written by the JS
    # below and read back here on the next page load.
    # Why a cookie and not localStorage: Streamlit renders components in an
    # iframe sandboxed WITHOUT allow-top-navigation, so JS in there cannot
    # redirect the top window to hand a stored value back to Python. It does
    # have allow-same-origin, so a cookie set there is sent with the next
    # request and shows up in st.context.cookies.
    _vid = st.session_state.get("visitor_id")
    if not _vid:
        _cookie_vid = ""
        try:
            _cookie_vid = st.context.cookies.get("tailorlist_vid") or ""
        except Exception:
            pass    # older Streamlit without st.context — degrade to per-session
        _vid = _cookie_vid if _UUID_RE.match(_cookie_vid) else str(_uuid.uuid4())
        st.session_state["visitor_id"] = _vid

    # ── sid + visitor-id cookies ─────────────────────────────────────────────
    # The sid cookie mirrors Python's view of the session: write it while there
    # is one, delete it once the visitor drops it. Any sid still sitting in
    # localStorage came from the old redirect-based scheme that the iframe
    # sandbox blocked, so migrate it across the first time we see it.
    _sid_state = st.session_state.get("uc_session_id", "")
    if _sid_state and _UUID_RE.match(_sid_state):
        # A live session supersedes an earlier "forgotten" marker, so starting a
        # fresh enrichment re-establishes the cookie instead of staying deleted
        st.session_state.pop("_sid_forgotten", None)
    _sid_now = resolve_sid()
    if st.session_state.get("_sid_forgotten"):
        # Only a deliberate drop deletes the cookie — see forget_uc_session()
        _sid_js = "document.cookie = 'tailorlist_sid=;path=/;max-age=0';"
    elif _sid_now:
        _sid_js = (
            f"document.cookie = 'tailorlist_sid={_sid_now}'"
            f" + ';path=/;max-age={_SID_COOKIE_MAX_AGE};SameSite=Lax';"
        )
    else:
        _sid_js = (
            "const legacySid = localStorage.getItem('tailorlist_sid');\n"
            "        if (legacySid && UUID_RE.test(legacySid)) {\n"
            "            document.cookie = 'tailorlist_sid=' + legacySid"
            f" + ';path=/;max-age={_SID_COOKIE_MAX_AGE};SameSite=Lax';\n"
            "        }"
        )

    import streamlit.components.v1 as _components
    _components.html(f"""
<script>
(function() {{
    // We're inside an iframe — need to work with parent window
    try {{
        const UUID_RE = /^[0-9a-f]{{8}}-[0-9a-f]{{4}}-4[0-9a-f]{{3}}-[89ab][0-9a-f]{{3}}-[0-9a-f]{{12}}$/i;

        // ── sid — YC session, so a bookmarked URL can recover the collection
        {_sid_js}

        // ── vid — analytics visitor id, in a 1-year first-party cookie.
        // Written only when missing or malformed, so the id stays sticky and
        // Python (st.context.cookies) always sees a value it will accept.
        const match = document.cookie.match(/(?:^|;\\s*)tailorlist_vid=([^;]*)/);
        const cookieVid = match ? decodeURIComponent(match[1]) : '';
        if (!UUID_RE.test(cookieVid)) {{
            document.cookie = 'tailorlist_vid={_vid}'
                            + ';path=/;max-age=31536000;SameSite=Lax';
        }}
    }} catch(e) {{
        // Cross-origin or other error — silently fail
        console.warn('tailorlist state restore failed:', e);
    }}
}})();
</script>
""", height=0)

    # ── Session restore on any page refresh ──────────────────────────────────
    # resolve_sid() already rejects malformed values before any DB lookup, and
    # falls back to the cookie so a bookmarked URL still finds the collection.
    _sid = resolve_sid()
    if (_sid
            and not st.session_state.get("uc_active")
            and not st.session_state.get("_dev_loaded")
            and not st.session_state.get("_adding_playlist")):
        from app_state.session import load_uc_session
        try:
            _session = load_uc_session(_sid)
            if _session:
                st.session_state["uc_enriched"]         = _session["enriched"]
                st.session_state["uc_skipped"]          = _session["skipped"]
                st.session_state["uc_failed"]           = _session["failed"]
                st.session_state["uc_playlists"]        = _session["playlists"]
                st.session_state["uc_active"]           = True
                st.session_state["uc_enrichment_state"] = "idle"
                st.session_state["uc_session_id"]       = _sid
                st.session_state["mode"]                = MODE_YC
            else:
                # Expired, or the DB was unreachable — stop retrying this run,
                # but keep the cookie so a transient outage isn't permanent
                mark_uc_session_unavailable()
                st.query_params.pop("sid", None)
        except Exception:
            pass

    # Preserve session ID in URL across all page navigations
    _sid = st.session_state.get("uc_session_id", "")
    if _sid and st.query_params.get("sid", "") != _sid:
        st.query_params["sid"] = _sid

    # ── Analytics tracking ────────────────────────────────────────────────────────
    if not is_dev_mode():
        try:
            from app_state.analytics import track_page_view
            track_page_view(page)
        except Exception:
            pass

    # The app only has Your Collection now. setdefault semantics (not an
    # overwrite): nothing sets FC anymore; the FC branches still in pages are
    # removed in R2/R3.
    if not st.session_state.get("mode"):
        st.session_state["mode"] = MODE_YC

    with st.sidebar:
        st.page_link("pages/0_home.py", label="🏠 Home")
        st.page_link("pages/1_Overview.py", label="📊 Overview")
        st.page_link("pages/2_Playlist_Detail.py", label="📖 Playlist Detail")
        st.page_link("pages/3_Artist_Album.py", label="🎤 Artist / Album")
        st.page_link("pages/4_Playlist_Comparison.py", label="💿 Playlist Comparison")
        st.page_link("pages/5_Audio_DNA.py", label="🧬 Audio DNA")
        st.page_link("pages/6_My_Clusters.py", label="🎛️ My Clusters")
        st.page_link("pages/7_Glossary.py", label="ℹ️ Glossary")
        st.page_link("pages/8_Contact.py", label="✉️ Contact")

        st.markdown("---")
        st.markdown(
            "<p style='color:#666;font-size:0.72rem;margin:0 0 6px 0;'>Support this project</p>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<div style='display:flex;gap:6px;'>"
            "<a href='https://ko-fi.com/tailorlist' target='_blank'"
            "   style='flex:1;text-align:center;background:#FF5E5B;color:#FFF;"
            "          font-size:0.75rem;font-weight:700;padding:6px 0;"
            "          border-radius:8px;text-decoration:none;display:block;'>"
            "☕ Ko-fi</a>"
            "<a href='https://cafecito.app/tailorlist' target='_blank'"
            "   style='flex:1;text-align:center;background:#6F3DE9;color:#FFF;"
            "          font-size:0.75rem;font-weight:700;padding:6px 0;"
            "          border-radius:8px;text-decoration:none;display:block;'>"
            "☕ Cafecito</a>"
            "</div>",
            unsafe_allow_html=True,
        )

        import os
        if is_dev_mode():
            import streamlit as st
            from spotify.client import get_spotify_oauth_client
            st.sidebar.markdown("---")
            st.sidebar.markdown("**🎵 Spotify Export**")
            if st.sidebar.button("🔗 Connect Spotify", key="connect_spotify_sidebar"):
                sp = get_spotify_oauth_client()
                if sp:
                    try:
                        user = sp.current_user()
                        st.session_state["sp_oauth"] = sp
                        st.session_state["sp_user"] = user["display_name"]
                    except Exception:
                        st.session_state.pop("sp_oauth", None)
            if st.session_state.get("sp_user"):
                st.sidebar.success(f"✓ {st.session_state['sp_user']}")
            if st.session_state.get("sp_oauth") and st.sidebar.button(
                "🔌 Disconnect", key="disconnect_spotify_sidebar"
            ):
                st.session_state.pop("sp_oauth", None)
                st.session_state.pop("sp_user", None)
                import pathlib
                pathlib.Path(".spotify_cache").unlink(missing_ok=True)


def check_collection_mode() -> bool:
    """
    Call at the top of every page after inject_sidebar_nav().
    If mode is Your Collection but no data exists yet, shows a prompt and returns False.
    Pages should exit early if this returns False.
    Returns True if the page should render normally.
    """
    import streamlit as st
    if (st.session_state.get("mode") == MODE_YC
            and not st.session_state.get("uc_active")):
        st.markdown("""
        <div style="display:flex;flex-direction:column;align-items:center;
                    justify-content:center;padding:4rem 2rem;text-align:center;">
          <div style="font-size:3rem;margin-bottom:1rem;">🔗</div>
          <h2 style="color:#FFFFFF;margin-bottom:0.5rem;">No collection yet</h2>
          <p style="color:#B3B3B3;font-size:0.95rem;max-width:400px;">
            You haven't enriched a collection yet.
            Head to Home to paste your Spotify playlist links and get started.
          </p>
        </div>
        """, unsafe_allow_html=True)
        if st.button("→ Go to Home", type="primary", key="go_home_prompt"):
            st.switch_page("pages/0_home.py")
        return False
    return True