"""Collaudo funzionale «Bonifici da associare» -> busta -> posizione dipendente.

Per ogni azione del titolare si guarda il RISULTATO sui dati, non la risposta
HTTP. Esito atteso scritto dal CLAUDE.md, «Personale»:

1. bonifico associato a mano come STIPENDIO uguale al netto: busta pagata,
   posizione a zero, bonifico ``confermato_manuale``, nessun motore automatico
   lo riassegna, il secondo giro non crea doppioni;
2. ACCONTO minore del netto: la busta non si salda, l'acconto e' un pagamento
   (``acconti_dipendenti``) mai sommato al netto; un secondo bonifico che
   completa porta il saldo a zero, in posizione **e** sul registro paghe; un
   acconto recuperato in busta conta nel DARE;
3. CONCILIAZIONE e BONUS: totale = somma delle voci, il bonus ha un conto suo,
   nessuno dei due tocca il netto o lo stato della busta;
5. omonimi: coda con candidati, nessuna proposta, mai applicato da solo;
   l'importo da solo non produce candidati.
"""
import pytest

from app.constants.stati_associazione_bonifico import e_confermato_manuale
from tests.hr.scenari_base import ANNO, mondo, run  # noqa: F401  (fixture)

CF_ROSSI = "RSSMRA80A01F839X"
CF_BIANCHI = "BNCLGU85B02F839Y"
CF_RUSSO_C = "RSSCMN90C03F839Z"
CF_RUSSO_A = "RSSNNA91D44F839W"
MB = "MB0B00923006"
DESCR_MOV = f"VOSTRA DISPOSIZIONE - VS.DISP. RIF. {MB}/90679785 FAVORE Rossi Mario - ADD.TOT"


@pytest.fixture
def rossi(mondo):
    mondo.dipendente("d-rossi", "Mario", "Rossi", CF_ROSSI)
    mondo.busta("d-rossi", 3, 1000.0)
    return mondo


# ── 1. stipendio uguale al netto ────────────────────────────────────────────

def test_1_stipendio_uguale_al_netto_chiude_busta_e_posizione(rossi):
    m = rossi
    m.coda("q1", 1000.0, rif_banca=MB, gestionale_movimento_id="mov-1")
    run(m.gest.estratto_conto_movimenti.insert_one(
        {"id": "mov-1", "data": "2026-04-03", "importo": -1000.0, "tipo": "uscita",
         "descrizione_originale": DESCR_MOV}))
    run(m.gest.prima_nota_salari.insert_one(
        {"id": "S1", "dipendente_id": "d-rossi", "dipendente": "ROSSI MARIO", "anno": 2026, "mese": 3,
         "importo_busta": 1000.0, "riconciliato": False}))

    r = m.associa("q1", "d-rossi")
    assert r.status_code == 200, r.text

    # la busta e' pagata, per intero, sul registro paghe (che e' lo stato che HR mostra)
    paga = m.paga("d-rossi")
    assert paga["stato_pagamento"] == "pagato" and paga["saldo"] == 0.0
    assert paga["bonifico_importo"] == 1000.0 and paga["bonifico_ricevuto"] is True
    # un pagamento solo, con le prove del bonifico, e il segno del titolare
    esiti = run(m.hr.pagamenti_esiti.find({"dipendente_id": "d-rossi"}, {"_id": 0}).to_list(10))
    assert len(esiti) == 1 and esiti[0]["importo"] == 1000.0 and (esiti[0]["mese"], esiti[0]["anno"]) == (3, ANNO)
    assert e_confermato_manuale(esiti[0]) and esiti[0]["rif_banca"] == MB
    coda = run(m.hr.bonifici_da_associare.find_one({"id": "q1"}, {"_id": 0}))
    assert coda["stato"] == "associato" and coda["confermato_manuale"] is True
    assert coda["confermato_da"] == "Titolare" and coda["associato_tipo"] == "stipendio"
    # il movimento d'estratto da cui nasce porta lo stesso segno
    assert e_confermato_manuale(run(m.gest.estratto_conto_movimenti.find_one({"id": "mov-1"})))

    # posizione: DARE = netto, AVERE = bonifico, chiusura a zero
    p = m.posizione("d-rossi")
    assert (p["totale_dare"], p["totale_avere"], p["chiusura"]) == (1000.0, 1000.0, 0.0)
    assert [x["tipo"] for x in p["righe"] if x["dare"] or x["avere"]] == ["busta", "bonifico"]
    # il riscontro per busta lo dice confermato
    riscontro = m.client.get(f"/api/posizione-dipendente/riscontro-bonifici?anno={ANNO}&dipendente_id=d-rossi").json()
    assert "confermato" in str(riscontro).lower()


def test_1_nessun_motore_automatico_riassegna_il_bonifico_confermato(rossi):
    from app.services.hr_pagamenti_deposito import deposita_movimento_banca_in_hr, deposita_pagamenti_in_hr
    from app.services.stipendi_bonifici import associa_bonifici_stipendi

    m = rossi
    m.coda("q1", 1000.0, rif_banca=MB, gestionale_movimento_id="mov-1")
    movimento = {"id": "mov-1", "data": "2026-04-03", "importo": -1000.0, "tipo": "uscita",
                 "descrizione_originale": DESCR_MOV, "descrizione": DESCR_MOV}
    run(m.gest.estratto_conto_movimenti.insert_one(dict(movimento)))
    # controllo: senza la conferma del titolare il motore bancario QUESTO movimento lo assocerebbe
    # (stessa busta, nome completo, importo e periodo): e' la prova che sotto e' la conferma a fermarlo
    run(m.gest.prima_nota_salari.insert_one(
        {"id": "S1", "dipendente_id": "d-rossi", "dipendente": "ROSSI MARIO", "anno": 2026, "mese": 3,
         "importo_busta": 1000.0, "riconciliato": False}))
    assert m.associa("q1", "d-rossi").status_code == 200   # conferma a mano: segna anche mov-1

    esito = run(associa_bonifici_stipendi(m.gest))
    assert esito["bonifici_associati"] == 0
    s1 = run(m.gest.prima_nota_salari.find_one({"id": "S1"}, {"_id": 0}))
    assert s1["riconciliato"] is False and not s1.get("movimenti_bancari_ids")
    assert e_confermato_manuale(run(m.gest.estratto_conto_movimenti.find_one({"id": "mov-1"})))

    # il ponte gestionale -> HR, riletto da capo, non deposita un secondo pagamento
    prima = m.conta("pagamenti_esiti")
    marca = run(deposita_movimento_banca_in_hr(m.gest, run(m.gest.estratto_conto_movimenti.find_one({"id": "mov-1"}, {"_id": 0}))))
    assert marca["esito"] == "confermato_manuale"
    run(deposita_pagamenti_in_hr(m.gest))
    giro2 = run(deposita_pagamenti_in_hr(m.gest))
    assert m.conta("pagamenti_esiti") == prima == 1
    assert m.conta("bonifici_da_associare", {"id": {"$ne": "q1"}}) == 0   # niente nuova riga in coda
    assert not giro2["dettaglio"]                                         # il secondo giro e' a zero
    assert m.paga("d-rossi")["bonifico_importo"] == 1000.0               # nessun importo raddoppiato

    # controllo di sensibilita': lo stesso movimento NON confermato verrebbe associato dal motore
    run(m.gest.estratto_conto_movimenti.update_one(
        {"id": "mov-1"}, {"$set": {"confermato_manuale": False}, "$unset": {"hr_deposito": ""}}))
    assert run(associa_bonifici_stipendi(m.gest))["bonifici_associati"] == 1


def test_1_secondo_giro_e_ritiro_non_lasciano_doppioni(rossi):
    m = rossi
    m.coda("q1", 1000.0, rif_banca=MB)
    assert m.associa("q1", "d-rossi").status_code == 200
    # lo stesso bonifico non si associa due volte
    r2 = m.associa("q1", "d-rossi")
    assert r2.status_code == 409 and r2.json()["detail"]["code"] == "GIA_ASSOCIATO"
    # nemmeno la sua copia (stesso «MB…», altra riga: ricevuta ed estratto)
    m.coda("q1bis", 1000.0, causale=f"VS.DISP. RIF. {MB}/9 FAVORE BENEFICIARI VARI", rif_banca=MB)
    r3 = m.associa("q1bis", "d-rossi")
    assert r3.status_code == 409
    assert m.conta("pagamenti_esiti") == 1 and m.conta("bonifici") == 1
    assert m.paga("d-rossi")["bonifico_importo"] == 1000.0

    # ritiro: il bonifico torna in coda, la busta torna aperta, la posizione riapre il dovuto
    assert m.client.post("/api/dipendenti-cloud/bonifici-da-associare/q1/ritira-conferma").status_code == 200
    assert m.conta("pagamenti_esiti") == 0 and m.conta("bonifici") == 0
    assert m.paga("d-rossi")["stato_pagamento"] == "in_attesa_pagamento"
    coda = run(m.hr.bonifici_da_associare.find_one({"id": "q1"}, {"_id": 0}))
    assert coda["stato"] == "da_associare" and not e_confermato_manuale(coda)
    p = m.posizione("d-rossi")
    assert (p["totale_dare"], p["totale_avere"], p["chiusura"]) == (1000.0, 0.0, 1000.0)


def test_1_motore_bancario_secondo_giro_nuovi_zero(rossi):
    """Il motore automatico (estratto conto -> busta del gestionale): secondo giro a zero."""
    from app.services.stipendi_bonifici import associa_bonifici_stipendi

    m = rossi
    run(m.gest.estratto_conto_movimenti.insert_one(
        {"id": "mov-1", "data": "2026-04-03", "importo": -1000.0, "tipo": "uscita",
         "descrizione_originale": DESCR_MOV}))
    run(m.gest.prima_nota_salari.insert_one(
        {"id": "S1", "dipendente_id": "d-rossi", "dipendente": "ROSSI MARIO", "anno": 2026, "mese": 3,
         "importo_busta": 1000.0, "riconciliato": False}))
    assert run(associa_bonifici_stipendi(m.gest))["bonifici_associati"] == 1
    s1 = run(m.gest.prima_nota_salari.find_one({"id": "S1"}, {"_id": 0}))
    assert s1["riconciliato"] is True and s1["importo_bonifico"] == 1000.0 and s1["saldo"] == 0.0
    assert run(associa_bonifici_stipendi(m.gest))["bonifici_associati"] == 0
    s1bis = run(m.gest.prima_nota_salari.find_one({"id": "S1"}, {"_id": 0}))
    assert (s1bis["importo_bonifico"], s1bis["saldo"], s1bis["movimenti_bancari_ids"]) == (1000.0, 0.0, ["mov-1"])


def test_1_la_riga_d_estratto_dello_stesso_bonifico_arricchisce_non_duplica(rossi):
    """Ricevuta PDF in coda (senza nome), associata a mano; poi arriva l'estratto con il nome:
    stesso dipendente, importo al centesimo, 1 giorno -> e' lo stesso pagamento, mai un secondo."""
    from app.services.hr_pagamenti_deposito import deposita_movimento_banca_in_hr

    m = rossi
    m.coda("q1", 1000.0, data="2026-04-03", causale="BENEFICIARI VARI", cro="CRO123")
    assert m.associa("q1", "d-rossi").status_code == 200
    mov = {"id": "mov-1", "data": "2026-04-04", "importo": -1000.0, "tipo": "uscita",
           "descrizione": DESCR_MOV, "descrizione_originale": DESCR_MOV}
    marca = run(deposita_movimento_banca_in_hr(m.gest, mov))
    assert marca["esito"] == "arricchito" and marca["key"] == "beneficiari-diversi:q1"
    assert m.conta("pagamenti_esiti") == 1 and m.paga("d-rossi")["bonifico_importo"] == 1000.0
    # un altro bonifico stesso importo, un mese dopo, e' un altro pagamento (altra competenza): non si fonde
    altro = {**mov, "id": "mov-2", "data": "2026-04-30", "descrizione": DESCR_MOV.replace(MB, "MB0B00999999")}
    assert run(deposita_movimento_banca_in_hr(m.gest, altro))["esito"] == "depositato"
    assert m.conta("pagamenti_esiti") == 2


# ── 2. acconto minore del netto ─────────────────────────────────────────────

def test_2_acconto_non_salda_la_busta_e_il_secondo_bonifico_la_completa(rossi):
    m = rossi
    m.coda("q-acc", 400.0, data="2026-03-10")
    m.coda("q-saldo", 600.0, data="2026-04-03")

    assert m.associa("q-acc", "d-rossi", tipo="acconto").status_code == 200

    # l'acconto e' un pagamento del registro acconti: non e' un bonifico di busta, non si somma al netto
    acc = run(m.hr.acconti_dipendenti.find({"dipendente_id": "d-rossi"}, {"_id": 0}).to_list(10))
    assert len(acc) == 1 and acc[0]["importo"] == 400.0 and acc[0]["tipo"] == "stipendio"
    assert acc[0]["scalato_su_anno_mese"] == "2026-03" and acc[0]["bonifico_da_associare_id"] == "q-acc"
    assert m.conta("pagamenti_esiti") == 0 and m.conta("bonifici") == 0
    ced = run(m.hr.cedolini.find_one({"id": "c-d-rossi-2026-3"}, {"_id": 0}))
    assert ced["netto"] == 1000.0                                      # il netto della busta non cambia
    assert m.paga("d-rossi")["stato_pagamento"] != "pagato"            # la busta non si salda
    p = m.posizione("d-rossi")
    assert (p["totale_dare"], p["totale_avere"], p["chiusura"]) == (1000.0, 400.0, 600.0)  # residuo = differenza
    assert [x["avere"] for x in p["righe"] if x["tipo"] == "acconto"] == [400.0]
    assert all(x["dare"] is None for x in p["righe"] if x["tipo"] == "acconto")
    # il registro paghe dice la stessa cosa della posizione: residuo 600, non 1000
    assert m.paga("d-rossi")["saldo"] == 600.0

    # il secondo bonifico completa: saldo a zero ovunque
    assert m.associa("q-saldo", "d-rossi", tipo="stipendio").status_code == 200
    p = m.posizione("d-rossi")
    assert (p["totale_dare"], p["totale_avere"], p["chiusura"]) == (1000.0, 1000.0, 0.0)
    paga = m.paga("d-rossi")
    assert paga["stato_pagamento"] == "pagato" and paga["saldo"] == 0.0

    # il giro periodico che ricostruisce il registro paghe dai cedolini (ogni 6 ore) dice lo stesso:
    # non riapre una busta che l'acconto e il bonifico hanno chiuso
    from app.hr.services.sincronizza_paghe_mensili import sincronizza

    run(sincronizza(m.hr))
    paga = m.paga("d-rossi")
    assert paga["stato_pagamento"] == "pagato" and paga["saldo"] == 0.0
    assert m.conta("paghe_mensili") == 1                      # nessuna riga doppia
    p = m.posizione("d-rossi")
    assert (p["totale_dare"], p["totale_avere"], p["chiusura"]) == (1000.0, 1000.0, 0.0)


def test_2_stipendio_minore_del_netto_e_parziale_col_residuo(rossi):
    m = rossi
    m.coda("q1", 400.0)
    assert m.associa("q1", "d-rossi", tipo="stipendio").status_code == 200
    paga = m.paga("d-rossi")
    assert paga["stato_pagamento"] == "parziale" and paga["saldo"] == 600.0 and paga["bonifico_importo"] == 400.0
    p = m.posizione("d-rossi")
    assert (p["totale_dare"], p["totale_avere"], p["chiusura"]) == (1000.0, 400.0, 600.0)


def test_2_acconto_registrato_dalla_pagina_acconti_segue_lo_stesso_conto(rossi):
    """Un acconto di stipendio nato altrove (pagina Acconti) o corretto dopo: lo stato del mese lo segue subito."""
    m = rossi
    r = m.client.post("/api/tfr/acconti", json={"dipendente_id": "d-rossi", "tipo": "stipendio", "importo": 400.0,
                                                "data": "2026-03-10"})
    assert r.status_code == 200, r.text
    acconto_id = r.json()["acconto_id"]
    assert (m.paga("d-rossi")["stato_pagamento"], m.paga("d-rossi")["saldo"]) == ("parziale", 600.0)
    assert m.client.put(f"/api/tfr/acconti/{acconto_id}", json={"importo": 1000.0}).status_code == 200
    assert (m.paga("d-rossi")["stato_pagamento"], m.paga("d-rossi")["saldo"]) == ("pagato", 0.0)
    p = m.posizione("d-rossi")
    assert (p["totale_dare"], p["totale_avere"], p["chiusura"]) == (1000.0, 1000.0, 0.0)
    assert m.client.delete(f"/api/tfr/acconti/{acconto_id}").status_code == 200
    assert m.paga("d-rossi")["stato_pagamento"] == "in_attesa_pagamento"
    assert m.posizione("d-rossi")["chiusura"] == 1000.0


def test_2_secondo_giro_dell_acconto_non_lo_duplica(rossi):
    m = rossi
    m.coda("q-acc", 400.0, data="2026-03-10")
    assert m.associa("q-acc", "d-rossi", tipo="acconto").status_code == 200
    assert m.associa("q-acc", "d-rossi", tipo="acconto").status_code == 409
    assert m.conta("acconti_dipendenti") == 1
    assert m.posizione("d-rossi")["totale_avere"] == 400.0


def test_2_acconto_recuperato_in_busta_conta_nel_dare(mondo):
    m = mondo
    m.dipendente("d-rossi", "Mario", "Rossi", CF_ROSSI)
    # busta di 150 € che recupera un acconto di 1.000 € (voce 000306): il dovuto del mese e' 1.150
    m.busta("d-rossi", 3, 150.0, cedolino_extra={"dati_chiave": {"acconto_recuperato_busta": "1.000,00",
                                                                 "acconto_recuperato_voce": "000306"}})
    m.coda("q-acc", 1000.0, data="2026-03-10")
    m.coda("q-saldo", 150.0, data="2026-04-03")
    assert m.associa("q-acc", "d-rossi", tipo="acconto").status_code == 200
    p = m.posizione("d-rossi")
    assert p["totale_dare"] == 1150.0 and p["totale_avere"] == 1000.0 and p["chiusura"] == 150.0
    busta = next(x for x in p["righe"] if x["tipo"] == "busta")
    assert busta["dare"] == 1150.0 and "acconto recuperato" in busta["descrizione"]
    assert m.associa("q-saldo", "d-rossi", tipo="stipendio").status_code == 200
    p = m.posizione("d-rossi")
    assert (p["totale_dare"], p["totale_avere"], p["chiusura"]) == (1150.0, 1150.0, 0.0)
    # lo stato del mese segue la posizione: l'acconto dato (1.000) + il bonifico (150) coprono 1.150
    assert m.paga("d-rossi")["stato_pagamento"] == "pagato"


# ── 3. conciliazione e bonus ────────────────────────────────────────────────

def _conciliazione(m, **extra):
    corpo = {"dipendente_id": "d-rossi", "data": "2026-05-10", "tipo": "conciliazione_sindacale",
             "modalita_pagamento": "bonifico",
             "voci": [{"voce": "straordinari", "importo": "700.00"},
                      {"voce": "bonus_transattivo", "importo": "300.00"}],
             "totale": "1000.00", **extra}
    return m.client.post("/api/posizione-dipendente/conciliazioni", json=corpo)


def test_3_conciliazione_e_bonus_non_toccano_il_netto_ne_lo_stato_della_busta(rossi):
    m = rossi
    m.coda("q-conc", 700.0, data="2026-05-20")
    m.coda("q-bonus", 300.0, data="2026-05-21")
    r = _conciliazione(m)
    assert r.status_code == 200
    conc = r.json()
    assert conc["totale"] == "1000.00" and conc["bonus"] == "300.00" and conc["parte_ordinaria"] == "700.00"

    assert m.associa("q-conc", "d-rossi", tipo="conciliazione", conciliazione_id=conc["id"]).status_code == 200
    assert m.associa("q-bonus", "d-rossi", tipo="bonus", conciliazione_id=conc["id"]).status_code == 200

    # nessuno dei due e' un pagamento di busta
    assert m.conta("pagamenti_esiti") == 0 and m.conta("bonifici") == 0 and m.conta("acconti_dipendenti") == 0
    assert m.paga("d-rossi")["stato_pagamento"] == "in_attesa_pagamento" and not m.paga("d-rossi").get("bonifico_importo")
    assert run(m.hr.cedolini.find_one({"id": "c-d-rossi-2026-3"}, {"_id": 0}))["netto"] == 1000.0
    lista = m.client.get("/api/posizione-dipendente/conciliazioni?dipendente_id=d-rossi").json()["righe"]
    assert lista[0]["stato"] == "pagata" and lista[0]["pagato_ordinaria"] == "700.00" and lista[0]["pagato_bonus"] == "300.00"

    p = m.posizione("d-rossi")
    # conto paghe: busta 1.000 + parte ordinaria della conciliazione 700 contro il bonifico ordinario 700
    assert (p["totale_dare"], p["totale_avere"], p["chiusura"]) == (1700.0, 700.0, 1000.0)
    # il bonus ha il suo conto, fuori dalle paghe, e a fine pagamenti e' chiuso
    assert p["bonus"]["dovuto"] == 300.0 and p["bonus"]["pagato"] == 300.0 and p["bonus"]["saldo"] == 0.0
    assert not any(x["descrizione"].startswith("Bonus") for x in p["righe"])


def test_3_conciliazione_con_totale_diverso_dalla_somma_e_rifiutata(rossi):
    r = _conciliazione(rossi, totale="999.99")
    assert r.status_code == 400 and r.json()["detail"]["code"] == "TOTALE_NON_QUADRA"
    assert rossi.conta("conciliazioni") == 0


def test_3_bonus_su_conciliazione_senza_bonus_e_rifiutato(rossi):
    m = rossi
    conc = _conciliazione(m, voci=[{"voce": "straordinari", "importo": "700.00"}], totale="700.00").json()
    m.coda("q-b", 100.0, data="2026-05-21")
    r = m.associa("q-b", "d-rossi", tipo="bonus", conciliazione_id=conc["id"])
    assert r.status_code == 400 and r.json()["detail"]["code"] == "SENZA_BONUS"
    assert run(m.hr.bonifici_da_associare.find_one({"id": "q-b"}))["stato"] == "da_associare"  # niente applicato


# ── 5. omonimi e ambiguita' ─────────────────────────────────────────────────

def test_5_omonimi_coda_con_candidati_nessuna_proposta_mai_applicato(mondo):
    m = mondo
    m.dipendente("d-russo-c", "Carmine", "Russo", CF_RUSSO_C)
    m.dipendente("d-russo-a", "Anna", "Russo", CF_RUSSO_A)
    m.busta("d-russo-c", 3, 950.0)
    m.busta("d-russo-a", 3, 700.0)
    m.coda("q-russo", 950.0, causale="bonifico russo marzo")

    coda = m.client.get("/api/dipendenti-cloud/bonifici-da-associare").json()
    riga = next(r for r in coda if r["id"] == "q-russo")
    assert {c["dipendente_id"] for c in riga["candidati"]} == {"d-russo-c", "d-russo-a"}
    assert riga["avviso_multi_dipendente"] is True and riga["proposta"] is None
    # niente applicato da solo: la coda e' com'era, le buste aperte, nessun pagamento
    assert m.conta("pagamenti_esiti") == 0 and m.conta("acconti_dipendenti") == 0
    assert run(m.hr.bonifici_da_associare.find_one({"id": "q-russo"}))["stato"] == "da_associare"
    assert m.paga("d-russo-c")["stato_pagamento"] == "in_attesa_pagamento"


def test_5_il_ponte_banca_non_sceglie_fra_omonimi(mondo):
    from app.services.hr_pagamenti_deposito import deposita_movimento_banca_in_hr

    m = mondo
    m.dipendente("d-russo-c", "Carmine", "Russo", CF_RUSSO_C)
    m.dipendente("d-russo-a", "Anna", "Russo", CF_RUSSO_A)
    m.busta("d-russo-c", 3, 950.0)
    mov = {"id": "mov-russo", "data": "2026-04-03", "importo": -950.0, "tipo": "uscita",
           "descrizione_originale": "VOSTRA DISPOSIZIONE - VS.DISP. RIF. MB0B00111111/9 FAVORE Russo - ADD.TOT"}
    mov["descrizione"] = mov["descrizione_originale"]
    marca = run(deposita_movimento_banca_in_hr(m.gest, mov))
    assert marca["esito"] == "in_coda"
    assert m.conta("pagamenti_esiti") == 0 and m.conta("bonifici_da_associare") == 1
    # il secondo giro dello stesso movimento non crea una seconda riga in coda
    run(deposita_movimento_banca_in_hr(m.gest, mov))
    assert m.conta("bonifici_da_associare") == 1


def test_5_importo_da_solo_non_produce_candidati(mondo):
    m = mondo
    m.dipendente("d-rossi", "Mario", "Rossi", CF_ROSSI)
    m.dipendente("d-bianchi", "Luigi", "Bianchi", CF_BIANCHI)
    m.busta("d-rossi", 3, 950.0)
    m.busta("d-bianchi", 3, 950.0)
    m.coda("q-solo-importo", 950.0, causale="AGGIUNTIVA")
    m.coda("q-vuota", 950.0, causale="")
    righe = {r["id"]: r for r in m.client.get("/api/dipendenti-cloud/bonifici-da-associare").json()}
    assert righe["q-solo-importo"]["candidati"] == [] and righe["q-vuota"]["candidati"] == []
    assert righe["q-solo-importo"]["proposta"] is None


def test_5_il_motore_bancario_distingue_gli_omonimi_per_nome_completo(mondo):
    """Due Russo con la stessa busta: «FAVORE Russo Carmine» e' di Carmine soltanto;
    «FAVORE Russo» (cognome solo) non e' di nessuno dei due."""
    from app.services.stipendi_bonifici import associa_bonifici_stipendi

    m = mondo
    m.dipendente("d-russo-c", "Carmine", "Russo", CF_RUSSO_C)
    m.dipendente("d-russo-a", "Anna", "Russo", CF_RUSSO_A)
    for id_, dip, nome in (("S-C", "d-russo-c", "RUSSO CARMINE"), ("S-A", "d-russo-a", "RUSSO ANNA")):
        run(m.gest.prima_nota_salari.insert_one(
            {"id": id_, "dipendente_id": dip, "dipendente": nome, "anno": 2026, "mese": 3,
             "importo_busta": 950.0, "riconciliato": False}))
    run(m.gest.estratto_conto_movimenti.insert_one(
        {"id": "m-solo-cognome", "data": "2026-04-03", "importo": -950.0, "tipo": "uscita",
         "descrizione_originale": "VOSTRA DISPOSIZIONE - VS.DISP. RIF. MB0B00000001/9 FAVORE Russo - ADD.TOT"}))
    assert run(associa_bonifici_stipendi(m.gest))["bonifici_associati"] == 0
    assert all(r["riconciliato"] is False for r in run(m.gest.prima_nota_salari.find({}, {"_id": 0}).to_list(10)))

    run(m.gest.estratto_conto_movimenti.insert_one(
        {"id": "m-completo", "data": "2026-04-03", "importo": -950.0, "tipo": "uscita",
         "descrizione_originale": "VOSTRA DISPOSIZIONE - VS.DISP. RIF. MB0B00000002/9 FAVORE Russo Carmine - ADD.TOT"}))
    assert run(associa_bonifici_stipendi(m.gest))["bonifici_associati"] == 1
    righe = {r["id"]: r for r in run(m.gest.prima_nota_salari.find({}, {"_id": 0}).to_list(10))}
    assert righe["S-C"]["riconciliato"] is True and righe["S-C"]["movimenti_bancari_ids"] == ["m-completo"]
    assert righe["S-A"]["riconciliato"] is False and not righe["S-A"].get("movimenti_bancari_ids")
