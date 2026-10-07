"""Denaro in Decimal nel motore Prima Nota (CLAUDE.md §12, §23).

Il motore ``scritture_contabili`` faceva somme, differenze e confronti con
``float``: ``0.1 + 0.2`` non e' ``0.3`` e ``round(1.005, 2)`` da' ``1.0``.
Su un registro che si quadra al centesimo sono errori veri. Qui si verifica
che ogni calcolo passi da Decimal (ROUND_HALF_UP) e che un importo mancante
resti mancante, non diventi uno zero.
"""
import asyncio
from decimal import Decimal

import pytest

from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services import scritture_contabili as motore
from app.services.scritture_contabili import (
    ScritturaNonValida,
    _cents,
    _decimale,
    _euro,
    _prepara_documento,
    _valida,
    raggruppa_accrediti_pos_per_giorno,
    registra_corrispettivo,
    valuta_evidenza,
)


def _run(awaitable):
    return asyncio.run(awaitable)


def _mov(**extra):
    base = {"data": "2026-05-31", "tipo": "entrata", "importo": "1.005",
            "categoria": "Corrispettivi", "source": "test"}
    base.update(extra)
    return base


# --- helper canonici --------------------------------------------------------

def test_decimale_arrotonda_half_up_e_non_eredita_il_rumore_float():
    assert _decimale(1.005) == Decimal("1.01")          # round(1.005, 2) == 1.0
    assert _decimale("1.005") == Decimal("1.01")
    assert _decimale(0.1 + 0.2) == Decimal("0.30")       # 0.30000000000000004
    assert _decimale(2.675) == Decimal("2.68")           # round(2.675, 2) == 2.67
    assert _cents(1.005) == 101
    assert _cents(0.1 + 0.2) == 30
    assert _cents("19.99") == 1999


def test_decimale_none_e_stringa_vuota_restano_mancanti():
    assert _decimale(None) is None
    assert _decimale("") is None
    assert _decimale("   ") is None
    assert _euro(None) is None
    # ``_cents`` mantiene il contratto storico dei confronti di gruppo.
    assert _cents(None) == 0


def test_decimale_rifiuta_il_non_numerico_come_valueerror():
    with pytest.raises(ScritturaNonValida):
        _decimale("abc")
    with pytest.raises(ValueError):  # compatibile con il vecchio float()
        _decimale("12,50")
    with pytest.raises(ScritturaNonValida):
        _decimale(True)


def test_euro_e_un_numero_a_due_decimali_per_il_documento():
    assert _euro(Decimal("1.005")) == 1.01
    assert _euro(Decimal("0.1") + Decimal("0.2")) == 0.3
    assert isinstance(_euro(Decimal("5")), float)


# --- validazione e documento -------------------------------------------------

def test_valida_rifiuta_importo_mancante_zero_e_negativo_in_decimal():
    for importo in (None, "", 0, "0.00", -0.01, "-5", 0.004):
        with pytest.raises(ScritturaNonValida, match="importo non positivo"):
            _valida(_mov(importo=importo))
    _valida(_mov(importo="0.01"))
    _valida(_mov(importo=0.005))  # half-up -> 0.01, positivo


def test_prepara_documento_persiste_il_centesimo_corretto():
    doc = _prepara_documento(_mov(importo=1.005))
    assert doc["importo"] == 1.01
    assert doc["amount"] == 1.01
    doc = _prepara_documento(_mov(importo=0.1 + 0.2))
    assert doc["importo"] == 0.3


# --- evidenze POS ----------------------------------------------------------------

def test_valuta_evidenza_confronta_in_decimal():
    precedente = {"importo": 0.1 + 0.2, "fonte_dato": "manuale",
                  "valori_per_fonte": {}}
    esito = valuta_evidenza(precedente, "0.30", "export_numia_storico")
    assert esito["stato_dato"] == motore.STATO_CONFERMATO
    assert esito["differenza"] == 0.0
    assert esito["valori_per_fonte"] == {"manuale": 0.3, "export_numia_storico": 0.3}

    esito = valuta_evidenza(precedente, "1.005", "export_numia_storico")
    assert esito["stato_dato"] == motore.STATO_DIFFERENZA
    assert esito["differenza"] == 0.71          # 1.01 - 0.30, non 0.7099999


def test_valuta_evidenza_rifiuta_importo_mancante():
    with pytest.raises(ScritturaNonValida):
        valuta_evidenza(None, None, "manuale")


def test_raggruppa_accrediti_somma_in_decimal_e_scarta_senza_importo():
    movs = [
        {"id": "a", "data": "2026-06-03", "importo": 0.1, "rapporto": "BPM",
         "descrizione_originale": "INC.POS CARTE CREDIT - NUMIA-INTER DEL 02/06/26 PDV 1"},
        {"id": "b", "data": "2026-06-03", "importo": 0.2, "rapporto": "BPM",
         "descrizione_originale": "INCAS. TRAMITE P.O.S - NUMIA-BNCMT DEL 02/06/26 PDV 2"},
        {"id": "c", "data": "2026-06-03", "importo": None, "rapporto": "BPM",
         "descrizione_originale": "INC.POS CARTE CREDIT - NUMIA-AMEX DEL 02/06/26 PDV 3"},
    ]
    gruppi = raggruppa_accrediti_pos_per_giorno(movs)
    assert gruppi["2026-06-02"]["totale"] == 0.3
    assert gruppi["2026-06-02"]["estratto_conto_ids"] == ["a", "b"]


# --- corrispettivo: dato mancante != zero -------------------------------------------

def _db():
    return ClientArchivioMemoria()["scritture_decimal_test"]


def test_corrispettivo_senza_imponibile_e_iva_non_inventa_zero():
    db = _db()
    esito = _run(registra_corrispettivo(db, {
        "id": "corr-1", "data": "2026-05-31", "matricola_rt": "RT1",
        "totale": "0.30", "pagato_contanti": 0.1 + 0.2, "pagato_elettronico": 0,
    }))
    riga = _run(db.prima_nota_cassa.find_one({"id": esito["prima_nota_cassa_id"]}))
    assert riga["importo"] == 0.3
    assert riga["contanti"] == 0.3
    assert riga["totale_corrispettivo"] == 0.3
    assert riga["imponibile"] is None, "imponibile assente non e' zero"
    assert riga["iva"] is None, "IVA assente non e' zero"


def test_corrispettivo_con_imponibile_e_iva_li_porta_al_centesimo():
    db = _db()
    esito = _run(registra_corrispettivo(db, {
        "id": "corr-2", "data": "2026-05-30", "matricola_rt": "RT1",
        "totale": 1.005, "pagato_contanti": 1.005,
        "totale_imponibile": "0.825", "totale_iva": 0.18,
    }))
    riga = _run(db.prima_nota_cassa.find_one({"id": esito["prima_nota_cassa_id"]}))
    assert riga["importo"] == 1.01
    assert riga["imponibile"] == 0.83
    assert riga["iva"] == 0.18


# --- libro giornale (registrazione_contabile) ------------------------------------

def test_riga_giornale_arrotonda_half_up_via_decimal():
    from app.services import registrazione_contabile as giornale

    r = giornale.riga(giornale._C_CASSA, dare=1.005)
    assert r["dare"] == 1.01 and r["avere"] == 0.0
    r = giornale.riga(giornale._C_CASSA, avere=0.1 + 0.2)
    assert r["avere"] == 0.3
    assert giornale.totali_righe([{"dare": 0.1}, {"dare": 0.2}, {"avere": "0.30"}]) == (0.3, 0.3)


def test_importo_dichiarato_distingue_mancante_da_zero():
    from app.services.registrazione_contabile import _importo_dichiarato, _primo_importo

    assert _importo_dichiarato({"a": None, "b": ""}, "a", "b") is None
    assert _importo_dichiarato({"a": 0}, "a") == Decimal("0.00")
    assert _importo_dichiarato({"a": "abc", "b": "1.005"}, "a", "b") == Decimal("1.01")
    # componenti di una ripartizione: assente = zero esplicito
    assert _primo_importo({}, "pagato_contanti") == Decimal("0.00")
