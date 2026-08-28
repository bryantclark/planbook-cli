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
    monkeypatch.delenv("PLANBOOK_TOKEN", raising=False)
    return xdg


@pytest.fixture
def session_file(isolated_config):
    session_dir = isolated_config / "planbook"
    session_dir.mkdir(parents=True)
    path = session_dir / "token.json"
    # A syntactically valid JWT so token decoding has something to chew on.
    path.write_text('{"token": "eyJhbGciOiJIUzUxMiJ9.eyJzdWIiOiJ7fSJ9.sig"}')
    return path
