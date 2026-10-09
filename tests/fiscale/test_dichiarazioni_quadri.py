"""Lettura per posizione dei quadri delle dichiarazioni (MINI-02).

Le fixture sono le parole con coordinate delle pagine reali del minisito
(`golden_minisito/manifest_final.json`), ridotte alle righe attorno alle
etichette: gli importi sono quelli dichiarati dalla societa' e gia'
pubblici nel golden.
"""
import asyncio
from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import settings
from app.services import dichiarazioni_quadri as dq
from app.services.archivio_documenti_memoria import ClientArchivioMemoria

#: Il ripasso dell'archivio legge la societa' fiscale della configurazione.
SOCIETA = settings.FISCAL_COMPANY_ID


def _parole(righe):
    return [{"x0": x0, "y0": y0, "x1": x1, "y1": y1, "text": t} for x0, y0, x1, y1, t in righe]


# IVA 2022 (periodo 2021), pagina 9 (quadro VL) e 11 (quadro VX): VL33 = VX2 = 451.
IVA22_VL = [[549.53, 506.93, 559.65, 514.87, ",00"], [549.53, 542.95, 559.65, 550.89, ",00"], [447.56, 518.93, 457.68, 526.87, ",00"], [133.25, 519.37, 143.53, 527.12, "IVA"], [145.55, 519.37, 150.29, 527.12, "A"], [152.31, 519.79, 172.19, 526.99, "DEBITO"], [133.25, 543.19, 142.8, 550.39, "IVA"], [144.67, 543.19, 149.07, 550.39, "A"], [150.95, 542.76, 177.41, 550.52, "CREDITO"], [133.25, 530.07, 155.72, 539.14, "ovvero"], [108.29, 542.32, 125.86, 551.18, "VL33"], [108.29, 518.82, 125.86, 527.68, "VL32"], [108.29, 554.32, 125.86, 563.18, "VL34"], [531.0, 542.57, 549.0, 555.06, "451"]]
IVA22_VX = [[27.65, 135.7, 64.58, 145.67, "QUADRO"], [67.18, 135.7, 78.54, 145.67, "VX"], [108.37, 145.59, 123.09, 154.46, "VX1"], [132.02, 146.44, 142.3, 154.2, "IVA"], [144.32, 146.44, 152.23, 154.2, "da"], [154.26, 146.44, 176.65, 154.2, "versare"], [549.76, 148.48, 559.87, 156.41, ",00"], [108.37, 169.59, 123.09, 178.46, "VX2"], [132.02, 170.44, 142.3, 178.2, "IVA"], [144.32, 170.44, 148.28, 178.2, "a"], [150.3, 170.44, 170.8, 178.2, "credito"], [239.93, 170.3, 254.5, 178.24, "VX4,"], [256.52, 170.3, 269.07, 178.24, "VX5"], [276.53, 170.3, 291.12, 178.24, "VX6)"], [549.76, 172.48, 559.87, 180.41, ",00"], [471.0, 162.05, 473.32, 166.59, "1"], [530.0, 168.57, 548.0, 181.06, "451"]]
TESTO_VL = "QUADRO VL\nLIQUIDAZIONE DELL’IMPOSTA ANNUALE\nVL32\nVL33\nPeriodo d’imposta 2021\nMODELLO IVA 2022\nIdentificativo dichiarazione: 16475868926 - 0000001 del 27/4/2022\n451\n"
TESTO_VX = "QUADRO VX\nDETERMINAZIONE DELL’IVA DA VERSARE O A CREDITO\nVX1    IVA da versare\nVX2    IVA a credito\n,00\nPeriodo d’imposta 2021\nIdentificativo dichiarazione: 16475868926 - 0000001 del 27/4/2022\n451\n"

# Redditi SC 2022 (periodo 2021), pagina 6: RN1 = 24.178 (terza colonna), RN2 vuoto, RN17 = 935.
RED22_RN = [[135.65, 140.56, 157.4, 148.5, "Reddito"], [106.85, 140.6, 122.01, 149.46, "RN1"], [549.19, 160.56, 558.3, 168.5, ",00"], [549.19, 544.56, 558.3, 552.5, ",00"], [549.19, 556.34, 558.3, 564.28, ",00"], [135.65, 158.56, 155.74, 166.5, "Perdita"], [106.85, 158.3, 122.01, 167.16, "RN2"], [106.85, 542.8, 126.63, 551.66, "RN16"], [106.85, 554.8, 126.63, 563.66, "RN17"], [106.85, 566.6, 126.63, 575.46, "RN18"], [135.65, 554.56, 148.48, 562.5, "IRES"], [150.5, 554.56, 170.44, 562.5, "dovuta"], [410.26, 144.78, 413.15, 150.45, "2"], [469.94, 148.04, 479.05, 155.98, ",00"], [489.46, 144.78, 492.35, 150.45, "3"], [549.14, 148.04, 558.25, 155.98, ",00"], [433.98, 136.6, 456.53, 143.4, "Liberalità"], [331.06, 144.78, 333.95, 150.45, "1"], [390.74, 148.04, 399.84, 155.98, ",00"], [341.24, 136.6, 355.79, 143.4, "Legge"], [363.78, 136.6, 390.87, 143.4, "112/2016"], [512.0, 145.57, 548.0, 158.06, "24.178"], [530.0, 553.57, 548.0, 566.06, "935"]]
TESTO_RN = "IRES\nReddito\nRN1\nRN2\nRN17\nQUADRO RN\nDeterminazione dell’IRES\nPERIODO D’IMPOSTA 2021\nIdentificativo dichiarazione: 14391821287 - 0000001 del 30/11/2022\n24.178\n935\n935\n"

# IRAP 2022 (periodo 2021), pagina 5: IR26 = 1.796, IR27 vuoto.
IRAP22_IR = [[128.45, 656.56, 151.16, 664.51, "Importo"], [153.19, 656.56, 157.08, 664.51, "a"], [159.1, 656.56, 177.53, 664.51, "debito"], [128.45, 680.56, 151.16, 688.51, "Importo"], [159.1, 680.56, 179.18, 688.51, "credito"], [548.47, 664.05, 557.58, 672.0, ",00"], [548.47, 688.05, 557.58, 696.0, ",00"], [106.85, 656.23, 122.59, 665.11, "IR26"], [106.85, 680.23, 122.59, 689.11, "IR27"], [518.0, 660.57, 548.0, 673.06, "1.796"]]
TESTO_IR = "QUADRO IR\nRipartizione della base imponibile\nPERIODO D’IMPOSTA 2021\nIR26\nIR27\nIdentificativo dichiarazione: 14413363590 - 0000001 del 30/11/2022\n1.796\n"

# IVA 2024 (periodo 2023), scansione letta con RapidOCR: il segnaposto perde la
# virgola («00»), il valore porta i decimali attaccati («1.462.00», «1.462,00»).
IVA24_OCR_VL = [[107.5, 542.0, 128.5, 551.0, "VL32"], [131.0, 541.0, 173.5, 552.0, "IVAADEBITO"], [447.5, 541.0, 460.0, 551.5, ",00"], [132.5, 555.0, 157.5, 563.5, "ovvero"], [107.0, 565.0, 128.5, 575.5, "VL33"], [131.0, 566.0, 178.5, 574.5, "IVAACREDITO"], [517.0, 564.5, 562.5, 578.5, "1.462.00"]]
IVA24_OCR_VX = [[26.5, 134.0, 80.5, 145.5, "QUADROVX"], [107.0, 145.0, 124.0, 154.5, "VX1"], [129.0, 144.5, 179.0, 155.5, "IVA da versare"], [551.5, 149.0, 560.5, 155.5, "00"], [108.0, 170.0, 125.0, 177.0, "VX2"], [129.5, 169.5, 291.5, 179.0, "IVA a credito (da ripartire tra i righi VX4, VX5 e VX6)"], [516.0, 168.5, 562.5, 181.5, "1.462,00"]]
TESTO_OCR_VL = "Identificativo dichiarazione: 16232014575 - 0000002 del 24/4/2024\nMODELLOIVA2024\nPeriodo d’imposta 2023\nQUADROVL\nVL32\nVL33\n"
TESTO_OCR_VX = "Identificativo dichiarazione: 16232014575 - 0000002 del 24/4/2024\nMODELLOIVA2024\nQUADROVX\nVX1\nVX2\n"

# Esito ISA 2023 (CG37U, punteggio 8,20), pagina 1 e 2.
ISA_P1 = [[252.68, 310.86, 287.69, 324.6, "Modello"], [369.81, 310.86, 403.15, 324.6, "CG37U"], [252.68, 323.13, 283.8, 336.87, "Codice"], [286.58, 323.13, 318.25, 336.87, "Fiscale"], [369.81, 323.13, 430.97, 336.87, "04523831214"], [252.68, 347.67, 287.69, 361.41, "Modello"], [290.47, 347.67, 351.04, 361.41, "Dichiarazione"], [369.81, 347.67, 409.81, 361.41, "REDDITI"], [412.59, 347.67, 448.72, 361.41, "SC2023"], [252.68, 359.94, 297.14, 373.68, "Protocollo"], [369.81, 359.94, 503.25, 373.68, "231129161737127710000001"]]
ISA_P2 = [[510.28, 79.37, 546.3, 90.36, "Punteggio"], [379.59, 98.05, 388.76, 113.2, "8,"], [401.6, 98.05, 448.05, 113.2, "permette"], [416.67, 109.05, 428.9, 124.2, "11"], [537.55, 97.98, 560.9, 114.5, "8,20"]]
TESTO_ISA_P1 = "DATI RICALCOLATI\nModello\nCG37U\nCodice Fiscale\n04523831214\nModello Dichiarazione\nREDDITI SC2023\nProtocollo\n231129161737127710000001\nMotore \"Il tuo Isa\" 2023\n"
TESTO_ISA_P2 = "Esito del ricalcolo\nINDICE\nSINTETICO DI\nAFFIDABILITA'\nPunteggio\n8,20\n"


def _pagina(numero, testo, righe):
    return {"page_number": numero, "text": testo, "layout_words": _parole(righe)}


def _run(coro):
    return asyncio.run(coro)


# ── funzioni pure ─────────────────────────────────────────────────────────────

def test_iva_annuale_vl33_e_vx2_letti_per_posizione_e_caselle_vuote_restano_none():
    esito = dq.estrai_quadri_pagine([_pagina(9, TESTO_VL, IVA22_VL), _pagina(11, TESTO_VX, IVA22_VX)])
    assert esito["tipo_letto"] == "DICHIARAZIONE_IVA"
    assert esito["identificativo"] == "16475868926 - 0000001"
    assert esito["data_presentazione"] == "27/4/2022"
    assert esito["anno_imposta"] == 2021
    campi = esito["campi"]
    assert campi["vl33_iva_credito"] == {"valore": "451.00", "motivo": None, "pagina": 9, "rigo": "VL33"}
    assert campi["vx2_a_credito"]["valore"] == "451.00" and campi["vx2_a_credito"]["pagina"] == 11
    # VL32 e VX1 sono in bianco nel modulo: nullo con motivo, mai 0.
    assert campi["vl32_iva_debito"] == {"valore": None, "motivo": "casella_vuota", "pagina": 9, "rigo": "VL32"}
    assert campi["vx1_da_versare"]["valore"] is None and campi["vx1_da_versare"]["motivo"] == "casella_vuota"
    assert esito["campi_da_verificare"] == []


def test_redditi_sc_rn1_prende_l_ultima_colonna_e_rn17_ignora_la_riga_di_rn16():
    esito = dq.estrai_quadri_pagine([_pagina(6, TESTO_RN, RED22_RN)], "REDDITI_SC")
    assert esito["tipo_letto"] == "REDDITI_SC"
    assert esito["anno_imposta"] == 2021 and esito["identificativo"] == "14391821287 - 0000001"
    campi = esito["campi"]
    assert campi["rn1_reddito"]["valore"] == "24178.00"
    assert campi["rn2_perdita"]["valore"] is None and campi["rn2_perdita"]["motivo"] == "casella_vuota"
    assert campi["rn17_ires_dovuta_differenza"]["valore"] == "935.00"


def test_irap_ir26_debito_e_ir27_credito():
    esito = dq.estrai_quadri_pagine([_pagina(5, TESTO_IR, IRAP22_IR)])
    assert esito["tipo_letto"] == "DICHIARAZIONE_IRAP"
    assert esito["campi"]["ir26_importo_a_debito"]["valore"] == "1796.00"
    assert esito["campi"]["ir27_importo_a_credito"] == {"valore": None, "motivo": "casella_vuota", "pagina": 5, "rigo": "IR27"}


def test_iva_scansionata_letta_dalle_parole_ocr():
    esito = dq.estrai_quadri_pagine([_pagina(8, TESTO_OCR_VL, IVA24_OCR_VL), _pagina(10, TESTO_OCR_VX, IVA24_OCR_VX)])
    assert esito["tipo_letto"] == "DICHIARAZIONE_IVA"
    assert esito["anno_imposta"] == 2023
    campi = esito["campi"]
    assert campi["vl33_iva_credito"]["valore"] == "1462.00"
    assert campi["vx2_a_credito"]["valore"] == "1462.00"
    assert campi["vl32_iva_debito"]["motivo"] == "casella_vuota"
    assert campi["vx1_da_versare"]["motivo"] == "casella_vuota"


def test_esito_isa_punteggio_codice_protocollo_e_anno_dal_modello():
    esito = dq.estrai_quadri_pagine([_pagina(1, TESTO_ISA_P1, ISA_P1), _pagina(2, TESTO_ISA_P2, ISA_P2)], "REDDITI_SC")
    assert esito["tipo_letto"] == "ISA_ESITO"
    campi = esito["campi"]
    assert campi["isa_punteggio"]["valore"] == "8.20"
    assert campi["codice_isa"]["valore"] == "CG37U"
    assert campi["protocollo"]["valore"] == "231129161737127710000001"
    assert esito["modello_dichiarazione"] == "REDDITI SC2023"
    assert esito["anno_imposta"] == 2022 and esito["anno_imposta_fonte"] == "modello_redditi_anno_meno_uno"


def test_rigo_assente_e_pagina_senza_coordinate_hanno_un_motivo():
    solo_vl = dq.estrai_quadri_pagine([_pagina(9, TESTO_VL, IVA22_VL)])
    assert solo_vl["campi"]["vx1_da_versare"] == {"valore": None, "motivo": "rigo_non_trovato", "pagina": None, "rigo": "VX1"}
    senza = dq.estrai_quadri_pagine([_pagina(9, TESTO_VL, []), _pagina(11, TESTO_VX, [])])
    assert senza["campi"]["vl33_iva_credito"]["motivo"] == "pagina_senza_coordinate"
    assert senza["campi"]["vl33_iva_credito"]["valore"] is None
    assert dq.estrai_quadri_pagine([_pagina(1, "informativa privacy", [])])["motivo"] == "tipo_non_riconosciuto"


def test_due_valori_diversi_per_lo_stesso_rigo_vanno_in_campi_da_verificare():
    altra = [list(r) for r in RED22_RN]
    for r in altra:
        if r[4] == "935":
            r[4] = "1.935"
            r[0] = 524.0
    esito = dq.estrai_quadri_pagine([_pagina(6, TESTO_RN, RED22_RN), _pagina(16, TESTO_RN, altra)])
    campo = esito["campi"]["rn17_ires_dovuta_differenza"]
    assert campo["valore"] is None and campo["motivo"] == "ambiguo"
    assert campo["candidati"] == ["1935.00", "935.00"]
    assert esito["campi_da_verificare"] == ["rn17_ires_dovuta_differenza"]
    # lo stesso valore su due pagine invece non e' un'ambiguita'
    doppia = dq.estrai_quadri_pagine([_pagina(6, TESTO_RN, RED22_RN), _pagina(16, TESTO_RN, RED22_RN)])
    assert doppia["campi"]["rn17_ires_dovuta_differenza"]["valore"] == "935.00"


def test_valore_rigo_ambiguo_sulla_stessa_pagina():
    parole = _parole(IRAP22_IR) + [{"x0": 500.0, "y0": 660.6, "x1": 547.5, "y1": 673.0, "text": "2.000"}]
    esito = dq.valore_rigo(parole, "IR26")
    assert esito["valore"] is None and esito["motivo"] == "ambiguo"
    assert esito["candidati"] == ["1796.00", "2000.00"]
    assert dq.valore_rigo(_parole(IRAP22_IR), "IR26")["valore"] == Decimal("1796.00")


def test_pagina_con_quadro_decide_quali_coordinate_conservare():
    assert dq.pagina_con_quadro(TESTO_VL) and dq.pagina_con_quadro(TESTO_RN) and dq.pagina_con_quadro(TESTO_ISA_P2)
    assert not dq.pagina_con_quadro("Con questa informativa l’Agenzia delle Entrate spiega come tratta i dati")


# ── archivio ──────────────────────────────────────────────────────────────────

def _db_con_documento(con_coordinate=True):
    db = ClientArchivioMemoria()["quadri_test"]
    _run(db.fiscal_documents.insert_one({
        "id": "fdoc_iva22", "company_id": SOCIETA, "filename": "IVA_T220427164758689261_04523831214.pdf",
        "document_type": "DICHIARAZIONE_IVA", "current_version_id": "fver_iva22",
    }))
    for numero, testo, righe in ((9, TESTO_VL, IVA22_VL), (11, TESTO_VX, IVA22_VX)):
        _run(db.fiscal_pages.insert_one({
            "id": f"fpage_{numero}", "company_id": SOCIETA, "document_id": "fdoc_iva22",
            "version_id": "fver_iva22", "page_number": numero, "text": testo,
            "layout_words": _parole(righe) if con_coordinate else [],
        }))
    return db


def test_estrai_quadri_documento_scrive_prove_idempotenti_e_riepilogo():
    db = _db_con_documento()
    primo = _run(dq.estrai_quadri_documento(db, "fdoc_iva22", company_id=SOCIETA))
    assert primo["esito"] == "letto" and primo["prove"] == 2
    secondo = _run(dq.estrai_quadri_documento(db, "fdoc_iva22", company_id=SOCIETA))
    assert secondo["prove"] == 2
    prove = _run(db.fiscal_evidence.find({"company_id": SOCIETA}, {"_id": 0}).to_list(50))
    assert len(prove) == 2, "rilanciare non duplica le prove"
    per_campo = {p["field_name"]: p for p in prove}
    assert per_campo["vl33_iva_credito"]["normalized_value"] == "451.00"
    assert per_campo["vl33_iva_credito"]["page_number"] == 9
    assert per_campo["vx2_a_credito"]["parser_version"] == dq.PARSER_VERSION
    doc = _run(db.fiscal_documents.find_one({"id": "fdoc_iva22"}, {"_id": 0}))
    assert doc["quadri"]["campi"]["vl32_iva_debito"]["motivo"] == "casella_vuota"
    assert doc["quadri"]["identificativo"] == "16475868926 - 0000001"


def test_estrai_quadri_documento_dry_run_non_scrive():
    db = _db_con_documento()
    esito = _run(dq.estrai_quadri_documento(db, "fdoc_iva22", company_id=SOCIETA, dry_run=True))
    assert esito["quadri"]["campi"]["vl33_iva_credito"]["valore"] == "451.00"
    assert _run(db.fiscal_evidence.count_documents({})) == 0
    assert "quadri" not in _run(db.fiscal_documents.find_one({"id": "fdoc_iva22"}, {"_id": 0}))


def test_pagine_senza_coordinate_e_senza_originale_restano_dichiarate():
    db = _db_con_documento(con_coordinate=False)
    esito = _run(dq.estrai_quadri_documento(db, "fdoc_iva22", company_id=SOCIETA, dry_run=True))
    assert esito["quadri"]["coordinate_rilette"] is False
    assert esito["quadri"]["campi"]["vl33_iva_credito"]["motivo"] == "pagina_senza_coordinate"


def test_endpoint_archivio_gira_in_sottofondo_con_stato(monkeypatch):
    from app.database import Database
    from app.routers import dichiarazioni_quadri as router_quadri
    from app.utils.dependencies import get_current_admin_user, get_current_user

    db = _db_con_documento()
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))
    monkeypatch.setattr(dq, "_job_task", None)
    app = FastAPI()
    app.include_router(router_quadri.router, prefix="/api/fiscale")
    app.dependency_overrides[get_current_user] = lambda: {"sub": "u", "role": "user"}
    app.dependency_overrides[get_current_admin_user] = lambda: {"sub": "a", "role": "admin", "user_id": "a"}
    with TestClient(app) as client:
        avvio = client.post("/api/fiscale/dichiarazioni/estrai-quadri", params={"dry_run": "false"})
        assert avvio.status_code == 200, avvio.text
        assert avvio.json()["avviato"] is True and avvio.json()["dry_run"] is False
        for _ in range(50):
            stato = client.get("/api/fiscale/dichiarazioni/estrai-quadri/stato").json()
            if stato.get("stato") == "completato":
                break
        assert stato["stato"] == "completato", stato
        assert stato["risultato"]["documenti"] == 1 and stato["risultato"]["letti"] == 1
        singolo = client.post("/api/fiscale/dichiarazioni/fdoc_iva22/estrai-quadri")
        assert singolo.status_code == 200 and singolo.json()["quadri"]["campi"]["vx2_a_credito"]["valore"] == "451.00"
    prove = _run(db.fiscal_evidence.find({}, {"_id": 0}).to_list(50))
    assert {p["field_name"] for p in prove} == {"vl33_iva_credito", "vx2_a_credito"}
