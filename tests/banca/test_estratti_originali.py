"""L'originale di ogni estratto conto si conserva e si riscarica."""
import asyncio
import base64

from app.services import estratti_originali as eo
from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.blob_store import MemoryBlobStore


def _db():
    return ClientArchivioMemoria()["test_estratti_originali"]


def test_conserva_una_volta_sola_e_si_riscarica(monkeypatch):
    monkeypatch.setattr(eo, "_archivio", lambda: MemoryBlobStore())
    db = _db()
    csv = "Data contabile;Importo\n25/09/2026;-43,86\n".encode("utf-8")

    async def scenario():
        primo = await eo.conserva_originale(db, csv, "Elenco.csv", fonte="test")
        secondo = await eo.conserva_originale(db, csv, "Elenco (1).csv", fonte="test")
        righe = await db[eo.COLL].find({}, {"_id": 0}).to_list(10)
        return primo, secondo, righe, await eo.contenuto(db, primo)

    primo, secondo, righe, trovato = asyncio.run(scenario())
    assert primo == secondo and len(righe) == 1
    dati, nome, mime = trovato
    assert dati == csv and nome == "Elenco.csv" and mime == "text/csv"


def test_elenco_mostra_banca_e_nexi_il_piu_recente_prima(monkeypatch):
    monkeypatch.setattr(eo, "_archivio", lambda: MemoryBlobStore())
    db = _db()

    async def scenario():
        await eo.conserva_originale(db, b"a;b\n", "BPM.csv", fonte="test")
        await db["estratto_conto_nexi"].insert_one({
            "id": "nexi_statement:abc", "filename": "Estratto_Conto (8).pdf",
            "metadata": {"data_estratto_iso": "2025-12-31", "totale_addebito": 2758.32},
            "pdf_data": base64.b64encode(b"%PDF-1.4").decode(),
        })
        return await eo.elenco(db), await eo.contenuto(db, "nexi_statement:abc")

    voci, nexi = asyncio.run(scenario())
    assert [v["tipo"] for v in voci] == ["banca", "nexi"]
    assert nexi[0] == b"%PDF-1.4" and nexi[2] == "application/pdf"


def test_originale_mancante_da_none():
    assert asyncio.run(eo.contenuto(_db(), "inesistente")) is None
