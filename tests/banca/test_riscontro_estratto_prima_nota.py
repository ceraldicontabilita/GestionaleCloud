"""Stipendi, PayPal e assegni in Prima Nota: riconciliati sull'estratto ufficiale.

Titolare, 28/09/2026: «riconcilia solo paypal, stipendi, assegni: cerca gli
estratti per scrivere che l'operazione e' riconciliata». La proiezione
bancaria scriveva queste righe sempre con ``riconciliato: False``.
"""
import asyncio

from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.riscontro_estratto_prima_nota import segna_righe_riscontrate


def _run(coro):
    return asyncio.run(coro)


def _riga(rid, categoria, mov, data="2026-03-10", importo=1200.0):
    return {"id": rid, "data": data, "importo": importo, "tipo": "uscita",
            "categoria": categoria, "estratto_conto_id": mov, "riconciliato": False}


def _mov(mid, data="2026-03-10", importo=-1200.0, **extra):
    return {"id": mid, "data": data, "importo": importo, "tipo": "uscita", **extra}


def test_riga_con_movimento_dell_estratto_ufficiale_diventa_riconciliata():
    async def scenario():
        db = ClientArchivioMemoria()["riscontro"]
        await db.estratto_conto_movimenti.insert_many([
            _mov("m1", evidenza_bancaria_ufficiale=True, livello_evidenza="ufficiale",
                 source_filename_ufficiale="Estratto conto corrente_31-03-2026.pdf"),
            _mov("m2", in_attesa_estratto_ufficiale=True, livello_evidenza="provvisoria"),
            _mov("m3", importo=-1199.99, evidenza_bancaria_ufficiale=True),
            _mov("m4", evidenza_bancaria_ufficiale=True, riconciliato=False),
        ])
        await db.prima_nota_banca.insert_many([
            _riga("p1", "Stipendi", "m1"),
            # solo l'export CSV: aspetta il PDF della banca
            _riga("p2", "Pagamento PayPal", "m2"),
            # un centesimo di differenza non e' la stessa operazione
            _riga("p3", "Assegni", "m3"),
            # categoria che il titolare non ha chiesto
            _riga("p4", "Commissioni bancarie", "m4"),
        ])
        esito = await segna_righe_riscontrate(db)
        assert esito["riconciliate"] == 1
        assert esito["senza_estratto_ufficiale"] == 1 and esito["non_coincidenti"] == 1
        p1 = await db.prima_nota_banca.find_one({"id": "p1"}, {"_id": 0})
        assert p1["riconciliato"] is True and p1["riscontro_estratto"]["movimento_id"] == "m1"
        assert p1["riscontro_estratto"]["file"] == "Estratto conto corrente_31-03-2026.pdf"
        for rid in ("p2", "p3", "p4"):
            assert (await db.prima_nota_banca.find_one({"id": rid}, {"_id": 0}))["riconciliato"] is False
        # il movimento resta libero per il motore degli stipendi
        assert "riconciliato" not in await db.estratto_conto_movimenti.find_one({"id": "m1"}, {"_id": 0})
        # il secondo giro non riscrive niente
        assert (await segna_righe_riscontrate(db))["riconciliate"] == 0

    _run(scenario())


def test_il_pdf_promuove_il_csv_e_la_riga_si_riconcilia():
    """L'export CSV diventa prova quando l'estratto PDF lo promuove a ufficiale."""
    async def scenario():
        db = ClientArchivioMemoria()["riscontro"]
        await db.estratto_conto_movimenti.insert_one(
            _mov("m1", data="2025-08-11", importo=-1850.0,
                 in_attesa_estratto_ufficiale=True, livello_evidenza="provvisoria"))
        await db.prima_nota_banca.insert_one(_riga("p1", "Stipendi", "m1", data="2025-08-11", importo=1850.0))
        assert (await segna_righe_riscontrate(db))["riconciliate"] == 0
        await db.estratto_conto_movimenti.update_one({"id": "m1"}, {"$set": {
            "in_attesa_estratto_ufficiale": False, "evidenza_bancaria_ufficiale": True,
            "livello_evidenza": "ufficiale"}})
        assert (await segna_righe_riscontrate(db))["riconciliate"] == 1

    _run(scenario())


def test_movimento_in_quarantena_non_e_una_prova():
    async def scenario():
        db = ClientArchivioMemoria()["riscontro"]
        await db.estratto_conto_movimenti.insert_one(
            _mov("m1", evidenza_bancaria_ufficiale=True, status="deleted"))
        await db.prima_nota_banca.insert_one(_riga("p1", "Stipendi", "m1"))
        assert (await segna_righe_riscontrate(db))["riconciliate"] == 0

    _run(scenario())
