"""
Test suite for pages/3_Artist_Album.py
Run with:  pytest tests/test_artist_album.py -v
"""

import datetime
import numpy as np
import pandas as pd
import pytest
from unittest.mock import patch


MIN_TRACKS_ARTIST = 5
MIN_TRACKS_ALBUM  = 3
BIN_SIZE          = 5
RADAR_FEATURES    = ["energy", "valence", "danceability", "acousticness", "speechiness", "liveness"]


# ---------------------------------------------------------------------------
# Helpers — mirrors pure logic from 3_Artist_Album.py
# ---------------------------------------------------------------------------

def fmt_duration(minutes: float) -> str:
    """This page uses divmod — note: different from Overview/Playlist Detail."""
    total_sec = int(round(minutes * 60))
    m, s = divmod(total_sec, 60)
    return f"{m}:{s:02d}"


def genre_pills_html(genres_series: pd.Series) -> str:
    all_genres: list[str] = []
    for val in genres_series.dropna():
        all_genres.extend([g.strip() for g in str(val).split(",") if g.strip()])
    counts = pd.Series(all_genres).value_counts()
    top = counts.head(8).index.tolist()
    pills = "".join(
        f'<span style="background:#1DB954;color:#000;border-radius:12px;'
        f'padding:2px 10px;margin:2px;font-size:0.75rem;font-weight:600;'
        f'display:inline-block;">{g}</span>'
        for g in top
    )
    return pills


def eligible_artists(df: pd.DataFrame, min_tracks: int = MIN_TRACKS_ARTIST):
    track_counts_all = df["artist_name"].value_counts()
    filtered = track_counts_all[track_counts_all >= min_tracks]
    return sorted(filtered.index.tolist()), filtered


def eligible_albums(df: pd.DataFrame, min_tracks: int = MIN_TRACKS_ALBUM):
    pair_counts = (
        df.dropna(subset=["album_name", "artist_name", "track_id"])
        .groupby(["album_name", "artist_name"], observed=True)["track_id"]
        .nunique()
        .reset_index(name="n")
    )
    pair_counts = pair_counts[pair_counts["n"] >= min_tracks].copy()
    pair_counts["label"] = pair_counts["album_name"] + " — " + pair_counts["artist_name"]
    pair_counts = pair_counts.sort_values("label")
    return pair_counts.reset_index(drop=True)


def build_rank_map_artists(df: pd.DataFrame, min_tracks: int = MIN_TRACKS_ARTIST) -> dict:
    track_counts_all = df["artist_name"].value_counts()
    ranked = (
        track_counts_all[track_counts_all >= min_tracks]
        .sort_values(ascending=False)
        .reset_index()
    )
    ranked.columns = ["artist_name", "count"]
    return {row["artist_name"]: i + 1 for i, row in ranked.head(20).iterrows()}


def build_rank_map_albums(pair_counts: pd.DataFrame) -> dict:
    top10 = pair_counts.nlargest(10, "n").reset_index(drop=True)
    return {row["label"]: i + 1 for i, row in top10.iterrows()}


def build_options(names: list, rank_map: dict) -> list:
    return [
        f"🏆 #{rank_map[name]} · {name}" if name in rank_map else name
        for name in names
    ]


def dedup_sel_df(sel_df: pd.DataFrame) -> pd.DataFrame:
    if "track_id" in sel_df.columns:
        return sel_df.drop_duplicates(subset=["track_id", "playlist_name"])
    return sel_df


def normalize_duration(sel_df: pd.DataFrame, is_yc: bool) -> pd.DataFrame:
    sel_df = sel_df.copy()
    if "duration_raw" in sel_df.columns:
        sel_df["duration_min"] = sel_df["duration_raw"] / 60_000 if is_yc else sel_df["duration_raw"]
    return sel_df


def compute_popularity_bins(pop_vals: pd.Series, bin_size: int = BIN_SIZE):
    bin_edges  = list(range(0, 105, bin_size))
    bin_labels = [f"{b}–{b + bin_size - 1}" for b in bin_edges[:-1]]
    bin_counts = [
        int(((pop_vals >= b) & (pop_vals < b + bin_size)).sum())
        for b in bin_edges[:-1]
    ]
    non_zero = [(l, c, b) for l, c, b in zip(bin_labels, bin_counts, bin_edges[:-1]) if c > 0]
    return non_zero


def compute_release_timeline(sel_df: pd.DataFrame) -> pd.DataFrame:
    return (
        sel_df.dropna(subset=["release_year"])
        .groupby("release_year", observed=True)
        .size()
        .reset_index(name="count")
        .sort_values("release_year", ascending=False)
    )


def compute_tempo_norm(sel_df: pd.DataFrame, df_all: pd.DataFrame) -> float:
    t_min = df_all["tempo"].min()
    t_max = df_all["tempo"].max()
    mean_raw = sel_df["tempo"].mean()
    return (mean_raw - t_min) / (t_max - t_min) if t_max > t_min else 0.5


def compute_playlist_dist(sel_df: pd.DataFrame) -> pd.DataFrame:
    return (
        sel_df.groupby("playlist_name", observed=True)
        .size()
        .reset_index(name="count")
        .sort_values("count", ascending=False)
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_artist_df(artist: str = "ArtistX", n_tracks: int = 8,
                    n_playlists: int = 2) -> pd.DataFrame:
    """Generate tracks for a single artist spread across n_playlists."""
    rows = []
    for i in range(n_tracks):
        pl = f"PL{(i % n_playlists) + 1}"
        rows.append({
            "track_id":      f"t{i}",
            "track_name":    f"Song {i}",
            "artist_name":   artist,
            "artist_display":artist,
            "playlist_name": pl,
            "album_name":    f"Album {i // 3}",
            "popularity_raw": 50 + i,
            "release_year":   2000 + i,
            "duration_raw":   3.5 + i * 0.1,
            "artist_genres":  "rock, indie",
            "energy":         0.6 + i * 0.01,
            "valence":        0.5,
            "danceability":   0.7,
            "acousticness":   0.3,
            "speechiness":    0.05,
            "liveness":       0.1,
            "tempo":          120.0 + i,
        })
    return pd.DataFrame(rows)


@pytest.fixture
def small_df():
    """One qualifying artist (8 tracks), one below threshold (2 tracks)."""
    big = _make_artist_df("ArtistX", n_tracks=8)
    small = _make_artist_df("ArtistTiny", n_tracks=2)
    return pd.concat([big, small], ignore_index=True)


@pytest.fixture
def sel_df():
    """Already-filtered df for ArtistX."""
    return _make_artist_df("ArtistX", n_tracks=8, n_playlists=2)


@pytest.fixture
def multi_artist_df():
    """Three artists — only the first two meet the 5-track threshold."""
    a = _make_artist_df("Artist A", n_tracks=10)
    b = _make_artist_df("Artist B", n_tracks=6)
    c = _make_artist_df("Artist C", n_tracks=2)
    return pd.concat([a, b, c], ignore_index=True)


@pytest.fixture
def album_df():
    """Two albums for the same artist, both meeting MIN_TRACKS_ALBUM."""
    rows = []
    for album, n in [("Album X", 5), ("Album Y", 4), ("Short Album", 1)]:
        for i in range(n):
            rows.append({
                "track_id":    f"{album}-t{i}",
                "track_name":  f"{album} Song {i}",
                "artist_name": "ArtistX",
                "album_name":  album,
                "playlist_name":"PL1",
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# TC-01 – TC-06  fmt_duration  (divmod implementation)
# ---------------------------------------------------------------------------

class TestFmtDuration:
    def test_normal_float(self):
        assert fmt_duration(3.5) == "3:30"

    def test_zero(self):
        assert fmt_duration(0.0) == "0:00"

    def test_whole_minutes(self):
        assert fmt_duration(5.0) == "5:00"

    def test_seconds_zero_padded(self):
        assert fmt_duration(3 + 5 / 60) == "3:05"

    def test_rollover_at_boundary(self):
        # 4 min 59.9 sec → rounds to 5:00 (not 4:60)
        val = (5 * 60 - 0.1) / 60
        assert fmt_duration(val) == "5:00"

    def test_large_value(self):
        assert fmt_duration(60.0) == "60:00"


# ---------------------------------------------------------------------------
# TC-07 – TC-10  genre_pills_html
# ---------------------------------------------------------------------------

class TestGenrePillsHtml:
    def test_produces_pill_spans(self):
        s = pd.Series(["rock, pop", "rock"])
        html = genre_pills_html(s)
        assert "<span" in html
        assert "rock" in html

    def test_top_8_limit(self):
        # 10 distinct genres — only top 8 should appear
        genres = [f"genre{i}" for i in range(10)]
        s = pd.Series([", ".join(genres)])
        html = genre_pills_html(s)
        assert html.count("<span") == 8

    def test_nan_values_ignored(self):
        s = pd.Series([None, "jazz"])
        html = genre_pills_html(s)
        assert "jazz" in html
        assert "None" not in html

    def test_empty_series_returns_empty_string(self):
        html = genre_pills_html(pd.Series([], dtype=str))
        assert html == ""

    def test_frequency_ordering(self):
        # "rock" appears 3 times, "pop" once — rock should be first (highest count)
        s = pd.Series(["rock", "rock, pop", "rock"])
        html = genre_pills_html(s)
        assert html.index("rock") < html.index("pop")


# ---------------------------------------------------------------------------
# TC-11 – TC-16  Eligible artists / albums filtering
# ---------------------------------------------------------------------------

class TestEligibleArtists:
    def test_below_threshold_excluded(self, small_df):
        eligible, _ = eligible_artists(small_df)
        assert "ArtistTiny" not in eligible

    def test_above_threshold_included(self, small_df):
        eligible, _ = eligible_artists(small_df)
        assert "ArtistX" in eligible

    def test_sorted_alphabetically(self, multi_artist_df):
        eligible, _ = eligible_artists(multi_artist_df)
        assert eligible == sorted(eligible)

    def test_threshold_boundary(self):
        # Exactly MIN_TRACKS_ARTIST tracks — should be included
        df = _make_artist_df("BorderArtist", n_tracks=MIN_TRACKS_ARTIST)
        eligible, _ = eligible_artists(df)
        assert "BorderArtist" in eligible

    def test_one_below_threshold_excluded(self):
        df = _make_artist_df("AlmostArtist", n_tracks=MIN_TRACKS_ARTIST - 1)
        eligible, _ = eligible_artists(df)
        assert "AlmostArtist" not in eligible


class TestEligibleAlbums:
    def test_short_album_excluded(self, album_df):
        pairs = eligible_albums(album_df)
        labels = pairs["label"].tolist()
        assert not any("Short Album" in l for l in labels)

    def test_qualifying_albums_included(self, album_df):
        pairs = eligible_albums(album_df)
        labels = pairs["label"].tolist()
        assert any("Album X" in l for l in labels)
        assert any("Album Y" in l for l in labels)

    def test_label_format(self, album_df):
        pairs = eligible_albums(album_df)
        for lbl in pairs["label"]:
            assert " — " in lbl

    def test_sorted_by_label(self, album_df):
        pairs = eligible_albums(album_df)
        labels = pairs["label"].tolist()
        assert labels == sorted(labels)

    def test_unique_track_count_not_row_count(self):
        # Same track_id saved twice in same playlist — should count as 1 unique
        df = pd.DataFrame({
            "track_id":    ["t1", "t1", "t2", "t3"],
            "artist_name": ["A", "A", "A", "A"],
            "album_name":  ["Alb", "Alb", "Alb", "Alb"],
            "playlist_name":["PL1","PL1","PL1","PL1"],
        })
        pairs = eligible_albums(df, min_tracks=3)
        assert int(pairs.iloc[0]["n"]) == 3  # 3 unique track_ids


# ---------------------------------------------------------------------------
# TC-17 – TC-21  Rank map & options display formatting
# ---------------------------------------------------------------------------

class TestRankMapAndOptions:
    def test_top_artist_gets_rank_1(self, multi_artist_df):
        rank_map = build_rank_map_artists(multi_artist_df)
        # Artist A has 10 tracks — highest count
        assert rank_map["Artist A"] == 1

    def test_second_artist_gets_rank_2(self, multi_artist_df):
        rank_map = build_rank_map_artists(multi_artist_df)
        assert rank_map["Artist B"] == 2

    def test_below_threshold_artist_not_in_rank_map(self, multi_artist_df):
        rank_map = build_rank_map_artists(multi_artist_df)
        assert "Artist C" not in rank_map

    def test_ranked_option_contains_trophy_and_rank(self, multi_artist_df):
        rank_map = build_rank_map_artists(multi_artist_df)
        names = ["Artist A", "Artist B"]
        options = build_options(names, rank_map)
        assert "🏆 #1" in options[0]
        assert "🏆 #2" in options[1]

    def test_unranked_option_has_no_trophy(self):
        rank_map = {}  # empty — no one ranked
        options = build_options(["Artist Z"], rank_map)
        assert options[0] == "Artist Z"

    def test_album_rank_map_top_album_is_rank_1(self, album_df):
        pairs = eligible_albums(album_df)
        rank_map = build_rank_map_albums(pairs)
        # Album X has 5 unique tracks — should be rank 1
        top_label = next(l for l in rank_map if "Album X" in l)
        assert rank_map[top_label] == 1


# ---------------------------------------------------------------------------
# TC-22 – TC-26  sel_df filtering and deduplication
# ---------------------------------------------------------------------------

class TestSelDfFiltering:
    def test_artist_mode_filters_correct_rows(self, small_df):
        sel = small_df[small_df["artist_name"] == "ArtistX"].copy()
        assert (sel["artist_name"] == "ArtistX").all()
        assert "ArtistTiny" not in sel["artist_name"].values

    def test_album_mode_filters_by_album_and_artist(self, album_df):
        pairs = eligible_albums(album_df)
        pair_row = pairs[pairs["album_name"] == "Album X"].iloc[0]
        sel = album_df[
            (album_df["album_name"] == pair_row["album_name"]) &
            (album_df["artist_name"] == pair_row["artist_name"])
        ].copy()
        assert (sel["album_name"] == "Album X").all()

    def test_dedup_removes_same_track_id_same_playlist(self):
        df = pd.DataFrame({
            "track_id":      ["t1", "t1", "t2"],
            "playlist_name": ["PL1", "PL1", "PL1"],
        })
        result = dedup_sel_df(df)
        assert len(result) == 2

    def test_dedup_keeps_same_track_id_different_playlists(self):
        # Same track in PL1 and PL2 — both rows must be kept
        df = pd.DataFrame({
            "track_id":      ["t1", "t1", "t2"],
            "playlist_name": ["PL1", "PL2", "PL1"],
        })
        result = dedup_sel_df(df)
        assert len(result) == 3

    def test_track_count_uses_nunique_on_track_id(self, sel_df):
        deduped = dedup_sel_df(sel_df)
        assert deduped["track_id"].nunique() == len(deduped)


# ---------------------------------------------------------------------------
# TC-27 – TC-29  Duration normalization
# ---------------------------------------------------------------------------

class TestDurationNormalization:
    def test_db_mode_uses_raw_directly(self, sel_df):
        result = normalize_duration(sel_df, is_yc=False)
        pd.testing.assert_series_equal(
            result["duration_min"].reset_index(drop=True),
            sel_df["duration_raw"].reset_index(drop=True),
            check_names=False,
        )

    def test_yc_mode_divides_by_60000(self, sel_df):
        sel_ms = sel_df.copy()
        sel_ms["duration_raw"] = sel_ms["duration_raw"] * 60_000
        result = normalize_duration(sel_ms, is_yc=True)
        expected = sel_df["duration_raw"]
        pd.testing.assert_series_equal(
            result["duration_min"].reset_index(drop=True),
            expected.reset_index(drop=True),
            check_names=False,
        )

    def test_no_duration_column_leaves_df_unchanged(self):
        df = pd.DataFrame({"track_id": ["t1"], "track_name": ["S"]})
        result = normalize_duration(df, is_yc=False)
        assert "duration_min" not in result.columns


# ---------------------------------------------------------------------------
# TC-30 – TC-35  Popularity bins
# ---------------------------------------------------------------------------

class TestPopularityBins:
    def test_label_format(self):
        bins = compute_popularity_bins(pd.Series([10, 20]))
        labels = [x[0] for x in bins]
        for l in labels:
            assert "–" in l

    def test_zero_count_bins_excluded(self):
        # All tracks in range 10–14 — only one bin should be non-zero
        bins = compute_popularity_bins(pd.Series([10, 11, 12]))
        assert len(bins) == 1
        assert bins[0][0] == "10–14"

    def test_bin_count_correct(self):
        pop = pd.Series([5, 5, 15, 25])
        bins = compute_popularity_bins(pop)
        counts = {x[0]: x[1] for x in bins}
        assert counts.get("5–9", 0) == 2
        assert counts.get("15–19", 0) == 1
        assert counts.get("25–29", 0) == 1

    def test_boundary_value_in_lower_bin(self):
        # Value exactly at bin edge belongs to that bin (>= b, < b+5)
        pop = pd.Series([5])
        bins = compute_popularity_bins(pop)
        labels = [x[0] for x in bins]
        assert "5–9" in labels
        assert "0–4" not in labels

    def test_total_count_matches_input(self):
        pop = pd.Series(range(0, 100, 10))
        bins = compute_popularity_bins(pop)
        total = sum(x[1] for x in bins)
        assert total == len(pop)

    def test_empty_series_returns_no_bins(self):
        bins = compute_popularity_bins(pd.Series([], dtype=float))
        assert bins == []


# ---------------------------------------------------------------------------
# TC-36 – TC-39  Release timeline (artist mode)
# ---------------------------------------------------------------------------

class TestReleaseTimeline:
    def test_sorted_descending_by_year(self, sel_df):
        tl = compute_release_timeline(sel_df)
        years = tl["release_year"].tolist()
        assert years == sorted(years, reverse=True)

    def test_nan_years_excluded(self, sel_df):
        df = sel_df.copy()
        df.loc[0, "release_year"] = None
        tl = compute_release_timeline(df)
        assert tl["count"].sum() == len(sel_df) - 1

    def test_count_per_year_correct(self):
        df = pd.DataFrame({
            "release_year": [2000, 2000, 2001],
            "track_id":     ["t1", "t2", "t3"],
        })
        tl = compute_release_timeline(df)
        row_2000 = tl[tl["release_year"] == 2000]
        assert int(row_2000["count"].iloc[0]) == 2

    def test_empty_after_nan_drop(self):
        df = pd.DataFrame({"release_year": [None, None], "track_id": ["t1", "t2"]})
        tl = compute_release_timeline(df)
        assert tl.empty


# ---------------------------------------------------------------------------
# TC-40 – TC-42  Album release year (album mode)
# ---------------------------------------------------------------------------

class TestAlbumReleaseYear:
    def test_mode_year_selected(self):
        yr_vals = pd.Series([1995, 1995, 1996])
        album_year = int(yr_vals.mode().iloc[0])
        assert album_year == 1995

    def test_years_ago_calculation(self):
        album_year = 2010
        years_ago = datetime.date.today().year - album_year
        assert years_ago == 2026 - 2010  # 16

    def test_this_year_label(self):
        album_year = datetime.date.today().year
        years_ago = datetime.date.today().year - album_year
        ago_str = f"{years_ago} years ago" if years_ago > 0 else "This year"
        assert ago_str == "This year"


# ---------------------------------------------------------------------------
# TC-43 – TC-47  Extremes
# ---------------------------------------------------------------------------

class TestExtremes:
    def test_longest_track_identified(self, sel_df):
        df = normalize_duration(sel_df, is_yc=False)
        dur_valid = df.dropna(subset=["duration_min"])
        longest = dur_valid.loc[dur_valid["duration_min"].idxmax()]
        assert longest["duration_min"] == df["duration_min"].max()

    def test_shortest_track_identified(self, sel_df):
        df = normalize_duration(sel_df, is_yc=False)
        dur_valid = df.dropna(subset=["duration_min"])
        shortest = dur_valid.loc[dur_valid["duration_min"].idxmin()]
        assert shortest["duration_min"] == df["duration_min"].min()

    def test_most_popular_track_identified(self, sel_df):
        pop_valid = sel_df.dropna(subset=["popularity_raw"])
        most_pop = pop_valid.loc[pop_valid["popularity_raw"].idxmax()]
        assert most_pop["popularity_raw"] == sel_df["popularity_raw"].max()

    def test_least_popular_track_identified(self, sel_df):
        pop_valid = sel_df.dropna(subset=["popularity_raw"])
        least_pop = pop_valid.loc[pop_valid["popularity_raw"].idxmin()]
        assert least_pop["popularity_raw"] == sel_df["popularity_raw"].min()

    def test_oldest_track_identified(self, sel_df):
        yr_valid = sel_df.dropna(subset=["release_year"])
        oldest = yr_valid.loc[yr_valid["release_year"].idxmin()]
        assert oldest["release_year"] == sel_df["release_year"].min()

    def test_nan_duration_rows_excluded(self):
        df = pd.DataFrame({
            "duration_min": [None, 3.5, 5.0],
            "track_name":   ["A", "B", "C"],
        })
        dur_valid = df.dropna(subset=["duration_min"])
        longest = dur_valid.loc[dur_valid["duration_min"].idxmax()]
        assert longest["track_name"] == "C"


# ---------------------------------------------------------------------------
# TC-48 – TC-50  Playlist distribution
# ---------------------------------------------------------------------------

class TestPlaylistDistribution:
    def test_sorted_descending(self, sel_df):
        dist = compute_playlist_dist(sel_df)
        counts = dist["count"].tolist()
        assert counts == sorted(counts, reverse=True)

    def test_count_per_playlist_correct(self):
        df = pd.DataFrame({
            "track_id":      ["t1", "t2", "t3", "t4"],
            "playlist_name": ["PL1", "PL1", "PL1", "PL2"],
        })
        dist = compute_playlist_dist(df)
        pl1 = dist[dist["playlist_name"] == "PL1"]
        assert int(pl1["count"].iloc[0]) == 3

    def test_all_playlists_present(self, sel_df):
        dist = compute_playlist_dist(sel_df)
        assert set(dist["playlist_name"]) == set(sel_df["playlist_name"].unique())


# ---------------------------------------------------------------------------
# TC-51 – TC-55  Audio fingerprint (radar)
# ---------------------------------------------------------------------------

class TestAudioFingerprint:
    def test_available_radar_filters_missing_cols(self):
        df = pd.DataFrame({"energy": [0.8], "valence": [0.6]})
        avail = [f for f in RADAR_FEATURES if f in df.columns]
        assert avail == ["energy", "valence"]

    def test_at_least_3_features_required(self):
        df = pd.DataFrame({"energy": [0.8], "valence": [0.6]})
        avail = [f for f in RADAR_FEATURES if f in df.columns]
        assert len(avail) < 3  # not enough → section skipped

    def test_means_computed_correctly(self, sel_df):
        avail = [f for f in RADAR_FEATURES if f in sel_df.columns]
        means = sel_df[avail].mean()
        assert means["energy"] == pytest.approx(sel_df["energy"].mean())

    def test_tempo_normalized_to_0_1(self, sel_df):
        df_all = sel_df.copy()
        norm = compute_tempo_norm(sel_df, df_all)
        assert 0.0 <= norm <= 1.0

    def test_tempo_norm_same_min_max_returns_half(self, sel_df):
        df_all = sel_df.copy()
        df_all["tempo"] = 120.0  # flat — t_max == t_min
        sel = sel_df.copy()
        sel["tempo"] = 120.0
        norm = compute_tempo_norm(sel, df_all)
        assert norm == pytest.approx(0.5)

    def test_polygon_closed_correctly(self, sel_df):
        avail = [f for f in RADAR_FEATURES if f in sel_df.columns]
        means = sel_df[avail].mean()
        values = means.tolist()
        labels = avail

        closed_labels = labels + [labels[0]]
        closed_values = values + [values[0]]

        assert closed_labels[0] == closed_labels[-1]
        assert closed_values[0] == closed_values[-1]


# ---------------------------------------------------------------------------
# TC-56 – TC-60  AppTest integration (requires streamlit >= 1.35)
# ---------------------------------------------------------------------------

try:
    from streamlit.testing.v1 import AppTest
    APPTEST_AVAILABLE = True
except ImportError:
    APPTEST_AVAILABLE = False


def _make_full_df():
    a = _make_artist_df("Artist Alpha", n_tracks=8, n_playlists=2)
    b = _make_artist_df("Artist Beta",  n_tracks=6, n_playlists=2)
    # Give each track a proper album_name column
    df = pd.concat([a, b], ignore_index=True)
    return df


@pytest.mark.skipif(not APPTEST_AVAILABLE, reason="streamlit.testing not available")
class TestArtistAlbumPageRender:

    def _run_page(self, mock_df=None, session_state=None):
        if mock_df is None:
            mock_df = _make_full_df()

        at = AppTest.from_file("pages/3_Artist_Album.py", default_timeout=30)
        if session_state:
            for k, v in session_state.items():
                at.session_state[k] = v

        with patch("db.queries.get_all_tracks", return_value=mock_df), \
             patch("utils.inject_global_css"), \
             patch("utils.inject_sidebar_nav"), \
             patch("utils.check_collection_mode", return_value=True), \
             patch("utils.spotify_icon_html", return_value=""), \
             patch("utils.page_brand_html", return_value=""):
            at.run()

        return at

    def test_TC56_artist_mode_renders_without_exception(self):
        at = self._run_page()
        assert not at.exception

    def test_TC57_album_mode_renders_without_exception(self):
        mock_df = _make_full_df()
        at = AppTest.from_file("pages/3_Artist_Album.py", default_timeout=30)
        # Keep all patches active for BOTH runs — switching the radio triggers a
        # full page re-execution, so inject_sidebar_nav must stay mocked.
        with patch("db.queries.get_all_tracks", return_value=mock_df), \
             patch("utils.inject_global_css"), \
             patch("utils.inject_sidebar_nav"), \
             patch("utils.check_collection_mode", return_value=True), \
             patch("utils.spotify_icon_html", return_value=""), \
             patch("utils.page_brand_html", return_value=""):
            at.run()
            assert not at.exception
            at.radio[0].set_value("💿 Album")
            at.run()
        assert not at.exception

    def test_TC58_no_eligible_artists_shows_info(self):
        # All artists have fewer than MIN_TRACKS_ARTIST tracks
        tiny = pd.concat([
            _make_artist_df("A", n_tracks=2),
            _make_artist_df("B", n_tracks=3),
        ])
        at = self._run_page(mock_df=tiny)
        # Page calls st.stop() after st.info — no exception expected
        assert not at.exception

    def test_TC59_yc_mode_renders_without_exception(self):
        at = self._run_page(session_state={"mode": "🔗 Your Collection"})
        assert not at.exception

    def test_TC60_without_audio_features_renders_without_exception(self):
        df = _make_full_df().drop(
            columns=["energy", "valence", "danceability",
                     "acousticness", "speechiness", "liveness", "tempo"],
            errors="ignore",
        )
        at = self._run_page(mock_df=df)
        assert not at.exception
