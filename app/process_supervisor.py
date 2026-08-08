"""Supervisore minimale per separare HTTP e automazioni sul servizio Render.

Render avvia un unico comando per il web service.  Il supervisore crea due
processi indipendenti nello stesso container:

* Uvicorn serve esclusivamente le richieste HTTP;
* ``app.scheduler_runner`` esegue Drive, Gmail, OCR e job periodici.

In questo modo una scansione lenta non blocca l'event loop della Prima Nota.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class ChildSpec:
    name: str
    command: tuple[str, ...]
    environment: dict[str, str]


def build_child_specs(
    environ: Mapping[str, str] | None = None,
) -> tuple[ChildSpec, ChildSpec]:
    """Costruisce comandi e ambienti senza avviare processi (testabile)."""

    base = dict(environ or os.environ)
    base.setdefault("PYTHONUNBUFFERED", "1")
    port = base.get("PORT", "8000")

    web_env = dict(base)
    web_env.update({"PROCESS_ROLE": "web", "ENABLE_SCHEDULER": "false"})
    scheduler_env = dict(base)
    scheduler_env.update(
        {"PROCESS_ROLE": "scheduler", "ENABLE_SCHEDULER": "true"}
    )

    web = ChildSpec(
        name="web",
        command=(
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            port,
        ),
        environment=web_env,
    )
    scheduler = ChildSpec(
        name="scheduler",
        command=(sys.executable, "-m", "app.scheduler_runner"),
        environment=scheduler_env,
    )
    return web, scheduler


def _start(spec: ChildSpec) -> subprocess.Popen:
    print(f"[supervisor] avvio processo {spec.name}", flush=True)
    return subprocess.Popen(spec.command, env=spec.environment)


def _stop(process: subprocess.Popen | None, name: str) -> None:
    if process is None or process.poll() is not None:
        return
    print(f"[supervisor] arresto processo {name}", flush=True)
    process.terminate()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main() -> int:
    """Mantiene il web disponibile e riavvia solo lo scheduler se cade."""

    web_spec, scheduler_spec = build_child_specs()
    web: subprocess.Popen | None = None
    scheduler: subprocess.Popen | None = None
    stopping = False
    scheduler_restart_at = 0.0
    scheduler_failures = 0

    def _request_stop(*_args) -> None:
        nonlocal stopping
        stopping = True

    for signame in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, signame, None)
        if sig is not None:
            try:
                signal.signal(sig, _request_stop)
            except (OSError, RuntimeError, ValueError):
                pass

    try:
        web = _start(web_spec)
        scheduler = _start(scheduler_spec)

        while not stopping:
            web_code = web.poll()
            if web_code is not None:
                print(
                    f"[supervisor] processo web terminato con codice {web_code}",
                    file=sys.stderr,
                    flush=True,
                )
                return web_code or 1

            scheduler_code = scheduler.poll() if scheduler else None
            if scheduler is not None and scheduler_code is not None:
                scheduler_failures += 1
                delay = min(60, 5 * scheduler_failures)
                scheduler_restart_at = time.monotonic() + delay
                print(
                    "[supervisor] scheduler terminato con codice "
                    f"{scheduler_code}; nuovo tentativo tra {delay}s",
                    file=sys.stderr,
                    flush=True,
                )
                scheduler = None

            if scheduler is None and time.monotonic() >= scheduler_restart_at:
                scheduler = _start(scheduler_spec)

            time.sleep(0.5)
        return 0
    finally:
        _stop(scheduler, "scheduler")
        _stop(web, "web")


if __name__ == "__main__":
    raise SystemExit(main())
