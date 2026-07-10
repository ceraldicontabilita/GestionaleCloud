"""
Test funzioni pure del ciclo di vita trattenute verbali.
Nessun DB reale: si testano solo calcolo mese successivo, validazione
formato mese, matching voci cedolino ed estrazione testo ricercabile.
"""
from datetime import date, datetime, timezone

from app.services.trattenute_verbali_service import (
    PAROLE_VOCE_TRATTENUTA,
    estrai_testo_cedolino,
    mese_successivo,
    periodo_yyyymm,
    trova_voce_trattenuta,
    valida_mese_cedolino,
)


# ── mese_successivo ─────────────────────────────────────────────────────

class TestMeseSuccessivo:
    def test_data_semplice(self):
        assert mese_successivo("2026-01-15") == "2026-02"

    def test_datetime_iso_con_z(self):
        assert mese_successivo("2026-06-30T10:00:00Z") == "2026-07"

    def test_cavallo_anno(self):
        # Pagamento a dicembre → cedolino di gennaio anno dopo
        assert mese_successivo("2025-12-05") == "2026-01"

    def test_oggetto_datetime(self):
        assert mese_successivo(datetime(2026, 7, 10, tzinfo=timezone.utc)) == "2026-08"

    def test_oggetto_date(self):
        assert mese_successivo(date(2026, 12, 31)) == "2027-01"

    def test_stringa_solo_anno_mese(self):
        assert mese_successivo("2026-03") == "2026-04"

    def test_input_non_valido(self):
        assert mese_successivo(None) is None
        assert mese_successivo("") is None
        assert mese_successivo("non-una-data") is None
        assert mese_successivo(12345) is None


# ── valida_mese_cedolino / periodo_yyyymm ───────────────────────────────

class TestFormatoMese:
    def test_formati_validi(self):
        assert valida_mese_cedolino("2026-08")
        assert valida_mese_cedolino("2026-12")
        assert valida_mese_cedolino(" 2026-01 ")  # spazi tollerati

    def test_formati_non_validi(self):
        assert not valida_mese_cedolino("2026-13")
        assert not valida_mese_cedolino("2026-00")
        assert not valida_mese_cedolino("2026-8")
        assert not valida_mese_cedolino("08-2026")
        assert not valida_mese_cedolino("2026-08-01")
        assert not valida_mese_cedolino("")
        assert not valida_mese_cedolino(None)
        assert not valida_mese_cedolino(202608)

    def test_periodo_da_mese_anno(self):
        assert periodo_yyyymm(7, 2026) == "2026-07"
        assert periodo_yyyymm("12", "2025") == "2025-12"
        assert periodo_yyyymm(13, 2026) is None
        assert periodo_yyyymm(None, 2026) is None
        assert periodo_yyyymm(5, None) is None


# ── trova_voce_trattenuta (matching voci cedolino) ──────────────────────

class TestTrovaVoceTrattenuta:
    def test_tutte_le_parole_del_catalogo(self):
        for parola in PAROLE_VOCE_TRATTENUTA:
            assert trova_voce_trattenuta(f"voce: {parola} 120,00") == parola

    def test_case_insensitive(self):
        assert trova_voce_trattenuta("TRATTENUTA VERBALE ART. 7") == "trattenuta verbale"
        assert trova_voce_trattenuta("Recupero Verbale n. 123") == "recupero verbale"
        assert trova_voce_trattenuta("MULTA codice strada") == "multa"

    def test_spazi_e_newline_normalizzati(self):
        # Nel PDF la voce può essere spezzata su più spazi/righe
        assert trova_voce_trattenuta("trattenuta   verbale") == "trattenuta verbale"
        assert trova_voce_trattenuta("addebito\nauto aziendale") == "addebito auto"

    def test_nessuna_voce(self):
        assert trova_voce_trattenuta("stipendio ordinario ferie rol tfr") is None
        assert trova_voce_trattenuta("") is None
        assert trova_voce_trattenuta(None) is None

    def test_voce_dentro_testo_lungo(self):
        testo = "PAGA BASE 1.500,00\nCONTINGENZA 120,00\nTRATTENUTA DIPENDENTE VERB. 85,00\nNETTO 1.350,00"
        assert trova_voce_trattenuta(testo) == "trattenuta dipendente"


# ── estrai_testo_cedolino ───────────────────────────────────────────────

class TestEstraiTestoCedolino:
    def test_campi_stringa_semplici(self):
        doc = {"nome_dipendente": "ROSSI MARIO", "note": "recupero verbale 123"}
        testo = estrai_testo_cedolino(doc)
        assert "ROSSI MARIO" in testo
        assert trova_voce_trattenuta(testo) == "recupero verbale"

    def test_voci_annidate_in_lista(self):
        doc = {
            "voci": [
                {"descrizione": "PAGA BASE", "importo": 1500},
                {"descrizione": "Trattenuta verbale n. 99", "importo": -85},
            ]
        }
        assert trova_voce_trattenuta(estrai_testo_cedolino(doc)) == "trattenuta verbale"

    def test_salta_campi_binari(self):
        # Una sequenza base64 può contenere per caso la parola 'multa':
        # i campi binari NON devono entrare nel testo ricercabile.
        doc = {"pdf_data": "aGVsbG8multaXYZ==", "quietanza_pdf": "multa000",
               "descrizione": "stipendio ordinario"}
        testo = estrai_testo_cedolino(doc)
        assert "multa" not in testo.lower()
        assert trova_voce_trattenuta(testo) is None

    def test_valori_non_stringa_ignorati(self):
        doc = {"netto": 1350.5, "mese": 7, "pagato": False, "extra": None}
        assert estrai_testo_cedolino(doc) == ""

    def test_input_none(self):
        assert estrai_testo_cedolino(None) == ""
