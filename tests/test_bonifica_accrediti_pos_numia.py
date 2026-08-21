"""Bonifica del vecchio import NUMIA in Prima Nota Banca.

Le componenti BNCMT/AMEX/INTER dello stesso giorno sono prove bancarie del
trasferimento giornaliero, non cinque rimborsi/ricavi indipendenti.
"""
import asyncio

from app.services.sheets_document_store import MemorySheetsClient
from pydantic import ValidationError
import pytest

from app.routers.sumup import NumiaRepairRequest
from app.services.scritture_contabili import (
    bonifica_accrediti_pos_numia,
    registra_chiusura_pos_reale,
)


ACCREDITI = [
    ("ec-1", 14.00, "NUMIA-BNCMT DEL 05/08/26 PDV 3757283/00011"),
    ("ec-2", 16.60, "NUMIA-BNCMT DEL 05/08/26 PDV 3757283/00012"),
    ("ec-3", 16.50, "NUMIA-AMEX DEL 05/08/26 PDV 3757283/00011"),
    ("ec-4", 523.00, "NUMIA-INTER DEL 05/08/26 PDV 3757283/00011"),
    ("ec-5", 244.00, "NUMIA-INTER DEL 05/08/26 PDV 3757283/00012"),
]


def _run(awaitable):
    return asyncio.run(awaitable)


def _db():
    return MemorySheetsClient()["bonifica_pos_numia_test"]


def test_payload_bonifica_numia_rifiuta_campi_e_anni_non_validi():
    with pytest.raises(ValidationError):
        NumiaRepairRequest.model_validate({"anno": 2019})
    with pytest.raises(ValidationError):
        NumiaRepairRequest.model_validate({"anno": 2026, "$where": "1 == 1"})


def _prepara(db):
    _run(registra_chiusura_pos_reale(
        db, "2026-08-05", 814.10, gestore="numia",
        fonte="manuale", actor={"sub": "test"},
    ))
    _run(registra_chiusura_pos_reale(
        db, "2026-08-05", 721.30, gestore="sumup",
        fonte="api", actor={"sub": "test"},
    ))
    for indice, (ec_id, importo, descrizione) in enumerate(ACCREDITI):
        _run(db["estratto_conto_movimenti"].insert_one({
            "id": ec_id,
            "data": "2026-08-06",
            "tipo": "entrata",
            "importo": importo,
            "descrizione_originale": descrizione,
            "riconciliato": False,
        }))
        _run(db["prima_nota_banca"].insert_one({
            "id": f"legacy-{indice}",
            "data": "2026-08-06",
            "tipo": "entrata",
            "importo": importo,
            "categoria": "Rimborso",
            "source": "export_bancario_operativo",
            "estratto_conto_id": ec_id,
            "status": "active",
        }))


def test_bonifica_archivia_le_cinque_copie_e_riconcilia_un_solo_totale():
    db = _db()
    _prepara(db)

    esito = _run(bonifica_accrediti_pos_numia(
        db, 2026, dry_run=False, actor={"sub": "test-admin"},
    ))

    assert esito["righe_prima_nota_archiviate"] == 5
    assert esito["giornate_riconciliate"] == 1
    assert esito["righe_ec_riconciliate"] == 5

    numia = _run(db["prima_nota_banca"].find_one({
        "source": "trasferimento_pos", "gestore": "numia",
    }))
    assert numia["importo"] == 814.10
    assert numia["accreditato_ec"] == 814.10
    assert numia["riconciliato"] is True
    assert numia["in_transito"] is False
    assert len(numia["estratto_conto_ids"]) == 5

    legacy = _run(db["prima_nota_banca"].find({
        "source": "export_bancario_operativo",
    }).to_list(20))
    assert len(legacy) == 5
    assert all(r["status"] == "archived" and r["deleted"] for r in legacy)
    assert _run(db["prima_nota_migrazioni_audit"].count_documents({})) == 5

    ec = _run(db["estratto_conto_movimenti"].find({}).to_list(20))
    assert all(r["riconciliato"] is True for r in ec)
    assert all(r["importato_prima_nota"] is False for r in ec)

    # Il circuito SumUp dello stesso giorno non viene mai sommato a Numia.
    sumup = _run(db["prima_nota_banca"].find_one({
        "source": "trasferimento_pos", "gestore": "sumup",
    }))
    assert sumup["importo"] == 721.30
    assert sumup.get("accreditato_ec") in (None, 0)


def test_bonifica_e_idempotente():
    db = _db()
    _prepara(db)

    _run(bonifica_accrediti_pos_numia(db, 2026, dry_run=False))
    secondo = _run(bonifica_accrediti_pos_numia(db, 2026, dry_run=False))

    assert secondo["righe_prima_nota_archiviate"] == 0
    assert _run(db["prima_nota_migrazioni_audit"].count_documents({})) == 5
    assert _run(db["prima_nota_banca"].count_documents({
        "source": "trasferimento_pos", "gestore": "numia",
        "status": {"$nin": ["deleted", "archived"]},
    })) == 1


def test_anteprima_non_modifica_la_prima_nota():
    db = _db()
    _prepara(db)

    esito = _run(bonifica_accrediti_pos_numia(db, 2026, dry_run=True))

    assert esito["righe_prima_nota_da_archiviare"] == 5
    assert esito["righe_prima_nota_archiviate"] == 0
    assert _run(db["prima_nota_banca"].count_documents({
        "source": "export_bancario_operativo", "status": "active",
    })) == 5
    assert _run(db["prima_nota_migrazioni_audit"].count_documents({})) == 0


def test_due_trasferimenti_numia_nello_stesso_giorno_restano_ambigui():
    db = _db()
    _prepara(db)
    _run(db["prima_nota_banca"].insert_one({
        "id": "numia-duplicato",
        "data": "2026-08-05",
        "giorno_vendita": "2026-08-05",
        "anno": 2026,
        "tipo": "entrata",
        "importo": 814.10,
        "source": "trasferimento_pos",
        "gestore": "numia",
        "status": "active",
    }))

    esito = _run(bonifica_accrediti_pos_numia(db, 2026, dry_run=False))

    assert esito["giornate_trasferimento_ambiguo"] == 1
    assert esito["giornate_riconciliate"] == 0
    assert esito["dettaglio"][0]["stato"] == "trasferimenti_duplicati"
    # Nessun candidato viene scelto e nessuna prova bancaria viene marcata
    # riconciliata finche' l'ambiguita' non e' risolta.
    assert _run(db["estratto_conto_movimenti"].count_documents({
        "riconciliato": True,
    })) == 0
