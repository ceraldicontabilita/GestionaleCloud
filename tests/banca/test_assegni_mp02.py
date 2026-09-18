"""MP02 (assegno) come prova documentale nel matching assegno-fattura.

MP02 e' lo strumento dichiarato nell'XML FatturaPA: e' cosa diversa dal
metodo di pagamento del fornitore, che indica la destinazione contabile
(cassa/banca). Qui verifichiamo che la prova venga usata davvero, senza
rendere il matcher meno prudente sulle ambiguita' reali.
"""
import pytest

from app.routers.bank.assegni_auto_match import _try_l1, _copre_una_rata_assegno
from app.services.assegni_fattura_intent import (
    fattura_dichiara_assegno,
    importi_assegno_dichiarati,
    rate_assegno_dichiarate,
)


def _fattura(fid="f1", residuo=1000.0, **extra):
    fattura = {
        "id": fid,
        "invoice_number": "1/2026",
        "supplier_vat": "06714021000",
        "total_amount": residuo,
        "_residuo": residuo,
    }
    fattura.update(extra)
    return fattura


def _assegno(importo=1000.0):
    return {"id": "a1", "numero": "0000001", "importo": importo}


# --- Riconoscimento dello strumento ---------------------------------------

def test_riconosce_mp02_dalla_lista_delle_fatture_canoniche():
    assert fattura_dichiara_assegno(_fattura(modalita_pagamento_xml=["MP02"])) is True


def test_riconosce_mp02_anche_quando_e_una_stringa_singola():
    """L'indice del report AE salva una stringa, non una lista."""
    assert fattura_dichiara_assegno({"modalita_pagamento_xml": "MP02"}) is True


def test_riconosce_mp02_dalle_rate():
    fattura = _fattura(pagamento_rate=[{"modalita": "mp02", "importo": 500}])
    assert fattura_dichiara_assegno(fattura) is True


def test_il_bonifico_non_viene_scambiato_per_assegno():
    assert fattura_dichiara_assegno(_fattura(modalita_pagamento_xml=["MP05"])) is False


def test_il_metodo_del_fornitore_non_e_la_prova_dello_strumento():
    """"banca" e' la destinazione contabile, non dice come si paga."""
    assert fattura_dichiara_assegno(_fattura(metodo_pagamento_previsto="banca")) is False
    assert fattura_dichiara_assegno(_fattura(metodo_pagamento_previsto="assegno")) is True


# --- Rate dichiarate: nessun fallback nel matching -------------------------

def test_le_rate_restituite_sono_solo_quelle_mp02():
    fattura = _fattura(pagamento_rate=[
        {"modalita": "MP02", "importo": 400},
        {"modalita": "MP05", "importo": 600},   # bonifico: non e' un assegno
        {"modalita": "MP02", "importo": 400},   # duplicata: una sola volta
    ])
    assert rate_assegno_dichiarate(fattura) == [400.0]


def test_senza_rate_mp02_il_matching_non_riceve_alcun_importo():
    """Il fallback al totale resta fuori dal matching: sovrapagherebbe."""
    fattura = _fattura(residuo=600.0, total_amount=1000.0)
    assert rate_assegno_dichiarate(fattura) == []
    assert importi_assegno_dichiarati(fattura) == [1000.0]  # fallback solo qui


def test_una_rata_piu_grande_del_residuo_non_e_capiente():
    fattura = _fattura(residuo=300.0, pagamento_rate=[{"modalita": "MP02", "importo": 1000}])
    assert _copre_una_rata_assegno(fattura, 1000.0) is False


def test_una_rata_dentro_il_residuo_e_capiente():
    fattura = _fattura(residuo=3000.0, pagamento_rate=[{"modalita": "MP02", "importo": 1000}])
    assert _copre_una_rata_assegno(fattura, 1000.0) is True


# --- Il collegamento reale nel matcher L1 ---------------------------------

def test_aggancia_un_assegno_che_paga_una_rata_mp02():
    """Prima restava non agganciato: il residuo non e' mai uguale alla rata."""
    fattura = _fattura(residuo=3000.0, pagamento_rate=[
        {"modalita": "MP02", "importo": 1000},
        {"modalita": "MP02", "importo": 1000},
        {"modalita": "MP02", "importo": 1000},
    ])
    status, candidate = _try_l1(_assegno(1000.0), [fattura])
    assert status == "ok"
    assert candidate[0]["id"] == "f1"


def test_non_aggancia_una_rata_che_sfonda_il_residuo():
    fattura = _fattura(residuo=300.0, pagamento_rate=[{"modalita": "MP02", "importo": 1000}])
    assert _try_l1(_assegno(1000.0), [fattura])[0] == "miss"


def test_mp02_scioglie_l_ambiguita_tra_due_fatture_distinte_di_pari_importo():
    con_prova = _fattura("con-mp02", invoice_number="7/2026",
                         modalita_pagamento_xml=["MP02"])
    senza_prova = _fattura("senza-mp02", invoice_number="8/2026",
                           modalita_pagamento_xml=["MP05"])

    status, candidate = _try_l1(_assegno(1000.0), [senza_prova, con_prova])

    assert status == "ok"
    assert candidate[0]["id"] == "con-mp02"


def test_due_fatture_che_dichiarano_entrambe_assegno_restano_ambigue():
    """Regola dell'utente: due candidate compatibili non si decidono da sole."""
    prima = _fattura("f1", invoice_number="7/2026", modalita_pagamento_xml=["MP02"])
    seconda = _fattura("f2", invoice_number="8/2026", modalita_pagamento_xml=["MP02"])

    status, candidate = _try_l1(_assegno(1000.0), [prima, seconda])

    assert status == "ambiguous"
    assert len(candidate) == 2


def test_senza_alcuna_prova_mp02_l_ambiguita_resta():
    prima = _fattura("f1", invoice_number="7/2026")
    seconda = _fattura("f2", invoice_number="8/2026")
    assert _try_l1(_assegno(1000.0), [prima, seconda])[0] == "ambiguous"


def test_due_copie_della_stessa_fattura_restano_un_duplicato_non_un_ambiguita():
    """Il dedup storico agisce prima di MP02: stesso numero = stesso documento."""
    prima = _fattura("copia-1", invoice_date="2026-01-10")
    seconda = _fattura("copia-2", invoice_date="2026-02-10")

    status, candidate = _try_l1(_assegno(1000.0), [seconda, prima])

    assert status == "ok"
    assert candidate[0]["id"] == "copia-1"  # la piu' vecchia


def test_il_match_secco_sul_residuo_continua_a_funzionare():
    """Nessuna regressione sul comportamento storico."""
    status, candidate = _try_l1(_assegno(1000.0), [_fattura(residuo=1000.0)])
    assert status == "ok"
    assert candidate[0]["id"] == "f1"


@pytest.mark.parametrize("importo", [999.99, 1000.01])
def test_uno_scarto_di_un_centesimo_non_produce_match(importo):
    assert _try_l1(_assegno(importo), [_fattura(residuo=1000.0)])[0] == "miss"
