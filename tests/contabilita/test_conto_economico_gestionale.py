"""Conto economico gestionale: ricavi RT, personale, IVA da classificare, Banca.

Regressioni dei difetti misurati sui dati live del 27/09/2026:

- il costo del personale sommava ``costo_azienda``, campo che nessuna busta
  ha: la Dashboard mostrava 0 e un utile falso;
- i corrispettivi con ``status: deleted`` e ``entity_status`` vuoto (30 righe
  di luglio) restavano nei ricavi, e quelli senza ``totale_imponibile`` (19
  righe di agosto) ne uscivano o vi entravano al lordo;
- il conto economico del Bilancio non aveva il personale e dichiarava UTILE;
- «Banca» fondeva BPM, righe senza conto e Mastercard SumUp;
- ``iva_detraibile`` assente valeva 0 nel saldo IVA;
- il budget prendeva il lordo ``totale`` quando mancava ``totale_imponibile``;
- la chiusura d'esercizio bloccava febbraio, chiuso per ristrutturazione.
"""
import asyncio

from app.services.archivio_documenti_memoria import ClientArchivioMemoria

from app.routers import controllo_gestione, finanziaria
from app.routers import chiusura_esercizio as chiusura_mod
from app.routers.accounting import bilancio, contabilita_gestionale
from app.services import conto_economico_gestionale as ceg


def _run(coro):
    return asyncio.run(coro)


def _db(monkeypatch, nome):
    db = ClientArchivioMemoria()[nome]
    monkeypatch.setattr(controllo_gestione.Database, "get_db", staticmethod(lambda: db))
    return db


def _semina(db):
    _run(db["corrispettivi"].insert_many([
        {"id": "lug", "data": "2026-07-10", "totale": 110.0,
         "totale_imponibile": 100.0, "totale_iva": 10.0},
        # Stessa giornata cancellata col solo ``status``: fuori dai ricavi.
        {"id": "lug-canc", "data": "2026-07-10", "totale": 110.0,
         "totale_imponibile": 100.0, "totale_iva": 10.0,
         "status": "deleted", "entity_status": ""},
        {"id": "lug-arch", "data": "2026-07-11", "totale": 11.0,
         "totale_imponibile": 10.0, "totale_iva": 1.0, "status": "archiviata"},
        # Storico: niente ``totale_imponibile``, vale ``imponibile``.
        {"id": "ago", "data": "2026-08-05", "totale": 55.0,
         "imponibile": 50.0, "iva": 5.0},
        # Solo il lordo, senza IVA dichiarata: non e' un imponibile.
        {"id": "ago-lordo", "data": "2026-08-06", "totale": 22.0},
    ]))
    _run(db["invoices"].insert_many([
        {"id": "f-lug", "invoice_date": "2026-07-12", "tipo_documento": "TD01",
         "imponibile": 40.0, "iva": 8.8, "iva_detraibile": 8.8, "total_amount": 48.8},
        # IVA detraibile mai valutata: il saldo IVA non si conosce.
        {"id": "f-ago", "invoice_date": "2026-08-01", "tipo_documento": "TD01",
         "imponibile": 10.0, "iva": 2.2, "total_amount": 12.2},
        {"id": "f-ago-arch", "invoice_date": "2026-08-01", "tipo_documento": "TD01",
         "imponibile": 10.0, "iva": 2.2, "total_amount": 12.2, "status": "archiviata"},
    ]))
    _run(db["cedolini"].insert_many([
        {"id": "b-lug", "anno": 2026, "mese": 7, "lordo": 30.0,
         "costo_azienda": None},
        {"id": "b-ago", "anno": 2026, "mese": 8, "lordo": None},
    ]))


# ---------------------------------------------------------------- servizio

def test_filtro_corrispettivi_esclude_tutti_gli_stati_cancellati():
    assert ceg.FILTRO_CORRISPETTIVI_VALIDI == {
        "entity_status": {"$ne": "deleted"},
        "status": {"$nin": ["deleted", "archived", "archiviata"]},
    }


def test_imponibile_corrispettivo_mai_dal_lordo():
    assert ceg.imponibile_corrispettivo({"totale_imponibile": 100, "totale": 122}) == 100
    assert ceg.imponibile_corrispettivo({"totale_imponibile": 0, "imponibile": 80}) == 80
    assert ceg.imponibile_corrispettivo({"totale": 122, "totale_iva": 22}) == 100
    assert ceg.imponibile_corrispettivo({"totale": 122}) is None


def test_ricavi_corrispettivi_filtrano_e_ripiegano_su_imponibile(monkeypatch):
    db = _db(monkeypatch, "ceg_ricavi")
    _semina(db)
    ricavi = _run(ceg.ricavi_corrispettivi(db, {"$gte": "2026-01-01", "$lte": "2026-12-31"}))
    assert ricavi["imponibile"] == 150.0
    assert ricavi["per_mese"] == {7: 100.0, 8: 50.0}
    assert ricavi["documenti"] == 3
    assert ricavi["senza_imponibile"] == 1


def test_costo_personale_e_il_lordo_delle_buste(monkeypatch):
    db = _db(monkeypatch, "ceg_personale")
    _semina(db)
    anno = _run(ceg.costo_personale(db, 2026))
    assert anno["lordo"] == 30.0
    assert anno["buste"] == 2
    assert anno["buste_senza_lordo"] == 1
    assert anno["contributi"] is None
    assert anno["incompleto"] is True
    # Agosto ha solo una busta senza lordo, settembre nessuna: non costano 0.
    assert _run(ceg.costo_personale(db, 2026, 8))["lordo"] is None
    assert _run(ceg.costo_personale(db, 2026, 9))["lordo"] is None


# -------------------------------------------------- 1. Dashboard / controllo

def test_dashboard_personale_dal_lordo_e_contributi_dichiarati(monkeypatch):
    db = _db(monkeypatch, "ceg_dashboard")
    _semina(db)
    r = _run(controllo_gestione.get_analisi_costi_ricavi(anno=2026))
    assert r["ricavi"]["totale"] == 150.0
    assert r["costi"]["personale"] == 30.0
    assert r["costi"]["personale_contributi"] is None
    assert r["costi"]["personale_incompleto"] is True
    assert r["costi"]["acquisti_merce"] == 50.0  # la copia archiviata non conta
    assert r["costi"]["totale"] == 80.0
    assert r["margine"]["importo"] == 70.0


def test_dashboard_mese_senza_buste_non_e_un_utile(monkeypatch):
    db = _db(monkeypatch, "ceg_dashboard_mese")
    _semina(db)
    r = _run(controllo_gestione.get_analisi_costi_ricavi(anno=2026, mese=8))
    assert r["ricavi"]["totale"] == 50.0
    assert r["costi"]["personale"] is None
    assert r["costi"]["totale"] is None
    assert r["margine"]["importo"] is None
    assert r["margine"]["tipo"] is None

    trend = _run(controllo_gestione.get_trend_mensile(anno=2026))
    luglio = trend["trend"][6]
    assert luglio["margine"] == 100.0 - (30.0 + 40.0)
    assert trend["trend"][7]["margine"] is None
    assert trend["totale_anno"]["margine"] is None


# ------------------------------------------------ 2-3. Bilancio: CE e IVA

def test_bilancio_conto_economico_con_personale_e_iva_da_classificare(monkeypatch):
    db = _db(monkeypatch, "ceg_bilancio_ce")
    _semina(db)
    ce = _run(bilancio.get_conto_economico(anno=2026, mese=None))
    assert ce["ricavi"]["corrispettivi"] == 150.0
    assert ce["costi"]["costi_netti"] == 50.0
    assert ce["costi"]["personale"] == 30.0
    assert ce["costi"]["personale_contributi"] is None
    assert ce["costi"]["personale_incompleto"] is True
    assert ce["costi"]["totale_costi"] == 80.0
    assert ce["risultato"]["utile_perdita"] == 70.0
    assert ce["risultato"]["incompleto"] is True
    # Una fattura attiva senza iva_detraibile: IVA a credito ignota.
    assert ce["dettaglio_iva"]["fatture_iva_da_classificare"] == 1
    assert ce["dettaglio_iva"]["iva_acquisti"] is None
    assert ce["dettaglio_iva"]["iva_netta"] is None


def test_bilancio_mese_senza_buste_non_dichiara_utile(monkeypatch):
    db = _db(monkeypatch, "ceg_bilancio_mese")
    _semina(db)
    ce = _run(bilancio.get_conto_economico(anno=2026, mese=8))
    assert ce["ricavi"]["corrispettivi"] == 50.0
    assert ce["costi"]["totale_costi"] is None
    assert ce["risultato"]["utile_perdita"] is None
    assert ce["risultato"]["tipo"] == "non_determinabile"


# ---------------------------------------------------- 7. Banca per conto

def _semina_banca(db):
    _run(db["prima_nota_banca"].insert_many([
        {"id": "bpm", "data": "2026-03-01", "tipo": "entrata", "importo": 100.0,
         "conto_contabile": "19.01.01"},
        {"id": "storica", "data": "2026-03-02", "tipo": "entrata", "importo": 50.0},
        {"id": "sumup", "data": "2026-03-03", "tipo": "entrata", "importo": 20.0,
         "conto_contabile": "19.01.05"},
    ]))


def test_stato_patrimoniale_separa_bpm_e_sumup(monkeypatch):
    db = _db(monkeypatch, "ceg_sp_banca")
    _semina_banca(db)
    sp = _run(bilancio.get_stato_patrimoniale(anno=2026, mese=None, data_a=None))
    liquide = sp["attivo"]["disponibilita_liquide"]
    assert liquide["banca"] == 150.0
    assert liquide["mastercard_sumup"] == 20.0
    assert liquide["altri_conti_banca"] == 0.0
    assert liquide["totale"] == 170.0
    assert liquide["fonte"] == "saldi_prima_nota"


def test_finanziaria_separa_bpm_sumup_e_iva_da_classificare(monkeypatch):
    db = _db(monkeypatch, "ceg_finanziaria")
    _semina(db)
    _semina_banca(db)
    r = _run(finanziaria.get_financial_summary(anno=2026))
    assert r["banca"]["saldo"] == 150.0
    assert r["banca"]["saldo_certificato"] is False
    assert r["sumup"]["saldo"] == 20.0
    assert r["saldo_totale"] == 170.0
    assert r["vat_balance"] is None
    assert r["vat_credit"] is None
    assert r["vat_status"].startswith("Da classificare")
    assert r["vat_da_classificare"] == 1
    # I corrispettivi cancellati o archiviati non portano IVA a debito.
    assert r["corrispettivi"]["count"] == 3


# ------------------------------------------------------------- 9. Budget

def test_budget_consuntivo_imponibile_mai_lordo_e_personale(monkeypatch):
    db = _db(monkeypatch, "ceg_budget")
    _semina(db)
    r = _run(contabilita_gestionale.get_budget_vs_consuntivo(2026, mese=None))
    andamento = {m["mese"]: m for m in r["andamento_mensile"]}
    assert andamento[7]["ricavi_consuntivo"] == 100.0
    assert andamento[8]["ricavi_consuntivo"] == 50.0  # non 55 (lordo) ne' 77
    # Luglio: fattura 40 + personale 30.
    assert andamento[7]["costi_consuntivo"] == 70.0
    assert r["personale"]["mensile"][7] == 30.0
    assert r["personale"]["mensile"][8] is None
    assert r["personale"]["contributi"] is None
    assert r["totali"]["ricavi"]["consuntivo"] == 150.0


# ------------------------------------------------- 10. Chiusura esercizio

def test_chiusura_non_blocca_i_mesi_di_chiusura_attivita(monkeypatch):
    db = _db(monkeypatch, "ceg_chiusura")
    _run(db["corrispettivi"].insert_many([
        {"id": f"c{m}", "data": f"2026-{m:02d}-10", "totale_imponibile": 10.0}
        for m in range(1, 13) if m != 2
    ]))
    # Marzo ha solo un corrispettivo cancellato: e' davvero mancante.
    _run(db["corrispettivi"].delete_one({"id": "c3"}))
    _run(db["corrispettivi"].insert_one({
        "id": "c3-canc", "data": "2026-03-20", "totale_imponibile": 10.0,
        "status": "deleted",
    }))
    _run(db["chiusure_attivita"].insert_one({
        "id": "ristrutturazione", "data_inizio": "2026-01-26",
        "data_fine": "2026-03-08", "motivo": "ristrutturazione",
    }))

    async def registro(_db, _anno, dettaglio=False):
        return {
            "fonte": "movimenti_contabili",
            "quadratura": True,
            "totali": {"dare": 100.0, "avere": 100.0, "sbilancio": 0.0},
            "qualita_registro": {
                "registro_valido": True, "scritture_sbilanciate": 0,
                "scritture_senza_righe": 0, "righe_non_numeriche": 0,
                "righe_senza_conto": 0,
            },
            "completezza_registro": {
                "scritture_registrate": 1, "fatture_da_registrare": 0,
                "corrispettivi_da_registrare": 0, "documenti_da_registrare": 0,
                "completo": True,
            },
            "conti": [],
        }

    monkeypatch.setattr(chiusura_mod, "_bilancio_verifica_da_registro", registro)
    r = _run(chiusura_mod.verifica_preliminare_chiusura(2026))
    mancanti = [p for p in r["problemi_bloccanti"] if p["tipo"] == "mesi_corrispettivi_mancanti"]
    assert len(mancanti) == 1
    assert mancanti[0]["messaggio"] == "Nessun corrispettivo nei mesi: 3"


# ------------------------------------------- 2. altri riepiloghi dei ricavi

def test_backlog_registro_non_conta_i_corrispettivi_cancellati(monkeypatch):
    db = _db(monkeypatch, "ceg_backlog")
    _semina(db)
    r = _run(contabilita_gestionale._bilancio_verifica_da_registro(db, 2026, False))
    # Registro vuoto: ogni corrispettivo valido e' da registrare, i
    # cancellati/archiviati no (erano 5 righe, ne valgono 3).
    assert r["completezza_registro"]["corrispettivi_da_registrare"] == 3


def test_trend_dashboard_non_somma_i_corrispettivi_cancellati(monkeypatch):
    from app.routers.reports import dashboard as dashboard_mod

    db = _db(monkeypatch, "ceg_trend_dashboard")
    _semina(db)
    r = _run(dashboard_mod.get_trend_mensile.__wrapped__(anno=2026))
    mesi = {m["mese"]: m for m in r["trend_mensile"]}
    assert mesi[7]["entrate"] == 110.0  # non 231, con cancellato e archiviato
