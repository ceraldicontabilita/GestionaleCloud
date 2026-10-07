"""Credito IVA della dichiarazione annuale (rigo VX5) → gennaio dell'anno dopo.

Caso reale 07/10/2026: la dichiarazione IVA 2026 (periodo 2025) e' in
archivio con VL33 = VL39 = VX2 = 4.676 €, ma nessuna liquidazione di
dicembre 2025 e' confermata nel gestionale: gennaio 2026 partiva con
credito precedente 0 senza dirlo. Importi gia' letti dal lettore dei
quadri; nessun PDF reale nel repository.
"""
import asyncio

import pytest

from app.database import Database
from app.routers import iva as iva_router
from app.services import dichiarazioni_quadri as dq
from app.services.archivio_documenti_memoria import ClientArchivioMemoria

SOCIETA = "04523831214"


def _run(coro):
    return asyncio.run(coro)


def _db():
    return ClientArchivioMemoria()["credito_annuale"]


def _dichiarazione(db, doc_id, anno, *, vx5=None, vx5_motivo=None, vx2="4676.00", senza_vx5=False,
                   identificativo="18402817671 - 0000001"):
    campi = {"vx2_a_credito": {"valore": vx2, "motivo": None if vx2 else "casella_vuota",
                               "pagina": 11, "rigo": "VX2"}}
    if not senza_vx5:
        campi["vx5_da_riportare"] = {"valore": vx5, "motivo": vx5_motivo, "pagina": 11, "rigo": "VX5"}
    _run(db["fiscal_documents"].insert_one({
        "id": doc_id, "company_id": SOCIETA, "document_type": "DICHIARAZIONE_IVA",
        "filename": f"{doc_id}.pdf",
        "quadri": {"anno_imposta": anno, "identificativo": identificativo, "campi": campi},
    }))


def test_vx5_letto_e_il_credito_riportato():
    db = _db()
    _dichiarazione(db, "iva2026", 2025, vx5="4676.00")
    esito = _run(dq.credito_iva_riportato(db, 2025, company_id=SOCIETA))
    assert esito["credito"] == "4676.00" and esito["motivo"] is None
    assert esito["fonte"]["rigo"] == "VX5" and esito["fonte"]["document_id"] == "iva2026"


def test_senza_dichiarazione_in_archivio_niente_credito_e_niente_zero():
    esito = _run(dq.credito_iva_riportato(_db(), 2025, company_id=SOCIETA))
    assert esito == {"credito": None, "motivo": "dichiarazione_non_in_archivio", "fonte": None}


def test_vx5_non_letto_dal_lettore_precedente_non_usa_vx2():
    """VX2 e' «da ripartire» fra rimborso, detrazione e consolidato: senza
    VX5 il credito riportato non si deduce. Si rilancia la lettura."""
    db = _db()
    _dichiarazione(db, "iva2026", 2025, senza_vx5=True)
    esito = _run(dq.credito_iva_riportato(db, 2025, company_id=SOCIETA))
    assert esito["credito"] is None
    assert esito["motivo"] == "vx5_non_letto_rilanciare_quadri"
    assert esito["documenti"] == ["iva2026.pdf"]


def test_vx5_vuoto_con_quadro_letto_e_uno_zero_vero():
    db = _db()
    _dichiarazione(db, "iva2026", 2025, vx5=None, vx5_motivo="casella_vuota", vx2=None)
    esito = _run(dq.credito_iva_riportato(db, 2025, company_id=SOCIETA))
    assert esito["credito"] == "0.00" and esito["motivo"] is None


def test_due_copie_concordi_valgono_una_e_discordi_fermano():
    db = _db()
    _dichiarazione(db, "copia1", 2025, vx5="4676.00")
    _dichiarazione(db, "copia2", 2025, vx5="4676.00")
    assert _run(dq.credito_iva_riportato(db, 2025, company_id=SOCIETA))["credito"] == "4676.00"
    _dichiarazione(db, "copia3", 2025, vx5="4000.00")
    esito = _run(dq.credito_iva_riportato(db, 2025, company_id=SOCIETA))
    assert esito["credito"] is None and esito["motivo"] == "dichiarazioni_discordanti"
    assert esito["candidati"] == ["4000.00", "4676.00"]


def test_gennaio_prende_il_credito_dalla_dichiarazione_quando_dicembre_non_e_confermato(monkeypatch):
    db = _db()
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))
    _dichiarazione(db, "iva2026", 2025, vx5="4676.00")
    credito, fonte = _run(iva_router._credito_precedente(db, "2026-01"))
    assert credito == 4676.0
    assert fonte["tipo"] == "dichiarazione_annuale" and fonte["rigo"] == "VX5"
    # Febbraio non guarda la dichiarazione: senza gennaio confermato dice che manca.
    credito, fonte = _run(iva_router._credito_precedente(db, "2026-02"))
    assert credito == 0.0 and fonte["tipo"] == "non_disponibile"
    assert fonte["motivo"] == "liquidazione_precedente_non_confermata"


def test_gennaio_senza_dichiarazione_dichiara_il_dato_mancante():
    credito, fonte = _run(iva_router._credito_precedente(_db(), "2026-01"))
    assert credito == 0.0
    assert fonte == {"tipo": "non_disponibile", "motivo": "dichiarazione_non_in_archivio", "dettaglio": None}


def test_la_liquidazione_confermata_di_dicembre_vince_sulla_dichiarazione():
    db = _db()
    _dichiarazione(db, "iva2026", 2025, vx5="4676.00")
    _run(db["liquidazioni_iva"].insert_one({"id": "liq-dic", "periodo": "2025-12", "versione": 1,
                                            "stato": "CONFERMATA", "credito_periodo": 4600.0}))
    credito, fonte = _run(iva_router._credito_precedente(db, "2026-01"))
    assert credito == 4600.0 and fonte["tipo"] == "liquidazione_confermata"


def test_il_lettore_dei_quadri_legge_anche_vx5():
    from tests.fiscale.test_dichiarazioni_quadri import IVA22_VL, IVA22_VX, TESTO_VL, TESTO_VX, _pagina
    # VX5 sotto VX2 nel modulo: stessa casella (segnaposto ,00) e lo stesso 451.
    vx = IVA22_VX + [[108.37, 217.59, 123.09, 226.46, "VX5"], [549.76, 220.48, 559.87, 228.41, ",00"],
                     [530.0, 216.57, 548.0, 229.06, "451"]]
    esito = dq.estrai_quadri_pagine([_pagina(9, TESTO_VL, IVA22_VL), _pagina(11, TESTO_VX + "VX5\n", vx)])
    assert esito["campi"]["vx5_da_riportare"]["valore"] == "451.00"
    assert esito["campi"]["vx5_da_riportare"]["rigo"] == "VX5"
