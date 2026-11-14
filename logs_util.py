from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from config import BOOK_DIR, BOOK_SLUG, EVENTS, LOGS, PIPELINE_LOG, STATE, STATUS

ZONE = ZoneInfo("Europe/Belgrade")


def now_iso() -> str:
    return datetime.now(ZONE).isoformat(timespec="seconds")


def append_log(message: str) -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    line = f"{now_iso()} {message}"
    print(line, flush=True)
    with PIPELINE_LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def emit(kind: str, **fields: object) -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    row = {"at": now_iso(), "kind": kind, **fields}
    with EVENTS.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    extra = {key: value for key, value in fields.items() if key != "detail"}
    append_log(f"{kind} {extra}".strip())


def load_state() -> dict:
    if not STATE.is_file():
        return {"status": "idle", "round": 0, "message": "ещё не запускали", "rounds": []}
    try:
        payload = json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"status": "idle", "round": 0, "message": "state.json битый", "rounds": []}
    return payload if isinstance(payload, dict) else {}


def write_public_status(state: dict | None = None) -> None:
    current = state if isinstance(state, dict) else load_state()
    events: list[object] = []
    if EVENTS.is_file():
        for line in EVENTS.read_text(encoding="utf-8").splitlines()[-80:]:
            try:
                events.append(json.loads(line))
            except ValueError:
                continue
    BOOK_DIR.mkdir(parents=True, exist_ok=True)
    payload = {**current, "book": BOOK_SLUG, "events": events, "status_at": now_iso()}
    STATUS.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def save_state(payload: dict) -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    payload["updated_at"] = now_iso()
    STATE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_public_status(payload)


def patch_state(**fields: object) -> dict:
    current = load_state()
    current.update(fields)
    save_state(current)
    return current


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
