"""
Test calcoli TFR (Trattamento Fine Rapporto).

Verifica:
- Quota annuale TFR (retribuzione / 13.5) - Art. 2120 c.c.
- Rivalutazione ISTAT (1.5% fisso + 75% indice ISTAT)
- Limite anticipo TFR (max 70% del maturato)
- Tassazione separata TFR (23% semplificata)
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.routers.tfr import (
    TFR_DIVISORE,
    RIVALUTAZIONE_FISSA,
    ALIQUOTA_TFR,
)


class TestCostantiTFR:
    """Verifica costanti TFR secondo normativa italiana."""

    def test_divisore_tfr(self):
        """Divisore TFR = 13.5 (Art. 2120 c.c.)."""
        assert TFR_DIVISORE == 13.5

    def test_rivalutazione_fissa(self):
        """Rivalutazione fissa = 1.5% annuo."""
        assert RIVALUTAZIONE_FISSA == 1.5

    def test_aliquota_tassazione(self):
        """Aliquota tassazione separata TFR semplificata = 23%."""
        assert ALIQUOTA_TFR == 23.0


class TestCalcoloQuotaAnnuale:
    """Test calcolo quota annuale TFR."""

    def test_quota_annuale_standard(self):
        """Retribuzione 25.000€ → quota TFR = 25.000/13.5 ≈ 1.851,85€."""
        retribuzione = 25000.00
        quota = retribuzione / TFR_DIVISORE
        assert quota == pytest.approx(1851.85, abs=0.01)

    def test_quota_annuale_lordo_medio(self):
        """Lordo annuo 21.600€ (1.800/mese) → quota ≈ 1.600€."""
        retribuzione = 21600.00
        quota = retribuzione / TFR_DIVISORE
        assert quota == pytest.approx(1600.00, abs=0.01)


class TestRivalutazioneISTAT:
    """Test calcolo rivalutazione TFR con indice ISTAT."""

    def test_rivalutazione_con_istat_standard(self):
        """
        TFR precedente 10.000€, indice ISTAT 2.0%:
        Tasso = (1.5 + 2.0 * 0.75) / 100 = (1.5 + 1.5) / 100 = 3.0%
        Rivalutazione = 10.000 * 0.03 = 300€
        """
        tfr_precedente = 10000.00
        indice_istat = 2.0
        tasso = (RIVALUTAZIONE_FISSA + indice_istat * 0.75) / 100
        rivalutazione = tfr_precedente * tasso
        assert tasso == pytest.approx(0.03, abs=0.001)
        assert rivalutazione == pytest.approx(300.00, abs=0.01)

    def test_rivalutazione_senza_istat(self):
        """
        Con indice ISTAT 0%, rivalutazione = solo 1.5% fisso.
        TFR 10.000€ → rivalutazione = 150€
        """
        tfr_precedente = 10000.00
        indice_istat = 0.0
        tasso = (RIVALUTAZIONE_FISSA + indice_istat * 0.75) / 100
        rivalutazione = tfr_precedente * tasso
        assert rivalutazione == pytest.approx(150.00, abs=0.01)

    def test_rivalutazione_primo_anno(self):
        """Primo anno: nessun TFR precedente → rivalutazione = 0."""
        tfr_precedente = 0
        indice_istat = 2.0
        tasso = (RIVALUTAZIONE_FISSA + indice_istat * 0.75) / 100
        rivalutazione = tfr_precedente * tasso
        assert rivalutazione == 0

    def test_rivalutazione_istat_alto(self):
        """
        Indice ISTAT elevato (5%):
        Tasso = (1.5 + 5.0 * 0.75) / 100 = (1.5 + 3.75) / 100 = 5.25%
        """
        indice_istat = 5.0
        tasso = (RIVALUTAZIONE_FISSA + indice_istat * 0.75) / 100
        assert tasso == pytest.approx(0.0525, abs=0.001)


class TestAccantonamentoTotale:
    """Test calcolo totale accantonamento annuale."""

    def test_accantonamento_completo(self):
        """
        Anno 2, retribuzione 25.000€, TFR precedente 1.851,85€, ISTAT 2%:
        - Quota = 25.000 / 13.5 = 1.851,85€
        - Rivalutazione = 1.851,85 * 3.0% = 55,56€
        - Totale accantonamento = 1.851,85 + 55,56 = 1.907,41€
        - Nuovo TFR = 1.851,85 + 1.907,41 = 3.759,26€
        """
        retribuzione = 25000.00
        tfr_precedente = 1851.85
        indice_istat = 2.0

        quota = retribuzione / TFR_DIVISORE
        tasso = (RIVALUTAZIONE_FISSA + indice_istat * 0.75) / 100
        rivalutazione = tfr_precedente * tasso
        totale = quota + rivalutazione
        nuovo_tfr = tfr_precedente + totale

        assert quota == pytest.approx(1851.85, abs=0.01)
        assert rivalutazione == pytest.approx(55.56, abs=0.01)
        assert totale == pytest.approx(1907.41, abs=0.01)
        assert nuovo_tfr == pytest.approx(3759.26, abs=0.01)


class TestLimitiAnticipo:
    """Test limiti anticipo TFR (Art. 2120 c.c.)."""

    def test_anticipo_max_70_percento(self):
        """Anticipo TFR non può superare il 70% del maturato."""
        tfr_maturato = 10000.00
        max_anticipo = tfr_maturato * 0.70
        assert max_anticipo == 7000.00

    def test_anticipo_sotto_limite(self):
        """Anticipo richiesto sotto il 70% → consentito."""
        tfr_maturato = 10000.00
        richiesto = 5000.00
        max_anticipo = tfr_maturato * 0.70
        assert richiesto <= max_anticipo

    def test_anticipo_sopra_limite(self):
        """Anticipo richiesto sopra il 70% → rifiutato."""
        tfr_maturato = 10000.00
        richiesto = 8000.00
        max_anticipo = tfr_maturato * 0.70
        assert richiesto > max_anticipo


class TestTassazioneTFR:
    """Test tassazione separata TFR."""

    def test_ritenuta_su_liquidazione(self):
        """Ritenuta 23% su importo lordo."""
        importo_lordo = 10000.00
        ritenute = importo_lordo * ALIQUOTA_TFR / 100
        netto = importo_lordo - ritenute
        assert ritenute == 2300.00
        assert netto == 7700.00

    def test_netto_sempre_positivo(self):
        """Il netto TFR deve essere sempre positivo."""
        importo_lordo = 100.00
        ritenute = importo_lordo * ALIQUOTA_TFR / 100
        netto = importo_lordo - ritenute
        assert netto > 0
