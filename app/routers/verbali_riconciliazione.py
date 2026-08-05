"""
Gestione Verbali Noleggio - Sistema di Riconciliazione Completo

Flusso:
1. VERBALE (multa) → arriva via email o trovato su parabrezza
2. FATTURA NOLEGGIATORE → contiene numero verbale + spese notifica
3. PAGAMENTO → in banca/estratto conto
4. RICONCILIAZIONE → collega tutto: Verbale + Fattura + Pagamento + Veicolo + Driver

Stati del Verbale:
- da_scaricare: Trovato in posta, PDF da scaricare
- salvato: PDF scaricato, in attesa
- fattura_ricevuta: Fattura noleggiatore associata
- pagato: Pagamento trovato in estratto conto
- riconciliato: Tutto collegato
"""

# Endpoint rimossi il 14/07/2026 (piano residuo op.10, zero chiamanti verificati):
# associa-fattura, automazione-completa, crea-prima-nota-verbale, dettaglio-completo,
# pending-status, per-dipendente, per-driver, per-targa, per-veicolo,
# quietanze-verbale(+pdf), registra-pagamento, registra-quietanza,
# riconcilia-estratto-conto-paypal, scan-email (route; il servizio sottostante
# resta vivo via scheduler), scan-email-storico, scan-pagopa, scan-verbale,
# scheduler-status, {numero_verbale}/pdf — codice conservato nella cronologia git.
# NOTA 18/07/2026: scan-email è stata REINTRODOTTA (admin) per collaudare
# on-demand l'orchestratore completato di verbali_email_logic (audit P1-4).

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from bson import ObjectId
from bson.errors import InvalidId
import re
import logging

from app.database import Database
from app.utils.dependencies import get_current_admin_user
from app.utils.error_handler import handle_errors

logger = logging.getLogger(__name__)
router = APIRouter()


def campi_ricerca_verbale_in_fattura(numero_verbale: str) -> List[Dict[str, Any]]:
    """Costruisce il `$or` per cercare il numero verbale dentro una fattura
    `invoices`. Le righe fattura stanno nel campo canonico `linee` (NON `items`,
    che non esiste su invoices) → prima la ricerca sulle righe non trovava mai
    nulla. Vedi P0.4."""
    rx = {"$regex": re.escape(numero_verbale), "$options": "i"}
    return [
        {"descrizione": rx}, {"body": rx}, {"note": rx}, {"notes": rx},
        {"oggetto": rx}, {"subject": rx},
        {"linee.descrizione": rx}, {"linee.description": rx},
    ]


# ===== UTILITY FUNCTIONS =====

def extract_verbale_from_description(description: str) -> Optional[str]:
    """Estrae il numero verbale dalla descrizione fattura."""
    if not description:
        return None
    
    # Pattern comuni per numeri verbale
    patterns = [
        r'Verbale\s*(?:Nr|N\.?|Numero)?[:\s]*([A-Z0-9]+)',
        r'N\.\s*Verbale[:\s]*([A-Z0-9]+)',
        r'verbale[:\s]+([A-Z]\d{8,})',
        r'([A-Z]\d{10,})',  # Pattern generico tipo A25111540620
        r'([B]\d{10,})',    # Pattern B + 10 cifre
        r'Nr[:\s]*([A-Z]\d{8,})',  # Nr: A25111540620
        r'Numero[:\s]*([A-Z]\d{8,})',  # Numero: A25111540620
    ]
    
    for pattern in patterns:
        match = re.search(pattern, description, re.IGNORECASE)
        if match:
            return match.group(1).upper()
    
    return None


def serialize_doc(doc: dict) -> dict:
    """Serializza documento MongoDB per JSON."""
    if doc is None:
        return None
    result = {}
    for k, v in doc.items():
        if k == '_id':
            result['id'] = str(v)
        elif isinstance(v, ObjectId):
            result[k] = str(v)
        elif isinstance(v, datetime):
            result[k] = v.isoformat()
        else:
            result[k] = v
    return result


# ===== ENDPOINTS =====

@router.post("/scan-email")
@handle_errors
async def scan_email_verbali(
    days_back: int = Query(30, ge=1, le=730, description="Giorni indietro per la ricerca nuovi elementi"),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Esegue on-demand lo scan email verbali con logica di priorità
    (FASE 1: completa quietanze/PDF dei verbali sospesi; FASE 2: nuovi
    verbali e quietanze). Stesso motore del job orario dello scheduler."""
    from app.services.verbali_email_logic import scan_email_con_priorita
    db = Database.get_db()
    return await scan_email_con_priorita(db, days_back=days_back)


@router.post("/scan-gmail-attendibili")
@handle_errors
async def scan_gmail_mittenti_attendibili(
    days_back: int = Query(
        30,
        ge=1,
        le=3650,
        description="Giorni indietro; vengono ammessi solo mittenti verbali attendibili",
    ),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Importa PDF verbali solo dalla whitelist canonica.

    Endpoint di collaudo e recupero storico separato dall'orchestratore legacy:
    conserva una copia nell'app, deduplica per hash e archivia su Drive.
    """
    from app.services.verbali_gmail_scanner import scan_gmail_verbali

    return await scan_gmail_verbali(
        Database.get_db(), days_back=days_back, mark_as_read=False
    )


@router.get("/dashboard")
@handle_errors
async def get_verbali_dashboard() -> Dict[str, Any]:
    """Dashboard riassuntiva dello stato verbali."""
    db = Database.get_db()
    
    try:
        # Conta verbali per stato - USA PROIEZIONE per evitare di caricare PDF
        pipeline = [
            {"$project": {"stato": 1, "importo": 1}},  # Solo campi necessari
            {"$group": {
                "_id": "$stato",
                "count": {"$sum": 1},
                "totale_importo": {"$sum": {"$toDouble": {"$ifNull": ["$importo", 0]}}}
            }}
        ]
        stati = await db["verbali_noleggio"].aggregate(pipeline).to_list(100)
        
        per_stato = {}
        totale_verbali = 0
        totale_importo = 0
        for s in stati:
            stato = s["_id"] or "sconosciuto"
            per_stato[stato] = {"count": s["count"], "importo": round(s["totale_importo"], 2)}
            totale_verbali += s["count"]
            totale_importo += s["totale_importo"]
        
        # Verbali da riconciliare - solo count
        da_riconciliare = await db["verbali_noleggio"].count_documents({
            "$or": [
                {"stato": "fattura_ricevuta", "pagamento_id": {"$exists": False}},
                {"stato": "pagato", "fattura_id": {"$exists": False}},
                {"stato": "salvato"}
            ]
        })
        
        # Ultimi 5 verbali - ESCLUDI campi pesanti (pdf_content, pdf_base64, etc)
        projection = {
            "_id": 1,
            "id": 1,
            "numero_verbale": 1,
            "targa": 1,
            "importo": 1,
            "stato": 1,
            "data_violazione": 1,
            "created_at": 1
        }
        ultimi = await db["verbali_noleggio"].find({}, projection).sort("created_at", -1).limit(5).to_list(5)
        
        from app.config import settings
        from app.services.drive_folder_registry import get_folder_id

        email_user = (
            settings.GMAIL_EMAIL or settings.IMAP_USER or settings.EMAIL_USER
            or settings.GMAIL_ACCOUNT_AMMINISTRATIVO
        )
        email_password = (
            settings.GMAIL_APP_PASSWORD or settings.IMAP_PASSWORD
            or settings.EMAIL_PASSWORD or settings.EMAIL_APP_PASSWORD
            or settings.GMAIL_APP_PASSWORD_AMMINISTRATIVO
        )
        email_configurata = bool(email_user and email_password)
        email_abilitata = bool(settings.ENABLE_EMAIL_VERBALI_SYNC)
        drive_configurato = bool(get_folder_id("verbale"))
        documenti_drive = await db["documents_inbox"].count_documents({
            "$or": [
                {"tipo_documento": "verbale"},
                {"category": "verbale"},
                {"categoria": "verbale"},
            ]
        })
        avviso_sorgenti = None
        if not email_configurata and not drive_configurato:
            avviso_sorgenti = "Nessuna sorgente verbali configurata: il totale zero non e' un collaudo valido."
        elif email_configurata and not email_abilitata:
            avviso_sorgenti = "La casella email e' configurata ma la sincronizzazione automatica verbali e' disattivata."
        elif drive_configurato and documenti_drive == 0 and not email_configurata:
            avviso_sorgenti = "La cartella Drive Verbali e' collegata ma non contiene documenti importati."

        return {
            "success": True,
            "riepilogo": {
                "totale_verbali": totale_verbali,
                "totale_importo": round(totale_importo, 2),
                "da_riconciliare": da_riconciliare,
                "per_stato": per_stato
            },
            "ultimi_verbali": [serialize_doc(v) for v in ultimi],
            "sorgenti": {
                "email": {
                    "configurata": email_configurata,
                    "sincronizzazione_attiva": email_abilitata,
                },
                "drive": {
                    "configurata": drive_configurato,
                    "documenti_importati": documenti_drive,
                },
                "avviso": avviso_sorgenti,
            },
        }
    except Exception as e:
        logger.error(f"Errore dashboard verbali: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/lista")
@handle_errors
async def get_lista_verbali(
    stato: Optional[str] = Query(None, description="Filtra per stato"),
    targa: Optional[str] = Query(None, description="Filtra per targa veicolo"),
    da_riconciliare: bool = Query(False, description="Solo verbali da riconciliare"),
    ordinamento: str = Query("data_verbale", description="Ordinamento: data_verbale, numero_verbale, created_at")
) -> Dict[str, Any]:
    """Lista verbali con filtri e ordinamento. OTTIMIZZATO per escludere PDF."""
    db = Database.get_db()
    
    try:
        query = {}
        
        if stato:
            query["stato"] = stato
        
        if targa:
            query["targa"] = {"$regex": targa, "$options": "i"}
        
        if da_riconciliare:
            query["$or"] = [
                {"stato": "fattura_ricevuta", "pagamento_id": {"$exists": False}},
                {"stato": "pagato", "fattura_id": {"$exists": False}},
                {"stato": "salvato"}
            ]
        
        # PROIEZIONE: escludi campi pesanti (PDF base64)
        projection = {
            "_id": 1,
            "id": 1,
            "numero_verbale": 1,
            "targa": 1,
            "importo": 1,
            "stato": 1,
            "data_verbale": 1,
            "data_violazione": 1,
            "scadenza_pagamento": 1,
            "driver": 1,
            "driver_nome": 1,
            "driver_id": 1,
            "veicolo_id": 1,
            "fattura_id": 1,
            "fattura_associata_id": 1,
            "fattura_numero": 1,
            "fattura_associata_numero": 1,
            "fattura_associata_data": 1,
            "fattura_associata_fornitore": 1,
            "fattura_associata_importo": 1,
            "numero_fattura": 1,
            "fornitore": 1,
            "pagamento_id": 1,
            "paypal_transaction_id": 1,
            "movimento_banca_id": 1,
            "ricevuta_pagopa_id": 1,
            "iuv": 1,
            "data_pagamento": 1,
            "quietanza_ricevuta": 1,
            "stato_pagamento": 1,
            "metodo_pagamento": 1,
            "note": 1,
            "source": 1,
            "created_at": 1,
            "updated_at": 1
            # ESCLUDI: pdf_content, pdf_base64, email_body, attachment_content, pdf_quietanza, etc.
        }
        
        # Ordinamento configurabile
        sort_field = ordinamento if ordinamento in ("data_verbale", "numero_verbale", "created_at") else "data_verbale"
        sort_dir = 1 if sort_field == "numero_verbale" else -1
        
        verbali = await db["verbali_noleggio"].find(query, projection).sort(sort_field, sort_dir).to_list(500)
        
        # Normalizza driver_nome e fattura_numero
        for v in verbali:
            if not v.get("driver_nome") and v.get("driver"):
                v["driver_nome"] = v["driver"]
            if not v.get("fattura_numero") and v.get("numero_fattura"):
                v["fattura_numero"] = v["numero_fattura"]
            v["fattura_id"] = v.get("fattura_id") or v.get("fattura_associata_id")
            v["fattura_numero"] = (
                v.get("fattura_numero")
                or v.get("fattura_associata_numero")
                or v.get("numero_fattura")
            )
            v["fornitore"] = v.get("fornitore") or v.get("fattura_associata_fornitore")
            v["pagamento_id"] = (
                v.get("pagamento_id")
                or v.get("paypal_transaction_id")
                or v.get("ricevuta_pagopa_id")
                or v.get("movimento_banca_id")
            )
            if not v.get("metodo_pagamento"):
                if v.get("paypal_transaction_id"):
                    v["metodo_pagamento"] = "PayPal"
                elif v.get("ricevuta_pagopa_id"):
                    v["metodo_pagamento"] = "PagoPA"
                elif v.get("movimento_banca_id"):
                    v["metodo_pagamento"] = "Bonifico bancario"
        
        return {
            "success": True,
            "verbali": [serialize_doc(v) for v in verbali],
            "totale": len(verbali)
        }
    except Exception as e:
        logger.error(f"Errore lista verbali: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scan-fatture-verbali")
@handle_errors
async def scan_fatture_per_verbali() -> Dict[str, Any]:
    """
    Scansiona tutte le fatture dei noleggiatori per estrarre numeri verbale
    e creare associazioni automatiche.
    """
    db = Database.get_db()
    
    try:
        # Fornitori noleggio tipici (se vuoto cerca in tutte le fatture)
        fornitori_noleggio = ["ALD", "LEASYS", "ARVAL", "LEASEPLAN", "ALPHABET"]
        
        # Trova fatture dei noleggiatori E tutte quelle con numeri verbale
        fatture = await db["invoices"].find({
            "$or": [
                {"supplier_name": {"$regex": "|".join(fornitori_noleggio), "$options": "i"}},
                {"fornitore": {"$regex": "|".join(fornitori_noleggio), "$options": "i"}},
                # Cerca anche nelle fatture con pattern verbale nei testi
                {"descrizione": {"$regex": r"[AB]\d{8,12}", "$options": "i"}},
                {"body": {"$regex": r"[AB]\d{8,12}", "$options": "i"}},
                {"note": {"$regex": r"[AB]\d{8,12}", "$options": "i"}},
                {"oggetto": {"$regex": r"[AB]\d{8,12}", "$options": "i"}},
            ]
        }).to_list(5000)
        
        verbali_trovati = 0
        associazioni_create = 0
        
        for fattura in fatture:
            # Costruisci testo completo della fattura cercando in tutti i campi
            campi_testo = [
                fattura.get("descrizione", "") or "",
                fattura.get("body", "") or "",
                fattura.get("note", "") or "",
                fattura.get("notes", "") or "",
                fattura.get("oggetto", "") or "",
                fattura.get("subject", "") or "",
                fattura.get("invoice_number", "") or "",
            ]
            # Aggiungi le righe fattura reali salvate dal parser (chiave "linee",
            # non "items" — "items" non esiste mai sui documenti invoices, quindi
            # questo blocco non contribuiva mai nulla). Include anche
            # AltriDatiGestionali: alcuni fornitori (es. Leasys) mettono la
            # causale/il riferimento verbale reale solo lì, non in Descrizione.
            for linea in fattura.get("linee", []):
                campi_testo.append(linea.get("descrizione", "") or "")
                for adg in linea.get("altri_dati_gestionali") or []:
                    campi_testo.append(adg.get("riferimento_testo", "") or "")

            testo_completo = " ".join(campi_testo)
            
            # Cerca numero verbale nel testo completo
            numero_verbale = extract_verbale_from_description(testo_completo)
            
            if numero_verbale:
                verbali_trovati += 1
                fattura_id = fattura.get("id") or str(fattura.get("_id"))
                fattura_numero = fattura.get("invoice_number") or fattura.get("numero_fattura")
                
                # Verifica se esiste già l'associazione
                existing = await db["verbali_noleggio"].find_one({
                    "numero_verbale": numero_verbale,
                    "$or": [
                        {"fattura_id": fattura_id},
                        {"fattura_associata_id": fattura_id},
                    ],
                })
                
                if not existing:
                    # Crea o aggiorna verbale
                    verbale_doc = await db["verbali_noleggio"].find_one({"numero_verbale": numero_verbale})
                    
                    update_data = {
                        "fattura_id": fattura_id,
                        "fattura_associata_id": fattura_id,
                        "fattura_numero": fattura_numero,
                        "fattura_associata_numero": fattura_numero,
                        "numero_fattura": fattura_numero,
                        "fattura_associata_data": fattura.get("invoice_date") or fattura.get("data_documento"),
                        "fattura_associata_importo": fattura.get("total_amount") or fattura.get("importo_totale"),
                        "fornitore": fattura.get("supplier_name") or fattura.get("fornitore"),
                        "fattura_associata_fornitore": fattura.get("supplier_name") or fattura.get("fornitore"),
                        "targa": fattura.get("targa"),
                        "updated_at": datetime.now(timezone.utc)
                    }
                    
                    if verbale_doc:
                        # Aggiorna esistente
                        nuovo_stato = "riconciliato" if (
                            verbale_doc.get("pagamento_id")
                            or verbale_doc.get("paypal_transaction_id")
                            or verbale_doc.get("ricevuta_pagopa_id")
                            or verbale_doc.get("movimento_banca_id")
                        ) else "fattura_ricevuta"
                        update_data["stato"] = nuovo_stato
                        await db["verbali_noleggio"].update_one(
                            {"numero_verbale": numero_verbale},
                            {"$set": update_data}
                        )
                    else:
                        # Crea nuovo
                        update_data["numero_verbale"] = numero_verbale
                        update_data["stato"] = "fattura_ricevuta"
                        update_data["created_at"] = datetime.now(timezone.utc)
                        await db["verbali_noleggio"].insert_one(update_data)
                    await db["invoices"].update_one(
                        {"id": fattura_id},
                        {"$addToSet": {"verbali_collegati": numero_verbale}},
                    )
                    
                    associazioni_create += 1
        
        return {
            "success": True,
            "fatture_analizzate": len(fatture),
            "verbali_trovati": verbali_trovati,
            "associazioni_create": associazioni_create
        }
    except Exception as e:
        logger.error(f"Errore scan fatture verbali: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _punteggio_completezza(v: Dict[str, Any]) -> int:
    """Quanto è completo un documento verbale: usato per scegliere quale dei
    duplicati tenere come canonico durante il merge."""
    campi = ("fattura_id", "fattura_numero", "numero_fattura", "importo",
             "pagamento_id", "driver_id", "driver", "targa", "quietanza_ricevuta")
    return sum(1 for c in campi if v.get(c))


@router.post("/pulisci-duplicati")
@handle_errors
async def pulisci_duplicati_verbali(dry_run: bool = Query(True)) -> Dict[str, Any]:
    """
    verbali_noleggio è scritto da 8 percorsi indipendenti (scan email, scan
    fatture, trigger fattura, pipeline post-download, scanner PagoPA, ecc.):
    ognuno controlla i duplicati a modo suo prima di inserire, ma nessun
    controllo è condiviso tra i percorsi né esiste un indice unico sul DB,
    quindi due percorsi diversi possono creare due documenti per lo stesso
    numero_verbale (visibile in /lista come righe duplicate con dati
    diversi, es. una con l'importo e una senza).

    Questo endpoint raggruppa per numero_verbale, sceglie come "canonico" il
    documento più completo (più campi valorizzati, poi più recente), vi
    riversa i campi mancanti dagli altri duplicati, ed elimina i duplicati.
    Con dry_run=True (default) non scrive nulla, restituisce solo l'anteprima.
    """
    db = Database.get_db()

    pipeline = [
        {"$match": {"numero_verbale": {"$exists": True, "$nin": [None, ""]}}},
        {"$group": {"_id": "$numero_verbale", "count": {"$sum": 1}, "ids": {"$push": "$_id"}}},
        {"$match": {"count": {"$gt": 1}}},
    ]
    gruppi = await db["verbali_noleggio"].aggregate(pipeline).to_list(2000)

    gruppi_processati = 0
    documenti_eliminati = 0
    dettaglio = []

    for gruppo in gruppi:
        numero_verbale = gruppo["_id"]
        docs = await db["verbali_noleggio"].find({"numero_verbale": numero_verbale}).to_list(20)
        if len(docs) < 2:
            continue

        docs.sort(
            key=lambda v: (_punteggio_completezza(v), str(v.get("updated_at") or v.get("created_at") or "")),
            reverse=True,
        )
        canonico, duplicati = docs[0], docs[1:]

        campi_mancanti = {}
        for dup in duplicati:
            for k, v in dup.items():
                if k in ("_id",):
                    continue
                if v not in (None, "", []) and canonico.get(k) in (None, "", []):
                    campi_mancanti[k] = v

        gruppi_processati += 1
        documenti_eliminati += len(duplicati)
        dettaglio.append({
            "numero_verbale": numero_verbale,
            "canonico_id": str(canonico["_id"]),
            "duplicati_eliminati": len(duplicati),
            "campi_recuperati": list(campi_mancanti.keys()),
        })

        if not dry_run:
            if campi_mancanti:
                await db["verbali_noleggio"].update_one(
                    {"_id": canonico["_id"]}, {"$set": campi_mancanti}
                )
            await db["verbali_noleggio"].delete_many(
                {"_id": {"$in": [d["_id"] for d in duplicati]}}
            )

    return {
        "dry_run": dry_run,
        "gruppi_duplicati_trovati": len(gruppi),
        "gruppi_processati": gruppi_processati,
        "documenti_eliminati": documenti_eliminati,
        "dettaglio": dettaglio[:50],
    }


@router.post("/riconcilia/{numero_verbale}")
@handle_errors
async def riconcilia_verbale(numero_verbale: str) -> Dict[str, Any]:
    """
    Tenta riconciliazione automatica di un verbale.
    
    Cerca:
    1. Fattura con numero verbale nella descrizione
    2. Pagamento in estratto conto
    3. Veicolo associato
    4. Driver assegnato al veicolo
    """
    db = Database.get_db()
    
    try:
        verbale = await db["verbali_noleggio"].find_one({"numero_verbale": numero_verbale})
        
        if not verbale:
            raise HTTPException(status_code=404, detail="Verbale non trovato")
        
        updates = {}
        messages = []
        
        # 1. Cerca fattura se non presente
        if not verbale.get("fattura_id"):
            fattura = await db["invoices"].find_one({
                "$or": campi_ricerca_verbale_in_fattura(numero_verbale)
            })
            
            if fattura:
                # id canonico UUID (non l'ObjectId _id): tutto il resto dell'app
                # collega le fatture per `id`. Vedi P0.4.
                fattura_id = fattura.get("id") or str(fattura.get("_id"))
                fattura_numero = fattura.get("invoice_number") or fattura.get("numero_fattura")
                fornitore = fattura.get("supplier_name") or fattura.get("fornitore")
                updates.update({
                    "fattura_id": fattura_id,
                    "fattura_associata_id": fattura_id,
                    "fattura_numero": fattura_numero,
                    "fattura_associata_numero": fattura_numero,
                    "numero_fattura": fattura_numero,
                    "fattura_associata_data": fattura.get("invoice_date") or fattura.get("data_documento"),
                    "fattura_associata_importo": fattura.get("total_amount") or fattura.get("importo_totale"),
                    "fornitore": fornitore,
                    "fattura_associata_fornitore": fornitore,
                })
                await db["invoices"].update_one(
                    {"id": fattura_id},
                    {"$addToSet": {"verbali_collegati": numero_verbale}},
                )
                messages.append(f"Fattura trovata: {fattura.get('invoice_number')}")
        
        # 2. Cerca targa se non presente
        targa = verbale.get("targa") or updates.get("targa")
        if not targa:
            # Cerca in verbali_noleggio_completi
            completo = await db["verbali_noleggio_completi"].find_one({"numero_verbale": numero_verbale})
            if completo and completo.get("targa"):
                targa = completo["targa"]
                updates["targa"] = targa
                messages.append(f"Targa trovata: {targa}")
        
        # 3. Cerca veicolo e driver
        if targa:
            veicolo = await db["veicoli_noleggio"].find_one({"targa": targa})
            if veicolo:
                updates["veicolo_id"] = str(veicolo["_id"])
                if veicolo.get("driver_id"):
                    updates["driver_id"] = veicolo["driver_id"]
                    
                    # Trova nome driver (driver_id è un UUID stringa, non ObjectId —
                    # vedi il pattern corretto già usato in associa_verbale_completo
                    # in questo stesso file)
                    driver = await db["dipendenti"].find_one({"id": veicolo["driver_id"]})
                    if driver:
                        updates["driver_nome"] = f"{driver.get('nome', '')} {driver.get('cognome', '')}"
                        messages.append(f"Driver: {updates['driver_nome']}")
        
        # 4. Determina nuovo stato
        has_fattura = verbale.get("fattura_id") or updates.get("fattura_id")
        has_pagamento = (
            verbale.get("pagamento_id")
            or verbale.get("paypal_transaction_id")
            or verbale.get("ricevuta_pagopa_id")
            or verbale.get("movimento_banca_id")
        )
        
        if has_fattura and has_pagamento:
            updates["stato"] = "riconciliato"
        elif has_fattura:
            updates["stato"] = "fattura_ricevuta"
        elif has_pagamento:
            updates["stato"] = "pagato"
        
        # Applica updates
        if updates:
            updates["updated_at"] = datetime.now(timezone.utc)
            await db["verbali_noleggio"].update_one(
                {"numero_verbale": numero_verbale},
                {"$set": updates}
            )
        
        # Ricarica verbale aggiornato
        verbale = await db["verbali_noleggio"].find_one({"numero_verbale": numero_verbale})
        
        return {
            "success": True,
            "numero_verbale": numero_verbale,
            "stato": verbale.get("stato"),
            "azioni": messages,
            "verbale": serialize_doc(verbale)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore riconciliazione verbale: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/collega-driver-massivo")
@handle_errors
async def collega_driver_massivo() -> Dict[str, Any]:
    """
    Collega automaticamente i verbali ai driver con strategia multi-livello:
    
    1. Targa → veicolo_noleggio → driver_id
    2. Targa → storico_assegnazioni_veicoli (driver alla data violazione)
    3. Targa → contratti_noleggio → intestatario/driver
    4. Targa → employees (veicolo_assegnato)
    5. Descrizione verbale → estrae nome/cognome → dipendente
    """
    db = Database.get_db()
    
    try:
        # Trova verbali con targa ma senza driver
        verbali = await db["verbali_noleggio"].find({
            "targa": {"$exists": True, "$nin": [None, ""]},
            "$or": [
                {"driver_id": {"$exists": False}},
                {"driver_id": None},
                {"driver_id": ""}
            ]
        }).to_list(1000)
        
        collegati = 0
        strategie_usate = {"veicolo": 0, "storico": 0, "contratto": 0, "dipendente": 0, "descrizione": 0}
        non_trovati = []
        
        for verbale in verbali:
            targa = (verbale.get("targa") or "").upper()
            data_violazione = verbale.get("data_violazione") or verbale.get("data_verbale")
            numero = verbale.get("numero_verbale", "?")
            
            if not targa:
                continue
            
            driver_id = None
            driver_nome = None
            strategia = None
            
            # === STRATEGIA 1: veicolo_noleggio → driver ===
            veicolo = await db["veicoli_noleggio"].find_one({"targa": targa})
            if veicolo:
                if veicolo.get("driver_id"):
                    driver_id = veicolo["driver_id"]
                    driver_nome = veicolo.get("driver") or veicolo.get("driver_nome")
                    strategia = "veicolo"
                elif veicolo.get("driver"):
                    driver_nome = veicolo["driver"]
                    strategia = "veicolo"
            
            # === STRATEGIA 2: storico assegnazioni (driver alla data della violazione) ===
            if not driver_id and not driver_nome:
                query_storico = {"targa": targa}
                if data_violazione:
                    query_storico["$or"] = [
                        {"data_inizio": {"$lte": data_violazione}, "data_fine": {"$gte": data_violazione}},
                        {"data_inizio": {"$lte": data_violazione}, "data_fine": {"$exists": False}},
                    ]
                
                storico = await db["storico_assegnazioni_veicoli"].find_one(
                    query_storico,
                    sort=[("data_inizio", -1)]
                )
                if storico and (storico.get("driver_id") or storico.get("driver")):
                    driver_id = storico.get("driver_id")
                    driver_nome = storico.get("driver") or storico.get("driver_nome")
                    strategia = "storico"
            
            # === STRATEGIA 3: contratti noleggio ===
            if not driver_id and not driver_nome:
                contratto = await db["contratti_noleggio"].find_one(
                    {"$or": [{"targa": targa}, {"targhe": targa}]}
                )
                if contratto and (contratto.get("driver") or contratto.get("intestatario")):
                    driver_nome = contratto.get("driver") or contratto.get("intestatario")
                    driver_id = contratto.get("driver_id")
                    strategia = "contratto"
            
            # === STRATEGIA 4: dipendenti con veicolo assegnato ===
            if not driver_id and not driver_nome:
                dipendente = await db["dipendenti"].find_one({
                    "$or": [
                        {"veicolo_targa": targa},
                        {"targa_assegnata": targa},
                        {"auto_aziendale": {"$regex": targa, "$options": "i"}}
                    ]
                })
                if not dipendente:
                    dipendente = await db["dipendenti"].find_one({
                        "$or": [
                            {"veicolo_targa": targa},
                            {"targa_assegnata": targa}
                        ]
                    })
                
                if dipendente:
                    driver_id = dipendente.get("id") or str(dipendente.get("_id"))
                    driver_nome = (
                        dipendente.get("nome_completo") or
                        f"{dipendente.get('nome', '')} {dipendente.get('cognome', '')}".strip()
                    )
                    strategia = "dipendente"
            
            # === STRATEGIA 5: cerca nome nella descrizione del verbale ===
            if not driver_id and not driver_nome:
                desc = (verbale.get("descrizione") or verbale.get("note") or "").upper()
                if desc:
                    # Prendi tutti i dipendenti attivi e cerca nome/cognome nel testo
                    all_dip = await db["dipendenti"].find(
                        {"stato": {"$ne": "cessato"}},
                        {"_id": 0, "id": 1, "cognome": 1, "nome": 1, "nome_completo": 1}
                    ).to_list(200)
                    
                    for dip in all_dip:
                        cognome = (dip.get("cognome") or "").upper()
                        if cognome and len(cognome) > 2 and cognome in desc:
                            driver_id = dip.get("id")
                            driver_nome = dip.get("nome_completo") or f"{dip.get('nome', '')} {cognome}"
                            strategia = "descrizione"
                            break
            
            # === APPLICA RISULTATO ===
            if driver_id or driver_nome:
                update_data = {"updated_at": datetime.now(timezone.utc)}
                if driver_id:
                    update_data["driver_id"] = driver_id
                if driver_nome:
                    update_data["driver_nome"] = driver_nome.strip()
                    update_data["driver"] = driver_nome.strip()
                
                await db["verbali_noleggio"].update_one(
                    {"_id": verbale["_id"]},
                    {"$set": update_data}
                )
                collegati += 1
                if strategia:
                    strategie_usate[strategia] = strategie_usate.get(strategia, 0) + 1
            else:
                non_trovati.append({
                    "numero": numero,
                    "targa": targa,
                    "data": data_violazione
                })
        
        return {
            "success": True,
            "verbali_analizzati": len(verbali),
            "collegati_a_driver": collegati,
            "strategie": strategie_usate,
            "non_trovati": non_trovati[:30],
            "non_trovati_count": len(non_trovati)
        }
    except Exception as e:
        logger.error(f"Errore collegamento driver massivo: {e}")
        raise HTTPException(status_code=500, detail=str(e))
