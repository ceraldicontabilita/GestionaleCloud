"""17/09/2026: fatture 2026 doppie legacy↔Drive.

Le 767 fatture importate dall'archivio legacy avevano l'XML in
``fattura_allegata`` ma nessuna identita' canonica (``invoice_key``,
``supplier_vat``, ``content_hash``): l'ingest Drive ne creava una seconda
copia (485 doppioni, 9 registrati due volte nel libro giornale) e la dedup
periodica non poteva raggrupparle. Qui: identita' dall'XML, dedup che tiene
la copia registrata e storna la scrittura del doppione, storno dell'archivio
storico entrato per errore nel giornale, filtro del pregresso.
"""
import asyncio
import hashlib

from app.routers.fatture_module import crud
from app.services import fatture_identita as fi
from app.services import registrazione_contabile as rc
from app.services.sheets_document_store import MemorySheetsClient

XML = """<?xml version="1.0" encoding="utf-8"?>
<p:FatturaElettronica versione="FPR12" xmlns:p="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2">
<FatturaElettronicaHeader><DatiTrasmissione><IdTrasmittente><IdPaese>IT</IdPaese><IdCodice>01234567890</IdCodice></IdTrasmittente>
<ProgressivoInvio>1</ProgressivoInvio><FormatoTrasmissione>FPR12</FormatoTrasmissione><CodiceDestinatario>0000000</CodiceDestinatario></DatiTrasmissione>
<CedentePrestatore><DatiAnagrafici><IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>04911190488</IdCodice></IdFiscaleIVA>
<Anagrafica><Denominazione>ARVAL SERVICE LEASE ITALIA SPA</Denominazione></Anagrafica><RegimeFiscale>RF01</RegimeFiscale></DatiAnagrafici>
<Sede><Indirizzo>Via X</Indirizzo><CAP>50100</CAP><Comune>Firenze</Comune><Nazione>IT</Nazione></Sede></CedentePrestatore>
<CessionarioCommittente><DatiAnagrafici><IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>04523831214</IdCodice></IdFiscaleIVA>
<Anagrafica><Denominazione>CERALDI GROUP SRL</Denominazione></Anagrafica></DatiAnagrafici>
<Sede><Indirizzo>Piazza Carita 14</Indirizzo><CAP>80134</CAP><Comune>Napoli</Comune><Nazione>IT</Nazione></Sede></CessionarioCommittente>
</FatturaElettronicaHeader>
<FatturaElettronicaBody><DatiGenerali><DatiGeneraliDocumento><TipoDocumento>TD01</TipoDocumento><Divisa>EUR</Divisa>
<Data>2026-06-11</Data><Numero>FT0014095324</Numero><ImportoTotaleDocumento>163.56</ImportoTotaleDocumento></DatiGeneraliDocumento></DatiGenerali>
<DatiBeniServizi><DettaglioLinee><NumeroLinea>1</NumeroLinea><Descrizione>Noleggio</Descrizione><Quantita>1.00</Quantita>
<PrezzoUnitario>134.07</PrezzoUnitario><PrezzoTotale>134.07</PrezzoTotale><AliquotaIVA>22.00</AliquotaIVA></DettaglioLinee>
<DatiRiepilogo><AliquotaIVA>22.00</AliquotaIVA><ImponibileImporto>134.07</ImponibileImporto><Imposta>29.49</Imposta></DatiRiepilogo></DatiBeniServizi>
</FatturaElettronicaBody></p:FatturaElettronica>"""
HASH = hashlib.sha256(XML.encode("utf-8")).hexdigest()


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _db(nome):
    return MemorySheetsClient()[nome]


def _legacy(id_="leg-1"):
    # forma reale delle righe legacy 2026 (source xml_import, 14/09/2026)
    return {"id": id_, "source": "xml_import", "numero": "FT0014095324",
            "numero_documento": "FT0014095324", "data_documento": "2026-06-11",
            "data": "2026-06-11", "importo_totale": 163.56, "totale": 163.56,
            "iva": 29.49, "imponibile": 134.07,
            "fornitore": "ARVAL SERVICE LEASE ITALIA SPA", "stato": "pagata",
            "fattura_allegata": XML, "legacy_source_table": "fatture",
            "created_at": "2026-09-14T05:27:06+00:00"}


def _drive(id_="drv-1", **extra):
    return {"id": id_, "source": "google_drive", "status": "imported",
            "invoice_key": "FT0014095324_04911190488_2026-06-11",
            "invoice_number": "FT0014095324", "supplier_vat": "04911190488",
            "supplier_name": "ARVAL SERVICE LEASE ITALIA SPA",
            "invoice_date": "2026-06-11", "total_amount": 163.56, "iva": 29.49,
            "imponibile": 134.07, "iva_detraibile": 29.49, "centro_costo_id": "noleggi",
            "xml_raw": XML, "content_hash": HASH,
            "created_at": "2026-09-15T10:00:00+00:00", **extra}


def test_identita_dall_xml_senza_sovrascrivere_i_dati_presenti():
    patch = fi.patch_identita_da_xml(_legacy())
    assert patch["invoice_key"] == "FT0014095324_04911190488_2026-06-11"
    assert patch["supplier_vat"] == "04911190488"
    assert patch["content_hash"] == HASH
    assert patch["invoice_number"] == "FT0014095324" and patch["invoice_date"] == "2026-06-11"
    assert patch["total_amount"] == 163.56 and patch["xml_raw"] == XML
    # i campi gia' valorizzati (iva, imponibile) non vengono toccati
    assert "iva" not in patch and "imponibile" not in patch
    # una fattura gia' canonica non produce nessuna patch
    assert fi.patch_identita_da_xml(_drive()) is None
    # senza XML non si inventa nulla
    senza = _legacy(); senza.pop("fattura_allegata")
    assert fi.patch_identita_da_xml(senza) is None


def test_bonifica_archivia_il_doppione_legacy_e_storna_la_sua_scrittura(monkeypatch):
    db = _db("identita-bonifica")
    monkeypatch.setattr(crud.Database, "get_db", lambda: db)

    async def scenario():
        await db["invoices"].insert_many([_legacy(), _drive()])
        # entrambe le copie erano finite nel libro giornale (caso reale: 9 fatture)
        r_leg = await rc.registra_fattura(db, {**_legacy(), "iva_detraibile": 29.49,
                                               "total_amount": 163.56, "invoice_date": "2026-06-11"})
        r_drv = await rc.registra_fattura(db, _drive())
        assert r_leg["stato"] == "registrato" and r_drv["stato"] == "registrato"

        primo = await fi.bonifica_identita_fatture(db)
        secondo = await fi.bonifica_identita_fatture(db)
        leg = await db["invoices"].find_one({"id": "leg-1"})
        drv = await db["invoices"].find_one({"id": "drv-1"})
        movimenti = await db["movimenti_contabili"].find({}).to_list(20)
        return primo, secondo, leg, drv, movimenti

    primo, secondo, leg, drv, movimenti = _run(scenario())

    assert primo["identita"]["normalizzate"] == 1
    assert primo["dedup"]["fatture_archiviate"] == 1
    assert primo["dedup"]["scritture_stornate"] == 1
    # la copia Drive (registrata, con XML e classificazione) resta canonica
    assert drv["status"] == "imported" and drv["registrata_contabilita"] is True
    assert leg["status"] == "archived" and leg["duplicate_of"] == "drv-1"
    assert leg["invoice_key"] == drv["invoice_key"] and leg["content_hash"] == HASH
    assert leg["registrata_contabilita"] is False
    assert leg["registrazione_contabile_esito"]["stato"] == "stornato"
    # partita doppia: l'originale del doppione resta, marcata stornata, e
    # nasce lo storno con DARE/AVERE invertiti; la scrittura Drive e' intatta
    per_tipo = {}
    for m in movimenti:
        per_tipo.setdefault(m["tipo"], []).append(m)
    assert len(per_tipo["fattura_acquisto"]) == 2 and len(per_tipo["storno_fattura_acquisto"]) == 1
    originale_leg = next(m for m in per_tipo["fattura_acquisto"] if m["fattura_id"] == "leg-1")
    storno = per_tipo["storno_fattura_acquisto"][0]
    assert originale_leg["stato"] == "stornato" and originale_leg["stornato_da"] == storno["id"]
    assert storno["storno_di"] == originale_leg["id"]
    assert storno["totale_dare"] == originale_leg["totale_avere"]
    assert storno["totale_avere"] == originale_leg["totale_dare"]
    assert storno["idempotency_key"] == "reg:storno-fattura:leg-1"
    dare = sum(float(r["dare"]) for m in movimenti for r in m["righe"])
    avere = sum(float(r["avere"]) for m in movimenti for r in m["righe"])
    assert round(dare, 2) == round(avere, 2)
    # idempotenza: al secondo giro non c'e' piu' nulla da fare
    assert secondo["identita"]["normalizzate"] == 0
    assert secondo["dedup"]["fatture_archiviate"] == 0
    assert secondo["storni"]["stornate"] == 0


def test_pregresso_esclude_archivio_storico_e_storna_chi_era_entrato():
    db = _db("identita-archivio")

    async def scenario():
        await db["invoices"].insert_many([
            {"id": "st-2025", "status": "archiviata", "stato_import": "archivio_storico",
             "invoice_date": "2025-03-01", "total_amount": 100.0, "iva": 0,
             "invoice_number": "9", "supplier_vat": "X"},
            {"id": "att-2026", "status": "imported", "invoice_date": "2026-03-01",
             "total_amount": 50.0, "iva": 0, "invoice_number": "10", "supplier_vat": "X"},
        ])
        esito = await rc.registra_pregresso(db, dry_run=False)
        # simula la registrazione fatta per errore prima del filtro
        await rc.registra_fattura(db, {"id": "st-2025", "total_amount": 100.0, "iva": 0,
                                       "invoice_date": "2025-03-01"})
        storni = await fi.storna_registrazioni_non_ammesse(db)
        st = await db["invoices"].find_one({"id": "st-2025"})
        di_nuovo = await fi.storna_registrazioni_non_ammesse(db)
        return esito, storni, st, di_nuovo

    esito, storni, st, di_nuovo = _run(scenario())
    assert esito["fatture"]["fatture_processate"] == 1 and esito["registrate"] == 1
    assert storni["da_stornare"] == 1 and storni["stornate"] == 1
    assert st["registrata_contabilita"] is False
    assert "archivio storico" in st["registrazione_contabile_esito"]["motivo"]
    assert di_nuovo["da_stornare"] == 0


def test_storno_e_idempotente_e_salta_chi_non_ha_scritture():
    db = _db("identita-storno")

    async def scenario():
        await db["invoices"].insert_one({"id": "f1", "total_amount": 10.0, "iva": 0,
                                         "invoice_date": "2026-01-05"})
        await rc.registra_fattura(db, {"id": "f1", "total_amount": 10.0, "iva": 0,
                                       "invoice_date": "2026-01-05"})
        a = await rc.storna_registrazione_fattura(db, "f1", "prova")
        b = await rc.storna_registrazione_fattura(db, "f1", "prova")
        c = await rc.storna_registrazione_fattura(db, "mai-registrata", "prova")
        n = await db["movimenti_contabili"].count_documents({})
        return a, b, c, n

    a, b, c, n = _run(scenario())
    assert a["stato"] == "stornato" and b["stato"] == "gia_stornato" and b["storno_id"] == a["storno_id"]
    assert c["stato"] == "saltato" and n == 2


def test_router_avvia_in_background_e_dry_run_sincrono(monkeypatch):
    from app.routers.invoices import invoices_main as router_mod

    db = _db("identita-router")
    monkeypatch.setattr(router_mod.Database, "get_db", staticmethod(lambda: db))

    async def scenario():
        await db["invoices"].insert_one(_legacy())
        dry = await router_mod.bonifica_identita_fatture_endpoint(dry_run=True, _admin={})
        leg_dopo_dry = await db["invoices"].find_one({"id": "leg-1"})
        avvio = await router_mod.bonifica_identita_fatture_endpoint(dry_run=False, _admin={})
        await fi._task
        stato = await router_mod.stato_bonifica_identita_fatture(_admin={})
        leg = await db["invoices"].find_one({"id": "leg-1"})
        return dry, leg_dopo_dry, avvio, stato, leg

    dry, leg_dopo_dry, avvio, stato, leg = _run(scenario())
    assert dry["dry_run"] is True and dry["identita"]["normalizzate"] == 1
    assert "invoice_key" not in leg_dopo_dry  # il dry-run non scrive
    assert avvio == {"status": "started", "message": "Bonifica identita' fatture avviata"}
    assert stato["stato"] == "completato" and stato["in_corso"] is False
    assert stato["risultato"]["identita"]["normalizzate"] == 1
    assert leg["invoice_key"] == "FT0014095324_04911190488_2026-06-11"


def test_una_scrittura_in_timeout_non_ferma_la_normalizzazione():
    """17/09/2026: in produzione un solo gc_upsert_documents in timeout
    faceva abortire l'intero giro (le fatture dopo restavano senza identita')."""
    db = MemorySheetsClient()["test"]
    _run(db[fi.COLL].insert_many([_legacy("leg-1"), _legacy("leg-2")]))
    tabella = db[fi.COLL]
    originale = tabella.update_one

    async def update_one(selector, update, *args, **kwargs):
        if selector.get("id") == "leg-1":
            raise RuntimeError("Supabase RPC gc_upsert_documents fallita (HTTP 500): statement timeout")
        return await originale(selector, update, *args, **kwargs)

    tabella.update_one = update_one
    esito = _run(fi.normalizza_fatture_senza_identita(db, pausa=0))

    assert esito["normalizzate"] == 1
    assert len(esito["errori"]) == 1 and "leg-1" in esito["errori"][0]
    assert _run(tabella.find_one({"id": "leg-2"}))["invoice_key"] == "FT0014095324_04911190488_2026-06-11"
    assert not _run(tabella.find_one({"id": "leg-1"})).get("invoice_key")


# --- 17/09/2026: impronta del contenuto (42 collisioni per un byte di BOM) ---

XML_BOM = "﻿" + XML
XML_CRLF = XML.replace("\n", "\r\n")
XML_ALTRO = XML.replace("<Numero>FT0014095324</Numero>", "<Numero>FT0014095325</Numero>")


def test_impronta_contenuto_insensibile_a_bom_a_capo_e_codifica():
    base = fi.impronta_contenuto_fattura(XML)
    assert base and base.startswith("c:")
    assert fi.impronta_contenuto_fattura(XML_BOM) == base
    assert fi.impronta_contenuto_fattura(XML_CRLF) == base
    assert fi.impronta_contenuto_fattura(XML.replace('encoding="utf-8"', 'encoding="UTF-8"')) == base
    # i byte del file invece differiscono: era questo a bloccare la dedup
    assert hashlib.sha256(XML_BOM.encode("utf-8")).hexdigest() != HASH
    # contenuto diverso = impronta diversa; XML illeggibile = nessuna impronta
    assert fi.impronta_contenuto_fattura(XML_ALTRO) != base
    assert fi.impronta_contenuto_fattura("<html>no</html>") is None
    assert fi.impronta_contenuto_fattura("<p:FatturaElettronica><rotto") is None
    assert fi.impronta_contenuto_fattura(None) is None
    # anche l'identita' dall'XML la calcola
    assert fi.patch_identita_da_xml(_legacy())["content_hash_canonico"] == base


def test_normalizza_impronte_marca_chi_non_ha_xml_e_non_lo_ritenta():
    db = _db("impronte-backfill")

    async def scenario():
        drv = _drive(); drv.pop("content_hash_canonico", None)
        senza = {"id": "no-xml", "status": "imported", "invoice_number": "1",
                 "supplier_vat": "X", "invoice_date": "2026-01-01"}
        await db["invoices"].insert_many([drv, senza])
        primo = await fi.normalizza_impronte_canoniche(db, pausa=0)
        secondo = await fi.normalizza_impronte_canoniche(db, pausa=0)
        return primo, secondo, await db["invoices"].find_one({"id": "drv-1"}), \
            await db["invoices"].find_one({"id": "no-xml"})

    primo, secondo, drv, senza = _run(scenario())
    assert primo["candidate"] == 2 and primo["calcolate"] == 1 and primo["senza_xml"] == 1
    assert drv["content_hash_canonico"] == fi.impronta_contenuto_fattura(XML)
    assert senza["senza_xml_leggibile"] is True
    assert secondo["candidate"] == 0


def test_dedup_chiude_la_collisione_legacy_drive_che_differisce_di_un_byte(monkeypatch):
    """Caso reale (42 coppie): stessa fattura, la copia legacy con l'XML con
    BOM, la copia Drive importata come «collisione» perche' lo sha256 dei
    byte era diverso. La dedup deve archiviare il doppione, chiudere la
    collisione sulla copia tenuta e risolvere l'avviso."""
    db = _db("impronte-collisione")
    monkeypatch.setattr(crud.Database, "get_db", lambda: db)

    async def scenario():
        legacy = _legacy(); legacy["fattura_allegata"] = XML_BOM
        legacy["identity_collision_with_ids"] = ["drv-1"]
        legacy["duplicate_review_required"] = True
        drive = _drive(status="da_verificare", stato_import="collisione_identita_da_verificare",
                       stato_derivati="bloccato_collisione_identita",
                       duplicate_review_required=True, identity_collision_with_ids=["leg-1"])
        await db["invoices"].insert_many([legacy, drive])
        await db["alerts"].insert_one({"codice": "FATTURA_IDENTITA_DA_VERIFICARE",
                                       "entita_id": "drv-1", "stato": "aperto"})
        esito = await fi.bonifica_identita_fatture(db)
        return esito, await db["invoices"].find_one({"id": "leg-1"}), \
            await db["invoices"].find_one({"id": "drv-1"}), \
            await db["alerts"].find_one({"entita_id": "drv-1"})

    esito, leg, drv, alert = _run(scenario())
    assert esito["identita"]["normalizzate"] == 1
    assert esito["impronte"]["calcolate"] == 1          # la copia Drive
    assert esito["dedup"]["fatture_archiviate"] == 1
    assert esito["dedup"]["collisioni_chiuse"] == 1
    assert leg["content_hash"] != drv["content_hash"]  # byte diversi...
    assert leg["content_hash_canonico"] == drv["content_hash_canonico"]  # ...stesso contenuto
    assert leg["status"] == "archived" and leg["duplicate_of"] == "drv-1"
    assert drv["status"] == "imported" and drv["stato_import"] == "attivo"
    assert drv["stato_derivati"] == "da_ricalcolare"
    assert drv["duplicate_review_required"] is False and drv["identity_collision_with_ids"] == []
    assert alert["stato"] == "risolto" and alert["resolved_by"] == "dedup_impronta_contenuto"


def test_dedup_non_chiude_la_collisione_con_una_fattura_ancora_attiva(monkeypatch):
    db = _db("impronte-collisione-aperta")
    monkeypatch.setattr(crud.Database, "get_db", lambda: db)

    async def scenario():
        legacy = _legacy(); legacy["fattura_allegata"] = XML_BOM
        drive = _drive(status="da_verificare", identity_collision_with_ids=["leg-1", "altra"],
                       duplicate_review_required=True)
        await db["invoices"].insert_many([legacy, drive])
        esito = await fi.bonifica_identita_fatture(db)
        return esito, await db["invoices"].find_one({"id": "drv-1"})

    esito, drv = _run(scenario())
    assert esito["dedup"]["fatture_archiviate"] == 1 and esito["dedup"]["collisioni_chiuse"] == 0
    assert drv["status"] == "da_verificare" and drv["duplicate_review_required"] is True
    assert drv["identity_collision_with_ids"] == ["altra"]


def test_import_riconosce_lo_stesso_originale_con_bom_diverso():
    from app.routers.invoices.fatture_upload import _same_documentary_original

    esistente = _legacy(); esistente["fattura_allegata"] = XML_BOM
    # la copia legacy non ha content_hash: il confronto passa dal contenuto
    assert _same_documentary_original(esistente, None, XML) is True
    assert _same_documentary_original(esistente, None, XML_CRLF) is True
    assert _same_documentary_original(esistente, None, XML_ALTRO) is False
    # anche con lo sha256 dei byte gia' calcolato (e diverso) non e' una collisione
    con_hash = _drive(content_hash=hashlib.sha256(XML_BOM.encode()).hexdigest(), xml_raw=XML_BOM)
    con_hash.pop("content_hash_canonico", None)
    assert _same_documentary_original(con_hash, None, XML) is True
