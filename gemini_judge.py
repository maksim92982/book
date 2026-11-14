from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from config import JUDGE_MODEL, ROOT
from logs_util import emit

JOB_ROOT = ROOT.parent / "job-apply-agent"
_ENV_FILES = (
    JOB_ROOT / ".env",
    Path("/opt/job-apply-agent/.env"),
    ROOT.parent / "telegram-content-bot" / ".env",
)
FALLBACK_MODELS = ("gemini-3.8-flash", "gemini-3.5-flash-lite")


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


def gemini_key() -> str:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if key:
        return key
    for path in _ENV_FILES:
        key = _read_env_file(path).get("GEMINI_API_KEY", "").strip()
        if key:
            return key
    return ""


def judge_model() -> str:
    return JUDGE_MODEL


def generate_json(prompt: str, *, timeout: int = 180) -> tuple[str, str]:
    key = gemini_key()
    if not key:
        raise RuntimeError("нет GEMINI_API_KEY — судья Gemini не запустится")
    models = (judge_model(),) + tuple(item for item in FALLBACK_MODELS if item != judge_model())
    last_error = "неизвестная ошибка"
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "thinkingConfig": {"thinkingLevel": "low"},
            },
        }
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "x-goog-api-key": key},
            method="POST",
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")[:400]
            last_error = f"{model}: HTTP {error.code} {detail}"
            emit("gemini_http", model=model, code=error.code)
            continue
        except (URLError, TimeoutError, ValueError) as error:
            last_error = f"{model}: {error}"
            emit("gemini_error", model=model, error=str(error)[:300])
            continue
        try:
            text = str(body["candidates"][0]["content"]["parts"][0]["text"] or "")
        except (KeyError, IndexError, TypeError):
            last_error = f"{model}: пустой ответ"
            continue
        emit("gemini_ok", model=model, chars=len(text))
        return text, model
    raise RuntimeError(f"Gemini не ответил: {last_error}")
