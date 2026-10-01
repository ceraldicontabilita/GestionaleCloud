"""Quadratura Dare=Avere in Decimal, con la tolleranza di un centesimo; guardia admin sulle
cancellazioni per sorgente di Prima Nota."""
from app.services.registrazione_contabile import scrittura_quadrata, totali_righe
from app.utils.dependencies import get_current_admin_user


def _righe(dare, avere):
    return [{"dare": d, "avere": 0} for d in dare] + [{"dare": 0, "avere": a} for a in avere]


def test_somma_decimale_senza_deriva_binaria():
    # 0.1 + 0.2 != 0.3 in float: in Decimal si quadra
    assert scrittura_quadrata(_righe([0.1, 0.2], [0.3]))
    assert totali_righe(_righe([0.1, 0.2], [0.3])) == (0.3, 0.3)


def test_oltre_un_centesimo_di_differenza_non_quadra():
    assert scrittura_quadrata(_righe([100.01], [100.00]))
    assert not scrittura_quadrata(_righe([100.02], [100.00]))
    assert not scrittura_quadrata([])


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
