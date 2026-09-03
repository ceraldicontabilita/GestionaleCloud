"""Audit del commercialista 03/09/2026 §2, PR 8 — registrazione AUTOMATICA in
partita doppia all'import di fatture e corrispettivi.

Prima: `movimenti_contabili` in produzione aveva 0 scritture perche' il libro
giornale nasceva solo dal comando manuale "Registra fatture"; l'hook in
`fatture_upload.py` era dichiarato "DISATTIVATO". Ora l'import chiama il
motore unico `registrazione_contabile` (idempotente per documento, anche
tra processi grazie a `idempotency_key`) e il bilancio di verifica passa da
REGISTRO_VUOTO a QUADRA senza alcun comando manuale.
"""
import asyncio

import pytest

from app.routers.accounting.contabilita_gestionale import _bilancio_verifica_da_registro
from app.routers.invoices import fatture_upload as fu_mod
from app.routers.invoices.corrispettivi_helpers import ingest_corrispettivo_parsed
from app.services import event_bus
from app.services import registrazione_contabile as rc
from app.services.mapping_piano_conti import operativo_a_ufficiale
from app.services.sheets_document_store import MemorySheetsClient
from app.services.supabase_runtime_database import DocumentoDuplicatoRemoto


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _db(nome):
    return MemorySheetsClient()[nome]


def _parsed_corrispettivo(**extra):
    base = {
        "corrispettivo_key": "IT04523831214_2026-03-22_RT001_1",
        "data": "2026-03-22",
        "matricola_rt": "RT001",
        "id_dispositivo": "RT001",
        "totale": 4629.20,
        "totale_imponibile": 4208.36,
        "totale_iva": 420.84,
        "pagato_contanti": 1629.20,
        "pagato_elettronico": 3000.00,
    }
    base.update(extra)
    return base


def _parsed_fattura():
    return {
        "invoice_number": "77/2026",
        "invoice_date": "2026-03-10",
        "supplier_vat": "01234567890",
        "supplier_name": "Fornitore Latticini Srl",
        "total_amount": 122.0,
        "imponibile": 100.0,
        "iva": 22.0,
        "divisa": "EUR",
        "tipo_documento": "TD01",
        "fornitore": {},
        "cliente": {},
        "linee": [{"descrizione": "Latte fresco", "prezzo_totale": 100.0, "aliquota_iva": 22}],
        "riepilogo_iva": [],
        "causali": [],
    }


@pytest.fixture
def import_fattura_isolato(monkeypatch):
    """Import fattura reale (import_parsed_invoice) con i soli collaboratori
    esterni al perimetro del test sostituiti: anagrafica fornitore, prima
    nota provvisoria e riprocessamento estratto conto. L'event bus resta
    quello vero con il handler di classificazione (che scrive
    `iva_detraibile`): e' la condizione reale in cui gira l'hook."""
    async def fake_supplier(*_args, **_kwargs):
        return {"supplier_id": "FORN-1", "supplier_created": False, "metodo_pagamento": "banca"}

    async def nessuna_prima_nota(*_args, **_kwargs):
        return None

    async def nessun_riprocessamento(*_args, **_kwargs):
        return None

    monkeypatch.setattr(fu_mod, "ensure_supplier_exists", fake_supplier)
    monkeypatch.setattr(fu_mod, "auto_registra_prima_nota", nessuna_prima_nota)
    monkeypatch.setattr(fu_mod, "riprocessa_estratto_dopo_import_fattura", nessun_riprocessamento)

    from app.handlers.learning import handler_classifica_cdc
    handlers = event_bus._handlers.setdefault(event_bus.EventTypes.FATTURA_CREATED, [])
    handlers.append(handler_classifica_cdc)
    yield
    handlers.remove(handler_classifica_cdc)


def test_import_corrispettivo_e_fattura_alimentano_il_libro_giornale_e_il_bilancio_quadra(
    import_fattura_isolato,
):
    db = _db("pr8-e2e")

    async def scenario():
        prima = await _bilancio_verifica_da_registro(db, 2026, False)
        corr = await ingest_corrispettivo_parsed(db, _parsed_corrispettivo(), filename="rt.xml", source="xml")
        fatt = await fu_mod.import_parsed_invoice(db, _parsed_fattura(), "f.xml", "xml_upload")
        scritture = await db["movimenti_contabili"].find({}).to_list(100)
        dopo = await _bilancio_verifica_da_registro(db, 2026, True)
        corr_db = await db["corrispettivi"].find_one({"id": corr["corrispettivo_id"]})
        fatt_db = await db["invoices"].find_one({"id": fatt["id"]})
        return prima, corr, fatt, scritture, dopo, corr_db, fatt_db

    prima, corr, fatt, scritture, dopo, corr_db, fatt_db = _run(scenario())

    assert prima["stato"] == "REGISTRO_VUOTO"
    assert corr["action"] == "created" and fatt["status"] == "imported"

    # 2 scritture bilanciate, una per documento, con chiave idempotente
    assert len(scritture) == 2
    per_tipo = {s["tipo"]: s for s in scritture}
    assert set(per_tipo) == {"corrispettivo", "fattura_acquisto"}
    for s in scritture:
        assert round(s["totale_dare"], 2) == round(s["totale_avere"], 2) > 0
        assert s["idempotency_key"] in {
            f"reg:corrispettivo:{corr['corrispettivo_id']}", f"reg:fattura:{fatt['id']}",
        }
        # solo conti operativi con un corrispondente CEE ufficiale (regola del repo)
        for riga in s["righe"]:
            assert operativo_a_ufficiale(riga["conto_codice"]), riga
    assert per_tipo["corrispettivo"]["totale_dare"] == 4629.20
    assert per_tipo["fattura_acquisto"]["totale_avere"] == 122.0

    # flag sui documenti sorgente scritti dal motore, nessun esito negativo
    assert corr_db["registrato_contabilita"] is True
    assert corr_db["movimento_contabile_id"] == per_tipo["corrispettivo"]["id"]
    assert fatt_db["registrata_contabilita"] is True
    assert fatt_db["iva_detraibile"] == 22.0  # scritto dal handler di classificazione
    assert "registrazione_contabile_esito" not in fatt_db

    # bilancio di verifica: da REGISTRO_VUOTO a QUADRA, completezza ok
    assert dopo["stato"] == "QUADRA"
    assert dopo["quadratura"] is True
    assert dopo["completezza_registro"] == {
        "scritture_registrate": 2,
        "fatture_da_registrare": 0,
        "corrispettivi_da_registrare": 0,
        "documenti_da_registrare": 0,
        "completo": True,
    }
    assert dopo["totali"]["dare"] == dopo["totali"]["avere"] == round(4629.20 + 122.0, 2)


def test_stesso_corrispettivo_due_volte_produce_una_sola_scrittura():
    db = _db("pr8-idempotenza-corr")

    async def scenario():
        await ingest_corrispettivo_parsed(db, _parsed_corrispettivo(), filename="a.xml", source="xml")
        # stesso file ricaricato (duplicato) e stesso file con update_if_exists
        await ingest_corrispettivo_parsed(db, _parsed_corrispettivo(), filename="a.xml", source="xml")
        await ingest_corrispettivo_parsed(
            db, _parsed_corrispettivo(), filename="a.xml", source="xml", update_if_exists=True,
        )
        return await db["movimenti_contabili"].find({"tipo": "corrispettivo"}).to_list(10)

    scritture = _run(scenario())
    assert len(scritture) == 1


def test_stessa_fattura_due_volte_produce_una_sola_scrittura(import_fattura_isolato):
    db = _db("pr8-idempotenza-fatt")

    async def scenario():
        primo = await fu_mod.import_parsed_invoice(db, _parsed_fattura(), "f.xml", "xml_upload")
        secondo = await fu_mod.import_parsed_invoice(db, _parsed_fattura(), "f.xml", "xml_upload")
        # anche un secondo giro esplicito del motore sulla stessa fattura
        fattura = await db["invoices"].find_one({"id": primo["id"]})
        terzo = await rc.registra_documento_import(db, "fattura", fattura)
        return primo, secondo, terzo, await db["movimenti_contabili"].find({}).to_list(10)

    primo, secondo, terzo, scritture = _run(scenario())
    assert primo["status"] == "imported" and secondo["status"] == "duplicate"
    assert terzo["stato"] == "gia_registrato"
    assert len(scritture) == 1


def test_corrispettivo_provvisorio_senza_xml_non_entra_nel_giornale():
    db = _db("pr8-provvisorio")

    async def scenario():
        esito = await rc.registra_documento_import(db, "corrispettivo", {
            "id": "c-prov", "data": "2026-03-01", "totale": 500.0, "stato": "provvisorio",
        })
        return esito, await db["movimenti_contabili"].find({}).to_list(10)

    esito, scritture = _run(scenario())
    assert esito["stato"] == "rimandato"
    assert scritture == []


def test_hook_non_blocca_mai_l_import_e_annota_l_esito_sul_documento(monkeypatch):
    db = _db("pr8-hook-errore")

    async def esplode(*_args, **_kwargs):
        raise RuntimeError("motore contabile fuori uso")

    monkeypatch.setattr(rc, "registra_corrispettivo", esplode)

    async def scenario():
        await db["corrispettivi"].insert_one({"id": "c1", "data": "2026-03-02", "totale": 10.0})
        esito = await rc.registra_documento_import(db, "corrispettivo", {
            "id": "c1", "data": "2026-03-02", "totale": 10.0,
        })
        return esito, await db["corrispettivi"].find_one({"id": "c1"})

    esito, doc = _run(scenario())
    assert esito["stato"] == "errore"
    assert doc["registrazione_contabile_esito"]["stato"] == "errore"
    assert "fuori uso" in doc["registrazione_contabile_esito"]["motivo"]


def test_fattura_senza_iva_classificata_resta_da_verificare_e_lo_dice_sul_documento():
    db = _db("pr8-da-verificare")

    async def scenario():
        await db["invoices"].insert_one({
            "id": "F-noiva", "total_amount": 122.0, "iva": 22.0, "invoice_date": "2026-03-10",
        })
        esito = await rc.registra_documento_import(db, "fattura", {
            "id": "F-noiva", "total_amount": 122.0, "iva": 22.0, "invoice_date": "2026-03-10",
        })
        return esito, await db["invoices"].find_one({"id": "F-noiva"}), \
            await db["movimenti_contabili"].find({}).to_list(10)

    esito, doc, scritture = _run(scenario())
    assert esito["stato"] == "da_verificare"
    assert doc["registrazione_contabile_esito"]["motivo"] == "IVA detraibile non classificata"
    assert scritture == []


def test_importo_cambiato_dopo_la_registrazione_viene_segnalato_non_riscritto():
    db = _db("pr8-importo-cambiato")

    async def scenario():
        corr = {"id": "c-xml", "data": "2026-03-05", "totale": 100.0, "stato": "definitivo_xml"}
        await db["corrispettivi"].insert_one(dict(corr))
        primo = await rc.registra_documento_import(db, "corrispettivo", corr)
        secondo = await rc.registra_documento_import(db, "corrispettivo", {**corr, "totale": 130.0})
        return primo, secondo, await db["movimenti_contabili"].find({}).to_list(10), \
            await db["corrispettivi"].find_one({"id": "c-xml"})

    primo, secondo, scritture, doc = _run(scenario())
    assert primo["stato"] == "registrato"
    assert secondo["stato"] == "da_verificare"
    assert len(scritture) == 1 and scritture[0]["importo_totale"] == 100.0
    assert "130.00" in doc["registrazione_contabile_esito"]["motivo"]


def test_rifiuto_postgres_per_chiave_idempotente_non_crea_seconda_scrittura():
    """Due processi registrano la stessa fattura: Postgres rifiuta la seconda
    riga (indice unico su idempotency_key) e il runtime solleva
    DocumentoDuplicatoRemoto. Il motore deve rispondere `gia_registrato`
    con l'id esistente, senza toccare i saldi e senza propagare l'errore."""
    db = _db("pr8-chiave-remota")
    chiave = rc.chiave_idempotenza("fattura", "F-race")

    class _CollRifiuta:
        def __init__(self, inner):
            self.inner = inner

        async def insert_one(self, doc):
            raise DocumentoDuplicatoRemoto("movimenti_contabili", [{
                "id_rifiutato": doc.get("id"), "id_esistente": "MOV-ALTRO-PROCESSO",
                "idempotency_key": chiave,
                "documento_esistente": {"_id": "MOV-ALTRO-PROCESSO", "id": "MOV-ALTRO-PROCESSO",
                                        "tipo": "fattura_acquisto", "importo_totale": 100.0},
            }])

        def __getattr__(self, name):
            return getattr(self.inner, name)

    saldi_toccati = []

    async def _saldo(_db, codice, importo, verso):
        saldi_toccati.append((codice, importo, verso))

    import app.routers.accounting.piano_conti as pcmod

    class _DbWrap:
        def __getitem__(self, name):
            coll = db[name]
            return _CollRifiuta(coll) if name == "movimenti_contabili" else coll

    async def scenario(monkey_saldo):
        await db["invoices"].insert_one({"id": "F-race", "total_amount": 100.0, "iva": 0})
        return await rc.registra_fattura(_DbWrap(), {
            "id": "F-race", "total_amount": 100.0, "iva": 0, "invoice_date": "2026-01-05",
        })

    originale = pcmod.aggiorna_saldo_conto
    pcmod.aggiorna_saldo_conto = _saldo
    try:
        esito = _run(scenario(_saldo))
    finally:
        pcmod.aggiorna_saldo_conto = originale

    assert esito == {"stato": "gia_registrato", "movimento_id": "MOV-ALTRO-PROCESSO"}
    assert saldi_toccati == []
    fattura = _run(db["invoices"].find_one({"id": "F-race"}))
    assert fattura["movimento_contabile_id"] == "MOV-ALTRO-PROCESSO"


def test_registra_pregresso_dry_run_conta_senza_scrivere_ed_e_idempotente():
    db = _db("pr8-pregresso")

    async def scenario():
        await db["corrispettivi"].insert_many([
            {"id": "c1", "data": "2026-02-01", "totale": 110.0, "stato": "definitivo_xml"},
            {"id": "c-prov", "data": "2026-02-02", "totale": 50.0, "stato": "provvisorio"},
            {"id": "c-del", "data": "2026-02-03", "totale": 50.0, "entity_status": "deleted"},
        ])
        await db["invoices"].insert_many([
            {"id": "f1", "total_amount": 100.0, "iva": 0, "invoice_date": "2026-02-01"},
            {"id": "f-arch", "total_amount": 100.0, "iva": 0, "invoice_date": "2026-02-01",
             "status": "archived"},
        ])
        prova = await rc.registra_pregresso(db, dry_run=True)
        dopo_prova = await db["movimenti_contabili"].find({}).to_list(10)
        vero = await rc.registra_pregresso(db, dry_run=False)
        secondo = await rc.registra_pregresso(db, dry_run=False)
        return prova, dopo_prova, vero, secondo, await db["movimenti_contabili"].find({}).to_list(10)

    prova, dopo_prova, vero, secondo, scritture = _run(scenario())
    assert prova["dry_run"] is True and prova["da_registrare"] == 2 and prova["registrate"] == 0
    assert prova["corrispettivi"]["provvisori_esclusi"] == 1
    assert dopo_prova == []
    assert vero["registrate"] == 2
    assert secondo["registrate"] == 0 and secondo["errori"] == []
    assert len(scritture) == 2
