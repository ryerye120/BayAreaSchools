"""Configuration for the Bay Area school ETL pipeline."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"

# --------------------------------------------------------------------------
# Geography
# --------------------------------------------------------------------------
# The first two digits of a CDS code are the county code (alphabetical, 01-58).
# We filter on BOTH code and name so a wrong assumption fails loudly instead of
# silently dropping a county.
BAY_AREA_COUNTIES = {
    "01": "Alameda",
    "07": "Contra Costa",
    "21": "Marin",
    "28": "Napa",
    "38": "San Francisco",
    "41": "San Mateo",
    "43": "Santa Clara",
    "48": "Solano",
    "49": "Sonoma",
}

# Rough bounding box for the nine-county Bay Area, used in validation.
BBOX = {"lat_min": 36.85, "lat_max": 38.90, "lon_min": -123.60, "lon_max": -121.20}

# --------------------------------------------------------------------------
# Sources
# --------------------------------------------------------------------------
# VERIFY these against https://www.cde.ca.gov/ds/si/ds/pubschls.asp before a
# production run -- CDE occasionally changes report ids. The file is generated
# live, so it reflects real-time directory data.
SOURCES = {
    "pubschls": {
        "url": "https://www.cde.ca.gov/schooldirectory/report?rid=dl1&tp=txt",
        "filename": "pubschls.txt",
        "auto": True,
        "note": "CDE Public Schools and Districts, tab-delimited.",
    },
    # These are not reliably fetchable by URL (session-generated or zipped
    # behind a form). Download by hand into data/raw/ once a year.
    "private": {
        "url": "https://www.cde.ca.gov/ds/si/ps/",
        "filename": "privateschools.xlsx",
        "auto": False,
        "note": "CDE Private School Affidavit directory. Grab the current-year "
        "workbook from the Private School Data page.",
    },
    "caaspp_sb": {
        "url": "https://caaspp-elpac.ets.org/caaspp/ResearchFileListSB",
        "filename": "sb_ca_all.csv",
        "auto": False,
        "note": "Smarter Balanced research file. Pick the statewide 'All Student "
        "Groups' CSV for the most recent year, unzip into data/raw/.",
    },
}

# --------------------------------------------------------------------------
# Code mappings (from the CDE file structure doc)
# --------------------------------------------------------------------------

# School Ownership Codes we treat as mainstream, family-selectable schools.
SOC_SELECTABLE = {
    "60": "Elementary School (Public)",
    "61": "Elementary School in 1 School District (Public)",
    "62": "Intermediate/Middle School (Public)",
    "63": "Alternative School of Choice",
    "64": "Junior High School (Public)",
    "65": "K-12 School (Public)",
}

# Real schools, but not part of a normal family's choice set. Kept in the
# dataset with is_selectable=False so counts stay auditable.
SOC_NON_SELECTABLE = {
    "08": "Preschool",
    "09": "Special Education School (Public)",
    "10": "County Community",
    "11": "Youth Authority Facility",
    "13": "Opportunity School",
    "14": "Juvenile Court School",
    "15": "Other County or District Program",
    "31": "State Special School",
    "66": "High School (Public)",
    "67": "High School in 1 School District (Public)",
    "68": "Continuation High School",
    "69": "District Community Day School",
    "70": "Adult Education Center",
    "98": "Regional Occupational Center/Program",
}

# Educational Instruction Level codes that can plausibly contain K-8 grades.
EIL_KEEP = {"ELEM", "ELEMHIGH", "INTMIDJR", "PS", "UG"}

# Ordinal values for grade-span parsing. Preschool and TK sort below K so an
# ordinary K-5 school and a TK-5 school compare correctly.
GRADE_ORD = {
    "P": -2,
    "PS": -2,
    "PK": -2,
    "TK": -1,
    "K": 0,
    "N": 0,  # occasionally used for kindergarten in older records
    "ADULT": 99,
    "UG": None,
}
for _n in range(1, 13):
    GRADE_ORD[str(_n)] = _n
    GRADE_ORD[f"{_n:02d}"] = _n

# The K-8 window we care about, in ordinal terms.
TARGET_LOW, TARGET_HIGH = 0, 8
