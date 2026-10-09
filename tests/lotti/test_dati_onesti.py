"""Blocco 2 dell'audit Lotti: un numero che non si conosce non è uno zero.

- spesa del mese: l'importo vero è quello della fattura nel gestionale,
  trovata per identità (mai per importo); senza corrispondenza la fattura è
  contata «senza importo», e se il gestionale non risponde il dato è None;
- righe di costo (spese, trasporto, sconti, arrotondamenti) non sono merce;
- il costo di un lotto prodotto viene dal consumo reale per il prezzo di
  fattura, altrimenti None con il motivo — mai lo 0 che mandava il tablet.
"""
import asyncio
import types

import pytest

from app.lotti.routers import supervisor_operativo as sup
from app.lotti.routers.classificatore_alimenti import e_servizio
from app.lotti.routers.lotti_produzione import costo_da_consumo


def _run(coro):
    return asyncio.run(coro)


def _gestionale(monkeypatch, documenti, errore=None):
    import app.routers.lotti_integration as li

    async def _documents():
        if errore:
            raise errore
        return documenti

    monkeypatch.setattr(li, "_documents", _documents)
    monkeypatch.setattr(li, "_projection", lambda doc, include_xml=False: doc)


def test_spesa_per_identita_non_per_importo(monkeypatch):
    _gestionale(monkeypatch, [
        {"source_id": "g1", "invoice_number": "2714", "supplier_vat": "IT07832841212",
         "invoice_date": "2026-09-22", "total_amount": "66.0", "document_type": "TD01"},
        {"source_id": "g2", "invoice_number": "135208", "supplier_vat": "04352551214",
         "invoice_date": "2026-09-21", "total_amount": 293.13, "document_type": "TD01"},
        {"source_id": "g3", "invoice_number": "NC1", "supplier_vat": "04352551214",
         "invoice_date": "2026-09-23", "total_amount": 10, "document_type": "TD04"},
        {"source_id": "g4", "invoice_number": "77", "supplier_vat": "111",
         "invoice_date": "2026-09-20", "total_amount": 5, "document_type": "TD01"},
    ])
    fatture = [
        # collegata dal ponte
        {"gestionale_source_id": "g2", "numero_fattura": "x", "data_fattura": "21/09/2026"},
        # nessun collegamento: numero + P.IVA (con e senza «IT»)
        {"numero_fattura": "2714", "piva": "07832841212", "data_fattura": "22/09/2026"},
        # nota di credito: riduce la spesa
        {"numero_fattura": "NC1", "piva": "04352551214", "data_fattura": "23/09/2026"},
        # numero + data quando la P.IVA manca
        {"numero_fattura": "77", "piva": "", "data_fattura": "20/09/2026"},
        # nessuna corrispondenza: non vale zero, si conta
        {"numero_fattura": "999", "piva": "123", "data_fattura": "19/09/2026"},
    ]
    esito = _run(sup.spesa_da_gestionale(fatture))
    assert esito["totale"] == pytest.approx(66.0 + 293.13 - 10 + 5)
    assert esito["senza_importo"] == 1
    assert esito["errore"] is None


def test_corrispondenza_ambigua_non_si_indovina(monkeypatch):
    _gestionale(monkeypatch, [
        {"source_id": "a", "invoice_number": "1", "supplier_vat": "", "invoice_date": "2026-09-20",
         "total_amount": 10, "document_type": "TD01"},
        {"source_id": "b", "invoice_number": "1", "supplier_vat": "", "invoice_date": "2026-09-20",
         "total_amount": 20, "document_type": "TD01"},
    ])
    esito = _run(sup.spesa_da_gestionale([{"numero_fattura": "1", "data_fattura": "20/09/2026"}]))
    assert esito["totale"] == 0.0 and esito["senza_importo"] == 1


def test_gestionale_giu_non_e_zero(monkeypatch):
    _gestionale(monkeypatch, [], errore=RuntimeError("giù"))
    esito = _run(sup.spesa_da_gestionale([{"numero_fattura": "1", "data_fattura": "20/09/2026"}]))
    assert esito["totale"] is None and "RuntimeError" in esito["errore"]


def test_scorte_non_lette_non_sono_zero(monkeypatch):
    import app.lotti.routers.magazzino_unificato as mu

    async def rotto(**kwargs):
        raise RuntimeError("archivio")

    monkeypatch.setattr(mu, "prodotti_unificati", rotto)
    esito = _run(sup.riepilogo_scorte())
    assert esito["sotto_scorta"] is None and esito["errore"]


def test_scorte_contano_senza_soglia(monkeypatch):
    import app.lotti.routers.magazzino_unificato as mu

    async def avvisi(**kwargs):
        return {"avvisi": [{"livello": mu.LIVELLO_ESAURITO}, {"livello": mu.LIVELLO_SCORTA}]}

    async def prodotti(**kwargs):
        return [{"soglia_minima": 0}, {"soglia_minima": 2}, {"soglia_minima": None}]

    monkeypatch.setattr(mu, "calcola_avvisi_scorte", avvisi)
    monkeypatch.setattr(mu, "prodotti_unificati", prodotti)
    esito = _run(sup.riepilogo_scorte())
    assert esito == {"sotto_scorta": 2, "esauriti": 1, "senza_soglia": 2, "errore": None}


@pytest.mark.parametrize("riga", [
    "Spese trasporto", "SPESE DI TRASPORTO", "Costi di spedizione: GLS CORRIERE ESPRESSO",
    "SCONTO PAGAMENTO", "Sconto cassa 5 % su 329,41 pari a 16,47",
    "ADDEBITO SUL TOTALE SCONTRINO PER ARROTONDAMENTO FISCALE", "Contributo CONAI",
])
def test_righe_di_costo_non_sono_merce(riga):
    assert e_servizio(riga)


@pytest.mark.parametrize("riga", [
    "FARINA 00 KG 25", "UOVA FRESCHE CAT. A", "SALE FINO IODATO", "BURRO PLACCA 1KG",
    "PROSECCO DOC 75CL", "ZUCCHERO SEMOLATO", "LATTE INTERO UHT",
])
def test_merce_resta_merce(riga):
    assert not e_servizio(riga)


def test_costo_da_consumo_reale():
    costo, motivo = costo_da_consumo({"lotti_scalati": [
        {"prodotto": "Farina", "quantita_consumata": 2.5, "prezzo_unitario": 0.8},
        {"prodotto": "Uova", "quantita_consumata": 6, "prezzo_unitario": "0.25"},
    ]})
    assert (costo, motivo) == (3.5, None)


@pytest.mark.parametrize("info, parola", [
    ({"lotti_scalati": [{"prodotto": "Burro", "quantita_consumata": 1, "prezzo_unitario": None}]}, "senza prezzo"),
    ({"lotti_scalati": [{"prodotto": "Burro", "quantita_consumata": 1, "prezzo_unitario": 0}]}, "senza prezzo"),
    ({"lotti_scalati": [{"prodotto": "Burro", "quantita_consumata": 1, "prezzo_unitario": 5}],
      "ingredienti_insufficienti": [{"ingrediente": "Zucchero"}]}, "insufficiente"),
    ({"lotti_scalati": [{"prodotto": "Burro", "quantita_consumata": 1, "prezzo_unitario": 5}],
      "ingredienti_non_trovati": ["Vaniglia"]}, "senza lotto"),
    ({"lotti_scalati": []}, "nessun lotto"),
])
def test_costo_parziale_non_si_spaccia_per_intero(info, parola):
    costo, motivo = costo_da_consumo(info)
    assert costo is None and parola in motivo


def test_tablet_non_manda_piu_costo_zero():
    from pathlib import Path

    testo = (Path(__file__).resolve().parents[2]
             / "frontend_lotti/src/components/haccp/tablet/ModalRegistraLotto.jsx").read_text(encoding="utf-8")
    assert "costo_totale: 0" not in testo


def test_lotto_a_costo_zero_vale_non_noto():
    from app.lotti.servizi.lotto_arricchimento_service import calcola_valore_economico

    assert calcola_valore_economico({"costo_pezzo": 0, "quantita": 10}) is None
    assert calcola_valore_economico({"costo_pezzo": None, "quantita": 10}) is None
    assert calcola_valore_economico({"costo_pezzo": 0.5, "quantita": 10}) == 5.0
