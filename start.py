from __future__ import annotations

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
from config import DASHBOARD_HOST, DASHBOARD_PORT
from git_sync import push_snapshot
from logs_util import emit, patch_state


def _serve() -> None:
    try:
        dashboard.main()
    except OSError as error:
        emit("dashboard_bind_failed", error=str(error), host=DASHBOARD_HOST, port=DASHBOARD_PORT)
        patch_state(message=f"дашборд не сел на {DASHBOARD_HOST}:{DASHBOARD_PORT}: {error}; цикл идёт")


def main() -> None:
    thread = threading.Thread(target=_serve, daemon=True, name="litress-dashboard")
    thread.start()
    push_snapshot("старт цикла")
    loop.main()


if __name__ == "__main__":
    main()
