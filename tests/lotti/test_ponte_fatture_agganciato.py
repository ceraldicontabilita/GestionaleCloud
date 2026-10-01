"""Guardia: una fattura che entra nel gestionale alimenta anche Lotti.

Tre cose che non si tenevano, e che insieme hanno lasciato il magazzino di
Lotti fermo al 26/05/2026 mentre nel gestionale le fatture continuavano ad
arrivare.

**1. Due criteri diversi per «fattura attiva».** Il ponte guardava solo
`deleted`; il gestionale esclude anche `archived`/`archiviata`, l'archivio
storico e le collisioni di identita' ancora aperte. Il 20/09/2026 il ponte
vedeva **1.444** fatture del 2026 mentre le attive erano **889**: 555
archiviate in piu' (doppioni che la contabilita' aveva gia' scartato) e 46
collisioni non ancora decise, tutte pronte a diventare righe di magazzino.

**2. Il registro delle ricevute non verificava niente.** Diceva «presa» e
tanto bastava: svuotare le fatture operative di Lotti (ripopolamento da zero,
ripristino) lasciava il registro pieno, il ponte saltava tutto e il magazzino
non si rialimentava piu'.

**3. Nessun aggancio all'ingresso.** L'unico percorso era il giro dei 15
minuti sull'intero elenco dell'anno. Quando quel giro si e' fermato, i due
lati hanno smesso di parlarsi senza un errore.
"""
import asyncio

import pytest
from mongomock_motor import AsyncMongoMockClient
from unittest.mock import AsyncMock


def run(coro):
    return asyncio.run(coro)


# ── 1. Un solo criterio di «fattura attiva» ──────────────────────────────────

CASI_ATTIVA = [
    ("fattura normale", {"id": "f1", "status": "imported"}, True),
    ("cancellata", {"id": "f2", "status": "deleted"}, False),
    ("entita' cancellata", {"id": "f3", "entity_status": "deleted"}, False),
    ("flag deleted", {"id": "f4", "deleted": True}, False),
    ("archiviata (inglese)", {"id": "f5", "status": "archived"}, False),
    ("archiviata (italiano)", {"id": "f6", "status": "archiviata"}, False),
    ("archivio storico", {"id": "f7", "stato_import": "archivio_storico"}, False),
    ("collisione aperta", {"id": "f8", "duplicate_review_required": True}, False),
    ("collisione risolta", {"id": "f9", "duplicate_review_required": False}, True),
]


@pytest.mark.parametrize("caso,documento,atteso", CASI_ATTIVA, ids=[c[0] for c in CASI_ATTIVA])
def test_il_ponte_usa_lo_stesso_criterio_del_gestionale(caso, documento, atteso):
    from app.routers.lotti_integration import _attiva

    assert _attiva(documento) is atteso, (
        f"{caso}: il ponte la considera {'attiva' if not atteso else 'non attiva'} "
        "al contrario del gestionale. Un filtro parallelo manda a Lotti merce "
        "nata da documenti che la contabilita' ha gia' scartato."
    )


def test_le_due_grafie_dello_stato_archiviato_valgono_uguale():
    """Regola 13 di CLAUDE.md: in archivio convivono `archived` e `archiviata`."""
    from app.routers.lotti_integration import _attiva

    assert _attiva({"status": "ARCHIVIATA"}) is False, (
        "Il confronto deve essere insensibile alle maiuscole: una sola grafia "
        "conosciuta lascia passare documenti che doveva escludere."
    )


# ── 2. Il registro vale solo se la fattura c'e' ancora ───────────────────────

@pytest.fixture()
def ponte(monkeypatch):
    import app.lotti.routers.fatture as fatture
    import app.lotti.routers.gestionale_fatture as module

    database = AsyncMongoMockClient()["Gestionale_Test"]
    monkeypatch.setattr(module, "db", database)
    monkeypatch.setattr(fatture, "db", database)
    monkeypatch.setenv("GESTIONALECLOUD_API_URL", "https://gestionale.example")
    monkeypatch.setenv("LOTTI_INTEGRATION_KEY", "test-secret")
    return module, database


def _item(source_id="invoice-1", source_hash="hash-1"):
    return {
        "source_id": source_id, "source_hash": source_hash,
        "invoice_number": "42/A", "invoice_date": "2026-08-31",
        "supplier_name": "FORNITORE TEST SRL", "supplier_vat": "01234567890",
        "has_xml": True, "source": "gestionalecloud",
    }


def _ingresso_reale(ponte, monkeypatch, quantita=2, source_hash="hash-1", lines=None):
    """Motore XML vero, soli servizi di sottofondo sostituiti con fixture."""
    from app.database import Database
    module, database = ponte
    monkeypatch.setattr(Database, "db", database)
    item = {**_item(source_hash=source_hash), "lines": lines if lines is not None else [
        {"description": "FARINA FIXTURE", "quantity": quantita, "unit": "KG", "unit_price": 3, "line_total": quantita * 3},
        {"description": "ZUCCHERO FIXTURE", "quantity": 1, "unit": "KG", "unit_price": 4, "line_total": 4},
    ]}
    detail = {**item, "xml_raw": module._xml_from_projection(item)}
    monkeypatch.setattr(module, "_dettaglio_locale", AsyncMock(return_value=detail))
    monkeypatch.setattr(module, "_get_json", AsyncMock(return_value=detail))
    monkeypatch.setattr(module, "_elenco", AsyncMock(return_value=([item], 1)))
    monkeypatch.setattr("app.lotti.routers.pipeline.esegui_pipeline_post_import", AsyncMock())
    monkeypatch.setattr("app.lotti.routers.aggiornamento_ricette.aggiorna_ricette_da_fattura",
                        AsyncMock(return_value={"aggiornate": 0}))
    return item, detail


def test_sync_collega_ricette_una_volta_senza_match_fuzzy(ponte, monkeypatch):
    module, _database = ponte
    _ingresso_reale(ponte, monkeypatch)

    fuzzy = AsyncMock(side_effect=AssertionError("il sync non deve usare il matcher fuzzy"))
    canonico = AsyncMock(return_value={"ingredienti_collegati": 4})
    monkeypatch.setattr(
        "app.lotti.routers.aggiornamento_ricette.aggiorna_ricette_da_fattura", fuzzy
    )
    monkeypatch.setattr(
        "app.lotti.routers.ricette.collega_ingredienti_canonico", canonico
    )

    esito = run(module.esegui_sync_gestionale(anno=2026, massimo=40, anteprima=False))

    assert esito["importate"] == 1
    assert esito["ingredienti_ricette_collegati"] == 4
    fuzzy.assert_not_awaited()
    canonico.assert_awaited_once()


@pytest.mark.parametrize("retry", ["evento", "sync"])
def test_carico_bar_parziale_non_terminalizza_e_retry_completa_per_riga(ponte, monkeypatch, retry):
    module, database = ponte
    import app.lotti.routers.magazzino_bar as bar
    monkeypatch.setattr(bar, "db", database)
    lines = [
        {"description": "ACQUA FIXTURE", "quantity": 2, "unit": "PZ", "unit_price": 3, "line_total": 6},
        {"description": "BIRRA FIXTURE", "quantity": 1, "unit": "PZ", "unit_price": 4, "line_total": 4},
    ]
    _ingresso_reale(ponte, monkeypatch, lines=lines)
    run(database.magazzino_bar_prodotti.insert_many([
        {"id": "bar-acqua", "nome": "ACQUA FIXTURE", "stock": 0},
        {"id": "bar-birra", "nome": "BIRRA FIXTURE", "stock": 0},
    ]))
    collection_type = type(database.magazzino_bar_movimenti)
    find_one = collection_type.find_one
    guasto = {"attivo": True}

    async def leggi(self, query=None, *args, **kwargs):
        if (guasto["attivo"] and self.name == "magazzino_bar_movimenti"
                and str((query or {}).get("fattura_riga_key", "")).endswith(":1")):
            raise RuntimeError("guasto fixture lettura prima del carico seconda riga")
        return await find_one(self, query, *args, **kwargs)

    monkeypatch.setattr(collection_type, "find_one", leggi)
    primo = run(module.alimenta_lotti_da_fattura("invoice-1"))
    assert primo["stato"] == "errore"
    assert run(database.fatture.find_one({}))["haccp_import_completo"] is False
    assert run(database.magazzino_bar_movimenti.count_documents({})) == 1
    assert run(database.gestionale_fatture_ricevute.count_documents({})) == 0
    guasto["attivo"] = False
    if retry == "evento":
        assert run(module.alimenta_lotti_da_fattura("invoice-1"))["stato"] == "alimentata"
    else:
        assert run(module.esegui_sync_gestionale(anno=2026, anteprima=False))["ok"] is True
    assert run(database.magazzino_bar_prodotti.find_one({"id": "bar-acqua"}))["stock"] == 2
    assert run(database.magazzino_bar_prodotti.find_one({"id": "bar-birra"}))["stock"] == 1
    assert run(database.magazzino_bar_movimenti.count_documents({})) == 2
    assert run(database.fatture.find_one({}))["haccp_import_completo"] is True
    assert run(module.alimenta_lotti_da_fattura("invoice-1"))["stato"] == "alimentata"
    assert run(database.magazzino_bar_movimenti.count_documents({})) == 2


@pytest.mark.parametrize("interruzione", ["eccezione", "arresto"])
def test_bar_stock_senza_movimento_blocca_retry_anche_se_processo_si_interrompe(ponte, monkeypatch, interruzione):
    module, database = ponte
    import app.lotti.routers.magazzino_bar as bar
    monkeypatch.setattr(bar, "db", database)
    _ingresso_reale(ponte, monkeypatch, lines=[
        {"description": "ACQUA FIXTURE", "quantity": 2, "unit": "PZ", "unit_price": 3, "line_total": 6},
    ])
    run(database.magazzino_bar_prodotti.insert_one({"id": "bar-acqua", "nome": "ACQUA FIXTURE", "stock": 0}))
    collection_type = type(database.magazzino_bar_movimenti)
    insert = collection_type.insert_one
    guasto = {"attivo": True}

    class ArrestoFixture(BaseException):
        pass

    async def inserisci(self, *args, **kwargs):
        if guasto["attivo"] and self.name == "magazzino_bar_movimenti":
            if interruzione == "arresto":
                raise ArrestoFixture()
            raise RuntimeError("guasto fixture registro dopo incremento stock")
        return await insert(self, *args, **kwargs)

    monkeypatch.setattr(collection_type, "insert_one", inserisci)
    if interruzione == "arresto":
        with pytest.raises(ArrestoFixture):
            run(module.alimenta_lotti_da_fattura("invoice-1"))
    else:
        assert run(module.alimenta_lotti_da_fattura("invoice-1"))["stato"] == "errore"
    doc = run(database.fatture.find_one({}))
    assert doc["haccp_import_ambiguo"] is True
    assert doc["haccp_stock_riga_in_corso"].endswith(":0")
    assert doc["haccp_import_completo"] is False
    assert run(database.magazzino_bar_prodotti.find_one({"id": "bar-acqua"}))["stock"] == 2
    assert run(database.magazzino_bar_movimenti.count_documents({})) == 0
    assert run(database.gestionale_fatture_ricevute.count_documents({})) == 0
    guasto["attivo"] = False
    assert run(module.alimenta_lotti_da_fattura("invoice-1"))["stato"] == "errore"
    assert run(module.esegui_sync_gestionale(anno=2026, anteprima=False))["ok"] is False
    assert run(database.magazzino_bar_prodotti.find_one({"id": "bar-acqua"}))["stock"] == 2
    assert run(database.magazzino_bar_movimenti.count_documents({})) == 0
    import app.lotti.routers.fatture as fatture
    old_doc = run(database.fatture.find_one({}))
    # Stesso XML e XML modificato: anche il motore diretto deve fermarsi
    # prima di sovrascrivere flag, documento o quantita'.
    xml_mutato = module._xml_from_projection({**_item(), "lines": [
        {"description": "ACQUA FIXTURE", "quantity": 5, "unit": "PZ", "unit_price": 3, "line_total": 15},
    ]})
    for xml in (old_doc["xml_raw"], xml_mutato):
        direct = run(fatture.importa_fattura_xml([fatture._UF("fixture-diretta.xml", xml.encode())]))
        assert direct["fatture_processate"] == 0 and direct["errori"]
        assert run(database.fatture.find_one({}))["xml_raw"] == old_doc["xml_raw"]
        assert run(database.fatture.find_one({}))["haccp_import_ambiguo"] is True
        assert run(database.magazzino_bar_prodotti.find_one({"id": "bar-acqua"}))["stock"] == 2
        assert run(database.magazzino_bar_movimenti.count_documents({})) == 0


@pytest.mark.parametrize("retry", ["evento", "sync"])
def test_import_parziale_reale_retry_completa_senza_raddoppiare_lotti(ponte, monkeypatch, retry):
    module, database = ponte
    _ingresso_reale(ponte, monkeypatch)
    collection_type = type(database.lotti_fornitori)
    insert = collection_type.insert_one
    guasto = {"attivo": True}

    async def inserisci(self, document, *args, **kwargs):
        if (guasto["attivo"] and self.name == "lotti_fornitori"
                and document.get("prodotto_nome") == "ZUCCHERO FIXTURE"):
            raise RuntimeError("guasto fixture sulla seconda riga")
        return await insert(self, document, *args, **kwargs)

    monkeypatch.setattr(collection_type, "insert_one", inserisci)
    primo = run(module.alimenta_lotti_da_fattura("invoice-1"))
    assert primo["stato"] == "errore"
    assert "guasto fixture" in primo["motivo"]
    assert run(database.fatture.find_one({}))["haccp_import_completo"] is False
    assert run(database.lotti_fornitori.count_documents({})) == 1
    assert run(database.gestionale_fatture_ricevute.count_documents({})) == 0
    assert run(module._source_id_gia_presi()) == {}

    guasto["attivo"] = False
    if retry == "evento":
        assert run(module.alimenta_lotti_da_fattura("invoice-1"))["stato"] == "alimentata"
    else:
        secondo = run(module.esegui_sync_gestionale(anno=2026, anteprima=False))
        assert secondo["ok"] is True and secondo["importate"] == 1
    assert run(database.fatture.find_one({}))["haccp_import_completo"] is True
    assert run(database.fatture.count_documents({})) == 1
    assert run(database.lotti_fornitori.count_documents({})) == 2
    assert run(database.gestionale_fatture_ricevute.count_documents({})) == 1
    assert run(module._source_id_gia_presi()) == {"invoice-1": "hash-1"}
    terzo = run(module.esegui_sync_gestionale(anno=2026, anteprima=False))
    assert terzo["gia_ricevute"] == 1 and terzo["importate"] == 0
    assert run(database.lotti_fornitori.count_documents({})) == 2


@pytest.mark.parametrize("ingresso", ["evento", "sync"])
def test_xml_mutato_regola_unica_preserva_documento_e_quantita(ponte, monkeypatch, ingresso):
    module, database = ponte
    _ingresso_reale(ponte, monkeypatch)
    assert run(module.alimenta_lotti_da_fattura("invoice-1"))["stato"] == "alimentata"
    prima = run(database.fatture.find_one({}))
    lotti_prima = run(database.lotti_fornitori.find({}, {"_id": 0}).to_list(10))
    _ingresso_reale(ponte, monkeypatch, quantita=5, source_hash="hash-mutato")
    if ingresso == "evento":
        assert run(module.alimenta_lotti_da_fattura("invoice-1"))["stato"] == "conflitto_hash"
    else:
        result = run(module.esegui_sync_gestionale(anno=2026, anteprima=False))
        assert result["ok"] is False and len(result["conflitti"]) == 1
    dopo = run(database.fatture.find_one({}))
    assert dopo["xml_raw"] == prima["xml_raw"]
    assert dopo["prodotti"] == prima["prodotti"]
    assert run(database.lotti_fornitori.find({}, {"_id": 0}).to_list(10)) == lotti_prima
    receipt = run(database.gestionale_fatture_ricevute.find_one({"source_id": "invoice-1"}))
    assert receipt["stato"] == "conflitto_hash"
    assert receipt["source_hash"] == "hash-1"
    assert receipt["nuovo_source_hash"] == "hash-mutato"


def test_evento_metadata_mutati_xml_identico_riallinea_senza_nuovi_lotti(ponte, monkeypatch):
    module, database = ponte
    _ingresso_reale(ponte, monkeypatch)
    run(module.alimenta_lotti_da_fattura("invoice-1"))
    _ingresso_reale(ponte, monkeypatch, source_hash="metadata-mutati")
    assert run(module.alimenta_lotti_da_fattura("invoice-1"))["stato"] == "alimentata"
    assert run(database.lotti_fornitori.count_documents({})) == 2
    assert run(database.fatture.find_one({}))["gestionale_source_hash"] == "metadata-mutati"
    assert run(module._source_id_gia_presi()) == {"invoice-1": "metadata-mutati"}


def test_una_fattura_sparita_da_lotti_torna_fra_quelle_da_prendere(ponte, monkeypatch):
    module, database = ponte

    async def elenco(_client, _anno):
        return [_item()], 1

    monkeypatch.setattr(module, "_elenco", elenco)
    # Il registro dice «presa», ma la fattura operativa non c'e' piu'.
    run(database.gestionale_fatture_ricevute.insert_one({
        "source_id": "invoice-1", "source_hash": "hash-1",
        "stato": "importata", "fattura_id": "fattura-cancellata",
    }))

    esito = run(module.esegui_sync_gestionale(anno=2026, anteprima=True))

    assert esito["gia_ricevute"] == 0, (
        "Il ponte l'ha saltata fidandosi del registro: se si svuota Lotti, il "
        "magazzino non si rialimenta piu' e nessuno capisce perche'."
    )
    assert esito["importabili"] == 1


def test_una_fattura_ancora_presente_non_si_rilavora(ponte, monkeypatch):
    """L'altro lato: se c'e' davvero, il ponte non rifa' il lavoro."""
    module, database = ponte

    async def elenco(_client, _anno):
        return [_item()], 1

    monkeypatch.setattr(module, "_elenco", elenco)
    run(database.fatture.insert_one({"id": "fattura-viva", "numero_fattura": "42/A"}))
    run(database.gestionale_fatture_ricevute.insert_one({
        "source_id": "invoice-1", "source_hash": "hash-1",
        "stato": "importata", "fattura_id": "fattura-viva",
    }))

    esito = run(module.esegui_sync_gestionale(anno=2026, anteprima=True))

    assert esito["gia_ricevute"] == 1
    assert esito["importabili"] == 0


def test_ricevuta_senza_fattura_non_blocca_il_recupero(ponte, monkeypatch):
    module, database = ponte

    async def elenco(_client, _anno):
        return [_item()], 1

    monkeypatch.setattr(module, "_elenco", elenco)
    run(database.gestionale_fatture_ricevute.insert_one({
        "source_id": "invoice-1", "source_hash": "hash-1",
        "stato": "importata", "fattura_id": None,
    }))

    esito = run(module.esegui_sync_gestionale(anno=2026, anteprima=True))

    assert esito["gia_ricevute"] == 0
    assert esito["importabili"] == 1


def test_evento_import_fallito_resta_recuperabile_e_retry_non_duplica(ponte, monkeypatch):
    module, database = ponte
    import app.lotti.routers.fatture as fatture

    async def dettaglio(_source_id):
        return {**_item(), "xml_raw": "<FatturaElettronica/>"}

    async def importa_fallita(_files, **_kwargs):
        return {"fatture_processate": 0, "errori": ["XML non elaborabile"]}

    monkeypatch.setattr(module, "_dettaglio_locale", dettaglio)
    monkeypatch.setattr(fatture, "importa_fattura_xml", importa_fallita)

    esito = run(module.alimenta_lotti_da_fattura("invoice-1"))
    assert esito["stato"] == "errore"
    assert "XML non elaborabile" in esito["motivo"]
    assert run(database.gestionale_fatture_ricevute.count_documents({})) == 0
    assert run(module._source_id_gia_presi()) == {}

    async def importa_riprovata(_files, **_kwargs):
        await database.fatture.update_one(
            {"id": "lotti-recuperata"},
            {"$set": {"numero_fattura": "42/A", "piva": "01234567890"}},
            upsert=True,
        )
        return {"fatture_processate": 1, "fatture_ids": ["lotti-recuperata"]}

    monkeypatch.setattr(fatture, "importa_fattura_xml", importa_riprovata)
    assert run(module.alimenta_lotti_da_fattura("invoice-1"))["stato"] == "alimentata"
    assert run(module.alimenta_lotti_da_fattura("invoice-1"))["stato"] == "alimentata"
    assert run(database.fatture.count_documents({})) == 1
    assert run(database.gestionale_fatture_ricevute.count_documents({})) == 1
    assert run(module._source_id_gia_presi()) == {"invoice-1": "hash-1"}


@pytest.mark.parametrize("ingresso", ["evento", "sync"])
def test_id_restituito_senza_documento_non_diventa_ricevuta(ponte, monkeypatch, ingresso):
    module, database = ponte
    import app.lotti.routers.fatture as fatture

    async def dettaglio(*_args, **_kwargs):
        return {**_item(), "xml_raw": "<FatturaElettronica/>"}

    async def elenco(_client, _anno):
        return [_item()], 1

    async def importa(_files, **_kwargs):
        return {"fatture_processate": 1, "fatture_ids": ["fattura-inesistente"]}

    monkeypatch.setattr(module, "_dettaglio_locale", dettaglio)
    monkeypatch.setattr(module, "_get_json", dettaglio)
    monkeypatch.setattr(module, "_elenco", elenco)
    monkeypatch.setattr(fatture, "importa_fattura_xml", importa)
    if ingresso == "evento":
        esito = run(module.alimenta_lotti_da_fattura("invoice-1"))
        assert esito["stato"] == "errore"
    else:
        esito = run(module.esegui_sync_gestionale(anno=2026, anteprima=False))
        assert esito["ok"] is False
        assert esito["importate"] == 0
    assert run(database.gestionale_fatture_ricevute.count_documents({})) == 0
    assert run(database.fatture.count_documents({})) == 0


# ── 3. L'aggancio automatico all'ingresso ────────────────────────────────────

def test_l_handler_e_registrato_su_fattura_created():
    """Senza la registrazione l'aggancio non esiste, e non lo dice nessuno."""
    import app.services.event_bus as bus

    bus._handlers.clear()
    bus.register_all_handlers()
    registrati = [
        getattr(h, "__name__", "")
        for h in bus._handlers.get(bus.EventTypes.FATTURA_CREATED, [])
    ]

    assert "on_fattura_created_alimenta_lotti" in registrati, (
        f"Handler su fattura.created: {registrati}. Senza quello, una fattura "
        "che entra da Drive non alimenta il magazzino."
    )


def test_l_handler_non_fa_fallire_l_import_se_lotti_non_risponde(monkeypatch):
    """Lotti e' un consumatore a valle: un suo guasto non blocca la contabilita'."""
    from app.services.handlers import fattura_handlers

    async def esplode(_source_id):
        raise RuntimeError("Lotti non raggiungibile")

    monkeypatch.setattr(
        "app.lotti.routers.gestionale_fatture.alimenta_lotti_da_fattura", esplode
    )

    async def scenario():
        esito = await fattura_handlers.on_fattura_created_alimenta_lotti(
            {"fattura_id": "f-1"}, db=None
        )
        await fattura_handlers.attendi_alimentazione_lotti()
        return esito

    esito = run(scenario())

    # non solleva e non aspetta Lotti: l'import contabile prosegue
    assert esito == {"action": "lotti_accodato", "fattura_id": "f-1"}


def test_l_handler_lavora_una_sola_fattura(monkeypatch):
    """Il controllo che protegge dal guasto del 20/09: `fattura.created` nasce
    una volta per fattura e il giro Drive ne importa 25 alla volta. Un motore
    che ripassa l'archivio, moltiplicato per il lotto, aveva mandato la CPU al
    95% e fatto entrare 4 fatture su 49."""
    from app.services.handlers import fattura_handlers

    chiamate = []

    async def finta(source_id):
        chiamate.append(source_id)
        return {"stato": "alimentata", "fattura_id": source_id}

    monkeypatch.setattr(
        "app.lotti.routers.gestionale_fatture.alimenta_lotti_da_fattura", finta
    )

    async def scenario():
        await fattura_handlers.on_fattura_created_alimenta_lotti({"fattura_id": "f-7"}, db=None)
        await fattura_handlers.attendi_alimentazione_lotti()

    run(scenario())

    assert chiamate == ["f-7"], (
        f"L'handler ha toccato {chiamate}: deve alimentare SOLO la fattura "
        "dell'evento, mai l'archivio."
    )


def test_l_import_contabile_non_aspetta_lotti(monkeypatch):
    """23/09/2026: il bus aspetta ogni handler, e con Lotti lento uno ZIP di
    fatture restava fermo 14 minuti su una fattura. L'handler accoda e torna."""
    import asyncio

    from app.services.handlers import fattura_handlers

    lotti_in_corso = asyncio.Event
    stato = {}

    async def lenta(source_id):
        stato["partita"] = True
        await stato["sblocca"].wait()
        return {"stato": "alimentata", "fattura_id": source_id}

    monkeypatch.setattr(
        "app.lotti.routers.gestionale_fatture.alimenta_lotti_da_fattura", lenta
    )

    async def scenario():
        stato["sblocca"] = lotti_in_corso()
        esito = await asyncio.wait_for(
            fattura_handlers.on_fattura_created_alimenta_lotti({"fattura_id": "f-9"}, db=None),
            timeout=1,
        )
        stato["sblocca"].set()
        await fattura_handlers.attendi_alimentazione_lotti()
        return esito

    esito = run(scenario())
    assert esito["action"] == "lotti_accodato"
    assert stato.get("partita") is True
