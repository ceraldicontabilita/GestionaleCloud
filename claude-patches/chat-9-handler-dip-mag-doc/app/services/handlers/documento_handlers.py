"""
Handler Eventi Documenti/Inbox — Gestionale Ceraldi Group
===========================================================
Copre le specifiche di Documenti__Inbox.txt:
- Classificazione automatica documento (XML, PDF, tipo)
- Instradamento al modulo corretto
- Deduplica su hash file
- Alert parser fallito, non classificato, entità non trovata
- Reprocessing idempotente
- Audit trail di ogni documento acquisito
"""
import logging
import hashlib
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


async def on_documento_acquisito(event: Dict[str, Any], db) -> Optional[Dict]:
    """
    Quando un documento entra nel sistema (da PEC, Gmail o upload),
    classifica e instrada automaticamente.
    """
    from app.services.alert_engine import genera_alert
    from app.services.audit_logger import log_evento

    doc_id = event.get("documento_id", "")
    filename = event.get("filename", "")
    origine = event.get("origine", "")  # "pec", "gmail", "upload", "reprocessing"
    mime_type = event.get("mime_type", "")
    hash_file = event.get("hash_file", "")
    mittente = event.get("mittente", "")

    if not doc_id:
        return None

    risultati = []

    # --- DEDUPLICA su hash ---
    if hash_file:
        existing = await db["documents_inbox"].find_one(
            {"hash_file": hash_file, "id": {"$ne": doc_id}},
            {"_id": 0, "id": 1}
        )
        if existing:
            await genera_alert(
                "DOC_DUPLICATO", doc_id, "documents_inbox",
                f"Documento '{filename}' già presente (hash identico a {existing['id']})",
                db
            )
            risultati.append("duplicato")
            # Non blocchiamo, ma segnaliamo

    # --- CLASSIFICAZIONE ---
    tipo = _classifica_documento(filename, mime_type, mittente)

    if tipo == "fattura_xml":
        modulo_target = "fatture"
        risultati.append("classificato_fattura")
    elif tipo == "f24":
        modulo_target = "f24"
        risultati.append("classificato_f24")
    elif tipo == "cedolino":
        modulo_target = "cedolini"
        risultati.append("classificato_cedolino")
    elif tipo == "lul_presenze":
        modulo_target = "presenze"
        risultati.append("classificato_presenze")
    elif tipo == "verbale":
        modulo_target = "verbali"
        risultati.append("classificato_verbale")
    else:
        modulo_target = "non_associato"
        await genera_alert(
            "DOC_NON_CLASSIFICATO", doc_id, "documents_inbox",
            f"Documento '{filename}' non classificabile automaticamente (origine: {origine})",
            db, extra={"filename": filename, "mime_type": mime_type, "mittente": mittente}
        )
        risultati.append("non_classificato")

    # Aggiorna documento con classificazione
    await db["documents_inbox"].update_one(
        {"id": doc_id},
        {"$set": {
            "tipo_documento": tipo,
            "modulo_target": modulo_target,
            "stato_elaborazione": "classificato" if tipo != "non_riconosciuto" else "da_verificare",
            "classificato_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
        }}
    )

    # Audit
    await log_evento(
        modulo="documenti", azione="acquisito", entita_id=doc_id,
        entita_collection="documents_inbox", db=db,
        nuovo_stato={"tipo": tipo, "modulo_target": modulo_target, "filename": filename},
        fonte=origine,
        dettaglio=f"'{filename}' da {origine} → {modulo_target}"
    )

    return {"action": "documento_classificato", "tipo": tipo, "modulo": modulo_target, "risultati": risultati}


async def on_documento_instradato(event: Dict[str, Any], db) -> Optional[Dict]:
    """
    Quando il documento è stato elaborato dal modulo target,
    aggiorna lo stato e risolve alert.
    """
    from app.services.alert_engine import risolvi_alert

    doc_id = event.get("documento_id", "")
    modulo = event.get("modulo_target", "")
    record_id = event.get("record_creato_id", "")  # id fattura/cedolino/f24 creato
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
            }}
        )
        await risolvi_alert("DOC_NON_CLASSIFICATO", doc_id, db)
        await risolvi_alert("DOC_DUPLICATO", doc_id, db)
        await risolvi_alert("DOC_ENTITA_NON_TROVATA", doc_id, db)
    else:
        await db["documents_inbox"].update_one(
            {"id": doc_id},
            {"$set": {"stato_elaborazione": "fallito"}}
        )
        from app.services.alert_engine import genera_alert
        await genera_alert(
            "DOC_PARSER_FALLITO", doc_id, "documents_inbox",
            f"Parser fallito per documento → modulo {modulo}",
            db
        )

    return {"action": "instradamento_aggiornato", "successo": successo}


# ============================================================
# CLASSIFICAZIONE
# ============================================================
def _classifica_documento(filename: str, mime_type: str, mittente: str) -> str:
    """
    Classifica il tipo di documento in base a filename, mime e mittente.
    """
    fn = (filename or "").lower()
    mt = (mittente or "").lower()

    # Fattura XML/P7M
    if fn.endswith(".xml") or fn.endswith(".p7m") or fn.endswith(".xml.p7m"):
        if "fattura" in fn or "ft" in fn or "it" in fn[:5]:
            return "fattura_xml"
        # Se da PEC SDI è sempre fattura
        if "fatturapa" in mt or "pec.fatturapa.it" in mt:
            return "fattura_xml"
        return "fattura_xml"  # XML nel contesto gestionale = quasi sempre fattura

    # F24 (dal nome file o mittente)
    if "f24" in fn or "f-24" in fn or "modello f24" in fn:
        return "f24"
    if "ferrantini" in mt or "marotta" in mt:
        if "f24" in fn:
            return "f24"

    # Cedolino/LUL
    if any(kw in fn for kw in ["cedolino", "busta_paga", "busta paga", "cedolini"]):
        return "cedolino"
    if any(kw in fn for kw in ["lul", "libro_unico", "libro unico", "presenze"]):
        return "lul_presenze"
    # Da mittente consulente → cedolino se PDF
    if ("ferrantini" in mt or "marotta" in mt) and fn.endswith(".pdf"):
        return "cedolino"

    # Verbale
    if any(kw in fn for kw in ["verbale", "multa", "sanzione", "contravvenzione"]):
        return "verbale"
    if "comune.napoli" in mt or "partenopay" in mt:
        return "verbale"

    # PDF generico
    if fn.endswith(".pdf"):
        return "pdf_generico"

    return "non_riconosciuto"
