"""Diff the newly built dataset against the committed one.

Turns "some bytes changed" into "3 schools closed, 1 opened, 2 changed grade
span" -- which is what you actually want in a PR description.
"""

from __future__ import annotations

import io
import json
import subprocess

import pandas as pd

from .config import PROCESSED

WATCHED = ["name", "district", "grade_low", "grade_high", "level",
           "is_charter", "latitude", "longitude", "website", "status"]


def _previous() -> pd.DataFrame | None:
    """Read schools.json as committed at HEAD. None if unavailable."""
    try:
        root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        rel = (PROCESSED / "schools.json").resolve().relative_to(root)
        blob = subprocess.run(
            ["git", "show", f"HEAD:{rel.as_posix()}"],
            capture_output=True, text=True, check=True,
        ).stdout
        if not blob.strip():
            return None
        return pd.read_json(io.StringIO(blob))
    except Exception:
        # Not a repo, no prior commit, or file not yet tracked -- all fine.
        return None


def run() -> str:
    new = pd.read_json(PROCESSED / "schools.json")
    old = _previous()

    if old is None or old.empty:
        msg = f"Initial dataset: {len(new):,} schools."
        (PROCESSED / "_changelog.md").write_text(msg + "\n")
        print(msg)
        return msg

    o = old.set_index("cds_code")
    n = new.set_index("cds_code")

    added = n.index.difference(o.index)
    removed = o.index.difference(n.index)
    common = n.index.intersection(o.index)

    edits: dict[str, int] = {}
    examples: list[str] = []
    for col in WATCHED:
        if col not in o.columns or col not in n.columns:
            continue
        diff = o.loc[common, col].astype(str) != n.loc[common, col].astype(str)
        if diff.any():
            edits[col] = int(diff.sum())
            for cds in list(common[diff])[:3]:
                examples.append(
                    f"  - {n.loc[cds, 'name']}: {col} "
                    f"{o.loc[cds, col]!r} -> {n.loc[cds, col]!r}"
                )

    lines = [
        f"**{len(new):,} schools** (was {len(old):,})",
        "",
        f"- added: {len(added)}",
        f"- removed: {len(removed)}",
        f"- modified fields: {sum(edits.values())} across {len(edits)} columns",
    ]
    if edits:
        lines.append("")
        for col, cnt in sorted(edits.items(), key=lambda kv: -kv[1]):
            lines.append(f"  - `{col}`: {cnt}")
    if examples:
        lines += ["", "<details><summary>Sample changes</summary>", ""] + examples[:15] + ["", "</details>"]
    if len(added):
        lines += ["", "New schools:"] + [f"  - {n.loc[c, 'name']} ({n.loc[c, 'county']})"
                                          for c in list(added)[:10]]
    if len(removed):
        lines += ["", "Dropped schools:"] + [f"  - {o.loc[c, 'name']} ({o.loc[c, 'county']})"
                                              for c in list(removed)[:10]]

    md = "\n".join(lines)
    (PROCESSED / "_changelog.md").write_text(md + "\n")
    (PROCESSED / "_changelog.json").write_text(json.dumps({
        "total": int(len(new)), "previous_total": int(len(old)),
        "added": int(len(added)), "removed": int(len(removed)), "edits": edits,
    }, indent=2))
    print(md)
    return md


if __name__ == "__main__":
    run()
