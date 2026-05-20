"""
Test suite for pages/5_Audio_DNA.py
Run with:  pytest tests/test_audio_dna.py -v
"""

import numpy as np
import pandas as pd
import pytest
from unittest.mock import patch

RADAR_FEATS = ["energy", "acousticness", "valence", "danceability",
               "speechiness", "instrumentalness", "liveness"]

AUDIO_FEATURES = [
    "energy", "acousticness", "valence", "danceability",
    "speechiness", "instrumentalness", "liveness", "loudness", "tempo",
]

NORMALIZED_FEATURES = [
    "energy", "acousticness", "valence", "danceability",
    "speechiness", "instrumentalness", "liveness",
]

_PL_PALETTE = [
    "#1DB954", "#E8534A", "#4A90D9", "#F5A623", "#B97FE8",
    "#E8D44A", "#4AE8D4", "#E84A90", "#A8E84A", "#E8934A",
    "#7B9EA8", "#C0392B", "#8E44AD", "#2ECC71",
]

FEAT_LABELS = {
    "energy": "Energy", "acousticness": "Acousticness", "valence": "Valence",
    "danceability": "Danceability", "speechiness": "Speechiness",
    "instrumentalness": "Instrumentalness", "liveness": "Liveness",
    "loudness": "Loudness", "tempo": "Tempo",
}


# ---------------------------------------------------------------------------
# Helpers — mirrors pure logic from 5_Audio_DNA.py
# ---------------------------------------------------------------------------

def _short_name(name: str, max_len: int = 22) -> str:
    return name if len(name) <= max_len else name[:max_len - 1] + "…"


def _hex_to_rgb(hex_color: str):
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _playlist_color_map(playlists):
    return {pl: _PL_PALETTE[i % len(_PL_PALETTE)] for i, pl in enumerate(sorted(playlists))}


def compute_quadrants(df: pd.DataFrame) -> dict:
    return {
        "Happy":     df[(df["valence"] >= 0.5) & (df["energy"] >= 0.5)],
        "Turbulent": df[(df["valence"] <  0.5) & (df["energy"] >= 0.5)],
        "Peaceful":  df[(df["valence"] >= 0.5) & (df["energy"] <  0.5)],
        "Dark":      df[(df["valence"] <  0.5) & (df["energy"] <  0.5)],
    }


def quadrant_pct(subset: pd.DataFrame, total: pd.DataFrame) -> float:
    return len(subset) / len(total) * 100 if len(total) else 0.0


def compute_global_means(df: pd.DataFrame, feats: list) -> list:
    return [df[f].mean() for f in feats]


def compute_playlist_means(df: pd.DataFrame, pl: str, feats: list) -> list:
    sub = df[df["playlist_name"] == pl].drop_duplicates(subset="track_id")
    return [sub[f].mean() for f in feats]


def should_use_log_scale(vals: pd.Series, feat: str) -> bool:
    return feat in ("instrumentalness", "speechiness") and (vals > 0).sum() > 10


def compute_feature_histogram(vals: pd.Series, feat: str, n_bins: int = 30):
    if should_use_log_scale(vals, feat):
        pos = vals[vals > 0]
        log_vals = np.log10(pos + 1e-4)
        bins = np.linspace(log_vals.min(), log_vals.max(), n_bins)
        hist_vals, bin_edges = np.histogram(log_vals, bins=bins)
    else:
        hist_vals, bin_edges = np.histogram(vals, bins=n_bins)
    return hist_vals, bin_edges


def compute_correlation_matrix(df: pd.DataFrame, feats: list) -> pd.DataFrame:
    return df[feats].dropna().corr(method="pearson").round(2)


def compute_top_correlations(corr_matrix: pd.DataFrame, n: int = 3) -> pd.DataFrame:
    mask = np.triu(np.ones(corr_matrix.shape), k=1).astype(bool)
    flat = corr_matrix.where(mask).stack().reset_index()
    flat.columns = ["feat_a", "feat_b", "r"]
    return flat.assign(abs_r=flat["r"].abs()).sort_values("abs_r", ascending=False).head(n)


def format_extreme_value(val: float, feat: str) -> str:
    if feat == "tempo":
        result = f"{val:.1f}"
    elif feat == "loudness":
        result = f"{val:.1f}"
    elif feat in ("instrumentalness", "speechiness"):
        result = f"{val:.4f}"
    else:
        result = f"{val:.3f}"
    if result in ("0.000", "0.0000", "0.0001"):
        return "< 0.001"
    return result


def compute_extreme_tracks(df: pd.DataFrame, feat: str, n: int = 5):
    top = df.nlargest(n, feat)[["track_name", "artist_display", "playlist_name", feat]]
    if feat in ("instrumentalness", "speechiness"):
        non_zero = df[df[feat] > 0]
        bot = (non_zero.nsmallest(n, feat) if len(non_zero) >= n
               else df.nsmallest(n, feat))[["track_name", "artist_display", "playlist_name", feat]]
    else:
        bot = df.nsmallest(n, feat)[["track_name", "artist_display", "playlist_name", feat]]
    return top, bot


def compute_marker_size(sub: pd.DataFrame) -> list:
    if "popularity_raw" in sub.columns:
        return (sub["popularity_raw"].astype(float).fillna(0.0) / 100 * 8 + 3).tolist()
    return [6] * len(sub)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_df():
    """Two playlists, 10 tracks each, all audio features present."""
    rng = np.random.default_rng(42)
    rows = []
    for pl in ["PL1", "PL2"]:
        for i in range(10):
            rows.append({
                "track_id":       f"{pl}-t{i}",
                "track_name":     f"Track {pl} {i}",
                "artist_display": f"Artist {i % 3}",
                "playlist_name":  pl,
                "popularity_raw": float(40 + i * 5),
                "energy":         float(rng.uniform(0.1, 0.9)),
                "acousticness":   float(rng.uniform(0.0, 1.0)),
                "valence":        float(rng.uniform(0.0, 1.0)),
                "danceability":   float(rng.uniform(0.3, 0.9)),
                "speechiness":    float(rng.uniform(0.03, 0.15)),
                "instrumentalness": float(rng.uniform(0.0, 0.5)),
                "liveness":       float(rng.uniform(0.05, 0.4)),
                "loudness":       float(rng.uniform(-15.0, -3.0)),
                "tempo":          float(rng.uniform(80.0, 160.0)),
            })
    return pd.DataFrame(rows)


@pytest.fixture
def mood_df():
    """Hand-crafted tracks in all four quadrants."""
    return pd.DataFrame({
        "track_id":       ["t1", "t2", "t3", "t4", "t5"],
        "track_name":     ["Happy Song", "Turbulent Song", "Peaceful Song", "Dark Song", "Edge Song"],
        "artist_display": ["A", "B", "C", "D", "E"],
        "playlist_name":  ["PL1"] * 5,
        "valence":        [0.8,  0.3,  0.7,  0.2,  0.5],
        "energy":         [0.7,  0.8,  0.3,  0.2,  0.5],
    })


# ---------------------------------------------------------------------------
# TC-01 – TC-05  _short_name
# ---------------------------------------------------------------------------

class TestShortName:
    def test_short_name_unchanged(self):
        assert _short_name("Short", 22) == "Short"

    def test_exactly_at_limit_unchanged(self):
        name = "A" * 22
        assert _short_name(name, 22) == name

    def test_one_over_limit_truncated(self):
        name = "A" * 23
        result = _short_name(name, 22)
        assert len(result) == 22
        assert result.endswith("…")

    def test_long_name_truncated_correctly(self):
        name = "Very Long Playlist Name That Exceeds Limit"
        result = _short_name(name, 22)
        assert len(result) == 22
        assert result == name[:21] + "…"

    def test_custom_max_len(self):
        assert _short_name("Hello World", max_len=5) == "Hell…"


# ---------------------------------------------------------------------------
# TC-06 – TC-09  _hex_to_rgb
# ---------------------------------------------------------------------------

class TestHexToRgb:
    def test_spotify_green(self):
        assert _hex_to_rgb("#1DB954") == (29, 185, 84)

    def test_white(self):
        assert _hex_to_rgb("#FFFFFF") == (255, 255, 255)

    def test_black(self):
        assert _hex_to_rgb("#000000") == (0, 0, 0)

    def test_without_hash(self):
        assert _hex_to_rgb("FF0000") == (255, 0, 0)

    def test_red_component(self):
        r, g, b = _hex_to_rgb("#E8534A")
        assert r == 232
        assert g == 83
        assert b == 74


# ---------------------------------------------------------------------------
# TC-10 – TC-13  _playlist_color_map
# ---------------------------------------------------------------------------

class TestPlaylistColorMap:
    def test_assigns_color_to_each_playlist(self):
        color_map = _playlist_color_map(["PL1", "PL2", "PL3"])
        assert set(color_map.keys()) == {"PL1", "PL2", "PL3"}

    def test_sorted_order_gets_first_palette_color(self):
        color_map = _playlist_color_map(["Zebra", "Alpha"])
        assert color_map["Alpha"] == _PL_PALETTE[0]
        assert color_map["Zebra"] == _PL_PALETTE[1]

    def test_cycles_when_more_playlists_than_palette(self):
        n = len(_PL_PALETTE) + 2
        pls = [f"PL{i}" for i in range(n)]
        color_map = _playlist_color_map(pls)
        sorted_pls = sorted(pls)
        assert color_map[sorted_pls[0]]  == _PL_PALETTE[0]
        assert color_map[sorted_pls[len(_PL_PALETTE)]] == _PL_PALETTE[0]

    def test_single_playlist(self):
        color_map = _playlist_color_map(["Solo"])
        assert color_map["Solo"] == _PL_PALETTE[0]


# ---------------------------------------------------------------------------
# TC-14 – TC-19  Mood Map quadrant categorization
# ---------------------------------------------------------------------------

class TestMoodMapQuadrants:
    def test_happy_quadrant(self, mood_df):
        q = compute_quadrants(mood_df)
        assert "Happy Song" in q["Happy"]["track_name"].values

    def test_turbulent_quadrant(self, mood_df):
        q = compute_quadrants(mood_df)
        assert "Turbulent Song" in q["Turbulent"]["track_name"].values

    def test_peaceful_quadrant(self, mood_df):
        q = compute_quadrants(mood_df)
        assert "Peaceful Song" in q["Peaceful"]["track_name"].values

    def test_dark_quadrant(self, mood_df):
        q = compute_quadrants(mood_df)
        assert "Dark Song" in q["Dark"]["track_name"].values

    def test_edge_exactly_05_goes_to_happy(self, mood_df):
        # valence=0.5, energy=0.5 — >= threshold, goes to Happy
        q = compute_quadrants(mood_df)
        assert "Edge Song" in q["Happy"]["track_name"].values

    def test_quadrants_are_mutually_exclusive_and_exhaustive(self, mood_df):
        q = compute_quadrants(mood_df)
        total = sum(len(v) for v in q.values())
        assert total == len(mood_df)

    def test_quadrant_pct_sums_to_100(self, mood_df):
        q = compute_quadrants(mood_df)
        pct_sum = sum(quadrant_pct(v, mood_df) for v in q.values())
        assert pct_sum == pytest.approx(100.0)

    def test_quadrant_pct_zero_when_empty_total(self):
        empty = pd.DataFrame({"valence": [], "energy": []})
        q = compute_quadrants(empty)
        assert quadrant_pct(q["Happy"], empty) == 0.0


# ---------------------------------------------------------------------------
# TC-20 – TC-23  Global fingerprint
# ---------------------------------------------------------------------------

class TestGlobalFingerprint:
    def test_global_means_length(self, sample_df):
        means = compute_global_means(sample_df, RADAR_FEATS)
        assert len(means) == len(RADAR_FEATS)

    def test_global_means_values_correct(self, sample_df):
        means = compute_global_means(sample_df, RADAR_FEATS)
        for i, feat in enumerate(RADAR_FEATS):
            assert means[i] == pytest.approx(sample_df[feat].mean())

    def test_global_means_in_valid_range(self, sample_df):
        means = compute_global_means(sample_df, RADAR_FEATS)
        for val in means:
            assert 0.0 <= val <= 1.0

    def test_per_playlist_means_independent(self, sample_df):
        means_pl1 = compute_playlist_means(sample_df, "PL1", RADAR_FEATS)
        means_pl2 = compute_playlist_means(sample_df, "PL2", RADAR_FEATS)
        # Different playlists → different means (with seeded random they will differ)
        assert means_pl1 != means_pl2


# ---------------------------------------------------------------------------
# TC-24 – TC-27  Feature distributions (log vs linear scale)
# ---------------------------------------------------------------------------

class TestFeatureDistributions:
    def test_log_scale_applied_to_speechiness(self):
        vals = pd.Series([0.05] * 15)  # >10 positive values
        assert should_use_log_scale(vals, "speechiness") == True

    def test_log_scale_applied_to_instrumentalness(self):
        vals = pd.Series([0.1] * 15)
        assert should_use_log_scale(vals, "instrumentalness") == True

    def test_log_scale_not_applied_to_energy(self):
        vals = pd.Series([0.5] * 20)
        assert should_use_log_scale(vals, "energy") == False

    def test_log_scale_not_applied_when_few_positives(self):
        # Only 5 positive values — threshold is >10
        vals = pd.Series([0.05] * 5 + [0.0] * 10)
        assert should_use_log_scale(vals, "speechiness") == False

    def test_histogram_returns_correct_structure(self, sample_df):
        vals = sample_df["energy"].dropna()
        hist_vals, bin_edges = compute_feature_histogram(vals, "energy")
        assert len(hist_vals) == len(bin_edges) - 1
        assert hist_vals.sum() == len(vals)

    def test_log_histogram_bin_count(self, sample_df):
        vals = sample_df["speechiness"].dropna()
        hist_vals, bin_edges = compute_feature_histogram(vals, "speechiness", n_bins=30)
        assert len(hist_vals) == len(bin_edges) - 1


# ---------------------------------------------------------------------------
# TC-28 – TC-32  Correlation heatmap
# ---------------------------------------------------------------------------

class TestCorrelationHeatmap:
    def test_matrix_is_square(self, sample_df):
        corr = compute_correlation_matrix(sample_df, AUDIO_FEATURES)
        assert corr.shape[0] == corr.shape[1] == len(AUDIO_FEATURES)

    def test_diagonal_is_one(self, sample_df):
        corr = compute_correlation_matrix(sample_df, AUDIO_FEATURES)
        for feat in AUDIO_FEATURES:
            assert corr.loc[feat, feat] == pytest.approx(1.0)

    def test_values_rounded_to_2_decimals(self, sample_df):
        corr = compute_correlation_matrix(sample_df, AUDIO_FEATURES)
        for val in corr.values.flatten():
            assert round(val, 2) == val

    def test_values_in_minus1_to_1_range(self, sample_df):
        corr = compute_correlation_matrix(sample_df, AUDIO_FEATURES)
        assert (corr.values >= -1.0).all()
        assert (corr.values <=  1.0).all()

    def test_top_correlations_upper_triangle_only(self, sample_df):
        corr = compute_correlation_matrix(sample_df, AUDIO_FEATURES)
        top = compute_top_correlations(corr)
        # No (a, b) pair should appear as (b, a) — upper triangle excludes that
        pairs = set(zip(top["feat_a"], top["feat_b"]))
        reversed_pairs = {(b, a) for a, b in pairs}
        assert pairs.isdisjoint(reversed_pairs)

    def test_top_correlations_excludes_diagonal(self, sample_df):
        corr = compute_correlation_matrix(sample_df, AUDIO_FEATURES)
        top = compute_top_correlations(corr)
        assert not (top["feat_a"] == top["feat_b"]).any()

    def test_top_correlations_sorted_by_abs_r(self, sample_df):
        corr = compute_correlation_matrix(sample_df, AUDIO_FEATURES)
        top = compute_top_correlations(corr)
        abs_rs = top["abs_r"].tolist()
        assert abs_rs == sorted(abs_rs, reverse=True)

    def test_top_correlations_head_n(self, sample_df):
        corr = compute_correlation_matrix(sample_df, AUDIO_FEATURES)
        top = compute_top_correlations(corr, n=3)
        assert len(top) == 3


# ---------------------------------------------------------------------------
# TC-33 – TC-39  Extreme tracks
# ---------------------------------------------------------------------------

class TestExtremeTracks:
    def test_top5_has_highest_values(self, sample_df):
        top, _ = compute_extreme_tracks(sample_df, "energy")
        assert top["energy"].min() >= sample_df["energy"].nlargest(5).min()

    def test_bot5_has_lowest_values(self, sample_df):
        _, bot = compute_extreme_tracks(sample_df, "energy")
        assert bot["energy"].max() <= sample_df["energy"].nsmallest(5).max()

    def test_speechiness_bot5_skips_zeros(self):
        df = pd.DataFrame({
            "track_id":       [f"t{i}" for i in range(10)],
            "track_name":     [f"S{i}" for i in range(10)],
            "artist_display": ["A"] * 10,
            "playlist_name":  ["PL1"] * 10,
            "speechiness":    [0.0, 0.0, 0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07],
        })
        _, bot = compute_extreme_tracks(df, "speechiness")
        assert (bot["speechiness"] > 0).all()

    def test_fallback_to_all_rows_when_few_nonzero(self):
        # Only 3 non-zero values — fewer than n=5
        df = pd.DataFrame({
            "track_id":       [f"t{i}" for i in range(6)],
            "track_name":     [f"S{i}" for i in range(6)],
            "artist_display": ["A"] * 6,
            "playlist_name":  ["PL1"] * 6,
            "speechiness":    [0.0, 0.0, 0.0, 0.01, 0.02, 0.03],
        })
        _, bot = compute_extreme_tracks(df, "speechiness", n=5)
        assert len(bot) == 5  # falls back to nsmallest on full df

    def test_energy_bot5_includes_zeros(self):
        df = pd.DataFrame({
            "track_id":       [f"t{i}" for i in range(6)],
            "track_name":     [f"S{i}" for i in range(6)],
            "artist_display": ["A"] * 6,
            "playlist_name":  ["PL1"] * 6,
            "energy":         [0.0, 0.1, 0.2, 0.3, 0.8, 0.9],
        })
        _, bot = compute_extreme_tracks(df, "energy", n=3)
        # energy does NOT skip zeros
        assert 0.0 in bot["energy"].values


# ---------------------------------------------------------------------------
# TC-40 – TC-47  Value display formatting
# ---------------------------------------------------------------------------

class TestFormatExtremeValue:
    def test_energy_three_decimals(self):
        assert format_extreme_value(0.756, "energy") == "0.756"

    def test_tempo_one_decimal(self):
        assert format_extreme_value(120.5, "tempo") == "120.5"

    def test_loudness_one_decimal(self):
        assert format_extreme_value(-8.3, "loudness") == "-8.3"

    def test_instrumentalness_four_decimals(self):
        assert format_extreme_value(0.0023, "instrumentalness") == "0.0023"

    def test_speechiness_four_decimals(self):
        assert format_extreme_value(0.0456, "speechiness") == "0.0456"

    def test_zero_energy_shows_less_than(self):
        assert format_extreme_value(0.0, "energy") == "< 0.001"

    def test_zero_instrumentalness_shows_less_than(self):
        assert format_extreme_value(0.0, "instrumentalness") == "< 0.001"

    def test_near_zero_instrumentalness_shows_less_than(self):
        # 0.0001 formatted as "0.0001" → triggers replacement
        assert format_extreme_value(0.00009, "instrumentalness") == "< 0.001"

    def test_nonzero_energy_not_replaced(self):
        assert format_extreme_value(0.005, "energy") == "0.005"


# ---------------------------------------------------------------------------
# TC-48 – TC-50  Mood marker size calculation
# ---------------------------------------------------------------------------

class TestMarkerSize:
    def test_size_with_popularity(self):
        df = pd.DataFrame({"popularity_raw": [0.0, 50.0, 100.0]})
        sizes = compute_marker_size(df)
        assert sizes[0] == pytest.approx(3.0)   # 0/100*8+3
        assert sizes[1] == pytest.approx(7.0)   # 50/100*8+3
        assert sizes[2] == pytest.approx(11.0)  # 100/100*8+3

    def test_nan_popularity_treated_as_zero(self):
        df = pd.DataFrame({"popularity_raw": [None]})
        sizes = compute_marker_size(df)
        assert sizes[0] == pytest.approx(3.0)

    def test_no_popularity_column_returns_constant_6(self):
        df = pd.DataFrame({"track_id": ["t1", "t2", "t3"]})
        sizes = compute_marker_size(df)
        assert sizes == [6, 6, 6]


# ---------------------------------------------------------------------------
# TC-51 – TC-55  AppTest integration (requires streamlit >= 1.35)
# ---------------------------------------------------------------------------

try:
    from streamlit.testing.v1 import AppTest
    APPTEST_AVAILABLE = True
except ImportError:
    APPTEST_AVAILABLE = False


def _make_full_mock_df():
    rng = np.random.default_rng(0)
    rows = []
    for pl in ["PL1", "PL2"]:
        for i in range(8):
            rows.append({
                "track_id":       f"{pl}-t{i}",
                "track_name":     f"Track {i}",
                "artist_display": f"Artist {i % 2}",
                "playlist_name":  pl,
                "popularity_raw": float(50 + i),
                "energy":         float(rng.uniform(0.2, 0.9)),
                "acousticness":   float(rng.uniform(0.0, 0.8)),
                "valence":        float(rng.uniform(0.1, 0.9)),
                "danceability":   float(rng.uniform(0.3, 0.9)),
                "speechiness":    float(rng.uniform(0.03, 0.2)),
                "instrumentalness": float(rng.uniform(0.0, 0.4)),
                "liveness":       float(rng.uniform(0.05, 0.5)),
                "loudness":       float(rng.uniform(-14.0, -3.0)),
                "tempo":          float(rng.uniform(85.0, 155.0)),
            })
    return pd.DataFrame(rows)


@pytest.mark.skipif(not APPTEST_AVAILABLE, reason="streamlit.testing not available")
class TestAudioDnaPageRender:

    def _run_page(self, mock_df=None, session_state=None):
        if mock_df is None:
            mock_df = _make_full_mock_df()
        at = AppTest.from_file("pages/5_Audio_DNA.py", default_timeout=30)
        if session_state:
            for k, v in session_state.items():
                at.session_state[k] = v
        with patch("db.queries.get_tracks", return_value=mock_df), \
             patch("utils.inject_global_css"), \
             patch("utils.inject_sidebar_nav"), \
             patch("utils.check_collection_mode", return_value=True), \
             patch("utils.spotify_icon_html", return_value=""), \
             patch("utils.page_brand_html", return_value=""):
            at.run()
        return at

    def test_TC51_page_renders_without_exception(self):
        at = self._run_page()
        assert not at.exception

    def test_TC52_yc_mode_all_enriched_shows_info(self):
        mock_df = _make_full_mock_df()
        n = len(mock_df["track_id"].unique())
        at = self._run_page(session_state={
            "mode": "🔗 Your Collection",
            "uc_enriched": mock_df["track_id"].unique().tolist(),
            "uc_skipped":  [],
            "uc_failed":   [],
        })
        assert not at.exception
        info_texts = [i.value for i in at.info]
        assert any("Your Collection" in t for t in info_texts)

    def test_TC53_yc_mode_partial_enrichment_shows_warning(self):
        mock_df = _make_full_mock_df()
        all_ids = mock_df["track_id"].unique().tolist()
        at = self._run_page(session_state={
            "mode":         "🔗 Your Collection",
            "uc_enriched":  all_ids[:6],
            "uc_skipped":   all_ids[6:],
            "uc_failed":    [],
        })
        assert not at.exception
        warn_texts = [w.value for w in at.warning]
        assert any("could not be enriched" in t for t in warn_texts)

    def test_TC54_page_renders_with_single_playlist(self):
        df = _make_full_mock_df()
        df["playlist_name"] = "Solo"
        at = self._run_page(mock_df=df)
        assert not at.exception

    def test_TC55_page_renders_without_loudness_or_tempo(self):
        df = _make_full_mock_df().drop(columns=["loudness", "tempo"], errors="ignore")
        at = self._run_page(mock_df=df)
        assert not at.exception
