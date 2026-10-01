"""Collaudo funzionale 2: pago una fattura (bonifico, cassa, assegno, acconti, importo diverso, ritenuta).

Parte dall'azione dell'utente e legge il risultato sui dati: la fattura e' pagata su tutti i campi di
stato, il pagamento sta in Prima Nota (una riga che pesa, non due), le prove restano distinte
(fattura, bonifico, movimento d'estratto, riga di Prima Nota) e il secondo giro non cambia niente.
Motori reali; l'unico finto e' il lettore del PDF dell'estratto, che ha i suoi test per coordinate.
"""
from decimal import Decimal

import pytest

from tests.fatture._scenari_comuni import (
    FilePdf, app_assegni, app_prima_nota, archivio_scenari, crea_fornitore, cent, e_pagata_su_ogni_campo,
    esegui, fattura, importa, importa_estratto, ingresso, parser_pdf_con, richiesta, righe_che_contano,
    transazione_pdf, tutti, xml_fattura,
)

__all__ = ["archivio_scenari", "ingresso"]

CAUSALE_BONIFICO = "VS.DISP. RIF. MBVT12345678/001 FAVORE FORNITORE TEST SRL"


def _d(valore) -> Decimal:
    return Decimal(str(valore))


async def _saldo_banca(app) -> Decimal:
    risposta = await richiesta(app, "GET", "/api/prima-nota/banca?anno=2026&limit=100")
    assert risposta.status_code == 200, risposta.text
    return _d(risposta.json()["saldo"])


async def _estratto_ufficiale(monkeypatch, movimenti):
    """Un PDF dell'estratto con questi movimenti: [(data, causale, importo)]."""
    parser_pdf_con(monkeypatch, [transazione_pdf(d, c, i) for d, c, i in movimenti])
    return await importa_estratto(FilePdf())


def _testo_bonifico(causale: str) -> str:
    return (
        "Banco BPM\nRicevuta di bonifico\nData esecuzione: 15/09/2026\nOrdinante: CERALDI GROUP SRL\n"
        "Beneficiario: FORNITORE TEST SRL\nIBAN beneficiario: IT60X0542811101000000123456\n"
        f"Importo: EUR 122,00\nCausale: {causale}\nCRO: 05034123456789012345\nRif. interno: MBVT12345678\n"
    )


# ── 2a. bonifico + estratto ufficiale ────────────────────────────────────────

@pytest.mark.parametrize("pdf_prima", [True, False], ids=["pdf_poi_estratto", "estratto_poi_pdf"])
def test_bonifico_e_movimento_d_estratto_pagano_la_fattura_una_volta(archivio_scenari, monkeypatch, pdf_prima):
    db = archivio_scenari
    from app.services import bonifici_pdf_ingest as ingest

    monkeypatch.setattr(ingest, "read_pdf_bytes", lambda _c: _testo_bonifico("PAGAMENTO FATTURA 123"))

    async def scenario():
        await crea_fornitore(db, metodo="bonifico")
        esito = await importa(db, xml_fattura(), "drive")
        fid = esito["id"]
        app = app_prima_nota()

        async def pdf_bonifico():
            return await ingest.importa_pdf_bonifico(db, b"%PDF-1.4 bonifico", "bonifico.pdf")

        prima = {}
        if pdf_prima:
            prima["pdf"] = await pdf_bonifico()
            # disposizione senza prova bancaria: collega il documento, NON paga
            prima["fattura"] = await fattura(db, fid)
        await _estratto_ufficiale(monkeypatch, [("2026-09-15", CAUSALE_BONIFICO, -122.0)])
        if not pdf_prima:
            prima["pdf"] = await pdf_bonifico()
        dopo = await fattura(db, fid)
        saldo = await _saldo_banca(app)
        giro2 = await _estratto_ufficiale(monkeypatch, [("2026-09-15", CAUSALE_BONIFICO, -122.0)])
        return {
            "fid": fid, "prima": prima, "dopo": dopo, "saldo": saldo, "giro2": giro2,
            "rige": await righe_che_contano(db, "prima_nota_banca", fid),
            "cassa": await tutti(db, "prima_nota_cassa"),
            "ec": await tutti(db, "estratto_conto_movimenti"),
            "partite": await tutti(db, "partite_aperte"),
            "rel": await tutti(db, "entity_relations"),
            "trasferimenti": await tutti(db, "bonifici_transfers"),
            "fattura_finale": await fattura(db, fid),
        }

    r = esegui(scenario())

    if pdf_prima:
        from app.services.stato_pagamento_fattura import e_pagata

        assert r["prima"]["pdf"]["associato"] is True and r["prima"]["pdf"]["fattura_ids"] == [r["fid"]]
        assert not e_pagata(r["prima"]["fattura"]), "il solo bonifico PDF non e' una prova di pagamento"

    # fattura pagata e coerente su ogni campo di stato
    assert e_pagata_su_ogni_campo(r["dopo"]), r["dopo"]
    assert r["dopo"]["data_pagamento"] == "2026-09-15"
    # una sola riga di Prima Nota Banca che pesa, legata al movimento d'estratto
    assert len(r["rige"]) == 1
    riga = r["rige"][0]
    assert _d(riga["importo"]) == Decimal("122.00") and riga["riconciliato"] is True
    assert len(r["ec"]) == 1 and riga["estratto_conto_id"] == r["ec"][0]["id"]
    assert r["ec"][0]["riconciliato"] is True and r["ec"][0]["evidenza_bancaria_ufficiale"] is True
    assert r["cassa"] == []
    # il saldo bancario conta il pagamento una volta
    assert r["saldo"] == Decimal("-122.00")
    # la partita e' chiusa
    assert len(r["partite"]) == 1 and r["partite"][0]["stato"] == "chiusa" and _d(r["partite"][0]["residuo"]) == 0
    # prove distinte, collegate da relazioni: movimento -> fattura, bonifico -> fattura
    tipi = {(x["source"]["type"], x["relation_type"], x["target"]["type"]) for x in r["rel"]}
    assert ("bank_movement", "allocates_invoice_payment", "invoice") in tipi
    assert ("bonifico_pdf", "documents_invoice_payment", "invoice") in tipi
    assert len(r["trasferimenti"]) == 1
    # secondo giro: niente di nuovo
    assert r["giro2"]["stats"]["nuovi"] == 0
    assert r["fattura_finale"]["importo_pagato"] == r["dopo"]["importo_pagato"] == 122.0


@pytest.mark.xfail(strict=True, reason=(
    "BUG NON CORRETTO (area bonifici, altro agente): il bonifico PDF gia' legato alla fattura per il numero in "
    "causale e' escluso da `bonifici_da_estratto` (`_gia_decisa`), quindi non viene mai legato al suo "
    "movimento d'estratto (stesso riferimento MBVT… e stesso importo): resta `stato_riconciliazione=documentato`, "
    "senza `movimento_estratto_conto_id` e senza relazione `confirmed_by_bank_movement`. "
    "`STATO_BONIFICO_RICONCILIATO` non ha scrittori."))
def test_il_bonifico_pdf_si_lega_al_suo_movimento_e_diventa_riconciliato(archivio_scenari, monkeypatch):
    db = archivio_scenari
    from app.services import bonifici_pdf_ingest as ingest

    monkeypatch.setattr(ingest, "read_pdf_bytes", lambda _c: _testo_bonifico("PAGAMENTO FATTURA 123"))

    async def scenario():
        await crea_fornitore(db, metodo="bonifico")
        await importa(db, xml_fattura(), "drive")
        await ingest.importa_pdf_bonifico(db, b"%PDF-1.4 bonifico", "bonifico.pdf")
        await _estratto_ufficiale(monkeypatch, [("2026-09-15", CAUSALE_BONIFICO, -122.0)])
        from app.services.bonifici_da_estratto import abbina_bonifici_via_estratto

        await abbina_bonifici_via_estratto(db)
        return (await tutti(db, "bonifici_transfers"))[0], (await tutti(db, "estratto_conto_movimenti"))[0], \
            await tutti(db, "entity_relations")

    t, m, rel = esegui(scenario())
    assert t["movimento_estratto_conto_id"] == m["id"]
    assert t["stato_riconciliazione"] == "riconciliato"
    assert ("bonifico_pdf", "confirmed_by_bank_movement", "bank_movement") in {
        (x["source"]["type"], x["relation_type"], x["target"]["type"]) for x in rel}


@pytest.mark.parametrize("importo,nome", [
    (121.99, "FORNITORE TEST SRL"),     # un centesimo in meno
    (122.01, "FORNITORE TEST SRL"),     # un centesimo in piu'
    (122.0, "ALTRO FORNITORE SRL"),     # importo giusto, identita' diversa
])
def test_importo_o_identita_diversi_non_collegano_la_fattura(archivio_scenari, monkeypatch, importo, nome):
    db = archivio_scenari

    async def scenario():
        await crea_fornitore(db, metodo="bonifico")
        esito = await importa(db, xml_fattura(), "drive")
        await _estratto_ufficiale(monkeypatch, [
            ("2026-09-15", f"VS.DISP. RIF. MBVT12345678/001 FAVORE {nome}", -importo)])
        return await fattura(db, esito["id"]), await tutti(db, "estratto_conto_movimenti"), \
            await tutti(db, "partite_aperte"), await righe_che_contano(db, "prima_nota_banca", esito["id"])

    inv, ec, partite, righe = esegui(scenario())
    from app.services.stato_pagamento_fattura import e_pagata

    assert not e_pagata(inv)
    assert ec[0].get("riconciliato") is not True and not ec[0].get("fattura_id")
    assert partite[0]["stato"] == "aperta" and _d(partite[0]["residuo"]) == Decimal("122.00")
    assert righe == []


def test_due_fatture_uguali_dello_stesso_fornitore_rendono_ambiguo_l_abbinamento(archivio_scenari, monkeypatch):
    db = archivio_scenari

    async def scenario():
        await crea_fornitore(db, metodo="bonifico")
        a = await importa(db, xml_fattura(numero="1"), "drive")
        b = await importa(db, xml_fattura(numero="2", data="2026-09-11"), "drive")
        await _estratto_ufficiale(monkeypatch, [("2026-09-15", CAUSALE_BONIFICO, -122.0)])
        return await fattura(db, a["id"]), await fattura(db, b["id"]), await tutti(db, "estratto_conto_movimenti")

    a, b, ec = esegui(scenario())
    from app.services.stato_pagamento_fattura import e_pagata

    assert not e_pagata(a) and not e_pagata(b), "nei casi ambigui non si applica il collegamento"
    assert ec[0].get("riconciliato") is not True


# ── 2d. acconti ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("importi,date,pagata", [
    ([60.0, 62.0], ["2026-09-15", "2026-09-17"], True),
    ([30.0, 30.0, 30.0, 32.0], ["2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18"], True),
    ([0.10, 0.20, 121.70], ["2026-09-15", "2026-09-16", "2026-09-17"], True),   # i float sommano 0.1 + 0.2 != 0.3
    ([60.0, 61.99], ["2026-09-15", "2026-09-17"], False),                      # un centesimo in meno
    ([60.0, 62.01], ["2026-09-15", "2026-09-17"], False),                      # un centesimo in piu'
    ([60.0, 62.0], ["2026-09-15", "2027-01-20"], False),                       # il secondo oltre i 90 giorni
])
def test_gli_acconti_pagano_la_fattura_solo_se_la_somma_torna_al_centesimo(archivio_scenari, monkeypatch,
                                                                        importi, date, pagata):
    db = archivio_scenari

    async def scenario():
        await crea_fornitore(db, metodo="bonifico")
        esito = await importa(db, xml_fattura(), "drive")
        movimenti = [(d, f"VS.DISP. RIF. MBVT1234567{i}/001 FAVORE FORNITORE TEST SRL", -x)
                     for i, (x, d) in enumerate(zip(importi, date))]
        await _estratto_ufficiale(monkeypatch, movimenti)
        primo = {"fattura": await fattura(db, esito["id"]), "ec": await tutti(db, "estratto_conto_movimenti"),
                 "partite": await tutti(db, "partite_aperte"),
                 "righe": await righe_che_contano(db, "prima_nota_banca", esito["id"]),
                 "saldo": await _saldo_banca(app_prima_nota())}
        # secondo giro: stessi movimenti, nessun effetto nuovo
        await _estratto_ufficiale(monkeypatch, movimenti)
        primo["righe2"] = await righe_che_contano(db, "prima_nota_banca", esito["id"])
        return primo

    r = esegui(scenario())
    from app.services.stato_pagamento_fattura import e_pagata

    if pagata:
        assert e_pagata_su_ogni_campo(r["fattura"])
        assert all(m["riconciliato"] is True for m in r["ec"])
        assert sum(cent(x["importo"]) for x in r["righe"]) == cent("122.00")
        assert r["saldo"] == Decimal("-122.00")
        assert r["partite"][0]["stato"] == "chiusa"
        assert len(r["righe2"]) == len(r["righe"]), "il secondo giro ha aggiunto righe"
    else:
        assert not e_pagata(r["fattura"])
        assert not any(m.get("riconciliato") for m in r["ec"])
        assert r["righe"] == [] and r["saldo"] == Decimal("0.00")
        assert r["partite"][0]["stato"] == "aperta" and _d(r["partite"][0]["residuo"]) == Decimal("122.00")


# ── 2b. cassa ────────────────────────────────────────────────────────────────

def test_cassa_import_non_paga_la_conferma_scrive_una_sola_riga_di_cassa(archivio_scenari, ingresso):
    db = archivio_scenari

    async def scenario():
        await crea_fornitore(db, metodo="contanti", iban=None)
        esito = await importa(db, xml_fattura(), ingresso)
        fid = esito["id"]
        app = app_prima_nota()
        prima = {"fattura": await fattura(db, fid), "cassa": await tutti(db, "prima_nota_cassa"),
                 "banca": await tutti(db, "prima_nota_banca")}
        ok = await richiesta(app, "POST", "/api/prima-nota/provvisori/conferma",
                             json={"fattura_id": fid, "metodo": "cassa", "data_pagamento": "2026-09-12"})
        doppia = await richiesta(app, "POST", "/api/prima-nota/provvisori/conferma",
                                 json={"fattura_id": fid, "metodo": "cassa", "data_pagamento": "2026-09-12"})
        elenco = await richiesta(app, "GET", "/api/prima-nota/cassa?anno=2026&limit=100")
        return {"prima": prima, "ok": ok, "doppia": doppia, "elenco": elenco.json(), "dopo": await fattura(db, fid),
                "cassa": await tutti(db, "prima_nota_cassa"), "banca": await tutti(db, "prima_nota_banca"),
                "partite": await tutti(db, "partite_aperte"), "fid": fid}

    r = esegui(scenario())
    from app.services.stato_pagamento_fattura import e_pagata

    # all'import niente cassa e niente pagamento: il fatto autorevole e' la conferma del titolare
    assert not e_pagata(r["prima"]["fattura"]) and r["prima"]["cassa"] == [] and r["prima"]["banca"] == []
    assert r["ok"].status_code == 200, r["ok"].text
    assert e_pagata_su_ogni_campo(r["dopo"]) and r["dopo"]["data_pagamento"] == "2026-09-12"
    assert r["dopo"]["prima_nota_tipo"] == "cassa" and r["dopo"]["metodo_pagamento_effettivo"] == "cassa"
    # una riga in Cassa, importo al centesimo, conto di tesoreria della cassa; niente in Banca
    assert len(r["cassa"]) == 1 and r["banca"] == []
    riga = r["cassa"][0]
    assert _d(riga["importo"]) == Decimal("122.00") and riga["fattura_id"] == r["fid"]
    assert riga["conto_contabile"] == "19.03.03" and riga["conto_contropartita"] == "33.03.01"
    assert _d(r["elenco"]["saldo"]) == Decimal("-122.00")
    # la seconda conferma e' rifiutata e non scrive un secondo pagamento
    assert r["doppia"].status_code == 409
    assert len(r["cassa"]) == 1
    assert r["partite"][0]["stato"] == "chiusa"


def test_cassa_su_fornitore_a_banca_senza_approvazione_e_rifiutata(archivio_scenari):
    """Il metodo non si cambia di nascosto: `cassa` su un fornitore a bonifico serve l'approvazione esplicita."""
    db = archivio_scenari

    async def scenario():
        await crea_fornitore(db, metodo="bonifico")
        esito = await importa(db, xml_fattura(), "drive")
        app = app_prima_nota()
        senza = await richiesta(app, "POST", "/api/prima-nota/provvisori/conferma",
                                json={"fattura_id": esito["id"], "metodo": "cassa"})
        return senza, await tutti(db, "prima_nota_cassa")

    risposta, cassa = esegui(scenario())
    assert risposta.status_code == 409 and cassa == []


# ── 2c. assegno ──────────────────────────────────────────────────────────────

async def _assegno_per_fattura(db, app, fid, importo=122.0):
    genera = await richiesta(app, "POST", "/api/assegni/genera", json={"numero_primo": "0208771000", "quantita": 2})
    assert genera.status_code == 200, genera.text
    assegni = await tutti(db, "assegni")
    assegno = next(a for a in assegni if a["numero"] == "0208771000")
    compila = await richiesta(app, "PUT", f"/api/assegni/{assegno['id']}", json={
        "importo": importo, "beneficiario": "FORNITORE TEST SRL", "fornitore_piva": "01234567890"})
    assert compila.status_code == 200, compila.text
    collega = await richiesta(app, "PUT", f"/api/assegni/{assegno['id']}/fatture-collegate",
                              json={"fatture": [{"fattura_id": fid, "quota": importo}]})
    return assegno, collega


@pytest.mark.parametrize("id_numerico", [False, True], ids=["id_testo", "id_numerico"])
def test_assegno_dichiara_subito_poi_l_estratto_con_numero_e_importo_lo_riscontra(archivio_scenari, monkeypatch,
                                                                              id_numerico):
    db = archivio_scenari

    async def scenario():
        await crea_fornitore(db, metodo="assegno")
        esito = await importa(db, xml_fattura(), "drive")
        fid = esito["id"]
        if id_numerico:
            # su meta' delle righe di `invoices` l'id e' un numero: la UI lo rimanda cosi' com'e'
            for coll in ("invoices", "prima_nota_banca", "partite_aperte", "movimenti_contabili"):
                campo = "documento_id" if coll == "partite_aperte" else "id" if coll == "invoices" else "fattura_id"
                await db[coll].update_many({campo: fid}, {"$set": {campo: 850878}})
            fid = 850878
        app = app_assegni()
        assegno, collega = await _assegno_per_fattura(db, app, fid)
        assert collega.status_code == 200, collega.text
        dichiarata = await fattura(db, fid)
        # addebito di un ALTRO numero con lo stesso importo: non e' questo assegno
        await _estratto_ufficiale(monkeypatch, [
            ("2026-09-17", "PRELIEVO ASSEGNO - DM 05387 CRA: 26050700167309 NUM: 0208771001", -122.0)])
        altro_numero = await fattura(db, fid)
        ass_altro = await tutti(db, "assegni", {"numero": "0208771000"})
        await _estratto_ufficiale(monkeypatch, [
            ("2026-09-18", "PRELIEVO ASSEGNO - DM 05387 CRA: 26050700167309 NUM: 0208771000", -122.0)])
        riscontrata = await fattura(db, fid)
        giro2 = await _estratto_ufficiale(monkeypatch, [
            ("2026-09-18", "PRELIEVO ASSEGNO - DM 05387 CRA: 26050700167309 NUM: 0208771000", -122.0)])
        return {
            "fid": fid, "dichiarata": dichiarata, "altro_numero": altro_numero, "ass_altro": ass_altro,
            "riscontrata": riscontrata, "giro2": giro2,
            "assegno": (await tutti(db, "assegni", {"numero": "0208771000"}))[0],
            "righe": await righe_che_contano(db, "prima_nota_banca", fid),
            "partite": await tutti(db, "partite_aperte"),
            "saldo": await _saldo_banca(app_prima_nota()),
        }

    r = esegui(scenario())
    # compilare l'assegno dichiara la fattura pagata, in attesa del solo riscontro bancario
    assert e_pagata_su_ogni_campo(r["dichiarata"])
    assert r["dichiarata"]["in_attesa_riscontro_banca"] is True
    # l'addebito di un altro numero non riscontra questo assegno
    assert r["altro_numero"]["in_attesa_riscontro_banca"] is True
    assert r["ass_altro"][0].get("incassato_confermato_banca") is not True
    # numero e importo uguali: assegno incassato, fattura riscontrata, una sola riga che pesa
    assert r["assegno"]["incassato_confermato_banca"] is True and r["assegno"]["stato"] == "incassato"
    assert r["riscontrata"]["in_attesa_riscontro_banca"] is False
    assert e_pagata_su_ogni_campo(r["riscontrata"])
    assert len(r["righe"]) == 1 and _d(r["righe"][0]["importo"]) == Decimal("122.00")
    assert r["righe"][0]["numero_assegno"] == "0208771000"
    assert r["saldo"] == Decimal("-122.00"), "la dichiarazione e il movimento vero non si sommano"
    assert r["partite"][0]["stato"] == "chiusa"
    assert r["giro2"]["stats"]["nuovi"] == 0


# ── 2f. parcella con ritenuta ────────────────────────────────────────────────

def _parcella():
    return xml_fattura(numero="P1", imponibile="1000.00", iva="220.00", totale="1220.00", ritenuta="200.00",
                       descrizione="Consulenza")


def test_parcella_con_ritenuta_al_fornitore_esce_il_netto_e_la_ritenuta_resta_da_versare(archivio_scenari, monkeypatch,
                                                                                      ingresso):
    db = archivio_scenari
    import app.services.telegram_notifications as telegram

    async def _muto(*_a, **_k):
        return True

    monkeypatch.setattr(telegram, "send_notification", _muto)

    async def scenario():
        await crea_fornitore(db, metodo="bonifico")
        esito = await importa(db, _parcella(), ingresso)
        fid = esito["id"]
        inizio = {"fattura": await fattura(db, fid), "rit": await tutti(db, "ritenute_acconto"),
                  "alert": await tutti(db, "alerts", {"codice": "RITENUTA_DA_VERSARE"}),
                  "banca": await tutti(db, "prima_nota_banca")}
        # il lordo non paga la parcella: al fornitore esce il netto
        await _estratto_ufficiale(monkeypatch, [("2026-09-15", CAUSALE_BONIFICO, -1220.0)])
        col_lordo = await fattura(db, fid)
        await _estratto_ufficiale(monkeypatch, [("2026-09-16", CAUSALE_BONIFICO, -1020.0)])
        col_netto = await fattura(db, fid)
        return {"fid": fid, "inizio": inizio, "col_lordo": col_lordo, "col_netto": col_netto,
                "righe": await righe_che_contano(db, "prima_nota_banca", fid),
                "alert_dopo_bonifico": await tutti(db, "alerts", {"codice": "RITENUTA_DA_VERSARE"})}

    r = esegui(scenario())
    from app.services.stato_pagamento_fattura import e_pagata

    assert _d(r["inizio"]["fattura"]["importo_ritenuta"]) == Decimal("200.00")
    # la ritenuta nasce con la parcella: attesa 1040, scadenza il 16 del mese dopo, alert aperto
    assert len(r["inizio"]["rit"]) == 1
    rit = r["inizio"]["rit"][0]
    assert rit["importo_cents"] == 20000 and rit["scadenza"] == "2026-10-16" and rit["fattura_id"] == r["fid"]
    assert [a["stato"] for a in r["inizio"]["alert"]] == ["aperto"]
    # la riga provvisoria di Banca porta il netto, mai il lordo
    assert _d(r["inizio"]["banca"][0]["importo"]) == Decimal("1020.00")
    assert not e_pagata(r["col_lordo"]), "un bonifico di 1.220,00 non e' il netto della parcella"
    assert e_pagata_su_ogni_campo(r["col_netto"])
    assert len(r["righe"]) == 1 and _d(r["righe"][0]["importo"]) == Decimal("1020.00")
    # pagare il fornitore non versa la ritenuta: l'alert resta aperto fino al 1040
    assert [a["stato"] for a in r["alert_dopo_bonifico"]] == ["aperto"]


def test_il_1040_versato_chiude_l_alert_della_ritenuta(archivio_scenari, monkeypatch):
    db = archivio_scenari
    import app.services.telegram_notifications as telegram
    from app.routers import ritenute

    async def _muto(*_a, **_k):
        return True

    monkeypatch.setattr(telegram, "send_notification", _muto)

    def quietanza(importo_cents):
        riga = {"codice_tributo": "1040", "periodo_riferimento": "09/2026",
                "importo_debito_cents": importo_cents, "importo_credito_cents": 0}
        return {"id": "q-1040", "data_pagamento": "2026-10-16", "protocollo_telematico": "26101612345678901/000001",
                "sezione_erario": [riga], "sezione_regioni": [], "sezione_tributi_locali": [], "sezione_inps": [],
                "totali": {"saldo_netto_cents": importo_cents}, "f24_associati": []}

    async def scenario():
        await crea_fornitore(db, metodo="bonifico")
        await importa(db, _parcella(), "drive")
        # un F24 col 1040 di importo diverso non chiude
        await db["quietanze_f24"].insert_one(quietanza(19999))
        await ritenute.riconcilia_ritenute_esistenti(db)
        con_importo_sbagliato = (await tutti(db, "alerts", {"codice": "RITENUTA_DA_VERSARE"}))[0]["stato"]
        await db["quietanze_f24"].delete_one({"id": "q-1040"})
        await db["quietanze_f24"].insert_one(quietanza(20000))
        await ritenute.riconcilia_ritenute_esistenti(db)
        rit = (await tutti(db, "ritenute_acconto"))[0]
        alert = (await tutti(db, "alerts", {"codice": "RITENUTA_DA_VERSARE"}))[0]
        await ritenute.riconcilia_ritenute_esistenti(db)
        return con_importo_sbagliato, rit, alert, await tutti(db, "alerts", {"codice": "RITENUTA_DA_VERSARE"})

    sbagliato, rit, alert, alert_dopo = esegui(scenario())
    assert sbagliato == "aperto"
    assert rit["stato_obbligazione"] == "VERSATA" and rit["stato"] == "pagata_puntuale"
    assert alert["stato"] != "aperto" and alert["risolto"] is True
    assert len(alert_dopo) == 1


# ── 2c bis. assegno non dichiarato sulla fattura: l'addebito col numero e l'importo ──────────────────────────

@pytest.mark.parametrize("fatture,importo_ec,atteso", [
    # unica fattura di pari importo emessa nei 15 giorni prima dell'addebito: regola del titolare
    ([("1", "2026-09-10", "122.00")], -122.0, "collegata"),
    # emessa 29 giorni prima: solo una proposta da confermare, mai un collegamento
    ([("1", "2026-08-20", "122.00")], -122.0, "proposta"),
    # due fatture uguali nella finestra: ambigue, due proposte e nessuna scelta
    ([("1", "2026-09-10", "122.00"), ("2", "2026-09-12", "122.00")], -122.0, "proposta"),
    # un centesimo di scarto: niente, nemmeno una proposta
    ([("1", "2026-09-10", "122.00")], -121.99, "niente"),
], ids=["unica_nei_15_giorni", "oltre_i_15_giorni", "due_candidate", "importo_diverso"])
def test_assegno_addebitato_senza_fattura_dichiarata_collega_solo_con_la_regola_del_titolare(
        archivio_scenari, monkeypatch, fatture, importo_ec, atteso):
    db = archivio_scenari

    async def scenario():
        await crea_fornitore(db, metodo="assegno")
        ids = []
        for numero, data, totale in fatture:
            imponibile = (_d(totale) / Decimal("1.22")).quantize(Decimal("0.01"))
            esito = await importa(db, xml_fattura(numero=numero, data=data, imponibile=str(imponibile),
                                                  iva=str(_d(totale) - imponibile), totale=totale), "drive")
            ids.append(esito["id"])
        await _estratto_ufficiale(monkeypatch, [
            ("2026-09-18", "PRELIEVO ASSEGNO - DM 05387 CRA: 26050700167309 NUM: 0208771000", importo_ec)])
        return {"fatture": [await fattura(db, i) for i in ids], "ec": (await tutti(db, "estratto_conto_movimenti"))[0],
                "assegno": (await tutti(db, "assegni", {"numero": "0208771000"}))[0],
                "proposte": await tutti(db, "proposte_associazione_assegni"),
                "partite": await tutti(db, "partite_aperte")}

    r = esegui(scenario())
    from app.services.stato_pagamento_fattura import e_pagata

    # l'addebito dell'assegno e' sempre un fatto bancario: la riga resta e l'assegno risulta incassato
    assert r["ec"]["riconciliato"] is True and r["ec"]["categoria"] == "Assegni"
    assert r["assegno"]["incassato_confermato_banca"] is True
    if atteso == "collegata":
        assert e_pagata_su_ogni_campo(r["fatture"][0])
        assert r["fatture"][0]["assegni_collegati"][0]["match_livello"] == "REGOLA_TITOLARE_GIORNI_PRECEDENTI"
        assert r["partite"][0]["stato"] == "chiusa"
        assert r["proposte"] == []
    else:
        assert not any(e_pagata(f) for f in r["fatture"]), "l'importo da solo non collega una fattura"
        assert all(f.get("assegni_collegati") in (None, []) for f in r["fatture"])
        assert all(p["stato"] == "aperta" for p in r["partite"])
        assert len(r["proposte"]) == (len(fatture) if atteso == "proposta" else 0)
        assert all(p["stato"] == "da_confermare" for p in r["proposte"])
