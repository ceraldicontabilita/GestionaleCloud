"""Vendite e accrediti SumUp sulla stessa riga: il collegamento e' il payout_id delle transazioni."""
from app.routers.prima_nota_module.banca import _collega_vendite_e_accrediti


def _g(data, netto):
    return {"data": data, "vendite": netto, "rimborsi": 0.0, "netto": netto, "transazioni": 2}


def test_ogni_giornata_porta_il_suo_accredito_e_la_differenza():
    giornate = [_g("2026-10-04", 2084.81), _g("2026-10-05", 2538.90)]
    transazioni = [
        {"data": "2026-10-04", "payout_id": "P1"}, {"data": "2026-10-04", "payout_id": "P1"},
        {"data": "2026-10-05", "payout_id": ""},          # SumUp non ha ancora assegnato il payout
    ]
    movimenti = [{"data": "2026-10-05", "importo": 2070.29, "payout_id": "P1"},
                 {"data": "2026-10-01", "importo": 999.0, "payout_id": "P0"}]
    giorni = [{"data": "2026-10-05", "payout_ids": ["P1"], "numero_payout": 1, "importo": 2070.29},
              {"data": "2026-10-01", "payout_ids": ["P0"], "numero_payout": 1, "importo": 999.0}]
    non_collegati = _collega_vendite_e_accrediti(giornate, transazioni, movimenti, giorni)
    quattro, cinque = giornate
    assert quattro["accredito_data"] == "2026-10-05" and quattro["ricevuto"] == 2070.29
    assert quattro["differenza"] == 14.52 and quattro["in_attesa"] is False
    assert cinque["in_attesa"] is True and cinque["ricevuto"] is None and cinque["differenza"] is None
    assert [g["data"] for g in non_collegati] == ["2026-10-01"]   # il payout P0 non richiama nessuna vendita


def test_un_payout_su_piu_giornate_non_si_divide():
    giornate = [_g("2026-10-03", 100.0), _g("2026-10-04", 200.0)]
    transazioni = [{"data": "2026-10-03", "payout_id": "P9"}, {"data": "2026-10-04", "payout_id": "P9"}]
    movimenti = [{"data": "2026-10-05", "importo": 295.0, "payout_id": "P9"}]
    _collega_vendite_e_accrediti(giornate, transazioni, movimenti, [])
    assert all(g["payout_condiviso"] and g["ricevuto"] is None and g["differenza"] is None for g in giornate)
