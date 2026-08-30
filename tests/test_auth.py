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


def test_import_skips_a_browser_token_the_api_rejects(monkeypatch):
    # A rejected token does not always say notLoggedIn - one answered "date
    # must not be null" - so any probe failure must disqualify the candidate.
    import argparse

    from planbook import browser_cookies as bc
    from planbook.commands import auth as cmd
    from planbook.errors import ApiError

    monkeypatch.setattr(bc, "search", lambda _pref: [("brave", "t.t.t")])
    monkeypatch.setattr(cmd.pbtoken, "is_expired", lambda _t: False)
    monkeypatch.setattr(
        cmd.pbtoken, "describe", lambda _t: {"expires_in_seconds": 3600}
    )

    def rejected(_client):
        raise ApiError("date must not be null")

    monkeypatch.setattr(cmd.api, "list_classes", rejected)
    monkeypatch.setattr(cmd, "PlanbookClient", lambda *a, **k: object())

    args = argparse.Namespace(browser="brave", verbose=False)
    assert cmd._best_browser_token(args) is None
