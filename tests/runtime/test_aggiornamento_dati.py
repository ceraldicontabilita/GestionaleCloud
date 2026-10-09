"""Riquadro «Aggiornamento dati»: stato delle fonti letto da dove i motori lo
scrivono, mai inventato; una fonte senza dato e' «non disponibile»."""
import asyncio
from datetime import datetime, timedelta, timezone

from mongomock_motor import AsyncMongoMockClient

from app.services import aggiornamento_dati as ad

ORA = datetime(2026, 9, 25, 8, 0, tzinfo=timezone.utc)


def run(coro):
    return asyncio.run(coro)


def _per_codice(esito):
    return {f["codice"]: f for f in esito["fonti"]}


def test_archivio_vuoto_non_inventa_niente():
    db = AsyncMongoMockClient()["t"]
    esito = run(ad.stato_fonti(db, ORA))
    assert [f["ordine"] for f in esito["fonti"]] == [1, 2, 3, 4, 5]
    for fonte in esito["fonti"]:
        assert fonte["stato"] == ad.NON_DISPONIBILE, fonte
        assert fonte["testo"]
        assert fonte["ultimo_aggiornamento"] is None


def test_stati_letti_dai_motori():
    db = AsyncMongoMockClient()["t"]

    async def prepara():
        # Banca, fatture, corrispettivi, cedolini e F24 entrano tutti dalla
        # cartella unica: il loro giro e' quello dello smistatore.
        await db.sistema_stato.insert_one(
            {"chiave": "drive_cartella_unica_last_sync",
             "valore": (ORA - timedelta(minutes=10)).isoformat(), "last_error": None})
        await db.estratto_conto_movimenti.insert_many([{"data": "2026-09-21"}, {"data": "2026-09-01"}])
        await db.invoices.insert_many([{"invoice_date": "2026-09-22"}])
        await db.corrispettivi.insert_many([{"data": "2026-09-18"}, {"data": "2026-09-17"}])
        await db.chiusure_attivita.insert_one({"data_inizio": "2026-09-19", "data_fine": "2026-09-20"})

    run(prepara())
    fonti = _per_codice(run(ad.stato_fonti(db, ORA)))

    banca = fonti["banca"]
    assert banca["stato"] == ad.GIALLO and "21/09/2026" in banca["testo"]
    assert banca["conteggi"] == {"movimenti": 2}

    assert fonti["fatture"]["stato"] == ad.VERDE
    assert fonti["fatture"]["ultimo_dato"] == "2026-09-22"

    corr = fonti["corrispettivi"]
    # 19 e 20 sono chiusure: mancano 21, 22, 23, 24 (ieri) = 4 giorni.
    assert corr["stato"] == ad.ROSSO and "mancano 4 giorni" in corr["testo"]
    assert corr["ultimo_dato"] == "2026-09-18" and corr["conteggi"]["giornate"] == 2

    assert fonti["cedolini_f24"]["stato"] == ad.VERDE

    assert fonti["riconciliazione"]["stato"] == ad.NON_DISPONIBILE


def test_giro_della_cartella_unica_fermo_ferma_le_fonti_drive():
    db = AsyncMongoMockClient()["t"]
    run(db.sistema_stato.insert_one(
        {"chiave": "drive_cartella_unica_last_sync",
         "valore": (ORA - timedelta(hours=5)).isoformat(), "last_error": None}))
    fonti = _per_codice(run(ad.stato_fonti(db, ORA)))
    for codice in ("banca", "fatture", "cedolini_f24"):
        assert fonti[codice]["stato"] == ad.ROSSO and "Fermo" in fonti[codice]["testo"], codice


def test_giro_riconciliazione_registrato_e_letto():
    db = AsyncMongoMockClient()["t"]
    run(ad.registra_giro_riconciliazione(
        db, iniziato_at=datetime.now(timezone.utc),
        risultato={"salari": {"bonifici_associati": 3}, "f24": {"movimenti_associati": 0}}))
    ric = _per_codice(run(ad.stato_fonti(db)))["riconciliazione"]
    assert ric["stato"] == ad.VERDE
    assert ric["conteggi"] == {"stipendi": 3, "f24": 0}

    run(ad.registra_giro_riconciliazione(db, iniziato_at=datetime.now(timezone.utc),
                                         errore=TimeoutError()))
    ric = _per_codice(run(ad.stato_fonti(db)))["riconciliazione"]
    assert ric["stato"] == ad.ROSSO and "TimeoutError" in ric["testo"]


def test_corrispettivi_fermi_solo_per_chiusura_sono_verdi():
    db = AsyncMongoMockClient()["t"]

    async def prepara():
        await db.corrispettivi.insert_one({"data": "2026-08-14"})
        await db.chiusure_attivita.insert_one({"data_inizio": "2026-08-15", "data_fine": "2026-08-23"})

    run(prepara())
    corr = _per_codice(run(ad.stato_fonti(db, datetime(2026, 8, 24, 9, tzinfo=timezone.utc))))["corrispettivi"]
    assert corr["stato"] == ad.VERDE


def test_una_fonte_lenta_non_blocca_il_riquadro(monkeypatch):
    """26/09/2026: una lettura lenta faceva scadere tutto il riquadro dopo 20 s."""
    db = AsyncMongoMockClient()["t"]

    async def lenta(db, ora):
        await asyncio.sleep(5)

    lenta.__name__ = "_fatture"
    monkeypatch.setattr(ad, "_fatture", lenta)
    monkeypatch.setattr(ad, "TEMPO_MAX_FONTE_SECONDI", 0.2)
    esito = run(ad.stato_fonti(db, ORA))
    per = _per_codice(esito)
    assert [f["ordine"] for f in esito["fonti"]] == [1, 2, 3, 4, 5]
    assert per["fatture"]["stato"] == ad.NON_DISPONIBILE
    assert "lenta" in per["fatture"]["testo"]
    assert per["banca"]["testo"]  # le altre fonti ci sono comunque
