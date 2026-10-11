"""Suite-wide safety net: deterministic env + loud failure on real DB / network access.

Why: tests patch loaders by import path (e.g. ``db.queries.load_cluster_data``).
If code moves and a patch stops intercepting, a test could silently hit the real
local MySQL or Spotify/ReccoBeats and pass by accident. These guards make that fail.
"""
import ipaddress
import socket

import pytest

# config loads .env at import time. Import it FIRST so that happens now, then
# pin the env, so later monkeypatch.setenv wins and results never depend on the
# developer's local .env.
import config  # noqa: F401

import os

os.environ["DEV_MODE"] = "1"  # effective value today (local .env sets it)

DB_MSG = ("test tried to reach a real database - patch the loader where the "
          "page looks it up")
NET_MSG = ("test tried to make a real network call - mock it (requests/spotipy) "
           "where the code looks it up")


class RealResourceAccess(AssertionError):
    pass


# Every blocked access is recorded here; app code with `except Exception` can
# swallow the raised error, so the fixture teardown fails the test from this list.
_attempts: list[str] = []


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "allows_blocked_access: test intentionally runs with DB/network unreachable "
        "(accesses are still blocked, but not failed at teardown)",
    )


def _db_blocked(*args, **kwargs):
    _attempts.append("DB: %s" % (str(args[0])[:80] if args else "connect"))
    raise RealResourceAccess(DB_MSG)


def _net_blocked(*args, **kwargs):
    req = args[1] if len(args) > 1 else None
    _attempts.append("network: %s" % getattr(req, "url", "?"))
    raise RealResourceAccess(NET_MSG)


def _is_local(host) -> bool:
    if isinstance(host, bytes):
        host = host.decode()
    if host in ("localhost", ""):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


@pytest.fixture(autouse=True)
def _no_real_db_or_network(monkeypatch, request):
    _attempts.clear()
    # DB: create_engine is the choke point for every engine (db.connection binds
    # it by name, so patch that binding too); pymysql.connect catches any engine
    # built before the guard existed (e.g. a cached get_engine()).
    import sqlalchemy
    import sqlalchemy.engine
    import pymysql
    import db.connection

    monkeypatch.setattr(sqlalchemy, "create_engine", _db_blocked)
    monkeypatch.setattr(sqlalchemy.engine, "create_engine", _db_blocked)
    monkeypatch.setattr(db.connection, "create_engine", _db_blocked)
    monkeypatch.setattr(pymysql, "connect", _db_blocked)

    # Network, requests level: urllib3 wraps socket errors into ConnectionError,
    # so block HTTPAdapter.send (what spotipy/requests go through) directly.
    import requests.adapters
    monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", _net_blocked)

    # Network, socket level: any non-loopback socket connect fails (covers requests, urllib3,
    # spotipy, pymysql). Tests that mock requests.get never reach this.
    real_connect = socket.socket.connect

    def guarded_connect(self, address):
        if isinstance(address, tuple) and not _is_local(address[0]):
            _attempts.append("network: socket connect %s" % (address,))
            raise RealResourceAccess(NET_MSG)
        return real_connect(self, address)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(
        socket, "create_connection",
        lambda address, *a, **k: _raise_if_remote(address, *a, **k),
    )
    yield
    if _attempts and not request.node.get_closest_marker("allows_blocked_access"):
        found = "\n  ".join(_attempts)
        _attempts.clear()
        pytest.fail("blocked real DB/network access (possibly swallowed by app code):\n  "
                    + found, pytrace=False)


def _raise_if_remote(address, *a, **k):
    if not _is_local(address[0]):
        _attempts.append("network: create_connection %s" % (address,))
        raise RealResourceAccess(NET_MSG)
    return _orig_create_connection(address, *a, **k)


_orig_create_connection = socket.create_connection
