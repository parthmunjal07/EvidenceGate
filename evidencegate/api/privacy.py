"""Sanitizers for public, analyst-facing reference projections."""

from __future__ import annotations

import re


def public_reference_list(values: tuple[str, ...] | list[str]) -> list[str]:
    """Hide private artifact locators and filesystem paths at the API boundary."""
    return [
        value
        for value in values
        if not value.startswith("drive:")
        and "drive.google.com" not in value.lower()
        and not re.search(r"(?i)(?:[a-z]:\\|/users/|/home/)", value)
    ]
