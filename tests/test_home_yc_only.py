"""R1: the Demo Collection (FC) mode is gone from nav and Home.

No test here may touch a database.
"""
from pathlib import Path
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest

_ROOT = Path(__file__).resolve().parent.parent
HOME_PAGE = str(_ROOT / "pages" / "0_home.py")
SID = "12345678-1234-4123-8123-123456789abc"


@pytest.fixture(autouse=True)
def _no_db(monkeypatch, patch_get_engine):
    import streamlit as st
    monkeypatch.setenv("DEV_MODE", "0")
    # page_link needs the multipage registry, absent in a single-file AppTest
    monkeypatch.setattr(st, "page_link", lambda *a, **k: None)

    def _refuse(*_a, **_kw):
        raise RuntimeError("DB access is not allowed in tests")

    patch_get_engine(_refuse)
    yield


def _run_home(params=None, cookie=None, session=None):
    import streamlit as st

    class _Ctx:
        @property
        def cookies(self):
            return {"tailorlist_sid": cookie} if cookie else {}

    at = AppTest.from_file(HOME_PAGE, default_timeout=90)
    for k, v in (params or {}).items():
        at.query_params[k] = v
    with patch.object(st, "context", _Ctx()), \
         patch("db.sessions.load_uc_session", return_value=session), \
         patch("db.sessions.touch_uc_session"):
        at.run()
    return at


def _all_text(at):
    return " ".join(m.value for m in at.markdown)


def test_nav_has_no_radio_and_writes_no_mode_key():
    at = _run_home()
    assert not at.exception, at.exception
    assert "mode" not in at.session_state
    assert not at.radio


@pytest.mark.parametrize("value", ["demo", "uc"])
def test_mode_query_param_is_ignored_and_yc_ui_renders(value):
    at = _run_home(params={"mode": value})
    assert not at.exception, at.exception
    assert "mode" not in at.session_state
    assert at.text_input, "the playlist URL input must be shown"
    assert not at.radio


def test_expired_session_shows_banner_with_new_copy_and_about_expander():
    at = _run_home(cookie=SID, session=None)
    assert not at.exception, at.exception
    text = _all_text(at)
    assert "Session expired" in text
    assert "Paste your playlist URLs below to reload your collection." in text
    assert "in the sidebar" not in text
    assert any("About this app" in e.label for e in at.expander)


def test_about_expander_renders_on_the_idle_landing_page():
    at = _run_home()
    assert any("About this app" in e.label for e in at.expander)
    assert "Powered by" in _all_text(at)


def test_demo_header_is_gone():
    at = _run_home(params={"mode": "demo"})
    assert "Explore a curated demo collection" not in _all_text(at)
