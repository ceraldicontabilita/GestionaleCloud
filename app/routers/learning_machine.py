"""
Router Learning Machine - Classificazione Documenti Intelligente
================================================================

Sistema di classificazione automatica documenti con apprendimento iterativo.
Ogni correzione dell'utente migliora la logica di riconoscimento.

Funzionalità:
- Scansione email multi-cartella
- Classificazione automatica con 23 categorie
- Feedback loop per apprendimento
- Estrazione dati strutturati
- Report statistiche
"""

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from typing import Dict, Any, List
from datetime import datetime, timezone, timedelta
from pydantic import BaseModel
import imaplib
import email
from email.header import decode_header
import logging
import os

from app.database import Database

logger = logging.getLogger(__name__)
router = APIRouter()

# Configurazione Email
EMAIL = os.environ.get("EMAIL_ADDRESS", "")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", "") or os.environ.get("EMAIL_APP_PASSWORD", "")
IMAP_SERVER = os.environ.get("IMAP_SERVER", "imap.gmail.com")

# Collezioni
COLLECTION_DOCS = "documenti_classificati"
COLLECTION_FEEDBACK = "learning_feedback"
COLLECTION_RULES = "learning_rules"


# ============================================================
# CATEGORIE E REGOLE DI CLASSIFICAZIONE
# ============================================================

CATEGORIE_BASE = {
    "F24": {
        "keywords": ["f24", "modello f24", "tributo", "versamento", "delega f24", "codice tributo"],
        "weight": 1.0
    },
    "BUSTE_PAGA": {
        "keywords": ["cedolino", "busta paga", "retribuzione", "stipendio", "paghe", "netto in busta", "riepilogo paghe"],
        "weight": 1.0
    },
    "FATTURE_FORNITORI": {
        "keywords": ["fattura", "invoice", "ft-", "nota di credito", "fatt.", "n.documento", "fattura elettronica"],
        "weight": 1.0
    },
    "INPS_CONTRIBUTI": {
        "keywords": ["inps", "contributi", "dm10", "uniemens", "durc", "matricola inps", "sede inps"],
        "weight": 1.0
    },
    "INPS_FONSI": {
        "keywords": ["fonsi", "delibere", "cassa integrazione", "cig", "ammortizzatori", "cigo", "cigs"],
        "weight": 1.0
    },
    "INPS_DILAZIONI": {
        "keywords": ["dilazione", "rateizzazione", "5100 dmra", "piano rateale"],
        "weight": 1.0
    },
    "AGENZIA_ENTRATE": {
        "keywords": ["agenzia delle entrate", "ader", "cartella esattoriale", "riscossione", "intimazione"],
        "weight": 1.0
    },
    "ROTTAMAZIONE": {
        "keywords": ["rottamazione", "definizione agevolata", "pace fiscale", "197/2022", "stralcio"],
        "weight": 1.0
    },
    "VERBALI_MULTE": {
        "keywords": ["verbale", "multa", "infrazione", "contravvenzione", "violazione cds", "perizia"],
        "weight": 1.0
    },
    "NOLEGGIO_AUTO": {
        "keywords": ["leasys", "ald", "arval", "leaseplan", "noleggio", "ayvens", "psrenting", "canone", "free2move"],
        "weight": 1.0
    },
    "BONIFICI_STIPENDI": {
        "keywords": ["bonifico", "info bonifico", "pagamento stipendio", "accredito", "you business", "youbusiness"],
        "weight": 1.0
    },
    "ESTRATTO_CONTO": {
        "keywords": ["estratto conto", "saldo", "movimenti c/c", "conto corrente", "rendiconto"],
        "weight": 1.0
    },
    "ASSICURAZIONE": {
        "keywords": ["polizza", "assicurazione", "generali", "premio", "sinistro", "quietanza", "rca"],
        "weight": 1.0
    },
    "DIMISSIONI": {
        "keywords": ["dimissioni", "recesso", "cessazione rapporto", "cliclavoro", "notifica recesso"],
        "weight": 1.0
    },
    "CONTRATTI_LAVORO": {
        "keywords": ["assunzione", "contratto", "proroghe", "trasformazione", "lettera impegno"],
        "weight": 1.0
    },
    "TFR": {
        "keywords": ["tfr", "trattamento fine rapporto", "liquidazione", "fondi pensione"],
        "weight": 1.0
    },
    "INAIL": {
        "keywords": ["inail", "infortunio", "autoliquidazione", "denuncia infortunio"],
        "weight": 1.0
    },
    "TARI": {
        "keywords": ["tari", "rifiuti", "tassa rifiuti", "tarsu"],
        "weight": 1.0
    },
    "IMU": {
        "keywords": ["imu", "imposta municipale", "tasi"],
        "weight": 1.0
    },
    "UTENZE": {
        "keywords": ["enel", "gas", "acqua", "telecom", "tim", "wind", "sorgenia", "bolletta", "fornitura"],
        "weight": 1.0
    },
    "LEGALE": {
        "keywords": ["avvocato", "sentenza", "pignoramento", "tribunale", "causa", "citazione", "precetto", "decreto"],
        "weight": 1.0
    },
    "HACCP": {
        "keywords": ["haccp", "alimentaristi", "sanificazione", "asl", "autocontrollo"],
        "weight": 1.0
    },
    "CERTIFICATI_MEDICI": {
        "keywords": ["certificato medico", "malattia", "protocollo inps", "prognosi"],
        "weight": 1.0
    }
}


def decode_email_subject(subject: str) -> str:
    """Decodifica subject email."""
    if not subject:
        return ""
    decoded = []
    for part, encoding in decode_header(subject):
        if isinstance(part, bytes):
            decoded.append(part.decode(encoding or 'utf-8', errors='replace'))
        else:
            decoded.append(part)
    return ' '.join(decoded)


async def get_learned_rules(db) -> Dict[str, List[str]]:
    """Recupera regole apprese dal feedback utente."""
    rules = {}
    cursor = db[COLLECTION_RULES].find({})
    async for rule in cursor:
        cat = rule.get("categoria")
        if cat:
            rules[cat] = rule.get("keywords_extra", [])
    return rules


def classify_document(subject: str, sender: str, body: str, learned_rules: Dict = None) -> tuple:
    """
    Classifica un documento basandosi su contenuto.
    Ritorna (categoria, confidence)
    """
    text = f"{subject} {sender} {body}".lower()
    
    scores = {}
    
    for categoria, config in CATEGORIE_BASE.items():
        score = 0
        for kw in config["keywords"]:
            if kw.lower() in text:
                score += 1 * config["weight"]
                # Bonus se nel subject
                if kw.lower() in subject.lower():
                    score += 2
        
        # Aggiungi keywords apprese
        if learned_rules and categoria in learned_rules:
            for kw in learned_rules[categoria]:
                if kw.lower() in text:
                    score += 1.5  # Peso maggiore per keywords apprese
        
        if score > 0:
            scores[categoria] = score
    
    if scores:
        best = max(scores.items(), key=lambda x: x[1])
        total_score = sum(scores.values())
        confidence = round((best[1] / total_score) * 100 if total_score > 0 else 0, 1)
        return best[0], confidence
    
    return "NON_CLASSIFICATO", 0.0


# ============================================================
# MODELLI
# ============================================================

class FeedbackRequest(BaseModel):
    document_id: str
    categoria_corretta: str
    keywords_nuove: List[str] = []
    note: str = ""


class ScanRequest(BaseModel):
    cartelle: List[str] = ["INBOX"]
    giorni: int = 30
    limite_per_cartella: int = 100


# ============================================================
# ENDPOINT API
# ============================================================

@router.get("/dashboard")
async def get_learning_dashboard() -> Dict[str, Any]:
    """
    Dashboard completa della Learning Machine.
    """
    db = Database.get_db()
    
    # Conta documenti per categoria
    pipeline = [
        {"$group": {"_id": "$categoria", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]
    categories_stats = {}
    async for stat in db[COLLECTION_DOCS].aggregate(pipeline):
        categories_stats[stat["_id"]] = stat["count"]
    
    # Totali
    total_docs = await db[COLLECTION_DOCS].count_documents({})
    total_with_pdf = await db[COLLECTION_DOCS].count_documents({"has_pdf": True})
    total_processati = await db[COLLECTION_DOCS].count_documents({"processato": True})
    total_non_classificati = await db[COLLECTION_DOCS].count_documents({"categoria": "NON_CLASSIFICATO"})
    
    # Feedback ricevuti
    total_feedback = await db[COLLECTION_FEEDBACK].count_documents({})
    
    # Regole apprese
    total_rules = await db[COLLECTION_RULES].count_documents({})
    
    # Ultimi documenti
    ultimi = await db[COLLECTION_DOCS].find(
        {},
        {"_id": 0, "_key": 0, "body_preview": 0}
    ).sort("created_at", -1).limit(10).to_list(10)
    
    return {
        "success": True,
        "totale_documenti": total_docs,
        "documenti_con_pdf": total_with_pdf,
        "documenti_processati": total_processati,
        "non_classificati": total_non_classificati,
        "feedback_ricevuti": total_feedback,
        "regole_apprese": total_rules,
        "distribuzione_categorie": categories_stats,
        "ultimi_documenti": ultimi,
        "categorie_disponibili": list(CATEGORIE_BASE.keys())
    }


@router.get("/documenti")
async def get_documenti(
    categoria: str = Query(None),
    has_pdf: bool = Query(None),
    processato: bool = Query(None),
    limit: int = Query(100),
    skip: int = Query(0)
) -> Dict[str, Any]:
    """
    Lista documenti classificati con filtri.
    """
    db = Database.get_db()
    
    filtro = {}
    if categoria:
        filtro["categoria"] = categoria
    if has_pdf is not None:
        filtro["has_pdf"] = has_pdf
    if processato is not None:
        filtro["processato"] = processato
    
    cursor = db[COLLECTION_DOCS].find(
        filtro,
        {"_id": 0, "_key": 0}
    ).sort("created_at", -1).skip(skip).limit(limit)
    
    docs = await cursor.to_list(limit)
    total = await db[COLLECTION_DOCS].count_documents(filtro)
    
    return {
        "success": True,
        "totale": total,
        "documenti": docs,
        "limit": limit,
        "skip": skip
    }


@router.post("/feedback")
async def submit_feedback(request: FeedbackRequest) -> Dict[str, Any]:
    """
    Invia feedback per correggere la classificazione.
    Il sistema apprende dalle correzioni.
    """
    db = Database.get_db()
    
    # Trova documento
    doc = await db[COLLECTION_DOCS].find_one({"_key": request.document_id})
    if not doc:
        # Prova con subject
        doc = await db[COLLECTION_DOCS].find_one({"subject": {"$regex": request.document_id[:30]}})
    
    if not doc:
        raise HTTPException(404, "Documento non trovato")
    
    categoria_precedente = doc.get("categoria")
    
    # Salva feedback
    feedback = {
        "document_key": doc.get("_key"),
        "subject": doc.get("subject"),
        "categoria_precedente": categoria_precedente,
        "categoria_corretta": request.categoria_corretta,
        "keywords_nuove": request.keywords_nuove,
        "note": request.note,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db[COLLECTION_FEEDBACK].insert_one(feedback)
    
    # Aggiorna documento
    await db[COLLECTION_DOCS].update_one(
        {"_key": doc.get("_key")},
        {"$set": {
            "categoria": request.categoria_corretta,
            "feedback_utente": request.categoria_corretta,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    # LEARNING: Aggiorna regole
    if request.keywords_nuove:
        await db[COLLECTION_RULES].update_one(
            {"categoria": request.categoria_corretta},
            {
                "$addToSet": {"keywords_extra": {"$each": request.keywords_nuove}},
                "$set": {"updated_at": datetime.now(timezone.utc).isoformat()},
                "$inc": {"feedback_count": 1}
            },
            upsert=True
        )
    
    # Estrai keywords automaticamente dal subject
    subject_words = doc.get("subject", "").lower().split()
    meaningful_words = [w for w in subject_words if len(w) > 4 and w.isalpha()]
    
    if meaningful_words:
        await db[COLLECTION_RULES].update_one(
            {"categoria": request.categoria_corretta},
            {
                "$addToSet": {"keywords_auto": {"$each": meaningful_words[:3]}},
                "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}
            },
            upsert=True
        )
    
    return {
        "success": True,
        "message": f"Documento riclassificato: {categoria_precedente} → {request.categoria_corretta}",
        "keywords_apprese": request.keywords_nuove + meaningful_words[:3],
        "learning_applied": True
    }


@router.post("/scan")
async def scan_emails_full(request: ScanRequest, background_tasks: BackgroundTasks) -> Dict[str, Any]:
    """
    Avvia scansione email completa.
    """
    if not EMAIL or not EMAIL_PASSWORD:
        raise HTTPException(400, "Credenziali email non configurate")
    
    db = Database.get_db()
    learned_rules = await get_learned_rules(db)
    
    results = {
        "cartelle_scansionate": 0,
        "email_analizzate": 0,
        "nuovi_documenti": 0,
        "per_categoria": {}
    }
    
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL, EMAIL_PASSWORD)
        
        for folder in request.cartelle:
            try:
                status, _ = mail.select(f'"{folder}"', readonly=True)
                if status != "OK":
                    continue
                
                results["cartelle_scansionate"] += 1
                
                # Cerca email degli ultimi N giorni
                date_since = (datetime.now() - timedelta(days=request.giorni)).strftime("%d-%b-%Y")
                status, messages = mail.search(None, f'(SINCE "{date_since}")')
                
                if status != "OK" or not messages[0]:
                    continue
                
                email_ids = messages[0].split()[-request.limite_per_cartella:]
                
                for eid in email_ids:
                    try:
                        status, msg_data = mail.fetch(eid, "(RFC822)")
                        if status != "OK":
                            continue
                        
                        raw_email = msg_data[0][1]
                        msg = email.message_from_bytes(raw_email)
                        
                        subject = decode_email_subject(msg.get("Subject", ""))
                        sender = msg.get("From", "")
                        date_str = msg.get("Date", "")
                        
                        # Estrai body
                        body = ""
                        if msg.is_multipart():
                            for part in msg.walk():
                                if part.get_content_type() == "text/plain":
                                    try:
                                        payload = part.get_payload(decode=True)
                                        if payload:
                                            body = payload.decode("utf-8", errors="replace")[:1000]
                                            break
                                    except Exception:
                                        pass
                        
                        # Classifica con regole apprese
                        categoria, confidence = classify_document(subject, sender, body, learned_rules)
                        
                        # Verifica allegati
                        has_pdf = False
                        attachments = []
                        if msg.is_multipart():
                            for part in msg.walk():
                                fn = part.get_filename()
                                if fn:
                                    attachments.append(fn)
                                    if fn.lower().endswith(".pdf"):
                                        has_pdf = True
                        
                        # Salva
                        key = f"{folder}_{subject[:50]}_{date_str}"
                        existing = await db[COLLECTION_DOCS].find_one({"_key": key})
                        
                        if not existing:
                            doc = {
                                "_key": key,
                                "folder": folder,
                                "subject": subject[:200],
                                "from": sender[:100],
                                "date": date_str,
                                "categoria": categoria,
                                "confidence": confidence,
                                "has_pdf": has_pdf,
                                "attachments": attachments[:5],
                                "body_preview": body[:300],
                                "processato": False,
                                "created_at": datetime.now(timezone.utc).isoformat()
                            }
                            await db[COLLECTION_DOCS].insert_one(doc)
                            results["nuovi_documenti"] += 1
                            results["per_categoria"][categoria] = results["per_categoria"].get(categoria, 0) + 1
                        
                        results["email_analizzate"] += 1
                        
                    except Exception as e:
                        logger.error(f"Errore email: {e}")
                        
            except Exception as e:
                logger.error(f"Errore cartella {folder}: {e}")
        
        mail.logout()
        
    except Exception as e:
        raise HTTPException(500, f"Errore scansione: {str(e)}")
    
    return {
        "success": True,
        **results
    }


@router.get("/regole-apprese")
async def get_learned_rules_api() -> Dict[str, Any]:
    """
    Mostra le regole apprese dal feedback utente.
    """
    db = Database.get_db()
    
    rules = await db[COLLECTION_RULES].find({}, {"_id": 0}).to_list(100)
    
    return {
        "success": True,
        "totale_regole": len(rules),
        "regole": rules
    }


@router.get("/statistiche-feedback")
async def get_feedback_stats() -> Dict[str, Any]:
    """
    Statistiche sui feedback ricevuti.
    """
    db = Database.get_db()
    
    # Conteggio per categoria corretta
    pipeline = [
        {"$group": {
            "_id": "$categoria_corretta",
            "count": {"$sum": 1}
        }},
        {"$sort": {"count": -1}}
    ]
    
    stats = {}
    async for s in db[COLLECTION_FEEDBACK].aggregate(pipeline):
        stats[s["_id"]] = s["count"]
    
    # Ultimi feedback
    ultimi = await db[COLLECTION_FEEDBACK].find(
        {},
        {"_id": 0}
    ).sort("created_at", -1).limit(20).to_list(20)
    
    return {
        "success": True,
        "totale_feedback": await db[COLLECTION_FEEDBACK].count_documents({}),
        "per_categoria": stats,
        "ultimi_feedback": ultimi
    }


@router.delete("/reset-learning")
async def reset_learning() -> Dict[str, Any]:
    """
    Reset delle regole apprese (solo per admin).
    """
    db = Database.get_db()
    
    deleted_rules = await db[COLLECTION_RULES].delete_many({})
    deleted_feedback = await db[COLLECTION_FEEDBACK].delete_many({})
    
    # Rimuovi feedback_utente dai documenti
    await db[COLLECTION_DOCS].update_many(
        {},
        {"$unset": {"feedback_utente": ""}}
    )
    
    return {
        "success": True,
        "regole_eliminate": deleted_rules.deleted_count,
        "feedback_eliminati": deleted_feedback.deleted_count
    }
