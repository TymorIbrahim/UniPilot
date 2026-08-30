#!/usr/bin/env python3
"""Build the DDS demo catalog the API seeds into the live demo on startup.

The gallery demo runs in kiosk mode: no volumes, nothing carried over between
visitors, and no access to the promoted production database. Whatever a visitor
sees has to be seeded from code every time the stack starts. Until now that was
a hand-written fixture of five courses, which made the Course Catalog page
effectively empty next to a poster advertising the real Technion catalog.

This script builds a real one instead, from two files already tracked in the
repo:

  * the reviewed DDS catalog export -- the same document the promotion pipeline
    turns into production `degree_programs` / `degree_requirements` /
    `catalog_rules`, so the demo's three DDS tracks carry their real credit
    buckets, semester matrices and course pools rather than invented ones
  * the raw Technion semester JSON, for course titles, credits and the weekly
    schedule the semester planner needs

Output is a single deterministic JSON fixture committed alongside the API, so
the demo image needs no extra build context and startup stays a bulk insert.

    python3 scripts/build_demo_seed.py

Re-run it when the DDS export or the raw semester files change.
"""

from __future__ import annotations

import importlib.util
import json
from collections import OrderedDict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DDS_EXPORT = (
    REPO_ROOT
    / "services/data-engineering/data/generated/technion/catalog/catalog_reviewed.json"
)
RAW_DIR = REPO_ROOT / "services/data-engineering/data/raw/technion"
OUTPUT = REPO_ROOT / "services/api/app/db/seed_data/dds_demo_catalog.json"

# The two semesters the demo offers. Winter first so a visitor opening the
# planner lands on a term that actually has offerings.
DEMO_SEMESTERS = ("courses_2025_200.json", "courses_2025_201.json")
SEMESTER_NAMES = {200: "winter", 201: "spring", 202: "summer"}

CATALOG_YEAR = 2025
CATALOG_VERSION = "2025-2026"
INSTITUTION = "technion"
DDS_FACULTY_MARKER = "מדעי הנתונים"

# Raw Technion JSON is keyed in Hebrew.
F_NUMBER = "מספר מקצוע"
F_TITLE = "שם מקצוע"
F_CREDITS = "נקודות"
F_FACULTY = "פקולטה"
F_SYLLABUS = "סילבוס"
F_PREREQ = "מקצועות קדם"
F_NO_CREDIT = "מקצועות ללא זיכוי נוסף"
F_INSTRUCTORS = "אחראים"
F_NOTES = "הערות"
F_EXAM_A = "מועד א"
F_EXAM_B = "מועד ב"

# A credit_bucket group is a real graduation requirement; everything else
# (semester matrices, course pools, track requirements) is advisory guidance
# that the progress calculator must not enforce.
HARD_RULE_TYPE = "credit_bucket"


def load_excluded_course_numbers() -> frozenset[str]:
    """The course numbers production purges, read from the API's own list.

    The promoter deletes these from production after every promotion, so the
    demo must not seed them either -- otherwise the fixture holds rows the real
    system would have removed, and the `ai` service (which reads `courses`
    directly, without the API's filter) would see courses no visitor can.
    """
    module_path = REPO_ROOT / "services/api/app/catalog/excluded_courses.py"
    spec = importlib.util.spec_from_file_location("excluded_courses", module_path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load excluded course list: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.PRODUCTION_EXCLUDED_COURSE_NUMBERS


def _float(value: Any) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def load_fallback_records() -> dict[str, dict]:
    """Course descriptions from every semester the repo has, oldest first.

    A track can name a course that simply isn't offered in either demo
    semester -- a course on hiatus, or one that only runs in summer. Without
    this, 15 of them landed in the fixture with `credits: null`, which the
    progress calculator would silently count as zero. Any semester's record
    carries the credit value, so the newest one that has the course wins.
    """
    records: dict[str, dict] = {}
    for path in sorted(RAW_DIR.glob("courses_*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for record in payload:
            general = record.get("general") or {}
            number = _clean(general.get(F_NUMBER))
            if number:
                records[number] = general
    return records


def load_raw_courses() -> tuple[dict[str, dict], list[dict]]:
    """Return (course_number -> best raw record, offering documents)."""
    courses: dict[str, dict] = {}
    offerings: list[dict] = []

    for filename in DEMO_SEMESTERS:
        path = RAW_DIR / filename
        if not path.is_file():
            raise SystemExit(f"missing raw semester file: {path}")
        year, code = int(filename.split("_")[1]), int(filename.split("_")[2].split(".")[0])
        for record in json.loads(path.read_text(encoding="utf-8")):
            general = record.get("general") or {}
            number = _clean(general.get(F_NUMBER))
            if not number:
                continue
            # Later semesters win: the newest description is the truest one.
            courses[number] = general
            schedule = record.get("schedule") or []
            exams = {
                key: value
                for key, value in (
                    ("moedA", _clean(general.get(F_EXAM_A))),
                    ("moedB", _clean(general.get(F_EXAM_B))),
                )
                if value
            }
            offerings.append(
                {
                    "productionKey": f"{INSTITUTION}:course-offering:{number}:{year}:{code}",
                    "institutionId": INSTITUTION,
                    "courseNumber": number,
                    "academicYear": year,
                    "semesterCode": code,
                    "semesterName": SEMESTER_NAMES.get(code, str(code)),
                    # Passed through exactly as Technion publishes them -- the
                    # API's schedule normalizer reads these Hebrew keys directly.
                    "scheduleGroups": schedule,
                    "examDates": exams,
                    "instructors": _clean(general.get(F_INSTRUCTORS)),
                    "sourceFile": filename,
                    "catalogYear": CATALOG_YEAR,
                    "catalogVersion": CATALOG_VERSION,
                    "status": "published",
                }
            )
    return courses, offerings


def collect_course_references(programs: list[dict]) -> dict[str, dict]:
    """Every distinct course the DDS tracks point at, with its catalogue hints."""
    references: dict[str, dict] = {}
    for program in programs:
        for group in program.get("requirementGroups") or []:
            for reference in group.get("courseReferences") or []:
                number = _clean(reference.get("courseNumber"))
                if number and number not in references:
                    references[number] = reference
    return references


def build_course_document(
    number: str,
    reference: dict | None,
    raw: dict | None,
) -> dict[str, Any]:
    """Prefer the raw semester record; fall back to the catalogue's hints."""
    reference = reference or {}
    raw = raw or {}

    title = _clean(raw.get(F_TITLE)) or _clean(reference.get("titleHint")) or number
    credits = _float(raw.get(F_CREDITS))
    if credits is None:
        credits = _float(reference.get("creditsHint"))
    faculty = _clean(raw.get(F_FACULTY)) or _clean(reference.get("facultyHint"))

    document: dict[str, Any] = {
        "productionKey": f"{INSTITUTION}:course:{number}",
        "institutionId": INSTITUTION,
        "courseNumber": number,
        "titleHebrew": title,
        "title": title,
        "credits": credits,
        "faculty": faculty,
        "catalogYear": CATALOG_YEAR,
        "catalogVersion": CATALOG_VERSION,
        "status": "published",
        "metadata": {"degreeRequirementsInferred": False},
    }

    for field, value in (
        ("syllabus", _clean(raw.get(F_SYLLABUS))),
        (
            "prerequisitesText",
            _clean(raw.get(F_PREREQ)) or _clean(reference.get("prerequisitesText")),
        ),
        (
            "noAdditionalCreditText",
            _clean(raw.get(F_NO_CREDIT)) or _clean(reference.get("noAdditionalCreditText")),
        ),
        ("notes", _clean(raw.get(F_NOTES))),
    ):
        if value:
            document[field] = value

    semesters = reference.get("semestersOffered")
    if semesters:
        document["semestersOffered"] = semesters
    return document


def credit_bucket_slugs(program: dict) -> set[str]:
    return {
        group["groupId"].split(":", 1)[1]
        for group in program.get("requirementGroups") or []
        if (group.get("ruleExpression") or {}).get("type") == HARD_RULE_TYPE
    }


def build_program_document(program: dict) -> dict[str, Any]:
    code = program["programCode"]
    return {
        "productionKey": f"{INSTITUTION}-dds:program:{code}:{CATALOG_VERSION}",
        "institutionId": INSTITUTION,
        "programCode": code,
        "name": program.get("name"),
        "nameEn": program.get("nameEn"),
        "totalCredits": program.get("totalCredits"),
        "catalogYear": CATALOG_YEAR,
        "catalogVersion": CATALOG_VERSION,
        "status": "published",
        "paths": program.get("paths") or [],
        "metadata": {
            "facultyId": "faculty-dds",
            "faculty": "dds",
            "wikiPage": (program.get("metadata") or {}).get("wikiPage"),
            "programKind": "bsc_track",
        },
        "sourceMetadata": {
            "curationReport": {
                "vaultSignoff": {
                    "signedOffBy": "vault-wiki",
                    "signoffSource": "vault-wiki",
                }
            }
        },
    }


def build_requirement_document(program_code: str, group: dict) -> dict[str, Any]:
    group_id = group["groupId"]
    slug = group_id.split(":", 1)[1]
    return {
        "productionKey": f"{INSTITUTION}-dds:requirement:{group_id}:{CATALOG_VERSION}",
        "institutionId": INSTITUTION,
        "programCode": program_code,
        "requirementGroupId": group_id,
        "title": group.get("title"),
        "requirementType": group.get("requirementType") or "elective",
        "minCredits": group.get("minCredits"),
        "courseReferences": group.get("courseReferences") or [],
        "ruleExpression": group.get("ruleExpression") or {},
        "ruleIsExecutable": True,
        "isMandatory": slug == "core-mandatory",
        "advisoryOnly": False,
        "catalogYear": CATALOG_YEAR,
        "catalogVersion": CATALOG_VERSION,
        "status": "published",
    }


def build_rule_document(program_code: str, group: dict, buckets: set[str]) -> dict[str, Any]:
    group_id = group["groupId"]
    slug = group_id.split(":", 1)[1]

    document: dict[str, Any] = {
        "productionKey": f"{INSTITUTION}-dds:advisory:{group_id}:{CATALOG_VERSION}",
        "institutionId": INSTITUTION,
        "programCode": program_code,
        "requirementGroupId": group_id,
        "recordType": "advisory_requirement_group",
        "title": group.get("title"),
        "requirementType": group.get("requirementType") or "elective",
        "minCredits": group.get("minCredits"),
        "courseReferences": group.get("courseReferences") or [],
        "ruleExpression": group.get("ruleExpression") or {},
        "ruleIsExecutable": False,
        "advisoryOnly": True,
        "enforceInGraduationProgress": False,
        "manualReviewRequired": True,
        "isMandatory": False,
        "catalogYear": CATALOG_YEAR,
        "catalogVersion": CATALOG_VERSION,
        "status": "published",
    }

    # A pool named `<slug>-pool` fills the credit bucket named `<slug>`, when
    # the program actually has that bucket. Derived rather than hard-coded so a
    # new pool in the export links itself without editing this script.
    if slug.endswith("-pool") and slug[: -len("-pool")] in buckets:
        document["linkedCreditBucketId"] = f"{program_code}:{slug[: -len('-pool')]}"
    return document


def stamp(document: dict, key_prefix: str, key_field: str) -> dict[str, Any]:
    """Add the production identity fields the promoter would otherwise add."""
    stamped = dict(document)
    stamped.setdefault("institutionId", INSTITUTION)
    stamped["productionKey"] = (
        f"{INSTITUTION}:{key_prefix}:{document[key_field]}:{CATALOG_VERSION}"
    )
    stamped["catalogYear"] = CATALOG_YEAR
    stamped["catalogVersion"] = CATALOG_VERSION
    stamped["status"] = "published"
    return stamped


def main() -> int:
    if not DDS_EXPORT.is_file():
        raise SystemExit(f"missing DDS export: {DDS_EXPORT}")
    export = json.loads(DDS_EXPORT.read_text(encoding="utf-8"))
    programs = export["programs"]

    raw_courses, offerings = load_raw_courses()
    fallback_records = load_fallback_records()
    references = collect_course_references(programs)

    # DDS-relevant means: every course the three tracks reference, plus every
    # course the DDS faculty itself offers this year, so the catalog page has a
    # real faculty to browse rather than only the courses a rule happens to name.
    dds_faculty_numbers = {
        number
        for number, general in raw_courses.items()
        if DDS_FACULTY_MARKER in (general.get(F_FACULTY) or "")
    }
    excluded = load_excluded_course_numbers()
    wanted = sorted((set(references) | dds_faculty_numbers) - excluded)

    courses = [
        build_course_document(
            number,
            references.get(number),
            raw_courses.get(number) or fallback_records.get(number),
        )
        for number in wanted
    ]
    kept_offerings = sorted(
        (o for o in offerings if o["courseNumber"] in set(wanted)),
        key=lambda o: (o["courseNumber"], o["academicYear"], o["semesterCode"]),
    )

    requirements: list[dict] = []
    rules: list[dict] = []
    for program in programs:
        code = program["programCode"]
        buckets = credit_bucket_slugs(program)
        for group in program.get("requirementGroups") or []:
            rule_type = (group.get("ruleExpression") or {}).get("type")
            if rule_type == HARD_RULE_TYPE:
                requirements.append(build_requirement_document(code, group))
            else:
                rules.append(build_rule_document(code, group, buckets))

    fixture = OrderedDict(
        (
            (
                "_meta",
                {
                    "description": "DDS demo catalog seeded into the live gallery demo",
                    "generatedBy": "scripts/build_demo_seed.py",
                    "sources": [
                        str(DDS_EXPORT.relative_to(REPO_ROOT)),
                        *[f"services/data-engineering/data/raw/technion/{n}" for n in DEMO_SEMESTERS],
                    ],
                    "catalogYear": CATALOG_YEAR,
                    "catalogVersion": CATALOG_VERSION,
                },
            ),
            ("catalog_faculties", [stamp(f, "faculty", "facultyId") for f in export["faculties"]]),
            (
                "catalog_path_options",
                [stamp(p, "path-option", "optionKey") for p in export["pathOptions"]],
            ),
            ("degree_programs", [build_program_document(p) for p in programs]),
            ("degree_requirements", requirements),
            ("catalog_rules", rules),
            ("courses", courses),
            ("course_offerings", kept_offerings),
        )
    )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(fixture, ensure_ascii=False, indent=1, sort_keys=False) + "\n",
        encoding="utf-8",
    )

    missing_credits = [c["courseNumber"] for c in courses if c["credits"] is None]
    print(f"wrote {OUTPUT.relative_to(REPO_ROOT)} ({OUTPUT.stat().st_size / 1024:.0f} KB)")
    for name, rows in fixture.items():
        if name != "_meta":
            print(f"  {name:<22} {len(rows)}")
    print(f"  courses referenced by tracks: {len(references)}")
    print(f"  courses offered by DDS faculty: {len(dds_faculty_numbers)}")
    print(f"  excluded from production (not seeded): {len((set(references) | dds_faculty_numbers) & excluded)}")
    if missing_credits:
        print(f"  WARNING: {len(missing_credits)} course(s) with no credits: {missing_credits[:10]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
