"""Riprocessamento batch: non duplica, non svuota la memoria, non e' aperto a tutti.

Le tre garanzie che questi test difendono, nell'ordine in cui contano:

1. **non crea documenti**: scrive solo con update sui documenti che esistono
   gia', quindi non puo' generare righe doppie in archivio;
2. **non carica tutto in memoria**: legge a blocchi, perche' prima prendeva
   fino a 5.000 documenti in una lista sola, ognuno col PDF in base64 dentro;
3. **e' riservato all'admin**: avvia una scrittura di massa, e prima bastava
   essere loggati — anche in sola lettura.
"""
import asyncio
import base64
import inspect

import pytest
from app.services.archivio_documenti_memoria import ClientArchivioMemoria

from app.services import batch_reprocessing as servizio
from app.services.batch_reprocessing import BatchReprocessingService

PDF = base64.b64encode(b"%PDF-1.4 finto").decode()


def _run(awaitable):
    return asyncio.run(awaitable)


def _db(quanti):
    db = ClientArchivioMemoria()["batch_reprocessing_test"]
    _run(db["cedolini"].insert_many(
        [{"id": f"c{i}", "pdf_data": PDF} for i in range(quanti)]))
    return db


@pytest.fixture
def _parser_finto(monkeypatch):
    """Sostituisce il modello: qui si verifica il giro, non l'estrazione."""
    chiamate = []

    async def _finto(pdf_bytes, mime):
        chiamate.append(pdf_bytes)
        return {"success": True, "importi_finali": {"netto_in_busta": 100.0}}

    monkeypatch.setattr(servizio, "parse_cedolino_enhanced", _finto)
    return chiamate


def _riprocessa(db, dry_run=False):
    service = BatchReprocessingService()
    service.db = db

    async def _giro():
        # init_db() cerca la connessione reale: qui il db e' gia' iniettato.
        service.init_db = lambda: asyncio.sleep(0)
        return await service.reprocess_all_cedolini(dry_run=dry_run)

    return _run(_giro())


# --- Nessuna duplicazione --------------------------------------------------

def test_non_crea_documenti_nuovi(_parser_finto):
    """La paura legittima: che un riprocessamento raddoppi l'archivio."""
    db = _db(5)
    prima = _run(db["cedolini"].count_documents({}))

    _riprocessa(db)

    assert _run(db["cedolini"].count_documents({})) == prima == 5


def test_arricchisce_senza_toccare_i_campi_originali(_parser_finto):
    db = _db(1)
    _run(db["cedolini"].update_one({"id": "c0"}, {"$set": {"netto": 1.0}}))

    _riprocessa(db)

    doc = _run(db["cedolini"].find_one({"id": "c0"}))
    assert doc["netto"] == 1.0          # originale intatto
    assert doc["netto_enhanced"] == 100.0
    assert doc["enhanced_parser_version"] == "v2"


def test_la_prova_a_vuoto_non_scrive_niente(_parser_finto):
    db = _db(3)
    esito = _riprocessa(db, dry_run=True)

    assert esito["cedolini_success"] == 3
    assert _run(db["cedolini"].find_one({"enhanced_parsing": {"$exists": True}})) is None


def test_rieseguirlo_non_moltiplica_niente(_parser_finto):
    db = _db(3)
    _riprocessa(db)
    _riprocessa(db)

    assert _run(db["cedolini"].count_documents({})) == 3


# --- Memoria ---------------------------------------------------------------

def test_i_pdf_si_leggono_a_blocchi_non_tutti_insieme(monkeypatch, _parser_finto):
    """Il blocco piu' grande mai tenuto in memoria non supera la soglia."""
    monkeypatch.setattr(servizio, "DIMENSIONE_BLOCCO", 4)
    db = _db(10)

    letture = []
    originale = servizio._blocco

    async def _spia(coll, identificativi, proiezione):
        letture.append(len(identificativi))
        return await originale(coll, identificativi, proiezione)

    monkeypatch.setattr(servizio, "_blocco", _spia)
    esito = _riprocessa(db)

    assert max(letture) <= 4
    assert sum(letture) == 10          # nessun documento saltato
    assert esito["cedolini_processed"] == 10


def test_la_prima_lettura_non_porta_dietro_i_pdf():
    """Serve a contare e a paginare: caricare i PDF qui vanificherebbe tutto."""
    db = _db(3)
    identificativi = _run(servizio._identificativi(
        db["cedolini"], {"pdf_data": {"$exists": True}}))

    assert len(identificativi) == 3
    assert all(not isinstance(i, dict) for i in identificativi)


# --- Un documento rotto non ferma gli altri --------------------------------

def test_un_documento_illeggibile_non_blocca_il_lotto(monkeypatch):
    db = _db(3)
    _run(db["cedolini"].update_one({"id": "c1"}, {"$set": {"pdf_data": "non-base64!!"}}))

    async def _finto(pdf_bytes, mime):
        return {"success": True, "importi_finali": {}}

    monkeypatch.setattr(servizio, "parse_cedolino_enhanced", _finto)
    esito = _riprocessa(db)

    assert esito["cedolini_errors"] == 1
    assert esito["cedolini_success"] == 2
    assert esito["errors"][0]["type"] == "cedolino"


# --- Controllo di ruolo ----------------------------------------------------

@pytest.mark.parametrize("nome_endpoint", [
    "get_preview", "get_status",
    "start_reprocessing", "start_cedolini_only",
])
def test_ogni_endpoint_e_riservato_all_admin(nome_endpoint):
    """Avvia una scrittura di massa: prima bastava essere loggati, anche in
    sola lettura."""
    from app.routers import batch_reprocessing as router
    from app.utils.dependencies import get_current_admin_user

    parametri = inspect.signature(getattr(router, nome_endpoint)).parameters.values()
    assert any(
        getattr(p.default, "dependency", None) is get_current_admin_user
        for p in parametri
    ), f"{nome_endpoint} deve restare admin-only"


# --- Niente F24 ------------------------------------------------------------

def test_il_batch_non_rilegge_piu_i_modelli_f24():
    """I modelli F24 hanno un solo lettore (`parser_f24`) e un solo ingresso:
    il riprocessamento AI scriveva campi paralleli su collezioni dismesse."""
    from pathlib import Path
    from app.routers import batch_reprocessing as router
    from app.services import enhanced_document_parser as lettore

    assert not hasattr(servizio.BatchReprocessingService, "reprocess_all_f24")
    assert not hasattr(router, "start_f24_only")
    assert not hasattr(lettore, "parse_f24_enhanced")
    sorgente = Path(servizio.__file__).read_text(encoding="utf-8")
    assert "f24_models" not in sorgente.split('"""', 2)[2]  # solo nella docstring di testa
