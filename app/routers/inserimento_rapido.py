"""
Router Inserimento Rapido - Endpoint semplificati per mobile
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from pydantic import BaseModel
import uuid

from app.database import Database

router = APIRouter(prefix="/rapido", tags=["Inserimento Rapido"])


class CorrispettivoInput(BaseModel):
    data: str
    importo: float
    descrizione: Optional[str] = "Corrispettivo giornaliero"
    tipo: Optional[str] = "CONTANTI"


class MovimentoInput(BaseModel):
    data: str
    importo: float
    descrizione: Optional[str] = ""
    tipo: str
    conto_dare: str
    conto_avere: str


class AccontoInput(BaseModel):
    dipendente_id: str
    importo: float
    data: str
    note: Optional[str] = ""


class PresenzaInput(BaseModel):
    dipendente_id: str
    data: str
    tipo: str  # PRESENTE, FERIE, MALATTIA, PERMESSO
    ore: Optional[float] = None
    note: Optional[str] = ""


@router.post("/corrispettivo")
async def salva_corrispettivo(data: CorrispettivoInput) -> Dict[str, Any]:
    """Salva un corrispettivo manuale."""
    db = Database.get_db()
    
    doc = {
        "id": str(uuid.uuid4()),
        "data": data.data,
        "importo": data.importo,
        "descrizione": data.descrizione,
        "tipo": data.tipo,
        "source": "inserimento_rapido",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db["corrispettivi_manuali"].insert_one(doc.copy())
    
    # Registra anche in prima nota cassa
    prima_nota = {
        "id": str(uuid.uuid4()),
        "data": data.data,
        "descrizione": data.descrizione,
        "importo": data.importo,
        "tipo": "CORRISPETTIVO",
        "conto_dare": "CASSA",
        "conto_avere": "RICAVI_VENDITE",
        "source": "inserimento_rapido",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db["prima_nota_cassa"].insert_one(prima_nota.copy())
    
    return {"success": True, "id": doc["id"], "message": "Corrispettivo salvato"}


@router.post("/versamento-banca")
async def salva_versamento_banca(data: MovimentoInput) -> Dict[str, Any]:
    """Salva un versamento dalla cassa alla banca."""
    db = Database.get_db()
    
    doc = {
        "id": str(uuid.uuid4()),
        "data": data.data,
        "importo": data.importo,
        "descrizione": data.descrizione or "Versamento in banca",
        "tipo": "VERSAMENTO_BANCA",
        "conto_dare": "BANCA",
        "conto_avere": "CASSA",
        "source": "inserimento_rapido",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    # Movimento negativo in cassa
    await db["prima_nota_cassa"].insert_one({
        **doc,
        "id": str(uuid.uuid4()),
        "importo": -data.importo,  # Uscita dalla cassa
        "tipo": "VERSAMENTO_USCITA"
    })
    
    # Movimento positivo in banca
    await db["prima_nota_banca"].insert_one({
        **doc,
        "tipo": "VERSAMENTO_ENTRATA"
    })
    
    return {"success": True, "id": doc["id"], "message": "Versamento salvato"}


@router.post("/apporto-soci")
async def salva_apporto_soci(data: MovimentoInput) -> Dict[str, Any]:
    """Salva un apporto soci."""
    db = Database.get_db()
    
    destinazione = "BANCA" if data.conto_dare == "BANCA" else "CASSA"
    collection = "prima_nota_banca" if destinazione == "BANCA" else "prima_nota_cassa"
    
    doc = {
        "id": str(uuid.uuid4()),
        "data": data.data,
        "importo": data.importo,
        "descrizione": data.descrizione or "Apporto soci",
        "tipo": "APPORTO_SOCI",
        "conto_dare": destinazione,
        "conto_avere": "CAPITALE_SOCIALE",
        "source": "inserimento_rapido",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db[collection].insert_one(doc)
    
    return {"success": True, "id": doc["id"], "message": "Apporto salvato"}


@router.post("/acconto-dipendente")
async def salva_acconto_dipendente(data: AccontoInput) -> Dict[str, Any]:
    """Salva un acconto a un dipendente."""
    db = Database.get_db()
    
    # Cerca dipendente in più collezioni
    dipendente = None
    for coll in ["employees", "dipendenti", "anagrafica_dipendenti"]:
        dipendente = await db[coll].find_one({"id": data.dipendente_id})
        if dipendente:
            break
    
    if not dipendente:
        raise HTTPException(status_code=404, detail="Dipendente non trovato")
    
    # Estrai nome/cognome
    nome = dipendente.get("nome") or dipendente.get("name", "")
    cognome = dipendente.get("cognome") or dipendente.get("surname", "")
    
    doc = {
        "id": str(uuid.uuid4()),
        "dipendente_id": data.dipendente_id,
        "dipendente_nome": f"{cognome} {nome}".strip(),
        "data": data.data,
        "importo": data.importo,
        "note": data.note,
        "tipo": "ACCONTO",
        "source": "inserimento_rapido",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db["acconti_dipendenti"].insert_one(doc)
    
    return {"success": True, "id": doc["id"], "message": "Acconto salvato"}


@router.post("/presenza")
async def salva_presenza(data: PresenzaInput) -> Dict[str, Any]:
    """Salva una presenza o assenza."""
    db = Database.get_db()
    
    # Cerca dipendente in più collezioni
    dipendente = None
    for coll in ["employees", "dipendenti", "anagrafica_dipendenti"]:
        dipendente = await db[coll].find_one({"id": data.dipendente_id})
        if dipendente:
            break
    
    if not dipendente:
        raise HTTPException(status_code=404, detail="Dipendente non trovato")
    
    # Estrai nome/cognome
    nome = dipendente.get("nome") or dipendente.get("name", "")
    cognome = dipendente.get("cognome") or dipendente.get("surname", "")
    
    # Mappa tipo a giustificativo
    tipo_map = {
        "PRESENTE": {"codice": "ORD", "descrizione": "Ordinario"},
        "FERIE": {"codice": "FER", "descrizione": "Ferie"},
        "MALATTIA": {"codice": "MAL", "descrizione": "Malattia"},
        "PERMESSO": {"codice": "PER", "descrizione": "Permesso"}
    }
    
    giustificativo = tipo_map.get(data.tipo, {"codice": "ORD", "descrizione": data.tipo})
    
    # Calcola ore
    ore = data.ore if data.ore else (8 if data.tipo == "PRESENTE" else 0)
    
    doc = {
        "id": str(uuid.uuid4()),
        "dipendente_id": data.dipendente_id,
        "dipendente_nome": f"{cognome} {nome}".strip(),
        "data": data.data,
        "tipo": data.tipo,
        "giustificativo_codice": giustificativo["codice"],
        "giustificativo_descrizione": giustificativo["descrizione"],
        "ore": ore,
        "note": data.note,
        "source": "inserimento_rapido",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    # Verifica se esiste già una presenza per questo giorno
    existing = await db["presenze"].find_one({
        "dipendente_id": data.dipendente_id,
        "data": data.data
    })
    
    if existing:
        # Aggiorna
        await db["presenze"].update_one(
            {"id": existing["id"]},
            {"$set": doc}
        )
        doc["id"] = existing["id"]
    else:
        # Inserisci
        await db["presenze"].insert_one(doc)
    
    return {"success": True, "id": doc["id"], "message": "Presenza salvata"}


@router.post("/paga-fattura")
async def paga_fattura_rapido(
    invoice_id: str,
    metodo_pagamento: str,
    importo: Optional[float] = None
) -> Dict[str, Any]:
    """Registra il pagamento di una fattura (endpoint rapido senza auth)."""
    db = Database.get_db()
    
    # Trova la fattura
    fattura = await db["invoices"].find_one({"id": invoice_id})
    if not fattura:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    
    # Usa l'importo fornito o quello della fattura
    amount = importo or fattura.get("total_amount", 0)
    
    # Aggiorna la fattura
    update = {
        "metodo_pagamento": metodo_pagamento,
        "pagata": True,
        "data_pagamento": datetime.now(timezone.utc).isoformat().split("T")[0],
        "importo_pagato": amount,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db["invoices"].update_one(
        {"id": invoice_id},
        {"$set": update}
    )
    
    return {
        "success": True,
        "message": f"Fattura pagata in {metodo_pagamento}",
        "invoice_id": invoice_id,
        "importo": amount
    }


@router.get("/ultimi-inserimenti")
async def get_ultimi_inserimenti(limit: int = 10) -> Dict[str, Any]:
    """Recupera gli ultimi inserimenti da tutte le sezioni."""
    db = Database.get_db()
    
    inserimenti = []
    
    # Corrispettivi
    cursor = db["corrispettivi_manuali"].find(
        {"source": "inserimento_rapido"},
        {"_id": 0}
    ).sort("created_at", -1).limit(limit)
    async for doc in cursor:
        inserimenti.append({
            "tipo": "corrispettivo",
            "descrizione": f"Corrispettivo €{doc.get('importo', 0):.2f}",
            "data": doc.get("data"),
            "created_at": doc.get("created_at"),
            "importo": doc.get("importo")
        })
    
    # Versamenti banca
    cursor = db["prima_nota_banca"].find(
        {"source": "inserimento_rapido", "tipo": "VERSAMENTO_ENTRATA"},
        {"_id": 0}
    ).sort("created_at", -1).limit(limit)
    async for doc in cursor:
        inserimenti.append({
            "tipo": "versamento",
            "descrizione": f"Versamento banca €{doc.get('importo', 0):.2f}",
            "data": doc.get("data"),
            "created_at": doc.get("created_at"),
            "importo": doc.get("importo")
        })
    
    # Acconti
    cursor = db["acconti_dipendenti"].find(
        {"source": "inserimento_rapido"},
        {"_id": 0}
    ).sort("created_at", -1).limit(limit)
    async for doc in cursor:
        inserimenti.append({
            "tipo": "acconto",
            "descrizione": f"Acconto {doc.get('dipendente_nome', '')} €{doc.get('importo', 0):.2f}",
            "data": doc.get("data"),
            "created_at": doc.get("created_at"),
            "importo": doc.get("importo")
        })
    
    # Presenze
    cursor = db["presenze"].find(
        {"source": "inserimento_rapido"},
        {"_id": 0}
    ).sort("created_at", -1).limit(limit)
    async for doc in cursor:
        inserimenti.append({
            "tipo": "presenza",
            "descrizione": f"{doc.get('dipendente_nome', '')} - {doc.get('tipo', '')}",
            "data": doc.get("data"),
            "created_at": doc.get("created_at"),
            "ore": doc.get("ore")
        })
    
    # Ordina per data creazione
    inserimenti.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    
    return {"inserimenti": inserimenti[:limit]}


@router.get("/dipendenti-attivi")
async def get_dipendenti_attivi() -> Dict[str, Any]:
    """Lista dipendenti attivi per selezione rapida."""
    db = Database.get_db()
    
    # Prima prova 'employees', poi 'dipendenti', poi 'anagrafica_dipendenti'
    collections_to_try = ["employees", "dipendenti", "anagrafica_dipendenti", "_deprecated_anagrafica_dipendenti"]
    
    dipendenti = []
    for coll_name in collections_to_try:
        cursor = db[coll_name].find(
            {"$or": [{"in_carico": True}, {"in_carico": {"$exists": False}}, {"active": True}, {"active": {"$exists": False}}]},
            {"_id": 0, "id": 1, "nome": 1, "cognome": 1, "name": 1, "surname": 1}
        ).sort([("cognome", 1), ("surname", 1)])
        
        async for d in cursor:
            # Normalizza i campi
            dipendente = {
                "id": d.get("id", str(d.get("_id", ""))),
                "nome": d.get("nome") or d.get("name", ""),
                "cognome": d.get("cognome") or d.get("surname", "")
            }
            if dipendente["nome"] or dipendente["cognome"]:
                dipendenti.append(dipendente)
        
        if dipendenti:
            break  # Usa la prima collezione con dati
    
    return {"dipendenti": dipendenti}
