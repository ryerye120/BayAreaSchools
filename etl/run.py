"""Run the full pipeline: extract -> transform -> validate -> summarize.

    python -m etl.run              # normal run, uses cached raw files
    python -m etl.run --force      # re-download sources
    python -m etl.run --fixture    # synthetic data, for testing the code path
"""

import sys

from . import diff, extract, private, transform, validate


def main() -> int:
    args = set(sys.argv[1:])

    if "--fixture" in args:
        from . import make_fixture
        print("== FIXTURE (synthetic data, not real) ==")
        make_fixture.main()
    else:
        print("== EXTRACT ==")
        present = extract.run(force="--force" in args)
        if not present.get("pubschls"):
            print("\nFATAL: public schools file unavailable.")
            return 2

    print("\n== TRANSFORM (public) ==")
    transform.run()

    print("\n== TRANSFORM (private) ==")
    private.run()

    print("\n== VALIDATE ==")
    ok = validate.run()
    validate.summarize()

    print("\n== DIFF ==")
    try:
        diff.run()
    except Exception as exc:
        print(f"  (skipped: {exc})")

    if not ok:
        print("\nValidation failed. Fix before building the site.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
