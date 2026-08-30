import pytest
import responses

from planbook import auth
from planbook.client import API_BASE, AUTH_BASE
from planbook.errors import LoginFailed


def test_csrf_token_extracts_hidden_input_value():
    html = """
    <html><body>
      <form><input type="hidden" name="_csrf" value="token-123"></form>
    </body></html>
    """
    assert auth._csrf_token(html) == "token-123"


def test_csrf_token_raises_when_missing():
    with pytest.raises(LoginFailed):
        auth._csrf_token("<html><form></form></html>")


@responses.activate
def test_login_mentions_sso_when_no_candidate_session_cookie_works():
    responses.get(
        f"{AUTH_BASE}/login",
        body='<input type="hidden" name="_csrf" value="csrf-1">',
        headers={"Set-Cookie": "SESSION=pre-auth; Path=/; Domain=.planbook.com"},
    )
    responses.post(
        f"{AUTH_BASE}/login",
        body="<html>login response</html>",
        headers={"Set-Cookie": "SESSION=post-auth; Path=/; Domain=.planbook.com"},
    )
    responses.post(f"{API_BASE}/getClasses2", json={"notLoggedIn": "true"})
    responses.post(f"{API_BASE}/getClasses2", json={"notLoggedIn": "true"})

    with pytest.raises(LoginFailed, match="SSO"):
        auth.login("teacher@example.com", "bad-password")


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
