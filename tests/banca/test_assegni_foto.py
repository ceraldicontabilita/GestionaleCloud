"""Foto dell'assegno: una sola per assegno, visibile anche dalla fattura pagata.

- rifiuta un file che non e' un'immagine e uno troppo grande;
- l'upload scrive i campi foto sull'assegno, lascia traccia nello storico e
  propaga lo stesso URL alle fatture collegate (nessuna seconda copia);
- la lettura serve i byte dallo storage solo se l'assegno ha quella foto_id.
"""
import asyncio
import io

import pytest
from starlette.datastructures import Headers, UploadFile

from app.routers.bank import assegni as assegni_router
from app.services import foto_assegni
from app.services.archivio_documenti_memoria import ClientArchivioMemoria


def _run(coroutine):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coroutine)
    finally:
        loop.close()


def _db(monkeypatch, nome):
    db = ClientArchivioMemoria()[nome]
    monkeypatch.setattr(assegni_router.Database, "get_db", staticmethod(lambda: db))
    return db


def _file(contenuto: bytes, mime: str, nome: str = "assegno.jpg") -> UploadFile:
    return UploadFile(
        filename=nome, file=io.BytesIO(contenuto), headers=Headers({"content-type": mime}),
    )


def test_upload_rifiuta_un_file_che_non_e_un_immagine(monkeypatch):
    db = _db(monkeypatch, "foto_rifiuto_mime")
    _run(db["assegni"].insert_one({"id": "a1", "numero": "0208770700", "stato": "compilato"}))

    with pytest.raises(Exception) as exc:
        _run(assegni_router.upload_foto_assegno("a1", _file(b"non un'immagine", "application/pdf")))
    assert getattr(exc.value, "status_code", None) == 400


def test_upload_rifiuta_un_immagine_troppo_grande(monkeypatch):
    db = _db(monkeypatch, "foto_rifiuto_size")
    _run(db["assegni"].insert_one({"id": "a1", "numero": "0208770700", "stato": "compilato"}))
    troppo_grande = b"x" * (15 * 1024 * 1024 + 1)

    with pytest.raises(Exception) as exc:
        _run(assegni_router.upload_foto_assegno("a1", _file(troppo_grande, "image/jpeg")))
    assert getattr(exc.value, "status_code", None) == 400


def test_upload_salva_la_foto_e_la_propaga_alle_fatture_collegate(monkeypatch):
    db = _db(monkeypatch, "foto_upload_ok")
    _run(db["assegni"].insert_one({
        "id": "a1", "numero": "0208770700", "stato": "compilato", "importo": 300.0,
        "fatture_collegate": [{"fattura_id": "f1", "quota": 300.0}],
    }))
    _run(db["invoices"].insert_one({"id": "f1", "invoice_number": "12/A", "total_amount": 300.0}))

    monkeypatch.setattr(foto_assegni, "carica", lambda **kw: {
        "id": "a1_deadbeef", "bucket": "menu-images", "path": "bank/assegni/a1_deadbeef.jpg",
        "sha256": "abc123", "filename": kw.get("filename"),
    })

    esito = _run(assegni_router.upload_foto_assegno("a1", _file(b"foto vera", "image/jpeg")))

    assert esito["success"] is True
    assert esito["foto_url"] == "/api/assegni/foto/a1_deadbeef?v=" + esito["foto_url"].rsplit("v=", 1)[1]
    assert esito["fatture_aggiornate"] == 1

    assegno = _run(db["assegni"].find_one({"id": "a1"}))
    assert assegno["foto_id"] == "a1_deadbeef"
    assert assegno["foto_storage_path"] == "bank/assegni/a1_deadbeef.jpg"
    assert assegno["foto_content_type"] == "image/jpeg"
    assert assegno["foto_sha256"] == "abc123"
    assert assegno["storico"][-1]["azione"] == "foto"

    fattura = _run(db["invoices"].find_one({"id": "f1"}))
    assert fattura["foto_assegno_id"] == "a1_deadbeef"
    assert fattura["foto_assegno_url"] == assegno["foto_url"]
    assert fattura["foto_assegno_numero"] == "0208770700"


def test_leggi_foto_404_se_nessun_assegno_ha_quella_foto_id(monkeypatch):
    _db(monkeypatch, "foto_leggi_404")

    with pytest.raises(Exception) as exc:
        _run(assegni_router.leggi_foto_assegno("non-esiste"))
    assert getattr(exc.value, "status_code", None) == 404


def test_leggi_foto_serve_i_byte_dallo_storage(monkeypatch):
    db = _db(monkeypatch, "foto_leggi_ok")
    _run(db["assegni"].insert_one({
        "id": "a1", "numero": "0208770700", "foto_id": "a1_deadbeef",
        "foto_storage_path": "bank/assegni/a1_deadbeef.jpg", "foto_content_type": "image/jpeg",
    }))
    monkeypatch.setattr(foto_assegni, "leggi", lambda percorso: b"contenuto immagine")

    risposta = _run(assegni_router.leggi_foto_assegno("a1_deadbeef"))

    assert risposta.body == b"contenuto immagine"
    assert risposta.media_type == "image/jpeg"
    assert risposta.headers["cache-control"] == "public, max-age=31536000, immutable"
