"""Scenario funzionale: il pagamento F24 non e' mai un costo (CLAUDE.md, «Competenza e pagamento»).

Quietanza e addebito in banca chiudono un DEBITO (ritenute 1001, addizionali 3802, INPS quota lavoratore):
dopo import, riscontro CERTO e giro bancario il conto economico del Bilancio non deve cambiare.
"""
import pytest

from app.db_collections import COLL_ESTRATTO_CONTO
from app.routers.accounting import bilancio
from app.services import f24_canonico, quietanze_import as qi
from app.services import f24_controllo_incrociato as reg
from tests.fiscale.scenari_f24_comuni import causale_i24, collezione, db_nuovo, modello_parsed, quietanza_parsed, run
from tests.fiscale.test_scenari_funzionali_f24_banca import ambiente, _importa_estratto  # noqa: F401  (fixture)

RIGHE = [
    ("sezione_erario", "1001", "07/2026", "1450.00", "0"),     # ritenute lavoro dipendente
    ("sezione_regioni", "3802", "07/2026", "80.50", "0"),      # addizionale regionale trattenuta
    ("sezione_inps", "DM10", "07/2026", "2210.40", "0"),       # contributi INPS (anche quota lavoratore)
]
TOTALE = "3740.90"


def _semina_conto_economico(db):
    run(db["corrispettivi"].insert_many([
        {"id": "c1", "data": "2026-07-10", "totale": 1100.0, "totale_imponibile": 1000.0, "totale_iva": 100.0}]))
    run(db["invoices"].insert_many([
        {"id": "f1", "invoice_date": "2026-07-12", "tipo_documento": "TD01", "imponibile": 400.0, "iva": 88.0,
         "iva_detraibile": 88.0, "total_amount": 488.0}]))
    run(db["cedolini"].insert_many([{"id": "b1", "anno": 2026, "mese": 7, "lordo": 2500.0}]))


def _costi(db, monkeypatch):
    monkeypatch.setattr(bilancio.Database, "get_db", staticmethod(lambda: db))
    ce = run(bilancio.get_conto_economico(anno=2026, mese=None))
    return ce["costi"]["totale_costi"], ce["costi"]["acquisti"], ce["costi"]["personale"]


def test_quietanza_e_riconciliazione_f24_non_cambiano_i_costi_del_bilancio(ambiente):
    db, letti, mp = ambiente
    import app.routers.accounting.bilancio as modulo_bilancio

    _semina_conto_economico(db)
    prima = _costi(db, mp)
    assert prima[0] == 400.0 + 2500.0           # 400 di fatture + il lordo della busta, nessun F24

    letti[b"%PDF-modello"] = modello_parsed(RIGHE, "2026-08-20")
    assert run(f24_canonico.importa_modello_bytes(db, b"%PDF-modello", "F24 luglio.pdf", source="test"))["success"]
    letti[b"%PDF-quietanza"] = quietanza_parsed(RIGHE, "2026-08-20", "26081811065626134/000001")
    q = run(qi.importa_quietanza_bytes(db, b"%PDF-quietanza", "q.pdf", fonte="test"))
    assert q["success"] and len(q["f24_matchati"]) == 1
    # la quietanza non scrive mai in giornale: al massimo una proposta versionata, mai definitiva
    prop = q["journal_proposal"]
    assert prop["definitive_posting_created"] is False and prop["posting_allowed"] is False
    assert prop["income_statement_candidates"] == [] and prop["lines"] == []
    _importa_estratto(db, mp, [{"data": "2026-08-20", "importo": -3740.90, "descrizione": causale_i24("20/08/2026")}])

    # il pagamento e' provato in banca...
    [qz] = collezione(db, "quietanze_f24")
    assert qz["riscontro_banca"]["livello"] == reg.LIVELLO_CERTO and qz["riscontro_banca"]["importo"] == 3740.90
    [m] = collezione(db, COLL_ESTRATTO_CONTO)
    assert m["categoria"] == "F24" and m["riconciliato"] is True
    # ... ma il conto economico (costi e anche il Prima Nota a costo) non si e' mosso
    assert _costi(db, mp) == prima
    giornale = [r for r in collezione(db, "movimenti_contabili")]
    assert giornale == [], "un F24 pagato non genera mai una scrittura di costo"
    assert modulo_bilancio is not None


def test_la_proposta_di_un_codice_registrato_e_un_debito_mai_un_costo(ambiente):
    """1040 e' nel registro versionato: regolazione di un debito verso l'Erario, nessun conto economico."""
    db, letti, mp = ambiente
    righe = [("sezione_erario", "1040", "07/2026", "210.00", "0")]
    letti[b"%PDF-1040"] = quietanza_parsed(righe, "2026-08-20", "26081811065626134/000002")
    q = run(qi.importa_quietanza_bytes(db, b"%PDF-1040", "q1040.pdf", fonte="test"))
    [cand] = q["journal_proposal"]["bilancio_candidates"]
    assert cand["accounting_nature"] == "TAX_LIABILITY_SETTLEMENT"
    assert cand["conto_economico"] is None and cand["stato_patrimoniale"] == "PASSIVO_D12_DEBITI_TRIBUTARI"
    assert q["journal_proposal"]["deducibilita"][0]["ires"] == "NON_APPLICABILE_NON_E_UN_COSTO"
