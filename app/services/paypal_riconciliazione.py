"""
Servizio di Riconciliazione PayPal con Fatture Ricevute

Logica:
1. Importa pagamenti da estratto conto PayPal (CSV o lista manuale)
2. Cerca corrispondenze con fatture ricevute per:
   - Importo esatto
   - Nome fornitore simile
   - Data compatibile
3. Aggiorna le fatture come "pagate via PayPal"
"""

import re
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)


# Mappatura beneficiari PayPal → Fornitori nel sistema
PAYPAL_TO_FORNITORE_MAP = {
    "infocert spa": ["infocert", "info cert"],
    "spotify ab": ["spotify"],
    "intesa sanpaolo": ["intesa", "sanpaolo"],
    "aruba spa": ["aruba"],
    "register spa": ["register"],
    "hp italy": ["hp", "hewlett"],
    "adobe": ["adobe"],
    "f.lli casolaro": ["casolaro", "f.lli casolaro", "casolaro hotellerie"],
    "elmax srl": ["elmax"],
    "erredi forniture": ["erredi"],
    "detertecnica": ["detertecnica"],
    "ristofast": ["ristofast"],
    "nuova bever-li": ["beverli", "bever-li", "nuova bever"],
    "erretre": ["erretre", "erre4m"],
    "laspillatura": ["laspillatura", "spillatura"],
    "coltelleria zoppi": ["zoppi", "coltelleria"],
    "bellerofonte": ["bellerofonte"],
    "timbri.it": ["timbri"],
    "indors": ["indors"],
    "wps group": ["wps"],
    "van berkel": ["van berkel", "berkel"],
    "fattura 24": ["fattura24", "fattura 24"],
    "mooney": ["mooney"],
    "lab19": ["lab19"],
    "express checkout": ["express"],  # Generico PayPal
    "pagamento cellulare": [],  # Non mappabile
    "pagamento sito web": [],  # Non mappabile
}


def normalize_string(s: str) -> str:
    """Normalizza stringa per confronto."""
    if not s:
        return ""
    return re.sub(r'[^a-z0-9]', '', s.lower())


def parse_paypal_date(date_str: str) -> Optional[datetime]:
    """Parse data PayPal in vari formati."""
    formats = [
        "%d/%m/%Y",
        "%d/%m/%y", 
        "%Y-%m-%d",
        "%d-%m-%Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None


def match_fornitore(paypal_name: str, fornitore_name: str) -> float:
    """
    Calcola score di matching tra nome PayPal e fornitore.
    
    Returns:
        Float 0-1, dove 1 è match perfetto
    """
    if not paypal_name or not fornitore_name:
        return 0.0
    
    paypal_norm = normalize_string(paypal_name)
    fornitore_norm = normalize_string(fornitore_name)
    
    # Match esatto
    if paypal_norm == fornitore_norm:
        return 1.0
    
    # Uno contiene l'altro
    if paypal_norm in fornitore_norm or fornitore_norm in paypal_norm:
        return 0.9
    
    # Check mappatura conosciuta
    for paypal_key, fornitore_variants in PAYPAL_TO_FORNITORE_MAP.items():
        if normalize_string(paypal_key) in paypal_norm:
            for variant in fornitore_variants:
                if normalize_string(variant) in fornitore_norm:
                    return 0.95
    
    # Check parole comuni
    paypal_words = set(paypal_norm.split())
    fornitore_words = set(fornitore_norm.split())
    common = paypal_words & fornitore_words
    if common:
        return len(common) / max(len(paypal_words), len(fornitore_words))
    
    return 0.0


async def riconcilia_pagamenti_paypal(
    db: AsyncIOMotorDatabase,
    pagamenti: List[Dict[str, Any]],
    tolleranza_importo: float = 0.02,  # 2% tolleranza
    tolleranza_giorni: int = 60  # 60 giorni
) -> Dict[str, Any]:
    """
    Riconcilia una lista di pagamenti PayPal con le fatture ricevute.
    
    Args:
        db: Database MongoDB
        pagamenti: Lista di pagamenti PayPal con keys: data, beneficiario, importo
        tolleranza_importo: Tolleranza percentuale sull'importo (default 2%)
        tolleranza_giorni: Giorni di tolleranza sulla data
    
    Returns:
        Statistiche della riconciliazione
    """
    risultato = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "pagamenti_processati": len(pagamenti),
        "riconciliati": 0,
        "gia_pagati_paypal": 0,
        "aggiornati_metodo": 0,
        "non_trovati": 0,
        "errori": 0,
        "dettaglio_riconciliazioni": [],
        "dettaglio_non_trovati": []
    }
    
    # Usa la collection corretta (invoices invece di fatture_ricevute)
    collection_name = "invoices"
    
    for pag in pagamenti:
        try:
            importo = abs(float(pag.get("importo", 0)))
            if importo <= 0:
                continue
                
            data_pag = parse_paypal_date(pag.get("data", ""))
            beneficiario = pag.get("beneficiario", "") or pag.get("descrizione", "")
            
            # Cerca fatture con importo simile (tolleranza 2% o 1€)
            min_importo = importo * (1 - tolleranza_importo) - 1
            max_importo = importo * (1 + tolleranza_importo) + 1
            
            query = {
                "total_amount": {"$gte": min_importo, "$lte": max_importo}
            }
            
            fatture_candidate = await db[collection_name].find(
                query,
                {"_id": 0}
            ).to_list(100)
            
            if not fatture_candidate:
                risultato["non_trovati"] += 1
                risultato["dettaglio_non_trovati"].append({
                    "pagamento": pag,
                    "motivo": f"Nessuna fattura con importo ~€{importo:.2f}"
                })
                continue
            
            # Trova la migliore corrispondenza per nome fornitore
            best_match = None
            best_score = 0.0
            
            for fattura in fatture_candidate:
                # Supporta entrambi i formati: supplier_name e fornitore_ragione_sociale
                fornitore = fattura.get("supplier_name") or fattura.get("fornitore_ragione_sociale", "")
                score = match_fornitore(beneficiario, fornitore)
                
                # Bonus se data è vicina
                if data_pag:
                    data_fatt_str = fattura.get("invoice_date") or fattura.get("data_documento")
                    if data_fatt_str:
                        try:
                            data_fatt = datetime.strptime(str(data_fatt_str)[:10], "%Y-%m-%d")
                            diff_giorni = abs((data_pag - data_fatt).days)
                            if diff_giorni <= 7:
                                score += 0.2
                            elif diff_giorni <= 30:
                                score += 0.1
                        except:
                            pass
                
                if score > best_score:
                    best_score = score
                    best_match = fattura
            
            if best_match and best_score >= 0.3:  # Soglia abbassata
                fattura_id = best_match.get("id")
                fornitore_nome = best_match.get("supplier_name") or best_match.get("fornitore_ragione_sociale", "?")
                importo_fatt = best_match.get("total_amount") or best_match.get("importo_totale", 0)
                numero_fatt = best_match.get("invoice_number") or best_match.get("numero_documento", "?")
                data_fatt = best_match.get("invoice_date") or best_match.get("data_documento", "?")
                
                # Verifica se già pagata via PayPal
                if best_match.get("riconciliato_paypal"):
                    risultato["gia_pagati_paypal"] += 1
                    continue
                
                # Aggiorna fattura come pagata via PayPal
                update_data = {
                    "pagato": True,
                    "metodo_pagamento": "PayPal",
                    "data_pagamento": data_pag.isoformat() if data_pag else datetime.now(timezone.utc).isoformat(),
                    "riconciliato_paypal": True,
                    "paypal_transaction_id": pag.get("codice_transazione", ""),
                    "paypal_beneficiario": beneficiario,
                    "updated_at": datetime.now(timezone.utc)
                }
                
                await db[collection_name].update_one(
                    {"id": fattura_id},
                    {"$set": update_data}
                )
                
                # Crea movimento in Prima Nota Banca se non già pagata
                if not best_match.get("pagato"):
                    import uuid
                    movimento_id = str(uuid.uuid4())
                    data_mov = data_pag.strftime("%Y-%m-%d") if data_pag else datetime.now(timezone.utc).strftime("%Y-%m-%d")
                    anno_mov = int(data_mov[:4])
                    
                    movimento = {
                        "id": movimento_id,
                        "data": data_mov,
                        "anno": anno_mov,
                        "descrizione": f"PayPal - {fornitore_nome} - Fatt. {numero_fatt}",
                        "causale": "Pagamento fattura fornitore via PayPal",
                        "importo": float(importo),
                        "tipo": "uscita",
                        "categoria": "fornitori",
                        "stato": "confermato",
                        "fattura_id": fattura_id,
                        "fattura_collegata": fattura_id,
                        "fattura_numero": numero_fatt,
                        "fornitore": fornitore_nome,
                        "metodo_pagamento": "PayPal",
                        "paypal_transaction_id": pag.get("codice_transazione", ""),
                        "riconciliato": True,
                        "source": "riconciliazione_paypal",
                        "created_at": datetime.now(timezone.utc).isoformat()
                    }
                    
                    await db["prima_nota_banca"].insert_one(movimento)
                    risultato["riconciliati"] += 1
                else:
                    risultato["aggiornati_metodo"] += 1
                    
                risultato["dettaglio_riconciliazioni"].append({
                    "pagamento_paypal": {
                        "data": pag.get("data"),
                        "beneficiario": beneficiario,
                        "importo": importo,
                        "codice": pag.get("codice_transazione", "")
                    },
                    "fattura": {
                        "id": fattura_id,
                        "fornitore": fornitore_nome,
                        "importo": importo_fatt,
                        "numero": numero_fatt,
                        "data": str(data_fatt)[:10] if data_fatt else "?"
                    },
                    "score_matching": best_score,
                    "azione": "aggiornato_metodo" if best_match.get("pagato") else "riconciliato"
                })
            else:
                risultato["non_trovati"] += 1
                candidati_info = []
                for f in fatture_candidate[:3]:
                    fn = f.get("supplier_name") or f.get("fornitore_ragione_sociale", "?")
                    fa = f.get("total_amount") or f.get("importo_totale", 0)
                    candidati_info.append(f"{fn}: €{fa:.2f}")
                
                risultato["dettaglio_non_trovati"].append({
                    "pagamento": pag,
                    "motivo": f"Nessun fornitore corrispondente a '{beneficiario}' (best score: {best_score:.2f})",
                    "candidati": candidati_info
                })
                
        except Exception as e:
            logger.error(f"Errore riconciliazione pagamento {pag}: {e}")
            risultato["errori"] += 1
    
    return risultato


# Pagamenti estratti dai PDF PayPal forniti dall'utente
PAGAMENTI_PAYPAL_2024 = [
    {"data": "06/01/2024", "beneficiario": "InfoCert Spa", "importo": -30.38},
    {"data": "12/01/2024", "beneficiario": "Spotify AB", "importo": -17.99},
    {"data": "20/01/2024", "beneficiario": "Intesa Sanpaolo S.p.A.", "importo": -7.50},
    {"data": "25/01/2024", "beneficiario": "Indors Snc Di Inciso Domenico & C", "importo": -259.00},
    {"data": "25/01/2024", "beneficiario": "WPS GROUP S.N.C.", "importo": -109.80},
    {"data": "12/02/2024", "beneficiario": "Spotify AB", "importo": -17.99},
    {"data": "14/02/2024", "beneficiario": "Intesa Sanpaolo S.p.A.", "importo": -2877.34},
    {"data": "15/02/2024", "beneficiario": "InfoCert Spa", "importo": -30.38},
    {"data": "19/02/2024", "beneficiario": "F.lli Casolaro Hotellerie Spa", "importo": -493.62},
    {"data": "12/03/2024", "beneficiario": "Spotify AB", "importo": -17.99},
    {"data": "12/04/2024", "beneficiario": "Spotify AB", "importo": -17.99},
    {"data": "16/04/2024", "beneficiario": "timbri.it SRL", "importo": -53.58},
    {"data": "02/05/2024", "beneficiario": "Intesa Sanpaolo S.p.A.", "importo": -860.89},
    {"data": "12/05/2024", "beneficiario": "Spotify AB", "importo": -17.99},
    {"data": "12/06/2024", "beneficiario": "Spotify AB", "importo": -17.99},
    {"data": "12/07/2024", "beneficiario": "Spotify AB", "importo": -17.99},
    {"data": "20/07/2024", "beneficiario": "InfoCert Spa", "importo": -32.94},
    {"data": "05/08/2024", "beneficiario": "Adobe Systems Software Ireland LTD", "importo": -14.99},
    {"data": "11/08/2024", "beneficiario": "Register spa", "importo": -18.24},
    {"data": "11/08/2024", "beneficiario": "Register spa", "importo": -59.29},
    {"data": "12/08/2024", "beneficiario": "Spotify AB", "importo": -17.99},
    {"data": "09/09/2024", "beneficiario": "Laspillatura Srls", "importo": -136.99},
    {"data": "12/09/2024", "beneficiario": "Spotify AB", "importo": -17.99},
    {"data": "14/09/2024", "beneficiario": "HP Italy S.r.l.", "importo": -4.99},
    {"data": "18/09/2024", "beneficiario": "Aruba Spa", "importo": -54.78},
    {"data": "21/09/2024", "beneficiario": "elmax srl", "importo": -159.60},
    {"data": "21/09/2024", "beneficiario": "ERREDI FORNITURE SRL", "importo": -134.66},
    {"data": "21/09/2024", "beneficiario": "Detertecnica di Cesari Maurizio", "importo": -160.90},
    {"data": "12/10/2024", "beneficiario": "Spotify AB", "importo": -17.99},
    {"data": "17/10/2024", "beneficiario": "HP Italy S.r.l.", "importo": -4.99},
    {"data": "06/11/2024", "beneficiario": "elmax srl", "importo": -156.62},
    {"data": "12/11/2024", "beneficiario": "Spotify AB", "importo": -17.99},
    {"data": "14/11/2024", "beneficiario": "HP Italy S.r.l.", "importo": -4.99},
    {"data": "18/11/2024", "beneficiario": "Coltelleria Zoppi", "importo": -106.72},
    {"data": "22/11/2024", "beneficiario": "Bellerofonte s.r.l.", "importo": -25.39},
    {"data": "05/12/2024", "beneficiario": "Nuova Bever-li", "importo": -84.22},
    {"data": "07/12/2024", "beneficiario": "Erretre s.r.l.", "importo": -968.67},
    {"data": "10/12/2024", "beneficiario": "RISTOFAST SRL", "importo": -711.80},
    {"data": "12/12/2024", "beneficiario": "Spotify AB", "importo": -17.99},
    {"data": "13/12/2024", "beneficiario": "HP Italy S.r.l.", "importo": -4.99},
    {"data": "29/12/2024", "beneficiario": "InfoCert Spa", "importo": -59.78},
]

PAGAMENTI_PAYPAL_2025_Q4 = [
    # Ottobre 2025
    {"data": "03/10/2025", "beneficiario": "Express Checkout", "importo": -112.83, "codice_transazione": "9KS57534V2632643L"},
    {"data": "06/10/2025", "beneficiario": "Express Checkout", "importo": -364.29, "codice_transazione": "4WJ89470GU353651W"},
    {"data": "12/10/2025", "beneficiario": "Spotify AB", "importo": -20.99, "codice_transazione": "9AA47835U9009970R"},
    {"data": "14/10/2025", "beneficiario": "Express Checkout", "importo": -72.50, "codice_transazione": "3XM5514274274112U"},
    {"data": "16/10/2025", "beneficiario": "Pagamento cellulare", "importo": -600.56, "codice_transazione": "1R0929797P4188928"},
    {"data": "17/10/2025", "beneficiario": "Express Checkout", "importo": -149.70, "codice_transazione": "3DN08766LW313924T"},
    {"data": "20/10/2025", "beneficiario": "Pagamento sito web", "importo": -869.28, "codice_transazione": "9P673182U1498743Y"},
    # Novembre 2025
    {"data": "11/11/2025", "beneficiario": "Fattura 24 S.r.L.", "importo": -234.24, "codice_transazione": "79S94023J1364974M"},
    {"data": "12/11/2025", "beneficiario": "Spotify AB", "importo": -20.99, "codice_transazione": "07S11543F09047914"},
    {"data": "15/11/2025", "beneficiario": "Mooney Spa", "importo": -30.90, "codice_transazione": "9VH2776161860634G"},
    # Dicembre 2025
    {"data": "09/12/2025", "beneficiario": "VAN BERKEL INTERNATIONAL S.R.L.", "importo": -597.55, "codice_transazione": "5GU97502M45522434"},
    {"data": "12/12/2025", "beneficiario": "Spotify AB", "importo": -20.99, "codice_transazione": "04Y8796475272505J"},
    {"data": "16/12/2025", "beneficiario": "WEB-E / puntoluce.net", "importo": -231.59, "codice_transazione": "7RY34371MG450372P"},
    {"data": "21/12/2025", "beneficiario": "Lab19", "importo": -247.98, "codice_transazione": "48J749537Y577813C"},
]


async def esegui_riconciliazione_completa(db: AsyncIOMotorDatabase) -> Dict[str, Any]:
    """
    Esegue la riconciliazione completa con tutti i pagamenti PayPal estratti.
    """
    tutti_pagamenti = PAGAMENTI_PAYPAL_2024 + PAGAMENTI_PAYPAL_2025_Q4
    
    logger.info(f"🔄 Avvio riconciliazione PayPal con {len(tutti_pagamenti)} pagamenti...")
    
    risultato = await riconcilia_pagamenti_paypal(db, tutti_pagamenti)
    
    logger.info(f"✅ Riconciliazione completata: {risultato['riconciliati']} fatture riconciliate")
    
    return risultato
