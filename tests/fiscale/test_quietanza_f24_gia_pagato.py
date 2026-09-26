"""La quietanza si aggancia al suo F24 anche se il modello e' gia' pagato.

Aprile 2026: il modello (6.469,23 EUR) era gia' riscontrato in banca quando
e' arrivata la quietanza, e l'abbinamento guardava solo gli F24 «da pagare».
La quietanza restava orfana e dalla tabella F24 si arrivava solo
all'estratto conto.
"""
import asyncio

from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.quietanze_import import (
    COLL_F24_ALERTS,
    abbina_quietanza_a_f24,
    ricollega_quietanze_orfane,
)

CF = "04523831214"
RIGHE = {
    "sezione_erario": [
        {"codice_tributo": "1001", "periodo_riferimento": "04/2026", "importo_debito": 940.79},
        {"codice_tributo": "1075", "periodo_riferimento": "04/2026", "importo_debito": 26.66},
        {"codice_tributo": "3802", "periodo_riferimento": "04/2025", "importo_debito": 220.03},
    ],
    "sezione_inps": [
        {"causale": "DM10", "periodo_riferimento": "04/2026", "importo_debito": 5218.0},
    ],
}


# Come sui dati veri: il modello porta la causale INAIL («P»), la quietanza no.
INAIL_F24 = [{"causale": "P", "codice_sede": "33400", "importo_debito": 649.9,
              "importo_debito_cents": 64990}]
INAIL_QUIETANZA = [{"codice_atto": "902026|P", "codice_ufficio": "33400",
                    "periodo_riferimento": "", "importo_debito": 649.9,
                    "importo_debito_cents": 64990}]


def _f24(fid, **extra):
    return {"id": fid, "codice_fiscale": CF, "file_name": f"{fid}.pdf", **RIGHE,
            "sezione_inail": INAIL_F24, **extra}


def _quietanza(qid="q-apr"):
    return {
        "id": qid, "codice_fiscale": CF, "protocollo_telematico": "26051810582342599/000001",
        "data_pagamento": "2026-05-18", "saldo": 6469.23, "f24_associati": [],
        "stato_associazione": "f24_non_corrispondente",
        "stato_quietanza": "QUIETANZA_PRESENTE_F24_NON_CORRISPONDENTE", **RIGHE,
        "sezione_inail": INAIL_QUIETANZA,
    }


def _db():
    return ClientArchivioMemoria()["test_quietanza_f24_pagato"]


def test_orfana_si_aggancia_al_modello_gia_pagato_senza_declassarlo():
    db = _db()

    async def scenario():
        await db["f24_unificato"].insert_one(_f24(
            "f24-apr", status="pagato", pagato=True, pagamento_verificato_banca=True,
            stato_pagamento="PAGATO", movimento_bancario_id="ec-19-05",
        ))
        await db["quietanze_f24"].insert_one(_quietanza())
        await db[COLL_F24_ALERTS].insert_one({
            "id": "al-1", "tipo": "quietanza_senza_match", "quietanza_id": "q-apr",
            "status": "pending",
        })
        esito = await ricollega_quietanze_orfane(db)
        secondo = await ricollega_quietanze_orfane(db)
        return (esito, secondo, await db["f24_unificato"].find_one({"id": "f24-apr"}),
                await db["quietanze_f24"].find_one({"id": "q-apr"}),
                await db[COLL_F24_ALERTS].find_one({"id": "al-1"}))

    esito, secondo, f24, quietanza, alert = asyncio.run(scenario())
    assert esito == {"orfane": 1, "collegate": 1, "rietichettate": 0}
    assert secondo == {"orfane": 0, "collegate": 0, "rietichettate": 0}
    assert f24["quietanza_id"] == "q-apr"
    assert f24["protocollo_quietanza"] == "26051810582342599/000001"
    # Resta pagato in banca: la quietanza non lo riporta «da verificare».
    assert f24["status"] == "pagato" and f24["pagato"] is True
    assert f24["pagamento_verificato_banca"] is True
    assert quietanza["f24_associati"] == ["f24-apr"]
    assert quietanza["stato_associazione"] == "associata"
    assert "stato_quietanza" not in quietanza
    assert alert["status"] == "risolto"


def test_due_modelli_uguali_non_si_collega_niente():
    db = _db()

    async def scenario():
        await db["f24_unificato"].insert_one(_f24("f24-a", status="da_pagare"))
        await db["f24_unificato"].insert_one(_f24("f24-b", status="pagato"))
        return await abbina_quietanza_a_f24(db, _quietanza())

    esito = asyncio.run(scenario())
    assert esito["f24_matchati"] == []
    assert len(esito["candidati"]) == 2


def test_modello_con_gia_una_quietanza_non_e_candidato():
    db = _db()

    async def scenario():
        await db["f24_unificato"].insert_one(_f24("f24-a", status="pagato", quietanza_id="altra"))
        return await abbina_quietanza_a_f24(db, _quietanza())

    assert asyncio.run(scenario())["candidati"] == []


def test_modello_da_pagare_riceve_lo_stato_documentale():
    db = _db()

    async def scenario():
        await db["f24_unificato"].insert_one(_f24("f24-a", status="da_pagare", riconciliato=False))
        await abbina_quietanza_a_f24(db, _quietanza())
        return await db["f24_unificato"].find_one({"id": "f24-a"})

    f24 = asyncio.run(scenario())
    assert f24["quietanza_id"] == "q-apr"
    assert f24["stato_pagamento"] == "DA_VERIFICARE_BANCA"
    assert f24["pagato"] is False


def test_il_modello_arrivato_dopo_trova_subito_la_quietanza(monkeypatch):
    """Arrivo in ordine inverso: prima la quietanza, poi il modello F24."""
    import app.services.parser_f24 as parser
    from app.services.f24_canonico import importa_modello_bytes

    parsed = {
        "dati_generali": {"codice_fiscale": CF, "data_versamento": "2026-05-18"},
        **RIGHE,
        "sezione_inail": INAIL_F24,
        "totali": {"totale_debito": 6469.23, "totale_credito": 0.0, "saldo_netto": 6469.23},
        "validazione": {"saldo_quadrato": True, "parser_version": "test-v1"},
    }
    monkeypatch.setattr(parser, "parse_f24_commercialista", lambda pdf_content: parsed)
    db = _db()

    async def scenario():
        await db["quietanze_f24"].insert_one(_quietanza())
        esito = await importa_modello_bytes(db, b"%PDF-1.4 aprile", "F24 aprile.pdf", source="test")
        f24 = await db["f24_unificato"].find_one({"id": esito["f24_id"]})
        return esito, f24, await db["quietanze_f24"].find_one({"id": "q-apr"})

    esito, f24, quietanza = asyncio.run(scenario())
    assert esito["controparti"]["quietanze"]["collegate"] == 1
    assert f24["quietanza_id"] == "q-apr"
    assert quietanza["stato_associazione"] == "associata"



# Maggio 2026: due righe comunali con lo stesso codice e periodo.
RIGHE_MAGGIO = {
    "sezione_erario": [
        {"codice_tributo": "1001", "periodo_riferimento": "05/2026", "importo_debito": 1026.51},
    ],
    "sezione_tributi_locali": [
        {"codice_tributo": "3847", "periodo_riferimento": "05/2026", "importo_debito": 55.55},
        {"codice_tributo": "3847", "periodo_riferimento": "05/2026", "importo_debito": 19.26},
    ],
}


def test_due_righe_con_stesso_codice_e_periodo_combaciano():
    db = _db()

    async def scenario():
        await db["f24_unificato"].insert_one({
            "id": "f24-mag", "codice_fiscale": CF, "status": "pagato",
            "pagamento_verificato_banca": True, **RIGHE_MAGGIO,
            # Il parser copia le righe comunali anche in sezione_imu.
            "sezione_imu": RIGHE_MAGGIO["sezione_tributi_locali"],
            "totali": {"saldo_netto": 1101.32},
        })
        return await abbina_quietanza_a_f24(db, {
            "id": "q-mag", "codice_fiscale": CF, "saldo": 1101.32, **RIGHE_MAGGIO,
        })

    esito = asyncio.run(scenario())
    assert [m["f24_id"] for m in esito["f24_matchati"]] == ["f24-mag"]


def test_saldo_diverso_non_e_lo_stesso_versamento():
    db = _db()

    async def scenario():
        await db["f24_unificato"].insert_one({
            "id": "f24-x", "codice_fiscale": CF, "status": "da_pagare", **RIGHE_MAGGIO,
            "totali": {"saldo_netto": 1500.00},
        })
        return await abbina_quietanza_a_f24(db, {
            "id": "q-x", "codice_fiscale": CF, "saldo": 1101.32, **RIGHE_MAGGIO,
        })

    assert asyncio.run(scenario())["f24_matchati"] == []


def test_quietanza_senza_modello_si_dichiara_f24_mancante():
    db = _db()

    async def scenario():
        # Un F24 dello stesso contribuente esiste, ma e' un altro versamento.
        await db["f24_unificato"].insert_one(_f24("f24-altro", status="pagato",
                                                  totali={"saldo_netto": 99.0}))
        await db["quietanze_f24"].insert_one({
            **_quietanza("q-sola"), "saldo": 1234.56,
            "sezione_erario": [{"codice_tributo": "1001", "periodo_riferimento": "06/2026",
                                "importo_debito": 1234.56}],
        })
        esito = await ricollega_quietanze_orfane(db)
        return esito, await db["quietanze_f24"].find_one({"id": "q-sola"})

    esito, quietanza = asyncio.run(scenario())
    assert esito["rietichettate"] == 1
    assert quietanza["stato_associazione"] == "f24_mancante"
    assert quietanza["stato_quietanza"] == "QUIETANZA_PRESENTE_F24_MANCANTE"
