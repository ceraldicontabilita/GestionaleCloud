"""
Router Cespiti - Gestione Beni Ammortizzabili
Anagrafica cespiti, calcolo ammortamenti, dismissioni
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from uuid import uuid4
import logging

from app.database import Database
from app.utils.error_handler import handle_errors

router = APIRouter()
logger = logging.getLogger(__name__)

# ============================================
# COEFFICIENTI AMMORTAMENTO FISCALI
# DM 31/12/1988 - Settore Ristorazione
# ============================================

CATEGORIE_CESPITI = {
    "fabbricati": {
        "descrizione": "Fabbricati",
        "coefficiente": 3,
        "vita_utile": 33
    },
    "impianti_generici": {
        "descrizione": "Impianti generici (elettrico, idraulico)",
        "coefficiente": 10,
        "vita_utile": 10
    },
    "impianti_cucina": {
        "descrizione": "Impianti specifici cucina",
        "coefficiente": 12,
        "vita_utile": 8
    },
    "attrezzature": {
        "descrizione": "Attrezzature (piccola attrezzatura)",
        "coefficiente": 15,
        "vita_utile": 7
    },
    "mobili_arredi": {
        "descrizione": "Mobili e arredi",
        "coefficiente": 12,
        "vita_utile": 8
    },
    "automezzi": {
        "descrizione": "Automezzi",
        "coefficiente": 20,
        "vita_utile": 5
    },
    "macchine_ufficio": {
        "descrizione": "Macchine ufficio elettroniche",
        "coefficiente": 20,
        "vita_utile": 5
    },
    "software": {
        "descrizione": "Software",
        "coefficiente": 20,
        "vita_utile": 5
    },
    "insegne": {
        "descrizione": "Insegne e pubblicità",
        "coefficiente": 20,
        "vita_utile": 5
    },
    "frigoriferi": {
        "descrizione": "Frigoriferi e congelatori",
        "coefficiente": 12,
        "vita_utile": 8
    },
    "forni": {
        "descrizione": "Forni e piastre",
        "coefficiente": 12,
        "vita_utile": 8
    }
}


# ============================================
# MODELLI
# ============================================

class CespiteInput(BaseModel):
    descrizione: str
    categoria: str  # chiave di CATEGORIE_CESPITI
    data_acquisto: str  # YYYY-MM-DD
    valore_acquisto: float
    fornitore: Optional[str] = None
    numero_fattura: Optional[str] = None
    ubicazione: Optional[str] = None
    note: Optional[str] = None


class DismissioneInput(BaseModel):
    cespite_id: str
    data_dismissione: str  # YYYY-MM-DD
    tipo: str  # "vendita", "eliminazione", "permuta"
    prezzo_vendita: Optional[float] = 0
    note: Optional[str] = None


# ============================================
# ENDPOINT
# ============================================

@router.get("/categorie")
@handle_errors
async def get_categorie_cespiti() -> Dict[str, Any]:
    """Restituisce le categorie disponibili con coefficienti."""
    return {
        "categorie": [
            {
                "codice": k,
                "descrizione": v["descrizione"],
                "coefficiente": v["coefficiente"],
                "vita_utile_anni": v["vita_utile"]
            }
            for k, v in CATEGORIE_CESPITI.items()
        ]
    }


@router.post("/")
@handle_errors
async def crea_cespite(cespite: CespiteInput) -> Dict[str, Any]:
    """Registra un nuovo cespite ammortizzabile."""
    db = Database.get_db()
    
    if cespite.categoria not in CATEGORIE_CESPITI:
        raise HTTPException(
            status_code=400, 
            detail=f"Categoria non valida. Categorie disponibili: {list(CATEGORIE_CESPITI.keys())}"
        )
    
    cat_info = CATEGORIE_CESPITI[cespite.categoria]
    coeff = cat_info["coefficiente"]
    
    # Anno di acquisto
    anno_acquisto = int(cespite.data_acquisto[:4])
    
    nuovo_cespite = {
        "id": str(uuid4()),
        "descrizione": cespite.descrizione,
        "categoria": cespite.categoria,
        "categoria_descrizione": cat_info["descrizione"],
        "coefficiente_ammortamento": coeff,
        "vita_utile_anni": cat_info["vita_utile"],
        "data_acquisto": cespite.data_acquisto,
        "anno_acquisto": anno_acquisto,
        "valore_acquisto": cespite.valore_acquisto,
        "valore_residuo": cespite.valore_acquisto,
        "fondo_ammortamento": 0,
        "fornitore": cespite.fornitore,
        "numero_fattura": cespite.numero_fattura,
        "ubicazione": cespite.ubicazione,
        "note": cespite.note,
        "stato": "attivo",
        "ammortamento_completato": False,
        "piano_ammortamento": [],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db["cespiti"].insert_one(nuovo_cespite.copy())
    
    return {
        "success": True,
        "cespite_id": nuovo_cespite["id"],
        "messaggio": f"Cespite '{cespite.descrizione}' registrato",
        "dettaglio": {
            "valore": cespite.valore_acquisto,
            "coefficiente": coeff,
            "quota_annua_ordinaria": round(cespite.valore_acquisto * coeff / 100, 2),
            "quota_primo_anno": round(cespite.valore_acquisto * coeff / 200, 2),  # dimezzata
            "anni_ammortamento_stimati": cat_info["vita_utile"]
        }
    }


@router.get("/")
@handle_errors
async def lista_cespiti(
    attivi: bool = Query(True, description="Solo cespiti attivi"),
    categoria: str = Query(None, description="Filtra per categoria")
) -> List[Dict[str, Any]]:
    """Lista cespiti con stato ammortamento."""
    db = Database.get_db()
    
    query = {}
    if attivi:
        query["stato"] = "attivo"
    if categoria:
        query["categoria"] = categoria
    
    cespiti = await db["cespiti"].find(query, {"_id": 0}).to_list(1000)
    
    return cespiti


@router.get("/riepilogo")
@handle_errors
async def get_riepilogo_cespiti() -> Dict[str, Any]:
    """Riepilogo totale cespiti per categoria."""
    db = Database.get_db()
    
    # Aggregazione per categoria
    pipeline = [
        {"$match": {"stato": "attivo"}},
        {"$group": {
            "_id": "$categoria",
            "num_cespiti": {"$sum": 1},
            "valore_acquisto_totale": {"$sum": "$valore_acquisto"},
            "fondo_ammortamento_totale": {"$sum": "$fondo_ammortamento"},
            "valore_residuo_totale": {"$sum": "$valore_residuo"}
        }},
        {"$sort": {"valore_acquisto_totale": -1}}
    ]
    
    per_categoria = await db["cespiti"].aggregate(pipeline).to_list(100)
    
    # Totali generali
    totale_valore = sum(c["valore_acquisto_totale"] for c in per_categoria)
    totale_fondo = sum(c["fondo_ammortamento_totale"] for c in per_categoria)
    totale_residuo = sum(c["valore_residuo_totale"] for c in per_categoria)
    totale_cespiti = sum(c["num_cespiti"] for c in per_categoria)
    
    # Arricchisci con info categoria
    for cat in per_categoria:
        cat_code = cat["_id"]
        if cat_code in CATEGORIE_CESPITI:
            cat["descrizione"] = CATEGORIE_CESPITI[cat_code]["descrizione"]
            cat["coefficiente"] = CATEGORIE_CESPITI[cat_code]["coefficiente"]
        cat["valore_acquisto_totale"] = round(cat["valore_acquisto_totale"], 2)
        cat["fondo_ammortamento_totale"] = round(cat["fondo_ammortamento_totale"], 2)
        cat["valore_residuo_totale"] = round(cat["valore_residuo_totale"], 2)
    
    return {
        "totali": {
            "num_cespiti": totale_cespiti,
            "valore_acquisto": round(totale_valore, 2),
            "fondo_ammortamento": round(totale_fondo, 2),
            "valore_netto_contabile": round(totale_residuo, 2),
            "percentuale_ammortizzata": round(totale_fondo / totale_valore * 100, 1) if totale_valore > 0 else 0
        },
        "per_categoria": per_categoria
    }


@router.get("/calcolo/{anno}")
@handle_errors
async def calcola_ammortamenti_anno(anno: int) -> Dict[str, Any]:
    """
    Calcola ammortamenti per tutti i cespiti attivi per l'anno.
    NON registra, solo preview.
    """
    db = Database.get_db()
    
    cespiti = await db["cespiti"].find(
        {"stato": "attivo", "ammortamento_completato": False},
        {"_id": 0}
    ).to_list(1000)
    
    ammortamenti = []
    totale = 0
    
    for cespite in cespiti:
        valore = cespite["valore_acquisto"]
        coeff = cespite["coefficiente_ammortamento"]
        fondo = cespite.get("fondo_ammortamento", 0)
        anno_acquisto = cespite["anno_acquisto"]
        
        # Verifica se già ammortizzato per quest'anno
        piano = cespite.get("piano_ammortamento", [])
        gia_ammortizzato = any(p.get("anno") == anno for p in piano)
        
        if gia_ammortizzato:
            continue
        
        # Quota ordinaria
        quota_ordinaria = valore * coeff / 100
        
        # Primo anno: dimezzata (prassi fiscale)
        if anno == anno_acquisto:
            quota = quota_ordinaria / 2
        else:
            quota = quota_ordinaria
        
        # Non superare valore residuo
        valore_residuo = valore - fondo
        quota = min(quota, valore_residuo)
        
        if quota > 0:
            ammortamenti.append({
                "cespite_id": cespite["id"],
                "descrizione": cespite["descrizione"],
                "categoria": cespite["categoria"],
                "valore_acquisto": valore,
                "fondo_precedente": round(fondo, 2),
                "quota_anno": round(quota, 2),
                "nuovo_fondo": round(fondo + quota, 2),
                "nuovo_residuo": round(valore_residuo - quota, 2),
                "completato": (valore_residuo - quota) <= 0.01,
                "primo_anno": anno == anno_acquisto
            })
            totale += quota
    
    return {
        "anno": anno,
        "preview": True,
        "ammortamenti": ammortamenti,
        "totale_ammortamenti": round(totale, 2),
        "num_cespiti": len(ammortamenti)
    }


# ============================================
# AUTO-SCAN: Estrai cespiti da righe fatture XML
# (Must be before /{cespite_id} route to avoid catch-all conflict)
# ============================================

KEYWORD_CATEGORY_MAP = [
    (["forno", "piastra cottura"], "forni"),
    (["frigo", "congelator", "abbattitore"], "frigoriferi"),
    (["computer", "stampante", "monitor", "pc ", "notebook", "tablet"], "macchine_ufficio"),
    (["sfogliatric", "planetaria", "impastatric", "pastocrema"], "impianti_cucina"),
    (["lavastoviglie", "lavapiatti", "lavabicchier", "lavaoggetti"], "attrezzature"),
    (["mobile", "arredo", "poltroncin", "sedia", "tavol", "banco", "armadio", "vetrina"], "mobili_arredi"),
    (["impianto", "climatizz", "condizionat"], "impianti_generici"),
    (["insegn", "pubblicita"], "insegne"),
    (["software", "licenz"], "software"),
]

EXCLUDE_KEYWORDS = [
    "caffe", "caffè", "kimbo", "grani", "capsul", "omaggio", "storno",
    "acconto", "anticip", "consulenz", "compensi", "noleggio",
    "canone", "abbonament", "rifatturaz", "penalita", "sinistro",
    "manutenzione ordinaria", "riparazion", "intervento lavori",
    "wi-fi", "sim ", "telefon", "cover", "custodia"
]


def classify_asset(descrizione: str, prezzo: float):
    desc_lower = descrizione.lower()
    for excl in EXCLUDE_KEYWORDS:
        if excl in desc_lower:
            return None
    for keywords, categoria in KEYWORD_CATEGORY_MAP:
        for kw in keywords:
            if kw in desc_lower:
                return categoria
    if prezzo >= 2000:
        for kw in ["supporto", "cappa", "scaffal", "contenitor"]:
            if kw in desc_lower:
                return "attrezzature"
    return None


@router.post("/scan-fatture")
@handle_errors
async def scan_fatture_per_cespiti(
    soglia_valore: float = Query(200, description="Valore minimo"),
    dry_run: bool = Query(False, description="Preview senza salvare")
) -> Dict[str, Any]:
    """Scansiona righe fatture XML per identificare potenziali cespiti.
    
    Legge da invoices[*].righe[*] (campo nested, dove sono importate le righe XML).
    Fallback: se `righe` è vuoto, usa `invoices.notes`/`description` per il riconoscimento.
    """
    db = Database.get_db()

    # Esistenti (dedup)
    existing = await db["cespiti"].find({}, {"_id": 0, "descrizione": 1, "valore_acquisto": 1}).to_list(5000)
    existing_set = {(c["descrizione"], c["valore_acquisto"]) for c in existing}

    nuovi_cespiti: List[Dict[str, Any]] = []
    seen = set()

    # Itera TUTTE le fatture passive non annullate
    cursor = db["invoices"].find({
        "entity_status": {"$ne": "deleted"},
        "$or": [{"total_amount": {"$gt": soglia_valore}}, {"importo_totale": {"$gt": soglia_valore}}],
    }, {"_id": 0})

    async for inv in cursor:
        righe = inv.get("righe") or []
        fattura_id = inv.get("id") or inv.get("invoice_key")
        data_fattura = inv.get("invoice_date") or inv.get("data_fattura") or ""
        data_acquisto = str(data_fattura)[:10] if data_fattura else "2025-01-01"
        try:
            anno_acquisto = int(data_acquisto[:4])
        except (ValueError, IndexError):
            anno_acquisto = 2025
        fornitore = inv.get("supplier_name") or inv.get("cedente_denominazione")

        # Se non ci sono righe, usa total_amount come riga unica
        if not righe:
            total = float(inv.get("total_amount") or inv.get("importo_totale") or 0)
            desc = f"{fornitore or 'Fornitore ignoto'} — Fatt. {inv.get('invoice_number') or inv.get('numero_fattura') or ''}".strip(" -")
            righe = [{"descrizione": desc, "prezzo_totale": total}]

        for riga in righe:
            descrizione = str(riga.get("descrizione") or "").strip()
            prezzo = float(riga.get("prezzo_totale") or riga.get("importo") or 0)
            if not descrizione or prezzo < soglia_valore:
                continue

            categoria = classify_asset(descrizione, prezzo)
            if not categoria:
                continue

            dedup_key = (descrizione[:100], round(prezzo, 2))
            if dedup_key in seen or dedup_key in existing_set:
                continue
            seen.add(dedup_key)

            cat_info = CATEGORIE_CESPITI.get(categoria, {"descrizione": categoria, "coefficiente": 15, "vita_utile": 7})
            cespite = {
                "id": str(uuid4()),
                "descrizione": descrizione[:200],
                "categoria": categoria,
                "categoria_descrizione": cat_info["descrizione"],
                "coefficiente_ammortamento": cat_info["coefficiente"],
                "vita_utile_anni": cat_info["vita_utile"],
                "data_acquisto": data_acquisto,
                "anno_acquisto": anno_acquisto,
                "valore_acquisto": round(prezzo, 2),
                "valore_residuo": round(prezzo, 2),
                "fondo_ammortamento": 0,
                "fornitore": fornitore,
                "fattura_id": fattura_id,
                "note": "Auto-estratto da fattura XML",
                "stato": "attivo",
                "ammortamento_completato": False,
                "piano_ammortamento": [],
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            nuovi_cespiti.append(cespite)

    if dry_run:
        return {
            "preview": True,
            "num_potenziali_cespiti": len(nuovi_cespiti),
            "valore_totale": round(sum(c["valore_acquisto"] for c in nuovi_cespiti), 2),
            "cespiti": [
                {"descrizione": c["descrizione"][:80], "categoria": c["categoria"],
                 "valore_acquisto": c["valore_acquisto"], "fornitore": c.get("fornitore")}
                for c in nuovi_cespiti[:100]
            ],
        }

    if nuovi_cespiti:
        await db["cespiti"].insert_many([c.copy() for c in nuovi_cespiti])

    return {
        "success": True,
        "cespiti_creati": len(nuovi_cespiti),
        "valore_totale": round(sum(c["valore_acquisto"] for c in nuovi_cespiti), 2),
        "messaggio": f"Estratti {len(nuovi_cespiti)} cespiti dalle fatture XML",
    }



@router.get("/{cespite_id}")
@handle_errors
async def get_cespite(cespite_id: str) -> Dict[str, Any]:
    """Dettaglio singolo cespite con piano ammortamento."""
    db = Database.get_db()
    
    cespite = await db["cespiti"].find_one(
        {"id": cespite_id},
        {"_id": 0}
    )
    
    if not cespite:
        raise HTTPException(status_code=404, detail="Cespite non trovato")
    
    return cespite


@router.post("/registra/{anno}")
@handle_errors
async def registra_ammortamenti_anno(anno: int) -> Dict[str, Any]:
    """
    Registra gli ammortamenti calcolati in contabilità.
    Aggiorna i cespiti e crea movimenti contabili.
    """
    db = Database.get_db()
    
    # Calcola ammortamenti
    calcolo = await calcola_ammortamenti_anno(anno)
    
    if len(calcolo["ammortamenti"]) == 0:
        return {
            "success": True,
            "anno": anno,
            "messaggio": "Nessun ammortamento da registrare",
            "totale_registrato": 0
        }
    
    for amm in calcolo["ammortamenti"]:
        # Aggiungi al piano ammortamento del cespite
        quota_record = {
            "anno": anno,
            "quota": amm["quota_anno"],
            "fondo_dopo": amm["nuovo_fondo"],
            "residuo_dopo": amm["nuovo_residuo"],
            "primo_anno": amm["primo_anno"],
            "data_registrazione": datetime.now(timezone.utc).isoformat()
        }
        
        # Aggiorna cespite
        update = {
            "$set": {
                "fondo_ammortamento": amm["nuovo_fondo"],
                "valore_residuo": amm["nuovo_residuo"],
                "ammortamento_completato": amm["completato"]
            },
            "$push": {"piano_ammortamento": quota_record}
        }
        
        await db["cespiti"].update_one(
            {"id": amm["cespite_id"]},
            update
        )
    
    # Crea movimento contabile riepilogativo
    movimento = {
        "id": str(uuid4()),
        "data": f"{anno}-12-31",
        "descrizione": f"Ammortamenti cespiti {anno}",
        "tipo": "ammortamento",
        "importo": calcolo["totale_ammortamenti"],
        "anno": anno,
        "num_cespiti": len(calcolo["ammortamenti"]),
        "dettaglio": [
            {
                "descrizione": a["descrizione"],
                "quota": a["quota_anno"]
            }
            for a in calcolo["ammortamenti"]
        ],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db["movimenti_contabili"].insert_one(movimento.copy())
    
    # G1: Registra anche in prima_nota_cassa
    from uuid import uuid4
    mov_ammort = {
        "id": str(uuid4()),
        "tipo": "uscita",
        "importo": calcolo["totale_ammortamenti"],
        "data": f"{anno}-12-31",
        "descrizione": f"Ammortamenti cespiti {anno} ({len(calcolo['ammortamenti'])} beni)",
        "categoria": "Ammortamenti",
        "source": "ammortamento_cespiti",
        "anno": anno,
        "riconciliato": True,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db["prima_nota_cassa"].insert_one(mov_ammort.copy())
    
    return {
        "success": True,
        "anno": anno,
        "totale_registrato": calcolo["totale_ammortamenti"],
        "cespiti_ammortizzati": len(calcolo["ammortamenti"]),
        "movimento_id": movimento["id"],
        "messaggio": f"Ammortamenti {anno} registrati in contabilità"
    }


@router.post("/dismissione")
@handle_errors
async def dismetti_cespite(input_data: DismissioneInput) -> Dict[str, Any]:
    """
    Dismette un cespite per vendita, eliminazione o permuta.
    Calcola eventuale plus/minusvalenza.
    """
    db = Database.get_db()
    
    cespite = await db["cespiti"].find_one(
        {"id": input_data.cespite_id},
        {"_id": 0}
    )
    
    if not cespite:
        raise HTTPException(status_code=404, detail="Cespite non trovato")
    
    if cespite["stato"] != "attivo":
        raise HTTPException(status_code=400, detail="Cespite già dismesso")
    
    valore_residuo = cespite.get("valore_residuo", 0)
    prezzo_vendita = input_data.prezzo_vendita or 0
    
    # Calcola plus/minusvalenza
    if input_data.tipo == "vendita":
        plusminusvalenza = prezzo_vendita - valore_residuo
    else:
        plusminusvalenza = -valore_residuo  # Eliminazione = perdita totale residuo
    
    tipo_risultato = "plusvalenza" if plusminusvalenza > 0 else ("minusvalenza" if plusminusvalenza < 0 else "pareggio")
    
    # Aggiorna cespite
    dismissione_record = {
        "data": input_data.data_dismissione,
        "tipo": input_data.tipo,
        "prezzo_vendita": prezzo_vendita,
        "valore_residuo_al_momento": valore_residuo,
        "plusminusvalenza": round(plusminusvalenza, 2),
        "tipo_risultato": tipo_risultato,
        "note": input_data.note,
        "data_registrazione": datetime.now(timezone.utc).isoformat()
    }
    
    await db["cespiti"].update_one(
        {"id": input_data.cespite_id},
        {
            "$set": {
                "stato": "dismesso",
                "dismissione": dismissione_record
            }
        }
    )
    
    # Registra movimento contabile
    descrizione_mov = f"Dismissione cespite: {cespite['descrizione']}"
    if input_data.tipo == "vendita":
        descrizione_mov += f" - Vendita €{prezzo_vendita}"
    
    movimento = {
        "id": str(uuid4()),
        "data": input_data.data_dismissione,
        "descrizione": descrizione_mov,
        "tipo": f"dismissione_cespite_{tipo_risultato}",
        "importo": abs(plusminusvalenza),
        "segno": "dare" if plusminusvalenza >= 0 else "avere",
        "cespite_id": input_data.cespite_id,
        "dettaglio": dismissione_record,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db["movimenti_contabili"].insert_one(movimento.copy())
    
    # G1: Registra plus/minusvalenza in prima nota
    if abs(plusminusvalenza) > 0:
        coll_pn = "prima_nota_banca" if input_data.tipo == "vendita" and prezzo_vendita else "prima_nota_cassa"
        mov_dis = {
            "id": str(uuid4()),
            "tipo": "entrata" if plusminusvalenza > 0 else "uscita",
            "importo": abs(plusminusvalenza),
            "data": input_data.data_dismissione,
            "descrizione": f"{'Plusvalenza' if plusminusvalenza > 0 else 'Minusvalenza'} cessione {cespite.get('descrizione','')}",
            "categoria": "Plusvalenza cespiti" if plusminusvalenza > 0 else "Minusvalenza cespiti",
            "source": "dismissione_cespite",
            "cespite_id": input_data.cespite_id,
            "riconciliato": False,
            "anno": int(input_data.data_dismissione[:4]),
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db[coll_pn].insert_one(mov_dis.copy())
    
    return {
        "success": True,
        "messaggio": f"Cespite '{cespite['descrizione']}' dismesso",
        "dettaglio": {
            "valore_residuo": round(valore_residuo, 2),
            "prezzo_vendita": prezzo_vendita,
            "plusminusvalenza": round(plusminusvalenza, 2),
            "tipo_risultato": tipo_risultato
        }
    }


class CespiteUpdate(BaseModel):
    descrizione: Optional[str] = None
    fornitore: Optional[str] = None
    numero_fattura: Optional[str] = None
    ubicazione: Optional[str] = None
    note: Optional[str] = None
    valore_acquisto: Optional[float] = None
    data_acquisto: Optional[str] = None


@router.put("/{cespite_id}")
@handle_errors
async def aggiorna_cespite(cespite_id: str, update_data: CespiteUpdate) -> Dict[str, Any]:
    """
    Aggiorna i dati di un cespite esistente.
    Non permette modifica della categoria o del coefficiente.
    """
    db = Database.get_db()
    
    # Verifica che il cespite esista
    cespite = await db["cespiti"].find_one({"id": cespite_id}, {"_id": 0})
    if not cespite:
        raise HTTPException(status_code=404, detail="Cespite non trovato")
    
    # Prepara i campi da aggiornare
    update_fields = {}
    update_dict = update_data.model_dump(exclude_unset=True)
    
    for key, value in update_dict.items():
        if value is not None:
            update_fields[key] = value
    
    # Se viene aggiornato il valore acquisto, ricalcola il residuo
    if "valore_acquisto" in update_fields:
        nuovo_valore = update_fields["valore_acquisto"]
        fondo = cespite.get("fondo_ammortamento", 0)
        update_fields["valore_residuo"] = nuovo_valore - fondo
    
    # Se viene aggiornata la data acquisto, aggiorna anche anno
    if "data_acquisto" in update_fields:
        update_fields["anno_acquisto"] = int(update_fields["data_acquisto"][:4])
    
    if not update_fields:
        return {"success": True, "messaggio": "Nessun campo da aggiornare"}
    
    update_fields["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db["cespiti"].update_one(
        {"id": cespite_id},
        {"$set": update_fields}
    )
    
    return {
        "success": True,
        "messaggio": f"Cespite '{cespite['descrizione']}' aggiornato",
        "campi_aggiornati": list(update_fields.keys())
    }


@router.delete("/{cespite_id}")
@handle_errors
async def elimina_cespite(cespite_id: str) -> Dict[str, Any]:
    """
    Elimina un cespite dal sistema.
    Attenzione: questa operazione è irreversibile.
    Non permette l'eliminazione se ci sono ammortamenti registrati.
    """
    db = Database.get_db()
    
    # Verifica che il cespite esista
    cespite = await db["cespiti"].find_one({"id": cespite_id}, {"_id": 0})
    if not cespite:
        raise HTTPException(status_code=404, detail="Cespite non trovato")
    
    # Verifica che non ci siano ammortamenti registrati
    piano = cespite.get("piano_ammortamento", [])
    if len(piano) > 0:
        raise HTTPException(
            status_code=400, 
            detail=f"Impossibile eliminare: {len(piano)} quote di ammortamento già registrate. Usare la dismissione invece."
        )
    
    # Elimina il cespite
    result = await db["cespiti"].delete_one({"id": cespite_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=500, detail="Errore durante l'eliminazione")
    
    return {
        "success": True,
        "messaggio": f"Cespite '{cespite['descrizione']}' eliminato definitivamente",
        "cespite_eliminato": {
            "id": cespite_id,
            "descrizione": cespite["descrizione"],
            "valore_acquisto": cespite.get("valore_acquisto", 0)
        }
    }

# (scan endpoint moved above /{cespite_id} routes)
