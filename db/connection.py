import os

import streamlit as st
from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv()

_DEV_MODE = os.getenv("DEV_MODE", "1") == "1"


def _local_url() -> str:
    keys = ("DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT", "DB_NAME")
    cfg = {k: os.getenv(k) for k in keys}
    if not all(cfg[k] for k in ("DB_USER", "DB_HOST", "DB_NAME")):
        try:
            for k in keys:
                cfg[k] = st.secrets.get(k, cfg[k])
        except Exception:
            pass
    return (
        f"mysql+pymysql://{cfg['DB_USER']}:{cfg['DB_PASSWORD']}"
        f"@{cfg['DB_HOST']}:{cfg.get('DB_PORT') or 3307}/{cfg['DB_NAME']}?charset=utf8mb4"
    )


def _production_url() -> str:
    raw = os.getenv("DATABASE_URL")
    if not raw:
        try:
            raw = st.secrets["DATABASE_URL"]
        except Exception:
            pass
    if not raw:
        raise EnvironmentError("DATABASE_URL is required when DEV_MODE != 1")
    # Railway provides mysql:// — SQLAlchemy needs the driver dialect
    url = raw.replace("mysql://", "mysql+pymysql://", 1)
    if "charset=" not in url:
        sep = "&" if "?" in url else "?"
        url += f"{sep}charset=utf8mb4"
    return url


@st.cache_resource
def get_engine():
    url = _local_url() if _DEV_MODE else _production_url()
    return create_engine(url, echo=False)
