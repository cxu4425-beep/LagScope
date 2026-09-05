"""The desktop server and the Android viewer have to agree on the wire.

They are written in different languages, tested by different runners, and each
suite was perfectly consistent with itself - which is exactly why the access
code was sent as "code" and read as "key" for as long as it was. Nothing in
either language could see the other end.

So the contract is asserted here, by reading both sides.
"""

import re
from pathlib import Path

import pytest

from lagscope.web import ACCESS_QUERY, PAGE, dashboard_urls

ANDROID = Path(__file__).resolve().parent.parent / "android"
PAIRING = ANDROID / "src" / "tw" / "lagscope" / "viewer" / "Pairing.java"


def _java_constant(source: str, name: str) -> str:
    match = re.search(
        r'public\s+static\s+final\s+String\s+%s\s*=\s*"([^"]*)"' % name, source)
    assert match, f"{name} not found in Pairing.java"
    return match.group(1)


@pytest.fixture(scope="module")
def pairing_java():
    if not PAIRING.exists():
        pytest.skip("the Android sources are not present")
    return PAIRING.read_text(encoding="utf-8")


def test_both_sides_name_the_access_code_the_same(pairing_java):
    """The phone built "?code=" and the server read "key", so pairing by the
    two fields on screen produced a 403 and the page said the access code was
    wrong. Pasting the whole URL happened to work, which is why it survived."""
    assert _java_constant(pairing_java, "QUERY_KEY") == ACCESS_QUERY


def test_the_page_reads_the_same_parameter_it_is_given():
    """Three places have to agree: the URL the desktop shows, the check on the
    server, and the JavaScript that re-sends the code with every poll."""
    assert f'get("{ACCESS_QUERY}")' in PAGE
    assert f'"?{ACCESS_QUERY}=" + encodeURIComponent(KEY)' in PAGE


def test_the_url_the_desktop_shows_is_one_the_phone_accepts(pairing_java):
    """What the user actually copies has to survive the phone's own parsing."""
    url = dashboard_urls(23125, "4821")[0]
    assert f"?{ACCESS_QUERY}=4821" in url
    # Pairing returns a pasted URL untouched, so it must already be complete.
    assert url.startswith("http://") and url.count("?") == 1


def test_both_sides_agree_on_the_port(pairing_java):
    from lagscope.web import DEFAULT_PORT

    match = re.search(r"public\s+static\s+final\s+int\s+DEFAULT_PORT\s*=\s*(\d+)",
                      pairing_java)
    assert match, "DEFAULT_PORT not found in Pairing.java"
    assert int(match.group(1)) == DEFAULT_PORT


def test_the_phone_asks_the_endpoint_the_server_serves():
    """The page fetches a relative "api/state"; the handler has to route it."""
    assert 'fetch("api/state"' in PAGE
    import lagscope.web as web

    assert "api/state" in Path(web.__file__).read_text(encoding="utf-8")
