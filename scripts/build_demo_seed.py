#!/usr/bin/env python3
"""Build the catalog the API seeds into the live demo on startup.

The gallery demo runs in kiosk mode: no volumes, nothing carried over between
visitors, and no access to the promoted production database. Whatever a visitor
sees has to be seeded from code every time the stack starts, and the seed has to
be the real catalog -- not a fixture -- or the demo undersells the system.

This builds it from files already tracked in the repo:

  * every reviewed faculty catalog export under
    `data/generated/technion/*/catalog_reviewed.json` -- the same documents the
    promotion pipeline turns into production `degree_programs` /
    `degree_requirements` / `catalog_rules`, so every track carries its real
    credit buckets, semester matrices and course pools
  * the raw Technion semester JSON for the current catalog year, for course
    titles, credits, syllabi and the weekly schedule the planner needs

Output is a single deterministic JSON fixture committed alongside the API, so
the demo image needs no extra build context and startup stays a bulk insert.

    python3 scripts/build_demo_seed.py

Re-run it when a faculty export or the raw semester files change.
"""

from __future__ import annotations

import gzip
import importlib.util
import json
from collections import OrderedDict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
GENERATED = REPO_ROOT / "services/data-engineering/data/generated/technion"
RAW_DIR = REPO_ROOT / "services/data-engineering/data/raw/technion"
# Gzipped: the fixture is 12 MB of real catalogue text and 1 MB compressed, and
# it is derived data regenerated from files already in the repo. Committing the
# compressed form keeps the clone small; the API decompresses it once at startup.
OUTPUT = REPO_ROOT / "services/api/app/db/seed_data/demo_catalog.json.gz"

# The catalog year the demo presents. Winter first so a visitor opening the
# planner lands on a term that actually has offerings.
DEMO_SEMESTERS = ("courses_2025_200.json", "courses_2025_201.json")
SEMESTER_NAMES = {200: "winter", 201: "spring", 202: "summer"}

CATALOG_YEAR = 2025
CATALOG_VERSION = "2025-2026"
INSTITUTION = "technion"

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


def load_exports() -> tuple[list[dict], dict[str, dict], dict[str, dict]]:
    """Merge every faculty export into (programs, faculties, path options).

    A joint program is exported by both of its owning faculties -- 023323-1-000
    by computer-science and mathematics, for instance -- and production holds a
    single document per code. Deduplicating by code in sorted directory order
    keeps that true and keeps the output deterministic.
    """
    programs: dict[str, dict] = {}
    faculties: dict[str, dict] = {}
    options: dict[str, dict] = {}

    export_files = sorted(GENERATED.glob("*/catalog_reviewed.json"))
    if not export_files:
        raise SystemExit(f"no faculty exports found under {GENERATED}")

    for path in export_files:
        export = json.loads(path.read_text(encoding="utf-8"))
        for program in export.get("programs") or []:
            programs.setdefault(program["programCode"], program)
        for faculty in export.get("faculties") or []:
            faculties.setdefault(faculty["facultyId"], faculty)
        for option in export.get("pathOptions") or []:
            options.setdefault(option["optionKey"], option)

    ordered = [programs[code] for code in sorted(programs)]
    return ordered, faculties, options


def load_fallback_records() -> dict[str, dict]:
    """Course descriptions from every semester the repo has, oldest first.

    A track can name a course that simply isn't offered in the demo year -- a
    course on hiatus, or one that only runs in summer. Without this those land
    in the fixture with `credits: null`, which the progress calculator would
    silently read as zero. Any semester's record carries the credit value, so
    the newest one that has the course wins.
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
                    "scheduleGroups": record.get("schedule") or [],
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
    """Every distinct course the tracks point at, with its catalogue hints."""
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


def faculty_slug(program: dict) -> str:
    return (program.get("metadata") or {}).get("faculty") or "technion"


def credit_bucket_slugs(program: dict) -> set[str]:
    return {
        group["groupId"].split(":", 1)[1]
        for group in program.get("requirementGroups") or []
        if (group.get("ruleExpression") or {}).get("type") == HARD_RULE_TYPE
    }


def build_program_document(program: dict) -> dict[str, Any]:
    code = program["programCode"]
    slug = faculty_slug(program)
    metadata = program.get("metadata") or {}
    return {
        "productionKey": f"{INSTITUTION}-{slug}:program:{code}:{CATALOG_VERSION}",
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
            "facultyId": metadata.get("facultyId") or f"faculty-{slug}",
            "faculty": slug,
            "wikiPage": metadata.get("wikiPage"),
            "programKind": metadata.get("programKind") or "bsc_track",
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


def build_requirement_document(program: dict, group: dict) -> dict[str, Any]:
    code = program["programCode"]
    slug = faculty_slug(program)
    group_id = group["groupId"]
    bucket = group_id.split(":", 1)[1]
    return {
        "productionKey": f"{INSTITUTION}-{slug}:requirement:{group_id}:{CATALOG_VERSION}",
        "institutionId": INSTITUTION,
        "programCode": code,
        "requirementGroupId": group_id,
        "title": group.get("title"),
        "requirementType": group.get("requirementType") or "elective",
        "minCredits": group.get("minCredits"),
        "courseReferences": group.get("courseReferences") or [],
        "ruleExpression": group.get("ruleExpression") or {},
        "ruleIsExecutable": True,
        "isMandatory": bucket == "core-mandatory",
        "advisoryOnly": False,
        "catalogYear": CATALOG_YEAR,
        "catalogVersion": CATALOG_VERSION,
        "status": "published",
    }


def build_rule_document(program: dict, group: dict, buckets: set[str]) -> dict[str, Any]:
    code = program["programCode"]
    slug = faculty_slug(program)
    group_id = group["groupId"]
    suffix = group_id.split(":", 1)[1]

    document: dict[str, Any] = {
        "productionKey": f"{INSTITUTION}-{slug}:advisory:{group_id}:{CATALOG_VERSION}",
        "institutionId": INSTITUTION,
        "programCode": code,
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
    # new pool in an export links itself without editing this script.
    if suffix.endswith("-pool") and suffix[: -len("-pool")] in buckets:
        document["linkedCreditBucketId"] = f"{code}:{suffix[: -len('-pool')]}"
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
    programs, faculties, options = load_exports()
    raw_courses, offerings = load_raw_courses()
    fallback_records = load_fallback_records()
    references = collect_course_references(programs)
    excluded = load_excluded_course_numbers()

    # The full published catalog for the demo year, plus any course a track
    # names that the year does not happen to offer.
    wanted = sorted((set(raw_courses) | set(references)) - excluded)

    courses = [
        build_course_document(
            number,
            references.get(number),
            raw_courses.get(number) or fallback_records.get(number),
        )
        for number in wanted
    ]
    kept = set(wanted)
    kept_offerings = sorted(
        (o for o in offerings if o["courseNumber"] in kept),
        key=lambda o: (o["courseNumber"], o["academicYear"], o["semesterCode"]),
    )

    requirements: list[dict] = []
    rules: list[dict] = []
    for program in programs:
        buckets = credit_bucket_slugs(program)
        for group in program.get("requirementGroups") or []:
            if (group.get("ruleExpression") or {}).get("type") == HARD_RULE_TYPE:
                requirements.append(build_requirement_document(program, group))
            else:
                rules.append(build_rule_document(program, group, buckets))

    fixture = OrderedDict(
        (
            (
                "_meta",
                {
                    "description": "Technion catalog seeded into the live gallery demo",
                    "generatedBy": "scripts/build_demo_seed.py",
                    "catalogYear": CATALOG_YEAR,
                    "catalogVersion": CATALOG_VERSION,
                    "semesters": list(DEMO_SEMESTERS),
                },
            ),
            (
                "catalog_faculties",
                [stamp(faculties[k], "faculty", "facultyId") for k in sorted(faculties)],
            ),
            (
                "catalog_path_options",
                [stamp(options[k], "path-option", "optionKey") for k in sorted(options)],
            ),
            ("degree_programs", [build_program_document(p) for p in programs]),
            ("degree_requirements", requirements),
            ("catalog_rules", rules),
            ("courses", courses),
            ("course_offerings", kept_offerings),
        )
    )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(fixture, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    # mtime=0 so regenerating unchanged input produces a byte-identical file
    # rather than a spurious diff.
    with gzip.GzipFile(OUTPUT, "wb", compresslevel=9, mtime=0) as handle:
        handle.write(payload)

    missing = [c["courseNumber"] for c in courses if c["credits"] is None]
    print(
        f"wrote {OUTPUT.relative_to(REPO_ROOT)} "
        f"({OUTPUT.stat().st_size / 1_048_576:.2f} MB gzipped, "
        f"{len(payload) / 1_048_576:.1f} MB raw)"
    )
    for name, rows in fixture.items():
        if name != "_meta":
            print(f"  {name:<22} {len(rows)}")
    print(f"  faculties with an export: {len(sorted(GENERATED.glob('*/catalog_reviewed.json')))}")
    print(f"  courses named by a track: {len(references)}")
    print(f"  excluded from production: {len((set(raw_courses) | set(references)) & excluded)}")
    if missing:
        print(f"  WARNING: {len(missing)} course(s) with no credits: {missing[:8]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
