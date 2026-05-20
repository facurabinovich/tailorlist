import math
import time

import pandas as pd
import streamlit as st
from config import PAGE_CONFIG

st.set_page_config(**PAGE_CONFIG)

# ---------------------------------------------------------------------------
# DEV_MODE startup — run ETL once per server session to keep local DB fresh
# ---------------------------------------------------------------------------
import os
import subprocess

@st.cache_resource
def _run_etl_on_startup():
    """Run ETL pipeline once on startup in DEV_MODE. Cached so it only runs once per session."""
    from dotenv import load_dotenv
    load_dotenv()
    if os.getenv("DEV_MODE") == "1":
        import logging
        logger = logging.getLogger(__name__)
        logger.info("DEV_MODE=1 — running ETL pipeline on startup...")
        try:
            result = subprocess.run(
                ["python", "-m", "pipeline.run_etl"],
                capture_output=True,
                text=True,
                cwd=os.path.dirname(os.path.abspath(__file__)),
            )
            if result.returncode == 0:
                logger.info("ETL pipeline completed successfully on startup.")
            else:
                logger.warning("ETL pipeline exited with code %d: %s", result.returncode, result.stderr)
        except Exception as e:
            logger.exception("Failed to run ETL on startup: %s", e)

_run_etl_on_startup()

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