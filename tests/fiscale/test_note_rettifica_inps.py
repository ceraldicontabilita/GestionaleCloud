"""Note di rettifica INPS (Mod. DMRA) ↔ versamenti DMRA ↔ dilazioni.

Caso reale 07/10/2026: sette note in archivio «da verificare», nessuna
agganciata. Periodo 02/2022 con quattro note (8.025,51 → 7.097,50 →
3.280,98 → 6.215,53): vale l'ultima emessa, le altre restano elencate.
"""
from datetime import date

from app.services import incroci_fiscali as inc
from app.services import inps_adjustment_parser as parser


def _nota(doc_id, periodo, totale, scadenza, emessa=None, matricola="5124776507"):
    return {"id": doc_id, "filename": f"{doc_id}.pdf", "document_type": "nota_rettifica_inps",
            "parsed_metadata": {"periodo_competenza": periodo, "importo_totale": totale, "data_scadenza": scadenza,
                                "data_emissione": emessa, "matricola_inps": matricola,
                                "differenze_contributive": None if totale is None else round(totale - 100, 2),
                                "sanzioni_civili": None if totale is None else 100.0}}


def _versamento(id_, data, causale, periodo, cents):
    anno, mese = int(periodo[3:]), int(periodo[:2])
    return {"fonte": "quietanze_f24", "id": id_, "filename": f"{id_}.pdf", "protocollo": f"P{id_}",
            "data_versamento": data, "saldo_cents": cents, "quietanza": True, "ravvedimento": False,
            "righe": [{"codice": causale, "sezione": "sezione_inps", "anno": anno, "mese": mese,
                       "periodo_riferimento": periodo, "importo_debito_cents": cents, "importo_credito_cents": 0}]}


OGGI = date(2026, 10, 7)


def test_ultima_nota_del_periodo_vince_e_le_altre_restano_sostituite():
    note = [_nota("n1", "02/2022", 8025.51, "2022-10-12", "2022-09-12"),
            _nota("n2", "02/2022", 7097.50, "2022-11-16", "2022-10-17"),
            _nota("n3", "02/2022", 3280.98, "2022-11-23", "2022-10-24"),
            _nota("n4", "02/2022", 6215.53, "2022-12-28", "2022-11-28")]
    [esito] = inc.note_rettifica_inps(note, [], [], OGGI)
    assert esito["document_id"] == "n4" and esito["importo_totale"] == 6215.53
    assert [n["document_id"] for n in esito["note_sostituite"]] == ["n1", "n2", "n3"]
    assert esito["stato"] == "NON_PAGATA" and esito["giorni_oltre_scadenza"] > 1000


def test_versamento_dmra_del_periodo_chiude_la_nota_al_centesimo():
    note = [_nota("n", "01/2023", 2070.21, "2024-02-05", "2024-01-04")]
    v = _versamento("q", "2024-02-05", "DMRA", "01/2023", 207021)
    [esito] = inc.note_rettifica_inps(note, [v], [], OGGI)
    assert esito["stato"] == "PAGATA" and esito["pagata"] is True
    assert esito["f24_versamenti"][0]["codice_tributo"] == "DMRA" and esito["f24_versamenti"][0]["periodo"] == "01/2023"
    # un DM10 dello stesso periodo non e' il versamento della nota
    altro = _versamento("z", "2023-02-16", "DM10", "01/2023", 207021)
    [solo_dm10] = inc.note_rettifica_inps(note, [altro], [], OGGI)
    assert solo_dm10["stato"] == "NON_PAGATA"


def test_importo_diverso_resta_visibile_non_si_assorbe():
    note = [_nota("n", "11/2021", 3963.59, "2022-07-06", "2022-06-06")]
    [esito] = inc.note_rettifica_inps(note, [_versamento("q", "2022-07-06", "DMRA", "11/2021", 18967)], [], OGGI)
    assert esito["stato"] == "PARZIALE" and esito["mancante"] == 3773.92
    [troppo] = inc.note_rettifica_inps(note, [_versamento("q", "2022-07-06", "DMRA", "11/2021", 500000)], [], OGGI)
    assert troppo["stato"] == "PAGATA_IMPORTO_DIVERSO" and troppo["differenza"] == 1036.41


def test_la_dilazione_che_copre_il_periodo_e_un_candidato_non_un_pagamento():
    note = [_nota("n", "02/2022", 6215.53, "2022-12-28", "2022-11-28")]
    dil = {"rif": "INPS.5100.10/05/2023.0392289", "stato": "SALDATA", "causale": "RC01", "matricola": "5124776507",
           "periodo_da": "02/2022", "periodo_a": "11/2022", "totale_debito_cents": 360100, "data_domanda": "2023-05-10"}
    fuori = {**dil, "rif": "altra", "periodo_da": "07/2025", "periodo_a": "07/2025"}
    [esito] = inc.note_rettifica_inps(note, [], [dil, fuori], OGGI)
    assert esito["stato"] == "IN_DILAZIONE_DA_VERIFICARE" and esito["pagata"] is False
    assert [d["rif"] for d in esito["dilazioni_che_coprono_il_periodo"]] == ["INPS.5100.10/05/2023.0392289"]
    assert esito["giorni_oltre_scadenza"] is None


def test_nota_senza_periodo_o_totale_resta_da_verificare():
    senza_periodo = {"id": "x", "filename": "x.pdf", "parsed_metadata": {}}
    senza_totale = _nota("y", "03/2023", None, None)
    esiti = inc.note_rettifica_inps([senza_periodo, senza_totale], [], [], OGGI)
    assert {e["stato"] for e in esiti} == {"DA_VERIFICARE"}


def test_alert_solo_per_le_note_non_pagate_o_parziali():
    esito = {"confronti_iva_mensile": [], "irap_riscontro": [], "iva_annuale_riscontro": [], "comunicazioni_54bis": [],
             "note_rettifica_inps": inc.note_rettifica_inps(
                 [_nota("a", "01/2023", 2070.21, "2024-02-05", "2024-01-04"),
                  _nota("b", "02/2023", 1698.81, "2024-02-05", "2024-01-04")],
                 [_versamento("q", "2024-02-05", "DMRA", "02/2023", 169881)], [], OGGI)}
    alert = inc._alert_previsti(esito)
    assert [a["entita_id"] for a in alert] == ["a"]
    assert alert[0]["codice"] == inc.ALERT_NOTA_INPS and alert[0]["entita_collection"] == "documents_inbox"
    assert "2.070,21 €" in alert[0]["dettaglio"] and "05/02/2024" in alert[0]["dettaglio"]
    from app.services.alert_engine import ALERT_CATALOG
    assert inc.ALERT_NOTA_INPS in ALERT_CATALOG


def test_il_parser_legge_la_data_di_emissione(monkeypatch):
    testo = ("Mod. DMRA Matricola azienda 5124776507 Codice fiscale 04523831214 "
             "La presente nota di rettifica, emessa il 04/01/2024, si riferisce alla denuncia mensile DM-2013 di "
             "competenza 01/2023 con saldo di € 5.500,00. Differenze contributive a debito azienda € 1.887,18 "
             "Sanzioni civili per differenze contributive € 183,03 Importo totale a debito dell' azienda € 2.070,21 "
             "Da versare entro il 05/02/2024 Codice Sede Causale Contributo Matricola Periodo di riferimento Importo "
             "5100 DMRA 5124776507 01/2023 € 2.070,21")
    monkeypatch.setattr(parser, "_extract_text", lambda content: (testo, 2))
    monkeypatch.setattr(parser, "fitz", None, raising=False)
    esito = parser.parse_nota_rettifica_inps(b"%PDF")
    assert esito["data_emissione"] == "2024-01-04" and esito["periodo_competenza"] == "01/2023"
    assert esito["importo_totale"] == 2070.21 and esito["data_scadenza"] == "2024-02-05"
