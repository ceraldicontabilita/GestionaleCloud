"""P0.8 — Il parser F24 (`parse_f24_commercialista`) ha un contratto unico:
ritorna {"error": ...} in caso di errore, altrimenti il dict F24 direttamente
(dati_generali/sezione_erario/sezione_inps/totali). NON restituisce success/f24_data.
Dal 30/09/2026 (AV3-06) `documenti.py` non lo chiama piu' da solo: gli F24 in
`documents_inbox` passano da `importa_modello_bytes`, l'ingresso unico."""
from pathlib import Path


def test_processa_f24_scaricati_usa_contratto_reale():
    src = Path("app/routers/documenti.py").read_text(encoding="utf-8")
    assert 'parsed.get("success") and parsed.get("f24_data")' not in src
    assert 'parsed["f24_data"]' not in src


def test_parser_non_restituisce_success_ne_f24_data():
    src = Path("app/services/parser_f24.py").read_text(encoding="utf-8")
    assert '"dati_generali"' in src
    assert '"sezione_erario"' in src


def test_processa_f24_passa_dall_ingresso_unico():
    src = Path("app/routers/documenti.py").read_text(encoding="utf-8")
    inizio = src.index('@router.post("/sync-f24-automatico")')
    fine = src.index('@router.get("/ultimo-sync")')
    blocco = src[inizio:fine]
    assert "importa_modello_bytes(" in blocco
    assert "salva_f24(" not in blocco
    assert "parse_f24_commercialista" not in blocco
    # Il secondo downloader della INBOX non c'e' piu': la posta la legge solo
    # email_full_download, tutte le cartelle.
    assert "download_documents_from_email(" not in blocco
    assert '"processed_to": "f24_unificato"' in blocco
