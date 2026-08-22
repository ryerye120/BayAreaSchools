"""Generate a synthetic pubschls.txt for testing. NOT REAL DATA."""

import random
from pathlib import Path

from .config import BAY_AREA_COUNTIES, RAW

COLUMNS = [
    "CDSCode", "NCESDist", "NCESSchool", "StatusType", "County", "District", "School",
    "Street", "StreetAbr", "City", "Zip", "State", "MailStreet", "MailStrAbr",
    "MailCity", "MailZip", "MailState", "Phone", "PhoneExt", "FaxNumber", "Website",
    "OpenDate", "ClosedDate", "Charter", "CharterNum", "FundingType", "DOC", "DOCType",
    "SOC", "SOCType", "EdOpsCode", "EdOpsName", "EILCode", "EILName", "GSoffered",
    "GSserved", "Virtual", "Magnet", "YearRound", "FederalDFCDistrictID",
    "Latitude", "Longitude", "AdmFName", "AdmLName", "LastUpDate", "Multilingual",
]

SPANS = [
    ("K-5", "K-5", "60", "ELEM"), ("TK-5", "K-5", "60", "ELEM"),
    ("K-8", "K-8", "60", "ELEM"), ("6-8", "6-8", "62", "INTMIDJR"),
    ("7-8", "7-8", "64", "INTMIDJR"), ("K-12", "K-12", "65", "ELEMHIGH"),
    ("9-12", "9-12", "66", "HS"), ("K-6", "K-6", "60", "ELEM"),
    ("P-Adult", "K-12", "65", "ELEMHIGH"), ("K-5", "No Data", "60", "ELEM"),
    ("Ungraded", "No Data", "09", "UG"), ("P-K", "No Data", "08", "PS"),
    ("9-12", "9-12", "68", "HS"), ("5-8", "5-8", "62", "INTMIDJR"),
]

CITIES = {
    "01": ("Oakland", 37.80, -122.27), "07": ("Concord", 37.98, -122.03),
    "21": ("San Rafael", 37.97, -122.53), "28": ("Napa", 38.30, -122.29),
    "38": ("San Francisco", 37.76, -122.44), "41": ("San Mateo", 37.56, -122.32),
    "43": ("San Jose", 37.34, -121.89), "48": ("Vallejo", 38.10, -122.26),
    "49": ("Santa Rosa", 38.44, -122.71),
}


def main(n_per_county: int = 90) -> None:
    random.seed(42)
    rows = []
    for code, county in BAY_AREA_COUNTIES.items():
        city, lat0, lon0 = CITIES[code]
        # one district record, which should be filtered out
        rows.append(_row(f"{code}61119" + "0000000", county, f"{county} Unified",
                         "District Office", city, lat0, lon0, ("K-12", "K-12", "", "")))
        for i in range(n_per_county):
            span = random.choice(SPANS)
            cds = f"{code}{random.randint(10000,99999)}{i:07d}"
            rows.append(_row(cds, county, f"{county} Unified",
                             f"{random.choice(['Lincoln','Madison','Bayview','Glen Park','Marshall','Alvarado','Cesar Chavez','Rooftop'])} "
                             f"{random.choice(['Elementary','Middle','Academy','School'])} {i}",
                             city, lat0 + random.uniform(-.12,.12), lon0 + random.uniform(-.12,.12), span))
    # a couple of deliberate problems
    rows.append(_row("19647330000001", "Los Angeles", "LAUSD", "Wrong County Elem",
                     "Los Angeles", 34.05, -118.24, ("K-5","K-5","60","ELEM")))
    rows.append(_row("38684780000002", "San Francisco", "SFUSD", "Bad Geo Elem",
                     "San Francisco", 0.0, 0.0, ("K-5","K-5","60","ELEM")))

    RAW.mkdir(parents=True, exist_ok=True)
    out = Path(RAW / "pubschls.txt")
    with out.open("w", encoding="cp1252") as fh:
        fh.write("\t".join(COLUMNS) + "\n")
        for r in rows:
            fh.write("\t".join(r) + "\n")
    print(f"wrote {len(rows):,} synthetic rows -> {out}")


def _row(cds, county, district, school, city, lat, lon, span):
    offered, served, soc, eil = span
    d = dict.fromkeys(COLUMNS, "")
    d.update({
        "CDSCode": cds, "NCESDist": "0600001", "NCESSchool": "12345",
        "StatusType": "Active", "County": county, "District": district,
        "School": school, "Street": "1 Main St", "City": city, "Zip": "94110",
        "State": "CA", "Phone": "415-555-0100", "Website": "example.org",
        "Charter": random.choice(["Y","N","N","N"]), "DOC": "54",
        "SOC": soc, "SOCType": "", "EILCode": eil,
        "GSoffered": offered, "GSserved": served,
        "Magnet": random.choice(["Y","N","N"]), "YearRound": "N",
        "Latitude": f"{lat:.5f}", "Longitude": f"{lon:.5f}",
        "AdmFName": "Jane", "AdmLName": "Doe", "LastUpDate": "2026-08-01",
        "Multilingual": random.choice(["Y","N","N"]), "Virtual": "N",
    })
    return [d[c] for c in COLUMNS]


if __name__ == "__main__":
    main()
