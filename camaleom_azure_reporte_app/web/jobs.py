from __future__ import annotations

import threading
import time
import traceback
import uuid
from datetime import date
from typing import Any

from . import db, pipeline

_JOBS: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()
MAX_ATTEMPTS = 3
RETRY_WAIT_SECONDS = 5


def _set(job_id: str, **kwargs) -> None:
    with _LOCK:
        _JOBS.setdefault(job_id, {}).update(kwargs)


def get_job(job_id: str) -> dict[str, Any] | None:
    with _LOCK:
        job = _JOBS.get(job_id)
        return dict(job) if job else None


def _run(job_id: str, user_id: int, params: dict) -> None:
    lines: list[str] = []

    def log(msg: str) -> None:
        print(f"[job {job_id}] {msg}", flush=True)
        lines.append(str(msg))
        _set(job_id, last_lines=list(lines[-40:]))

    _set(job_id, state="running", last_lines=[], attempt=1, max_attempts=MAX_ATTEMPTS)
    last_error = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        _set(job_id, attempt=attempt)
        try:
            result = pipeline.ejecutar(log=log, **params)
            xlsx = result.pop("_xlsx", None)
            run_id = db.create_run(user_id, result, xlsx)
            _set(job_id, state="ok", run_id=run_id)
            log(f"Reporte listo (run {run_id}).")
            return
        except Exception as exc:
            last_error = str(exc) or exc.__class__.__name__
            print(f"[job {job_id}] intento {attempt} fallo: {last_error}", flush=True)
            traceback.print_exc()
            if attempt < MAX_ATTEMPTS:
                _set(job_id, state="retrying", error=last_error)
                time.sleep(RETRY_WAIT_SECONDS)

    _set(job_id, state="failed", error=last_error)


def start_job(user_id: int, params: dict) -> str:
    job_id = uuid.uuid4().hex
    _set(job_id, state="queued", last_lines=[], attempt=0, max_attempts=MAX_ATTEMPTS, user_id=user_id)
    thread = threading.Thread(target=_run, args=(job_id, user_id, params), daemon=True)
    thread.start()
    return job_id
