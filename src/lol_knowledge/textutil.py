"""Helpers for the text embedded in Data Dragon documents."""

from __future__ import annotations

import re
from collections.abc import Mapping

PLACEHOLDER_PATTERN = re.compile(r"\{\{\s*([A-Za-z][A-Za-z0-9_]*)\s*\}\}")


def substitute_placeholders(text: str, values: Mapping[str, str]) -> str:
    """Replace known ``{{ key }}`` placeholders and keep unknown ones untouched.

    Data Dragon tooltips reference effect values by placeholder. Leaving an
    unknown placeholder visible is deliberate: silently blanking it would hide
    a missing value instead of surfacing it.
    """
    return PLACEHOLDER_PATTERN.sub(
        lambda match: values.get(match.group(1), match.group(0)),
        text,
    )
