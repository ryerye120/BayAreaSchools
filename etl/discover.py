"""Discover download URLs by parsing source index pages.

Hardcoded URLs rot. CDE changes report ids; CAASPP publishes a new research
file each year with a new name. Rather than pinning a URL and finding out it
broke six months later, we parse the page that lists the downloads and pick the
link that matches. The pinned URL stays as a fallback.
"""

from __future__ import annotations

import re
import urllib.parse
import urllib.request

USER_AGENT = "bay-school-atlas-etl/0.1 (+contact@example.com)"

# href pattern, link-text pattern. Both must match.
DISCOVERY = {
    "pubschls": {
        "index": "https://www.cde.ca.gov/ds/si/ds/pubschls.asp",
        "href_re": r"report\?rid=dl1&(?:amp;)?tp=txt",
        "text_re": r"public schools and districts",
        "fallback": "https://www.cde.ca.gov/schooldirectory/report?rid=dl1&tp=txt",
    },
    "private": {
        "index": "https://www.cde.ca.gov/ds/si/ps/",
        "href_re": r"\.(xlsx|xls)$",
        "text_re": r"private school",
        "fallback": None,
    },
    "caaspp_sb": {
        "index": "https://caaspp-elpac.ets.org/caaspp/ResearchFileListSB",
        "href_re": r"sb_ca\d{4}.*\.zip$",
        "text_re": r".*",
        "fallback": None,
    },
}

_LINK_RE = re.compile(
    r'<a\b[^>]*?href\s*=\s*["\']([^"\']+)["\'][^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")


def extract_links(html: str, base: str) -> list[tuple[str, str]]:
    """Return (absolute_url, visible_text) for every anchor in the page."""
    out = []
    for href, inner in _LINK_RE.findall(html):
        text = _TAG_RE.sub(" ", inner)
        text = re.sub(r"\s+", " ", text).strip()
        out.append((urllib.parse.urljoin(base, href.replace("&amp;", "&")), text))
    return out


def find(html: str, base: str, href_re: str, text_re: str) -> list[str]:
    """All links whose href and text both match."""
    hp = re.compile(href_re, re.IGNORECASE)
    tp = re.compile(text_re, re.IGNORECASE)
    return [
        url for url, text in extract_links(html, base)
        if hp.search(url) and tp.search(text)
    ]


def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read()
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def resolve(key: str) -> tuple[str | None, str]:
    """Return (url, how) where how is 'discovered', 'fallback', or 'failed'."""
    spec = DISCOVERY.get(key)
    if not spec:
        return (None, "failed")

    try:
        html = _fetch(spec["index"])
        matches = find(html, spec["index"], spec["href_re"], spec["text_re"])
        if matches:
            # Prefer the last match: CAASPP lists years ascending, and CDE
            # lists the newest private-school workbook lower on the page.
            return (matches[-1], "discovered")
        print(f"    ! no link matched on {spec['index']}")
    except Exception as exc:  # noqa: BLE001
        print(f"    ! could not read index page: {exc}")

    if spec["fallback"]:
        return (spec["fallback"], "fallback")
    return (None, "failed")


if __name__ == "__main__":
    for k in DISCOVERY:
        url, how = resolve(k)
        print(f"{k:<12} [{how}] {url}")
