import datetime
import os
import sys
import threading
import time
import traceback
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.management import call_command
from django.db import close_old_connections
from django.db.utils import OperationalError


_thread_started = False
_lock = threading.Lock()


def _should_start() -> bool:
    if "runserver" not in sys.argv:
        return False

    return os.getenv("RUN_MAIN") == "true"


def start_noon_flow_scheduler() -> None:
    global _thread_started

    if not _should_start():
        return

    with _lock:
        if _thread_started:
            return
        _thread_started = True

    thread = threading.Thread(target=_loop, name="acqm-noon-flow", daemon=True)
    thread.start()


def _loop() -> None:
    tz = ZoneInfo(getattr(settings, "TIME_ZONE", "America/Sao_Paulo"))
    run_times = [(13, 55), (17, 0)]

    while True:
        now = datetime.datetime.now(tz=tz)
        candidates: list[datetime.datetime] = []
        for hour, minute in run_times:
            candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if candidate <= now:
                candidate = candidate + datetime.timedelta(days=1)
            candidates.append(candidate)

        next_run = min(candidates)

        wait_seconds = int((next_run - now).total_seconds())
        print(
            f"[scheduler] agora={now.isoformat()} proxima_execucao={next_run.isoformat()} espera={wait_seconds}s",
            flush=True,
        )
        time.sleep(max(1, wait_seconds))

        print("[scheduler] disparando run_daily_flow", flush=True)
        try:
            close_old_connections()
            call_command("run_daily_flow")
        except OperationalError as exc:
            print(
                f"[scheduler] erro de banco durante run_daily_flow: {exc}",
                flush=True,
            )
            traceback.print_exc()
            time.sleep(10)
        except Exception as exc:
            print(f"[scheduler] erro inesperado no run_daily_flow: {exc}", flush=True)
            traceback.print_exc()
            time.sleep(5)
        finally:
            close_old_connections()

