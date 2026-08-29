"""Unit tests for the boolean prerequisite expression parser.

The catalog states prerequisites as text with a small, consistent grammar:
course numbers joined by `ו-` (and) and `או` (or), grouped with parentheses.
Reading that text as a flat list of course numbers -- which is what
`extract_course_numbers_from_text` does -- turns "any one of these five" into
"all five of these", which is wrong for 769 of the 1,105 catalog courses that
use either operator.
"""

from __future__ import annotations

import pytest

from app.planning.prerequisite_expression import (
    AllOf,
    AnyOf,
    CourseLeaf,
    PrerequisiteParseError,
    course_numbers,
    is_satisfied_by,
    missing_alternatives,
    parse_prerequisite_expression,
)


def _leaf(number: str) -> CourseLeaf:
    return CourseLeaf(number)


class TestParsing:
    def test_a_single_course_is_a_leaf(self) -> None:
        assert parse_prerequisite_expression("00940412") == _leaf("00940412")

    def test_and_joins_into_all_of(self) -> None:
        assert parse_prerequisite_expression("00940564 ו-00940424") == AllOf(
            (_leaf("00940564"), _leaf("00940424"))
        )

    def test_or_joins_into_any_of(self) -> None:
        """The bug this module exists to fix.

        `00970215` requires ONE of five alternatives. Flattened to a list it
        reads as five requirements, and the student is told they are missing
        four courses they never needed.
        """
        text = "02360756 או 00960411 או 00460203 או 00460202 או 00460195"

        assert parse_prerequisite_expression(text) == AnyOf(
            (
                _leaf("02360756"),
                _leaf("00960411"),
                _leaf("00460203"),
                _leaf("00460202"),
                _leaf("00460195"),
            )
        )

    def test_and_binds_tighter_than_or(self) -> None:
        """Real catalog text relies on this precedence without parentheses.

        `01240400 ו-02340128 או 01150203 ו-02340128` is four courses forming
        two alternative PAIRS, not two courses and two alternatives.
        """
        parsed = parse_prerequisite_expression(
            "01240400 ו-02340128 או 01150203 ו-02340128"
        )

        assert parsed == AnyOf(
            (
                AllOf((_leaf("01240400"), _leaf("02340128"))),
                AllOf((_leaf("01150203"), _leaf("02340128"))),
            )
        )

    def test_parentheses_group_explicitly(self) -> None:
        parsed = parse_prerequisite_expression(
            "(00940347 ו-00940411) או (00940345 ו-00940411)"
        )

        assert parsed == AnyOf(
            (
                AllOf((_leaf("00940347"), _leaf("00940411"))),
                AllOf((_leaf("00940345"), _leaf("00940411"))),
            )
        )

    def test_parentheses_can_override_the_default_precedence(self) -> None:
        parsed = parse_prerequisite_expression("00140205 ו-(00140322 או 00140315)")

        assert parsed == AllOf(
            (_leaf("00140205"), AnyOf((_leaf("00140322"), _leaf("00140315"))))
        )

    def test_a_single_child_group_collapses(self) -> None:
        """`(A)` is A -- keeping a one-child AllOf would make equality and
        rendering depend on incidental punctuation."""
        assert parse_prerequisite_expression("(00940412)") == _leaf("00940412")

    def test_legacy_six_digit_numbers_are_normalised(self) -> None:
        """The catalog mixes 6-digit legacy numbers with 8-digit current ones;
        an unnormalised leaf never matches a completed course."""
        assert parse_prerequisite_expression("234114") == _leaf("00234114")

    @pytest.mark.parametrize("text", [None, "", "   "])
    def test_blank_text_means_no_prerequisites(self, text) -> None:
        assert parse_prerequisite_expression(text) is None

    @pytest.mark.parametrize(
        "text",
        [
            "(00940412 או 00940413",  # unbalanced open
            "00940412 או 00940413)",  # unbalanced close
            "00940412 או",  # trailing operator
            "או 00940412",  # leading operator
            "00940412 ו-ו-00940413",  # doubled operator
            "()",  # empty group
            "בהתאם לתנאי הפקולטה",  # prose, no course numbers
            "00940412 בהתאם לתנאי הפקולטה",  # partially understood
        ],
    )
    def test_text_we_do_not_fully_understand_raises(self, text) -> None:
        """Never guess. A partial parse is how a flat list of numbers became a
        conjunction in the first place -- the caller must decide what to do
        with text the grammar does not cover.
        """
        with pytest.raises(PrerequisiteParseError):
            parse_prerequisite_expression(text)


class TestIsSatisfiedBy:
    def test_any_one_alternative_satisfies_an_or(self) -> None:
        expression = parse_prerequisite_expression("02360756 או 00960411 או 00460203")

        assert is_satisfied_by(expression, {"00960411"}) is True

    def test_an_or_with_none_of_the_alternatives_is_not_satisfied(self) -> None:
        expression = parse_prerequisite_expression("02360756 או 00960411")

        assert is_satisfied_by(expression, {"00940412"}) is False

    def test_an_and_needs_every_child(self) -> None:
        expression = parse_prerequisite_expression("00940564 ו-00940424")

        assert is_satisfied_by(expression, {"00940564"}) is False
        assert is_satisfied_by(expression, {"00940564", "00940424"}) is True

    def test_nested_expressions_evaluate_through(self) -> None:
        expression = parse_prerequisite_expression(
            "(00140205 ו-00140212) או (00140322 ו-00140212)"
        )

        assert is_satisfied_by(expression, {"00140322", "00140212"}) is True
        assert is_satisfied_by(expression, {"00140205", "00140322"}) is False

    def test_no_prerequisites_is_satisfied_by_anything(self) -> None:
        assert is_satisfied_by(None, set()) is True

    def test_completed_numbers_are_normalised_before_comparison(self) -> None:
        """A completed set carrying legacy 6-digit numbers must still match."""
        expression = parse_prerequisite_expression("00234114")

        assert is_satisfied_by(expression, {"234114"}) is True


class TestCourseNumbers:
    def test_returns_every_course_mentioned(self) -> None:
        expression = parse_prerequisite_expression(
            "(00140205 ו-00140212) או (00140322 ו-00140212)"
        )

        assert course_numbers(expression) == {"00140205", "00140212", "00140322"}

    def test_no_prerequisites_mentions_nothing(self) -> None:
        assert course_numbers(None) == set()


class TestMissingAlternatives:
    def test_an_or_offers_each_alternative_separately(self) -> None:
        """The student needs ONE of these, and the UI has to say so."""
        expression = parse_prerequisite_expression("02360756 או 00960411")

        assert missing_alternatives(expression, set()) == [
            frozenset({"02360756"}),
            frozenset({"00960411"}),
        ]

    def test_an_and_offers_one_combined_alternative(self) -> None:
        expression = parse_prerequisite_expression("00940564 ו-00940424")

        assert missing_alternatives(expression, set()) == [
            frozenset({"00940564", "00940424"})
        ]

    def test_courses_already_completed_drop_out_of_the_alternatives(self) -> None:
        expression = parse_prerequisite_expression("00940564 ו-00940424")

        assert missing_alternatives(expression, {"00940564"}) == [
            frozenset({"00940424"})
        ]

    def test_a_satisfied_expression_has_one_empty_alternative(self) -> None:
        """Empty means "nothing further needed" -- distinct from no alternatives
        at all, which would read as unsatisfiable."""
        expression = parse_prerequisite_expression("02360756 או 00960411")

        assert missing_alternatives(expression, {"00960411"}) == [frozenset()]

    def test_a_cheaper_alternative_hides_the_supersets_of_it(self) -> None:
        """Offering {A} and {A,B} side by side invites doing needless work."""
        expression = parse_prerequisite_expression("00140205 או (00140205 ו-00140212)")

        assert missing_alternatives(expression, set()) == [frozenset({"00140205"})]

    def test_no_prerequisites_needs_nothing(self) -> None:
        assert missing_alternatives(None, set()) == [frozenset()]
