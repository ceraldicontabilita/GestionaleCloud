import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.routers.prima_nota_module import banca


def _run(awaitable):
    return asyncio.run(awaitable)


def test_lista_banca_esclude_crediti_pos_virtuali_da_righe_e_saldo(monkeypatch):
    """Il credito verso il gestore POS non e' ancora denaro sul conto BPM."""
    db = AsyncMongoMockClient()["banca_saldo_reale_test"]
    monkeypatch.setattr(banca.Database, "get_db", staticmethod(lambda: db))

    async def _aggrega_senza_convert(
        db_corrente, collection, query, anno, query_base_precedente=None,
    ):
        """Replica i totali senza $convert, non implementato da mongomock."""
        documenti = await db_corrente[collection].find(query, {"_id": 0}).to_list(None)
        entrate = sum(float(doc.get("importo") or 0) for doc in documenti if doc.get("tipo") == "entrata")
        uscite = sum(float(doc.get("importo") or 0) for doc in documenti if doc.get("tipo") == "uscita")
        saldo = round(entrate - uscite, 2)
        return {
            "saldo": saldo,
            "saldo_anno": saldo,
            "saldo_precedente": 0.0,
            "saldo_iniziale_manuale": False,
            "totale_entrate": round(entrate, 2),
            "totale_uscite": round(uscite, 2),
        }

    monkeypatch.setattr(banca, "aggrega_saldo_prima_nota", _aggrega_senza_convert)
    _run(db["prima_nota_banca"].insert_many([
        {
            "id": "credito-pos", "data": "2026-08-07", "anno": 2026,
            "tipo": "entrata", "importo": 1000.0,
            "categoria": "POS NUMIA Verso Banca",
            "source": "trasferimento_pos", "natura": "credito_pos",
        },
        {
            "id": "accredito-reale", "data": "2026-08-08", "anno": 2026,
            "tipo": "entrata", "importo": 980.0,
            "categoria": "Accrediti POS", "source": "estratto_conto",
            "natura": "movimento_bancario_reale",
        },
        {
            "id": "uscita-reale", "data": "2026-08-09", "anno": 2026,
            "tipo": "uscita", "importo": 80.0,
            "categoria": "Bonifico", "source": "estratto_conto",
            "natura": "movimento_bancario_reale",
        },
        {
            "id": "sumup-mastercard", "data": "2026-08-10", "anno": 2026,
            "tipo": "entrata", "importo": 834.20,
            "categoria": "Accrediti POS", "source": "accredito_payout",
            "natura": "liquidita", "conto_contabile": "19.01.05",
        },
        {
            "id": "commissione-sumup", "data": "2026-08-10", "anno": 2026,
            "tipo": "uscita", "importo": 7.70,
            "categoria": "Commissioni e spese bancarie", "source": "commissioni_sumup",
            "natura": "costo", "conto_contabile": "75.01.07.02",
        },
    ]))

    risultato = _run(banca.list_prima_nota_banca(
        skip=0, limit=100, anno=2026, data_da=None, data_a=None,
        tipo=None, categoria=None,
    ))

    assert [riga["id"] for riga in risultato["movimenti"]] == [
        "uscita-reale", "accredito-reale",
    ]
    assert risultato["totale_entrate"] == 980.0
    assert risultato["totale_uscite"] == 80.0
    assert risultato["saldo_anno"] == 900.0


def test_scheda_sumup_espone_solo_payout_ricevuti_aggregati_per_giorno(monkeypatch):
    db = AsyncMongoMockClient()["conto_sumup_separato_test"]
    monkeypatch.setattr(banca.Database, "get_db", staticmethod(lambda: db))
    _run(db["prima_nota_banca"].insert_many([
        {
            "id": "p1", "data": "2026-08-10", "tipo": "entrata", "importo": 800.0,
            "source": "accredito_payout", "conto_contabile": "19.01.05", "payout_id": "PID1",
        },
        {
            "id": "p2", "data": "2026-08-10", "tipo": "entrata", "importo": 34.20,
            "source": "accredito_payout", "conto_contabile": "19.01.05", "payout_id": "PID2",
        },
        {
            "id": "p3", "data": "2026-08-09", "tipo": "entrata", "importo": 100.0,
            "source": "accredito_payout", "conto_contabile": "19.01.05", "payout_id": "PID3",
        },
        {
            "id": "vendita", "data": "2026-08-10", "tipo": "entrata", "importo": 999.0,
            "source": "corrispettivi_sync", "conto_contabile": "15.07.02",
        },
        {
            "id": "bpm", "data": "2026-08-10", "tipo": "entrata", "importo": 500.0,
            "source": "estratto_conto", "conto_contabile": "19.01.01",
        },
    ]))

    risultato = _run(banca.list_prima_nota_sumup(anno=2026))

    assert risultato["conto"] == "19.01.05"
    assert risultato["totale_ricevuto"] == 934.20
    assert risultato["numero_payout"] == 3
    assert risultato["giorni"] == [
        {
            "data": "2026-08-10", "importo": 834.20, "numero_payout": 2,
            "payout_ids": ["PID1", "PID2"],
        },
        {
            "data": "2026-08-09", "importo": 100.0, "numero_payout": 1,
            "payout_ids": ["PID3"],
        },
    ]
