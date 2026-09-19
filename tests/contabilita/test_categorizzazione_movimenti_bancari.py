"""Motore unico di categorizzazione dei movimenti bancari da descrizione
(`app/services/categorizzazione_movimenti.py`).

Il 18/09/2026 esistevano due funzioni omonime, nessuna collegata al vero
import (`app/routers/bank/estratto_conto.py`): 1.764 dei 1.920 movimenti
bancari 2026 (92%) restavano senza categoria. Questi test coprono i quattro
casi richiesti dal titolare: F24, pattern generico non ambiguo, nessun
pattern, e il caso ambiguo che NON deve categorizzare (CLAUDE.md, "Identita',
prove e attese": nessuna associazione per solo importo o per tentativo)."""
import asyncio

import pytest

from app.services.categorizzazione_movimenti import (
    backfill_categorie_banca,
    categorizza_movimento_bancario,
)
from app.services.sheets_document_store import MemorySheetsClient


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# --- F24 --------------------------------------------------------------

def test_f24_riconosciuto_da_parola_chiave():
    esito = categorizza_movimento_bancario("ADDEBITO F24 IVA E RITENUTE", -780.0)
    assert esito.categoria == "F24"
    assert not esito.ambiguo


def test_f24_arricchito_dal_codice_tributo_quando_presente():
    esito = categorizza_movimento_bancario("PAGAMENTO F24 COD.6001 IVA SALDO", -500.0)
    assert esito.categoria == "F24"
    assert esito.codice_tributo == "6001"


def test_f24_inps_riconosciuto_da_codice_dm():
    esito = categorizza_movimento_bancario("VERSAMENTO F24 DM10 CONTRIBUTI", -300.0)
    assert esito.categoria == "F24"
    assert esito.codice_tributo == "DM10"


# --- Pattern generico non ambiguo --------------------------------------

def test_commissioni_bancarie_riconosciute():
    esito = categorizza_movimento_bancario("COMMISSIONI TRIMESTRALI C/C", -12.5)
    assert esito.categoria == "Commissioni bancarie"


def test_utenza_riconosciuta_dal_marchio():
    esito = categorizza_movimento_bancario("ADDEBITO SDD ENEL ENERGIA SPA", -145.0)
    assert esito.categoria == "Utenze"


def test_fattura_fornitore_riconosciuta_da_riferimento_esplicito():
    esito = categorizza_movimento_bancario(
        "BONIFICO A FAVORE SCARAMUZZA SPA - SALDO FATTURA 123", -1807.71,
    )
    assert esito.categoria == "Fatture"


def test_assicurazione_va_su_fatture_come_la_tassonomia_bancaria():
    esito = categorizza_movimento_bancario("ADDEBITO POLIZZA RC PROFESSIONALE", -320.0)
    assert esito.categoria == "Fatture"


# --- Nessun pattern -----------------------------------------------------

def test_nessun_pattern_riconosciuto_resta_senza_categoria():
    esito = categorizza_movimento_bancario("BONIFICO A FAVORE MARIO ROSSI", -250.0)
    assert esito.categoria is None
    assert not esito.ambiguo
    assert "nessun pattern" in esito.motivo


def test_descrizione_vuota_non_categorizza():
    esito = categorizza_movimento_bancario("", -10.0)
    assert esito.categoria is None


def test_non_associa_mai_per_solo_importo():
    """Stesso importo di una fattura aperta non basta: senza un riferimento
    testuale la riga resta senza categoria."""
    esito = categorizza_movimento_bancario("BONIFICO A FAVORE FORNITORE XYZ", -1807.71)
    assert esito.categoria is None


def test_non_duplica_gli_stipendi_ne_il_versamento_prelievo_generico():
    """ADD.TOT/VS.DISP da soli non bastano: quello ha un motore proprio piu'
    rigoroso (app.services.stipendi_bonifici)."""
    esito = categorizza_movimento_bancario("VS.DISP FAVORE ADD.TOT", -1200.0)
    assert esito.categoria is None


# --- Ambiguo --------------------------------------------------------------

def test_pattern_in_conflitto_non_categorizza():
    esito = categorizza_movimento_bancario("PAGAMENTO F24 SALDO FATTURA 99", -900.0)
    assert esito.categoria is None
    assert esito.ambiguo
    assert "ambiguo" in esito.motivo


# --- Backfill -------------------------------------------------------------

def test_backfill_categorizza_solo_i_pattern_certi_e_riporta_il_resto():
    db = MemorySheetsClient()["backfill_categorie"]

    async def scenario():
        await db["estratto_conto_movimenti"].insert_many([
            {"id": "1", "data": "2026-03-01", "importo": 780.0,
             "descrizione_originale": "ADDEBITO F24 IVA E RITENUTE", "categoria": ""},
            {"id": "2", "data": "2026-03-02", "importo": 12.5,
             "descrizione_originale": "COMMISSIONI TRIMESTRALI C/C", "categoria": None},
            {"id": "3", "data": "2026-03-03", "importo": 250.0,
             "descrizione_originale": "BONIFICO A FAVORE MARIO ROSSI", "categoria": ""},
            # gia' categorizzato dal CSV bancario: non va toccato
            {"id": "4", "data": "2026-03-04", "importo": 99.0,
             "descrizione_originale": "QUALSIASI COSA", "categoria": "Rimborso"},
        ])
        return await backfill_categorie_banca(db, anno=2026, dry_run=False)

    esito = _run(scenario())

    assert esito["movimenti_esaminati"] == 3  # il 4 aveva gia' categoria
    assert esito["per_categoria"] == {"F24": 1, "Commissioni bancarie": 1}
    assert esito["aggiornati"] == 2
    assert esito["non_riconosciuti"] == 1

    mov1 = _run(db["estratto_conto_movimenti"].find_one({"id": "1"}))
    assert mov1["categoria"] == "F24"
    assert mov1["categoria_auto"] is True
    assert "categoria_codice_tributo" not in mov1  # nessun codice tributo in questa causale

    mov4 = _run(db["estratto_conto_movimenti"].find_one({"id": "4"}))
    assert mov4["categoria"] == "Rimborso"
    assert not mov4.get("categoria_auto")


def test_backfill_dry_run_non_scrive_nulla():
    db = MemorySheetsClient()["backfill_dry_run"]

    async def scenario():
        await db["estratto_conto_movimenti"].insert_one(
            {"id": "1", "data": "2026-05-01", "importo": 780.0,
             "descrizione_originale": "ADDEBITO F24 IVA E RITENUTE", "categoria": ""})
        return await backfill_categorie_banca(db, anno=2026, dry_run=True)

    esito = _run(scenario())
    assert esito["dry_run"] is True
    assert esito["per_categoria"] == {"F24": 1}
    assert esito["aggiornati"] == 0

    mov = _run(db["estratto_conto_movimenti"].find_one({"id": "1"}))
    assert mov["categoria"] == ""
