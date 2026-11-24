"""Which web services are reachable: fail fast when one is down, and say so in plain words.

A service (host) that times out, refuses the connection or answers with a server error (5xx) is
marked *down* for a few minutes; later requests to it are skipped at once instead of each waiting
for a timeout. Reports say "X was not available, so this check did not run" instead of HTTP codes.
"""

from __future__ import annotations

import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

DOWN_FOR = 300.0        # seconds a failed host is skipped (the app is long-running; services come back)
PROBE_TIMEOUT = 5.0     # seconds for the quick "is it up?" check

_down: dict[str, float] = {}
_lock = threading.Lock()

SERVICES = {
    "oops.linkeddata.es": "The OOPS! web service (oops.linkeddata.es)",
    "www.ebi.ac.uk": "The EBI Ontology Lookup Service (OLS)",
    "data.bioontology.org": "BioPortal",
    "huggingface.co": "Hugging Face (model downloads)",
}
_TOOL_SERVICE = {
    "OOPS!": "The OOPS! web service (oops.linkeddata.es)",
    "Cross-domain interoperability": "A reference repository it needs (OLS / BioPortal)",
    "Scientific interoperability": "A reference repository it needs (OLS / BioPortal)",
    "IRI checks": "A term repository it needs (OLS / BioPortal)",
    "OntoCheck": "A web service it needs",
}

# what an error looks like when the other side is simply not there (not a problem with the ontology)
_UNAVAILABLE = re.compile(
    r"HTTP( Error)? ?5\d\d|\b50[0-4]\b|Service Unavailable|Bad Gateway|Gateway Time-?out|Internal Server Error"
    r"|timed? ?out|Timeout|urlopen error|URLError|ConnectionError|Connection (refused|reset|aborted)"
    r"|ConnectTimeout|ReadTimeout|Max retries exceeded|RemoteDisconnected|Name or service not known"
    r"|nodename nor servname|Temporary failure in name resolution|getaddrinfo|Network is unreachable"
    r"|No route to host|Too Many Requests|HTTP( Error)? ?429|host unreachable earlier",
    re.IGNORECASE)


def host(url: str) -> str:
    return urllib.parse.urlsplit(url).netloc.lower()


def is_down(url: str) -> bool:
    h = host(url)
    with _lock:
        t = _down.get(h)
        if t is not None and time.time() - t > DOWN_FOR:
            del _down[h]
            return False
        return t is not None


def mark_down(url: str) -> None:
    with _lock:
        _down[host(url)] = time.time()


def down_hosts() -> set[str]:
    with _lock:
        now = time.time()
        return {h for h, t in _down.items() if now - t <= DOWN_FOR}


def reset() -> None:
    with _lock:
        _down.clear()


def is_unavailable(error: object) -> bool:
    """The error means the service was not reachable or not working (timeout, connection, 5xx)."""
    if isinstance(error, urllib.error.HTTPError):
        return error.code >= 500 or error.code == 429
    if isinstance(error, (urllib.error.URLError, TimeoutError, ConnectionError)):
        return True
    return bool(error) and bool(_UNAVAILABLE.search(str(error) if not isinstance(error, BaseException)
                                                   else f"{type(error).__name__}: {error}"))


def service_name(url_or_host: str) -> str:
    h = host(url_or_host) if "//" in url_or_host else url_or_host.lower()
    return SERVICES.get(h, h or "A web service")


def not_available(url_or_host: str) -> str:
    return f"{service_name(url_or_host)} was not available, so this check did not run."


def probe(url: str, timeout: float = PROBE_TIMEOUT) -> bool:
    """A quick check that ``url``'s host answers at all (any response below 500 counts); a host that
    does not answer within ``timeout`` seconds is marked down."""
    if is_down(url):
        return False
    parts = urllib.parse.urlsplit(url)
    root = f"{parts.scheme}://{parts.netloc}/"
    try:
        req = urllib.request.Request(root, method="HEAD", headers={"User-Agent": "ontoreview"})
        with urllib.request.urlopen(req, timeout=timeout):  # noqa: S310 - the service's own address
            return True
    except urllib.error.HTTPError as e:
        if e.code < 500:
            return True                 # it answered (405 for HEAD, 404 for /, …): it is up
        mark_down(url)
        return False
    except Exception:  # noqa: BLE001 - timeout, DNS, refused, TLS: not available
        mark_down(url)
        return False


def plain(tool: str, error: str | None) -> str | None:
    """A report's error in plain words: "X was not available, so this check did not run." when the
    error only means a service was down; any other error is returned unchanged."""
    if (not error or tool not in _TOOL_SERVICE or not is_unavailable(error)
            or error.endswith("so this check did not run.")):
        return error                    # ROBOT / the reasoner (Docker) and real errors keep their wording
    named = next((name for h, name in SERVICES.items() if h in error), None)
    who = named or _TOOL_SERVICE.get(tool, "A web service it needs")
    prefix = "Not computed: " if error.startswith("Not computed") else ""
    return f"{prefix}{who} was not available, so this check did not run."
