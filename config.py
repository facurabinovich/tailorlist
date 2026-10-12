# ---------------------------------------------------------------------------
# Shared constants — imported by pages and db modules
# ---------------------------------------------------------------------------
import os
from pathlib import Path

from dotenv import load_dotenv

# Single place where .env is loaded (repo root, regardless of CWD).
# override=False on purpose: variables already set in the process win over .env.
# monitoring.py sets os.environ["DEV_MODE"] = "0" before importing db.connection
# (-> config); override=True would let the local .env (DEV_MODE=1) clobber it.
load_dotenv(Path(__file__).resolve().parent / ".env", override=False)


def is_dev_mode() -> bool:
    """True only when DEV_MODE=1. Read on every call; unset means production."""
    return os.environ.get("DEV_MODE", "0") == "1"


# KMeans cluster labels (index → name)
CLUSTER_NAMES = {
    0: "High Energy · Dark · Fast",
    1: "High Energy · Happy · Danceable",
    2: "Rap · Danceable · Positive",
    3: "Acoustic · Dark",
}


CLUSTER_COLORS = {
    0: "#7B9EA8",
    1: "#E8734A",
    2: "#C0392B",
    3: "#F4C842",
}

# The 6 features used by KMeans (speechiness_log = log1p transform of raw speechiness)
CLUSTER_FEATURES = ["energy", "acousticness", "valence", "tempo", "danceability", "speechiness_log"]

# Audio features shown across the app (ordered for display)
AUDIO_FEATURES = [
    "energy", "acousticness", "valence", "danceability",
    "speechiness", "instrumentalness", "liveness", "loudness", "tempo",
]

# Features on 0–1 scale (vs loudness in dB, tempo in BPM)
NORMALIZED_FEATURES = [
    "energy", "acousticness", "valence", "danceability",
    "speechiness", "instrumentalness", "liveness",
]

# Model paths (relative to project root)
MODEL_PATH    = "models/rf_classifier.pkl"
SCALER_PATH   = "models/scaler.pkl"
FEATURES_PATH = "models/feature_cols.pkl"
KMEANS_PATH        = "models/kmeans.pkl"
KMEANS_SCALER_PATH = "models/kmeans_scaler.pkl"

# Streamlit page config (call once in app.py)
PAGE_CONFIG = dict(
    page_title="Spotify Analytics",
    page_icon="🎵",
    layout="wide",
    initial_sidebar_state="expanded",
)