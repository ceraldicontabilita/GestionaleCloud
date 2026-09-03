"""Adattatore HR: prefisso ``hr_`` e scarico dei PDF fuori dalla memoria.

Il runtime documentale tiene tutto in RAM: un cedolino con il suo PDF in
base64 non deve mai entrarci. Questi test usano lo store in memoria del
gestionale (``SheetDatabase``) e un ``MemoryBlobStore`` per verificare che il
documento salvato non contenga i binari, che le letture li riaggancino solo
quando richiesti e che cancellazioni/aggiornamenti tengano allineato l'archivio
dei blob.
"""
import asyncio

import pytest

from app.services.blob_store import MemoryBlobStore, blob_key
from app.hr.db_adapter import HRDatabase, MARKER, rewrite_selector, wanted_blob_fields, inner_projection
from app.services.sheets_document_store import SheetDatabase


def _run(coro):
    # Loop nuovo a ogni chiamata: nella suite completa altri test chiudono il loop di default.
    return asyncio.run(coro)


@pytest.fixture
def hr():
    inner = SheetDatabase("test")
    store = MemoryBlobStore()
    return HRDatabase(inner, store), inner, store


def test_collezioni_hr_hanno_il_prefisso(hr):
    db, inner, _ = hr
    _run(db.dipendenti.insert_one({"id": "d1", "nome": "Anna"}))
    assert _run(inner["hr_dipendenti"].count_documents({})) == 1
    assert _run(inner["dipendenti"].count_documents({})) == 0
    assert _run(db.list_collection_names()) == ["dipendenti"]


def test_insert_scarica_il_pdf_e_lascia_solo_il_marcatore(hr):
    db, inner, store = hr
    _run(db.cedolini.insert_one({"id": "c1", "mese": 3, "pdf_data": "JVBERi0x"}))
    grezzo = _run(inner["hr_cedolini"].find_one({"id": "c1"}))
    assert "pdf_data" not in grezzo
    assert grezzo[MARKER] == {"pdf_data": blob_key("JVBERi0x")}
    assert _run(store.get(blob_key("JVBERi0x"))) == "JVBERi0x"


def test_lettura_riaggancia_il_pdf_solo_se_richiesto(hr):
    db, _, _ = hr
    _run(db.cedolini.insert_one({"id": "c1", "mese": 3, "pdf_data": "JVBERi0x"}))
    completo = _run(db.cedolini.find_one({"id": "c1"}))
    assert completo["pdf_data"] == "JVBERi0x" and MARKER not in completo
    leggero = _run(db.cedolini.find_one({"id": "c1"}, {"_id": 0, "pdf_data": 0}))
    assert "pdf_data" not in leggero and MARKER not in leggero
    solo_pdf = _run(db.cedolini.find_one({"id": "c1"}, {"_id": 0, "pdf_data": 1, "mese": 1}))
    assert solo_pdf == {"pdf_data": "JVBERi0x", "mese": 3}
    elenco = _run(db.cedolini.find({}, {"_id": 0, "pdf_data": 0}).to_list(10))
    assert elenco == [{"id": "c1", "mese": 3}]


def test_iterazione_async_riaggancia_documento_per_documento(hr):
    db, _, _ = hr
    _run(db.cedolini.insert_many([{"id": f"c{i}", "pdf_data": f"pdf{i}"} for i in range(3)]))

    async def _leggi():
        return [d["pdf_data"] async for d in db.cedolini.find({}, {"_id": 0, "id": 1, "pdf_data": 1})]

    assert sorted(_run(_leggi())) == ["pdf0", "pdf1", "pdf2"]


def test_filtri_sui_campi_binari_usano_il_marcatore(hr):
    db, _, _ = hr
    _run(db.cedolini.insert_many([{"id": "con", "pdf_data": "x"}, {"id": "senza"}]))
    assert rewrite_selector({"pdf_data": {"$exists": True}}) == {f"{MARKER}.pdf_data": {"$exists": True}}
    assert rewrite_selector({"pdf_data": None}) == {f"{MARKER}.pdf_data": {"$exists": False}}
    con = _run(db.cedolini.find({"pdf_data": {"$exists": True}}, {"_id": 0, "id": 1}).to_list(10))
    senza = _run(db.cedolini.find({"pdf_data": {"$ne": None}}, {"_id": 0, "id": 1}).to_list(10))
    assert [d["id"] for d in con] == ["con"] and [d["id"] for d in senza] == ["con"]
    assert _run(db.cedolini.count_documents({"pdf_data": None})) == 1
    with pytest.raises(NotImplementedError):
        rewrite_selector({"pdf_data": {"$regex": "x"}})


def test_update_set_e_unset_tengono_allineato_lo_store(hr):
    db, inner, store = hr
    _run(db.documenti_cloud.insert_one({"id": "doc1", "tipo": "UNILAV"}))
    _run(db.documenti_cloud.update_one({"id": "doc1"}, {"$set": {"file_data": "AAA", "nome": "x.pdf"}}))
    grezzo = _run(inner["hr_documenti_cloud"].find_one({"id": "doc1"}))
    assert grezzo["nome"] == "x.pdf" and "file_data" not in grezzo
    assert _run(store.get(blob_key("AAA"))) == "AAA"
    assert _run(db.documenti_cloud.find_one({"id": "doc1"}))["file_data"] == "AAA"
    _run(db.documenti_cloud.update_one({"id": "doc1"}, {"$set": {"file_data": "BBB"}}))
    assert _run(store.get(blob_key("AAA"))) is None and _run(store.get(blob_key("BBB"))) == "BBB"
    _run(db.documenti_cloud.update_one({"id": "doc1"}, {"$unset": {"file_data": ""}}))
    assert _run(store.get(blob_key("BBB"))) is None
    assert MARKER not in _run(inner["hr_documenti_cloud"].find_one({"id": "doc1"}))


def test_upsert_senza_corrispondenza_crea_il_documento_con_il_blob(hr):
    db, _, store = hr
    r = _run(db.bonifici.update_one({"key": "k1"}, {"$set": {"pdf_data": "B", "importo": 10}, "$setOnInsert": {"creato": True}}, upsert=True))
    assert r.upserted_id
    doc = _run(db.bonifici.find_one({"key": "k1"}))
    assert doc["importo"] == 10 and doc["creato"] is True and doc["pdf_data"] == "B"
    assert _run(store.stats(""))["count"] == 1


def test_delete_rimuove_anche_i_blob(hr):
    db, _, store = hr
    _run(db.cedolini.insert_many([{"id": "a", "pdf_data": "1"}, {"id": "b", "pdf_data": "2"}, {"id": "c"}]))
    _run(db.cedolini.delete_one({"id": "a"}))
    assert _run(store.stats(""))["count"] == 1
    _run(db.cedolini.delete_many({}))
    assert _run(db.cedolini.count_documents({})) == 0
    assert _run(store.stats(""))["count"] == 0


def test_pdf_identici_occupano_spazio_una_sola_volta(hr):
    """La stessa distinta copiata su piu' bonifici, e lo stesso bonifico in
    piu' tabelle: un solo blob, con un riferimento per documento."""
    db, _, store = hr
    distinta = "JVBERi0xLjQK" * 10
    _run(db.bonifici.insert_many([{"id": f"b{i}", "pdf_data": distinta} for i in range(3)]))
    _run(db.pagamenti_esiti.insert_one({"id": "e1", "pdf_data": distinta}))
    stats = _run(store.stats(""))
    assert stats["count"] == 1 and stats["refs"] == 4
    assert _run(db.bonifici.count_with_blobs()) == 3
    # Cancellare un documento non toglie il PDF agli altri.
    _run(db.bonifici.delete_one({"id": "b0"}))
    assert _run(db.pagamenti_esiti.find_one({"id": "e1"}))["pdf_data"] == distinta
    assert _run(store.stats(""))["refs"] == 3
    # Riscrivere lo stesso contenuto non aggiunge riferimenti.
    _run(db.bonifici.update_one({"id": "b1"}, {"$set": {"pdf_data": distinta}}))
    assert _run(store.stats(""))["refs"] == 3
    # L'ultimo riferimento cancella davvero il file.
    _run(db.bonifici.delete_many({}))
    _run(db.pagamenti_esiti.delete_many({}))
    assert _run(store.stats("")) == {"count": 0, "bytes": 0, "refs": 0}


def test_update_senza_blob_passa_dritto_al_runtime(hr):
    db, _, _ = hr
    _run(db.dipendenti.insert_one({"id": "d1", "stato": "attivo"}))
    r = _run(db.dipendenti.update_one({"id": "d1"}, {"$set": {"stato": "cessato"}}))
    assert r.matched_count == 1
    assert _run(db.dipendenti.find_one({"id": "d1"}, {"_id": 0}))["stato"] == "cessato"


def test_aggregate_riscrive_solo_il_match(hr):
    db, _, _ = hr
    _run(db.cedolini.insert_many([{"id": "a", "netto": 10, "pdf_data": "1"}, {"id": "b", "netto": 5}]))
    righe = _run(db.cedolini.aggregate([
        {"$match": {"pdf_data": {"$exists": True}}},
        {"$group": {"_id": None, "tot": {"$sum": "$netto"}}},
    ]).to_list(10))
    assert righe[0]["tot"] == 10


def test_proiezioni_e_campi_richiesti():
    assert wanted_blob_fields(None) == {"pdf_data", "file_data", "pdf_firmato_dipendente", "pdf_definitivo"}
    assert wanted_blob_fields({"_id": 0, "pdf_data": 0}) == {"file_data", "pdf_firmato_dipendente", "pdf_definitivo"}
    assert wanted_blob_fields({"_id": 0, "id": 1}) == set()
    assert inner_projection({"_id": 0, "pdf_data": 1}) == {"_id": 0, MARKER: 1}
    assert inner_projection({"_id": 0, "pdf_data": 0}) == {"_id": 0}
