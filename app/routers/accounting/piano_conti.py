"""
Piano dei Conti Router - Contabilità Generale
Gestione del piano dei conti secondo i principi di ragioneria italiana.
"""
from fastapi import APIRouter, HTTPException, Body
from typing import Dict, Any, List
from datetime import datetime, timezone
import uuid
import logging

from app.database import Database
from app.utils.error_handler import handle_errors

logger = logging.getLogger(__name__)
router = APIRouter()

COLLECTION_PIANO_CONTI = "piano_conti"
COLLECTION_MOVIMENTI_CONTABILI = "movimenti_contabili"
COLLECTION_REGOLE_CATEGORIZZAZIONE = "regole_categorizzazione"

# ============== STRUTTURA PIANO DEI CONTI ==============
# Basato sulla ragioneria generale italiana:
# - Gruppo (2 cifre): 01-99
# - Sottogruppo (2 cifre): 01-99  
# - Conto (2 cifre): 01-99
# - Sottoconto (6 cifre): 000001-999999
# Formato codice: GG.SS.CC.SSSSSS

STRUTTURA_BASE = {
    "attivo": {
        "codice": "01",
        "nome": "ATTIVO",
        "descrizione": "Elementi patrimoniali attivi",
        "conti_tipici": [
            {"codice": "01.01.01", "nome": "Cassa", "natura": "finanziario"},
            {"codice": "01.01.02", "nome": "Banca c/c", "natura": "finanziario"},
            {"codice": "01.02.01", "nome": "Crediti v/clienti", "natura": "finanziario"},
            {"codice": "01.03.01", "nome": "Magazzino merci", "natura": "economico"},
            {"codice": "01.04.01", "nome": "IVA a credito", "natura": "finanziario"},
        ]
    },
    "passivo": {
        "codice": "02",
        "nome": "PASSIVO",
        "descrizione": "Elementi patrimoniali passivi",
        "conti_tipici": [
            {"codice": "02.01.01", "nome": "Debiti v/fornitori", "natura": "finanziario"},
            {"codice": "02.02.01", "nome": "Debiti tributari", "natura": "finanziario"},
            {"codice": "02.02.02", "nome": "Debiti v/INPS", "natura": "finanziario"},
            {"codice": "02.03.01", "nome": "IVA a debito", "natura": "finanziario"},
            {"codice": "02.04.01", "nome": "TFR", "natura": "finanziario"},
        ]
    },
    "patrimonio_netto": {
        "codice": "03",
        "nome": "PATRIMONIO NETTO",
        "descrizione": "Capitale proprio",
        "conti_tipici": [
            {"codice": "03.01.01", "nome": "Capitale sociale", "natura": "economico"},
            {"codice": "03.02.01", "nome": "Riserva legale", "natura": "economico"},
            {"codice": "03.03.01", "nome": "Utile d'esercizio", "natura": "economico"},
            {"codice": "03.03.02", "nome": "Perdita d'esercizio", "natura": "economico"},
        ]
    },
    "ricavi": {
        "codice": "04",
        "nome": "RICAVI",
        "descrizione": "Componenti positivi di reddito",
        "conti_tipici": [
            {"codice": "04.01.01", "nome": "Ricavi vendite prodotti", "natura": "economico"},
            {"codice": "04.01.02", "nome": "Ricavi vendite bar", "natura": "economico"},
            {"codice": "04.01.03", "nome": "Ricavi vendite cucina", "natura": "economico"},
            {"codice": "04.02.01", "nome": "Ricavi prestazioni servizi", "natura": "economico"},
            {"codice": "04.03.01", "nome": "Proventi finanziari", "natura": "economico"},
        ]
    },
    "costi": {
        "codice": "05",
        "nome": "COSTI",
        "descrizione": "Componenti negativi di reddito",
        "conti_tipici": [
            {"codice": "05.01.01", "nome": "Acquisto merci", "natura": "economico"},
            {"codice": "05.01.02", "nome": "Acquisto materie prime", "natura": "economico"},
            {"codice": "05.02.01", "nome": "Costi per servizi", "natura": "economico"},
            {"codice": "05.02.02", "nome": "Utenze (luce, gas, acqua)", "natura": "economico"},
            {"codice": "05.02.03", "nome": "Canoni di locazione", "natura": "economico"},
            {"codice": "05.03.01", "nome": "Salari e stipendi", "natura": "economico"},
            {"codice": "05.03.02", "nome": "Contributi previdenziali", "natura": "economico"},
            {"codice": "05.03.03", "nome": "TFR", "natura": "economico"},
            {"codice": "05.04.01", "nome": "Ammortamento immobilizzazioni", "natura": "economico"},
            {"codice": "05.05.01", "nome": "Oneri finanziari", "natura": "economico"},
            {"codice": "05.06.01", "nome": "Imposte e tasse", "natura": "economico"},
        ]
    }
}


@router.get("/")
@handle_errors
async def get_piano_conti() -> Dict[str, Any]:
    """Ottiene il piano dei conti completo con saldi calcolati dai dati reali."""
    db = Database.get_db()
    
    conti = await db[COLLECTION_PIANO_CONTI].find({}, {"_id": 0}).sort("codice", 1).to_list(1000)
    
    if not conti:
        conti = await inizializza_piano_conti_base(db)
    
    # Compute real saldi from invoices and corrispettivi
    costi_res = await db["invoices"].aggregate([
        {"$group": {"_id": None, "totale": {"$sum": "$importo_totale"}, "imponibile": {"$sum": "$importo_imponibile"}, "iva": {"$sum": "$importo_iva"}}}
    ]).to_list(1)
    ricavi_res = await db["corrispettivi"].aggregate([
        {"$match": {"entity_status": {"$ne": "deleted"}}},
        {"$group": {"_id": None, "totale": {"$sum": "$totale"}, "imponibile": {"$sum": "$totale_imponibile"}, "iva": {"$sum": "$totale_iva"}}}
    ]).to_list(1)
    
    real_saldi = {
        "01.02.01": round(ricavi_res[0]["totale"], 2) if ricavi_res else 0,
        "01.04.01": round(costi_res[0]["iva"], 2) if costi_res else 0,
        "02.01.01": round(costi_res[0]["totale"], 2) if costi_res else 0,
        "02.03.01": round(ricavi_res[0]["iva"], 2) if ricavi_res else 0,
        "04.01.01": round(ricavi_res[0]["imponibile"], 2) if ricavi_res else 0,
        "05.01.01": round(costi_res[0]["imponibile"], 2) if costi_res else 0,
    }
    
    # Inject real saldi into conti
    for conto in conti:
        codice = conto.get("codice", "")
        if codice in real_saldi:
            conto["saldo"] = real_saldi[codice]
    
    grouped = {
        "attivo": [],
        "passivo": [],
        "patrimonio_netto": [],
        "ricavi": [],
        "costi": []
    }
    
    for conto in conti:
        categoria = conto.get("categoria", "")
        if categoria in grouped:
            grouped[categoria].append(conto)
    
    return {
        "conti": conti,
        "grouped": grouped,
        "totale": len(conti),
        "struttura": STRUTTURA_BASE
    }


async def inizializza_piano_conti_base(db) -> List[Dict[str, Any]]:
    """Inizializza il piano dei conti con la struttura base."""
    conti = []
    now = datetime.now(timezone.utc).isoformat()
    
    for categoria, data in STRUTTURA_BASE.items():
        for conto_base in data["conti_tipici"]:
            conto = {
                "id": str(uuid.uuid4()),
                "codice": conto_base["codice"],
                "nome": conto_base["nome"],
                "categoria": categoria,
                "gruppo_codice": data["codice"],
                "gruppo_nome": data["nome"],
                "natura": conto_base["natura"],
                "attivo": True,
                "saldo": 0.0,
                "created_at": now,
                "updated_at": now
            }
            conti.append(conto)
    
    if conti:
        await db[COLLECTION_PIANO_CONTI].insert_many(conti)
    
    return conti


@router.post("/")
@handle_errors
async def create_conto(data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Crea un nuovo conto nel piano dei conti."""
    db = Database.get_db()
    
    codice = data.get("codice")
    nome = data.get("nome")
    categoria = data.get("categoria")
    
    if not codice or not nome or not categoria:
        raise HTTPException(status_code=400, detail="Codice, nome e categoria sono obbligatori")
    
    # Verifica unicità codice
    existing = await db[COLLECTION_PIANO_CONTI].find_one({"codice": codice})
    if existing:
        raise HTTPException(status_code=409, detail=f"Conto con codice {codice} già esistente")
    
    now = datetime.now(timezone.utc).isoformat()
    
    conto = {
        "id": str(uuid.uuid4()),
        "codice": codice,
        "nome": nome,
        "categoria": categoria,
        "gruppo_codice": STRUTTURA_BASE.get(categoria, {}).get("codice", ""),
        "gruppo_nome": STRUTTURA_BASE.get(categoria, {}).get("nome", ""),
        "natura": data.get("natura", "economico"),
        "attivo": True,
        "saldo": 0.0,
        "created_at": now,
        "updated_at": now
    }
    
    await db[COLLECTION_PIANO_CONTI].insert_one(conto.copy())
    conto.pop("_id", None)
    
    return {"success": True, "conto": conto}


@router.put("/{conto_id}")
@handle_errors
async def update_conto(conto_id: str, data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Aggiorna un conto esistente."""
    db = Database.get_db()
    
    update_data = {
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    for field in ["nome", "categoria", "natura", "attivo"]:
        if field in data:
            update_data[field] = data[field]
    
    result = await db[COLLECTION_PIANO_CONTI].update_one(
        {"id": conto_id},
        {"$set": update_data}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Conto non trovato")
    
    return {"success": True, "message": "Conto aggiornato"}


@router.delete("/{conto_id}")
@handle_errors
async def delete_conto(conto_id: str) -> Dict[str, Any]:
    """Elimina un conto (se non ha movimenti)."""
    db = Database.get_db()
    
    # Verifica che non ci siano movimenti
    movimenti = await db[COLLECTION_MOVIMENTI_CONTABILI].count_documents({"conto_id": conto_id})
    if movimenti > 0:
        raise HTTPException(status_code=400, detail=f"Impossibile eliminare: il conto ha {movimenti} movimenti")
    
    result = await db[COLLECTION_PIANO_CONTI].delete_one({"id": conto_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Conto non trovato")
    
    return {"success": True, "message": "Conto eliminato"}


# ============== REGOLE DI CATEGORIZZAZIONE ==============

@router.get("/regole")
@handle_errors
async def get_regole_categorizzazione() -> Dict[str, Any]:
    """Ottiene le regole di categorizzazione automatica."""
    db = Database.get_db()
    
    regole = await db[COLLECTION_REGOLE_CATEGORIZZAZIONE].find({}, {"_id": 0}).to_list(100)
    
    # Se non esistono regole, inizializza con quelle base
    if not regole:
        regole = await inizializza_regole_base(db)
    
    return {"regole": regole, "totale": len(regole)}


async def inizializza_regole_base(db) -> List[Dict[str, Any]]:
    """Inizializza le regole di categorizzazione base."""
    regole_base = [
        # Regole per fornitore (keyword nel nome)
        {"tipo": "fornitore", "pattern": "ENEL", "conto_dare": "05.02.02", "conto_avere": "02.01.01", "descrizione": "Utenze elettricità"},
        {"tipo": "fornitore", "pattern": "ENI|EDISON", "conto_dare": "05.02.02", "conto_avere": "02.01.01", "descrizione": "Utenze gas"},
        {"tipo": "fornitore", "pattern": "TELECOM|TIM|VODAFONE|WIND", "conto_dare": "05.02.01", "conto_avere": "02.01.01", "descrizione": "Telefonia"},
        {"tipo": "fornitore", "pattern": "ALIMENTARI|FOOD|DISTRIBUZIONE", "conto_dare": "05.01.01", "conto_avere": "02.01.01", "descrizione": "Acquisto merci"},
        
        # Regole per tipo documento
        {"tipo": "tipo_documento", "pattern": "TD01", "conto_dare": "05.01.01", "conto_avere": "02.01.01", "descrizione": "Fattura acquisto merce"},
        {"tipo": "tipo_documento", "pattern": "TD04", "conto_dare": "02.01.01", "conto_avere": "05.01.01", "descrizione": "Nota di credito ricevuta"},
        
        # Regole per pagamento
        {"tipo": "pagamento", "pattern": "contanti|cassa", "conto_dare": "02.01.01", "conto_avere": "01.01.01", "descrizione": "Pagamento in contanti"},
        {"tipo": "pagamento", "pattern": "banca|bonifico", "conto_dare": "02.01.01", "conto_avere": "01.01.02", "descrizione": "Pagamento tramite banca"},
    ]
    
    now = datetime.now(timezone.utc).isoformat()
    regole = []
    
    for r in regole_base:
        regola = {
            "id": str(uuid.uuid4()),
            "tipo": r["tipo"],
            "pattern": r["pattern"],
            "conto_dare": r["conto_dare"],
            "conto_avere": r["conto_avere"],
            "descrizione": r["descrizione"],
            "attiva": True,
            "created_at": now
        }
        regole.append(regola)
    
    if regole:
        await db[COLLECTION_REGOLE_CATEGORIZZAZIONE].insert_many(regole)
    
    return regole


@router.post("/regole")
@handle_errors
async def create_regola(data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Crea una nuova regola di categorizzazione."""
    db = Database.get_db()
    
    now = datetime.now(timezone.utc).isoformat()
    regola = {
        "id": str(uuid.uuid4()),
        "tipo": data.get("tipo", "fornitore"),
        "pattern": data.get("pattern", ""),
        "conto_dare": data.get("conto_dare", ""),
        "conto_avere": data.get("conto_avere", ""),
        "descrizione": data.get("descrizione", ""),
        "attiva": True,
        "created_at": now
    }
    
    await db[COLLECTION_REGOLE_CATEGORIZZAZIONE].insert_one(regola.copy())
    regola.pop("_id", None)
    
    return {"success": True, "regola": regola}


# ============== REGISTRAZIONE CONTABILE FATTURA ==============

@router.post("/registra-fattura")
@handle_errors
async def registra_fattura_contabilita(data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """
    Registra una fattura nella contabilità generale (partita doppia).
    
    Per una fattura acquisto:
    DARE: Costo acquisto merce (05.01.01) + IVA a credito (01.04.01)
    AVERE: Debito v/fornitore (02.01.01)
    """
    db = Database.get_db()
    
    fattura_id = data.get("fattura_id")
    if not fattura_id:
        raise HTTPException(status_code=400, detail="fattura_id obbligatorio")
    
    # Cerca la fattura
    fattura = await db["invoices"].find_one({"id": fattura_id})
    if not fattura:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    
    # Verifica se già registrata
    existing = await db[COLLECTION_MOVIMENTI_CONTABILI].find_one({"fattura_id": fattura_id})
    if existing:
        return {"success": False, "message": "Fattura già registrata in contabilità", "movimento_id": existing.get("id")}
    
    # Determina i conti da utilizzare
    conti = await determina_conti_fattura(db, fattura)
    
    importo_totale = float(fattura.get("total_amount") or fattura.get("importo_totale") or 0)
    imponibile = float(fattura.get("imponibile") or importo_totale)
    iva = float(fattura.get("iva") or 0)
    
    now = datetime.now(timezone.utc).isoformat()
    movimento_id = str(uuid.uuid4())
    
    # Crea movimento contabile (partita doppia)
    movimento = {
        "id": movimento_id,
        "fattura_id": fattura_id,
        "data_registrazione": now,
        "data_documento": fattura.get("invoice_date") or fattura.get("data_fattura"),
        "numero_documento": fattura.get("invoice_number") or fattura.get("numero_fattura"),
        "fornitore": fattura.get("supplier_name") or fattura.get("cedente_denominazione"),
        "descrizione": f"Fattura {fattura.get('invoice_number') or fattura.get('numero_fattura')}",
        "importo_totale": importo_totale,
        "imponibile": imponibile,
        "iva": iva,
        "righe": [
            # DARE: Costo merce
            {
                "tipo": "DARE",
                "conto_codice": conti["costo"]["codice"],
                "conto_nome": conti["costo"]["nome"],
                "importo": imponibile,
                "descrizione": "Costo acquisto"
            },
            # DARE: IVA a credito
            {
                "tipo": "DARE",
                "conto_codice": conti["iva_credito"]["codice"],
                "conto_nome": conti["iva_credito"]["nome"],
                "importo": iva,
                "descrizione": "IVA a credito"
            },
            # AVERE: Debito fornitore
            {
                "tipo": "AVERE",
                "conto_codice": conti["debito_fornitore"]["codice"],
                "conto_nome": conti["debito_fornitore"]["nome"],
                "importo": importo_totale,
                "descrizione": "Debito v/fornitore"
            }
        ],
        "stato": "registrato",
        "created_at": now
    }
    
    await db[COLLECTION_MOVIMENTI_CONTABILI].insert_one(movimento.copy())
    
    # Aggiorna saldi conti
    await aggiorna_saldo_conto(db, conti["costo"]["codice"], imponibile, "dare")
    await aggiorna_saldo_conto(db, conti["iva_credito"]["codice"], iva, "dare")
    await aggiorna_saldo_conto(db, conti["debito_fornitore"]["codice"], importo_totale, "avere")
    
    # Marca fattura come registrata
    await db["invoices"].update_one(
        {"id": fattura_id},
        {"$set": {"registrata_contabilita": True, "movimento_contabile_id": movimento_id}}
    )
    
    movimento.pop("_id", None)
    
    return {
        "success": True,
        "message": "Fattura registrata in contabilità",
        "movimento": movimento
    }


async def determina_conti_fattura(db, fattura: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    """Determina i conti da utilizzare per una fattura basandosi sulle regole."""
    
    # Conti di default
    conti = {
        "costo": {"codice": "05.01.01", "nome": "Acquisto merci"},
        "iva_credito": {"codice": "01.04.01", "nome": "IVA a credito"},
        "debito_fornitore": {"codice": "02.01.01", "nome": "Debiti v/fornitori"}
    }
    
    # Cerca regole applicabili
    fornitore = (fattura.get("supplier_name") or fattura.get("cedente_denominazione") or "").upper()
    
    regole = await db[COLLECTION_REGOLE_CATEGORIZZAZIONE].find({"attiva": True}).to_list(100)
    
    import re
    for regola in regole:
        pattern = regola.get("pattern", "")
        if not pattern:
            continue
        
        # Applica regola per fornitore
        if regola.get("tipo") == "fornitore":
            if re.search(pattern, fornitore, re.IGNORECASE):
                if regola.get("conto_dare"):
                    conto = await db[COLLECTION_PIANO_CONTI].find_one({"codice": regola["conto_dare"]})
                    if conto:
                        conti["costo"] = {"codice": conto["codice"], "nome": conto["nome"]}
                break
    
    return conti


async def aggiorna_saldo_conto(db, codice_conto: str, importo: float, tipo: str):
    """Aggiorna il saldo di un conto."""
    # Per conti ATTIVO e COSTI: DARE aumenta, AVERE diminuisce
    # Per conti PASSIVO, PN e RICAVI: AVERE aumenta, DARE diminuisce
    
    conto = await db[COLLECTION_PIANO_CONTI].find_one({"codice": codice_conto})
    if not conto:
        return
    
    categoria = conto.get("categoria", "")
    saldo_attuale = float(conto.get("saldo", 0))
    
    # Determina se aumentare o diminuire
    if categoria in ["attivo", "costi"]:
        nuovo_saldo = saldo_attuale + importo if tipo == "dare" else saldo_attuale - importo
    else:  # passivo, patrimonio_netto, ricavi
        nuovo_saldo = saldo_attuale + importo if tipo == "avere" else saldo_attuale - importo
    
    await db[COLLECTION_PIANO_CONTI].update_one(
        {"codice": codice_conto},
        {"$set": {"saldo": nuovo_saldo, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )


# ============== MOVIMENTI CONTABILI ==============

@router.get("/conto/{codice}/movimenti")
@handle_errors
async def get_movimenti_per_conto(
    codice: str,
    limit: int = 50,
    anno: str = None,
) -> Dict[str, Any]:
    """
    Dettaglio movimenti per un conto del piano dei conti.
    Logica SEMANTICA per conto — nessun fuzzy matching inaffidabile:
      - 01.01.01 (Cassa)          → prima_nota_cassa
      - 01.01.02 (Banca c/c)      → estratto_conto_movimenti (tutti)
      - 01.02.* (Crediti)         → fatture_ricevute non incassate
      - 02.01.* (Debiti fornitori) → fatture_ricevute non pagate
      - categoria=costi            → fatture_ricevute pagate
      - categoria=ricavi           → prima_nota_banca tipo=entrata
      - altri                      → info conto senza movimenti
    """
    db = Database.get_db()

    conto = await db["piano_conti"].find_one({"codice": codice}, {"_id": 0})
    if not conto:
        raise HTTPException(status_code=404, detail=f"Conto {codice} non trovato")

    cat  = conto.get("categoria", "").lower()
    nome = conto.get("nome", "")

    movimenti: list = []
    fonte: str      = "nessuna"

    # ── CASSA ────────────────────────────────────────────────────────────────
    if codice == "01.01.01" or "cassa" in nome.lower():
        q_cassa: dict = {}
        if anno:
            q_cassa["data"] = {"$gte": f"{anno}-01-01", "$lte": f"{anno}-12-31"}
        docs = await db["prima_nota"].find(
            q_cassa, {"_id": 0}
        ).sort("data", -1).limit(limit).to_list(limit)
        movimenti = [
            {"data": d.get("data"),
             "descrizione": d.get("causale") or d.get("descrizione") or d.get("riferimento") or "—",
             "importo": abs(d.get("importo", 0)),
             "tipo": d.get("tipo") or ("entrata" if (d.get("importo", 0) or 0) >= 0 else "uscita"),
             "categoria": d.get("categoria", ""),
             "fonte": "Prima Nota Cassa"}
            for d in docs
        ]
        fonte = "prima_nota"

    # ── BANCA C/C ─────────────────────────────────────────────────────────────
    elif codice in ("01.01.02", "01.01.03") or "banca" in nome.lower():
        # Prima prova prima_nota_banca (movimenti manuali confermati)
        q_banca: dict = {}
        if anno:
            q_banca["data"] = {"$gte": f"{anno}-01-01", "$lte": f"{anno}-12-31"}
        docs = await db["prima_nota_banca"].find(
            q_banca, {"_id": 0}
        ).sort("data", -1).limit(limit).to_list(limit)
        if not docs:
            # Fallback: movimenti_bancari (estratto conto completo)
            docs = await db["movimenti_bancari"].find(
                {}, {"_id": 0, "data_contabile": 1, "descrizione": 1, "importo": 1, "tipo": 1, "categoria": 1}
            ).sort("data_contabile", -1).limit(limit).to_list(limit)
            movimenti = [
                {"data": d.get("data_contabile"),
                 "descrizione": d.get("descrizione") or "—",
                 "importo": abs(d.get("importo", 0)),
                 "tipo": d.get("tipo", "uscita"),
                 "categoria": d.get("categoria", ""),
                 "fonte": "Estratto Conto"}
                for d in docs
            ]
            fonte = "movimenti_bancari"
        else:
            movimenti = [
                {"data": d.get("data"),
                 "descrizione": d.get("descrizione") or d.get("causale") or "—",
                 "importo": abs(d.get("importo", 0)),
                 "tipo": d.get("tipo", "uscita"),
                 "categoria": d.get("categoria", ""),
                 "fonte": "Prima Nota Banca"}
                for d in docs
            ]
            fonte = "prima_nota_banca"

    # ── CREDITI V/CLIENTI ─────────────────────────────────────────────────────
    elif codice.startswith("01.02") or "crediti" in nome.lower():
        q_crediti: dict = {}
        if anno:
            q_crediti["data_fattura"] = {"$gte": f"{anno}-01-01", "$lte": f"{anno}-12-31"}
        docs = await db["fatture"].find(
            q_crediti, {"_id": 0, "fornitore": 1, "numero_fattura": 1, "data_fattura": 1, "importo_totale": 1}
        ).sort("data_fattura", -1).limit(limit).to_list(limit)
        movimenti = [
            {"data": d.get("data_fattura"),
             "descrizione": f"Fatt. {d.get('numero_fattura', '')} — {d.get('fornitore', '')}",
             "importo": abs(d.get("importo_totale") or 0),
             "tipo": "entrata", "categoria": "fattura",
             "fonte": "Fatture"}
            for d in docs
        ]
        fonte = "fatture"

    # ── DEBITI V/FORNITORI ────────────────────────────────────────────────────
    elif codice.startswith("02.01") or "debiti" in nome.lower():
        q_debiti: dict = {}
        if anno:
            q_debiti["anno"] = int(anno)
        docs = await db["fatture_passive"].find(
            q_debiti,
            {"_id": 0, "fornitore_denominazione": 1, "numero": 1, "data": 1, "importo_totale": 1, "stato": 1}
        ).sort("data", -1).limit(limit).to_list(limit)
        movimenti = [
            {"data": d.get("data"),
             "descrizione": f"Fatt. {d.get('numero', '')} — {d.get('fornitore_denominazione', '')}",
             "importo": abs(d.get("importo_totale") or 0),
             "tipo": "uscita", "categoria": d.get("stato", ""),
             "fonte": "Fatture Passive"}
            for d in docs
        ]
        fonte = "fatture_passive"

    # ── COSTI / ACQUISTI ──────────────────────────────────────────────────────
    elif cat in ("costi",):
        q_costi: dict = {}
        if anno:
            q_costi["anno"] = int(anno)
        docs = await db["fatture_passive"].find(
            q_costi,
            {"_id": 0, "fornitore_denominazione": 1, "numero": 1, "data": 1, "importo_totale": 1, "stato": 1}
        ).sort("data", -1).limit(limit).to_list(limit)
        movimenti = [
            {"data": d.get("data"),
             "descrizione": f"Fatt. {d.get('numero', '')} — {d.get('fornitore_denominazione', '')}",
             "importo": abs(d.get("importo_totale") or 0),
             "tipo": "uscita", "categoria": d.get("stato", ""),
             "fonte": "Fatture Passive"}
            for d in docs
        ]
        fonte = "fatture_passive"

    # ── RICAVI ────────────────────────────────────────────────────────────────
    elif cat in ("ricavi",):
        q_ricavi: dict = {}
        if anno:
            q_ricavi["anno"] = int(anno)
        docs_corr = await db["corrispettivi"].find(
            q_ricavi, {"_id": 0, "data": 1, "descrizione": 1, "importo": 1, "totale": 1, "totale_imponibile": 1}
        ).sort("data", -1).limit(limit).to_list(limit)
        movimenti = [
            {"data": d.get("data"),
             "descrizione": d.get("descrizione") or "Corrispettivo",
             "importo": abs(d.get("importo") or d.get("totale") or 0),
             "tipo": "entrata", "categoria": "corrispettivo",
             "fonte": "Corrispettivi"}
            for d in docs_corr
        ]
        fonte = "corrispettivi"

    totale_importo = sum(m.get("importo", 0) for m in movimenti)

    return {
        "conto": conto,
        "movimenti": movimenti,
        "totale_movimenti": len(movimenti),
        "totale_importo": round(totale_importo, 2),
        "fonte": fonte,
        "nota": (
            "Movimenti contabili diretti non disponibili — "
            "i dati mostrati provengono dalla fonte più rilevante per questo conto."
        ) if movimenti else (
            "Nessun movimento disponibile. Il saldo è calcolato dalle fatture importate."
        ),
    }


@router.get("/movimenti")
@handle_errors
async def get_movimenti_contabili(
    skip: int = 0,
    limit: int = 50,
    data_da: str = None,
    data_a: str = None
) -> Dict[str, Any]:
    """Ottiene i movimenti contabili."""
    db = Database.get_db()
    
    query = {}
    if data_da:
        query["data_documento"] = {"$gte": data_da}
    if data_a:
        if "data_documento" in query:
            query["data_documento"]["$lte"] = data_a
        else:
            query["data_documento"] = {"$lte": data_a}
    
    movimenti = await db[COLLECTION_MOVIMENTI_CONTABILI].find(
        query, {"_id": 0}
    ).sort("data_registrazione", -1).skip(skip).limit(limit).to_list(limit)
    
    totale = await db[COLLECTION_MOVIMENTI_CONTABILI].count_documents(query)
    
    return {
        "movimenti": movimenti,
        "totale": totale,
        "skip": skip,
        "limit": limit
    }


@router.get("/bilancio")
@handle_errors
async def get_bilancio() -> Dict[str, Any]:
    """Genera il bilancio (situazione patrimoniale ed economica) con dati reali."""
    db = Database.get_db()
    
    conti = await db[COLLECTION_PIANO_CONTI].find({}, {"_id": 0}).to_list(1000)
    
    # Compute real saldi from actual data
    # Costi: sum of all invoices (fatture ricevute)
    costi_pipeline = [
        {"$group": {"_id": None, "totale": {"$sum": "$importo_totale"}, "imponibile": {"$sum": "$importo_imponibile"}, "iva": {"$sum": "$importo_iva"}}}
    ]
    costi_res = await db["invoices"].aggregate(costi_pipeline).to_list(1)
    totale_costi = costi_res[0]["imponibile"] if costi_res else 0
    totale_iva_credito = costi_res[0]["iva"] if costi_res else 0
    totale_debiti_fornitori = costi_res[0]["totale"] if costi_res else 0
    
    # Ricavi: corrispettivi
    ricavi_pipeline = [
        {"$match": {"entity_status": {"$ne": "deleted"}}},
        {"$group": {"_id": None, "totale": {"$sum": "$totale"}, "imponibile": {"$sum": "$totale_imponibile"}, "iva": {"$sum": "$totale_iva"}}}
    ]
    ricavi_res = await db["corrispettivi"].aggregate(ricavi_pipeline).to_list(1)
    totale_ricavi = ricavi_res[0]["imponibile"] if ricavi_res else 0
    totale_iva_debito = ricavi_res[0]["iva"] if ricavi_res else 0
    totale_crediti_clienti = ricavi_res[0]["totale"] if ricavi_res else 0
    
    # Map real values to conti
    real_saldi = {
        "01.01.01": 0,  # Cassa
        "01.01.02": 0,  # Banca c/c
        "01.02.01": round(totale_crediti_clienti, 2),  # Crediti v/clienti
        "01.04.01": round(totale_iva_credito, 2),  # IVA a credito
        "02.01.01": round(totale_debiti_fornitori, 2),  # Debiti v/fornitori
        "02.02.01": round(totale_iva_debito, 2),  # IVA a debito
        "04.01.01": round(totale_ricavi, 2),  # Ricavi
        "05.01.01": round(totale_costi, 2),  # Costi merci
    }
    
    bilancio = {
        "stato_patrimoniale": {
            "attivo": {"conti": [], "totale": 0},
            "passivo": {"conti": [], "totale": 0},
            "patrimonio_netto": {"conti": [], "totale": 0}
        },
        "conto_economico": {
            "ricavi": {"conti": [], "totale": 0},
            "costi": {"conti": [], "totale": 0},
            "risultato": 0
        }
    }
    
    for conto in conti:
        codice = conto.get("codice", "")
        saldo = real_saldi.get(codice, float(conto.get("saldo", 0)))
        categoria = conto.get("categoria", "")
        
        conto_info = {
            "codice": codice,
            "nome": conto.get("nome"),
            "saldo": saldo
        }
        
        if categoria == "attivo":
            bilancio["stato_patrimoniale"]["attivo"]["conti"].append(conto_info)
            bilancio["stato_patrimoniale"]["attivo"]["totale"] += saldo
        elif categoria == "passivo":
            bilancio["stato_patrimoniale"]["passivo"]["conti"].append(conto_info)
            bilancio["stato_patrimoniale"]["passivo"]["totale"] += saldo
        elif categoria == "patrimonio_netto":
            bilancio["stato_patrimoniale"]["patrimonio_netto"]["conti"].append(conto_info)
            bilancio["stato_patrimoniale"]["patrimonio_netto"]["totale"] += saldo
        elif categoria == "ricavi":
            bilancio["conto_economico"]["ricavi"]["conti"].append(conto_info)
            bilancio["conto_economico"]["ricavi"]["totale"] += saldo
        elif categoria == "costi":
            bilancio["conto_economico"]["costi"]["conti"].append(conto_info)
            bilancio["conto_economico"]["costi"]["totale"] += saldo
    
    bilancio["conto_economico"]["risultato"] = (
        bilancio["conto_economico"]["ricavi"]["totale"] - 
        bilancio["conto_economico"]["costi"]["totale"]
    )
    
    # Round totals
    for key in ["attivo", "passivo", "patrimonio_netto"]:
        bilancio["stato_patrimoniale"][key]["totale"] = round(bilancio["stato_patrimoniale"][key]["totale"], 2)
    for key in ["ricavi", "costi"]:
        bilancio["conto_economico"][key]["totale"] = round(bilancio["conto_economico"][key]["totale"], 2)
    bilancio["conto_economico"]["risultato"] = round(bilancio["conto_economico"]["risultato"], 2)
    
    return bilancio


@router.post("/registra-tutte-fatture")
@handle_errors
async def registra_tutte_fatture_contabilita() -> Dict[str, Any]:
    """
    Registra tutte le fatture non ancora registrate in contabilità.
    Utile per inizializzazione o recupero dati.
    """
    db = Database.get_db()
    
    # Trova fatture non registrate
    fatture = await db["invoices"].find({
        "$or": [
            {"registrata_contabilita": {"$ne": True}},
            {"registrata_contabilita": {"$exists": False}}
        ]
    }, {"_id": 0}).to_list(5000)
    
    registrate = 0
    errori = []
    
    for fattura in fatture:
        try:
            fattura_id = fattura.get("id")
            if not fattura_id:
                continue
            
            # Estrai importi
            imponibile = float(fattura.get("total_amount", 0) or 0) - float(fattura.get("total_tax", 0) or 0)
            iva = float(fattura.get("total_tax", fattura.get("totale_iva", 0)) or 0)
            importo_totale = imponibile + iva
            
            if importo_totale <= 0:
                continue
            
            # Determina conti
            conti = await determina_conti_fattura(db, fattura)
            
            # Crea movimento
            movimento_id = str(uuid.uuid4())
            data_fattura = fattura.get("invoice_date", datetime.now(timezone.utc).isoformat()[:10])
            
            movimento = {
                "id": movimento_id,
                "tipo": "fattura_acquisto",
                "data": data_fattura,
                "descrizione": f"Fattura {fattura.get('invoice_number', '')} - {fattura.get('supplier_name', '')}",
                "fattura_id": fattura_id,
                "righe": [
                    {
                        "conto_codice": conti["costo"]["codice"],
                        "conto_nome": conti["costo"]["nome"],
                        "dare": imponibile,
                        "avere": 0
                    },
                    {
                        "conto_codice": conti["iva_credito"]["codice"],
                        "conto_nome": conti["iva_credito"]["nome"],
                        "dare": iva,
                        "avere": 0
                    },
                    {
                        "conto_codice": conti["debito_fornitore"]["codice"],
                        "conto_nome": conti["debito_fornitore"]["nome"],
                        "dare": 0,
                        "avere": importo_totale
                    }
                ],
                "totale_dare": imponibile + iva,
                "totale_avere": importo_totale,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            
            await db[COLLECTION_MOVIMENTI_CONTABILI].insert_one(movimento.copy())
            
            # Aggiorna saldi
            await aggiorna_saldo_conto(db, conti["costo"]["codice"], imponibile, "dare")
            await aggiorna_saldo_conto(db, conti["iva_credito"]["codice"], iva, "dare")
            await aggiorna_saldo_conto(db, conti["debito_fornitore"]["codice"], importo_totale, "avere")
            
            # Marca fattura
            await db["invoices"].update_one(
                {"id": fattura_id},
                {"$set": {"registrata_contabilita": True, "movimento_contabile_id": movimento_id}}
            )
            
            registrate += 1
            
        except Exception as e:
            errori.append(f"Fattura {fattura.get('invoice_number', 'N/A')}: {str(e)}")
    
    return {
        "success": True,
        "fatture_processate": len(fatture),
        "registrate": registrate,
        "errori": errori[:20]
    }


@router.post("/registra-corrispettivi")
@handle_errors
async def registra_corrispettivi_contabilita() -> Dict[str, Any]:
    """
    Registra i corrispettivi in contabilità.
    Crea movimenti: Cassa/Banca -> Ricavi e IVA a debito
    """
    db = Database.get_db()
    
    # Trova corrispettivi non registrati
    corrispettivi = await db["corrispettivi"].find({
        "$or": [
            {"registrato_contabilita": {"$ne": True}},
            {"registrato_contabilita": {"$exists": False}}
        ]
    }, {"_id": 0}).to_list(5000)
    
    registrati = 0
    errori = []
    
    for corr in corrispettivi:
        try:
            corr_id = corr.get("id")
            if not corr_id:
                continue
            
            totale = float(corr.get("totale", 0) or 0)
            if totale <= 0:
                continue
            
            # Calcola IVA (tipicamente 10% per ristorazione)
            aliquota = 0.10
            iva = round(totale * aliquota / (1 + aliquota), 2)
            imponibile = totale - iva
            
            # Importi per tipo pagamento
            cassa = float(corr.get("pagato_contante", corr.get("pagato_cassa", 0)) or 0)
            pos = float(corr.get("pagato_elettronico", 0) or 0)
            
            if cassa + pos == 0:
                cassa = totale  # Default tutto in cassa
            
            # Crea movimento
            movimento_id = str(uuid.uuid4())
            data_corr = corr.get("data", datetime.now(timezone.utc).isoformat()[:10])
            
            righe = []
            
            # Entrata cassa
            if cassa > 0:
                righe.append({
                    "conto_codice": "01.01.01",
                    "conto_nome": "Cassa",
                    "dare": cassa,
                    "avere": 0
                })
            
            # Entrata banca (POS)
            if pos > 0:
                righe.append({
                    "conto_codice": "01.01.02",
                    "conto_nome": "Banca c/c",
                    "dare": pos,
                    "avere": 0
                })
            
            # Ricavi vendite
            righe.append({
                "conto_codice": "04.01.02",
                "conto_nome": "Ricavi vendite bar",
                "dare": 0,
                "avere": imponibile
            })
            
            # IVA a debito
            righe.append({
                "conto_codice": "02.03.01",
                "conto_nome": "IVA a debito",
                "dare": 0,
                "avere": iva
            })
            
            movimento = {
                "id": movimento_id,
                "tipo": "corrispettivo",
                "data": data_corr,
                "descrizione": f"Corrispettivo del {data_corr}",
                "corrispettivo_id": corr_id,
                "righe": righe,
                "totale_dare": cassa + pos,
                "totale_avere": totale,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            
            await db[COLLECTION_MOVIMENTI_CONTABILI].insert_one(movimento.copy())
            
            # Aggiorna saldi
            if cassa > 0:
                await aggiorna_saldo_conto(db, "01.01.01", cassa, "dare")
            if pos > 0:
                await aggiorna_saldo_conto(db, "01.01.02", pos, "dare")
            await aggiorna_saldo_conto(db, "04.01.02", imponibile, "avere")
            await aggiorna_saldo_conto(db, "02.03.01", iva, "avere")
            
            # Marca corrispettivo
            await db["corrispettivi"].update_one(
                {"id": corr_id},
                {"$set": {"registrato_contabilita": True, "movimento_contabile_id": movimento_id}}
            )
            
            registrati += 1
            
        except Exception as e:
            errori.append(f"Corrispettivo {corr.get('id', 'N/A')}: {str(e)}")
    
    return {
        "success": True,
        "corrispettivi_processati": len(corrispettivi),
        "registrati": registrati,
        "errori": errori[:20]
    }
