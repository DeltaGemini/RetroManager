"""
Fetching only from the internet: an address RetroManager is given to download from
(a picture's, a manual's) must be a public one, so a page or a request can't have it
fetch from the home network instead (the router's admin page, another machine's) and
keep what came back. Each redirect is checked again.
"""

import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import requests

MAX_REDIRECTS = 5


class NotPublic(ValueError):
    pass


def check_public(url: str):
    """Raises NotPublic unless url is http(s) to a host whose every address is a public one."""
    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname:
        raise NotPublic("not a web address")
    try:
        found = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == 'https' else 80), proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError) as e:
        raise NotPublic(f"{parsed.hostname} couldn't be found ({e})")
    for *_, address in found:
        ip = ipaddress.ip_address(address[0].split('%')[0])
        if not ip.is_global:
            raise NotPublic(f"{parsed.hostname} is on this network, not the internet: RetroManager only downloads from the internet")


def get_public(url: str, **kwargs) -> requests.Response:
    """requests.get, following redirects by hand so that each address is checked first."""
    kwargs['allow_redirects'] = False
    for _ in range(MAX_REDIRECTS + 1):
        check_public(url)
        response = requests.get(url, **kwargs)
        if not response.is_redirect:
            return response
        url = urljoin(url, response.headers.get('Location', ''))
        response.close()
    raise NotPublic("too many redirects")
