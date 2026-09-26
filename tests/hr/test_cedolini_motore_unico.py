"""Motore unico dei cedolini: un lettore per ogni tracciato, uno scrittore.

I casi vengono dall'archivio vero (testo anonimizzato): la busta Zucchetti di
un mese a zero con la cella del netto vuota, la 14a Teamsystem con «14a MENS.»
al posto del mese, il foglio presenze Zucchetti, il contratto di lavoro finito
fra i cedolini, lo storico prima del 2018.
"""
import asyncio
import base64
from pathlib import Path

import fitz
import pytest

from app.constants.stati_netto import NETTO_NON_PRESENTE_O_NON_LEGGIBILE
from app.parsers.busta_paga_multi_template import parse_template_teamsystem
from app.parsers.cedolino_voci import leggi_corpo_cedolino, leggi_foglio_presenze
from app.services import cedolini_manager, cedolini_motore

CF = "RSSMRA80A01H501U"


def _pdf(*pagine: str) -> bytes:
    doc = fitz.open()
    for testo in pagine:
        pagina = doc.new_page()
        pagina.insert_text((40, 60), testo, fontsize=7)
    try:
        return doc.tobytes()
    finally:
        doc.close()


def run(coro):
    return asyncio.run(coro)


def test_busta_a_zero_senza_netto_e_una_busta_col_netto_nullo():
    testo = "\n".join([
        "PERIODOsDIsRETRIBUZIONE", "Aprile 2024", "0300123", "ROSSI MARIO", CF,
        "TOTALEsCOMPETENZE", "TOTALEsTRATTENUTE", "ARROTONDAMENTO", "NETTOsDELsMESE",
    ])
    lettura = cedolini_motore.leggi_pdf(_pdf(testo))
    assert lettura["esito"] == cedolini_motore.ESITO_BUSTE
    busta = lettura["buste"][0]
    assert (busta["codice_fiscale"], busta["mese"], busta["anno"]) == (CF, 4, 2024)
    # Cella vuota -> nullo, mai zero.
    assert busta["netto"] is None
    assert busta["stato_netto"] == NETTO_NON_PRESENTE_O_NON_LEGGIBILE


def test_la_quattordicesima_teamsystem_e_la_busta_di_luglio():
    testo = f"Teamsystem S.p.A.\nNETTO BUSTA\n14a MENS.    2022     20     1   5124776507\n{CF}\n"
    letto = parse_template_teamsystem(testo)
    assert letto["periodo"]["mese"] == 7 and letto["periodo"]["anno"] == 2022
    assert letto["tipo_cedolino"] == "quattordicesima"
    tredicesima = parse_template_teamsystem("13a MENS. 2021\n")
    assert tredicesima["periodo"]["mese"] == 12 and tredicesima["tipo_cedolino"] == "tredicesima"


def test_il_foglio_presenze_non_e_una_busta():
    testo = "\n".join([
        "Autorizzazione Inail n. 301 del 15/01/2009", "GIUSTIFICATIVI", "TIMBRATURE",
        "Maggio 2024", CF, "LU 1 8,00", "MA 2 8,00", "ME 3 AI 6,40",
    ])
    lettura = cedolini_motore.leggi_pdf(_pdf(testo))
    assert lettura["esito"] == cedolini_motore.ESITO_PRESENZE
    assert lettura["buste"] == []
    foglio = lettura["presenze"][0]
    assert (foglio["codice_fiscale"], foglio["mese"], foglio["anno"]) == (CF, 5, 2024)


def test_un_contratto_di_lavoro_non_e_un_cedolino():
    testo = f"CONTRATTO INDIVIDUALE DI LAVORO\n{CF}\nLa retribuzione sara' indicata in busta paga.\nAprile 2024"
    lettura = cedolini_motore.leggi_pdf(_pdf(testo))
    assert lettura["esito"] == cedolini_motore.ESITO_NON_CEDOLINO


def test_lo_storico_prima_del_2018_e_fuori_periodo(monkeypatch):
    monkeypatch.setattr(cedolini_motore, "_parse_multi_template_units",
                        lambda _c: [{"codice_fiscale": CF, "mese": 11, "anno": 2012, "_raw_text": ""}])
    lettura = cedolini_motore.leggi_pdf(_pdf("LIBRO UNICO DEL LAVORO"))
    assert lettura["esito"] == cedolini_motore.ESITO_FUORI_PERIODO
    assert lettura["buste"] == [] and "2012" in lettura["motivo"]


def test_voci_e_dati_chiave_dal_corpo_del_cedolino():
    res = leggi_corpo_cedolino("\n".join([
        "C00001 Retribuzione 9,54850 79,99992 ORE 763,48",
        "C50000 Rateo 13ma Mensilita 63,62",
        "C50022 Rateo 14ma Mensilita 63,62",
        "F09081 Tratt. integrativo L.21 67,00",
    ]))
    assert [v["codice"] for v in res["voci"]] == ["C00001", "C50000", "C50022", "F09081"]
    dati = res["dati_chiave"]
    assert dati["rateo_13ma_presente"] is True and dati["rateo_13ma_importo"] == "63,62"
    assert dati["tratt_integrativo_l21"] == "67,00"
    assert dati["indennita_l207_24"] is None       # voce assente: nullo, non zero
    assert leggi_corpo_cedolino("C00001 Retribuzione 763,48")["dati_chiave"]["rateo_13ma_presente"] is False


def test_giorni_lavorati_esclude_i_giorni_con_giustificativo():
    res = leggi_foglio_presenze("\n".join(["LU 1 8,00", "MA 2 8,00", "ME 3 AI 6,40", "GI 4 FE 8,00", "SA 6"]))
    assert res["giorni_lavorati"] == 2 and res["giorni_con_giustificativo"] == 2


@pytest.fixture
def scrittore(monkeypatch):
    chiamate = {"v2": [], "hr": []}

    async def v2(**kw):
        chiamate["v2"].append(kw["cedolino_data"])
        return {"success": True, "prima_nota_id": "pn"}

    async def hr(record, **_):
        chiamate["hr"].append(record)
        return {"esito": "inserito"}

    import app.services.hr_cedolini_deposito as dep
    import app.services.salari_unificati_v2 as sal
    monkeypatch.setattr(sal, "processa_cedolino_v2", v2)
    monkeypatch.setattr(dep, "deposita_cedolino_in_hr", hr)
    return chiamate


def _lettura(esito, buste=(), presenze=()):
    return lambda _c: {"esito": esito, "buste": [dict(b) for b in buste], "presenze": list(presenze),
                       "fuori_periodo": [], "motivo": esito}


def test_la_busta_col_netto_va_in_contabilita_quella_senza_solo_in_hr(scrittore, monkeypatch):
    buste = [
        {"codice_fiscale": CF, "mese": 3, "anno": 2026, "netto": 941.0,
         "stato_netto": "NETTO_VERIFICATO_DA_CEDOLINO", "_pdf_data": "a", "_raw_text": "x"},
        {"codice_fiscale": CF, "mese": 4, "anno": 2026, "netto": None, "_pdf_data": "b", "_raw_text": "y"},
    ]
    monkeypatch.setattr(cedolini_motore, "leggi_pdf", _lettura("buste", buste))
    esito = run(cedolini_manager.processa_tutti_cedolini_pdf(None, base64.b64encode(b"%PDF").decode(), "c.pdf"))
    assert esito["success"] and esito["cedolini_processati"] == 1 and esito["buste_senza_netto"] == 1
    assert [c["mese"] for c in scrittore["v2"]] == [3]
    assert [c["mese"] for c in scrittore["hr"]] == [4] and scrittore["hr"][0]["pdf_data"] == "b"


def test_presenze_e_illeggibili_non_scrivono_nulla(scrittore, monkeypatch):
    monkeypatch.setattr(cedolini_motore, "leggi_pdf", _lettura("presenze", presenze=[{}]))
    esito = run(cedolini_manager.processa_tutti_cedolini_pdf(None, base64.b64encode(b"%PDF").decode(), "p.pdf"))
    assert esito["esito"] == "presenze" and esito["fogli_presenze"] == 1
    monkeypatch.setattr(cedolini_motore, "leggi_pdf", _lettura("illeggibile"))
    esito = run(cedolini_manager.processa_tutti_cedolini_pdf(None, base64.b64encode(b"%PDF").decode(), "i.pdf"))
    assert esito["success"] is False and esito["errori"]
    assert scrittore == {"v2": [], "hr": []}


def test_nessun_motore_parallelo_dei_cedolini():
    """Libro Unico, Document AI e regex storico non scrivono piu' cedolini."""
    assert not Path("app/services/libro_unico_workflow.py").exists()
    sorgente = Path("app/services/cedolini_manager.py").read_text(encoding="utf-8")
    for vietato in ("document_ai_extractor", "payslip_parser_v2", "processa_cedolino_completo"):
        assert vietato not in sorgente
    saver = Path("app/services/document_data_saver.py").read_text(encoding="utf-8")
    assert "save_busta_paga_to_gestionale" not in saver
    documenti = Path("app/routers/documenti.py").read_text(encoding="utf-8")
    assert "import_libro_unico" not in documenti


def test_voci_e_stato_netto_finiscono_nel_registro():
    sorgente = Path("app/services/salari_unificati_v2.py").read_text(encoding="utf-8")
    assert '"voci", "dati_chiave"' in sorgente and 'cedolino_record["stato_netto"]' in sorgente


def _parole(*celle):
    """Parole PyMuPDF (x0, y0, x1, y1, testo) di una busta anonima."""
    return [list(c) for c in celle]


def test_il_netto_zucchetti_si_legge_dalla_cella_sotto_l_etichetta():
    from app.parsers.busta_paga_multi_template import _netto_dalla_cella

    classico = _parole((531, 712, 551, 717, "NETTO"), (461, 719, 476, 725, "0,67"),
                       (515, 719, 560, 725, "1.018,00+"))
    assert _netto_dalla_cella([classico]) == {"netto": 1018.0}
    nuovo = _parole((487, 730, 534, 737, "NETTOsDELsMESE"), (519, 741, 554, 750, "941,00"))
    assert _netto_dalla_cella([nuovo]) == {"netto": 941.0}
    # Cella vuota: l'arrotondamento sopra l'etichetta non e' il netto.
    vuota = _parole((487, 730, 534, 737, "NETTOsDELsMESE"), (562, 725, 578, 732, "0,35"))
    assert _netto_dalla_cella([vuota]) == {"netto": None}


def test_il_netto_non_si_ricalcola_mai_da_competenze_e_trattenute():
    from app.constants.stati_netto import (
        MULTIPLE_NETS_DA_VERIFICARE,
        NETTO_NON_PRESENTE_O_NON_LEGGIBILE,
        NETTO_VERIFICATO_DA_CEDOLINO,
    )
    from app.parsers.busta_paga_multi_template import _verifica_netto

    assente = {"totali": {"competenze": 1227.09, "trattenute": 209.58}}
    _verifica_netto(assente)
    assert assente["totali"].get("netto") is None
    assert assente["totali"]["stato_netto"] == NETTO_NON_PRESENTE_O_NON_LEGGIBILE

    dal_testo = {"totali": {"competenze": 1227.09, "trattenute": 209.58, "netto": 0.48}}
    _verifica_netto(dal_testo)
    assert dal_testo["totali"]["netto"] is None and dal_testo["totali"]["netto_letto"] == 0.48
    assert dal_testo["totali"]["stato_netto"] == MULTIPLE_NETS_DA_VERIFICARE

    # La cella vince anche se competenze e trattenute sono lette male.
    dalla_cella = {"totali": {"competenze": 909.68, "trattenute": 342.89, "netto": 1252.0,
                              "netto_da_cella": True}}
    _verifica_netto(dalla_cella)
    assert dalla_cella["totali"]["netto"] == 1252.0
    assert dalla_cella["totali"]["stato_netto"] == NETTO_VERIFICATO_DA_CEDOLINO
    assert dalla_cella["totali"]["netto_calcolato"] == 566.79


def test_una_busta_col_netto_da_verificare_non_va_in_prima_nota(scrittore, monkeypatch):
    buste = [{"codice_fiscale": CF, "mese": 5, "anno": 2026, "netto": 900.0,
              "stato_netto": "MULTIPLE_NETS_DA_VERIFICARE", "_pdf_data": "c", "_raw_text": ""}]
    monkeypatch.setattr(cedolini_motore, "leggi_pdf", _lettura("buste", buste))
    esito = run(cedolini_manager.processa_tutti_cedolini_pdf(None, base64.b64encode(b"%PDF").decode(), "m.pdf"))
    assert scrittore["v2"] == [] and len(scrittore["hr"]) == 1
    assert esito["buste_senza_netto"] == 1
