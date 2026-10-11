"""
core/export.py
Pure text builders for exporting a track list (no streamlit).
"""

from __future__ import annotations


def spotlistr_lines(tracks: list[dict]) -> str:
    """Build the newline-separated "Artist - Song Name" text pasted into Spotlistr.

    Each track dict must provide "artists" (str, comma-separated; only the first
    artist is used, whitespace-stripped) and "name" (str). Missing keys fall
    back to an empty string. One line per track, in input order, duplicates kept.

    Returns the lines joined by "\\n" (empty string for an empty list).
    """
    return "\n".join(
        f"{t.get('artists', '').split(',')[0].strip()} - {t.get('name', '')}"
        for t in tracks
    )


def spotify_track_urls(tracks: list[dict]) -> str:
    """Build newline-separated Spotify track URLs (https://open.spotify.com/track/<id>).

    Each track dict must provide "id" (the Spotify track id); a missing "id"
    raises KeyError. One URL per track, in input order, duplicates kept.

    Returns the URLs joined by "\\n" (empty string for an empty list).
    """
    return "\n".join(
        f"https://open.spotify.com/track/{t['id']}" for t in tracks
    )
