from sqlalchemy import create_engine
import streamlit as st
from dotenv import load_dotenv
import os

load_dotenv()

def _get_db_config() -> dict:
    """Read DB credentials from env vars, falling back to st.secrets."""
    keys = ("DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT", "DB_NAME")
    cfg = {k: os.getenv(k) for k in keys}
    if not all(cfg[k] for k in ("DB_USER", "DB_HOST", "DB_NAME")):
        try:
            for k in keys:
                cfg[k] = st.secrets.get(k, cfg[k])
        except Exception:
            pass
    return cfg

@st.cache_resource
def get_engine():
    cfg = _get_db_config()
    url = (
        f"mysql+pymysql://{cfg['DB_USER']}:{cfg['DB_PASSWORD']}"
        f"@{cfg['DB_HOST']}:{cfg.get('DB_PORT') or 3307}/{cfg['DB_NAME']}?charset=utf8mb4"
    )
    return create_engine(url, echo=False)