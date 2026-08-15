import re as _re
import uuid as _uuid
import streamlit as st

import base64 as _base64

_UUID_RE = _re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
    _re.IGNORECASE,
)

# YC sessions expire server-side 7 days after creation (see load_uc_session)
_SID_COOKIE_MAX_AGE = 7 * 24 * 60 * 60


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
with open("assets/spotify-logo-icon/Primary_Logo_Green_RGB.svg", "rb") as _f:
    _SPOTIFY_ICON_B64 = _base64.b64encode(_f.read()).decode()


def spotify_icon_html(size: int = 36) -> str:
    """Returns the official Spotify green icon as an HTML img tag."""
    return (
        f'<img src="data:image/svg+xml;base64,{_SPOTIFY_ICON_B64}" '
        f'style="width:{size}px;height:{size}px;flex-shrink:0;"/>'
    )


def page_brand_html() -> str:
    """Right-aligned Tailorlist wordmark to place above every page header."""
    return (
        "<div style='text-align:right;margin-bottom:4px;'>"
        "<span style='font-size:1.6rem;font-weight:800;color:#FFFFFF;"
        "letter-spacing:-0.03em;'>"
        "Tailorlist<span style='color:#8FBF7A;'>.</span>"
        "</span>"
        "<span style='color:#888;font-size:0.88rem;font-style:italic;margin-left:10px;'>"
        "Music, made to measure."
        "</span>"
        "</div>"
    )


def inject_global_css():
    st.markdown("""
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=DM+Mono:wght@400;500&display=swap');

      :root {
        --spotify-green:   #1DB954;
        --spotify-black:   #121212;
        --spotify-dark:    #181818;
        --spotify-card:    #282828;
        --spotify-subtle:  #333333;
        --spotify-white:   #FFFFFF;
        --spotify-grey:    #B3B3B3;
      }

      html, body, [data-testid="stAppViewContainer"] {
        background-color: #121212 !important;
        color: #FFFFFF !important;
        font-family: 'Plus Jakarta Sans', sans-serif !important;
      }

      [data-testid="stSidebar"] {
        background-color: #181818 !important;
        border-right: 1px solid #333333;
      }

      [data-testid="stSidebarNav"] a {
        color: #B3B3B3 !important;
        font-weight: 500;
        transition: color 0.2s;
      }
      [data-testid="stSidebarNav"] a:hover,
      [data-testid="stSidebarNav"] a[aria-selected="true"] {
        color: #1DB954 !important;
      }

      [data-testid="stMetric"] {
        background-color: #282828;
        border-radius: 12px;
        padding: 16px 20px;
        border: 1px solid #333333;
      }
      [data-testid="stMetricLabel"] { color: #B3B3B3 !important; font-size: 0.75rem; }
      [data-testid="stMetricValue"] { color: #FFFFFF !important; font-weight: 700; }

      [data-testid="stSelectbox"] > div,
      [data-testid="stMultiSelect"] > div {
        background-color: #282828 !important;
        border: 1px solid #333333 !important;
        border-radius: 8px !important;
        color: #FFFFFF !important;
      }

      /* kind="primary" → green */
      button[kind="primary"] {
        background-color: #1DB954 !important;
        color: #121212 !important;
        font-weight: 700 !important;
        border: none !important;
        border-radius: 50px !important;
        padding: 10px 28px !important;
        transition: transform 0.15s, opacity 0.15s;
      }
      button[kind="primary"]:hover {
        opacity: 0.88 !important;
        transform: scale(1.03);
      }

      /* kind="secondary" → grey (✕ remove buttons) */
      button[kind="secondary"] {
        background-color: #333333 !important;
        color: #B3B3B3 !important;
        border: 1px solid #444444 !important;
        border-radius: 50px !important;
        font-weight: 600 !important;
      }
      button[kind="secondary"]:hover {
        background-color: #444444 !important;
        color: #ffffff !important;
        opacity: 1 !important;
        transform: none !important;
      }

      /* kind="tertiary" → RED (destructive reset buttons) */
      button[kind="tertiary"] {
        background-color: #c0392b !important;
        color: #ffffff !important;
        font-weight: 700 !important;
        border: none !important;
        border-radius: 50px !important;
        padding: 10px 28px !important;
        width: 100% !important;
        transition: background-color 0.15s, transform 0.15s;
      }
      button[kind="tertiary"]:hover {
        background-color: #e53935 !important;
        transform: scale(1.02);
        opacity: 1 !important;
      }

      [data-testid="stDataFrame"] { border-radius: 12px; overflow: hidden; }
      hr { border-color: #333333 !important; }

      h1, h2, h3 { font-family: 'Plus Jakarta Sans', sans-serif !important; font-weight: 800 !important; }
      h1 { font-size: 2.4rem !important; }
      h2 { font-size: 1.6rem !important; color: #FFFFFF !important; }
      h3 { font-size: 1.15rem !important; color: #B3B3B3 !important; font-weight: 600 !important; }

      ::-webkit-scrollbar { width: 6px; }
      ::-webkit-scrollbar-track { background: #181818; }
      ::-webkit-scrollbar-thumb { background: #333333; border-radius: 3px; }
      ::-webkit-scrollbar-thumb:hover { background: #1DB954; }

      [data-testid="stMain"] { background-color: #121212 !important; }
      section[data-testid="stSidebarContent"] { background-color: #181818 !important; }
    </style>
    """, unsafe_allow_html=True)


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
        from db.queries import load_uc_session
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
                st.session_state["mode"]                = "🔗 Your Collection"
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
    if os.getenv("DEV_MODE") != "1":
        try:
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
        except Exception:
            pass

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

        _current_mode = st.session_state.get("mode", "🎵 Demo Collection")
        _index = 1 if _current_mode == "🔗 Your Collection" else 0

        mode = st.radio(
            label="collection_mode",
            options=["🎵 Demo Collection", "🔗 Your Collection"],
            label_visibility="collapsed",
            index=_index,
            key="mode_radio",
        )
        st.session_state["mode"] = mode

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
        from dotenv import load_dotenv
        load_dotenv()
        if os.getenv("DEV_MODE", "0") == "1":
            import streamlit as st
            from spotify_client import get_spotify_oauth_client
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
    if (st.session_state.get("mode") == "🔗 Your Collection"
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