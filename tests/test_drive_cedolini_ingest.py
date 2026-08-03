"""
Test dell'ingest cedolini da Google Drive (funzioni pure, nessuna rete).

Verifica:
- classificazione dei nomi file (solo PDF)
- formato del documento inserito in documents_inbox: deve essere ESATTAMENTE
  quello che la pipeline cedolini esistente (processa_nuovi_documenti) si
  aspetta (category 'busta_paga', processed False, pdf_data base64, file_hash
  md5 usato per la dedup dei cedolini email)
- is_configured in funzione delle variabili d'ambiente
"""
import base64
import hashlib
import io
import zipfile

import pytest

from app.services import drive_cedolini_ingest as ing


# ── Classificazione nomi file ────────────────────────────────────────────────

def test_is_cedolino_filename_accetta_solo_pdf():
    assert ing.is_cedolino_filename("cedolino_giugno.pdf")
    assert ing.is_cedolino_filename("LUL_2026_06.PDF")
    assert not ing.is_cedolino_filename("fattura.xml")
    assert not ing.is_cedolino_filename("cedolino.pdf.p7m")
    assert not ing.is_cedolino_filename("")
    assert not ing.is_cedolino_filename("senza_estensione")


# ── Formato documento per documents_inbox ────────────────────────────────────

def test_build_inbox_doc_formato_pipeline_cedolini():
    content = b"%PDF-1.4 contenuto finto cedolino"
    doc = ing.build_inbox_doc(content, "cedolino_giugno.pdf")

    # Campi su cui lavora processa_nuovi_documenti (parser cedolini)
    assert doc["category"] == "busta_paga"
    assert doc["processed"] is False
    assert base64.b64decode(doc["pdf_data"]) == content

    # Dedup: stesso campo e stesso algoritmo dei cedolini email (md5)
    assert doc["file_hash"] == hashlib.md5(content).hexdigest()

    # Classificazione coerente con il routing dei cedolini email
    assert doc["tipo_documento"] == "cedolino"
    assert doc["categoria"] == "cedolino"
    assert doc["fonte"] == "drive_cedolini"
    assert doc["stato"] == "importato"
    assert doc["filename"] == "cedolino_giugno.pdf"
    assert doc["id"]  # uuid presente

    # Non deve passare dal routing mittenti email
    assert doc["xml_processed"] is True


def test_build_inbox_doc_hash_diverso_per_contenuti_diversi():
    d1 = ing.build_inbox_doc(b"cedolino A", "a.pdf")
    d2 = ing.build_inbox_doc(b"cedolino B", "b.pdf")
    assert d1["file_hash"] != d2["file_hash"]
    assert d1["id"] != d2["id"]


def test_zip_annidato_preserva_percorso_e_tutti_i_pdf():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("anno/a/cedolino.pdf", b"%PDF-primo")
        archive.writestr("anno/b/cedolino.pdf", b"%PDF-secondo")
        archive.writestr("note.txt", b"ignorato")

    estratti = list(ing.iter_pdf_members(buffer.getvalue()))

    assert [path for path, _ in estratti] == [
        "anno/a/cedolino.pdf",
        "anno/b/cedolino.pdf",
    ]
    assert [content for _, content in estratti] == [b"%PDF-primo", b"%PDF-secondo"]


def test_zip_rifiuta_path_insicuro():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("../cedolino.pdf", b"%PDF-dati")

    assert list(ing.iter_pdf_members(buffer.getvalue())) == []


def test_zip_rifiuta_falso_pdf_senza_importarlo():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("cedolino.pdf", b"non e un pdf")

    with pytest.raises(ValueError, match="contenuto non valido"):
        list(ing.iter_pdf_members(buffer.getvalue()))


def test_build_inbox_doc_conserva_provenienza_zip():
    doc = ing.build_inbox_doc(
        b"%PDF-dati",
        "cedolino.pdf",
        source_path="storico/2025/cedolino.pdf",
        source_container="Cedolini_riorganizzati.zip",
    )

    assert doc["source_path"] == "storico/2025/cedolino.pdf"
    assert doc["source_container"] == "Cedolini_riorganizzati.zip"


# ── Configurazione ───────────────────────────────────────────────────────────

def test_is_configured(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "GOOGLE_DRIVE_CEDOLINI_FOLDER_ID", None)
    monkeypatch.setattr(settings, "GOOGLE_DRIVE_SA_FILE", None)
    monkeypatch.setattr(settings, "GOOGLE_DRIVE_SA_JSON", None)
    assert ing.is_configured() is False

    # Solo cartella, senza credenziali: non configurato
    monkeypatch.setattr(settings, "GOOGLE_DRIVE_CEDOLINI_FOLDER_ID", "folder123")
    assert ing.is_configured() is False

    # Cartella + credenziali: configurato
    monkeypatch.setattr(settings, "GOOGLE_DRIVE_SA_JSON", '{"type": "service_account"}')
    assert ing.is_configured() is True


def test_scheduler_non_perde_import_cedolini_al_riavvio(monkeypatch):
    import app.scheduler as scheduler_mod

    class SchedulerFinto:
        def __init__(self):
            self.jobs = []

        def add_job(self, funzione, *args, **kwargs):
            self.jobs.append((funzione, args, kwargs))

        def start(self):
            pass

    scheduler = SchedulerFinto()
    monkeypatch.setattr(scheduler_mod, "scheduler", scheduler)
    scheduler_mod.start_scheduler()

    job = next(item for item in scheduler.jobs if item[2].get("id") == "drive_cedolini_ingest")
    assert job[2]["next_run_time"] is not None
    assert job[2]["misfire_grace_time"] == 300
    assert job[2]["coalesce"] is True
