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
