"""L'F24 del commercialista e il suo ravvedimento: legati per codici tributo.

Casi presi dall'archivio di produzione (27/09/2026): il modello del
commercialista ``1040 12/2024`` per 520,00 EUR e, accanto, il modello del
titolare ``1040 12/2024`` 521,57 (interessi cumulati, Ris. AdE 18/E 2023) piu'
la sanzione ``8948 12/2024`` 7,22. Si prova che:

- il legame nasce da codice e periodo, e la differenza di importo e' ammessa
  solo sulle righe del periodo che ha una sanzione: mai una tolleranza;
- l'originale resta com'e' (stato compreso), il ravvedimento prende l'etichetta;
- un'ambiguita' resta candidata, un legame che non regge piu' si toglie;
- il secondo giro non riscrive niente.
"""
import asyncio

from app.constants.codici_ravvedimento import CODICI_RAVVEDIMENTO
from app.db_collections import COLL_F24, COLL_QUIETANZE_F24
from app.services import f24_ravvedimento as rv
from app.services.archivio_documenti_memoria import ClientArchivioMemoria


def _run(coroutine):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coroutine)
    finally:
        loop.close()


def _riga(codice, periodo, debito=0.0, credito=0.0):
    return {"codice_tributo": codice, "periodo_riferimento": periodo,
            "importo_debito": debito, "importo_credito": credito}


def _f24(id_, righe, saldo, **extra):
    return {"id": id_, "status": "da_pagare", "codice_fiscale": "04523831214",
            "sezione_erario": righe, "totali": {"saldo_netto": saldo}, **extra}


def _quietanza(id_, righe, saldo, data="2026-04-16", protocollo="26041535212746370/000001"):
    return {"id": id_, "codice_fiscale": "04523831214", "sezione_erario": righe, "saldo": saldo,
            "data_pagamento": data, "protocollo_telematico": protocollo, "f24_associati": []}


ORIGINALE = _f24("orig", [_riga("1040", "12/2024", 520.00)], 520.00)
RAVVEDIMENTO = _f24("ravv", [_riga("1040", "12/2024", 521.57), _riga("8948", "12/2024", 7.22)], 528.79)


def test_le_sanzioni_della_risoluzione_18e_2023_sono_codici_di_ravvedimento():
    assert {"8947", "8948", "8949", "8950", "8951", "8952", "8953"} <= CODICI_RAVVEDIMENTO


def test_originale_e_modello_di_ravvedimento_si_legano_per_codice_e_periodo():
    esito = rv.abbina_ravvedimenti([ORIGINALE, RAVVEDIMENTO], [])

    [a] = esito["abbinati"]
    assert a["originale_id"] == "orig" and a["f24_ravvedimento_id"] == "ravv"
    [riga] = a["righe"]
    assert (riga["originale"], riga["versato"], riga["interessi_cumulati"]) == (520.00, 521.57, 1.57)
    assert [s["codice"] for s in a["sanzioni"]] == ["8948"]
    assert "1040 12/2024 520.00 -> 521.57 (interessi cumulati 1.57)" in a["motivazione"]
    assert "8948 12/2024 7.22" in a["motivazione"]


def test_la_quietanza_ade_del_ravvedimento_basta_anche_senza_modello():
    """16/04/2026: 1.150,62 EUR pagati per 1040 03/2026 e per due ritenute
    ravvedute; una e' l'F24 del commercialista 1040 02/2025 da 210,00."""
    originale = _f24("feb", [_riga("1040", "02/2025", 210.00)], 210.00)
    righe_q = [_riga("1040", "03/2026", 490.00), _riga("1040", "09/2025", 221.94),
               _riga("1040", "02/2025", 214.30), _riga("1040", "03/2026", 210.00),
               _riga("8948", "02/2025", 7.50), _riga("8948", "09/2025", 6.88)]
    copie = [_quietanza("q1", righe_q, 1150.62), _quietanza("q2", righe_q, 1150.62)]

    [a] = rv.abbina_ravvedimenti([originale], copie)["abbinati"]
    assert a["f24_ravvedimento_id"] is None
    assert a["quietanza_ids"] == ["q1", "q2"]  # due copie, un pagamento
    assert a["importo_ravvedimento"] == 1150.62 and a["data_pagamento"] == "2026-04-16"
    assert a["interessi_cumulati"] == 4.30
    assert [s["periodo"] for s in a["sanzioni"]] == ["02/2025"]


def test_senza_sanzione_per_quel_periodo_un_importo_diverso_non_si_lega():
    ravv = _f24("ravv", [_riga("1040", "12/2024", 521.57), _riga("8948", "11/2024", 7.22)], 528.79)
    assert rv.abbina_ravvedimenti([ORIGINALE, ravv], [])["abbinati"] == []


def test_un_importo_minore_non_e_un_ravvedimento():
    ravv = _f24("ravv", [_riga("1040", "12/2024", 519.99), _riga("8948", "12/2024", 7.22)], 527.21)
    assert rv.abbina_ravvedimenti([ORIGINALE, ravv], [])["abbinati"] == []


def test_la_sanzione_annuale_non_copre_una_ritenuta_mensile():
    originale = _f24("o", [_riga("1040", "08/2025", 210.00)], 210.00)
    ravv = _f24("r", [_riga("1040", "08/2025", 211.00), _riga("8904", "2025", 40.08)], 251.08)
    assert rv.abbina_ravvedimenti([originale, ravv], [])["abbinati"] == []


def test_una_riga_dell_originale_assente_dal_ravvedimento_non_si_lega():
    originale = _f24("o", [_riga("1040", "12/2024", 520.00), _riga("1001", "12/2024", 100.00)], 620.00)
    assert rv.abbina_ravvedimenti([originale, RAVVEDIMENTO], [])["abbinati"] == []


def test_due_copie_dell_originale_restano_candidate():
    copia = {**ORIGINALE, "id": "orig-2"}
    esito = rv.abbina_ravvedimenti([ORIGINALE, copia, RAVVEDIMENTO], [])
    assert esito["abbinati"] == []
    assert {a["originale_id"] for a in esito["ambigui"]} == {"orig", "orig-2"}


def test_un_modello_eliminato_non_conta():
    eliminato = {**RAVVEDIMENTO, "status": "eliminato"}
    assert rv.abbina_ravvedimenti([ORIGINALE, eliminato], [])["abbinati"] == []


# ── la scrittura ───────────────────────────────────────────────────────────

def _db(modelli, quietanze=()):
    db = ClientArchivioMemoria()["gestionale_test"]

    async def _carica():
        for m in modelli:
            await db[COLL_F24].insert_one(dict(m))
        for q in quietanze:
            await db[COLL_QUIETANZE_F24].insert_one(dict(q))
    _run(_carica())
    return db


def test_l_originale_resta_com_e_e_il_ravvedimento_prende_l_etichetta():
    righe_q = [_riga("1040", "12/2024", 521.57), _riga("1001", "02/2025", 300.00), _riga("8948", "12/2024", 7.22)]
    db = _db([ORIGINALE, RAVVEDIMENTO], [_quietanza("q1", righe_q, 828.79, data="2025-03-12")])

    esito = _run(rv.collega_ravvedimenti(db))
    assert esito["scritti"] == {"originali": 1, "modelli_ravvedimento": 1, "quietanze": 1}

    o = _run(db[COLL_F24].find_one({"id": "orig"}))
    assert o["status"] == "da_pagare" and o["totali"]["saldo_netto"] == 520.00
    assert o["ravvedimento"]["stato"] == rv.STATO_RAVVEDUTO
    assert o["ravvedimento"]["f24_ravvedimento_id"] == "ravv"
    assert o["ravvedimento"]["quietanza_ids"] == ["q1"]  # contiene tutto il ravvedimento
    r = _run(db[COLL_F24].find_one({"id": "ravv"}))
    assert (r["etichetta"], r["ravvedimento_di"]) == (rv.ETICHETTA, ["orig"])
    assert _run(db[COLL_QUIETANZE_F24].find_one({"id": "q1"}))["ravvedimento_di"] == ["orig"]


def test_la_quietanza_che_non_contiene_tutto_il_ravvedimento_non_si_lega():
    righe_q = [_riga("1040", "12/2024", 521.57), _riga("8948", "12/2024", 7.00)]
    db = _db([ORIGINALE, RAVVEDIMENTO], [_quietanza("q1", righe_q, 528.57)])

    _run(rv.collega_ravvedimenti(db))
    assert _run(db[COLL_F24].find_one({"id": "orig"}))["ravvedimento"]["quietanza_ids"] == []


def test_il_secondo_giro_non_riscrive_niente():
    db = _db([ORIGINALE, RAVVEDIMENTO])
    _run(rv.collega_ravvedimenti(db))
    assert _run(rv.collega_ravvedimenti(db))["scritti"] == {
        "originali": 0, "modelli_ravvedimento": 0, "quietanze": 0}


def test_in_simulazione_non_si_scrive():
    db = _db([ORIGINALE, RAVVEDIMENTO])
    esito = _run(rv.collega_ravvedimenti(db, dry_run=True))
    assert esito["conteggi"]["abbinati"] == 1
    assert "ravvedimento" not in _run(db[COLL_F24].find_one({"id": "orig"}))


def test_un_legame_che_non_regge_piu_si_toglie():
    db = _db([ORIGINALE, RAVVEDIMENTO])
    _run(rv.collega_ravvedimenti(db))
    _run(db[COLL_F24].update_one({"id": "ravv"}, {"$set": {"status": "eliminato"}}))

    _run(rv.collega_ravvedimenti(db))
    assert "ravvedimento" not in _run(db[COLL_F24].find_one({"id": "orig"}))
    assert "etichetta" not in _run(db[COLL_F24].find_one({"id": "ravv"}))
