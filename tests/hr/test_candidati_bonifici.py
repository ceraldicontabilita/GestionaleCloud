"""Coda «Bonifici da associare»: candidati, avviso multi-dipendente, conferma manuale.

Regole provate (CLAUDE.md, «Personale» e «Identita', prove e attese»):

* un candidato non si applica mai e l'importo da solo non produce candidati;
* i candidati sono al massimo 10, in ordine di forza della prova;
* un cognome condiviso elenca tutti, senza sceglierne uno (nessuna proposta);
* un bonifico confermato a mano e' consumato: sparisce dai candidati delle altre
  righe (nei due ordini di arrivo), non si riassegna, si puo' ritirare;
* nessun motore automatico tocca un bonifico ``confermato_manuale``.

Database finti (mongomock): HR (dipendenti, paghe_mensili, pagamenti_esiti,
bonifici_da_associare) e gestionale (estratto_conto_movimenti).
"""
import asyncio

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

from app.constants.stati_associazione_bonifico import (
    AVVISO_BENEFICIARI_VARI,
    AVVISO_COGNOME_CONDIVISO,
    AVVISO_NOTA_DI_TERZI,
    AVVISO_STESSO_IMPORTO_PIU_BUSTE,
    MAX_CANDIDATI,
    PROVA_CF,
    PROVA_COGNOME_IMPORTO,
    PROVA_IMPORTO_PERIODO,
    PROVA_NOME_COMPLETO,
)
from app.services import candidati_bonifico as cand
from app.services import hr_pagamenti_deposito as ponte

ADMIN = {"role": "admin", "name": "Titolare"}


def _run(coro):
    return asyncio.run(coro)


def _dip(id_, nome, cognome, cf):
    return {"id": id_, "nome": nome, "cognome": cognome, "nome_completo": f"{cognome} {nome}",
            "codice_fiscale": cf, "attivo": True}


VESPA = _dip("dip-vespa", "Vincenzo", "Vespa", "VSPVCN80A01F839X")
TAIANO = _dip("dip-taiano", "Luigi", "Taiano", "TNALGU85B02F839Y")
RUSSO_C = _dip("dip-russo-c", "Carmine", "Russo", "RSSCMN90C03F839Z")
RUSSO_A = _dip("dip-russo-a", "Anna", "Russo", "RSSNNA91D44F839W")


def _busta(dip, mese, netto, anno=2026, **extra):
    return {"dipendente_id": dip, "anno": anno, "mese": mese, "importo_busta": netto,
            "stato_pagamento": "in_attesa_pagamento", **extra}


@pytest.fixture
def hr(monkeypatch):
    from app.hr.database import Database as DatabaseHR
    from app.hr.routers import dipendenti_cloud as router

    db = AsyncMongoMockClient()["hr_test"]
    gest = AsyncMongoMockClient()["gest_test"]
    monkeypatch.setattr(DatabaseHR, "get_db", classmethod(lambda cls: db))
    monkeypatch.setattr(router, "_db_gestionale", lambda: gest)
    _run(db.dipendenti.insert_many([dict(d) for d in (VESPA, TAIANO, RUSSO_C, RUSSO_A)]))
    db.gest = gest
    return db


def _coda(db, id_, **campi):
    riga = {"id": id_, "stato": "da_associare", "data": "2026-04-03", "importo": 950.0,
            "causale": "bonifico", "created_at": "2026-04-03T00:00:00+00:00"}
    riga.update(campi)
    _run(db.bonifici_da_associare.insert_one(riga))
    return riga


def _calcola(db, **campi):
    """Candidati per una riga di coda, dai dati veri del database di prova."""
    from app.hr.routers.dipendenti_cloud import _indici_dipendenti

    indici = _run(_indici_dipendenti(db))
    buste = _run(cand.carica_buste_hr(db))
    riga = {"data": "2026-04-03", "importo": 950.0, "causale": "bonifico", **campi}
    return cand.calcola_per_riga(riga, indici, buste)


# ── candidati ────────────────────────────────────────────────────────────────

def test_cognome_condiviso_elenca_tutti_senza_sceglierne_uno(hr):
    _run(hr.paghe_mensili.insert_many([_busta("dip-russo-c", 3, 950.0), _busta("dip-russo-a", 3, 700.0)]))

    esito = _calcola(hr, causale="bonifico russo marzo")

    assert {c["dipendente_id"] for c in esito["candidati"]} == {"dip-russo-c", "dip-russo-a"}
    assert esito["avviso_multi_dipendente"] is True
    assert esito["avviso_motivo"] == AVVISO_COGNOME_CONDIVISO
    assert esito["proposta"] is None  # niente si sceglie da solo
    # l'importo uguale al residuo della busta alza la prova, ma non decide
    per_id = {c["dipendente_id"]: c for c in esito["candidati"]}
    assert per_id["dip-russo-c"]["prova"] == PROVA_COGNOME_IMPORTO
    assert per_id["dip-russo-c"]["punteggio"] > per_id["dip-russo-a"]["punteggio"]
    assert esito["candidati"][0]["dipendente_id"] == "dip-russo-c"
    # nessun pagamento scritto: la busta e' com'era
    paga = _run(hr.paghe_mensili.find_one({"dipendente_id": "dip-russo-c", "mese": 3}))
    assert paga["stato_pagamento"] == "in_attesa_pagamento" and not paga.get("bonifico_importo")


def test_nome_completo_univoco_e_il_solo_a_diventare_proposta(hr):
    _run(hr.paghe_mensili.insert_many([_busta("dip-vespa", 3, 950.0)]))

    esito = _calcola(hr, causale="VS.DISP. RIF. MB0B00923006 FAVORE Vespa Vincenzo - ADD.TOT")

    assert [c["dipendente_id"] for c in esito["candidati"]] == ["dip-vespa"]
    assert esito["candidati"][0]["prova"] == PROVA_NOME_COMPLETO
    assert esito["candidati"][0]["cedolino_id"] is None or isinstance(esito["candidati"][0]["cedolino_id"], str)
    assert esito["candidati"][0]["importo_residuo_cents"] == 95000
    assert esito["avviso_multi_dipendente"] is False
    assert esito["proposta"]["dipendente_id"] == "dip-vespa" and esito["proposta"]["tipo"] == "stipendio"


def test_codice_fiscale_batte_il_cognome_nel_ranking(hr):
    _run(hr.paghe_mensili.insert_many([_busta("dip-taiano", 3, 950.0)]))

    esito = _calcola(hr, causale="ADD.TOT - tnalgu85b02f839y stipendio marzo 2026")

    assert esito["candidati"][0]["prova"] == PROVA_CF
    assert esito["candidati"][0]["punteggio"] == 100


def test_massimo_dieci_candidati_in_ordine_di_prova(hr):
    for i in range(12):
        _run(hr.dipendenti.insert_one(_dip(f"dip-b{i}", f"Nome{i}", "Bianchi", f"BNCNMO80A01F8{i:02d}Z")))
    _run(hr.paghe_mensili.insert_many([_busta(f"dip-b{i}", 3, 950.0 if i < 11 else 100.0) for i in range(12)]))

    esito = _calcola(hr, causale="bonifico bianchi marzo")

    assert len(esito["candidati"]) == MAX_CANDIDATI
    punteggi = [c["punteggio"] for c in esito["candidati"]]
    assert punteggi == sorted(punteggi, reverse=True)
    # i pari-prova con importo uguale al residuo vengono prima di quelli senza
    assert esito["candidati"][0]["prova"] == PROVA_COGNOME_IMPORTO
    assert esito["avviso_multi_dipendente"] is True


def test_importo_da_solo_non_produce_candidati(hr):
    _run(hr.paghe_mensili.insert_many([_busta("dip-vespa", 3, 950.0), _busta("dip-taiano", 3, 950.0)]))

    # nessun nome, nessun periodo scritto: la data non basta e l'importo nemmeno
    assert _calcola(hr, causale="AGGIUNTIVA")["candidati"] == []
    assert _calcola(hr, causale="")["candidati"] == []


def test_importo_con_periodo_scritto_vale_solo_in_quel_periodo(hr):
    _run(hr.paghe_mensili.insert_many([
        _busta("dip-vespa", 3, 950.0), _busta("dip-taiano", 3, 950.0),
        _busta("dip-russo-c", 4, 950.0),  # stesso importo, altro periodo: fuori
    ]))

    esito = _calcola(hr, causale="stipendio marzo 2026")

    assert {c["dipendente_id"] for c in esito["candidati"]} == {"dip-vespa", "dip-taiano"}
    assert all(c["prova"] == PROVA_IMPORTO_PERIODO and (c["mese"], c["anno"]) == (3, 2026)
               for c in esito["candidati"])
    assert esito["avviso_motivo"] == AVVISO_STESSO_IMPORTO_PIU_BUSTE
    assert esito["proposta"] is None


def test_avviso_distinta_beneficiari_vari_e_nota_di_terzi(hr):
    vari = _calcola(hr, causale="VS.DISP. RIF. MB0B00000001/9043 FAVORE BENEFICIARI VARI DISTINTA - ADD.TOT")
    assert vari["avviso_multi_dipendente"] is True and vari["avviso_motivo"] == AVVISO_BENEFICIARI_VARI

    nota = _calcola(hr, causale="VS.DISP. RIF. MB0B00000002/9044 FAVORE BENEFICIARI VARI DISTINTA "
                                "- ADD.TOT - Vespa Vincenzo acc stipendio")
    assert nota["avviso_motivo"] == AVVISO_NOTA_DI_TERZI
    assert nota["proposta"] is None  # la nota puo' citare chi paga per piu' persone
    assert "dip-vespa" in [c["dipendente_id"] for c in nota["candidati"]]


# ── lettura della coda ───────────────────────────────────────────────────────

def test_lettura_coda_espone_candidati_avviso_rif_e_cro(hr):
    _run(hr.paghe_mensili.insert_one(_busta("dip-vespa", 3, 950.0)))
    _coda(hr, "q1", causale="VS.DISP. RIF. MB0B00923006/90679785 FAVORE Vespa Vincenzo - ADD.TOT",
          cro="5034903683956034480340003400IT")

    righe = _run(cand.arricchisci_coda(hr, _run(hr.bonifici_da_associare.find({}, {"_id": 0}).to_list(None))))

    r = righe[0]
    assert r["cro"] == "5034903683956034480340003400IT"
    assert r["rif_banca"] == "MB0B00923006"
    assert r["candidati"][0]["dipendente_id"] == "dip-vespa"
    assert r["avviso_multi_dipendente"] is False and r["proposta"]["dipendente_id"] == "dip-vespa"
    # ricalcolati e salvati sulla riga
    salvata = _run(hr.bonifici_da_associare.find_one({"id": "q1"}))
    assert salvata["candidati_versione"] == cand.VERSIONE_CANDIDATI and salvata["candidati"]


def test_bonifico_che_entra_in_coda_porta_i_candidati_e_il_cro(hr):
    _run(hr.paghe_mensili.insert_many([_busta("dip-russo-c", 3, 950.0), _busta("dip-russo-a", 3, 700.0)]))
    ctx = _run(ponte.carica_contesto_hr())

    _run(ponte._metti_in_coda(
        ctx, hash_pdf=None, data="2026-04-03", importo=950.0, causale="bonifico russo marzo",
        pdf_filename=None, pdf_data=None, fonte="x", riferimento={}, rif_banca="MB0B00000009", cro="CRO123"))

    riga = _run(hr.bonifici_da_associare.find_one({"rif_banca": "MB0B00000009"}, {"_id": 0}))
    assert riga["cro"] == "CRO123"
    assert len(riga["candidati"]) == 2 and riga["avviso_motivo"] == AVVISO_COGNOME_CONDIVISO
    assert riga["proposta"] is None


# ── conferma manuale ─────────────────────────────────────────────────────────

def _coppia(hr):
    """La stessa operazione vista da due documenti: ricevuta PDF ed estratto."""
    _run(hr.paghe_mensili.insert_many([_busta("dip-russo-c", 3, 950.0), _busta("dip-russo-a", 3, 950.0)]))
    _coda(hr, "q-pdf", causale="bonifico russo marzo", rif_banca="MB0B00923006",
          gestionale_transfer_id="tr-1", hash="a" * 64)
    _coda(hr, "q-banca", causale="VS.DISP. RIF. MB0B00923006/90679785 FAVORE russo - ADD.TOT",
          gestionale_movimento_id="mov-1")
    _run(hr.gest.estratto_conto_movimenti.insert_one({"id": "mov-1", "importo": -950.0, "tipo": "uscita"}))


def _leggi(hr):
    return _run(cand.arricchisci_coda(
        hr, _run(hr.bonifici_da_associare.find({"stato": "da_associare"}, {"_id": 0}).to_list(None))))


def test_conferma_segna_il_bonifico_e_lo_storico(hr):
    _coppia(hr)

    esito = _run(_associa("q-pdf", "dip-russo-c"))

    assert esito["ok"] is True
    riga = _run(hr.bonifici_da_associare.find_one({"id": "q-pdf"}))
    assert riga["stato"] == "associato" and riga["confermato_manuale"] is True
    assert riga["confermato_da"] == "Titolare" and riga["confermato_il"]
    assert riga["storico"][-1]["azione"] == "conferma_manuale"
    esito_paga = _run(hr.pagamenti_esiti.find_one({"key": "beneficiari-diversi:q-pdf"}))
    assert esito_paga["confermato_manuale"] is True and esito_paga["rif_banca"] == "MB0B00923006"
    bonifico = _run(hr.bonifici.find_one({"assegnato_da_bonifico_diversi": "q-pdf"}))
    assert bonifico["confermato_manuale"] is True
    # la riga in coda nata dalla ricevuta non tocca il movimento d'estratto dell'altra
    assert _run(hr.gest.estratto_conto_movimenti.find_one({"id": "mov-1"})).get("confermato_manuale") is None


def _associa(bonifico_id, dip_id, **extra):
    from app.hr.routers.dipendenti_cloud import associa_bonifico

    return associa_bonifico(bonifico_id, {"dipendente_id": dip_id, "tipo": "stipendio", "mese": 3,
                                          "anno": 2026, **extra}, utente=ADMIN)


def test_confermato_prima_l_altra_riga_non_ha_candidati_e_non_si_associa(hr):
    _coppia(hr)
    _run(_associa("q-pdf", "dip-russo-c"))

    righe = _leggi(hr)

    assert [r["id"] for r in righe] == ["q-banca"]
    assert righe[0]["gia_confermato_altrove"] is True
    assert righe[0]["candidati"] == [] and righe[0]["proposta"] is None
    with pytest.raises(HTTPException) as exc:
        _run(_associa("q-banca", "dip-russo-a"))
    assert exc.value.status_code == 409 and exc.value.detail["code"] == "GIA_ASSOCIATO"
    assert _run(hr.pagamenti_esiti.count_documents({})) == 1  # niente secondo pagamento


def test_confermato_dopo_i_candidati_gia_calcolati_spariscono_lo_stesso(hr):
    _coppia(hr)
    prima = {r["id"]: r for r in _leggi(hr)}
    assert prima["q-banca"]["candidati"], "prima della conferma ha i suoi candidati"

    _run(_associa("q-pdf", "dip-russo-a"))

    dopo = _leggi(hr)
    assert dopo[0]["id"] == "q-banca" and dopo[0]["candidati"] == []
    assert dopo[0]["gia_confermato_altrove"] is True
    # e il residuo dell'altro dipendente non e' quello di prima: la busta e' pagata
    paga = _run(hr.paghe_mensili.find_one({"dipendente_id": "dip-russo-a", "mese": 3}))
    assert paga["stato_pagamento"] == "pagato"


def test_ritira_conferma_spegne_il_segno_e_riapre_la_busta(hr):
    from app.hr.routers.dipendenti_cloud import ritira_conferma_bonifico

    _coppia(hr)
    _run(_associa("q-pdf", "dip-russo-c"))

    assert _run(ritira_conferma_bonifico("q-pdf", utente=ADMIN))["ok"] is True

    riga = _run(hr.bonifici_da_associare.find_one({"id": "q-pdf"}))
    assert riga["stato"] == "da_associare" and riga["confermato_manuale"] is False
    assert riga["confermato_da"] is None and riga["storico"][-1]["azione"] == "ritira_conferma"
    assert _run(hr.pagamenti_esiti.count_documents({})) == 0
    assert _run(hr.bonifici.count_documents({})) == 0
    paga = _run(hr.paghe_mensili.find_one({"dipendente_id": "dip-russo-c", "mese": 3}))
    assert paga["stato_pagamento"] == "in_attesa_pagamento" and paga["bonifico_importo"] == 0
    # con la conferma ritirata l'altra riga torna ad avere i candidati
    assert all(r["candidati"] for r in _leggi(hr))
    with pytest.raises(HTTPException) as exc:
        _run(ritira_conferma_bonifico("q-pdf", utente=ADMIN))
    assert exc.value.detail["code"] == "NON_CONFERMATO"


def test_conferma_segna_anche_il_movimento_del_gestionale(hr):
    _coppia(hr)

    _run(_associa("q-banca", "dip-russo-a"))

    mov = _run(hr.gest.estratto_conto_movimenti.find_one({"id": "mov-1"}))
    assert mov["confermato_manuale"] is True and mov["confermato_da"] == "Titolare"


# ── nessun motore automatico lo tocca ────────────────────────────────────────

def test_il_motore_stipendi_non_riassegna_un_bonifico_confermato(hr):
    from app.services.stipendi_bonifici import associa_bonifici_stipendi

    gest = hr.gest
    _run(gest.prima_nota_salari.insert_one({
        "id": "S1", "dipendente_id": "dip-vespa", "dipendente": "VESPA VINCENZO",
        "anno": 2026, "mese": 3, "importo_busta": 530.0, "riconciliato": False}))
    _run(gest.dipendenti.insert_one(dict(VESPA)))
    descr = "VOSTRA DISPOSIZIONE - VS.DISP. RIF. X FAVORE Vespa Vincenzo - ADD.TOT"
    _run(gest.estratto_conto_movimenti.insert_many([
        {"id": "M-conf", "data": "2026-04-03", "importo": 530.0, "tipo": "uscita",
         "descrizione_originale": descr, "confermato_manuale": True},
    ]))

    esito = _run(associa_bonifici_stipendi(gest))

    assert esito["bonifici_associati"] == 0
    mov = _run(gest.estratto_conto_movimenti.find_one({"id": "M-conf"}))
    assert not mov.get("riconciliato") and not mov.get("stipendio_id")
    assert not _run(gest.prima_nota_salari.find_one({"id": "S1"})).get("importo_bonifico")

    # la stessa riga senza la conferma invece si associa: il segno e' l'unica differenza
    _run(gest.estratto_conto_movimenti.update_one({"id": "M-conf"}, {"$set": {"confermato_manuale": False}}))
    assert _run(associa_bonifici_stipendi(gest))["bonifici_associati"] == 1


def test_il_ponte_hr_non_ridepone_un_movimento_confermato(hr):
    gest = hr.gest
    _run(hr.paghe_mensili.insert_one(_busta("dip-taiano", 3, 950.0)))
    mov = {"id": "mov-c", "data": "2026-04-03", "importo": -950.0, "tipo": "uscita",
           "descrizione": "VS.DISP. RIF. MB0B99998888/90111222 FAVORE TAIANO LUIGI - ADD.TOT",
           "confermato_manuale": True,
           "hr_deposito": {"esito": "in_coda", "coda_id": "q-c", "at": "x"}}
    _run(gest.estratto_conto_movimenti.insert_one(mov))
    _coda(hr, "q-c", gestionale_movimento_id="mov-c", importo=950.0)

    report = _run(ponte.deposita_pagamenti_in_hr(gest))

    assert report["estratto_conto_riesame"] == {}
    assert _run(hr.pagamenti_esiti.count_documents({})) == 0
    assert _run(hr.bonifici_da_associare.find_one({"id": "q-c"}))["stato"] == "da_associare"


def test_il_ponte_non_crea_una_seconda_riga_per_la_stessa_operazione_confermata(hr):
    _run(hr.bonifici_da_associare.insert_one({
        "id": "q-old", "stato": "associato", "rif_banca": "MB0B00923006", "confermato_manuale": True}))
    ctx = _run(ponte.carica_contesto_hr())

    marca = _run(ponte._deposita(
        ctx, key="ecm:x", testo="FAVORE BENEFICIARI VARI DISTINTA", data="2026-04-03", importo=950.0,
        hash_pdf=None, cro="MB0B00923006", causale="VS.DISP. RIF. MB0B00923006/90679785 FAVORE BENEFICIARI VARI",
        pdf_filename=None, pdf_data=None, origine="x", mese_dichiarato=None, anno_dichiarato=None,
        riferimento={}, dry_run=False))

    assert marca["esito"] == ponte.ESITO_DUPLICATO and marca["motivo"] == ponte.ESITO_CONFERMATO_MANUALE
    assert _run(hr.bonifici_da_associare.count_documents({"stato": "da_associare"})) == 0


# ── pagina «Distinte» ────────────────────────────────────────────────────────

def test_distinta_con_nota_che_nomina_una_persona_e_nota_di_terzi_senza_proposta(hr, monkeypatch):
    from app.database import Database as DatabaseGestionale
    from app.hr.routers.dipendenti_cloud import distinte_da_associare

    _run(hr.paghe_mensili.insert_one(_busta("dip-vespa", 4, 1234.0)))
    _run(hr.gest.estratto_conto_movimenti.insert_one({
        "id": "m3", "data": "2026-07-10", "importo": -1234.0,
        "descrizione": "VS.DISP. RIF. MB0B00000002/9044 FAVORE BENEFICIARI VARI DISTINTA - ADD.TOT - Vespa acc stipendio",
        "livello_evidenza": "provvisoria"}))
    _coda(hr, "q2", rif_banca="MB0B00000002", importo=1234.0, data="2026-07-10", causale="VS.DISP.",
          cro="CRO-Q2")
    monkeypatch.setattr(DatabaseGestionale, "get_db", classmethod(lambda cls: hr.gest))

    righe = _run(distinte_da_associare())

    assert len(righe) == 1
    r = righe[0]
    assert r["avviso_multi_dipendente"] is True and r["avviso_motivo"] == AVVISO_NOTA_DI_TERZI
    assert r["proposta"] is None and r["cro"] == "CRO-Q2" and r["rif_banca"] == "MB0B00000002"
    assert isinstance(r["candidati"], list)
