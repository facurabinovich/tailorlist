"""Shared Plotly presentation: base layout, playlist colors (no data logic)."""
from __future__ import annotations

#: Dark-theme layout shared by the dashboard charts.
BASE_LAYOUT = dict(
    plot_bgcolor="#121212",
    paper_bgcolor="#121212",
    font_color="#B3B3B3",
    margin=dict(t=20, b=20, l=10, r=10),
)

#: Colors assigned to playlists in sorted-name order, cycling when exhausted.
PLAYLIST_PALETTE = [
    "#1DB954", "#E8534A", "#4A90D9", "#F5A623", "#B97FE8",
    "#E8D44A", "#4AE8D4", "#E84A90", "#A8E84A", "#E8934A",
    "#7B9EA8", "#C0392B", "#8E44AD", "#2ECC71",
]


def layout(**overrides) -> dict:
    """BASE_LAYOUT with the given keys replaced (shallow merge: a key replaces the whole value)."""
    return {**BASE_LAYOUT, **overrides}


def playlist_color_map(playlists) -> dict[str, str]:
    """Map each playlist to a palette color by its position in the sorted names."""
    return {pl: PLAYLIST_PALETTE[i % len(PLAYLIST_PALETTE)] for i, pl in enumerate(sorted(playlists))}


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert "#RRGGBB" (the # is optional) to an (r, g, b) tuple of 0-255 ints."""
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
