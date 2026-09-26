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
import asyncio
import threading
import zipfile

import pytest

from app.services import drive_cedolini_ingest as ing


def test_sync_drive_cedolini_non_blocca_event_loop(monkeypatch):
    """La scansione sincrona di Drive deve restare fuori dal loop FastAPI."""
    event_loop_thread = None
    worker_threads = []

    class Service:
        def close(self):
            worker_threads.append(threading.get_ident())

    service = Service()

    def fuori_event_loop(result):
        def _call(*_args, **_kwargs):
            worker_threads.append(threading.get_ident())
            return result
        return _call

    class Collection:
        async def find_one(self, *_args, **_kwargs):
            return None

        async def update_one(self, *_args, **_kwargs):
            return None

    class DB:
        def __getitem__(self, _name):
            return Collection()

    monkeypatch.setattr(ing, "is_configured", lambda: True)
    monkeypatch.setattr(ing, "_folder_id", lambda: "root")
    monkeypatch.setattr(ing, "_load_credentials_cedolini", fuori_event_loop((object(), None)))
    monkeypatch.setattr(ing, "_build_drive_service", fuori_event_loop(service))
    monkeypatch.setattr(ing, "_inbox_contexts", fuori_event_loop([{
        "inbox_id": "inbox",
        "lifecycle_parent_id": "parent",
        "relative_path": "DA ELABORARE",
    }]))
    monkeypatch.setattr(ing, "_list_source_files_recursive", fuori_event_loop([]))

    async def run():
        nonlocal event_loop_thread
        event_loop_thread = threading.get_ident()
        return await ing._do_sync(DB())

    result = asyncio.run(run())

    assert result["status"] == "ok"
    assert len(worker_threads) == 5
    assert all(thread_id != event_loop_thread for thread_id in worker_threads)


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


def test_build_inbox_doc_drive_salva_riferimento_non_payload():
    content = b"%PDF-originale-su-drive"
    doc = ing.build_inbox_doc(
        content,
        "cedolino.pdf",
        drive_file_id="drive-123",
        drive_parent_id="folder-456",
        persist_pdf=False,
    )

    assert doc["drive_file_id"] == "drive-123"
    assert doc["drive_parent_id"] == "folder-456"
    assert doc["file_hash"] == hashlib.md5(content).hexdigest()
    assert doc["size_bytes"] == len(content)
    assert "pdf_data" not in doc


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


def test_scheduler_tiene_solo_la_cartella_unica_fra_i_canali_drive(monkeypatch):
    """I canali Drive per sezione puntano a cartelle cancellate: resta la
    cartella unica, e i controlli che vivevano dentro quei giri (fonti ferme,
    cedolini bloccati) hanno un job proprio."""
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

    ids = {item[2].get("id") for item in scheduler.jobs}
    canali_smontati = {
        "drive_fatture_ingest", "drive_cedolini_ingest", "drive_corrispettivi_ingest",
        "drive_f24_ingest", "drive_quietanze_ingest", "drive_estratti_conto_ingest",
        "drive_documenti_ingest", "protocollo_drive", "drive_fatture_quadratura",
        "drive_fatture_ricostruzione_ripresa", "drive_cedolini_quadratura",
        "drive_corrispettivi_quadratura", "drive_quietanze_quadratura",
    }
    assert not ids & canali_smontati
    assert {"drive_cartella_unica", "fonti_ferme", "cedolini_bloccati"} <= ids
    unica = next(item[2] for item in scheduler.jobs if item[2].get("id") == "drive_cartella_unica")
    assert unica["next_run_time"] is not None and unica["coalesce"] is True


def test_scheduler_allinea_subito_i_badge_documentali(monkeypatch):
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

    job = next(
        item[2] for item in scheduler.jobs
        if item[2].get("id") == "allinea_status_documenti"
    )
    assert job["next_run_time"] is not None
    assert 0 <= (job["next_run_time"] - scheduler_mod.datetime.now()).total_seconds() <= 60
    assert job["misfire_grace_time"] == 300
    assert job["coalesce"] is True


# ── Pregresso della coda lavorato anche senza file nuovi (15/09/2026) ────────

def test_il_pregresso_in_coda_viene_lavorato_anche_senza_file_nuovi(monkeypatch):
    """3.130 buste ferme in documents_inbox dal 12/09: la pipeline partiva
    solo con imported > 0. Ora parte se la coda non e' vuota, a lotti."""
    import threading

    chiamate = []
    coda = {"n": 250}

    async def _processa(db):
        chiamate.append(1)
        lavorati = min(100, coda["n"])
        coda["n"] -= lavorati
        return {"buste_paga": lavorati, "errori": []}

    class Collection:
        async def find_one(self, *_a, **_k):
            return None

        async def update_one(self, *_a, **_k):
            return None

        async def count_documents(self, filtro):
            assert filtro["category"] == "busta_paga" and filtro["processed"] == {"$ne": True}
            return coda["n"]

    class DB:
        def __getitem__(self, _name):
            return Collection()

    def fuori_event_loop(valore):
        def _f(*_a, **_k):
            return valore
        return _f

    monkeypatch.setattr("app.services.email_monitor_service.processa_nuovi_documenti", _processa)
    monkeypatch.setattr(ing, "is_configured", lambda: True)
    monkeypatch.setattr(ing, "_folder_id", lambda: "root")
    monkeypatch.setattr(ing, "_load_credentials_cedolini", fuori_event_loop((object(), None)))
    monkeypatch.setattr(ing, "_build_drive_service", fuori_event_loop(object()))
    monkeypatch.setattr(ing, "_inbox_contexts", fuori_event_loop([{
        "inbox_id": "inbox", "lifecycle_parent_id": "parent", "relative_path": "DA ELABORARE"}]))
    monkeypatch.setattr(ing, "_list_source_files_recursive", fuori_event_loop([]))

    result = asyncio.run(ing._do_sync(DB()))

    assert result["imported"] == 0 and result["in_coda_prima"] == 250
    # 3 lotti utili + 1 lotto vuoto che conferma la coda svuotata
    assert result["cedolini_processati"] == 250 and len(chiamate) == 4
    assert result["in_coda_dopo"] == 0
