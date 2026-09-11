"""
Handler Eventi Documenti/Inbox — Gestionale Ceraldi Group
===========================================================
- Classificazione prudente e instradamento
- Deduplica su hash
- Copia non distruttiva degli upload manuali nella stessa cartella Drive usata
  da Gmail e dall'ingest diretto
- Alert e audit trail
"""
import asyncio
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


async def on_documento_acquisito(event: Dict[str, Any], db) -> Optional[Dict]:
    """Classifica un documento acquisito e ne garantisce l'archivio Drive."""
    from app.services.alert_engine import genera_alert
    from app.services.audit_logger import log_evento
    from app.services.document_destination_registry import (
        destination_for_document_type,
        normalize_document_type,
    )

    doc_id = event.get("documento_id", "")
    filename = event.get("filename", "")
    origine = event.get("origine", "")
    mime_type = event.get("mime_type", "")
    hash_file = event.get("hash_file", "")
    mittente = event.get("mittente", "")

    if not doc_id:
        return None

    doc = await db["documents_inbox"].find_one({"id": doc_id}, {"_id": 0}) or {}
    filename = filename or doc.get("filename", "")
    mittente = mittente or doc.get("email_from", "")
    origine = origine or doc.get("source") or doc.get("fonte") or ""
    mime_type = mime_type or doc.get("mime_type") or ""
    digest = doc.get("sha256") or doc.get("file_hash") or doc.get("hash_file") or hash_file

    risultati = []

    # --- DEDUPLICA su hash (supporta i nomi campo storici) ---
    if digest:
        existing = await db["documents_inbox"].find_one(
            {
                "id": {"$ne": doc_id},
                "$or": [
                    {"sha256": digest},
                    {"file_hash": digest},
                    {"hash_file": digest},
                ],
            },
            {"_id": 0, "id": 1},
        )
        if existing:
            await genera_alert(
                "DOC_DUPLICATO", doc_id, "documents_inbox",
                f"Documento '{filename}' già presente (hash identico a {existing['id']})",
                db,
            )
            risultati.append("duplicato")

    # Una classificazione gia' prodotta dalla pipeline fiscale/documentale
    # prevale se corrisponde a un tipo con destinazione canonica.
    hinted_type = (
        event.get("tipo_documento")
        or event.get("category")
        or doc.get("tipo_documento")
        or doc.get("category")
        or doc.get("categoria")
        or ""
    )
    hinted_normalized = normalize_document_type(hinted_type)
    if destination_for_document_type(hinted_normalized):
        tipo = hinted_normalized
    else:
        tipo = _classifica_documento(filename, mime_type, mittente)

    modulo_target = _modulo_target(tipo)
    if modulo_target == "non_associato":
        await genera_alert(
            "DOC_NON_CLASSIFICATO", doc_id, "documents_inbox",
            f"Documento '{filename}' non classificabile automaticamente (origine: {origine})",
            db, extra={"filename": filename, "mime_type": mime_type, "mittente": mittente},
        )
        risultati.append("non_classificato")
    else:
        risultati.append(f"classificato_{tipo}")

    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    await db["documents_inbox"].update_one(
        {"id": doc_id},
        {"$set": {
            "tipo_documento": tipo,
            "modulo_target": modulo_target,
            "stato_elaborazione": "classificato" if modulo_target != "non_associato" else "da_verificare",
            "classificato_at": now,
        }},
    )

    # --- ARCHIVIO DRIVE UNICO ---
    # I documenti provenienti da Drive sono gia' nell'archivio canonico e non
    # vanno ricopiati. Gmail usa lo stesso archive_document_copy nel suo flusso;
    # qui copriamo in particolare Import Documenti/upload e reprocessing.
    source_lower = str(origine or "").lower()
    drive_result = None
    if not source_lower.startswith("drive") and destination_for_document_type(tipo):
        try:
            from app.services.email_drive_archive import archive_document_copy
            fresh_doc = await db["documents_inbox"].find_one({"id": doc_id}, {"_id": 0}) or doc
            drive_result = await asyncio.to_thread(archive_document_copy, fresh_doc, tipo)
            await db["documents_inbox"].update_one(
                {"id": doc_id},
                {"$set": {
                    "drive_archive_status": drive_result.get("status"),
                    "drive_archive_area": drive_result.get("area"),
                    "drive_archive_file_id": drive_result.get("drive_file_id"),
                    "drive_archive_url": drive_result.get("drive_url"),
                    "drive_archived_at": drive_result.get("archived_at"),
                    "drive_archive_sha256": drive_result.get("sha256"),
                }},
            )
            risultati.append(f"drive_{drive_result.get('status')}")
        except Exception as exc:
            logger.exception("Archivio Drive fallito per documento %s", doc_id)
            await db["documents_inbox"].update_one(
                {"id": doc_id},
                {"$set": {
                    "drive_archive_status": "error",
                    "drive_archive_error": str(exc)[:1000],
                }},
            )
            risultati.append("drive_error")

    await log_evento(
        modulo="documenti", azione="acquisito", entita_id=doc_id,
        entita_collection="documents_inbox", db=db,
        nuovo_stato={
            "tipo": tipo,
            "modulo_target": modulo_target,
            "filename": filename,
            "drive_archive_status": (drive_result or {}).get("status"),
        },
        fonte=origine,
        dettaglio=f"'{filename}' da {origine} → {modulo_target}",
    )

    return {
        "action": "documento_classificato",
        "tipo": tipo,
        "modulo": modulo_target,
        "drive_archive": drive_result,
        "risultati": risultati,
    }


async def on_documento_instradato(event: Dict[str, Any], db) -> Optional[Dict]:
    """Aggiorna lo stato quando il documento e' stato elaborato dal modulo target."""
    from app.services.alert_engine import risolvi_alert

    doc_id = event.get("documento_id", "")
    modulo = event.get("modulo_target", "")
    record_id = event.get("record_creato_id", "")
    successo = event.get("successo", True)

    if not doc_id:
        return None

    if successo:
        await db["documents_inbox"].update_one(
            {"id": doc_id},
            {"$set": {
                "stato_elaborazione": "elaborato",
                "record_target_id": record_id,
                "record_target_collection": modulo,
            }},
        )
        await risolvi_alert("DOC_NON_CLASSIFICATO", doc_id, db)
        await risolvi_alert("DOC_DUPLICATO", doc_id, db)
        await risolvi_alert("DOC_ENTITA_NON_TROVATA", doc_id, db)
    else:
        await db["documents_inbox"].update_one(
            {"id": doc_id}, {"$set": {"stato_elaborazione": "fallito"}}
        )
        from app.services.alert_engine import genera_alert
        await genera_alert(
            "DOC_PARSER_FALLITO", doc_id, "documents_inbox",
            f"Parser fallito per documento → modulo {modulo}", db,
        )

    return {"action": "instradamento_aggiornato", "successo": successo}


def _modulo_target(tipo: str) -> str:
    normalized = str(tipo or "").lower()
    if normalized in {"fattura", "fattura_xml", "fattura_estera_pdf"}:
        return "fatture"
    if normalized in {"f24", "quietanza", "quietanza_f24"}:
        return "f24"
    if normalized in {
        "cedolino", "busta_paga", "libro_unico", "riepilogo_paghe",
        "certificazione_unica", "contributi_inps", "inps", "inail",
    }:
        return "personale"
    if normalized in {"verbale", "verbale_auto", "pagopa", "ricevuta_pagopa", "partenopay"}:
        return "verbali"
    if normalized in {"cartella_esattoriale", "cartella_rateizzata", "rottamazione", "avviso_bonario", "dichiarazione_iva"}:
        return "fiscale"
    if normalized in {"estratto_conto", "bonifico"}:
        return "banca"
    if normalized in {"noleggio", "finanziamento", "mutuo", "avviso_pagamento_mutuo"}:
        return "noleggio"
    if normalized == "lul_presenze":
        return "presenze"
    return "non_associato"


# ============================================================
# CLASSIFICAZIONE
# ============================================================
def _classifica_documento(filename: str, mime_type: str, mittente: str) -> str:
    """Classifica usando segnali documentali; il mittente non forza il tipo."""
    fn = (filename or "").lower()
    mt = (mittente or "").lower()

    if fn.endswith(".xml") or fn.endswith(".p7m") or fn.endswith(".xml.p7m"):
        if "fatturapa" in mt or "pec.fatturapa.it" in mt or "fattura" in fn:
            return "fattura_xml"
        return "fattura_xml"

    if any(kw in fn for kw in ["quietanza", "ricevuta_f24", "ricevuta f24", "pagamento_f24"]):
        return "quietanza"
    if "f24" in fn or "f-24" in fn or "modello f24" in fn:
        return "f24"

    if any(kw in fn for kw in ["avviso_bonario", "avviso bonario", "comunicazione_irregolar"]):
        return "avviso_bonario"
    if any(kw in fn for kw in ["cartella_esattoriale", "cartella esattoriale", "rottamazione", "rateizzazione"]):
        if "rottam" in fn:
            return "rottamazione"
        if "rateizz" in fn:
            return "cartella_rateizzata"
        return "cartella_esattoriale"

    if any(kw in fn for kw in ["cedolino", "busta_paga", "busta paga", "cedolini"]):
        return "cedolino"
    if any(kw in fn for kw in ["lul", "libro_unico", "libro unico"]):
        return "libro_unico"
    if "riepilogo" in fn and "paghe" in fn:
        return "riepilogo_paghe"
    if any(kw in fn for kw in ["certificazione_unica", "certificazione unica", "cud", "cu_"]):
        return "certificazione_unica"

    if any(kw in fn for kw in ["ricevuta_pagopa", "ricevuta pagopa", "avvisodigitale", "pagopa"]):
        return "ricevuta_pagopa"
    if any(kw in fn for kw in ["verbale", "multa", "sanzione", "contravvenzione"]):
        return "verbale"

    if any(kw in fn for kw in ["estratto_conto", "estratto conto", "statement"]):
        return "estratto_conto"
    if any(kw in fn for kw in ["bonifico", "sepa", "disposizione"]):
        return "bonifico"

    if any(kw in fn for kw in ["mutuo", "finanziamento", "piano_ammortamento", "piano ammortamento"]):
        return "mutuo"

    # Niente piu' "Rosaria/Ferrantini => cedolino". Il mittente limita cio' che
    # e' ammesso, ma non trasforma un PDF generico in un documento contabile.
    if fn.endswith(".pdf"):
        return "pdf_generico"
    return "non_riconosciuto"
