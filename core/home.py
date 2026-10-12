"""Home page computations (no Streamlit, no session state, no I/O).

Pure functions behind the Home page of the Your Collection (YC) flow: parsing the
``?playlists=`` URL parameter, building playlist entries, the headline counts of an
enriched collection (including the duplicate accounting) and the pre-enrichment estimate.

Vocabulary shared by every function:
  - A *track record* is a dict from the session lists ``uc_enriched`` / ``uc_skipped`` /
    ``uc_failed``. Relevant keys: ``id`` (Spotify id; ``track_id`` is a legacy alias),
    ``playlist_name``.
  - A *playlist entry* is ``{"id", "name", "track_count", "followers"}``, as stored in
    ``uc_playlists``.
  - "enriched" = tracks with audio features; "skipped" = not found in ReccoBeats or the
    fallback database; "failed" = API errors. Skipped + failed are "without audio features".
  - Inputs are never mutated.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

#: Tracks per minute used to estimate enrichment time on the confirm step (empirical).
ENRICH_TRACKS_PER_MIN = 26

#: Enriched-track counts below which Home shows a "needs more tracks" tip.
TIP_STRONG_BELOW = 100
TIP_MILD_BELOW = 200


@dataclass(frozen=True)
class CollectionSummary:
    """Headline numbers of the active ("live") collection shown on Home.

    Attributes:
        n_enriched / n_skipped / n_failed: raw list lengths (a track saved in two playlists
            appears twice).
        n_raw: n_enriched + n_skipped + n_failed.
        n_unique_with_af: unique Spotify ids among enriched tracks.
        n_unique_without_af: unique ids among skipped + failed tracks that are not also enriched.
        total: n_unique_with_af + n_unique_without_af.
        cross_dupes: raw tracks that are repeats across playlists (n_raw - total, floored at 0).
        intra_dupes: tracks Spotify reports in the playlists but that never came back
            (sum of playlist track_count - n_raw, floored at 0); i.e. repeats inside a playlist.
        total_dupes: cross_dupes + intra_dupes.
    """
    n_enriched: int
    n_skipped: int
    n_failed: int
    n_raw: int
    n_unique_with_af: int
    n_unique_without_af: int
    total: int
    cross_dupes: int
    intra_dupes: int
    total_dupes: int


@dataclass(frozen=True)
class ConfirmEstimate:
    """Numbers on the "Ready to enrich?" step.

    Attributes:
        n_playlists: queued playlists.
        total_tracks: sum of the playlists' Spotify track_count.
        new_tracks: tracks still to enrich (total minus already-enriched ids, at least 1).
        est_min: ceil(new_tracks / ENRICH_TRACKS_PER_MIN).
    """
    n_playlists: int
    total_tracks: int
    new_tracks: int
    est_min: int


def parse_playlist_param(raw: str) -> list[str]:
    """Playlist ids from the ``?playlists=a,b,c`` URL parameter (trimmed, blanks dropped).

    Example: " a, ,b,," -> ["a", "b"]. Order is preserved; duplicates are kept.
    """
    return [p.strip() for p in raw.split(",") if p.strip()]


def missing_playlist_ids(param_ids: list[str], playlists: list[dict]) -> list[str]:
    """Ids from the URL that are not yet in the queued playlists (order kept)."""
    existing = {p["id"] for p in playlists}
    return [pid for pid in param_ids if pid not in existing]


def playlist_entry(pid: str, info: dict) -> dict:
    """Playlist entry from a Spotify ``playlist(fields="name,tracks.total,followers")`` response.

    followers falls back to 0 when the response has no followers block.
    """
    return {
        "id":          pid,
        "name":        info["name"],
        "track_count": info["tracks"]["total"],
        "followers":   info.get("followers", {}).get("total", 0),
    }


def playlists_query_value(playlists: list[dict]) -> str:
    """Value of the ``?playlists=`` URL parameter for the given playlists: ids joined by commas."""
    return ",".join(p["id"] for p in playlists)


def add_playlist_error(http_status: int | None) -> str:
    """User-facing message when Spotify rejects an added playlist (404 = not accessible)."""
    if http_status == 404:
        return ("❌ Playlist not found. Spotify editorial playlists are not accessible — "
                "copy their tracks into your own playlist first.")
    return "❌ Could not load playlist. Please try again."


def active_playlist_names(enriched: list[dict], skipped: list[dict], failed: list[dict]) -> set[str]:
    """Distinct non-empty playlist_name values across enriched + skipped + failed tracks."""
    return {
        t.get("playlist_name")
        for t in (enriched + skipped + failed)
        if t.get("playlist_name")
    }


def purge_unenriched_playlists(playlists: list[dict], active_names: set[str]) -> list[dict]:
    """Drop queued playlists that no enriched/skipped/failed track belongs to.

    With no active names at all (nothing processed yet) the playlists are returned unchanged
    (same list object), so a fresh queue is never emptied.
    """
    if not active_names:
        return playlists
    return [p for p in playlists if p["name"] in active_names]


def playlist_count(active_names: set[str], playlists: list[dict]) -> int:
    """Playlists to report: the distinct processed names, else the queued playlists."""
    return len(active_names) if active_names else len(playlists)


def summarize_collection(enriched: list[dict], skipped: list[dict], failed: list[dict],
                         playlists: list[dict]) -> CollectionSummary:
    """Unique-track counts and duplicate accounting for the live collection.

    Uniqueness is by Spotify ``id`` (records without one are ignored by the unique counts).
    A skipped/failed track whose id was also enriched counts once, as enriched.
    ``playlists[*]["track_count"]`` (missing = 0) is what Spotify reported per playlist.
    """
    enriched_ids = {t["id"] for t in enriched if t.get("id")}
    unenriched_ids = {t["id"] for t in (skipped + failed) if t.get("id")} - enriched_ids
    n_with = len(enriched_ids)
    n_without = len(unenriched_ids)
    total = n_with + n_without
    n_raw = len(enriched) + len(skipped) + len(failed)
    spotify_total = sum(pl.get("track_count", 0) for pl in playlists)
    cross = max(0, n_raw - total)
    intra = max(0, spotify_total - n_raw)
    return CollectionSummary(
        n_enriched=len(enriched), n_skipped=len(skipped), n_failed=len(failed), n_raw=n_raw,
        n_unique_with_af=n_with, n_unique_without_af=n_without, total=total,
        cross_dupes=cross, intra_dupes=intra, total_dupes=cross + intra,
    )


def duplicate_note(cross_dupes: int, intra_dupes: int) -> str:
    """Plain-text duplicate note, e.g. "3 duplicate(s) not counted (2 across playlists, 1 within same playlist)".

    Returns "" when there are no duplicates. The parenthesis part lists only the non-zero kinds.
    """
    total = cross_dupes + intra_dupes
    if total <= 0:
        return ""
    parts = []
    if cross_dupes > 0:
        parts.append(f"{cross_dupes} across playlists")
    if intra_dupes > 0:
        parts.append(f"{intra_dupes} within same playlist")
    return f"{total} duplicate(s) not counted" + (f" ({', '.join(parts)})" if parts else "")


def missing_features_note(n_skipped: int, n_failed: int) -> str:
    """Suffix of the "collection is live" banner: " · N without audio features", or ""."""
    n = n_skipped + n_failed
    return f" · {n} without audio features" if n else ""


def enrich_tip_level(n_enriched: int) -> str | None:
    """Which "add more playlists" tip to show: "strong" (<100), "mild" (<200) or None."""
    if n_enriched < TIP_STRONG_BELOW:
        return "strong"
    if n_enriched < TIP_MILD_BELOW:
        return "mild"
    return None


def confirm_estimate(playlists: list[dict], enriched: list[dict]) -> ConfirmEstimate:
    """Pre-enrichment estimate: new tracks = Spotify total minus already-enriched ids (min 1)."""
    total_t = sum(p["track_count"] for p in playlists)
    already = {t.get("id") or t.get("track_id") for t in enriched}
    new_tracks = max(total_t - len(already), 1)
    return ConfirmEstimate(
        n_playlists=len(playlists), total_tracks=total_t, new_tracks=new_tracks,
        est_min=math.ceil(new_tracks / ENRICH_TRACKS_PER_MIN),
    )


def dev_collection_state(data: dict) -> dict:
    """Session values for a saved dev collection file (``failed`` is optional there).

    Raises KeyError when ``enriched``, ``skipped`` or ``playlists`` is missing.
    """
    return {
        "enriched":  data["enriched"],
        "skipped":   data["skipped"],
        "failed":    data.get("failed", []),
        "playlists": data["playlists"],
    }
