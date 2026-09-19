"""La scadenza della fattura e' quella dichiarata nell'XML, non «+30 giorni».

`import_parsed_invoice` — il canale automatico, quello del Drive, da cui
passa la stragrande maggioranza delle fatture — calcolava `data_scadenza`
sempre e solo come data fattura + 30 giorni, con un commento che diceva
«come l'upload manuale». L'upload manuale invece prendeva prima la scadenza
dichiarata nelle `pagamento_rate` dell'XML, e usava il +30 solo come
ripiego. Le due copie della stessa regola erano divergenti.

Misurato in produzione il 19/09/2026 sulle 624 fatture attive del canale
Drive: 427 dichiarano una scadenza nell'XML, e in **414** e' stata
sostituita dal +30.

- 390 fatture, 204.069,70 EUR: scadenza **anticipata** in media di 29
  giorni (fino a 40) — mostrate scadute quando non lo sono.
- 24 fatture, 11.742,90 EUR: scadenza **posticipata** fino a 58 giorni —
  scadute davvero e mai segnalate.
"""
from pathlib import Path

import pytest

from app.services.scadenza_fattura import GIORNI_RIPIEGO, scadenza_sintetica

RADICE = Path(__file__).resolve().parents[2]


def test_vince_la_scadenza_dichiarata_nell_xml():
    fattura = {
        "invoice_date": "2026-03-01",
        "pagamento_rate": [{"data_scadenza": "2026-06-30", "importo": 100.0}],
    }

    assert scadenza_sintetica(fattura) == "2026-06-30", (
        "La scadenza pattuita col fornitore sta nell'XML. Sostituirla con "
        "«data fattura + 30» sposta il termine anche di 58 giorni."
    )


def test_fra_piu_rate_vince_la_prima():
    fattura = {
        "invoice_date": "2026-03-01",
        "pagamento_rate": [
            {"data_scadenza": "2026-08-31"},
            {"data_scadenza": "2026-05-31"},
            {"data_scadenza": "2026-06-30"},
        ],
    }
    assert scadenza_sintetica(fattura) == "2026-05-31"


def test_senza_scadenze_nell_xml_si_usa_il_ripiego():
    assert scadenza_sintetica({"invoice_date": "2026-03-01"}) == "2026-03-31"
    assert GIORNI_RIPIEGO == 30


@pytest.mark.parametrize("rate", [
    [], None, "non una lista",
    [{"data_scadenza": ""}],
    [{"data_scadenza": "30/06/2026"}],   # formato italiano: non ISO, si scarta
    [{"data_scadenza": None}],
    ["non un dizionario"],
])
def test_una_scadenza_illeggibile_non_blocca_il_ripiego(rate):
    assert scadenza_sintetica({"invoice_date": "2026-03-01", "pagamento_rate": rate}) == "2026-03-31"


@pytest.mark.parametrize("data", ["", None, "non-una-data", "2026-13-45"])
def test_senza_data_fattura_non_si_inventa_niente(data):
    """Campo vuoto e segnalazione, mai un valore plausibile."""
    assert scadenza_sintetica({"invoice_date": data}) is None


def test_una_scadenza_xml_regge_anche_senza_data_fattura():
    fattura = {"pagamento_rate": [{"data_scadenza": "2026-06-30T00:00:00"}]}
    assert scadenza_sintetica(fattura) == "2026-06-30"


def test_il_canale_automatico_non_calcola_piu_la_scadenza_per_conto_suo():
    """Controprova strutturale: il +30 a mano non deve tornare nel router."""
    sorgente = (
        RADICE / "app" / "routers" / "invoices" / "fatture_upload.py"
    ).read_text(encoding="utf-8")

    assert "timedelta(days=30)" not in sorgente, (
        "La regola della scadenza sta in `app/services/scadenza_fattura.py`. "
        "Ricalcolarla a mano nel router e' come le due copie divergenti da "
        "cui e' nato questo difetto."
    )
    assert sorgente.count("scadenza_sintetica(parsed)") == 2, (
        "Entrambi i percorsi di import — upload manuale e canale automatico "
        "— devono passare dalla stessa funzione."
    )
