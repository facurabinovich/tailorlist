import base64 as _base64
import streamlit as st



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
