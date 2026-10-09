"""Coerenza POS: si verifica solo cio' che ha un termine di confronto vero.

- un NUMIA ricavato dall'accredito BPM (manca la chiusura del terminale) vale
  come venduto per la fase 1, ma contro la banca non e' verificabile;
- BPM accredita il solo NUMIA, mai SumUp;
- il mensile registratore ↔ POS usa la regola della fase 1 sui giorni senza XML;
- una rettifica SumUp confermata chiude la giornata come un payout.
"""
import asyncio
from datetime import datetime, timedelta

from app.services.archivio_documenti_memoria import ClientArchivioMemoria

from app.routers import pos_corrispettivi_check as pc


def _run(coro):
    return asyncio.run(coro)


def _accredito(giorno_vendita: str, data_contabile: str, importo: float, marchio="NUMIA"):
    gg, mm, aaaa = giorno_vendita[8:10], giorno_vendita[5:7], giorno_vendita[2:4]
    return {
        "id": f"EC-{giorno_vendita}-{marchio}-{importo}",
        "data": data_contabile, "importo": importo,
        "descrizione_originale": (
            f"INC.POS CARTE CREDIT - {marchio}-INTER DEL {gg}/{mm}/{aaaa} PDV 3757283/00011"
        ),
    }


# --- 1. NUMIA senza chiusura del terminale ----------------------------------

def test_fase2_non_certifica_l_accredito_contro_se_stesso(monkeypatch):
    async def scenario():
        db = ClientArchivioMemoria()["test_numia_senza_chiusura"]
        await db["corrispettivi"].insert_one({
            "data": "2026-07-06", "pagato_elettronico": 900.00,
            "stato": "definitivo_xml",
        })
        await db["estratto_conto_movimenti"].insert_one(
            _accredito("2026-07-06", "2026-07-07", 867.30)
        )
        monkeypatch.setattr(pc.Database, "get_db", staticmethod(lambda: db))
        return await pc.controllo_incassi_due_fasi(
            data_da=None, data_a=None, anno=2026, tolleranza_euro=0.50
        )

    result = _run(scenario())
    giorno = next(g for g in result["giorni"] if g["data"] == "2026-07-06")
    stats = result["statistiche"]

    # Fase 1: l'accredito resta un proxy accettato del venduto.
    assert giorno["pos_manuale"] == 867.30
    assert giorno["stato_serale"] == "ok"
    # Fase 2: niente «ok», niente badge, niente saldo.
    assert giorno["stato_accredito"] == "senza_chiusura_terminale"
    assert giorno["riconciliato_banca_reale"] is False
    assert giorno["diff_accredito"] is None
    assert giorno["saldo_progressivo"] is None
    assert giorno["accredito_banca"] == 867.30
    assert stats["fase2_ok"] == 0
    assert stats["fase2_senza_chiusura_terminale"] == 1
    assert stats["fase2_saldo_finale"] == 0
    assert stats["fase2_pos_totale"] == 0
    assert stats["fase2_accrediti_totale"] == 0
    settimana = next(
        s for s in result["riepilogo_settimanale"] if s["data_inizio"] == "2026-07-06"
    )
    assert settimana["stato"] == "senza_chiusura_terminale"
    assert settimana["num_giorni_senza_chiusura_terminale"] == 1
    assert settimana["diff_totale"] == 0


def test_fase2_con_chiusura_numia_resta_verificata(monkeypatch):
    async def scenario():
        db = ClientArchivioMemoria()["test_numia_con_chiusura"]
        await db["chiusure_pos_manuali"].insert_one({
            "data": "2026-07-06", "importo": 867.30, "gestore": "numia",
            "source": "inserimento_manuale_terminale",
        })
        await db["estratto_conto_movimenti"].insert_one(
            _accredito("2026-07-06", "2026-07-07", 867.30)
        )
        monkeypatch.setattr(pc.Database, "get_db", staticmethod(lambda: db))
        return await pc.controllo_incassi_due_fasi(
            data_da=None, data_a=None, anno=2026, tolleranza_euro=0.50
        )

    result = _run(scenario())
    giorno = next(g for g in result["giorni"] if g["data"] == "2026-07-06")
    assert giorno["stato_accredito"] == "ok"
    assert giorno["riconciliato_banca_reale"] is True
    assert result["statistiche"]["fase2_ok"] == 1


def test_mensile_banca_non_verificabile_senza_chiusura_numia(monkeypatch):
    async def scenario():
        db = ClientArchivioMemoria()["test_mensile_numia_da_banca"]
        await db["estratto_conto_movimenti"].insert_one(
            _accredito("2026-07-06", "2026-07-07", 867.30)
        )
        monkeypatch.setattr(pc.Database, "get_db", staticmethod(lambda: db))
        return await pc.riepilogo_mensile_pos_corrispettivi(anno=2026)

    result = _run(scenario())
    luglio = result["mesi"][6]
    assert luglio["pos_accreditato"] == 867.30
    assert luglio["pos_numia"] == 867.30  # proxy del venduto (fase 1)
    assert luglio["differenza_pos_banca"] is None
    assert luglio["banca_verificabile"] is False
    assert luglio["pos_numia_senza_chiusura"] == 867.30
    assert luglio["giorni_numia_senza_chiusura"] == ["2026-07-06"]
    assert result["totali"]["differenza_pos_banca"] is None


def test_alert_banca_usa_l_importo_numia_non_numia_piu_sumup(monkeypatch):
    giorno = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")

    async def scenario():
        db = ClientArchivioMemoria()["test_alert_numia"]
        await db["chiusure_pos_manuali"].insert_many([
            {"data": giorno, "importo": 500.00, "gestore": "numia",
             "source": "inserimento_manuale_terminale"},
            {"data": giorno, "importo": 300.00, "gestore": "sumup",
             "source": "api_gestore_pos"},
        ])
        monkeypatch.setattr(pc.Database, "get_db", staticmethod(lambda: db))

        async def nessun_alert(*_args, **_kwargs):
            return None

        monkeypatch.setattr(pc, "_alert_pos_non_quadrato", nessun_alert)
        return await pc.alert_oggi(tolleranza_euro=0.5)

    result = _run(scenario())
    alert = next(a for a in result["alert_banca"] if a["data_incasso"] == giorno)
    assert alert["importo_atteso"] == 500.00
    assert "500.00" in alert["messaggio"]
    assert "800.00" not in alert["messaggio"]


def test_accredito_col_marchio_nexi_entra_nella_quadratura():
    """Numia e Nexi sono lo stesso circuito: la query non deve fermarsi a NUMIA."""
    async def scenario():
        db = ClientArchivioMemoria()["test_nexi_query"]
        await db["estratto_conto_movimenti"].insert_one(
            _accredito("2026-07-06", "2026-07-07", 410.50, marchio="NEXI")
        )
        return await pc._carica_accrediti_banca_pos(db, "2026-07-01", "2026-07-31")

    out = _run(scenario())
    assert out["2026-07-06"]["totale"] == 410.50


# --- 2. /verifica-coerenza: solo NUMIA contro BPM, calendario unico ----------

def test_verifica_coerenza_confronta_bpm_col_solo_numia(monkeypatch):
    async def scenario():
        db = ClientArchivioMemoria()["test_verifica_coerenza_numia"]
        await db["corrispettivi"].insert_one({
            "data": "2026-07-06", "pagato_elettronico": 1200.00,
            "stato": "definitivo_xml",
        })
        await db["chiusure_pos_manuali"].insert_many([
            {"data": "2026-07-06", "importo": 500.00, "gestore": "numia",
             "source": "inserimento_manuale_terminale"},
            {"data": "2026-07-06", "importo": 700.00, "gestore": "sumup",
             "source": "api_gestore_pos"},
        ])
        await db["estratto_conto_movimenti"].insert_one(
            _accredito("2026-07-06", "2026-07-07", 500.00)
        )
        monkeypatch.setattr(pc.Database, "get_db", staticmethod(lambda: db))
        return await pc.verifica_coerenza_pos_corrispettivi(
            data_da=None, data_a=None, anno=2026
        )

    result = _run(scenario())
    giorno = next(g for g in result["riepilogo_giornaliero"] if g["data"] == "2026-07-06")
    assert giorno["pos_numia"] == 500.00
    assert giorno["stato"] == "ok"
    assert giorno["differenza"] == 0
    # Il "non battuto" resta sul totale dei terminali (NUMIA + SumUp).
    assert giorno["non_battuto"] == 0


def test_verifica_coerenza_usa_il_calendario_con_i_festivi(monkeypatch):
    async def scenario():
        db = ClientArchivioMemoria()["test_verifica_coerenza_festivi"]
        await db["corrispettivi"].insert_one({
            "data": "2026-12-24", "pagato_elettronico": 100.00,
            "stato": "definitivo_xml",
        })
        monkeypatch.setattr(pc.Database, "get_db", staticmethod(lambda: db))
        return await pc.verifica_coerenza_pos_corrispettivi(
            data_da=None, data_a=None, anno=2026
        )

    result = _run(scenario())
    giorno = next(g for g in result["riepilogo_giornaliero"] if g["data"] == "2026-12-24")
    # Giovedi' 24/12: Natale e Santo Stefano slittano l'accredito al lunedi'.
    assert giorno["data_accredito_attesa"] == pc._data_accredito_attesa("2026-12-24")
    assert giorno["data_accredito_attesa"] != "2026-12-25"


# --- 3. Mensile registratore ↔ POS con la regola della fase 1 ----------------

def test_mensile_xml_pos_esclude_i_giorni_in_attesa_e_unisce_le_chiusure_doppie(monkeypatch):
    async def scenario():
        db = ClientArchivioMemoria()["test_mensile_fase1"]
        await db["corrispettivi"].insert_one({
            "data": "2026-09-09", "pagato_elettronico": 4111.80,
            "stato": "definitivo_xml",
        })
        await db["chiusure_pos_manuali"].insert_many([
            {"data": "2026-09-08", "importo": 2115.80, "gestore": "sumup",
             "source": "api_gestore_pos"},
            {"data": "2026-09-09", "importo": 1936.80, "gestore": "sumup",
             "source": "api_gestore_pos"},
            # Dopo l'ultima chiusura RT: l'XML non e' ancora arrivato.
            {"data": "2026-09-22", "importo": 1938.00, "gestore": "sumup",
             "source": "api_gestore_pos"},
        ])
        monkeypatch.setattr(pc.Database, "get_db", staticmethod(lambda: db))
        return await pc.riepilogo_mensile_pos_corrispettivi(anno=2026)

    result = _run(scenario())
    settembre = result["mesi"][8]
    assert settembre["pos_terminale"] == 5990.60  # colonna di consultazione
    assert settembre["pos_confrontato_xml"] == 4052.60
    assert settembre["differenza_xml_pos"] == 59.20  # 4111,80 - (2115,80 + 1936,80)
    assert settembre["pos_in_attesa_xml"] == 1938.00
    assert settembre["giorni_in_attesa_xml"] == ["2026-09-22"]
    assert settembre["giorni_chiusi_col_giorno_dopo"] == ["2026-09-08"]
    assert settembre["stato"] == "ok"
    assert result["totali"]["differenza_xml_pos"] == 59.20
    assert result["totali"]["pos_in_attesa_xml"] == 1938.00


# --- 9. Rettifica SumUp confermata -------------------------------------------

def test_rettifica_confermata_chiude_la_giornata_sumup(monkeypatch):
    async def scenario():
        db = ClientArchivioMemoria()["test_rettifica_sumup"]
        await db["chiusure_pos_manuali"].insert_one({
            "data": "2026-08-03", "importo": 721.30, "gestore": "sumup",
            "source": "api_gestore_pos",
        })
        await db["sumup_payouts"].insert_many([
            {"payout_id": "P-1", "data": "2026-08-04", "netto": 707.55,
             "commissione": 13.75, "giorni": ["2026-08-03"],
             "stato_riconciliazione": "riconciliato"},
            {"payout_id": "R-1", "data": "2026-08-04", "netto": -1.01,
             "commissione": 0.0, "giorni": ["2026-08-03"],
             "tipo_record": "rettifica",
             "stato_riconciliazione": "rettifica_confermata"},
        ])
        monkeypatch.setattr(pc.Database, "get_db", staticmethod(lambda: db))
        per_giorno = await pc._carica_payout_sumup_per_giorno(db, "2026-08-01", "2026-08-31")
        due_fasi = await pc.controllo_incassi_due_fasi(
            data_da=None, data_a=None, anno=2026, tolleranza_euro=0.50
        )
        mensile = await pc.riepilogo_mensile_pos_corrispettivi(anno=2026)
        return per_giorno, due_fasi, mensile

    per_giorno, due_fasi, mensile = _run(scenario())
    giorno = per_giorno["2026-08-03"]
    assert giorno["riconciliato"] is True
    assert giorno["netto_gruppi"] == 707.55
    assert giorno["rettifiche_gruppi"] == 1.01
    riga = next(g for g in due_fasi["giorni"] if g["data"] == "2026-08-03")
    assert riga["fase2_per_circuito"]["sumup"]["stato"] == "riconciliato"
    agosto = mensile["mesi"][7]
    assert agosto["sumup_pagato"] == 707.55
    assert agosto["sumup_rettifiche"] == 1.01


def test_rettifica_da_verificare_lascia_aperta_la_giornata():
    async def scenario():
        db = ClientArchivioMemoria()["test_rettifica_aperta"]
        await db["sumup_payouts"].insert_many([
            {"payout_id": "P-1", "data": "2026-08-04", "netto": 707.55,
             "giorni": ["2026-08-03"], "stato_riconciliazione": "riconciliato"},
            {"payout_id": "R-1", "data": "2026-08-04", "netto": -1.01,
             "giorni": ["2026-08-03"], "tipo_record": "rettifica",
             "stato_riconciliazione": "rettifica_da_verificare"},
        ])
        return await pc._carica_payout_sumup_per_giorno(db, "2026-08-01", "2026-08-31")

    assert _run(scenario())["2026-08-03"]["riconciliato"] is False
