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

PREV_TAIL_CHARS = 1800
NEXT_HEAD_CHARS = 700


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


def chapter_path(number: int) -> Path:
    return CHAPTERS / f"{number:02d}.md"


def read_tail(number: int, *, chars: int = PREV_TAIL_CHARS) -> str:
    path = chapter_path(number)
    if number < 1 or not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8").strip()
    if len(text) <= chars:
        return text
    return text[-chars:]


def read_head(number: int, *, chars: int = NEXT_HEAD_CHARS) -> str:
    path = chapter_path(number)
    if number < 1 or not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8").strip()
    return text[:chars]


def will_rewrite(chapter: dict, needed: set[int]) -> bool:
    number = int(chapter["n"])
    return number in needed or bool(blockers_of(chapter))


def correct_chapter(
    chapter: dict,
    data: dict,
    round_dir: Path,
    extra_notes: list[str] | None = None,
    *,
    prev_tail: str = "",
    next_head: str = "",
) -> dict:
    number = int(chapter["n"])
    notes = blockers_of(chapter) + list(extra_notes or [])
    src = chapter_path(number)
    before_dir = round_dir / "before"
    before_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, before_dir / src.name)
    if not notes:
        return {"n": number, "changed": False, "notes": []}
    text = src.read_text(encoding="utf-8")
    plan = _plan(data, number)
    bridge = ""
    if prev_tail:
        bridge += (
            f"\nХвост предыдущей главы {number - 1} (уже актуальный текст). "
            "Начни эту главу из той же ситуации, места и момента. "
            "Не прыгай в другой день и не делай вид, что предыдущей сцены не было.\n"
            f"{prev_tail}\n"
        )
    if next_head:
        bridge += (
            f"\nНачало следующей главы {number + 1} трогать не будут. "
            "Закончи текущую главу так, чтобы это начало осталось логичным продолжением.\n"
            f"{next_head}\n"
        )
    prompt = f"""Ты корректор детективной повести. Перепиши главу целиком на русском.

Это детектив, не черновик. Нужны улика в кадре, ложный след, живая сцена.
Нельзя:
- менять имена, убийцу, канон
- называть убийцу до главы 13
- писать китайский, служебные фразы, html, markdown-списки внутри сцен
- оставлять короче {MIN_CHAPTER_WORDS} слов
- оставлять опечатки, обрыв на полуслове, латиницу внутри русского слова
- повторять «кивнул и пошёл» без нового факта
- рвать сюжет с соседними главами

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
{bridge}
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
    chapters = sorted(review.get("chapters") or [], key=lambda row: int(row.get("n") or 0))
    needed = chapters_to_fix(scores, MIN_CRITERION_SCORE, len(chapters))
    to_fix = {int(row["n"]) for row in chapters if will_rewrite(row, needed)}
    results = []
    for chapter in chapters:
        number = int(chapter["n"])
        extra = criterion_notes(review, number)
        if number not in to_fix:
            results.append({"n": number, "changed": False, "notes": []})
            continue
        prev_tail = read_tail(number - 1) if number > 1 else ""
        next_head = ""
        if (number + 1) not in to_fix:
            next_head = read_head(number + 1)
        results.append(
            correct_chapter(
                chapter,
                data,
                round_dir,
                extra,
                prev_tail=prev_tail,
                next_head=next_head,
            )
        )
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
