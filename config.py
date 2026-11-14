from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
_SHARED = ROOT.parent / "shared"
if _SHARED.is_dir() and str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b").strip() or "qwen2.5:7b"
NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "8192") or "8192")
DASHBOARD_HOST = os.getenv("DASHBOARD_HOST", "127.0.0.1")
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "8765") or "8765")
MAX_ROUNDS = int(os.getenv("LITRESS_MAX_ROUNDS", "40") or "40")
MIN_CHAPTER_WORDS = int(os.getenv("LITRESS_MIN_WORDS", "450") or "450")
MIN_CRITERION_SCORE = int(os.getenv("LITRESS_MIN_SCORE", "8") or "8")
TARGET_CRITERION_SCORE = int(os.getenv("LITRESS_TARGET_SCORE", "10") or "10")
GIT_REMOTE = os.getenv("LITRESS_GIT_REMOTE", "git@github.com:maksim92982/book.git").strip()
GIT_BRANCH = os.getenv("LITRESS_GIT_BRANCH", "main").strip() or "main"
GIT_SYNC = os.getenv("LITRESS_GIT_SYNC", "1").strip().lower() not in {"0", "false", "no"}
CATALOG_PATH = ROOT / "books.json"


def default_catalog() -> dict:
    return {
        "current": "01-pesni-dunaya",
        "books": [
            {
                "id": "01-pesni-dunaya",
                "number": 1,
                "title": "Песни Дуная",
                "genre": "детектив",
            }
        ],
    }


def load_catalog() -> dict:
    if not CATALOG_PATH.is_file():
        return default_catalog()
    try:
        payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default_catalog()
    if not isinstance(payload, dict) or not payload.get("current"):
        return default_catalog()
    return payload


def save_catalog(payload: dict) -> None:
    CATALOG_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


BOOK_SLUG = os.getenv("LITRESS_BOOK", "").strip() or str(load_catalog().get("current") or "01-pesni-dunaya")
BOOK_DIR = ROOT / "books" / BOOK_SLUG
LOGS = BOOK_DIR / "logs"
ROUNDS = LOGS / "rounds"
STATE = LOGS / "state.json"
EVENTS = LOGS / "events.jsonl"
PIPELINE_LOG = LOGS / "pipeline.log"
STATUS = BOOK_DIR / "status.json"
