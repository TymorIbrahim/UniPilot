"""Fetch Technion semester offerings from the cheesefork archives.

Why this exists
---------------
`data/raw/technion/` held 2023 spring onward. Everything older was simply
absent, and the gap is not cosmetic: a real transcript listed `03240462`
("ברלין בקולנוע-מהנאציזם ועד ימינו", 2.0 credits, summer 2022) which no
catalog row could resolve, so the import kept the row with no course link and
the student's degree-applied credits were 2.0 short of their own transcript.
The same gap makes the planner blind to anything a student took before 2023.

The archives are the SOURCE our existing files already came from -- the files
in `data/raw/technion/` are byte-compatible with what these hosts serve, same
`{general, schedule}` shape and same Hebrew keys -- so this widens coverage
without introducing a second format.

Two hosts, two eras, two formats
--------------------------------
- `sap.cheesefork.cf/courses_<year>_<2NN>.min.js` covers roughly 2024 onward
  and serves a bare JSON array. Course numbers are already 8 digits.
- `ug.cheesefork.cf/courses_<year><N>.min.js` covers the older terms and serves
  `var courses_from_rishum = JSON.parse('<json>');`. Course numbers there are
  the OLD 6-digit Technion format, which the rest of UniPilot does not use.

`normalise_course_number` converts the old form; everything downstream keys on
8-digit numbers, and a 6-digit one silently matches nothing.

NOT taken from cheesefork
-------------------------
Its application code is GPL-3.0 and none of it is copied here -- this module
reads two published URLs and reshapes the payload. The companion
`technion-histograms` repository carries NO licence at all, so grade
distributions are deliberately not fetched.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

SAP_URL = "https://sap.cheesefork.cf/courses_{year}_{term}.min.js"
UG_URL = "https://ug.cheesefork.cf/courses_{year}{index:02d}.min.js"

COURSE_NUMBER_KEY = "מספר מקצוע"

_UG_PAYLOAD = re.compile(r"JSON\.parse\('(.*)'\)\s*;?\s*$", re.S)
_BARE_ARRAY = re.compile(r"=\s*(\[.*\])\s*;?\s*$", re.S)


@dataclass(frozen=True)
class ArchiveTerm:
    """One Technion term, in both the numbering schemes the hosts use."""

    year: int
    term: int  # 200 winter, 201 spring, 202 summer

    @property
    def index(self) -> int:
        """1/2/3. The `ug` host names files `courses_<year><index>` with the
        index ZERO-PADDED to two digits -- `courses_202203`, not
        `courses_20223`, which 404s and reads as "no archive for this term"."""
        return self.term - 199

    @property
    def semester_code(self) -> str:
        """`YYYY-N`, the form the rest of UniPilot uses."""
        return f"{self.year}-{self.index}"

    @property
    def filename(self) -> str:
        return f"courses_{self.year}_{self.term}.json"

    def urls(self) -> tuple[str, ...]:
        """Both hosts, newest-format first; callers try them in order."""
        return (
            SAP_URL.format(year=self.year, term=self.term),
            UG_URL.format(year=self.year, index=self.index),
        )


def normalise_course_number(raw: Any) -> str | None:
    """Technion course number as 8 digits, converting the legacy 6-digit form.

    `234114` (old) and `02340114` (current) are the same course: the new form
    inserts a leading zero and a zero between faculty and course. The older
    archive uses the short form throughout, and every join in UniPilot -- the
    transcript, the catalog, the pools -- is on the long one, so an unconverted
    number matches nothing at all rather than failing loudly.
    """
    if raw is None:
        return None
    digits = re.sub(r"\D", "", str(raw))
    if not digits:
        return None
    if len(digits) == 8:
        return digits
    if len(digits) == 6:
        return f"0{digits[:3]}0{digits[3:]}"
    if len(digits) == 7:
        # Occasionally the leading zero is dropped by a spreadsheet round-trip.
        return f"0{digits}"
    return None


def parse_archive_payload(body: str) -> list[dict[str, Any]]:
    """Decode either host's response into the list of course records.

    The `ug` host wraps its JSON in a single-quoted JavaScript string literal.
    Decoding that with `unicode_escape` looks right and is not: it mangles the
    Hebrew into mojibake, because the bytes are already UTF-8. Re-quoting the
    literal as JSON keeps `\\uXXXX` handling and leaves the UTF-8 alone.
    """
    text = body.strip()

    match = _UG_PAYLOAD.search(text)
    if match:
        inner = match.group(1).replace("\\'", "'").replace('"', '\\"')
        return json.loads(json.loads(f'"{inner}"'))

    match = _BARE_ARRAY.search(text)
    if match:
        return json.loads(match.group(1))

    return json.loads(text)


def normalise_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Course records with 8-digit numbers, in the shape `data/raw/technion` holds.

    Records whose number cannot be normalised are dropped rather than carried
    with a number nothing can join on -- a row that matches nothing is
    indistinguishable from an absent one downstream, except that it inflates
    every count.
    """
    normalised: list[dict[str, Any]] = []
    for record in records:
        general = record.get("general")
        if not isinstance(general, dict):
            continue
        number = normalise_course_number(general.get(COURSE_NUMBER_KEY))
        if number is None:
            continue
        normalised.append(
            {**record, "general": {**general, COURSE_NUMBER_KEY: number}}
        )
    return normalised
