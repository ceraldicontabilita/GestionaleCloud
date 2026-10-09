"""Fatture dell'anno prima pagate nell'anno attivo: solo il debito.

Titolare, 28/09/2026: FEP 71_25 e FEP 72_25 di A 2000 Costruzioni (12.200,00
ciascuna, 29/12/2025) pagate con tre bonifici del 2026 (12.200 + 8.000 +
4.200) che restavano senza documento.
"""
import asyncio

from app.services import debiti_anno_precedente as dap
from app.services.archivio_documenti_memoria import ClientArchivioMemoria


def _run(coro):
    return asyncio.run(coro)


def _parsed(numero, totale, data="2025-12-29", piva="08577391215", tipo="TD01"):
    return {"invoice_number": numero, "invoice_date": data, "total_amount": totale,
            "supplier_name": "A 2000 Costruzioni S.r.l", "supplier_vat": piva,
            "tipo_documento": tipo, "importo_ritenuta": None}


def _bonifico(mid, data, importo, **extra):
    return {"id": mid, "data": data, "tipo": "uscita", "importo": -importo,
            "descrizione_originale": f"VS.DISP. RIF. MBVT{mid}/1 FAVORE A 2000 COSTRUZIONI S.R.L",
            **extra}


def test_registro_idempotente_e_mai_note_di_credito():
    async def scenario():
        db = ClientArchivioMemoria()["dap-reg"]
        assert (await dap.registra(db, _parsed("FEP 71_25", 12200.0)))["registrato"]
        assert (await dap.registra(db, _parsed("FEP 71_25", 12200.0)))["gia_presente"]
        assert not (await dap.registra(db, _parsed("NC 1", 100.0, tipo="TD04")))["registrato"]
        assert await db[dap.COLL].count_documents({}) == 1
        assert dap.e_anno_precedente(_parsed("x", 1.0), 2026)
        assert not dap.e_anno_precedente(_parsed("x", 1.0, data="2024-05-01"), 2026)

    _run(scenario())


def test_i_bonifici_del_2026_chiudono_i_debiti_2025():
    async def scenario():
        db = ClientArchivioMemoria()["dap-abbina"]
        await dap.registra(db, _parsed("FEP 71_25", 12200.0))
        await dap.registra(db, _parsed("FEP 72_25", 12200.0))
        await db.estratto_conto_movimenti.insert_many([
            # collegato a una fattura che non esiste piu'
            _bonifico("m1", "2026-03-23", 12200.0, fattura_id="sparita", categoria="Fatture"),
            _bonifico("m2", "2026-04-10", 8000.0),
            _bonifico("m3", "2026-05-02", 4200.0),
        ])
        esito = await dap.abbina_pagamenti(db, anno_attivo=2026)
        # Due debiti uguali: nessun bonifico sa quale paga, ma i tre bonifici
        # fanno al centesimo i 24.400 dei due: si ripartiscono in ordine.
        assert len(esito["collegati"]) == 2 and esito["ambigui"] == 0
        per_numero = {c["numero"]: c["movimenti"] for c in esito["collegati"]}
        assert per_numero == {"FEP 71_25": ["m1"], "FEP 72_25": ["m2", "m3"]}

        # Se i bonifici non fanno il totale, nessuna ripartizione.
        db3 = ClientArchivioMemoria()["dap-no"]
        await dap.registra(db3, _parsed("FEP 71_25", 12200.0))
        await dap.registra(db3, _parsed("FEP 72_25", 12200.0))
        await db3.estratto_conto_movimenti.insert_many([
            _bonifico("m1", "2026-03-23", 12200.0), _bonifico("m2", "2026-04-10", 8000.0)])
        esito = await dap.abbina_pagamenti(db3, anno_attivo=2026)
        assert esito["collegati"] == [] and esito["ambigui"] == 2

        # Con un debito solo la scelta e' certa.
        db2 = ClientArchivioMemoria()["dap-uno"]
        await dap.registra(db2, _parsed("FEP 72_25", 12200.0))
        await db2.estratto_conto_movimenti.insert_many([
            _bonifico("m2", "2026-04-10", 8000.0),
            _bonifico("m3", "2026-05-02", 4200.0),
        ])
        esito = await dap.abbina_pagamenti(db2, anno_attivo=2026)
        assert len(esito["collegati"]) == 1
        debito = await db2[dap.COLL].find_one({}, {"_id": 0})
        assert debito["stato"] == "pagato" and debito["residuo_cents"] == 0
        m2 = await db2.estratto_conto_movimenti.find_one({"id": "m2"}, {"_id": 0})
        assert m2["categoria"] == dap.CATEGORIA and m2["riconciliato"] is True
        assert (await dap.abbina_pagamenti(db2, anno_attivo=2026))["collegati"] == []

    _run(scenario())


def test_il_collegamento_orfano_si_sostituisce():
    async def scenario():
        db = ClientArchivioMemoria()["dap-orfano"]
        await dap.registra(db, _parsed("FEP 71_25", 12200.0))
        await db.estratto_conto_movimenti.insert_one(
            _bonifico("m1", "2026-03-23", 12200.0, fattura_id="sparita", riconciliato=True))
        # Riconciliato con qualcosa che esiste (niente fattura_id): non si tocca.
        await db.estratto_conto_movimenti.insert_one(
            _bonifico("m9", "2026-03-24", 12200.0, riconciliato=True, assegno_id="a1"))
        esito = await dap.abbina_pagamenti(db, anno_attivo=2026)
        assert len(esito["collegati"]) == 1
        m1 = await db.estratto_conto_movimenti.find_one({"id": "m1"}, {"_id": 0})
        assert m1["fattura_id_orfano"] == "sparita" and m1["fattura_id"] is None
        # Prima Nota Banca: una riga sul conto fornitori, niente costo.
        righe = await db.prima_nota_banca.find({"estratto_conto_id": "m1"}, {"_id": 0}).to_list(5)
        assert len(righe) == 1
        assert righe[0]["conto_contropartita"] == "33.03.01" and righe[0]["importo"] == 12200.0
        assert righe[0]["categoria"] == dap.CATEGORIA
        await dap.abbina_pagamenti(db, anno_attivo=2026)
        assert await db.prima_nota_banca.count_documents({"estratto_conto_id": "m1"}) == 1

    _run(scenario())


def test_canone_a_importo_fisso_non_si_abbina_per_importo():
    """28/09/2026: due fatture Fastweb 2025 da 43,86 e una Arval da 832,25
    risultavano pagate dagli addebiti di agosto e settembre 2026: sono canoni
    mensili, quegli SDD pagano le fatture di quest'anno."""
    async def scenario():
        db = ClientArchivioMemoria()["dap-canoni"]
        await dap.registra(db, {**_parsed("M031962931", 43.86, data="2025-12-01", piva="12878470157"),
                                "supplier_name": "FASTWEB SpA"})
        await db.invoices.insert_one({"id": "fw26", "supplier_vat": "12878470157",
                                      "total_amount": 43.86, "invoice_date": "2026-01-01"})
        await db.estratto_conto_movimenti.insert_one({
            "id": "sdd", "data": "2026-01-10", "tipo": "uscita", "importo": 43.86,
            "descrizione_originale": "ADDEBITO DIRETTO SDD - SDD CORE: 3F3811A21532878 FASTWEB SpA"})
        esito = await dap.abbina_pagamenti(db, anno_attivo=2026)
        assert esito["collegati"] == []
        # Con il numero della fattura in causale il legame e' certo.
        await db.estratto_conto_movimenti.update_one({"id": "sdd"}, {"$set": {
            "descrizione_originale": "SDD CORE: 3F38 FASTWEB SpA FATTURA M031962931"}})
        assert len((await dap.abbina_pagamenti(db, anno_attivo=2026))["collegati"]) == 1

    _run(scenario())


def test_oltre_sei_mesi_non_e_il_pagamento_di_quella_fattura():
    async def scenario():
        db = ClientArchivioMemoria()["dap-finestra"]
        await dap.registra(db, _parsed("FEP 71_25", 12200.0))
        await db.estratto_conto_movimenti.insert_one(_bonifico("m1", "2026-09-02", 12200.0))
        assert (await dap.abbina_pagamenti(db, anno_attivo=2026))["collegati"] == []

    _run(scenario())
