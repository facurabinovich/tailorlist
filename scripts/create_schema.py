"""
Create all MySQL tables and seed reference data for the Spotify Streamlit app.
Safe to re-run — uses CREATE TABLE IF NOT EXISTS and INSERT IGNORE.

Usage:
    $env:DATABASE_URL="mysql://root:...@host:port/railway"
    python scripts/create_schema.py
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

raw = os.getenv("DATABASE_URL")
if raw:
    url = raw.replace("mysql://", "mysql+pymysql://", 1)
    if "charset=" not in url:
        sep = "&" if "?" in url else "?"
        url += f"{sep}charset=utf8mb4"
else:
    host     = os.getenv("DB_HOST", "localhost")
    port     = int(os.getenv("DB_PORT", 3307))
    user     = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    database = os.getenv("DB_NAME", "spotify_analytics")
    url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}?charset=utf8mb4"

engine = create_engine(url, echo=False)

DDL = [
    # ── Dimension tables ──────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS dim_artist (
        id         INT AUTO_INCREMENT PRIMARY KEY,
        name       VARCHAR(255) NOT NULL,
        spotify_id VARCHAR(50),
        popularity INT DEFAULT 0,
        genres     TEXT,
        UNIQUE KEY uq_spotify_id (spotify_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS dim_playlist (
        id               INT AUTO_INCREMENT PRIMARY KEY,
        name             VARCHAR(255) NOT NULL,
        spotify_id       VARCHAR(50),
        description      TEXT,
        owner_id         VARCHAR(100),
        owner_name       VARCHAR(255),
        is_public        TINYINT(1) DEFAULT 1,
        is_collaborative TINYINT(1) DEFAULT 0,
        total_tracks     INT DEFAULT 0,
        followers        INT DEFAULT 0,
        snapshot_id      VARCHAR(100),
        is_personal      TINYINT(1) DEFAULT 1,
        UNIQUE KEY uq_spotify_id (spotify_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS dim_album (
        id           INT AUTO_INCREMENT PRIMARY KEY,
        name         VARCHAR(255) NOT NULL,
        spotify_id   VARCHAR(50),
        release_date DATE,
        UNIQUE KEY uq_spotify_id (spotify_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS dim_releasedate (
        id        INT AUTO_INCREMENT PRIMARY KEY,
        full_date DATE NOT NULL,
        year      INT,
        month     INT,
        day       INT,
        decade    INT,
        year_half INT,
        quarter   INT,
        UNIQUE KEY uq_full_date (full_date)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS dim_date (
        id             INT AUTO_INCREMENT PRIMARY KEY,
        full_date      DATE NOT NULL,
        day_of_month   INT,
        month          INT,
        year           INT,
        day_of_week    INT,
        day_name       VARCHAR(20),
        month_name     VARCHAR(20),
        quarter        INT,
        year_month_str VARCHAR(10),
        week_of_year   INT,
        is_weekend     TINYINT(1) DEFAULT 0,
        is_holiday     TINYINT(1) DEFAULT 0,
        holiday_name   VARCHAR(100),
        season         VARCHAR(20),
        day_of_year    INT,
        UNIQUE KEY uq_full_date (full_date)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS dim_songs (
        id                 INT AUTO_INCREMENT PRIMARY KEY,
        name               VARCHAR(255) NOT NULL,
        spotify_id         VARCHAR(50),
        is_local           TINYINT(1) DEFAULT 0,
        has_audio_features TINYINT(1) DEFAULT 0,
        UNIQUE KEY uq_spotify_id (spotify_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS dim_audio_features (
        id               INT AUTO_INCREMENT PRIMARY KEY,
        spotify_id       VARCHAR(50) NOT NULL,
        danceability     FLOAT,
        energy           FLOAT,
        key_value        INT,
        loudness         FLOAT,
        mode             INT,
        speechiness      FLOAT,
        acousticness     FLOAT,
        instrumentalness FLOAT,
        liveness         FLOAT,
        valence          FLOAT,
        tempo            FLOAT,
        time_signature   INT,
        explicit         TINYINT(1),
        track_number     INT,
        disc_number      INT,
        UNIQUE KEY uq_spotify_id (spotify_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS dim_popularity (
        id         INT AUTO_INCREMENT PRIMARY KEY,
        range_name VARCHAR(50) NOT NULL,
        min_value  INT NOT NULL,
        max_value  INT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS dim_duration (
        id          INT AUTO_INCREMENT PRIMARY KEY,
        range_name  VARCHAR(50) NOT NULL,
        min_minutes DECIMAL(6,2) NOT NULL,
        max_minutes DECIMAL(6,2) NOT NULL
    )
    """,
    # ── Bridge + Fact ─────────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS bridge_song_artists (
        id                INT AUTO_INCREMENT PRIMARY KEY,
        dim_song_id       INT NOT NULL,
        dim_artist_id     INT NOT NULL,
        spotify_artist_id VARCHAR(50),
        is_primary        TINYINT(1) DEFAULT 1,
        artist_order      INT DEFAULT 1,
        UNIQUE KEY uq_song_artist (dim_song_id, dim_artist_id),
        KEY idx_song   (dim_song_id),
        KEY idx_artist (dim_artist_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS fac_songs (
        id                    INT AUTO_INCREMENT PRIMARY KEY,
        dim_song_id           INT NOT NULL,
        dim_playlist_id       INT NOT NULL,
        dim_album_id          INT,
        dim_releasedate_id    INT,
        dim_date_added_id     INT,
        dim_popularity_id     INT,
        dim_duration_id       INT,
        dim_audio_features_id INT,
        popularity_raw        INT,
        duration_raw          FLOAT,
        added_at              DATETIME,
        added_by              VARCHAR(100),
        UNIQUE KEY uq_song_playlist (dim_song_id, dim_playlist_id),
        KEY idx_song        (dim_song_id),
        KEY idx_playlist    (dim_playlist_id),
        KEY idx_audio_feat  (dim_audio_features_id)
    )
    """,
    # ── App tables ────────────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS user_cluster_progress (
        id           INT AUTO_INCREMENT PRIMARY KEY,
        user_key     VARCHAR(100) NOT NULL,
        track_id     VARCHAR(50)  NOT NULL,
        status       ENUM('done','manual') NOT NULL,
        cluster_name VARCHAR(100),
        created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uq_user_track (user_key, track_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS user_progress_meta (
        user_key VARCHAR(100) NOT NULL PRIMARY KEY,
        reset_at DATETIME     NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS uc_sessions (
        id             INT AUTO_INCREMENT PRIMARY KEY,
        session_id     VARCHAR(36)  NOT NULL UNIQUE,
        enriched_json  LONGTEXT     NOT NULL,
        skipped_json   LONGTEXT,
        failed_json    LONGTEXT,
        playlists_json LONGTEXT,
        created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        last_seen_at   TIMESTAMP NULL,
        KEY idx_session_id  (session_id),
        KEY idx_created_at  (created_at),
        KEY idx_last_seen   (last_seen_at)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS app_analytics (
        id          INT AUTO_INCREMENT PRIMARY KEY,
        event       VARCHAR(50) NOT NULL,
        page        VARCHAR(50),
        session_id  VARCHAR(36),
        visitor_id  VARCHAR(36),
        properties  JSON,
        created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        KEY idx_event      (event),
        KEY idx_created_at (created_at),
        KEY idx_session_id (session_id),
        KEY idx_visitor_id (visitor_id)
    )
    """,
    # ── dim_audio_fallback (migrated from SQLite) ─────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS dim_audio_fallback (
        spotify_id       VARCHAR(50) NOT NULL PRIMARY KEY,
        energy           FLOAT,
        acousticness     FLOAT,
        valence          FLOAT,
        tempo            FLOAT,
        danceability     FLOAT,
        loudness         FLOAT,
        instrumentalness FLOAT,
        speechiness      FLOAT,
        liveness         FLOAT,
        mode             INT,
        duration_ms      INT
    )
    """,
]

POPULARITY_SEED = [
    (1, "Unknown",     0,   0),
    (2, "Obscure",     1,  20),
    (3, "Niche",      21,  40),
    (4, "Moderate",   41,  60),
    (5, "Popular",    61,  80),
    (6, "Very Popular", 81, 100),
]

DURATION_SEED = [
    (1, "Very Short",  0.00,   2.00),
    (2, "Short",       2.00,   3.00),
    (3, "Medium",      3.00,   5.00),
    (4, "Long",        5.00,   8.00),
    (5, "Very Long",   8.00, 999.00),
]

with engine.connect() as conn:
    version = conn.execute(text("SELECT VERSION()")).fetchone()[0]
    print(f"Connected to MySQL {version}")

print("Creating tables...")
with engine.begin() as conn:
    for stmt in DDL:
        conn.execute(text(stmt))
print(f"  {len(DDL)} tables ensured.")

print("Seeding dim_popularity...")
with engine.begin() as conn:
    for row in POPULARITY_SEED:
        conn.execute(text(
            "INSERT IGNORE INTO dim_popularity (id, range_name, min_value, max_value) "
            "VALUES (:id, :name, :lo, :hi)"
        ), {"id": row[0], "name": row[1], "lo": row[2], "hi": row[3]})
print(f"  {len(POPULARITY_SEED)} rows.")

print("Seeding dim_duration...")
with engine.begin() as conn:
    for row in DURATION_SEED:
        conn.execute(text(
            "INSERT IGNORE INTO dim_duration (id, range_name, min_minutes, max_minutes) "
            "VALUES (:id, :name, :lo, :hi)"
        ), {"id": row[0], "name": row[1], "lo": row[2], "hi": row[3]})
print(f"  {len(DURATION_SEED)} rows.")

print("Applying analytics schema migrations (safe to re-run)...")
_migrations = [
    ("app_analytics", "ADD COLUMN visitor_id VARCHAR(36)"),
    ("app_analytics", "ADD COLUMN properties JSON"),
    ("app_analytics", "ADD INDEX idx_visitor_id (visitor_id)"),
    ("uc_sessions",   "ADD COLUMN last_seen_at TIMESTAMP NULL"),
    ("uc_sessions",   "ADD INDEX idx_last_seen (last_seen_at)"),
]
with engine.begin() as conn:
    for table, clause in _migrations:
        try:
            conn.execute(text(f"ALTER TABLE {table} {clause}"))
            print(f"  ✓ {table}: {clause}")
        except Exception as e:
            print(f"  · {table}: {clause} — skipped ({e})")

print("Schema ready.")
