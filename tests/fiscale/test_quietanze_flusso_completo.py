"""Due quietanze dello stesso invio (protocollo con suffisso /000001 e /000002),
PDF sintetici: import → riscontro con la banca → registro versamenti → scadenzario,
e il secondo caricamento dello stesso file non crea niente (nuovi = 0)."""
import asyncio

from app.db_collections import COLL_ESTRATTO_CONTO, COLL_QUIETANZE_F24
from app.services import quietanze_import as qi
from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.f24_controllo_incrociato import riconcilia_f24_banca
from app.services.registro_versamenti_f24 import vista_versamenti

PROTOCOLLO = "26091600000000001"


def _run(coro):
    return asyncio.run(coro)


def _quietanza(suffisso, saldo, codice, periodo):
    return {
        "dati_generali": {"protocollo_telematico": f"{PROTOCOLLO}/{suffisso}", "saldo_delega": saldo,
                          "data_pagamento": "2026-09-16", "codice_fiscale": "01879020517"},
        "sezione_erario": [{"codice_tributo": codice, "periodo_riferimento": periodo, "anno": "2026",
                            "importo_debito": saldo, "importo_debito_cents": round(saldo * 100),
                            "importo_credito": 0.0, "importo_credito_cents": 0}],
        "sezione_inps": [], "sezione_regioni": [], "sezione_tributi_locali": [], "sezione_inail": [],
        "totali": {"saldo_netto": saldo},
        "validazione": {"saldo_quadrato": True, "differenza_saldo": 0.0, "parser_version": "test-v1"},
    }


PDF_1, PDF_2 = b"%PDF-sintetico-1", b"%PDF-sintetico-2"
PARSED = {PDF_1: _quietanza("000001", 9421.15, "6008", "08/2026"),
          PDF_2: _quietanza("000002", 104.54, "6099", "2026")}


def _movimento(id_, importo):
    return {"id": id_, "data": "2026-09-17", "importo": -importo, "tipo": "uscita",
            "descrizione": "I24 AGENZIA ENTRATE - PAG.TO TELEMATICO - DATA INCASSO 16/09/2026 "
                           "2026-09-17-10.00.00.000000000001"}


def _prepara(monkeypatch):
    import app.services.f24_parser as f24_parser

    monkeypatch.setattr(f24_parser, "parse_quietanza_f24", lambda pdf_content: PARSED[pdf_content])
    db = ClientArchivioMemoria()["f24_flusso_completo"]
    for m in (_movimento("mov-1", 9421.15), _movimento("mov-2", 104.54)):
        _run(db[COLL_ESTRATTO_CONTO].insert_one(m))
    return db


def _conteggi(db):
    return {c: len(_run(db[c].find({}, {"_id": 0}).to_list(None)))
            for c in (COLL_QUIETANZE_F24, COLL_ESTRATTO_CONTO, "scadenzario_tributi", "entity_relations")}


def test_le_due_quietanze_arrivano_si_riscontrano_e_il_secondo_caricamento_non_crea_niente(monkeypatch):
    db = _prepara(monkeypatch)

    primo = [_run(qi.importa_quietanza_bytes(db, pdf, f"q{i}.pdf", fonte="test"))
             for i, pdf in enumerate((PDF_1, PDF_2), 1)]
    assert all(e["success"] and not e["duplicate"] for e in primo)
    assert len(_run(db[COLL_QUIETANZE_F24].find({}, {"_id": 0}).to_list(None))) == 2

    # il riscontro parte all'arrivo (nessun giro in attesa): livello CERTO, importo al centesimo
    quietanze = {q["protocollo_telematico"]: q for q in
                 _run(db[COLL_QUIETANZE_F24].find({}, {"_id": 0}).to_list(None))}
    assert set(quietanze) == {f"{PROTOCOLLO}/000001", f"{PROTOCOLLO}/000002"}
    for q in quietanze.values():
        assert q["riscontro_banca"]["livello"] == "CERTO"
    assert quietanze[f"{PROTOCOLLO}/000001"]["riscontro_banca"]["movimento_id"] == "mov-1"
    assert quietanze[f"{PROTOCOLLO}/000002"]["riscontro_banca"]["movimento_id"] == "mov-2"

    # registro versamenti: due deleghe dello stesso invio, distinte dal suffisso
    registro = _run(vista_versamenti(db, anno=2026))
    testo = str(registro)
    assert f"{PROTOCOLLO}/000001" in testo and f"{PROTOCOLLO}/000002" in testo

    # scadenzario: una riga per ogni tributo pagato
    assert len(_run(db["scadenzario_tributi"].find({}, {"_id": 0}).to_list(None))) >= 2

    prima = _conteggi(db)
    # secondo caricamento degli stessi file: duplicati, nulla di nuovo
    secondo = [_run(qi.importa_quietanza_bytes(db, pdf, f"q{i}.pdf", fonte="test"))
               for i, pdf in enumerate((PDF_1, PDF_2), 1)]
    assert all(e["success"] and e["duplicate"] for e in secondo)
    assert _conteggi(db) == prima
    # e il giro completo dei 30 minuti non scrive piu' niente
    giro = _run(riconcilia_f24_banca(db))
    assert giro["scritti"]["quietanze"] == 0 and giro["scritti"]["addebiti"] == 0
    assert _conteggi(db) == prima
