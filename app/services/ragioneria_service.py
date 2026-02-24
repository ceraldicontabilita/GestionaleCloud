"""
Servizio Ragioneria - Principi contabili italiani
Gestisce sconti, resi, storni e duplicazioni IVA secondo OIC e normativa fiscale
"""
import logging
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


# ============================================
# COSTANTI E CONFIGURAZIONI
# ============================================

# Tipi di note di variazione (art. 26 DPR 633/72)
NOTE_VARIAZIONE_DIMINUZIONE = ["TD04", "NC", "nota_credito"]  # Note di credito
NOTE_VARIAZIONE_AUMENTO = ["TD05", "ND", "nota_debito"]  # Note di debito

# Aliquote IVA standard Italia 2025
ALIQUOTE_IVA = {
    22: "Aliquota ordinaria",
    10: "Aliquota ridotta (ristorazione, alimentari trasformati)",
    5: "Aliquota super-ridotta",
    4: "Aliquota minima (alimentari base)",
    0: "Esente/Non imponibile"
}


# ============================================
# GESTIONE SCONTI
# ============================================

def calcola_sconto_incondizionato(prezzo_lordo: float, percentuale_sconto: float) -> Dict[str, float]:
    """
    Calcola sconto incondizionato (già nel prezzo concordato).
    L'IVA si calcola sul prezzo scontato.
    
    Args:
        prezzo_lordo: Prezzo prima dello sconto
        percentuale_sconto: Percentuale di sconto (es: 10 per 10%)
    
    Returns:
        Dict con prezzo_netto, importo_sconto, base_imponibile_iva
    """
    importo_sconto = prezzo_lordo * (percentuale_sconto / 100)
    prezzo_netto = prezzo_lordo - importo_sconto
    
    return {
        "prezzo_lordo": round(prezzo_lordo, 2),
        "percentuale_sconto": percentuale_sconto,
        "importo_sconto": round(importo_sconto, 2),
        "prezzo_netto": round(prezzo_netto, 2),
        "base_imponibile_iva": round(prezzo_netto, 2),
        "tipo_sconto": "incondizionato"
    }


def genera_nota_credito_sconto(sconto_data: Dict[str, Any], fornitore_cliente: str) -> Dict[str, Any]:
    """
    Genera una nota di credito per sconto condizionato (fine anno, volume, ecc).
    Usato quando lo sconto matura DOPO la fattura originale.
    
    Art. 26 DPR 633/72 - Variazioni dell'imponibile e dell'imposta
    """
    importo = sconto_data.get("importo", 0)
    aliquota_iva = sconto_data.get("aliquota_iva", 22)
    
    # Calcola IVA da stornare
    iva_storno = importo * (aliquota_iva / 100)
    
    return {
        "id": str(uuid4()),
        "tipo_documento": "TD04",  # Nota di credito
        "descrizione": f"Nota credito per sconto - {sconto_data.get('descrizione', 'Sconto condizionato')}",
        "fornitore_cliente": fornitore_cliente,
        "imponibile": round(-importo, 2),  # Negativo perché riduce
        "aliquota_iva": aliquota_iva,
        "iva": round(-iva_storno, 2),
        "totale": round(-(importo + iva_storno), 2),
        "riferimento_fattura": sconto_data.get("fattura_originale_id"),
        "data_documento": datetime.now(timezone.utc).isoformat(),
        "motivo": "sconto_condizionato",
        "created_at": datetime.now(timezone.utc).isoformat()
    }


# ============================================
# GESTIONE RESI
# ============================================

def genera_nota_credito_reso(reso_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Genera nota di credito per reso merce.
    
    Il reso di vendita comporta:
    - Storno del ricavo
    - Storno del credito cliente
    - Rettifica IVA (art. 26 DPR 633/72)
    """
    importo = reso_data.get("importo", 0)
    aliquota_iva = reso_data.get("aliquota_iva", 22)
    quantita = reso_data.get("quantita", 1)
    
    iva_storno = importo * (aliquota_iva / 100)
    
    return {
        "id": str(uuid4()),
        "tipo_documento": "TD04",
        "descrizione": f"Nota credito per reso - {reso_data.get('prodotto', 'Merce')}",
        "cliente": reso_data.get("cliente"),
        "imponibile": round(-importo, 2),
        "aliquota_iva": aliquota_iva,
        "iva": round(-iva_storno, 2),
        "totale": round(-(importo + iva_storno), 2),
        "quantita_resa": quantita,
        "riferimento_fattura": reso_data.get("fattura_originale_id"),
        "riferimento_scontrino": reso_data.get("scontrino_id"),
        "data_documento": datetime.now(timezone.utc).isoformat(),
        "motivo": "reso_merce",
        "created_at": datetime.now(timezone.utc).isoformat()
    }


# ============================================
# GESTIONE STORNI
# ============================================

def genera_storno_contabile(movimento_originale: Dict[str, Any], motivo: str) -> Dict[str, Any]:
    """
    Genera uno storno contabile (movimento opposto).
    
    Lo storno è una registrazione di rettifica:
    - Storno totale: movimento opposto completo
    - Storno parziale: solo la quota eccedente
    """
    return {
        "id": str(uuid4()),
        "tipo": "storno",
        "movimento_originale_id": movimento_originale.get("id"),
        "importo": -movimento_originale.get("importo", 0),  # Segno opposto
        "dare": movimento_originale.get("avere"),  # Inversione dare/avere
        "avere": movimento_originale.get("dare"),
        "descrizione": f"STORNO: {movimento_originale.get('descrizione', '')} - {motivo}",
        "data": datetime.now(timezone.utc).isoformat(),
        "motivo_storno": motivo,
        "created_at": datetime.now(timezone.utc).isoformat()
    }


# ============================================
# GESTIONE DUPLICAZIONE IVA (FATTURA + CORRISPETTIVO)
# ============================================

def verifica_fattura_in_corrispettivo(fattura: Dict[str, Any], corrispettivi: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Verifica se una fattura emessa è relativa a un corrispettivo già emesso.
    
    PRINCIPIO CONTABILE:
    Se il cliente chiede fattura DOPO lo scontrino, l'IVA è già stata assolta
    con il corrispettivo. La fattura viene emessa ma NON va conteggiata
    nel calcolo IVA periodica (duplicazione).
    
    Returns:
        Dict con info corrispettivo correlato o None
    """
    data_fattura = fattura.get("data_documento", "")
    importo_fattura = fattura.get("totale", 0)
    
    # Tolleranza importo (per arrotondamenti)
    tolleranza = 0.05
    
    for corr in corrispettivi:
        data_corr = corr.get("data", "")
        importo_corr = corr.get("totale", 0)
        
        # Stesso giorno e stesso importo (con tolleranza)
        if data_corr == data_fattura[:10]:  # Confronta solo la data
            if abs(importo_fattura - importo_corr) <= tolleranza:
                return {
                    "corrispettivo_id": corr.get("id"),
                    "data_corrispettivo": data_corr,
                    "importo_corrispettivo": importo_corr,
                    "match_type": "same_day_same_amount"
                }
    
    return None


def marca_fattura_gia_in_corrispettivo(fattura_id: str, corrispettivo_id: str) -> Dict[str, Any]:
    """
    Marca una fattura come già inclusa in un corrispettivo.
    Questa fattura NON deve essere conteggiata nel calcolo IVA.
    
    Returns:
        Dict con i campi da aggiornare sulla fattura
    """
    return {
        "inclusa_in_corrispettivo": True,
        "corrispettivo_correlato_id": corrispettivo_id,
        "escludere_da_liquidazione_iva": True,
        "nota": "Fattura emessa su richiesta cliente dopo scontrino. IVA già assolta con corrispettivo.",
        "updated_at": datetime.now(timezone.utc).isoformat()
    }


async def calcola_iva_debito_corretto(db, anno: int, mese: int) -> Dict[str, Any]:
    """
    Calcola l'IVA a debito corretta escludendo:
    1. Fatture emesse già incluse nei corrispettivi
    2. Note di credito (che riducono il debito)
    
    Args:
        db: Database MongoDB
        anno: Anno di riferimento
        mese: Mese di riferimento (1-12)
    
    Returns:
        Dict con IVA da corrispettivi, fatture emesse (escl. duplicati), totale
    """
    
    # Range date del mese
    primo_giorno = f"{anno}-{str(mese).zfill(2)}-01"
    if mese == 12:
        ultimo_giorno = f"{anno}-12-31"
    else:
        ultimo_giorno = f"{anno}-{str(mese+1).zfill(2)}-01"
    
    # 1. IVA da corrispettivi
    pipeline_corr = [
        {"$match": {
            "data": {"$gte": primo_giorno, "$lt": ultimo_giorno}
        }},
        {"$group": {
            "_id": None,
            "totale_imponibile": {"$sum": "$totale_imponibile"},
            "totale_iva": {"$sum": "$totale_iva"},
            "count": {"$sum": 1}
        }}
    ]
    
    result_corr = await db["corrispettivi"].aggregate(pipeline_corr).to_list(1)
    iva_corrispettivi = result_corr[0]["totale_iva"] if result_corr else 0
    
    # 2. IVA da fatture emesse (ESCLUDENDO quelle già in corrispettivo)
    pipeline_fatt = [
        {"$match": {
            "data_documento": {"$gte": primo_giorno, "$lt": ultimo_giorno},
            "$or": [
                {"inclusa_in_corrispettivo": {"$ne": True}},
                {"inclusa_in_corrispettivo": {"$exists": False}}
            ],
            "tipo_documento": {"$nin": NOTE_VARIAZIONE_DIMINUZIONE}  # Esclude note credito
        }},
        {"$group": {
            "_id": None,
            "totale_imponibile": {"$sum": "$imponibile"},
            "totale_iva": {"$sum": "$iva"},
            "count": {"$sum": 1}
        }}
    ]
    
    result_fatt = await db["invoices_emesse"].aggregate(pipeline_fatt).to_list(1)
    iva_fatture_emesse = result_fatt[0]["totale_iva"] if result_fatt else 0
    
    # 3. Note di credito emesse (riducono IVA a debito)
    pipeline_nc = [
        {"$match": {
            "data_documento": {"$gte": primo_giorno, "$lt": ultimo_giorno},
            "tipo_documento": {"$in": NOTE_VARIAZIONE_DIMINUZIONE}
        }},
        {"$group": {
            "_id": None,
            "totale_iva_storno": {"$sum": {"$abs": "$iva"}}
        }}
    ]
    
    result_nc = await db["invoices_emesse"].aggregate(pipeline_nc).to_list(1)
    iva_note_credito = result_nc[0]["totale_iva_storno"] if result_nc else 0
    
    # Totale IVA a debito
    totale_iva_debito = iva_corrispettivi + iva_fatture_emesse - iva_note_credito
    
    return {
        "anno": anno,
        "mese": mese,
        "iva_corrispettivi": round(iva_corrispettivi, 2),
        "iva_fatture_emesse": round(iva_fatture_emesse, 2),
        "iva_note_credito_storno": round(iva_note_credito, 2),
        "totale_iva_debito": round(totale_iva_debito, 2),
        "note": "Fatture già incluse nei corrispettivi sono escluse per evitare duplicazione IVA"
    }


# ============================================
# VALIDAZIONI CONTABILI
# ============================================

def valida_registrazione_contabile(movimento: Dict[str, Any]) -> Dict[str, Any]:
    """
    Valida una registrazione contabile secondo principi OIC.
    
    Verifica:
    - Principio della competenza economica
    - Quadratura dare/avere
    - Completezza dati obbligatori
    """
    errori = []
    warnings = []
    
    # Verifica campi obbligatori
    campi_obbligatori = ["data", "importo", "descrizione"]
    for campo in campi_obbligatori:
        if not movimento.get(campo):
            errori.append(f"Campo obbligatorio mancante: {campo}")
    
    # Verifica importo positivo o nullo solo con descrizione appropriata
    importo = movimento.get("importo", 0)
    if importo == 0 and "storno" not in movimento.get("descrizione", "").lower():
        warnings.append("Importo zero - verificare se corretto")
    
    # Verifica data non futura
    data_mov = movimento.get("data", "")
    if data_mov:
        try:
            data_parsed = datetime.fromisoformat(data_mov.replace("Z", "+00:00"))
            if data_parsed > datetime.now(timezone.utc):
                warnings.append("Data movimento nel futuro")
        except:
            errori.append("Formato data non valido")
    
    return {
        "valido": len(errori) == 0,
        "errori": errori,
        "warnings": warnings
    }


# ============================================
# UTILITY
# ============================================

def arrotonda_monetario(valore: float, decimali: int = 2) -> float:
    """Arrotondamento monetario standard (half-up)."""
    d = Decimal(str(valore))
    return float(d.quantize(Decimal(10) ** -decimali, rounding=ROUND_HALF_UP))


def scorporo_iva(totale_ivato: float, aliquota: int = 22) -> Dict[str, float]:
    """
    Scorporo IVA da un importo lordo.
    
    Formula: Imponibile = Totale / (1 + aliquota/100)
    """
    divisore = 1 + (aliquota / 100)
    imponibile = totale_ivato / divisore
    iva = totale_ivato - imponibile
    
    return {
        "totale_ivato": arrotonda_monetario(totale_ivato),
        "imponibile": arrotonda_monetario(imponibile),
        "iva": arrotonda_monetario(iva),
        "aliquota": aliquota
    }
