"""Asking whether a URL answers, without arguing about how it answers.

Two suites need this and they had better agree: the external link checker and
the configuration checker both want to know that an address is real, not what
it serves. The subtleties are the reason this is one place rather than two.

A HEAD costs the other end almost nothing, so it goes first, but plenty of
servers refuse it, our own /v3/models among them. A refusal of HEAD is not an
answer about the address, so the request is then made properly with GET.

An authentication or rate-limit response also means the address is real. A bot
wall in front of a perfectly good page is far more common than a page that
moved and kept its credentials check, so those count as existing.
"""

from functools import cache

import requests

TIMEOUT = 30

# These say "you may not have this", which still means the address is there.
EXISTS_ANYWAY = frozenset({401, 403, 405, 429})

# A bare python-requests user agent is refused by enough sites to be worth
# avoiding, and a request that says what it is beats one that pretends.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; edenai-docs-linkcheck; "
        "+https://github.com/edenai/docs)"
    ),
    "Accept": "*/*",
}


def fetch(url: str, method: str) -> requests.Response | None:
    """One request, or None if the host never answered."""
    try:
        return requests.request(
            method,
            url,
            timeout=TIMEOUT,
            allow_redirects=True,
            headers=HEADERS,
        )
    except requests.RequestException:
        return None


def answers(url: str) -> requests.Response | None:
    """The response to a HEAD, or to a GET when HEAD was no use."""
    response = fetch(url, "HEAD")
    if response is None or response.status_code >= 400:
        response = fetch(url, "GET")
    return response


@cache
def url_exists(url: str) -> bool:
    """Whether the address is real, whatever it chooses to serve.

    Cached, because a base URL is written on a dozen pages and asking a dozen
    times says nothing the first answer did not.
    """
    response = answers(url)
    if response is None:
        return False
    return response.status_code < 400 or response.status_code in EXISTS_ANYWAY
