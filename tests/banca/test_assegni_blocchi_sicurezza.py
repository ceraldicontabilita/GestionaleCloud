"""Assegni: le regole che la «Logica canonica carnet e assegni» del titolare
dà per vincolanti (§2, §8, §9, §10, §11, §13).

- un numero emesso non torna disponibile;
- l'annullo e lo storno riaprono le fatture che l'assegno pagava;
- ogni modifica lascia lo storico, e l'importo cambiato dopo la banca rimette
  la riconciliazione da verificare;
- un addebito in banca si lega a un assegno solo con numero **e** importo;
- lo stesso assegno registrato due volte diventa una scheda sola.

Il caso dei doppioni è quello di produzione (28/09/2026): 19 numeri, ognuno
in due schede da due export BPM («EC-2026-03-26-1247.01-…» con la data
operazione e «2026-03-30_-1247.01_VOSTRO_ASSEGNO_N_…» con la valuta), e la
fattura collegata alla sola copia orfana.
"""
import asyncio

import pytest

from app.routers.bank import assegni as assegni_router
from app.services import assegni_doppioni
from app.services.archivio_documenti_memoria import ClientArchivioMemoria


def _run(coroutine):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coroutine)
    finally:
        loop.close()


def _db(monkeypatch, nome):
    db = ClientArchivioMemoria()[nome]
    monkeypatch.setattr(assegni_router.Database, "get_db", staticmethod(lambda: db))
    return db


def _stato_http(exc_info):
    return getattr(exc_info.value, "status_code", None)


# ── numero consumato ──────────────────────────────────────────────────────

def test_un_numero_emesso_non_torna_disponibile(monkeypatch):
    db = _db(monkeypatch, "numero_consumato")
    _run(db["assegni"].insert_one({"id": "a1", "numero": "0208770641", "stato": "emesso", "importo": 10.0}))
    for stato in ("vuoto", "compilato"):
        with pytest.raises(Exception) as exc:
            _run(assegni_router.update_assegno("a1", {"stato": stato}))
        assert _stato_http(exc) == 409
    assert _run(db["assegni"].find_one({"id": "a1"}))["stato"] == "emesso"


def test_annullo_e_storno_non_passano_dal_put(monkeypatch):
    db = _db(monkeypatch, "annullo_put")
    _run(db["assegni"].insert_one({"id": "a1", "numero": "1", "stato": "emesso", "importo": 10.0}))
    with pytest.raises(Exception) as exc:
        _run(assegni_router.update_assegno("a1", {"stato": "annullato"}))
    assert _stato_http(exc) == 409


def test_si_cancellano_in_blocco_solo_i_moduli_vuoti(monkeypatch):
    db = _db(monkeypatch, "clear")
    _run(db["assegni"].insert_many([
        {"id": "v", "numero": "1", "stato": "vuoto"},
        {"id": "a", "numero": "2", "stato": "annullato"},
    ]))
    with pytest.raises(Exception) as exc:
        _run(assegni_router.clear_generated_assegni(stato="annullato"))
    assert _stato_http(exc) == 400
    assert _run(assegni_router.clear_generated_assegni(stato="vuoto"))["deleted_count"] == 1
    assert _run(db["assegni"].find_one({"id": "a"}))["stato"] == "annullato"


# ── annullo e storno riaprono le fatture ──────────────────────────────────

def _assegno_con_fattura(db):
    _run(db["assegni"].insert_one({
        "id": "a1", "numero": "0208770650", "stato": "assegnato", "importo": 300.0,
        "fatture_collegate": [{"fattura_id": "f1", "quota": 300.0}], "fattura_collegata": "f1",
    }))
    _run(db["invoices"].insert_one({
        "id": "f1", "invoice_number": "12/A", "total_amount": 300.0, "metodo_pagamento": "assegno",
        "metodo_pagamento_fornitore_originale": "bonifico", "stato_finanziario": "in_attesa_estratto_conto",
        "assegni_collegati": [{"assegno_id": "a1", "quota": 300.0}],
    }))


def test_l_annullo_chiede_il_motivo_consuma_il_numero_e_riapre_la_fattura(monkeypatch):
    db = _db(monkeypatch, "annullo")
    _assegno_con_fattura(db)

    esito = _run(assegni_router.annulla_assegno("a1", assegni_router.AnnulloAssegnoIn(motivo="Scritto male")))
    assert esito["fatture_riaperte"] == 1

    a = _run(db["assegni"].find_one({"id": "a1"}))
    assert (a["stato"], a["stato_pre_annullo"], a["motivo_annullo"]) == ("annullato", "assegnato", "Scritto male")
    assert a["fatture_collegate"] == [] and a["fatture_prima_dell_annullo"][0]["fattura_id"] == "f1"
    assert a["storico"][-1]["azione"] == "annullo"
    f = _run(db["invoices"].find_one({"id": "f1"}))
    assert f["assegni_collegati"] == [] and f["metodo_pagamento"] == "bonifico"
    assert f["stato_finanziario"] == "provvisoria"
    # ... e il numero annullato non torna disponibile
    with pytest.raises(Exception):
        _run(assegni_router.update_assegno("a1", {"stato": "vuoto"}))


def test_un_assegno_gia_addebitato_non_si_annulla(monkeypatch):
    db = _db(monkeypatch, "annullo_banca")
    _run(db["assegni"].insert_one({"id": "a1", "numero": "1", "stato": "incassato",
                                   "incassato_confermato_banca": True}))
    with pytest.raises(Exception) as exc:
        _run(assegni_router.annulla_assegno("a1", assegni_router.AnnulloAssegnoIn(motivo="prova")))
    assert _stato_http(exc) == 409


def test_lo_storno_riapre_la_fattura(monkeypatch):
    db = _db(monkeypatch, "storno")
    _assegno_con_fattura(db)
    _run(assegni_router.storna_assegno("a1", assegni_router.StornoAssegnoIn(motivo="Respinto")))
    assert _run(db["invoices"].find_one({"id": "f1"}))["assegni_collegati"] == []
    assert _run(db["assegni"].find_one({"id": "a1"}))["fatture_prima_dello_storno"][0]["fattura_id"] == "f1"


# ── compilare l'assegno dichiara la fattura pagata in banca ────────────────

def _assegno_da_compilare(db):
    _run(db["assegni"].insert_one({
        "id": "a1", "numero": "0208770651", "stato": "compilato", "importo": 300.0,
    }))
    _run(db["invoices"].insert_one({
        "id": "f1", "invoice_number": "12/A", "total_amount": 300.0,
        "importo_residuo": 300.0, "pagato": False,
    }))


def test_compilare_l_assegno_dichiara_la_fattura_pagata_in_prima_nota_banca(monkeypatch):
    db = _db(monkeypatch, "compila_dichiara")
    _assegno_da_compilare(db)

    _run(assegni_router.collega_fatture_assegno(
        "a1", assegni_router.FattureCollegateIn(fatture=[
            assegni_router.FatturaQuotaIn(fattura_id="f1", quota=300.0),
        ]),
    ))

    f = _run(db["invoices"].find_one({"id": "f1"}))
    assert f["pagato"] is True and f["in_attesa_riscontro_banca"] is True
    assert f["stato_finanziario"] == "pagata_dichiarata_in_attesa_banca"
    assert f["metodo_pagamento_dichiarato"] == "assegno"
    assert f["assegno_numero_dichiarato"] == "0208770651"
    righe = _run(db["prima_nota_banca"].find(
        {"fattura_id": "f1", "status": {"$nin": ["deleted", "archived"]}}, {"_id": 0}).to_list(10))
    assert len(righe) == 1
    assert righe[0]["dichiarato_titolare"] is True
    assert righe[0]["importo"] == 300.0


def test_annullare_l_assegno_ritira_la_dichiarazione_e_riapre_la_fattura(monkeypatch):
    db = _db(monkeypatch, "compila_annulla")
    _assegno_da_compilare(db)
    _run(assegni_router.collega_fatture_assegno(
        "a1", assegni_router.FattureCollegateIn(fatture=[
            assegni_router.FatturaQuotaIn(fattura_id="f1", quota=300.0),
        ]),
    ))

    _run(assegni_router.annulla_assegno("a1", assegni_router.AnnulloAssegnoIn(motivo="Scritto male")))

    f = _run(db["invoices"].find_one({"id": "f1"}))
    assert f["pagato"] is False and f["in_attesa_riscontro_banca"] is False
    assert f["metodo_pagamento"] == "sospesa"
    # _aggiorna_stato_intento_fattura riscrive lo stato dopo il ritiro.
    assert f["stato_finanziario"] == "provvisoria"
    riga = _run(db["prima_nota_banca"].find_one({"fattura_id": "f1"}))
    assert riga["status"] == "deleted"


def test_stornare_l_assegno_ritira_la_dichiarazione_e_riapre_la_fattura(monkeypatch):
    db = _db(monkeypatch, "compila_storna")
    _assegno_da_compilare(db)
    _run(assegni_router.collega_fatture_assegno(
        "a1", assegni_router.FattureCollegateIn(fatture=[
            assegni_router.FatturaQuotaIn(fattura_id="f1", quota=300.0),
        ]),
    ))

    _run(assegni_router.storna_assegno("a1", assegni_router.StornoAssegnoIn(motivo="Respinto in banca")))

    f = _run(db["invoices"].find_one({"id": "f1"}))
    assert f["pagato"] is False and f["in_attesa_riscontro_banca"] is False
    riga = _run(db["prima_nota_banca"].find_one({"fattura_id": "f1"}))
    assert riga["status"] == "deleted"


def test_ricollegare_l_assegno_a_un_altra_fattura_ritira_la_vecchia_dichiarazione(monkeypatch):
    db = _db(monkeypatch, "compila_ricollega")
    _assegno_da_compilare(db)
    _run(db["invoices"].insert_one({
        "id": "f2", "invoice_number": "13/B", "total_amount": 300.0,
        "importo_residuo": 300.0, "pagato": False,
    }))
    _run(assegni_router.collega_fatture_assegno(
        "a1", assegni_router.FattureCollegateIn(fatture=[
            assegni_router.FatturaQuotaIn(fattura_id="f1", quota=300.0),
        ]),
    ))
    # Il titolare si accorge di aver sbagliato fattura e la sostituisce.
    _run(assegni_router.collega_fatture_assegno(
        "a1", assegni_router.FattureCollegateIn(fatture=[
            assegni_router.FatturaQuotaIn(fattura_id="f2", quota=300.0),
        ]),
    ))

    f1 = _run(db["invoices"].find_one({"id": "f1"}))
    f2 = _run(db["invoices"].find_one({"id": "f2"}))
    assert f1["pagato"] is False and f1["in_attesa_riscontro_banca"] is False
    assert f2["pagato"] is True and f2["in_attesa_riscontro_banca"] is True
    riga_vecchia = _run(db["prima_nota_banca"].find_one({"fattura_id": "f1"}))
    assert riga_vecchia["status"] == "deleted"
    righe_nuove = _run(db["prima_nota_banca"].find(
        {"fattura_id": "f2", "status": {"$nin": ["deleted", "archived"]}}, {"_id": 0}).to_list(10))
    assert len(righe_nuove) == 1


# ── storico ───────────────────────────────────────────────────────────────

def test_ogni_modifica_lascia_valore_precedente_e_nuovo(monkeypatch):
    db = _db(monkeypatch, "storico")
    _run(db["assegni"].insert_one({"id": "a1", "numero": "1", "stato": "compilato",
                                   "importo": 100.0, "beneficiario": "Rossi"}))
    _run(assegni_router.update_assegno("a1", {"beneficiario": "Bianchi", "storico": ["finto"]}))
    a = _run(db["assegni"].find_one({"id": "a1"}))
    assert a["storico"][-1]["campi"]["beneficiario"] == {"prima": "Rossi", "dopo": "Bianchi"}
    assert "finto" not in a["storico"]


def test_l_importo_cambiato_dopo_la_banca_rimette_la_riconciliazione_da_verificare(monkeypatch):
    db = _db(monkeypatch, "importo_dopo_banca")
    _run(db["assegni"].insert_one({"id": "a1", "numero": "1", "stato": "incassato", "importo": 100.0,
                                   "incassato_confermato_banca": True}))
    _run(assegni_router.update_assegno("a1", {"importo": 110.0}))
    a = _run(db["assegni"].find_one({"id": "a1"}))
    assert a["riscontro_banca_da_verificare"]["importo_precedente"] == 100.0


# ── lo stesso assegno due volte ───────────────────────────────────────────

COPIA_ORFANA = {
    "id": "07241e09", "numero": "0208770641", "importo": 1247.01, "stato": "incassato",
    "movimento_id": "EC-2026-03-26-1247.01-203d6e87", "prima_nota_banca_id": "pn-1",
    "fattura_collegata": "f-641", "fatture_collegate": [{"fattura_id": "f-641", "quota": 1247.01}],
    "created_at": "2026-04-01",
}
SCHEDA_BUONA = {
    "id": "8c25e754", "numero": "0208770641", "importo": 1247.01, "stato": "incassato",
    "movimento_id": "2026-03-30_-1247.01_VOSTRO_ASSEGNO_N_02087706", "prima_nota_banca_id": "pn-1",
    "created_at": "2026-05-01",
}


def _db_doppioni():
    db = ClientArchivioMemoria()["doppioni_assegni"]

    async def carica():
        await db["assegni"].insert_many([dict(COPIA_ORFANA), dict(SCHEDA_BUONA)])
        await db["estratto_conto_movimenti"].insert_one({
            "id": SCHEDA_BUONA["movimento_id"], "descrizione": "VOSTRO ASSEGNO N. 0208770641",
            "assegno_id": "07241e09",
        })
        await db["prima_nota_banca"].insert_one({"id": "pn-1", "assegno_id": "07241e09"})
        await db["invoices"].insert_one({"id": "f-641", "assegni_collegati": [
            {"assegno_id": "07241e09", "quota": 1247.01}]})
    _run(carica())
    return db


def test_resta_la_scheda_col_movimento_vivo_e_prende_la_fattura_della_copia():
    db = _db_doppioni()
    esito = _run(assegni_doppioni.unifica(db))
    assert (esito["copie"], esito["fatture_cedute"]) == (1, 1)

    assert [a["id"] for a in _run(db["assegni"].find({}).to_list(10))] == ["8c25e754"]
    resta = _run(db["assegni"].find_one({"id": "8c25e754"}))
    assert resta["fattura_collegata"] == "f-641"
    assert _run(db["invoices"].find_one({"id": "f-641"}))["assegni_collegati"][0]["assegno_id"] == "8c25e754"
    assert _run(db["prima_nota_banca"].find_one({"id": "pn-1"}))["assegno_id"] == "8c25e754"
    assert _run(db["estratto_conto_movimenti"].find_one({}))["assegno_id"] == "8c25e754"
    copia = _run(db["assegni_quarantena"].find_one({"id": "07241e09"}))
    assert copia["duplicato_di"] == "8c25e754" and copia["motivo_quarantena"] == assegni_doppioni.MOTIVO

    assert _run(assegni_doppioni.unifica(db))["copie"] == 0  # il secondo giro non fa niente


def test_in_simulazione_non_si_sposta_niente():
    db = _db_doppioni()
    assert _run(assegni_doppioni.unifica(db, dry_run=True))["copie"] == 1
    assert len(_run(db["assegni"].find({}).to_list(10))) == 2


def test_stesso_numero_con_importo_diverso_non_e_un_doppione():
    db = _db_doppioni()
    _run(db["assegni"].update_one({"id": "8c25e754"}, {"$set": {"importo": 1247.02}}))
    assert _run(assegni_doppioni.unifica(db))["copie"] == 0


def test_due_schede_che_pagano_fatture_diverse_restano_e_si_segnalano():
    db = _db_doppioni()
    _run(db["assegni"].update_one({"id": "8c25e754"}, {"$set": {"fattura_collegata": "f-altra"}}))
    esito = _run(assegni_doppioni.unifica(db))
    assert esito["copie"] == 0 and esito["in_conflitto"][0]["numero"] == "0208770641"


# ── la banca lega l'addebito solo con numero e importo ────────────────────

def test_stesso_numero_ma_importo_diverso_non_si_riconcilia():
    from app.services.assegni_estratto_conto import sincronizza_assegni_da_estratto_conto

    db = ClientArchivioMemoria()["banca_importo"]

    async def scenario():
        await db["assegni"].insert_one({"id": "a1", "numero": "0208770700", "importo": 500.0,
                                        "stato": "emesso"})
        await db["estratto_conto_movimenti"].insert_one({
            "id": "m1", "data": "2026-04-02", "importo": -550.0, "tipo": "uscita",
            "descrizione": "VOSTRO ASSEGNO N. 0208770700", "livello_evidenza": "ufficiale",
            "evidenza_bancaria_ufficiale": True,
        })
        return await sincronizza_assegni_da_estratto_conto(db, movimento_ids=["m1"])

    esito = _run(scenario())
    assert esito["importo_diverso"][0]["importo_banca"] == 550.0
    a = _run(db["assegni"].find_one({"id": "a1"}))
    assert a["stato"] == "emesso" and not a.get("incassato_confermato_banca")
    assert a["riscontro_banca_da_verificare"]["movimento_id"] == "m1"


def test_l_addebito_senza_scheda_crea_l_assegno_da_recuperare():
    from app.services.assegni_estratto_conto import sincronizza_assegni_da_estratto_conto

    db = ClientArchivioMemoria()["banca_senza_scheda"]

    async def scenario():
        await db["estratto_conto_movimenti"].insert_one({
            "id": "m2", "data": "2026-04-02", "importo": -80.0, "tipo": "uscita",
            "descrizione": "VOSTRO ASSEGNO N. 0208770701", "livello_evidenza": "ufficiale",
            "evidenza_bancaria_ufficiale": True,
        })
        await sincronizza_assegni_da_estratto_conto(db, movimento_ids=["m2"])

    _run(scenario())
    a = _run(db["assegni"].find_one({"numero": "0208770701"}))
    assert a["rilevato_da_banca"] and a["documento_da_recuperare"]
