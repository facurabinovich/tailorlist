"""
Test suite for pages/1_Overview.py
Run with:  pytest tests/test_overview.py -v
"""

import datetime
import math
import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers — mirrors the logic in 1_Overview.py so we can test it in isolation
# without pulling in Streamlit at import time.
# ---------------------------------------------------------------------------

def fmt_duration(minutes: float) -> str:
    m = int(minutes)
    s = int(round((minutes - m) * 60))
    return f"{m}:{s:02d}"


def compute_kpis(deduped: pd.DataFrame, is_your_collection: bool = False):
    """Replicate all KPI derivations from 1_Overview.py."""
    total_tracks = len(deduped)
    total_artists = deduped["artist_name"].nunique() if "artist_name" in deduped.columns else 0
    total_playlists = deduped["playlist_name"].nunique() if "playlist_name" in deduped.columns else 0
    avg_popularity = deduped["popularity_raw"].mean() if "popularity_raw" in deduped.columns else None
    decade_mode = (
        int(deduped["decade"].mode()[0])
        if "decade" in deduped.columns and deduped["decade"].notna().any()
        else None
    )

    avg_duration = None
    if "duration_raw" in deduped.columns:
        raw = deduped["duration_raw"].mean()
        avg_duration = (raw / 60000) if is_your_collection else raw

    return {
        "total_tracks": total_tracks,
        "total_artists": total_artists,
        "total_playlists": total_playlists,
        "avg_popularity": avg_popularity,
        "decade_mode": decade_mode,
        "avg_duration": avg_duration,
    }


def compute_oldest_newest(deduped: pd.DataFrame):
    """Replicate oldest/newest/span logic from 1_Overview.py."""
    if "release_year" not in deduped.columns or not deduped["release_year"].notna().any():
        return None, None, None, None, None
    valid = deduped.dropna(subset=["release_year"]).copy()
    valid["release_year"] = valid["release_year"].astype(int)
    oldest = valid.loc[valid["release_year"].idxmin()]
    newest = valid.loc[valid["release_year"].idxmax()]
    oldest_year = int(valid["release_year"].min())
    newest_year = int(valid["release_year"].max())
    span = newest_year - oldest_year
    return oldest, newest, oldest_year, newest_year, span


def compute_listening_age(deduped: pd.DataFrame, current_year: int = 2026):
    """Replicate listening_age / median_year / est_birth from 1_Overview.py."""
    if "release_year" not in deduped.columns or not deduped["release_year"].notna().any():
        return None, None, None
    median_year = int(deduped["release_year"].dropna().median())
    est_birth = median_year - 16
    listening_age = current_year - est_birth
    return median_year, est_birth, listening_age


def compute_top_artists(df: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    return (
        df.groupby("artist_name")["track_id"]
        .nunique()
        .reset_index(name="track_count")
        .sort_values("track_count", ascending=False)
        .head(n)
    )


def compute_top_popular_artists(df: pd.DataFrame, deduped: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    if "popularity_raw" not in df.columns:
        return pd.DataFrame()
    min_t = min(5, max(1, len(deduped) // 10))
    return (
        df.groupby("artist_name")
        .agg(track_count=("track_id", "nunique"), avg_popularity=("popularity_raw", "mean"))
        .query(f"track_count >= {min_t}")
        .sort_values("avg_popularity", ascending=False)
        .head(n)
        .reset_index()
    )


def compute_top_albums(df: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    if "album_name" not in df.columns or "popularity_raw" not in df.columns:
        return pd.DataFrame()
    return (
        df.groupby(["album_name", "artist_name"])
        .agg(track_count=("track_id", "nunique"), avg_popularity=("popularity_raw", "mean"))
        .sort_values(["track_count", "avg_popularity"], ascending=False)
        .head(n)
        .reset_index()
    )


def compute_timeline(df: pd.DataFrame) -> pd.DataFrame:
    if "added_at" not in df.columns or not df["added_at"].notna().any():
        return pd.DataFrame()
    _df = df.copy()
    _df["added_at"] = pd.to_datetime(_df["added_at"], errors="coerce")
    return (
        _df.dropna(subset=["added_at"])
        .assign(year_month=lambda x: x["added_at"].dt.strftime("%Y-%m"))
        .groupby("year_month")
        .size()
        .reset_index(name="tracks_added")
        .sort_values("year_month")
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_df():
    """Full-featured DataFrame — simulates a typical Facu's Collection result."""
    return pd.DataFrame({
        "track_id":      ["t1", "t2", "t3", "t4", "t5", "t1"],  # t1 duplicated across playlists
        "track_name":    ["Song A", "Song B", "Song C", "Song D", "Song E", "Song A"],
        "artist_name":   ["Artist X", "Artist X", "Artist Y", "Artist Y", "Artist Z", "Artist X"],
        "artist_display":["Artist X", "Artist X", "Artist Y", "Artist Y", "Artist Z", "Artist X"],
        "playlist_name": ["PL1", "PL1", "PL2", "PL2", "PL3", "PL2"],
        "album_name":    ["Album 1", "Album 1", "Album 2", "Album 2", "Album 3", "Album 1"],
        "popularity_raw":[80, 70, 60, 50, 40, 80],
        "release_year":  [1990, 2000, 1985, 2010, 2020, 1990],
        "decade":        [1990, 2000, 1980, 2010, 2020, 1990],
        "duration_raw":  [200.0, 210.0, 195.0, 230.0, 180.0, 200.0],  # minutes (DB mode)
        "added_at":      ["2024-01-15", "2024-01-20", "2024-03-05", "2024-03-10", "2024-05-01", "2024-01-15"],
        "artist_genres": ["rock", "rock", "pop", "pop", "jazz", "rock"],
    })


@pytest.fixture
def deduped(sample_df):
    return sample_df.drop_duplicates(subset="track_id").copy()


@pytest.fixture
def minimal_df():
    """Bare-minimum DataFrame — only required columns, no optional ones."""
    return pd.DataFrame({
        "track_id":      ["t1", "t2"],
        "track_name":    ["Song A", "Song B"],
        "artist_name":   ["Artist X", "Artist Y"],
        "artist_display":["Artist X", "Artist Y"],
        "playlist_name": ["PL1", "PL1"],
    })


@pytest.fixture
def empty_df():
    """Empty DataFrame with expected columns."""
    return pd.DataFrame(columns=[
        "track_id", "track_name", "artist_name", "artist_display",
        "playlist_name", "album_name", "popularity_raw", "release_year",
        "decade", "duration_raw", "added_at",
    ])


# ---------------------------------------------------------------------------
# TC-01 – TC-04  fmt_duration
# ---------------------------------------------------------------------------

class TestFmtDuration:
    def test_normal_float(self):
        # 3 min 30 sec
        assert fmt_duration(3.5) == "3:30"

    def test_zero(self):
        assert fmt_duration(0.0) == "0:00"

    def test_whole_minutes(self):
        assert fmt_duration(4.0) == "4:00"

    def test_almost_a_minute(self):
        # 0 min 59 sec — 59/60 ≈ 0.9833
        assert fmt_duration(59 / 60) == "0:59"

    def test_large_value(self):
        # 60 min exactly
        assert fmt_duration(60.0) == "60:00"

    def test_rounding(self):
        # 3 min 29.5 sec rounds to 30
        val = 3 + 29.5 / 60
        result = fmt_duration(val)
        assert result == "3:30"


# ---------------------------------------------------------------------------
# TC-05 – TC-09  KPI derivations
# ---------------------------------------------------------------------------

class TestKpiDerivations:
    def test_total_tracks_deduped(self, sample_df):
        # t1 appears twice across playlists — dedup should give 5 unique tracks
        deduped = sample_df.drop_duplicates(subset="track_id")
        kpis = compute_kpis(deduped)
        assert kpis["total_tracks"] == 5

    def test_total_artists(self, deduped):
        kpis = compute_kpis(deduped)
        # Artist X, Artist Y, Artist Z
        assert kpis["total_artists"] == 3

    def test_total_playlists(self, sample_df, deduped):
        # PL1, PL2, PL3 — playlists counted from deduped too
        kpis = compute_kpis(deduped)
        assert kpis["total_playlists"] == 3

    def test_avg_popularity(self, deduped):
        kpis = compute_kpis(deduped)
        expected = deduped["popularity_raw"].mean()
        assert kpis["avg_popularity"] == pytest.approx(expected)

    def test_decade_mode(self, deduped):
        kpis = compute_kpis(deduped)
        # Decades: 1990, 2000, 1980, 2010, 2020 — all unique, mode = first
        assert kpis["decade_mode"] in [1990, 2000, 1980, 2010, 2020]

    def test_avg_duration_db_mode(self, deduped):
        kpis = compute_kpis(deduped, is_your_collection=False)
        assert kpis["avg_duration"] == pytest.approx(deduped["duration_raw"].mean())

    def test_avg_duration_yc_mode(self, deduped):
        # YC sends milliseconds — should be divided by 60_000
        deduped_ms = deduped.copy()
        deduped_ms["duration_raw"] = deduped_ms["duration_raw"] * 60000
        kpis = compute_kpis(deduped_ms, is_your_collection=True)
        expected = deduped["duration_raw"].mean()
        assert kpis["avg_duration"] == pytest.approx(expected)

    def test_missing_optional_columns(self, minimal_df):
        deduped = minimal_df.drop_duplicates(subset="track_id")
        kpis = compute_kpis(deduped)
        assert kpis["avg_popularity"] is None
        assert kpis["decade_mode"] is None
        assert kpis["avg_duration"] is None


# ---------------------------------------------------------------------------
# TC-10 – TC-13  Oldest / Newest track
# ---------------------------------------------------------------------------

class TestOldestNewest:
    def test_oldest_track_identified(self, deduped):
        oldest, _, _, _, _ = compute_oldest_newest(deduped)
        assert oldest["release_year"] == 1985
        assert oldest["track_name"] == "Song C"

    def test_newest_track_identified(self, deduped):
        _, newest, _, _, _ = compute_oldest_newest(deduped)
        assert newest["release_year"] == 2020
        assert newest["track_name"] == "Song E"

    def test_span_calculation(self, deduped):
        _, _, oldest_year, newest_year, span = compute_oldest_newest(deduped)
        assert oldest_year == 1985
        assert newest_year == 2020
        assert span == 35

    def test_nan_release_years_excluded(self, deduped):
        df_with_nan = deduped.copy()
        df_with_nan.loc[df_with_nan["track_id"] == "t3", "release_year"] = np.nan
        oldest, newest, oldest_year, _, _ = compute_oldest_newest(df_with_nan)
        # t3 (1985) is now NaN — next oldest should be 1990
        assert oldest_year == 1990

    def test_no_release_year_column(self, minimal_df):
        deduped = minimal_df.drop_duplicates(subset="track_id")
        result = compute_oldest_newest(deduped)
        assert all(v is None for v in result)

    def test_all_nan_release_years(self, deduped):
        df_nan = deduped.copy()
        df_nan["release_year"] = np.nan
        result = compute_oldest_newest(df_nan)
        assert all(v is None for v in result)


# ---------------------------------------------------------------------------
# TC-14 – TC-16  Listening age
# ---------------------------------------------------------------------------

class TestListeningAge:
    def test_median_year(self, deduped):
        # release_years: 1985, 1990, 2000, 2010, 2020 → median = 2000
        median_year, _, _ = compute_listening_age(deduped, current_year=2026)
        assert median_year == 2000

    def test_est_birth(self, deduped):
        _, est_birth, _ = compute_listening_age(deduped, current_year=2026)
        assert est_birth == 2000 - 16  # 1984

    def test_listening_age(self, deduped):
        _, _, listening_age = compute_listening_age(deduped, current_year=2026)
        assert listening_age == 2026 - 1984  # 42

    def test_missing_column(self, minimal_df):
        deduped = minimal_df.drop_duplicates(subset="track_id")
        result = compute_listening_age(deduped)
        assert all(v is None for v in result)


# ---------------------------------------------------------------------------
# TC-17 – TC-19  Top artists
# ---------------------------------------------------------------------------

class TestTopArtists:
    def test_counts_unique_tracks_per_artist(self, sample_df):
        top = compute_top_artists(sample_df)
        # Artist X: t1, t2 (2 unique); Artist Y: t3, t4 (2 unique); Artist Z: t5 (1)
        x_row = top[top["artist_name"] == "Artist X"]
        assert int(x_row["track_count"].iloc[0]) == 2

    def test_sorted_descending(self, sample_df):
        top = compute_top_artists(sample_df)
        counts = top["track_count"].tolist()
        assert counts == sorted(counts, reverse=True)

    def test_capped_at_n(self, sample_df):
        top = compute_top_artists(sample_df, n=2)
        assert len(top) == 2

    def test_track_across_playlists_counts_once(self, sample_df):
        # t1 appears in PL1 and PL2 for Artist X — should count as 1 unique track
        top = compute_top_artists(sample_df)
        x_row = top[top["artist_name"] == "Artist X"]
        assert int(x_row["track_count"].iloc[0]) == 2  # t1 + t2, not t1 twice


# ---------------------------------------------------------------------------
# TC-20 – TC-22  Top popular artists
# ---------------------------------------------------------------------------

class TestTopPopularArtists:
    def test_sorted_by_avg_popularity_desc(self, sample_df, deduped):
        top = compute_top_popular_artists(sample_df, deduped)
        pops = top["avg_popularity"].tolist()
        assert pops == sorted(pops, reverse=True)

    def test_min_threshold_applied(self):
        # Build a df where one artist has only 1 track in a large collection
        rows = [{"track_id": f"t{i}", "artist_name": "Big Artist", "popularity_raw": 90}
                for i in range(50)]
        rows.append({"track_id": "t99", "artist_name": "Tiny Artist", "popularity_raw": 99})
        df = pd.DataFrame(rows)
        deduped = df.drop_duplicates(subset="track_id")
        top = compute_top_popular_artists(df, deduped)
        # min_t = min(5, max(1, 51//10)) = 5 — Tiny Artist has 1 track, should be excluded
        assert "Tiny Artist" not in top["artist_name"].values

    def test_no_popularity_column(self, sample_df, deduped):
        df_no_pop = sample_df.drop(columns=["popularity_raw"])
        top = compute_top_popular_artists(df_no_pop, deduped)
        assert top.empty


# ---------------------------------------------------------------------------
# TC-23 – TC-24  Top albums
# ---------------------------------------------------------------------------

class TestTopAlbums:
    def test_ranked_by_track_count(self, sample_df):
        top = compute_top_albums(sample_df)
        counts = top["track_count"].tolist()
        assert counts == sorted(counts, reverse=True)

    def test_tie_broken_by_avg_popularity(self):
        df = pd.DataFrame({
            "track_id":      ["t1", "t2", "t3", "t4"],
            "artist_name":   ["A", "A", "B", "B"],
            "album_name":    ["AlbX", "AlbX", "AlbY", "AlbY"],
            "popularity_raw":[90, 80, 60, 50],  # AlbX avg=85, AlbY avg=55
        })
        top = compute_top_albums(df)
        assert top.iloc[0]["album_name"] == "AlbX"
        assert top.iloc[1]["album_name"] == "AlbY"

    def test_missing_columns_returns_empty(self, minimal_df):
        deduped = minimal_df.drop_duplicates(subset="track_id")
        top = compute_top_albums(minimal_df)
        assert top.empty


# ---------------------------------------------------------------------------
# TC-25 – TC-26  Timeline
# ---------------------------------------------------------------------------

class TestTimeline:
    def test_groups_by_year_month(self, sample_df):
        tl = compute_timeline(sample_df)
        assert "year_month" in tl.columns
        assert "tracks_added" in tl.columns
        # Jan 2024: 2 entries (t1 + t2 + duplicate t1 → 3 rows in sample_df with Jan dates)
        jan = tl[tl["year_month"] == "2024-01"]
        assert not jan.empty
        assert int(jan["tracks_added"].iloc[0]) == 3  # t1 twice + t2

    def test_nat_dates_excluded(self, sample_df):
        df = sample_df.copy()
        df.loc[0, "added_at"] = None  # NaT
        tl = compute_timeline(df)
        total = tl["tracks_added"].sum()
        # One entry removed — 6 rows → 5 non-null
        assert total == 5

    def test_no_added_at_column(self, minimal_df):
        tl = compute_timeline(minimal_df)
        assert tl.empty

    def test_sorted_chronologically(self, sample_df):
        tl = compute_timeline(sample_df)
        months = tl["year_month"].tolist()
        assert months == sorted(months)


# ---------------------------------------------------------------------------
# TC-27 – TC-32  AppTest integration (requires streamlit >= 1.35)
# ---------------------------------------------------------------------------

try:
    from streamlit.testing.v1 import AppTest  # noqa: E402
    APPTEST_AVAILABLE = True
except ImportError:
    APPTEST_AVAILABLE = False

pytestmark_apptest = pytest.mark.skipif(
    not APPTEST_AVAILABLE, reason="streamlit.testing not available"
)


def _make_mock_df():
    return pd.DataFrame({
        "track_id":      ["t1", "t2", "t3"],
        "track_name":    ["Song A", "Song B", "Song C"],
        "artist_name":   ["Artist X", "Artist X", "Artist Y"],
        "artist_display":["Artist X", "Artist X", "Artist Y"],
        "playlist_name": ["PL1", "PL1", "PL2"],
        "album_name":    ["Album 1", "Album 1", "Album 2"],
        "popularity_raw":[80, 70, 60],
        "release_year":  [1990, 2000, 2010],
        "decade":        [1990, 2000, 2010],
        "duration_raw":  [3.5, 4.0, 3.0],
        "added_at":      ["2024-01-15", "2024-01-20", "2024-03-05"],
        "artist_genres": ["rock", "rock", "pop"],
    })


@pytest.mark.skipif(not APPTEST_AVAILABLE, reason="streamlit.testing not available")
class TestOverviewPageRender:
    """Integration tests — run the Streamlit page in a simulated environment."""

    def _run_page(self, mock_df=None, session_state=None):
        if mock_df is None:
            mock_df = _make_mock_df()

        at = AppTest.from_file("pages/1_Overview.py", default_timeout=30)

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

    def test_TC29_page_renders_without_exception(self):
        at = self._run_page()
        assert not at.exception

    def test_TC30_yc_banner_appears_in_yc_mode(self):
        at = self._run_page(
            session_state={
                "mode": "🔗 Your Collection",
                "uc_active": True,
            }
        )
        assert not at.exception
        # Banner text should mention "Your Collection"
        info_texts = [i.value for i in at.info]
        assert any("Your Collection" in t for t in info_texts)

    def test_TC31_page_renders_with_minimal_columns(self):
        # album_name is required — the page calls st.rerun() if it is missing.
        # Optional analytics columns (popularity_raw, release_year, decade,
        # duration_raw, added_at, artist_genres) are intentionally absent here
        # to verify the page degrades gracefully when they are not present.
        minimal = pd.DataFrame({
            "track_id":      ["t1"],
            "track_name":    ["Song A"],
            "artist_name":   ["Artist X"],
            "artist_display":["Artist X"],
            "playlist_name": ["PL1"],
            "album_name":    ["Album 1"],
        })
        at = self._run_page(mock_df=minimal)
        assert not at.exception

    def test_TC32_page_renders_with_empty_dataframe(self):
        empty = pd.DataFrame(columns=[
            "track_id", "track_name", "artist_name", "artist_display",
            "playlist_name", "album_name", "popularity_raw", "release_year",
            "decade", "duration_raw", "added_at",
        ])
        at = self._run_page(mock_df=empty)
        assert not at.exception
