"""Ore lavorate e quota annua TFR non sono settimane o quote mensili.

Fixture sintetiche senza dati personali: l'ordine dei token PDF è diverso
dalle colonne stampate e la quota TFR del mese può non essere disponibile.
"""
import asyncio

import fitz
import pytest

from app.handlers.tfr import handler_aggiorna_tfr
from app.parsers.busta_paga_multi_template import (
    _parse_zucchetti_worked_layout,
    extract_summary,
    parse_busta_paga_from_bytes,
    parse_template_zucchetti_new,
)
from app.services.cedolini_motore import _con_voci
from app.services.salari_unificati_v2 import estrai_ferie_rol_from_text


def _word(x, y, value, width=18):
    return (x, y, x + width, y + 7, value, 0, 0, 0)


def _worked_words(hours="105,50", days="21"):
    # In PyMuPDF le settimane INPS possono apparire prima di tutte le ore.
    return [
        _word(35, 80, "4"), _word(145, 70, "Giorni"),
        _word(180, 60, "LAVORATO", 40), _word(180, 70, "Ore", 12),
        _word(195, 70, "ordinarie", 35), _word(35, 70, "Settimane", 40),
        _word(145, 80, days), _word(180, 80, hours, 35),
    ]


def test_colonne_lavorato_non_leggono_settimane_e_conservano_frazioni():
    assert _parse_zucchetti_worked_layout([_worked_words()]) == {
        "ore_lavorate": 105.5, "giorni_lavorati": 21,
    }


def test_ore_zero_stampate_non_diventano_assenti_nel_riepilogo():
    periodo = _parse_zucchetti_worked_layout([_worked_words("0,00", "0")])
    summary = extract_summary({"periodo": periodo, "ore_ferie": {"ore_lavorate_mese": 8}})
    assert summary["ore_lavorate"] == 0
    assert summary["giorni_lavorati"] == 0


def test_cella_ore_vuota_o_ambigua_non_legge_numeri_di_altre_colonne():
    words = _worked_words()
    vuoti = [w for w in words if w[4] != "105,50"]
    assert "ore_lavorate" not in _parse_zucchetti_worked_layout([vuoti])
    assert "ore_lavorate" not in _parse_zucchetti_worked_layout([
        words + [_word(180, 80, "104,50", 35)],
    ])


def test_testo_senza_celle_non_scambia_quattro_settimane_per_ore():
    parsed = parse_template_zucchetti_new("LAVORATO\n4\n21\n105\n21\n105,50")
    assert "ore_lavorate" not in parsed["periodo"]
    assert "giorni_lavorati" not in parsed["periodo"]
    esplicito = parse_template_zucchetti_new("Z00001 Retribuzione 8,00 105,50000 ORE 844,00")
    assert esplicito["periodo"]["ore_lavorate"] == 105.5


def test_parser_pdf_legge_le_celle_del_lavorato():
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((35, 35), "PERIODOsDIsRETRIBUZIONE\nSettembre 2025", fontsize=7)
    for x, y, _x1, _y1, text, *_ in _worked_words():
        page.insert_text((x, y + 7), text, fontsize=7)
    data = doc.tobytes()
    doc.close()
    summary = extract_summary(parse_busta_paga_from_bytes(data))
    assert summary["ore_lavorate"] == 105.5
    assert summary["giorni_lavorati"] == 21


def test_progressivo_annuo_non_diventa_mensile_o_fondo():
    dati = estrai_ferie_rol_from_text("T.F.R.\nQuota anno\n522,53\nTFR a fondi\nAnticipi")
    assert dati["tfr_quota_anno"] == 522.53
    assert dati["tfr_mese"] is None
    assert dati["tfr_accantonato"] == 0
    summary = extract_summary(parse_template_zucchetti_new("Quota anno\n522,53"))
    assert summary["tfr_quota_anno"] == 522.53
    assert summary["tfr_quota"] is None


def test_quota_mensile_esplicita_rimane_distinta_dal_progressivo():
    dati = estrai_ferie_rol_from_text("Quota anno: 522,53\nTFR mese: 95,50")
    assert dati["tfr_quota_anno"] == 522.53
    assert dati["tfr_mese"] == 95.5
    assert extract_summary({"tfr": {"quota_mese": 0, "quota_anno": 522.53}})["tfr_quota"] == 0
    assert estrai_ferie_rol_from_text("Accantonamento TFR: 2.000,00")["tfr_mese"] is None


def test_ricarica_scheda_preserva_quota_mensile_sconosciuta():
    busta = _con_voci({"_raw_text": "Quota anno: 522,53"})
    assert busta["dati_extra"]["tfr_quota_anno"] == 522.53
    assert "tfr_mese" in busta["dati_extra"]
    assert busta["dati_extra"]["tfr_mese"] is None


class _DbInaccessibile:
    def __getitem__(self, name):
        raise AssertionError("Nessuna scrittura o lettura per la quota mensile assente/zero")


@pytest.mark.parametrize("monthly", [None, 0])
def test_annuale_o_zero_non_generano_un_accantonamento_mensile(monthly):
    result = asyncio.run(handler_aggiorna_tfr({
        "dipendente_id": "dip-test", "mese": 9, "anno": 2025, "lordo": 2000,
        "tfr_quota_mese": monthly, "tfr_quota_anno": 522.53,
    }, _DbInaccessibile()))
    assert result["skipped"] is True
    assert result["reason"] == ("quota mensile non disponibile" if monthly is None else "quota TFR zero")


class _Collection:
    def __init__(self):
        self.docs = []
        self.updates = []

    async def find_one(self, query):
        return next((d for d in self.docs if all(d.get(k) == v for k, v in query.items())), None)

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def update_one(self, query, update):
        self.updates.append((query, update))


def test_mensile_documentato_e_secondo_ingest_non_incrementano_due_volte():
    db = {"tfr_accantonamenti": _Collection(), "dipendenti": _Collection()}
    payload = {"dipendente_id": "dip-test", "anno": 2025, "mese": 9, "lordo": 2000,
               "tfr_quota_mese": 95.5, "tfr_quota_anno": 522.53}
    first = asyncio.run(handler_aggiorna_tfr(payload, db))
    second = asyncio.run(handler_aggiorna_tfr(payload, db))
    assert first["quota"] == 95.5
    assert second["skipped"] is True
    assert len(db["tfr_accantonamenti"].docs) == len(db["dipendenti"].updates) == 1


def test_evento_storico_senza_chiave_mensile_conserva_compatibilita():
    db = {"tfr_accantonamenti": _Collection(), "dipendenti": _Collection()}
    result = asyncio.run(handler_aggiorna_tfr({
        "dipendente_id": "dip-test", "anno": 2025, "mese": 9, "lordo": 1350,
    }, db))
    assert result["quota"] == 100
