from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

from .models import Profile

# Windows defaults to cp1252 for pipes/consoles — job titles and rich traces blow up otherwise.
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
DATA_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

load_dotenv(ROOT / ".env")

# Default model depends on which key is present.
_default = "gemini-2.0-flash" if os.getenv("GEMINI_API_KEY") and not os.getenv("OPENAI_API_KEY") else "gpt-4o-mini"
MODEL = os.getenv("APPLYFORME_MODEL", _default)


def load_profile(path: str | Path | None = None) -> Profile:
    p = Path(path) if path else ROOT / "profile.yaml"
    if not p.exists():
        raise SystemExit(f"{p} not found. Run `python -m applyforme init` first.")
    with open(p, encoding="utf-8") as f:
        return Profile(**yaml.safe_load(f))
