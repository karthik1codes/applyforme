"""Entry point: force UTF-8 on Windows so job titles / logs never crash on cp1252."""
from __future__ import annotations

import sys


def _force_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass


_force_utf8()

from .cli import main

main()
