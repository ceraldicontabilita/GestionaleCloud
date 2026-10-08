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
import re
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

#: Categorie che non dicono niente: il documento e' ancora da classificare.
CATEGORIE_NON_DECISE = frozenset({"", "altro", "auto"})

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def categoria_decisa(documento: Optional[Dict[str, Any]]) -> Optional[str]:
    """La categoria gia' assegnata al documento, se dice qualcosa."""
    categoria = str((documento or {}).get("category") or "").strip().lower()
    return None if categoria in CATEGORIE_NON_DECISE else categoria


def impronta_sha256(*valori: Any) -> Optional[str]:
    """Il primo valore che e' davvero uno SHA-256: la deduplica documentale
    non decide mai su un MD5 (CLAUDE.md, «Deduplica documentale certa»)."""
    for valore in valori:
        testo = str(valore or "").strip().lower()
        if _SHA256.match(testo):
            return testo
    return None


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
    documento = await db["documents_inbox"].find_one(
        {"id": doc_id},
        {
            "_id": 0,
            "id": 1,
            "category": 1,
            "sha256": 1,
            "file_hash": 1,
            "tipo_documento": 1,
            "testo_estratto": 1,
            "extracted_text": 1,
            "content_text": 1,
            "text": 1,
        },
    ) or {}

    # --- DEDUPLICA su SHA-256 ---
    # Il campo `hash_file` non esiste su nessun documento (0 righe): l'impronta
    # sta in `sha256` o in `file_hash`. Si cercano entrambi.
    sha256 = impronta_sha256(hash_file, documento.get("sha256"), documento.get("file_hash"))
    if sha256:
        existing = await db["documents_inbox"].find_one(
            {"$or": [{"sha256": sha256}, {"file_hash": sha256}], "id": {"$ne": doc_id}},
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
    # Un documento che ha gia' la sua categoria (dall'import, dal classificatore
    # del contenuto o dal titolare) non si riclassifica dal solo nome del file:
    # prima si sovrascriveva `tipo_documento` e si apriva un «non classificato».
    categoria = categoria_decisa(documento)
    if categoria:
        await log_evento(
            modulo="documenti", azione="acquisito", entita_id=doc_id,
            entita_collection="documents_inbox", db=db,
            nuovo_stato={"categoria": categoria, "filename": filename},
            fonte=origine,
            dettaglio=f"'{filename}' da {origine} gia' classificato come {categoria}",
        )
        return {"action": "documento_gia_classificato", "categoria": categoria,
                "risultati": risultati}

    testo = next(
        (
            str(valore)
            for valore in (
                event.get("testo_estratto"),
                event.get("extracted_text"),
                event.get("content_text"),
                event.get("text"),
                documento.get("testo_estratto"),
                documento.get("extracted_text"),
                documento.get("content_text"),
                documento.get("text"),
            )
            if valore
        ),
        "",
    )
    tipo = _classifica_documento(testo, mime_type)

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
def _classifica_documento(testo: str, mime_type: str = "") -> str:
    """Classifica solo quando il contenuto fornisce una prova sufficiente.

    Nome file e mittente restano metadati utili per la revisione, ma non sono
    fatti contabili: non possono assegnare da soli una categoria definitiva.
    """
    compatto = re.sub(r"\s+", " ", str(testo or "")).upper()
    senza_separatore = re.sub(r"[^A-Z0-9]", "", compatto)

    if "FATTURAELETTRONICA" in senza_separatore:
        return "fattura_xml"
    if (
        ("DELEGAIRREVOCABILE" in senza_separatore or "MODELLODIPAGAMENTOUNIFICATO" in senza_separatore)
        and "CODICETRIBUTO" in senza_separatore
    ):
        return "f24"
    if sum(
        marker in senza_separatore
        for marker in ("NETTODELMESE", "TOTALECOMPETENZE", "TOTALETRATTENUTE", "PERIODODIRETRIBUZIONE")
    ) >= 3:
        return "cedolino"
    if "LIBROUNICODELLAVORO" in senza_separatore and "PRESENZE" in senza_separatore:
        return "lul_presenze"
    if any(
        marker in compatto
        for marker in (
            "VERBALE DI ACCERTAMENTO DI VIOLAZIONE",
            "SANZIONE AMMINISTRATIVA",
            "CONTRAVVENZIONE",
        )
    ):
        return "verbale"
    if mime_type == "application/pdf" and compatto:
        return "pdf_generico"
    return "non_riconosciuto"
