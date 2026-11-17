"""Offline license lookup (replaces Widoco's Licensius web service)."""

from __future__ import annotations

_LICENSES = {
    "creativecommons.org/licenses/by/4.0": "CC BY 4.0",
    "creativecommons.org/licenses/by/3.0": "CC BY 3.0",
    "creativecommons.org/licenses/by-sa/4.0": "CC BY-SA 4.0",
    "creativecommons.org/licenses/by-sa/3.0": "CC BY-SA 3.0",
    "creativecommons.org/licenses/by-nc/4.0": "CC BY-NC 4.0",
    "creativecommons.org/licenses/by-nc-sa/4.0": "CC BY-NC-SA 4.0",
    "creativecommons.org/licenses/by-nd/4.0": "CC BY-ND 4.0",
    "creativecommons.org/licenses/by-nc-nd/4.0": "CC BY-NC-ND 4.0",
    "creativecommons.org/publicdomain/zero/1.0": "CC0 1.0 (Public Domain)",
    "creativecommons.org/publicdomain/mark/1.0": "Public Domain Mark 1.0",
    "opensource.org/licenses/mit": "MIT License",
    "opensource.org/license/mit": "MIT License",
    "opensource.org/licenses/apache-2.0": "Apache License 2.0",
    "www.apache.org/licenses/license-2.0": "Apache License 2.0",
    "opensource.org/licenses/bsd-3-clause": "BSD 3-Clause License",
    "opensource.org/licenses/bsd-2-clause": "BSD 2-Clause License",
    "www.gnu.org/licenses/gpl-3.0": "GNU GPL v3.0",
    "www.gnu.org/licenses/lgpl-3.0": "GNU LGPL v3.0",
    "www.w3.org/consortium/legal/2015/copyright-software-and-document": "W3C Software and Document License",
    "www.w3.org/copyright/software-license-2023": "W3C Software and Document License (2023)",
    "opendatacommons.org/licenses/by/1-0": "ODC Attribution 1.0",
    "opendatacommons.org/licenses/odbl/1-0": "ODC Open Database License 1.0",
    "opendatacommons.org/licenses/pddl/1-0": "ODC Public Domain Dedication 1.0",
}

_SPDX = {
    "cc-by-4.0": "CC BY 4.0",
    "cc-by-sa-4.0": "CC BY-SA 4.0",
    "cc0-1.0": "CC0 1.0 (Public Domain)",
    "mit": "MIT License",
    "apache-2.0": "Apache License 2.0",
    "bsd-3-clause": "BSD 3-Clause License",
    "gpl-3.0": "GNU GPL v3.0",
    "gpl-3.0-only": "GNU GPL v3.0",
}


def _norm(url: str) -> str:
    u = url.strip().lower()
    for pre in ("https://", "http://"):
        if u.startswith(pre):
            u = u[len(pre):]
    for suf in ("legalcode", ".html", ".txt", ".php"):
        if u.endswith(suf):
            u = u[: -len(suf)]
    u = u.rstrip("/#")
    if u.endswith("/deed.en"):
        u = u[: -len("/deed.en")]
    return u


def license_label(url: str | None) -> str | None:
    if not url:
        return None
    n = _norm(url)
    if n in _LICENSES:
        return _LICENSES[n]
    if "spdx.org/licenses/" in n:
        key = n.rsplit("/", 1)[-1]
        return _SPDX.get(key, key.upper())
    return _SPDX.get(n)
