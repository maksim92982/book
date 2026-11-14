from __future__ import annotations

from notify import format_round_report


def test_format_matches_dashboard() -> None:
    text = format_round_report(
        {
            "n": 4,
            "at": "2026-11-14T08:21:36+01:00",
            "min_score": 4,
            "words": 7916,
            "criteria": {
                "puzzle": {"title": "Загадка и ставка", "score": 8, "gap": "нужны более четкие улики и мотивы"},
                "fair_play": {"title": "Честная игра", "score": 4, "gap": "ранний спойлер убийцы"},
                "red_herrings": {"title": "Ложные следы", "score": 6, "gap": "не хватает правдоподобного ложного следа"},
                "payoff": {
                    "title": "Разоблачение",
                    "score": 7,
                    "gap": "недостаточно объединения улик и мотивов для финального разоблачения",
                },
                "cast": {
                    "title": "Персонажи и канон",
                    "score": 8,
                    "gap": "персонажи различимы, но можно добавить больше деталей их характера",
                },
                "prose": {"title": "Готовая проза", "score": 6, "gap": "есть главы короче минимума слов"},
                "mechanics": {"title": "Механический брак", "score": 5, "gap": "есть главы короче минимума слов"},
            },
        }
    )
    assert "круг 4 · 2026-11-14T08:21:36+01:00 · мин 4/10 · 7916 слов" in text
    assert "Честная игра: 4/10 — ранний спойлер убийцы" in text
    assert "Готовая проза: 6/10 — есть главы короче минимума слов" in text
    assert "Механический брак: 5/10" in text


if __name__ == "__main__":
    test_format_matches_dashboard()
    print("ok")
