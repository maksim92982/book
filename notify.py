from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from config import ROOT
from criteria import CRITERIA
from logs_util import emit

JOB_ROOT = ROOT.parent / "job-apply-agent"
_ENV_FILES = (
    JOB_ROOT / ".env",
    Path("/opt/job-apply-agent/.env"),
)
_INBOX_FILES = (
    JOB_ROOT / "data" / "inbox.json",
    JOB_ROOT / "data" / "_vps_inbox.json",
    Path("/opt/job-apply-agent/data/inbox.json"),
)


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _job_token() -> str:
    token = os.getenv("JOB_TELEGRAM_BOT_TOKEN", "").strip()
    if token:
        return token
    for path in _ENV_FILES:
        token = _read_env_file(path).get("JOB_TELEGRAM_BOT_TOKEN", "").strip()
        if token:
            return token
    return ""


def _job_chat_id() -> str:
    chat = os.getenv("JOB_TELEGRAM_CHAT_ID", "").strip()
    for path in _INBOX_FILES:
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        stored = str(payload.get("chat_id") or "").strip() if isinstance(payload, dict) else ""
        if stored:
            return stored
    if chat:
        return chat
    for path in _ENV_FILES:
        chat = _read_env_file(path).get("JOB_TELEGRAM_CHAT_ID", "").strip()
        if chat:
            return chat
    return ""


def format_round_report(summary: dict, *, footer: str = "") -> str:
    n = summary.get("n")
    at = summary.get("at") or ""
    min_score = summary.get("min_score")
    words = summary.get("words")
    lines = [
        "Круги разбора",
        f"круг {n} · {at} · мин {min_score}/10 · {words} слов",
    ]
    criteria = summary.get("criteria") if isinstance(summary.get("criteria"), dict) else {}
    for item in CRITERIA:
        raw = criteria.get(item["key"])
        if not isinstance(raw, dict):
            continue
        title = str(raw.get("title") or item["title"])
        score = raw.get("score")
        gap = str(raw.get("gap") or "").strip()
        line = f"{title}: {score}/10"
        if gap:
            line += f" — {gap}"
        lines.append(line)
    if footer:
        lines += ["", footer]
    return "\n".join(lines)


def send_job_chat(text: str) -> bool:
    if os.getenv("LITRESS_TG_NOTIFY", "1").strip().lower() in {"0", "false", "no"}:
        emit("telegram_skip", reason="LITRESS_TG_NOTIFY=0")
        return False
    token = _job_token()
    chat_id = _job_chat_id()
    if not token or not chat_id:
        emit("telegram_skip", reason="нет токена или chat_id пайплайна вакансий")
        return False
    payload = urlencode(
        {
            "chat_id": chat_id,
            "text": text[:3900],
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")
    request = Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        method="POST",
        headers={"User-Agent": "litress-notify/1"},
    )
    try:
        with urlopen(request, timeout=40) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, ValueError) as error:
        emit("telegram_failed", error=str(error)[:400])
        return False
    if not isinstance(body, dict) or not body.get("ok"):
        emit("telegram_failed", error=str(body)[:400])
        return False
    emit("telegram_sent", chars=len(text))
    return True


def notify_round(summary: dict, *, footer: str = "") -> bool:
    return send_job_chat(format_round_report(summary, footer=footer))
