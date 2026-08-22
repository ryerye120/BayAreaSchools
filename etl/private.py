"""Transform the CDE Private School Affidavit (PSA) workbook.

Two things make this file different from the public one:

1. It has no addresses. Joining back to the School Directory (or NCES PSS) by
   CDS code is required before anything can be mapped.
2. Filing a PSA is not evidence of being a school. CDE says so explicitly --
   filers include homeschools and satellite programs. But an enrollment cutoff
   is the wrong filter: it deletes real micro-schools, 1:1 academies, and
   special-needs schools, which are exactly the options families search hardest
   for. We score shape instead and let the UI decide.
"""

from __future__ import annotations

import json
import re

import pandas as pd

from .config import BAY_AREA_COUNTIES, PROCESSED, RAW
from .transform import classify, slugify

SRC = RAW / "privateschools.xlsx"

GRADE_COLS = {
    "Grade K Enroll": 0,
    **{f"Grade {i} Enroll": i for i in range(1, 13)},
}
K8_COLS = [c for c, g in GRADE_COLS.items() if 0 <= g <= 8]


def find_header(path) -> int:
    """CDE prefixes the sheet with title/provenance rows; locate the real header."""
    probe = pd.read_excel(path, header=None, nrows=20)
    for i, row in probe.iterrows():
        cells = {str(v).strip() for v in row.tolist()}
        if "CDS Code" in cells and "School Name" in cells:
            return int(i)
    raise RuntimeError("Could not locate header row (no 'CDS Code' + 'School Name')")


def read() -> pd.DataFrame:
    hdr = find_header(SRC)
    df = pd.read_excel(SRC, header=hdr)
    df.columns = [str(c).strip() for c in df.columns]
    print(f"  header row: {hdr}, columns: {len(df.columns)}, rows: {len(df)}")
    return df


def num(df: pd.DataFrame, name: str) -> pd.Series:
    if name not in df.columns:
        return pd.Series(0, index=df.index, dtype=float)
    return pd.to_numeric(df[name], errors="coerce").fillna(0)


def score_shape(row) -> str:
    """Classify what kind of entity this is, without deleting anything.

    - homeschool_shaped: tiny, almost no staff, few grades in use
    - micro: small but properly staffed (1:1 academies, special-needs schools)
    - established: a conventional school
    """
    enroll, staff, grades = row["total_enrollment"], row["staff"], row["grades_used"]
    if enroll >= 50 or staff >= 8:
        return "established"
    if staff <= 2 and enroll <= 15:
        return "homeschool_shaped"
    if enroll < 50:
        return "micro"
    return "established"


def run() -> pd.DataFrame:
    if not SRC.exists():
        print(f"  [SKIP] {SRC} not present -- private schools omitted.")
        print("         Export from cde.ca.gov/ds/si/ps/ -> List of Private Schools")
        return pd.DataFrame()

    df = read()
    report = {"raw_rows": len(df)}

    # --- CDS codes: Excel strips leading zeros, so 273/2995 arrive 13 digits --
    df["cds_code"] = (
        df["CDS Code"].astype(str).str.strip()
        .str.replace(r"\.0$", "", regex=True)
        .str.zfill(14)
    )
    short = (df["cds_code"].str.len() != 14).sum()
    report["cds_padded"] = int((df["CDS Code"].astype(str).str.strip().str.len() < 14).sum())
    print(f"  zero-padded {report['cds_padded']} short CDS codes")
    if short:
        print(f"  !! {short} codes still not 14 digits after padding")

    # --- Bay Area, checking code against name -------------------------------
    df["county_code"] = df["cds_code"].str[:2]
    by_code = df["county_code"].isin(BAY_AREA_COUNTIES)
    stated = df["County"].astype(str).str.strip()
    expected = df["county_code"].map(BAY_AREA_COUNTIES)
    mismatch = df[by_code & (expected != stated)]
    if len(mismatch):
        print(f"  !! {len(mismatch)} row(s) where CDS county != stated county:")
        print(mismatch[["cds_code", "County", "School Name"]].to_string(index=False))

    df = df[by_code].copy()
    report["bay_area"] = len(df)

    # --- enrollment ---------------------------------------------------------
    for c in GRADE_COLS:
        df[c] = num(df, c)
    df["k8_enrollment"] = df[K8_COLS].sum(axis=1)
    df["total_enrollment"] = num(df, "Total Enrollment")
    df["grades_used"] = (df[list(GRADE_COLS)] > 0).sum(axis=1)

    # --- staffing -----------------------------------------------------------
    df["teachers_ft"] = num(df, "Full Time Teachers")
    df["teachers_pt"] = num(df, "Part Time Teachers")
    df["staff"] = df["teachers_ft"] + df["teachers_pt"]
    df["administrators"] = num(df, "Administrators")
    # Use numpy NaN, not pd.NA -- pandas can't round NAType.
    df["student_teacher_ratio"] = (
        df["total_enrollment"] / df["staff"].replace(0, float("nan"))
    ).round(1)

    # --- grade span, derived from actual enrollment, not a declared span -----
    present = df[list(GRADE_COLS)] > 0
    ordinals = pd.Series(GRADE_COLS)
    df["grade_low"] = present.apply(
        lambda r: ordinals[r.values].min() if r.any() else None, axis=1)
    df["grade_high"] = present.apply(
        lambda r: ordinals[r.values].max() if r.any() else None, axis=1)

    # --- keep anything serving a K-8 grade ----------------------------------
    df = df[df["k8_enrollment"] > 0].copy()
    report["k8_relevant"] = len(df)

    df["school_shape"] = df.apply(score_shape, axis=1)
    report["by_shape"] = df["school_shape"].value_counts().to_dict()

    out = pd.DataFrame({
        "cds_code": df["cds_code"],
        "name": df["School Name"].astype(str).str.strip(),
        "district": df["Public School District"].astype(str).str.strip(),
        "county": df["county_code"].map(BAY_AREA_COUNTIES),
        "county_code": df["county_code"],
        # No address in this export -- must be joined from the School Directory
        # or NCES PSS before these can appear on a map.
        "street": "", "city": "", "zip": "", "phone": "", "website": "",
        "latitude": pd.NA, "longitude": pd.NA,
        "grade_low": df["grade_low"],
        "grade_high": df["grade_high"],
        "grade_source": "PSA enrollment by grade",
        "level": [classify(lo, hi) for lo, hi in zip(df["grade_low"], df["grade_high"])],
        "total_enrollment": df["total_enrollment"].astype(int),
        "k8_enrollment": df["k8_enrollment"].astype(int),
        "teachers_ft": df["teachers_ft"].astype(int),
        "teachers_pt": df["teachers_pt"].astype(int),
        "student_teacher_ratio": df["student_teacher_ratio"],
        "grades_used": df["grades_used"].astype(int),
        "school_shape": df["school_shape"],
        "is_selectable": df["school_shape"] != "homeschool_shaped",
        "is_virtual": False,
        "sector": "private",
        "status": "Active",
    })

    out["grade_span_raw"] = [
        f"{'K' if lo == 0 else int(lo)}-{'K' if hi == 0 else int(hi)}"
        if pd.notna(lo) and pd.notna(hi) else ""
        for lo, hi in zip(out["grade_low"], out["grade_high"])
    ]
    out["slug"] = [slugify(n, c) for n, c in zip(out["name"], out["county"])]
    dupes = out["slug"].duplicated(keep=False)
    if dupes.any():
        out.loc[dupes, "slug"] = out.loc[dupes, "slug"] + "-" + out.loc[dupes, "cds_code"].str[-7:]

    out = out.sort_values(["county", "name"]).reset_index(drop=True)

    PROCESSED.mkdir(parents=True, exist_ok=True)
    out.to_json(PROCESSED / "private_schools.json", orient="records", indent=2)
    out.to_csv(PROCESSED / "private_schools.csv", index=False)
    (PROCESSED / "_private_report.json").write_text(json.dumps(report, indent=2, default=str))

    print("\n  Funnel:")
    for k, v in report.items():
        print(f"    {k:<18} {v}")
    return out


if __name__ == "__main__":
    run()
