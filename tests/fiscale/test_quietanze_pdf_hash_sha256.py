"""La quietanza F24 si riconosce per SHA-256 (`pdf_hash`), non piu' per MD5.

L'MD5 resta in `pdf_hash_md5` (serve solo a ritrovare la copia identica su
Drive, che l'API fornisce in MD5). Le righe scritte prima del passaggio
portano l'MD5 in `pdf_hash`: la stessa copia si riconosce lo stesso e la riga
si promuove (SHA-256 in `pdf_hash`, il vecchio in `pdf_hash_md5`), compreso
il guscio vuoto che si rilegge sul posto.
"""
import asyncio
import hashlib

from app.services import quietanze_import as qi
from app.services.archivio_documenti_memoria import ClientArchivioMemoria

PDF = b"%PDF-1.4 quietanza finta 2026"
SHA = hashlib.sha256(PDF).hexdigest()
MD5 = hashlib.md5(PDF).hexdigest()  # noqa: S324

PARSED = {
    "dati_generali": {"protocollo_telematico": "26061612000000001/000001", "saldo_delega": 250.0,
                      "data_pagamento": "2026-06-16", "codice_fiscale": "01879020517"},
    "sezione_erario": [{"codice_tributo": "1040", "periodo_riferimento": "05/2026", "importo_debito": 250.0}],
    "sezione_inps": [], "sezione_regioni": [], "sezione_tributi_locali": [], "sezione_inail": [],
    "totali": {"saldo_netto": 250.0},
    "validazione": {"saldo_quadrato": True, "differenza_saldo": 0.0},
}


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _db():
    return ClientArchivioMemoria()["quietanze_sha256"]


def _patch(monkeypatch):
    import app.services.f24_parser as f24_parser
    monkeypatch.setattr(f24_parser, "parse_quietanza_f24", lambda pdf_content: dict(PARSED))


def _quietanze(db):
    return _run(db[qi.COLL_QUIETANZE].find({}, {"_id": 0}).to_list(10))


def test_la_quietanza_nuova_porta_sha256_e_md5_separati(monkeypatch):
    _patch(monkeypatch)
    db = _db()
    esito = _run(qi.importa_quietanza_bytes(db, PDF, "q.pdf", fonte="test"))
    assert esito["success"] and not esito["duplicate"]
    [q] = _quietanze(db)
    assert q["pdf_hash"] == SHA and len(q["pdf_hash"]) == 64
    assert q["pdf_hash_md5"] == MD5
    assert q["idempotency_key"] == f"quietanza_f24:{SHA}"
    assert q["source_occurrences"][0]["md5"] == MD5 and q["source_occurrences"][0]["sha256"] == SHA


def test_lo_stesso_pdf_due_volte_e_uno_solo(monkeypatch):
    _patch(monkeypatch)
    db = _db()
    primo = _run(qi.importa_quietanza_bytes(db, PDF, "q.pdf"))
    secondo = _run(qi.importa_quietanza_bytes(db, PDF, "copia.pdf"))
    assert secondo["duplicate"] and secondo["quietanza_id"] == primo["quietanza_id"]
    assert len(_quietanze(db)) == 1


def test_la_riga_con_md5_in_pdf_hash_si_riconosce_e_si_promuove(monkeypatch):
    _patch(monkeypatch)
    db = _db()
    # Riga scritta prima del passaggio: MD5 in `pdf_hash`, protocollo DIVERSO da quello
    # del PDF (cosi' e' solo l'impronta a riconoscerla).
    _run(db[qi.COLL_QUIETANZE].insert_one({
        "id": "vecchia", "pdf_hash": MD5, "protocollo_telematico": "ALTRO/000001",
        "data_pagamento": "2026-06-16", "saldo": 250.0, "sezione_erario": PARSED["sezione_erario"],
        "source_occurrences": [], "f24_associati": [],
    }))
    esito = _run(qi.importa_quietanza_bytes(db, PDF, "q.pdf"))
    assert esito["duplicate"] is True and esito["quietanza_id"] == "vecchia"
    [q] = _quietanze(db)
    assert q["pdf_hash"] == SHA and q["pdf_hash_md5"] == MD5
    assert q["idempotency_key"] == f"quietanza_f24:{SHA}"


def test_il_guscio_vuoto_con_md5_si_rilegge_sul_posto(monkeypatch):
    _patch(monkeypatch)
    db = _db()
    _run(db[qi.COLL_QUIETANZE].insert_one({
        "id": "guscio", "pdf_hash": MD5, "protocollo_telematico": "", "created_at": "2026-01-01T00:00:00+00:00",
        "source_occurrences": [{"source": "drive", "md5": MD5}], "f24_associati": [],
    }))
    esito = _run(qi.importa_quietanza_bytes(db, PDF, "q.pdf"))
    assert esito["success"] and not esito["duplicate"] and esito["quietanza_id"] == "guscio"
    [q] = _quietanze(db)
    assert q["pdf_hash"] == SHA and q["pdf_hash_md5"] == MD5
    assert q["protocollo_telematico"] == PARSED["dati_generali"]["protocollo_telematico"]
    assert q["created_at"] == "2026-01-01T00:00:00+00:00"


def test_un_altro_file_non_si_promuove():
    db = _db()
    riga = {"id": "x", "pdf_hash": "a" * 64}
    _run(db[qi.COLL_QUIETANZE].insert_one(dict(riga)))
    assert _run(qi.promuovi_pdf_hash_sha256(db, dict(riga), sha256=SHA, md5=MD5)) is False
    assert _quietanze(db)[0]["pdf_hash"] == "a" * 64
