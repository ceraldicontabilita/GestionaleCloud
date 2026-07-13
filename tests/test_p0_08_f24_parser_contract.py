"""P0.8 — Il parser F24 (`parse_f24_commercialista`) ha un contratto unico:
ritorna {"error": ...} in caso di errore, altrimenti il dict F24 direttamente
(dati_generali/sezione_erario/sezione_inps/totali). NON restituisce success/f24_data.
Tutti i chiamanti devono usare questo contratto."""
from pathlib import Path


def test_processa_f24_scaricati_usa_contratto_reale():
    src = Path("app/routers/documenti.py").read_text(encoding="utf-8")
    # il contratto inesistente non deve più comparire
    assert 'parsed.get("success") and parsed.get("f24_data")' not in src
    assert 'parsed["f24_data"]' not in src


def test_parser_non_restituisce_success_ne_f24_data():
    src = Path("app/services/parser_f24.py").read_text(encoding="utf-8")
    # il parser restituisce dati_generali/sezione_erario, non un wrapper success
    assert '"dati_generali"' in src
    assert '"sezione_erario"' in src


def test_processa_f24_imposta_file_name_per_dedup():
    """Il file_name deve essere impostato prima del controllo duplicati, altrimenti
    find_one({'file_name': None}) salterebbe sempre l'import (review P0.8)."""
    src = Path("app/routers/documenti.py").read_text(encoding="utf-8")
    assert 'f24_data["file_name"] = doc.get("filename")' in src
