"""Collaudo funzionale: POS, chiusura del terminale e accredito bancario.

Tre fatti distinti (CLAUDE.md, «Regole contabili vincolanti»): corrispettivo XML,
chiusura del terminale, accredito in banca. L'estratto conto e' un'evidenza
successiva: **soddisfa** l'attesa creata dal terminale, non la crea mai.

* accredito riconosciuto solo con causale del circuito + giorno operativo
  `DEL gg/mm/aa`; Numia e Nexi sono lo stesso circuito; commissioni escluse;
* attesa mancante o multipla -> `DA_VERIFICARE`, la banca non crea la chiusura;
* un giorno con POS e senza XML non e' uno scarto: «attendo XML», fuori dal saldo;
* una vendita SumUp si conta una volta (la copia `LEGACY-SUMUP` cede alla gemella API).
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import pos_corrispettivi_check as pc
from app.services import sumup_sync
from app.services.scritture_contabili import (
    FONTE_API, recupera_pos_storico_da_estratto, registra_chiusura_pos_reale,
    riconcilia_accredito_pos_ec,
)

from ._comune import D, attive, nuovo_db, righe, run, somma

GIORNO = "2026-07-06"


def _ec(db, id_, importo, causale, data="2026-07-07"):
    run(db["estratto_conto_movimenti"].insert_one({
        "id": id_, "data": data, "importo": importo, "descrizione_originale": causale}))


def _riconcilia(db, id_):
    ec = run(db["estratto_conto_movimenti"].find_one({"id": id_}))
    return run(riconcilia_accredito_pos_ec(db, ec))


def _ec_riga(db, id_):
    return run(db["estratto_conto_movimenti"].find_one({"id": id_}, {"_id": 0}))


def _credito(db, gestore="numia"):
    return [r for r in run(attive(db, "prima_nota_banca"))
            if r.get("source") == "trasferimento_pos" and r.get("gestore") == gestore]


CAUSALE_BNCMT = "INCAS. TRAMITE P.O.S - NUMIA-BNCMT DEL 06/07/26 PDV 3757283/00012"
CAUSALE_INTER = "INC.POS CARTE CREDIT - NUMIA-INTER DEL 06/07/26 PDV 3757283/00011"


# ── accredito riconosciuto ──────────────────────────────────────────────────

def test_accrediti_a_pezzi_riconciliano_il_credito_solo_alla_somma_al_centesimo():
    db = nuovo_db("s5_accredito")
    run(registra_chiusura_pos_reale(db, GIORNO, 1353.70, gestore="numia"))
    (atteso,) = _credito(db)
    assert atteso["expectation_status"] == "ATTESO" and atteso["riconciliato"] is False
    _ec(db, "ec-1", 1000.20, CAUSALE_BNCMT, "2026-07-07")
    _ec(db, "ec-2", 353.50, CAUSALE_INTER, "2026-07-08")

    # Il primo pezzo da solo non basta: l'attesa resta aperta.
    assert _riconcilia(db, "ec-1") is True
    (parziale,) = _credito(db)
    assert D(parziale["accreditato_ec"]) == D("1000.20") and parziale["riconciliato"] is False
    assert parziale["expectation_status"] != "SODDISFATTO"
    assert _ec_riga(db, "ec-1")["riconciliato"] is False

    # Il secondo completa: 1.000,20 + 353,50 = 1.353,70.
    assert _riconcilia(db, "ec-2") is True
    (chiuso,) = _credito(db)
    assert chiuso["id"] == atteso["id"] and chiuso["riconciliato"] is True
    assert chiuso["expectation_status"] == "SODDISFATTO" and D(chiuso["accreditato_ec"]) == D("1353.70")
    for ec_id in ("ec-1", "ec-2"):
        ec = _ec_riga(db, ec_id)
        assert ec["riconciliato"] is True and ec["tipo_riconciliazione"] == "accredito_pos_trasferimento"
    # Nessuna riga in piu': l'accredito riconcilia, non crea.
    assert len(run(attive(db, "prima_nota_banca"))) == 1
    assert run(attive(db, "prima_nota_cassa")) == []


def test_riprocessare_lo_stesso_accredito_non_lo_somma_due_volte():
    db = nuovo_db("s5_idempotente")
    run(registra_chiusura_pos_reale(db, GIORNO, 100.0, gestore="numia"))
    _ec(db, "ec-1", 60.0, CAUSALE_INTER)
    for _ in range(3):
        _riconcilia(db, "ec-1")
    (credito,) = _credito(db)
    assert D(credito["accreditato_ec"]) == D("60.00") and credito["riconciliato"] is False


def test_differenza_di_un_euro_non_e_riconciliazione():
    db = nuovo_db("s5_un_euro")
    run(registra_chiusura_pos_reale(db, GIORNO, 100.0, gestore="numia"))
    _ec(db, "ec-1", 99.0, CAUSALE_INTER)
    _riconcilia(db, "ec-1")
    (credito,) = _credito(db)
    assert credito["riconciliato"] is False and credito["expectation_status"] != "SODDISFATTO"
    assert _ec_riga(db, "ec-1")["tipo_riconciliazione"] == "accredito_pos_non_quadrato"


def test_numia_e_nexi_sono_lo_stesso_circuito():
    db = nuovo_db("s5_nexi")
    run(registra_chiusura_pos_reale(db, GIORNO, 100.0, gestore="numia"))
    _ec(db, "ec-1", 100.0, "INC.POS CARTE CREDIT - NEXI-INTER DEL 06/07/26 PDV 1")
    assert _riconcilia(db, "ec-1") is True
    assert _credito(db)[0]["riconciliato"] is True


@pytest.mark.parametrize("causale", [
    "COMMISSIONI NUMIA-INTER DEL 06/07/26",                    # commissione del gestore
    "FATTURA NUMIA N. 55 DEL 06/07/26",                         # fattura del gestore
    "REMUNERAZIONE DCC NUMIA-INTER DEL 06/07/26",
    "SPESA CON CARTA DI CREDITO NEXI DEL 06/07/26",
    "INC.POS CARTE CREDIT - NUMIA-INTER senza giorno operativo",  # senza `DEL gg/mm/aa`
    "BONIFICO DA CLIENTE DEL 06/07/26",
])
def test_causali_che_non_sono_un_accredito_pos_non_riconciliano_niente(causale):
    db = nuovo_db("s5_escluse")
    run(registra_chiusura_pos_reale(db, GIORNO, 100.0, gestore="numia"))
    _ec(db, "ec-1", 100.0, causale)
    assert _riconcilia(db, "ec-1") is False
    (credito,) = _credito(db)
    assert credito["riconciliato"] is False and credito["expectation_status"] == "ATTESO"
    assert "riconciliato" not in _ec_riga(db, "ec-1")


def test_un_accredito_numia_non_chiude_il_credito_sumup_dello_stesso_giorno():
    db = nuovo_db("s5_circuiti")
    run(registra_chiusura_pos_reale(db, GIORNO, 100.0, gestore="sumup", fonte=FONTE_API))
    _ec(db, "ec-1", 100.0, CAUSALE_INTER)

    assert _riconcilia(db, "ec-1") is False       # nessuna attesa NUMIA: non scambia il circuito
    (sumup,) = _credito(db, "sumup")
    assert sumup["riconciliato"] is False and sumup["expectation_status"] == "ATTESO"
    assert _ec_riga(db, "ec-1")["tipo_riconciliazione"] == "evidenza_senza_attesa"


# ── attesa mancante o multipla ──────────────────────────────────────────────

def test_accredito_senza_attesa_e_da_verificare_e_la_banca_non_crea_la_chiusura():
    db = nuovo_db("s5_mancante")
    _ec(db, "ec-1", 1353.70, CAUSALE_INTER)

    assert _riconcilia(db, "ec-1") is False
    esito = run(recupera_pos_storico_da_estratto(db, 2026))

    ec = _ec_riga(db, "ec-1")
    assert ec["riconciliato"] is False and ec["stato_riconciliazione"] == "da_verificare"
    assert ec["tipo_riconciliazione"] == "evidenza_senza_attesa"
    assert esito["creati"] == 0 and esito["giorni_senza_attesa"] == 1
    # La banca NON ha creato la chiusura, ne' il credito, ne' un'entrata.
    assert run(righe(db, "chiusure_pos_manuali")) == []
    assert run(righe(db, "prima_nota_banca")) == []
    assert run(righe(db, "prima_nota_cassa")) == []


def test_attesa_multipla_e_da_verificare_e_non_se_ne_sceglie_una_a_caso():
    db = nuovo_db("s5_multipla")
    for i in (1, 2):
        run(db["prima_nota_banca"].insert_one({
            "id": f"t{i}", "source": "trasferimento_pos", "gestore": "numia", "status": "active",
            "giorno_vendita": GIORNO, "data": GIORNO, "importo": 100.0, "riconciliato": False}))
    _ec(db, "ec-1", 100.0, CAUSALE_INTER)

    assert _riconcilia(db, "ec-1") is False

    ec = _ec_riga(db, "ec-1")
    assert ec["riconciliato"] is False and ec["tipo_riconciliazione"] == "attese_pos_ambigue"
    assert ec["dettagli_riconciliazione"]["attese_candidate"] == 2
    assert all(r["riconciliato"] is False for r in run(righe(db, "prima_nota_banca")))
    # La procedura di ricollegamento storico dice lo stesso.
    assert run(recupera_pos_storico_da_estratto(db, 2026))["giorni_con_attese_ambigue"] == 1


# ── giorno POS senza XML ────────────────────────────────────────────────────

def test_giorno_con_pos_e_senza_xml_e_in_attesa_non_e_uno_scarto(monkeypatch):
    db = nuovo_db("s5_senza_xml")
    # XML fino all'08/09; il 22/09 il terminale ha incassato ma l'XML non e' ancora arrivato.
    run(db["corrispettivi"].insert_one({
        "data": "2026-09-08", "pagato_elettronico": 2000.0, "stato": "definitivo_xml"}))
    run(registra_chiusura_pos_reale(db, "2026-09-08", 2000.0, gestore="sumup", fonte=FONTE_API))
    run(registra_chiusura_pos_reale(db, "2026-09-22", 1938.0, gestore="sumup", fonte=FONTE_API))
    monkeypatch.setattr(pc.Database, "get_db", staticmethod(lambda: db))

    risultato = run(pc.controllo_incassi_due_fasi(
        data_da=None, data_a=None, anno=2026, tolleranza_euro=0.50))

    giorni = {g["data"]: g for g in risultato["giorni"]}
    assert giorni["2026-09-08"]["stato_serale"] == "ok"
    # Senza XML: «attendo XML», differenza zero (nessuno scarto pari a tutto il POS).
    assert giorni["2026-09-22"]["stato_serale"] == "in_attesa_xml"
    assert giorni["2026-09-22"]["diff_serale"] == 0


def test_xml_che_copre_due_giorni_non_fa_scarto_sul_primo(monkeypatch):
    """L'RT chiude due giorni in una volta: il giorno senza XML si confronta con la chiusura che lo copre."""
    db = nuovo_db("s5_chiusura_doppia")
    run(db["corrispettivi"].insert_one({
        "data": "2026-09-09", "pagato_elettronico": 4052.60, "stato": "definitivo_xml"}))
    run(registra_chiusura_pos_reale(db, "2026-09-08", 2115.80, gestore="sumup", fonte=FONTE_API))
    run(registra_chiusura_pos_reale(db, "2026-09-09", 1936.80, gestore="sumup", fonte=FONTE_API))
    monkeypatch.setattr(pc.Database, "get_db", staticmethod(lambda: db))

    risultato = run(pc.controllo_incassi_due_fasi(
        data_da=None, data_a=None, anno=2026, tolleranza_euro=0.50))

    giorni = {g["data"]: g for g in risultato["giorni"]}
    assert giorni["2026-09-08"]["stato_serale"] == "chiusa_col_giorno_dopo"
    assert giorni["2026-09-08"]["diff_serale"] == 0
    assert giorni["2026-09-09"]["diff_serale"] == 0 and giorni["2026-09-09"]["stato_serale"] == "ok"


# ── SumUp: una vendita si conta una volta ───────────────────────────────────

def _vendita_api(codice, importo, data="2026-08-03"):
    return {"chiave": f"MFNRDMC4:{codice}", "transaction_code": codice, "tipo": "PAYMENT",
            "stato": "SUCCESSFUL", "data": data, "importo": importo, "payout_id": "P1"}


def _vendita_legacy(codice, importo, data="2026-08-03"):
    return {"id": f"LEGACY-{codice}", "id_trans": codice, "tipo": "PAYMENT",
            "stato": "SUCCESSFUL", "data": data, "importo": importo, "fonte": "legacy_staging_2026"}


def test_vendita_sumup_copiata_dal_vecchio_archivio_si_conta_una_volta(monkeypatch):
    db = nuovo_db("s5_sumup")
    run(db[sumup_sync.COLL_TRANSAZIONI].insert_many([
        _vendita_api("TA1", 10.0), _vendita_legacy("TA1", 10.0),     # stessa vendita, due righe
        _vendita_legacy("TA2", 5.0),                                  # solo nel vecchio archivio: conta
        _vendita_api("TB1", 4.0, data="2026-08-05"),
    ]))
    # Chiusura raddoppiata come l'aveva scritta la sincronizzazione prima della correzione.
    run(registra_chiusura_pos_reale(db, "2026-08-03", 25.0, gestore="sumup", fonte=FONTE_API))
    run(registra_chiusura_pos_reale(db, "2026-08-05", 4.0, gestore="sumup", fonte=FONTE_API))

    async def payout_finto(db, dal, al, actor=None):
        return {"success": True}

    monkeypatch.setattr(sumup_sync, "sincronizza_payouts", payout_finto)
    venduto = run(sumup_sync.transazioni_del_periodo(db, "2026-08-03", "2026-08-03"))
    assert somma(r["importo"] for r in venduto) == D("15.00")        # 10 (una volta) + 5

    esito = run(sumup_sync.riallinea_chiusure_da_archivio(db, "2026-08-01", "2026-08-31"))

    assert esito["corrette"] == [{"data": "2026-08-03", "era": 25.0, "ora": 15.0}]
    (credito,) = [r for r in _credito(db, "sumup") if r["data"] == "2026-08-03"]
    assert D(credito["importo"]) == D("15.00")
    assert run(sumup_sync.riallinea_chiusure_da_archivio(db, "2026-08-01", "2026-08-31"))["corrette"] == []


# ── ordine degli arrivi e correzioni ────────────────────────────────────────

def test_accredito_arrivato_prima_della_chiusura_si_riconcilia_quando_la_chiusura_arriva():
    """L'estratto conto e' un'evidenza successiva ma puo' essere LETTO prima: resta
    «senza attesa» (da verificare), poi la chiusura crea l'attesa e il ricollegamento
    la soddisfa. Mai il contrario: l'estratto non crea la chiusura."""
    db = nuovo_db("s5_ordine")
    _ec(db, "ec-1", 100.0, CAUSALE_INTER)
    assert _riconcilia(db, "ec-1") is False
    assert run(righe(db, "prima_nota_banca")) == []

    run(registra_chiusura_pos_reale(db, GIORNO, 100.0, gestore="numia"))
    esito = run(recupera_pos_storico_da_estratto(db, 2026))

    assert esito["componenti_bancarie_ricollegate"] == 1
    (credito,) = _credito(db)
    assert credito["riconciliato"] is True and credito["expectation_status"] == "SODDISFATTO"
    assert _ec_riga(db, "ec-1")["riconciliato"] is True


def test_chiusura_corretta_dopo_l_accredito_riapre_la_riconciliazione():
    """Un accredito da 100 chiude un credito da 100. Se la chiusura viene corretta a 120
    la riga d'estratto non puo' restare «riconciliata»: il credito ha 20 euro scoperti."""
    db = nuovo_db("s5_correzione")
    run(registra_chiusura_pos_reale(db, GIORNO, 100.0, gestore="numia"))
    _ec(db, "ec-1", 100.0, CAUSALE_INTER)
    _riconcilia(db, "ec-1")
    assert _credito(db)[0]["riconciliato"] is True

    run(registra_chiusura_pos_reale(db, GIORNO, 120.0, gestore="numia"))

    (credito,) = _credito(db)
    assert D(credito["importo"]) == D("120.00") and credito["riconciliato"] is False
    assert credito["expectation_status"] != "SODDISFATTO"
    ec = _ec_riga(db, "ec-1")
    assert ec["riconciliato"] is False and ec["tipo_riconciliazione"] == "accredito_pos_non_quadrato"

    # Il pezzo mancante chiude di nuovo il gruppo.
    _ec(db, "ec-2", 20.0, CAUSALE_BNCMT)
    assert _riconcilia(db, "ec-2") is True
    assert _credito(db)[0]["riconciliato"] is True
    assert _ec_riga(db, "ec-1")["riconciliato"] is True


def test_chiusura_azzerata_dopo_l_accredito_lascia_l_estratto_senza_attesa():
    db = nuovo_db("s5_zero")
    run(registra_chiusura_pos_reale(db, GIORNO, 100.0, gestore="numia"))
    _ec(db, "ec-1", 100.0, CAUSALE_INTER)
    _riconcilia(db, "ec-1")

    run(registra_chiusura_pos_reale(db, GIORNO, 0.0, gestore="numia"))

    assert _credito(db) == []                                         # il credito e' stato ritirato
    ec = _ec_riga(db, "ec-1")
    assert ec["riconciliato"] is False and ec["tipo_riconciliazione"] == "evidenza_senza_attesa"


def test_riepilogo_mensile_tiene_il_giorno_senza_xml_fuori_dal_saldo(monkeypatch):
    """Anche nel mensile: il POS di un giorno senza XML e' esposto a parte («in attesa XML»)
    e non entra nella differenza XML-POS del mese."""
    db = nuovo_db("s5_mensile")
    run(db["corrispettivi"].insert_one({
        "data": "2026-09-08", "pagato_elettronico": 2000.0, "totale": 2300.0, "stato": "definitivo_xml"}))
    run(registra_chiusura_pos_reale(db, "2026-09-08", 2000.0, gestore="sumup", fonte=FONTE_API))
    run(registra_chiusura_pos_reale(db, "2026-09-22", 1938.0, gestore="sumup", fonte=FONTE_API))
    monkeypatch.setattr(pc.Database, "get_db", staticmethod(lambda: db))

    risultato = run(pc.riepilogo_mensile_pos_corrispettivi(anno=2026))

    settembre = next(m for m in risultato["mesi"] if m["mese"] == 9)
    assert D(settembre["pos_in_attesa_xml"]) == D("1938.00")
    assert settembre["giorni_in_attesa_xml"] == ["2026-09-22"]
    assert D(settembre["differenza_xml_pos"]) == D("0.00")         # nessuno scarto pari a tutto il POS
    assert D(settembre["pos_terminale"]) == D("3938.00")


def test_giornata_completa_xml_terminale_accredito_con_il_motore_unico_della_banca(monkeypatch):
    """Dall'inizio alla fine, come nell'uso reale: XML (Documenti > Import), chiusura serale
    del terminale (PUT /pos-corrispettivi/chiusura-giornaliera), accredito dell'estratto conto
    riconciliato dal motore unico. Alla fine: cassa 300, credito POS 700 chiuso, giornale 1."""
    from app.services import riconciliazione_bancaria as banca
    from app.utils.dependencies import get_current_user

    from ._comune import Importatore, xml_chiusura

    db = nuovo_db("s5_completa")
    imp = Importatore(db, monkeypatch)
    monkeypatch.setattr(banca.Database, "get_db", staticmethod(lambda: db))

    imp.importa("2700.xml", xml_chiusura(data="2026-09-10"))
    app = FastAPI()
    app.include_router(pc.router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: {"sub": "titolare", "email": "t@example.com"}
    with TestClient(app) as client:
        risposta = client.put("/api/pos-corrispettivi/chiusura-giornaliera",
                              json={"data": "2026-09-10", "importo": 700.0, "gestore": "numia"})
    assert risposta.status_code == 200, risposta.text
    run(db["estratto_conto_movimenti"].insert_one({
        "id": "ec-1", "data": "2026-09-11", "importo": 700.0, "tipo": "entrata",
        "descrizione_originale": "INC.POS CARTE CREDIT - NUMIA-INTER DEL 10/09/26 PDV 3757283/00011"}))

    esito = run(banca.riconcilia_movimenti_banca())
    secondo = run(banca.riconcilia_movimenti_banca())

    assert esito["riconciliati_pos"] == 1 and secondo["riconciliati_pos"] == 0
    (credito,) = _credito(db)
    assert credito["riconciliato"] is True and credito["expectation_status"] == "SODDISFATTO"
    assert D(credito["accreditato_ec"]) == D("700.00")
    assert [D(r["importo"]) for r in run(attive(db, "prima_nota_cassa"))] == [D("300.00")]
    assert len(run(attive(db, "movimenti_contabili"))) == 1
    assert len(run(attive(db, "prima_nota_banca"))) == 1            # la banca non ha scritto altro
