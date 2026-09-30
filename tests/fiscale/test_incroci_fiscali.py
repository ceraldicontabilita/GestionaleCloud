"""MINI-04: un motore solo per gli incroci fiscali del minisito.

L'archivio si ricostruisce dal golden `manifest_final.json` (LIPE canoniche
in `lipe_periodi`, quietanze F24 in `quietanze_f24`, dichiarazioni IRAP e IVA
in `fiscal_documents.quadri`, comunicazioni 54-bis strutturate) e il motore
deve riprodurre i 63 confronti mensili e i 16 alert del pacchetto del
titolare: 11 IVA mensili, 2 IRAP, 3 comunicazioni 54-bis, nessuno sull'IVA
annuale (VX1 = 0 ogni anno).
"""
import asyncio
import inspect
import json
from datetime import date
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services import f24_controllo_incrociato as ctrl
from app.services import incroci_fiscali as mod
from app.services import lipe_deposito
from app.services.alert_engine import ALERT_CATALOG
from app.services.archivio_documenti_memoria import ClientArchivioMemoria

GOLDEN = Path(__file__).parent / "golden_minisito" / "manifest_final.json"
OGGI = date(2026, 9, 16)


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(scope="module")
def golden():
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


# ── archivio dal golden ───────────────────────────────────────────────────────

def _lipe_righe(raw_lipe, lipe_stato):
    righe = []
    for doc in raw_lipe:
        stato = (lipe_stato.get(doc["filename"]) or {}).get("stato") or "canonica"
        for p in doc["periodi"]:
            debito = p.get("iva_da_versare") or 0.0
            credito = p.get("iva_a_credito") or 0.0
            righe.append({
                "id": f"lipe-{p['anno']}-{p['mese']:02d}-{doc['filename']}",
                "periodo": f"{p['anno']}-{p['mese']:02d}", "anno": p["anno"],
                "iva_esigibile": p["vp4_iva_esigibile"], "iva_detratta": p["vp5_iva_detratta"],
                "iva_da_versare_o_credito": debito if debito else credito,
                "iva_da_versare_o_credito_segno": "debito" if debito else "credito",
                "quadratura_ok": True, "stato": stato, "nome_file": doc["filename"],
                "protocollo": lipe_deposito.protocollo_da_nome(doc["filename"]),
            })
    return righe


def _quietanza(q, n):
    sezioni = {"sezione_erario": [], "sezione_regioni": [], "sezione_inps": [], "sezione_tributi_locali": []}
    for t in q["tributi"]:
        riga = {"periodo_riferimento": t["periodo"], "importo_debito": t["debito"], "importo_credito": t["credito"]}
        if t["sezione"] == "INPS":
            riga["causale"] = t["causale"].split(" ")[0]
            sezioni["sezione_inps"].append(riga)
        elif t["sezione"] == "REGIONI":
            sezioni["sezione_regioni"].append({**riga, "codice_tributo": t["codice_tributo"]})
        else:
            sezioni["sezione_erario"].append({**riga, "codice_tributo": t["codice_tributo"]})
    return {
        "id": f"q-{n}", "filename": q["filename"], "protocollo_telematico": q.get("protocollo") or "",
        "data_pagamento": q.get("data_versamento_iso") or q["filename"].split("_")[3],
        "saldo": q["totale_debito"] - q["totale_credito"],
        "totali": {"saldo_netto": q["totale_debito"] - q["totale_credito"]},
        "validazione": {"saldo_quadrato": True}, **sezioni,
    }


def _dichiarazione(d, n, tipo, rigo, chiave):
    return {
        "id": f"dich-{n}", "filename": d["filename"], "document_type": tipo, "company_id": "04523831214",
        "quadri": {"tipo_letto": tipo, "anno_imposta": d["anno_imposta"], "identificativo": d["identificativo"],
                   "campi": {rigo: {"valore": f"{d[chiave]:.2f}", "motivo": None, "rigo": rigo.split('_')[0].upper()}}},
    }


def _comunicazione(c, n):
    return {
        "id": f"cv6-{n}", "filename": c["filename"], "document_type": "COMUNICAZIONE_IRREGOLARITA",
        "comunicazione_54bis": {
            "numero_comunicazione": c["numero_comunicazione"], "codice_atto": c["codice_atto"],
            "anno_modello": c["anno_modello"], "anno_imposta": c.get("anno_imposta"),
            "tipo_modello": c["tipo_modello"], "importo_totale": c["importo_totale"],
            "data_elaborazione": c["data_elaborazione"], "periodi": c["periodi"],
        },
    }


def _archivio_dal_golden(golden):
    raw = golden["raw"]
    db = ClientArchivioMemoria()["incroci_golden"]
    _run(db.lipe_periodi.insert_many(_lipe_righe(raw["lipe"], golden["lipe_stato"])))
    _run(db.quietanze_f24.insert_many([_quietanza(q, n) for n, q in enumerate(raw["f24"])]))
    _run(db.fiscal_documents.insert_many(
        [_dichiarazione(d, n, "DICHIARAZIONE_IVA", "vx1_da_versare", "vx1_da_versare")
         for n, d in enumerate(raw["iva"])]
        + [_dichiarazione(d, 100 + n, "DICHIARAZIONE_IRAP", "ir26_importo_a_debito", "irap_importo_a_debito")
           for n, d in enumerate(g for g in raw["generic"] if g["type"] == "IRAP_DICH")]
        + [_comunicazione(c, n) for n, c in enumerate(raw["irregolarita"])]
    ))
    return db


@pytest.fixture(scope="module")
def quadro(golden):
    db = _archivio_dal_golden(golden)
    return db, _run(mod.incroci(db, oggi=OGGI))


# ── il golden si riproduce ───────────────────────────────────────────────────

def test_i_63_confronti_mensili_del_golden(golden, quadro):
    _db, esito = quadro
    righe = esito["confronti_iva_mensile"]
    assert len(righe) == 63
    assert esito["conteggi_mensili"] == {"OK": 45, "MANCANTE": 11, "ECCEDENTE": 7}
    attesi = {(c["anno"], c["mese"]): c for c in golden["confronti_iva_mensile"]}
    for r in righe:
        atteso = attesi[(r["anno"], r["mese"])]
        assert r["dovuto_da_lipe"] == pytest.approx(atteso["dovuto_da_lipe"]), (r["anno"], r["mese"])
        assert r["versato_f24"] == pytest.approx(atteso["versato_f24"]), (r["anno"], r["mese"])
        assert r["lipe_source"] == atteso["lipe_source"]
        assert sorted(r["f24_sources"]) == sorted(atteso["f24_sources"])
    # ECCEDENTE = versato sopra il dovuto di piu' di 1 EUR (2022-05: 0,01 e 2024-09: 0,03 restano OK)
    assert [(r["anno"], r["mese"]) for r in righe if r["stato"] == "ECCEDENTE"] == [
        (2021, 2), (2022, 7), (2022, 8), (2022, 9), (2022, 10), (2023, 10), (2023, 12),
    ]
    assert next(r for r in righe if (r["anno"], r["mese"]) == (2024, 9))["differenza"] == 0.03


def test_gli_11_alert_iva_mensili_con_gli_importi_del_golden(golden, quadro):
    _db, esito = quadro
    attesi = {(a["anno"], a["mese"]): a for a in golden["alerts"] if a["tipo"] == "PAGAMENTO_MANCANTE_O_PARZIALE"}
    previsti = [a for a in esito["alert_previsti"] if a["codice"] == mod.ALERT_IVA_MENSILE]
    assert len(previsti) == len(attesi) == 11
    for a in previsti:
        atteso = attesi[(a["extra"]["anno"], a["extra"]["mese"])]
        assert a["extra"]["importo_dovuto"] == pytest.approx(atteso["importo_dovuto"])
        assert a["extra"]["importo_versato"] == 0.0 and a["extra"]["importo_mancante"] == pytest.approx(atteso["importo_mancante"])
        assert a["entita_collection"] == "lipe_periodi"
        assert atteso["lipe_source"] in a["dettaglio"]


def test_irap_ir26_contro_3800_e_iva_annuale_vx1_contro_6099(quadro):
    _db, esito = quadro
    irap = {r["anno_imposta"]: r for r in esito["irap_riscontro"]}
    assert set(irap) == {2020, 2021, 2022, 2024}
    assert irap[2022]["importo_dichiarato"] == 12061.0 and irap[2022]["importo_versato"] == 6000.0
    assert irap[2022]["mancante"] == 6061.0 and irap[2022]["stato"] == "PARZIALE"
    assert irap[2024]["importo_dichiarato"] == 5164.0 and irap[2024]["importo_versato"] == 0.0
    assert irap[2024]["stato"] == "MANCANTE" and irap[2024]["mancante"] == 5164.0
    assert irap[2021]["stato"] == "ECCEDENTE"  # 1.803,18 versati su 1.796,00 dichiarati
    assert irap[2020]["stato"] == "OK"
    alert_irap = [a for a in esito["alert_previsti"] if a["codice"] == mod.ALERT_IRAP]
    assert sorted(a["extra"]["anno"] for a in alert_irap) == [2022, 2024]
    assert {a["extra"]["anno"]: (a["extra"]["importo_dovuto"], a["extra"]["importo_versato"], a["extra"]["importo_mancante"])
            for a in alert_irap} == {2022: (12061.0, 6000.0, 6061.0), 2024: (5164.0, 0.0, 5164.0)}
    # VX1 = 0 ogni anno: i 6099 sono solo crediti compensati, nessun alert
    assert [r["stato"] for r in esito["iva_annuale_riscontro"]] == ["OK"] * 5
    assert all(r["importo_dichiarato"] == 0.0 for r in esito["iva_annuale_riscontro"])
    assert not [a for a in esito["alert_previsti"] if a["codice"] == mod.ALERT_IVA_ANNUALE]


def test_le_3_comunicazioni_54bis_non_pagate(golden, quadro):
    _db, esito = quadro
    per_numero = {c["numero_comunicazione"]: c for c in esito["comunicazioni_54bis"]}
    attesi = {a["mese_nome"].split("n. ")[1]: a for a in golden["alerts"] if a["tipo"] == "COMUNICAZIONE_54BIS_NON_PAGATA"}
    assert set(per_numero) == set(attesi)
    for numero, c in per_numero.items():
        assert c["stato"] == "NON_PAGATA" and c["pagata"] is False
        assert c["importo_totale"] == pytest.approx(attesi[numero]["importo_dovuto"])
        assert c["scadenza"] is None and "notifica" in c["scadenza_motivo"]
    assert per_numero["0154594223401"]["codici_cercati"] == ["9033", "9034", "9035"]
    assert per_numero["0025645524601"]["codici_cercati"] == ["9571", "9572", "9573"]
    alert = [a for a in esito["alert_previsti"] if a["codice"] == mod.ALERT_54BIS]
    assert len(alert) == 3 and all(a["entita_collection"] == "fiscal_documents" for a in alert)


def test_in_tutto_16_alert_e_nessuno_dagli_indizi(quadro):
    _db, esito = quadro
    assert len(esito["alert_previsti"]) == 16
    assert set(a["codice"] for a in esito["alert_previsti"]) <= set(mod.CODICI_ALERT)
    assert all(codice in ALERT_CATALOG for codice in mod.CODICI_ALERT)
    assert esito["file_rotti"] == [] and esito["guardia"]["f24_esclusi"] == []
    # le due LIPE 2022 ritrasmesse: la guardia tiene fuori quelle sostituite
    assert sorted({g["nome_file"] for g in esito["guardia"]["lipe_escluse"]}) == [
        "LIPE_2022_IItrim_312334116.pdf", "LIPE_2022_Itrim_305938061.pdf",
    ]
    assert len(esito["guardia"]["lipe_escluse"]) == 6  # tre mesi per trimestre ritrasmesso
    assert {g["motivo"][:10] for g in esito["guardia"]["lipe_escluse"]} == {"sostituita"}
    assert esito["fonti"]["versamenti_da_quietanza"] == 212 and esito["fonti"]["versamenti_da_modello"] == 0


def test_gli_alert_si_scrivono_una_volta_sola(golden):
    db = _archivio_dal_golden(golden)
    primo = _run(mod.esegui_incroci(db))
    assert primo["alert"] == {"creati": 16, "chiusi": 0, "invariati": 0}
    secondo = _run(mod.esegui_incroci(db))
    assert secondo["alert"] == {"creati": 0, "chiusi": 0, "invariati": 16}
    aperti = _run(db.alerts.find({"stato": "aperto"}, {"_id": 0}).to_list(None))
    assert len(aperti) == 16
    assert {a["modulo"] for a in aperti} == {"fiscale"}
    giugno_2024 = next(a for a in aperti if a["codice"] == mod.ALERT_IVA_MENSILE and a["extra"]["anno"] == 2024)
    assert giugno_2024["extra"]["mese"] == 6 and giugno_2024["extra"]["importo_mancante"] == 1463.15


def test_un_alert_si_chiude_col_motivo_quando_arriva_il_versamento(golden):
    db = _archivio_dal_golden(golden)
    _run(mod.esegui_incroci(db))
    # Arriva la quietanza del 6006 di giugno 2024 per l'importo della LIPE.
    _run(db.quietanze_f24.insert_one({
        "id": "q-nuova", "filename": "F24_QUIETANZA_2026_2026-09-10_26091000000000001_000001.pdf",
        "protocollo_telematico": "26091000000000001", "data_pagamento": "2026-09-10", "saldo": 1463.15,
        "validazione": {"saldo_quadrato": True},
        "sezione_erario": [{"codice_tributo": "6006", "periodo_riferimento": "2024", "importo_debito": 1463.15}],
    }))
    esito = _run(mod.esegui_incroci(db))
    assert esito["alert"] == {"creati": 0, "chiusi": 1, "invariati": 15}
    chiuso = _run(db.alerts.find_one({"codice": mod.ALERT_IVA_MENSILE, "stato": "risolto"}, {"_id": 0}))
    assert chiuso["extra"]["anno"] == 2024 and chiuso["extra"]["mese"] == 6
    assert chiuso["resolved_by"] == "incroci_fiscali" and "condizione non vale piu'" in chiuso["motivo_chiusura"]


def test_un_alert_ignorato_dal_titolare_non_rinasce(golden):
    db = _archivio_dal_golden(golden)
    _run(mod.esegui_incroci(db))
    _run(db.alerts.update_one({"codice": mod.ALERT_IRAP, "extra.anno": 2024}, {"$set": {"stato": "ignorato"}}))
    esito = _run(mod.esegui_incroci(db))
    assert esito["alert"]["creati"] == 0
    assert _run(db.alerts.count_documents({"codice": mod.ALERT_IRAP})) == 2


# ── casi sintetici: guardia, indizi, dedup ───────────────────────────────────

def _lipe(periodo, importo, segno="debito", **extra):
    return {"periodo": periodo, "iva_da_versare_o_credito": importo, "iva_da_versare_o_credito_segno": segno,
            "quadratura_ok": True, "nome_file": f"LIPE_{periodo[:4]}_1.pdf", "stato": "canonica", **extra}


def _q(id_, protocollo, data, righe, saldo=None, **extra):
    erario = [{"codice_tributo": c, "periodo_riferimento": p, "importo_debito": d, "importo_credito": cr}
              for c, p, d, cr in righe]
    return {"id": id_, "filename": f"{id_}.pdf", "protocollo_telematico": protocollo, "data_pagamento": data,
            "saldo": saldo if saldo is not None else sum(r[2] for r in righe) - sum(r[3] for r in righe),
            "validazione": {"saldo_quadrato": True}, "sezione_erario": erario, **extra}


def _db():
    return ClientArchivioMemoria()["incroci_sintetici"]


def test_la_guardia_esclude_lipe_non_quadrate_sostituite_e_f24_non_quadrati():
    db = _db()
    _run(db.lipe_periodi.insert_many([
        _lipe("2025-01", 534.06),
        _lipe("2025-02", 100.0, quadratura_ok=False),
        _lipe("2025-03", 200.0, stato="sostituita"),
    ]))
    _run(db.quietanze_f24.insert_many([
        _q("q-ok", "P1", "2025-02-17", [("6001", "2025", 534.06, 0.0)]),
        _q("q-rotta", "P2", "2025-03-17", [("6002", "2025", 100.0, 0.0)], validazione={"saldo_quadrato": False}),
    ]))
    esito = _run(mod.incroci(db))
    assert [(r["periodo"], r["stato"]) for r in esito["confronti_iva_mensile"]] == [("2025-01", "OK")]
    assert [(g["periodo"], g["motivo"][:12]) for g in esito["guardia"]["lipe_escluse"]] == [
        ("2025-02", "l'aritmetica"), ("2025-03", "sostituita d"),
    ]
    assert [g["id"] for g in esito["guardia"]["f24_esclusi"]] == ["q-rotta"]
    assert esito["alert_previsti"] == []


def test_una_quietanza_si_conta_una_volta_per_protocollo_e_saldo_e_il_modello_coperto_non_si_somma():
    db = _db()
    _run(db.lipe_periodi.insert_one(_lipe("2025-06", 5771.48)))
    _run(db.quietanze_f24.insert_many([
        _q("q-a", "P6", "2025-07-16", [("6006", "2025", 5000.0, 0.0)]),
        _q("q-a-copia", "P6", "2025-07-16", [("6006", "2025", 5000.0, 0.0)]),
        _q("q-ravv", "P7", "2025-09-01", [("6006", "2025", 771.48, 0.0), ("8904", "2025", 9.64, 0.0)]),
    ]))
    # Il modello del commercialista della stessa delega (stesso protocollo) non si somma.
    _run(db.f24_unificato.insert_one({
        "id": "m-6006", "status": "da_pagare", "file_name": "F24 IVA giugno.pdf", "protocollo": "P6",
        "dati_generali": {"data_versamento": "2025-07-16"}, "totali": {"saldo_netto": 5000.0},
        "sezione_erario": [{"codice_tributo": "6006", "anno": "2025", "importo_debito": 5000.0}],
    }))
    esito = _run(mod.incroci(db))
    (riga,) = esito["confronti_iva_mensile"]
    assert riga["versato_f24"] == 5771.48 and riga["stato"] == "OK" and riga["ravvedimento_rilevato"] is True
    assert sorted(v["id"] for v in riga["f24_versamenti"]) == ["q-a", "q-ravv"]
    motivi = {g["id"]: g["motivo"] for g in esito["guardia"]["f24_esclusi"]}
    assert motivi["q-a-copia"].startswith("stesso protocollo") and motivi["m-6006"].startswith("coperto dalla quietanza")


def test_un_modello_scoperto_conta_ma_uno_stornato_o_in_quarantena_no():
    db = _db()
    _run(db.lipe_periodi.insert_one(_lipe("2025-01", 534.06)))
    _run(db.f24_unificato.insert_many([
        {"id": "m-1", "status": "da_pagare", "file_name": "F24 gennaio.pdf",
         "dati_generali": {"data_versamento": "2025-02-17"}, "totali": {"saldo_netto": 534.06},
         "sezione_erario": [{"codice_tributo": "6001", "anno": "2025", "importo_debito": 534.06}]},
        {"id": "m-2", "status": "eliminato", "file_name": "F24 gennaio (2).pdf",
         "sezione_erario": [{"codice_tributo": "6001", "anno": "2025", "importo_debito": 534.06}]},
        {"id": "m-3", "status": "stornato", "file_name": "F24 gennaio storno.pdf",
         "sezione_erario": [{"codice_tributo": "6001", "anno": "2025", "importo_debito": 534.06}]},
        {"id": "m-4", "status": "da_pagare", "file_name": "F24 gennaio 2024.pdf",
         "sezione_erario": [{"codice_tributo": "6001", "anno": "2024", "importo_debito": 999.0}]},
    ]))
    (riga,) = _run(mod.incroci(db))["confronti_iva_mensile"]
    assert riga["versato_f24"] == 534.06 and riga["stato"] == "OK"
    assert riga["f24_sources"] == ["F24 gennaio.pdf"]


def test_gli_indizi_a_3_euro_restano_indizi_e_non_alert():
    db = _db()
    _run(db.lipe_periodi.insert_many([_lipe("2024-10", 1211.90), _lipe("2024-11", 500.0)]))
    _run(db.quietanze_f24.insert_many([
        # stesso codice 6010 con importo a 2,50 EUR ma anno 2023: periodo imputato male?
        _q("q-2023", "P1", "2024-11-18", [("6010", "2023", 1209.40, 0.0)]),
        # un 6099 a credito quasi identico: possibile compensazione
        _q("q-6099", "P2", "2025-03-17", [("6099", "2024", 0.0, 1213.00)]),
        # oltre i 3 EUR: nessun indizio
        _q("q-lontana", "P3", "2024-12-16", [("6011", "2023", 504.0, 0.0)]),
    ]))
    esito = _run(mod.incroci(db))
    ottobre, novembre = esito["confronti_iva_mensile"]
    assert ottobre["stato"] == "MANCANTE" and ottobre["versato_f24"] == 0.0
    assert sorted(h["tipo"] for h in ottobre["hints"]) == [
        ctrl.INDIZIO_COMPENSAZIONE_6099, ctrl.INDIZIO_ERRORE_PERIODO,
    ]
    assert novembre["stato"] == "MANCANTE" and novembre["hints"] == []
    assert esito["soglia_indizi_euro"] == 3.0 and ctrl.TOLLERANZA_INDIZIO_CENTS == 300
    codici = [a["codice"] for a in esito["alert_previsti"]]
    assert codici == [mod.ALERT_IVA_MENSILE, mod.ALERT_IVA_MENSILE]
    # l'alert cita gli indizi come nota, non ne nascono alert
    ottobre_alert = next(a for a in esito["alert_previsti"] if a["extra"]["mese"] == 10)
    assert sorted(ottobre_alert["extra"]["hints"]) == [ctrl.INDIZIO_COMPENSAZIONE_6099, ctrl.INDIZIO_ERRORE_PERIODO]


def test_una_lipe_a_credito_o_senza_vp14_non_da_alert():
    db = _db()
    _run(db.lipe_periodi.insert_many([
        _lipe("2026-01", 18324.30, segno="credito"),
        {"periodo": "2026-02", "iva_da_versare_o_credito": None, "quadratura_ok": True, "nome_file": "LIPE_2026.pdf"},
    ]))
    esito = _run(mod.incroci(db))
    gen, feb = esito["confronti_iva_mensile"]
    assert gen["dovuto_da_lipe"] == 0.0 and gen["stato"] == "OK"
    assert feb["dovuto_da_lipe"] is None and feb["stato"] == "NON_DETERMINABILE" and "VP14" in feb["nota"]
    assert esito["alert_previsti"] == []


def test_un_avviso_54bis_pagato_con_i_suoi_codici_e_uno_parziale():
    db = _db()
    _run(db.fiscal_documents.insert_many([
        {"id": "cv6-pagata", "filename": "CV62024-1.pdf", "document_type": "COMUNICAZIONE_IRREGOLARITA",
         "comunicazione_54bis": {"numero_comunicazione": "1", "anno_modello": 2024, "anno_imposta": 2024,
                                 "tipo_modello": "LIPE", "importo_totale": 1633.04, "data_notifica": "2025-02-22",
                                 "periodi": [{"codice_tributo_da_versare": "9035", "codice_tributo_sanzioni": "9034",
                                              "codice_tributo_interessi": "9033", "imposta_da_versare": 1463.15,
                                              "sanzioni": 146.32, "interessi": 23.57, "totale": 1633.04, "mese": "GIUGNO"}]}},
        {"id": "cv6-parziale", "filename": "CV62023-2.pdf", "document_type": "AVVISO_BONARIO",
         "comunicazione_54bis": {"numero_comunicazione": "2", "anno_modello": 2024, "anno_imposta": 2023,
                                 "tipo_modello": "REDDITI", "importo_totale": 7754.58,
                                 "periodi": [{"codice_tributo_da_versare": "9571", "codice_tributo_sanzioni": "9573",
                                              "codice_tributo_interessi": "9572", "totale": 7754.58}]}},
        {"id": "cv6-senza-righe", "filename": "CV62022-3.pdf", "document_type": "COMUNICAZIONE_IRREGOLARITA"},
    ]))
    _run(db.quietanze_f24.insert_many([
        _q("q-54bis", "P9", "2025-03-10", [("9035", "2024", 1463.15, 0.0), ("9034", "2024", 146.32, 0.0),
                                            ("9033", "2024", 23.57, 0.0)]),
        _q("q-parz", "P10", "2026-06-10", [("9571", "2023", 3000.0, 0.0)]),
    ]))
    esito = _run(mod.incroci(db, oggi=date(2026, 9, 16)))
    per_id = {c["document_id"]: c for c in esito["comunicazioni_54bis"]}
    assert per_id["cv6-pagata"]["stato"] == "PAGATA" and per_id["cv6-pagata"]["importo_versato"] == 1633.04
    assert per_id["cv6-pagata"]["scadenza"] == "2025-03-24" and per_id["cv6-pagata"]["giorni_oltre_scadenza"] is None
    assert per_id["cv6-parziale"]["stato"] == "PARZIALE" and per_id["cv6-parziale"]["mancante"] == 4754.58
    assert [s["document_id"] for s in esito["comunicazioni_senza_righe_strutturate"]] == ["cv6-senza-righe"]
    (alert,) = esito["alert_previsti"]
    assert alert["codice"] == mod.ALERT_54BIS and alert["entita_id"] == "cv6-parziale"


def test_file_rotti_elencati_senza_alert():
    db = _db()
    _run(db.fiscal_documents.insert_one({"id": "d-ocr", "filename": "scan.pdf", "document_type": "F24",
                                         "review_status": "TO_VERIFY"}))
    _run(db.fiscal_pages.insert_one({"document_id": "d-ocr", "page_number": 2, "requires_ocr": True}))
    esito = _run(mod.incroci(db))
    (rotto,) = esito["file_rotti"]
    assert rotto["document_id"] == "d-ocr" and len(rotto["motivi"]) == 2
    assert esito["alert_previsti"] == []


def test_confronta_importi_e_la_soglia_di_un_euro():
    assert mod.confronta_importi(100000, 100050)["stato"] == "OK"
    assert mod.confronta_importi(100000, 100101)["stato"] == "ECCEDENTE"
    assert mod.confronta_importi(100000, 0) == {"stato": "MANCANTE", "differenza_cents": -100000, "mancante_cents": 100000}
    assert mod.confronta_importi(100000, 40000)["stato"] == "PARZIALE"
    assert mod.confronta_importi(None, 0)["stato"] == "NON_DETERMINABILE"


# ── endpoint e scheduler ─────────────────────────────────────────────────────

def test_endpoint_incroci_e_solo_admin_e_filtra_gli_anni(golden, monkeypatch):
    from app.database import Database
    from app.routers import incroci_fiscali as router_mod
    from app.utils.dependencies import get_current_admin_user

    db = _archivio_dal_golden(golden)
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))
    app = FastAPI()
    app.include_router(router_mod.router, prefix="/api/fiscale")
    assert TestClient(app).get("/api/fiscale/incroci").status_code in (401, 403)
    app.dependency_overrides[get_current_admin_user] = lambda: {"role": "admin"}
    res = TestClient(app).get("/api/fiscale/incroci?anni=2021,2024")
    assert res.status_code == 200, res.text
    corpo = res.json()
    assert corpo["anni"] == [2021, 2024] and len(corpo["confronti_iva_mensile"]) == 24
    assert [r["anno_imposta"] for r in corpo["irap_riscontro"]] == [2021, 2024]
    assert len(corpo["alert_previsti"]) == 7 + 1 + 1 + 1  # IVA 2021 (7) e 2024 (1), IRAP 2024, 54-bis 2024
    assert TestClient(app).get("/api/fiscale/incroci?anni=duemila").status_code == 422


def test_confronto_commercialista_e_servito_dal_motore(golden, monkeypatch):
    from app.services import confronto_iva_commercialista as conf
    from app.services import iva_liquidation_query

    db = _archivio_dal_golden(golden)

    async def _snapshot(_db, anno, mese):
        return {"stato_calcolo": "NON_CALCOLATO", "motivi": ["archivio_storico"]}

    monkeypatch.setattr(iva_liquidation_query, "get_iva_period_snapshot", _snapshot)
    esito = _run(conf.confronto_mensile(db, 2024))
    per_periodo = {r["periodo"]: r for r in esito["righe"]}
    assert per_periodo["2024-06"]["f24"]["nota"] == "f24_mancante" and esito["f24_mancanti"] == ["2024-06"]
    settembre = per_periodo["2024-09"]["f24"]
    assert settembre["stato"] == "OK" and settembre["differenza"] == 0.03 and settembre["nota"] == "versato"
    assert per_periodo["2024-02"]["f24"]["documenti"] and per_periodo["2024-02"]["f24"]["codice_tributo"] == "6002"
    assert not hasattr(conf, "f24_iva_per_periodo")


def test_il_giro_del_mattino_e_registrato_con_la_lease(monkeypatch):
    import app.scheduler as scheduler_mod

    class _FakeScheduler:
        def __init__(self):
            self.jobs = []
            self.running = False

        def add_job(self, fn, *args, **kwargs):
            self.jobs.append((fn, args, kwargs))

        def start(self):
            self.running = True

    finto = _FakeScheduler()
    monkeypatch.setattr(scheduler_mod, "scheduler", finto)
    scheduler_mod.start_scheduler()
    per_id = {j[2].get("id"): j for j in finto.jobs if isinstance(j[2], dict)}
    assert "incroci_fiscali" in per_id
    fn, _args, opzioni = per_id["incroci_fiscali"]
    assert fn.__name__ == "_incroci_fiscali_job" and opzioni["coalesce"] is True
    assert "esegui_incroci" in inspect.getsource(fn)
    # Lo scheduler vero (SchedulerConLease) avvolge ogni job nella lease distribuita.
    assert "_esegui_con_lease" in inspect.getsource(scheduler_mod.SchedulerConLease.add_job)
