"""Collaudo funzionale: TFR, cessazione, cedolino senza netto.

Esito atteso scritto dal CLAUDE.md, «Personale»:

4. TFR: un bonifico TFR non entra mai come stipendio (veto, in ogni grafia della
   banca); si registra come TFR e popola il TFR del dipendente; l'acconto TFR e
   l'accantonamento scrivono il giornale **del gestionale**, quadrato
   (Dare = Avere); un acconto eliminato o corretto si storna, non si cancella;
6. cessazione: revoca il PIN, chiude i contratti, rifiuta le assenze future,
   annulla le partite stipendio residue (che stanno nel gestionale);
7. cedolino senza netto letto: entra solo in HR col netto nullo, mai in Prima
   Nota, non alimenta salari ne' bonifici (``alimenta_salari`` fallisce chiuso).
"""
import base64

import pytest

from app.constants.stati_netto import (
    ERRORE_PARSER,
    MULTIPLE_NETS_DA_VERIFICARE,
    NETTO_NON_PRESENTE_O_NON_LEGGIBILE,
    NETTO_VERIFICATO_DA_CEDOLINO,
    alimenta_salari,
)
from tests.hr.scenari_base import mondo, run  # noqa: F401  (fixture)

CF_ROSSI = "RSSMRA80A01F839X"


@pytest.fixture
def rossi(mondo):
    mondo.dipendente("d-rossi", "Mario", "Rossi", CF_ROSSI, tfr_accantonato=5000.0)
    return mondo


def _giornale(m, tipo=None):
    filtro = {"tipo": tipo} if tipo else {}
    return run(m.gest["movimenti_contabili"].find(filtro, {"_id": 0}).to_list(100))


def _quadra(scrittura):
    dare = round(sum(r["dare"] for r in scrittura["righe"]), 2)
    avere = round(sum(r["avere"] for r in scrittura["righe"]), 2)
    return dare == avere == round(float(scrittura["totale_dare"]), 2) == round(float(scrittura["totale_avere"]), 2)


# ── 4. TFR ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("causale", [
    "TFR", "liquidazione TFR 2025", "TFR2025", "T.F.R.", "T.F.R", "trattamento di fine rapporto",
    "TRATTAMENTO FINE RAPPORTO",
])
def test_4_bonifico_tfr_non_entra_mai_come_stipendio(rossi, causale):
    from app.services.hr_pagamenti_deposito import deposita_movimento_banca_in_hr

    m = rossi
    m.busta("d-rossi", 3, 1000.0)
    descrizione = f"VOSTRA DISPOSIZIONE - VS.DISP. RIF. MB0B00923006/90679785 FAVORE Rossi Mario - ADD.TOT - {causale}"
    mov = {"id": "mov-tfr", "data": "2026-04-03", "importo": -4000.0, "tipo": "uscita",
           "descrizione": descrizione, "descrizione_originale": descrizione}

    marca = run(deposita_movimento_banca_in_hr(m.gest, mov))

    assert marca["esito"] == "non_stipendio"
    assert m.conta("pagamenti_esiti") == 0 and m.conta("bonifici_da_associare") == 0   # nemmeno in coda
    assert not m.paga("d-rossi").get("bonifico_importo")                                # la busta non e' toccata
    assert m.paga("d-rossi")["stato_pagamento"] == "in_attesa_pagamento"
    assert m.posizione("d-rossi")["totale_avere"] == 0.0


def test_4_acconto_tfr_popola_il_tfr_e_scrive_il_giornale_del_gestionale_quadrato(rossi):
    m = rossi
    r = m.client.post("/api/tfr/acconti", json={"dipendente_id": "d-rossi", "tipo": "tfr", "importo": 500.0,
                                                "data": "2026-04-06"})
    assert r.status_code == 200, r.text
    acconto_id = r.json()["acconto_id"]

    # e' un acconto TFR del registro acconti, il TFR del dipendente scende
    acc = run(m.hr.acconti_dipendenti.find_one({"id": acconto_id}, {"_id": 0}))
    assert acc["tipo"] == "tfr" and acc["importo"] == 500.0
    assert run(m.hr.dipendenti.find_one({"id": "d-rossi"}))["tfr_accantonato"] == 4500.0
    assert m.client.get("/api/tfr/situazione/d-rossi").json()["tfr_accantonato"] == 4500.0

    # il giornale e' quello del gestionale (non una tabella dello schema HR), quadrato
    assert m.conta("movimenti_contabili") == 0                     # nulla nello schema HR
    scritture = _giornale(m, "acconto_tfr")
    assert len(scritture) == 1 and _quadra(scritture[0])
    assert scritture[0]["acconto_id"] == acconto_id and scritture[0]["numero_registrazione"] == 1
    assert {(x["conto_codice"], x["dare"], x["avere"]) for x in scritture[0]["righe"]} == {
        ("29.01.01", 500.0, 0.0), ("39.07.05", 0.0, 500.0)}        # fondo TFR / personale c/liquidazione

    # un acconto TFR non e' stipendio: non entra nella posizione paghe, ne' come AVERE ne' come DARE
    p = m.posizione("d-rossi")
    assert (p["totale_dare"], p["totale_avere"], p["chiusura"]) == (0.0, 0.0, 0.0)


def test_4_accantonamento_tfr_popola_tfr_accantonamenti_una_volta_sola(rossi):
    m = rossi
    run(m.hr.dipendenti.update_one({"id": "d-rossi"}, {"$set": {"tfr_accantonato": 0.0}}))
    corpo = {"dipendente_id": "d-rossi", "anno": 2026, "retribuzione_annua": 27000.0, "indice_istat": 1.0}
    r1 = m.client.post("/api/tfr/accantonamento", json=corpo)
    assert r1.status_code == 200 and r1.json()["dettaglio"]["quota_annuale"] == 2000.0

    righe = run(m.hr.tfr_accantonamenti.find({"dipendente_id": "d-rossi"}, {"_id": 0}).to_list(10))
    assert len(righe) == 1 and righe[0]["anno"] == 2026
    sit = m.client.get("/api/tfr/situazione/d-rossi").json()
    assert sit["tfr_accantonato"] == 2000.0 and sit["num_accantonamenti"] == 1
    scritture = _giornale(m, "tfr_accantonamento")
    assert len(scritture) == 1 and _quadra(scritture[0])
    assert m.conta("movimenti_contabili") == 0

    # secondo giro: niente doppioni, ne' nel TFR ne' nel giornale
    r2 = m.client.post("/api/tfr/accantonamento", json={**corpo, "retribuzione_annua": 99999.0})
    assert r2.json()["gia_registrato"] is True
    assert m.conta("tfr_accantonamenti") == 1 and len(_giornale(m, "tfr_accantonamento")) == 1
    assert run(m.hr.dipendenti.find_one({"id": "d-rossi"}))["tfr_accantonato"] == 2000.0


def test_4_acconto_tfr_eliminato_si_storna_non_si_cancella(rossi):
    m = rossi
    acconto_id = m.client.post("/api/tfr/acconti", json={
        "dipendente_id": "d-rossi", "tipo": "tfr", "importo": 500.0, "data": "2026-04-06"}).json()["acconto_id"]

    assert m.client.delete(f"/api/tfr/acconti/{acconto_id}").status_code == 200

    # il TFR torna com'era...
    assert run(m.hr.dipendenti.find_one({"id": "d-rossi"}))["tfr_accantonato"] == 5000.0
    assert m.conta("acconti_dipendenti") == 0
    # ...e il giornale lo dice: la scrittura originale resta, c'e' la rettifica inversa, il netto e' zero
    tutte = _giornale(m)
    assert [s["tipo"] for s in tutte] == ["acconto_tfr", "acconto_tfr_rettifica"]
    assert all(_quadra(s) for s in tutte)
    netto_fondo = sum(r["dare"] - r["avere"] for s in tutte for r in s["righe"] if r["conto_codice"] == "29.01.01")
    assert round(netto_fondo, 2) == 0.0


def test_4_acconto_tfr_corretto_di_importo_rettifica_la_differenza(rossi):
    m = rossi
    acconto_id = m.client.post("/api/tfr/acconti", json={
        "dipendente_id": "d-rossi", "tipo": "tfr", "importo": 500.0, "data": "2026-04-06"}).json()["acconto_id"]
    assert m.client.put(f"/api/tfr/acconti/{acconto_id}", json={"importo": 300.0}).status_code == 200
    assert run(m.hr.dipendenti.find_one({"id": "d-rossi"}))["tfr_accantonato"] == 4700.0
    assert m.client.put(f"/api/tfr/acconti/{acconto_id}", json={"importo": 400.0}).status_code == 200
    assert run(m.hr.dipendenti.find_one({"id": "d-rossi"}))["tfr_accantonato"] == 4600.0

    tutte = _giornale(m)
    assert all(_quadra(s) for s in tutte) and len(tutte) == 3
    # il fondo TFR del giornale e' sempre quello dell'acconto: 400 (= 5.000 - 4.600)
    fondo = sum(r["dare"] - r["avere"] for s in tutte for r in s["righe"] if r["conto_codice"] == "29.01.01")
    assert round(fondo, 2) == 400.0
    # una correzione identica non scrive niente
    assert m.client.put(f"/api/tfr/acconti/{acconto_id}", json={"importo": 400.0}).status_code == 200
    assert len(_giornale(m)) == 3


# ── 6. cessazione ───────────────────────────────────────────────────────────

@pytest.fixture
def con_handler_cessazione():
    """Il bus vero, con l'handler che l'avvio registra (``register_all_handlers``)."""
    from app.services.event_bus import EventTypes, _handlers, register_handler
    from app.services.handlers.dipendente_handlers import on_dipendente_cessato

    register_handler(EventTypes.DIPENDENTE_CESSATO, on_dipendente_cessato)
    yield
    _handlers[EventTypes.DIPENDENTE_CESSATO].remove(on_dipendente_cessato)


def test_6_cessazione_revoca_pin_chiude_contratti_assenze_e_partite(rossi, con_handler_cessazione):
    m = rossi
    m.dipendente("d-altro", "Luigi", "Bianchi", "BNCLGU85B02F839Y")
    assert m.client.post("/api/dipendenti-cloud/dipendenti/d-rossi/pin", json={"pin": "4821"}).status_code == 200
    assert run(m.hr.dipendenti.find_one({"id": "d-rossi"})).get("pin_hash")
    # HR: contratti e richieste di assenza; gestionale: partite aperte e avvisi
    run(m.hr["employee_contracts"].insert_many([
        {"id": "ct1", "dipendente_id": "d-rossi", "stato": "attivo"},
        {"id": "ct-altro", "dipendente_id": "d-altro", "stato": "attivo"}]))
    run(m.hr["richieste_assenza"].insert_many([
        {"id": "r-futura", "employee_id": "d-rossi", "stato": "pending", "data_inizio": "2026-10-15"},
        {"id": "r-passata", "employee_id": "d-rossi", "stato": "pending", "data_inizio": "2026-09-01"}]))
    run(m.gest["partite_aperte"].insert_many([
        {"id": "pa1", "controparte_id": "d-rossi", "tipo": "stipendio", "stato": "aperta", "importo": 900.0},
        {"id": "pa2", "controparte_id": "d-rossi", "tipo": "stipendio", "stato": "parziale", "importo": 400.0},
        {"id": "pa-pagata", "controparte_id": "d-rossi", "tipo": "stipendio", "stato": "chiusa"},
        {"id": "pa-altro", "controparte_id": "d-altro", "tipo": "stipendio", "stato": "aperta"}]))
    run(m.gest["alerts"].insert_one({"id": "al1", "entita_id": "d-rossi", "stato": "aperto",
                                     "codice": "DIP_IBAN_MANCANTE"}))

    r = m.client.post("/api/dipendenti-cloud/dipendenti/d-rossi/cessa",
                      json={"data_cessazione": "2026-09-30", "motivo": "dimissioni"})
    assert r.status_code == 200 and r.json()["stato"] == "cessato"

    dip = run(m.hr.dipendenti.find_one({"id": "d-rossi"}, {"_id": 0}))
    assert dip["data_fine_rapporto"] == "2026-09-30" and dip["motivo_cessazione"] == "dimissioni"
    assert not dip.get("pin_hash") and not dip.get("pin_lookup")                      # PIN revocato
    ct = run(m.hr["employee_contracts"].find_one({"id": "ct1"}, {"_id": 0}))
    assert ct["stato"] == "terminato" and ct["data_fine"] == "2026-09-30"             # contratto chiuso
    assert run(m.hr["employee_contracts"].find_one({"id": "ct-altro"}))["stato"] == "attivo"
    assert run(m.hr["richieste_assenza"].find_one({"id": "r-futura"}))["stato"] == "rifiutata"
    assert run(m.hr["richieste_assenza"].find_one({"id": "r-passata"}))["stato"] == "pending"
    # le partite stipendio residue stanno nel gestionale: sono annullate li'
    partite = {p["id"]: p["stato"] for p in run(m.gest["partite_aperte"].find({}, {"_id": 0}).to_list(10))}
    assert partite == {"pa1": "annullata", "pa2": "annullata", "pa-pagata": "chiusa", "pa-altro": "aperta"}
    assert run(m.gest["alerts"].find_one({"id": "al1"}))["stato"] == "risolto"
    # il PIN revocato non e' piu' di nessuno: un altro dipendente puo' sceglierlo
    assert m.client.post("/api/dipendenti-cloud/dipendenti/d-altro/pin", json={"pin": "4821"}).status_code == 200


def test_6_la_cessazione_ripetuta_non_duplica_ne_riapre(rossi, con_handler_cessazione):
    m = rossi
    run(m.hr["employee_contracts"].insert_one({"id": "ct1", "dipendente_id": "d-rossi", "stato": "attivo"}))
    run(m.gest["partite_aperte"].insert_one(
        {"id": "pa1", "controparte_id": "d-rossi", "tipo": "stipendio", "stato": "aperta"}))
    corpo = {"data_cessazione": "2026-09-30", "motivo": "dimissioni"}
    assert m.client.post("/api/dipendenti-cloud/dipendenti/d-rossi/cessa", json=corpo).status_code == 200
    prima = run(m.hr["employee_contracts"].find_one({"id": "ct1"}, {"_id": 0}))
    assert m.client.post("/api/dipendenti-cloud/dipendenti/d-rossi/cessa", json=corpo).status_code == 200
    assert run(m.hr["employee_contracts"].find_one({"id": "ct1"}, {"_id": 0})) == prima
    assert run(m.gest["partite_aperte"].find_one({"id": "pa1"}))["stato"] == "annullata"


# ── 7. cedolino senza netto letto ───────────────────────────────────────────

def _busta_letta(**extra):
    base = {"codice_fiscale": CF_ROSSI, "nome_dipendente": "ROSSI MARIO", "anno": 2026, "mese": 6,
            "tipo_cedolino": "mensile", "netto": None, "stato_netto": NETTO_NON_PRESENTE_O_NON_LEGGIBILE,
            "netto_fonte": "non_letto_da_lul", "lordo": 2000.0, "cedolino_dedup_key": "k1", "canale": "drive"}
    base.update(extra)
    return base


@pytest.mark.parametrize("stato,netto", [
    (NETTO_NON_PRESENTE_O_NON_LEGGIBILE, None),
    (NETTO_NON_PRESENTE_O_NON_LEGGIBILE, 1234.0),   # un numero qualunque non rende verificato un netto illeggibile
    (MULTIPLE_NETS_DA_VERIFICARE, 1234.0),
    (ERRORE_PARSER, 1234.0),
    (None, 1234.0), ("", 1234.0), ("QUALCOSA_DI_NUOVO", 1234.0),   # fallisce chiuso
    (NETTO_VERIFICATO_DA_CEDOLINO, None),                          # verificato ma vuoto: niente da pagare
    (NETTO_VERIFICATO_DA_CEDOLINO, 0),
])
def test_7_busta_senza_netto_verificato_entra_solo_in_hr_col_netto_nullo(mondo, monkeypatch, stato, netto):
    from app.services import hr_cedolini_deposito as deposito
    from app.services.cedolini_manager import registra_busta
    from tests.hr.test_hr_cedolini_deposito import ConnessioneFinta, DIPENDENTE_HR, _configura

    assert alimenta_salari(stato) is (stato == NETTO_VERIFICATO_DA_CEDOLINO)
    con = ConnessioneFinta(dipendenti=[DIPENDENTE_HR])
    _configura(monkeypatch, con)
    risultati = {"buste_senza_netto": 0, "errori": [], "cedolini_processati": 0, "prima_nota_create": 0}

    run(registra_busta(mondo.gest, _busta_letta(stato_netto=stato, netto=netto), filename="busta.pdf",
                       pdf_data=base64.b64encode(b"%PDF-1.4 finto").decode(), pdf_text="", results=risultati))

    # una sola riga, solo in HR; il netto illeggibile resta nullo (mai zero, mai un numero di ripiego)
    assert risultati["buste_senza_netto"] == 1 and not risultati["errori"]
    assert len(con.inseriti) == 1
    # niente in contabilita': ne' registro cedolini, ne' Prima Nota salari, ne' partite, ne' giornale
    for collezione in ("cedolini", "prima_nota_salari", "partite_aperte", "movimenti_contabili", "prima_nota"):
        assert run(mondo.gest[collezione].count_documents({})) == 0, collezione
    assert risultati["cedolini_processati"] == 0 and risultati["prima_nota_create"] == 0


def test_7_in_hr_la_busta_senza_netto_non_alimenta_paghe_ne_posizione_ne_stato(mondo):
    m = mondo
    m.dipendente("d-rossi", "Mario", "Rossi", CF_ROSSI)
    run(m.hr.cedolini.insert_one({"id": "c1", "dipendente_id": "d-rossi", "anno": 2026, "mese": 6,
                                  "tipo_cedolino": "ordinario", "netto": None,
                                  "stato_netto": NETTO_NON_PRESENTE_O_NON_LEGGIBILE}))
    from app.hr.services.sincronizza_paghe_mensili import sincronizza

    assert run(sincronizza(m.hr))["creati"] == 0 and m.conta("paghe_mensili") == 0   # nessuna riga paghe
    p = m.posizione("d-rossi")
    busta = next(x for x in p["righe"] if x["tipo"] == "busta")
    assert busta["dare"] is None and "netto non leggibile" in busta["avviso"]          # dichiarato, non zero
    assert (p["totale_dare"], p["chiusura"]) == (0.0, 0.0)

    # nessun bonifico viene proposto a quel mese per importo: la busta non ha un residuo da coprire
    m.coda("q", 1200.0, causale="AGGIUNTIVA stipendio giugno 2026", data="2026-07-03")
    riga = m.client.get("/api/dipendenti-cloud/bonifici-da-associare").json()[0]
    assert riga["candidati"] == [] and riga["proposta"] is None
