"""Audit 19/09/2026, punto 4 — tetto annuo noleggio auto NON cumulativo.

Prima `calcola_importi_fiscali()` applicava il limite di deducibilita'
dell'art. 164 TUIR (3.615,20 €/anno) a livello di SINGOLA fattura
(`min(imponibile, limite)`): due canoni mensili dello stesso contratto nello
stesso anno deducevano il limite pieno DUE volte, invece di dividerselo.
Ora il limite si applica al RESIDUO dell'anno per lo stesso contratto
(`numero_contratto_noleggio`, o in mancanza la P.IVA fornitore).
"""
import asyncio

from app.services import learning_machine_cdc as lm
from app.services.archivio_documenti_memoria import ClientArchivioMemoria


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


NOLEGGIO_CONFIG = lm.CENTRI_COSTO["6.1_NOLEGGIO_AUTO"]


# ------------------------------------------------------------------
# calcola_importi_fiscali: funzione pura, limite RESIDUO sull'anno
# ------------------------------------------------------------------

def test_prima_fattura_dellanno_usa_lintero_limite():
    importi = lm.calcola_importi_fiscali(3000.0, 660.0, NOLEGGIO_CONFIG)
    assert importi["imponibile_limitato_periodo"] == 3000.0
    assert importi["imponibile_deducibile_ires"] == 600.0  # 3000 * 20%


def test_seconda_fattura_dello_stesso_contratto_usa_solo_il_residuo():
    """3.615,20 già "consumati" per 3.000 dalla prima fattura: alla seconda
    resta un residuo di 615,20, non un nuovo tetto pieno."""
    importi = lm.calcola_importi_fiscali(
        3000.0, 660.0, NOLEGGIO_CONFIG, imponibile_gia_dedotto_anno=3000.0,
    )
    assert importi["imponibile_limitato_periodo"] == 615.20
    assert importi["imponibile_deducibile_ires"] == round(615.20 * 0.20, 2)


def test_tetto_esaurito_azzera_il_residuo_senza_andare_sotto_zero():
    importi = lm.calcola_importi_fiscali(
        3000.0, 660.0, NOLEGGIO_CONFIG, imponibile_gia_dedotto_anno=3615.20,
    )
    assert importi["imponibile_limitato_periodo"] == 0.0
    assert importi["imponibile_deducibile_ires"] == 0.0


def test_centro_senza_limite_annuo_ignora_il_parametro():
    caffe = lm.CENTRI_COSTO["1.1_CAFFE_BEVANDE_CALDE"]
    importi = lm.calcola_importi_fiscali(100.0, 22.0, caffe, imponibile_gia_dedotto_anno=999.0)
    assert importi["imponibile_limitato_periodo"] is None
    assert importi["imponibile_deducibile_ires"] == 100.0  # deducibilita' 100%, nessun tetto


# ------------------------------------------------------------------
# somma_gia_dedotto_periodo_anno: aggregazione dal db
# ------------------------------------------------------------------

def test_somma_gia_dedotto_per_numero_contratto():
    db = ClientArchivioMemoria()["test"]
    _run(db["invoices"].insert_one({
        "id": "NOL-1", "centro_costo_id": "6.1_NOLEGGIO_AUTO",
        "invoice_date": "2026-03-01", "numero_contratto_noleggio": "CONTR-XYZ",
        "imponibile_limitato_periodo": 3000.0,
    }))
    # Altro contratto (fornitore diverso o veicolo diverso): non deve contare.
    _run(db["invoices"].insert_one({
        "id": "NOL-ALTRO", "centro_costo_id": "6.1_NOLEGGIO_AUTO",
        "invoice_date": "2026-03-05", "numero_contratto_noleggio": "CONTR-ALTRO",
        "imponibile_limitato_periodo": 1000.0,
    }))
    gia_dedotto = _run(lm.somma_gia_dedotto_periodo_anno(
        db, cdc_id="6.1_NOLEGGIO_AUTO", anno=2026, numero_contratto="CONTR-XYZ",
    ))
    assert gia_dedotto == 3000.0


def test_somma_gia_dedotto_esclude_lanno_precedente():
    db = ClientArchivioMemoria()["test"]
    _run(db["invoices"].insert_one({
        "id": "NOL-2025", "centro_costo_id": "6.1_NOLEGGIO_AUTO",
        "invoice_date": "2025-12-01", "numero_contratto_noleggio": "CONTR-XYZ",
        "imponibile_limitato_periodo": 3000.0,
    }))
    gia_dedotto = _run(lm.somma_gia_dedotto_periodo_anno(
        db, cdc_id="6.1_NOLEGGIO_AUTO", anno=2026, numero_contratto="CONTR-XYZ",
    ))
    assert gia_dedotto == 0.0


def test_somma_gia_dedotto_esclude_la_fattura_corrente():
    db = ClientArchivioMemoria()["test"]
    _run(db["invoices"].insert_one({
        "id": "NOL-CORRENTE", "centro_costo_id": "6.1_NOLEGGIO_AUTO",
        "invoice_date": "2026-03-01", "numero_contratto_noleggio": "CONTR-XYZ",
        "imponibile_limitato_periodo": 3000.0,
    }))
    gia_dedotto = _run(lm.somma_gia_dedotto_periodo_anno(
        db, cdc_id="6.1_NOLEGGIO_AUTO", anno=2026, numero_contratto="CONTR-XYZ",
        escludi_fattura_id="NOL-CORRENTE",
    ))
    assert gia_dedotto == 0.0


def test_somma_gia_dedotto_fallback_su_fornitore_senza_numero_contratto():
    db = ClientArchivioMemoria()["test"]
    _run(db["invoices"].insert_one({
        "id": "NOL-SENZA-CONTRATTO", "centro_costo_id": "6.1_NOLEGGIO_AUTO",
        "invoice_date": "2026-03-01", "supplier_vat": "IT12345678901",
        "imponibile_limitato_periodo": 2000.0,
    }))
    gia_dedotto = _run(lm.somma_gia_dedotto_periodo_anno(
        db, cdc_id="6.1_NOLEGGIO_AUTO", anno=2026, fornitore_piva="IT12345678901",
    ))
    assert gia_dedotto == 2000.0


# ------------------------------------------------------------------
# End-to-end: due fatture dello stesso contratto nello stesso anno
# tramite l'handler automatico (fattura.created)
# ------------------------------------------------------------------

def test_handler_classifica_cdc_cumula_il_tetto_su_due_fatture_dello_stesso_contratto():
    from app.handlers.learning import handler_classifica_cdc

    db = ClientArchivioMemoria()["test"]

    def _seed_invoice(fattura_id, mese):
        _run(db["invoices"].insert_one({
            "id": fattura_id,
            "linee": [{"descrizione": "Canone noleggio auto lungo termine Arval Fiat Panda",
                       "prezzo_totale": 3000.0}],
            "dati_contratto": [{"id_documento": "CONTR-ARVAL-1"}],
            "supplier_vat": "IT00000000001",
            "invoice_date": f"2026-{mese:02d}-15",
        }))

    def _payload(fattura_id, mese):
        return {
            "fattura_id": fattura_id,
            "fornitore_ragione_sociale": "Arval Service Lease Italia Srl",
            "descrizione": "",
            "righe_linee": [{"descrizione": "Canone noleggio auto lungo termine Arval Fiat Panda",
                              "prezzo_totale": 3000.0}],
            "imponibile": 3000.0, "iva": 660.0,
            "data_documento": f"2026-{mese:02d}-15",
        }

    _seed_invoice("NOL-1", 3)
    esito1 = _run(handler_classifica_cdc(_payload("NOL-1", 3), db))
    assert esito1.get("centro_costo") == NOLEGGIO_CONFIG["nome"]
    fattura1 = _run(db["invoices"].find_one({"id": "NOL-1"}))
    assert fattura1["centro_costo_id"] == "6.1_NOLEGGIO_AUTO"
    assert fattura1["numero_contratto_noleggio"] == "CONTR-ARVAL-1"
    assert fattura1["imponibile_limitato_periodo"] == 3000.0
    assert fattura1["imponibile_deducibile_ires"] == 600.0

    _seed_invoice("NOL-2", 4)
    _run(handler_classifica_cdc(_payload("NOL-2", 4), db))
    fattura2 = _run(db["invoices"].find_one({"id": "NOL-2"}))
    assert fattura2["numero_contratto_noleggio"] == "CONTR-ARVAL-1"
    # SENZA cumulo il bug avrebbe rideducibile 3000 di nuovo (deducibile 600).
    # Con il cumulo resta solo il residuo del tetto annuo: 3.615,20 - 3.000.
    assert fattura2["imponibile_limitato_periodo"] == 615.20
    assert fattura2["imponibile_deducibile_ires"] == round(615.20 * 0.20, 2)
