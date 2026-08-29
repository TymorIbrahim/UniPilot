#!/usr/bin/env python3
"""Download missing Technion semester offerings into `data/raw/technion/`.

    python scripts/fetch_cheesefork_archive.py --from 2017 --to 2026        # dry run
    python scripts/fetch_cheesefork_archive.py --from 2022 --to 2022 --apply

Writes nothing without `--apply`, and never overwrites a file that is already
there -- the existing exports are the reference copies and a re-fetch that
silently replaced them would be untraceable.

See `app/sources/cheesefork_archive.py` for why the older archive needs a
course-number conversion, and for what is deliberately NOT fetched.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.sources.cheesefork_archive import (  # noqa: E402
    ArchiveTerm,
    normalise_records,
    parse_archive_payload,
)

TARGET_DIR = Path(__file__).resolve().parents[1] / "data" / "raw" / "technion"
TERMS = (200, 201, 202)


def fetch_term(client: httpx.Client, term: ArchiveTerm) -> list[dict] | None:
    """First host that answers with parseable courses wins."""
    for url in term.urls():
        try:
            response = client.get(url, timeout=60.0)
        except httpx.HTTPError as exc:
            print(f"    {url} -> {type(exc).__name__}")
            continue
        if response.status_code != 200:
            continue
        try:
            records = normalise_records(parse_archive_payload(response.text))
        except (ValueError, KeyError) as exc:
            # A 200 that does not parse is worth seeing: the hosts return an
            # HTML 404 page with a 200 in some paths.
            print(f"    {url} -> unparseable ({type(exc).__name__})")
            continue
        if records:
            print(f"    {url} -> {len(records)} courses")
            return records
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from", dest="start", type=int, required=True)
    parser.add_argument("--to", dest="end", type=int, required=True)
    parser.add_argument("--apply", action="store_true", help="write the files")
    args = parser.parse_args()

    if not TARGET_DIR.is_dir():
        print(f"target directory missing: {TARGET_DIR}", file=sys.stderr)
        return 2

    wanted = [
        ArchiveTerm(year, term)
        for year in range(args.start, args.end + 1)
        for term in TERMS
    ]
    present = {path.name for path in TARGET_DIR.glob("courses_*.json")}
    missing = [term for term in wanted if term.filename not in present]

    print(f"terms requested : {len(wanted)}")
    print(f"already on disk : {len(wanted) - len(missing)}")
    print(f"to fetch        : {len(missing)}")
    if not args.apply:
        print("\nDRY RUN -- pass --apply to write. Would fetch:")
        for term in missing:
            print(f"  {term.filename}  ({term.semester_code})")
        return 0

    written = skipped = 0
    with httpx.Client(follow_redirects=True) as client:
        for term in missing:
            print(f"  {term.filename} ({term.semester_code})")
            records = fetch_term(client, term)
            if not records:
                skipped += 1
                print("    no archive for this term")
                continue
            destination = TARGET_DIR / term.filename
            destination.write_text(
                json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8"
            )
            written += 1

    print(f"\nwritten: {written}   unavailable: {skipped}")
    print("Remember to add new files to data/raw/technion/manifest.json.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
