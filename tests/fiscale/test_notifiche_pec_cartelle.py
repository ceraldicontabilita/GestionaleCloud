"""La data di notifica di una cartella arriva dalla PEC che la notifica, in qualunque ordine."""
import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.services import notifiche_pec_cartelle as pec
from app.services.cartelle_pagamento import COLL

OGGETTO = ("POSTA CERTIFICATA: Notifica cartella di pagamento n. 07120260127882548002 "
           "Codice Fiscale CRLNNT75M55F352C")
CORPO = """Messaggio di posta certificata

Il giorno 24/09/2026 alle ore 11:06:23 (+0200) il messaggio
"Notifica cartella di pagamento n. 07120260127882548002 Codice Fiscale CRLNNT75M55F352C" è stato inviato da "notifica.acc.campania@pec.agenziariscossione.gov.it"
ed indirizzato a:
ceraldiantonietta@legalmail.it
"""


def run(coro):
    return asyncio.run(coro)


def _db(cartella=None):
    db = AsyncMongoMockClient()["cartelle"]
    if cartella:
        run(db[COLL].insert_one(dict(cartella)))
    return db


def _cartella(**extra):
    return {"id": "cartella:07120260127882548002", "numero_cartella": "071 2026 01278825 48/002",
            "data_notifica": None, "scadenza": None, **extra}


def test_si_legge_il_numero_dall_oggetto_e_la_data_dal_corpo():
    assert pec.e_notifica_cartella(OGGETTO) and not pec.e_notifica_cartella("Ricevuta di pagamento IUV:800")
    n = pec.leggi_notifica(OGGETTO, CORPO)
    assert n == {"numero": "07120260127882548002", "data_notifica": "2026-09-24", "ora": "11:06:23",
                 "fuso": "+0200", "mittente_originale": "notifica.acc.campania@pec.agenziariscossione.gov.it"}
    # senza uno dei due non si indovina niente
    assert pec.leggi_notifica(OGGETTO, "nessuna data qui") is None
    assert pec.leggi_notifica("Notifica cartella", CORPO) is None
    assert pec.leggi_notifica(OGGETTO, CORPO.replace("24/09/2026", "31/02/2026")) is None


def test_la_cartella_gia_in_archivio_riceve_la_data_e_la_scadenza_a_60_giorni():
    db = _db(_cartella())
    esito = run(pec.registra_notifica_email(db, OGGETTO, CORPO, messaggio_id="<m1>"))
    assert esito["stato"] == "applicata" and esito["nuova"] is True
    c = run(db[COLL].find_one({"id": "cartella:07120260127882548002"}))
    assert c["data_notifica"] == "2026-09-24" and c["scadenza"] == "2026-11-23"   # 24/09 + 60 gg (lunedi')
    assert c["data_notifica_fonte"] == "pec" and c["notifica_pec"]["messaggio"] == "<m1>"
    # la stessa PEC letta un'altra volta (storico) non cambia niente
    assert run(pec.registra_notifica_email(db, OGGETTO, CORPO, messaggio_id="<m1>"))["nuova"] is False


def test_la_pec_arrivata_prima_della_cartella_si_applica_alla_sua_registrazione():
    db = _db()
    assert run(pec.registra_notifica_email(db, OGGETTO, CORPO))["stato"] == "in_attesa_della_cartella"
    run(db[COLL].insert_one(_cartella()))
    esito = run(pec.applica_notifiche_in_attesa(db, "cartella:07120260127882548002"))
    assert esito["stato"] == "applicata"
    assert run(db[COLL].find_one({"id": "cartella:07120260127882548002"}))["data_notifica"] == "2026-09-24"


def test_la_data_del_titolare_non_si_sovrascrive_e_la_differenza_si_segnala():
    db = _db(_cartella(data_notifica="2026-09-26", scadenza="2026-11-25"))
    esito = run(pec.registra_notifica_email(db, OGGETTO, CORPO))
    assert esito["stato"] == "data_diversa_da_decidere" and esito["data_presente"] == "2026-09-26"
    c = run(db[COLL].find_one({"id": "cartella:07120260127882548002"}))
    assert c["data_notifica"] == "2026-09-26" and c["notifica_pec_diversa"] is True
    assert c["notifica_pec"]["data"] == "2026-09-24"        # la prova resta, la decide lui


def test_un_altro_numero_non_tocca_la_cartella():
    db = _db(_cartella())
    run(pec.registra_notifica_email(db, OGGETTO.replace("07120260127882548002", "07120260117439961000"),
                                    CORPO.replace("07120260127882548002", "07120260117439961000")))
    assert run(db[COLL].find_one({"id": "cartella:07120260127882548002"}))["data_notifica"] is None
