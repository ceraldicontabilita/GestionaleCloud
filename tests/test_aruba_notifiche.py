"""Test del parser notifiche Aruba e della normalizzazione numero fattura."""
import pytest

from app.services.aruba_notifiche import (
    normalizza_numero_fattura,
    parse_notifica_aruba,
    _norm_data,
)


class TestNormalizzaNumero:
    def test_zeri_iniziali(self):
        assert normalizza_numero_fattura("0000123/A") == normalizza_numero_fattura("123/A")

    def test_spazi_e_case(self):
        assert normalizza_numero_fattura(" fpr 12 /b ") == "FPR12/B"

    def test_vuoto(self):
        assert normalizza_numero_fattura("") == ""
        assert normalizza_numero_fattura(None) == ""


class TestNormData:
    def test_italiana(self):
        assert _norm_data("09/07/2026") == "2026-07-09"

    def test_iso(self):
        assert _norm_data("2026-07-09") == "2026-07-09"

    def test_invalida(self):
        assert _norm_data("luglio 2026") is None


class TestParseNotifica:
    def test_formato_etichette(self):
        body = (
            "Ti è stata recapitata una nuova fattura.\n"
            "Mittente: ACME FORNITURE SRL\n"
            "Numero documento: 123/A\n"
            "Data documento: 08/07/2026\n"
            "Importo: 1.234,56 €\n"
        )
        p = parse_notifica_aruba("Aruba Fatturazione: nuova fattura ricevuta", body)
        assert p["completa"] is True
        assert p["fornitore_nome"] == "ACME FORNITURE SRL"
        assert p["numero_fattura"] == "123/A"
        assert p["importo"] == pytest.approx(1234.56)
        assert p["data_documento"] == "2026-07-08"

    def test_formato_discorsivo_nel_subject(self):
        subject = "Ricevuta fattura n. 45 del 01/07/2026"
        body = "Cedente: ROSSI & FIGLI SNC\nTotale documento: 87,90 EUR"
        p = parse_notifica_aruba(subject, body)
        assert p["completa"] is True
        assert p["numero_fattura"] == "45"
        assert p["importo"] == pytest.approx(87.90)
        assert p["fornitore_nome"] == "ROSSI & FIGLI SNC"

    def test_importo_migliaia_senza_decimali_non_ambiguo(self):
        body = "Fornitore: BETA SPA\nNumero fattura: 7\nImporto totale: 1.500,00"
        p = parse_notifica_aruba("", body)
        assert p["importo"] == pytest.approx(1500.0)

    def test_notifica_illeggibile_non_completa(self):
        p = parse_notifica_aruba("Comunicazione di servizio", "Testo senza dati utili")
        assert p["completa"] is False
        assert p["numero_fattura"] is None

    def test_fornitore_url_scartato(self):
        body = "Mittente: https://example.com/xyz\nNumero documento: 9\nImporto: 10,00"
        p = parse_notifica_aruba("", body)
        assert p["fornitore_nome"] is None
        # numero+importo bastano comunque per il riscontro
        assert p["completa"] is True
