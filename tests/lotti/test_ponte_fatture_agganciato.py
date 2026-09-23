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
