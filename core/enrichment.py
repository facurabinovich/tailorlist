"""Enrichment run computations (no Streamlit, no session state, no network).

Pure logic behind the Enrich page: which tracks still need enriching, how a fetch result
is classified, the records stored per outcome, progress/ETA math and the wait-message
tier. The network calls (ReccoBeats, fallback DB) stay in pipeline/enrich.py; the
session-state flow lives in app_state/enrichment.py.

Vocabulary:
  - A *track* is a dict from the Spotify playlist fetch: id, name, artists, playlist_name,
    added_at, popularity, album, release_date, duration_ms.
  - Outcomes of one track: "enriched" (audio features found; stored as the track merged with
    the features), "skipped" (not in ReccoBeats nor the fallback DB; will not be retried) or
    "failed" (API error; retried on the next run).
  - Inputs are never mutated.
"""
from __future__ import annotations

from dataclasses import dataclass

#: Fallback rate when no elapsed time is known yet (tracks per minute, empirical).
FALLBACK_TRACKS_PER_MIN = 26

#: Wait-message tiers by estimated remaining minutes.
SHORT_WAIT_BELOW_MIN = 15
MEDIUM_WAIT_BELOW_MIN = 30

#: Rotate the wait message every this many tracks (one track takes about a second).
ROTATE_EVERY_TRACKS = 60

#: Fields copied from a track into its skipped/failed record, with the default for a missing one.
_UNENRICHED_FIELDS: tuple[tuple[str, object], ...] = (
    ("name", ""), ("artists", ""), ("playlist_name", ""), ("id", ""),
    ("added_at", ""), ("popularity", 0), ("album", ""), ("release_date", ""),
    ("duration_ms", 0),
)


@dataclass(frozen=True)
class EtaEstimate:
    """Time left in the current run.

    Attributes:
        label: text shown to the user: "~Xm Ys left", "~Ys left" (under a minute) or
            "estimating…" when no time has elapsed yet.
        seconds_left: estimated seconds remaining; None while estimating.
    """
    label: str
    seconds_left: float | None


def track_key_id(track: dict) -> str | None:
    """Spotify id of a stored track: ``id``, else the legacy ``track_id``, else None."""
    return track.get("id") or track.get("track_id")


def pending_tracks(all_tracks: list[dict], enriched: list[dict], skipped: list[dict]) -> list[dict]:
    """Tracks of this run that still need enriching, order kept.

    Excluded: ids already enriched, and ids previously skipped (re-trying will not help).
    Failed tracks are deliberately NOT excluded so they get another chance. Skipped records
    without any id exclude nothing. Every track in ``all_tracks`` must have an ``id`` key.
    """
    enriched_ids = {track_key_id(t) for t in enriched}
    enriched_ids.discard(None)
    skipped_ids = {track_key_id(t) for t in skipped if track_key_id(t)}
    return [t for t in all_tracks
            if t["id"] not in enriched_ids and t["id"] not in skipped_ids]


def unenriched_record(track: dict) -> dict:
    """Record stored for a skipped or failed track: the nine display fields with defaults."""
    return {k: track.get(k, default) for k, default in _UNENRICHED_FIELDS}


def enriched_record(track: dict, features: dict, drop_keys: tuple[str, ...] = ()) -> dict:
    """The track merged with its audio features (features win on key clashes).

    ``drop_keys`` are removed from the features first (the ReccoBeats mapping drops
    "spotify_id"; the fallback features are merged whole).
    """
    return {**track, **{k: v for k, v in features.items() if k not in drop_keys}}


def classify_fetch(status: str | None, raw_data: dict | None) -> str:
    """How to treat a ReccoBeats fetch result: "skip", "fail" or "map".

    "skip" when status == "skip" (try the fallback DB next); "fail" when status == "fail" or
    there is no data; otherwise "map" (map the raw response to audio features; the mapping
    itself may still fail, which counts as a failure).
    """
    if status == "skip":
        return "skip"
    if status == "fail" or raw_data is None:
        return "fail"
    return "map"


def progress_fraction(cursor: int, total: int) -> float:
    """Progress bar value cursor/total. ``total`` must be positive (callers finish at 0)."""
    return cursor / total


def retry_note(n_failed_prev: int) -> str:
    """Suffix of the progress text when previously failed tracks are being retried."""
    return f" (includes {n_failed_prev} retried)" if n_failed_prev else ""


def estimate_eta(cursor: int, total: int, elapsed_s: float | None) -> EtaEstimate:
    """Estimate time left from the observed rate (tracks done / elapsed seconds).

    Estimating (no label figures) when nothing is done yet or no start time is known
    (``elapsed_s`` None). ``elapsed_s`` of exactly 0 with progress raises ZeroDivisionError,
    as the original inline code did; callers pass wall-clock deltas so this does not occur.
    """
    if elapsed_s is not None and cursor > 0:
        rate = cursor / elapsed_s
        secs_left = (total - cursor) / rate
        m, s = divmod(int(secs_left), 60)
        label = f"~{m}m {s}s left" if m else f"~{s}s left"
        return EtaEstimate(label=label, seconds_left=secs_left)
    return EtaEstimate(label="estimating…", seconds_left=None)


def estimated_remaining_min(cursor: int, total: int, eta: EtaEstimate) -> float:
    """Minutes left: from the observed ETA when available, else at the empirical 26 tracks/min."""
    if eta.seconds_left is not None:
        return eta.seconds_left / 60
    return (total - cursor) / FALLBACK_TRACKS_PER_MIN


def wait_tier(est_remaining_min: float) -> str:
    """Which wait message to show: "short" (<15 min), "medium" (<30 min) or "long"."""
    if est_remaining_min < SHORT_WAIT_BELOW_MIN:
        return "short"
    if est_remaining_min < MEDIUM_WAIT_BELOW_MIN:
        return "medium"
    return "long"


def rotation_index(cursor: int, *list_lengths: int) -> int:
    """Index that rotates the wait message every 60 tracks, modulo the longest list."""
    return (cursor // ROTATE_EVERY_TRACKS) % max(list_lengths)


def pre_enrich_snapshot(to_enrich: list[dict], playlists: list[dict],
                        enriched: list[dict], session_id: str | None) -> dict:
    """State to restore if the user cancels the run.

    ``playlists`` keeps only those NOT part of this run (their name does not appear in
    ``to_enrich``), i.e. the previously enriched ones. Keys: enriched (copy), playlists,
    session_id.
    """
    new_names = {t.get("playlist_name") for t in to_enrich}
    return {
        "enriched":   list(enriched),
        "playlists":  [p for p in playlists if p["name"] not in new_names],
        "session_id": session_id,
    }


def playlist_set_key(playlists: list[dict]) -> str:
    """Proxy session id for analytics before a real one exists: hash of the playlist ids.

    Stable only within one Python process (str hashing is randomized per process), which
    is enough: it is written at start and back-filled at completion in the same run.
    """
    return str(hash(tuple(p["id"] for p in playlists)))
