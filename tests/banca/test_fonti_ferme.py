"""18/09/2026: Prima Nota banca mostrava solo attese SumUp «da verificare» e
un saldo a -186.866,90. Nessuna logica rotta: dal 24/08 non arrivava piu'
nessun documento e il sistema non lo diceva. Qui il silenzio diventa avviso."""
import asyncio
from datetime import date

from app.services import fonti_ferme
from app.services.archivio_documenti_memoria import ClientArchivioMemoria


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _db(nome="fonti"):
    return ClientArchivioMemoria()[nome]


def _popola(db, estratto="2026-08-24", corrispettivi="2026-08-24", pos="2026-07-31"):
    async def scenario():
        if estratto:
            await db["estratto_conto_movimenti"].insert_one(
                {"id": "ec-1", "data": estratto, "importo": 10.0})
        if corrispettivi:
            await db["corrispettivi"].insert_one({"id": "co-1", "data": corrispettivi})
        if pos:
            await db["chiusure_pos_manuali"].insert_one(
                {"id": "pt-1", "data": pos, "gestore": "numia", "importo": 100.0})
    _run(scenario())


def test_avvisa_su_ogni_fonte_ferma_con_giorni_e_ultima_data():
    db = _db("ferme")
    _popola(db)
    esito = _run(fonti_ferme.controlla_fonti_ferme(db, oggi=date(2026, 9, 18)))

    assert esito["controllate"] == 3
    ferme = {r["fonte"]: r for r in esito["ferme"]}
    assert set(ferme) == {"estratto_conto", "corrispettivi", "pos_numia"}
    assert ferme["estratto_conto"]["giorni"] == 25
    assert ferme["estratto_conto"]["ultima_data"] == "2026-08-24"
    assert ferme["pos_numia"]["giorni"] == 49

    alerts = _run(db["alerts"].find({"codice": "FONTE_CONTABILE_FERMA"}).to_list(10))
    assert len(alerts) == 3
    estratto = next(a for a in alerts if a["entita_id"] == "estratto_conto")
    assert estratto["stato"] == "aperto"
    assert "25 giorni" in estratto["dettaglio"] and "24/08/2026" in estratto["dettaglio"]
    # la conseguenza e' scritta nell'avviso: dice perche' la pagina e' vuota
    assert "versamento" in estratto["dettaglio"]


def test_non_avvisa_finche_il_ritardo_e_nella_norma_e_non_duplica():
    db = _db("recenti")
    _popola(db, estratto="2026-09-15", corrispettivi="2026-09-16", pos="2026-09-14")
    primo = _run(fonti_ferme.controlla_fonti_ferme(db, oggi=date(2026, 9, 18)))
    assert primo["ferme"] == []
    assert _run(db["alerts"].count_documents({})) == 0

    # una fonte si ferma: l'avviso nasce una volta sola anche a piu' giri
    db2 = _db("doppioni")
    _popola(db2)
    _run(fonti_ferme.controlla_fonti_ferme(db2, oggi=date(2026, 9, 18)))
    _run(fonti_ferme.controlla_fonti_ferme(db2, oggi=date(2026, 9, 18)))
    assert _run(db2["alerts"].count_documents(
        {"codice": "FONTE_CONTABILE_FERMA", "entita_id": "estratto_conto"})) == 1


def test_quando_la_fonte_riparte_l_avviso_si_chiude():
    db = _db("ripresa")
    _popola(db)
    _run(fonti_ferme.controlla_fonti_ferme(db, oggi=date(2026, 9, 18)))

    _run(db["estratto_conto_movimenti"].insert_one(
        {"id": "ec-2", "data": "2026-09-17", "importo": 5.0}))
    esito = _run(fonti_ferme.controlla_fonti_ferme(db, oggi=date(2026, 9, 18)))

    assert "estratto_conto" in esito["riprese"]
    assert {r["fonte"] for r in esito["ferme"]} == {"corrispettivi", "pos_numia"}
    alert = _run(db["alerts"].find_one(
        {"codice": "FONTE_CONTABILE_FERMA", "entita_id": "estratto_conto"}))
    assert alert["stato"] == "risolto" and alert["resolved_by"] == "fonte_ripartita"


def test_fonte_vuota_non_diventa_un_avviso_inventato():
    """Una collezione vuota non prova che la fonte si sia fermata: potrebbe
    non essere mai partita. Si dichiara, non si allarma."""
    db = _db("vuota")
    _popola(db, estratto=None, corrispettivi="2026-09-17", pos=None)
    esito = _run(fonti_ferme.controlla_fonti_ferme(db, oggi=date(2026, 9, 18)))

    assert set(esito["vuote"]) == {"estratto_conto", "pos_numia"}
    assert esito["ferme"] == []
    assert _run(db["alerts"].count_documents({})) == 0


def test_stato_fonti_espone_giorni_e_conseguenza_per_la_pagina():
    db = _db("stato")
    _popola(db)
    righe = {r["fonte"]: r for r in _run(fonti_ferme.stato_fonti(db, oggi=date(2026, 9, 18)))}

    assert righe["estratto_conto"]["ferma"] is True
    assert righe["estratto_conto"]["giorni_fermi"] == 25
    assert righe["estratto_conto"]["etichetta"] == "Estratto conto bancario"
    assert righe["corrispettivi"]["conseguenza"]


# --- Copertura categoria banca (19/09/2026) --------------------------------
#
# Diverso dal fermo di una fonte: l'estratto conto puo' arrivare puntuale e i
# suoi movimenti restare comunque senza categoria (nessuna causale nota), e
# senza categoria un movimento non entra mai in Prima Nota Banca. Verificato
# il 18/09/2026: 1.764 dei 1.920 movimenti bancari 2026 (92%) senza categoria.

def test_copertura_sopra_soglia_quando_la_maggioranza_e_senza_categoria():
    db = _db("copertura_alta")

    async def scenario():
        for i in range(18):
            await db["estratto_conto_movimenti"].insert_one(
                {"id": f"senza-{i}", "data": "2026-03-01", "importo": 10.0, "categoria": ""})
        for i in range(2):
            await db["estratto_conto_movimenti"].insert_one(
                {"id": f"con-{i}", "data": "2026-03-01", "importo": 10.0, "categoria": "F24"})
        return await fonti_ferme.copertura_categoria_banca(db, anno=2026)

    esito = _run(scenario())
    assert esito["totale"] == 20
    assert esito["senza_categoria"] == 18
    assert esito["percentuale"] == 90.0
    assert esito["sopra_soglia"] is True


def test_copertura_sotto_soglia_non_avvisa():
    db = _db("copertura_bassa")

    async def scenario():
        for i in range(19):
            await db["estratto_conto_movimenti"].insert_one(
                {"id": f"con-{i}", "data": "2026-03-01", "importo": 10.0, "categoria": "F24"})
        await db["estratto_conto_movimenti"].insert_one(
            {"id": "senza-1", "data": "2026-03-01", "importo": 10.0, "categoria": ""})
        return await fonti_ferme.copertura_categoria_banca(db, anno=2026)

    esito = _run(scenario())
    assert esito["percentuale"] == 5.0
    assert esito["sopra_soglia"] is False


def test_copertura_filtra_per_anno_e_ignora_altri_anni():
    db = _db("copertura_anni")

    async def scenario():
        await db["estratto_conto_movimenti"].insert_one(
            {"id": "2025", "data": "2025-12-31", "importo": 10.0, "categoria": ""})
        await db["estratto_conto_movimenti"].insert_one(
            {"id": "2026", "data": "2026-01-02", "importo": 10.0, "categoria": "F24"})
        return await fonti_ferme.copertura_categoria_banca(db, anno=2026)

    esito = _run(scenario())
    assert esito["totale"] == 1
    assert esito["senza_categoria"] == 0
    assert esito["anno"] == 2026


def test_copertura_senza_movimenti_non_avvisa():
    db = _db("copertura_vuota")
    esito = _run(fonti_ferme.copertura_categoria_banca(db, anno=2026))
    assert esito["totale"] == 0
    assert esito["sopra_soglia"] is False


def test_corrispettivi_fermi_da_due_giorni_d_apertura_avvisano_su_telegram(monkeypatch):
    """28/09/2026: il PC del negozio si e' fermato e nessuno se n'e' accorto.
    Il bar apre tutti i giorni: dopo due giorni d'apertura senza chiusura RT
    l'avviso nasce e arriva su Telegram, una volta sola."""
    inviati = []

    async def finto_invio(testo, **_kw):
        inviati.append(testo)
        return {"success": True}

    monkeypatch.setattr("app.services.telegram_notifications.send_notification", finto_invio)
    db = _db("corr-telegram")
    _popola(db, estratto="2026-09-20", corrispettivi="2026-09-21", pos="2026-09-20")

    # 21 -> 23: due giorni, ancora nella norma.
    assert _run(fonti_ferme.controlla_fonti_ferme(db, oggi=date(2026, 9, 23)))["ferme"] == []
    # 21 -> 24: tre giorni, avviso e un solo messaggio anche al giro dopo.
    esito = _run(fonti_ferme.controlla_fonti_ferme(db, oggi=date(2026, 9, 24)))
    assert [r["fonte"] for r in esito["ferme"]] == ["corrispettivi"]
    _run(fonti_ferme.controlla_fonti_ferme(db, oggi=date(2026, 9, 24)))
    assert len(inviati) == 1 and "21/09/2026" in inviati[0]


def test_i_giorni_di_chiusura_non_contano_come_corrispettivi_mancanti(monkeypatch):
    async def finto_invio(testo, **_kw):
        return {"success": True}

    monkeypatch.setattr("app.services.telegram_notifications.send_notification", finto_invio)
    db = _db("corr-ferie")
    _popola(db, estratto="2026-08-20", corrispettivi="2026-08-14", pos="2026-08-20")
    _run(db["chiusure_attivita"].insert_one(
        {"id": "ferie", "data_inizio": "2026-08-15", "data_fine": "2026-08-23"}))
    # Ferie 15-23/08: al 25/08 manca solo il 24 e oggi, nessun avviso.
    esito = _run(fonti_ferme.controlla_fonti_ferme(db, oggi=date(2026, 8, 25)))
    assert "corrispettivi" not in {r["fonte"] for r in esito["ferme"]}
    riga = next(r for r in _run(fonti_ferme.stato_fonti(db, oggi=date(2026, 8, 25)))
                if r["fonte"] == "corrispettivi")
    assert riga["giorni_fermi"] == 2 and riga["ferma"] is False


def _accredito_numia(giorno_vendita, accredito, importo=50.0, n=1):
    gg, mm, aa = giorno_vendita[8:10], giorno_vendita[5:7], giorno_vendita[2:4]
    return {"id": f"ec-numia-{giorno_vendita}-{n}", "data": accredito, "tipo": "entrata",
            "importo": importo,
            "descrizione": f"INC.POS CARTE CREDIT - NUMIA-INTER DEL {gg}/{mm}/{aa} PDV 1/00011 NEGOZIO"}


def test_numia_dismesso_non_e_una_fonte_ferma():
    """Titolare, 28/09/2026: Numia spento dopo il 04/09. Se l'ultima vendita
    Numia accreditata ha la sua chiusura, il terminale spento non avvisa."""
    db = _db("numia-dismesso")
    _popola(db, estratto="2026-09-27", corrispettivi="2026-09-27", pos="2026-09-04")
    _run(db["estratto_conto_movimenti"].insert_one(_accredito_numia("2026-09-04", "2026-09-07")))

    esito = _run(fonti_ferme.controlla_fonti_ferme(db, oggi=date(2026, 9, 28)))

    assert esito["ferme"] == []


def test_accrediti_numia_senza_chiusura_restano_un_avviso():
    db = _db("numia-buco")
    _popola(db, estratto="2026-09-27", corrispettivi="2026-09-27", pos="2026-07-31")
    _run(db["estratto_conto_movimenti"].insert_one(_accredito_numia("2026-09-04", "2026-09-07")))
    # Una chiusura SumUp non copre Numia.
    _run(db["chiusure_pos_manuali"].insert_one(
        {"id": "su-1", "data": "2026-09-27", "gestore": "sumup", "importo": 10.0}))

    esito = _run(fonti_ferme.controlla_fonti_ferme(db, oggi=date(2026, 9, 28)))

    ferme = {r["fonte"]: r for r in esito["ferme"]}
    assert set(ferme) == {"pos_numia"}
    assert ferme["pos_numia"]["giorni"] == 35  # dal 31/07 all'ultima vendita del 04/09
