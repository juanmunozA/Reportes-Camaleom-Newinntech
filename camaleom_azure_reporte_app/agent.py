from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

DEFAULT_INTERVAL_SECONDS = int(os.getenv("AGENT_INTERVAL_SECONDS", "900"))
DEFAULT_LOG_DIR = Path(os.getenv("AGENT_LOG_DIR", str(Path.cwd() / "agent_logs"))).resolve()

STOP = False


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def write_line(path: Path, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(f"[{now_iso()}] {message}\n")


def write_status(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def acquire_lock(lock_file: Path):
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(lock_file), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return None
    os.write(fd, str(os.getpid()).encode("utf-8"))
    return fd


def release_lock(fd, lock_file: Path) -> None:
    if fd is not None:
        os.close(fd)
    try:
        lock_file.unlink()
    except FileNotFoundError:
        pass


def handle_stop(signum, frame) -> None:
    global STOP
    STOP = True


def run_once(command: list[str], log_file: Path, status_file: Path) -> int:
    started = time.perf_counter()
    write_line(log_file, f"RUN start: {' '.join(command)}")
    write_status(status_file, {"state": "running", "started_at": now_iso(), "command": command})

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    proc = subprocess.Popen(
        command,
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
        print(clean, flush=True)
        write_line(log_file, clean)
        last_lines.append(clean)
        if len(last_lines) > 40:
            last_lines = last_lines[-40:]
        write_status(
            status_file,
            {
                "state": "running",
                "pid": proc.pid,
                "updated_at": now_iso(),
                "command": command,
                "last_line": clean,
                "last_lines": last_lines[-10:],
            },
        )

    returncode = proc.wait()
    duration_ms = int((time.perf_counter() - started) * 1000)
    state = "ok" if returncode == 0 else "failed"
    write_status(
        status_file,
        {
            "state": state,
            "returncode": returncode,
            "duration_ms": duration_ms,
            "finished_at": now_iso(),
            "command": command,
            "last_lines": last_lines[-20:],
        },
    )
    write_line(log_file, f"RUN {state}: returncode={returncode} duration_ms={duration_ms}")
    return returncode

def sleep_interruptible(seconds: int) -> None:
    deadline = time.time() + seconds
    while not STOP and time.time() < deadline:
        time.sleep(min(1, max(0, deadline - time.time())))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Agente persistente para Camaleom + Azure DevOps.")
    parser.add_argument("--interval-segundos", type=int, default=DEFAULT_INTERVAL_SECONDS, help="Cada cuantos segundos vuelve a ejecutar. Default: 900.")
    parser.add_argument("--interval-minutos", type=float, help="Atajo para definir intervalo en minutos.")
    parser.add_argument("--once", action="store_true", help="Ejecuta una vez y termina.")
    parser.add_argument("--python", default=sys.executable, help="Python que ejecuta el reporte.")
    parser.add_argument("--script", default=str(Path(__file__).resolve().parents[1] / "camaleom_azure_reporte.py"), help="Script principal del reporte.")
    parser.add_argument("--log-file", default=str(DEFAULT_LOG_DIR / "agent.log"), help="Archivo de log del agente.")
    parser.add_argument("--status-file", default=str(DEFAULT_LOG_DIR / "status.json"), help="Estado actual/ultimo run en JSON.")
    parser.add_argument("--lock-file", default=str(DEFAULT_LOG_DIR / "agent.lock"), help="Lock para evitar agentes duplicados.")
    parser.add_argument("reporte_args", nargs=argparse.REMAINDER, help="Argumentos para camaleom_azure_reporte.py. Usa -- para separarlos.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    signal.signal(signal.SIGINT, handle_stop)
    signal.signal(signal.SIGTERM, handle_stop)

    args = parse_args(argv)
    interval = int(args.interval_minutos * 60) if args.interval_minutos else args.interval_segundos
    interval = max(5, interval)

    log_file = Path(args.log_file).resolve()
    status_file = Path(args.status_file).resolve()
    lock_file = Path(args.lock_file).resolve()

    fd = acquire_lock(lock_file)
    if fd is None:
        write_line(log_file, f"Agente ya esta corriendo. Lock: {lock_file}")
        return 2

    reporte_args = list(args.reporte_args)
    if reporte_args and reporte_args[0] == "--":
        reporte_args = reporte_args[1:]
    command = [args.python, args.script, *reporte_args]

    try:
        write_line(log_file, f"Agente iniciado. interval={interval}s")
        while not STOP:
            run_once(command, log_file, status_file)
            if args.once:
                break
            write_status(status_file, {"state": "waiting", "next_run_in_seconds": interval, "updated_at": now_iso(), "command": command})
            sleep_interruptible(interval)
        write_line(log_file, "Agente detenido.")
        return 0
    finally:
        release_lock(fd, lock_file)


if __name__ == "__main__":
    raise SystemExit(main())
