"""
pipeline/enrich.py
Fetch missing audio features from ReccoBeats and backfill the DB.

For every song in dim_songs where has_audio_features = 0:
  1. GET https://api.reccobeats.com/v1/track?ids={spotify_id}
       → extract content[0].id as the ReccoBeats internal ID
       → if content is empty, log as SKIP and move on (no FAIL)
  2. GET https://api.reccobeats.com/v1/track/{reccobeats_id}/audio-features
       → if this call fails, log as FAIL
  3. INSERT into dim_audio_features (ON DUPLICATE KEY UPDATE — idempotent)
  4. UPDATE dim_songs SET has_audio_features = 1
  5. UPDATE fac_songs SET dim_audio_features_id = <new id>
  6. Sleep 1 second (rate limit)

Resumable: spotify_ids already present in dim_audio_features are skipped
before any HTTP request is made.
"""

import logging
import os
import re
import sqlite3
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

_FALLBACK_DB = os.path.join(os.path.dirname(__file__), "..", "data", "audio_fallback.db")

_LOOKUP_ENDPOINT   = "https://api.reccobeats.com/v1/track"
_FEATURES_ENDPOINT = "https://api.reccobeats.com/v1/track/{reccobeats_id}/audio-features"
_RATE_LIMIT = 1.0  # seconds between requests


# ── Engine ────────────────────────────────────────────────────────────────────

def _create_engine(env_path: str | Path | None = None) -> Engine:
    load_dotenv(env_path)

    host     = os.getenv("DB_HOST", "localhost")
    port     = int(os.getenv("DB_PORT", 3307))
    user     = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    database = os.getenv("DB_NAME", "spotify_analytics")

    if not all([user, password]):
        raise EnvironmentError("Missing DB_USER or DB_PASSWORD environment variables")

    url = (
        f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"
        "?charset=utf8mb4"
    )
    engine = create_engine(url, echo=False)

    with engine.connect() as conn:
        version = conn.execute(text("SELECT VERSION()")).fetchone()[0]
        logger.info("Connected to MySQL %s at %s:%d/%s", version, host, port, database)

    return engine


# ── HTTP fetch ────────────────────────────────────────────────────────────────

def _fetch(spotify_id: str) -> tuple[dict | None, str]:
    """
    Two-step ReccoBeats lookup for one track.

    Step 1: GET /v1/track?ids={spotify_id} → extract content[0].id
    Step 2: GET /v1/track/{reccobeats_id}/audio-features → audio features

    Returns:
        (data_dict, "ok")   — step 2 succeeded; data_dict is the features JSON
        (None,      "skip") — step 1 returned empty content (track not in ReccoBeats)
        (None,      "fail") — step 1 HTTP error OR step 2 failed
    """
    # ── Step 1: resolve Spotify ID → ReccoBeats internal ID ──────────────────
    try:
        resp1 = requests.get(_LOOKUP_ENDPOINT, params={"ids": spotify_id}, timeout=10)
        resp1.raise_for_status()
        payload = resp1.json()
    except requests.exceptions.Timeout:
        logger.warning("ReccoBeats step-1 timeout for %s", spotify_id)
        return None, "fail"
    except requests.exceptions.RequestException as exc:
        logger.warning("ReccoBeats step-1 request error for %s: %s", spotify_id, exc)
        return None, "fail"
    except ValueError:
        logger.warning("ReccoBeats step-1 invalid JSON for %s", spotify_id)
        return None, "fail"

    content = payload.get("content", [])
    if not content:
        logger.debug("ReccoBeats step-1 empty content for %s — SKIP", spotify_id)
        return None, "skip"

    reccobeats_id = str(content[0]["id"])
    if not re.match(r'^[a-zA-Z0-9_-]{1,100}$', reccobeats_id):
        logger.warning("ReccoBeats returned unexpected id format for %s: %r", spotify_id, reccobeats_id)
        return None, "fail"

    # ── Step 2: fetch audio features ──────────────────────────────────────────
    url2 = _FEATURES_ENDPOINT.format(reccobeats_id=reccobeats_id)
    try:
        resp2 = requests.get(url2, timeout=10)
        if resp2.status_code == 404:
            logger.debug("ReccoBeats step-2 404 for %s (rb_id=%s)", spotify_id, reccobeats_id)
            return None, "fail"
        resp2.raise_for_status()
        return resp2.json(), "ok"
    except requests.exceptions.Timeout:
        logger.warning("ReccoBeats step-2 timeout for %s", spotify_id)
        return None, "fail"
    except requests.exceptions.RequestException as exc:
        logger.warning("ReccoBeats step-2 request error for %s: %s", spotify_id, exc)
        return None, "fail"
    except ValueError:
        logger.warning("ReccoBeats step-2 invalid JSON for %s", spotify_id)
        return None, "fail"


def _fetch_fallback(spotify_id: str) -> dict | None:
    """
    Try to recover audio features from local SQLite fallback DB.
    Returns a mapped dict compatible with _map_fields output, or None if not found.
    """
    try:
        conn = sqlite3.connect(_FALLBACK_DB)
        cursor = conn.execute(
            "SELECT energy, acousticness, valence, tempo, danceability, "
            "loudness, instrumentalness, speechiness, liveness, mode, duration_ms "
            "FROM audio_features WHERE spotify_id = ?",
            (spotify_id,)
        )
        row = cursor.fetchone()
        conn.close()
        if row is None:
            return None
        return {
            "energy":           row[0],
            "acousticness":     row[1],
            "valence":          row[2],
            "tempo":            row[3],
            "danceability":     row[4],
            "loudness":         row[5],
            "instrumentalness": row[6],
            "speechiness":      row[7],
            "liveness":         row[8],
            "mode":             row[9],
            "duration_ms":      row[10],
        }
    except Exception as exc:
        logger.warning("Fallback DB lookup failed for %s: %s", spotify_id, exc)
        return None


# ── Field mapping ─────────────────────────────────────────────────────────────

def _map_fields(spotify_id: str, data: dict) -> dict | None:
    """
    Map ReccoBeats audio-features response to dim_audio_features column values.

    ReccoBeats returns 'key'; our schema uses 'key_value' (reserved word workaround).
    Fields not returned by ReccoBeats (time_signature, track_number, disc_number)
    stay NULL; explicit stays False.

    Returns None if no audio metrics are present in the response.
    """
    def _f(key: str) -> float | None:
        val = data.get(key)
        if val is None:
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    def _i(key: str) -> int | None:
        val = data.get(key)
        if val is None:
            return None
        try:
            return int(val)
        except (TypeError, ValueError):
            return None

    # ReccoBeats returns 'key'; our schema column is 'key_value' (reserved word)
    key_val = _i("key")

    mapped = {
        "spotify_id":        spotify_id,
        "danceability":      _f("danceability"),
        "energy":            _f("energy"),
        "key_value":         key_val,
        "loudness":          _f("loudness"),
        "mode":              _i("mode"),
        "speechiness":       _f("speechiness"),
        "acousticness":      _f("acousticness"),
        "instrumentalness":  _f("instrumentalness"),
        "liveness":          _f("liveness"),
        "valence":           _f("valence"),
        "tempo":             _f("tempo"),
        # ReccoBeats does not provide these columns
        "time_signature":    None,
        "track_number":      None,
        "disc_number":       None,
        "explicit":          False,
    }

    audio_metrics = (
        "danceability", "energy", "loudness", "speechiness",
        "acousticness", "instrumentalness", "liveness", "valence", "tempo",
    )
    if all(mapped[f] is None for f in audio_metrics):
        logger.warning("ReccoBeats returned no usable audio metrics for %s", spotify_id)
        return None

    return mapped


# ── DB writes ─────────────────────────────────────────────────────────────────

_SQL_INSERT = text("""
    INSERT INTO dim_audio_features
        (spotify_id, danceability, energy, key_value, loudness, mode,
         speechiness, acousticness, instrumentalness, liveness, valence,
         tempo, time_signature, explicit, track_number, disc_number)
    VALUES
        (:spotify_id, :danceability, :energy, :key_value, :loudness, :mode,
         :speechiness, :acousticness, :instrumentalness, :liveness, :valence,
         :tempo, :time_signature, :explicit, :track_number, :disc_number)
    ON DUPLICATE KEY UPDATE
        danceability     = VALUES(danceability),
        energy           = VALUES(energy),
        key_value        = VALUES(key_value),
        loudness         = VALUES(loudness),
        mode             = VALUES(mode),
        speechiness      = VALUES(speechiness),
        acousticness     = VALUES(acousticness),
        instrumentalness = VALUES(instrumentalness),
        liveness         = VALUES(liveness),
        valence          = VALUES(valence),
        tempo            = VALUES(tempo),
        id               = LAST_INSERT_ID(id)
""")

_SQL_FLAG_SONG = text("""
    UPDATE dim_songs
    SET has_audio_features = 1
    WHERE spotify_id = :spotify_id
""")

# Backfill the FK column in fac_songs for every fact row tied to this track.
# Runs only where the FK is still NULL (won't overwrite a previous backfill).
_SQL_BACKFILL_FACT = text("""
    UPDATE fac_songs fs
    JOIN dim_songs      s  ON fs.dim_song_id = s.id
    JOIN dim_audio_features af ON af.spotify_id = s.spotify_id
    SET fs.dim_audio_features_id = af.id
    WHERE s.spotify_id = :spotify_id
      AND fs.dim_audio_features_id IS NULL
""")


def _write(engine: Engine, row: dict) -> None:
    """Insert audio features and backfill dim_songs + fac_songs in one transaction."""
    with engine.begin() as conn:
        conn.execute(_SQL_INSERT, row)
        conn.execute(_SQL_FLAG_SONG,     {"spotify_id": row["spotify_id"]})
        conn.execute(_SQL_BACKFILL_FACT, {"spotify_id": row["spotify_id"]})


# ── Public API ────────────────────────────────────────────────────────────────

_SQL_GLOBAL_BACKFILL = text("""
    UPDATE fac_songs fs
    JOIN dim_songs s          ON fs.dim_song_id = s.id
    JOIN dim_audio_features af ON af.spotify_id = s.spotify_id
    SET fs.dim_audio_features_id = af.id
    WHERE fs.dim_audio_features_id IS NULL
""")


def enrich(env_path: str | Path | None = None) -> dict[str, int]:
    """
    Fetch missing audio features from ReccoBeats and backfill the DB.

    Args:
        env_path: Path to .env with DB_* variables. Defaults to standard
                  dotenv lookup.

    Returns:
        dict with keys:
          attempted  — tracks for which an HTTP request was made
          succeeded  — tracks successfully written to dim_audio_features
          failed     — tracks where the API returned no data or the DB write failed
          skipped    — tracks whose spotify_id was already in dim_audio_features
    """
    engine = _create_engine(env_path)

    # ── Global backfill: fix fac_songs rows that gained a NULL dim_audio_features_id
    # after a fresh load (songs already in dim_audio_features have has_audio_features=1
    # so they never appear in candidates below, but new fac_songs rows still need the FK).
    with engine.begin() as conn:
        result = conn.execute(_SQL_GLOBAL_BACKFILL)
        if result.rowcount:
            logger.info("Global backfill: updated %d fac_songs rows", result.rowcount)

    # ── Candidates: songs that still need audio features ──────────────────────
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT spotify_id
            FROM dim_songs
            WHERE has_audio_features = 0
              AND is_local           = 0
              AND spotify_id        != ''
        """)).fetchall()

    candidates: list[str] = [r[0] for r in rows]
    logger.info("%d songs need audio feature enrichment", len(candidates))

    if not candidates:
        logger.info("Nothing to enrich")
        return {"attempted": 0, "succeeded": 0, "failed": 0, "skipped": 0}

    # ── Already enriched: pre-load to skip without HTTP ───────────────────────
    with engine.connect() as conn:
        already_done: set[str] = {
            r[0]
            for r in conn.execute(
                text("SELECT spotify_id FROM dim_audio_features")
            ).fetchall()
        }

    logger.info("%d spotify_ids already present in dim_audio_features", len(already_done))

    # ── Main loop ─────────────────────────────────────────────────────────────
    stats = {"attempted": 0, "succeeded": 0, "failed": 0, "skipped": 0}
    total = len(candidates)
    _PROGRESS_EVERY = 10  # print a summary line every N HTTP requests

    t_loop_start = time.monotonic()

    for i, spotify_id in enumerate(candidates, start=1):
        if spotify_id in already_done:
            stats["skipped"] += 1
            continue

        stats["attempted"] += 1

        raw, status = _fetch(spotify_id)

        if status == "skip":
            # Try local fallback DB before giving up
            fallback = _fetch_fallback(spotify_id)
            if fallback is not None:
                # Build a mapped dict compatible with _write()
                mapped_fallback = {
                    "spotify_id":        spotify_id,
                    "danceability":      fallback.get("danceability"),
                    "energy":            fallback.get("energy"),
                    "key_value":         None,
                    "loudness":          fallback.get("loudness"),
                    "mode":              fallback.get("mode"),
                    "speechiness":       fallback.get("speechiness"),
                    "acousticness":      fallback.get("acousticness"),
                    "instrumentalness":  fallback.get("instrumentalness"),
                    "liveness":          fallback.get("liveness"),
                    "valence":           fallback.get("valence"),
                    "tempo":             fallback.get("tempo"),
                    "time_signature":    None,
                    "track_number":      None,
                    "disc_number":       None,
                    "explicit":          False,
                }
                try:
                    _write(engine, mapped_fallback)
                    already_done.add(spotify_id)
                    stats["succeeded"] += 1
                    logger.info(
                        "[%d/%d] FALLBACK  %s  (recovered from local DB)  "
                        "ok=%d  fail=%d  skip=%d",
                        i, total, spotify_id,
                        stats["succeeded"], stats["failed"], stats["skipped"],
                    )
                except Exception as exc:
                    logger.error("[%d/%d] DB error (fallback) for %s: %s", i, total, spotify_id, exc)
                    stats["failed"] += 1
            else:
                stats["skipped"] += 1
                logger.info(
                    "[%d/%d] SKIP  %s  (not in ReccoBeats or fallback DB)  "
                    "ok=%d  fail=%d  skip=%d",
                    i, total, spotify_id,
                    stats["succeeded"], stats["failed"], stats["skipped"],
                )
            time.sleep(_RATE_LIMIT)
            continue

        if status == "fail" or raw is None:
            stats["failed"] += 1
            logger.info(
                "[%d/%d] FAIL  %s  (API error on step 2)  "
                "ok=%d  fail=%d  skip=%d",
                i, total, spotify_id,
                stats["succeeded"], stats["failed"], stats["skipped"],
            )
            time.sleep(_RATE_LIMIT)
            continue

        mapped = _map_fields(spotify_id, raw)
        if mapped is None:
            stats["failed"] += 1
            logger.info(
                "[%d/%d] FAIL  %s  (empty metrics)  "
                "ok=%d  fail=%d  skip=%d",
                i, total, spotify_id,
                stats["succeeded"], stats["failed"], stats["skipped"],
            )
            time.sleep(_RATE_LIMIT)
            continue

        try:
            _write(engine, mapped)
            already_done.add(spotify_id)
            stats["succeeded"] += 1
        except Exception as exc:
            logger.error("[%d/%d] DB error for %s: %s", i, total, spotify_id, exc)
            stats["failed"] += 1
            time.sleep(_RATE_LIMIT)
            continue

        # ── Progress log every N successful requests ───────────────────────
        if stats["attempted"] % _PROGRESS_EVERY == 0:
            elapsed   = time.monotonic() - t_loop_start
            rate      = stats["attempted"] / elapsed          # requests/sec
            remaining = total - i
            eta_sec   = int(remaining / rate) if rate > 0 else 0
            eta_min, eta_s = divmod(eta_sec, 60)
            logger.info(
                "[%d/%d] ok=%-4d  fail=%-3d  skip=%-4d  "
                "%.2f req/s  ETA %dm%02ds",
                i, total,
                stats["succeeded"], stats["failed"], stats["skipped"],
                rate, eta_min, eta_s,
            )

        time.sleep(_RATE_LIMIT)

    logger.info(
        "Enrichment done — attempted=%d  succeeded=%d  failed=%d  skipped=%d",
        stats["attempted"], stats["succeeded"], stats["failed"], stats["skipped"],
    )
    return stats
