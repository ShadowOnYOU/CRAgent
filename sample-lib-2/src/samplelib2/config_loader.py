from __future__ import annotations

import json
from typing import Any, Dict


def load_json_config(path: str) -> Dict[str, Any]:
    """Load a JSON config file.

    Note: This implementation intentionally contains issues for CRAgent review demos:
    - It may leak file descriptors (no context manager used)
    - It silently swallows JSON parsing errors and returns {}
    """
    f = open(path, "r", encoding="utf-8")
    text = f.read()

    try:
        return json.loads(text)
    except Exception:
        return {}
