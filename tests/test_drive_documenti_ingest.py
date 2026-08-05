"""
Ingest generico documenti fiscali da Drive (dichiarazione IVA, cartelle
esattoriali, avvisi bonari): canali, categoria del doc, guardie enable/config.
"""
import asyncio

from app.services import drive_documenti_ingest as d


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_canali_definiti():
    assert set(d.CANALI) == {
        "bonifico", "dichiarazione_iva", "cartella_esattoriale", "avviso_bonario",
        "verbale",
    }


def test_build_doc_categoria_corretta():
    for canale in d.CANALI:
        doc = d._build_inbox_doc(b"%PDF-1.4 x", "f.pdf", canale)
        assert doc["category"] == canale
        assert doc["pdf_data"] and doc["file_hash"] and doc["id"]
        assert doc["fonte"] == f"drive_{canale}"


def test_sync_canale_sconosciuto():
    res = _run(d.sync(None, "pippo"))
    assert res["status"] == "error"


def test_sync_disabilitato_non_tocca_db():
    # di default gli interruttori sono spenti → status disabled, nessun accesso db
    res = _run(d.sync(None, "dichiarazione_iva"))
    assert res["status"] in ("disabled", "not_configured")


def test_sync_tutti_vuoto_se_spenti():
    res = _run(d.sync_tutti(None))
    assert res["status"] == "ok"
    assert res["canali"] == {}  # nessun canale acceso+configurato di default
