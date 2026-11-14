from __future__ import annotations

import atexit
import os
import sys

"""Один процесс: дашборд + цикл разбор→правка.

Локально:
  python start.py

На VPS:
  set OLLAMA_URL=http://127.0.0.1:11434
  set DASHBOARD_HOST=0.0.0.0
  set DASHBOARD_PORT=8765
  python start.py
"""

import threading

import dashboard
import loop
from config import DASHBOARD_HOST, DASHBOARD_PORT, LOGS
from git_sync import push_snapshot
from logs_util import emit, patch_state

PID_FILE = LOGS / "pipeline.pid"


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _release_pid() -> None:
    try:
        if PID_FILE.is_file() and PID_FILE.read_text(encoding="utf-8").strip() == str(os.getpid()):
            PID_FILE.unlink()
    except OSError:
        return


def acquire_lock() -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    if PID_FILE.is_file():
        try:
            old = int(PID_FILE.read_text(encoding="utf-8").strip())
        except ValueError:
            old = 0
        if old and old != os.getpid() and _pid_alive(old):
            sys.exit(f"litress уже запущен (pid {old}); второй цикл не стартую")
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    atexit.register(_release_pid)


def _serve() -> None:
    try:
        dashboard.main()
    except OSError as error:
        emit("dashboard_bind_failed", error=str(error), host=DASHBOARD_HOST, port=DASHBOARD_PORT)
        patch_state(message=f"дашборд не сел на {DASHBOARD_HOST}:{DASHBOARD_PORT}: {error}; цикл идёт")


def main() -> None:
    acquire_lock()
    thread = threading.Thread(target=_serve, daemon=True, name="litress-dashboard")
    thread.start()
    push_snapshot("старт цикла")
    loop.main()


if __name__ == "__main__":
    main()
