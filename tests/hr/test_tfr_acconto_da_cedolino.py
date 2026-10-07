"""L'acconto gia' recuperato in busta si legge dal campo del motore unico.

`dati_chiave.acconto_recuperato_busta` e' la voce codificata che
`cedolini_motore` scrive su ogni busta (all'ingresso e nella rilettura
`batch_reprocessing`). Il campo `enhanced_parsing` del lettore AI ritirato il
07/10/2026 resta leggibile solo per i dati gia' in archivio.

Il lettore e' uno solo, in ``app/hr/routers/tfr.py``; il modulo ERP lo
re-esporta (stesso oggetto, non una copia da tenere allineata).
"""
from app.hr.routers import tfr as tfr_hr
from app.routers import tfr as tfr_erp

_estrai = tfr_hr._estrai_acconto_da_cedolino


def test_legge_prima_la_voce_del_motore_unico():
    ced = {"dati_chiave": {"acconto_recuperato_busta": 300.0},
           "enhanced_parsing": {"importi_finali": {"acconto_mese_precedente": 999.0}}}
    assert _estrai(ced) == 300.0


def test_i_dati_gia_scritti_dal_lettore_ritirato_restano_leggibili():
    ced = {"enhanced_parsing": {"importi_finali": {"acconto_mese_precedente": 150.5}}}
    assert _estrai(ced) == 150.5


def test_senza_acconto_il_dato_e_nullo_non_zero():
    assert _estrai({"dati_chiave": {}}) is None
    assert _estrai({"dati_chiave": {"acconto_recuperato_busta": 0}}) is None


def test_il_modulo_erp_non_ha_una_copia_del_lettore():
    assert tfr_erp._estrai_acconto_da_cedolino is tfr_hr._estrai_acconto_da_cedolino
    for nome in ("TFR_DIVISORE", "RIVALUTAZIONE_FISSA", "ALIQUOTA_TFR"):
        assert getattr(tfr_erp, nome) == getattr(tfr_hr, nome)


def test_il_modulo_erp_espone_solo_le_due_letture_del_fondo_gestionale():
    """Il motore TFR (accantonamento, liquidazione, acconti, scalatura, simulatore)
    vive solo in HR: il lato ERP non deve tornare a crescere come secondo writer."""
    assert sorted(r.path for r in tfr_erp.router.routes) == [
        "/riepilogo-aziendale", "/situazione/{dipendente_id}"]
    assert all(r.methods == {"GET"} for r in tfr_erp.router.routes)
