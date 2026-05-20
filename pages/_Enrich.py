import time
import math as _math

import streamlit as st
from config import PAGE_CONFIG

st.set_page_config(**PAGE_CONFIG)

from utils import inject_global_css
inject_global_css()

from pipeline.enrich import _fetch, _map_fields, _fetch_fallback
from spotify_client import get_playlist_tracks

import base64
with open("assets/spotify-logo-icon/Primary_Logo_Green_RGB.svg", "rb") as f:
    spotify_icon_b64 = base64.b64encode(f.read()).decode()
with open("assets/recco_logo.svg", "rb") as f:
    recco_b64 = base64.b64encode(f.read()).decode()

# ---------------------------------------------------------------------------
# Guard — redirect if no playlists queued
# ---------------------------------------------------------------------------
if not st.session_state.get("uc_playlists"):
    st.session_state["uc_enrichment_state"] = "idle"
    st.switch_page("pages/0_home.py")

import os
if os.getenv("DEV_MODE") != "1" and not st.session_state.get("_enrichment_start_tracked"):
    try:
        from db.queries import track_event
        # Use uc_playlists hash as a proxy session id since uc_session_id not set yet
        _proxy_sid = str(hash(tuple(
            p["id"] for p in st.session_state.get("uc_playlists", [])
        )))
        track_event(
            event      = "enrichment_start",
            page       = "Enrich",
            session_id = _proxy_sid,
        )
        st.session_state["_enrichment_start_tracked"] = True
    except Exception:
        pass

# uc_enriched is preserved across runs (incremental enrichment)
# uc_skipped and uc_failed are reset each run — they reflect only the current run
if "uc_enriched" not in st.session_state:
    st.session_state["uc_enriched"] = []

# Always reset skipped/failed at the start of a new enrichment run
# Use a flag to ensure we only reset once per run, not on every rerun
if not st.session_state.get("_enrich_run_started"):
    st.session_state["uc_skipped"]         = []
    st.session_state["uc_failed"]          = []
    st.session_state["_enrich_run_started"] = True

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
n_pl = len(st.session_state["uc_playlists"])
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
<div style="display:flex;align-items:center;justify-content:space-between;padding:0.4rem 0 0.5rem 0;">
  <div>
    <h1 style="color:#FFFFFF;margin:0;font-size:2rem;line-height:1.1;">Enriching…</h1>
    <p style="color:#B3B3B3;font-size:0.9rem;margin:4px 0 0 0;">
      Processing {n_pl} playlist(s). Keep this tab open.
    </p>
  </div>
  <div style="display:flex;align-items:center;gap:12px;flex-shrink:0;">
    <img src="data:image/svg+xml;base64,{spotify_icon_b64}"
         style="height:26px;width:auto;opacity:0.85;"/>
    <img src="data:image/svg+xml;base64,{recco_b64}"
         style="height:22px;width:auto;opacity:0.75;"/>
  </div>
</div>
<hr style="border-color:#333;margin:0 0 1rem 0;"/>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Fetch all tracks on first entry
# ---------------------------------------------------------------------------
if "uc_all_tracks" not in st.session_state:
    with st.spinner("Fetching tracks from Spotify…"):
        all_tracks: list[dict] = []
        try:
            for pl in st.session_state["uc_playlists"]:
                raw = get_playlist_tracks(pl["id"])
                for t in raw:
                    t["playlist_name"] = pl["name"]
                all_tracks.extend(raw)
        except Exception as e:
            import requests
            if isinstance(e, requests.exceptions.ConnectionError):
                st.error("🌐 Couldn't reach Spotify. Check your connection and try again.")
            elif isinstance(e, requests.exceptions.Timeout):
                st.error("⏱️ Spotify timed out. Try again in a moment.")
            else:
                st.error("Something went wrong fetching your tracks. Try again.")
            st.stop()
    # IDs already successfully enriched → skip
    enriched_ids = {
        t.get("id") or t.get("track_id")
        for t in st.session_state["uc_enriched"]
    }
    enriched_ids.discard(None)

    # IDs previously skipped (not in ReccoBeats or fallback) → skip again, won't help
    skipped_ids = {
        t.get("name", "") + "||" + t.get("artists", "")
        for t in st.session_state.get("uc_skipped", [])
    }
    # Match skipped by spotify id if available, otherwise by name||artists
    skipped_spotify_ids = {
        t.get("id") or t.get("track_id")
        for t in st.session_state.get("uc_skipped", [])
        if t.get("id") or t.get("track_id")
    }

    # IDs that failed (API errors) → retry these
    # They are NOT excluded so they get another chance

    st.session_state["uc_all_tracks"] = [
        t for t in all_tracks
        if t["id"] not in enriched_ids
        and t["id"] not in skipped_spotify_ids
    ]
    st.session_state["uc_enrichment_cursor"] = 0
    st.session_state["_enrich_start_time"] = time.time()
    st.rerun()

to_enrich = st.session_state["uc_all_tracks"]
cursor    = st.session_state.get("uc_enrichment_cursor", 0)
total     = len(to_enrich)

# ---------------------------------------------------------------------------
# Snapshot pre-enrichment state (taken once, right after uc_all_tracks is set)
# Used by the cancel button to restore a previously-enriched collection
# instead of wiping everything.
# ---------------------------------------------------------------------------
if "_pre_enrich_snapshot" not in st.session_state:
    _new_pl_names = {t.get("playlist_name") for t in to_enrich}
    _old_playlists = [
        p for p in st.session_state.get("uc_playlists", [])
        if p["name"] not in _new_pl_names
    ]
    st.session_state["_pre_enrich_snapshot"] = {
        "enriched":   list(st.session_state.get("uc_enriched", [])),
        "playlists":  _old_playlists,
        "session_id": st.session_state.get("uc_session_id"),
    }

# ---------------------------------------------------------------------------
# Completion — navigate back to Home
# ---------------------------------------------------------------------------
if not to_enrich or cursor >= total:
    st.session_state["uc_enrichment_state"] = "complete"
    st.session_state["uc_active"] = True
    st.session_state.pop("uc_all_tracks", None)
    st.session_state.pop("_enrich_run_started", None)
    st.session_state.pop("_enrichment_start_tracked", None)
    st.session_state.pop("_pre_enrich_snapshot", None)
    st.session_state.pop("_enrich_start_time", None)

    import uuid
    from db.queries import save_uc_session

    # Generate session ID if not already set
    if not st.session_state.get("uc_session_id"):
        st.session_state["uc_session_id"] = str(uuid.uuid4())

    # Persist YC session to MySQL
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
    if os.getenv("DEV_MODE") != "1":
        try:
            from db.queries import track_event, get_engine
            from sqlalchemy import text
            _real_sid = st.session_state.get("uc_session_id")
            track_event(
                event      = "enrichment_complete",
                page       = "Enrich",
                session_id = _real_sid,
            )
            # Backfill the enrichment_start row with the real session_id
            with get_engine().begin() as conn:
                conn.execute(text("""
                    UPDATE app_analytics
                    SET session_id = :sid
                    WHERE event = 'enrichment_start'
                      AND session_id = :proxy
                    ORDER BY created_at DESC
                    LIMIT 1
                """), {
                    "sid":   _real_sid,
                    "proxy": str(hash(tuple(
                        p["id"] for p in st.session_state.get("uc_playlists", [])
                    )))
                })
        except Exception:
            pass

    st.session_state["_pending_sid"] = st.session_state["uc_session_id"]
    st.switch_page("pages/0_home.py")

# ---------------------------------------------------------------------------
# Playlist cards (locked, dimmed)
# ---------------------------------------------------------------------------
for pl in st.session_state["uc_playlists"]:
    st.markdown(
        f"<div style='background:#282828;border-radius:10px;padding:10px 16px;"
        f"border:1px solid #333;margin-top:8px;opacity:0.5;'>"
        f"<b style='color:#FFF;'>{pl['name']}</b>"
        f"&nbsp;<span style='color:#1DB954;font-size:0.82rem;'>{pl['track_count']} tracks</span>"
        f"</div>", unsafe_allow_html=True)

st.markdown("---")

# ---------------------------------------------------------------------------
# Progress
# ---------------------------------------------------------------------------
n_failed_prev = len(st.session_state.get("uc_failed", []))
retry_note = f" (includes {n_failed_prev} retried)" if n_failed_prev else ""
st.progress(cursor / total, text=f"Enriching tracks… {cursor}/{total}{retry_note}")

n_ok   = len(st.session_state["uc_enriched"])
n_skip = len(st.session_state["uc_skipped"])
n_fail = len(st.session_state["uc_failed"])

_start_t = st.session_state.get("_enrich_start_time")
if _start_t and cursor > 0:
    _elapsed = time.time() - _start_t
    _rate    = cursor / _elapsed          # tracks/sec
    _secs_left = (total - cursor) / _rate
    _m, _s   = divmod(int(_secs_left), 60)
    _eta_str = f"~{_m}m {_s}s left" if _m else f"~{_s}s left"
else:
    _eta_str = "estimating…"

st.caption(f"✅ {n_ok}  ⚠️ {n_skip}  ❌ {n_fail} &nbsp;·&nbsp; ⏱ {_eta_str}")

st.markdown("---")

# ---------------------------------------------------------------------------
# Contextual wait message — adapts to elapsed time
# ---------------------------------------------------------------------------
# Use actual observed remaining time if available, else fall back to fixed rate
if _start_t and cursor > 0:
    _est_remaining_min = _secs_left / 60
else:
    _est_remaining_min = (total - cursor) / 26  # ~26 tracks/min empirical

_SHORT_TIPS = [
    ("☕", "Go make a coffee and shuffle your favourite playlist — we'll see if it matches our insights."),
    ("🎧", "Put on some headphones and close your eyes for a track or two. We've got this."),
    ("🛋️", "Kick back, hit shuffle on something you haven't listened to in a while. We'll be ready soon."),
    ("🪴", "Good time to water a plant, stretch a little, or just stare out the window with music on."),
]

_MEDIUM_ALBUMS = [
    ("The Ramones", "Ramones", "~29 min"),
    ("Simon & Garfunkel", "Bookends", "~29 min"),
    ("The Strokes", "Is This It", "~35 min"),
    ("Creedence Clearwater Revival", "Green River", "~29 min"),
    ("The Beach Boys", "Surf's Up", "~38 min"),
    ("David Bowie", "Hunky Dory", "~41 min"),
    ("Vampire Weekend", "Vampire Weekend", "~34 min"),
    ("Daft Punk", "Discovery", "~45 min"),
]

_LONG_ALBUMS = [
    ("Nas", "Illmatic", "1994"),
    ("The Beatles", "Abbey Road", "1969"),
    ("Pink Floyd", "The Dark Side of the Moon", "1973"),
    ("The Rolling Stones", "Sticky Fingers", "1971"),
    ("Radiohead", "OK Computer", "1997"),
    ("Kendrick Lamar", "To Pimp a Butterfly", "2015"),
    ("Amy Winehouse", "Back to Black", "2006"),
    ("Jay-Z", "The Blueprint", "2001"),
]

# Rotate every ~60 seconds (1 track ≈ 1 sec)
_rot = (cursor // 60) % max(len(_SHORT_TIPS), len(_MEDIUM_ALBUMS), len(_LONG_ALBUMS))

if _est_remaining_min < 15:
    _icon, _tip = _SHORT_TIPS[_rot % len(_SHORT_TIPS)]
    st.markdown(
        f"<div style='background:#1a1a1a;border:1px solid #2a2a2a;border-radius:10px;"
        f"padding:14px 18px;margin-bottom:1rem;'>"
        f"<span style='font-size:1.2rem;'>{_icon}</span>"
        f"<span style='color:#B3B3B3;font-size:0.88rem;margin-left:10px;'>{_tip}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )
elif _est_remaining_min < 30:
    _artist, _album, _dur = _MEDIUM_ALBUMS[_rot % len(_MEDIUM_ALBUMS)]
    st.markdown(
        f"<div style='background:#1a1a1a;border:1px solid #2a2a2a;border-radius:10px;"
        f"padding:14px 18px;margin-bottom:1rem;'>"
        f"<div style='color:#FFFFFF;font-size:0.9rem;font-weight:600;margin-bottom:6px;'>"
        f"⏳ Hang in there — this is your chance to listen to this awesome album.</div>"
        f"<div style='color:#1DB954;font-size:0.95rem;font-weight:700;'>{_album}</div>"
        f"<div style='color:#888;font-size:0.82rem;margin-top:2px;'>{_artist} · {_dur}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )
else:
    _artist, _album, _year = _LONG_ALBUMS[_rot % len(_LONG_ALBUMS)]
    st.markdown(
        f"<div style='background:#1a1a2e;border:1px solid #333;border-radius:10px;"
        f"padding:14px 18px;margin-bottom:1rem;'>"
        f"<div style='color:#FFFFFF;font-size:0.9rem;font-weight:600;margin-bottom:6px;'>"
        f"🚀 Looks like you have a big collection — this is exactly what Tailorlist craves.</div>"
        f"<div style='color:#B3B3B3;font-size:0.85rem;margin-bottom:8px;'>"
        f"It'll take a little while. Perfect time to revisit a legendary album:</div>"
        f"<div style='color:#1DB954;font-size:0.95rem;font-weight:700;'>{_album}</div>"
        f"<div style='color:#888;font-size:0.82rem;margin-top:2px;'>{_artist} · {_year}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# Cancel button
# ---------------------------------------------------------------------------
if st.button("🗑️ Cancel and start over", type="secondary", use_container_width=True):
    _snapshot = st.session_state.pop("_pre_enrich_snapshot", None)

    # Always clear current-run state
    for k in ("uc_playlists", "uc_enriched", "uc_failed", "uc_skipped",
              "uc_active", "uc_enrichment_state", "uc_enrichment_cursor",
              "uc_all_tracks", "_enrich_run_started", "_enrichment_start_tracked",
              "uc_session_id", "_enrich_start_time"):
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
                from db.queries import load_uc_session
                _db_session = load_uc_session(_prev_sid)
                if _db_session:
                    st.session_state["uc_enriched"]          = _db_session["enriched"]
                    st.session_state["uc_skipped"]           = _db_session["skipped"]
                    st.session_state["uc_failed"]            = _db_session["failed"]
                    st.session_state["uc_playlists"]         = _db_session["playlists"]
                    st.session_state["uc_session_id"]        = _prev_sid
                    st.session_state["uc_active"]            = True
                    st.session_state["uc_enrichment_state"]  = "idle"
                    st.session_state["mode"]                 = "🔗 Your Collection"
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
            st.session_state["mode"]                = "🔗 Your Collection"

    st.switch_page("pages/0_home.py")

# ---------------------------------------------------------------------------
# Process one track, then rerun
# ---------------------------------------------------------------------------
track = to_enrich[cursor]
sid   = track["id"]

try:
    raw_data, status = _fetch(sid)
except Exception:
    st.session_state["uc_failed"].append({
        "name":          track.get("name", ""),
        "artists":       track.get("artists", ""),
        "playlist_name": track.get("playlist_name", ""),
        "id":            track.get("id", ""),
        "added_at":      track.get("added_at", ""),
        "popularity":    track.get("popularity", 0),
        "album":         track.get("album", ""),
        "release_date":  track.get("release_date", ""),
        "duration_ms":   track.get("duration_ms", 0),
    })
    time.sleep(1)
    st.session_state["uc_enrichment_cursor"] += 1
    st.rerun()

if status == "skip":
    fallback = _fetch_fallback(sid)
    if fallback is not None:
        st.session_state["uc_enriched"].append(
            {**track, **fallback})
    else:
        st.session_state["uc_skipped"].append({
            "name":          track.get("name", ""),
            "artists":       track.get("artists", ""),
            "playlist_name": track.get("playlist_name", ""),
            "id":            track.get("id", ""),
            "added_at":      track.get("added_at", ""),
            "popularity":    track.get("popularity", 0),
            "album":         track.get("album", ""),
            "release_date":  track.get("release_date", ""),
            "duration_ms":   track.get("duration_ms", 0),
        })
elif status == "fail" or raw_data is None:
    st.session_state["uc_failed"].append({
        "name":          track.get("name", ""),
        "artists":       track.get("artists", ""),
        "playlist_name": track.get("playlist_name", ""),
        "id":            track.get("id", ""),
        "added_at":      track.get("added_at", ""),
        "popularity":    track.get("popularity", 0),
        "album":         track.get("album", ""),
        "release_date":  track.get("release_date", ""),
        "duration_ms":   track.get("duration_ms", 0),
    })
else:
    mapped = _map_fields(sid, raw_data)
    if mapped is None:
        st.session_state["uc_failed"].append({
            "name":          track.get("name", ""),
            "artists":       track.get("artists", ""),
            "playlist_name": track.get("playlist_name", ""),
            "id":            track.get("id", ""),
            "added_at":      track.get("added_at", ""),
            "popularity":    track.get("popularity", 0),
            "album":         track.get("album", ""),
            "release_date":  track.get("release_date", ""),
            "duration_ms":   track.get("duration_ms", 0),
        })
    else:
        st.session_state["uc_enriched"].append(
            {**track, **{k: v for k, v in mapped.items() if k != "spotify_id"}})

time.sleep(1)
st.session_state["uc_enrichment_cursor"] += 1
st.rerun()