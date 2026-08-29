"""Locate the repo checkout without assuming how deep this file is nested.

`Path(__file__).resolve().parents[3]` worked from a developer checkout and threw
`IndexError` inside the service image, where the tree is mounted at `/app` and
has only three ancestors. Because both call sites ran it at module scope, that
was a collection error, not a test failure: two files failed to import and
pytest refused to run any of the other 86 tests. Searching for a marker instead
gives the same answer in a checkout and a defined one everywhere else.
"""

from __future__ import annotations

from pathlib import Path


def find_repo_root() -> Path | None:
    """Nearest ancestor directory that holds `services/`, or None when unmounted."""
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "services").is_dir():
            return candidate
    return None


def repo_file(*parts: str) -> Path | None:
    """A path under the repo root, or None when the checkout is not reachable."""
    root = find_repo_root()
    return root.joinpath(*parts) if root else None
