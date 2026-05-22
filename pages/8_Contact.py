import streamlit as st
from config import PAGE_CONFIG
st.set_page_config(**PAGE_CONFIG)
from utils import inject_global_css, inject_sidebar_nav, spotify_icon_html, page_brand_html
inject_global_css()
inject_sidebar_nav("Contact")

st.markdown(page_brand_html(), unsafe_allow_html=True)
st.markdown(
    f"<div style='display:flex;align-items:center;gap:16px;padding:0.8rem 0;'>"
    f"{spotify_icon_html(36)}"
    f"<div>"
    f"<h1 style='color:#FFFFFF;margin:0;font-size:2rem;line-height:1.1;'>Contact</h1>"
    f"<p style='color:#B3B3B3;font-size:0.9rem;margin:4px 0 0 0;'>"
    f"Bug reports, suggestions, or just want to say hi."
    f"</p>"
    f"</div>"
    f"</div>"
    f"<hr style='border-color:#333;margin:0 0 1.5rem 0;'/>",
    unsafe_allow_html=True,
)

# ── Two columns ───────────────────────────────────────────────────────────────
col1, col2 = st.columns(2, gap="large")

with col1:
    st.markdown("""
    <div style="background:#1a1a1a;border:1px solid #333;border-radius:12px;padding:24px;">
      <div style="color:#1DB954;font-size:1rem;font-weight:700;margin-bottom:12px;">
        🐛 Bug Reports & Suggestions
      </div>
      <p style="color:#B3B3B3;font-size:0.88rem;line-height:1.6;margin:0 0 16px 0;">
        Found something broken? Have an idea for a new feature?
        I'd love to hear from you.
      </p>
      <a href="https://mail.google.com/mail/?view=cm&to=tailorlistapp@gmail.com&su=TailorList%20%E2%80%94%20Feedback"
         target="_blank"
         style="display:inline-block;background:#1DB954;color:#000;font-weight:700;
                font-size:0.88rem;padding:10px 20px;border-radius:20px;
                text-decoration:none;">
        ✉️ Send me an email
      </a>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    st.markdown("""
    <div style="background:#1a1a1a;border:1px solid #333;border-radius:12px;padding:24px;">
      <div style="color:#1DB954;font-size:1rem;font-weight:700;margin-bottom:12px;">
        💻 Source Code
      </div>
      <p style="color:#B3B3B3;font-size:0.88rem;line-height:1.6;margin:0 0 16px 0;">
        The full project is open source. Star it, fork it, or open an issue.
      </p>
      <a href="https://github.com/facurabinovich/spotify-streamlit"
         target="_blank"
         style="display:inline-block;background:#282828;color:#FFF;font-weight:700;
                font-size:0.88rem;padding:10px 20px;border-radius:20px;
                text-decoration:none;border:1px solid #444;">
        ⭐ GitHub
      </a>
    </div>
    """, unsafe_allow_html=True)

with col2:
    st.markdown("""
    <div style="background:#1a1a1a;border:1px solid #333;border-radius:12px;padding:24px;">
      <div style="color:#1DB954;font-size:1rem;font-weight:700;margin-bottom:12px;">
        ☕ Support this project
      </div>
      <p style="color:#B3B3B3;font-size:0.88rem;line-height:1.6;margin:0 0 16px 0;">
        This app is free to use. If you found it useful, a coffee goes a long way.
      </p>
      <a href="https://ko-fi.com/tailorlist"
         target="_blank"
         style="display:inline-block;background:#FF5E5B;color:#FFF;font-weight:700;
                font-size:0.88rem;padding:10px 20px;border-radius:20px;
                text-decoration:none;margin-right:8px;margin-bottom:8px;">
        ☕ Ko-fi (International)
      </a>
      <a href="https://cafecito.app/tailorlist"
         target="_blank"
         style="display:inline-block;background:#6F3DE9;color:#FFF;font-weight:700;
                font-size:0.88rem;padding:10px 20px;border-radius:20px;
                text-decoration:none;margin-bottom:8px;">
        ☕ Cafecito (Argentina)
      </a>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    st.markdown("""
    <div style="background:#1a1a1a;border:1px solid #333;border-radius:12px;padding:24px;">
      <div style="color:#1DB954;font-size:1rem;font-weight:700;margin-bottom:12px;">
        🎵 Demo Playlists
      </div>
      <p style="color:#B3B3B3;font-size:0.88rem;line-height:1.6;margin:0 0 16px 0;">
        Do you like the demo playlists? 
        These are the playlists powering Demo Collection and their urls. 
      </p>
      <div style="display:flex;flex-direction:column;gap:8px;">
        <a href="https://open.spotify.com/playlist/538TXA5GvgRPwEBYQrHWk4"
           target="_blank"
           style="color:#1DB954;font-size:0.85rem;text-decoration:none;">
          🎵 Early Soft Rock
        </a>
        <a href="https://open.spotify.com/playlist/1WNhgNZKtCMNo2w6SNQZFr"
           target="_blank"
           style="color:#1DB954;font-size:0.85rem;text-decoration:none;">
          🎵 Mighty nineties
        </a>
        <a href="https://open.spotify.com/playlist/1CTDFGPgOc8Qx5bokMs220"
           target="_blank"
           style="color:#1DB954;font-size:0.85rem;text-decoration:none;">
          🎵 The 52nd Street Radio
        </a>
        <a href="https://open.spotify.com/playlist/4oqAXBJDlC45JaMgNIoC7g"
           target="_blank"
           style="color:#1DB954;font-size:0.85rem;text-decoration:none;">
          🎵 OG Rap
        </a>
        <a href="https://open.spotify.com/playlist/2lgYGMBvGQfQTT8p9MYhr4"
           target="_blank"
           style="color:#1DB954;font-size:0.85rem;text-decoration:none;">
          🎵 Class of '03
        </a>
      </div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<div style='height:2rem'></div>", unsafe_allow_html=True)
st.markdown("""
<p style="color:#555;font-size:0.75rem;text-align:center;">
  Built by Facundo Rabinovich 
</p>
""", unsafe_allow_html=True)
