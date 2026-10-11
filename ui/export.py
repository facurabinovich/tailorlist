"""
ui/export.py
Spotlistr export UI.
"""

from app_state.analytics import log_export_event
from core.export import spotify_track_urls, spotlistr_lines


def render_export_to_spotify(
    tracks: list[dict],
    playlist_name: str,
    key_prefix: str = "export",
    on_export=None,
) -> None:
    """on_export, if given, is called with n_tracks=<int> when the visitor
    downloads the CSV — lets the caller log analytics without this module
    knowing anything about them."""
    import streamlit as st
    import streamlit.components.v1 as components
    import pandas as pd

    st.subheader(f"🎵 Export: {playlist_name}")
    st.caption(f"{len(tracks)} tracks")

    # Build "Artist - Song Name" format for Spotlistr beta
    artist_song_list = spotlistr_lines(tracks)

    # Step 1 — Copy to clipboard via JS
    st.markdown(
        "<p style='color:#B3B3B3;font-size:0.85rem;font-weight:700;margin-bottom:4px;'>"
        "Step 1 — Copy your tracks</p>",
        unsafe_allow_html=True,
    )

    import json as _json
    components.html(
        f"""
        <html><body style="margin:0;padding:0;">
        <textarea id="copydata" style="display:none">{_json.dumps(artist_song_list)}</textarea>
        <button id="copybtn"
        style="background:#333;color:#FFFFFF;border:none;border-radius:8px;
               padding:10px 20px;font-size:0.9rem;cursor:pointer;width:100%;
               transition:background 0.2s;"
        onclick="
            var text = JSON.parse(document.getElementById('copydata').value);
            navigator.clipboard.writeText(text)
                .then(function() {{
                    document.getElementById('copybtn').innerText = '✓ Copied {len(tracks)} tracks!';
                    document.getElementById('copybtn').style.background = '#1DB954';
                    setTimeout(function() {{
                        document.getElementById('copybtn').innerText = '📋 Copy {len(tracks)} tracks to clipboard';
                        document.getElementById('copybtn').style.background = '#333';
                    }}, 2500);
                }})
                .catch(function() {{
                    document.getElementById('copybtn').innerText = '⚠️ Copy failed — use text box below';
                    document.getElementById('copybtn').style.background = '#E8534A';
                }});
        ">
            📋 Copy {len(tracks)} tracks to clipboard
        </button>
        </body></html>
        """,
        height=50,
    )

    # Step 2 — Open Spotlistr beta
    st.markdown(
        "<p style='color:#B3B3B3;font-size:0.85rem;font-weight:700;"
        "margin-top:12px;margin-bottom:4px;'>Step 2 — Open Spotlistr Beta</p>",
        unsafe_allow_html=True,
    )
    st.link_button(
        "🚀 Open Spotlistr Beta",
        "https://beta.spotlistr.com/search/v2/textbox",
        type="primary",
        use_container_width=True,
    )

    # Step 3 — Instructions
    st.markdown(
        "<div style='background:#1a1a1a;border:1px solid #333;border-radius:8px;"
        "padding:10px 16px;margin-top:8px;'>"
        "<p style='color:#FFFFFF;font-size:0.85rem;margin:0 0 8px;'>"
        "<b>Step 3 — What happens on Spotlistr:</b></p>"
        "<ol style='color:#B3B3B3;font-size:0.82rem;margin:0;padding-left:18px;line-height:1.8;'>"
        "<li>Paste your tracks into the <b style='color:#FFFFFF;'>Inputs</b> box</li>"
        "<li>Sign in with your <b style='color:#FFFFFF;'>email</b> — no password needed, "
        "they send a 6-digit code</li>"
        "<li>Spotlistr searches Spotify for each track and shows <b style='color:#FFFFFF;'>"
        "confidence scores</b> — review any uncertain matches</li>"
        "<li>Click <b style='color:#1DB954;'>Create Playlist</b> — done, "
        "it appears in your Spotify account</li>"
        "</ol>"
        "</div>",
        unsafe_allow_html=True,
    )

    st.markdown(
        "<div style='background:#1a1a1a;border:1px solid #F5A623;border-radius:8px;"
        "padding:10px 16px;margin-top:8px;'>"
        "<span style='color:#B3B3B3;font-size:0.78rem;'>"
        "⏱️ <b style='color:#F5A623;'>Heads up</b> — "
        "playlists created via Spotlistr can take <b style='color:#FFFFFF;'>up to 5 minutes</b> "
        "to appear in your Spotify app. If it's not there yet, just wait a bit and refresh."
        "</span>"
        "</div>",
        unsafe_allow_html=True,
    )

    st.markdown(
        "<div style='background:#1a1a1a;border:1px solid #333;border-radius:8px;"
        "padding:10px 16px;margin-top:8px;'>"
        "<span style='color:#B3B3B3;font-size:0.78rem;'>"
        "ℹ️ <b style='color:#FFFFFF;'>Why Spotlistr?</b> "
        "Since November 2023, Spotify restricts new apps to 5 authenticated users "
        "in development mode. Until this app receives extended quota approval, "
        "playlist creation goes through Spotlistr — a free third-party service. "
        "Your Spotify login stays between you and Spotlistr — "
        "this app never sees your credentials."
        "</span>"
        "</div>",
        unsafe_allow_html=True,
    )

    # Fallback text area in case clipboard fails
    with st.expander("📋 Can't copy? Get the text here", expanded=False):
        st.text_area(
            "Paste this into Spotlistr:",
            artist_song_list,
            height=200,
            key=f"{key_prefix}_artistsong",
        )

    # Other export options
    with st.expander("Other export options", expanded=False):
        df = pd.DataFrame(tracks)
        if st.download_button(
            "📥 Download as CSV",
            df.to_csv(index=False),
            f"{playlist_name}.csv",
            "text/csv",
            use_container_width=True,
            key=f"{key_prefix}_csv_dl",
        ) and on_export:
            on_export(n_tracks=len(tracks))
        url_string = spotify_track_urls(tracks)
        st.text_area(
            "Spotify URLs (clickable):",
            url_string,
            height=200,
            key=f"{key_prefix}_urls",
        )

    log_export_event(playlist_name, len(tracks))

