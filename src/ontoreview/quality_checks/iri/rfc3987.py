"""IRI syntax per RFC 3987 §2.2 (absolute ``IRI`` production), with RFC 3986 IP literals.

Pure standard library. Validation is component by component so a failure names the part that
breaks the grammar. Beyond the grammar, :func:`check` adds checks that matter for RDF identifiers on
the web: ``http(s)`` IRIs need a host, credentials in the authority are flagged (deprecated by
RFC 3986 §3.2.1), and ports must be 0–65535.

ABNF (RFC 3987 §2.2, abridged)::

    IRI            = scheme ":" ihier-part [ "?" iquery ] [ "#" ifragment ]
    ihier-part     = "//" iauthority ipath-abempty / ipath-absolute / ipath-rootless / ipath-empty
    iauthority     = [ iuserinfo "@" ] ihost [ ":" port ]
    iuserinfo      = *( iunreserved / pct-encoded / sub-delims / ":" )
    ihost          = IP-literal / IPv4address / ireg-name
    ireg-name      = *( iunreserved / pct-encoded / sub-delims )
    ipath-abempty  = *( "/" isegment )
    ipath-absolute = "/" [ isegment-nz *( "/" isegment ) ]
    ipath-rootless = isegment-nz *( "/" isegment )
    ipchar         = iunreserved / pct-encoded / sub-delims / ":" / "@"
    iquery         = *( ipchar / iprivate / "/" / "?" )
    ifragment      = *( ipchar / "/" / "?" )
    iunreserved    = ALPHA / DIGIT / "-" / "." / "_" / "~" / ucschar
"""

from __future__ import annotations

import ipaddress
import re

# ucschar and iprivate code point ranges (RFC 3987 §2.2)
_UCS = (" -퟿豈-﷏ﷰ-￯"
        "\U00010000-\U0001FFFD\U00020000-\U0002FFFD\U00030000-\U0003FFFD\U00040000-\U0004FFFD"
        "\U00050000-\U0005FFFD\U00060000-\U0006FFFD\U00070000-\U0007FFFD\U00080000-\U0008FFFD"
        "\U00090000-\U0009FFFD\U000A0000-\U000AFFFD\U000B0000-\U000BFFFD\U000C0000-\U000CFFFD"
        "\U000D0000-\U000DFFFD\U000E1000-\U000EFFFD")
_PRIVATE = "-\U000F0000-\U000FFFFD\U00100000-\U0010FFFD"
_UNRESERVED = "A-Za-z0-9\\-._~" + _UCS
_SUB_DELIMS = "!$&'()*+,;="
_PCT = "%[0-9A-Fa-f]{2}"

_IUNRES_OR_PCT_OR_SUB = f"(?:[{_UNRESERVED}{re.escape(_SUB_DELIMS)}]|{_PCT})"
_IPCHAR = f"(?:[{_UNRESERVED}{re.escape(_SUB_DELIMS)}:@]|{_PCT})"

SCHEME = re.compile(r"[A-Za-z][A-Za-z0-9+.\-]*")
USERINFO = re.compile(f"(?:[{_UNRESERVED}{re.escape(_SUB_DELIMS)}:]|{_PCT})*")
REG_NAME = re.compile(f"{_IUNRES_OR_PCT_OR_SUB}*")
PORT = re.compile(r"[0-9]*")
IPVFUTURE = re.compile(r"v[0-9A-Fa-f]+\.[A-Za-z0-9\-._~!$&'()*+,;=:]+")
SEGMENT = re.compile(f"{_IPCHAR}*")
QUERY = re.compile(f"(?:{_IPCHAR}|[{_PRIVATE}/?])*")
FRAGMENT = re.compile(f"(?:{_IPCHAR}|[/?])*")
_BAD_PCT = re.compile(r"%(?![0-9A-Fa-f]{2})")


def _bad_char(text: str, pattern: re.Pattern) -> str:
    """The first character in ``text`` the component grammar does not allow (escapes are skipped)."""
    i = 0
    while i < len(text):
        if text[i] == "%":
            i += 3
            continue
        if not pattern.fullmatch(text[i]):
            ch = text[i]
            shown = repr(ch) if ch.isprintable() and not ch.isspace() else f"U+{ord(ch):04X}"
            where = text if len(text) <= 40 else text[:37] + "…"
            return f"{shown} at position {i + 1} of '{where}'"
        i += 1
    return ""


def _check_host(host: str) -> str | None:
    if host.startswith("["):
        if not host.endswith("]"):
            return "unclosed IP literal in host"
        inner = host[1:-1]
        if inner[:1] in ("v", "V"):
            return None if IPVFUTURE.fullmatch(inner) else "invalid IPvFuture literal"
        try:
            ipaddress.IPv6Address(inner)
        except ValueError:
            return "invalid IPv6 address in host"
        return None
    if not REG_NAME.fullmatch(host):
        return "character not allowed in host: " + _bad_char(host, REG_NAME)
    return None


def syntax_error(value: str) -> str | None:
    """None if ``value`` matches the RFC 3987 ``IRI`` production, else which part fails and why."""
    if not isinstance(value, str) or not value:
        return "empty or non-string IRI"
    m = _BAD_PCT.search(value)
    if m:
        return f"invalid percent escape at position {m.start() + 1}"
    if ":" not in value:
        return "missing scheme (not an absolute IRI)"
    scheme, rest = value.split(":", 1)
    if not SCHEME.fullmatch(scheme):
        return "invalid scheme (must start with a letter, then letters, digits, + - .)" if scheme else "empty scheme"
    rest, _, fragment = rest.partition("#") if "#" in rest else (rest, "", None)
    rest, _, query = rest.partition("?") if "?" in rest else (rest, "", None)
    if fragment is not None and not FRAGMENT.fullmatch(fragment):
        return "character not allowed in fragment: " + _bad_char(fragment, FRAGMENT)
    if query is not None and not QUERY.fullmatch(query):
        return "character not allowed in query: " + _bad_char(query, QUERY)
    if rest.startswith("//"):
        authority, slash, path = rest[2:].partition("/")
        path = slash + path
        userinfo, at, hostport = authority.rpartition("@")
        if at and not USERINFO.fullmatch(userinfo):
            return "character not allowed in user info: " + _bad_char(userinfo, USERINFO)
        host, port = hostport, None
        if hostport.startswith("["):
            close = hostport.find("]")
            if close == -1:
                return "unclosed IP literal in host"
            host, tail = hostport[: close + 1], hostport[close + 1:]
            if tail:
                if not tail.startswith(":"):
                    return "unexpected characters after IP literal"
                port = tail[1:]
        elif ":" in hostport:
            host, port = hostport.rsplit(":", 1)
        err = _check_host(host)
        if err:
            return err
        if port is not None and not PORT.fullmatch(port):
            return "port is not a number"
        segments = path.split("/")[1:] if path else []
    else:
        path = rest
        if path.startswith("/") or not path:
            segments = path.split("/")[1:] if path else []
        else:
            segments = path.split("/")
            if not segments[0]:
                return "empty first path segment"
    for seg in segments:
        if not SEGMENT.fullmatch(seg):
            return "character not allowed in path: " + _bad_char(seg, SEGMENT)
    return None


def check(value: str, http_only: bool = False) -> str | None:
    """RFC 3987 syntax plus web-identifier checks used for RDF terms."""
    err = syntax_error(value)
    if err:
        return err
    scheme, rest = value.split(":", 1)
    scheme = scheme.lower()
    if http_only and scheme not in ("http", "https"):
        return "HTTP(S) required for retrieval"
    if scheme in ("http", "https"):
        if not rest.startswith("//"):
            return "missing host"
        authority = rest[2:].split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
        userinfo, at, hostport = authority.rpartition("@")
        if at:
            return "credentials in the authority (deprecated, RFC 3986 §3.2.1)"
        host = hostport.rsplit(":", 1)[0] if not hostport.startswith("[") else hostport.split("]")[0] + "]"
        if not host:
            return "missing host"
        port = hostport[len(host) + 1:] if len(hostport) > len(host) else ""
        if port and int(port) > 65535:
            return "port out of range (0–65535)"
    return None


__all__ = ["check", "syntax_error"]
