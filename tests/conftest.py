import pytest


@pytest.fixture
def isolated_config(monkeypatch, tmp_path):
    home = tmp_path / "home"
    xdg = tmp_path / "xdg"
    home.mkdir()
    xdg.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
    monkeypatch.delenv("PLANBOOK_SESSION", raising=False)
    return xdg


@pytest.fixture
def session_file(isolated_config):
    session_dir = isolated_config / "planbook"
    session_dir.mkdir(parents=True)
    path = session_dir / "session.json"
    path.write_text('{"session": "test-session"}')
    return path
