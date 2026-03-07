from __future__ import annotations

from typing import Dict


def parse_notes_kv(notes: str) -> Dict[str, str]:
    """
    Parse `sources/sources.csv` "notes" field tokens.

    Format: space-separated `key=value` tokens.
    Unknown tokens are ignored; later tokens with the same key win.
    """
    out: Dict[str, str] = {}
    for tok in (notes or "").split():
        if "=" not in tok:
            continue
        k, v = tok.split("=", 1)
        k = k.strip()
        v = v.strip()
        if k and v:
            out[k] = v
    return out

