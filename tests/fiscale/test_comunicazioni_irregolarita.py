"""Lettere dell'Agenzia sul controllo delle dichiarazioni: riconosciute dal
contenuto, lette nel prospetto delle somme e incrociate con i versamenti.

Caso reale 07/10/2026: quattro lettere archiviate come «LIPE» (citano le
liquidazioni periodiche) e una 36-bis finita in ERRORI «non riconosciuto»;
nessuna agganciata ai pagamenti. Testi sintetici con la struttura dei PDF.
"""
import asyncio
from datetime import date

from app.services import dichiarazioni_quadri as dq
from app.services import incroci_fiscali as inc
from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.fiscal_domain import classify_document

TESTO_54BIS = (
    "Comunicazione 54-bis n. 0053544925401\nProgressivo n. 00\nCodice atto n. 05354492513\nC.F. 04523831214\n"
    "nei mesi scorsi le abbiamo segnalato possibili anomalie relative ai versamenti dell'IVA da lei dovuta in base "
    "alla comunicazione dei dati delle liquidazioni periodiche IVA presentata per il II trimestre 2024.\n"
    "Puo' regolarizzare la sua posizione versando la somma di euro 1.633,04 entro 60 giorni\n"
    "Comunicazione 54-bis elaborata il 23-01-2025\n"
)
TESTO_PROSPETTO_54BIS = (
    "Liquidazioni periodiche IVA 2024\nProspetto delle somme che risultano dovute\nCodice fiscale\n0 4 5\n"
    "GIUGNO\nCodice\n tributo\nImporto\nImposta a debito\n 1.463,15\nImposta versata\n 0,00\n"
    "Imposta da versare\n9035\n 1.463,15\nSanzioni\n9034\n 146,32\nInteressi\n9033\n 23,57\nTOTALE\n 1.633,04\n"
)
TESTO_36BIS = (
    "Comunicazione n. 0154594223401\nProgressivo n. 00\nCodice atto n. 37581572312\n"
    "dai controlli effettuati sulla sua dichiarazione modello IVA 2023, sono emerse alcune incongruenze\n"
    "versando la somma di euro 27,46 entro 60 giorni\nComunicazione elaborata il 10-04-2025\n"
    "(art. 36-bis del d.P.R. n. 600 del 1973; art. 54-bis del d.P.R. n. 633 del 1972)\n"
)
TESTO_PROSPETTO_36BIS = (
    "IVA 2023\nProspetto delle somme periodiche che risultano dovute\n"
    "MARZO\nCodice\n tributo\nImporto\nImposta a debito\n 370,00\nImposta versata e/o eccedenza versamento precedente\n 359,33\n"
    "Imposta recuperata\n 0,00\nImposta da versare\n9035\n 10,67\nSanzioni\n9034\n 1,07\nInteressi\n9033\n 1,10\nTOTALE\n 12,84\n"
    "APRILE\nCodice\n tributo\nImporto\nImposta a debito\n 2.515,00\nImposta versata e/o eccedenza versamento precedente\n 2.511,42\n"
    "Imposta recuperata\n 0,00\nImposta da versare\n9035\n 3,58\nSanzioni\n9034\n 0,36\nInteressi\n9033\n 0,36\nTOTALE\n 4,30\n"
    "GIUGNO\nCodice\n tributo\nImporto\nImposta a debito\n 4.092,00\nImposta versata e/o eccedenza versamento precedente\n 4.083,36\n"
    "Imposta recuperata\n 0,00\nImposta da versare\n9035\n 8,64\nSanzioni\n9034\n 0,86\nInteressi\n9033\n 0,82\nTOTALE\n 10,32\n"
)
TESTO_COMPLIANCE = (
    "desideriamo informarla che abbiamo riscontrato una possibile anomalia nel versamento dell'IVA dovuta in base "
    "alla comunicazione dei dati delle liquidazioni periodiche IVA relativa al III trimestre 2024. "
    "controllo automatizzato effettuato ai sensi dell'art. 54-bis del d.P.R. n. 633 del 1972.\n"
)
TESTO_LIPE_VERA = "Comunicazione liquidazioni periodiche IVA\nQuadro VP\nVP1 Periodo di riferimento\nVP14 IVA da versare 1.131,77\n"


def _pag(n, testo):
    return {"page_number": n, "text": testo, "layout_words": []}


def test_le_lettere_si_riconoscono_dal_contenuto_prima_della_lipe():
    assert classify_document("CV62024-005354492540100.pdf", TESTO_54BIS + TESTO_PROSPETTO_54BIS)["document_type"] == "COMUNICAZIONE_IRREGOLARITA"
    assert classify_document("CV62022-015459422340100.pdf", TESTO_36BIS + TESTO_PROSPETTO_36BIS)["document_type"] == "COMUNICAZIONE_IRREGOLARITA"
    assert classify_document("Anomalia versamento 222188875.pdf", TESTO_COMPLIANCE)["document_type"] == "LETTERA_COMPLIANCE"
    assert classify_document("CV2022TF45979574.pdf", "non ci risulta pervenuta la sua Comunicazione liquidazioni periodiche IVA")["document_type"] == "LETTERA_COMPLIANCE"
    assert classify_document("LIPE_2024_367079261.pdf", TESTO_LIPE_VERA)["document_type"] == "LIPE"


def test_54bis_sulla_lipe_letta_con_codici_tributo_e_quadratura():
    esito = dq.estrai_quadri_pagine([_pag(1, TESTO_54BIS), _pag(3, TESTO_PROSPETTO_54BIS)])
    assert esito["tipo_letto"] == "COMUNICAZIONE_IRREGOLARITA"
    c = esito["comunicazione_54bis"]
    assert c["norma"] == "54-bis" and c["numero_comunicazione"] == "0053544925401"
    assert c["codice_atto"] == "05354492513" and c["data_elaborazione"] == "2025-01-23"
    assert c["tipo_modello"] == "LIPE" and c["anno_imposta"] == 2024
    assert c["importo_totale"] == "1633.04" and c["quadratura"]["ok"] is True
    assert c["trimestre_lettera"] == {"trimestre": 2, "anno": 2024}
    [p] = c["periodi"]
    assert p["periodo"] == "Giugno" and p["mese"] == 6 and p["anno"] == 2024
    assert (p["imposta_da_versare"], p["codice_tributo_da_versare"]) == ("1463.15", "9035")
    assert (p["sanzioni"], p["codice_tributo_sanzioni"]) == ("146.32", "9034")
    assert (p["interessi"], p["codice_tributo_interessi"]) == ("23.57", "9033")
    assert p["totale"] == "1633.04" and esito["campi_da_verificare"] == []
    assert esito["identificativo"] == "0053544925401" and esito["anno_imposta"] == 2024


def test_36bis_sulla_dichiarazione_iva_tre_periodi_anno_imposta_meno_uno():
    esito = dq.estrai_quadri_pagine([_pag(1, TESTO_36BIS), _pag(4, TESTO_PROSPETTO_36BIS)])
    c = esito["comunicazione_54bis"]
    assert c["norma"] == "36-bis" and c["tipo_modello"] == "IVA"
    assert c["anno_modello"] == 2023 and c["anno_imposta"] == 2022
    assert [p["periodo"] for p in c["periodi"]] == ["Marzo", "Aprile", "Giugno"]
    assert c["periodi"][0]["imposta_versata"] == "359.33"
    assert c["importo_totale"] == "27.46" and c["quadratura"] == {"ok": True, "somma_periodi": "27.46", "importo_totale": "27.46"}


def test_senza_prospetto_niente_periodi_e_totale_da_verificare():
    esito = dq.estrai_quadri_pagine([_pag(1, TESTO_54BIS.replace("1.633,04", "1.700,00")), _pag(3, TESTO_PROSPETTO_54BIS)])
    c = esito["comunicazione_54bis"]
    assert c["quadratura"]["ok"] is False and esito["campi_da_verificare"] == ["importo_totale"]
    solo_lettera = dq.estrai_quadri_pagine([_pag(1, TESTO_54BIS)])
    assert solo_lettera["comunicazione_54bis"]["periodi"] == [] and solo_lettera["comunicazione_54bis"]["quadratura"] is None


def test_la_lettera_entrata_come_lipe_si_riclassifica_dal_contenuto_con_traccia():
    db = ClientArchivioMemoria()["riclassifica"]
    societa = "04523831214"

    async def scenario():
        await db["fiscal_documents"].insert_one({"id": "fdoc_cv", "company_id": societa, "document_type": "LIPE",
                                                 "filename": "CV62024.pdf", "current_version_id": "v1"})
        await db["fiscal_pages"].insert_one({"company_id": societa, "document_id": "fdoc_cv", "version_id": "v1",
                                             "page_number": 1, "text": TESTO_54BIS, "layout_words": []})
        await db["fiscal_pages"].insert_one({"company_id": societa, "document_id": "fdoc_cv", "version_id": "v1",
                                             "page_number": 3, "text": TESTO_PROSPETTO_54BIS, "layout_words": []})
        await db["fiscal_documents"].insert_one({"id": "fdoc_lipe", "company_id": societa, "document_type": "LIPE",
                                                 "filename": "LIPE_2024.pdf", "current_version_id": "v2"})
        await db["fiscal_pages"].insert_one({"company_id": societa, "document_id": "fdoc_lipe", "version_id": "v2",
                                             "page_number": 1, "text": TESTO_LIPE_VERA, "layout_words": []})
        esito = await dq.estrai_quadri_documento(db, "fdoc_cv", company_id=societa)
        lipe = await dq.estrai_quadri_documento(db, "fdoc_lipe", company_id=societa)
        doc = await db["fiscal_documents"].find_one({"id": "fdoc_cv"}, {"_id": 0})
        doc_lipe = await db["fiscal_documents"].find_one({"id": "fdoc_lipe"}, {"_id": 0})
        return esito, lipe, doc, doc_lipe

    esito, lipe, doc, doc_lipe = asyncio.run(scenario())
    assert esito["esito"] == "letto" and esito["riclassificato"] == "COMUNICAZIONE_IRREGOLARITA"
    assert doc["document_type"] == "COMUNICAZIONE_IRREGOLARITA"
    assert doc["riclassificazione"]["da"] == "LIPE" and doc["comunicazione_54bis"]["numero_comunicazione"] == "0053544925401"
    assert doc["comunicazione_54bis"]["periodi"][0]["codice_tributo_da_versare"] == "9035"
    # la LIPE vera non cambia e non riceve quadri
    assert lipe["esito"] == "tipo_non_riconosciuto" and doc_lipe["document_type"] == "LIPE" and "quadri" not in doc_lipe


def _versamento(id_, data, saldo, righe):
    return {"fonte": "quietanze_f24", "id": id_, "filename": f"{id_}.pdf", "protocollo": f"P{id_}",
            "data_versamento": data, "saldo_cents": saldo, "quietanza": True, "ravvedimento": False,
            "righe": [{"codice": c, "anno": a, "mese": None, "periodo_riferimento": str(a),
                       "importo_debito_cents": imp, "importo_credito_cents": 0} for c, a, imp in righe]}


def _doc54bis():
    esito = dq.estrai_quadri_pagine([_pag(1, TESTO_54BIS), _pag(3, TESTO_PROSPETTO_54BIS)])
    return {"id": "fdoc_cv", "filename": "CV62024.pdf", "document_type": "COMUNICAZIONE_IRREGOLARITA",
            "comunicazione_54bis": esito["comunicazione_54bis"]}


def test_incrocio_pagata_con_i_codici_della_comunicazione():
    v = _versamento("q1", "2025-02-17", 163304, [("9035", 2024, 146315), ("9034", 2024, 14632), ("9033", 2024, 2357)])
    voce = inc._comunicazione_54bis(_doc54bis(), [v], date(2026, 10, 7))
    assert voce["stato"] == "PAGATA" and voce["pagata"] is True
    assert voce["importo_totale"] == 1633.04 and voce["importo_versato"] == 1633.04
    assert voce["codice_atto"] == "05354492513" and voce["candidati_per_importo"] == []


def test_incrocio_versamento_di_pari_importo_con_codici_diversi_e_da_verificare_non_pagata():
    """La quietanza del 17/02/2025 (1.633,04 €) e' stata letta con il solo codice
    9001: importo e data coincidono, i codici no. Candidato, non prova."""
    v = _versamento("q1", "2025-02-17", 163304, [("9001", 2024, 163304)])
    voce = inc._comunicazione_54bis(_doc54bis(), [v], date(2026, 10, 7))
    assert voce["stato"] == "DA_VERIFICARE" and voce["pagata"] is False
    assert voce["candidati_per_importo"][0]["protocollo"] == "Pq1"
    assert voce["candidati_per_importo"][0]["codici_tributo"] == ["9001"]
    assert "pari importo" in voce["nota"]
    # un versamento uguale ma prima dell'elaborazione non e' candidato
    prima = _versamento("q0", "2024-12-01", 163304, [("9001", 2024, 163304)])
    voce2 = inc._comunicazione_54bis(_doc54bis(), [prima], date(2026, 10, 7))
    assert voce2["stato"] == "NON_PAGATA" and voce2["candidati_per_importo"] == []


def test_l_arretrato_dei_quadri_si_smaltisce_a_lotti_e_non_ripassa_il_gia_letto():
    db = ClientArchivioMemoria()["arretrato"]
    societa = "04523831214"

    async def scenario():
        for i in range(3):
            await db["fiscal_documents"].insert_one({"id": f"cv{i}", "company_id": societa, "document_type": "LIPE",
                                                     "filename": f"CV{i}.pdf", "current_version_id": f"v{i}"})
            await db["fiscal_pages"].insert_one({"company_id": societa, "document_id": f"cv{i}", "version_id": f"v{i}",
                                                 "page_number": 1, "text": TESTO_54BIS, "layout_words": []})
        await db["fiscal_documents"].insert_one({"id": "lipe", "company_id": societa, "document_type": "LIPE",
                                                 "filename": "LIPE.pdf", "current_version_id": "vl"})
        await db["fiscal_pages"].insert_one({"company_id": societa, "document_id": "lipe", "version_id": "vl",
                                             "page_number": 1, "text": TESTO_LIPE_VERA, "layout_words": []})
        await db["fiscal_documents"].insert_one({"id": "senza_pagine", "company_id": societa,
                                                 "document_type": "DICHIARAZIONE_IVA", "filename": "x.pdf"})
        primo = await dq.estrai_quadri_arretrato(db, limite=2, company_id=societa)
        secondo = await dq.estrai_quadri_arretrato(db, limite=10, company_id=societa)
        terzo = await dq.estrai_quadri_arretrato(db, limite=10, company_id=societa)
        docs = await db["fiscal_documents"].find({}, {"_id": 0}).to_list(10)
        return primo, secondo, terzo, docs

    primo, secondo, terzo, docs = asyncio.run(scenario())
    assert primo["arretrato"] == 5 and primo["letti"] == 2 and primo["riclassificati"] == 2 and primo["restanti"] == 3
    assert secondo["arretrato"] == 3 and secondo["letti"] == 1 and secondo["tipo_non_riconosciuto"] == 1
    assert secondo["pagine_assenti"] == 1 and secondo["restanti"] == 0
    assert terzo["arretrato"] == 0, "il secondo giro non ripassa niente"
    assert all(d.get("quadri_controllati_v") == dq.PARSER_VERSION for d in docs)
    tipi = {d["id"]: d["document_type"] for d in docs}
    assert tipi["cv0"] == tipi["cv1"] == tipi["cv2"] == "COMUNICAZIONE_IRREGOLARITA" and tipi["lipe"] == "LIPE"
