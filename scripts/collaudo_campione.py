"""Replay locale di uno snapshot: nessuna connessione o scrittura di produzione.

Uso: python scripts/collaudo_campione.py snapshot.json risultato.json
Lo snapshot contiene invoices, payslips, payments e period. Non va committato.
"""

import asyncio
import json
import sys
import socket
from pathlib import Path
from collections import Counter
import os
import logging

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.collaudo_isolato import ambiente_isolato

isolated = ambiente_isolato(os.environ)
os.environ.clear()
os.environ.update(isolated)
os.environ["LIBRO_GIORNALE_ATTIVO"] = "true"
os.environ["LOTTI_TEST_MEMORY"] = "1"
os.environ["PYTHON_DOTENV_DISABLED"] = "1"
logging.disable(logging.CRITICAL)


def denied(*args, **kwargs):
    raise RuntimeError("Rete vietata nel replay del campione")


socket.socket.connect = denied
socket.socket.connect_ex = denied

from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services import registrazione_contabile as ledger
from app.services.payment_allocation_validator import to_cents
from app.services.posizione_dipendente import componi_movimenti, ZERO
from app.services.ripartizione_salari import ripartisci_movimenti


async def replay(snapshot):
    db = ClientArchivioMemoria()["collaudo_campione"]
    invoices = snapshot.get("invoices") or []
    for i in invoices:
        await db["invoices"].insert_one(i)
    states = Counter()
    failures = Counter()
    for i in invoices:
        try:
            r = await ledger.registra_fattura(db, dict(i))
            states[r.get("stato", "senza_stato")] += 1
        except Exception as e:
            failures[type(e).__name__] += 1
    before = await db["movimenti_contabili"].count_documents({})
    for i in invoices:
        try:
            await ledger.registra_fattura(db, dict(i))
        except Exception:
            pass
    rows = await db["movimenti_contabili"].find({}).to_list(None)
    bad = sum(
        sum(to_cents(r.get("dare")) for r in m.get("righe", []))
        != sum(to_cents(r.get("avere")) for r in m.get("righe", []))
        for m in rows
    )
    keys = [m.get("idempotency_key") for m in rows if m.get("idempotency_key")]
    pays = snapshot.get("payslips") or []
    payments = snapshot.get("payments") or []
    ids = {p.get("dipendente_id") for p in pays + payments}
    salary_errors = 0
    total_payment = ZERO
    for ident in ids:
        p = [d for d in pays if d.get("dipendente_id") == ident]
        e = [d for d in payments if d.get("dipendente_id") == ident]
        movements = componi_movimenti(
            paghe=[], esiti=e, cedolini=p, acconti=[], conciliazioni=[]
        )["registro"]
        split = ripartisci_movimenti(movements)["movimenti"]
        original = sum((m.get("avere") or ZERO for m in movements), ZERO)
        allocated = sum((m.get("avere") or ZERO for m in split), ZERO)
        total_payment += original
        if original != allocated:
            salary_errors += 1
    return {
        "period": snapshot["period"],
        "source": {
            "invoices": len(invoices),
            "payslips": len(pays),
            "payments": len(payments),
        },
        "ledger": {
            "states": dict(states),
            "errors": dict(failures),
            "entries": len(rows),
            "unbalanced_entries": bad,
            "duplicates_on_replay": len(rows) - before,
            "duplicate_keys": len(keys) - len(set(keys)),
        },
        "salary": {
            "payment_total": str(total_payment),
            "split_conservation_errors": salary_errors,
        },
        "production_writes": 0,
    }


if __name__ == "__main__":
    report = asyncio.run(replay(json.loads(Path(sys.argv[1]).read_text())))
    Path(sys.argv[2]).write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
