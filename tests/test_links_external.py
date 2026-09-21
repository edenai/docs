"""Checks on the links that leave the documentation.

Two very different things live here because both need the network and neither
needs a credential.

The OpenAPI specs are ours. docs.json points the API reference tabs at two
live URLs, and Mintlify renders those tabs by fetching them at build time, so
a spec that stops resolving or stops parsing empties a whole section of the
site with nothing in this repository having changed. That check runs on every
pull request.

The external links are not ours. Fifteen of the forty-odd are github.com,
which rate-limits an unauthenticated CI address, and the rest are other
people's sites going down on their own schedule. A docs pull request must not
go red because somebody else's marketing page is having an afternoon, so these
run on the weekly schedule against main, where there is nobody waiting.
"""

import json

import pytest
import requests

from tests.helpers.env import env_flag
from tests.links import external_urls, openapi_specs

CHECK_EXTERNAL_LINKS_ENV_VAR = "EDEN_AI_CHECK_EXTERNAL_LINKS"

_TIMEOUT = 30

# Somebody else's server answering at all is the thing being tested. These say
# "you may not have this", which still means the address is real; a bot wall in
# front of a perfectly good page is far more common than a page that has moved
# and kept its credentials check.
_EXISTS_ANYWAY = frozenset({401, 403, 405, 429})

# A bare python-requests user agent is refused by enough sites to be worth
# avoiding, and a request that says what it is beats one that pretends.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; edenai-docs-linkcheck; "
        "+https://github.com/edenai/docs)"
    ),
    "Accept": "*/*",
}

_URLS = external_urls()
_SPECS = openapi_specs()


def _fetch(url: str, method: str) -> requests.Response | None:
    """One request, or None if the host never answered."""
    try:
        return requests.request(
            method,
            url,
            timeout=_TIMEOUT,
            allow_redirects=True,
            headers=_HEADERS,
        )
    except requests.RequestException:
        return None


@pytest.mark.parametrize("url", _SPECS, ids=_SPECS)
def test_the_openapi_spec_an_api_reference_renders_from_is_usable(url):
    """The spec fetches, parses, and describes endpoints.

    Checking for a 200 alone would miss the failure that actually happens: the
    URL answers, with an error page or a truncated document, and the reference
    tab renders empty.
    """
    response = _fetch(url, "GET")
    assert response is not None, f"{url} did not answer"
    assert response.status_code == 200, (
        f"{url} answered {response.status_code}, so the API reference it "
        f"renders has nothing to render"
    )

    try:
        spec = response.json()
    except json.JSONDecodeError as exc:
        pytest.fail(f"{url} did not answer with JSON: {exc}")

    assert spec.get("openapi"), f"{url} has no openapi version, so it is not a spec"
    assert spec.get("paths"), f"{url} describes no endpoints"


@pytest.mark.parametrize("url", _URLS, ids=_URLS)
def test_an_external_link_still_goes_somewhere(url):
    """Every address the docs send a reader to still answers."""
    if not env_flag(CHECK_EXTERNAL_LINKS_ENV_VAR):
        pytest.skip(
            f"third-party sites are checked on the weekly run; set "
            f"{CHECK_EXTERNAL_LINKS_ENV_VAR}=1 to check them here"
        )

    # HEAD first because it costs the other site almost nothing. Plenty of
    # servers refuse it though, including our own /v3/models, so a refusal is
    # not an answer about the link and the request is made properly instead.
    response = _fetch(url, "HEAD")
    if response is None or response.status_code >= 400:
        response = _fetch(url, "GET")

    assert response is not None, f"{url} did not answer"

    if response.status_code < 400 or response.status_code in _EXISTS_ANYWAY:
        return

    pytest.fail(f"{url} answered {response.status_code} ({response.reason})")


def test_the_checks_have_something_to_check():
    """An extraction change that quietly found nothing would pass everything."""
    assert len(_SPECS) == 2, "docs.json should point at two OpenAPI documents"
    assert len(_URLS) > 30
