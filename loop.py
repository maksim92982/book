from __future__ import annotations

from analyze import blockers_of, is_clean, run_review
from config import MAX_ROUNDS, MIN_CRITERION_SCORE, ROUNDS, TARGET_CRITERION_SCORE
from correct import apply_review
from git_sync import push_snapshot
from logs_util import emit, load_state, patch_state, save_state
from notify import notify_round, send_job_chat


def next_round() -> int:
    existing = [int(path.name) for path in ROUNDS.glob("*") if path.name.isdigit()]
    return (max(existing) + 1) if existing else 1


def run() -> None:
    ROUNDS.mkdir(parents=True, exist_ok=True)
    state = load_state()
    if "rounds" not in state or not isinstance(state["rounds"], list):
        state["rounds"] = []
    save_state(state)
    emit("loop_start", max_rounds=MAX_ROUNDS, min_score=MIN_CRITERION_SCORE, target=TARGET_CRITERION_SCORE)
    while True:
        round_n = next_round()
        if round_n > MAX_ROUNDS:
            patch_state(
                status="stopped",
                message=f"достигнут лимит кругов {MAX_ROUNDS}",
            )
            emit("loop_stop", reason="max_rounds")
            notify_round(
                load_state().get("last_review") or {"n": round_n, "criteria": {}},
                footer=f"Остановлен: лимит кругов {MAX_ROUNDS}.",
            )
            return
        round_dir = ROUNDS / f"{round_n:03d}"
        round_dir.mkdir(parents=True, exist_ok=True)
        patch_state(status="analyze", round=round_n, message=f"круг {round_n}: разбор")
        review = run_review(round_n=round_n, round_dir=round_dir)
        criteria = review.get("criteria") or {}
        summary = {
            "n": round_n,
            "at": review.get("at"),
            "issue_count": review.get("issue_count"),
            "clean": review.get("clean"),
            "words": review.get("words"),
            "min_score": review.get("min_score"),
            "criteria": {
                key: {"score": row.get("score"), "title": row.get("title"), "gap": row.get("gap")}
                for key, row in criteria.items()
            },
            "issues": [
                {
                    "chapter": chapter.get("n"),
                    "title": chapter.get("title"),
                    "notes": blockers_of(chapter),
                    "score": chapter.get("score"),
                }
                for chapter in review.get("chapters") or []
                if blockers_of(chapter)
            ],
        }
        state = load_state()
        rounds = [row for row in state.get("rounds") or [] if int(row.get("n") or 0) != round_n]
        rounds.append(summary)
        patch_state(
            rounds=rounds,
            last_review=summary,
            issue_count=review.get("issue_count"),
            min_score=review.get("min_score"),
            criteria=summary["criteria"],
        )
        if is_clean(review):
            patch_state(
                status="done",
                round=round_n,
                message=(
                    f"круг {round_n}: все критерии ≥ {MIN_CRITERION_SCORE}/10 "
                    f"(мин {review.get('min_score')})"
                ),
            )
            emit("loop_done", round=round_n, min_score=review.get("min_score"))
            notify_round(summary, footer="Готово: все критерии ≥ 8. Цикл остановлен.")
            push_snapshot("книга готова")
            return
        notify_round(summary)
        push_snapshot(f"круг {round_n}: разбор")
        apply_review(review, round_dir)
        patch_state(message=f"круг {round_n}: правки записаны, будет новый разбор")
        push_snapshot(f"круг {round_n}: правки")


def main() -> None:
    try:
        run()
    except Exception as error:
        emit("loop_error", error=str(error))
        patch_state(status="error", message=str(error))
        send_job_chat(f"Круги разбора\nошибка цикла: {error}")
        raise


if __name__ == "__main__":
    main()
