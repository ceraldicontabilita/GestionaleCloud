"""La pagina TFR di HR vede le quote maturate dalle buste, che scrive il gestionale.

``app/handlers/tfr.handler_aggiorna_tfr`` registra una riga per cedolino in
``tfr_accantonamenti`` **del gestionale** (dipendente del gestionale, anno, mese,
``quota``). ``GET /hr/api/tfr/situazione/{id}`` deve mostrarle accanto al valore
HR come «quota da buste», senza sommarle al valore manuale: se la scheda ha il
manuale vince quello (``tfr_fonte=manuale``), altrimenti la somma delle quote
(``buste``); senza nessuno dei due ``None`` e ``nessuna``, mai zero.
"""
from tests.hr.scenari_base import mondo, run  # noqa: F401  (fixture)

CF_ROSSI = "RSSMRA80A01F839X"


def _quote_gestionale(m, dip_gest="g-d1", cf=CF_ROSSI, quote=(137.0, 137.0, 137.0)):
    run(m.gest.dipendenti.insert_one({"id": dip_gest, "codice_fiscale": cf, "nome_completo": "Rossi Mario"}))
    for i, q in enumerate(quote, start=5):
        run(m.gest.tfr_accantonamenti.insert_one({
            "id": f"acc-{i}", "dipendente_id": dip_gest, "anno": 2026, "mese": i, "quota": q,
            "lordo_base": q * 13.5, "source": "cedolino_auto"}))


def _situazione(m, dip="d-rossi"):
    r = m.client.get(f"/api/tfr/situazione/{dip}")
    assert r.status_code == 200, r.text
    return r.json()


def test_solo_buste_la_fonte_e_buste_e_il_totale_e_la_somma_delle_quote(mondo):
    m = mondo
    m.dipendente("d-rossi", "Mario", "Rossi", CF_ROSSI, tfr_accantonato=0.0)
    _quote_gestionale(m)
    run(m.gest.tfr_accantonamenti.insert_one(      # riga annuale senza mese: non e' una busta
        {"id": "acc-lul", "dipendente_id": "g-d1", "anno": 2025, "quota_annuale": 800.0}))

    s = _situazione(m)
    assert s["tfr_fonte"] == "buste" and s["tfr_accantonato"] == 411.0
    assert s["quota_da_buste"] == 411.0 and s["quota_da_buste_disponibile"] is True
    assert [a["periodo"] for a in s["accantonamenti_buste"]] == ["05/2026", "06/2026", "07/2026"]
    assert s["tfr_disponibile"] == 411.0 and s["tfr_manuale"] == 0.0


def test_il_manuale_vince_e_le_quote_si_mostrano_senza_sommarsi(mondo):
    m = mondo
    m.dipendente("d-rossi", "Mario", "Rossi", CF_ROSSI, tfr_accantonato=5000.0)
    _quote_gestionale(m)
    s = _situazione(m)
    assert s["tfr_fonte"] == "manuale" and s["tfr_accantonato"] == 5000.0
    assert s["quota_da_buste"] == 411.0                      # visibile accanto, non sommata


def test_senza_niente_il_dato_non_e_disponibile_mai_zero(mondo):
    m = mondo
    m.dipendente("d-rossi", "Mario", "Rossi", CF_ROSSI, tfr_accantonato=0.0)
    s = _situazione(m)
    assert s["tfr_fonte"] == "nessuna" and s["tfr_accantonato"] is None
    assert s["quota_da_buste"] is None and s["quota_da_buste_disponibile"] is True
    assert s["tfr_disponibile"] is None


def test_aggancio_per_codice_fiscale_non_per_nome(mondo):
    m = mondo
    m.dipendente("d-rossi", "Mario", "Rossi", CF_ROSSI, tfr_accantonato=0.0)
    _quote_gestionale(m, dip_gest="g-altro", cf="BNCLGU85B02F839Y")   # omonimo con altro CF
    assert _situazione(m)["quota_da_buste"] is None
    _quote_gestionale(m, dip_gest="g-rossi", quote=(100.0,))
    assert _situazione(m)["quota_da_buste"] == 100.0


def test_gestionale_non_raggiungibile_dichiara_il_motivo(mondo, monkeypatch):
    from app.hr.routers import tfr as router_tfr

    m = mondo
    m.dipendente("d-rossi", "Mario", "Rossi", CF_ROSSI, tfr_accantonato=0.0)

    def _giu():
        raise RuntimeError("supabase giu'")

    monkeypatch.setattr(router_tfr, "_db_giornale", _giu)
    s = _situazione(m)
    assert s["quota_da_buste"] is None and s["quota_da_buste_disponibile"] is False
    assert s["quota_da_buste_motivo"] and s["tfr_accantonato"] is None
