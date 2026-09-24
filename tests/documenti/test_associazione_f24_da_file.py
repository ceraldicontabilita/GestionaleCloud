"""GC-17: un PDF F24 letto da file va solo all'F24 del suo mese, anno e tributo."""
import asyncio

from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.email_full_download import _indizi_f24_da_nome, associate_f24_from_filesystem


def test_indizi_dal_nome():
    assert _indizi_f24_da_nome("F24_IVA_09_2025.pdf") == (9, 2025, "iva")
    assert _indizi_f24_da_nome("F24 giugno 2025 INPS.pdf") == (6, 2025, "contributi")
    assert _indizi_f24_da_nome("F24_IVA_11.25.pdf") == (11, 2025, "iva")
    assert _indizi_f24_da_nome("F24_2023_12.pdf") == (12, 2023, None)
    # solo l'anno: non basta per abbinare
    assert _indizi_f24_da_nome("F24_ravv_II_acc_Ires_2023.pdf") == (None, 2023, "imposte_reddito")


def _db(tmp_path, filename, f24s):
    f = tmp_path / filename
    f.write_bytes(b"%PDF-1.4 prova")
    db = ClientArchivioMemoria()["test"]

    async def seed():
        for d in f24s:
            await db["f24_unificato"].insert_one(dict(d))
        await db["documents_inbox"].insert_one({
            "id": "doc1", "category": "f24", "file_exists": True, "status": "nuovo",
            "filename": filename, "filepath": str(f),
        })
    asyncio.run(seed())
    return db


def _pdf(db, fid):
    return asyncio.run(db["f24_unificato"].find_one({"id": fid})).get("pdf_data")


def test_mese_in_lettere_e_tipo_scelgono_l_f24_giusto(tmp_path):
    db = _db(tmp_path, "F24 giugno 2025 IVA.pdf", [
        {"id": "inps", "mese": 6, "anno": 2025, "sezione_inps": [{"causale": "DM10"}]},
        {"id": "iva", "mese": 6, "anno": 2025, "sezione_erario": [{"codice_tributo": "6006"}]},
        {"id": "maggio", "mese": 5, "anno": 2025, "sezione_erario": [{"codice_tributo": "6005"}]},
    ])
    asyncio.run(associate_f24_from_filesystem(db))
    assert _pdf(db, "iva")
    assert _pdf(db, "inps") is None and _pdf(db, "maggio") is None


def test_solo_anno_non_associa_niente(tmp_path):
    db = _db(tmp_path, "F24_ravv_II_acc_Ires_2023.pdf", [
        {"id": "a", "mese": 3, "anno": 2023, "sezione_erario": [{"codice_tributo": "2001"}]},
    ])
    stats = asyncio.run(associate_f24_from_filesystem(db))
    assert _pdf(db, "a") is None
    assert stats["associated"] == 0


def test_due_candidati_restano_da_associare(tmp_path):
    db = _db(tmp_path, "F24_09_2025.pdf", [
        {"id": "a", "mese": 9, "anno": 2025},
        {"id": "b", "mese": 9, "anno": 2025},
    ])
    asyncio.run(associate_f24_from_filesystem(db))
    assert _pdf(db, "a") is None and _pdf(db, "b") is None
