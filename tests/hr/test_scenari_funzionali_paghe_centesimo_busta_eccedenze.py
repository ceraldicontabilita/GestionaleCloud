"""Decisioni del titolare del 02/10/2026 sulle paghe (collaudo funzionale).

5. «Pagato» al centesimo: nessuna tolleranza (prima 0,50 € di comodo), in ogni
   punto che calcola lo stato del mese (motore unico, sincronizzazione dai
   cedolini, vista Archivio paghe, pannello «in attesa»).
6. Bonifico di stipendio su un mese senza busta: stato ``in_attesa_busta`` sul
   registro del dipendente (``importo_busta`` assente, mai 0), visibile in
   Archivio paghe; all'arrivo della busta si aggancia da solo; secondo giro a zero.
7. Conciliazione: il pagamento copre la parte al centesimo, l'eccedenza resta
   ``da_attribuire`` sulla posizione con avviso; decide il titolare
   (stipendio / acconto / bonus), mai in automatico; idempotente.
"""
import pytest

from app.constants.stati_associazione_bonifico import (
    STATO_PAGA_IN_ATTESA_BUSTA, STATO_PAGA_PAGATO, STATO_PAGA_PARZIALE, stato_paga_mese,
)
from app.services import posizione_dipendente as pos
from tests.hr.scenari_base import ANNO, mondo, run  # noqa: F401  (fixture)

CF_ROSSI = "RSSMRA80A01F839X"
POS = "/api/posizione-dipendente"
D = pos.importo


@pytest.fixture
def rossi(mondo):
    mondo.dipendente("d-rossi", "Mario", "Rossi", CF_ROSSI)
    mondo.busta("d-rossi", 3, 1000.0)
    return mondo


def _archivio_paghe(m, anno=ANNO):
    r = m.client.get(f"/api/dipendenti-cloud/paghe/associazioni-bonifici?anno={anno}")
    assert r.status_code == 200, r.text
    return {(x["dipendente_id"], x["mese"]): x for x in r.json()["righe"]}


# ── 5. pagato al centesimo ──────────────────────────────────────────────────

def test_5_motore_unico_senza_tolleranza():
    assert stato_paga_mese(D("1000.00"), D("1000.00")) == STATO_PAGA_PAGATO
    assert stato_paga_mese(D("1000.00"), D("999.99")) == STATO_PAGA_PARZIALE
    assert stato_paga_mese(D("1000.00"), D("999.50")) == STATO_PAGA_PARZIALE   # prima era «pagato»
    assert stato_paga_mese(D("1000.00"), D("1000.01")) == STATO_PAGA_PAGATO
    assert stato_paga_mese(None, D("1000.00")) == STATO_PAGA_IN_ATTESA_BUSTA
    assert stato_paga_mese(None, pos.ZERO) == "vuoto"


def test_5_bonifico_di_un_centesimo_in_meno_lascia_la_busta_parziale(rossi):
    m = rossi
    m.coda("q1", 999.99)
    assert m.associa("q1", "d-rossi").status_code == 200
    paga = m.paga("d-rossi")
    assert paga["stato_pagamento"] == "parziale" and paga["saldo"] == 0.01
    # la vista Archivio paghe (riconciliata a mano) non dice «esatto»
    riga = _archivio_paghe(m)[("d-rossi", 3)]
    assert riga["stato_importo"] == "parziale" and riga["saldo"] == 0.01 and riga["qualita"] != "esatto"
    # il pannello «in attesa» lo elenca col centesimo che manca
    attesa = m.client.get("/api/dipendenti-cloud/paghe/in-attesa").json()
    assert [r["saldo"] for r in attesa["righe"]] == [0.01]
    # la sincronizzazione dai cedolini dice la stessa cosa
    from app.hr.services.sincronizza_paghe_mensili import sincronizza

    run(sincronizza(m.hr))
    assert (m.paga("d-rossi")["stato_pagamento"], m.paga("d-rossi")["saldo"]) == ("parziale", 0.01)


def test_5_mezzo_euro_in_meno_non_e_pagato_e_al_centesimo_lo_e(rossi):
    m = rossi
    m.coda("q1", 999.50, data="2026-04-03")
    m.coda("q2", 0.50, data="2026-04-04")
    assert m.associa("q1", "d-rossi").status_code == 200
    assert (m.paga("d-rossi")["stato_pagamento"], m.paga("d-rossi")["saldo"]) == ("parziale", 0.5)
    assert m.associa("q2", "d-rossi").status_code == 200
    assert (m.paga("d-rossi")["stato_pagamento"], m.paga("d-rossi")["saldo"]) == ("pagato", 0.0)
    assert m.client.get("/api/dipendenti-cloud/paghe/in-attesa").json()["righe"] == []


# ── 6. bonifico prima della busta ───────────────────────────────────────────

def test_6_bonifico_prima_della_busta_resta_in_attesa_e_la_busta_lo_aggancia(rossi):
    from app.hr.services.sincronizza_paghe_mensili import sincronizza

    m = rossi
    m.coda("q-apr", 1050.0, data="2026-05-03")
    assert m.associa("q-apr", "d-rossi", mese=4).status_code == 200

    paga = m.paga("d-rossi", mese=4)
    assert paga["stato_pagamento"] == STATO_PAGA_IN_ATTESA_BUSTA
    assert "importo_busta" not in paga and paga["saldo"] is None       # mai uno 0 di comodo
    assert paga["bonifico_importo"] == 1050.0
    # Archivio paghe lo mostra «in attesa della busta», senza saldo e senza «da verificare»
    riga = _archivio_paghe(m)[("d-rossi", 4)]
    assert riga["stato"] == STATO_PAGA_IN_ATTESA_BUSTA and riga["saldo"] is None and riga["busta"] == 0
    assert m.client.get("/api/dipendenti-cloud/paghe/in-attesa").json()["righe"][0]["mese"] == 3  # solo marzo
    # la posizione lo conta fra i pagamenti (e' uscito davvero)
    assert m.posizione("d-rossi")["totale_avere"] == 1050.0

    # arriva la busta di aprile: il pagamento si aggancia da solo
    run(m.hr.cedolini.insert_one({"id": "c-apr", "dipendente_id": "d-rossi", "anno": ANNO, "mese": 4,
                                  "tipo_cedolino": "ordinario", "netto": 1050.0}))
    run(sincronizza(m.hr))
    paga = m.paga("d-rossi", mese=4)
    assert paga["stato_pagamento"] == "pagato" and paga["saldo"] == 0.0 and paga["importo_busta"] == 1050.0
    assert paga["cedolino_id"] == "c-apr" and paga["bonifico_importo"] == 1050.0
    assert _archivio_paghe(m)[("d-rossi", 4)]["stato_importo"] == "pagato"
    p = m.posizione("d-rossi")
    assert (p["totale_dare"], p["totale_avere"]) == (2050.0, 1050.0)

    # secondo giro: niente doppioni, stesso stato
    run(sincronizza(m.hr))
    assert m.conta("paghe_mensili", {"dipendente_id": "d-rossi"}) == 2
    assert m.conta("pagamenti_esiti") == 1
    assert m.paga("d-rossi", mese=4)["stato_pagamento"] == "pagato"


def test_6_busta_minore_del_bonifico_gia_arrivato_diventa_pagata_maggiore_parziale(rossi):
    from app.hr.services.sincronizza_paghe_mensili import sincronizza

    m = rossi
    m.coda("q-mag", 800.0, data="2026-06-03")
    assert m.associa("q-mag", "d-rossi", mese=5).status_code == 200
    assert m.paga("d-rossi", mese=5)["stato_pagamento"] == STATO_PAGA_IN_ATTESA_BUSTA
    run(m.hr.cedolini.insert_one({"id": "c-mag", "dipendente_id": "d-rossi", "anno": ANNO, "mese": 5,
                                  "tipo_cedolino": "ordinario", "netto": 800.01}))
    run(sincronizza(m.hr))
    paga = m.paga("d-rossi", mese=5)
    assert paga["stato_pagamento"] == "parziale" and paga["saldo"] == 0.01


def test_6_il_ponte_banca_deposita_in_attesa_della_busta(rossi):
    """Il motore automatico (estratto conto -> HR) con il nome del dipendente e
    nessuna busta del periodo: deposita, e il mese e' in attesa della busta."""
    from app.services.hr_pagamenti_deposito import deposita_movimento_banca_in_hr

    m = rossi
    mov = {"id": "mov-giu", "data": "2026-07-03", "importo": -1000.0, "tipo": "uscita",
           "descrizione_originale": "VOSTRA DISPOSIZIONE - VS.DISP. RIF. MB0B00777777/9 FAVORE Rossi Mario STIPENDIO GIUGNO - ADD.TOT"}
    mov["descrizione"] = mov["descrizione_originale"]
    marca = run(deposita_movimento_banca_in_hr(m.gest, mov))
    assert marca["esito"] == "depositato" and (marca["mese"], marca["anno"]) == (6, ANNO)
    paga = m.paga("d-rossi", mese=6)
    assert paga["stato_pagamento"] == STATO_PAGA_IN_ATTESA_BUSTA and "importo_busta" not in paga
    assert run(deposita_movimento_banca_in_hr(m.gest, mov))["esito"] != "depositato"   # secondo giro
    assert m.conta("pagamenti_esiti") == 1


# ── 7. eccedenza della conciliazione ────────────────────────────────────────

def _conciliazione(m, **extra):
    corpo = {"dipendente_id": "d-rossi", "data": "2026-05-10", "tipo": "conciliazione_sindacale",
             "modalita_pagamento": "bonifico",
             "voci": [{"voce": "straordinari", "importo": "700.00"},
                      {"voce": "bonus_transattivo", "importo": "300.00"}],
             "totale": "1000.00", **extra}
    r = m.client.post(f"{POS}/conciliazioni", json=corpo)
    assert r.status_code == 200, r.text
    return r.json()


def _eccedenze(m):
    return run(m.hr[pos.COLL_ECCEDENZE].find({"dipendente_id": "d-rossi"}, {"_id": 0}).to_list(10))


def test_7_il_bonifico_copre_la_conciliazione_al_centesimo_e_l_eccedenza_resta_da_attribuire(rossi):
    m = rossi
    conc = _conciliazione(m)
    m.coda("q-conc", 900.0, data="2026-05-20")
    r = m.associa("q-conc", "d-rossi", tipo="conciliazione", conciliazione_id=conc["id"])
    assert r.status_code == 200, r.text

    # la parte ordinaria e' coperta al centesimo (700), non di piu'
    c = m.client.get(f"{POS}/conciliazioni?dipendente_id=d-rossi").json()["righe"][0]
    assert c["pagato_ordinaria"] == "700.00" and c["pagato_bonus"] == "0.00" and c["stato"] == "pagata_in_parte"
    assert c["pagamenti"][0]["importo"] == "700.00" and c["pagamenti"][0]["importo_versato"] == "900.00"
    # l'eccedenza di 200 e' da attribuire, nessun conto l'ha presa
    ecc = _eccedenze(m)
    assert len(ecc) == 1 and ecc[0]["importo"] == "200.00" and ecc[0]["stato"] == "da_attribuire"
    assert ecc[0]["bonifico_da_associare_id"] == "q-conc" and ecc[0]["pagamento_id"] == c["pagamenti"][0]["id"]
    assert m.conta("pagamenti_esiti") == 0 and m.conta("acconti_dipendenti") == 0
    assert m.paga("d-rossi")["stato_pagamento"] == "in_attesa_pagamento"

    # la posizione: avere 700 (non 900), l'eccedenza visibile con l'avviso, fuori dal saldo
    p = m.posizione("d-rossi")
    assert (p["totale_dare"], p["totale_avere"], p["chiusura"]) == (1700.0, 700.0, 1000.0)
    assert [e["importo"] for e in p["eccedenze_da_attribuire"]] == ["200.00"]
    riga = next(x for x in p["righe"] if x["tipo"] == "eccedenza")
    assert riga["dare"] is None and riga["avere"] is None and "da attribuire" in riga["avviso"]
    assert any("da attribuire" in a for a in p["avvisi"])
    assert p["bonus"]["pagato"] == 0.0

    # secondo giro: lo stesso bonifico non si applica due volte, nessuna seconda eccedenza
    assert m.associa("q-conc", "d-rossi", tipo="conciliazione", conciliazione_id=conc["id"]).status_code == 409
    run(pos.aggiungi_pagamento(m.hr, conc["id"], {"data": "2026-05-20", "importo": 900, "parte": "conciliazione",
                                                  "bonifico_da_associare_id": "q-conc"}))
    assert len(_eccedenze(m)) == 1
    assert len(m.client.get(f"{POS}/conciliazioni?dipendente_id=d-rossi").json()["righe"][0]["pagamenti"]) == 1


def test_7_attribuzione_a_stipendio_decisa_dal_titolare(rossi):
    m = rossi
    conc = _conciliazione(m)
    m.coda("q-conc", 900.0, data="2026-05-20")
    assert m.associa("q-conc", "d-rossi", tipo="conciliazione", conciliazione_id=conc["id"]).status_code == 200
    ecc_id = _eccedenze(m)[0]["id"]

    r = m.client.post(f"{POS}/eccedenze/{ecc_id}/attribuisci", json={"destinazione": "stipendio", "anno": ANNO, "mese": 3})
    assert r.status_code == 200, r.text
    assert r.json()["stato"] == "attribuita" and r.json()["attribuita_a"] == "stipendio"
    esiti = run(m.hr.pagamenti_esiti.find({"dipendente_id": "d-rossi"}, {"_id": 0}).to_list(10))
    assert len(esiti) == 1 and esiti[0]["importo"] == 200.0 and (esiti[0]["mese"], esiti[0]["anno"]) == (3, ANNO)
    # la busta di marzo lo conta subito, al centesimo
    paga = m.paga("d-rossi")
    assert paga["stato_pagamento"] == "parziale" and paga["saldo"] == 800.0
    p = m.posizione("d-rossi")
    assert (p["totale_avere"], p["chiusura"]) == (900.0, 800.0) and p["eccedenze_da_attribuire"] == []
    assert not any(x["tipo"] == "eccedenza" for x in p["righe"])
    # una volta attribuita non si tocca piu'
    r2 = m.client.post(f"{POS}/eccedenze/{ecc_id}/attribuisci", json={"destinazione": "acconto"})
    assert r2.status_code == 409 and r2.json()["detail"]["code"] == "ECCEDENZA_GIA_ATTRIBUITA"
    assert m.conta("pagamenti_esiti") == 1 and m.conta("acconti_dipendenti") == 0


def test_7_attribuzione_ad_acconto(rossi):
    m = rossi
    conc = _conciliazione(m)
    m.coda("q-conc", 900.0, data="2026-05-20")
    assert m.associa("q-conc", "d-rossi", tipo="conciliazione", conciliazione_id=conc["id"]).status_code == 200
    ecc_id = _eccedenze(m)[0]["id"]
    r = m.client.post(f"{POS}/eccedenze/{ecc_id}/attribuisci", json={"destinazione": "acconto", "anno": ANNO, "mese": 3})
    assert r.status_code == 200, r.text
    acc = run(m.hr.acconti_dipendenti.find({"dipendente_id": "d-rossi"}, {"_id": 0}).to_list(10))
    assert len(acc) == 1 and acc[0]["importo"] == 200.0 and acc[0]["scalato_su_anno_mese"] == f"{ANNO}-03"
    assert acc[0]["eccedenza_id"] == ecc_id and acc[0]["tipo"] == "stipendio"
    assert (m.paga("d-rossi")["stato_pagamento"], m.paga("d-rossi")["saldo"]) == ("parziale", 800.0)
    assert m.posizione("d-rossi")["totale_avere"] == 900.0


def test_7_attribuzione_a_bonus_solo_se_ci_sta_al_centesimo(rossi):
    m = rossi
    conc = _conciliazione(m)
    m.coda("q-conc", 900.0, data="2026-05-20")
    assert m.associa("q-conc", "d-rossi", tipo="conciliazione", conciliazione_id=conc["id"]).status_code == 200
    ecc_id = _eccedenze(m)[0]["id"]
    r = m.client.post(f"{POS}/eccedenze/{ecc_id}/attribuisci", json={"destinazione": "bonus"})
    assert r.status_code == 200, r.text
    c = m.client.get(f"{POS}/conciliazioni?dipendente_id=d-rossi").json()["righe"][0]
    assert c["pagato_ordinaria"] == "700.00" and c["pagato_bonus"] == "200.00" and c["stato"] == "pagata_in_parte"
    p = m.posizione("d-rossi")
    assert p["bonus"] == {**p["bonus"], "dovuto": 300.0, "pagato": 200.0, "saldo": 100.0}
    assert p["totale_avere"] == 700.0 and m.conta("pagamenti_esiti") == 0   # il bonus non e' paga

    # un'eccedenza piu' grande del bonus residuo (100) non ci entra: la decide altrove
    m.coda("q-bis", 850.0, data="2026-05-25")   # ordinaria gia' coperta: tutto eccedenza
    assert m.associa("q-bis", "d-rossi", tipo="conciliazione", conciliazione_id=conc["id"]).status_code == 200
    ecc2 = next(e for e in _eccedenze(m) if e["stato"] == "da_attribuire")
    assert ecc2["importo"] == "850.00" and ecc2["pagamento_id"] is None
    assert len(m.client.get(f"{POS}/conciliazioni?dipendente_id=d-rossi").json()["righe"][0]["pagamenti"]) == 2
    r = m.client.post(f"{POS}/eccedenze/{ecc2['id']}/attribuisci", json={"destinazione": "bonus"})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "OLTRE_BONUS"
    assert next(e for e in _eccedenze(m) if e["id"] == ecc2["id"])["stato"] == "da_attribuire"


def test_7_pagamento_scritto_a_mano_oltre_il_dovuto_segue_la_stessa_regola(rossi):
    m = rossi
    conc = _conciliazione(m)
    r = m.client.post(f"{POS}/conciliazioni/{conc['id']}/pagamenti",
                      json={"data": "2026-05-20", "importo": "1000.00", "parte": "conciliazione", "modalita": "contanti"})
    assert r.status_code == 200, r.text
    assert r.json()["pagato_ordinaria"] == "700.00" and r.json()["eccedenza"]["importo"] == "300.00"
    assert _eccedenze(m)[0]["modalita"] == "contanti" and _eccedenze(m)[0]["origine"] == "manuale"
    # destinazione sconosciuta: rifiutata, niente scelto al posto del titolare
    r = m.client.post(f"{POS}/eccedenze/{_eccedenze(m)[0]['id']}/attribuisci", json={"destinazione": "tfr"})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "VALORE_NON_AMMESSO"
    assert m.client.get(f"{POS}/eccedenze?dipendente_id=d-rossi").json()["righe"][0]["importo"] == "300.00"
    assert "destinazioni_eccedenza" in m.client.get(f"{POS}/vocabolari").json()
