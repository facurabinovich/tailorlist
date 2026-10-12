"""Artist / album deep-dive analysis behind the Artist / Album page (no Streamlit, no session state, no plotting).

Pure functions that turn the collection DataFrame into what the page shows for one selected
artist or one selected album: the list of selectable entries, the rows of the selection, header
KPIs, the track tables, extremes, playlist spread, audio fingerprint, popularity distribution
and release years.

Conventions shared by every function:
  - The collection frame (df) has one row per (track, playlist) pair. Expected columns (all
    optional unless a function says otherwise): track_id, track_name, artist_name (primary
    artist), artist_display, album_name, playlist_name, popularity_raw (0-100), release_year,
    duration_raw (MILLISECONDS), artist_genres (comma-separated tags) and the audio features
    energy, valence, danceability, acousticness, speechiness, liveness, tempo.
  - The selection frame (sel_df) is the output of artist_rows / album_rows: one row per
    (track_id, playlist_name), with an extra duration_min column (minutes) when duration_raw exists.
  - Inputs are never mutated. Nothing reads the clock or the session (the current year is a parameter).
  - Missing columns give None / empty results as documented on each function.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from core.formatting import fmt_duration

#: Minimum unique tracks for an artist to be selectable / for its audio and popularity analysis.
MIN_TRACKS_ARTIST = 5
#: Minimum unique tracks for an album to be selectable / for its analysis.
MIN_TRACKS_ALBUM = 3
#: Audio features on the fingerprint radar, in axis order (tempo is appended when available).
RADAR_FEATURES = ["energy", "valence", "danceability", "acousticness", "speechiness", "liveness"]
#: Width of one popularity histogram bin.
POPULARITY_BIN_SIZE = 5
#: How many artists / albums get a rank badge in the selector.
TOP_ARTISTS_RANKED = 20
TOP_ALBUMS_RANKED = 10


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SelectionChoices:
    """What can be selected in one mode (artist or album) of the page.

    Attributes:
        options_raw: selectable keys: artist names sorted alphabetically, or album labels
            "Album — Artist" sorted alphabetically.
        options: display strings aligned with options_raw; ranked entries get a "🏆 #N · " prefix.
        top_default: the entry with the most tracks (first on ties), None when nothing is selectable.
        rank_map: entry -> rank (1-based) for the top 20 artists / top 10 albums.
        pairs: album mode only, DataFrame [label, album_name, artist_name, n] (n = unique
            track_ids) aligned with options_raw; None in artist mode.
    """
    options_raw: list[str]
    options: list[str]
    top_default: str | None
    rank_map: dict[str, int]
    pairs: pd.DataFrame | None


@dataclass(frozen=True)
class SelectionKpis:
    """Headline numbers of a selection.

    Attributes:
        track_count: unique track_ids (row count when there is no track_id column).
        playlist_count: distinct playlists the selection appears in.
        enough: track_count reached the mode's minimum (so audio/popularity analysis is shown).
    """
    track_count: int
    playlist_count: int
    enough: bool


@dataclass(frozen=True)
class TrackExtremes:
    """Notable tracks of a selection; each is a full row (pd.Series) or None when not computable.

    Attributes:
        longest, shortest: by duration_min (None without durations).
        most_popular, least_popular: by popularity_raw (None without popularity).
        oldest, newest: by release_year (None unless include_years and there is a year).
        On ties the first row wins.
    """
    longest: pd.Series | None
    shortest: pd.Series | None
    most_popular: pd.Series | None
    least_popular: pd.Series | None
    oldest: pd.Series | None
    newest: pd.Series | None


@dataclass(frozen=True)
class AudioRadar:
    """Audio fingerprint of a selection.

    Attributes:
        features: RADAR_FEATURES present in sel_df (the radar needs at least 3).
        n_enriched: rows with at least one of those features (0 when none are present).
        axis_labels: radar axes (features, plus "tempo" when sel_df has it); empty when
            n_enriched is 0.
        axis_values: one value per axis; tempo is normalized to 0-1 with the min/max of the whole
            collection (0.5 when the collection has a single tempo); empty when n_enriched is 0.
        feature_means: mean of each feature in `features` (same order); empty when n_enriched is 0.
        mean_tempo_bpm: mean tempo of the selection, None without a tempo column.
    """
    features: list[str]
    n_enriched: int
    axis_labels: list[str]
    axis_values: list[float]
    feature_means: list[float]
    mean_tempo_bpm: float | None


@dataclass(frozen=True)
class PopularityDistribution:
    """Popularity histogram (bins of POPULARITY_BIN_SIZE) plus summary statistics.

    Attributes:
        bin_labels: "0–4", "5–9", ... for the non-empty bins only.
        counts: tracks in each of those bins.
        bin_starts: lower bound of each of those bins.
        average, median, highest, lowest: statistics of popularity_raw ignoring missing
            (NaN when the selection has no popularity values).
    """
    bin_labels: list[str]
    counts: list[int]
    bin_starts: list[int]
    average: float
    median: float
    highest: float
    lowest: float


@dataclass(frozen=True)
class YearSummary:
    """Release-year summary of an artist selection (years ignoring missing)."""
    average: float
    oldest: int
    newest: int
    span: int


@dataclass(frozen=True)
class AlbumRelease:
    """Release year of an album.

    Attributes:
        year: most common release_year of the album's rows (smallest on ties).
        years_ago: current_year - year (can be <= 0 for a new album).
    """
    year: int
    years_ago: int


# ---------------------------------------------------------------------------
# Selector
# ---------------------------------------------------------------------------

def _badged(names: list[str], rank_map: dict[str, int]) -> list[str]:
    return [f"🏆 #{rank_map[n]} · {n}" if n in rank_map else n for n in names]


def artist_choices(df: pd.DataFrame, min_tracks: int = MIN_TRACKS_ARTIST) -> SelectionChoices:
    """Artists with at least `min_tracks` rows in the collection, ready for a selector.

    Counts ROWS per artist_name (value_counts), not unique tracks. Ranks the top 20 by count.

    Args:
        df: collection frame; needs artist_name.
        min_tracks: row threshold.
    Returns:
        SelectionChoices (pairs=None). options_raw is empty when no artist qualifies.
    """
    counts = df["artist_name"].value_counts()
    filtered = counts[counts >= min_tracks]
    eligible = sorted(filtered.index.tolist())
    ranked = filtered.sort_values(ascending=False).reset_index()
    ranked.columns = ["artist_name", "count"]
    rank_map = {row["artist_name"]: i + 1 for i, row in ranked.head(TOP_ARTISTS_RANKED).iterrows()}
    top = filtered.idxmax() if not filtered.empty else None
    return SelectionChoices(eligible, _badged(eligible, rank_map), top, rank_map, None)


def album_choices(df: pd.DataFrame, min_tracks: int = MIN_TRACKS_ALBUM) -> SelectionChoices | None:
    """Albums with at least `min_tracks` unique tracks, keyed by (album, artist) pair.

    Pairs avoid collisions such as "Greatest Hits" by different artists. Rows with a missing
    album_name, artist_name or track_id are ignored. Ranks the top 10 by unique tracks.

    Args:
        df: collection frame; needs artist_name, track_id and, for a non-None result, album_name.
        min_tracks: unique-track threshold.
    Returns:
        SelectionChoices with `pairs` set (options_raw empty when none qualifies), or None when
        df has no album_name column.
    """
    if "album_name" not in df.columns:
        return None
    pair_counts = (
        df.dropna(subset=["album_name", "artist_name", "track_id"])
        .groupby(["album_name", "artist_name"], observed=True)["track_id"]
        .nunique()
        .reset_index(name="n")
    )
    pair_counts = pair_counts[pair_counts["n"] >= min_tracks].copy()
    pair_counts["label"] = pair_counts["album_name"] + " — " + pair_counts["artist_name"]
    pair_counts = pair_counts.sort_values("label")
    pairs = pair_counts[["label", "album_name", "artist_name", "n"]].reset_index(drop=True)
    labels = pairs["label"].tolist()
    top = pair_counts.loc[pair_counts["n"].idxmax(), "label"] if not pair_counts.empty else None
    top_n = pair_counts.nlargest(TOP_ALBUMS_RANKED, "n").reset_index(drop=True)
    rank_map = {row["label"]: i + 1 for i, row in top_n.iterrows()}
    return SelectionChoices(labels, _badged(labels, rank_map), top, rank_map, pairs)


def default_option_index(choices: SelectionChoices, pinned: str | None = None) -> int:
    """Index in choices.options the selector should start on.

    Args:
        choices: from artist_choices / album_choices.
        pinned: text to look for inside the display options (substring match, first hit wins);
            used to land on an album chosen from an artist's page. Falls back to 0 when pinned is
            given but matches nothing.
    Returns:
        The pinned match, else the position of top_default in options_raw, else 0.
    """
    if pinned:
        match = next((o for o in choices.options if pinned in o), None)
        return choices.options.index(match) if match else 0
    top = choices.top_default
    return choices.options_raw.index(top) if top in choices.options_raw else 0


def album_pair(choices: SelectionChoices, label: str) -> tuple[str, str]:
    """(album_name, artist_name) behind an album label of an album-mode `choices`.

    Raises IndexError when the label is not in choices.pairs (and AttributeError in artist mode).
    """
    row = choices.pairs[choices.pairs["label"] == label].iloc[0]
    return row["album_name"], row["artist_name"]


# ---------------------------------------------------------------------------
# Selection rows and KPIs
# ---------------------------------------------------------------------------

def _finish_selection(sel_df: pd.DataFrame) -> pd.DataFrame:
    # An artist can appear under several roles for one track: keep one row per (track, playlist).
    if "track_id" in sel_df.columns:
        sel_df = sel_df.drop_duplicates(subset=["track_id", "playlist_name"])
    if "duration_raw" in sel_df.columns:
        sel_df["duration_min"] = sel_df["duration_raw"] / 60_000
    return sel_df


def artist_rows(df: pd.DataFrame, artist: str) -> pd.DataFrame:
    """Rows of one artist (by primary artist_name), one per (track_id, playlist_name).

    Adds duration_min (duration_raw milliseconds / 60000) when duration_raw exists. A copy.
    """
    return _finish_selection(df[df["artist_name"] == artist].copy())


def album_rows(df: pd.DataFrame, album_name: str, artist_name: str) -> pd.DataFrame:
    """Rows of one album by one artist, one per (track_id, playlist_name), with duration_min.

    Same shape as artist_rows. A copy.
    """
    return _finish_selection(df[(df["album_name"] == album_name) & (df["artist_name"] == artist_name)].copy())


def selection_kpis(sel_df: pd.DataFrame, min_tracks: int) -> SelectionKpis:
    """Track count, playlist count and whether the selection reaches `min_tracks`.

    Args:
        sel_df: output of artist_rows / album_rows; needs playlist_name.
        min_tracks: MIN_TRACKS_ARTIST or MIN_TRACKS_ALBUM.
    """
    track_count = sel_df["track_id"].nunique() if "track_id" in sel_df.columns else len(sel_df)
    return SelectionKpis(track_count, sel_df["playlist_name"].nunique(), track_count >= min_tracks)


def top_genre_tags(genres: pd.Series, n: int = 8) -> list[str]:
    """The n most frequent genre tags in a column of comma-separated genre strings.

    Missing values and blank tags are ignored; ties keep first-seen order.

    Args:
        genres: e.g. sel_df["artist_genres"].
        n: how many tags to return.
    """
    tags: list[str] = []
    for val in genres.dropna():
        tags.extend([g.strip() for g in str(val).split(",") if g.strip()])
    return pd.Series(tags).value_counts().head(n).index.tolist()


def selection_genres(sel_df: pd.DataFrame, n: int = 8) -> list[str]:
    """Top genre tags of a selection; empty when artist_genres is missing or entirely empty."""
    if "artist_genres" not in sel_df.columns or sel_df["artist_genres"].isna().all():
        return []
    return top_genre_tags(sel_df["artist_genres"], n)


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

def track_table(sel_df: pd.DataFrame, include_album: bool, include_playlist: bool = True,
                include_year: bool = True) -> pd.DataFrame:
    """Display table of tracks: Track, [Album], [Playlist], [Popularity], [Year], [Duration].

    Columns appear in that order and only when their source column exists (album_name,
    popularity_raw, release_year, duration_min). Sorted by Popularity descending, or by Track
    ascending when there is no popularity. Year is cast to nullable Int64 and Duration is
    "m:ss" ("—" when missing). Used for the main list, a clicked playlist, a clicked popularity
    bin and a clicked year.

    Args:
        sel_df: output of artist_rows / album_rows (or a subset of it).
        include_album: show Album when album_name exists.
        include_playlist: show Playlist.
        include_year: show Year when release_year exists.
    Returns:
        DataFrame with a fresh RangeIndex.
    """
    cols = ["track_name"]
    rename = {"track_name": "Track"}
    if include_album and "album_name" in sel_df.columns:
        cols.append("album_name")
        rename["album_name"] = "Album"
    if include_playlist:
        cols.append("playlist_name")
        rename["playlist_name"] = "Playlist"
    has_popularity = "popularity_raw" in sel_df.columns
    if has_popularity:
        cols.append("popularity_raw")
        rename["popularity_raw"] = "Popularity"
    if include_year and "release_year" in sel_df.columns:
        cols.append("release_year")
        rename["release_year"] = "Year"
    work = sel_df
    if "duration_min" in sel_df.columns:
        work = sel_df.copy()
        work["_dur"] = work["duration_min"].apply(lambda x: fmt_duration(x) if pd.notna(x) else "—")
        cols.append("_dur")
        rename["_dur"] = "Duration"
    sort_col = "popularity_raw" if has_popularity else "track_name"
    table = (
        work[cols]
        .rename(columns=rename)
        .sort_values(rename[sort_col], ascending=not has_popularity)
        .reset_index(drop=True)
    )
    if "Year" in table.columns:
        table["Year"] = table["Year"].astype("Int64")
    return table


def popularity_bin_tracks(sel_df: pd.DataFrame, bin_start: int) -> pd.DataFrame:
    """Rows with bin_start <= popularity_raw < bin_start + POPULARITY_BIN_SIZE (needs popularity_raw)."""
    return sel_df[
        (sel_df["popularity_raw"] >= bin_start)
        & (sel_df["popularity_raw"] < bin_start + POPULARITY_BIN_SIZE)
    ].copy()


def album_breakdown(sel_df: pd.DataFrame) -> pd.DataFrame:
    """Albums of an artist selection: DataFrame [album_name, count] (unique track_ids) by count descending.

    Needs album_name and track_id.
    """
    return (
        sel_df.groupby("album_name", observed=True)["track_id"]
        .nunique()
        .reset_index(name="count")
        .sort_values("count", ascending=False)
    )


def deep_dive_albums(album_counts: pd.DataFrame, min_tracks: int = MIN_TRACKS_ALBUM) -> list[str]:
    """Album names from album_breakdown with at least `min_tracks` unique tracks (same order)."""
    return album_counts[album_counts["count"] >= min_tracks]["album_name"].tolist()


def playlist_distribution(sel_df: pd.DataFrame) -> pd.DataFrame:
    """Rows per playlist: DataFrame [playlist_name, count] by count descending."""
    return (
        sel_df.groupby("playlist_name", observed=True)
        .size()
        .reset_index(name="count")
        .sort_values("count", ascending=False)
    )


# ---------------------------------------------------------------------------
# Extremes, audio, popularity, release years
# ---------------------------------------------------------------------------

def track_extremes(sel_df: pd.DataFrame, include_years: bool) -> TrackExtremes:
    """Longest/shortest, most/least popular and oldest/newest tracks of a selection.

    Rows with a missing value in the relevant column are ignored for that pair.

    Args:
        sel_df: output of artist_rows / album_rows.
        include_years: compute oldest/newest (the page does it for artists only, since an
            album's tracks share one year).
    Returns:
        TrackExtremes; a pair is None when its column is missing or has no values.
    """
    def pair(col: str) -> tuple[pd.Series | None, pd.Series | None]:
        if col not in sel_df.columns:
            return None, None
        valid = sel_df.dropna(subset=[col])
        if valid.empty:
            return None, None
        return valid.loc[valid[col].idxmax()], valid.loc[valid[col].idxmin()]

    longest, shortest = pair("duration_min")
    most_pop, least_pop = pair("popularity_raw")
    newest, oldest = pair("release_year") if include_years else (None, None)
    return TrackExtremes(longest, shortest, most_pop, least_pop, oldest, newest)


def audio_radar(sel_df: pd.DataFrame, collection_df: pd.DataFrame) -> AudioRadar:
    """Audio fingerprint: mean of each radar feature plus normalized tempo.

    Args:
        sel_df: output of artist_rows / album_rows.
        collection_df: the whole collection; its tempo min/max normalize the selection's tempo.
    Returns:
        AudioRadar. The page shows the radar only with >= 3 features, enough tracks and
        n_enriched > 0; when n_enriched is 0 the axis/mean fields are empty.
    """
    available = [f for f in RADAR_FEATURES if f in sel_df.columns]
    n_enriched = int(sel_df[available].dropna(how="all").shape[0]) if available else 0
    if n_enriched == 0:
        return AudioRadar(available, 0, [], [], [], None)
    means = sel_df[available].mean()
    labels = list(available)
    values = means.tolist()
    mean_tempo = None
    if "tempo" in sel_df.columns:
        t_min = collection_df["tempo"].min()
        t_max = collection_df["tempo"].max()
        mean_tempo = sel_df["tempo"].mean()
        values = values + [(mean_tempo - t_min) / (t_max - t_min) if t_max > t_min else 0.5]
        labels = labels + ["tempo"]
    return AudioRadar(available, n_enriched, labels, values, means.tolist(), mean_tempo)


def popularity_distribution(sel_df: pd.DataFrame) -> PopularityDistribution:
    """Histogram (5-point bins from 0 to 104, empty bins dropped) and statistics of popularity_raw.

    Args:
        sel_df: output of artist_rows / album_rows; needs popularity_raw.
    """
    pop = sel_df["popularity_raw"].dropna()
    starts = list(range(0, 105, POPULARITY_BIN_SIZE))[:-1]
    counts = [int(((pop >= b) & (pop < b + POPULARITY_BIN_SIZE)).sum()) for b in starts]
    kept = [(f"{b}–{b + POPULARITY_BIN_SIZE - 1}", c, b) for c, b in zip(counts, starts) if c > 0]
    return PopularityDistribution(
        [k[0] for k in kept], [k[1] for k in kept], [k[2] for k in kept],
        pop.mean(), pop.median(), pop.max(), pop.min(),
    )


def release_year_counts(sel_df: pd.DataFrame) -> pd.DataFrame:
    """Rows per release year: DataFrame [release_year (Int64), count] newest year first. Needs release_year."""
    counts = (
        sel_df.dropna(subset=["release_year"])
        .groupby("release_year", observed=True)
        .size()
        .reset_index(name="count")
        .sort_values("release_year", ascending=False)
    )
    counts["release_year"] = counts["release_year"].astype("Int64")
    return counts


def year_summary(sel_df: pd.DataFrame) -> YearSummary | None:
    """Average, oldest, newest year and span of an artist selection; None without any year."""
    years = sel_df["release_year"].dropna()
    if years.empty:
        return None
    oldest, newest = int(years.min()), int(years.max())
    return YearSummary(years.mean(), oldest, newest, newest - oldest)


def album_release(sel_df: pd.DataFrame, current_year: int) -> AlbumRelease | None:
    """Release year of an album (most common year among its rows) and how long ago it was.

    Args:
        sel_df: output of album_rows; needs release_year.
        current_year: the year to measure against (the caller supplies the clock).
    Returns:
        AlbumRelease, or None when no row has a year.
    """
    years = sel_df["release_year"].dropna()
    if years.empty:
        return None
    year = int(years.mode().iloc[0])
    return AlbumRelease(year, current_year - year)
