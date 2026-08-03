"""Test motore controlli noleggio: segnali cessazione e storico driver."""
from app.services.noleggio.controlli import (
    contiene_segnali_cessazione,
    driver_alla_data,
)
from app.services.noleggio.parsers import (
    estrai_breakdown_linea,
    estrai_modello_marca,
    estrai_veicolo_strutturato,
)


def test_descrizione_contabile_non_diventa_modello_auto():
    assert estrai_modello_marca("GW980EP Canone di Locazione", "GW980EP") == ("", "")


def test_targa_strutturata_arval_identifica_mazda_cx60_e_anno():
    linea = {
        "descrizione": "GW980EP Canone di Locazione",
        "altri_dati_gestionali": [{
            "tipo_dato": "TARGA",
            "riferimento_testo": "GW980EP MAZDA CX-60 / 2022 / 5P / SUV",
        }],
    }

    atteso = {
        "targa": "GW980EP",
        "marca": "Mazda",
        "modello": "CX-60",
        "anno_immatricolazione": 2022,
    }
    assert estrai_veicolo_strutturato(linea) == atteso
    assert estrai_breakdown_linea(linea).items() >= atteso.items()


class TestSegnaliCessazione:
    def test_dicitura_in_riga(self):
        inv = {"linee": [{"descrizione": "Canone finale - CESSAZIONE CONTRATTO GG782PN"}]}
        assert "cessazione contratto" in contiene_segnali_cessazione(inv)

    def test_dicitura_in_causale(self):
        inv = {"linee": [], "causali": ["Addebito per restituzione veicolo"]}
        assert "restituzione veicolo" in contiene_segnali_cessazione(inv)

    def test_fattura_normale(self):
        inv = {"linee": [{"descrizione": "Canone locazione mensile BMW X1 GX037HJ"}]}
        assert contiene_segnali_cessazione(inv) == []

    def test_ultimo_canone(self):
        inv = {"linee": [{"descrizione": "Ultimo canone e conguaglio finale km"}]}
        trovate = contiene_segnali_cessazione(inv)
        assert "ultimo canone" in trovate and "conguaglio finale" in trovate


class TestDriverAllaData:
    VEICOLO = {
        "targa": "GX037HJ",
        "driver": "Mario Attuale",
        "driver_id": "d-attuale",
        "assegnazioni": [
            {"driver": "Valerio Ceraldi", "driver_id": "d-vc", "dal": "2024-01-01", "al": "2025-06-30"},
            {"driver": "Mario Attuale", "driver_id": "d-attuale", "dal": "2025-07-01", "al": None},
        ],
    }

    def test_verbale_nel_periodo_storico(self):
        # Verbale del 10/03/2025 → driver valido a quella data, non l'attuale
        r = driver_alla_data(self.VEICOLO, "2025-03-10")
        assert r["driver"] == "Valerio Ceraldi"
        assert r["fonte"] == "storico_assegnazioni"

    def test_verbale_nel_periodo_aperto(self):
        r = driver_alla_data(self.VEICOLO, "2026-01-15")
        assert r["driver"] == "Mario Attuale"
        assert r["fonte"] == "storico_assegnazioni"

    def test_data_fuori_storico_fallback_attuale(self):
        r = driver_alla_data(self.VEICOLO, "2023-05-01")
        assert r["driver"] == "Mario Attuale"
        assert r["fonte"] == "driver_attuale"

    def test_senza_storico(self):
        v = {"driver": "Solo Attuale", "driver_id": "x"}
        r = driver_alla_data(v, "2025-03-10")
        assert r["driver"] == "Solo Attuale"
        assert r["fonte"] == "driver_attuale"

    def test_senza_data(self):
        r = driver_alla_data(self.VEICOLO, None)
        assert r["fonte"] == "driver_attuale"
