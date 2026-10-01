"""Export «Spese» di SumUp: arricchisce i movimenti dell'estratto, non diventa un estratto BPM."""
import asyncio
import io

import openpyxl
import pytest
from mongomock_motor import AsyncMongoMockClient

from app.services import sumup_conto as sc

TESTATA = ["N.", "Data", "Descrizione", "Importo netto", "Importo IVA", "Aliquota IVA", "Categoria",
           "Fornitore", "Paese", "Cod. Fisc./P. IVA", "Stato del pagamento"]


def _xlsx(righe):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(TESTATA)
    for r in righe:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


RIGHE = [
    [13, "2026-09-07", "Stipendio", "1095", "0", None, "Salari", "NOME PROVA", "IT", None, "Pagato"],
    [10, "2026-09-04", "Bank transfer", "1908,41", "419,85", "0,22", "Spese finanziarie", "MM S.p.a.", "IT", None, "Pagato"],
    [26, "2026-09-15", "Giroconto", "10.000", "0", None, "Giroconto", "Ceraldi Group srl", "IT", None, "Pagato"],
]


def _run(c):
    return asyncio.run(c)


def test_il_lordo_e_netto_piu_iva_e_i_decimali_italiani_si_leggono_giusti():
    letto = sc.leggi_spese_sumup_xlsx(_xlsx(RIGHE))
    assert letto["errori"] == []
    per_numero = {r["numero"]: r for r in letto["righe"]}
    assert (per_numero[10]["netto_cents"], per_numero[10]["iva_cents"]) == (190841, 41985)
    assert per_numero[26]["netto_cents"] == 1000000                      # «10.000» = diecimila, non dieci
    assert per_numero[13]["netto_cents"] == 109500 and per_numero[13]["iva_cents"] == 0


def test_un_altro_xlsx_non_e_l_export_spese():
    wb = openpyxl.Workbook()
    wb.active.append(["Data", "Descrizione", "Importo"])
    buf = io.BytesIO()
    wb.save(buf)
    with pytest.raises(ValueError):
        sc.leggi_spese_sumup_xlsx(buf.getvalue())
    assert sc.e_export_spese_sumup(TESTATA) is True and sc.e_export_spese_sumup(["Data", "Importo"]) is False


def _db(movimenti):
    db = AsyncMongoMockClient()["t"]
    _run(db[sc.COLL_MOVIMENTI].insert_many(movimenti))
    return db


def test_arricchisce_per_lordo_al_centesimo_senza_creare_ne_toccare_importi():
    db = _db([
        {"id": "sumup_conto:A", "data": "2026-09-07", "importo": "-1095.00"},
        {"id": "sumup_conto:B", "data": "2026-09-05", "importo": "-2328.26"},     # 1908,41 + 419,85
        {"id": "sumup_conto:C", "data": "2026-09-15", "importo": "-10000.00"},
        {"id": "sumup_conto:D", "data": "2026-09-07", "importo": "-5.00"},
    ])
    esito = _run(sc.arricchisci_da_spese_sumup(db, _xlsx(RIGHE), "expenses.xlsx"))
    assert esito["arricchiti"] == 3 and esito["ambigui"] == [] and esito["senza_movimento"] == []
    b = _run(db[sc.COLL_MOVIMENTI].find_one({"id": "sumup_conto:B"}))
    assert b["spesa_fornitore"] == "MM S.p.a." and b["spesa_iva_cents"] == 41985 and b["importo"] == "-2328.26"
    assert _run(db[sc.COLL_MOVIMENTI].count_documents({})) == 4
    # secondo giro: niente di nuovo
    assert _run(sc.arricchisci_da_spese_sumup(db, _xlsx(RIGHE), "expenses.xlsx"))["arricchiti"] == 0


def test_ambiguo_e_assente_si_elencano_e_l_anteprima_non_scrive():
    db = _db([
        {"id": "sumup_conto:A1", "data": "2026-09-07", "importo": "-1095.00"},
        {"id": "sumup_conto:A2", "data": "2026-09-07", "importo": "-1095.00"},
    ])
    esito = _run(sc.arricchisci_da_spese_sumup(db, _xlsx(RIGHE), "e.xlsx", dry_run=True))
    assert [v["riga"] for v in esito["ambigui"]] == [2]
    assert {v["riga"] for v in esito["senza_movimento"]} == {3, 4}
    assert _run(db[sc.COLL_MOVIMENTI].count_documents({"spesa_fonte": {"$exists": True}})) == 0


def test_documenti_import_riconosce_l_export_spese_e_non_lo_manda_all_estratto_bpm():
    from app.routers.documenti import detect_document_type

    assert detect_document_type("expenses_2026-08-01_2026-09-22.xlsx", _xlsx(RIGHE)) == "spese_sumup"


def test_import_errato_in_quarantena_per_id_con_anteprima_e_prima_nota_stornata():
    from app.services import doppioni_estratto_conto as d

    db = AsyncMongoMockClient()["t"]
    _run(db[d.COLLEZIONE].insert_many([
        {"id": "EC-1", "data": "2026-09-07", "importo": 0.0, "descrizione": "Stipendio", "source_filename": "expenses_x.xlsx"},
        {"id": "EC-2", "data": "2026-09-04", "importo": 419.85, "descrizione": "Bank transfer", "source_filename": "expenses_x.xlsx"},
        {"id": "EC-3", "data": "2026-09-04", "importo": -50.0, "descrizione": "Vero", "source_filename": "bpm.pdf"},
    ]))
    _run(db["prima_nota_banca"].insert_one({"id": "PN1", "estratto_conto_id": "EC-2", "status": "active"}))
    anteprima = _run(d.quarantena_import_errato(db, "expenses_x.xlsx", "letto col lettore sbagliato", dry_run=True))
    assert anteprima["righe"] == 2 and anteprima["prima_nota_da_stornare"] == 1
    assert _run(db[d.COLLEZIONE].count_documents({})) == 3                        # l'anteprima non scrive
    _run(d.quarantena_import_errato(db, "expenses_x.xlsx", "letto col lettore sbagliato", dry_run=False))
    assert _run(db[d.COLLEZIONE].count_documents({})) == 1                        # resta solo la riga vera
    assert _run(db[d.COLLEZIONE_QUARANTENA].count_documents({"motivo_quarantena": "letto col lettore sbagliato"})) == 2
    assert _run(db["prima_nota_banca"].find_one({"id": "PN1"}))["status"] == "deleted"
