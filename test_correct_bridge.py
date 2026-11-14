from __future__ import annotations

from correct import will_rewrite


def test_will_rewrite_needed_or_flags() -> None:
    assert will_rewrite({"n": 3, "flags": []}, {3, 4})
    assert will_rewrite({"n": 5, "flags": ["обрыв главы"]}, set())
    assert not will_rewrite({"n": 2, "flags": []}, {3})


if __name__ == "__main__":
    test_will_rewrite_needed_or_flags()
    print("ok")
