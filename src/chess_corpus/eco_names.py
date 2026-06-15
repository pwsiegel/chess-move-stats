"""ECO code → canonical opening name.

Lumbra's PGNs include the `[ECO "..."]` tag but no `[Opening "..."]` tag,
so the `opening` parquet column is mostly null. This module ships a static
ECO → name mapping derived from the Lichess `chess-openings` repo
(https://github.com/lichess-org/chess-openings, MIT licensed). For each
3-character ECO code we pick the shortest-PGN entry — the most root /
canonical variation in that bucket.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_DATA_PATH = Path(__file__).parent / "eco_names.json"


@lru_cache(maxsize=1)
def _table() -> dict[str, str]:
    return json.loads(_DATA_PATH.read_text())


def name_for(eco: str | None) -> str | None:
    """Look up the canonical opening name for a 3-character ECO code.

    Accepts longer codes (e.g. Lumbra's `B23m`) and truncates to the first
    three characters. Returns None for unknown / missing inputs.
    """
    if not eco or len(eco) < 3:
        return None
    return _table().get(eco[:3])
