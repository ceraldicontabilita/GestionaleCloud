"""Quadro ST del 770 letto per posizione e agganciato allo scadenzario.

Geometria presa dal 770/2025 (periodo 2024) del titolare: etichetta STn a
sinistra, sopra periodo e importi (caselle 1, 2, 6, 7, 8), sotto ravvedimento,
note, codice tributo e data (caselle 9, 10, 11, 14). Importi sintetici.
"""
from app.services import dichiarazioni_quadri as dq
from app.services import scadenzario_tributi as sc

SOCIETA = "04523831214"


def _w(x0, y0, testo, larghezza=20):
    return {"x0": x0, "y0": y0, "x1": x0 + larghezza, "y1": y0 + 8, "text": testo}


def _rigo_st(n, y, mese, anno, ritenute, versato, interessi=None, codice="1001", data=("16", "02", "2024"),
             ravvedimento=False, note=None, distanza_sotto=10):
    """Le parole di un rigo: numeri delle caselle in piccolo, valori accostati."""
    parole = [_w(107, y, f"ST{n}", 18)]
    # sopra: numeri casella a y-12, valori a y-7
    for x, num in ((128, "1"), (208, "2"), (294, "6"), (380, "7"), (467, "8")):
        parole.append(_w(x, y - 12, num, 3))
    parole += [_w(139, y - 7, mese, 12), _w(161, y - 7, anno, 24),
               _w(286 - 48, y - 7, ritenute, 48), _w(458 - 48, y - 7, versato, 48)]
    if interessi:
        parole.append(_w(522, y - 7, interessi, 24))
    # sotto: numeri casella, poi i valori 7 punti piu' in basso
    yn = y + distanza_sotto
    for x, num in ((128, "9"), (157, "10"), (251, "11"), (301, "14"), (409, "15"), (445, "16")):
        parole.append(_w(x, yn, num, 4))
    if ravvedimento:
        parole.append(_w(138, yn + 7, "X", 6))
    if note:
        parole.append(_w(160, yn + 7, note, 6))
    if codice:
        parole.append(_w(256, yn + 7, codice, 20))
    if data:
        g, m, a = data
        parole += [_w(309, yn + 7, g, 10), _w(330, yn + 7, m, 10), _w(351, yn + 7, a, 20)]
    return parole


def _pagina_st(righe, numero=4, testo_extra=""):
    parole = []
    for r in righe:
        parole += r
    testo = ("QUADRO ST\nSezione I\nIdentificativo dichiarazione: 18045028409 - 0000001 del 6/10/2025\n"
             "MODELLO 770/2025\nAnno 2024\n" + testo_extra)
    return {"page_number": numero, "text": testo, "layout_words": parole}


def test_righe_st_lette_per_casella_con_ravvedimento_note_codice_e_data():
    pagina = _pagina_st([
        # ST2 e' il primo rigo del modulo: fra etichetta e caselle corrono le intestazioni.
        _rigo_st(2, 189, "01", "2024", "745,77", "745,77", codice="1001", data=("16", "02", "2024"), distanza_sotto=21),
        _rigo_st(3, 248, "01", "2024", "4.544,54", "4.544,54", codice="1012"),
        _rigo_st(4, 296, "01", "2024", "11,51", "11,51", codice="1701", note="P"),
        _rigo_st(5, 344, "02", "2024", "1.706,64", "1.707,11", interessi="0,47", codice="1001",
                 data=("22", "03", "2024"), ravvedimento=True),
    ])
    esito = dq.estrai_quadri_pagine([pagina])
    assert esito["tipo_letto"] == "MODELLO_770"
    assert esito["anno_imposta"] == 2024 and esito["anno_modello"] == 2025
    assert esito["identificativo"] == "18045028409 - 0000001"
    assert esito["st"] == {"righe_lette": 4, "righe_incomplete": 0, "pagine_senza_coordinate": []}
    righe = {r["rigo"]: r for r in esito["st_righe"]}
    assert righe["ST2"]["codice_tributo"] == "1001" and righe["ST2"]["data_versamento"] == "2024-02-16"
    assert righe["ST3"]["ritenute_operate_cents"] == 454454 and righe["ST3"]["codice_tributo"] == "1012"
    assert righe["ST4"]["note"] == "P" and righe["ST4"]["codice_tributo"] == "1701"
    st5 = righe["ST5"]
    assert st5["periodo"] == "02/2024" and st5["ravvedimento"] is True
    assert st5["importo_versato_cents"] == 170711 and st5["interessi_cents"] == 47
    assert st5["data_versamento"] == "2024-03-22"
    assert righe["ST3"]["ravvedimento"] is False


def test_rigo_senza_codice_o_data_resta_incompleto_non_inventato():
    pagina = _pagina_st([_rigo_st(3, 248, "05", "2023", "280,60", "280,60", codice=None, data=("", "06", "2023"))])
    esito = dq.estrai_quadri_pagine([pagina])
    r = esito["st_righe"][0]
    assert r["codice_tributo"] is None and r["data_versamento"] is None
    assert r["data_versamento_testo"] == " 06 2023".strip() or r["data_versamento_testo"]
    assert esito["st"]["righe_incomplete"] == 1


def test_pagina_st_senza_coordinate_si_conta_solo_se_ha_importi():
    piena = {"page_number": 4, "text": "QUADRO ST\nST3 01 2024 4.544,54 4.544,54\n", "layout_words": []}
    vuota = {"page_number": 5, "text": "Sezione II\nST14\nST15\nST16\n", "layout_words": []}
    st = dq.quadro_st([piena, vuota])
    assert st["pagine_senza_coordinate"] == [4] and st["righe"] == []
    assert dq.pagina_con_quadro("Sezione II\nST15") and dq.pagina_con_quadro("QUADRO ST")
    assert dq.riconosci_tipo([{"text": "MODELLO 770/2025\nQUADRO ST"}]) == "MODELLO_770"


# ── scadenzario ───────────────────────────────────────────────────────────

def _doc770(doc_id, anno, righe, data_presentazione="6/10/2025", identificativo="18045028409 - 0000001"):
    return {"id": doc_id, "filename": f"{doc_id}.pdf",
            "quadri": {"tipo_letto": "MODELLO_770", "anno_imposta": anno, "identificativo": identificativo,
                       "data_presentazione": data_presentazione, "st_righe": righe}}


def _st(mese, anno, codice, versato, ritenute=None, ravvedimento=False, data=None, sezione="I"):
    return {"rigo": "ST3", "sezione": sezione, "mese": mese, "anno": anno, "periodo": f"{mese:02d}/{anno}",
            "ritenute_operate_cents": ritenute if ritenute is not None else versato,
            "importo_versato_cents": versato, "interessi_cents": None, "codice_tributo": codice,
            "data_versamento": data, "ravvedimento": ravvedimento, "note": None}


def _voce(codice, anno, mese, pagato, stato=sc.PUNTUALE):
    return {"chiave": f"sezione_erario|{codice}|{anno}|{mese}", "sezione": "sezione_erario", "codice": codice,
            "anno": anno, "mese": mese, "periodo": f"{mese:02d}/{anno}", "scadenza": None, "scadenza_fonte": "",
            "pagamenti": [{"data": "2024-02-16", "importo_cents": pagato, "stato": stato}],
            "stato": stato, "stato_label": sc.ETICHETTE[stato], "pagato_cents": pagato,
            "ultimo_pagamento": "2024-02-16", "motivazione": ""}


def test_la_correttiva_presentata_dopo_vince_e_le_altre_restano_elencate():
    docs = [_doc770("a", 2024, [_st(1, 2024, "1001", 74577)], "6/10/2025", "18045028409 - 0000001"),
            _doc770("b", 2024, [_st(1, 2024, "1001", 74600)], "27/10/2025", "18112464681 - 0000001")]
    scelte = sc.dichiarazioni_770_canoniche(docs)
    assert scelte[2024]["documento"]["id"] == "b"
    assert [s["document_id"] for s in scelte[2024]["sostituite"]] == ["a"]
    righe = sc.righe_770(docs)
    assert len(righe) == 1 and righe[0]["importo_versato_cents"] == 74600
    assert righe[0]["fonte_770"]["pdf_url"] == "/api/originale/documento_fiscale/b"


def test_riga_st_con_quietanza_confronta_importo_e_ravvedimento():
    voci = [_voce("1001", 2024, 1, 74577), _voce("1001", 2024, 2, 170711, stato=sc.RAVVEDUTO)]
    righe = [{**_st(1, 2024, "1001", 74577, data="2024-02-16"), "fonte_770": {"identificativo": "X"}},
             {**_st(2, 2024, "1001", 170711, ritenute=170664, ravvedimento=True), "fonte_770": {"identificativo": "X"}}]
    esito = {v["chiave"]: v for v in sc.integra_770(voci, righe)}
    gennaio = esito["sezione_erario|1001|2024|1"]
    assert gennaio["confronto_770"] == {"importo": "COINCIDE", "differenza_cents": 0,
                                        "ravvedimento_dichiarato": False, "ravvedimento_coerente": True}
    febbraio = esito["sezione_erario|1001|2024|2"]
    assert febbraio["confronto_770"]["ravvedimento_dichiarato"] is True
    assert febbraio["confronto_770"]["ravvedimento_coerente"] is True
    assert febbraio["dichiarato_770"][0]["ritenute_operate_cents"] == 170664
    assert len(esito) == 2, "nessuna voce nuova quando la quietanza c'e'"


def test_riga_st_senza_quietanza_diventa_attesa_dichiarata_nel_770():
    righe = [{**_st(9, 2023, "1040", 160414, ritenute=118000, ravvedimento=True, data="2023-12-18"),
              "fonte_770": {"identificativo": "18161244457 - 0000003", "anno_imposta": 2023}}]
    esito = sc.integra_770([], righe)
    assert len(esito) == 1
    v = esito[0]
    assert v["stato"] == sc.DICHIARATO_770_SENZA_QUIETANZA
    assert v["stato_label"] == "Dichiarato nel 770, quietanza non in archivio"
    assert v["pagamenti"] == [] and v["pagato_cents"] == 0
    assert v["scadenza"] == "2023-10-16" and v["chiave"] == "sezione_erario|1040|2023|9"
    assert "ravvedimento (X)" in v["motivazione"] and "1.604,14 €" in v["motivazione"]
    assert v["confronto_770"]["importo"] == "QUIETANZA_MANCANTE"
    # riepilogo: il nuovo stato compare fra gli esiti, con il suo conteggio
    rie = sc.riepilogo(esito)
    assert {"id": sc.DICHIARATO_770_SENZA_QUIETANZA, "label": v["stato_label"], "n": 1} in rie["per_stato"]


def test_riga_st_senza_codice_non_crea_chiavi():
    righe = [{**_st(1, 2024, None, 100), "fonte_770": {}}]
    assert sc.integra_770([], righe) == []


def test_sezione_ii_va_sulle_regioni():
    righe = [{**_st(1, 2024, "3802", 5000, sezione="II"), "fonte_770": {}}]
    assert sc.integra_770([], righe)[0]["sezione"] == "sezione_regioni"
