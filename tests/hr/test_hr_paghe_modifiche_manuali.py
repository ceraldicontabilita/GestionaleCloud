"""Titolare 14/09/2026, pagina HR Paghe e bonifici:
- spostare un pagamento al periodo giusto (bonifico 01/01/2026 -> dicembre
  2025) e/o correggerne l'importo;
- correggere l'importo della busta quando non torna col cedolino, senza che
  la sincronizzazione dai cedolini lo sovrascriva.
"""
import asyncio

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

from app.hr.routers import dipendenti_cloud as mod


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def hr(monkeypatch):
    from app.hr.database import Database as DatabaseHR

    db = AsyncMongoMockClient()["hr_test"]
    monkeypatch.setattr(DatabaseHR, "get_db", classmethod(lambda cls: db))
    _run(db.dipendenti.insert_one({"id": "dip-1", "nome_completo": "Vespa Vincenzo", "codice_fiscale": "VSPVCN67T26F839P"}))
    _run(db.paghe_mensili.insert_many([
        {"dipendente_id": "dip-1", "anno": 2025, "mese": 12, "importo_busta": 1300.0, "stato_pagamento": "in_attesa_pagamento"},
        {"dipendente_id": "dip-1", "anno": 2026, "mese": 1, "importo_busta": 1250.0, "bonifico_importo": 1300.0, "stato_pagamento": "pagato"},
    ]))
    _run(db.pagamenti_esiti.insert_one({"key": "ecm:m-1", "dipendente_id": "dip-1", "data": "2026-01-01",
                                        "importo": 1300.0, "mese": 1, "anno": 2026, "origine": "gestionale-estratto-conto"}))
    return db


def test_sposta_pagamento_a_dicembre_e_ricalcola_entrambi_i_mesi(hr):
    esito = _run(mod.modifica_pagamento_esito("ecm:m-1", {"mese": 12, "anno": 2025, "nota": "saldo di dicembre pagato il 1 gennaio"}))
    assert esito["ok"] and (esito["mese"], esito["anno"]) == (12, 2025)
    assert esito["stati"] == {"2025-12": "pagato", "2026-01": "in_attesa_pagamento"}
    e = _run(hr.pagamenti_esiti.find_one({"key": "ecm:m-1"}, {"_id": 0}))
    assert (e["mese"], e["anno"], e["importo"]) == (12, 2025, 1300.0)
    assert e["modificato_manualmente"] is True and e["modifiche_manuali"][0]["da_mese"] == 1
    dic = _run(hr.paghe_mensili.find_one({"dipendente_id": "dip-1", "anno": 2025, "mese": 12}))
    gen = _run(hr.paghe_mensili.find_one({"dipendente_id": "dip-1", "anno": 2026, "mese": 1}))
    assert dic["bonifico_importo"] == 1300.0 and dic["stato_pagamento"] == "pagato"
    assert gen["bonifico_importo"] == 0 and gen["stato_pagamento"] == "in_attesa_pagamento"


def test_corregge_solo_l_importo_del_pagamento(hr):
    esito = _run(mod.modifica_pagamento_esito("ecm:m-1", {"importo": "1250"}))
    assert esito["importo"] == 1250.0 and esito["stati"] == {"2026-01": "pagato"}
    with pytest.raises(HTTPException) as exc:
        _run(mod.modifica_pagamento_esito("ecm:m-1", {"importo": -5}))
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc:
        _run(mod.modifica_pagamento_esito("non-esiste", {"mese": 1}))
    assert exc.value.status_code == 404


def test_sposta_su_un_mese_senza_busta_crea_la_riga(hr):
    esito = _run(mod.modifica_pagamento_esito("ecm:m-1", {"mese": 11, "anno": 2025}))
    assert esito["stati"]["2025-11"] == "pagato"  # busta 0, erogato > 0: il motore unico dice pagato
    riga = _run(hr.paghe_mensili.find_one({"dipendente_id": "dip-1", "anno": 2025, "mese": 11}))
    assert riga["bonifico_importo"] == 1300.0 and riga["bonifico_da_esiti"] is True


def test_corregge_importo_busta_e_la_sincronizzazione_non_lo_sovrascrive(hr):
    esito = _run(mod.modifica_importo_busta({"dipendente_id": "dip-1", "anno": 2026, "mese": 1,
                                             "importo_busta": 1300, "nota": "netto del cedolino letto male"}))
    assert esito["ok"] and esito["importo_busta"] == 1300.0 and esito["importo_busta_originale"] == 1250.0
    assert esito["stato"] == "pagato"
    paga = _run(hr.paghe_mensili.find_one({"dipendente_id": "dip-1", "anno": 2026, "mese": 1}))
    assert paga["origine"] == "manuale" and paga["importo_busta_manuale"] is True
    assert paga["importo_busta_nota"] == "netto del cedolino letto male"

    # la sincronizzazione dai cedolini salta i mesi modificati a mano
    from app.hr.services.sincronizza_paghe_mensili import sincronizza

    _run(hr.cedolini.insert_one({"id": "ced-1", "dipendente_id": "dip-1", "anno": 2026, "mese": 1,
                                 "netto": 1250.0, "tipo_cedolino": "ordinario"}))
    ris = _run(sincronizza(hr, 2026))
    assert ris["saltati_manuali"] == 1
    assert _run(hr.paghe_mensili.find_one({"dipendente_id": "dip-1", "anno": 2026, "mese": 1}))["importo_busta"] == 1300.0

    # una seconda correzione conserva l'originale della prima volta
    _run(mod.modifica_importo_busta({"dipendente_id": "dip-1", "anno": 2026, "mese": 1, "importo_busta": 1310}))
    paga = _run(hr.paghe_mensili.find_one({"dipendente_id": "dip-1", "anno": 2026, "mese": 1}))
    assert paga["importo_busta"] == 1310.0 and paga["importo_busta_originale"] == 1250.0


def test_associazioni_espongono_chiave_e_flag_manuali(hr):
    _run(mod.modifica_importo_busta({"dipendente_id": "dip-1", "anno": 2026, "mese": 1, "importo_busta": 1300}))
    out = _run(mod._calcola_associazioni_bonifici(hr, 2026, 1))
    riga = out["righe"][0]
    assert riga["busta_manuale"] is True and riga["busta_originale"] == 1250.0
    assert riga["bonifici"][0]["key"] == "ecm:m-1" and riga["bonifici"][0]["modificato"] is False
