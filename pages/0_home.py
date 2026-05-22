import html
import logging
import math
import requests
import pandas as pd
import streamlit as st

_log = logging.getLogger(__name__)

from utils import inject_global_css
inject_global_css()
from db.queries import load_playlist_track_counts

import base64
with open("assets/spotify-full-logo/Full_Logo_Green_RGB.svg", "rb") as f:
    img_b64 = base64.b64encode(f.read()).decode()

from utils import inject_sidebar_nav

# Pick up sid set by _Enrich.py on completion
if st.session_state.get("_pending_sid"):
    st.query_params["sid"] = st.session_state.pop("_pending_sid")

# ── YC session restore ────────────────────────────────────────────────────────
# Check session state first (survives page navigation within same session)
# Fall back to URL sid (survives full browser refresh)
from utils import _UUID_RE as _SID_RE
_raw_sid = st.query_params.get("sid", "")
if _raw_sid and not _SID_RE.match(_raw_sid):
    _raw_sid = ""
_sid = st.session_state.get("uc_session_id") or _raw_sid

if (_sid
        and not st.session_state.get("uc_active")
        and not st.session_state.get("_dev_loaded")
        and not st.session_state.get("_adding_playlist")):
    from db.queries import load_uc_session, touch_uc_session
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
        touch_uc_session(_sid)
    else:
        st.session_state["_session_expired"] = True
        st.query_params.pop("sid", None)

# ── DEV MODE — must run before inject_sidebar_nav() ─────────────────────────
from dotenv import load_dotenv
load_dotenv()
import json, os
if (os.getenv("DEV_MODE") == "1"
        and not st.session_state.get("uc_active")
        and not st.session_state.get("_dev_loaded")
        and not st.session_state.get("uc_playlists")):
    _dev_path = "data/dev_collection.json"
    if os.path.exists(_dev_path):
        with open(_dev_path, "r") as f:
            _dev_data = json.load(f)
        st.session_state["uc_enriched"]         = _dev_data["enriched"]
        st.session_state["uc_skipped"]          = _dev_data["skipped"]
        st.session_state["uc_failed"]           = _dev_data.get("failed", [])
        st.session_state["uc_playlists"]        = _dev_data["playlists"]
        st.session_state["uc_active"]           = True
        st.session_state["uc_enrichment_state"] = "idle"
        st.session_state["mode"]                = "🔗 Your Collection"
        st.session_state["_dev_loaded"]         = True

# ── Landing-page deep-link: ?mode=uc → Your Collection, ?mode=demo → Demo ────
_mode_param = st.query_params.get("mode", "")
if _mode_param and not st.session_state.get("mode"):
    if _mode_param == "uc":
        st.session_state["mode"] = "🔗 Your Collection"
    elif _mode_param == "demo":
        st.session_state["mode"] = "🎵 Demo Collection"

inject_sidebar_nav("Home")

# ── site_visit event — once per session ───────────────────────────────────────
if os.getenv("DEV_MODE") != "1":
    _vid = st.session_state.get("visitor_id")
    if _vid and not st.session_state.get(f"_tracked_site_visit_{_vid}"):
        try:
            from db.queries import track_event as _track_event
            _mode_param = st.query_params.get("mode", "")
            _track_event(
                event      = "site_visit",
                page       = "Home",
                session_id = st.session_state.get("uc_session_id", "fc_user"),
                visitor_id = _vid,
                properties = {"referrer": _mode_param} if _mode_param else None,
            )
        except Exception:
            pass
        st.session_state[f"_tracked_site_visit_{_vid}"] = True

# ===========================================================================
# YOUR COLLECTION MODE
# ===========================================================================
if st.session_state.get("mode") == "🔗 Your Collection":

    import spotipy
    from spotify_client import extract_playlist_id, get_spotify_client

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

    _RESET_KEYS = (
        "uc_playlists",
        "uc_enriched",
        "uc_failed",
        "uc_skipped",
        "uc_active",
        "uc_enrichment_state",
        "uc_enrichment_cursor",
        "uc_all_tracks",
        "mode",
        "_dev_loaded",
        "uc_session_id",
        "_pending_sid",
        "_adding_playlist",
    )

    def _do_reset():
        for k in _RESET_KEYS:
            st.session_state.pop(k, None)
        st.query_params.clear()
        # Clear localStorage sid
        import streamlit.components.v1 as _components
        _components.html("""
<script>
localStorage.removeItem('tailorlist_sid');
</script>
""", height=0)

    if st.session_state.pop("_navigate_to_enrich", False):
        st.switch_page("pages/_Enrich.py")

    param_raw = st.query_params.get("playlists", "")
    param_ids = [p.strip() for p in param_raw.split(",") if p.strip()]
    if param_ids:
        existing_ids = {p["id"] for p in st.session_state["uc_playlists"]}
        missing = [pid for pid in param_ids if pid not in existing_ids]
        if missing:
            try:
                sp_r = get_spotify_client()
                for pid in missing:
                    try:
                        info = sp_r.playlist(pid, fields="name,tracks.total,followers")
                        st.session_state["uc_playlists"].append({
                            "id":          pid,
                            "name":        info["name"],
                            "track_count": info["tracks"]["total"],
                            "followers":   info.get("followers", {}).get("total", 0),
                        })
                    except Exception:
                        pass
            except requests.exceptions.ConnectionError:
                st.error("🌐 Couldn't reach Spotify right now. Check your connection and try again.")
            except requests.exceptions.Timeout:
                st.error("⏱️ Spotify took too long to respond. Try again in a moment.")
            except RuntimeError:
                pass

    # ── YC header ─────────────────────────────────────────────────────────────
    st.markdown(f"""
    <div style="padding:0.5rem 0 0.3rem 0;">
      <div style="display:flex;align-items:baseline;gap:12px;">
        <span style="font-size:1.6rem;font-weight:800;color:#FFFFFF;letter-spacing:-0.03em;">
          Tailorlist<span style="color:#8FBF7A;">.</span>
        </span>
        <span style="color:#888;font-size:0.88rem;font-style:italic;">
          Music, made to measure.
        </span>
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(f"""
    <div style="display:flex;align-items:center;justify-content:space-between;padding:0.4rem 0 0.5rem 0;">
      <div>
        <h1 style="color:#FFFFFF;margin:0;font-size:2rem;line-height:1.1;">Your Collection</h1>
        <p style="color:#B3B3B3;font-size:0.9rem;margin:4px 0 0 0;">
          Paste public Spotify playlist links to analyse your music with the same models.
        </p>
      </div>
      <img src="data:image/svg+xml;base64,{img_b64}"
           style="height:28px;width:auto;flex-shrink:0;opacity:0.85;"/>
    </div>
    <hr style="border-color:#333;margin:0 0 1rem 0;"/>
    """, unsafe_allow_html=True)

    _state = st.session_state["uc_enrichment_state"]

    # =========================================================================
    # BRANCH: complete
    # =========================================================================
    if _state == "complete":

        n_enriched  = len(st.session_state["uc_enriched"])
        n_skipped   = len(st.session_state.get("uc_skipped", []))
        n_failed    = len(st.session_state.get("uc_failed", []))
        _active_pl_names = {
            t.get("playlist_name")
            for t in (st.session_state["uc_enriched"]
                      + st.session_state.get("uc_skipped", [])
                      + st.session_state.get("uc_failed", []))
            if t.get("playlist_name")
        }
        # Purge playlists that were queued but never enriched so all downstream
        # checks (duplicate guard, card display, counts) stay accurate.
        if _active_pl_names:
            st.session_state["uc_playlists"] = [
                p for p in st.session_state["uc_playlists"]
                if p["name"] in _active_pl_names
            ]
        n_playlists = len(_active_pl_names) if _active_pl_names else len(st.session_state["uc_playlists"])

        total        = n_enriched + n_skipped + n_failed
        missing_note = f" · {n_skipped + n_failed} without audio features" if (n_skipped + n_failed) else ""
        st.success(f"✅ Your collection is live — {total:,} tracks across {n_playlists} playlist(s){missing_note}.")

        _n_enriched = len(st.session_state.get("uc_enriched", []))
        _n_playlists = n_playlists

        if _n_enriched < 100:
            st.markdown(
                "<div style='background:#1a1a1a;border:1px solid #F5A623;border-radius:10px;"
                "padding:12px 18px;margin-top:12px;'>"
                "<span style='color:#F5A623;font-weight:700;'>💡 Tip — </span>"
                "<span style='color:#FFFFFF;font-size:0.88rem;'>"
                f"You've enriched <b>{_n_enriched} tracks</b> across "
                f"<b>{_n_playlists} playlist(s)</b>. "
                "My Clusters works best with <b>200+ tracks across multiple playlists</b> — "
                "the more variety, the more meaningful the clusters. "
                "Consider going back and adding more playlists before clustering.</span>"
                "</div>",
                unsafe_allow_html=True,
            )
        elif _n_enriched < 200:
            st.markdown(
                "<div style='background:#1a1a1a;border:1px solid #333;border-radius:10px;"
                "padding:12px 18px;margin-top:12px;'>"
                "<span style='color:#B3B3B3;font-size:0.85rem;'>"
                f"💡 You've enriched <b style='color:#FFFFFF;'>{_n_enriched} tracks</b> — "
                "good start. Adding playlists from different genres or eras will give "
                "My Clusters more variety to work with and produce richer groupings."
                "</span>"
                "</div>",
                unsafe_allow_html=True,
            )

        st.markdown("#### ✅ Enrichment complete!")
        c1, c2, c3 = st.columns(3)
        c1.metric("🎵 Tracks enriched", f"{n_enriched:,}")
        c2.metric("⚠️ Not found", f"{n_skipped:,}", help="Not found in ReccoBeats or fallback database. ~15% is normal.")
        if n_failed:
            c3.metric("❌ Failed (API errors)", f"{n_failed:,}")

        if n_skipped > 0:
            with st.expander("📋 Skipped tracks — assign to clusters manually"):
                st.dataframe(
                    pd.DataFrame(st.session_state["uc_skipped"])[["name","artists","playlist_name"]],
                    use_container_width=True, hide_index=True)
        if n_failed > 0:
            with st.expander(f"❌ {n_failed} tracks failed (API errors)"):
                st.dataframe(
                    pd.DataFrame(st.session_state["uc_failed"])[["name","artists","playlist_name"]],
                    use_container_width=True, hide_index=True)

        st.markdown("---")
        if st.button("👉 Explore your collection", type="primary",
                use_container_width=True, key="uc_go"):
            st.session_state["uc_enrichment_state"] = "idle"
            st.rerun()
        st.markdown("---")
        if st.session_state.get("_url_add_error_complete"):
            st.error(st.session_state.pop("_url_add_error_complete"))
        url_input_c = st.text_input("Add another playlist",
                                    placeholder="https://open.spotify.com/playlist/...",
                                    key=f"uc_url_input_complete_{st.session_state['uc_url_counter']}")
        st.caption("Any public user-created playlist works. Spotify editorial playlists will not load.")

        if st.button("Add playlist", type="primary", key="uc_add_complete"):
            pid = extract_playlist_id(url_input_c) if url_input_c.strip() else None
            if not pid:
                st.session_state["_url_add_error_complete"] = "❌ Invalid URL."
                st.session_state["uc_url_counter"] += 1
                st.rerun()
            elif pid in {p["id"] for p in st.session_state["uc_playlists"]}:
                st.warning("Already added.")
            else:
                try:
                    info = get_spotify_client().playlist(pid, fields="name,tracks.total,followers")
                    st.session_state["uc_playlists"].append({
                        "id":          pid,
                        "name":        info["name"],
                        "track_count": info["tracks"]["total"],
                        "followers":   info.get("followers", {}).get("total", 0),
                    })
                    st.query_params["playlists"] = ",".join(
                        p["id"] for p in st.session_state["uc_playlists"])
                    st.session_state["_adding_playlist"] = True
                    st.session_state["uc_active"] = False
                    st.session_state["uc_enrichment_state"] = "idle"
                    st.rerun()
                except requests.exceptions.ConnectionError:
                    st.error("🌐 Couldn't reach Spotify right now. Check your connection and try again.")
                except requests.exceptions.Timeout:
                    st.error("⏱️ Spotify took too long to respond. Try again in a moment.")
                except spotipy.SpotifyException as e:
                    _log.warning("Spotify error adding playlist: %s", e)
                    st.session_state["_url_add_error_complete"] = (
                        "❌ Playlist not found. Spotify editorial playlists are not accessible — "
                        "copy their tracks into your own playlist first."
                        if e.http_status == 404 else "❌ Could not load playlist. Please try again.")
                    st.session_state["uc_url_counter"] += 1
                    st.rerun()
                except RuntimeError as e:
                    _log.warning("Runtime error adding playlist: %s", e)
                    st.session_state["_url_add_error_complete"] = "❌ Could not load playlist. Please check the URL and try again."
                    st.session_state["uc_url_counter"] += 1
                    st.rerun()

        for pl in list(st.session_state["uc_playlists"]):
            col_card, col_btn = st.columns([9, 1])
            with col_card:
                st.markdown(
                    f"<div style='background:#282828;border-radius:10px;padding:10px 16px;"
                    f"border:1px solid #333;margin-top:8px;'>"
                    f"<b style='color:#FFF;'>{html.escape(pl['name'])}</b>"
                    f"&nbsp;<span style='color:#1DB954;font-size:0.82rem;'>{int(pl['track_count'])} tracks</span>"
                    f"<span style='color:#888;font-size:0.78rem;'> · {html.escape(pl['id'])}</span></div>",
                    unsafe_allow_html=True)
            with col_btn:
                st.markdown("<div style='margin-top:16px;'>", unsafe_allow_html=True)
                if st.button("✕", key=f"uc_rm_complete_{pl['id']}", type="secondary"):
                    st.session_state["uc_playlists"] = [
                        p for p in st.session_state["uc_playlists"] if p["id"] != pl["id"]]
                    remaining = [p["id"] for p in st.session_state["uc_playlists"]]
                    st.query_params["playlists"] = ",".join(remaining) if remaining else ""
                    if not remaining:
                        st.query_params.clear()
                        for k in ("uc_enriched", "uc_failed", "uc_skipped",
                                  "uc_active", "uc_enrichment_state",
                                  "uc_enrichment_cursor", "uc_all_tracks", "mode"):
                            st.session_state.pop(k, None)
                    else:
                        st.session_state["uc_active"] = False
                        st.session_state["uc_enrichment_state"] = "idle"
                    st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("---")
        if st.button("🗑️ Start over with different playlists", type="tertiary",
                     use_container_width=True, key="uc_reset_complete"):
            _do_reset()
            st.rerun()

    # =========================================================================
    # BRANCH: confirm
    # =========================================================================
    elif _state == "confirm":

        total_t  = sum(p["track_count"] for p in st.session_state["uc_playlists"])
        n_pl     = len(st.session_state["uc_playlists"])
        already_ids = {t.get("id") or t.get("track_id") for t in st.session_state["uc_enriched"]}
        new_tracks = total_t - len(already_ids)
        new_tracks = max(new_tracks, 1)
        est_min  = math.ceil(new_tracks / 26)

        st.markdown("#### Ready to enrich?")

        for pl in st.session_state["uc_playlists"]:
            st.markdown(
                f"<div style='background:#282828;border-radius:10px;padding:10px 16px;"
                f"border:1px solid #333;margin-top:8px;'>"
                f"<b style='color:#FFF;'>{html.escape(pl['name'])}</b>"
                f"&nbsp;<span style='color:#1DB954;font-size:0.82rem;'>{int(pl['track_count'])} tracks</span>"
                f"</div>", unsafe_allow_html=True)

        st.markdown(f"""
        <div style="background:#1a1a2e;border:1px solid #333;border-radius:10px;
                    padding:16px 20px;margin:16px 0;">
          <p style="color:#FFF;font-size:0.95rem;margin:0 0 8px 0;">
            <b>{n_pl} playlist(s) · {total_t:,} total tracks · ~{est_min} min for new tracks</b>
          </p>
          <p style="color:#B3B3B3;font-size:0.85rem;margin:0;">
            ⚠️ Once enrichment starts you <b>cannot add or remove playlists</b>.
            You'll need to start over if you want to change them.
          </p>
        </div>
        """, unsafe_allow_html=True)

        st.info(
            "🎵 **What happens during enrichment?**\n\n"
            "We send each track to the ReccoBeats API to recover audio features "
            "(energy, valence, tempo, danceability, etc.). "
            "ReccoBeats typically recovers ~85% of tracks.\n\n"
            "**Tracks without audio features** will still appear in Overview, Playlist Detail, "
            "and Comparison — but will be excluded from K-Means clustering and Audio DNA.\n\n"
            "**Good news:** once clustering finishes, you can manually assign skipped tracks "
            "to any cluster you like."
        )

        st.markdown("---")

        _c1, _c2 = st.columns(2)
        with _c1:
            if st.button("🎵 Start Enrichment", type="primary",
                         use_container_width=True, key="uc_confirm_start"):
                st.session_state["_navigate_to_enrich"] = True
                st.rerun()
        with _c2:
            if st.button("← Edit playlists", type="secondary",
                         use_container_width=True, key="uc_confirm_back"):
                st.session_state["uc_enrichment_state"] = "idle"
                st.rerun()

    # =========================================================================
    # BRANCH: idle
    # =========================================================================
    else:

        # ── Active collection — enrichment done, show summary and nav ────────
        if st.session_state.get("uc_active") and st.session_state.get("uc_enriched"):
            n_enriched  = len(st.session_state["uc_enriched"])
            n_skipped   = len(st.session_state.get("uc_skipped", []))
            n_failed    = len(st.session_state.get("uc_failed", []))
            _active_pl_names = {
                t.get("playlist_name")
                for t in (st.session_state["uc_enriched"]
                          + st.session_state.get("uc_skipped", [])
                          + st.session_state.get("uc_failed", []))
                if t.get("playlist_name")
            }
            # Remove playlists that were queued but never enriched (e.g. cancelled
            # before any tracks were processed) so duplicate checks stay accurate.
            if _active_pl_names:
                st.session_state["uc_playlists"] = [
                    p for p in st.session_state["uc_playlists"]
                    if p["name"] in _active_pl_names
                ]
            n_playlists = len(_active_pl_names) if _active_pl_names else len(st.session_state["uc_playlists"])

            # Unique counts via set operations on Spotify track IDs
            _enriched_ids = {t["id"] for t in st.session_state["uc_enriched"] if t.get("id")}
            _unenriched_all = st.session_state.get("uc_skipped", []) + st.session_state.get("uc_failed", [])
            _unenriched_unique_ids = {t["id"] for t in _unenriched_all if t.get("id")} - _enriched_ids
            n_unique_with_af    = len(_enriched_ids)
            n_unique_without_af = len(_unenriched_unique_ids)
            total = n_unique_with_af + n_unique_without_af

            # Dupe accounting
            _uc_playlists_meta  = st.session_state.get("uc_playlists", [])
            _spotify_total_home = sum(pl.get("track_count", 0) for pl in _uc_playlists_meta)
            _n_raw              = n_enriched + n_skipped + n_failed
            _cross_dupes        = max(0, _n_raw - total)
            _intra_dupes        = max(0, _spotify_total_home - _n_raw)
            _total_dupes        = _cross_dupes + _intra_dupes
            _dupe_parts = []
            if _cross_dupes > 0:
                _dupe_parts.append(f"{_cross_dupes} across playlists")
            if _intra_dupes > 0:
                _dupe_parts.append(f"{_intra_dupes} within same playlist")
            _dupe_note_home = (
                f' · <span style="color:#888;">'
                + f"{_total_dupes} duplicate(s) not counted"
                + (f" ({', '.join(_dupe_parts)})" if _dupe_parts else "")
                + "</span>"
            ) if _total_dupes > 0 else ""

            st.markdown(f"""
            <div style="background:#1a2e1a;border:1px solid #1DB954;border-radius:12px;
                        padding:24px 28px;margin-bottom:1.5rem;">
              <div style="color:#1DB954;font-size:1.5rem;font-weight:800;margin-bottom:4px;">
                ✅ Your collection is live
              </div>
              <div style="color:#FFFFFF;font-size:1rem;margin-bottom:12px;">
                {total:,} tracks across {n_playlists} playlist(s) ·
                <span style="color:#1DB954;">{n_unique_with_af:,} with audio features</span>
                {f' · <span style="color:#B3B3B3;">{n_unique_without_af} without</span>' if n_unique_without_af else ''}
                {_dupe_note_home}
              </div>
              <p style="color:#B3B3B3;font-size:0.88rem;margin:0;">
                Use the sidebar to explore — Overview, Playlist Detail, Audio DNA and more.
              </p>
            </div>
            """, unsafe_allow_html=True)

            st.markdown("""
<div style="background:#1a2e1a;border:1px solid #1DB954;border-radius:10px;
            padding:14px 18px;margin:12px 0;">
  <div style="display:flex;align-items:center;gap:10px;">
    <span style="font-size:1.2rem;">🔖</span>
    <div>
      <div style="color:#1DB954;font-weight:700;font-size:0.9rem;">
        Bookmark this page to return to your collection
      </div>
      <div style="color:#B3B3B3;font-size:0.82rem;margin-top:3px;">
        Your session is saved for 7 days. The URL contains your session ID —
        bookmark it now and your collection will be here when you come back.
        Don't share the URL with others.
      </div>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

            st.markdown("---")

            with st.expander("➕ Add another playlist to your collection"):
                if st.session_state.get("_url_add_error_active"):
                    st.error(st.session_state.pop("_url_add_error_active"))
                url_input = st.text_input(
                    "Playlist URL",
                    placeholder="https://open.spotify.com/playlist/...",
                    key=f"uc_url_input_active_{st.session_state['uc_url_counter']}")
                st.caption(
                    "Adding a playlist **won't reset your collection** — "
                    "only the new tracks will be enriched. "
                    "Previously enriched tracks are preserved."
                )
                if st.button("Add playlist", type="primary", key="uc_add_active"):
                    pid = extract_playlist_id(url_input) if url_input.strip() else None
                    if not pid:
                        st.session_state["_url_add_error_active"] = "❌ Invalid URL."
                        st.session_state["uc_url_counter"] += 1
                        st.rerun()
                    elif pid in {p["id"] for p in st.session_state["uc_playlists"]}:
                        st.warning("Already added.")
                    else:
                        try:
                            info = get_spotify_client().playlist(pid, fields="name,tracks.total,followers")
                            st.session_state["uc_playlists"].append({
                                "id":          pid,
                                "name":        info["name"],
                                "track_count": info["tracks"]["total"],
                                "followers":   info.get("followers", {}).get("total", 0),
                            })
                            st.query_params["playlists"] = ",".join(
                                p["id"] for p in st.session_state["uc_playlists"])
                            st.session_state["_adding_playlist"] = True  # prevent restore
                            st.session_state["uc_active"] = False
                            st.session_state["uc_enrichment_state"] = "idle"
                            # Update persisted session with new playlist list
                            if st.session_state.get("uc_session_id"):
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
                            st.rerun()
                        except requests.exceptions.ConnectionError:
                            st.error("🌐 Couldn't reach Spotify right now. Check your connection and try again.")
                        except requests.exceptions.Timeout:
                            st.error("⏱️ Spotify took too long to respond. Try again in a moment.")
                        except spotipy.SpotifyException as e:
                            _log.warning("Spotify error adding playlist: %s", e)
                            st.session_state["_url_add_error_active"] = (
                                "❌ Playlist not found. Spotify editorial playlists are not accessible — "
                                "copy their tracks into your own playlist first."
                                if e.http_status == 404 else "❌ Could not load playlist. Please try again.")
                            st.session_state["uc_url_counter"] += 1
                            st.rerun()
                        except RuntimeError as e:
                            _log.warning("Runtime error adding playlist: %s", e)
                            st.session_state["_url_add_error_active"] = "❌ Could not load playlist. Please check the URL and try again."
                            st.session_state["uc_url_counter"] += 1
                            st.rerun()

            # DEV — remove before deploy
            import json, os
            from dotenv import load_dotenv
            load_dotenv()
            if os.getenv("DEV_MODE") == "1":
                if st.button("💾 Save as dev collection", type="secondary", key="dev_save"):
                    data = {
                        "enriched":  st.session_state["uc_enriched"],
                        "skipped":   st.session_state.get("uc_skipped", []),
                        "failed":    st.session_state.get("uc_failed", []),
                        "playlists": st.session_state["uc_playlists"],
                    }
                    with open("data/dev_collection.json", "w") as f:
                        json.dump(data, f, indent=2, default=str)
                    st.success(f"✅ Saved {len(data['enriched'])} enriched tracks to data/dev_collection.json")
            st.markdown("---")
            if st.button("🗑️ Delete my session data", type="secondary",
                         key="uc_delete_session"):
                if st.session_state.get("uc_session_id"):
                    from db.queries import get_engine
                    from sqlalchemy import text
                    try:
                        with get_engine().begin() as conn:
                            conn.execute(
                                text("DELETE FROM uc_sessions WHERE session_id = :sid"),
                                {"sid": st.session_state["uc_session_id"]}
                            )
                            conn.execute(
                                text("DELETE FROM user_cluster_progress WHERE user_key = :uk"),
                                {"uk": st.session_state["uc_session_id"]}
                            )
                    except Exception:
                        pass
                import streamlit.components.v1 as _components
                _components.html("""
<script>
localStorage.removeItem('tailorlist_sid');
</script>
""", height=0)
                _do_reset()
                st.rerun()
            if st.button("🗑️ Start over with different playlists", type="tertiary",
                         use_container_width=True, key="uc_reset_active"):
                _do_reset()
                st.rerun()

        else:

            # ── Interrupted warning ──────────────────────────────────────────
            if st.session_state["uc_enriched"] and st.session_state["uc_playlists"] and not st.session_state.get("uc_active"):
                st.warning(
                    f"⚠️ Enrichment was interrupted. "
                    f"Your {len(st.session_state['uc_enriched']):,} previously enriched tracks are safe. "
                    f"Click **Review & Start** to process remaining tracks.")
            elif st.session_state["uc_enriched"] and not st.session_state.get("uc_active"):
                st.info(f"ℹ️ {len(st.session_state['uc_enriched']):,} tracks already enriched — "
                        f"only new tracks will be processed.")

            if st.session_state.get("_url_add_error"):
                st.error(st.session_state.pop("_url_add_error"))
            url_input = st.text_input(
                "Paste a Spotify playlist URL",
                placeholder="https://open.spotify.com/playlist/...",
                key=f"uc_url_input_{st.session_state['uc_url_counter']}")
            st.caption("Any public user-created playlist works. Spotify editorial playlists will not load.")

            if st.button("Add playlist", type="primary", key="uc_add"):
                pid = extract_playlist_id(url_input) if url_input.strip() else None
                if not pid:
                    st.session_state["_url_add_error"] = "❌ Invalid URL. Paste a link from open.spotify.com/playlist/…"
                    st.session_state["uc_url_counter"] += 1
                    st.rerun()
                elif pid in {p["id"] for p in st.session_state["uc_playlists"]}:
                    st.warning("Already added.")
                else:
                    try:
                        info = get_spotify_client().playlist(pid, fields="name,tracks.total,followers")
                        st.session_state["uc_playlists"].append({
                            "id":          pid,
                            "name":        info["name"],
                            "track_count": info["tracks"]["total"],
                            "followers":   info.get("followers", {}).get("total", 0),
                        })
                        st.query_params["playlists"] = ",".join(
                            p["id"] for p in st.session_state["uc_playlists"])
                        st.session_state["uc_url_counter"] += 1
                        st.rerun()
                    except requests.exceptions.ConnectionError:
                        st.error("🌐 Couldn't reach Spotify right now. Check your connection and try again.")
                    except requests.exceptions.Timeout:
                        st.error("⏱️ Spotify took too long to respond. Try again in a moment.")
                    except spotipy.SpotifyException as e:
                        _log.warning("Spotify error adding playlist: %s", e)
                        st.session_state["_url_add_error"] = (
                            "❌ Playlist not found. Spotify editorial playlists are not accessible — "
                            "copy their tracks into your own playlist first."
                            if e.http_status == 404 else "❌ Could not load playlist. Please try again.")
                        st.session_state["uc_url_counter"] += 1
                        st.rerun()
                    except RuntimeError as e:
                        _log.warning("Runtime error adding playlist: %s", e)
                        st.session_state["_url_add_error"] = "❌ Could not load playlist. Please check the URL and try again."
                        st.session_state["uc_url_counter"] += 1
                        st.rerun()

            for pl in list(st.session_state["uc_playlists"]):
                col_card, col_btn = st.columns([9, 1])
                with col_card:
                    st.markdown(
                        f"<div style='background:#282828;border-radius:10px;padding:10px 16px;"
                        f"border:1px solid #333;margin-top:8px;'>"
                        f"<b style='color:#FFF;'>{html.escape(pl['name'])}</b>"
                        f"&nbsp;<span style='color:#1DB954;font-size:0.82rem;'>{int(pl['track_count'])} tracks</span>"
                        f"<span style='color:#888;font-size:0.78rem;'> · {html.escape(pl['id'])}</span></div>",
                        unsafe_allow_html=True)
                with col_btn:
                    st.markdown("<div style='margin-top:16px;'>", unsafe_allow_html=True)
                    if st.button("✕", key=f"uc_rm_{pl['id']}", type="secondary"):
                        st.session_state["uc_playlists"] = [
                            p for p in st.session_state["uc_playlists"] if p["id"] != pl["id"]]
                        remaining = [p["id"] for p in st.session_state["uc_playlists"]]
                        st.query_params["playlists"] = ",".join(remaining) if remaining else ""
                        if not remaining:
                            st.query_params.clear()
                            for k in ("uc_enriched", "uc_failed", "uc_skipped",
                                      "uc_active", "uc_enrichment_state",
                                      "uc_enrichment_cursor", "uc_all_tracks", "mode"):
                                st.session_state.pop(k, None)
                        st.rerun()
                    st.markdown("</div>", unsafe_allow_html=True)

            st.markdown("---")

            _c1, _c2 = st.columns(2)
            with _c1:
                if st.button("🎵 Review & Start", type="primary",
                             use_container_width=True, key="uc_review",
                             disabled=not bool(st.session_state["uc_playlists"])):
                    st.session_state["uc_enrichment_state"] = "confirm"
                    st.rerun()
            with _c2:
                if st.button("🗑️ Reset", type="secondary",
                             use_container_width=True, key="uc_reset",
                             disabled=not (st.session_state["uc_playlists"]
                                           or st.session_state["uc_enriched"])):
                    _do_reset()
                    st.rerun()

# ===========================================================================
# DEMO COLLECTION MODE
# ===========================================================================
else:

    # ── Expired session banner ───────────────────────────────────────────────
    if st.session_state.pop("_session_expired", False):
        st.markdown("""
<div style="background:#2a1a1a;border:1px solid #7f3333;border-radius:10px;
            padding:14px 18px;margin-bottom:1.2rem;display:flex;align-items:center;gap:12px;">
  <span style="font-size:1.3rem;">⏳</span>
  <div>
    <div style="color:#ff6b6b;font-weight:700;font-size:0.95rem;margin-bottom:3px;">
      Session expired
    </div>
    <div style="color:#c9a0a0;font-size:0.85rem;line-height:1.5;">
      Saved sessions last 7 days. Switch to <b style="color:#FFF;">Your Collection</b>
      in the sidebar and paste your playlist URLs to reload your collection.
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

    # ── Tailorlist branded header ─────────────────────────────────────────────
    st.markdown(f"""
    <div style="background:linear-gradient(135deg,#1a1a1a 0%,#111 100%);
                border:1px solid #2a2a2a;border-radius:14px;
                padding:28px 32px 24px 32px;margin-bottom:1.2rem;">
      <div style="display:flex;align-items:baseline;gap:12px;margin-bottom:6px;">
        <span style="font-size:2rem;font-weight:800;color:#FFFFFF;letter-spacing:-0.03em;">
          Tailorlist<span style="color:#8FBF7A;">.</span>
        </span>
        <span style="color:#888;font-size:0.95rem;font-style:italic;">
          Music, made to measure.
        </span>
      </div>
      <p style="color:#B3B3B3;font-size:0.9rem;margin:0;line-height:1.55;">
        Explore a curated demo collection — playlists, clusters, audio fingerprints,
        and everything the platform can do. Switch to <b style="color:#FFF;">Your Collection</b>
        in the sidebar to analyse your own music.
      </p>
    </div>
    """, unsafe_allow_html=True)

    # ── Feature cards ─────────────────────────────────────────────────────────
    st.markdown("""
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:1.2rem;">

      <div style="background:#1c1c1c;border-radius:12px;padding:20px 22px;
                  border:1px solid #2a2a2a;">
        <div style="font-size:1.5rem;margin-bottom:10px;">📊</div>
        <div style="color:#FFFFFF;font-size:1.05rem;font-weight:700;margin-bottom:6px;">
          Explore
        </div>
        <p style="color:#999;font-size:0.82rem;line-height:1.55;margin:0;">
          Overview, Playlist Detail, Artist / Album, and Playlist Comparison
          break down the collection by size, era, popularity, and audio character.
        </p>
      </div>

      <div style="background:#1c1c1c;border-radius:12px;padding:20px 22px;
                  border:1px solid #2a2a2a;">
        <div style="font-size:1.5rem;margin-bottom:10px;">🔵</div>
        <div style="color:#FFFFFF;font-size:1.05rem;font-weight:700;margin-bottom:6px;">
          Cluster & Export
        </div>
        <p style="color:#999;font-size:0.82rem;line-height:1.55;margin:0;">
          Audio DNA reveals your sonic fingerprint. My Clusters groups tracks
          by sound — filter by genre and decade, then export clusters directly
          to your Spotify account.
        </p>
      </div>

    </div>
    """, unsafe_allow_html=True)

    with st.expander("ℹ️ About this app & known limitations", expanded=False):
        st.markdown(
            """
**What is Tailorlist?**
A Spotify playlist analytics platform built with Streamlit, scikit-learn, and the Spotify API.
It analyzes audio features (energy, valence, danceability, tempo, acousticness, speechiness)
to cluster tracks, compare playlists, and help reorganize music collections.
Clusters can be exported directly to your Spotify account as new playlists.

**Your Collection mode**
When you enrich your own Spotify playlists, audio features are fetched via the
[ReccoBeats API](https://reccobeats.com). Coverage isn't 100% — some tracks
(especially obscure or very new releases) may not have features available and
will be excluded from clustering.

**Data privacy**
Your Collection data is stored temporarily in a session tied to your browser URL.
Sessions expire after 7 days. No personal data is stored beyond what's needed
to power the analysis.

**Built by**
Facundo Rabinovich — Systems Engineer transitioning into Data Science.
[Ko-fi](https://ko-fi.com/facurabs) · [Cafecito](https://cafecito.app/facurabs)
            """,
            unsafe_allow_html=True,
        )

    # ── Powered by Spotify ────────────────────────────────────────────────────
    st.markdown(f"""
    <div style="display:flex;align-items:center;gap:10px;
                padding:10px 16px;margin-top:0.8rem;margin-bottom:1.2rem;
                background:#161616;border:1px solid #2a2a2a;border-radius:10px;">
      <span style="color:#888;font-size:0.8rem;white-space:nowrap;">Powered by</span>
      <img src="data:image/svg+xml;base64,{img_b64}"
           style="height:22px;width:auto;flex-shrink:0;"/>
    </div>
    """, unsafe_allow_html=True)

    # ── Bottom footer ─────────────────────────────────────────────────────────
    st.markdown("""
    <div style="text-align:center;padding:20px 0 8px 0;margin-top:0.5rem;
                border-top:1px solid #2a2a2a;">
      <p style="color:#555;font-size:0.75rem;margin:0;line-height:1.6;">
        Built with Streamlit · MySQL · scikit-learn · Plotly<br/>
        <a href="https://github.com/facurabinovich" style="color:#1DB954;text-decoration:none;">
          github.com/facurabinovich
        </a>
      </p>
    </div>
    """, unsafe_allow_html=True)