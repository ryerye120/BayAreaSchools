"""Extract: resolve and fetch raw source files into data/raw/.

URLs are discovered from each source's index page (see discover.py) so the
pipeline survives CDE renaming things. Checksums let downstream steps and CI
know whether anything actually changed.
"""

from __future__ import annotations

import hashlib
import json
import sys
import urllib.request
from datetime import datetime, timezone

from .config import RAW, SOURCES
from .discover import USER_AGENT, resolve

MANIFEST = RAW / "_manifest.json"


def _download(url: str, dest) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    # CDE generates this file live; it can take 20+ seconds to start.
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = resp.read()
    dest.write_bytes(data)
    return data


def _load_manifest() -> dict:
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text())
    return {}


def run(force: bool = False) -> dict:
    RAW.mkdir(parents=True, exist_ok=True)
    old = _load_manifest()
    new: dict = {"fetched_at": datetime.now(timezone.utc).isoformat(), "sources": {}}
    changed: list[str] = []

    for key, src in SOURCES.items():
        dest = RAW / src["filename"]
        url, how = resolve(key)

        if url is None:
            print(f"  [MISS]  {key:<12} no URL resolved")
            print(f"          {src['note']}")
            print(f"          Check by hand: {src['url']}")
            new["sources"][key] = {"ok": False, "reason": "unresolved"}
            continue

        if dest.exists() and not force:
            digest = hashlib.sha256(dest.read_bytes()).hexdigest()
            print(f"  [cache] {key:<12} {dest.stat().st_size:,} bytes")
            new["sources"][key] = {"ok": True, "url": url, "how": how,
                                   "sha256": digest, "bytes": dest.stat().st_size}
            continue

        try:
            data = _download(url, dest)
            digest = hashlib.sha256(data).hexdigest()
            prev = old.get("sources", {}).get(key, {}).get("sha256")
            did_change = prev is not None and prev != digest
            if did_change:
                changed.append(key)

            flag = "CHANGED" if did_change else "same" if prev else "new"
            print(f"  [ok]    {key:<12} {len(data):,} bytes  [{how}] [{flag}]")
            new["sources"][key] = {"ok": True, "url": url, "how": how,
                                   "sha256": digest, "bytes": len(data),
                                   "changed": did_change}
        except Exception as exc:  # noqa: BLE001
            print(f"  [FAIL]  {key:<12} {exc}")
            print(f"          URL was: {url}")
            new["sources"][key] = {"ok": False, "reason": str(exc), "url": url}

    new["changed"] = changed
    MANIFEST.write_text(json.dumps(new, indent=2))
    return new


if __name__ == "__main__":
    result = run(force="--force" in sys.argv)
    if not result["sources"].get("pubschls", {}).get("ok"):
        sys.exit("\nFATAL: the public schools file is required.")
