"""Cartella di pagamento: lettura, attesa «da pagare», verbale e ricevuta con lo stesso IUV (dati inventati)."""
import asyncio
import os

import fitz
from mongomock_motor import AsyncMongoMockClient

from app.services import cartelle_pagamento as cp

IUV = "80070000000000123"
NUMERO = "071 2026 00000001 11/000"

RIGHE = [
    "Spett. AZIENDA TEST SRL",
    f"CARTELLA DI PAGAMENTO N. {NUMERO}",
    "Agenzia delle entrate-Riscossione",
    "Totale da pagare entro 60 giorni dalla data di notifica",
    "euro 118,88",
    "113,00",
    "5,88",
    "118,88",
    "RUOLO EMESSO DA",
    "Comune di Prova Polizia Urbana",
    "RUOLO N. 2026/000001",
    "1", "2025", "5242 Contrav.cod.strada l.689/81", "100,00",
    "VER. 111/V/2025 31/03/2025 NOT. IL 02/06/2025 TG. AB123CD ART. 7",
    "2", "2025", "5243 Contrav.cod.strada mag.", "13,00",
    "VER. 111/V/2025 31/03/2025 NOT. IL 02/06/2025 TG. AB123CD ART. 7",
    "Destinatario Cod. Fiscale 00000000000",
    "AJZ8Z",
    "1" + IUV,
]

_FONT = next((f for f in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                          "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf")
              if os.path.exists(f)), None)


def _pdf(righe=RIGHE) -> bytes:
    doc = fitz.open()
    pagina = doc.new_page()
    pagina.insert_font(fontname="F1", fontfile=_FONT)
    y = 30
    for riga in righe:
        pagina.insert_text((30, y), riga, fontsize=8, fontname="F1")
        y += 12
    contenuto = doc.tobytes()
    doc.close()
    return contenuto


def _run(coro):
    return asyncio.run(coro)


def test_legge_numero_ente_righe_verbale_e_iuv_e_i_conti_tornano():
    dati = cp.leggi_cartella(cp._testo(_pdf()))

    assert dati["numero_cartella"] == NUMERO and dati["ente_creditore"].startswith("Comune di Prova")
    assert (dati["importo_ente"], dati["diritti_notifica"], dati["totale"]) == ("113.00", "5.88", "118.88")
    assert dati["importi_quadrano"] is True
    assert dati["iuv"] == IUV and dati["codice_avviso"] == "1" + IUV
    assert [r["codice_tributo"] for r in dati["righe"]] == ["5242", "5243"]
    assert dati["verbali"] == [{"numero_verbale": "111/V/2025", "targa": "AB123CD"}]


def test_somme_che_non_tornano_lasciano_la_cartella_da_verificare():
    righe = [r.replace("13,00", "14,00") for r in RIGHE]

    dati = cp.leggi_cartella(cp._testo(_pdf(righe)))

    assert dati["importi_quadrano"] is False


def test_registra_apre_l_attesa_senza_scadenza_e_il_secondo_file_non_duplica():
    db = AsyncMongoMockClient()["cartelle"]

    primo = _run(cp.registra_cartella(db, "a.pdf", _pdf()))
    secondo = _run(cp.registra_cartella(db, "b.pdf", _pdf()))
    doc = _run(db[cp.COLL].find_one({"id": primo["id"]}))

    assert primo["success"] and primo["duplicate"] is False and secondo["duplicate"] is True
    assert _run(db[cp.COLL].count_documents({})) == 1
    assert doc["expectation_status"] == "ATTESO" and doc["expectation_type"] == cp.TIPO_ATTESA
    assert doc["source_fact_id"] == primo["id"]
    # La notifica non e' nel PDF: nessuna scadenza inventata.
    assert doc["data_notifica"] is None and doc["scadenza"] is None


def test_la_notifica_dice_il_termine_di_60_giorni_e_salta_il_fine_settimana():
    db = AsyncMongoMockClient()["cartelle"]
    cartella = _run(cp.registra_cartella(db, "a.pdf", _pdf()))

    esito = _run(cp.imposta_notifica(db, cartella["id"], "2026-07-25"))

    # 25/07 + 60 giorni = 23/09/2026 (mercoledi')
    assert esito["scadenza"] == "2026-09-23"
    # 28/07 + 60 giorni = sabato 26/09: passa a lunedi' 28/09.
    assert cp.scadenza_da_notifica("2026-07-28") == "2026-09-28"
    assert _run(cp.imposta_notifica(db, cartella["id"], "31/13/2026"))["success"] is False


def test_ricevuta_con_lo_stesso_iuv_e_importo_chiude_l_attesa():
    db = AsyncMongoMockClient()["cartelle"]
    cartella = _run(cp.registra_cartella(db, "a.pdf", _pdf()))

    stato = _run(cp.chiudi_da_ricevuta(db, {
        "id": "ric-1", "identificativo_bolletta": IUV, "operation_amount": 118.88,
        "data_pagamento": "2026-09-20",
    }))
    doc = _run(db[cp.COLL].find_one({"id": cartella["id"]}))

    assert stato == "SODDISFATTO" and doc["expectation_evidence_ids"] == ["ric-1"]


def test_ricevuta_con_lo_stesso_iuv_e_importo_diverso_resta_da_verificare():
    db = AsyncMongoMockClient()["cartelle"]
    cartella = _run(cp.registra_cartella(db, "a.pdf", _pdf()))

    stato = _run(cp.chiudi_da_ricevuta(db, {
        "id": "ric-2", "identificativo_bolletta": IUV, "operation_amount": 113.00,
    }))

    assert stato == "DA_VERIFICARE"
    assert _run(db[cp.COLL].find_one({"id": cartella["id"]}))["expectation_status"] == "DA_VERIFICARE"


def test_ricevuta_arrivata_prima_della_cartella_la_chiude_subito():
    db = AsyncMongoMockClient()["cartelle"]
    _run(db["ricevute_pagopa"].insert_one({
        "id": "ric-3", "identificativo_bolletta": IUV, "operation_amount": 118.88,
    }))

    cartella = _run(cp.registra_cartella(db, "a.pdf", _pdf()))

    assert cartella["ricevuta"] == "SODDISFATTO"


def test_verbale_si_aggancia_solo_se_unico_e_con_la_stessa_targa():
    db = AsyncMongoMockClient()["cartelle"]
    _run(db["verbali_noleggio"].insert_many([
        {"id": "v1", "numero_verbale": "111/V/2025", "targa": "AB123CD"},
        {"id": "v2", "numero_verbale": "222/V/2025", "targa": "AB123CD"},
    ]))

    cartella = _run(cp.registra_cartella(db, "a.pdf", _pdf()))
    doc = _run(db[cp.COLL].find_one({"id": cartella["id"]}))

    assert [v["id"] for v in doc["verbali_collegati"]] == ["v1"]

    # Due verbali con lo stesso numero e targa: ambiguo, nessun collegamento.
    _run(db["verbali_noleggio_completi"].insert_one(
        {"id": "v3", "numero_verbale": "111/V/2025", "targa": "AB123CD"}))
    _run(cp.collega_verbali(db, cartella["id"]))
    doc = _run(db[cp.COLL].find_one({"id": cartella["id"]}))
    assert doc["verbali_collegati"] == [] and len(doc["verbali_candidati"]["111/V/2025"]) == 2


def test_documenti_import_riconosce_la_cartella_di_pagamento():
    from app.routers.documenti import detect_document_type

    assert detect_document_type("cartella.pdf", _pdf()) == "cartella_pagamento"
