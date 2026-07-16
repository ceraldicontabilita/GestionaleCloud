"""Anno di importazione attivo — impostazione GLOBALE (richiesta utente
14/07/2026: "puoi mettere in qualche parte un selettore dove selezioni
l'anno che voglio importare?", un solo selettore condiviso, non uno per
canale).

Governa il filtro anno applicato SOLO ai canali di import automatico che
lo supportano oggi (Drive fatture, Drive corrispettivi): i documenti con
data nell'anno attivo entrano nel flusso contabile attivo (Prima Nota,
scadenzario, alert, magazzino); gli altri anni vengono archiviati per
sola consultazione. Non tocca l'upload manuale via UI, né AnnoContext.jsx
(che è solo un filtro di visualizzazione lato frontend, indipendente).

Persistito in `sistema_stato` (stessa collection già usata per lo stato
dei sync Drive) così sopravvive a riavvii/deploy — un parametro simile a
GOOGLE_DRIVE_FATTURE_FOLDER_ID ma che deve poter cambiare da UI senza
un redeploy.
"""
from datetime import datetime, timezone
from typing import Any, Dict

_CHIAVE = "config_import_anno_attivo"


async def get_anno_importazione_attivo(db) -> int:
    """Anno attivo per l'import automatico. Default: anno solare corrente
    se non è mai stato impostato esplicitamente."""
    doc = await db["sistema_stato"].find_one({"chiave": _CHIAVE}, {"_id": 0})
    if doc and isinstance(doc.get("anno"), int):
        return doc["anno"]
    return datetime.now(timezone.utc).year


async def set_anno_importazione_attivo(db, anno: int) -> Dict[str, Any]:
    if not isinstance(anno, int) or anno < 2000 or anno > 2100:
        raise ValueError("Anno non valido")
    now = datetime.now(timezone.utc).isoformat()
    await db["sistema_stato"].update_one(
        {"chiave": _CHIAVE},
        {"$set": {"anno": anno, "updated_at": now}},
        upsert=True,
    )
    return {"anno": anno, "updated_at": now}


async def promuovi_archivio_anno(db, anno: int) -> Dict[str, Any]:
    """Promuove nel flusso contabile ATTIVO i documenti dell'anno indicato
    già presenti in archivio storico (stato_import="archivio_storico").

    Serve al selettore anno (richiesta utente 16/07/2026): quando un file
    Drive di un anno diverso da quello attivo viene processato, finisce in
    archivio e il file viene spostato in Elaborate — rilanciare il sync
    dopo aver cambiato anno non lo ritroverebbe mai nella cartella. La
    promozione riprende quei documenti dall'archivio e li fa entrare nel
    flusso attivo come se fossero stati importati ora.
    """
    # ── Corrispettivi archiviati: entrano in Prima Nota col writer canonico
    # (entrata totale + uscita quota POS verso banca + entrata POS banca).
    from app.routers.invoices.corrispettivi_helpers import _create_prima_nota_movements

    corr_promossi = 0
    corr_gia_attivi = 0
    archivio_corr = await db["corrispettivi"].find(
        {"stato_import": "archivio_storico", "data": {"$regex": f"^{anno}"}},
        {"_id": 0},
    ).to_list(10000)
    for corr in archivio_corr:
        attivo = await db["corrispettivi"].find_one({
            "data": corr.get("data"),
            "stato_import": {"$ne": "archivio_storico"},
            "entity_status": {"$ne": "deleted"},
        })
        if attivo:
            corr_gia_attivi += 1
            continue
        pn = await _create_prima_nota_movements(db, corr)
        await db["corrispettivi"].update_one(
            {"id": corr["id"]},
            {"$set": {
                "status": "imported",
                "stato_import": "promosso_da_archivio",
                "prima_nota_id": pn.get("prima_nota_cassa_id"),
                "prima_nota_cassa_id": pn.get("prima_nota_cassa_id"),
                "prima_nota_banca_id": pn.get("prima_nota_banca_id"),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }},
        )
        corr_promossi += 1

    # ── Fatture archiviate: si ripassa l'XML originale (salvato all'atto
    # dell'archiviazione) nella pipeline di import completa — fornitore,
    # prima nota provvisoria, eventi. Il documento archiviato viene rimosso
    # PRIMA del reimport, altrimenti il dedup su invoice_key lo bloccherebbe.
    from app.routers.invoices.fatture_upload import process_xml_bytes

    fatture_promosse = 0
    fatture_senza_xml = 0
    fatture_errori = 0
    archivio_fatture = await db["invoices"].find(
        {"stato_import": "archivio_storico", "invoice_date": {"$regex": f"^{anno}"}},
        {"_id": 0},
    ).to_list(50000)
    for fatt in archivio_fatture:
        xml_raw = fatt.get("xml_raw")
        if not xml_raw:
            fatture_senza_xml += 1
            continue
        await db["invoices"].delete_one({"id": fatt["id"]})
        esito = await process_xml_bytes(
            db,
            xml_raw.encode("utf-8") if isinstance(xml_raw, str) else xml_raw,
            fatt.get("filename", ""),
            source="promozione_archivio",
            applica_filtro_anno=False,
        )
        if esito.get("status") in ("imported", "success", "duplicate") or esito.get("success"):
            fatture_promosse += 1
        else:
            fatture_errori += 1

    return {
        "anno": anno,
        "corrispettivi_promossi": corr_promossi,
        "corrispettivi_gia_attivi": corr_gia_attivi,
        "fatture_promosse": fatture_promosse,
        "fatture_senza_xml": fatture_senza_xml,
        "fatture_errori": fatture_errori,
    }


async def importa_anno_da_drive(db, anno: int) -> Dict[str, Any]:
    """Import "pulito per anno" (bottone Admin, richiesta utente 16/07/2026):

    1. imposta l'anno di importazione attivo;
    2. lancia il sync Drive fatture e Drive corrispettivi (i file di anni
       diversi finiscono in archivio storico, quelli dell'anno entrano);
    3. promuove nel flusso attivo i documenti dell'anno già in archivio
       (processati in passato quando era attivo un altro anno).
    """
    await set_anno_importazione_attivo(db, anno)

    from app.services import drive_invoice_ingest, drive_corrispettivi_ingest

    sync_fatture = None
    sync_corrispettivi = None
    if drive_invoice_ingest.is_configured():
        sync_fatture = await drive_invoice_ingest.sync(db)
    if drive_corrispettivi_ingest.is_configured():
        sync_corrispettivi = await drive_corrispettivi_ingest.sync(db)

    promozione = await promuovi_archivio_anno(db, anno)

    return {
        "anno": anno,
        "sync_fatture": sync_fatture or {"skipped": "Drive fatture non configurato"},
        "sync_corrispettivi": sync_corrispettivi or {"skipped": "Drive corrispettivi non configurato"},
        "promozione_archivio": promozione,
    }
