import pytest


def test_cookie_read_is_time_bounded(monkeypatch):
    # An unanswered macOS Keychain prompt blocks forever; the command must
    # give up and say why rather than hang with no output.
    import planbook.browser_cookies as bc

    class _Slow:
        def brave(self, **_kw: object) -> object:
            import time

            time.sleep(5)
            return []

    monkeypatch.setattr(bc, "_import_bc", lambda: _Slow())
    with pytest.raises(bc.CookieTimeout):
        bc.tokens_from("brave", timeout=1)


def test_diagnose_names_a_timeout(monkeypatch):
    import planbook.browser_cookies as bc

    def _boom(browser: str, **_kw: object) -> list[str]:
        raise bc.CookieTimeout

    monkeypatch.setattr(bc, "tokens_from", _boom)
    report = bc.diagnose()
    assert all("timed out" in v for v in report.values())


def _probe_setup(monkeypatch, cookies, lifetimes):
    from planbook import browser_cookies as bc
    from planbook.commands import auth as cmd

    monkeypatch.setattr(bc, "search", lambda _pref: cookies)
    monkeypatch.setattr(cmd.pbtoken, "is_expired", lambda _t: False)
    monkeypatch.setattr(
        cmd.pbtoken,
        "describe",
        lambda t: {"expires_in_seconds": lifetimes[t]},
    )
    monkeypatch.setattr(cmd, "PlanbookClient", lambda *a, **k: object())
    return cmd


def test_import_keeps_a_token_the_api_errors_on(monkeypatch):
    # "date must not be null" is the account's data breaking the probe, not a
    # dead token - discarding it locks the CLI out on the API's bad day.
    import argparse

    from planbook.errors import ApiError

    cmd = _probe_setup(monkeypatch, [("brave", "t.t.t")], {"t.t.t": 3600})

    def broken(_client):
        raise ApiError("date must not be null")

    monkeypatch.setattr(cmd, "list_classes", broken)

    args = argparse.Namespace(browser="brave", verbose=False)
    best = cmd._best_browser_token(args)
    assert best is not None
    assert best.token == "t.t.t"
    assert best.verified is False


def test_import_skips_a_token_the_api_rejects(monkeypatch):
    import argparse

    from planbook.errors import NotAuthenticated

    cmd = _probe_setup(monkeypatch, [("brave", "t.t.t")], {"t.t.t": 3600})

    def rejected(_client):
        raise NotAuthenticated("notLoggedIn")

    monkeypatch.setattr(cmd, "list_classes", rejected)

    args = argparse.Namespace(browser="brave", verbose=False)
    assert cmd._best_browser_token(args) is None


def test_a_verified_token_beats_a_longer_lived_unverified_one(monkeypatch):
    import argparse

    from planbook.errors import ApiError

    cmd = _probe_setup(
        monkeypatch,
        [("brave", "long.t.t"), ("chrome", "short.t.t")],
        {"long.t.t": 7200, "short.t.t": 600},
    )

    def probe(client):
        if getattr(client, "token", None) == "long.t.t":
            raise ApiError("date must not be null")

    class _Client:
        def __init__(self, token, **_kw):
            self.token = token

    monkeypatch.setattr(cmd, "PlanbookClient", _Client)
    monkeypatch.setattr(cmd, "list_classes", probe)

    args = argparse.Namespace(browser=None, verbose=False)
    best = cmd._best_browser_token(args)
    assert best is not None
    assert best.token == "short.t.t"
    assert best.verified is True
