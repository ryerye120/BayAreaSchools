# Bay Area School Atlas — ETL

Normalizes California Department of Education data into a clean dataset of
K–8-relevant schools across the nine Bay Area counties.

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python -m etl.run --fixture   # sanity-check the code path on synthetic data
python -m etl.run             # the real thing
```

Output lands in `data/processed/`:

| File | What it is |
|---|---|
| `schools.json` | Canonical dataset, one record per school |
| `schools.csv` | Same, for eyeballing in a spreadsheet |
| `_report.json` | Row counts at each funnel stage |
| `_summary.json` | Totals by county and level |

## Sources

| Key | Auto-download | Where |
|---|---|---|
| `pubschls` | yes | CDE Public Schools and Districts (tab-delimited) |
| `private` | **no** | CDE Private School Data — save as `data/raw/privateschools.xlsx` |
| `caaspp_sb` | **no** | CAASPP Smarter Balanced research files — unzip to `data/raw/sb_ca_all.csv` |

The two manual sources are session-generated or zipped behind a form. The
pipeline tells you exactly what's missing and where to get it rather than
silently producing a partial dataset.

Verify `SOURCES["pubschls"]["url"]` against
<https://www.cde.ca.gov/ds/si/ds/pubschls.asp> before a production run — CDE
changes report ids occasionally.

## Design notes

**CDS code is the join key.** 14 digits: 2 county + 5 district + 7 school. A
code ending in `0000000` is a district record, not a school, and gets dropped.

**`GSserved` beats `GSoffered`.** `GSoffered` is self-reported by the district;
`GSserved` comes from certified CALPADS Fall 1 enrollment. We prefer served and
fall back to offered, recording which was used in `grade_source`. If more than
25% of records fall back, validation warns — that's a data-quality signal worth
surfacing in the UI.

**Nothing is silently dropped.** Schools outside a family's realistic choice set
(juvenile court, community day, adult ed, continuation) stay in the dataset with
`is_selectable = false`. Counts stay auditable and you can always widen the
filter later without re-running everything.

**County filtering is belt-and-braces.** We match on both the CDS county code
and the county name, and print any row where the two disagree.

## Level classification

Follows California convention, where 6th grade often sits in elementary:

| Span | Level |
|---|---|
| K–5, K–6, 1–6, P–6, 3–5 | `elementary` |
| 5–8, 6–8, 7–8, 4–8 | `middle` |
| K–8, TK–8, 2–8 | `k8` |
| K–12, TK–12 | `k12` |
| 6–12, 8–12 | `middle_high` |
| 9–12 | `high` (excluded by the K–8 filter) |

## Caveats to carry into the product

CDE states plainly that directory data is voluntarily self-reported by local
education agencies and may be outdated or contain errors and omissions. Treat
grade spans, websites, and principal names as hints, not truth. Link out to the
school's own site everywhere.

## Automation

`.github/workflows/refresh-data.yml` runs the pipeline on the 3rd of each month
and on manual dispatch. GitHub's runners have unrestricted network access, so
the whole thing is hands-off:

1. **Discover** current download URLs by parsing each source's index page
2. **Extract** with checksums, so we know what actually changed
3. **Transform → Validate → Diff**
4. **Open a PR** with a human-readable changelog if the dataset moved
5. **Open an issue** (or comment on the existing one) if anything failed

You review a PR that says "3 schools added, 1 removed, 4 grade spans changed"
instead of an opaque 2MB diff. Merge it and the site rebuilds.

Nothing is auto-merged on purpose: a sudden 200-school swing almost always means
a source format change, not 200 real closures.
