"""YC session (sid) recovery from a bookmarked or typed URL.

The old scheme stored the sid in localStorage and had the component iframe
redirect the top window to put it back in the URL. Streamlit sandboxes that
iframe without allow-top-navigation, so the redirect was always blocked and
recovery never worked. The sid now travels in a cookie that Python reads via
st.context.cookies, and gets written back into the URL from there.

No test here may touch a database.
"""
import os
from unittest.mock import MagicMock, patch

import pytest

import spotify_client  # noqa: F401 — does load_dotenv(override=True) on import

from streamlit.testing.v1 import AppTest
from pathlib import Path

import utils

_ROOT = Path(__file__).resolve().parent.parent
HOME_PAGE = str(_ROOT / "pages" / "0_home.py")

SID = "12345678-1234-4123-8123-123456789abc"
OTHER_SID = "abcdef01-2345-4678-89ab-cdef01234567"
MAX_AGE = 7 * 24 * 60 * 60

FAKE_SESSION = {
    "enriched": [], "skipped": [], "failed": [],
    "playlists": [{"id": "pl1", "name": "PL 1", "track_count": 3}],
}


@pytest.fixture(autouse=True)
def _no_db(monkeypatch):
    monkeypatch.setenv("DEV_MODE", "0")

    def _refuse(*_a, **_kw):
        raise RuntimeError("DB access is not allowed in tests")

    monkeypatch.setattr("db.connection.get_engine", _refuse)
    yield


class _Ctx:
    def __init__(self, sid=None):
        self._sid = sid

    @property
    def cookies(self):
        return {"tailorlist_sid": self._sid} if self._sid else {}


def _resolve(state=None, params=None, cookie=None, context=None):
    import streamlit as st
    ctx = context if context is not None else _Ctx(cookie)
    with patch.object(st, "session_state", state or {}), \
         patch.object(st, "query_params", params or {}), \
         patch.object(st, "context", ctx):
        return utils.resolve_sid()


class TestResolveSid:
    def test_none_anywhere(self):
        assert _resolve() == ""

    def test_from_cookie_alone(self):
        """The whole point: no sid in the URL, recovered from the cookie."""
        assert _resolve(cookie=SID) == SID

    def test_from_url(self):
        assert _resolve(params={"sid": SID}) == SID

    def test_session_state_wins_over_url_and_cookie(self):
        got = _resolve(state={"uc_session_id": SID},
                       params={"sid": OTHER_SID}, cookie=OTHER_SID)
        assert got == SID

    def test_url_wins_over_cookie(self):
        """A shared link should open that collection, not the stored one."""
        assert _resolve(params={"sid": SID}, cookie=OTHER_SID) == SID

    def test_malformed_values_are_rejected(self):
        assert _resolve(cookie="not-a-uuid") == ""
        assert _resolve(params={"sid": "../../etc/passwd"}) == ""
        assert _resolve(state={"uc_session_id": "' OR 1=1--"}) == ""

    def test_forgotten_blocks_cookie_recovery(self):
        state = {"_sid_forgotten": True}
        assert _resolve(state=state, cookie=SID) == ""

    def test_forgotten_does_not_block_an_explicit_url_sid(self):
        state = {"_sid_forgotten": True}
        assert _resolve(state=state, params={"sid": SID}, cookie=OTHER_SID) == SID

    def test_failed_lookup_stops_retrying_this_session(self):
        state = {"_sid_unavailable": True}
        assert _resolve(state=state, cookie=SID) == ""


class TestUnavailableVsForgotten:
    """A failed lookup must not destroy the cookie: load_uc_session() returns
    None both for an expired session and for a DB it could not reach."""

    def test_unavailable_keeps_the_cookie(self):
        import streamlit as st
        state = {}
        with patch.object(st, "session_state", state):
            utils.mark_uc_session_unavailable()
        assert state == {"_sid_unavailable": True}
        assert "_sid_forgotten" not in state

    def test_only_forgotten_triggers_deletion(self):
        js_unavailable = TestCookieJsBranch()._injected_js(
            {"_sid_unavailable": True}, cookie=SID)
        assert "max-age=0" not in js_unavailable

        js_forgotten = TestCookieJsBranch()._injected_js(
            {"_sid_forgotten": True}, cookie=SID)
        assert "max-age=0" in js_forgotten

    def test_missing_st_context_is_survivable(self):
        class _Raises:
            @property
            def cookies(self):
                raise RuntimeError("no st.context on this Streamlit version")

        assert _resolve(context=_Raises()) == ""
        assert _resolve(params={"sid": SID}, context=_Raises()) == SID


class TestForgetUcSession:
    def test_sets_the_flag(self):
        import streamlit as st
        state = {}
        with patch.object(st, "session_state", state):
            utils.forget_uc_session()
        assert state["_sid_forgotten"] is True


class TestCookieJsBranch:
    """Which JS the sidebar injects — write, delete, or migrate legacy."""

    def _injected_js(self, state, params=None, cookie=None):
        import streamlit as st
        payloads = []

        def _html(body, **_kw):
            payloads.append(body)

        with patch.object(st, "session_state", state), \
             patch.object(st, "query_params", params if params is not None else {}), \
             patch.object(st, "context", _Ctx(cookie)), \
             patch.object(st, "sidebar", MagicMock()), \
             patch("streamlit.components.v1.html", _html):
            try:
                utils.inject_sidebar_nav("Home")
            except Exception:
                pass          # everything after the cookie block needs a real run
        assert payloads, "no component HTML was injected"
        return payloads[0]

    def test_writes_the_cookie_when_a_session_exists(self):
        js = self._injected_js({"uc_session_id": SID})
        assert f"tailorlist_sid={SID}" in js
        assert f"max-age={MAX_AGE}" in js
        assert "SameSite=Lax" in js
        assert "path=/" in js

    def test_deletes_the_cookie_once_forgotten(self):
        js = self._injected_js({"_sid_forgotten": True}, cookie=SID)
        assert "tailorlist_sid=;path=/;max-age=0" in js
        assert SID not in js

    def test_migrates_a_legacy_localstorage_sid(self):
        js = self._injected_js({})
        assert "localStorage.getItem('tailorlist_sid')" in js
        assert "UUID_RE.test(legacySid)" in js

    def test_a_new_session_supersedes_forgotten(self):
        """Enriching again after a reset must re-establish the cookie."""
        state = {"_sid_forgotten": True, "uc_session_id": SID}
        js = self._injected_js(state)
        # The injected JS is the proof: it writes the cookie instead of
        # deleting it, which only happens once the marker has been cleared.
        assert f"tailorlist_sid={SID}" in js
        assert "max-age=0" not in js

    def test_no_blocked_top_navigation_remains(self):
        """The old redirect could never run inside the sandboxed iframe."""
        js = self._injected_js({"uc_session_id": SID})
        assert "location.replace" not in js


class TestHomeRecoversFromCookie:
    def _run(self, cookie=None, params=None, session=FAKE_SESSION):
        at = AppTest.from_file(HOME_PAGE, default_timeout=90)
        for k, v in (params or {}).items():
            at.query_params[k] = v
        import streamlit as st
        with patch.object(st, "context", _Ctx(cookie)), \
             patch("db.queries.load_uc_session", return_value=session) as load, \
             patch("db.queries.touch_uc_session") as touch, \
             patch("utils.inject_sidebar_nav"):
            at.run()
        return at, load, touch

    def test_bookmarked_bare_url_recovers_the_collection(self):
        at, load, touch = self._run(cookie=SID)
        assert not at.exception, at.exception
        load.assert_called_once_with(SID)
        assert at.session_state["uc_active"] is True
        assert at.session_state["uc_session_id"] == SID
        assert at.session_state["mode"] == "🔗 Your Collection"
        assert touch.call_count == 1

    def test_failed_lookup_shows_the_banner_and_keeps_the_cookie(self):
        at, _load, touch = self._run(cookie=SID, session=None)
        assert not at.exception, at.exception
        # AppTest's session_state has no .get()
        assert at.session_state["_sid_unavailable"] is True
        assert "_sid_forgotten" not in at.session_state, \
            "a failed lookup must not delete the cookie — the DB may be down"
        # _session_expired is consumed by the banner in this same run
        assert any("Session expired" in m.value for m in at.markdown)
        assert touch.call_count == 0

    def test_no_cookie_no_restore(self):
        at, load, _touch = self._run(cookie=None)
        assert not at.exception, at.exception
        assert load.call_count == 0
        assert "uc_active" not in at.session_state
