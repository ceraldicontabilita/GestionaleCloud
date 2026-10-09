"""Collaudo funzionale: l'associazione manuale di un bonifico in HR aggiorna il
cedolino del gestionale.

Lo stato vero del mese e' ``paghe_mensili.stato_pagamento``; il campo ``pagato``
della collezione ``cedolini`` del gestionale (quello che leggono riepiloghi e
doppioni) deve seguirlo, da un solo scrittore (``cedolini_pagamento``):

* stipendio uguale al netto → ``pagato=True``, ``importo_pagato``, ``data_pagamento``,
  una voce in ``pagamenti[]`` col riferimento del bonifico;
* ``ritira-conferma`` → la voce sparisce e il cedolino si riapre;
* acconto parziale → la voce c'e' ma ``pagato=False``; il secondo bonifico chiude;
* il cedolino si trova per ``gestionale_cedolino_id``, altrimenti per CF+anno+mese+tipo;
  una versione ``sostituito`` non si tocca; senza cedolino l'esito lo dichiara;
* ``/paghe/conferma-associazione`` segna e, con ``riconciliato=false``, riapre;
* lo stesso bonifico visto due volte non raddoppia ``importo_pagato``.
"""
import pytest

from tests.hr.scenari_base import ANNO, mondo, run  # noqa: F401  (fixture)

CF_ROSSI = "RSSMRA80A01F839X"


def _cedolino_gest(m, id_="g-rossi-3", netto=1000.0, **extra):
    doc = {"id": id_, "codice_fiscale": CF_ROSSI, "anno": ANNO, "mese": 3, "tipo_cedolino": "mensile",
           "netto": netto, "pagato": False, "importo_pagato": 0, "pagamenti": [], **extra}
    run(m.gest.cedolini.insert_one(dict(doc)))
    return doc


def _gest(m, id_="g-rossi-3"):
    return run(m.gest.cedolini.find_one({"id": id_}, {"_id": 0}))


@pytest.fixture
def rossi(mondo):
    mondo.dipendente("d-rossi", "Mario", "Rossi", CF_ROSSI)
    return mondo


def test_stipendio_intero_segna_pagato_il_cedolino_del_gestionale_e_il_ritiro_lo_riapre(rossi):
    m = rossi
    m.busta("d-rossi", 3, 1000.0, cedolino_extra={"gestionale_cedolino_id": "g-rossi-3"})
    _cedolino_gest(m)
    m.coda("q1", 1000.0, data="2026-04-03")

    r = m.associa("q1", "d-rossi")
    assert r.status_code == 200, r.text
    assert m.paga("d-rossi")["stato_pagamento"] == "pagato"
    assert r.json()["cedolino_gestionale"]["esito"] == "segnato"

    ced = _gest(m)
    assert ced["pagato"] is True
    assert ced["importo_pagato"] == 1000.0 and ced["saldo_residuo"] == 0.0
    assert ced["data_pagamento"] == "2026-04-03" and ced["metodo_pagamento"] == "bonifico"
    assert len(ced["pagamenti"]) == 1
    voce = ced["pagamenti"][0]
    assert voce["riferimento"] == "hr:bonifici_da_associare:q1" and voce["importo"] == 1000.0
    assert voce["fonte"] == "hr_associazione_manuale" and voce["stato_mese"] == "pagato"

    # il ritiro toglie il pagamento e riapre il cedolino
    assert m.client.post("/api/dipendenti-cloud/bonifici-da-associare/q1/ritira-conferma").status_code == 200
    assert m.paga("d-rossi")["stato_pagamento"] == "in_attesa_pagamento"
    ced = _gest(m)
    assert ced["pagato"] is False and ced["importo_pagato"] == 0.0 and ced["pagamenti"] == []
    assert ced["data_pagamento"] is None and ced["saldo_residuo"] == 1000.0


def test_acconto_parziale_non_dichiara_pagato_e_il_saldo_chiude(rossi):
    m = rossi
    m.busta("d-rossi", 3, 1000.0, cedolino_extra={"gestionale_cedolino_id": "g-rossi-3"})
    _cedolino_gest(m)
    m.coda("q1", 600.0, data="2026-04-03")
    m.coda("q2", 400.0, data="2026-04-10")

    assert m.associa("q1", "d-rossi").status_code == 200
    assert m.paga("d-rossi")["stato_pagamento"] == "parziale"
    ced = _gest(m)
    assert ced["pagato"] is False and ced["importo_pagato"] == 600.0 and ced["saldo_residuo"] == 400.0
    assert len(ced["pagamenti"]) == 1

    assert m.associa("q2", "d-rossi").status_code == 200
    assert m.paga("d-rossi")["stato_pagamento"] == "pagato"
    ced = _gest(m)
    assert ced["pagato"] is True and ced["importo_pagato"] == 1000.0 and ced["saldo_residuo"] == 0.0
    assert [p["riferimento"] for p in ced["pagamenti"]] == [
        "hr:bonifici_da_associare:q1", "hr:bonifici_da_associare:q2"]
    assert ced["data_pagamento"] == "2026-04-10"

    # ritirando il saldo resta l'acconto: parziale, non pagato
    assert m.client.post("/api/dipendenti-cloud/bonifici-da-associare/q2/ritira-conferma").status_code == 200
    ced = _gest(m)
    assert ced["pagato"] is False and ced["importo_pagato"] == 600.0 and len(ced["pagamenti"]) == 1


def test_cedolino_trovato_per_cf_anno_mese_tipo_senza_id_di_collegamento(rossi):
    m = rossi
    m.busta("d-rossi", 3, 1000.0)                       # la riga HR non porta gestionale_cedolino_id
    _cedolino_gest(m, "g-ordinario")                    # tipo "mensile" nel gestionale = "ordinario" in HR
    _cedolino_gest(m, "g-13", tipo_cedolino="tredicesima")
    _cedolino_gest(m, "g-vecchio", status="sostituito")  # la versione perdente non e' il cedolino
    m.coda("q1", 1000.0)

    r = m.associa("q1", "d-rossi")
    assert r.status_code == 200 and r.json()["cedolino_gestionale"]["cedolino_id"] == "g-ordinario"
    assert _gest(m, "g-ordinario")["pagato"] is True
    assert _gest(m, "g-13")["pagato"] is False and _gest(m, "g-vecchio")["pagato"] is False


def test_senza_cedolino_nel_gestionale_l_associazione_riesce_e_lo_dichiara(rossi):
    m = rossi
    m.busta("d-rossi", 3, 1000.0)
    m.coda("q1", 1000.0)
    r = m.associa("q1", "d-rossi")
    assert r.status_code == 200
    assert r.json()["cedolino_gestionale"]["esito"] == "cedolino_gestionale_non_trovato"
    assert m.paga("d-rossi")["stato_pagamento"] == "pagato"    # il lato HR non si blocca


def test_due_cedolini_attivi_dello_stesso_tipo_nessuno_scelto(rossi):
    m = rossi
    m.busta("d-rossi", 3, 1000.0)
    _cedolino_gest(m, "g-a")
    _cedolino_gest(m, "g-b")
    m.coda("q1", 1000.0)
    r = m.associa("q1", "d-rossi")
    assert r.json()["cedolino_gestionale"]["esito"] == "cedolino_gestionale_non_trovato"
    assert _gest(m, "g-a")["pagato"] is False and _gest(m, "g-b")["pagato"] is False


def test_conferma_associazione_segna_e_annulla_riapre(rossi):
    m = rossi
    m.busta("d-rossi", 3, 1000.0, cedolino_extra={"gestionale_cedolino_id": "g-rossi-3"},
            bonifico_importo=1000.0, bonifico_ricevuto=True, stato_pagamento="pagato")
    _cedolino_gest(m)
    corpo = {"dipendente_id": "d-rossi", "anno": ANNO, "mese": 3}

    r = m.client.post("/api/dipendenti-cloud/paghe/conferma-associazione", json={**corpo, "riconciliato": True})
    assert r.status_code == 200, r.text
    ced = _gest(m)
    assert ced["pagato"] is True and ced["importo_pagato"] == 1000.0
    assert ced["pagamenti"][0]["riferimento"] == f"hr:conferma_associazione:d-rossi:{ANNO}-03"

    r = m.client.post("/api/dipendenti-cloud/paghe/conferma-associazione", json={**corpo, "riconciliato": False})
    assert r.status_code == 200
    ced = _gest(m)
    assert ced["pagato"] is False and ced["pagamenti"] == [] and ced["importo_pagato"] == 0.0


def test_lo_stesso_riferimento_due_volte_non_raddoppia(rossi):
    from app.services.cedolini_pagamento import riapri_cedolino, segna_cedolino_pagato

    m = rossi
    ced = _cedolino_gest(m)
    for _ in range(2):
        run(segna_cedolino_pagato(m.gest, ced, importo=1000.0, data="2026-04-03",
                                  riferimento="prima_nota_salari:S1", fonte="riconciliazione_automatica"))
    salvato = _gest(m)
    assert salvato["importo_pagato"] == 1000.0 and len(salvato["pagamenti"]) == 1 and salvato["pagato"] is True

    # un riferimento che il cedolino non ha non cambia niente (la prova automatica resta)
    esito = run(riapri_cedolino(m.gest, salvato, riferimento="hr:bonifici_da_associare:x"))
    assert esito["esito"] == "riferimento_assente" and _gest(m)["pagato"] is True


def test_il_motore_automatico_passa_dallo_stesso_scrittore(rossi):
    """``processa_cedolino_v2`` non scrive piu' ``pagato`` da solo: la riga arriva
    da ``segna_cedolino_pagato`` con la prova della Prima Nota salari."""
    import inspect

    from app.services import salari_unificati_v2 as mod

    sorgente = inspect.getsource(mod.processa_cedolino_v2)
    assert "segna_cedolino_pagato" in sorgente
    assert '"pagato": True' not in sorgente
    sorgente_manuale = inspect.getsource(mod.registra_pagamento_salario)
    assert "segna_cedolino_pagato" in sorgente_manuale and '"pagato":' not in sorgente_manuale
