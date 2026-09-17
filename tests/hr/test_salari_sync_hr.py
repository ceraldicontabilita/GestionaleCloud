"""PR 15 (audit 03/09/2026 §5): sincronizzazione prima_nota_salari <- HR.

Nessuna rete: la connessione asyncpg verso l'archivio HR e' sostituita da
una finta che risponde alla sola query usata dal servizio (stessa tecnica di
``tests/test_hr_cedolini_deposito.py``); il gestionale usa
``MemorySheetsClient``.
"""
import asyncio
import json

from app.services.sheets_document_store import MemorySheetsClient

from app.services import salari_sync_hr as modulo
from app.services.salari_sync_hr import sincronizza_da_hr

DSN_FINTA = "postgresql://finto:finto@localhost/hr"


def _run(coro):
    return asyncio.run(coro)


def _db(nome):
    return MemorySheetsClient()[nome]


class ConnessioneHRFinta:
    def __init__(self, cedolini):
        self.cedolini = list(cedolini)

    async def fetch(self, sql, *args):
        assert "app_cedolini" in sql
        righe = self.cedolini
        if args:
            (anno,) = args
            righe = [c for c in righe if int(c["anno"]) == anno]
        return [{"id": c["id"], "doc": json.dumps(c)} for c in righe]

    async def close(self):
        pass


def _configura(monkeypatch, cedolini):
    monkeypatch.setenv("HR_SUPABASE_DB_URL", DSN_FINTA)
    connessione = ConnessioneHRFinta(cedolini)

    async def connetti(dsn):
        return connessione

    monkeypatch.setattr(modulo, "connetti_hr", connetti)
    return connessione


def _cedolino_hr(**extra):
    base = {
        "id": "hr-ced-1", "codice_fiscale": "PRSNTN80R12F839X",
        "nome_dipendente": "Parisi Antonio", "anno": 2026, "mese": 1,
        "tipo_cedolino": "ordinario", "netto": 1458.0,
    }
    base.update(extra)
    return base


def test_cedolino_hr_senza_prima_nota_viene_creato(monkeypatch):
    async def scenario():
        db = _db("crea_riga_mancante")
        _configura(monkeypatch, [_cedolino_hr()])

        report = await sincronizza_da_hr(db, dry_run=True, anno=2026)
        assert report["hr_configurato"] is True
        assert report["totale_cedolini_senza_prima_nota"] == 1
        assert report["cedolini_senza_prima_nota"][0]["codice_fiscale"] == "PRSNTN80R12F839X"
        assert (await db["prima_nota_salari"].find_one({})) is None

        esito = await sincronizza_da_hr(db, dry_run=False, anno=2026, riallinea_bonifici=False)
        assert esito["righe_create"] == 1
        riga = await db["prima_nota_salari"].find_one({"codice_fiscale": "PRSNTN80R12F839X"})
        assert riga is not None
        assert riga["anno"] == 2026 and riga["mese"] == 1
        assert riga["tipo_cedolino"] == "ordinario"
        assert riga["importo_busta"] == 1458.0
        assert riga["importo_bonifico"] == 0
        assert riga["saldo"] == -1458.0
        assert riga["hr_cedolino_id"] == "hr-ced-1"

        # Idempotente: un secondo giro non ricrea la riga.
        secondo = await sincronizza_da_hr(db, dry_run=False, anno=2026, riallinea_bonifici=False)
        assert secondo["righe_create"] == 0
        tutte = [r async for r in db["prima_nota_salari"].find({})]
        assert len(tutte) == 1

    _run(scenario())


def test_riga_con_netto_diverso_segnala_discrepanza_senza_sovrascrivere(monkeypatch):
    async def scenario():
        db = _db("discrepanza_netto")
        _configura(monkeypatch, [_cedolino_hr(netto=1458.0)])
        await db["prima_nota_salari"].insert_one({
            "id": "pn-parisi", "codice_fiscale": "PRSNTN80R12F839X",
            "dipendente": "PARISI ANTONIO", "anno": 2026, "mese": 1,
            "tipo_cedolino": "ordinario", "importo_busta": 1129.0,
            "importo_bonifico": 0,
        })

        report = await sincronizza_da_hr(db, dry_run=True, anno=2026)
        assert report["totale_cedolini_senza_prima_nota"] == 0
        assert report["totale_discrepanze_netto"] == 1
        discrepanza = report["discrepanze"][0]
        assert discrepanza["prima_nota_id"] == "pn-parisi"
        assert discrepanza["netto_hr"] == 1458.0
        assert discrepanza["importo_busta_gestionale"] == 1129.0

        # dry_run=False non deve mai toccare una riga con netto diverso.
        await sincronizza_da_hr(db, dry_run=False, anno=2026, riallinea_bonifici=False)
        riga = await db["prima_nota_salari"].find_one({"id": "pn-parisi"})
        assert riga["importo_busta"] == 1129.0

    _run(scenario())


def test_prima_nota_senza_cedolino_hr_viene_segnalata(monkeypatch):
    async def scenario():
        db = _db("senza_cedolino_hr")
        _configura(monkeypatch, [])  # archivio HR vuoto per l'anno
        await db["prima_nota_salari"].insert_one({
            "id": "pn-sankapala", "codice_fiscale": "SNKJNY74H48Z209K",
            "dipendente": "SANKAPALA_JANANIE", "anno": 2026, "mese": 2,
            "importo_busta": 954.0, "importo_bonifico": 0,
        })

        report = await sincronizza_da_hr(db, dry_run=True, anno=2026)
        assert report["totale_prima_nota_senza_cedolino_hr"] == 1
        voce = report["prima_nota_senza_cedolino_hr"][0]
        assert voce["id"] == "pn-sankapala"
        assert voce["codice_fiscale"] == "SNKJNY74H48Z209K"

    _run(scenario())


def test_senza_dsn_configurata_non_fallisce(monkeypatch):
    async def scenario():
        db = _db("senza_dsn")
        for nome in ("HR_SUPABASE_DB_URL", "APPDIPENDENTI_DB_URL", "SUPABASE_DB_URL"):
            monkeypatch.delenv(nome, raising=False)
        report = await sincronizza_da_hr(db, dry_run=True)
        assert report["hr_configurato"] is False

    _run(scenario())
