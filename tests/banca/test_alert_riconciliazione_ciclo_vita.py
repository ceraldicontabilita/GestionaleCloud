"""Alert di riconciliazione: nascono una volta, si chiudono quando il
movimento e' riconciliato, e il «pagamento multiplo» non abbina per importo.

Difetti del 27/09/2026: RIC_NON_RICONCILIATO, RIC_MATCH_AMBIGUO e
RIC_PAGAMENTO_MULTIPLO non si chiudevano mai (15 doppioni aperti), e
RIC_PAGAMENTO_MULTIPLO combinava le prime 40 fatture non pagate di qualunque
fornitore, anche archiviate, entro ±0,05 €.
"""
import asyncio
from pathlib import Path

from app.services.alert_engine import (
    chiudi_alert_movimento_riconciliato,
    genera_alert,
    id_alert_deterministico,
)
from app.services.archivio_documenti_memoria import ArchivioDocumenti
from app.services.riconciliazione_bancaria import _alert_pagamento_multiplo

RADICE = Path(__file__).resolve().parents[2]


def _run(coro):
    return asyncio.run(coro)


def test_genera_alert_concorrente_crea_un_solo_alert_con_id_stabile():
    async def scenario():
        db = ArchivioDocumenti()
        risultati = await asyncio.gather(*[
            genera_alert("RIC_NON_RICONCILIATO", "MOV-1", "estratto_conto_movimenti", "x", db)
            for _ in range(5)
        ])
        creati = [r for r in risultati if r]
        aperti = await db["alerts"].find({"stato": "aperto"}, {"_id": 0}).to_list(None)
        return creati, aperti

    creati, aperti = _run(scenario())
    assert len(creati) == 1 and len(aperti) == 1
    assert aperti[0]["id"] == id_alert_deterministico("RIC_NON_RICONCILIATO", "MOV-1", 0)


def test_alert_riaperto_dopo_la_chiusura_ha_un_id_nuovo_e_lo_storico_resta():
    async def scenario():
        db = ArchivioDocumenti()
        primo = await genera_alert("RIC_NON_RICONCILIATO", "MOV-1", "estratto_conto_movimenti", "x", db)
        await chiudi_alert_movimento_riconciliato(db, "MOV-1")
        secondo = await genera_alert("RIC_NON_RICONCILIATO", "MOV-1", "estratto_conto_movimenti", "x", db)
        tutti = await db["alerts"].find({}, {"_id": 0}).to_list(None)
        return primo, secondo, tutti

    primo, secondo, tutti = _run(scenario())
    assert primo["id"] != secondo["id"]
    assert sorted(a["stato"] for a in tutti) == ["aperto", "risolto"]


def test_movimento_riconciliato_chiude_i_tre_alert_e_non_altri():
    async def scenario():
        db = ArchivioDocumenti()
        for codice in ("RIC_NON_RICONCILIATO", "RIC_MATCH_AMBIGUO", "RIC_PAGAMENTO_MULTIPLO",
                       "RIC_DIFFERENZA_IMPORTO"):
            await genera_alert(codice, "MOV-1", "estratto_conto_movimenti", "x", db)
        await genera_alert("RIC_NON_RICONCILIATO", "MOV-2", "estratto_conto_movimenti", "x", db)
        chiusi = await chiudi_alert_movimento_riconciliato(db, "MOV-1")
        aperti = await db["alerts"].find({"stato": "aperto"}, {"_id": 0}).to_list(None)
        return chiusi, aperti

    chiusi, aperti = _run(scenario())
    assert chiusi == 3
    assert sorted((a["codice"], a["entita_id"]) for a in aperti) == [
        ("RIC_DIFFERENZA_IMPORTO", "MOV-1"), ("RIC_NON_RICONCILIATO", "MOV-2"),
    ]


def test_i_motori_che_riconciliano_chiudono_gli_alert_del_movimento():
    # Allocazione fatture, stipendi, F24 e il motore unico: ognuno, quando
    # scrive `riconciliato: True` sul movimento, chiude i suoi alert.
    for relativo in (
        "app/services/bank_payment_allocations.py",
        "app/services/stipendi_bonifici.py",
        "app/services/f24_controllo_incrociato.py",
        "app/services/riconciliazione_bancaria.py",
    ):
        testo = (RADICE / relativo).read_text(encoding="utf-8")
        assert "chiudi_alert_movimento_riconciliato(" in testo, relativo


FORNITORE = {"supplier_name": "ALFA FORNITURE SRL", "supplier_vat": "01234567890"}


def _fattura(fid, importo, **extra):
    return {"id": fid, "invoice_number": fid, "total_amount": importo,
            "stato_pagamento": "da_pagare", **FORNITORE, **extra}


def _movimento(descrizione, importo=-300.0):
    return {"id": "MOV-9", "importo": importo, "tipo": "uscita", "descrizione": descrizione}


async def _alert_multiplo(db, movimento, importo):
    await _alert_pagamento_multiplo(db, movimento, importo)
    return await db["alerts"].find(
        {"codice": "RIC_PAGAMENTO_MULTIPLO"}, {"_id": 0},
    ).to_list(None)


def test_pagamento_multiplo_stesso_fornitore_somma_al_centesimo():
    async def scenario():
        db = ArchivioDocumenti()
        await db["invoices"].insert_many([
            _fattura("F-1", 100.10), _fattura("F-2", 199.90), _fattura("F-3", 50.00),
        ])
        return await _alert_multiplo(db, _movimento("BONIFICO A ALFA FORNITURE SRL"), 300.00)

    alert = _run(scenario())
    assert len(alert) == 1
    candidate = alert[0]["extra"]["fatture_candidate"]
    assert sorted(c["id"] for c in candidate) == ["F-1", "F-2"]


def test_pagamento_multiplo_senza_fornitore_riconosciuto_nessun_alert():
    async def scenario():
        db = ArchivioDocumenti()
        await db["invoices"].insert_many([_fattura("F-1", 100.10), _fattura("F-2", 199.90)])
        return await _alert_multiplo(db, _movimento("BONIFICO SEPA DISPOSTO"), 300.00)

    assert _run(scenario()) == []


def test_pagamento_multiplo_non_accetta_scarti_ne_fatture_archiviate():
    async def scenario():
        db = ArchivioDocumenti()
        await db["invoices"].insert_many([
            _fattura("F-1", 100.10), _fattura("F-2", 199.89),  # somma 299,99
            _fattura("F-A", 199.90, status="archived"),         # copia archiviata
        ])
        return await _alert_multiplo(db, _movimento("BONIFICO A ALFA FORNITURE SRL"), 300.00)

    assert _run(scenario()) == []


def test_pagamento_multiplo_non_mescola_fornitori():
    async def scenario():
        db = ArchivioDocumenti()
        await db["invoices"].insert_many([
            _fattura("F-1", 100.10),
            {"id": "B-1", "invoice_number": "B-1", "total_amount": 199.90,
             "supplier_name": "BETA SPA", "supplier_vat": "09876543210"},
        ])
        return await _alert_multiplo(db, _movimento("BONIFICO A ALFA FORNITURE SRL BETA SPA"), 300.00)

    assert _run(scenario()) == []
