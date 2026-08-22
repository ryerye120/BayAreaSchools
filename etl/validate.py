"""Validate: assert the processed dataset is sane before it reaches the app.

Every check either passes, warns (data quality note worth surfacing in the UI),
or fails (pipeline bug -- do not ship).
"""

from __future__ import annotations

import json
import sys

import pandas as pd

from .config import BAY_AREA_COUNTIES, BBOX, PROCESSED

FAILURES: list[str] = []
WARNINGS: list[str] = []


def check(cond: bool, msg: str, fatal: bool = True) -> None:
    if cond:
        return
    (FAILURES if fatal else WARNINGS).append(msg)


def run() -> bool:
    df = pd.read_json(PROCESSED / "schools.json")

    # --- structural --------------------------------------------------------
    check(len(df) > 0, "dataset is empty")
    check(df["cds_code"].is_unique, "duplicate CDS codes present")
    check(df["slug"].is_unique, "duplicate slugs -- URL collisions")
    check(df["name"].str.strip().ne("").all(), "some schools have no name")

    # --- geography ---------------------------------------------------------
    missing_geo = df["latitude"].isna() | df["longitude"].isna()
    check(
        missing_geo.sum() < len(df) * 0.05,
        f"{missing_geo.sum()} schools missing coordinates (>5%)",
        fatal=False,
    )

    geo = df[~missing_geo]
    out_of_box = geo[
        (geo["latitude"] < BBOX["lat_min"]) | (geo["latitude"] > BBOX["lat_max"])
        | (geo["longitude"] < BBOX["lon_min"]) | (geo["longitude"] > BBOX["lon_max"])
    ]
    check(len(out_of_box) == 0, f"{len(out_of_box)} schools outside the Bay Area bbox")
    if len(out_of_box):
        print("\n  Out-of-bounds schools:")
        print(out_of_box[["name", "city", "latitude", "longitude"]].head(20).to_string(index=False))

    check(
        set(df["county"].unique()).issubset(set(BAY_AREA_COUNTIES.values())),
        f"unexpected counties: {set(df['county'].unique()) - set(BAY_AREA_COUNTIES.values())}",
    )

    # --- grades ------------------------------------------------------------
    check((df["grade_low"] <= df["grade_high"]).all(), "grade_low > grade_high somewhere")
    check(df["level"].ne("unknown").all(), 
          f"{df['level'].eq('unknown').sum()} schools with unclassifiable grade span",
          fatal=False)

    fallback = df["grade_source"].eq("GSoffered").sum()
    check(
        fallback < len(df) * 0.25,
        f"{fallback} schools ({fallback/len(df):.0%}) fall back to self-reported GSoffered",
        fatal=False,
    )

    # --- coverage sanity ---------------------------------------------------
    # San Francisco should land in a plausible range. If it doesn't, the filter
    # is wrong somewhere.
    sf = df[df["county"] == "San Francisco"]
    check(60 <= len(sf) <= 200, f"San Francisco count implausible: {len(sf)}", fatal=False)

    for county in BAY_AREA_COUNTIES.values():
        n = (df["county"] == county).sum()
        check(n > 0, f"no schools found in {county}", fatal=False)

    # --- report ------------------------------------------------------------
    print("\n" + "=" * 60)
    if WARNINGS:
        print("WARNINGS")
        for w in WARNINGS:
            print(f"  ~ {w}")
    if FAILURES:
        print("FAILURES")
        for f in FAILURES:
            print(f"  X {f}")
    if not WARNINGS and not FAILURES:
        print("All checks passed.")
    print("=" * 60)

    return not FAILURES


def summarize() -> None:
    """Print the counts you actually want to see."""
    df = pd.read_json(PROCESSED / "schools.json")

    print(f"\nTOTAL K-8-relevant public schools, 9 Bay Area counties: {len(df):,}")
    print(f"  of which family-selectable: {df['is_selectable'].sum():,}\n")

    pivot = pd.crosstab(df["county"], df["level"], margins=True, margins_name="TOTAL")
    print(pivot.to_string())

    print("\nBy sector flag:")
    print(f"  charter:      {df['is_charter'].sum():,}")
    print(f"  magnet:       {df['is_magnet'].sum():,}")
    print(f"  multilingual: {df['is_multilingual'].sum():,}")

    print("\nLargest districts by school count:")
    print(df["district"].value_counts().head(15).to_string())

    (PROCESSED / "_summary.json").write_text(json.dumps({
        "total": int(len(df)),
        "selectable": int(df["is_selectable"].sum()),
        "by_county": df["county"].value_counts().to_dict(),
        "by_level": df["level"].value_counts().to_dict(),
    }, indent=2))


if __name__ == "__main__":
    ok = run()
    summarize()
    sys.exit(0 if ok else 1)
