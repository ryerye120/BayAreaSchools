"""Transform: normalize the CDE public schools file into our canonical schema."""

from __future__ import annotations

import json
import re
import unicodedata

import pandas as pd

from .config import (
    BAY_AREA_COUNTIES,
    EIL_KEEP,
    GRADE_ORD,
    PROCESSED,
    RAW,
    SOC_NON_SELECTABLE,
    SOC_SELECTABLE,
    TARGET_HIGH,
    TARGET_LOW,
)

# CDE exports are Windows-encoded, not UTF-8. Try in order.
ENCODINGS = ("utf-8-sig", "cp1252", "latin-1")

# Grade spans arrive as "K-5", "K–8" (en dash), "TK-8", "P-Adult", "7-8",
# "Ungraded", "No Data", and occasionally a single grade like "K".
DASHES = "\u2010\u2011\u2012\u2013\u2014\u2015-"
_DASH_RE = re.compile(f"[{DASHES}]")


# Columns we expect from the CDE file structure doc. The live file drifts from
# the documentation, so we look these up case-insensitively and substitute an
# empty column when one is absent -- and say so loudly.
EXPECTED = [
    "CDSCode", "NCESDist", "NCESSchool", "StatusType", "County", "District",
    "School", "Street", "City", "Zip", "Phone", "Website", "Charter", "DOC",
    "SOC", "SOCType", "EILCode", "GSoffered", "GSserved", "Virtual", "Magnet",
    "YearRound", "Latitude", "Longitude", "AdmFName", "AdmLName", "LastUpDate",
    "Multilingual",
]

# Alternate spellings seen in the wild, checked before giving up on a column.
ALIASES = {
    "Website": ["WebSite", "Web Site", "URL", "WebAddress"],
    "LastUpDate": ["LastUpdate", "LastUpdated"],
    "YearRound": ["YearRoundYN"],
    "AdmFName": ["AdmFName1"],
    "AdmLName": ["AdmLName1"],
}


def col(df: pd.DataFrame, name: str) -> pd.Series:
    """Fetch a column case-insensitively, or an empty column if it's gone."""
    lookup = {c.strip().lower(): c for c in df.columns}
    for candidate in [name] + ALIASES.get(name, []):
        actual = lookup.get(candidate.strip().lower())
        if actual is not None:
            return df[actual].astype(str).str.strip()
    return pd.Series([""] * len(df), index=df.index, dtype="object")


def report_schema(df: pd.DataFrame) -> None:
    lookup = {c.strip().lower() for c in df.columns}
    missing = []
    for name in EXPECTED:
        names = [name] + ALIASES.get(name, [])
        if not any(n.strip().lower() in lookup for n in names):
            missing.append(name)
    print(f"  columns in file: {len(df.columns)}")
    if missing:
        print(f"  !! expected but ABSENT: {', '.join(missing)}")
        print("     (substituting empty values; check the CDE changes page)")
    extra = [c for c in df.columns
             if c.strip().lower() not in
             {n.strip().lower() for e in EXPECTED for n in [e] + ALIASES.get(e, [])}]
    if extra:
        print(f"  ~  present but unused: {', '.join(extra[:15])}")
    print(f"  actual header: {list(df.columns)}")


def read_pubschls() -> pd.DataFrame:
    path = RAW / "pubschls.txt"
    last_err = None
    for enc in ENCODINGS:
        try:
            return pd.read_csv(
                path, sep="\t", dtype=str, encoding=enc, keep_default_na=False,
                on_bad_lines="warn",
            )
        except (UnicodeDecodeError, LookupError) as exc:
            last_err = exc
    raise RuntimeError(f"Could not decode {path}: {last_err}")


def parse_grade(token: str):
    """Map a single grade token to an ordinal, or None if unparseable."""
    t = token.strip().upper().replace(".", "")
    if not t:
        return None
    if t in GRADE_ORD:
        return GRADE_ORD[t]
    if t.startswith("ADULT"):
        return 99
    t = t.lstrip("0") or "0"
    return GRADE_ORD.get(t)


def parse_span(raw: str):
    """Parse a grade span string into (low_ord, high_ord).

    Returns (None, None) when the span is missing or ungraded.
    """
    if not raw:
        return (None, None)
    s = unicodedata.normalize("NFKC", str(raw)).strip().upper()
    if s in {"", "NO DATA", "N/A", "NA", "UNGRADED", "UG"}:
        return (None, None)

    parts = [p for p in _DASH_RE.split(s) if p.strip()]
    if len(parts) == 1:
        g = parse_grade(parts[0])
        return (g, g)
    lo, hi = parse_grade(parts[0]), parse_grade(parts[-1])
    if lo is not None and hi is not None and lo > hi:
        lo, hi = hi, lo
    return (lo, hi)


def overlaps_k8(lo, hi) -> bool:
    """True if [lo, hi] intersects the K-8 window."""
    if lo is None or hi is None:
        return False
    return lo <= TARGET_HIGH and hi >= TARGET_LOW


def classify(lo, hi) -> str:
    """Bucket a school for filtering in the UI.

    Boundaries follow California convention: 6th grade sits in elementary at
    many districts, so K-6 and 1-6 are elementary, not K-8. A K-8 must reach
    at least 7th grade.
    """
    if lo is None or hi is None:
        return "unknown"
    if lo >= 9:
        return "high"
    if lo <= 5 and hi <= 6:
        return "elementary"
    if lo >= 3 and 7 <= hi <= 8:
        return "middle"
    if lo >= 5 and hi <= 8:
        return "middle"
    if lo <= 2 and 7 <= hi <= 8:
        return "k8"
    if lo <= 2 and hi >= 9:
        return "k12"
    if lo >= 3 and hi >= 9:
        return "middle_high"
    return "other"


def slugify(name: str, city: str) -> str:
    base = f"{name} {city}".lower()
    base = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    return re.sub(r"-+", "-", base)


def run() -> pd.DataFrame:
    df = read_pubschls()
    report_schema(df)
    report = {"raw_rows": len(df)}

    # --- drop district / county-office records -----------------------------
    df = df[~col(df, "CDSCode").str.endswith("0000000")]
    report["school_records"] = len(df)

    # --- active only -------------------------------------------------------
    df = df[col(df, "StatusType").isin(["Active", "Pending"])]
    report["active_or_pending"] = len(df)

    # --- Bay Area ----------------------------------------------------------
    df["county_code"] = col(df, "CDSCode").str[:2]
    by_code = df["county_code"].isin(BAY_AREA_COUNTIES)
    by_name = col(df, "County").isin(BAY_AREA_COUNTIES.values())

    mismatch = df[by_code != by_name]
    if len(mismatch):
        print(f"  !! {len(mismatch)} rows where county code and name disagree:")
        print(mismatch[["CDSCode", "County", "School"]].head(10).to_string(index=False))

    df = df[by_code | by_name]
    report["bay_area"] = len(df)

    # --- grade spans -------------------------------------------------------
    served = col(df, "GSserved").apply(parse_span)
    offered = col(df, "GSoffered").apply(parse_span)
    df["served_low"] = [s[0] for s in served]
    df["served_high"] = [s[1] for s in served]
    df["offered_low"] = [o[0] for o in offered]
    df["offered_high"] = [o[1] for o in offered]

    # Prefer CALPADS-certified GSserved; fall back to self-reported GSoffered.
    df["grade_low"] = df["served_low"].fillna(df["offered_low"])
    df["grade_high"] = df["served_high"].fillna(df["offered_high"])
    df["grade_source"] = df["served_low"].notna().map(
        {True: "GSserved", False: "GSoffered"}
    )

    # --- K-8 filter --------------------------------------------------------
    keeps_eil = col(df, "EILCode").str.upper().isin(EIL_KEEP)
    keeps_grades = [overlaps_k8(lo, hi) for lo, hi in zip(df["grade_low"], df["grade_high"])]
    df = df[keeps_eil | pd.Series(keeps_grades, index=df.index)]
    df = df[pd.Series([overlaps_k8(lo, hi) for lo, hi in
                       zip(df["grade_low"], df["grade_high"])], index=df.index)]
    report["k8_overlap"] = len(df)

    # --- selectability -----------------------------------------------------
    soc = col(df, "SOC").str.zfill(2)
    df["is_selectable"] = soc.isin(SOC_SELECTABLE)
    df["school_type_label"] = soc.map({**SOC_SELECTABLE, **SOC_NON_SELECTABLE}).fillna(
        col(df, "SOCType")
    )
    report["selectable"] = int(df["is_selectable"].sum())

    # --- shape the output --------------------------------------------------
    out = pd.DataFrame({
        "cds_code": col(df, "CDSCode"),
        "nces_id": col(df, "NCESDist") + col(df, "NCESSchool"),
        "name": col(df, "School"),
        "district": col(df, "District"),
        "county": col(df, "County"),
        "county_code": df["county_code"],
        "street": col(df, "Street"),
        "city": col(df, "City"),
        "zip": col(df, "Zip"),
        "phone": col(df, "Phone"),
        "website": col(df, "Website"),
        "latitude": pd.to_numeric(col(df, "Latitude"), errors="coerce"),
        "longitude": pd.to_numeric(col(df, "Longitude"), errors="coerce"),
        "grade_low": df["grade_low"],
        "grade_high": df["grade_high"],
        "grade_span_raw": col(df, "GSserved").where(
            col(df, "GSserved") != "", col(df, "GSoffered")),
        "grade_source": df["grade_source"],
        "level": [classify(lo, hi) for lo, hi in zip(df["grade_low"], df["grade_high"])],
        "is_charter": col(df, "Charter").str.upper().eq("Y"),
        "is_magnet": col(df, "Magnet").str.upper().eq("Y"),
        "is_multilingual": col(df, "Multilingual").str.upper().eq("Y"),
        "is_year_round": col(df, "YearRound").str.upper().eq("Y"),
        "virtual_code": col(df, "Virtual"),
        # F = exclusively virtual, V = primarily virtual. These have no
        # meaningful physical location for a family choosing a school.
        "is_virtual": col(df, "Virtual").str.upper().isin(["F", "V"]),
        "school_type_label": df["school_type_label"],
        "is_selectable": df["is_selectable"],
        "sector": "public",
        "status": col(df, "StatusType"),
        "principal": (col(df, "AdmFName") + " " + col(df, "AdmLName")).str.strip(),
        "last_updated": col(df, "LastUpDate"),
    })

    out["slug"] = [slugify(n, c) for n, c in zip(out["name"], out["city"])]
    dupes = out["slug"].duplicated(keep=False)
    if dupes.any():
        out.loc[dupes, "slug"] = out.loc[dupes, "slug"] + "-" + out.loc[dupes, "cds_code"].str[-7:]

    out = out.sort_values(["county", "district", "name"]).reset_index(drop=True)

    PROCESSED.mkdir(parents=True, exist_ok=True)
    out.to_json(PROCESSED / "schools.json", orient="records", indent=2)
    out.to_csv(PROCESSED / "schools.csv", index=False)
    (PROCESSED / "_report.json").write_text(json.dumps(report, indent=2))

    print("\n  Funnel:")
    for k, v in report.items():
        print(f"    {k:<20} {v:>7,}")

    return out


if __name__ == "__main__":
    run()
