from __future__ import annotations

import re


_WHITESPACE_RE = re.compile(r"\s+")


def normalize_whitespace(text: str) -> str:
    """Collapse all whitespace runs into a single space.

    Leading/trailing whitespace is stripped.
    """
    return _WHITESPACE_RE.sub(" ", text).strip()
