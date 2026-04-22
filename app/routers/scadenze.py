"""
Scadenze e Notifiche Router - Sistema alert per scadenze fiscali e pagamenti

Gestisce:
- Scadenze IVA trimestrali (16 del mese successivo al trimestre)
- Scadenze F24 (16 di ogni mese)
- Fatture in scadenza (pagamento entro X giorni)
- Notifiche personalizzate
"""

from fastapi import APIRouter, Query, HTTPException, Body
from typing import Dict, Any, List, Optional
from datetime import datetime, date, timedelta, timezone
from app.database import Database, Collections
import logging
import uuid
from app.utils.error_handler import handle_errors

logger = logging.getLogger(__name__)
router = APIRouter()

# Scadenze fiscali fisse italiane
SCADENZE_FISCALI = {
    "iva_q1": {"mese": 5, "giorno": 16, "descrizione": "Versamento IVA 1° Trimestre", "tipo": "IVA"},
    "iva_q2": {"mese": 8, "giorno": 20, "descrizione": "Versamento IVA 2° Trimestre", "tipo": "IVA"},  # 20 agosto
    "iva_q3": {"mese": 11, "giorno": 16, "descrizione": "Versamento IVA 3° Trimestre", "tipo": "IVA"},
    "iva_q4": {"mese": 3, "giorno": 16, "descrizione": "Versamento IVA 4° Trimestre (anno prec.)", "tipo": "IVA"},
    "f24_mensile": {"giorno": 16, "descrizione": "Versamento F24 mensile", "tipo": "F24"},
    "inps": {"giorno": 16, "descrizione": "Versamento contributi INPS", "tipo": "INPS"},
    "irpef": {"giorno": 16, "descrizione": "Versamento ritenute IRPEF", "tipo": "IRPEF"},
}


@router.get("/tutte")
@handle_errors
async def get_tutte_scadenze(
    anno: int = Query(None),
    mese: int = Query(None),
    tipo: str = Query(None, description="Filtra per tipo: IVA, F24, FATTURA, INPS"),
    include_passate: bool = Query(False),
    limit: int = Query(20)
) -> Dict[str, Any]:
    """
    Ottiene tutte le scadenze (fiscali + fatture da pagare + notifiche custom).
    """
    db = Database.get_db()
    oggi = date.today()
    
    if not anno:
        anno = oggi.year
    if not mese:
        mese = oggi.month
    
    scadenze = []
    
    # 1. Scadenze fiscali fisse
    scadenze_fiscali = _genera_scadenze_fiscali(anno, mese, include_passate)
    if tipo:
        scadenze_fiscali = [s for s in scadenze_fiscali if s["tipo"] == tipo]
    scadenze.extend(scadenze_fiscali)
    
    # 2. Fatture da pagare (scadenza pagamento)
    if not tipo or tipo == "FATTURA":
        fatture_scadenza = await _get_fatture_in_scadenza(db, anno, include_passate)
        scadenze.extend(fatture_scadenza)
    
    # 3. Notifiche custom salvate
    notifiche_custom = await db["notifiche_scadenze"].find(
        {"completata": False} if not include_passate else {},
        {"_id": 0}
    ).to_list(100)
    
    for n in notifiche_custom:
        scadenze.append({
            "id": n.get("id"),
            "data": n.get("data_scadenza"),
            "tipo": n.get("tipo", "CUSTOM"),
            "descrizione": n.get("descrizione"),
            "importo": n.get("importo"),
            "priorita": n.get("priorita", "media"),
            "completata": n.get("completata", False),
            "source": "custom"
        })
    
    # Ordina per data
    scadenze.sort(key=lambda x: x.get("data", "9999-99-99"))
    
    # Filtra passate se richiesto
    if not include_passate:
        scadenze = [s for s in scadenze if s.get("data", "9999-99-99") >= oggi.isoformat()]
    
    # Calcola statistiche
    urgenti = [s for s in scadenze if _is_urgente(s.get("data"))]
    prossime_7gg = [s for s in scadenze if _is_prossimi_giorni(s.get("data"), 7)]
    
    return {
        "scadenze": scadenze[:limit],
        "totale": len(scadenze),
        "statistiche": {
            "urgenti": len(urgenti),
            "prossimi_7_giorni": len(prossime_7gg),
            "totale_importo": sum(s.get("importo", 0) or 0 for s in scadenze if s.get("importo"))
        }
    }


@router.get("/prossime")
@handle_errors
async def get_prossime_scadenze(
    giorni: int = Query(30, description="Giorni futuri da considerare"),
    limit: int = Query(10)
) -> Dict[str, Any]:
    """
    Ottiene le prossime scadenze entro N giorni.
    Endpoint ottimizzato per widget dashboard.
    """
    db = Database.get_db()
    oggi = date.today()
    data_limite = (oggi + timedelta(days=giorni)).isoformat()
    
    scadenze = []
    
    # Scadenze fiscali
    for i in range(giorni // 30 + 2):  # Prossimi mesi
        mese = (oggi.month + i - 1) % 12 + 1
        anno = oggi.year + (oggi.month + i - 1) // 12
        scadenze_mese = _genera_scadenze_fiscali(anno, mese, False)
        scadenze.extend(scadenze_mese)
    
    # Fatture in scadenza
    fatture = await _get_fatture_in_scadenza(db, oggi.year, False, giorni)
    scadenze.extend(fatture)
    
    # Notifiche custom non completate
    notifiche = await db["notifiche_scadenze"].find(
        {
            "completata": False,
            "data_scadenza": {"$lte": data_limite}
        },
        {"_id": 0}
    ).to_list(50)
    
    for n in notifiche:
        scadenze.append({
            "id": n.get("id"),
            "data": n.get("data_scadenza"),
            "tipo": n.get("tipo", "CUSTOM"),
            "descrizione": n.get("descrizione"),
            "importo": n.get("importo"),
            "priorita": _calcola_priorita(n.get("data_scadenza")),
            "source": "custom"
        })
    
    # Filtra e ordina
    scadenze = [s for s in scadenze if oggi.isoformat() <= s.get("data", "9999") <= data_limite]
    scadenze.sort(key=lambda x: x.get("data", "9999"))
    
    # Aggiungi info urgenza
    for s in scadenze:
        s["giorni_mancanti"] = _giorni_mancanti(s.get("data"))
        s["urgente"] = s["giorni_mancanti"] <= 3 if s["giorni_mancanti"] is not None else False
    
    return {
        "scadenze": scadenze[:limit],
        "totale": len(scadenze),
        "prossima_scadenza": scadenze[0] if scadenze else None
    }


@router.get("/iva/{anno}")
@handle_errors
async def get_scadenze_iva(anno: int) -> Dict[str, Any]:
    """
    Ottiene le scadenze IVA per un anno con importi calcolati.
    """
    db = Database.get_db()
    
    scadenze_iva = []
    
    for q in range(1, 5):
        # Calcola importo IVA trimestre
        start_month = (q - 1) * 3 + 1
        end_month = q * 3
        
        # IVA Debito (corrispettivi)
        iva_debito = 0
        for m in range(start_month, end_month + 1):
            prefix = f"{anno}-{m:02d}"
            result = await db["corrispettivi"].aggregate([
                {"$match": {"data": {"$regex": f"^{prefix}"}}},
                {"$group": {"_id": None, "totale": {"$sum": "$totale_iva"}}}
            ]).to_list(1)
            iva_debito += result[0]["totale"] if result else 0
        
        # IVA Credito (fatture)
        iva_credito = 0
        for m in range(start_month, end_month + 1):
            prefix = f"{anno}-{m:02d}"
            result = await db[Collections.INVOICES].aggregate([
                {"$match": {
                    "$or": [
                        {"data_ricezione": {"$regex": f"^{prefix}"}},
                        {"invoice_date": {"$regex": f"^{prefix}"}}
                    ]
                }},
                {"$group": {"_id": None, "totale": {"$sum": "$iva"}}}
            ]).to_list(1)
            iva_credito += result[0]["totale"] if result else 0
        
        saldo = iva_debito - iva_credito
        
        # Data scadenza
        if q == 1:
            data_scad = f"{anno}-05-16"
        elif q == 2:
            data_scad = f"{anno}-08-20"  # 20 agosto
        elif q == 3:
            data_scad = f"{anno}-11-16"
        else:
            data_scad = f"{anno + 1}-03-16"
        
        scadenze_iva.append({
            "trimestre": q,
            "periodo": f"Q{q} {anno}",
            "data_scadenza": data_scad,
            "iva_debito": round(iva_debito, 2),
            "iva_credito": round(iva_credito, 2),
            "saldo": round(saldo, 2),
            "da_versare": saldo > 0,
            "importo_versamento": round(max(saldo, 0), 2),
            "a_credito": round(abs(min(saldo, 0)), 2),  # Importo a credito quando saldo < 0
            "stato": "da_versare" if saldo > 0 else "a_credito",
            "giorni_mancanti": _giorni_mancanti(data_scad)
        })
    
    totale_da_versare = sum(s["importo_versamento"] for s in scadenze_iva)
    
    return {
        "anno": anno,
        "scadenze": scadenze_iva,
        "totale_da_versare": round(totale_da_versare, 2),
        "prossima_scadenza": next((s for s in scadenze_iva if s["giorni_mancanti"] and s["giorni_mancanti"] > 0), None)
    }



@router.get("/iva-mensile/{anno}")
@handle_errors
async def get_scadenze_iva_mensile(anno: int) -> Dict[str, Any]:
    """
    Ottiene le scadenze IVA mensili per un anno.
    Per regime IVA mensile: versamento entro il 16 del mese successivo.
    """
    db = Database.get_db()
    
    scadenze_mensili = []
    
    for mese in range(1, 13):
        prefix = f"{anno}-{mese:02d}"
        
        # IVA Debito (corrispettivi)
        result_debito = await db["corrispettivi"].aggregate([
            {"$match": {"data": {"$regex": f"^{prefix}"}}},
            {"$group": {"_id": None, "totale": {"$sum": "$totale_iva"}}}
        ]).to_list(1)
        iva_debito = result_debito[0]["totale"] if result_debito else 0
        
        # IVA Credito (fatture)
        result_credito = await db[Collections.INVOICES].aggregate([
            {"$match": {
                "$or": [
                    {"data_ricezione": {"$regex": f"^{prefix}"}},
                    {"invoice_date": {"$regex": f"^{prefix}"}}
                ]
            }},
            {"$group": {"_id": None, "totale": {"$sum": "$iva"}}}
        ]).to_list(1)
        iva_credito = result_credito[0]["totale"] if result_credito else 0
        
        saldo = iva_debito - iva_credito
        
        # Data scadenza: 16 del mese successivo
        if mese == 12:
            data_scad = f"{anno + 1}-01-16"
        else:
            data_scad = f"{anno}-{mese + 1:02d}-16"
        
        mesi_nomi = ['', 'Gennaio', 'Febbraio', 'Marzo', 'Aprile', 'Maggio', 'Giugno',
                    'Luglio', 'Agosto', 'Settembre', 'Ottobre', 'Novembre', 'Dicembre']
        
        scadenze_mensili.append({
            "mese": mese,
            "mese_nome": mesi_nomi[mese],
            "periodo": f"{mesi_nomi[mese]} {anno}",
            "data_scadenza": data_scad,
            "iva_debito": round(iva_debito, 2),
            "iva_credito": round(iva_credito, 2),
            "saldo": round(saldo, 2),
            "da_versare": saldo > 0,
            "importo_versamento": round(max(saldo, 0), 2),
            "a_credito": round(abs(min(saldo, 0)), 2),  # Importo a credito quando saldo < 0
            "stato": "da_versare" if saldo > 0 else "a_credito",
            "giorni_mancanti": _giorni_mancanti(data_scad)
        })
    
    totale_da_versare = sum(s["importo_versamento"] for s in scadenze_mensili)
    totale_a_credito = sum(abs(s["saldo"]) for s in scadenze_mensili if s["saldo"] < 0)
    
    # Calcola saldo progressivo con riporto credito dal mese precedente
    saldo_progressivo = 0.0
    for s in scadenze_mensili:
        saldo_progressivo = round(saldo_progressivo + s["saldo"], 2)
        s["saldo_progressivo"] = saldo_progressivo
        # Il versamento F24 è dovuto solo se il progressivo è positivo
        if saldo_progressivo > 0.005:
            s["da_versare_effettivo"] = True
            s["importo_versamento_effettivo"] = round(saldo_progressivo, 2)
        else:
            s["da_versare_effettivo"] = False
            s["importo_versamento_effettivo"] = 0.0
    
    return {
        "anno": anno,
        "regime": "mensile",
        "scadenze": scadenze_mensili,
        "totale_da_versare": round(totale_da_versare, 2),
        "totale_a_credito": round(totale_a_credito, 2),
        "saldo_annuale": round(totale_da_versare - totale_a_credito, 2),
        "saldo_progressivo": round(saldo_progressivo, 2)
    }



@router.post("/crea")
@handle_errors
async def crea_notifica_scadenza(data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """
    Crea una notifica/scadenza personalizzata.
    """
    db = Database.get_db()
    
    required = ["data_scadenza", "descrizione"]
    for field in required:
        if not data.get(field):
            raise HTTPException(status_code=400, detail=f"Campo {field} obbligatorio")
    
    notifica = {
        "id": str(uuid.uuid4()),
        "data_scadenza": data["data_scadenza"],
        "descrizione": data["descrizione"],
        "tipo": data.get("tipo", "CUSTOM"),
        "importo": float(data.get("importo", 0) or 0),
        "priorita": data.get("priorita", "media"),
        "note": data.get("note", ""),
        "completata": False,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db["notifiche_scadenze"].insert_one(notifica.copy())
    notifica.pop("_id", None)
    
    return {"success": True, "notifica": notifica}


@router.put("/completa/{notifica_id}")
@handle_errors
async def completa_notifica(notifica_id: str) -> Dict[str, Any]:
    """Segna una notifica come completata."""
    db = Database.get_db()
    
    result = await db["notifiche_scadenze"].update_one(
        {"id": notifica_id},
        {"$set": {"completata": True, "completata_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Notifica non trovata")
    
    return {"success": True, "message": "Notifica completata"}


@router.delete("/{notifica_id}")
@handle_errors
async def elimina_notifica(notifica_id: str) -> Dict[str, Any]:
    """Elimina una notifica personalizzata."""
    db = Database.get_db()
    
    result = await db["notifiche_scadenze"].delete_one({"id": notifica_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Notifica non trovata")
    
    return {"success": True, "message": "Notifica eliminata"}


# Helper functions

def _genera_scadenze_fiscali(anno: int, mese: int, include_passate: bool) -> List[Dict]:
    """Genera scadenze fiscali per un mese specifico."""
    oggi = date.today()
    scadenze = []
    
    # F24/INPS/IRPEF mensile (16 del mese)
    data_16 = f"{anno}-{mese:02d}-16"
    if include_passate or data_16 >= oggi.isoformat():
        scadenze.append({
            "data": data_16,
            "tipo": "F24",
            "descrizione": f"Versamento F24 - {_nome_mese(mese)} {anno}",
            "priorita": _calcola_priorita(data_16),
            "source": "fiscale"
        })
    
    # IVA trimestrale
    if mese == 5:  # Q1
        data = f"{anno}-05-16"
        if include_passate or data >= oggi.isoformat():
            scadenze.append({
                "data": data,
                "tipo": "IVA",
                "descrizione": f"IVA 1° Trimestre {anno}",
                "priorita": _calcola_priorita(data),
                "source": "fiscale"
            })
    elif mese == 8:  # Q2
        data = f"{anno}-08-20"
        if include_passate or data >= oggi.isoformat():
            scadenze.append({
                "data": data,
                "tipo": "IVA",
                "descrizione": f"IVA 2° Trimestre {anno}",
                "priorita": _calcola_priorita(data),
                "source": "fiscale"
            })
    elif mese == 11:  # Q3
        data = f"{anno}-11-16"
        if include_passate or data >= oggi.isoformat():
            scadenze.append({
                "data": data,
                "tipo": "IVA",
                "descrizione": f"IVA 3° Trimestre {anno}",
                "priorita": _calcola_priorita(data),
                "source": "fiscale"
            })
    elif mese == 3:  # Q4 anno precedente
        data = f"{anno}-03-16"
        if include_passate or data >= oggi.isoformat():
            scadenze.append({
                "data": data,
                "tipo": "IVA",
                "descrizione": f"IVA 4° Trimestre {anno - 1}",
                "priorita": _calcola_priorita(data),
                "source": "fiscale"
            })
    
    return scadenze


async def _get_fatture_in_scadenza(db, anno: int, include_passate: bool, giorni_limite: int = 60) -> List[Dict]:
    """Ottiene fatture con scadenza pagamento imminente."""
    oggi = date.today()
    data_limite = (oggi + timedelta(days=giorni_limite)).isoformat()
    
    query = {
        "pagato": {"$ne": True},
        "status": {"$ne": "paid"},
        "stato_pagamento": {"$nin": ["pagata", "pagato"]},
        "$or": [
            {"data_ricezione": {"$regex": f"^{anno}"}},
            {"invoice_date": {"$regex": f"^{anno}"}}
        ]
    }
    
    fatture = await db[Collections.INVOICES].find(query, {"_id": 0}).limit(100).to_list(100)
    
    scadenze = []
    for f in fatture:
        # Calcola data scadenza (default 30 giorni da data fattura)
        data_fatt = f.get("data_ricezione") or f.get("invoice_date") or ""
        if not data_fatt:
            continue
        
        try:
            dt = datetime.strptime(data_fatt[:10], "%Y-%m-%d")
            data_scadenza = (dt + timedelta(days=30)).strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            continue
        
        if not include_passate and data_scadenza < oggi.isoformat():
            continue
        if data_scadenza > data_limite:
            continue
        
        # Estrai nome fornitore da tutti i campi possibili
        fornitore = (
            f.get("supplier_name") or 
            f.get("cedente_denominazione") or
            (f.get("cedente_prestatore", {}) or {}).get("denominazione", "") or
            (f.get("fornitore", {}) or {}).get("denominazione", "") or
            (f.get("fornitore", {}) or {}).get("ragione_sociale", "") or
            ""
        )
        importo_raw = f.get("total_amount") or f.get("importo_totale") or f.get("importo") or f.get("totale_documento") or 0
        try:
            importo = abs(float(importo_raw)) if importo_raw else 0
        except (ValueError, TypeError):
            importo = 0
        numero_fatt = f.get("invoice_number") or f.get("numero_documento") or f.get("numero_fattura", "")
        fattura_id = f.get("id")
        
        scadenze.append({
            "id": f.get("id"),
            "data": data_scadenza,
            "tipo": "FATTURA",
            "descrizione": f"Pagamento fattura {numero_fatt}",
            "importo": importo,
            "priorita": _calcola_priorita(data_scadenza),
            "fornitore": fornitore,
            "numero_fattura": numero_fatt,
            "fattura_id": fattura_id,  # Per il link "Vedi"
            "source": "fattura"
        })
    
    return scadenze


def _calcola_priorita(data_str: str) -> str:
    """Calcola priorità in base ai giorni mancanti."""
    giorni = _giorni_mancanti(data_str)
    if giorni is None:
        return "bassa"
    if giorni <= 3:
        return "critica"
    if giorni <= 7:
        return "alta"
    if giorni <= 14:
        return "media"
    return "bassa"


def _giorni_mancanti(data_str: str) -> Optional[int]:
    """Calcola giorni mancanti alla scadenza."""
    if not data_str:
        return None
    try:
        data = datetime.strptime(data_str[:10], "%Y-%m-%d").date()
        return (data - date.today()).days
    except (ValueError, TypeError):
        return None


def _is_urgente(data_str: str) -> bool:
    """Verifica se la scadenza è urgente (entro 3 giorni)."""
    giorni = _giorni_mancanti(data_str)
    return giorni is not None and giorni <= 3


def _is_prossimi_giorni(data_str: str, giorni: int) -> bool:
    """Verifica se la scadenza è entro N giorni."""
    g = _giorni_mancanti(data_str)
    return g is not None and 0 <= g <= giorni


def _nome_mese(mese: int) -> str:
    """Restituisce nome mese in italiano."""
    nomi = ["", "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
            "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]
    return nomi[mese] if 1 <= mese <= 12 else ""


@router.get("/dashboard-widget")
@handle_errors
async def get_dashboard_scadenze() -> Dict[str, Any]:
    """
    Widget scadenze per dashboard - riepilogo compatto.
    Ritorna le scadenze più urgenti di ogni tipo.
    """
    db = Database.get_db()
    oggi = datetime.now(timezone.utc)
    oggi_str = oggi.strftime('%Y-%m-%d')
    limite_30 = (oggi + timedelta(days=30)).strftime('%Y-%m-%d')
    limite_60 = (oggi + timedelta(days=60)).strftime('%Y-%m-%d')
    
    # Fatture da pagare
    fatture_urgenti = await db[Collections.INVOICES].count_documents({
        "data_scadenza": {"$lte": limite_30},
        "stato_pagamento": {"$in": ["non_pagata", "da_pagare", None]}
    })
    
    # Contratti in scadenza
    contratti_scadenza = await db["contratti_dipendenti"].count_documents({
        "data_fine": {"$lte": limite_60, "$gte": oggi_str},
        "stato": "attivo"
    })
    
    # Libretti scaduti o in scadenza
    libretti_scaduti = await db["libretti_sanitari"].count_documents({
        "data_scadenza": {"$lt": oggi_str}
    })
    libretti_in_scadenza = await db["libretti_sanitari"].count_documents({
        "data_scadenza": {"$gte": oggi_str, "$lte": limite_30}
    })
    
    # F24 da pagare
    f24_da_pagare = await db["f24_unificato"].count_documents({
        "data_scadenza": {"$lte": limite_30},
        "pagato": {"$ne": True}
    })
    
    # Scadenze fiscali prossime
    scadenze_fiscali = _genera_scadenze_fiscali(oggi.year, oggi.month, False)
    scadenze_urgenti = [s for s in scadenze_fiscali if _is_prossimi_giorni(s.get("data", s.get("data_scadenza", "")), 15)]
    
    totale_alert = (
        (1 if fatture_urgenti > 0 else 0) +
        (1 if contratti_scadenza > 0 else 0) +
        (1 if libretti_scaduti > 0 else 0) +
        (1 if libretti_in_scadenza > 0 else 0) +
        (1 if f24_da_pagare > 0 else 0) +
        len(scadenze_urgenti)
    )
    
    return {
        "totale_alert": totale_alert,
        "fatture": {
            "da_pagare_30gg": fatture_urgenti,
            "urgenza": "alta" if fatture_urgenti > 5 else "media" if fatture_urgenti > 0 else "bassa"
        },
        "contratti": {
            "in_scadenza_60gg": contratti_scadenza,
            "urgenza": "alta" if contratti_scadenza > 2 else "media" if contratti_scadenza > 0 else "bassa"
        },
        "libretti_sanitari": {
            "scaduti": libretti_scaduti,
            "in_scadenza_30gg": libretti_in_scadenza,
            "urgenza": "alta" if libretti_scaduti > 0 else "media" if libretti_in_scadenza > 0 else "bassa"
        },
        "f24": {
            "da_pagare_30gg": f24_da_pagare,
            "urgenza": "alta" if f24_da_pagare > 0 else "bassa"
        },
        "fiscali": {
            "prossime": len(scadenze_urgenti),
            "dettaglio": scadenze_urgenti[:3]
        }
    }
