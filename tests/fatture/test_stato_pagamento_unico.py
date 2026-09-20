"""«È pagata?» ha una risposta sola, e il filtro deve filtrare davvero.

Il 20/09/2026, su 2.555 fatture in archivio:

- 639 (311.838,20 €) avevano `stato = "pagata"` e **nessun** campo `pagato`;
- il frontend chiedeva `fattura.pagato` e le mostrava **non pagate**;
- il backend cercava le aperte con `{"pagato": {"$ne": True}}`, che su un
  campo assente da 2.509 righe **passa sempre**: riconciliazione, cash flow e
  solleciti lavoravano anche sulle pagate.

Questi test difendono due cose diverse, e la seconda è quella che conta:
la lettura in Python (`e_pagata`) **e** il filtro di query, provato contro
`matches_filter`, cioè il motore vero che il runtime usa sui documenti. Un
filtro giusto in teoria e muto in produzione è esattamente il guasto da cui
veniamo.
"""
from __future__ import annotations

import pytest

from app.services.archivio_documenti_memoria import matches_filter
from app.services.stato_pagamento_fattura import (
    ANNULLATA,
    DA_PAGARE,
    DA_VERIFICARE,
    FILTRO_ANNULLATE,
    FILTRO_NON_PAGATE,
    FILTRO_PAGATE,
    PAGATA,
    PARZIALE,
    con_non_pagate,
    e_pagata,
    stato_pagamento,
)

# I cinque modi, tutti presenti in archivio, di dire che una fattura è pagata.
PAGATE_VERE = [
    pytest.param({"stato": "pagata"}, id="stato=pagata (639 righe)"),
    pytest.param({"stato_pagamento": "pagata"}, id="stato_pagamento=pagata (46)"),
    pytest.param({"stato_pagamento": "pagato"}, id="stato_pagamento=pagato (3)"),
    pytest.param({"pagato": True}, id="pagato=true (46)"),
    pytest.param({"paid": True}, id="paid=true (46)"),
    pytest.param({"payment_status": "paid"}, id="payment_status=paid (29)"),
]


# ── la lettura ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("fattura", PAGATE_VERE)
def test_ogni_modo_di_scrivere_pagata_vale(fattura):
    assert e_pagata(fattura) is True
    assert stato_pagamento(fattura) == PAGATA


def test_il_caso_da_311mila_euro():
    """639 fatture hanno solo `stato`: e' il caso che il frontend perdeva."""
    fattura = {"stato": "pagata", "total_amount": 488.01}
    assert "pagato" not in fattura          # com'e' davvero in archivio
    assert e_pagata(fattura) is True


def test_una_fattura_muta_non_e_pagata_ne_da_pagare():
    """Nessun campo dice niente: `da_verificare`, non un debito inventato."""
    fattura = {"invoice_number": "1/2026", "total_amount": 100}
    assert e_pagata(fattura) is False
    assert stato_pagamento(fattura) == DA_VERIFICARE


def test_da_pagare_resta_da_pagare():
    assert stato_pagamento({"stato": "da_pagare"}) == DA_PAGARE
    assert e_pagata({"stato": "da_pagare"}) is False


def test_parziale_non_e_pagata():
    fattura = {"stato": "parziale"}
    assert e_pagata(fattura) is False
    assert stato_pagamento(fattura) == PARZIALE


def test_annullata_batte_pagata():
    """Una stornata non e' pagata: non deve entrare nei totali incassati."""
    fattura = {"stato": "annullata", "pagato": True}
    assert e_pagata(fattura) is False
    assert stato_pagamento(fattura) == ANNULLATA


def test_basta_un_campo_solo():
    """Pretendere che tutti concordino perderebbe le 639."""
    assert e_pagata({"stato": "pagata", "stato_pagamento": "da_verificare"}) is True


def test_maiuscole_e_spazi_non_cambiano_la_risposta():
    assert e_pagata({"stato": "  PAGATA "}) is True


# ── il filtro, provato sul motore vero ────────────────────────────────────

@pytest.mark.parametrize("fattura", PAGATE_VERE)
def test_le_pagate_non_entrano_fra_le_aperte(fattura):
    assert matches_filter(fattura, FILTRO_NON_PAGATE) is False
    assert matches_filter(fattura, FILTRO_PAGATE) is True


def test_la_fattura_muta_entra_fra_le_aperte():
    aperta = {"invoice_number": "7/2026", "total_amount": 100}
    assert matches_filter(aperta, FILTRO_NON_PAGATE) is True
    assert matches_filter(aperta, FILTRO_PAGATE) is False


def test_il_vecchio_filtro_sbagliava_e_questo_no():
    """La prova del difetto: `pagato $ne True` lascia passare una pagata."""
    pagata_solo_su_stato = {"stato": "pagata"}
    assert matches_filter(pagata_solo_su_stato, {"pagato": {"$ne": True}}) is True
    assert matches_filter(pagata_solo_su_stato, FILTRO_NON_PAGATE) is False


def test_le_annullate_non_stanno_da_nessuna_delle_due_parti():
    annullata = {"stato": "annullata"}
    assert matches_filter(annullata, FILTRO_NON_PAGATE) is False
    assert matches_filter(annullata, FILTRO_PAGATE) is False
    assert matches_filter(annullata, FILTRO_ANNULLATE) is True


@pytest.mark.parametrize("marcatore", [
    pytest.param({"pagato": True}, id="pagato=true"),
    pytest.param({"paid": True}, id="paid=true"),
    pytest.param({"stato_pagamento": "pagata"}, id="stato_pagamento=pagata"),
    pytest.param({"payment_status": "paid"}, id="payment_status=paid"),
])
def test_una_stornata_che_porta_ancora_il_marcatore_di_pagata_resta_fuori(marcatore):
    """Il caso che i test non vedevano e il collaudo del 20/09/2026 ha trovato.

    `e_pagata` diceva già di no, ma `FILTRO_PAGATE` la contava fra le pagate:
    la funzione e la query non rispondevano la stessa cosa, e il conteggio
    degli incassi avrebbe preso dentro una fattura stornata. Il test vecchio
    provava l'annullata *senza* marcatore, cioè il caso facile.
    """
    stornata = {"stato": "annullata", **marcatore}
    assert e_pagata(stornata) is False
    assert matches_filter(stornata, FILTRO_PAGATE) is False, (
        "la query deve dire quello che dice la funzione"
    )
    assert matches_filter(stornata, FILTRO_NON_PAGATE) is False
    assert matches_filter(stornata, FILTRO_ANNULLATE) is True


def test_la_funzione_e_il_filtro_dicono_sempre_la_stessa_cosa():
    """La cricchetta contro il ritorno dello scarto: provati insieme, non a parte."""
    casi = [
        {}, {"stato": "pagata"}, {"stato": "da_pagare"}, {"stato": "parziale"},
        {"pagato": True}, {"paid": True}, {"payment_status": "paid"},
        {"stato_pagamento": "pagata"}, {"stato_pagamento": "da_verificare"},
        {"stato": "annullata"}, {"stato": "annullata", "pagato": True},
        {"stato": "stornata", "stato_pagamento": "pagata"},
        {"status": "archiviata"}, {"stato_finanziario": "riconciliato"},
    ]
    for f in casi:
        assert matches_filter(f, FILTRO_PAGATE) == e_pagata(f), f
        # aperta = né pagata né annullata
        atteso_aperta = not e_pagata(f) and not matches_filter(f, FILTRO_ANNULLATE)
        assert matches_filter(f, FILTRO_NON_PAGATE) == atteso_aperta, f


def test_con_non_pagate_non_perde_i_criteri_di_partenza():
    filtro = con_non_pagate({"fornitore_id": "F1"})
    assert matches_filter({"fornitore_id": "F1"}, filtro) is True
    assert matches_filter({"fornitore_id": "F2"}, filtro) is False
    assert matches_filter({"fornitore_id": "F1", "stato": "pagata"}, filtro) is False


def test_con_non_pagate_senza_criteri_resta_il_filtro_nudo():
    assert con_non_pagate() == FILTRO_NON_PAGATE
    assert con_non_pagate({}) == FILTRO_NON_PAGATE


def test_due_nor_non_si_sovrascrivono():
    """Il motivo per cui `con_non_pagate` esiste invece di un dict fuso."""
    fuso = {**{"$nor": [{"x": 1}]}, **FILTRO_NON_PAGATE}
    assert len(fuso["$nor"]) == len(FILTRO_NON_PAGATE["$nor"])  # il primo e' sparito
    tenuto = con_non_pagate({"$nor": [{"x": 1}]})
    assert matches_filter({"x": 1}, tenuto) is False            # il criterio regge
