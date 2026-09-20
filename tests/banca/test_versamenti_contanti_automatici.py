"""Il versamento si riconosce dall'estratto conto, senza premere niente.

Il titolare: «nell'estratto conto c'e' il segno, la descrizione e l'importo,
quindi non vedo perche' dovrebbe sbagliare. Non devo far riparare niente».

Il vecchio comando «Ripara versamenti» sbagliava per un motivo preciso: il
contante versato e' spesso **gia' scritto a mano** in Prima Nota Cassa il
giorno in cui esce dal negozio, mentre la banca lo contabilizza il giorno
dopo. Il comando creava comunque la gamba di cassa, e il contante usciva due
volte. Questi test tengono fermo che non possa piu' succedere.
"""
import asyncio

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.services.versamenti_contanti import classifica, riconosci_versamenti


def run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def db(monkeypatch):
    finto = AsyncMongoMockClient()["Gestionale_Test"]
    from app.database import Database

    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: finto))
    return finto


def _ec(id_, descrizione, importo, tipo, data="2026-03-10"):
    return {"id": id_, "descrizione_originale": descrizione, "importo": importo,
            "tipo": tipo, "data": data}


async def _prepara(db, movimenti):
    from app.database import Collections

    await db[Collections.BANK_STATEMENTS].insert_many(movimenti)


# ── il riconoscimento ──────────────────────────────────────────────────────

CASI = [
    ("VERS. CONTANTI - VVVVV", "entrata", "versamento"),
    ("VERSAMENTO CONTANTI", "entrata", "versamento"),
    ("PRELIEVO CONTANTI SPORTELLO", "uscita", "prelievo"),
    ("PRELEV. BANCOMAT CARTA 123", "uscita", "prelievo"),
    # Uno storno e' una rettifica della banca, non un secondo deposito.
    ("STORNO VERS. CONTANTI", "entrata", None),
    # Il segno deve concordare con la causale.
    ("VERS. CONTANTI - VVVVV", "uscita", None),
    ("PRELIEVO CONTANTI SPORTELLO", "entrata", None),
    ("BONIFICO A FAVORE DI TIZIO", "uscita", None),
    ("PRELIEVO ASSEGNO - DM 00000", "uscita", None),
]


@pytest.mark.parametrize("descrizione,verso,atteso", CASI,
                         ids=[f"{c[0][:22]}-{c[1]}" for c in CASI])
def test_riconoscimento(descrizione, verso, atteso):
    assert classifica({"descrizione_originale": descrizione, "tipo": verso}) == atteso


# ── le due gambe ───────────────────────────────────────────────────────────

def test_un_versamento_scrive_uscita_cassa_ed_entrata_banca(db):
    run(_prepara(db, [_ec("EC1", "VERS. CONTANTI - VVVVV", 5000.0, "entrata")]))

    esito = run(riconosci_versamenti(db, dry_run=False))

    cassa = run(db["prima_nota_cassa"].find({}).to_list(10))
    banca = run(db["prima_nota_banca"].find({}).to_list(10))
    assert len(cassa) == 1 and len(banca) == 1
    assert cassa[0]["tipo"] == "uscita" and banca[0]["tipo"] == "entrata"
    assert cassa[0]["importo"] == banca[0]["importo"] == 5000.0
    assert esito["versamenti"] == 1


def test_un_prelievo_e_il_movimento_opposto(db):
    run(_prepara(db, [_ec("EC2", "PRELIEVO CONTANTI SPORTELLO", 500.0, "uscita")]))

    run(riconosci_versamenti(db, dry_run=False))

    cassa = run(db["prima_nota_cassa"].find({}).to_list(10))
    banca = run(db["prima_nota_banca"].find({}).to_list(10))
    assert cassa[0]["tipo"] == "entrata" and banca[0]["tipo"] == "uscita"


def test_le_due_gambe_sono_collegate_fra_loro(db):
    """CLAUDE.md: due movimenti speculari con `trasferimento_collegato_id`,
    stesso `operation_id` e categoria `trasferimento_interno` — non un flag
    sul singolo movimento."""
    run(_prepara(db, [_ec("EC1", "VERS. CONTANTI", 1000.0, "entrata")]))

    run(riconosci_versamenti(db, dry_run=False))

    cassa = run(db["prima_nota_cassa"].find_one({}))
    banca = run(db["prima_nota_banca"].find_one({}))
    assert cassa["operation_id"] == banca["operation_id"] == "versamento:EC1"
    assert cassa["trasferimento_collegato_id"] == banca["id"]
    assert banca["trasferimento_collegato_id"] == cassa["id"]
    assert cassa["categoria"] == banca["categoria"] == "trasferimento_interno"


# ── il difetto che faceva uscire il contante due volte ─────────────────────

def test_la_cassa_gia_registrata_a_mano_si_collega_non_si_duplica(db):
    """Il negozio versa il 9, la banca contabilizza il 10."""
    run(db["prima_nota_cassa"].insert_one({
        "id": "MANUALE", "data": "2026-03-09", "importo": 5000.0, "tipo": "uscita",
        "categoria": "versamento", "descrizione": "Versamento in banca",
    }))
    run(_prepara(db, [_ec("EC1", "VERS. CONTANTI - VVVVV", 5000.0, "entrata",
                          data="2026-03-10")]))

    esito = run(riconosci_versamenti(db, dry_run=False))

    cassa = run(db["prima_nota_cassa"].find({}).to_list(10))
    assert len(cassa) == 1, (
        f"Il contante e' uscito due volte dalla cassa: {cassa}"
    )
    assert cassa[0]["id"] == "MANUALE"
    assert cassa[0]["operation_id"] == "versamento:EC1"
    assert esito["gambe_cassa_collegate"] == 1 and esito["gambe_cassa_create"] == 0


def test_fuori_dalla_finestra_di_giorni_non_si_collega(db):
    """Una riga di un mese prima non e' questo versamento."""
    run(db["prima_nota_cassa"].insert_one({
        "id": "VECCHIA", "data": "2026-02-01", "importo": 5000.0, "tipo": "uscita",
        "categoria": "versamento",
    }))
    run(_prepara(db, [_ec("EC1", "VERS. CONTANTI", 5000.0, "entrata", data="2026-03-10")]))

    esito = run(riconosci_versamenti(db, dry_run=False))

    assert esito["gambe_cassa_create"] == 1
    assert run(db["prima_nota_cassa"].find_one({"id": "VECCHIA"})).get("operation_id") is None


def test_un_importo_diverso_non_si_collega(db):
    """L'importo e' parte della prova: deve tornare al centesimo."""
    run(db["prima_nota_cassa"].insert_one({
        "id": "ALTRA", "data": "2026-03-10", "importo": 4999.0, "tipo": "uscita",
        "categoria": "versamento",
    }))
    run(_prepara(db, [_ec("EC1", "VERS. CONTANTI", 5000.0, "entrata", data="2026-03-10")]))

    assert run(riconosci_versamenti(db, dry_run=False))["gambe_cassa_create"] == 1


def test_una_riga_di_cassa_chiude_un_solo_versamento(db):
    """Due versamenti uguali lo stesso giorno non possono pescare la stessa riga."""
    run(db["prima_nota_cassa"].insert_one({
        "id": "MANUALE", "data": "2026-03-10", "importo": 5000.0, "tipo": "uscita",
        "categoria": "versamento",
    }))
    run(_prepara(db, [
        _ec("EC1", "VERS. CONTANTI", 5000.0, "entrata", data="2026-03-10"),
        _ec("EC2", "VERS. CONTANTI", 5000.0, "entrata", data="2026-03-10"),
    ]))

    esito = run(riconosci_versamenti(db, dry_run=False))

    assert esito["gambe_cassa_collegate"] == 1
    assert esito["gambe_cassa_create"] == 1
    assert run(db["prima_nota_cassa"].count_documents({})) == 2


# ── idempotenza ────────────────────────────────────────────────────────────

def test_rileggere_lo_stesso_estratto_non_duplica_niente(db):
    """Il criterio di collaudo: il secondo giro non scrive nulla di nuovo."""
    run(_prepara(db, [_ec("EC1", "VERS. CONTANTI", 5000.0, "entrata")]))

    run(riconosci_versamenti(db, dry_run=False))
    run(riconosci_versamenti(db, dry_run=False))
    run(riconosci_versamenti(db, dry_run=False))

    assert run(db["prima_nota_cassa"].count_documents({})) == 1
    assert run(db["prima_nota_banca"].count_documents({})) == 1


def test_per_difetto_non_scrive(db):
    run(_prepara(db, [_ec("EC1", "VERS. CONTANTI", 5000.0, "entrata")]))

    esito = run(riconosci_versamenti(db))

    assert esito["dry_run"] is True
    assert run(db["prima_nota_cassa"].count_documents({})) == 0


def test_senza_data_o_importo_si_segnala_non_si_indovina(db):
    run(_prepara(db, [{"id": "EC1", "descrizione_originale": "VERS. CONTANTI",
                       "importo": 0, "tipo": "entrata", "data": ""}]))

    esito = run(riconosci_versamenti(db, dry_run=False))

    assert esito["senza_data_o_importo"] == 1
    assert run(db["prima_nota_cassa"].count_documents({})) == 0


def test_lo_storno_non_crea_movimenti(db):
    run(_prepara(db, [_ec("EC1", "STORNO VERS. CONTANTI", 5000.0, "entrata")]))

    esito = run(riconosci_versamenti(db, dry_run=False))

    assert esito["esaminati"] == 0
    assert run(db["prima_nota_cassa"].count_documents({})) == 0


# ── gira da solo ───────────────────────────────────────────────────────────

def test_l_orchestratore_lo_chiama_senza_bottoni():
    """Non c'e' piu' niente da premere: sta nel giro dei 30 minuti."""
    import inspect

    from app.services import reconciliation_orchestrator as orchestratore

    sorgente = inspect.getsource(orchestratore.riconcilia_documenti_e_pagamenti)
    assert "riconosci_versamenti(db, anno=anno, dry_run=False)" in sorgente


def test_il_vecchio_comando_di_riparazione_non_esiste_piu():
    from app.routers.bank import estratto_conto

    assert not hasattr(estratto_conto, "ripara_versamenti_cassa")
