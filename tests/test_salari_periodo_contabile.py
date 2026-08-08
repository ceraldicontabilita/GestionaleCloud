from datetime import date

from app.services.salari_periodo import (
    filtro_fuori_periodo_prima_nota,
    filtro_periodo_prima_nota,
    periodo_ammesso_in_prima_nota,
)


def test_solo_dicembre_2025_e_2026_fino_al_mese_corrente():
    oggi = date(2026, 8, 8)
    assert not periodo_ammesso_in_prima_nota(2025, 11, oggi=oggi)
    assert periodo_ammesso_in_prima_nota(2025, 12, oggi=oggi)
    assert periodo_ammesso_in_prima_nota(2026, 1, oggi=oggi)
    assert periodo_ammesso_in_prima_nota(2026, 8, oggi=oggi)
    assert not periodo_ammesso_in_prima_nota(2026, 9, oggi=oggi)
    assert not periodo_ammesso_in_prima_nota(None, None, oggi=oggi)


def test_filtri_mongo_sono_complementari():
    oggi = date(2026, 8, 8)
    ammessi = filtro_periodo_prima_nota(oggi=oggi)
    esclusi = filtro_fuori_periodo_prima_nota(oggi=oggi)
    assert ammessi["$or"][0] == {"anno": 2025, "mese": {"$gte": 12}}
    assert ammessi["$or"][-1] == {"anno": 2026, "mese": {"$lte": 8}}
    assert esclusi == {"$nor": [ammessi]}
