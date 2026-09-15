"""Verifica il criterio di accettazione della Fase 0 (PROMPT_CLAUDE_CODE_FASE_0.md).

SOLA LETTURA: non scrive nulla, esegue solo count_documents/find.

Controlla, per il periodo indicato (default: ultime 24 ore):
1. Nessuna riga nuova in `prima_nota_cassa` con `source` in
   {auto_metodo_fornitore, riconciliazione_ec_auto, ripara_versamenti, rapido}
   — i quattro motori spenti dalla Fase 0 che scrivevano cassa senza prova.
2. Nessun modello in `f24_unificato` che risulti "riconciliato/pagato
   automaticamente" in passato ma oggi non più riconciliato — un flip da
   riconciliato a da_pagare senza intervento umano (il sintomo descritto
   nell'audit per la quadratura F24 domenicale, punto 4).

Uso:
    python scripts/verifica_fase0.py [--dal 2026-09-15T00:00:00+00:00]

Richiede le stesse credenziali DB di produzione previste da app/config.py.
"""
import argparse
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.getcwd())

from app.database import Database  # noqa: E402

FONTI_VIETATE_CASSA = [
    "auto_metodo_fornitore",
    "riconciliazione_ec_auto",
    "ripara_versamenti",
    "rapido",
]


async def verifica_prima_nota_cassa(db, dal: str) -> dict:
    risultati = {}
    for fonte in FONTI_VIETATE_CASSA:
        risultati[fonte] = await db["prima_nota_cassa"].count_documents({
            "source": fonte,
            "created_at": {"$gte": dal},
        })
    return risultati


async def verifica_f24_flip(db) -> list:
    """F24 che portano il segno di una riconciliazione/conferma automatica
    passata (riconciliato_automaticamente o pagato_manualmente) ma oggi
    risultano non riconciliati: un flip senza intervento umano."""
    candidati = await db["f24_unificato"].find({
        "$or": [
            {"riconciliato_automaticamente": True},
            {"pagato_manualmente": True},
        ],
        "riconciliato": {"$ne": True},
    }, {"_id": 0, "id": 1, "periodo_riferimento": 1, "status": 1,
        "riconciliato": 1, "riconciliato_automaticamente": 1,
        "pagato_manualmente": 1, "updated_at": 1}).to_list(1000)
    return candidati


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dal", default=None,
        help="Timestamp ISO da cui contare (default: 24 ore fa)",
    )
    args = parser.parse_args()
    dal = args.dal or (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()

    await Database.connect_db()
    db = Database.get_db()

    print(f"Verifica Fase 0 — dal {dal}\n")

    conteggi_cassa = await verifica_prima_nota_cassa(db, dal)
    print("prima_nota_cassa, righe nuove per fonte vietata:")
    ok_cassa = True
    for fonte, conteggio in conteggi_cassa.items():
        stato = "OK" if conteggio == 0 else "VIOLAZIONE"
        if conteggio != 0:
            ok_cassa = False
        print(f"  - {fonte}: {conteggio} ({stato})")

    flip_f24 = await verifica_f24_flip(db)
    print(f"\nf24_unificato, modelli con segno di riconciliazione automatica "
          f"passata ma oggi non riconciliati: {len(flip_f24)}")
    for f in flip_f24:
        print(f"  - id={f.get('id')} periodo={f.get('periodo_riferimento')} "
              f"status={f.get('status')} updated_at={f.get('updated_at')}")

    ok = ok_cassa and not flip_f24
    print(f"\nEsito complessivo: {'OK' if ok else 'DA VERIFICARE'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
