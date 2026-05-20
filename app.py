import math
import time

import pandas as pd
import streamlit as st
from config import PAGE_CONFIG

st.set_page_config(**PAGE_CONFIG)

# ---------------------------------------------------------------------------
# Navigation — hidden, Enrich registered but excluded from sidebar
# ---------------------------------------------------------------------------
pg = st.navigation(
    [
        st.Page("pages/0_home.py", title="Home", default=True),
        st.Page("pages/1_Overview.py", title="Overview"),
        st.Page("pages/2_Playlist_Detail.py", title="Playlist Detail"),
        st.Page("pages/3_Artist_Album.py", title="Artist/Album view"),
        st.Page("pages/4_Playlist_Comparison.py", title="Playlist Comparison"),
        st.Page("pages/5_Audio_DNA.py", title="Audio DNA"),
        st.Page("pages/6_My_Clusters.py", title="My Clusters"),
        st.Page("pages/7_Glossary.py", title="Glossary"),
        st.Page("pages/8_Contact.py", title="Contact"),
        st.Page("pages/_Enrich.py"),           # registered but hidden from sidebar
        st.Page("pages/_album_goto.py"),       # registered but hidden from sidebar
        st.Page("pages/_Cluster_Results.py"), # registered but hidden from sidebar
    ],
    position="hidden",
)
pg.run()