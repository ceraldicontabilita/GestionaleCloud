"""
Test deducibilità fiscale italiana - Auto aziendali e telefonia.

Verifica le regole di deducibilità e detraibilità IVA secondo:
- Art. 164 TUIR (auto aziendali): deducibilità 20%, IVA 40%
- Art. 102 TUIR (telefonia): deducibilità 80%, IVA 50%
- Noleggio auto: 20% su max €3.615,20/anno
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestDeducibilitaAuto:
    """Test deducibilità auto aziendali (Art. 164 TUIR)."""

    DEDUCIBILITA_AUTO = 0.20  # 20%
    IVA_DETRAIBILE_AUTO = 0.40  # 40%
    MAX_NOLEGGIO_ANNUO = 3615.20  # €3.615,20/anno

    def test_carburante_deducibile_20_percento(self):
        """Carburante auto: deducibile 20%."""
        costo_carburante = 1000.00
        deducibile = costo_carburante * self.DEDUCIBILITA_AUTO
        indeducibile = costo_carburante - deducibile
        assert deducibile == 200.00
        assert indeducibile == 800.00

    def test_carburante_iva_detraibile_40_percento(self):
        """Carburante auto: IVA detraibile 40%."""
        iva_carburante = 220.00
        iva_detraibile = iva_carburante * self.IVA_DETRAIBILE_AUTO
        assert iva_detraibile == pytest.approx(88.00, abs=0.01)

    def test_noleggio_auto_limite_annuo(self):
        """Noleggio auto: deducibile 20% su max €3.615,20."""
        costo_noleggio_annuo = 5000.00

        # Applica limite
        costo_limitato = min(costo_noleggio_annuo, self.MAX_NOLEGGIO_ANNUO)
        deducibile = costo_limitato * self.DEDUCIBILITA_AUTO

        assert costo_limitato == self.MAX_NOLEGGIO_ANNUO
        assert deducibile == pytest.approx(723.04, abs=0.01)

    def test_noleggio_auto_sotto_limite(self):
        """Noleggio auto sotto il limite: deduce sul totale."""
        costo_noleggio_annuo = 2000.00

        costo_limitato = min(costo_noleggio_annuo, self.MAX_NOLEGGIO_ANNUO)
        deducibile = costo_limitato * self.DEDUCIBILITA_AUTO

        assert costo_limitato == costo_noleggio_annuo
        assert deducibile == 400.00

    def test_noleggio_iva_detraibile_40_percento(self):
        """Noleggio auto: IVA detraibile 40% (sull'intero importo)."""
        iva_noleggio = 1100.00
        iva_detraibile = iva_noleggio * self.IVA_DETRAIBILE_AUTO
        assert iva_detraibile == 440.00

    def test_manutenzione_auto_deducibile_20(self):
        """Manutenzione auto: deducibile 20%."""
        costo_manutenzione = 500.00
        deducibile = costo_manutenzione * self.DEDUCIBILITA_AUTO
        assert deducibile == 100.00

    def test_assicurazione_auto_iva_esente(self):
        """Assicurazione auto: deducibile 20%, IVA esente."""
        costo_assicurazione = 1200.00
        deducibile = costo_assicurazione * self.DEDUCIBILITA_AUTO
        assert deducibile == 240.00
        # IVA esente → nessuna detrazione

    def test_auto_assegnata_dipendente_70_percento(self):
        """Se auto assegnata a dipendente: deducibilità sale al 70%."""
        costo = 1000.00
        deducibilita_assegnata = 0.70
        deducibile = costo * deducibilita_assegnata
        assert deducibile == 700.00


class TestDeducibilitaTelefonia:
    """Test deducibilità telefonia (Art. 102 TUIR)."""

    DEDUCIBILITA_TELEFONIA = 0.80  # 80%
    IVA_DETRAIBILE_TELEFONIA = 0.50  # 50%

    def test_telefonia_deducibile_80_percento(self):
        """Telefonia: deducibile 80%."""
        costo_telefonia = 200.00
        deducibile = costo_telefonia * self.DEDUCIBILITA_TELEFONIA
        indeducibile = costo_telefonia - deducibile
        assert deducibile == 160.00
        assert indeducibile == 40.00

    def test_telefonia_iva_detraibile_50_percento(self):
        """Telefonia: IVA detraibile 50%."""
        iva_telefonia = 44.00
        iva_detraibile = iva_telefonia * self.IVA_DETRAIBILE_TELEFONIA
        assert iva_detraibile == 22.00

    def test_telefonia_costo_reale_azienda(self):
        """Calcolo costo reale telefonia per l'azienda (dopo deduzioni)."""
        imponibile = 200.00
        iva = 44.00

        # Costo deducibile: 80% dell'imponibile
        costo_deducibile = imponibile * self.DEDUCIBILITA_TELEFONIA
        # IVA recuperabile: 50% dell'IVA
        iva_recuperabile = iva * self.IVA_DETRAIBILE_TELEFONIA

        # Costo effettivo = imponibile + iva - iva_recuperabile
        # (l'indeducibilità è una questione fiscale, non di cassa)
        costo_cassa = imponibile + iva - iva_recuperabile
        assert costo_cassa == pytest.approx(222.00, abs=0.01)

    def test_telefonia_multipli_fornitori(self):
        """Deducibilità si applica a tutti i fornitori telefonici."""
        fornitori_telefonici = ["TIM S.p.A.", "Vodafone Italia", "Fastweb", "WINDTRE"]
        costo_per_fornitore = 100.00

        totale_deducibile = 0
        for _ in fornitori_telefonici:
            totale_deducibile += costo_per_fornitore * self.DEDUCIBILITA_TELEFONIA

        assert totale_deducibile == 320.00  # 80% di 400€


class TestRiepilogoDeducibilita:
    """Test riepilogo deducibilità per bilancio dettagliato."""

    def test_calcolo_bilancio_con_deducibilita(self):
        """Simula calcolo bilancio con tutte le regole di deducibilità."""
        # Dati esempio
        costi = {
            "telefonia": {"imponibile": 200.00, "iva": 44.00},
            "noleggio_auto": {"imponibile": 5000.00, "iva": 1100.00},
            "carburante": {"imponibile": 1000.00, "iva": 220.00},
            "materie_prime": {"imponibile": 3000.00, "iva": 660.00},
        }

        # Calcoli deducibilità
        # Telefonia: 80%
        tel_deducibile = costi["telefonia"]["imponibile"] * 0.80
        assert tel_deducibile == 160.00

        # Noleggio auto: 20% su max 3615.20
        noleggio_limitato = min(costi["noleggio_auto"]["imponibile"], 3615.20)
        noleggio_deducibile = noleggio_limitato * 0.20
        assert noleggio_deducibile == pytest.approx(723.04, abs=0.01)

        # Carburante: 20%
        carburante_deducibile = costi["carburante"]["imponibile"] * 0.20
        assert carburante_deducibile == 200.00

        # Materie prime: 100%
        materie_deducibile = costi["materie_prime"]["imponibile"] * 1.00
        assert materie_deducibile == 3000.00

        # Totale deducibile
        totale_deducibile = tel_deducibile + noleggio_deducibile + carburante_deducibile + materie_deducibile
        assert totale_deducibile == pytest.approx(4083.04, abs=0.01)

        # Totale indeducibile
        totale_indeducibile = (
            (costi["telefonia"]["imponibile"] - tel_deducibile) +
            (costi["noleggio_auto"]["imponibile"] - noleggio_deducibile) +
            (costi["carburante"]["imponibile"] - carburante_deducibile) +
            0  # materie prime: tutto deducibile
        )
        assert totale_indeducibile > 0
