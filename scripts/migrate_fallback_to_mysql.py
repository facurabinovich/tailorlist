"""
One-time migration: import audio_fallback.db → dim_audio_fallback in Railway MySQL.

Usage (PowerShell):
    $env:DATABASE_URL="mysql://root:...@roundhouse.proxy.rlwy.net:PORT/railway"
    python scripts/migrate_fallback_to_mysql.py

The script is safe to re-run — it uses INSERT IGNORE so already-imported rows are skipped.
Progress is printed every 100k rows.
"""

import os
import sqlite3
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

try:
    from tqdm import tqdm as _tqdm
    _HAS_TQDM = True
except ImportError:
    _HAS_TQDM = False

_SQLITE_PATH = Path(__file__).parent.parent / "data" / "audio_fallback.db"
_CHUNK_SIZE  = 5_000
_LOG_EVERY   = 100_000

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS dim_audio_fallback (
    spotify_id        VARCHAR(22)  NOT NULL,
    danceability      FLOAT,
    energy            FLOAT,
    loudness          FLOAT,
    mode              TINYINT,
    speechiness       FLOAT,
    acousticness      FLOAT,
    instrumentalness  FLOAT,
    liveness          FLOAT,
    valence           FLOAT,
    tempo             FLOAT,
    duration_ms       INT,
    PRIMARY KEY (spotify_id)
)
"""

_INSERT = """
INSERT IGNORE INTO dim_audio_fallback
    (spotify_id, danceability, energy, loudness, mode,
     speechiness, acousticness, instrumentalness, liveness,
     valence, tempo, duration_ms)
VALUES
    (:spotify_id, :danceability, :energy, :loudness, :mode,
     :speechiness, :acousticness, :instrumentalness, :liveness,
     :valence, :tempo, :duration_ms)
"""


def _build_mysql_url() -> str:
    load_dotenv()
    raw = os.getenv("DATABASE_URL")
    if not raw:
        sys.exit("ERROR: DATABASE_URL env var not set.")
    url = raw.replace("mysql://", "mysql+pymysql://", 1)
    if "charset=" not in url:
        sep = "&" if "?" in url else "?"
        url += f"{sep}charset=utf8mb4"
    return url


def migrate():
    if not _SQLITE_PATH.exists():
        sys.exit(f"ERROR: SQLite file not found at {_SQLITE_PATH}")

    print(f"Source : {_SQLITE_PATH}")

    # ── Count source rows ──────────────────────────────────────────────────────
    src = sqlite3.connect(str(_SQLITE_PATH))
    total = src.execute("SELECT COUNT(*) FROM audio_features").fetchone()[0]
    print(f"Rows   : {total:,}")

    # ── Connect to MySQL ───────────────────────────────────────────────────────
    engine = create_engine(_build_mysql_url(), echo=False)
    with engine.begin() as conn:
        conn.execute(text(_CREATE_TABLE))
    print("Table  : dim_audio_fallback ready\n")

    # ── Stream and insert in chunks ────────────────────────────────────────────
    cursor = src.execute(
        "SELECT spotify_id, danceability, energy, loudness, mode, "
        "speechiness, acousticness, instrumentalness, liveness, "
        "valence, tempo, duration_ms "
        "FROM audio_features"
    )

    cols = [
        "spotify_id", "danceability", "energy", "loudness", "mode",
        "speechiness", "acousticness", "instrumentalness", "liveness",
        "valence", "tempo", "duration_ms",
    ]

    inserted = 0
    t_start  = time.monotonic()

    bar = _tqdm(total=total, unit="rows", unit_scale=True, dynamic_ncols=True) if _HAS_TQDM else None

    while True:
        rows = cursor.fetchmany(_CHUNK_SIZE)
        if not rows:
            break

        params = [dict(zip(cols, row)) for row in rows]
        with engine.begin() as conn:
            conn.execute(text(_INSERT), params)

        inserted += len(rows)
        if bar:
            bar.update(len(rows))
        elif inserted % _LOG_EVERY < _CHUNK_SIZE or inserted >= total:
            elapsed = time.monotonic() - t_start
            rate    = inserted / elapsed
            eta_s   = int((total - inserted) / rate) if rate > 0 else 0
            m, s    = divmod(eta_s, 60)
            print(
                f"  {inserted:>9,} / {total:,}  "
                f"({100 * inserted / total:.1f}%)  "
                f"{rate:,.0f} rows/s  ETA {m}m{s:02d}s"
            )

    if bar:
        bar.close()
    src.close()
    elapsed = time.monotonic() - t_start
    print(f"\nDone — {inserted:,} rows in {elapsed:.1f}s")


if __name__ == "__main__":
    migrate()
