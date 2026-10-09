"""Audit avversariale sul consolidamento del motore conti (PR 19/09/2026,
`app/routers/accounting/piano_conti.py::determina_conti_fattura`).

Quattro problemi "DA CORREGGERE" trovati e corretti, uno per test-case:

1. Confidenza del motore ricco ignorata: "Mobile bar con ripiani in legno"
   matchava il pattern debole "mobile" di Telefonia (80% deducibile) invece
   di restare sul fallback generico (100% deducibile) — nessuna scrittura
   fiscale automatica a bassa confidenza (CLAUDE.md, sezione F24).
2. Categoria con accento diverso ("Caffè" vs "caffe") salvata con successo
   ma silenziosamente inefficace: ora o combacia (normalizzazione) o viene
   rifiutata esplicitamente alla creazione.
3. Ordine non deterministico tra regole utente sovrapposte dello stesso
   tipo: ora vince sempre il pattern piu' specifico, non il primo iterato.
"""
import asyncio

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

import app.routers.accounting.piano_conti as pcmod
from app.database import Database
from app.routers.accounting.regole_categorizzazione import (
    aggiungi_regola_fornitore,
    normalizza_categoria,
)
from tests.contabilita.test_motore_unico_conto_costo import _Db, _run


# ── 1. "Mobile bar" non deve più finire su Telefonia a bassa confidenza ─────

def test_mobile_bar_non_finisce_su_telefonia_bassa_confidenza():
    db = _Db()
    fattura = {
        "id": "MOBILEBAR1",
        "supplier_name": "ARREDI SCONOSCIUTI SRL",
        "linee": [{"descrizione": "Mobile bar in acciaio inox", "prezzo_totale": 800.0}],
    }

    conti = _run(pcmod.determina_conti_fattura(db, fattura))

    # Non più Telefonia (80% deducibile): il match "mobile" e' debole e
    # sotto soglia, quindi si ricade sul fallback generico 100% deducibile.
    assert conti["costo"]["codice"] != "05.02.07"
    assert conti["costo"]["codice"] == "05.01.01"


def test_mobile_bar_segnala_il_caso_bassa_confidenza():
    """Il caso non deve sparire nel nulla: viene upsertato in
    `agenti_segnalazioni`, stesso pattern gia' usato per l'anomalia cespiti."""
    db = _Db()
    fattura = {
        "id": "MOBILEBAR2",
        "supplier_name": "ARREDI SCONOSCIUTI SRL",
        "linee": [{"descrizione": "Mobile bar in acciaio inox", "prezzo_totale": 800.0}],
    }

    _run(pcmod.determina_conti_fattura(db, fattura))

    segnalazioni = db["agenti_segnalazioni"].docs
    assert any(
        s.get("tipo") == "conto_costo_bassa_confidenza" and s.get("fattura_id") == "MOBILEBAR2"
        for s in segnalazioni
    )
    sig = next(s for s in segnalazioni if s.get("fattura_id") == "MOBILEBAR2")
    assert sig["dettaglio"]["conto_scartato"] == "05.02.07"
    assert sig["dettaglio"]["confidenza"] < sig["dettaglio"]["soglia"]


def test_match_forte_su_telefonia_resta_applicato():
    """Contro-prova: un match FORTE su telefonia (es. "TIM") deve continuare
    ad applicarsi normalmente — il fix riguarda solo i pattern deboli."""
    db = _Db()
    fattura = {
        "id": "TELEFONIA1",
        "supplier_name": "TIM SPA",
        "linee": [{"descrizione": "Canone telefonico mensile", "prezzo_totale": 50.0}],
    }

    conti = _run(pcmod.determina_conti_fattura(db, fattura))

    assert conti["costo"]["codice"] == "05.02.07"


# ── 2. Categoria con accento diverso: combacia o viene rifiutata esplicitamente ──

def test_normalizza_categoria_toglie_accenti_e_spazi():
    assert normalizza_categoria("Caffè") == "caffe"
    assert normalizza_categoria("CAFFÈ") == "caffe"
    assert normalizza_categoria("  Caffe  ") == "caffe"
    assert normalizza_categoria("Bevande Analcoliche") == "bevande_analcoliche"


def test_regola_fornitore_con_categoria_accentata_trova_il_conto_giusto():
    """Una regola scritta con "Caffè" (accentato) deve risolvere lo stesso
    conto della chiave interna "caffe" (senza accento) — prima dell'audit
    restava silenziosamente inefficace."""
    db = _Db()
    db["regole_categorizzazione_fornitori"].docs.append({
        "pattern": "torrefazione ignota", "categoria": "Caffè", "attivo": True,
    })
    fattura = {
        "supplier_name": "TORREFAZIONE IGNOTA SRL",
        "linee": [{"descrizione": "Merce varia", "prezzo_totale": 40.0}],
    }

    conti = _run(pcmod.determina_conti_fattura(db, fattura))

    assert conti["costo"]["codice"] == "05.01.09"  # Acquisto caffe e affini


def _con_db_reale(coro):
    """Esegue una coroutine con un vero Database.db (mongomock) montato,
    come richiesto dagli endpoint del router (`Database.get_db()`)."""
    db = AsyncMongoMockClient()["gc"]
    Database.db = db
    try:
        return asyncio.run(coro(db))
    finally:
        Database.db = None


def test_creazione_regola_con_categoria_inesistente_viene_rifiutata():
    """Una categoria che non esiste (nemmeno dopo la normalizzazione) non
    viene più salvata silenziosamente: la creazione è rifiutata con un
    errore esplicito, e nessuna regola resta scritta."""

    async def _scenario(db):
        with pytest.raises(HTTPException) as exc_info:
            await aggiungi_regola_fornitore({
                "pattern": "FORNITORE FANTASIA",
                "categoria": "categoria completamente inventata xyz",
            })
        assert exc_info.value.status_code == 400
        assert "non esiste" in exc_info.value.detail.lower()
        rimaste = await db["regole_categorizzazione_fornitori"].find({}).to_list(10)
        assert rimaste == []

    _con_db_reale(_scenario)


def test_creazione_regola_con_categoria_esistente_accentata_viene_accettata():
    """Contro-prova: una categoria che esiste per davvero (anche scritta con
    un accento diverso da quello della chiave interna) viene accettata."""

    async def _scenario(db):
        risultato = await aggiungi_regola_fornitore({
            "pattern": "TORREFAZIONE NUOVA",
            "categoria": "Caffè",
        })
        assert risultato["success"] is True
        salvata = await db["regole_categorizzazione_fornitori"].find_one({"pattern": "TORREFAZIONE NUOVA"})
        assert salvata["categoria"] == "caffe"

    _con_db_reale(_scenario)


# ── 3. Ordine non deterministico tra regole utente sovrapposte ─────────────

def test_regole_sovrapposte_danno_sempre_il_risultato_piu_specifico():
    """Due regole "ACME"->consulenze e "ACME SRL"->manutenzione sulla
    fattura "ACME SRL": deve vincere sempre il pattern più specifico
    ("ACME SRL" -> manutenzione), indipendentemente dall'ordine di
    inserimento/iterazione."""
    fattura = {
        "supplier_name": "ACME SRL",
        "linee": [{"descrizione": "Merce varia", "prezzo_totale": 40.0}],
    }

    for ordine in (
        [("acme", "consulenze"), ("acme srl", "manutenzione")],
        [("acme srl", "manutenzione"), ("acme", "consulenze")],
    ):
        db = _Db()
        for pattern, categoria in ordine:
            db["regole_categorizzazione_fornitori"].docs.append({
                "pattern": pattern, "categoria": categoria, "attivo": True,
            })

        conti = _run(pcmod.determina_conti_fattura(db, fattura))

        # manutenzione -> 05.02.10 (piu' specifico di consulenze -> 05.02.12)
        assert conti["costo"]["codice"] == "05.02.10", ordine
