"""Rilettura batch dei cedolini: motore unico, nessun doppione, memoria, admin.

Le garanzie che questi test difendono, nell'ordine in cui contano:

1. **legge col motore unico**: il PDF passa da `cedolini_motore.leggi_pdf`,
   lo stesso lettore di posta, Drive e Documenti > Import. Fino al 07/10/2026
   qui c'era un secondo lettore AI (`enhanced_document_parser`) che calcolava
   il netto da competenze meno trattenute e scriveva zero al posto del dato
   mancante;
2. **non inventa il netto**: netto nullo resta nullo, netti multipli restano
   `MULTIPLE_NETS_DA_VERIFICARE`, e il netto si scrive solo se verificato;
3. **non crea documenti**: scrive solo con update sui documenti che esistono
   gia', senza toccare i campi originali;
4. **non carica tutto in memoria**: legge a blocchi;
5. **e' riservato all'admin**: avvia una scrittura di massa.
"""
import asyncio
import base64
import inspect

import pytest
from app.constants.stati_netto import (
    MULTIPLE_NETS_DA_VERIFICARE,
    NETTO_NON_PRESENTE_O_NON_LEGGIBILE,
    NETTO_VERIFICATO_DA_CEDOLINO,
)
from app.services.archivio_documenti_memoria import ClientArchivioMemoria

from app.services import batch_reprocessing as servizio
from app.services.batch_reprocessing import BatchReprocessingService

PDF = base64.b64encode(b"%PDF-1.4 finto").decode()
CF = "RSSMRA80A01H501U"


def _run(awaitable):
    return asyncio.run(awaitable)


def _db(quanti, **extra):
    db = ClientArchivioMemoria()["batch_reprocessing_test"]
    _run(db["cedolini"].insert_many([
        {"id": f"c{i}", "pdf_data": PDF, "codice_fiscale": CF, "anno": 2025, "mese": 3,
         "tipo_cedolino": "mensile", **extra}
        for i in range(quanti)
    ]))
    return db


def _busta(**campi):
    base = {"codice_fiscale": CF, "anno": 2025, "mese": 3, "tipo_cedolino": "mensile",
            "netto": 100.0, "stato_netto": NETTO_VERIFICATO_DA_CEDOLINO,
            "netto_fonte": "cella", "lordo": 1500.0, "totale_trattenute": 400.0,
            "dati_chiave": {"acconto_recuperato_busta": 300.0, "acconto_recuperato_voce": "000033"},
            "_pdf_data": PDF, "_raw_text": "..."}
    base.update(campi)
    return base


def _lettura(*buste):
    return {"esito": "buste" if buste else "illeggibile", "buste": list(buste),
            "presenze": [], "fuori_periodo": [], "motivo": f"{len(buste)} buste lette"}


@pytest.fixture
def _lettore_finto(monkeypatch):
    """Sostituisce il lettore: qui si verifica il giro, non l'estrazione."""
    chiamate = []

    def _finto(pdf_bytes):
        chiamate.append(pdf_bytes)
        return _lettura(_busta())

    monkeypatch.setattr(servizio, "leggi_pdf", _finto)
    return chiamate


def _riprocessa(db, dry_run=False):
    service = BatchReprocessingService()
    service.db = db

    async def _giro():
        # init_db() cerca la connessione reale: qui il db e' gia' iniettato.
        service.init_db = lambda: asyncio.sleep(0)
        return await service.reprocess_all_cedolini(dry_run=dry_run)

    return _run(_giro())


# --- Motore unico ----------------------------------------------------------

def test_il_batch_legge_col_motore_unico_dei_cedolini():
    """Lo stesso lettore di posta, Drive e Documenti > Import: non un secondo."""
    from app.services import cedolini_motore

    assert servizio.leggi_pdf is cedolini_motore.leggi_pdf


def test_il_lettore_ai_parallelo_non_esiste_piu():
    from pathlib import Path

    with pytest.raises(ImportError):
        __import__("app.services.enhanced_document_parser")
    sorgente = Path(servizio.__file__).read_text(encoding="utf-8")
    corpo = sorgente.split('"""', 2)[2]  # il nome resta solo nella docstring di testa
    assert "enhanced_document_parser" not in corpo
    assert "parse_cedolino_enhanced" not in corpo
    assert "netto_enhanced" not in corpo


def test_il_lettore_riceve_i_byte_del_pdf(_lettore_finto):
    _riprocessa(_db(1))
    assert _lettore_finto == [b"%PDF-1.4 finto"]


# --- Il netto non si inventa ----------------------------------------------

def test_scrive_il_netto_verificato_e_i_dati_chiave(_lettore_finto):
    db = _db(1)
    _riprocessa(db)

    doc = _run(db["cedolini"].find_one({"id": "c0"}))
    blocco = doc[servizio.CAMPO_RILETTURA]
    assert blocco["esito"] == "ritrovata"
    assert blocco["netto"] == 100.0
    assert blocco["stato_netto"] == NETTO_VERIFICATO_DA_CEDOLINO
    assert blocco["netto_fonte"] == "cella"
    assert blocco["versione"] == servizio.VERSIONE_RILETTURA
    # Il campo canonico che `posizione_dipendente` e `tfr` leggono.
    assert doc["dati_chiave"]["acconto_recuperato_busta"] == 300.0
    # Il PDF e il testo della busta non finiscono nel blocco.
    assert "_pdf_data" not in blocco and "_raw_text" not in blocco
    assert "netto_enhanced" not in doc and "enhanced_parsing" not in doc


def test_netto_mancante_resta_nullo_mai_zero(monkeypatch):
    """Cella del netto vuota: il blocco porta lo stato, il netto resta None."""
    monkeypatch.setattr(servizio, "leggi_pdf", lambda pdf: _lettura(
        _busta(netto=None, stato_netto=NETTO_NON_PRESENTE_O_NON_LEGGIBILE, netto_fonte=None)))
    db = _db(1)
    esito = _riprocessa(db)

    blocco = _run(db["cedolini"].find_one({"id": "c0"}))[servizio.CAMPO_RILETTURA]
    assert blocco["esito"] == "netto_non_verificato"
    assert blocco["netto"] is None
    assert blocco["stato_netto"] == NETTO_NON_PRESENTE_O_NON_LEGGIBILE
    assert esito["esiti"] == {"netto_non_verificato": 1}


def test_netti_multipli_restano_da_verificare(monkeypatch):
    """Due candidati discordanti: non si sceglie il primo ne' il piu' grande."""
    monkeypatch.setattr(servizio, "leggi_pdf", lambda pdf: _lettura(
        _busta(netto=None, stato_netto=MULTIPLE_NETS_DA_VERIFICARE)))
    db = _db(1)
    _riprocessa(db)

    blocco = _run(db["cedolini"].find_one({"id": "c0"}))[servizio.CAMPO_RILETTURA]
    assert blocco["netto"] is None
    assert blocco["stato_netto"] == MULTIPLE_NETS_DA_VERIFICARE
    assert blocco["esito"] == "netto_non_verificato"


def test_non_calcola_il_netto_da_competenze_meno_trattenute(monkeypatch):
    """Lordo e trattenute ci sono, la cella no: il netto non si ricostruisce."""
    monkeypatch.setattr(servizio, "leggi_pdf", lambda pdf: _lettura(
        _busta(netto=None, stato_netto=NETTO_NON_PRESENTE_O_NON_LEGGIBILE,
               lordo=1500.0, totale_trattenute=400.0)))
    db = _db(1)
    _riprocessa(db)

    blocco = _run(db["cedolini"].find_one({"id": "c0"}))[servizio.CAMPO_RILETTURA]
    assert blocco["netto"] is None
    assert blocco["lordo"] == 1500.0 and blocco["totale_trattenute"] == 400.0


def test_una_busta_di_un_altro_dipendente_non_si_abbina(monkeypatch):
    monkeypatch.setattr(servizio, "leggi_pdf", lambda pdf: _lettura(
        _busta(codice_fiscale="VRDLGI75B02F839X")))
    db = _db(1)
    _riprocessa(db)

    blocco = _run(db["cedolini"].find_one({"id": "c0"}))[servizio.CAMPO_RILETTURA]
    assert blocco["esito"] == "non_ritrovata"
    assert blocco["netto"] is None and "dati_chiave" not in blocco


def test_due_buste_uguali_con_netti_diversi_restano_ambigue(monkeypatch):
    monkeypatch.setattr(servizio, "leggi_pdf", lambda pdf: _lettura(
        _busta(netto=100.0), _busta(netto=250.0)))
    db = _db(1)
    _riprocessa(db)

    blocco = _run(db["cedolini"].find_one({"id": "c0"}))[servizio.CAMPO_RILETTURA]
    assert blocco["esito"] == "ambigua"
    assert blocco["netto"] is None
    assert blocco["netti_candidati"] == ["100.00", "250.00"]


def test_un_cedolino_storico_senza_identita_si_abbina_solo_a_una_busta_sola(monkeypatch):
    db = ClientArchivioMemoria()["batch_reprocessing_test"]
    _run(db["cedolini"].insert_many([{"id": "vecchio", "pdf_data": PDF}]))

    monkeypatch.setattr(servizio, "leggi_pdf", lambda pdf: _lettura(_busta()))
    _riprocessa(db)
    assert _run(db["cedolini"].find_one({"id": "vecchio"}))[servizio.CAMPO_RILETTURA]["netto"] == 100.0

    monkeypatch.setattr(servizio, "leggi_pdf", lambda pdf: _lettura(_busta(), _busta(mese=4)))
    _riprocessa(db)
    blocco = _run(db["cedolini"].find_one({"id": "vecchio"}))[servizio.CAMPO_RILETTURA]
    assert blocco["esito"] == "non_ritrovata" and blocco["netto"] is None


def test_la_lettura_illeggibile_e_un_esito_non_un_errore(monkeypatch):
    monkeypatch.setattr(servizio, "leggi_pdf", lambda pdf: _lettura())
    db = _db(1)
    esito = _riprocessa(db)

    blocco = _run(db["cedolini"].find_one({"id": "c0"}))[servizio.CAMPO_RILETTURA]
    assert blocco["esito_lettura"] == "illeggibile" and blocco["esito"] == "non_ritrovata"
    assert esito["cedolini_success"] == 1 and esito["cedolini_errors"] == 0


# --- Nessuna duplicazione --------------------------------------------------

def test_non_crea_documenti_nuovi(_lettore_finto):
    """La paura legittima: che un riprocessamento raddoppi l'archivio."""
    db = _db(5)
    prima = _run(db["cedolini"].count_documents({}))

    _riprocessa(db)

    assert _run(db["cedolini"].count_documents({})) == prima == 5


def test_arricchisce_senza_toccare_i_campi_originali(_lettore_finto):
    db = _db(1)
    _run(db["cedolini"].update_one({"id": "c0"}, {"$set": {"netto": 1.0}}))

    _riprocessa(db)

    doc = _run(db["cedolini"].find_one({"id": "c0"}))
    assert doc["netto"] == 1.0          # originale intatto
    assert doc[servizio.CAMPO_RILETTURA]["netto"] == 100.0


def test_i_dati_chiave_esistenti_vincono_e_si_completano(_lettore_finto):
    db = _db(1, dati_chiave={"acconto_recuperato_busta": 250.0, "rateo_13ma_presente": True})

    _riprocessa(db)

    chiave = _run(db["cedolini"].find_one({"id": "c0"}))["dati_chiave"]
    assert chiave["acconto_recuperato_busta"] == 250.0      # esistente intatto
    assert chiave["rateo_13ma_presente"] is True
    assert chiave["acconto_recuperato_voce"] == "000033"    # chiave mancante aggiunta


def test_la_prova_a_vuoto_non_scrive_niente(_lettore_finto):
    db = _db(3)
    esito = _riprocessa(db, dry_run=True)

    assert esito["cedolini_success"] == 3
    assert esito["esiti"] == {"ritrovata": 3}
    assert _run(db["cedolini"].find_one({servizio.CAMPO_RILETTURA: {"$exists": True}})) is None


def test_rieseguirlo_non_moltiplica_niente(_lettore_finto):
    db = _db(3)
    _riprocessa(db)
    _riprocessa(db)

    assert _run(db["cedolini"].count_documents({})) == 3


# --- Memoria ---------------------------------------------------------------

def test_i_pdf_si_leggono_a_blocchi_non_tutti_insieme(monkeypatch, _lettore_finto):
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

    monkeypatch.setattr(servizio, "leggi_pdf", lambda pdf: _lettura(_busta()))
    esito = _riprocessa(db)

    assert esito["cedolini_errors"] == 1
    assert esito["cedolini_success"] == 2
    assert esito["errors"][0]["type"] == "cedolino"


def test_un_pdf_che_rompe_il_lettore_resta_un_errore_contato(monkeypatch):
    def _rotto(pdf):
        raise RuntimeError("fitz: cannot open")

    monkeypatch.setattr(servizio, "leggi_pdf", _rotto)
    db = _db(2)
    esito = _riprocessa(db)

    assert esito["cedolini_processed"] == 2 and esito["cedolini_errors"] == 2
    assert "RuntimeError" in esito["errors"][0]["error"]
    assert _run(db["cedolini"].find_one({servizio.CAMPO_RILETTURA: {"$exists": True}})) is None


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

    assert not hasattr(servizio.BatchReprocessingService, "reprocess_all_f24")
    assert not hasattr(router, "start_f24_only")
    sorgente = Path(servizio.__file__).read_text(encoding="utf-8")
    assert "f24_models" not in sorgente.split('"""', 2)[2]  # solo nella docstring di testa
