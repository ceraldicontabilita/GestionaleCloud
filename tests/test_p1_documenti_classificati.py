"""P1 §5.8 — Documenti classificati unificati sulla canonica UNICA
`documenti_classificati` (scelta utente). Il pipeline email non deve più scrivere
sull'alias legacy `documents_classified`; i doc email scritti portano i campi canonici
della Learning Machine; la migrazione mappa lo schema legacy su quello canonico."""
import pathlib

APP = pathlib.Path(__file__).resolve().parent.parent / "app"


def test_nessun_accesso_db_a_documents_classified():
    offenders = []
    for p in APP.rglob("*.py"):
        if p.name == "migra_documents_classified.py":
            continue  # la migrazione LEGGE legittimamente la legacy
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if 'db["documents_classified"]' in line or "db['documents_classified']" in line:
                offenders.append(f"{p.relative_to(APP)}:{i}")
    assert offenders == [], f"accessi residui alla legacy documents_classified: {offenders}"


def test_costante_alias_punta_a_canonica():
    from app.db_collections import COLL_DOCUMENTS_CLASSIFIED, COLL_DOCUMENTI_CLASSIFICATI
    assert COLL_DOCUMENTI_CLASSIFICATI == "documenti_classificati"
    assert COLL_DOCUMENTS_CLASSIFIED == "documenti_classificati"


def test_pipeline_email_scrive_campi_canonici():
    """Il doc email inserito deve portare i campi attesi dalla Learning Machine."""
    src = (APP / "services" / "email_classifier_service.py").read_text(encoding="utf-8")
    assert 'db["documenti_classificati"].insert_one' in src
    for campo in ('"categoria"', '"has_pdf"', '"processato"', '"_key"', '"fonte"'):
        assert campo in src, f"manca il campo canonico {campo} nel doc email"


def test_migrazione_mappa_schema():
    from app.scripts.migra_documents_classified import _mappa
    legacy = {
        "_id": "x", "tipo": "cedolino", "filename": "c.pdf", "subject": "Busta",
        "sender": "hr@x.it", "data_email": "2026-03-01", "pdf_base64": "AAA",
        "processed": True, "data_inserimento": "2026-03-01T00:00:00",
    }
    m = _mappa(legacy)
    assert "_id" not in m
    assert m["categoria"] == "cedolino"
    assert m["from"] == "hr@x.it"
    assert m["date"] == "2026-03-01"
    assert m["has_pdf"] is True
    assert m["processato"] is True
    assert m["fonte"] == "email_classifier"
    assert m["_key"].startswith("email_")
