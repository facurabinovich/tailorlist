import time
import math as _math

import streamlit as st
from config import PAGE_CONFIG

st.set_page_config(**PAGE_CONFIG)

from ui.theme import inject_global_css
inject_global_css()

from spotify.client import get_playlist_tracks
from app_state.enrichment import (
    cancel_enrichment, complete_enrichment, init_run_state, process_track,
    set_pending_tracks, take_snapshot_once, track_enrichment_start,
)
from core.enrichment import (
    estimate_eta, estimated_remaining_min, playlist_fetch_stats, progress_fraction,
    retry_note, rotation_index, wait_tier,
)

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

track_enrichment_start()

# uc_enriched is preserved across runs (incremental enrichment)
# uc_skipped and uc_failed are reset each run — they reflect only the current run
init_run_state()

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
                pl.update(playlist_fetch_stats(raw))
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
    # Skip tracks already enriched or previously skipped; failed ones are retried
    set_pending_tracks(all_tracks)
    st.rerun()

to_enrich = st.session_state["uc_all_tracks"]
cursor    = st.session_state.get("uc_enrichment_cursor", 0)
total     = len(to_enrich)

# ---------------------------------------------------------------------------
# Snapshot pre-enrichment state (taken once, right after uc_all_tracks is set)
# Used by the cancel button to restore a previously-enriched collection
# instead of wiping everything.
# ---------------------------------------------------------------------------
take_snapshot_once(to_enrich)

# ---------------------------------------------------------------------------
# Completion — navigate back to Home
# ---------------------------------------------------------------------------
if not to_enrich or cursor >= total:
    complete_enrichment()
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
st.progress(progress_fraction(cursor, total),
            text=f"Enriching tracks… {cursor}/{total}{retry_note(len(st.session_state.get('uc_failed', [])))}")

n_ok   = len(st.session_state["uc_enriched"])
n_skip = len(st.session_state["uc_skipped"])
n_fail = len(st.session_state["uc_failed"])

_start_t = st.session_state.get("_enrich_start_time")
_eta = estimate_eta(cursor, total, (time.time() - _start_t) if _start_t else None)
_eta_str = _eta.label

st.caption(f"✅ {n_ok}  ⚠️ {n_skip}  ❌ {n_fail} &nbsp;·&nbsp; ⏱ {_eta_str}")

st.markdown("---")

# ---------------------------------------------------------------------------
# Contextual wait message — adapts to elapsed time
# ---------------------------------------------------------------------------
_est_remaining_min = estimated_remaining_min(cursor, total, _eta)

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
_rot = rotation_index(cursor, len(_SHORT_TIPS), len(_MEDIUM_ALBUMS), len(_LONG_ALBUMS))
_tier = wait_tier(_est_remaining_min)

if _tier == "short":
    _icon, _tip = _SHORT_TIPS[_rot % len(_SHORT_TIPS)]
    st.markdown(
        f"<div style='background:#1a1a1a;border:1px solid #2a2a2a;border-radius:10px;"
        f"padding:14px 18px;margin-bottom:1rem;'>"
        f"<span style='font-size:1.2rem;'>{_icon}</span>"
        f"<span style='color:#B3B3B3;font-size:0.88rem;margin-left:10px;'>{_tip}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )
elif _tier == "medium":
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
    cancel_enrichment()
    st.switch_page("pages/0_home.py")

# ---------------------------------------------------------------------------
# Process one track, then rerun
# ---------------------------------------------------------------------------
track = to_enrich[cursor]
process_track(track)

time.sleep(1)
st.session_state["uc_enrichment_cursor"] += 1
st.rerun()