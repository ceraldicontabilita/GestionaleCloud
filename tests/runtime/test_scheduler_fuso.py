"""Ogni CronTrigger dello scheduler dichiara il fuso Europe/Rome."""
import ast
from pathlib import Path

SORGENTE = Path(__file__).resolve().parents[2] / "app" / "scheduler.py"


def _nome(nodo):
    f = nodo.func
    return getattr(f, "id", getattr(f, "attr", ""))


def test_ogni_crontrigger_ha_il_timezone():
    albero = ast.parse(SORGENTE.read_text(encoding="utf-8"))
    senza = [
        n.lineno
        for n in ast.walk(albero)
        if isinstance(n, ast.Call)
        and _nome(n) == "CronTrigger"
        and not any(k.arg == "timezone" for k in n.keywords)
    ]
    assert not senza, f"CronTrigger senza timezone alle righe {senza}"


def test_lo_scheduler_gira_su_europe_rome():
    from app.scheduler import scheduler

    assert str(scheduler.timezone) == "Europe/Rome"
