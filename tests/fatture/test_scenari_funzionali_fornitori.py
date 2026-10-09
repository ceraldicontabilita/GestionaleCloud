"""Collaudo funzionale 5: fornitori, doppioni, metodo di pagamento con data.

Fusione soft (mai DELETE) con ripuntamento di fatture, partite e pagamenti; due P.IVA valide diverse non
si fondono mai; il metodo del fornitore ha una data e `applica-metodo-dal` in `dry_run` non scrive,
il giro vero scrive solo dove consentito e il secondo giro non trova piu' niente.
"""
import asyncio
import copy
from datetime import datetime, timezone
from decimal import Decimal

from tests.fatture._scenari_comuni import (
    FilePdf, app_con, archivio_scenari, crea_fornitore, esegui, fattura, importa,
    importa_estratto, parser_pdf_con, richiesta, righe_che_contano, transazione_pdf, tutti, xml_fattura,
)

__all__ = ["archivio_scenari"]

PIVA_TOP = "07267610637"
PIVA_TIMAS = "07818970639"
PIVA_SUMUP_NL = "NL858187498B01"
PIVA_SUMUP_IE = "IE9813461A"


def _d(valore) -> Decimal:
    return Decimal(str(valore))


def _fotografia(raccolte):
    return copy.deepcopy(raccolte)


# ── fusione ──────────────────────────────────────────────────────────────────

def test_stessa_piva_fusione_soft_con_ripuntamento_e_secondo_giro_a_vuoto(archivio_scenari):
    db = archivio_scenari
    from app.services import fornitori_dedupe as dd
    from app.services.event_bus import EventTypes, propagate_event
    from app.services.eventi_fattura import costruisci_evento_fattura_created

    async def scenario():
        # il fornitore vero nasce dall'import (fattura 1); il doppione e' un'anagrafica manuale con refuso
        await crea_fornitore(db, metodo="bonifico", piva=PIVA_TOP, nome="TOP DISTRIBUZIONE SRL", id_="forn-vincente")
        a = await importa(db, xml_fattura(numero="1", piva=PIVA_TOP, nome="TOP DISTRIBUZIONE SRL"), "drive")
        await db["fornitori"].insert_one({
            "id": 115, "ragione_sociale": "Top Distribuzione S.r.l.", "partita_iva": "IT" + PIVA_TOP,
            "iban": "IT60X0542811101000000999999", "created_at": "2026-04-22"})
        # fattura 2, pagamenti e alert agganciati al doppione (115)
        await db["invoices"].insert_one({
            "id": "inv-doppione", "invoice_number": "2", "invoice_date": "2026-09-11", "total_amount": 61.0,
            "imponibile": 50.0, "iva": 11.0, "tipo_documento": "TD01", "supplier_id": 115,
            "supplier_name": "Top Distribuzione S.r.l.", "supplier_vat": PIVA_TOP, "status": "imported",
            "metodo_pagamento": "bonifico"})
        inv = await db["invoices"].find_one({"id": "inv-doppione"})
        await propagate_event(EventTypes.FATTURA_CREATED, costruisci_evento_fattura_created(
            inv, fornitore_id=115, metodo_pagamento="bonifico"), db)
        await db["prima_nota_banca"].insert_one({
            "id": "pn-doppione", "data": "2026-09-12", "tipo": "uscita", "importo": 61.0, "categoria": "Fatture",
            "fattura_id": "inv-doppione", "fornitore_piva": "IT" + PIVA_TOP, "source": "manuale"})
        prima = {"fornitori": len(await tutti(db, "fornitori")),
                 "partite": await tutti(db, "partite_aperte")}
        giro = await dd.giro_unifica_fornitori()
        secondo = await dd.giro_unifica_fornitori()
        # una nuova fattura dello stesso fornitore dopo la fusione: va al vincente, nessuna anagrafica nuova
        c = await importa(db, xml_fattura(numero="3", data="2026-09-13", piva=PIVA_TOP,
                                          nome="TOP DISTRIBUZIONE SRL"), "drive")
        return {"a": a, "c": c, "prima": prima, "giro": giro, "secondo": secondo,
                "fornitori": await tutti(db, "fornitori"), "fatture": await tutti(db, "invoices"),
                "partite": await tutti(db, "partite_aperte"), "pn": await tutti(db, "prima_nota_banca")}

    r = esegui(scenario())
    vincente = next(f for f in r["fornitori"] if f["id"] == "forn-vincente")
    # un solo giro fonde il doppione certo (stessa P.IVA, anche col prefisso IT); il secondo non trova niente
    assert [(x["target_id"], x["duplicate_id"]) for x in r["giro"]["fusi"]] == [("forn-vincente", 115)]
    assert r["secondo"]["fusi"] == []
    # fusione soft: nessuna anagrafica cancellata, il perdente e' marcato e punta al vincente
    assert len(r["fornitori"]) == r["prima"]["fornitori"] == 2
    perdente = next(f for f in r["fornitori"] if f["id"] == 115)
    assert perdente["status"] == "unificato" and perdente["merged_into"] == "forn-vincente"
    assert vincente.get("status") != "unificato"
    assert vincente["id_precedenti"] == ["115"] and "IT60X0542811101000000999999" in vincente["iban_alternativi"]
    # le fatture del doppione passano al vincente (per id), nessuna resta sul perdente
    assert {str(f["supplier_id"]) for f in r["fatture"]} == {"forn-vincente"}
    # la partita aperta del doppione segue il fornitore: il debito si legge su un'anagrafica sola
    assert {str(p["controparte_id"]) for p in r["partite"]} == {"forn-vincente"}, [p["controparte_id"] for p in r["partite"]]
    # i pagamenti indicizzati per P.IVA seguono la forma canonica
    assert r["pn"][0]["fornitore_piva"] == PIVA_TOP
    # la fattura nuova non riattiva il perdente e non crea un'anagrafica
    assert r["c"]["status"] == "imported" and len(r["fornitori"]) == 2
    nuova = next(f for f in r["fatture"] if f["invoice_number"] == "3")
    assert str(nuova["supplier_id"]) == "forn-vincente"


def test_due_piva_valide_diverse_non_si_fondono_mai(archivio_scenari):
    db = archivio_scenari
    from app.services import fornitori_dedupe as dd

    async def scenario():
        await db["fornitori"].insert_many([
            {"id": "nl", "ragione_sociale": "SumUp Limited", "partita_iva": PIVA_SUMUP_NL},
            {"id": "ie", "ragione_sociale": "SumUp Limited", "partita_iva": PIVA_SUMUP_IE},
        ])
        await db["invoices"].insert_many([
            {"id": "f-nl", "supplier_id": "nl", "supplier_vat": PIVA_SUMUP_NL, "invoice_number": "1"},
            {"id": "f-ie", "supplier_id": "ie", "supplier_vat": PIVA_SUMUP_IE, "invoice_number": "2"},
        ])
        prima = _fotografia((await tutti(db, "fornitori"), await tutti(db, "invoices")))
        giro = await dd.giro_unifica_fornitori()
        errore = None
        try:
            await dd.merge_fornitori("nl", "ie", motivo="tentativo")
        except ValueError as exc:
            errore = str(exc)
        return prima, giro, errore, (await tutti(db, "fornitori"), await tutti(db, "invoices"))

    prima, giro, errore, dopo = esegui(scenario())
    assert giro["fusi"] == []
    assert errore is not None and "diverse" in errore
    assert dopo == prima, "una P.IVA valida diversa non si tocca, nemmeno con la fusione forzata a mano"


def test_la_fusione_non_e_mai_una_cancellazione(archivio_scenari):
    db = archivio_scenari
    from app.services import fornitori_dedupe as dd

    async def scenario():
        await db["fornitori"].insert_many([
            {"id": "a", "ragione_sociale": "Rossi Srl", "partita_iva": PIVA_TOP, "iban": "IT1"},
            {"id": "b", "ragione_sociale": "Rossi S.r.l.", "partita_iva": "IT" + PIVA_TOP},
        ])
        errore = None
        try:
            await dd.merge_fornitori("a", "b", soft=False)
        except ValueError as exc:
            errore = str(exc)
        return errore, await tutti(db, "fornitori")

    errore, fornitori = esegui(scenario())
    assert errore and "soft" in errore
    assert len(fornitori) == 2 and all("merged_into" not in f for f in fornitori)


# ── metodo di pagamento con data ─────────────────────────────────────────────

def _app_fornitori():
    from app.routers.suppliers_module import router
    from app.utils.dependencies import get_current_admin_user

    app = app_con((router, "/api/suppliers"))
    app.dependency_overrides[get_current_admin_user] = lambda: {"sub": "titolare", "role": "admin"}
    return app


def test_il_metodo_si_data_solo_quando_cambia_mai_per_un_semplice_salvataggio(archivio_scenari):
    db = archivio_scenari

    async def scenario():
        await db["fornitori"].insert_one({
            "id": "big", "partita_iva": PIVA_TOP, "ragione_sociale": "BIG FOOD SRL",
            "metodo_pagamento": "cassa", "metodo_pagamento_dal": "2025-01-01"})
        app = _app_fornitori()
        # salvataggio della scheda con lo stesso metodo: la data resta quella voluta dal titolare
        stesso = await richiesta(app, "PUT", "/api/suppliers/big", json={
            "metodo_pagamento": "cassa", "telefono": "081 1234567"})
        dopo_stesso = await db["fornitori"].find_one({"id": "big"}, {"_id": 0})
        # cambio di metodo senza data: si stampa a oggi
        cambio = await richiesta(app, "PUT", "/api/suppliers/big", json={"metodo_pagamento": "bonifico"})
        dopo_cambio = await db["fornitori"].find_one({"id": "big"}, {"_id": 0})
        # data esplicita del titolare: vale quella
        esplicita = await richiesta(app, "PUT", "/api/suppliers/big", json={
            "metodo_pagamento": "cassa", "metodo_pagamento_dal": "2025-06-01"})
        dopo_esplicita = await db["fornitori"].find_one({"id": "big"}, {"_id": 0})
        # data scritta male: rifiutata
        storta = await richiesta(app, "PUT", "/api/suppliers/big", json={
            "metodo_pagamento": "cassa", "metodo_pagamento_dal": "01/01/2025"})
        return stesso, dopo_stesso, cambio, dopo_cambio, esplicita, dopo_esplicita, storta

    stesso, dopo_stesso, cambio, dopo_cambio, esplicita, dopo_esplicita, storta = esegui(scenario())
    assert stesso.status_code == 200, stesso.text
    assert dopo_stesso["metodo_pagamento_dal"] == "2025-01-01"
    assert cambio.status_code == 200, cambio.text
    assert dopo_cambio["metodo_pagamento_dal"] == datetime.now(timezone.utc).strftime("%Y-%m-%d")
    assert esplicita.status_code == 200 and dopo_esplicita["metodo_pagamento_dal"] == "2025-06-01"
    assert storta.status_code == 400


async def _fornitore_che_passa_a_cassa(db):
    """Un fornitore a bonifico le cui fatture sono gia' entrate, poi «sempre cassa dal 01/01/2026»."""
    await crea_fornitore(db, metodo="bonifico", piva=PIVA_TOP, nome="BIG FOOD SRL", id_=381, iban=None)
    ids = {}
    for numero, data, imponibile, iva, totale in (
            ("1", "2026-09-10", "100.00", "22.00", "122.00"), ("2", "2026-09-11", "100.00", "22.00", "122.00"),
            ("3", "2026-09-12", "200.00", "44.00", "244.00")):
        ids[numero] = (await importa(db, xml_fattura(numero=numero, data=data, piva=PIVA_TOP, nome="BIG FOOD SRL",
                                                     imponibile=imponibile, iva=iva, totale=totale), "drive"))["id"]
    ids["NC"] = (await importa(db, xml_fattura(numero="NC1", tipo="TD04", data="2026-09-13", piva=PIVA_TOP,
                                               nome="BIG FOOD SRL", imponibile="10.00", iva="2.20", totale="12.20"),
                               "drive"))["id"]
    ids["vecchia"] = (await importa(db, xml_fattura(numero="V1", data="2025-12-20", piva=PIVA_TOP, nome="BIG FOOD SRL"),
                                    "drive"))["id"]
    # la fattura 3 e' stata pagata in banca (prova dell'estratto ufficiale): non si sposta in Cassa
    return ids


async def _passa_a_cassa(db, app):
    risposta = await richiesta(app, "PUT", "/api/suppliers/381", json={
        "metodo_pagamento": "cassa", "metodo_pagamento_dal": "2026-01-01"})
    assert risposta.status_code == 200, risposta.text


async def _attendi_giro(app, supplier="381"):
    for _ in range(200):
        stato = (await richiesta(app, "GET", f"/api/suppliers/{supplier}/applica-metodo-dal/stato")).json()
        if stato.get("stato") in ("completato", "errore"):
            return stato
        await asyncio.sleep(0.05)
    raise AssertionError("il giro non e' finito")


def test_applica_metodo_dal_dry_run_non_scrive_il_giro_vero_scrive_dove_consentito_e_il_secondo_chiude_zero(
        archivio_scenari, monkeypatch):
    db = archivio_scenari

    async def scenario():
        ids = await _fornitore_che_passa_a_cassa(db)
        parser_pdf_con(monkeypatch, [transazione_pdf(
            "2026-09-14", "VS.DISP. RIF. MBVT12345678/001 FAVORE BIG FOOD SRL FATT. 3", -244.0)])
        await importa_estratto(FilePdf())
        app = _app_fornitori()
        await _passa_a_cassa(db, app)

        prima = _fotografia({c: await tutti(db, c) for c in ("invoices", "prima_nota_cassa", "prima_nota_banca",
                                                              "partite_aperte")})
        anteprima = (await richiesta(app, "POST", "/api/suppliers/381/applica-metodo-dal")).json()
        dopo_anteprima = _fotografia({c: await tutti(db, c) for c in prima})
        avvio = (await richiesta(app, "POST", "/api/suppliers/381/applica-metodo-dal?dry_run=false")).json()
        stato = await _attendi_giro(app)
        secondo_piano = (await richiesta(app, "POST", "/api/suppliers/381/applica-metodo-dal")).json()
        await richiesta(app, "POST", "/api/suppliers/381/applica-metodo-dal?dry_run=false")
        stato2 = await _attendi_giro(app)
        return {"ids": ids, "anteprima": anteprima, "prima": prima, "dopo_anteprima": dopo_anteprima,
                "avvio": avvio, "stato": stato, "secondo_piano": secondo_piano, "stato2": stato2,
                "cassa": await tutti(db, "prima_nota_cassa"),
                "banca_1_2": [await righe_che_contano(db, "prima_nota_banca", ids[n]) for n in ("1", "2")],
                "banca_3": await righe_che_contano(db, "prima_nota_banca", ids["3"]),
                "partite": {p["documento_id"]: p["stato"] for p in await tutti(db, "partite_aperte")},
                "fatture": {n: await fattura(db, i) for n, i in ids.items()}}

    r = esegui(scenario())
    num = lambda voci: sorted(v["numero"] for v in voci)  # noqa: E731
    # l'anteprima elenca: 1 e 2 da chiudere (nessuna prova bancaria), 3 in conflitto (addebito in banca), NC non forzata
    assert r["anteprima"]["dry_run"] is True
    assert num(r["anteprima"]["da_chiudere_in_cassa"]) == ["1", "2"], r["anteprima"]
    assert num(r["anteprima"]["conflitto_banca_o_assegno"]) == ["3"]
    assert num(r["anteprima"]["non_forzate"]) == ["NC1"]
    assert r["anteprima"]["fatture_dal"] == 4, "la fattura del 2025 e' prima del «dal»"
    assert _d(r["anteprima"]["residuo_da_chiudere"]) == Decimal("244.00")
    # il dry_run non ha scritto niente
    assert r["dopo_anteprima"] == r["prima"]
    # il giro vero scrive solo dove consentito: due righe di Cassa da 122,00, la fattura in banca resta com'e'
    assert r["avvio"]["avviato"] is True
    assert r["stato"]["stato"] == "completato" and r["stato"]["registrate"] == 2 and r["stato"]["scartate"] == 0
    assert sorted(_d(c["importo"]) for c in r["cassa"]) == [Decimal("122.00"), Decimal("122.00")]
    assert {c["fattura_id"] for c in r["cassa"]} == {r["ids"]["1"], r["ids"]["2"]}
    f = r["fatture"]
    assert f["1"]["prima_nota_tipo"] == "cassa" and f["2"]["prima_nota_tipo"] == "cassa"
    assert f["3"]["prima_nota_tipo"] == "banca" and f["3"]["metodo_pagamento_effettivo"] != "cassa"
    assert f["NC"].get("prima_nota_tipo") != "cassa" and f["vecchia"].get("prima_nota_tipo") != "cassa"
    # le fatture chiuse in Cassa non pesano anche in Banca; quella provata dalla banca ci resta, una volta sola
    assert r["banca_1_2"] == [[], []]
    assert len(r["banca_3"]) == 1 and _d(r["banca_3"][0]["importo"]) == Decimal("244.00")
    assert r["partite"][r["ids"]["1"]] == "chiusa" and r["partite"][r["ids"]["2"]] == "chiusa"
    assert r["partite"][r["ids"]["3"]] == "chiusa"
    assert r["partite"][r["ids"]["NC"]] == "aperta" and r["partite"][r["ids"]["vecchia"]] == "aperta"
    # il secondo giro chiude zero
    assert r["secondo_piano"]["da_chiudere_in_cassa"] == []
    assert r["stato2"]["stato"] == "completato" and r["stato2"]["registrate"] == 0
    assert len(r["cassa"]) == 2


def test_cambiare_il_metodo_del_fornitore_non_toglie_il_pagamento_provato_dalla_banca(archivio_scenari, monkeypatch):
    """Il ripasso che parte al cambio metodo ripristina i provvisori sul lato sbagliato, non i pagamenti provati.

    La fattura 1 e' pagata e riconciliata con l'estratto ufficiale (resta anche la riga provvisoria che l'import
    aveva scritto per il metodo a bonifico); la fattura 2 e' ancora solo provvisoria. Poi il fornitore passa a cassa.
    """
    db = archivio_scenari
    from app.routers.prima_nota_module.manutenzione import ripristina_provvisori_metodo_errato

    async def scenario():
        await crea_fornitore(db, metodo="bonifico", piva=PIVA_TOP, nome="BIG FOOD SRL", id_=381, iban=None)
        pagata = (await importa(db, xml_fattura(numero="1", piva=PIVA_TOP, nome="BIG FOOD SRL"), "drive"))["id"]
        aperta = (await importa(db, xml_fattura(numero="2", data="2026-09-11", piva=PIVA_TOP, nome="BIG FOOD SRL",
                                                imponibile="50.00", iva="11.00", totale="61.00"), "drive"))["id"]
        parser_pdf_con(monkeypatch, [transazione_pdf(
            "2026-09-14", "VS.DISP. RIF. MBVT12345678/001 FAVORE BIG FOOD SRL FATT. 1", -122.0)])
        await importa_estratto(FilePdf())
        prima = await fattura(db, pagata)
        righe_prima = await righe_che_contano(db, "prima_nota_banca", pagata)
        await db["fornitori"].update_one({"id": 381}, {"$set": {"metodo_pagamento": "cassa"}})
        esito = await ripristina_provvisori_metodo_errato(dry_run=False, anno=2026, banca_non_riconciliate=False)
        return {"pagata": pagata, "aperta": aperta, "prima": prima, "righe_prima": righe_prima, "esito": esito,
                "dopo": await fattura(db, pagata), "righe_dopo": await righe_che_contano(db, "prima_nota_banca", pagata),
                "ec": await tutti(db, "estratto_conto_movimenti"),
                "banca": await tutti(db, "prima_nota_banca"), "aperta_dopo": await fattura(db, aperta)}

    r = esegui(scenario())
    from app.services.stato_pagamento_fattura import e_pagata

    assert e_pagata(r["prima"]) and len(r["righe_prima"]) == 1
    # la fattura provata dalla banca resta pagata, con la sua riga e il suo collegamento all'addebito
    assert e_pagata(r["dopo"]), "il cambio di metodo ha tolto a una fattura pagata la sua prova bancaria"
    assert r["dopo"]["prima_nota_id"] == r["prima"]["prima_nota_id"]
    assert r["dopo"].get("movimento_bancario_id") == r["prima"].get("movimento_bancario_id")
    assert [x["id"] for x in r["righe_dopo"]] == [x["id"] for x in r["righe_prima"]]
    assert r["ec"][0]["riconciliato"] is True
    # la fattura ancora solo provvisoria sul lato sbagliato torna ai provvisori, senza cancellare niente
    assert not e_pagata(r["aperta_dopo"])
    soft = [b for b in r["banca"] if b.get("status") == "deleted"]
    assert [b["fattura_id"] for b in soft] == [r["aperta"]]
    assert all(b.get("deleted_reason") for b in soft)


def test_un_cambio_di_ragione_sociale_o_il_prefisso_it_non_creano_un_secondo_fornitore(archivio_scenari):
    """Fornitore univoco per P.IVA: le fatture dello stesso cedente arrivano sempre alla stessa anagrafica."""
    db = archivio_scenari

    async def scenario():
        for numero, nome, piva in (("1", "ROSSI MARIO SRL", PIVA_TOP),
                                   ("2", "ROSSI MARIO S.R.L. IN LIQUIDAZIONE", PIVA_TOP),
                                   ("3", "ROSSI MARIO SRL", "IT" + PIVA_TOP)):
            await importa(db, xml_fattura(numero=numero, nome=nome, piva=piva), "drive")
        return await tutti(db, "fornitori"), await tutti(db, "invoices")

    fornitori, fatture = esegui(scenario())
    assert len(fornitori) == 1
    assert {f["supplier_id"] for f in fatture} == {fornitori[0]["id"]} and len(fatture) == 3
