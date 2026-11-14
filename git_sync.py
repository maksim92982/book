from __future__ import annotations

import subprocess

from config import (
    BOOK_SLUG,
    CATALOG_PATH,
    GIT_BRANCH,
    GIT_REMOTE,
    GIT_SYNC,
    ROOT,
    default_catalog,
    load_catalog,
    save_catalog,
)
from logs_util import emit, load_state, write_public_status


def _run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=ROOT,
        check=check,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )


def write_status() -> None:
    catalog = load_catalog()
    if catalog.get("current") != BOOK_SLUG:
        catalog["current"] = BOOK_SLUG
    if not any(str(row.get("id")) == BOOK_SLUG for row in catalog.get("books") or [] if isinstance(row, dict)):
        books = list(catalog.get("books") or [])
        books.append({"id": BOOK_SLUG, "number": len(books) + 1, "title": BOOK_SLUG, "genre": ""})
        catalog["books"] = books
    save_catalog(catalog)
    write_public_status()


def _ensure_repo() -> None:
    git_dir = ROOT / ".git"
    if not git_dir.is_dir():
        _run(["git", "init", "-b", GIT_BRANCH])
        emit("git_init", branch=GIT_BRANCH)
    remotes = _run(["git", "remote"], check=False).stdout.split()
    if "origin" not in remotes:
        _run(["git", "remote", "add", "origin", GIT_REMOTE])
        emit("git_remote", remote=GIT_REMOTE)
    else:
        current = _run(["git", "remote", "get-url", "origin"], check=False).stdout.strip()
        if current != GIT_REMOTE:
            _run(["git", "remote", "set-url", "origin", GIT_REMOTE])
    has_head = _run(["git", "rev-parse", "--verify", "HEAD"], check=False).returncode == 0
    if not has_head:
        _run(["git", "fetch", "origin"], check=False)
        checkout = _run(["git", "checkout", "-B", GIT_BRANCH, f"origin/{GIT_BRANCH}"], check=False)
        if checkout.returncode == 0:
            emit("git_checkout", branch=GIT_BRANCH)


def push_snapshot(reason: str) -> None:
    if not GIT_SYNC:
        emit("git_skip", reason="LITRESS_GIT_SYNC=0")
        return
    write_status()
    try:
        _ensure_repo()
        _run(["git", "add", "-A"])
        pending = _run(["git", "status", "--porcelain"], check=False)
        if not pending.stdout.strip():
            emit("git_unchanged", reason=reason)
            return
        state = load_state()
        round_n = state.get("round") or 0
        min_score = state.get("min_score")
        message = (
            f"книга {BOOK_SLUG}: {reason}; круг {round_n}"
            + (f"; мин {min_score}/10" if min_score is not None else "")
        )
        _run(["git", "commit", "-m", message])
        _run(["git", "pull", "origin", GIT_BRANCH, "--no-edit"], check=False)
        push = _run(["git", "push", "-u", "origin", f"HEAD:{GIT_BRANCH}"], check=False)
        if push.returncode != 0:
            emit("git_push_failed", reason=reason, error=(push.stderr or push.stdout)[-800:])
            return
        emit("git_pushed", reason=reason, message=message)
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or str(error))[-800:]
        emit("git_error", reason=reason, error=detail)


def main() -> None:
    if not CATALOG_PATH.is_file():
        save_catalog(default_catalog())
    push_snapshot("ручной снимок")


if __name__ == "__main__":
    main()
