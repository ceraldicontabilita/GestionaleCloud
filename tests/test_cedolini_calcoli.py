"""
Test calcoli cedolini - IRPEF, contributi INPS, TFR.

Verifica:
- Calcolo IRPEF per scaglioni 2025 (23%, 35%, 43%)
- Calcolo detrazioni lavoro dipendente
- TFR mensile (lordo / 13.5)
- Contributi INPS azienda (30%) e dipendente (9.19%)
- Costo totale azienda
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.routers.cedolini import (
    calcola_irpef_annua,
    calcola_detrazioni_lavoro,
    INPS_AZIENDA_PERCENT,
    INPS_DIPENDENTE_PERCENT,
    INAIL_PERCENT,
    TFR_DIVISORE,
    SCAGLIONI_IRPEF,
    DETRAZIONE_BASE,
)


class TestIRPEF:
    """Test calcolo IRPEF per scaglioni 2025."""

    def test_irpef_primo_scaglione(self):
        """Reddito fino a 28.000€ → aliquota 23%."""
        irpef = calcola_irpef_annua(20000)
        assert irpef == pytest.approx(20000 * 0.23, rel=1e-2)

    def test_irpef_secondo_scaglione(self):
        """Reddito 35.000€: 28.000*23% + 7.000*35%."""
        irpef = calcola_irpef_annua(35000)
        expected = 28000 * 0.23 + 7000 * 0.35
        assert irpef == pytest.approx(expected, rel=1e-2)

    def test_irpef_terzo_scaglione(self):
        """Reddito 60.000€: 28.000*23% + 22.000*35% + 10.000*43%."""
        irpef = calcola_irpef_annua(60000)
        expected = 28000 * 0.23 + 22000 * 0.35 + 10000 * 0.43
        assert irpef == pytest.approx(expected, rel=1e-2)

    def test_irpef_zero(self):
        """Reddito zero produce IRPEF zero."""
        assert calcola_irpef_annua(0) == 0

    def test_irpef_al_limite_primo_scaglione(self):
        """Reddito esattamente 28.000€."""
        irpef = calcola_irpef_annua(28000)
        assert irpef == pytest.approx(28000 * 0.23, rel=1e-2)

    def test_irpef_al_limite_secondo_scaglione(self):
        """Reddito esattamente 50.000€."""
        irpef = calcola_irpef_annua(50000)
        expected = 28000 * 0.23 + 22000 * 0.35
        assert irpef == pytest.approx(expected, rel=1e-2)


class TestDetrazioniLavoro:
    """Test detrazioni lavoro dipendente (Art. 13 TUIR)."""

    def test_detrazione_reddito_basso(self):
        """Reddito ≤ 15.000€ → detrazione base 1.955€."""
        assert calcola_detrazioni_lavoro(12000) == DETRAZIONE_BASE

    def test_detrazione_reddito_medio(self):
        """Reddito tra 15.001€ e 28.000€ → detrazione progressiva."""
        detr = calcola_detrazioni_lavoro(20000)
        expected = 1910 + 1190 * (28000 - 20000) / 13000
        assert detr == pytest.approx(expected, rel=1e-2)

    def test_detrazione_reddito_alto(self):
        """Reddito tra 28.001€ e 50.000€ → detrazione ridotta."""
        detr = calcola_detrazioni_lavoro(35000)
        expected = 1190 * (50000 - 35000) / 22000
        assert detr == pytest.approx(expected, rel=1e-2)

    def test_detrazione_oltre_50000(self):
        """Reddito > 50.000€ → nessuna detrazione."""
        assert calcola_detrazioni_lavoro(60000) == 0

    def test_detrazione_al_limite_15000(self):
        """Reddito esattamente 15.000€."""
        assert calcola_detrazioni_lavoro(15000) == DETRAZIONE_BASE


class TestCostantiContributive:
    """Verifica costanti contributive 2025."""

    def test_inps_azienda(self):
        """INPS carico azienda circa 30%."""
        assert INPS_AZIENDA_PERCENT == 30.0

    def test_inps_dipendente(self):
        """INPS carico dipendente 9.19%."""
        assert INPS_DIPENDENTE_PERCENT == 9.19

    def test_inail(self):
        """INAIL ristorazione circa 2%."""
        assert INAIL_PERCENT == 2.0

    def test_tfr_divisore(self):
        """TFR divisore 13.5 (Art. 2120 c.c.)."""
        assert TFR_DIVISORE == 13.5


class TestCalcoloCedolino:
    """Test calcolo completo cedolino di esempio."""

    def test_calcolo_netto_da_lordo(self):
        """Verifica calcolo netto in busta da lordo."""
        lordo = 1800.00

        # INPS dipendente
        inps_dip = lordo * INPS_DIPENDENTE_PERCENT / 100
        assert inps_dip == pytest.approx(165.42, abs=0.01)

        # Imponibile fiscale
        imponibile = lordo - inps_dip

        # IRPEF annualizzata
        reddito_annuo = imponibile * 12
        irpef_annua = calcola_irpef_annua(reddito_annuo)
        detrazioni_annue = calcola_detrazioni_lavoro(reddito_annuo)
        irpef_netta = max(0, irpef_annua - detrazioni_annue) / 12

        # Netto
        netto = lordo - inps_dip - irpef_netta
        assert netto > 0
        assert netto < lordo

    def test_costo_azienda_maggiore_lordo(self):
        """Il costo azienda deve essere sempre > lordo."""
        lordo = 1800.00
        inps_az = lordo * INPS_AZIENDA_PERCENT / 100
        inail = lordo * INAIL_PERCENT / 100
        tfr = lordo / TFR_DIVISORE
        costo_azienda = lordo + inps_az + inail + tfr
        assert costo_azienda > lordo
        # Circa 45% in più del lordo
        assert costo_azienda / lordo > 1.3

    def test_tfr_mensile(self):
        """TFR mensile = lordo / 13.5 (quota mensile)."""
        lordo = 1800.00
        tfr = lordo / TFR_DIVISORE
        assert tfr == pytest.approx(133.33, abs=0.01)

    def test_scaglioni_irpef_ordinati(self):
        """Verifica che gli scaglioni IRPEF siano ordinati correttamente."""
        limiti = [s[0] for s in SCAGLIONI_IRPEF]
        assert limiti[0] == 28000
        assert limiti[1] == 50000
        assert limiti[2] == float('inf')

    def test_aliquote_irpef_crescenti(self):
        """Verifica che le aliquote IRPEF siano crescenti."""
        aliquote = [s[1] for s in SCAGLIONI_IRPEF]
        assert aliquote[0] < aliquote[1] < aliquote[2]
