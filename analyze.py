from __future__ import annotations

import json
import re
from pathlib import Path

from config import BOOK_DIR, MIN_CHAPTER_WORDS, MIN_CRITERION_SCORE
from quality.mechanics import scan_mechanics
from criteria import (
    CRITERIA,
    cap_scores,
    empty_scores,
    failing,
    meets_bar,
    min_score_of,
    parse_scores,
    prompt_block,
)
from generate import (
    BOOK,
    CHAPTERS,
    CHARACTERS,
    FACTS,
    OUTLINE,
    PREMISE,
    chat,
    write,
)
from logs_util import emit, now_iso, patch_state

EMPTY_STYLE = {
    "шероховатость языка",
    "шероховатость",
    "2-4 предложения",
    "2 предложения",
    "можно улучшить гладкость текста",
}
_TASTE = (
    "можно ",
    "возможно",
    "стоит ",
    "добавьте",
    "добавить",
    "улучш",
    "красив",
    "более жив",
    "более динамич",
    "более разнообраз",
    "можно упростить",
    "можно сделать",
    "для лучшей читаемости",
    "для усиления",
)


def load_outline() -> dict:
    return json.loads(OUTLINE.read_text(encoding="utf-8"))


def chapter_files() -> list[Path]:
    return sorted(CHAPTERS.glob("*.md"))


def killer_name() -> str:
    blob = PREMISE.read_text(encoding="utf-8") if PREMISE.is_file() else ""
    if "Вукич" in blob:
        return "Вукич"
    return ""


def mechanical_chapter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    words = len(text.split())
    flags = [
        item.message
        for item in scan_mechanics(
            text,
            min_words=MIN_CHAPTER_WORDS,
            require_end=True,
            heading="Глава ",
            heading_max=2,
        )
    ]
    secret = killer_name()
    number = int(path.stem)
    if secret and number < 13:
        if re.search(rf"{secret}\w*.{{0,40}}убил", text, re.I | re.S):
            flags.append("ранний спойлер убийцы")
        if re.search(rf"{re.escape(secret)}.{{0,40}}убийца|убийца.{{0,40}}{re.escape(secret)}", text, re.I | re.S):
            flags.append("имя убийцы рядом со словом убийца")
    return {"file": path.name, "n": number, "words": words, "flags": flags, "text": text}


def _is_taste(text: str) -> bool:
    low = text.casefold()
    if low in EMPTY_STYLE:
        return True
    if "спойлер" in low or "убийц" in low or "канон" in low:
        return False
    return any(token in low for token in _TASTE)


def _clean_list(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    items: list[str] = []
    for item in raw:
        if isinstance(item, dict):
            comment = str(item.get("comment") or item.get("fact") or "")
            quote = str(item.get("text") or "")
            text = f"{quote}: {comment}".strip(": ").strip()
        else:
            text = str(item or "").strip()
        if not text or _is_taste(text):
            continue
        items.append(text)
    return items


def review_chapter(path: Path, data: dict, mech: dict) -> dict:
    number = int(path.stem)
    plan = next(
        (
            row
            for row in data.get("chapters") or []
            if isinstance(row, dict) and int(row.get("n") or 0) == number
        ),
        None,
    )
    prompt = f"""Ты строгий редактор детектива. Проверь ОДНУ главу.

Канон (убийцу до главы 13 нельзя называть убийцей):
{PREMISE.read_text(encoding="utf-8")[:1600]}

Персонажи:
{CHARACTERS.read_text(encoding="utf-8")[:1600]}

План главы:
{json.dumps(plan, ensure_ascii=False) if plan else "нет"}

Машинные флаги: {mech.get("flags") or "нет"}

Текст:
{mech["text"][:5200]}

Это детектив. Смотри: улики, ложные следы, спойлер убийцы, черновик прозы, опечатки и обрывы.
Верни СТРОГО JSON:
{{
  "score": 7,
  "plot_ok": true,
  "early_killer": false,
  "holes": [],
  "style": [],
  "canon": [],
  "verdict": "два предложения по делу"
}}
Правила списков: только конкретные замечания с цитатой или фактом.
Пустой список, если замечаний нет.
Запрещено писать «шероховатость языка» и заглушки вроде «2-4 предложения».
Не хвали. Не выдумывай дыры, которых нет в тексте."""
    raw = chat(prompt, temperature=0.15, num_predict=900, timeout=700)
    try:
        payload = json.loads(raw[raw.find("{") : raw.rfind("}") + 1])
    except (ValueError, json.JSONDecodeError):
        payload = {
            "score": 0,
            "plot_ok": False,
            "early_killer": False,
            "holes": ["модель не вернула JSON"],
            "style": [],
            "canon": [],
            "verdict": raw[:500],
        }
    return {
        "n": number,
        "title": str((plan or {}).get("title") or path.name),
        "file": path.name,
        "words": mech["words"],
        "flags": mech["flags"],
        "score": payload.get("score"),
        "plot_ok": bool(payload.get("plot_ok")),
        "early_killer": bool(payload.get("early_killer")),
        "holes": _clean_list(payload.get("holes")),
        "style": _clean_list(payload.get("style")),
        "canon": _clean_list(payload.get("canon")),
        "verdict": str(payload.get("verdict") or "").strip(),
    }


def _book_snippets() -> str:
    chunks: list[str] = []
    for path in chapter_files():
        body = path.read_text(encoding="utf-8")
        number = int(path.stem)
        if number in {1, 2, 3, 12, 13, 14}:
            chunks.append(f"### Глава {number}\n{body[:900]}\n[...]\n{body[-450:]}")
        else:
            chunks.append(f"### Глава {number}\n{body[:380]}\n[...]\n{body[-220:]}")
    return "\n\n".join(chunks)[:6200]


def score_book(data: dict, mechanical: list[dict], words: int) -> tuple[dict[str, dict[str, object]], str]:
    facts = FACTS.read_text(encoding="utf-8") if FACTS.is_file() else ""
    keys = ", ".join(item["key"] for item in CRITERIA)
    prompt = f"""Ты судья интеллектуального детектива, не болельщик. Повесть «{data.get("title")}».

{prompt_block()}

Ставь 10 только если критерий закрыт как в готовой книге. 7 — ещё черновик. Ниже 8 — нельзя публиковать.
Не завышай: локальная модель часто пишет гладко, но без улики и ложных следов.

Канон:
{(PREMISE.read_text(encoding="utf-8") if PREMISE.is_file() else "")[:1400]}

Факты:
{facts[:2200]}

Текст:
{_book_snippets()}

Верни СТРОГО JSON:
{{
  "criteria": {{
    "puzzle": {{"score": 7, "gap": "чего не хватает", "chapters": [1, 2]}},
    "fair_play": {{"score": 7, "gap": "...", "chapters": [12, 13]}},
    "red_herrings": {{"score": 7, "gap": "...", "chapters": [3]}},
    "payoff": {{"score": 7, "gap": "...", "chapters": [13, 14]}},
    "cast": {{"score": 7, "gap": "...", "chapters": [4]}},
    "prose": {{"score": 7, "gap": "...", "chapters": [2, 6]}},
    "mechanics": {{"score": 7, "gap": "...", "chapters": [2]}}
  }},
  "verdict": "четыре предложения: что ломает детектив и что править первым"
}}
Ключи только такие: {keys}. score целое 1–10. chapters — номера глав, которые надо переписать."""
    raw = chat(prompt, temperature=0.1, num_predict=900, timeout=900)
    try:
        payload = json.loads(raw[raw.find("{") : raw.rfind("}") + 1])
    except (ValueError, json.JSONDecodeError):
        payload = {}
        scores = empty_scores()
        verdict = raw[:700] or "модель не вернула JSON по критериям"
        return scores, verdict
    scores = cap_scores(parse_scores(payload), mechanical=mechanical, words=words)
    verdict = str(payload.get("verdict") or "").strip()
    return scores, verdict


def blockers_of(chapter: dict) -> list[str]:
    items: list[str] = []
    items.extend(f"машина: {flag}" for flag in chapter.get("flags") or [])
    if not chapter.get("plot_ok"):
        items.append("сюжет не по плану")
    if chapter.get("early_killer"):
        items.append("ранний спойлер убийцы")
    items.extend(f"дыра: {item}" for item in chapter.get("holes") or [])
    items.extend(f"канон: {item}" for item in chapter.get("canon") or [])
    items.extend(f"язык: {item}" for item in chapter.get("style") or [] if not _is_taste(item))
    return items


def is_clean(review: dict) -> bool:
    scores = review.get("criteria") if isinstance(review.get("criteria"), dict) else {}
    return meets_bar(scores, MIN_CRITERION_SCORE)


def render_markdown(review: dict) -> str:
    lines = [
        f"# Редакторская проверка — {review.get('title') or 'повесть'}",
        "",
        f"Круг {review.get('round')}. {review.get('at')}. Модель разобрала главы в JSON.",
        "",
        f"Замечаний: {review.get('issue_count')}. Чисто: {'да' if review.get('clean') else 'нет'}.",
        f"Мин. балл по критериям: {review.get('min_score')}. Порог {MIN_CRITERION_SCORE}/10.",
        "",
        "## Семь критериев",
        "",
    ]
    for item in CRITERIA:
        row = (review.get("criteria") or {}).get(item["key"]) or {}
        score = row.get("score", "?")
        lines.append(f"- {item['title']}: {score}/10. {row.get('gap') or ''}")
    lines += [
        "",
        str(review.get("book") or ""),
        "",
        "## Машинная проверка",
        "",
    ]
    for row in review.get("mechanical") or []:
        flags = ", ".join(row.get("flags") or []) or "ок"
        lines.append(f"- {row.get('file')}: {row.get('words')} слов — {flags}")
    lines += ["", f"Слов в книге: {review.get('words')}.", "", "## По главам", ""]
    for chapter in review.get("chapters") or []:
        lines.append(f"### Глава {chapter.get('n')}. {chapter.get('title')}")
        lines.append("")
        lines.append(
            f"Оценка {chapter.get('score')}/10. План: "
            f"{'да' if chapter.get('plot_ok') else 'нет'}. "
            f"Ранний убийца: {'да' if chapter.get('early_killer') else 'нет'}."
        )
        lines.append("")
        lines.append(str(chapter.get("verdict") or ""))
        lines.append("")
        notes = blockers_of(chapter)
        if notes:
            for note in notes:
                lines.append(f"- {note}")
            lines.append("")
        else:
            lines.append("Замечаний нет.")
            lines.append("")
    return "\n".join(lines)


def run_review(*, round_n: int = 0, round_dir: Path | None = None) -> dict:
    if not OUTLINE.is_file():
        raise RuntimeError("нет bible/outline.json")
    data = load_outline()
    patch_state(status="analyze", round=round_n, message=f"круг {round_n}: машинная проверка")
    emit("analyze_start", round=round_n)
    mechanical = []
    chapters = []
    for path in chapter_files():
        mech = mechanical_chapter(path)
        mechanical.append({key: mech[key] for key in ("file", "n", "words", "flags")})
        patch_state(message=f"круг {round_n}: разбор главы {mech['n']}")
        emit("analyze_chapter", round=round_n, chapter=mech["n"])
        chapters.append(review_chapter(path, data, mech))
    patch_state(message=f"круг {round_n}: оценка по критериям детектива")
    words = sum(int(row.get("words") or 0) for row in mechanical)
    scores, book_notes = score_book(data, mechanical, words)
    issue_count = sum(len(blockers_of(chapter)) for chapter in chapters) + len(
        failing(scores, MIN_CRITERION_SCORE)
    )
    review = {
        "at": now_iso(),
        "round": round_n,
        "title": data.get("title"),
        "words": words,
        "mechanical": mechanical,
        "chapters": chapters,
        "criteria": scores,
        "min_score": min_score_of(scores),
        "book": book_notes,
        "issue_count": issue_count,
        "clean": False,
        "book_path": str(BOOK),
    }
    review["clean"] = is_clean(review)
    report = render_markdown(review)
    write(BOOK_DIR / "review" / "REPORT.md", report)
    if round_dir is not None:
        round_dir.mkdir(parents=True, exist_ok=True)
        (round_dir / "review.json").write_text(
            json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (round_dir / "REPORT.md").write_text(report, encoding="utf-8")
    emit("analyze_done", round=round_n, issue_count=issue_count, clean=review["clean"])
    return review


def main() -> None:
    review = run_review(round_n=0, round_dir=BOOK_DIR / "review")
    print(f"замечаний {review['issue_count']}, чисто {review['clean']}", flush=True)


if __name__ == "__main__":
    main()
