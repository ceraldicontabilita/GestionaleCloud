"""Quadratura Dare=Avere in Decimal: esatta nel giornale, con la tolleranza di un
centesimo che finisce su una riga di arrotondamento (decisione del titolare
02/10/2026, n. 12); guardia admin sulle cancellazioni per sorgente di Prima Nota."""
from decimal import Decimal

import pytest

from app.services.registrazione_contabile import (
    DESCRIZIONE_ARROTONDAMENTO,
    ScritturaNonQuadrata,
    differenza_ammessa,
    quadra_righe,
    riga_arrotondamento,
    scrittura_quadrata,
    totali_righe,
)
from app.utils.dependencies import get_current_admin_user


def _righe(dare, avere):
    return [{"dare": d, "avere": 0} for d in dare] + [{"dare": 0, "avere": a} for a in avere]


def test_somma_decimale_senza_deriva_binaria():
    # 0.1 + 0.2 != 0.3 in float: in Decimal si quadra
    assert scrittura_quadrata(_righe([0.1, 0.2], [0.3]))
    assert totali_righe(_righe([0.1, 0.2], [0.3])) == (0.3, 0.3)


def test_un_centesimo_di_differenza_non_quadra_ma_e_ammesso():
    # Nel giornale la scrittura deve quadrare al centesimo esatto...
    assert not scrittura_quadrata(_righe([100.01], [100.00]))
    assert not scrittura_quadrata(_righe([100.02], [100.00]))
    assert not scrittura_quadrata([])
    # ...ma uno scarto di un centesimo si ammette: va sulla riga di arrotondamento.
    assert differenza_ammessa(Decimal("100.01"), Decimal("100.00"))
    assert not differenza_ammessa(Decimal("100.02"), Decimal("100.00"))


def test_riga_arrotondamento_segue_il_segno_dello_scarto():
    assert riga_arrotondamento(_righe([100.00], [100.00])) is None
    # DARE eccede: manca un AVERE, cioe' un provento (arrotondamento attivo).
    attiva = riga_arrotondamento(_righe([100.01], [100.00]))
    assert attiva["conto_codice"] == "53.01.29"
    assert (attiva["dare"], attiva["avere"]) == (0.0, 0.01)
    assert attiva["arrotondamento"] is True
    assert attiva["descrizione"] == DESCRIZIONE_ARROTONDAMENTO
    # AVERE eccede: manca un DARE, cioe' un onere (arrotondamento passivo).
    passiva = riga_arrotondamento(_righe([100.00], [100.01]))
    assert passiva["conto_codice"] == "71.03.17"
    assert (passiva["dare"], passiva["avere"]) == (0.01, 0.0)
    assert scrittura_quadrata(quadra_righe(_righe([100.01], [100.00])))
    assert len(quadra_righe(_righe([100.01], [100.00]))) == 3
    assert len(quadra_righe(_righe([100.00], [100.00]))) == 2
    with pytest.raises(ScritturaNonQuadrata):
        quadra_righe(_righe([100.02], [100.00]))


def test_importi_stringa_arrotondati_half_up():
    assert scrittura_quadrata([{"dare": "10.005", "avere": 0}, {"dare": 0, "avere": "10.01"}])


def test_delete_by_source_richiede_admin():
    from app.routers.prima_nota_module import router

    viste = {}
    for r in router.routes:
        if r.path.endswith("/delete-by-source/{source}"):
            viste[r.path] = [d.dependency for d in r.dependencies]
    assert len(viste) == 2
    for path, deps in viste.items():
        assert get_current_admin_user in deps, path
