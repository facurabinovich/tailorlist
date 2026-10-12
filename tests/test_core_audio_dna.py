"""Characterization tests for core/audio_dna.py and ui/charts.py."""
import numpy as np
import pandas as pd
import pytest

from core import audio_dna as dna
from core.formatting import short_name
from ui import charts


def _df():
    return pd.DataFrame({
        "track_id": ["a", "b", "c", "a", "d"],
        "track_name": ["A", "B", "C", "A", "D"],
        "artist_display": ["x"] * 5,
        "playlist_name": ["P1", "P1", "P2", "P2", "P2"],
        "valence": [0.9, 0.1, 0.5, 0.9, 0.2],
        "energy": [0.9, 0.9, 0.2, 0.9, 0.1],
        "popularity_raw": [100.0, None, 50.0, 100.0, 0.0],
    })


def test_select_playlists_filters_and_dedupes():
    sel = dna.select_playlists(_df(), ["P1", "P2"])
    assert len(sel.rows) == 5 and list(sel.unique["track_id"]) == ["a", "b", "c", "d"]
    only = dna.select_playlists(_df(), ["P2"])
    assert len(only.rows) == 3 and len(only.unique) == 3


def test_select_playlists_empty_and_unknown():
    sel = dna.select_playlists(_df(), [])
    assert sel.rows.empty and sel.unique.empty
    assert dna.select_playlists(_df(), ["nope"]).rows.empty


def test_has_audio_data():
    assert dna.has_audio_data(_df())
    assert not dna.has_audio_data(pd.DataFrame({"track_id": ["a"]}))
    assert not dna.has_audio_data(pd.DataFrame({"energy": [np.nan]}))
    assert not dna.has_audio_data(_df().iloc[0:0])


def test_enrichment_stats():
    e = [{"id": "1"}, {"id": "2"}, {"id": "2"}, {"name": "no id"}]
    s = [{"id": "2"}, {"id": "3"}]
    f = [{"id": "3"}, {"id": "4"}]
    st = dna.enrichment_stats(e, s, f)
    assert (st.with_audio_features, st.without_audio_features, st.total) == (2, 2, 4)
    assert dna.enrichment_stats([], [], []).total == 0


def test_mood_quadrants_threshold_and_nan():
    df = pd.DataFrame({"valence": [0.5, 0.49, 0.5, 0.1, np.nan], "energy": [0.5, 0.5, 0.49, 0.1, 0.9]})
    q = dna.mood_quadrants(df)
    assert list(q) == dna.MOOD_NAMES
    assert [len(q[n]) for n in dna.MOOD_NAMES] == [1, 1, 1, 1]  # NaN row in none
    stats = dna.mood_summary(df)
    assert [s.count for s in stats] == [1, 1, 1, 1]
    assert stats[0].pct == pytest.approx(20.0)  # percent over all 5 rows


def test_mood_summary_empty():
    stats = dna.mood_summary(pd.DataFrame({"valence": [], "energy": []}))
    assert all(s.count == 0 and s.pct == 0.0 for s in stats)


def test_mood_missing_column_raises():
    with pytest.raises(KeyError):
        dna.mood_quadrants(pd.DataFrame({"energy": [0.1]}))


def test_marker_sizes():
    assert dna.marker_sizes(_df()) == [11.0, 3.0, 7.0, 11.0, 3.0]
    assert dna.marker_sizes(pd.DataFrame({"x": [1, 2]})) == [6, 6]


def test_feature_means_defaults_and_nan():
    df = pd.DataFrame({f: [0.2, np.nan, 0.4] for f in dna.RADAR_FEATURES})
    assert dna.feature_means(df) == pytest.approx([0.3] * 7)
    assert dna.feature_means(df, ["energy"]) == pytest.approx([0.3])
    assert np.isnan(dna.feature_means(df.iloc[0:0], ["energy"])[0])


def test_playlist_feature_means_dedupes_within_playlist():
    df = pd.DataFrame({"playlist_name": ["P", "P", "P", "Q"], "track_id": ["a", "a", "b", "c"],
                       "energy": [0.2, 0.2, 0.8, 1.0]})
    assert dna.playlist_feature_means(df, "P", ["energy"]) == pytest.approx([0.5])
    assert np.isnan(dna.playlist_feature_means(df, "none", ["energy"])[0])


def test_distribution_and_correlation_features_follow_columns():
    df = pd.DataFrame({"energy": [1.0], "tempo": [100.0], "loudness": [-5.0]})
    assert dna.distribution_features(df) == ["energy", "tempo"]
    assert dna.correlation_features(df) == ["energy", "loudness", "tempo"]
    assert dna.distribution_features(pd.DataFrame()) == []


def test_histogram_linear_and_log():
    vals = pd.Series(np.linspace(0, 1, 50))
    h = dna.feature_histogram(vals, "energy")
    assert not h.log_scale and len(h.counts) == 30 and h.counts.sum() == 50
    pos = pd.Series([0.0] * 5 + list(np.linspace(0.001, 0.5, 20)))
    hl = dna.feature_histogram(pos, "speechiness")
    assert hl.log_scale and len(hl.counts) == 29 and hl.counts.sum() == 20
    assert min(hl.centers) < 0


def test_histogram_log_threshold_is_more_than_10_positives():
    ten = pd.Series([0.1 * (i + 1) for i in range(10)])
    assert not dna.uses_log_scale(ten, "speechiness")
    assert dna.uses_log_scale(pd.Series([0.1 * (i + 1) for i in range(11)]), "speechiness")


def test_histogram_empty_values_linear():
    h = dna.feature_histogram(pd.Series([], dtype=float), "energy")
    assert h.counts.sum() == 0 and len(h.centers) == 30


def test_correlation_matrix_and_top():
    df = pd.DataFrame({"a": [1, 2, 3, 4], "b": [2, 4, 6, 8], "c": [4, 3, 2, 1.5]})
    m = dna.correlation_matrix(df, ["a", "b", "c"])
    assert m.loc["a", "b"] == 1.0
    top = dna.top_correlations(m, n=2)
    assert len(top) == 2 and set(top.columns) == {"feat_a", "feat_b", "r", "abs_r"}
    assert top.iloc[0]["abs_r"] >= top.iloc[1]["abs_r"]


def test_correlation_ignores_rows_with_nan_and_handles_one_feature():
    df = pd.DataFrame({"a": [1, 2, np.nan, 4], "b": [1, 2, 3, 4]})
    assert dna.correlation_matrix(df, ["a", "b"]).shape == (2, 2)
    assert dna.top_correlations(dna.correlation_matrix(df, ["a"])).empty


def test_extreme_tracks_basic_and_few_rows():
    df = _df().drop_duplicates("track_id")
    top, bot = dna.extreme_tracks(df, "energy", n=2)
    assert list(top["energy"]) == [0.9, 0.9] and list(bot["energy"]) == [0.1, 0.2]
    top, bot = dna.extreme_tracks(df, "energy")
    assert len(top) == len(bot) == 4


def test_extreme_tracks_nan_ranks_last_and_only_fills_short_lists():
    df = pd.DataFrame({"track_name": list("abc"), "artist_display": "x", "playlist_name": "P",
                       "energy": [np.nan, 0.3, 0.7]})
    top, bot = dna.extreme_tracks(df, "energy")
    # pandas nlargest/nsmallest put NaN rows last, and they appear when fewer than n valid rows exist
    assert list(top["track_name"]) == ["c", "b", "a"] and list(bot["track_name"]) == ["b", "c", "a"]


def test_extreme_tracks_missing_feature_raises():
    with pytest.raises(KeyError):
        dna.extreme_tracks(_df(), "tempo")


@pytest.mark.parametrize("val,feat,expected", [
    (120.04, "tempo", "120.0"), (-7.26, "loudness", "-7.3"), (0.00123, "speechiness", "0.0012"),
    (0.0004, "energy", "< 0.001"), (0.00014, "instrumentalness", "< 0.001"),
    (0.0002, "instrumentalness", "0.0002"),
])
def test_format_extreme_value(val, feat, expected):
    assert dna.format_extreme_value(val, feat) == expected


def test_short_name():
    assert short_name("abc", 3) == "abc" and short_name("abcd", 3) == "ab…" and short_name("", 5) == ""


def test_charts_layout_override_is_shallow():
    base = charts.layout()
    assert base == charts.BASE_LAYOUT and base is not charts.BASE_LAYOUT
    out = charts.layout(height=10, margin=dict(t=1))
    assert out["height"] == 10 and out["margin"] == {"t": 1}
    assert charts.BASE_LAYOUT["margin"] == dict(t=20, b=20, l=10, r=10)


def test_charts_color_map_sorted_and_cycling():
    m = charts.playlist_color_map({"b", "a"})
    assert m == {"a": charts.PLAYLIST_PALETTE[0], "b": charts.PLAYLIST_PALETTE[1]}
    n = len(charts.PLAYLIST_PALETTE)
    big = charts.playlist_color_map([f"p{i:02d}" for i in range(n + 1)])
    assert big["p00"] == big[f"p{n:02d}"]
    assert charts.playlist_color_map([]) == {}


def test_hex_to_rgb():
    assert charts.hex_to_rgb("#1DB954") == (29, 185, 84)
    assert charts.hex_to_rgb("ff0000") == (255, 0, 0)
