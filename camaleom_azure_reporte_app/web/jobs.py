from __future__ import annotations

import os
import subprocess
import sys
import threading
import uuid
from pathlib import Path
from typing import Any

from ..config import OUT_DIR

_JOBS: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()

APP_ROOT = Path(__file__).resolve().parents[2]


def _set(job_id: str, **kwargs) -> None:
    with _LOCK:
        _JOBS.setdefault(job_id, {}).update(kwargs)


def get_job(job_id: str) -> dict[str, Any] | None:
    with _LOCK:
        job = _JOBS.get(job_id)
        return dict(job) if job else None


def _run(job_id: str, command: list[str], env: dict[str, str], nombre_salida: str) -> None:
    _set(job_id, state="running", last_lines=[])
    try:
        proc = subprocess.Popen(
            command,
            cwd=str(APP_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        )
        last_lines: list[str] = []
        assert proc.stdout is not None
        for line in proc.stdout:
            clean = line.rstrip()
            if not clean:
                continue
            last_lines.append(clean)
            if len(last_lines) > 60:
                last_lines = last_lines[-60:]
            _set(job_id, last_lines=list(last_lines))
        returncode = proc.wait()
    except Exception as exc:
        _set(job_id, state="failed", error=str(exc))
        return

    if returncode != 0:
        _set(job_id, state="failed", error=f"El proceso termino con codigo {returncode}")
        return

    html_path = OUT_DIR / f"{nombre_salida}.html"
    xlsx_path = OUT_DIR / f"{nombre_salida}.xlsx"
    if not html_path.exists():
        _set(job_id, state="failed", error="El reporte termino pero no encontre el archivo HTML generado.")
        return

    _set(job_id, state="ok", html_path=str(html_path), xlsx_path=str(xlsx_path) if xlsx_path.exists() else None)


def start_job(
    sprints: str,
    fecha_inicio: str,
    fecha_fin: str,
    camaleom_fecha_inicio: str,
    camaleom_fecha_fin: str,
    camaleom_user: str,
    camaleom_pass: str,
    azure_org: str,
    azure_project: str,
    azure_team: str,
    azure_full_name: str,
) -> str:
    job_id = uuid.uuid4().hex
    nombre_salida = f"reporte_integrado_{fecha_inicio}_a_{fecha_fin}_sprint_{sprints.replace(',', '-')}"

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["CAMALEOM_USER"] = camaleom_user
    env["CAMALEOM_PASS"] = camaleom_pass
    env["AZURE_ORG"] = azure_org
    env["AZURE_PROJECT"] = azure_project
    env["AZURE_TEAM"] = azure_team
    env["AZURE_ASSIGNED_TO_NAME"] = azure_full_name
    env["HEADLESS"] = "true"

    command = [
        sys.executable, "-m", "camaleom_azure_reporte_app",
        "--sprint", sprints,
        "--fecha-inicio", fecha_inicio,
        "--fecha-fin", fecha_fin,
        "--camaleom-creacion-inicio", camaleom_fecha_inicio,
        "--camaleom-creacion-fin", camaleom_fecha_fin,
        "--sin-browser-azure",
    ]

    _set(job_id, state="queued", last_lines=[])
    thread = threading.Thread(target=_run, args=(job_id, command, env, nombre_salida), daemon=True)
    thread.start()
    return job_id
