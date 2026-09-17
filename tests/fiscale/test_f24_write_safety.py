import asyncio

import pytest
from app.services.sheets_document_store import MemorySheetsClient

from app.services.f24_canonico import richiedi_quadratura_f24, salva_f24


def test_writer_canonico_rifiuta_f24_non_quadrato_senza_scrivere():
    db = MemorySheetsClient()["f24-write-safety"]
    document = {
        "file_name": "non_quadrato.pdf",
        "validazione": {"saldo_quadrato": False, "differenza_saldo": 0.01},
        "dati_generali": {"codice_fiscale": "00000000000"},
        "totali": {"saldo_netto": 10.0},
    }

    with pytest.raises(ValueError, match="salvataggio bloccato"):
        asyncio.run(salva_f24(db, document, source="test"))

    assert asyncio.run(db["f24_unificato"].count_documents({})) == 0


def test_pdf_f24_privo_di_validazione_esplicita_non_supera_il_gate():
    with pytest.raises(ValueError, match="non quadrato o non validato"):
        richiedi_quadratura_f24({"totali": {"saldo_netto": 10.0}})


def test_upload_modello_non_contiene_piu_creazione_movimento_banca_sintetico():
    from pathlib import Path
    import app.routers.f24.f24_riconciliazione as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    assert 'scrivi_movimento(db, "banca", mov_f24)' not in source
    assert "non viene mai sintetizzato durante l'upload" in source


def test_endpoint_overwrite_delega_al_writer_canonico():
    from pathlib import Path
    import app.routers.f24.f24_public as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    overwrite = source[source.index("async def upload_f24_pdf_overwrite"):]
    assert "await salva_f24(" in overwrite
    assert "existing_id=f24_id if existing else None" in overwrite
    assert "db[F24_COLLECTION].insert_one" not in overwrite
