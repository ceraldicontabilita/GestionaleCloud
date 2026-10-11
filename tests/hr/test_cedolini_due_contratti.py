"""Due rapporti nello stesso PDF: lettura, deposito HR e reimport della copia."""
import asyncio
import base64

import fitz
import pytest

from app.parsers import busta_paga_multi_template as parser
from app.services import cedolini_manager, cedolini_motore, hr_cedolini_deposito
from app.services.cedolini_rapporti import raggruppa_cedolini
from tests.hr.test_cedolini_versioni import _pipeline, _risultati
from tests.hr.test_hr_cedolini_deposito import ConnessioneFinta, _configura, _cedolino_erp


def _fascicolo(monkeypatch, continuazione=False):
    with fitz.open() as pdf:
        for codice, assunzione, netto in (("000018", "20-11-2024", "345.17"),
                                           ("000028", "26-11-2025", "121.00")):
            page = pdf.new_page()
            page.insert_text((40, 40), "CodiceDipendente", fontsize=8)
            page.insert_text((40, 53), codice, fontsize=8)
            page.insert_text((170, 40), "DataAssunzione", fontsize=8)
            page.insert_text((170, 53), assunzione, fontsize=8)
            page.insert_text((40, 100), "NETTO " + netto, fontsize=8)
            if continuazione:
                pdf.new_page().insert_text((40, 40), "CONTINUAZIONE")
        content = pdf.tobytes()

    def parse(data):
        with fitz.open(stream=data, filetype="pdf") as pdf:
            text = "\n".join(page.get_text() for page in pdf)
        if "NETTO" not in text:
            return {"parse_success": False}
        netto = float(text.split("NETTO ")[1].split()[0])
        return {"parse_success": True, "dipendente": {
            "codice_fiscale": "RSSMRA80A01H501U", "nome_completo": "ROSSI MARIO",
        }, "periodo": {"mese": 11, "anno": 2025}, "totali": {"netto": netto}}

    monkeypatch.setattr(parser, "parse_busta_paga_from_bytes", parse)
    return content


@pytest.mark.parametrize("continuazione", [False, True])
def test_due_contratti_stesso_mese_restano_distinti(monkeypatch, continuazione):
    content = _fascicolo(monkeypatch, continuazione)
    units = cedolini_motore._parse_multi_template_units(content)
    assert [u["netto"] for u in units] == [345.17, 121.0]
    assert [u["rapporto_id"] for u in units] == ["000018:2024-11-20", "000028:2025-11-26"]
    assert [(u["source_page_start"], u["source_page_end"]) for u in units] == (
        [(1, 2), (3, 4)] if continuazione else [(1, 1), (2, 2)])


def test_import_e_reimport_conservano_due_buste_in_erp_e_hr(monkeypatch):
    content = _fascicolo(monkeypatch)
    units = cedolini_motore._parse_multi_template_units(content)
    deposita = hr_cedolini_deposito.deposita_cedolino_in_hr
    db, _ = _pipeline(monkeypatch)
    monkeypatch.setattr(hr_cedolini_deposito, "deposita_cedolino_in_hr", deposita)

    class ArchivioHR(ConnessioneFinta):
        async def execute(self, sql, *args):
            result = await super().execute(sql, *args)
            self.cedolini.append(self.inseriti[-1])
            return result

    con = ArchivioHR()
    _configura(monkeypatch, con)

    async def scenario():
        for index, unit in enumerate(units):
            result = _risultati()
            await cedolini_manager.registra_busta(
                db, dict(unit), filename="Due contratti.pdf", pdf_data=unit["_pdf_data"],
                pdf_text=unit["_raw_text"], results=result)
            assert result["cedolini_processati"] == 1
            assert not result.get("versioni_da_decidere")
            assert not result["errori"]
        copia = cedolini_motore._parse_multi_template_units(base64.b64decode(units[1]["_pdf_data"]))[0]
        result = _risultati()
        await cedolini_manager.registra_busta(
            db, copia, filename="Contratto part-time.pdf", pdf_data=copia["_pdf_data"],
            pdf_text=copia["_raw_text"], results=result)
        assert result["gia_presenti"] == 1
        rows = await db["cedolini"].find({}, {"_id": 0}).to_list(None)
        assert len(rows) == 2
        total = list(raggruppa_cedolini(rows).values())[0]
        assert total["netto"] == 466.17
        assert len(total["cedolini_componenti"]) == 2
        assert len(con.inseriti) == 2
        assert sum(c["netto"] for c in con.inseriti) == 466.17
        assert all(c.get("rapporto_id") and c.get("source_page_start") for c in con.inseriti)

    asyncio.run(scenario())


def test_deposito_non_scarti_un_secondo_rapporto_con_lo_stesso_netto():
    con = ConnessioneFinta(cedolini=[_cedolino_erp(rapporto_id="18:2024-11-20")])
    nuovo = _cedolino_erp(rapporto_id="28:2025-11-26", cedolino_dedup_key="secondo")
    assert asyncio.run(hr_cedolini_deposito.deposita_cedolino_in_hr(nuovo, con=con))["esito"] == "inserito"


def test_riga_hr_legacy_non_assorbe_secondo_contratto_con_netto_diverso():
    con = ConnessioneFinta(cedolini=[_cedolino_erp(netto=121)])
    nuovo = _cedolino_erp(rapporto_id="18:2024-11-20", netto=345.17, cedolino_dedup_key="nuovo")
    assert asyncio.run(hr_cedolini_deposito.deposita_cedolino_in_hr(nuovo, con=con))["esito"] == "inserito"


def test_dedup_archivio_non_cancella_due_contratti_con_importi_identici():
    from app.services.doppioni_archivio import identita_cedolino

    prima = _cedolino_erp(rapporto_id="18:2024-11-20")
    seconda = _cedolino_erp(rapporto_id="28:2025-11-26")
    assert identita_cedolino(prima) != identita_cedolino(seconda)
