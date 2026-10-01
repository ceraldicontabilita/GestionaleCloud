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
    # un solo meccanismo (quello della cartella unica): `e_guasto_transitorio`
    assert cu.e_guasto_transitorio(TIMEOUT)
    assert cu.e_guasto_transitorio("503: memoria insufficiente per l'OCR")
    assert cu.e_guasto_transitorio(
        "Supabase RPC gc_upsert_documents fallita (HTTP 400): unsupported Unicode escape sequence")
    # un F24 che non quadra e' un difetto del lettore: non si rilegge da solo
    assert not cu.e_guasto_transitorio(
        "Errore import F24: F24 non quadrato o non validato: salvataggio bloccato")
    assert not cu.e_guasto_transitorio("tipo di documento non riconosciuto")


def test_il_tetto_ai_rinvii_e_uno_solo():
    drive = DriveFinto()
    drive.aggiungi("t3", "dichiarazione.pdf", b"%PDF-3", "errori")
    db = AsyncMongoMockClient()["t"]
    run(db[cu.REGISTRO].insert_one({
        "id": "t3", "nome": "dichiarazione.pdf", "cartella": cu.ERRORI, "esito": "errore",
        "tipo": "dichiarazione_fiscale", "motivo": TIMEOUT, "rinvii": cu.MAX_RINVII,
        "aggiornato_il": _fa(99999)}))
    # oltre MAX_RINVII il file resta in ERRORI col suo motivo
    assert run(cu.rimetti_in_coda_buste_gia_presenti(db, drive, dict(CARTELLE))) == 0
    assert drive.file["t3"]["parent"] == "errori"


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
    assert riga["cartella"] == cu.INBOX

    # secondo giro: t1 e' gia' in coda, t2 non e' transitorio -> nuovi = 0
    assert run(cu.rimetti_in_coda_buste_gia_presenti(db, drive, dict(CARTELLE))) == 0


def test_il_nul_si_toglie_dal_payload_senza_toccare_il_resto():
    payload = {"p_docs": [{"id": "a", "testo": "ab\x00cd", "n": 3, "k\x00": ["x\x00", {"y": "z"}]}]}
    pulito = _senza_nul(payload)
    assert pulito == {"p_docs": [{"id": "a", "testo": "abcd", "n": 3, "k": ["x", {"y": "z"}]}]}
    senza = {"p_docs": [{"id": "a", "testo": "ab"}]}
    assert _senza_nul(senza) is senza   # niente da pulire: lo stesso oggetto
