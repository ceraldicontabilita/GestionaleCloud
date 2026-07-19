"""Versione ISOLATA (mongomock) della pipeline testata in
test_corrispettivi_ingest.py: stessa logica applicativa reale
(ingest_corrispettivo_parsed → motore unico registra_corrispettivo), ma
senza bisogno di un backend live né di una connessione reale ad Atlas —
gira sempre, anche in un sandbox senza rete.

Usa un vero motore di query MongoDB in memoria (mongomock-motor), non un
fake scritto a mano collezione per collezione: un fake semplificato con
matching approssimativo delle query non avrebbe mai potuto rivelare la
race condition trovata il 19/07/2026 in registra_corrispettivo (due
scritture concorrenti duplicavano Prima Nota Cassa) — mongomock replica
find_one_and_update/upsert con semantica reale.

NON sostituisce test_corrispettivi_ingest.py, che resta la prova end-to-end
vera (HTTP + Atlas reale) per quando gira in un ambiente con accesso
effettivo a un backend live e a MongoDB Atlas."""
import asyncio

import pytest

mongomock_motor = pytest.importorskip("mongomock_motor")
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

from app.routers.invoices.corrispettivi_helpers import ingest_corrispettivo_parsed  # noqa: E402


def _db():
    client = AsyncMongoMockClient()
    return client["test_gestionale_isolato"]


def _parsed(data="2026-07-19", matricola="RT001", piva="99999999901",
            contanti=80.0, elettronico=20.0, imponibile=90.91, imposta=9.09,
            corrispettivo_key=None):
    return {
        "corrispettivo_key": corrispettivo_key or f"{matricola}-{data}",
        "data": data,
        "matricola_rt": matricola,
        "partita_iva": piva,
        "pagato_contanti": contanti,
        "pagato_elettronico": elettronico,
        "totale_imponibile": imponibile,
        "totale_iva": imposta,
        "totale": round(contanti + elettronico, 2),
        "numero_documenti": 5,
    }


def test_upload_crea_corrispettivo_e_prima_nota():
    db = _db()
    esito = asyncio.run(ingest_corrispettivo_parsed(
        db, _parsed(), filename="test.xml", source="xml", update_if_exists=True,
    ))

    assert esito["action"] == "created"
    assert esito.get("prima_nota_cassa_id")

    entrate = asyncio.run(
        db["prima_nota_cassa"].find({"tipo": "entrata", "categoria": "Corrispettivi"}).to_list(10)
    )
    assert len(entrate) == 1
    assert entrate[0]["importo"] == 100.0


def test_upload_duplicato_senza_force_non_crea_doppia_scrittura():
    db = _db()
    parsed = _parsed()
    asyncio.run(ingest_corrispettivo_parsed(
        db, parsed, filename="a.xml", source="xml", update_if_exists=True,
    ))

    esito2 = asyncio.run(ingest_corrispettivo_parsed(
        db, parsed, filename="a.xml", source="xml", update_if_exists=False,
    ))

    assert esito2["action"] == "duplicate"
    entrate = asyncio.run(
        db["prima_nota_cassa"].find({"tipo": "entrata", "categoria": "Corrispettivi"}).to_list(10)
    )
    assert len(entrate) == 1  # non raddoppiata dal secondo upload


def test_upload_force_update_ricrea_senza_duplicare_prima_nota():
    db = _db()
    parsed = _parsed()
    asyncio.run(ingest_corrispettivo_parsed(
        db, parsed, filename="a.xml", source="xml", update_if_exists=True,
    ))

    parsed_aggiornato = _parsed(contanti=100.0, elettronico=20.0)  # stesso key, totale diverso
    esito2 = asyncio.run(ingest_corrispettivo_parsed(
        db, parsed_aggiornato, filename="a.xml", source="xml", update_if_exists=True,
    ))

    assert esito2["action"] == "updated"
    entrate = asyncio.run(
        db["prima_nota_cassa"].find({"tipo": "entrata", "categoria": "Corrispettivi"}).to_list(10)
    )
    assert len(entrate) == 1
    assert entrate[0]["importo"] == 120.0  # rigenerato con l'importo aggiornato


def test_due_upload_concorrenti_dello_stesso_corrispettivo_non_duplicano():
    """Follow-up dal fix di registra_corrispettivo (PR #67):
    _find_existing_corrispettivo ha lo stesso pattern find_one-poi-insert
    sulla collection "corrispettivi". Due upload dello stesso corrispettivo
    (mai visto prima) lanciati DAVVERO in concorrenza non devono produrre
    due record "corrispettivi"."""
    db = _db()
    parsed = _parsed()

    async def _run():
        return await asyncio.gather(
            ingest_corrispettivo_parsed(db, parsed, filename="a.xml", source="xml", update_if_exists=True),
            ingest_corrispettivo_parsed(db, parsed, filename="b.xml", source="xml", update_if_exists=True),
        )

    esiti = asyncio.run(_run())

    record_corrispettivi = asyncio.run(
        db["corrispettivi"].find({"matricola_rt": "RT001", "data": "2026-07-19"}).to_list(10)
    )
    assert len(record_corrispettivi) == 1, (
        f"attesi 1 record 'corrispettivi', trovati {len(record_corrispettivi)}: "
        f"_find_existing_corrispettivo non è atomico sotto interleaving reale. Esiti: {esiti}"
    )


def test_riupload_dopo_soft_delete_ricrea_il_corrispettivo():
    """Review Codex su PR #68: la guardia atomica sull'insert (find_one_
    and_update su corrispettivo_key) deve escludere i soft-delete, esattamente
    come fa _find_existing_corrispettivo — altrimenti un corrispettivo
    eliminato (entity_status="deleted") con la stessa chiave XML verrebbe
    considerato "già esistente" e impedirebbe di ricaricare lo stesso file."""
    db = _db()
    parsed = _parsed()

    # Corrispettivo pre-esistente ma soft-deleted con la STESSA chiave XML
    # che genererebbe _build_corrispettivo_doc per lo stesso parsed.
    from app.routers.invoices.corrispettivi_helpers import _build_corrispettivo_doc
    doc_eliminato = _build_corrispettivo_doc(parsed, filename="vecchio.xml", source="xml")
    doc_eliminato["id"] = "corr-vecchio"
    doc_eliminato["entity_status"] = "deleted"
    doc_eliminato["status"] = "deleted"
    asyncio.run(db["corrispettivi"].insert_one(doc_eliminato))

    esito = asyncio.run(ingest_corrispettivo_parsed(
        db, parsed, filename="nuovo.xml", source="xml", update_if_exists=True,
    ))

    assert esito["action"] == "created", (
        f"atteso 'created' (deve poter ricreare dopo soft-delete), ottenuto: {esito}"
    )
    entrate = asyncio.run(
        db["prima_nota_cassa"].find({"tipo": "entrata", "categoria": "Corrispettivi"}).to_list(10)
    )
    assert len(entrate) == 1
