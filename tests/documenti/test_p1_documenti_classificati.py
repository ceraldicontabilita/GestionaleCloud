"""Documenti classificati: collezione UNICA `documenti_classificati`. Il pipeline email
non scrive su un secondo nome (`documents_classified`); i doc email scritti portano i
campi canonici della Learning Machine."""
import pathlib

APP = pathlib.Path(__file__).resolve().parents[2] / "app"


def test_nessun_accesso_db_a_documents_classified():
    offenders = []
    for p in APP.rglob("*.py"):
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if 'db["documents_classified"]' in line or "db['documents_classified']" in line:
                offenders.append(f"{p.relative_to(APP)}:{i}")
    assert offenders == [], f"accessi a una seconda collezione documents_classified: {offenders}"


def test_costante_canonica():
    from app.db_collections import COLL_DOCUMENTI_CLASSIFICATI
    assert COLL_DOCUMENTI_CLASSIFICATI == "documenti_classificati"


def test_pipeline_email_scrive_campi_canonici():
    """Il doc email inserito deve portare i campi attesi dalla Learning Machine."""
    src = (APP / "services" / "email_classifier_service.py").read_text(encoding="utf-8")
    assert 'db["documenti_classificati"].insert_one' in src
    for campo in ('"categoria"', '"has_pdf"', '"processato"', '"_key"', '"fonte"'):
        assert campo in src, f"manca il campo canonico {campo} nel doc email"
