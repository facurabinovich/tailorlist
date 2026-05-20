# ---------------------------------------------------------------------------
# Shared constants — imported by pages and db modules
# ---------------------------------------------------------------------------
import os

# 14 personal playlists (DEV_MODE=1)
_DEV_PLAYLIST_LABELS = {
    "AQ7": "AQ7",
    "GB7": "GB7",
    "507": "507",
    "EU7": "EU7",
    "IN7": "IN7",
    "US7": "US7",
    "ES7": "ES7",
    "RO7": "RO7",
    "AR7": "AR7",
    "AL7": "AL7",
    "RA7": "RA7",
    "MA7": "MA7",
    "807": "807",
    "BB7": "BB7",
}

# 5 demo playlists (DEV_MODE=0, production)
_DEMO_PLAYLIST_LABELS = {
    "Early Soft Rock":     "Early Soft Rock",
    "Mighty Nineties":     "Mighty Nineties",
    "The 52nd Street Radio": "The 52nd Street Radio",
    "Class of '03":        "Class of '03",
    "OG Rap":              "OG Rap",
}

PLAYLIST_LABELS = (
    _DEV_PLAYLIST_LABELS if os.getenv("DEV_MODE", "1") == "1" else _DEMO_PLAYLIST_LABELS
)

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