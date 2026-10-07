"""L'acconto gia' recuperato in busta si legge dal campo del motore unico.

`dati_chiave.acconto_recuperato_busta` e' la voce codificata che
`cedolini_motore` scrive su ogni busta (all'ingresso e nella rilettura
`batch_reprocessing`). Il campo `enhanced_parsing` del lettore AI ritirato il
07/10/2026 resta leggibile solo per i dati gia' in archivio.
"""
import pytest

from app.routers import tfr as tfr_erp
from app.hr.routers import tfr as tfr_hr


@pytest.mark.parametrize("modulo", [tfr_erp, tfr_hr])
def test_legge_prima_la_voce_del_motore_unico(modulo):
    ced = {"dati_chiave": {"acconto_recuperato_busta": 300.0},
           "enhanced_parsing": {"importi_finali": {"acconto_mese_precedente": 999.0}}}
    assert modulo._estrai_acconto_da_cedolino(ced) == 300.0


@pytest.mark.parametrize("modulo", [tfr_erp, tfr_hr])
def test_i_dati_gia_scritti_dal_lettore_ritirato_restano_leggibili(modulo):
    ced = {"enhanced_parsing": {"importi_finali": {"acconto_mese_precedente": 150.5}}}
    assert modulo._estrai_acconto_da_cedolino(ced) == 150.5


@pytest.mark.parametrize("modulo", [tfr_erp, tfr_hr])
def test_senza_acconto_il_dato_e_nullo_non_zero(modulo):
    assert modulo._estrai_acconto_da_cedolino({"dati_chiave": {}}) is None
    assert modulo._estrai_acconto_da_cedolino({"dati_chiave": {"acconto_recuperato_busta": 0}}) is None


def test_i_due_fork_leggono_allo_stesso_modo():
    import inspect

    assert inspect.getsource(tfr_erp._estrai_acconto_da_cedolino) == \
        inspect.getsource(tfr_hr._estrai_acconto_da_cedolino)
