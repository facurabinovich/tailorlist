"""Prove the conftest guards fail loudly instead of reaching real resources."""
from pathlib import Path

import pytest
import requests

from tests.conftest import RealResourceAccess


# These deliberately trigger the guards, so they opt out of the teardown failure.
@pytest.mark.allows_blocked_access
def test_creating_engine_is_blocked():
    import sqlalchemy
    from db.connection import get_engine
    with pytest.raises(RealResourceAccess, match="real database"):
        sqlalchemy.create_engine("mysql+pymysql://u:p@example.invalid/db")
    # get_engine may be cached; its underlying create_engine binding is guarded too.
    import db.connection
    with pytest.raises(RealResourceAccess, match="real database"):
        db.connection.create_engine("x")
    assert callable(get_engine)


@pytest.mark.allows_blocked_access
def test_http_get_is_blocked():
    with pytest.raises(RealResourceAccess, match="network"):
        requests.get("http://example.com", timeout=1)


def test_dev_mode_pinned():
    import os
    assert os.environ["DEV_MODE"] == "1"


pytest_plugins = ["pytester"]


def test_swallowed_access_still_fails(pytester, monkeypatch):
    """An `except Exception` in app code must not hide a blocked access."""
    # Reuse the real conftest in a throwaway project; the repo root must be importable.
    root = Path(__file__).resolve().parent.parent
    monkeypatch.setenv("PYTHONPATH", str(root))
    pytester.makeconftest((root / "tests" / "conftest.py").read_text())
    pytester.makepyfile("""
        import requests
        def test_swallows():
            try:
                requests.get("http://example.com", timeout=1)
            except Exception:
                pass
    """)
    result = pytester.runpytest_subprocess("-p", "no:cacheprovider")
    outcomes = result.parseoutcomes()
    assert outcomes.get("passed") == 1 and outcomes.get("errors") == 1
    result.stdout.fnmatch_lines(["*blocked real DB/network access*"])
