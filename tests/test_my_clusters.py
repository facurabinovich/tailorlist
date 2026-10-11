"""
Test suite for pages/6_My_Clusters.py
Run with:  pytest tests/test_my_clusters.py -v
"""

import warnings
import numpy as np
import pandas as pd
import pytest
from unittest.mock import patch, MagicMock

# KMeans memory-leak warning is a Windows/MKL env issue — not a code defect
pytestmark = pytest.mark.filterwarnings("ignore::UserWarning:sklearn")

CLUSTER_FEATURES = ["energy", "acousticness", "valence", "tempo", "danceability", "speechiness_log"]

from core.clustering import (
    verbose_description as _verbose_description,
    best_k as _best_k,
)
from core.genres import (
    GENRE_FAMILIES,
    assign_family as _assign_family,
    track_matches_families as _track_matches_families,
    preview_filter as _preview_filter,
)


# ---------------------------------------------------------------------------
# Helpers — mirror pure logic from 6_My_Clusters.py
# ---------------------------------------------------------------------------

def cluster_pct(count: int, total: int) -> float:
    return count / total * 100 if total else 0.0


def _describe_centroid(c: dict) -> str:
    """Mirrors the internal _describe() inside _make_names()."""
    parts = []
    energy          = c.get("energy", 0)
    valence         = c.get("valence", 0)
    acousticness    = c.get("acousticness", 0)
    danceability    = c.get("danceability", 0)
    tempo           = c.get("tempo", 0)
    speechiness_log = c.get("speechiness_log", 0)

    if energy > 0.65:
        parts.append("High Energy")
    elif energy < 0.45:
        parts.append("Low Energy")
    else:
        parts.append("Mid Energy")
    if acousticness > 0.5:
        parts.append("Acoustic")
    if valence > 0.6:
        parts.append("Happy")
    elif valence < 0.4:
        parts.append("Dark")
    if danceability > 0.65:
        parts.append("Danceable")
    if speechiness_log > 0.25:
        parts.append("Rap")
    if tempo > 130:
        parts.append("Fast")
    elif tempo < 90:
        parts.append("Slow")
    return " · ".join(parts) if parts else "Mixed"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def genre_df():
    """8 tracks across 2 playlists with varied decade and genre data."""
    return pd.DataFrame({
        "track_id":      [f"t{i}" for i in range(8)],
        "playlist_name": ["PL1"] * 4 + ["PL2"] * 4,
        "decade":        pd.array([1990, 1990, 2000, 2000, 1990, 2000, 2000, 2000], dtype="Int64"),
        "artist_genres": [
            "rock alternative",   # t0 PL1
            "hip hop trap",       # t1 PL1
            "pop dance pop",      # t2 PL1
            "xylophone ambient",  # t3 PL1  ← unrecognized
            "rock punk",          # t4 PL2
            "latin pop",          # t5 PL2
            "",                   # t6 PL2  ← empty
            "jazz bebop",         # t7 PL2
        ],
    })


# ---------------------------------------------------------------------------
# TC-01 – TC-08  _assign_family
# ---------------------------------------------------------------------------

def _uc_tracks(ids):
    """Real uc_enriched / uc_skipped entries are track dicts (see pages/_Enrich.py)."""
    return [{"id": i, "name": f"Track {i}", "artists": "Artist",
             "playlist_name": "Playlist"} for i in ids]


class TestAssignFamily:

    def test_TC01_none_returns_other(self):
        assert _assign_family(None) == ["Other"]

    def test_TC02_empty_string_returns_other(self):
        assert _assign_family("") == ["Other"]

    def test_TC03_whitespace_returns_other(self):
        assert _assign_family("   ") == ["Other"]

    def test_TC04_nan_returns_other(self):
        assert _assign_family(float("nan")) == ["Other"]

    def test_TC05_rock_matched(self):
        assert "Rock" in _assign_family("alternative rock")

    def test_TC06_hip_hop_matched(self):
        assert "Hip-Hop" in _assign_family("hip hop trap")

    def test_TC07_latin_pop_matches_two_families(self):
        result = _assign_family("latin pop")
        assert "Latin" in result
        assert "Pop" in result

    def test_TC08_unrecognized_genre_returns_other(self):
        assert _assign_family("xylophone abstract fusion") == ["Other"]


# ---------------------------------------------------------------------------
# TC-09 – TC-15  _track_matches_families
# ---------------------------------------------------------------------------

class TestTrackMatchesFamilies:

    def test_TC09_none_with_other_selected(self):
        assert _track_matches_families(None, ["Other"]) is True

    def test_TC10_none_without_other(self):
        # Genre-less tracks always pass the family filter (deliberate 2026-05-20 change); the old mirror had diverged.
        assert _track_matches_families(None, ["Rock"]) is True

    def test_TC11_empty_string_with_other(self):
        assert _track_matches_families("", ["Other"]) is True

    def test_TC12_rock_matches_rock_family(self):
        assert _track_matches_families("alternative rock", ["Rock"]) is True

    def test_TC13_rock_does_not_match_pop(self):
        assert _track_matches_families("alternative rock", ["Pop"]) is False

    def test_TC14_unrecognized_genre_with_other(self):
        assert _track_matches_families("xylophone fusion", ["Other"]) is True

    def test_TC15_unrecognized_genre_without_other(self):
        assert _track_matches_families("xylophone fusion", ["Rock", "Pop"]) is False


# ---------------------------------------------------------------------------
# TC-16 – TC-21  _preview_filter
# ---------------------------------------------------------------------------

class TestPreviewFilter:

    def test_TC16_single_playlist(self, genre_df):
        count = _preview_filter(genre_df, ["PL1"], [], [], [])
        assert count == 4

    def test_TC17_two_playlists(self, genre_df):
        count = _preview_filter(genre_df, ["PL1", "PL2"], [], [], [])
        assert count == 8

    def test_TC18_decade_filter(self, genre_df):
        # 1990: t0, t1 (PL1) + t4 (PL2) = 3
        count = _preview_filter(genre_df, ["PL1", "PL2"], ["1990"], [], [])
        assert count == 3

    def test_TC19_raw_genre_filter(self, genre_df):
        # "rock" appears in t0 and t4 only
        count = _preview_filter(genre_df, ["PL1", "PL2"], [], [], ["rock"])
        assert count == 2

    def test_TC20_family_filter_rock_only(self, genre_df):
        all_fams = ["Rock", "Pop", "Hip-Hop", "Electronic", "Jazz", "Classical", "Folk", "Latin", "Other"]
        # Rock matches t0 "rock alternative" and t4 "rock punk"
        count = _preview_filter(genre_df, ["PL1", "PL2"], [], ["Rock"], [], all_fams)
        # Genre-less tracks always pass the family filter (deliberate 2026-05-20 change); the old mirror had diverged.
        assert count == 3

    def test_TC21_zero_result_when_no_match(self, genre_df):
        # "Classical" only — nothing in the genre_df has classical keywords
        all_fams = ["Rock", "Pop", "Hip-Hop", "Electronic", "Jazz", "Classical", "Folk", "Latin", "Other"]
        count = _preview_filter(genre_df, ["PL1"], [], ["Classical"], [], all_fams)
        assert count == 0


# ---------------------------------------------------------------------------
# TC-22 – TC-23  cluster_pct
# ---------------------------------------------------------------------------

class TestClusterPct:

    def test_TC22_normal_calculation(self):
        assert cluster_pct(30, 100) == pytest.approx(30.0)

    def test_TC23_zero_total_returns_zero(self):
        assert cluster_pct(5, 0) == 0.0


# ---------------------------------------------------------------------------
# TC-24 – TC-32  _verbose_description
# ---------------------------------------------------------------------------

class TestVerboseDescription:

    def test_TC24_high_energy(self):
        assert "high energy" in _verbose_description(0.8, 0.5, 0.5)

    def test_TC25_low_energy(self):
        assert "low energy" in _verbose_description(0.3, 0.5, 0.5)

    def test_TC26_mid_energy(self):
        assert "mid energy" in _verbose_description(0.55, 0.5, 0.5)

    def test_TC27_happy_valence(self):
        assert "happy" in _verbose_description(0.5, 0.8, 0.5)

    def test_TC28_dark_valence(self):
        assert "dark" in _verbose_description(0.5, 0.2, 0.5)

    def test_TC29_acoustic(self):
        assert "acoustic" in _verbose_description(0.5, 0.5, 0.5, acousticness=0.7)

    def test_TC30_very_danceable(self):
        assert "very danceable" in _verbose_description(0.5, 0.5, 0.8)

    def test_TC31_fast_tempo(self):
        assert "fast tempo" in _verbose_description(0.5, 0.5, 0.5, tempo=140)

    def test_TC32_slow_tempo(self):
        assert "slow tempo" in _verbose_description(0.5, 0.5, 0.5, tempo=80)


# ---------------------------------------------------------------------------
# TC-33 – TC-38  _describe_centroid
# ---------------------------------------------------------------------------

class TestDescribeCentroid:

    def test_TC33_high_energy_label(self):
        result = _describe_centroid({"energy": 0.8, "valence": 0.5, "acousticness": 0.1})
        assert "High Energy" in result

    def test_TC34_low_energy_label(self):
        result = _describe_centroid({"energy": 0.3, "valence": 0.5, "acousticness": 0.1})
        assert "Low Energy" in result

    def test_TC35_acoustic_label(self):
        result = _describe_centroid({"energy": 0.5, "acousticness": 0.7})
        assert "Acoustic" in result

    def test_TC36_dark_label(self):
        result = _describe_centroid({"energy": 0.5, "valence": 0.2})
        assert "Dark" in result

    def test_TC37_rap_when_speechiness_high(self):
        result = _describe_centroid({"energy": 0.5, "speechiness_log": 0.3})
        assert "Rap" in result

    def test_TC38_all_zeros_gives_low_energy_dark_slow(self):
        # energy=0 → Low Energy, valence=0 → Dark, tempo=0 → Slow
        result = _describe_centroid({f: 0 for f in CLUSTER_FEATURES})
        assert result == "Low Energy · Dark · Slow"


# ---------------------------------------------------------------------------
# TC-39 – TC-42  _best_k
# ---------------------------------------------------------------------------

class TestBestK:

    def _make_metrics(self, sils, inertias=None):
        k_values = list(range(2, 2 + len(sils)))
        if inertias is None:
            inertias = [1000 / k for k in k_values]
        return pd.DataFrame({"k": k_values, "silhouette": sils, "inertia": inertias})

    def test_TC39_best_silhouette_is_idxmax(self):
        df = self._make_metrics([0.3, 0.6, 0.4, 0.2])  # k=3 has max
        best_sil, _ = _best_k(df)
        assert best_sil == 3

    def test_TC40_fallback_to_silhouette_when_few_points(self):
        df = self._make_metrics([0.2, 0.5, 0.3])  # only 3 points < 4
        best_sil, best_elbow = _best_k(df)
        assert best_elbow == best_sil

    def test_TC41_elbow_computed_with_4_points(self):
        # 4 inertia points → second derivative computed
        inertias = [800, 400, 350, 340]  # big drop from k=2→3, then flattens
        df = self._make_metrics([0.3, 0.4, 0.5, 0.2], inertias)
        best_sil, best_elbow = _best_k(df)
        assert isinstance(best_elbow, int)
        assert 2 <= best_elbow <= 5

    def test_TC42_returns_tuple_of_two_ints(self):
        df = self._make_metrics([0.3, 0.5, 0.4, 0.2, 0.1])
        result = _best_k(df)
        assert len(result) == 2
        assert all(isinstance(v, int) for v in result)


try:
    import sklearn  # noqa: F401
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False


# ---------------------------------------------------------------------------
# TC-43 – TC-47  KMeans sklearn integration (no Streamlit)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not SKLEARN_AVAILABLE, reason="scikit-learn not installed")
class TestKmeansLogic:

    def _make_feature_df(self, n=20, k=2):
        from sklearn.cluster import KMeans
        from sklearn.preprocessing import StandardScaler
        from sklearn.decomposition import PCA

        rng = np.random.default_rng(99)
        df = pd.DataFrame({
            "track_id":       [f"t{i}" for i in range(n)],
            "track_name":     [f"Track {i}" for i in range(n)],
            "artist_display": [f"Artist {i % 3}" for i in range(n)],
            "playlist_name":  ["PL1" if i < n // 2 else "PL2" for i in range(n)],
            "energy":         rng.uniform(0.2, 0.9, n),
            "acousticness":   rng.uniform(0.0, 0.8, n),
            "valence":        rng.uniform(0.1, 0.9, n),
            "tempo":          rng.uniform(85.0, 155.0, n),
            "danceability":   rng.uniform(0.3, 0.9, n),
            "speechiness_log": rng.uniform(0.03, 0.25, n),
        })
        X = df[CLUSTER_FEATURES].values
        scaler = StandardScaler()
        X_sc = scaler.fit_transform(X)
        km = KMeans(n_clusters=k, random_state=42, n_init=10)
        df["cluster"] = km.fit_predict(X_sc)
        pca = PCA(n_components=2, random_state=42)
        coords = pca.fit_transform(X_sc)
        df["PC1"] = coords[:, 0]
        df["PC2"] = coords[:, 1]
        return df, km, scaler, pca

    def test_TC43_cluster_column_has_k_unique_values(self):
        df, km, _, _ = self._make_feature_df(k=3)
        assert df["cluster"].nunique() == 3

    def test_TC44_all_tracks_assigned(self):
        df, _, _, _ = self._make_feature_df(k=2)
        assert df["cluster"].isna().sum() == 0

    def test_TC45_pc1_pc2_present(self):
        df, _, _, _ = self._make_feature_df()
        assert "PC1" in df.columns and "PC2" in df.columns

    def test_TC46_speechiness_log_derivation(self):
        base_df = pd.DataFrame({"speechiness": [0.05, 0.10, 0.20]})
        base_df["speechiness_log"] = np.log1p(base_df["speechiness"])
        expected = np.log1p(np.array([0.05, 0.10, 0.20]))
        np.testing.assert_allclose(base_df["speechiness_log"].values, expected)

    def test_TC47_centroids_have_k_rows(self):
        _, km, _, _ = self._make_feature_df(k=4)
        assert km.cluster_centers_.shape == (4, len(CLUSTER_FEATURES))


# ---------------------------------------------------------------------------
# TC-48 – TC-55  AppTest integration
# ---------------------------------------------------------------------------

try:
    from streamlit.testing.v1 import AppTest
    APPTEST_AVAILABLE = True
except ImportError:
    APPTEST_AVAILABLE = False


def _make_full_df():
    """Mock df returned by load_cluster_data for FC mode."""
    rng = np.random.default_rng(5)
    rows = []
    for pl in ["PL1", "PL2"]:
        for i in range(8):
            rows.append({
                "track_id":       f"{pl}-t{i}",
                "track_name":     f"Track {i}",
                "artist_name":    f"Artist {i % 2}",
                "artist_display": f"Artist {i % 2}",
                "playlist_name":  pl,
                "energy":         float(rng.uniform(0.2, 0.9)),
                "acousticness":   float(rng.uniform(0.0, 0.8)),
                "valence":        float(rng.uniform(0.1, 0.9)),
                "tempo":          float(rng.uniform(85.0, 155.0)),
                "danceability":   float(rng.uniform(0.3, 0.9)),
                "speechiness":    float(rng.uniform(0.03, 0.2)),
                "speechiness_log": float(np.log1p(rng.uniform(0.03, 0.2))),
                "decade":         pd.NA,
                "artist_genres":  "rock" if i % 2 == 0 else "pop",
            })
    return pd.DataFrame(rows)


def _make_clustering_results(df_all: pd.DataFrame) -> dict:
    """Build a fake clustering_results session state dict from df_all."""
    from sklearn.preprocessing import StandardScaler

    df = df_all.copy()
    n = len(df)
    df["cluster"] = [i % 2 for i in range(n)]
    df["cluster_name"] = df["cluster"].map({0: "High Energy · Dark", 1: "Low Energy · Happy"})
    rng = np.random.default_rng(7)
    df["PC1"] = rng.uniform(-2, 2, n)
    df["PC2"] = rng.uniform(-2, 2, n)

    scaler = StandardScaler()
    scaler.fit(df[CLUSTER_FEATURES].values)

    centroids_scaled = pd.DataFrame(
        np.vstack([
            df[df["cluster"] == c][CLUSTER_FEATURES].mean().values
            for c in [0, 1]
        ]),
        columns=CLUSTER_FEATURES,
    )

    return {
        "df_clust":          df,
        "name_map":          {0: "High Energy · Dark", 1: "Low Energy · Happy"},
        "centroids_scaled":  centroids_scaled,
        "var1":              25.0,
        "var2":              18.0,
        "scaler_used":       scaler,
        "pc1_label":         "energy",
        "pc2_label":         "valence",
        "metrics_df":        None,
        "best_k_sil":        None,
        "best_k_elbow":      None,
        "optimal_k":         2,
        "fc_override":       False,
        "n_tracks":          n,
        "selected_playlists": ["PL1", "PL2"],
        "k":                 2,
        "k_mode":            "Manual",
        "selected_decades":  [],
        "selected_families": [],
        "decade_options":    [],
        "track_ids":         tuple(df["track_id"].tolist()),
    }


def _empty_unmatched_df():
    return pd.DataFrame(columns=[
        "track_id", "track_name", "artist_name", "artist_display",
        "release_year", "artist_genres", "playlist_name",
    ])


@pytest.mark.skipif(not APPTEST_AVAILABLE, reason="streamlit.testing not available")
class TestMyClustersPageRender:

    @pytest.fixture(autouse=True)
    def _db_loaders_unavailable(self):
        """The page also reads load_all_tracks (collection size) and
        load_all_tracks_for_grouping (grouping preview); nothing patched them, so
        they hit the DB and the failure was swallowed by the page's own fallback.
        That only looked fine because an earlier test file leaked a stubbed
        get_engine into db.queries. Make the failure explicit where the page looks
        the loaders up, so these tests exercise the same fallback on any order."""
        down = RuntimeError("DB unavailable in tests")
        with patch("db.queries.load_all_tracks", side_effect=down), \
             patch("db.queries.load_all_tracks_for_grouping", side_effect=down):
            yield

    def _base_patches(self, mock_df=None):
        if mock_df is None:
            mock_df = _make_full_df()
        return (
            patch("db.queries.load_cluster_data", return_value=mock_df),
            patch("db.queries.load_cluster_progress", return_value={}),
            patch("db.queries.save_cluster_progress"),
            patch("db.queries.load_unmatched_tracks", return_value=_empty_unmatched_df()),
            patch("db.queries._add_artist_display", side_effect=lambda df: df),
            patch("ui.theme.inject_global_css"),
            patch("ui.nav.inject_sidebar_nav"),
            patch("ui.nav.check_collection_mode", return_value=True),
            patch("ui.theme.spotify_icon_html", return_value=""),
            patch("ui.theme.page_brand_html", return_value=""),
            patch("ui.export.render_export_to_spotify"),
        )

    def test_TC48_pre_clustering_renders_without_exception(self):
        mock_df = _make_full_df()
        at = AppTest.from_file("pages/6_My_Clusters.py", default_timeout=30)
        with (
            patch("db.queries.load_cluster_data", return_value=mock_df),
            patch("db.queries.load_cluster_progress", return_value={}),
            patch("db.queries.save_cluster_progress"),
            patch("db.queries.load_unmatched_tracks", return_value=_empty_unmatched_df()),
            patch("db.queries._add_artist_display", side_effect=lambda df: df),
            patch("ui.theme.inject_global_css"),
            patch("ui.nav.inject_sidebar_nav"),
            patch("ui.nav.check_collection_mode", return_value=True),
            patch("ui.theme.spotify_icon_html", return_value=""),
            patch("ui.theme.page_brand_html", return_value=""),
            patch("ui.export.render_export_to_spotify"),
        ):
            at.run()
        assert not at.exception

    def test_TC49_yc_mode_all_enriched_shows_info(self):
        mock_df = _make_full_df()
        all_ids = mock_df["track_id"].unique().tolist()
        at = AppTest.from_file("pages/6_My_Clusters.py", default_timeout=30)
        at.session_state["mode"] = "🔗 Your Collection"
        at.session_state["uc_enriched"] = _uc_tracks(all_ids)
        at.session_state["uc_skipped"] = []
        at.session_state["uc_failed"] = []
        with (
            patch("db.queries.load_cluster_data", return_value=mock_df),
            patch("app_state.collection.get_tracks", return_value=mock_df),
            patch("db.queries.load_cluster_progress", return_value={}),
            patch("db.queries.save_cluster_progress"),
            patch("db.queries.load_unmatched_tracks", return_value=_empty_unmatched_df()),
            patch("db.queries._add_artist_display", side_effect=lambda df: df),
            patch("ui.theme.inject_global_css"),
            patch("ui.nav.inject_sidebar_nav"),
            patch("ui.nav.check_collection_mode", return_value=True),
            patch("ui.theme.spotify_icon_html", return_value=""),
            patch("ui.theme.page_brand_html", return_value=""),
            patch("ui.export.render_export_to_spotify"),
        ):
            at.run()
        assert not at.exception
        info_texts = [i.value for i in at.info]
        assert any("Your Collection" in t for t in info_texts)

    def test_TC50_yc_mode_partial_enrichment_shows_warning(self):
        mock_df = _make_full_df()
        all_ids = mock_df["track_id"].unique().tolist()
        at = AppTest.from_file("pages/6_My_Clusters.py", default_timeout=30)
        at.session_state["mode"] = "🔗 Your Collection"
        at.session_state["uc_enriched"] = _uc_tracks(all_ids[:6])
        at.session_state["uc_skipped"] = _uc_tracks(all_ids[6:])
        at.session_state["uc_failed"] = []
        with (
            patch("db.queries.load_cluster_data", return_value=mock_df),
            patch("app_state.collection.get_tracks", return_value=mock_df),
            patch("db.queries.load_cluster_progress", return_value={}),
            patch("db.queries.save_cluster_progress"),
            patch("db.queries.load_unmatched_tracks", return_value=_empty_unmatched_df()),
            patch("db.queries._add_artist_display", side_effect=lambda df: df),
            patch("ui.theme.inject_global_css"),
            patch("ui.nav.inject_sidebar_nav"),
            patch("ui.nav.check_collection_mode", return_value=True),
            patch("ui.theme.spotify_icon_html", return_value=""),
            patch("ui.theme.page_brand_html", return_value=""),
            patch("ui.export.render_export_to_spotify"),
        ):
            at.run()
        assert not at.exception
        warn_texts = [w.value for w in at.warning]
        assert any("could not be enriched" in t for t in warn_texts)

    def test_TC51_full_render_with_preloaded_results(self):
        mock_df = _make_full_df()
        cr = _make_clustering_results(mock_df)
        at = AppTest.from_file("pages/6_My_Clusters.py", default_timeout=60)
        at.session_state["clustering_results"] = cr
        with (
            patch("db.queries.load_cluster_data", return_value=mock_df),
            patch("db.queries.load_cluster_progress", return_value={}),
            patch("db.queries.save_cluster_progress"),
            patch("db.queries.load_unmatched_tracks", return_value=_empty_unmatched_df()),
            patch("db.queries._add_artist_display", side_effect=lambda df: df),
            patch("ui.theme.inject_global_css"),
            patch("ui.nav.inject_sidebar_nav"),
            patch("ui.nav.check_collection_mode", return_value=True),
            patch("ui.theme.spotify_icon_html", return_value=""),
            patch("ui.theme.page_brand_html", return_value=""),
            patch("ui.export.render_export_to_spotify"),
        ):
            at.run()
        assert not at.exception

    def test_TC52_single_playlist_preloaded_results(self):
        mock_df = _make_full_df()
        mock_df["playlist_name"] = "Solo"
        cr = _make_clustering_results(mock_df)
        cr["selected_playlists"] = ["Solo"]
        at = AppTest.from_file("pages/6_My_Clusters.py", default_timeout=60)
        at.session_state["clustering_results"] = cr
        with (
            patch("db.queries.load_cluster_data", return_value=mock_df),
            patch("db.queries.load_cluster_progress", return_value={}),
            patch("db.queries.save_cluster_progress"),
            patch("db.queries.load_unmatched_tracks", return_value=_empty_unmatched_df()),
            patch("db.queries._add_artist_display", side_effect=lambda df: df),
            patch("ui.theme.inject_global_css"),
            patch("ui.nav.inject_sidebar_nav"),
            patch("ui.nav.check_collection_mode", return_value=True),
            patch("ui.theme.spotify_icon_html", return_value=""),
            patch("ui.theme.page_brand_html", return_value=""),
            patch("ui.export.render_export_to_spotify"),
        ):
            at.run()
        assert not at.exception

    def test_TC53_large_k_shows_numbered_clusters(self):
        from sklearn.preprocessing import StandardScaler

        mock_df = _make_full_df()
        # k=6 triggers "Playlist N" naming in the page
        n = len(mock_df)
        mock_df["cluster"] = [i % 6 for i in range(n)]
        mock_df["cluster_name"] = mock_df["cluster"].map(
            {i: f"Playlist {i+1}" for i in range(6)}
        )
        mock_df["PC1"] = np.random.default_rng(3).uniform(-2, 2, n)
        mock_df["PC2"] = np.random.default_rng(4).uniform(-2, 2, n)

        scaler = StandardScaler()
        scaler.fit(mock_df[CLUSTER_FEATURES].values)
        centroids_scaled = pd.DataFrame(
            np.vstack([
                mock_df[mock_df["cluster"] == c][CLUSTER_FEATURES].mean().values
                if not mock_df[mock_df["cluster"] == c].empty
                else np.zeros(len(CLUSTER_FEATURES))
                for c in range(6)
            ]),
            columns=CLUSTER_FEATURES,
        )

        cr = {
            "df_clust":          mock_df,
            "name_map":          {i: f"Playlist {i+1}" for i in range(6)},
            "centroids_scaled":  centroids_scaled,
            "var1":              20.0,
            "var2":              15.0,
            "scaler_used":       scaler,
            "pc1_label":         "energy",
            "pc2_label":         "tempo",
            "metrics_df":        None,
            "best_k_sil":        None,
            "best_k_elbow":      None,
            "optimal_k":         6,
            "fc_override":       False,
            "n_tracks":          n,
            "selected_playlists": ["PL1", "PL2"],
            "k":                 6,
            "k_mode":            "Manual",
            "selected_decades":  [],
            "selected_families": [],
            "decade_options":    [],
            "track_ids":         tuple(mock_df["track_id"].tolist()),
        }
        at = AppTest.from_file("pages/6_My_Clusters.py", default_timeout=60)
        at.session_state["clustering_results"] = cr
        with (
            patch("db.queries.load_cluster_data", return_value=mock_df),
            patch("db.queries.load_cluster_progress", return_value={}),
            patch("db.queries.save_cluster_progress"),
            patch("db.queries.load_unmatched_tracks", return_value=_empty_unmatched_df()),
            patch("db.queries._add_artist_display", side_effect=lambda df: df),
            patch("ui.theme.inject_global_css"),
            patch("ui.nav.inject_sidebar_nav"),
            patch("ui.nav.check_collection_mode", return_value=True),
            patch("ui.theme.spotify_icon_html", return_value=""),
            patch("ui.theme.page_brand_html", return_value=""),
            patch("ui.export.render_export_to_spotify"),
        ):
            at.run()
        assert not at.exception

    def test_TC54_preloaded_results_with_fc_override(self):
        mock_df = _make_full_df()
        cr = _make_clustering_results(mock_df)
        cr["fc_override"] = True
        cr["best_k_sil"] = 2
        cr["best_k_elbow"] = 3
        cr["k_mode"] = "Auto"
        at = AppTest.from_file("pages/6_My_Clusters.py", default_timeout=60)
        at.session_state["clustering_results"] = cr
        with (
            patch("db.queries.load_cluster_data", return_value=mock_df),
            patch("db.queries.load_cluster_progress", return_value={}),
            patch("db.queries.save_cluster_progress"),
            patch("db.queries.load_unmatched_tracks", return_value=_empty_unmatched_df()),
            patch("db.queries._add_artist_display", side_effect=lambda df: df),
            patch("ui.theme.inject_global_css"),
            patch("ui.nav.inject_sidebar_nav"),
            patch("ui.nav.check_collection_mode", return_value=True),
            patch("ui.theme.spotify_icon_html", return_value=""),
            patch("ui.theme.page_brand_html", return_value=""),
            patch("ui.export.render_export_to_spotify"),
        ):
            at.run()
        assert not at.exception

    def test_TC55_auto_mode_metrics_df_in_results(self):
        mock_df = _make_full_df()
        cr = _make_clustering_results(mock_df)
        cr["k_mode"] = "Auto"
        cr["fc_override"] = False
        cr["best_k_sil"] = 2
        cr["best_k_elbow"] = 2
        metrics_df = pd.DataFrame({
            "k": [2, 3, 4, 5],
            "silhouette": [0.35, 0.42, 0.38, 0.30],
            "inertia": [200.0, 150.0, 130.0, 120.0],
        })
        cr["metrics_df"] = metrics_df
        at = AppTest.from_file("pages/6_My_Clusters.py", default_timeout=60)
        at.session_state["clustering_results"] = cr
        with (
            patch("db.queries.load_cluster_data", return_value=mock_df),
            patch("db.queries.load_cluster_progress", return_value={}),
            patch("db.queries.save_cluster_progress"),
            patch("db.queries.load_unmatched_tracks", return_value=_empty_unmatched_df()),
            patch("db.queries._add_artist_display", side_effect=lambda df: df),
            patch("ui.theme.inject_global_css"),
            patch("ui.nav.inject_sidebar_nav"),
            patch("ui.nav.check_collection_mode", return_value=True),
            patch("ui.theme.spotify_icon_html", return_value=""),
            patch("ui.theme.page_brand_html", return_value=""),
            patch("ui.export.render_export_to_spotify"),
        ):
            at.run()
        assert not at.exception
