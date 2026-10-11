"""
Fetch the ReccoBeats audio-feature fallback DB at container start.

The file is ~360 MB and static, so it is not committed (see .gitignore). In
production it is published as a GitHub Release asset and pulled once per
container into data/audio_fallback.db; locally the file is normally already
present, in which case this module does nothing.

The download runs on a background thread so the app serves immediately.
pipeline.enrich._fetch_fallback() guards on os.path.exists(), so until the
file lands a ReccoBeats "skip" simply falls through to uc_skipped — the same
behaviour as when no fallback DB is configured at all.

Set FALLBACK_DB_URL to the release asset. A plain .db is downloaded as-is; a
.gz URL is decompressed while streaming, so peak disk stays at one copy.
"""

import gzip
import logging
import os
import shutil
import tempfile
import threading
import time

logger = logging.getLogger(__name__)

# Must stay in sync with pipeline/enrich.py::_FALLBACK_DB
FALLBACK_DB = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "audio_fallback.db"
)

# Guards against installing an error page or a truncated transfer. The real
# asset is ~360 MB; anything under this is not the fallback DB.
_MIN_BYTES = 100 * 1024 * 1024

_ATTEMPTS = 3
_BACKOFF_SECONDS = 15

_started = False
_lock = threading.Lock()


def _download(url: str, dest: str) -> None:
    """Stream url into dest. Atomic: dest only appears once fully written."""
    import requests

    os.makedirs(os.path.dirname(dest), exist_ok=True)
    fd, tmp = tempfile.mkstemp(
        dir=os.path.dirname(dest), prefix=".audio_fallback.", suffix=".part"
    )
    os.close(fd)
    try:
        with requests.get(url, stream=True, timeout=(10, 300)) as resp:
            resp.raise_for_status()
            # urllib3 handles Content-Encoding; GitHub serves release assets
            # without it, so a .gz URL still yields raw gzip bytes here.
            resp.raw.decode_content = True
            source = gzip.GzipFile(fileobj=resp.raw) if url.endswith(".gz") else resp.raw
            with open(tmp, "wb") as fh:
                shutil.copyfileobj(source, fh, length=4 * 1024 * 1024)

        size = os.path.getsize(tmp)
        if size < _MIN_BYTES:
            raise ValueError(
                f"downloaded {size:,} B, expected at least {_MIN_BYTES:,} — "
                "refusing to install (bad URL, or an error page?)"
            )
        os.replace(tmp, dest)  # atomic — readers never see a partial file
        logger.info("Fallback DB ready at %s (%.1f MB)", dest, size / 1024 / 1024)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def _run(url: str) -> None:
    for attempt in range(1, _ATTEMPTS + 1):
        try:
            _download(url, FALLBACK_DB)
            return
        except Exception as exc:
            logger.warning(
                "Fallback DB download failed (attempt %d/%d): %s", attempt, _ATTEMPTS, exc
            )
            if attempt < _ATTEMPTS:
                time.sleep(_BACKOFF_SECONDS * attempt)
    logger.error(
        "Fallback DB unavailable after %d attempts — enrichment will fall back "
        "to uc_skipped for tracks ReccoBeats cannot resolve.", _ATTEMPTS
    )


def ensure_fallback_db_async() -> None:
    """
    Kick off a one-shot background download if the DB is missing.

    Safe to call on every Streamlit rerun: the file check short-circuits once
    the DB is present, and the module-level flag ensures at most one thread
    per process.
    """
    global _started

    if os.path.exists(FALLBACK_DB):
        return

    url = os.getenv("FALLBACK_DB_URL", "").strip()
    if not url:
        logger.info("FALLBACK_DB_URL not set — skipping fallback DB download.")
        return

    with _lock:
        if _started:
            return
        _started = True

    threading.Thread(
        target=_run, args=(url,), name="fallback-db-download", daemon=True
    ).start()
    logger.info("Fallback DB download started in background from %s", url)
