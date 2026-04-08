from __future__ import annotations

import json
import os

_DB_PATH = os.path.join(os.path.dirname(__file__), "dimensions.json")
_db: dict[str, float] | None = None


def _load_db() -> dict[str, float]:
    global _db
    if _db is None:
        with open(_DB_PATH, encoding="utf-8") as f:
            _db = {k: v for k, v in json.load(f).items() if not k.startswith("_")}
    return _db


def get_height(name: str) -> float | None:
    """Look up real-world height in meters for a named object.

    Tries exact match, then underscore/hyphen normalization, then substring match.
    Returns height in meters or None if not found.
    """
    db = _load_db()
    key = name.lower().strip().replace(" ", "_").replace("-", "_")

    # Exact match
    if key in db:
        return db[key]

    # Fuzzy: find keys that contain the query or vice versa
    for db_key, value in db.items():
        if key in db_key or db_key in key:
            return value

    return None


def list_objects() -> list[str]:
    """List all objects in the dimensions database."""
    return list(_load_db().keys())
