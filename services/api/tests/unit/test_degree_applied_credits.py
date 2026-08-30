"""Unit tests for the credits a degree counts.

There is a known gap here, deliberately left open. `degreeAppliedCredits` sums
every course ASSIGNED to a bucket, which can exceed what the buckets actually
credit: one real student is reported as having all 98 of their credits applied
while the buckets count 97, because a course overflowed the faculty-elective
allowance.

Reporting 97 would be no more correct. The catalogue states what becomes of
overflow, and it is neither "nothing" nor a general spill -- it is bounded and
track-specific:

    CS 4-year     "נקודות מעבר ל-8 יחשבו כבחירה מרשימה ב'"   science past 8 -> list B
    Mathematics   "עודף של 2 נקודות לכל היותר"               overflow, capped at 2

None of it is modelled in the promoted data, which carries only
`semester_matrix`, `course_pool` and `track_requirement` rules with the
operators `all_of`, `min_credits`, `choose_n` and `choose_chain`. There is no
representation of overflow at all, so the calculator has no rule to apply and
inventing one would credit a degree by guess. The invariants below are what can
be asserted until the catalogue carries the rule.
"""

from __future__ import annotations

from bson import ObjectId

from app.services.graduation_progress_calculator import calculate_graduation_progress


def _progress(min_credits, completed):
    catalog, records = {}, []
    for index, credits in enumerate(completed):
        course_id = str(ObjectId())
        catalog[course_id] = {"courseNumber": f"0094010{index}", "credits": credits}
        records.append({"courseId": ObjectId(course_id), "grade": 90, "creditsEarned": credits})
    return calculate_graduation_progress(
        degree_program={"_id": ObjectId(), "programCode": "p-1", "totalCredits": min_credits},
        hard_requirements=[
            {
                "_id": ObjectId(),
                "requirementGroupId": "p-1:free-elective",
                "minCredits": min_credits,
                "isMandatory": False,
                "requirementType": "elective",
                "ruleExpression": {"type": "credit_bucket"},
            }
        ],
        pool_documents=[],
        catalog_courses_by_id=catalog,
        completed_course_records=records,
    )


def test_applied_credits_never_exceed_what_was_earned() -> None:
    progress = _progress(4.0, [3.0, 3.0])

    assert progress["completedCredits"] == 6.0
    assert progress["degreeAppliedCredits"] <= progress["completedCredits"]


def test_a_bucket_never_counts_more_than_its_minimum() -> None:
    progress = _progress(4.0, [3.0, 3.0])

    for entry in progress["requirementProgress"]:
        assert float(entry["creditsCompleted"]) <= float(entry["minCredits"])


def test_a_student_inside_every_bucket_has_all_credits_applied() -> None:
    progress = _progress(10.0, [3.0, 3.5])

    assert progress["completedCredits"] == 6.5
    assert progress["degreeAppliedCredits"] == 6.5
