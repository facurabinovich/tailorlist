"""config.py: single .env loader and is_dev_mode() as the single DEV_MODE source."""
import importlib

import pytest

import config


@pytest.mark.parametrize("value, expected", [(None, False), ("0", False), ("1", True), ("", False)])
def test_is_dev_mode(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv("DEV_MODE", raising=False)
    else:
        monkeypatch.setenv("DEV_MODE", value)
    assert config.is_dev_mode() is expected


def test_is_dev_mode_reads_env_on_every_call(monkeypatch):
    monkeypatch.setenv("DEV_MODE", "1")
    assert config.is_dev_mode() is True
    monkeypatch.setenv("DEV_MODE", "0")
    assert config.is_dev_mode() is False


def test_env_file_does_not_override_existing_process_env(monkeypatch, tmp_path):
    """monitoring.py sets DEV_MODE=0 before importing db.connection; .env must not clobber it."""
    import dotenv

    env_file = tmp_path / ".env"
    env_file.write_text("DEV_MODE=1\nT5_ONLY_IN_ENV_FILE=hello\n")
    real_load = dotenv.load_dotenv
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *_a, **kw: real_load(env_file, **kw))
    monkeypatch.setenv("DEV_MODE", "0")
    monkeypatch.delenv("T5_ONLY_IN_ENV_FILE", raising=False)
    try:
        importlib.reload(config)
        assert config.is_dev_mode() is False
        # ...but variables missing from the process env are still loaded from .env
        assert __import__("os").environ["T5_ONLY_IN_ENV_FILE"] == "hello"
    finally:
        monkeypatch.undo()
        importlib.reload(config)
