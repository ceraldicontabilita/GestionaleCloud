"""P0.7 — L'upload estratto BPM deve scrivere i movimenti F24 nella collezione
CANONICA `estratto_conto_movimenti` (quella letta dalla riconciliazione), non
nella morta `movimenti_f24_banca`."""
from pathlib import Path


def test_upload_scrive_su_collezione_canonica():
    src = Path("app/routers/bank/riconciliazione_f24_banca.py").read_text(encoding="utf-8")
    # non deve più inserire nella collezione morta
    assert 'db["movimenti_f24_banca"].insert_many' not in src
    # deve scrivere sulla canonica con dedup upsert
    assert "COLL_ESTRATTO_CONTO" in src
    assert "fingerprint" in src
    assert 'source": "estratto_bpm_f24"' in src


def test_riconciliazione_legge_la_stessa_collezione():
    src = Path("app/routers/bank/riconciliazione_f24_banca.py").read_text(encoding="utf-8")
    # la riconciliazione legge estratto_conto_movimenti via QUERY_F24_PATTERN
    assert "QUERY_F24_PATTERN" in src
    assert "db[COLL_ESTRATTO_CONTO].find(" in src


def test_dedup_per_chiave_naturale_non_per_fingerprint_diverso():
    """Il dedup deve avvenire per dati reali (data+importo+descrizione), non per un
    fingerprint con formula diversa da quella dell'importer canonico (review P0.7)."""
    src = Path("app/routers/bank/riconciliazione_f24_banca.py").read_text(encoding="utf-8")
    # niente più fingerprint locale divergente
    assert "hashlib.md5" not in src
    # dedup per chiave naturale con valore assoluto
    assert "$abs" in src and "importo_abs" in src
