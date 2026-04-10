"""
Learning Machine Router - Riclassificazione Automatica Costi

Questo router gestisce:
1. Riclassificazione automatica fatture per centro di costo
2. Parsing quietanze F24 e assegnazione al centro costo corretto
3. Riconciliazione F24 con estratto conto banca
4. Calcolo automatico costo del personale da cedolini + F24
"""

from fastapi import APIRouter, Query
from typing import Dict, Any, List
from datetime import datetime, timezone
import logging

from app.database import Database, Collections
from app.services.learning_machine_cdc import (
    classifica_fattura_per_centro_costo,
    classifica_f24_per_tributo,
    calcola_importi_fiscali,
    get_tutti_centri_costo
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/learning-cdc", tags=["Learning Machine CDC"])


@router.get("/centri-costo")
async def get_centri_costo() -> List[Dict[str, Any]]:
    """Restituisce l'elenco di tutti i centri di costo configurati."""
    return get_tutti_centri_costo()


@router.post("/riclassifica-fatture")
async def riclassifica_tutte_fatture(
    anno: int = Query(None, description="Anno da riclassificare"),
    forza: bool = Query(False, description="Forza riclassificazione anche se già classificate")
) -> Dict[str, Any]:
    """
    Riclassifica TUTTE le fatture leggendo la descrizione delle linee.
    Assegna ogni fattura al centro di costo corretto con deducibilità/detraibilità.
    """
    db = Database.get_db()
    
    if not anno:
        anno = datetime.now().year
    
    # Query fatture
    query = {
        "$or": [
            {"invoice_date": {"$regex": f"^{anno}"}},
            {"data_ricezione": {"$regex": f"^{anno}"}}
        ]
    }
    
    if not forza:
        # Solo fatture non ancora classificate
        query["centro_costo_id"] = {"$exists": False}
    
    fatture = await db[Collections.INVOICES].find(query).to_list(5000)
    
    risultati = {
        "anno": anno,
        "totale_fatture": len(fatture),
        "classificate": 0,
        "per_centro_costo": {},
        "errori": []
    }
    
    for fatt in fatture:
        try:
            # Estrai dati per classificazione
            supplier = fatt.get("supplier_name", "")
            descrizione = fatt.get("descrizione", "")
            linee = fatt.get("linee", [])
            
            # Classifica
            cdc_id, cdc_config, confidence = classifica_fattura_per_centro_costo(
                supplier, descrizione, linee
            )
            
            # Calcola importi fiscali
            imponibile = fatt.get("imponibile") or (fatt.get("total_amount", 0) - fatt.get("iva", 0))
            iva = fatt.get("iva", 0)
            
            importi = calcola_importi_fiscali(imponibile, iva, cdc_config)
            
            # Aggiorna fattura
            await db[Collections.INVOICES].update_one(
                {"_id": fatt["_id"]},
                {"$set": {
                    "centro_costo_id": cdc_id,
                    "centro_costo_codice": cdc_config["codice"],
                    "centro_costo_nome": cdc_config["nome"],
                    "categoria_bilancio": cdc_config["categoria_bilancio"],
                    "classificazione_confidence": confidence,
                    "percentuale_deducibilita_ires": importi["percentuale_deducibilita_ires"],
                    "percentuale_deducibilita_irap": importi["percentuale_deducibilita_irap"],
                    "percentuale_detraibilita_iva": importi["percentuale_detraibilita_iva"],
                    "imponibile_deducibile_ires": importi["imponibile_deducibile_ires"],
                    "imponibile_indeducibile_ires": importi["imponibile_indeducibile_ires"],
                    "iva_detraibile": importi["iva_detraibile"],
                    "iva_indetraibile": importi["iva_indetraibile"],
                    "classificato_da": "learning_machine",
                    "classificato_il": datetime.now(timezone.utc).isoformat()
                }}
            )
            
            risultati["classificate"] += 1
            
            # Conteggio per centro di costo
            if cdc_id not in risultati["per_centro_costo"]:
                risultati["per_centro_costo"][cdc_id] = {
                    "nome": cdc_config["nome"],
                    "count": 0,
                    "totale_imponibile": 0
                }
            risultati["per_centro_costo"][cdc_id]["count"] += 1
            risultati["per_centro_costo"][cdc_id]["totale_imponibile"] += imponibile
            
        except Exception as e:
            risultati["errori"].append({
                "fattura_id": str(fatt.get("id", fatt.get("_id"))),
                "errore": str(e)
            })
    
    # Arrotonda totali
    for cdc in risultati["per_centro_costo"].values():
        cdc["totale_imponibile"] = round(cdc["totale_imponibile"], 2)
    
    return risultati


@router.post("/processa-quietanza-f24")
async def processa_quietanza_f24(
    tributi: List[Dict[str, Any]],
    data_versamento: str,
    importo_totale: float,
    numero_quietanza: str = None
) -> Dict[str, Any]:
    """
    Processa una quietanza F24 ricevuta dall'Agenzia delle Entrate.
    
    Per ogni tributo:
    1. Identifica il centro di costo
    2. Registra il costo
    3. Cerca il movimento bancario corrispondente per riconciliare
    
    Args:
        tributi: Lista di dict con {codice_tributo, periodo, importo}
        data_versamento: Data versamento (YYYY-MM-DD)
        importo_totale: Importo totale F24
        numero_quietanza: Numero quietanza opzionale
    
    Esempio tributi:
        [
            {"codice_tributo": "6001", "periodo": "01/2025", "importo": 1500.00},  # IVA gennaio
            {"codice_tributo": "1001", "periodo": "01/2025", "importo": 800.00},   # Ritenute dip.
            {"codice_tributo": "DM10", "periodo": "01/2025", "importo": 2000.00}   # INPS
        ]
    """
    db = Database.get_db()
    
    risultato = {
        "data_versamento": data_versamento,
        "importo_totale": importo_totale,
        "numero_quietanza": numero_quietanza,
        "tributi_processati": [],
        "riconciliazione_banca": None
    }
    
    for tributo in tributi:
        codice = tributo.get("codice_tributo", "")
        periodo = tributo.get("periodo", "")
        importo = tributo.get("importo", 0)
        
        # Classifica per centro di costo
        cdc_id, cdc_config = classifica_f24_per_tributo(codice)
        
        # Registra in collezione f24_quietanze
        doc = {
            "codice_tributo": codice,
            "periodo": periodo,
            "importo": importo,
            "data_versamento": data_versamento,
            "numero_quietanza": numero_quietanza,
            "centro_costo_id": cdc_id,
            "centro_costo_nome": cdc_config["nome"],
            "categoria_bilancio": cdc_config["categoria_bilancio"],
            "processato_il": datetime.now(timezone.utc).isoformat()
        }
        
        await db["f24_quietanze"].insert_one(doc)
        
        risultato["tributi_processati"].append({
            "codice_tributo": codice,
            "descrizione": _descrizione_tributo(codice),
            "importo": importo,
            "centro_costo": cdc_config["nome"]
        })
    
    # Cerca movimento bancario per riconciliazione
    # L'F24 appare come "DELEGA F24" o simile in banca
    movimento = await db["prima_nota_banca"].find_one({
        "data": data_versamento,
        "$or": [
            {"importo": -importo_totale},
            {"importo": importo_totale * -1}
        ],
        "$or": [
            {"descrizione": {"$regex": "f24", "$options": "i"}},
            {"causale": {"$regex": "f24|delega|agenzia entrate", "$options": "i"}}
        ]
    })
    
    if movimento:
        # Riconcilia
        await db["prima_nota_banca"].update_one(
            {"_id": movimento["_id"]},
            {"$set": {
                "riconciliato": True,
                "riconciliato_con": "f24_quietanza",
                "numero_quietanza": numero_quietanza,
                "riconciliato_il": datetime.now(timezone.utc).isoformat()
            }}
        )
        risultato["riconciliazione_banca"] = {
            "trovato": True,
            "movimento_id": str(movimento.get("id", movimento.get("_id"))),
            "importo": movimento.get("importo")
        }
    else:
        risultato["riconciliazione_banca"] = {
            "trovato": False,
            "nota": "Movimento bancario non trovato. Verificare estratto conto."
        }
    
    return risultato


@router.get("/costo-personale-completo/{anno}")
async def calcola_costo_personale_completo(anno: int) -> Dict[str, Any]:
    """
    Calcola il costo del personale completo per l'anno:
    1. Dai cedolini (stipendi lordi)
    2. Dagli F24 (contributi INPS, ritenute)
    3. Dai bonifici stipendi
    
    Riconcilia tutto per avere un quadro completo del centro di costo B9.
    """
    db = Database.get_db()
    
    # 1. CEDOLINI
    cedolini = await db["cedolini"].aggregate([
        {"$match": {"$or": [{"anno": anno}, {"anno": str(anno)}]}},
        {"$group": {
            "_id": None,
            "totale_lordo": {"$sum": {"$ifNull": ["$lordo", 0]}},
            "totale_netto": {"$sum": {"$ifNull": ["$netto", 0]}},
            "totale_inps_dip": {"$sum": {"$ifNull": ["$inps_dipendente", 0]}},
            "totale_inps_az": {"$sum": {"$ifNull": ["$inps_azienda", 0]}},
            "totale_inail": {"$sum": {"$ifNull": ["$inail", 0]}},
            "totale_tfr": {"$sum": {"$ifNull": ["$tfr", 0]}},
            "totale_irpef": {"$sum": {"$ifNull": ["$irpef", 0]}},
            "totale_costo_azienda": {"$sum": {"$ifNull": ["$costo_azienda", 0]}},
            "num_cedolini": {"$sum": 1}
        }}
    ]).to_list(1)
    
    # 2. F24 QUIETANZE - tributi personale
    tributi_personale = ["1001", "1002", "1012", "DM10"]
    f24_personale = await db["f24_quietanze"].aggregate([
        {"$match": {
            "codice_tributo": {"$in": tributi_personale},
            "data_versamento": {"$regex": f"^{anno}"}
        }},
        {"$group": {
            "_id": "$codice_tributo",
            "totale": {"$sum": "$importo"},
            "count": {"$sum": 1}
        }}
    ]).to_list(10)
    
    # 3. BONIFICI STIPENDI
    bonifici = await db["bonifici_stipendi"].aggregate([
        {"$match": {"data_operazione": {"$regex": f"^{anno}"}}},
        {"$group": {
            "_id": None,
            "totale_pagato": {"$sum": "$importo"},
            "num_bonifici": {"$sum": 1}
        }}
    ]).to_list(1)
    
    # Costruisci risultato
    ced = cedolini[0] if cedolini else {}
    bon = bonifici[0] if bonifici else {}
    
    # Calcola costo totale
    lordo = ced.get("totale_lordo", 0)
    inps_azienda = ced.get("totale_inps_az", 0) or (lordo * 0.30)  # Stima 30% se mancante
    inail = ced.get("totale_inail", 0)
    tfr = ced.get("totale_tfr", 0) or (lordo * 0.0691)
    
    costo_totale = lordo + inps_azienda + inail + tfr
    
    return {
        "anno": anno,
        "centro_costo": "B9 - Costo del personale",
        "deducibilita_ires": "100%",
        "deducibilita_irap": "Variabile (cuneo fiscale)",
        "iva": "Fuori campo",
        
        "da_cedolini": {
            "num_cedolini": ced.get("num_cedolini", 0),
            "B9a_salari_stipendi_lordi": round(lordo, 2),
            "B9b_oneri_sociali": {
                "inps_carico_azienda": round(inps_azienda, 2),
                "inail": round(inail, 2),
                "totale": round(inps_azienda + inail, 2)
            },
            "B9c_tfr": round(tfr, 2)
        },
        
        "da_f24_quietanze": {
            tributo["_id"]: {
                "importo": round(tributo["totale"], 2),
                "num_versamenti": tributo["count"],
                "descrizione": _descrizione_tributo(tributo["_id"])
            }
            for tributo in f24_personale
        },
        
        "da_bonifici": {
            "totale_pagato_netto": round(bon.get("totale_pagato", 0), 2),
            "num_bonifici": bon.get("num_bonifici", 0)
        },
        
        "riepilogo": {
            "costo_totale_azienda": round(costo_totale, 2),
            "di_cui_stipendi_lordi": round(lordo, 2),
            "di_cui_oneri": round(inps_azienda + inail, 2),
            "di_cui_tfr": round(tfr, 2)
        },
        
        "riconciliazione": {
            "netto_cedolini": round(ced.get("totale_netto", 0), 2),
            "pagato_bonifici": round(bon.get("totale_pagato", 0), 2),
            "differenza": round(ced.get("totale_netto", 0) - bon.get("totale_pagato", 0), 2),
            "status": "OK" if abs(ced.get("totale_netto", 0) - bon.get("totale_pagato", 0)) < 100 else "DA VERIFICARE"
        }
    }


@router.get("/riepilogo-centri-costo/{anno}")
async def riepilogo_centri_costo(anno: int) -> Dict[str, Any]:
    """
    Riepilogo completo di tutti i costi per centro di costo.
    Include deducibilità IRES/IRAP e IVA detraibile per ogni centro.
    """
    db = Database.get_db()
    
    # Aggrega fatture per centro di costo
    pipeline = [
        {"$match": {
            "centro_costo_id": {"$exists": True},
            "$or": [
                {"invoice_date": {"$regex": f"^{anno}"}},
                {"data_ricezione": {"$regex": f"^{anno}"}}
            ]
        }},
        {"$group": {
            "_id": "$centro_costo_id",
            "nome": {"$first": "$centro_costo_nome"},
            "codice": {"$first": "$centro_costo_codice"},
            "categoria": {"$first": "$categoria_bilancio"},
            "totale_imponibile": {"$sum": {"$ifNull": ["$imponibile", {"$subtract": ["$total_amount", {"$ifNull": ["$iva", 0]}]}]}},
            "totale_iva": {"$sum": {"$ifNull": ["$iva", 0]}},
            "totale_deducibile_ires": {"$sum": "$imponibile_deducibile_ires"},
            "totale_indeducibile_ires": {"$sum": "$imponibile_indeducibile_ires"},
            "totale_iva_detraibile": {"$sum": "$iva_detraibile"},
            "totale_iva_indetraibile": {"$sum": "$iva_indetraibile"},
            "num_fatture": {"$sum": 1}
        }},
        {"$sort": {"totale_imponibile": -1}}
    ]
    
    centri = await db[Collections.INVOICES].aggregate(pipeline).to_list(50)
    
    # Totali
    totale_imponibile = sum(c["totale_imponibile"] for c in centri)
    totale_iva = sum(c["totale_iva"] for c in centri)
    totale_deducibile = sum(c.get("totale_deducibile_ires", c["totale_imponibile"]) for c in centri)
    totale_indeducibile = sum(c.get("totale_indeducibile_ires", 0) for c in centri)
    totale_iva_detr = sum(c.get("totale_iva_detraibile", c["totale_iva"]) for c in centri)
    totale_iva_indetr = sum(c.get("totale_iva_indetraibile", 0) for c in centri)
    
    return {
        "anno": anno,
        "centri_costo": [
            {
                "id": c["_id"],
                "codice": c["codice"],
                "nome": c["nome"],
                "categoria_bilancio": c["categoria"],
                "num_fatture": c["num_fatture"],
                "totale_imponibile": round(c["totale_imponibile"], 2),
                "totale_iva": round(c["totale_iva"], 2),
                "deducibile_ires": round(c.get("totale_deducibile_ires", c["totale_imponibile"]), 2),
                "indeducibile_ires": round(c.get("totale_indeducibile_ires", 0), 2),
                "iva_detraibile": round(c.get("totale_iva_detraibile", c["totale_iva"]), 2),
                "iva_indetraibile": round(c.get("totale_iva_indetraibile", 0), 2)
            }
            for c in centri
        ],
        "totali": {
            "imponibile": round(totale_imponibile, 2),
            "iva": round(totale_iva, 2),
            "deducibile_ires": round(totale_deducibile, 2),
            "indeducibile_ires": round(totale_indeducibile, 2),
            "iva_detraibile": round(totale_iva_detr, 2),
            "iva_indetraibile": round(totale_iva_indetr, 2)
        }
    }


def _descrizione_tributo(codice: str) -> str:
    """Restituisce la descrizione del codice tributo."""
    descrizioni = {
        "6001": "IVA Gennaio",
        "6002": "IVA Febbraio",
        "6003": "IVA Marzo",
        "6004": "IVA Aprile",
        "6005": "IVA Maggio",
        "6006": "IVA Giugno",
        "6007": "IVA Luglio",
        "6008": "IVA Agosto",
        "6009": "IVA Settembre",
        "6010": "IVA Ottobre",
        "6011": "IVA Novembre",
        "6012": "IVA Dicembre",
        "6099": "IVA Annuale",
        "1001": "Ritenute lavoro dipendente",
        "1002": "Ritenute su TFR",
        "1012": "Ritenute indennità",
        "1040": "Ritenute lavoro autonomo",
        "DM10": "Contributi INPS dipendenti",
        "3918": "IMU",
        "3930": "IMU fabbricati rurali",
        "3944": "TARI"
    }
    return descrizioni.get(codice, f"Tributo {codice}")
