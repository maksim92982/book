from __future__ import annotations

import sys
from pathlib import Path

_SHARED = Path(__file__).resolve().parents[1] / "shared"
if _SHARED.is_dir() and str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

from quality.mechanics import CRITERION as MECHANICS_CRITERION
from quality.mechanics import hard_score as mechanics_hard_score

# Шкала 1–10. Цикл не останавливается, пока каждый критерий < MIN_SCORE.
# 8 — «можно читать как повесть, не черновик». 10 — плотный детектив без дыр.

CRITERIA: tuple[dict[str, str], ...] = (
    {
        "key": "puzzle",
        "title": "Загадка и ставка",
        "rule": (
            "Есть конкретное преступление, понятно что поставлено на карту, "
            "читатель хочет узнать кто и зачем. Нет преступления «вообще» и пустых разговоров вместо дела."
        ),
    },
    {
        "key": "fair_play",
        "title": "Честная игра",
        "rule": (
            "До разоблачения читатель видит улики, которыми потом объясняется вина. "
            "Нельзя вытащить убийцу и мотив из ниоткуда в последней главе. "
            "Убийцу нельзя прямо назвать убийцей до главы 13."
        ),
    },
    {
        "key": "red_herrings",
        "title": "Ложные следы",
        "rule": (
            "Есть хотя бы один правдоподобный другой виновный или ложная версия, "
            "которую герой всерьёз проверяет. Подозреваемые не картон. "
            "Ложный след не должен противоречить уже показанным фактам."
        ),
    },
    {
        "key": "payoff",
        "title": "Разоблачение",
        "rule": (
            "Финал собирает средство, мотив и возможность. Одно решение, без «это сделал кто-то ещё». "
            "Признание/улика опирается на ранее показанный предмет или факт."
        ),
    },
    {
        "key": "cast",
        "title": "Персонажи и канон",
        "rule": (
            "Имена, роли и факты не прыгают. Корин — следователь-переводчик, не другой человек. "
            "Вукич, Марина, Милош, Стоичев различимы по речи и поступкам."
        ),
    },
    {
        "key": "prose",
        "title": "Готовая проза",
        "rule": (
            "Не черновик: законченные сцены, живой русский, мало повторов «кивнул/пошёл/понял». "
            "Канцелярит генератора и пустые кивки без нового факта — это ещё не книга."
        ),
    },
    MECHANICS_CRITERION,
)

CRITERION_KEYS = tuple(item["key"] for item in CRITERIA)


def empty_scores() -> dict[str, dict[str, object]]:
    return {
        item["key"]: {"score": 0, "gap": "ещё не считали", "chapters": [], "title": item["title"]}
        for item in CRITERIA
    }


def _as_int_score(raw: object) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 0
    return max(0, min(10, value))


def parse_scores(payload: object) -> dict[str, dict[str, object]]:
    rows = payload if isinstance(payload, dict) else {}
    nested = rows.get("criteria") if isinstance(rows.get("criteria"), dict) else rows
    result = empty_scores()
    for item in CRITERIA:
        key = item["key"]
        block = nested.get(key) if isinstance(nested, dict) else None
        if not isinstance(block, dict):
            continue
        chapters: list[int] = []
        for number in block.get("chapters") or []:
            try:
                chapters.append(int(number))
            except (TypeError, ValueError):
                continue
        result[key] = {
            "score": _as_int_score(block.get("score")),
            "gap": str(block.get("gap") or "").strip() or "нет пояснения",
            "chapters": chapters,
            "title": item["title"],
        }
    return result


def _mechanics_flags(mechanical: list[dict]) -> list[tuple[int, str]]:
    rows: list[tuple[int, str]] = []
    for row in mechanical:
        number = int(row.get("n") or 0)
        for flag in row.get("flags") or []:
            text = str(flag)
            if "спойлер" in text or "убийца" in text:
                continue
            rows.append((number, text))
    return rows


def cap_scores(
    scores: dict[str, dict[str, object]],
    *,
    mechanical: list[dict],
    words: int,
) -> dict[str, dict[str, object]]:
    flags = [str(flag) for row in mechanical for flag in (row.get("flags") or [])]
    blob = " ".join(flags)
    if any("короткая" in flag for flag in flags):
        scores["prose"]["score"] = min(int(scores["prose"]["score"]), 6)
        scores["prose"]["gap"] = "есть главы короче минимума слов"
    if "спойлер" in blob or "убийца" in blob:
        scores["fair_play"]["score"] = min(int(scores["fair_play"]["score"]), 4)
        scores["fair_play"]["gap"] = "ранний спойлер убийцы"
    if words < 8000:
        scores["prose"]["score"] = min(int(scores["prose"]["score"]), 6)
        if not str(scores["prose"].get("gap") or "").strip():
            scores["prose"]["gap"] = f"книга короткая: {words} слов"
    last_words = [int(row.get("words") or 0) for row in mechanical if int(row.get("n") or 0) >= 12]
    if last_words and min(last_words) < 450:
        scores["payoff"]["score"] = min(int(scores["payoff"]["score"]), 5)
        scores["payoff"]["gap"] = "финальные главы слишком короткие для разоблачения"

    mech_flags = _mechanics_flags(mechanical)
    chapters: list[int] = []
    messages: list[str] = []
    for number, flag in mech_flags:
        if number:
            chapters.append(number)
        messages.append(flag)
    extra = [6] if words < 8000 else []
    hard, gaps = mechanics_hard_score(messages, extra_caps=extra)
    if words < 8000 and "книга короткая" not in " ".join(gaps):
        gaps.append(f"книга короткая: {words} слов")
    scores["mechanics"]["score"] = min(int(scores["mechanics"]["score"]), hard)
    if gaps:
        scores["mechanics"]["gap"] = "; ".join(gaps)
        scores["mechanics"]["chapters"] = sorted(set(chapters))
    return scores


def min_score_of(scores: dict[str, dict[str, object]]) -> int:
    if not scores:
        return 0
    return min(int(row.get("score") or 0) for row in scores.values())


def failing(scores: dict[str, dict[str, object]], floor: int) -> list[dict[str, object]]:
    return [
        {"key": key, **row}
        for key, row in scores.items()
        if int(row.get("score") or 0) < floor
    ]


def meets_bar(scores: dict[str, dict[str, object]], floor: int) -> bool:
    if len(scores) < len(CRITERIA):
        return False
    return min_score_of(scores) >= floor


def chapters_to_fix(scores: dict[str, dict[str, object]], floor: int, chapter_count: int) -> set[int]:
    needed: set[int] = set()
    weak = failing(scores, floor)
    for row in weak:
        for number in row.get("chapters") or []:
            needed.add(int(number))
    keys = {str(row["key"]) for row in weak}
    if "payoff" in keys:
        needed.update({12, 13, 14})
    if "puzzle" in keys:
        needed.update({1, 2, 3})
    if "red_herrings" in keys:
        needed.update({3, 5, 6, 8})
    if "prose" in keys or "mechanics" in keys or not needed:
        needed.update(range(1, chapter_count + 1))
    return {n for n in needed if 1 <= n <= chapter_count}


def prompt_block() -> str:
    lines = ["Семь критериев, оценка 1–10 (8 минимум для готовности, 10 цель):"]
    for item in CRITERIA:
        lines.append(f"- {item['key']} ({item['title']}): {item['rule']}")
    return "\n".join(lines)
