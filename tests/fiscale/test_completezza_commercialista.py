"""Completezza del pacchetto commercialista: RT, originali fatture, estratto BPM."""
import asyncio
from datetime import date

from app.services import completezza_commercialista as cc
from app.services.archivio_documenti_memoria import ClientArchivioMemoria


def _scenario(corrispettivi, pos, fatture, movimenti, chiusure=()):
    async def run():
        db = ClientArchivioMemoria()["completezza"]
        for c in corrispettivi:
            await db["corrispettivi"].insert_one(c)
        for p in pos:
            await db["chiusure_pos_manuali"].insert_one(p)
        for f in fatture:
            await db["invoices"].insert_one(f)
        for m in movimenti:
            await db["estratto_conto_movimenti"].insert_one(m)
        for c in chiusure:
            await db["chiusure_attivita"].insert_one(c)
        return await cc.completezza(db, 2026, 8, oggi=date(2026, 9, 28))
    return asyncio.run(run())


def _giorni_agosto(salta=()):
    return [{"data": f"2026-08-{g:02d}", "pagato_elettronico": 10.0, "stato": "definitivo_xml"}
            for g in range(1, 32) if g not in salta]


def test_mese_completo():
    esito = _scenario(
        _giorni_agosto(), [],
        [{"id": "f1", "invoice_number": "1", "invoice_date": "2026-08-05", "status": "imported",
          "drive_file_id": "drv1", "supplier_name": "Alfa"}],
        [{"id": f"m{g}", "data": f"2026-08-{g:02d}"} for g in (3, 14, 29)],
    )
    assert esito["completo"] is True
    assert esito["dal"] == "2026-08-01" and esito["al"] == "2026-08-31"


def test_cosa_manca():
    esito = _scenario(
        # 10 senza chiusura; 11 senza, ma coperto dal 12 (POS e chiusura il giorno dopo);
        # 15-23 ferie dichiarate.
        _giorni_agosto(salta={10, 11, *range(15, 24)}),
        [{"data": "2026-08-11", "importo": 50.0, "gestore": "sumup", "source": "api_sumup"}],
        [
            {"id": "f1", "invoice_number": "1", "invoice_date": "2026-08-05", "status": "imported",
             "drive_file_id": "drv1", "supplier_name": "Alfa"},
            {"id": "f2", "invoice_number": "2", "invoice_date": "2026-08-06", "status": "imported",
             "xml_raw": "<FatturaElettronica/>", "supplier_name": "Beta"},
            {"id": "f3", "invoice_number": "3", "invoice_date": "2026-08-07", "status": "imported",
             "supplier_name": "Gamma"},
            {"id": "f4", "invoice_number": "4", "invoice_date": "2026-08-08", "status": "archived",
             "supplier_name": "Gamma"},
        ],
        [{"id": f"m{g}", "data": f"2026-08-{g:02d}"} for g in (3, 12)],
        [{"id": "ferie", "data_inizio": "2026-08-15", "data_fine": "2026-08-23"}],
    )
    assert esito["rt"]["mancanti"] == ["2026-08-10"]
    assert [f["id"] for f in esito["fatture"]["senza_originale"]] == ["f3"]
    assert esito["fatture"]["totale"] == 3
    assert esito["estratto_bpm"]["completo"] is False and esito["estratto_bpm"]["ultimo"] == "2026-08-12"
    assert esito["completo"] is False
    testo = cc.testo_leggimi(esito)
    assert "Chiusure RT mancanti (1): 10/08/2026" in testo
    assert "3 Gamma del 07/08/2026" in testo
    assert "solo dal 03/08/2026 al 12/08/2026" in testo
    assert testo.rstrip().endswith("PACCHETTO INCOMPLETO: vedi sopra.")


def test_mese_in_corso_non_chiede_oggi_e_ieri():
    assert cc.periodo(2026, 9, date(2026, 9, 28)) == ("2026-09-01", "2026-09-26")
    assert cc.periodo(2026, 0, date(2026, 9, 28)) == ("2026-01-01", "2026-09-26")
