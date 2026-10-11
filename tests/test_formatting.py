"""Characterization tests for core.formatting.fmt_duration."""
import pytest

from core.formatting import fmt_duration


@pytest.mark.parametrize("minutes, expected", [
    (0, "0:00"),
    (3.5, "3:30"),
    (4.0, "4:00"),
    (3.1166, "3:07"),
    (125.25, "125:15"),
])
def test_fmt_duration(minutes, expected):
    assert fmt_duration(minutes) == expected


def test_fmt_duration_rounding_overflow():
    # H6: existing behavior, preserved; fix pending decision
    assert fmt_duration(3.999) == "3:60"
