from __future__ import annotations

import json
import shutil
from pathlib import Path

from analyze import blockers_of
from config import MIN_CHAPTER_WORDS, MIN_CRITERION_SCORE, ROUNDS
from criteria import chapters_to_fix, failing
from generate import (
    CHAPTERS,
    CHARACTERS,
    FACTS,
    OUTLINE,
    PREMISE,
    assemble,
    chat,
    write,
)
from logs_util import emit, patch_state


def _plan(data: dict, number: int) -> dict | None:
    for row in data.get("chapters") or []:
        if isinstance(row, dict) and int(row.get("n") or 0) == number:
            return row
    return None


def criterion_notes(review: dict, number: int) -> list[str]:
    notes: list[str] = []
    for row in failing(review.get("criteria") or {}, MIN_CRITERION_SCORE):
        listed = {int(n) for n in (row.get("chapters") or [])}
        if listed and number not in listed:
            continue
        notes.append(f"{row.get('title') or row.get('key')}: {row.get('score')}/10 — {row.get('gap')}")
    if review.get("book"):
        notes.append(f"судья: {review.get('book')}")
    return notes


def correct_chapter(chapter: dict, data: dict, round_dir: Path, extra_notes: list[str] | None = None) -> dict:
    number = int(chapter["n"])
    notes = blockers_of(chapter) + list(extra_notes or [])
    src = CHAPTERS / f"{number:02d}.md"
    before_dir = round_dir / "before"
    before_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, before_dir / src.name)
    if not notes:
        return {"n": number, "changed": False, "notes": []}
    text = src.read_text(encoding="utf-8")
    plan = _plan(data, number)
    prompt = f"""Ты корректор детективной повести. Перепиши главу целиком на русском.

Это детектив, не черновик. Нужны улика в кадре, ложный след, живая сцена.
Нельзя:
- менять имена, убийцу, канон
- называть убийцу до главы 13
- писать китайский, служебные фразы, markdown-списки внутри сцен
- оставлять короче {MIN_CHAPTER_WORDS} слов
- повторять «кивнул и пошёл» без нового факта

Нужно исправить замечания:
{json.dumps(notes, ensure_ascii=False, indent=2)}

Канон:
{PREMISE.read_text(encoding="utf-8")[:1400]}

Персонажи:
{CHARACTERS.read_text(encoding="utf-8")[:1400]}

План главы:
{json.dumps(plan, ensure_ascii=False) if plan else "нет"}

Факты уже случившегося:
{(FACTS.read_text(encoding="utf-8") if FACTS.is_file() else "")[:1800]}

Текущий текст:
{text[:5200]}

Верни только текст главы, первая строка: Глава {number}. {chapter.get("title") or ""}
Проза 900–1400 слов, законченные абзацы."""
    patch_state(message=f"круг {round_dir.name}: правка главы {number}")
    emit("correct_chapter", round=int(round_dir.name), chapter=number, notes=notes)
    rewritten = chat(prompt, temperature=0.45, num_predict=2200, timeout=1200)
    rewritten = rewritten.replace("```", "").strip()
    if len(rewritten.split()) < 200:
        emit("correct_skip", round=int(round_dir.name), chapter=number, reason="слишком коротко")
        return {"n": number, "changed": False, "notes": notes, "reason": "короткий ответ модели"}
    write(src, rewritten)
    write(round_dir / "after" / src.name, rewritten)
    return {"n": number, "changed": True, "notes": notes, "words": len(rewritten.split())}


def apply_review(review: dict, round_dir: Path) -> dict:
    data = json.loads(OUTLINE.read_text(encoding="utf-8"))
    patch_state(status="correct", message=f"круг {review.get('round')}: правки")
    emit("correct_start", round=review.get("round"))
    scores = review.get("criteria") if isinstance(review.get("criteria"), dict) else {}
    needed = chapters_to_fix(scores, MIN_CRITERION_SCORE, len(review.get("chapters") or []))
    results = []
    for chapter in review.get("chapters") or []:
        number = int(chapter["n"])
        extra = criterion_notes(review, number)
        if number not in needed and not blockers_of(chapter):
            results.append({"n": number, "changed": False, "notes": []})
            continue
        results.append(correct_chapter(chapter, data, round_dir, extra))
    assemble()
    payload = {
        "round": review.get("round"),
        "changed": sum(1 for row in results if row.get("changed")),
        "chapters": results,
    }
    (round_dir / "corrections.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    emit("correct_done", round=review.get("round"), changed=payload["changed"])
    return payload


def main() -> None:
    latest = sorted(ROUNDS.glob("*"))
    if not latest:
        raise SystemExit("нет кругов разбора")
    review_path = latest[-1] / "review.json"
    if not review_path.is_file():
        raise SystemExit(f"нет {review_path}")
    review = json.loads(review_path.read_text(encoding="utf-8"))
    apply_review(review, latest[-1])


if __name__ == "__main__":
    main()
