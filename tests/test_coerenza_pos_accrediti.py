"""Quadratura POS: il giorno viene dalla descrizione dell'estratto conto."""
import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.routers import pos_corrispettivi_check as pc


def _run(coro):
    return asyncio.run(coro)


def test_somma_circuiti_sul_giorno_del_riferimento_non_sulla_data_contabile():
    async def scenario():
        db = AsyncMongoMockClient()["test_accrediti_giorno_operazione"]
        await db["estratto_conto_movimenti"].insert_many([
            {
                "data": "2026-07-07", "importo": 1000.20,
                "descrizione_originale": (
                    "INCAS. TRAMITE P.O.S - NUMIA-BNCMT DEL 06/07/26 PDV 3757283/00012"
                ),
            },
            {
                "data": "2026-07-08", "importo": 300.30,
                "descrizione_originale": (
                    "INC.POS CARTE CREDIT - NUMIA-INTER DEL 06/07/26 PDV 3757283/00011"
                ),
            },
            {
                "data": "2026-07-08", "importo": 53.20,
                "descrizione_originale": (
                    "INCAS. TRAMITE P.O.S - NUMIA-PGBNT DEL 06/07/26 PDV 3757283/00012"
                ),
            },
        ])

        out = await pc._carica_accrediti_banca_pos(db, "2026-07-01", "2026-07-31")

        assert out == {
            "2026-07-06": {
                "totale": 1353.70,
                "numero_movimenti": 3,
                "numero_movimenti_raw": 3,
                "duplicati_unificati": 0,
                "date_contabili": ["2026-07-07", "2026-07-08"],
                "fonti_movimento_ids": [],
                "origine": "estratto_conto_movimenti",
            }
        }

    _run(scenario())


def test_esclude_righe_numia_che_non_sono_accrediti_pos_giornalieri():
    async def scenario():
        db = AsyncMongoMockClient()["test_esclusioni_numia"]
        await db["estratto_conto_movimenti"].insert_many([
            {"data": "2026-07-09", "importo": 0.02,
             "descrizione_originale": "INC.POS CARTE CREDIT - REMUNERAZIONE DCC 06/26 NUMIA"},
            {"data": "2026-07-09", "importo": 12.00,
             "descrizione_originale": "SPESE - COMMISSIONI NUMIA"},
            {"data": "2026-07-09", "importo": 20.00,
             "descrizione_originale": "SPESE - FATTURA NUMIA"},
            {"data": "2026-07-09", "importo": 99.00,
             "descrizione_originale": "ACCREDITO NUMIA POS"},
            {"data": "2026-07-09", "importo": -50.00,
             "descrizione_originale": "INC.POS CARTE CREDIT - NUMIA-INTER DEL 08/07/26"},
        ])

        out = await pc._carica_accrediti_banca_pos(db, "2026-07-01", "2026-07-31")

        assert out == {}

    _run(scenario())


def test_riferimento_operazione_fuori_periodo_non_viene_contato():
    async def scenario():
        db = AsyncMongoMockClient()["test_periodo_giorno_operazione"]
        await db["estratto_conto_movimenti"].insert_one({
            "data": "2026-07-01", "importo": 700.00,
            "descrizione_originale": (
                "INC.POS CARTE CREDIT - NUMIA-INTER DEL 30/06/26 PDV 3757283/00011"
            ),
        })

        out = await pc._carica_accrediti_banca_pos(db, "2026-07-01", "2026-07-31")

        assert out == {}

    _run(scenario())


def test_unifica_copie_stessa_liquidazione_ma_non_due_date_contabili_distinte():
    async def scenario():
        db = AsyncMongoMockClient()["test_dedup_accrediti_pos"]
        causale = (
            "INC.POS CARTE CREDIT - NUMIA-AMEX DEL 14/07/26 "
            "PDV 3757283/00012 CERALDI CAFFE' NA"
        )
        await db["estratto_conto_movimenti"].insert_many([
            {
                "id": "EC-15-A", "data": "2026-07-15", "importo": 2.00,
                "rapporto": "CONTO-1", "descrizione_originale": causale,
                "created_at": "2026-08-04T12:01:00+00:00",
            },
            {
                "id": "EC-15-B", "data": "2026-07-15", "importo": 2.00,
                "rapporto": "CONTO-1", "descrizione_originale": causale,
                "created_at": "2026-08-04T12:04:00+00:00",
            },
            {
                "id": "EC-15-C", "data": "2026-07-15", "importo": 2.00,
                "rapporto": "CONTO-1", "descrizione_originale": causale,
                "created_at": "2026-08-04T12:09:00+00:00",
            },
            {
                "id": "EC-16", "data": "2026-07-16", "importo": 2.00,
                "rapporto": "CONTO-1", "descrizione_originale": causale,
            },
        ])

        out = await pc._carica_accrediti_banca_pos(db, "2026-07-01", "2026-07-31")
        evidenza = out["2026-07-14"]

        assert evidenza["totale"] == 4.00
        assert evidenza["numero_movimenti"] == 2
        assert evidenza["numero_movimenti_raw"] == 4
        assert evidenza["duplicati_unificati"] == 2
        assert evidenza["date_contabili"] == ["2026-07-15", "2026-07-16"]
        assert set(evidenza["fonti_movimento_ids"]) == {
            "EC-15-A", "EC-15-B", "EC-15-C", "EC-16",
        }

    _run(scenario())


def test_riepilogo_mensile_usa_pos_reale_giorno_vendita_e_deduplica(monkeypatch):
    async def scenario():
        db = AsyncMongoMockClient()["test_riepilogo_mensile_canonico"]
        await db["corrispettivi"].insert_one({
            "data": "2026-07-14", "totale": 150.00,
            "pagato_contanti": 45.00, "pagato_elettronico": 105.00,
            "stato": "definitivo_xml", "entity_status": "active",
        })
        await db["chiusure_pos_manuali"].insert_one({
            "data": "2026-07-14", "importo": 100.00,
            "source": "inserimento_manuale_terminale",
        })
        causale = (
            "INCAS. TRAMITE P.O.S - NUMIA-BNCMT DEL 14/07/26 "
            "PDV 3757283/00012"
        )
        await db["estratto_conto_movimenti"].insert_many([
            {"id": "EC-A", "data": "2026-07-15", "importo": 100.00,
             "rapporto": "CONTO-1", "descrizione_originale": causale},
            {"id": "EC-B", "data": "2026-07-15", "importo": 100.00,
             "rapporto": "CONTO-1", "descrizione_originale": causale},
            {"id": "EC-C", "data": "2026-07-15", "importo": 100.00,
             "rapporto": "CONTO-1", "descrizione_originale": causale},
        ])
        monkeypatch.setattr(pc.Database, "get_db", staticmethod(lambda: db))

        result = await pc.riepilogo_mensile_pos_corrispettivi(anno=2026)
        luglio = result["mesi"][6]

        assert luglio["elettronico_xml"] == 105.00
        assert luglio["pos_terminale"] == 100.00
        assert luglio["pos_accreditato"] == 100.00
        assert luglio["differenza_xml_pos"] == 5.00
        assert luglio["differenza_pos_banca"] == 0.00
        assert luglio["pos_count"] == 1
        assert luglio["pos_count_raw"] == 3
        assert luglio["duplicati_banca_unificati"] == 2
        assert result["totali"]["duplicati_banca_unificati"] == 2

    _run(scenario())


def test_riconoscimento_causale_richiede_numia_incasso_e_giorno():
    assert pc._e_accredito_pos_numia_con_giorno(
        "INCAS. TRAMITE P.O.S - NUMIA-BNCMT DEL 16/07/26 PDV 3757283/00012"
    )
    assert not pc._e_accredito_pos_numia_con_giorno(
        "INC.POS CARTE CREDIT - REMUNERAZIONE DCC 06/26 NUMIA"
    )
    assert not pc._e_accredito_pos_numia_con_giorno("ACCREDITO NUMIA POS")


def test_controllo_due_fasi_certifica_solo_match_da_estratto_conto(monkeypatch):
    async def scenario():
        db = AsyncMongoMockClient()["test_badge_riconciliazione_banca"]
        await db["corrispettivi"].insert_one({
            "data": "2026-07-06",
            "pagato_elettronico": 1400.00,
            "stato": "definitivo_xml",
        })
        await db["chiusure_pos_manuali"].insert_one({
            "data": "2026-07-06",
            "importo": 1353.70,
            "source": "inserimento_manuale_terminale",
        })
        await db["estratto_conto_movimenti"].insert_many([
            {
                "data": "2026-07-07", "importo": 1000.20,
                "descrizione_originale": (
                    "INCAS. TRAMITE P.O.S - NUMIA-BNCMT DEL 06/07/26 PDV 3757283/00012"
                ),
            },
            {
                "data": "2026-07-08", "importo": 353.50,
                "descrizione_originale": (
                    "INC.POS CARTE CREDIT - NUMIA-INTER DEL 06/07/26 PDV 3757283/00011"
                ),
            },
        ])
        monkeypatch.setattr(pc.Database, "get_db", staticmethod(lambda: db))

        result = await pc.controllo_incassi_due_fasi(
            data_da=None, data_a=None, anno=2026, tolleranza_euro=0.50
        )
        giorno = next(g for g in result["giorni"] if g["data"] == "2026-07-06")

        assert giorno["stato_accredito"] == "ok"
        assert giorno["riconciliato_banca_reale"] is True
        assert giorno["numero_movimenti_banca"] == 2
        assert giorno["origine_accredito"] == "estratto_conto_movimenti"
        assert giorno["date_contabili_banca"] == ["2026-07-07", "2026-07-08"]

    _run(scenario())


def test_controllo_due_fasi_non_certifica_un_importo_solo_trascritto(monkeypatch):
    async def scenario():
        db = AsyncMongoMockClient()["test_nessun_badge_senza_banca"]
        await db["corrispettivi"].insert_one({
            "data": "2026-07-05",
            "pagato_elettronico": 1000.00,
            "stato": "definitivo_xml",
        })
        await db["chiusure_pos_manuali"].insert_one({
            "data": "2026-07-05",
            "importo": 1000.00,
            "source": "inserimento_manuale_terminale",
        })
        monkeypatch.setattr(pc.Database, "get_db", staticmethod(lambda: db))

        result = await pc.controllo_incassi_due_fasi(
            data_da=None, data_a=None, anno=2026, tolleranza_euro=0.50
        )
        giorno = next(g for g in result["giorni"] if g["data"] == "2026-07-05")

        assert giorno["stato_accredito"] == "mancante"
        assert giorno["accredito_banca"] == 0
        assert giorno["riconciliato_banca_reale"] is False
        assert giorno["numero_movimenti_banca"] == 0
        assert giorno["origine_accredito"] is None

    _run(scenario())


def test_due_fasi_separa_numia_da_sumup_e_non_usa_xml_come_pos(monkeypatch):
    async def scenario():
        db = AsyncMongoMockClient()["test_due_circuiti_reali"]
        await db["corrispettivi"].insert_one({
            "data": "2026-08-03", "pagato_elettronico": 1629.50,
            "stato": "definitivo_xml", "entity_status": "active",
        })
        await db["chiusure_pos_manuali"].insert_one({
            "data": "2026-08-03", "importo": 721.30,
            "gestore": "sumup", "source": "api_sumup",
        })
        await db["estratto_conto_movimenti"].insert_many([
            {
                "id": f"EC-{indice}", "data": "2026-08-04", "importo": importo,
                "descrizione_originale": (
                    "INC.POS CARTE CREDIT - NUMIA-INTER DEL 03/08/26 "
                    f"PDV 3757283/000{indice}"
                ),
            }
            for indice, importo in enumerate([13.00, 410.50, 61.10, 382.70], start=1)
        ])
        monkeypatch.setattr(pc.Database, "get_db", staticmethod(lambda: db))

        result = await pc.controllo_incassi_due_fasi(
            data_da=None, data_a=None, anno=2026, tolleranza_euro=0.50
        )
        giorno = next(g for g in result["giorni"] if g["data"] == "2026-08-03")

        assert giorno["pos_per_circuito"] == {
            "numia": 867.30, "sumup": 721.30,
        }
        assert giorno["fonte_pos_per_circuito"]["numia"] == "estratto_conto_numia"
        assert giorno["fonte_pos_per_circuito"]["sumup"] == "api_sumup"
        assert giorno["pos_manuale"] == 1588.60
        assert giorno["diff_serale"] == 40.90
        assert giorno["fase2_per_circuito"]["numia"]["riconciliato"] is True
        assert giorno["fase2_per_circuito"]["numia"]["accredito"] == 867.30
        assert giorno["fase2_per_circuito"]["sumup"]["stato"] == "in_attesa_payout"
        assert result["statistiche"]["fase2_pos_totale"] == 867.30
        assert result["statistiche"]["fase2_sumup_pos_totale"] == 721.30

    _run(scenario())


def test_due_fasi_xml_senza_terminali_non_inventa_numia_o_sumup(monkeypatch):
    async def scenario():
        db = AsyncMongoMockClient()["test_xml_non_e_pos"]
        await db["corrispettivi"].insert_one({
            "data": "2026-08-01", "pagato_elettronico": 1620.70,
            "stato": "definitivo_xml", "entity_status": "active",
        })
        monkeypatch.setattr(pc.Database, "get_db", staticmethod(lambda: db))

        result = await pc.controllo_incassi_due_fasi(
            data_da=None, data_a=None, anno=2026, tolleranza_euro=0.50
        )
        giorno = next(g for g in result["giorni"] if g["data"] == "2026-08-01")

        assert giorno["xml_elettronico"] == 1620.70
        assert giorno["pos_per_circuito"] == {"numia": None, "sumup": None}
        assert giorno["pos_manuale_presente"] is False
        assert giorno["pos_manuale"] == 0

    _run(scenario())


def test_due_fasi_sumup_zero_esplicito_non_attende_un_payout(monkeypatch):
    async def scenario():
        db = AsyncMongoMockClient()["test_sumup_zero_esplicito"]
        await db["chiusure_pos_manuali"].insert_one({
            "data": "2026-08-02", "importo": 0,
            "gestore": "sumup", "source": "api_sumup",
        })
        monkeypatch.setattr(pc.Database, "get_db", staticmethod(lambda: db))

        result = await pc.controllo_incassi_due_fasi(
            data_da=None, data_a=None, anno=2026, tolleranza_euro=0.50
        )
        giorno = next(g for g in result["giorni"] if g["data"] == "2026-08-02")

        assert giorno["pos_per_circuito"]["sumup"] == 0
        assert giorno["fase2_per_circuito"]["sumup"]["stato"] == "nessun_incasso"
        assert result["statistiche"]["fase2_sumup_in_attesa_payout"] == 0

    _run(scenario())


def test_controllo_due_fasi_legge_e_somma_xml_drive_storici(monkeypatch):
    """I record Drive legacy usano pagato_pos e non avevano stato definitivo_xml."""
    async def scenario():
        db = AsyncMongoMockClient()["test_xml_drive_legacy"]
        await db["corrispettivi"].insert_many([
            {
                "data": "2026-01-02", "totale": 1000.00,
                "pagato_pos": 600.00, "pagato_contanti": 400.00,
                "content_hash": "hash-a", "filename": "rt-a.xml",
                "status": "imported", "entity_status": "active",
            },
            {
                "data": "2026-01-02", "totale": 250.00,
                "pagato_pos": 150.00, "pagato_contanti": 100.00,
                "content_hash": "hash-b", "filename": "rt-b.xml",
                "status": "imported", "entity_status": "active",
            },
        ])
        monkeypatch.setattr(pc.Database, "get_db", staticmethod(lambda: db))

        result = await pc.controllo_incassi_due_fasi(
            data_da=None, data_a=None, anno=2026, tolleranza_euro=0.50
        )
        giorno = next(g for g in result["giorni"] if g["data"] == "2026-01-02")

        assert giorno["stato_corrispettivo"] == "definitivo_xml"
        assert giorno["xml_elettronico"] == 750.00
        assert giorno["totale_xml"] == 1250.00

    _run(scenario())


def test_helper_preferisce_campo_elettronico_canonico_all_alias_storico():
    assert pc._importo_elettronico_xml({
        "pagato_elettronico": 321.45,
        "pagato_pos": 999.99,
    }) == 321.45


# --- NUMIA e NEXI sono lo stesso circuito ----------------------------------

def test_l_accredito_e_riconosciuto_con_entrambi_i_marchi():
    """In estratto conto compaiono sia NUMIA (chi accredita) sia NEXI (chi
    gestisce il terminale). Pretendere solo NUMIA lasciava i trasferimenti
    etichettati NEXI eternamente non riconciliati."""
    from app.services.pos_evidence import _e_accredito_pos_numia_con_giorno as riconosce

    assert riconosce("NUMIA INCAS. TRAMITE P.O.S. DEL 06/08/26") is True
    assert riconosce("NEXI INC. POS CARTE CREDIT DEL 06/08/26") is True


def test_le_righe_che_non_sono_accrediti_restano_escluse():
    """Allargare il marchio non deve far entrare commissioni e fatture."""
    from app.services.pos_evidence import _e_accredito_pos_numia_con_giorno as riconosce

    assert riconosce("NEXI PAGAMENTO COMMISSIONI DEL 06/08/26") is False
    assert riconosce("FATTURA NUMIA INCAS. TRAMITE P.O.S. DEL 06/08/26") is False
    assert riconosce("BONIFICO DA CLIENTE DEL 06/08/26") is False
    # Senza giorno operativo non si sa quale trasferimento chiuderebbe.
    assert riconosce("NEXI INCAS. TRAMITE P.O.S. senza giorno") is False
