"""Collaudo funzionale 1: importo una fattura XML di un fornitore a metodo BANCA.

Ogni test parte dall'azione dell'utente (import dell'XML) e legge il risultato sui dati: partita
aperta, evento, audit, libro giornale quadrato, periodo IVA. Motori reali, event bus con tutti gli
handler di produzione, archivio in memoria. L'atteso e' quello di CLAUDE.md («Fatture: identita e
duplicati», «Regole contabili vincolanti», «IVA»).
"""
from decimal import Decimal

from app.engines import iva_fatture
from tests.fatture._scenari_comuni import (
    archivio_scenari, crea_fornitore, esegui, fattura, importa, ingresso, tutti, xml_fattura,
)

__all__ = ["archivio_scenari", "ingresso"]


def _d(valore) -> Decimal:
    return Decimal(str(valore))


def test_import_fattura_banca_crea_partita_evento_e_giornale_quadrato(archivio_scenari, ingresso):
    db = archivio_scenari

    async def scenario():
        await crea_fornitore(db, metodo="bonifico")
        esito = await importa(db, xml_fattura(), ingresso)
        return esito, await fattura(db, esito["id"])

    esito, inv = esegui(scenario())
    assert esito["status"] == "imported"
    assert inv.get("stato_derivati", "allineato") == "allineato"
    # il metodo viene dall'anagrafica fornitore, mai dal documento
    assert inv["metodo_pagamento"] == "bonifico"
    # le fatture fornitore non hanno scadenza (decisione del 19/09/2026)
    assert inv["data_scadenza"] is None

    async def letture():
        return (await tutti(db, "partite_aperte"), await tutti(db, "audit_log"),
                await tutti(db, "movimenti_contabili"))

    partite, audit, giornale = esegui(letture())

    # partita aperta: una, per l'intero importo, collegata alla fattura
    assert len(partite) == 1
    p = partite[0]
    assert p["documento_id"] == inv["id"] and p["stato"] == "aperta"
    assert _d(p["importo_originale"]) == _d(p["residuo"]) == Decimal("122.00")
    # l'evento fattura.created e' arrivato agli handler (audit scritto dal suo handler)
    assert [a["azione"] for a in audit if a["entita_id"] == inv["id"] and a["modulo"] == "fatture"] == ["creata"]

    # libro giornale: una scrittura, chiave idempotente, quadrata al centesimo, in Decimal
    assert len(giornale) == 1
    g = giornale[0]
    assert g["idempotency_key"] == f"reg:fattura:{inv['id']}"
    dare = sum(_d(r["dare"]) for r in g["righe"])
    avere = sum(_d(r["avere"]) for r in g["righe"])
    assert dare == avere == Decimal("122.00")
    assert _d(g["totale_dare"]) == _d(g["totale_avere"]) == Decimal("122.00")
    assert g["anno"] == 2026 and g["numero_registrazione"] == 1
    # costo (imponibile) + IVA a credito a DARE, debito verso il fornitore ad AVERE
    per_conto = {r["conto_codice"]: r for r in g["righe"]}
    assert _d(per_conto["01.04.01"]["dare"]) == Decimal("22.00")
    assert _d(per_conto["02.01.01"]["avere"]) == Decimal("122.00")
    assert sum(_d(r["dare"]) for c, r in per_conto.items() if c not in ("01.04.01",)) == Decimal("100.00")
    assert inv["registrata_contabilita"] is True and inv["movimento_contabile_id"] == g["id"]


def test_secondo_ingest_della_stessa_fattura_non_crea_niente(archivio_scenari, ingresso):
    db = archivio_scenari

    async def scenario():
        await crea_fornitore(db, metodo="bonifico")
        primo = await importa(db, xml_fattura(), ingresso)
        prima = {c: len(await tutti(db, c)) for c in (
            "invoices", "partite_aperte", "movimenti_contabili", "prima_nota_banca", "audit_log",
            "alerts", "protocollo_registrazioni")}
        secondo = await importa(db, xml_fattura(), ingresso)
        # stesso contenuto da un altro nome di file e dall'altro ingresso: e' la stessa fattura
        altro = "documenti" if ingresso == "drive" else "drive"
        terzo = await importa(db, xml_fattura(), altro, nome_file="copia (2).xml")
        dopo = {c: len(await tutti(db, c)) for c in prima}
        return primo, secondo, terzo, prima, dopo

    primo, secondo, terzo, prima, dopo = esegui(scenario())
    assert primo["status"] == "imported"
    assert secondo["status"] == "duplicate" and terzo["status"] == "duplicate"
    assert prima == dopo, "il reimport ha scritto qualcosa"
    assert dopo["invoices"] == 1 and dopo["partite_aperte"] == 1 and dopo["movimenti_contabili"] == 1


def test_fornitore_banca_la_prima_nota_resta_provvisoria_senza_prova_bancaria(archivio_scenari, ingresso):
    """Import != pagamento: senza estratto ufficiale la fattura non e' pagata e la riga non conta nel saldo."""
    db = archivio_scenari

    async def scenario():
        await crea_fornitore(db, metodo="bonifico")
        esito = await importa(db, xml_fattura(), ingresso)
        return await fattura(db, esito["id"]), await tutti(db, "prima_nota_banca"), await tutti(db, "prima_nota_cassa")

    inv, banca, cassa = esegui(scenario())
    from app.services.stato_pagamento_fattura import e_pagata

    assert not e_pagata(inv)
    assert cassa == []
    assert len(banca) == 1
    riga = banca[0]
    assert riga["provvisorio"] is True and riga["stato"] == "DA_VERIFICARE"
    assert riga["in_attesa_estratto_ufficiale"] is True  # fuori dal saldo reale finche' la banca non la prova


def test_iva_detraibile_non_si_scrive_finche_nessuno_la_valuta():
    """`iva_detraibile` assente = non deciso. Il motore IVA non scrive uno 0 di comodo."""
    inv = {"id": "x", "invoice_date": "2026-09-10", "iva": 22.0, "total_amount": 122.0,
           "tipo_documento": "TD01"}
    campi = iva_fatture.campi_iva_da_fattura(inv)
    assert "iva_detraibile" not in campi
    assert campi["stato_detrazione_iva"] == "DA_VERIFICARE"
    assert campi["periodo_iva_attribuito"] == "2026-09"

    # valutata dal classificatore -> si riporta com'e', anche se e' zero (decisione esplicita)
    assert iva_fatture.campi_iva_da_fattura({**inv, "iva_detraibile": 0.0})["iva_detraibile"] == 0.0
    assert iva_fatture.campi_iva_da_fattura({**inv, "iva_detraibile": 22.0})["iva_detraibile"] == 22.0


def test_giornale_rifiuta_la_fattura_con_iva_non_classificata_e_la_registra_dopo(archivio_scenari):
    """Guardia del libro giornale: senza `iva_detraibile` non si scrive; dopo la classificazione rientra da sola."""
    db = archivio_scenari
    from app.services.registrazione_contabile import registra_documento_import

    async def scenario():
        await db["invoices"].insert_one({
            "id": "inv-iva", "invoice_number": "9", "invoice_date": "2026-09-10", "total_amount": 122.0,
            "imponibile": 100.0, "iva": 22.0, "tipo_documento": "TD01", "supplier_name": "ACME",
            "supplier_vat": "01234567890", "status": "imported"})
        inv = await db["invoices"].find_one({"id": "inv-iva"})
        rifiutata = await registra_documento_import(db, "fattura", inv)
        senza = await tutti(db, "movimenti_contabili")
        await db["invoices"].update_one({"id": "inv-iva"}, {"$set": {"iva_detraibile": 22.0}})
        inv = await db["invoices"].find_one({"id": "inv-iva"})
        registrata = await registra_documento_import(db, "fattura", inv)
        ancora = await registra_documento_import(db, "fattura", inv)
        return rifiutata, senza, registrata, ancora, await tutti(db, "movimenti_contabili")

    rifiutata, senza, registrata, ancora, dopo = esegui(scenario())
    assert rifiutata["stato"] == "da_verificare" and "non classificata" in rifiutata["motivo"]
    assert senza == []
    assert registrata["stato"] == "registrato"
    assert ancora["stato"] == "gia_registrato"
    assert len(dopo) == 1 and dopo[0]["idempotency_key"] == "reg:fattura:inv-iva"


def test_all_import_la_classificazione_valorizza_iva_detraibile_prima_del_giornale(archivio_scenari, ingresso):
    """CLAUDE.md: all'import il campo lo scrive `handler_classifica_cdc`, dopo il motore IVA, e il giornale lo vede."""
    db = archivio_scenari

    async def scenario():
        await crea_fornitore(db, metodo="bonifico")
        esito = await importa(db, xml_fattura(), ingresso)
        return await fattura(db, esito["id"]), (await tutti(db, "movimenti_contabili"))[0]

    inv, g = esegui(scenario())
    assert inv["iva_detraibile"] is not None
    assert _d(inv["iva_detraibile"]) + _d(inv["iva_indetraibile"]) == Decimal("22.00")
    # il giornale usa la detraibilita' valutata: credito = detraibile, il resto va a costo
    credito = sum(_d(r["dare"]) for r in g["righe"] if r["conto_codice"] == "01.04.01")
    assert credito == _d(inv["iva_detraibile"])


# ── regola del 15 ────────────────────────────────────────────────────────────

def _periodo(op, ricezione, registrazione=None, **extra):
    inv = {"id": "r", "invoice_date": op, "iva": 22.0, "data_ricezione": ricezione, **extra}
    if registrazione:
        inv["data_registrazione"] = registrazione
    campi = iva_fatture.campi_iva_da_fattura(inv)
    return campi["periodo_iva_attribuito"], campi["regola_iva_applicata"]


def test_regola_del_15_attribuzione_del_periodo():
    # operazione di agosto ricevuta e annotata entro il 15 di settembre -> liquidazione di agosto
    assert _periodo("2026-08-28", "2026-09-10") == ("2026-08", "ENTRO_15_MESE_SUCCESSIVO")
    assert _periodo("2026-08-28", "2026-09-15") == ("2026-08", "ENTRO_15_MESE_SUCCESSIVO")
    # ricevuta dopo il 15 -> mese di ricezione
    assert _periodo("2026-08-28", "2026-09-16") == ("2026-09", "RICEVUTA_DOPO_IL_15")
    # ricevuta il 10 ma annotata dopo il 15: serve anche la registrazione entro il 15
    assert _periodo("2026-08-28", "2026-09-10", "2026-09-20") == ("2026-09", "RICEVUTA_DOPO_IL_15")
    # stesso mese
    assert _periodo("2026-09-03", "2026-09-20") == ("2026-09", "STESSO_MESE")
    # operazione dell'anno precedente: mai retroattribuita a dicembre
    assert _periodo("2025-12-20", "2026-01-05") == ("2026-01", "OPERAZIONE_ANNO_PRECEDENTE")
    assert _periodo("2025-12-20", "2026-01-05")[0] != "2025-12"


def test_regola_del_15_vale_anche_dal_vero_handler_di_import(archivio_scenari):
    """Dall'evento `fattura.created` il periodo IVA arriva sulla fattura salvata, con la regola del 15."""
    db = archivio_scenari
    from app.services.handlers.fattura_handlers import on_fattura_created_iva

    async def scenario():
        await db["invoices"].insert_many([
            {"id": "a", "invoice_date": "2026-08-28", "data_ricezione": "2026-09-10", "iva": 22.0},
            {"id": "b", "invoice_date": "2026-08-28", "data_ricezione": "2026-09-20", "iva": 22.0},
            {"id": "c", "invoice_date": "2025-12-20", "data_ricezione": "2026-01-05", "iva": 22.0},
        ])
        for i in "abc":
            await on_fattura_created_iva({"fattura_id": i}, db)
        return {i: await fattura(db, i) for i in "abc"}

    r = esegui(scenario())
    assert r["a"]["periodo_iva_attribuito"] == "2026-08"
    assert r["b"]["periodo_iva_attribuito"] == "2026-09"
    assert r["c"]["periodo_iva_attribuito"] == "2026-01"
    assert all("iva_detraibile" not in x for x in r.values())  # nessuno l'ha classificata: non e' decisa
    assert all(x["stato_detrazione_iva"] == "DA_VERIFICARE" for x in r.values())


def test_una_fattura_con_iva_gia_in_liquidazione_non_si_riattribuisce():
    inv = {"id": "u", "invoice_date": "2026-08-28", "data_ricezione": "2026-09-20", "iva": 22.0,
           "iva_utilizzata": True, "periodo_iva_attribuito": "2026-08", "periodo_iva_utilizzato": "2026-08",
           "stato_detrazione_iva": "INSERITA_IN_LIQUIDAZIONE", "iva_detraibile": 22.0}
    campi = iva_fatture.campi_iva_da_fattura(inv)
    assert campi["periodo_iva_attribuito"] == "2026-08"
    assert campi["iva_utilizzata"] is True


# ── id numerico ──────────────────────────────────────────────────────────────

def test_fattura_con_id_numerico_ha_partita_audit_e_giornale_senza_doppioni(archivio_scenari):
    """Su `invoices` l'id e' un numero su meta' delle righe: l'evento deve trovarla e non duplicare."""
    db = archivio_scenari
    from app.services.eventi_fattura import costruisci_evento_fattura_created
    from app.services.event_bus import EventTypes, propagate_event
    from app.routers.invoices.fatture_upload import _registra_in_partita_doppia

    async def scenario():
        await crea_fornitore(db, metodo="bonifico")
        await db["invoices"].insert_one({
            "id": 850878, "invoice_number": "850878", "invoice_date": "2026-09-10", "total_amount": 122.0,
            "imponibile": 100.0, "iva": 22.0, "tipo_documento": "TD01", "supplier_id": "forn-1",
            "supplier_name": "FORNITORE TEST SRL", "supplier_vat": "01234567890", "status": "imported",
            "metodo_pagamento": "bonifico", "linee": [{"descrizione": "Farina 00", "prezzo_totale": "100.00",
                                                       "aliquota_iva": "22.00"}]})
        inv = await db["invoices"].find_one({"id": 850878})
        for _ in range(2):  # lo stesso evento due volte: il recupero del pregresso lo puo' ripubblicare
            await propagate_event(EventTypes.FATTURA_CREATED, costruisci_evento_fattura_created(inv), db)
            await _registra_in_partita_doppia(db, 850878)
        return await tutti(db, "partite_aperte"), await tutti(db, "movimenti_contabili"), await fattura(db, 850878)

    partite, giornale, inv = esegui(scenario())
    assert len(partite) == 1 and partite[0]["stato"] == "aperta"
    assert str(partite[0]["documento_id"]) == "850878"
    assert len(giornale) == 1 and giornale[0]["idempotency_key"] == "reg:fattura:850878"
    assert _d(giornale[0]["totale_dare"]) == _d(giornale[0]["totale_avere"]) == Decimal("122.00")
    assert inv["periodo_iva_attribuito"] == "2026-09"


# ── identita' e doppioni ─────────────────────────────────────────────────────

def test_la_stessa_fattura_con_bom_e_a_capo_diversi_e_un_doppione_non_una_collisione(archivio_scenari):
    db = archivio_scenari

    async def scenario():
        await crea_fornitore(db, metodo="bonifico")
        originale = xml_fattura()
        rimaneggiato = b"\xef\xbb\xbf" + originale.replace(b"\n", b"\r\n")  # BOM + a capo Windows
        primo = await importa(db, originale, "drive")
        secondo = await importa(db, rimaneggiato, "drive", nome_file="stessa (1).xml")
        return primo, secondo, await tutti(db, "invoices"), await tutti(db, "alerts", {"codice": "FATTURA_IDENTITA_DA_VERIFICARE"})

    primo, secondo, fatture, alert = esegui(scenario())
    assert primo["status"] == "imported" and secondo["status"] == "duplicate"
    assert len(fatture) == 1 and alert == []


def test_stesso_numero_fornitore_e_data_con_contenuto_diverso_e_una_collisione_senza_effetti_contabili(archivio_scenari):
    """Numero, fornitore e data uguali ma originale diverso: non e' una deduplica dimostrata. La seconda copia
    entra da verificare, bloccata: niente partita, niente Prima Nota, niente giornale; la prima resta intatta."""
    db = archivio_scenari

    async def scenario():
        await crea_fornitore(db, metodo="bonifico")
        prima = await importa(db, xml_fattura(descrizione="Farina 00"), "drive")
        seconda = await importa(db, xml_fattura(descrizione="Zucchero"), "drive", nome_file="altra.xml")
        return {"prima": prima, "seconda": seconda, "fatture": {f["id"]: f for f in await tutti(db, "invoices")},
                "partite": await tutti(db, "partite_aperte"), "giornale": await tutti(db, "movimenti_contabili"),
                "banca": await tutti(db, "prima_nota_banca"),
                "alert": await tutti(db, "alerts", {"codice": "FATTURA_IDENTITA_DA_VERIFICARE"})}

    r = esegui(scenario())
    assert r["seconda"]["status"] == "imported" and r["seconda"]["grezzo"]["requires_review"] is True
    f1, f2 = r["fatture"][r["prima"]["id"]], r["fatture"][r["seconda"]["id"]]
    assert f1["status"] == "imported" and f1["duplicate_review_required"] is True
    assert f2["status"] == "da_verificare" and f2["stato_derivati"] == "bloccato_collisione_identita"
    assert f2["identity_collision_with_ids"] == [f1["id"]]
    assert len(r["partite"]) == 1 and r["partite"][0]["documento_id"] == f1["id"]
    assert len(r["giornale"]) == 1 and r["giornale"][0]["fattura_id"] == f1["id"]
    assert [b["fattura_id"] for b in r["banca"]] == [f1["id"]]
    assert len(r["alert"]) == 1 and r["alert"][0]["entita_id"] == f2["id"]


def test_il_numero_di_registrazione_e_progressivo_per_anno_anche_con_import_paralleli(archivio_scenari):
    import asyncio

    db = archivio_scenari

    async def scenario():
        await crea_fornitore(db, metodo="bonifico")
        otto = await asyncio.gather(*[
            importa(db, xml_fattura(numero=str(n), data="2026-09-10"), "drive", nome_file=f"{n}.xml")
            for n in range(1, 9)])
        anno_prima = await importa(db, xml_fattura(numero="99", data="2025-12-30"), "drive", nome_file="99.xml")
        # la stessa fattura quattro volte nello stesso istante: una sola entra, nessuna registrazione sprecata
        quattro = await asyncio.gather(*[importa(db, xml_fattura(numero="500"), "drive") for _ in range(4)])
        return otto, anno_prima, quattro, await tutti(db, "movimenti_contabili"), await tutti(db, "invoices")

    otto, anno_prima, quattro, giornale, fatture = esegui(scenario())
    assert all(x["status"] == "imported" for x in otto) and anno_prima["status"] == "imported"
    assert sorted(x["status"] for x in quattro) == ["duplicate", "duplicate", "duplicate", "imported"]
    assert len([f for f in fatture if f["invoice_number"] == "500"]) == 1
    numeri = {anno: sorted(g["numero_registrazione"] for g in giornale if g["anno"] == anno) for anno in (2025, 2026)}
    # ogni anno riparte da 1, senza buchi e senza ripetizioni
    assert numeri[2025] == [1]
    assert numeri[2026] == list(range(1, 10))
