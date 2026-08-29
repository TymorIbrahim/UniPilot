#!/usr/bin/env python3
"""Load published Technion grade statistics into `course_grade_stats`.

    python scripts/fetch_technion_grade_stats.py --limit 40      # dry run
    python scripts/fetch_technion_grade_stats.py --apply

Reads one `index.json` per course from the technion-histograms `gh-pages`
branch -- the numbers printed under each histogram, not the images. See
`app/sources/technion_grade_stats.py` for which sitting is used and why.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

import httpx
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.sources.technion_grade_stats import index_url, parse_course_index  # noqa: E402

COLLECTION = "course_grade_stats"
REQUEST_DELAY_SECONDS = 0.05


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    settings = get_settings()
    database = AsyncIOMotorClient(settings.mongo_uri)[settings.mongo_db_name]

    numbers = sorted(
        {
            str(doc["courseNumber"])
            async for doc in database[settings.production_courses_collection].find(
                {"courseNumber": {"$exists": True}}, {"courseNumber": 1}
            )
        }
    )
    if args.limit:
        numbers = numbers[: args.limit]
    print(f"catalog courses to ask about: {len(numbers)}")

    found = []
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as http:
        for index, number in enumerate(numbers, start=1):
            try:
                response = await http.get(index_url(number))
            except httpx.HTTPError as exc:
                print(f"  {number}: {type(exc).__name__}")
                continue
            if response.status_code == 404:
                continue
            if response.status_code != 200:
                print(f"  {number}: HTTP {response.status_code}")
                continue
            try:
                stats = parse_course_index(response.json(), course_number=number)
            except ValueError:
                print(f"  {number}: unparseable index.json")
                continue
            if stats is not None:
                found.append(stats)
            if index % 200 == 0:
                print(f"  ...{index}/{len(numbers)} asked, {len(found)} with statistics")
            time.sleep(REQUEST_DELAY_SECONDS)

    print(f"\ncourses with published statistics: {len(found)}")
    if not args.apply:
        print("DRY RUN -- pass --apply to write. Sample:")
        for stats in found[:6]:
            print(f"  {stats.as_public_dict()}")
        return 0

    collection = database[COLLECTION]
    await collection.create_index("courseNumber", unique=True)
    for stats in found:
        await collection.update_one(
            {"courseNumber": stats.course_number},
            {"$set": stats.as_public_dict()},
            upsert=True,
        )
    print(f"written to `{COLLECTION}`: {len(found)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
