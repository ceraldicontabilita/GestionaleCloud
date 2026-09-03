"""Audit del commercialista 03/09/2026, §5 / PR 13.

Regola di LOGICA_FUNZIONAMENTO.md §7: un bonifico al dipendente prima del
giorno 25 e' riferito al cedolino del mese precedente. Casi reali:
Capezzuto 430,00 e Vespa 406,00 pagati il 20/02/2026 sono i SALDI di gennaio
(1.430 - 1.000 di acconto; 1.406 - 1.000), non acconti di febbraio.
"""
import asyncio

from app.routers.bank import estratto_conto
from app.services.sheets_document_store import MemorySheetsClient
from app.services.stipendi_bonifici import (
    associa_bonifici_stipendi,
    competenza_bonifico_stipendio,
    periodo_atteso_bonifico,
    riallinea_competenza_bonifici_stipendi,
)

CAUSALE_CAPEZZUTO = "VS.DISP. RIF. MB0B19307858/90207967 FAVORE CAPEZZUTO ALESSANDRO - ADD.TOT"
CAUSALE_VESPA = "VS.DISP. RIF. MB0B19307850/90207955 FAVORE VESPA VINCENZO - ADD.TOT"
EC_CAPEZZUTO = "EC-2026-02-20-430.00-b300d6c5"
EC_VESPA_SALDO = "EC-2026-02-20-406.00-65d1df9a"
EC_VESPA_ACCONTO = "EC-2026-02-03-1000.00-035cfc0b"


def _run(coro):
    return asyncio.run(coro)


def _riga(id_riga, nome, mese, anno, busta, bonifico=0.0, movimenti=None):
    movimenti = list(movimenti or [])
    return {
        "id": id_riga, "dipendente": nome, "mese": mese, "anno": anno,
        "importo_busta": busta, "importo_bonifico": bonifico,
        "saldo": round(busta - bonifico, 2) if movimenti else -busta,
        "riconciliato": bool(movimenti) and abs(busta - bonifico) <= 0.009,
        "stato_bonifico": (
            None if not movimenti else
            "riconciliato" if abs(busta - bonifico) <= 0.009 else "parzialmente_riconciliato"
        ),
        "movimenti_bancari_ids": movimenti,
        "source": "indice_cedolini_drive",
    }


def _movimento(ec_id, data, importo, causale, stipendio_id=None):
    doc = {
        "id": ec_id, "data": data, "importo": importo, "tipo": "uscita",
        "descrizione_originale": causale, "riconciliato": stipendio_id is not None,
    }
    if stipendio_id:
        doc.update({
            "stipendio_id": stipendio_id, "categoria": "Stipendi",
            "tipo_riconciliazione": "stipendio_nome_importo_entro_residuo",
        })
    return doc


def test_regola_del_giorno_25():
    assert competenza_bonifico_stipendio("2026-02-20") == (1, 2026)
    assert competenza_bonifico_stipendio("2026-02-03") == (1, 2026)
    assert competenza_bonifico_stipendio("2026-01-07") == (12, 2025)
    assert competenza_bonifico_stipendio("2026-02-24") == (1, 2026)
    assert competenza_bonifico_stipendio("2026-02-25") == (2, 2026)
    assert competenza_bonifico_stipendio("2026-03-30") == (3, 2026)
    assert competenza_bonifico_stipendio("data-non-valida") is None
    # la causale esplicita vince sempre sulla data
    assert periodo_atteso_bonifico("STIPENDIO FEBBRAIO 2026", "2026-02-20") == (2, 2026)
    assert periodo_atteso_bonifico(CAUSALE_VESPA, "2026-02-20") == (1, 2026)


def test_saldo_del_20_febbraio_chiude_gennaio_non_febbraio():
    async def scenario():
        db = MemorySheetsClient()["competenza-associa"]
        await db.prima_nota_salari.insert_many([
            _riga("cap-gen", "CAPEZZUTO ALESSANDRO", 1, 2026, 1430.0, 1000.0, ["EC-ACC-CAP"]),
            _riga("cap-feb", "CAPEZZUTO ALESSANDRO", 2, 2026, 801.0),
            _riga("vespa-gen", "VESPA VINCENZO", 1, 2026, 1406.0, 1000.0, [EC_VESPA_ACCONTO]),
            _riga("vespa-feb", "VESPA VINCENZO", 2, 2026, 890.0),
        ])
        await db.estratto_conto_movimenti.insert_many([
            _movimento("EC-ACC-CAP", "2026-02-03", 1000.0,
                       "VS.DISP. RIF. X FAVORE CAPEZZUTO ALESSANDRO - ADD.TOT", "cap-gen"),
            _movimento(EC_VESPA_ACCONTO, "2026-02-03", 1000.0, CAUSALE_VESPA, "vespa-gen"),
            _movimento(EC_CAPEZZUTO, "2026-02-20", 430.0, CAUSALE_CAPEZZUTO),
            _movimento(EC_VESPA_SALDO, "2026-02-20", 406.0, CAUSALE_VESPA),
        ])

        risultato = await associa_bonifici_stipendi(db)

        assert risultato["bonifici_associati"] == 2
        assert risultato["righe_stipendio_completate"] == 2
        for riga_id, ec_id in (("cap-gen", EC_CAPEZZUTO), ("vespa-gen", EC_VESPA_SALDO)):
            gennaio = await db.prima_nota_salari.find_one({"id": riga_id}, {"_id": 0})
            assert gennaio["riconciliato"] is True
            assert gennaio["saldo"] == 0.0
            assert ec_id in gennaio["movimenti_bancari_ids"]
            movimento = await db.estratto_conto_movimenti.find_one({"id": ec_id}, {"_id": 0})
            assert movimento["stipendio_id"] == riga_id
        for riga_id in ("cap-feb", "vespa-feb"):
            febbraio = await db.prima_nota_salari.find_one({"id": riga_id}, {"_id": 0})
            assert not febbraio.get("importo_bonifico")
            assert febbraio.get("riconciliato") is not True

    _run(scenario())


def _db_come_in_produzione():
    """Stato reale letto il 03/09/2026: i saldi del 20/02 stanno su febbraio;
    la riga di gennaio di Capezzuto non esiste in prima nota."""
    db = MemorySheetsClient()["competenza-riallineo"]

    async def semina():
        await db.prima_nota_salari.insert_many([
            _riga("c75fd3ab", "CAPEZZUTO ALESSANDRO", 2, 2026, 801.0, 430.0, [EC_CAPEZZUTO]),
            _riga("fd1dd4f6", "VESPA VINCENZO", 1, 2026, 1406.0, 1000.0, [EC_VESPA_ACCONTO]),
            _riga("4f615ee9", "VESPA VINCENZO", 2, 2026, 890.0, 406.0, [EC_VESPA_SALDO]),
            # dicembre 2025 pagato il 07/01: gia' coerente con la regola
            _riga("5d94d38f", "VESPA VINCENZO", 12, 2025, 457.0, 457.0, ["EC-2026-01-07-457.00-ee011d07"]),
        ])
        await db.estratto_conto_movimenti.insert_many([
            _movimento(EC_CAPEZZUTO, "2026-02-20", 430.0, CAUSALE_CAPEZZUTO, "c75fd3ab"),
            _movimento(EC_VESPA_ACCONTO, "2026-02-03", 1000.0, CAUSALE_VESPA, "fd1dd4f6"),
            _movimento(EC_VESPA_SALDO, "2026-02-20", 406.0, CAUSALE_VESPA, "4f615ee9"),
            _movimento("EC-2026-01-07-457.00-ee011d07", "2026-01-07", 457.0,
                       "VS.DISP. RIF. MB0B97111828/90415023 FAVORE VESPA VINCENZO - ADD.TOT", "5d94d38f"),
        ])
        await db.entity_relations.insert_many([
            {"relation_key": f"bank_movement|{EC_CAPEZZUTO}|allocates_salary_payment|salary_entry|c75fd3ab",
             "relation_type": "allocates_salary_payment", "status": "confirmed",
             "source": {"type": "bank_movement", "id": EC_CAPEZZUTO},
             "target": {"type": "salary_entry", "id": "c75fd3ab"}},
            {"relation_key": f"bank_movement|{EC_VESPA_SALDO}|allocates_salary_payment|salary_entry|4f615ee9",
             "relation_type": "allocates_salary_payment", "status": "confirmed",
             "source": {"type": "bank_movement", "id": EC_VESPA_SALDO},
             "target": {"type": "salary_entry", "id": "4f615ee9"}},
        ])

    asyncio.run(semina())
    return db


def test_riallineo_dry_run_elenca_senza_scrivere():
    db = _db_come_in_produzione()

    esito = _run(riallinea_competenza_bonifici_stipendi(db, dry_run=True, anno=2026))

    assert esito["dry_run"] is True
    assert esito["coerenti"] == 2  # acconto del 03/02 su gennaio, dicembre pagato il 07/01
    assert esito["totale_da_riallineare"] == 2
    assert esito["ambigui"] == []
    [spostamento] = esito["spostamenti"]
    assert spostamento["movimento_id"] == EC_VESPA_SALDO
    assert spostamento["da"] == {"id": "4f615ee9", "mese": 2, "anno": 2026}
    assert spostamento["a"] == {"id": "fd1dd4f6", "mese": 1, "anno": 2026}
    [senza] = esito["senza_destinazione"]
    assert senza["movimento_id"] == EC_CAPEZZUTO
    assert senza["periodo_atteso"] == {"mese": 1, "anno": 2026}

    async def invariato():
        febbraio = await db.prima_nota_salari.find_one({"id": "4f615ee9"}, {"_id": 0})
        movimento = await db.estratto_conto_movimenti.find_one({"id": EC_VESPA_SALDO}, {"_id": 0})
        return febbraio["importo_bonifico"], movimento["stipendio_id"]

    assert _run(invariato()) == (406.0, "4f615ee9")


def test_riallineo_applica_sposta_stacca_ed_e_idempotente():
    db = _db_come_in_produzione()

    esito = _run(riallinea_competenza_bonifici_stipendi(db, dry_run=False, anno=2026, actor="test"))

    assert esito["spostamenti_applicati"] == 1
    assert esito["movimenti_staccati"] == 1
    assert esito["righe_aggiornate"] == 3
    assert esito["relazioni_revocate"] == 2
    assert esito["relazioni_create"] == 1

    async def leggi():
        salari = {r["id"]: r for r in await db.prima_nota_salari.find({}, {"_id": 0}).to_list(None)}
        movimenti = {m["id"]: m for m in await db.estratto_conto_movimenti.find({}, {"_id": 0}).to_list(None)}
        relazioni = await db.entity_relations.find({}, {"_id": 0}).to_list(None)
        audit = await db.prima_nota_migrazioni_audit.find({}, {"_id": 0}).to_list(None)
        return salari, movimenti, relazioni, audit

    salari, movimenti, relazioni, audit = _run(leggi())
    # Vespa: gennaio chiuso (1.000 + 406 = 1.406), febbraio torna da pagare
    gennaio = salari["fd1dd4f6"]
    assert gennaio["movimenti_bancari_ids"] == [EC_VESPA_ACCONTO, EC_VESPA_SALDO]
    assert gennaio["importo_bonifico"] == 1406.0
    assert gennaio["saldo"] == 0.0 and gennaio["riconciliato"] is True
    assert gennaio["stato_bonifico"] == "riconciliato"
    assert gennaio["data_pagamento"] == "2026-02-20"
    febbraio = salari["4f615ee9"]
    assert febbraio["movimenti_bancari_ids"] == []
    assert febbraio["importo_bonifico"] == 0 and febbraio["saldo"] == -890.0
    assert febbraio["riconciliato"] is False and febbraio["stato_bonifico"] is None
    assert movimenti[EC_VESPA_SALDO]["stipendio_id"] == "fd1dd4f6"
    assert movimenti[EC_VESPA_SALDO]["riconciliato"] is True
    # Capezzuto: gennaio non esiste in prima nota -> il 430 viene staccato
    cap_feb = salari["c75fd3ab"]
    assert cap_feb["movimenti_bancari_ids"] == [] and cap_feb["importo_bonifico"] == 0
    assert movimenti[EC_CAPEZZUTO]["riconciliato"] is False
    assert movimenti[EC_CAPEZZUTO]["stipendio_id"] is None
    assert movimenti[EC_CAPEZZUTO]["riallineo_periodo_atteso"] == "01/2026"
    # dicembre non toccato
    assert salari["5d94d38f"]["importo_bonifico"] == 457.0
    # relazioni: vecchie revocate, nuova confermata
    stati = {r["relation_key"]: r["status"] for r in relazioni}
    assert stati[f"bank_movement|{EC_VESPA_SALDO}|allocates_salary_payment|salary_entry|4f615ee9"] == "revoked"
    assert stati[f"bank_movement|{EC_CAPEZZUTO}|allocates_salary_payment|salary_entry|c75fd3ab"] == "revoked"
    assert stati[f"bank_movement|{EC_VESPA_SALDO}|allocates_salary_payment|salary_entry|fd1dd4f6"] == "confirmed"
    assert audit[0]["migrazione"] == "riallineo_competenza_bonifici_stipendi_2026-09-03"

    di_nuovo = _run(riallinea_competenza_bonifici_stipendi(db, dry_run=False, anno=2026))
    assert di_nuovo["totale_da_riallineare"] == 0
    assert di_nuovo["righe_aggiornate"] == 0

    # quando la riga di gennaio di Capezzuto verra' creata (PR 15), il 430
    # staccato si aggancia da solo con l'associazione ordinaria
    _run(db.prima_nota_salari.insert_one(_riga("cap-gen", "CAPEZZUTO ALESSANDRO", 1, 2026, 1430.0, 1000.0, ["EC-ACC-CAP"])))
    _run(db.estratto_conto_movimenti.insert_one(_movimento(
        "EC-ACC-CAP", "2026-02-03", 1000.0, "VS.DISP. RIF. X FAVORE CAPEZZUTO ALESSANDRO - ADD.TOT", "cap-gen",
    )))
    risultato = _run(associa_bonifici_stipendi(db, anno=2026))
    assert risultato["riallineo_competenza"]["totale_da_riallineare"] == 0
    assert risultato["bonifici_associati"] == 1
    cap_gen = _run(db.prima_nota_salari.find_one({"id": "cap-gen"}, {"_id": 0}))
    assert cap_gen["riconciliato"] is True and cap_gen["importo_bonifico"] == 1430.0


def test_associazione_batch_riallinea_da_sola_prima_di_associare():
    db = _db_come_in_produzione()

    risultato = _run(associa_bonifici_stipendi(db, anno=2026))

    assert risultato["riallineo_competenza"]["spostamenti_applicati"] == 1
    assert risultato["riallineo_competenza"]["movimenti_staccati"] == 1
    gennaio = _run(db.prima_nota_salari.find_one({"id": "fd1dd4f6"}, {"_id": 0}))
    assert gennaio["riconciliato"] is True
    # il 430 staccato non viene riagganciato a febbraio dal giro ordinario
    cap_feb = _run(db.prima_nota_salari.find_one({"id": "c75fd3ab"}, {"_id": 0}))
    assert cap_feb["importo_bonifico"] == 0


def test_endpoint_batch_dry_run_non_scrive(monkeypatch):
    db = _db_come_in_produzione()
    monkeypatch.setattr(estratto_conto.Database, "get_db", staticmethod(lambda: db))

    esito = _run(estratto_conto.riconcilia_stipendi_automatico(anno=2026, dry_run=True))

    assert esito["dry_run"] is True
    assert esito["totale_da_riallineare"] == 2
    febbraio = _run(db.prima_nota_salari.find_one({"id": "4f615ee9"}, {"_id": 0}))
    assert febbraio["importo_bonifico"] == 406.0
