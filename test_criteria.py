from __future__ import annotations

from criteria import cap_scores, chapters_to_fix, meets_bar, parse_scores


def _ok() -> dict:
    return {
        "criteria": {
            "puzzle": {"score": 8, "gap": "ок", "chapters": []},
            "fair_play": {"score": 9, "gap": "ок", "chapters": []},
            "red_herrings": {"score": 8, "gap": "ок", "chapters": []},
            "payoff": {"score": 10, "gap": "ок", "chapters": []},
            "cast": {"score": 8, "gap": "ок", "chapters": []},
            "prose": {"score": 8, "gap": "ок", "chapters": []},
            "mechanics": {"score": 8, "gap": "ок", "chapters": []},
        }
    }


def test_parse_and_bar() -> None:
    scores = parse_scores(_ok())
    assert meets_bar(scores, 8)
    scores["mechanics"]["score"] = 7
    assert not meets_bar(scores, 8)


def test_missing_mechanics_blocks() -> None:
    payload = _ok()
    del payload["criteria"]["mechanics"]
    scores = parse_scores(payload)
    assert int(scores["mechanics"]["score"]) == 0
    assert not meets_bar(scores, 8)


def test_short_chapter_caps_mechanics() -> None:
    scores = parse_scores(
        {
            "prose": {"score": 10, "gap": "хвалит", "chapters": []},
            "payoff": {"score": 9, "gap": "", "chapters": [14]},
            "mechanics": {"score": 10, "gap": "хвалит", "chapters": []},
        }
    )
    capped = cap_scores(
        scores,
        mechanical=[{"n": 2, "words": 200, "flags": ["короткая (200 слов, минимум 450)"]}],
        words=9000,
    )
    assert int(capped["prose"]["score"]) <= 6
    assert int(capped["mechanics"]["score"]) <= 5
    assert 2 in capped["mechanics"]["chapters"]
    assert not meets_bar(capped, 8)


def test_cjk_caps_mechanics() -> None:
    scores = parse_scores(_ok())
    scores["mechanics"]["score"] = 10
    capped = cap_scores(
        scores,
        mechanical=[{"n": 4, "words": 500, "flags": ["китайские иероглифы"]}],
        words=9000,
    )
    assert int(capped["mechanics"]["score"]) <= 2
    assert not meets_bar(capped, 8)


def test_payoff_rewrites_finale() -> None:
    scores = parse_scores(
        {
            "puzzle": {"score": 8, "gap": "", "chapters": []},
            "fair_play": {"score": 8, "gap": "", "chapters": []},
            "red_herrings": {"score": 8, "gap": "", "chapters": []},
            "payoff": {"score": 5, "gap": "мотив ниоткуда", "chapters": [13]},
            "cast": {"score": 8, "gap": "", "chapters": []},
            "prose": {"score": 8, "gap": "", "chapters": []},
            "mechanics": {"score": 8, "gap": "", "chapters": []},
        }
    )
    needed = chapters_to_fix(scores, 8, 14)
    assert {12, 13, 14} <= needed
    assert 1 not in needed


if __name__ == "__main__":
    test_parse_and_bar()
    test_missing_mechanics_blocks()
    test_short_chapter_caps_mechanics()
    test_cjk_caps_mechanics()
    test_payoff_rewrites_finale()
    print("ok")
