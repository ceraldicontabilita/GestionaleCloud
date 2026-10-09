"""Vendite SumUp copiate dal vecchio archivio: una vendita si conta una volta.

Ad agosto 2026 il vecchio archivio aveva copiato in ``sumup_transactions``
(righe ``LEGACY-SUMUP-…``, codice in ``id_trans``) le stesse vendite che poi
l'API ha riportato col loro ``transaction_code``. Contarle entrambe
raddoppiava il venduto, la chiusura POS del giorno e il credito verso SumUp.
"""
import asyncio

from app.services import sumup_sync
from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.scritture_contabili import FONTE_API, FONTE_MANUALE, registra_chiusura_pos_reale


def _run(awaitable):
    return asyncio.run(awaitable)


def _db():
    return ClientArchivioMemoria()["sumup_doppioni_test"]


def _api(codice, importo, data="2026-08-03"):
    return {"chiave": f"MFNRDMC4:{codice}", "transaction_code": codice, "tipo": "PAYMENT",
            "stato": "SUCCESSFUL", "data": data, "importo": importo, "payout_id": "P1"}


def _legacy(codice, importo, data="2026-08-03"):
    return {"id": f"LEGACY-{codice}", "id_trans": codice, "tipo": "PAYMENT",
            "stato": "SUCCESSFUL", "data": data, "importo": importo,
            "fonte": "legacy_staging_2026"}


def test_la_copia_d_archivio_con_la_gemella_api_non_si_conta():
    db = _db()
    _run(db[sumup_sync.COLL_TRANSAZIONI].insert_many([
        _api("TA1", 10.0), _legacy("TA1", 10.0),
        # Senza gemella: e' l'unica prova di quella vendita, resta.
        _legacy("TA2", 5.0),
        # Gemella registrata il giorno dopo (fuso): si trova lo stesso.
        _legacy("TA3", 7.0), _api("TA3", 7.0, data="2026-08-04"),
    ]))
    righe = _run(sumup_sync.transazioni_del_periodo(db, "2026-08-03", "2026-08-03"))
    assert sorted(r.get("transaction_code") or r.get("id_trans") for r in righe) == ["TA1", "TA2"]
    assert sumup_sync.aggrega_per_giorno(righe)["2026-08-03"]["netto"] == 15.0


def test_il_riallineamento_corregge_la_chiusura_raddoppiata(monkeypatch):
    db = _db()
    _run(db[sumup_sync.COLL_TRANSAZIONI].insert_many([
        _api("TA1", 10.0), _legacy("TA1", 10.0), _api("TB1", 4.0, data="2026-08-05"),
    ]))
    _run(registra_chiusura_pos_reale(db, "2026-08-03", 20.0, gestore="sumup", fonte=FONTE_API))
    _run(registra_chiusura_pos_reale(db, "2026-08-05", 4.0, gestore="sumup", fonte=FONTE_API))
    ricollegati = []

    async def finto_payouts(db, dal, al, actor=None):
        ricollegati.append((dal, al))
        return {"success": True}

    monkeypatch.setattr(sumup_sync, "sincronizza_payouts", finto_payouts)
    esito = _run(sumup_sync.riallinea_chiusure_da_archivio(db, "2026-08-01", "2026-08-31"))

    assert esito["corrette"] == [{"data": "2026-08-03", "era": 20.0, "ora": 10.0}]
    credito = _run(db["prima_nota_banca"].find_one(
        {"data": "2026-08-03", "source": "trasferimento_pos", "status": "active"}))
    assert credito["importo"] == 10.0
    # Il payout che copriva la giornata si ricollega subito.
    assert ricollegati == [("2026-08-03", "2026-08-10")]

    # Un secondo giro non trova piu' niente da correggere.
    assert _run(sumup_sync.riallinea_chiusure_da_archivio(db, "2026-08-01", "2026-08-31"))["corrette"] == []


def test_il_riallineamento_non_tocca_una_chiusura_scritta_a_mano():
    db = _db()
    _run(db[sumup_sync.COLL_TRANSAZIONI].insert_one(_api("TA1", 10.0)))
    _run(registra_chiusura_pos_reale(db, "2026-08-03", 12.0, gestore="sumup", fonte=FONTE_MANUALE))
    assert _run(sumup_sync.riallinea_chiusure_da_archivio(db, "2026-08-01", "2026-08-31"))["corrette"] == []


def test_risincronizzare_le_vendite_non_stacca_il_payout():
    """La cronologia API non riporta il payout: il collegamento resta."""
    db = _db()
    grezza = {"id": "tx-1", "transaction_code": "TA9", "amount": 10.0,
              "timestamp": "2026-09-10T10:00:00Z", "type": "PAYMENT",
              "status": "SUCCESSFUL", "currency": "EUR"}
    _run(sumup_sync.salva_transazioni(db, [grezza], "MFNRDMC4"))
    _run(db[sumup_sync.COLL_TRANSAZIONI].update_one(
        {"transaction_code": "TA9"}, {"$set": {"payout_id": "SUMUP PID9"}}))

    esito = _run(sumup_sync.salva_transazioni(db, [grezza], "MFNRDMC4"))
    riga = _run(db[sumup_sync.COLL_TRANSAZIONI].find_one({"transaction_code": "TA9"}))
    assert riga["payout_id"] == "SUMUP PID9"
    assert esito["invariate"] == 1

    # Un rimborso cambiato dall'API si aggiorna lo stesso, payout compreso.
    esito = _run(sumup_sync.salva_transazioni(db, [{**grezza, "refunded_amount": 2.0}], "MFNRDMC4"))
    riga = _run(db[sumup_sync.COLL_TRANSAZIONI].find_one({"transaction_code": "TA9"}))
    assert esito["aggiornate"] == 1 and riga["rimborsato"] == 2.0 and riga["payout_id"] == "SUMUP PID9"
