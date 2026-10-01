"""Errori transitori della cartella unica: si rileggono con attesa crescente, mai
all'infinito, e un secondo giro non rilegge ne' sposta niente (nuovi=0)."""
import asyncio
from datetime import datetime, timedelta, timezone

from mongomock_motor import AsyncMongoMockClient

from app.services import drive_cartella_unica as cu
from app.services.supabase_runtime_database import _senza_nul
from tests.documenti.test_drive_cartella_unica import CARTELLE, DriveFinto

TIMEOUT = ("Errore durante l'importazione: Supabase RPC gc_fetch_documents_exact fallita "
           "(HTTP 500): canceling statement due to statement timeout")


def run(coro):
    return asyncio.run(coro)


def _fa(minuti: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minuti)).isoformat()


def test_il_motivo_transitorio_e_riconosciuto_e_non_il_difetto_del_file():
    adesso = datetime.now(timezone.utc)
    assert cu.transitorio_da_ritentare(TIMEOUT, 0, _fa(20), adesso)
    assert cu.transitorio_da_ritentare("503: memoria insufficiente per l'OCR", 0, _fa(20), adesso)
    assert cu.transitorio_da_ritentare(
        "Supabase RPC gc_upsert_documents fallita (HTTP 400): unsupported Unicode escape sequence",
        0, _fa(20), adesso)
    # un F24 che non quadra e' un difetto del lettore: non si rilegge da solo
    assert not cu.transitorio_da_ritentare(
        "Errore import F24: F24 non quadrato o non validato: salvataggio bloccato", 0, _fa(999), adesso)
    assert not cu.transitorio_da_ritentare("tipo di documento non riconosciuto", 0, _fa(999), adesso)


def test_attesa_crescente_e_tetto_ai_tentativi():
    adesso = datetime.now(timezone.utc)
    assert not cu.transitorio_da_ritentare(TIMEOUT, 0, _fa(10), adesso)   # attesa 15'
    assert cu.transitorio_da_ritentare(TIMEOUT, 0, _fa(16), adesso)
    assert not cu.transitorio_da_ritentare(TIMEOUT, 1, _fa(16), adesso)   # attesa 30'
    assert cu.transitorio_da_ritentare(TIMEOUT, 1, _fa(31), adesso)
    assert cu.transitorio_da_ritentare(TIMEOUT, 4, _fa(241), adesso)      # attesa 240'
    assert not cu.transitorio_da_ritentare(TIMEOUT, cu.TENTATIVI_TRANSITORI, _fa(99999), adesso)


def test_rimessi_in_coda_una_volta_e_il_secondo_giro_non_rimette_niente():
    drive = DriveFinto()
    drive.aggiungi("t1", "dichiarazione.pdf", b"%PDF-1", "errori")
    drive.aggiungi("t2", "modello.pdf", b"%PDF-2", "errori")
    db = AsyncMongoMockClient()["t"]
    run(db[cu.REGISTRO].insert_one({
        "id": "t1", "nome": "dichiarazione.pdf", "cartella": cu.ERRORI, "esito": "errore",
        "tipo": "dichiarazione_fiscale", "motivo": TIMEOUT, "aggiornato_il": _fa(60)}))
    run(db[cu.REGISTRO].insert_one({
        "id": "t2", "nome": "modello.pdf", "cartella": cu.ERRORI, "esito": "errore", "tipo": "f24",
        "motivo": "Errore import F24: F24 non quadrato o non validato: salvataggio bloccato",
        "aggiornato_il": _fa(600)}))

    assert run(cu.rimetti_in_coda_buste_gia_presenti(db, drive, dict(CARTELLE))) == 1
    assert drive.file["t1"]["parent"] == "inbox"
    assert drive.file["t2"]["parent"] == "errori"          # difetto del lettore: resta li'
    riga = run(db[cu.REGISTRO].find_one({"id": "t1"}))
    assert riga["tentativi_transitori"] == 1 and riga["cartella"] == cu.INBOX

    # secondo giro: t1 e' gia' in coda, t2 non e' transitorio -> nuovi = 0
    assert run(cu.rimetti_in_coda_buste_gia_presenti(db, drive, dict(CARTELLE))) == 0


def test_il_nul_si_toglie_dal_payload_senza_toccare_il_resto():
    payload = {"p_docs": [{"id": "a", "testo": "ab\x00cd", "n": 3, "k\x00": ["x\x00", {"y": "z"}]}]}
    pulito = _senza_nul(payload)
    assert pulito == {"p_docs": [{"id": "a", "testo": "abcd", "n": 3, "k": ["x", {"y": "z"}]}]}
    senza = {"p_docs": [{"id": "a", "testo": "ab"}]}
    assert _senza_nul(senza) is senza   # niente da pulire: lo stesso oggetto
