"""
Router per gestione Prodotti Finiti (in vendita).
Diverso da Ricettario (ricette) e Lotti (tracciabilità).
"""

import os
from datetime import datetime, timezone
from typing import List, Optional
import uuid

from fastapi import APIRouter, HTTPException
from app.routers.tracciabilita.server import db
from pydantic import BaseModel

router = APIRouter(prefix="/prodotti-vendita", tags=["Prodotti Vendita"])

# MongoDB connection


class ProdottoVendita(BaseModel):
    nome: str
    categoria: str = ""
    descrizione: str = ""
    ricetta_id: Optional[str] = None
    fonte: str = "interno"
    fornitore: str = ""
    pezzi_cartone: Optional[int] = None
    pezzi_per_ricetta: Optional[int] = None
    pezzi_singolo: Optional[int] = None       # Pezzi per confezione singola
    peso_pezzo_g: Optional[float] = None
    codice_prodotto: str = ""
    prezzo_vendita: float = 0
    costo_produzione: float = 0
    costo_produzione_cartone: float = 0       # Costo dell'intero cartone
    margine_percentuale: float = 0
    margine_euro: float = 0
    iva: float = 10                            # -1 = IVA compresa, 0 = Esente, 4/10/22 = %
    iva_compresa_aliquota: float = 10          # Aliquota quando iva = -1 (IVA compresa)
    prezzo_ivato: float = 0
    prezzo_netto: float = 0
    attivo: bool = True
    visibile_tablet: bool = True
    visibile_ricette: bool = True
    stagionale: bool = False
    stagione_note: str = ""
    allergeni: List[str] = []
    ingredienti: str = ""                     # Lista ingredienti dal listino
    istruzioni_cottura: str = ""              # Istruzioni forno/scongelamento
    acquaviva_id: str = ""                    # ID prodotto nel catalogo Acquaviva
    vegano: bool = False
    immagine_url: Optional[str] = None


class ProdottoResponse(ProdottoVendita):
    id: str
    created_at: str
    updated_at: Optional[str] = None


@router.get("/")
async def get_prodotti_vendita(
    solo_attivi: bool = True,
    categoria: Optional[str] = None
):
    """Lista prodotti in vendita con prezzi e margini"""
    query = {}
    if solo_attivi:
        query["attivo"] = True
    if categoria:
        query["categoria"] = categoria
    
    prodotti = await db.prodotti_vendita.find(query, {"_id": 0}).to_list(1000)
    
    # Ricalcola margini per ogni prodotto
    for p in prodotti:
        pv = float(p.get("prezzo_vendita", 0) or 0)
        cp = float(p.get("costo_produzione", 0) or 0)
        iva = float(p.get("iva", 10) or 10)
        p["prezzo_vendita"] = pv
        p["costo_produzione"] = cp
        if pv > 0 and cp > 0:
            margine = pv - cp
            p["margine_euro"] = round(margine, 2)
            p["margine_percentuale"] = round((margine / pv) * 100, 1)
            p["prezzo_ivato"] = round(pv * (1 + iva / 100), 2)
        elif pv > 0:
            p["prezzo_ivato"] = round(pv * (1 + iva / 100), 2)
    
    return prodotti


@router.get("/categorie")
async def get_categorie():
    """Lista categorie prodotti"""
    categorie = await db.prodotti_vendita.distinct("categoria")
    return [c for c in categorie if c]


@router.get("/anteprima-prezzi-margine")
async def anteprima_prezzi_margine(margine_percentuale: float = 30.0):
    """
    Restituisce un'anteprima dei prezzi calcolati per i prodotti senza prezzo,
    senza salvare nulla nel DB. Usata per mostrare la preview nel modal.
    """
    query = {
        "costo_produzione": {"$gt": 0},
        "$or": [
            {"prezzo_vendita": {"$exists": False}},
            {"prezzo_vendita": 0},
            {"prezzo_vendita": None}
        ]
    }
    prodotti = await db.prodotti_vendita.find(query, {"_id": 0}).to_list(1000)
    preview = []
    for p in prodotti:
        costo = float(p.get("costo_produzione") or 0)
        if costo <= 0:
            continue
        prezzo = round(costo / (1 - margine_percentuale / 100), 2)
        iva = float(p.get("iva", 10) or 10)
        preview.append({
            "id": p["id"],
            "nome": p["nome"],
            "costo": costo,
            "prezzo_suggerito": prezzo,
            "prezzo_ivato": round(prezzo * (1 + iva / 100), 2),
            "categoria": p.get("categoria", ""),
            "fonte": p.get("fonte", "")
        })
    return sorted(preview, key=lambda x: x["nome"])


@router.get("/{prodotto_id}")
async def get_prodotto(prodotto_id: str):
    """Dettaglio singolo prodotto"""
    prodotto = await db.prodotti_vendita.find_one({"id": prodotto_id}, {"_id": 0})
    if not prodotto:
        raise HTTPException(status_code=404, detail="Prodotto non trovato")
    return prodotto


@router.post("/")
async def create_prodotto(prodotto: ProdottoVendita):
    """Crea nuovo prodotto in vendita"""
    
    # Se collegato a ricetta, prendi costo e allergeni
    if prodotto.ricetta_id:
        ricetta = await db.ricette.find_one({"id": prodotto.ricetta_id}, {"_id": 0})
        if ricetta:
            prodotto.allergeni = ricetta.get("allergeni", [])
            # Calcola costo dalla ricetta tramite food cost — usa costo_porzione (per pezzo)
            try:
                from routers.food_cost import calcola_food_cost_ricetta
                costo = await calcola_food_cost_ricetta(prodotto.ricetta_id)
                # USA costo_porzione (per pezzo) non costo_totale (dell'intera ricetta)
                prodotto.costo_produzione = costo.get("costo_porzione") or costo.get("costo_totale", 0)
            except Exception:
                pass
    
    # Calcola margini
    if prodotto.prezzo_vendita > 0 and prodotto.costo_produzione > 0:
        prodotto.margine_euro = round(prodotto.prezzo_vendita - prodotto.costo_produzione, 2)
        prodotto.margine_percentuale = round((prodotto.margine_euro / prodotto.prezzo_vendita) * 100, 1)
    
    prodotto.prezzo_ivato = round(prodotto.prezzo_vendita * (1 + prodotto.iva / 100), 2)
    
    doc = prodotto.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["created_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.prodotti_vendita.insert_one(doc)
    
    if "_id" in doc:
        del doc["_id"]
    return doc


@router.put("/{prodotto_id}")
async def aggiorna_prodotto(prodotto_id: str, prodotto: ProdottoVendita):
    """Aggiorna prodotto completo (nome, categoria, prezzi, ecc.)"""
    existing = await db.prodotti_vendita.find_one({"id": prodotto_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Prodotto non trovato")
    
    pv = float(prodotto.prezzo_vendita or 0)
    cp = float(prodotto.costo_produzione or 0)
    iva = float(prodotto.iva or 10)
    
    update_data = prodotto.model_dump()
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    update_data["prezzo_ivato"] = round(pv * (1 + iva / 100), 2)
    
    if pv > 0 and cp > 0:
        margine = pv - cp
        update_data["margine_euro"] = round(margine, 2)
        update_data["margine_percentuale"] = round((margine / pv) * 100, 1)
    else:
        update_data["margine_euro"] = 0
        update_data["margine_percentuale"] = 0
    
    await db.prodotti_vendita.update_one({"id": prodotto_id}, {"$set": update_data})
    updated = await db.prodotti_vendita.find_one({"id": prodotto_id}, {"_id": 0})
    return updated


@router.put("/{prodotto_id}/prezzo")
async def aggiorna_prezzo_prodotto(prodotto_id: str, prezzo_vendita: float, iva: float = 10):
    """Aggiorna rapidamente solo il prezzo di vendita"""
    prodotto = await db.prodotti_vendita.find_one({"id": prodotto_id}, {"_id": 0})
    if not prodotto:
        raise HTTPException(status_code=404, detail="Prodotto non trovato")
    
    costo = float(prodotto.get("costo_produzione", 0) or 0)
    iva_rate = float(prodotto.get("iva", iva) or iva)
    
    update = {
        "prezzo_vendita": prezzo_vendita,
        "prezzo_ivato": round(prezzo_vendita * (1 + iva_rate / 100), 2),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    if prezzo_vendita > 0 and costo > 0:
        margine = prezzo_vendita - costo
        update["margine_euro"] = round(margine, 2)
        update["margine_percentuale"] = round((margine / prezzo_vendita) * 100, 1)
    elif prezzo_vendita > 0:
        update["margine_euro"] = 0
        update["margine_percentuale"] = 0
    
    await db.prodotti_vendita.update_one({"id": prodotto_id}, {"$set": update})
    updated = await db.prodotti_vendita.find_one({"id": prodotto_id}, {"_id": 0})
    return updated


@router.get("/{prodotto_id}/presenza")
async def get_presenza_prodotto(prodotto_id: str):
    """
    Restituisce dove appare un prodotto nel sistema:
    - prodotti_vendita (il record stesso)
    - ricette (come ingrediente)
    - magazzino
    - dizionario_prodotti (eventuale voce)
    """
    prod = await db.prodotti_vendita.find_one({"id": prodotto_id}, {"_id": 0})
    if not prod:
        raise HTTPException(status_code=404, detail="Prodotto non trovato")

    nome = prod.get("nome", "").lower()
    codice = str(prod.get("codice_prodotto", "") or "")

    # Cerca nelle ricette come ingrediente
    ricette_con_prod = []
    async for r in db.ricette.find({"ingredienti.nome": {"$regex": nome[:15], "$options": "i"}}, {"_id": 0, "nome": 1, "id": 1}):
        ricette_con_prod.append(r.get("nome", r.get("id", "?")))

    # Cerca nel magazzino
    mag = await db.magazzino.find_one(
        {"$or": [
            {"prodotto_id": prodotto_id},
            {"nome": {"$regex": nome[:15], "$options": "i"}}
        ]}, {"_id": 0}
    )

    # Cerca nel dizionario
    diz = await db.dizionario_prodotti.find_one(
        {"$or": [
            {"codice_prodotto": codice} if codice else {"_id": None},
            {"nome_normalizzato": {"$regex": nome[:15], "$options": "i"}}
        ]}, {"_id": 0, "id": 1, "nome_normalizzato": 1}
    )

    return {
        "prodotto": {"id": prodotto_id, "nome": prod.get("nome")},
        "presenza": {
            "prodotti_vendita": True,
            "ricette": ricette_con_prod,
            "magazzino": mag is not None,
            "dizionario": diz is not None,
        }
    }


@router.delete("/{prodotto_id}/cascade")
async def delete_prodotto_cascade(
    prodotto_id: str,
    da_prodotti: bool = True,
    da_ricette: bool = False,
    da_magazzino: bool = False,
    da_dizionario: bool = False
):
    """
    Elimina un prodotto da una o più sezioni del sistema.
    Query params: da_prodotti, da_ricette, da_magazzino, da_dizionario
    """
    prod = await db.prodotti_vendita.find_one({"id": prodotto_id}, {"_id": 0})
    if not prod:
        raise HTTPException(status_code=404, detail="Prodotto non trovato")

    nome = prod.get("nome", "").lower()
    codice = str(prod.get("codice_prodotto", "") or "")
    results = {}

    if da_prodotti:
        r = await db.prodotti_vendita.delete_one({"id": prodotto_id})
        results["prodotti_vendita"] = r.deleted_count

    if da_ricette:
        # Rimuovi l'ingrediente da tutte le ricette che lo contengono
        # MongoDB: rimuove l'elemento dall'array ingredienti
        r = await db.ricette.update_many(
            {"ingredienti.nome": {"$regex": nome[:15], "$options": "i"}},
            {"$pull": {"ingredienti": {"nome": {"$regex": nome[:15], "$options": "i"}}}}
        )
        results["ricette_modificate"] = r.modified_count

    if da_magazzino:
        r = await db.magazzino.delete_many(
            {"$or": [
                {"prodotto_id": prodotto_id},
                {"nome": {"$regex": nome[:15], "$options": "i"}}
            ]}
        )
        results["magazzino"] = r.deleted_count

    if da_dizionario:
        query_diz: dict = {}
        if codice:
            query_diz = {"$or": [
                {"codice_prodotto": codice},
                {"nome_normalizzato": {"$regex": nome[:15], "$options": "i"}}
            ]}
        else:
            query_diz = {"nome_normalizzato": {"$regex": nome[:15], "$options": "i"}}
        r = await db.dizionario_prodotti.delete_many(query_diz)
        results["dizionario"] = r.deleted_count

    return {"success": True, "eliminati": results}


@router.delete("/{prodotto_id}")
async def delete_prodotto(prodotto_id: str):
    """Elimina prodotto"""
    result = await db.prodotti_vendita.delete_one({"id": prodotto_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Prodotto non trovato")
    return {"success": True}


@router.post("/sync-acquaviva")
async def sync_prodotti_acquaviva():
    """
    Sincronizza i prodotti Acquaviva dal dizionario prodotti.
    Crea un prodotto vendita per ogni voce del dizionario con fornitore Acquaviva.
    """
    prodotti_acq = await db.dizionario_prodotti.find(
        {"fornitore": {"$regex": "acquaviva", "$options": "i"}},
        {"_id": 0}
    ).to_list(1000)

    esistenti = await db.prodotti_vendita.find(
        {"fonte": "acquaviva"},
        {"_id": 0, "nome": 1, "id": 1}
    ).to_list(1000)
    nomi_esistenti = {p["nome"].lower().strip(): p["id"] for p in esistenti}

    created = 0
    updated = 0
    for p in prodotti_acq:
        nome = p.get("nome_normalizzato", p.get("nome_originale", "")).strip()
        if not nome:
            continue

        # Calcola costo per pezzo (se il peso è disponibile)
        peso = float(p.get("peso_confezione", 0) or 0)
        prezzo_kg = float(p.get("prezzo_kg", 0) or 0)
        costo = 0
        if peso > 0 and prezzo_kg > 0:
            unita = p.get("unita_confezione", "kg")
            if unita == "pz":
                costo = float(p.get("prezzo_confezione", 0) or 0)
            else:
                costo = round(peso * prezzo_kg, 4)

        data = {
            "nome": nome.title(),
            "categoria": "Acquaviva",
            "fonte": "acquaviva",
            "fornitore": "Dolciaria Acquaviva",
            "costo_produzione": costo,
            "iva": 10,
            "attivo": True,
            "allergeni": [],
            "updated_at": datetime.now(timezone.utc).isoformat(),
            # Store prezzo_confezione for later recalc when pezzi_cartone is known
            "costo_produzione_cartone": float(p.get("prezzo_confezione", 0) or 0)
        }

        nome_key = nome.lower().strip()
        if nome_key in nomi_esistenti:
            await db.prodotti_vendita.update_one(
                {"id": nomi_esistenti[nome_key]},
                {"$set": data}
            )
            updated += 1
        else:
            data["id"] = str(uuid.uuid4())
            data["created_at"] = datetime.now(timezone.utc).isoformat()
            data["prezzo_vendita"] = 0
            data["margine_percentuale"] = 0
            data["margine_euro"] = 0
            data["prezzo_ivato"] = 0
            await db.prodotti_vendita.insert_one(data)
            created += 1

    return {"success": True, "creati": created, "aggiornati": updated, "totale": len(prodotti_acq)}


@router.post("/ricalcola-costi-acquaviva")
async def ricalcola_costi_acquaviva():
    """
    Ricalcola il costo per PEZZO di tutti i prodotti Acquaviva che hanno
    pezzi_cartone > 0 usando la formula: costo_pezzo = prezzo_cartone / pezzi_cartone.
    Il prezzo_cartone viene preso dal costo_produzione_cartone (salvato al sync)
    oppure cercando il prodotto nel dizionario prodotti.
    """
    prodotti = await db.prodotti_vendita.find(
        {"fonte": "acquaviva", "pezzi_cartone": {"$gt": 0}},
        {"_id": 0}
    ).to_list(1000)

    diz_items = await db.dizionario_prodotti.find(
        {"fornitore": {"$regex": "acquaviva", "$options": "i"}},
        {"_id": 0, "nome_normalizzato": 1, "nome_originale": 1, "prezzo_confezione": 1}
    ).to_list(500)

    # Mappa nome -> prezzo cartone
    diz_map = {}
    for d in diz_items:
        if d.get("prezzo_confezione", 0) > 0:
            diz_map[d["nome_normalizzato"].lower().strip()] = float(d["prezzo_confezione"])

    aggiornati = 0
    non_trovati = []

    for prod in prodotti:
        pz_cart = int(prod.get("pezzi_cartone", 0) or 0)
        if pz_cart <= 0:
            continue

        # Prima prova: usa costo_produzione_cartone salvato
        prezzo_cart = float(prod.get("costo_produzione_cartone", 0) or 0)

        # Se non disponibile, cerca nel dizionario per match parziale del nome
        if prezzo_cart <= 0:
            nome = prod.get("nome", "").lower().strip()
            for key, prezzo in diz_map.items():
                nome_clean = nome.replace(" ", "")[:12]
                key_clean = key.replace(" ", "")[:12]
                if nome_clean in key.replace(" ", "") or key_clean in nome.replace(" ", ""):
                    prezzo_cart = prezzo
                    break

        if prezzo_cart <= 0:
            non_trovati.append(prod["nome"])
            continue

        costo_pezzo = round(prezzo_cart / pz_cart, 4)
        pv = float(prod.get("prezzo_vendita", 0) or 0)
        update = {
            "costo_produzione": costo_pezzo,
            "costo_produzione_cartone": prezzo_cart,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        if pv > 0 and costo_pezzo > 0:
            margine = pv - costo_pezzo
            update["margine_euro"] = round(margine, 2)
            update["margine_percentuale"] = round((margine / pv) * 100, 1)

        await db.prodotti_vendita.update_one({"id": prod["id"]}, {"$set": update})
        aggiornati += 1

    return {
        "success": True,
        "aggiornati": aggiornati,
        "non_trovati": len(non_trovati),
        "lista_non_trovati": non_trovati[:20]
    }

@router.post("/sync-da-ricette")
async def sync_prodotti_da_ricette():
    """
    Sincronizza prodotti vendita dalle ricette esistenti.
    Crea un prodotto vendita per ogni ricetta che non ne ha già uno.
    Aggiorna costo_produzione e immagine_url per tutti i prodotti esistenti.
    """
    ricette = await db.ricette.find({}, {"_id": 0}).to_list(1000)
    prodotti_esistenti = await db.prodotti_vendita.find({}, {"_id": 0, "ricetta_id": 1, "id": 1, "nome": 1}).to_list(1000)
    ricette_con_prodotto = {p.get("ricetta_id"): p.get("id") for p in prodotti_esistenti if p.get("ricetta_id")}
    # Anche matching per nome (fallback per prodotti senza ricetta_id)
    nomi_con_prodotto = {p.get("nome", "").lower().strip(): p.get("id") for p in prodotti_esistenti}

    # Carica dizionario prodotti per calcolo costi
    prodotti_diz = await db.dizionario_prodotti.find({}, {"_id": 0}).to_list(10000)
    from routers.food_cost import trova_prodotto_dizionario, converti_in_kg
    dizionario = {p["nome_normalizzato"].lower(): p for p in prodotti_diz}

    def calcola_costo_ricetta(ricetta):
        costo = 0
        ingredienti_dettaglio = ricetta.get("ingredienti_dettaglio", [])
        if ingredienti_dettaglio:
            for ing in ingredienti_dettaglio:
                nome = ing.get("nome", "").strip()
                quantita_raw = ing.get("quantita", 0)
                unita = ing.get("unita_misura", "g")
                try:
                    quantita = float(str(quantita_raw).replace(",", ".")) if quantita_raw else 0
                except (ValueError, TypeError):
                    quantita = 0
                prodotto = trova_prodotto_dizionario(nome, dizionario)
                if prodotto and quantita > 0:
                    prezzo_kg = float(prodotto.get("prezzo_kg", 0) or 0)
                    quantita_kg = converti_in_kg(quantita, unita)
                    costo += quantita_kg * prezzo_kg
        return round(costo, 2)

    created = 0
    updated = 0
    foto_aggiornate = 0
    for ricetta in ricette:
        ricetta_id = ricetta.get("id")
        costo_totale = calcola_costo_ricetta(ricetta)
        # Usa costo PER PEZZO (non totale ricetta)
        porzioni = int(ricetta.get("porzioni") or 1)
        costo = round(costo_totale / porzioni, 4) if porzioni > 0 and costo_totale > 0 else costo_totale
        foto_url = ricetta.get("foto_url") or None

        # Trova prodotto esistente (prima per ricetta_id, poi per nome)
        prodotto_id = ricette_con_prodotto.get(ricetta_id)
        if not prodotto_id:
            nome_key = ricetta.get("nome", "").lower().strip()
            prodotto_id = nomi_con_prodotto.get(nome_key)

        if not prodotto_id:
            # Crea nuovo prodotto
            nuovo_prodotto = {
                "id": str(uuid.uuid4()),
                "nome": ricetta.get("nome", ""),
                "categoria": ricetta.get("categoria", ""),
                "descrizione": "",
                "ricetta_id": ricetta_id,
                "prezzo_vendita": 0,
                "costo_produzione": costo,
                "margine_percentuale": 0,
                "margine_euro": 0,
                "iva": 10,
                "prezzo_ivato": 0,
                "attivo": True,
                "allergeni": ricetta.get("allergeni", []),
                "immagine_url": foto_url,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await db.prodotti_vendita.insert_one(nuovo_prodotto)
            created += 1
        else:
            # Aggiorna costo e foto
            prodotto_esistente = await db.prodotti_vendita.find_one({"id": prodotto_id}, {"_id": 0})
            if prodotto_esistente:
                update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}
                if costo > 0 or prodotto_esistente.get("costo_produzione", 0) == 0:
                    update_data["costo_produzione"] = costo
                    # Ricalcola margini se ha prezzo
                    prezzo = float(prodotto_esistente.get("prezzo_vendita", 0) or 0)
                    if prezzo > 0 and costo > 0:
                        margine = prezzo - costo
                        update_data["margine_euro"] = round(margine, 2)
                        update_data["margine_percentuale"] = round((margine / prezzo) * 100, 1)
                # Copia foto dalla ricetta se il prodotto non ha già una foto
                if foto_url and not prodotto_esistente.get("immagine_url"):
                    update_data["immagine_url"] = foto_url
                    foto_aggiornate += 1
                # Aggiorna anche ricetta_id se mancante
                if not prodotto_esistente.get("ricetta_id") and ricetta_id:
                    update_data["ricetta_id"] = ricetta_id
                await db.prodotti_vendita.update_one({"id": prodotto_id}, {"$set": update_data})
                updated += 1

    return {
        "success": True,
        "prodotti_creati": created,
        "prodotti_aggiornati": updated,
        "foto_aggiornate": foto_aggiornate,
        "totale_ricette": len(ricette)
    }


@router.post("/imposta-prezzi-da-margine")
async def imposta_prezzi_da_margine(
    margine_percentuale: float = 30.0,
    solo_senza_prezzo: bool = True
):
    """
    Imposta automaticamente il prezzo di vendita per tutti i prodotti
    che hanno un costo ma non hanno un prezzo, usando un margine percentuale fisso.
    """
    query = {"costo_produzione": {"$gt": 0}}
    if solo_senza_prezzo:
        query["$or"] = [
            {"prezzo_vendita": {"$exists": False}},
            {"prezzo_vendita": 0},
            {"prezzo_vendita": None},
            {"prezzo_vendita": "0"},
            {"prezzo_vendita": "0.0"}
        ]

    prodotti = await db.prodotti_vendita.find(query, {"_id": 0}).to_list(1000)
    updated = 0
    skipped = 0

    for p in prodotti:
        costo = float(str(p.get("costo_produzione", 0) or 0))
        if costo <= 0:
            skipped += 1
            continue

        prezzo = round(costo / (1 - margine_percentuale / 100), 2)
        iva = float(p.get("iva", 10) or 10)
        margine_euro = round(prezzo - costo, 2)
        prezzo_ivato = round(prezzo * (1 + iva / 100), 2)

        await db.prodotti_vendita.update_one(
            {"id": p["id"]},
            {"$set": {
                "prezzo_vendita": prezzo,
                "margine_percentuale": margine_percentuale,
                "margine_euro": margine_euro,
                "prezzo_ivato": prezzo_ivato,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        updated += 1

    return {
        "success": True,
        "aggiornati": updated,
        "saltati_senza_costo": skipped,
        "margine_applicato": margine_percentuale
    }


@router.post("/auto-categorie")
async def auto_categorie():
    """
    Assegna automaticamente una categoria ai prodotti interni senza categoria,
    analizzando il nome del prodotto.
    """
    # Mappatura nome → categoria (più specifico prima)
    RULES = [
        # Cornetti e brioche
        (["cornetto", "brioche", "treccia", "krans", "francesina", "coda di aragosta", "sfogliatella", "pasta sfoglia", "pasta frolla", "pasta choux", "prussiana", "fiocco di neve", "strudel", "vesuvio", "rustico", "pan di spagna"], "Pasticceria > Lievitati"),
        # Torte e monoporzioni
        (["torta", "pastiera", "cheesecake", "cassatina", "caprese", "delizia", "tiramisù", "babà", "panettone", "struffoli", "cannolo", "pasticcino", "crostatina", "biscotto", "pasta di mandorle"], "Pasticceria > Torte e Monoporzioni"),
        # Creme e preparazioni base
        (["crema", "panna", "pasta choux", "ricotta zuccherata", "pan di spagna", "biscotto"], "Pasticceria > Basi e Creme"),
        # Pizze e focacce
        (["pizza", "focaccia"], "Pizze e Focacce"),
        # Secondi e preparazioni di carne
        (["polpettine", "salpicon", "salsiccia", "salame", "wrustel", "prosciutto", "porchetta", "cervellatine", "ragù", "arancini", "frittatina"], "Secondi > Carni"),
        # Salumi
        (["salame", "prosciutto", "salumi"], "Gastronomia > Salumi"),
        # Verdure
        (["melanzane", "melanzana", "peperoni", "zucchine", "zucca", "funghi", "scarole", "friarielli", "fagioli"], "Contorni > Verdure"),
        # Salse e condimenti
        (["salsa", "ragù", "crema pasticciera", "crema chantilly", "panna", "ricotta zuccherata"], "Semilavorati > Salse e Creme"),
        # Fritti e gastronomia
        (["crocche", "arancini", "frittatina", "crostone"], "Gastronomia > Fritti"),
        # Pane e focacce salate
        (["focaccia", "pane", "panino", "crostone"], "Pane e Focacce"),
        # Semilavorati
        (["pasta frolla", "pasta sfoglia", "pasta choux", "pan di spagna", "crema pasticciera", "crema chantilly"], "Semilavorati"),
    ]

    senza_cat = await db.prodotti_vendita.find(
        {"ricetta_id": {"$exists": True, "$ne": None}, "categoria": {"$in": ["", None]}},
        {"_id": 0, "id": 1, "nome": 1}
    ).to_list(500)

    assegnate = 0
    non_trovate = []
    results = []

    for prod in senza_cat:
        nome_lower = prod["nome"].lower()
        cat_assegnata = None

        for keywords, cat in RULES:
            if any(kw in nome_lower for kw in keywords):
                cat_assegnata = cat
                break

        if cat_assegnata:
            await db.prodotti_vendita.update_one(
                {"id": prod["id"]},
                {"$set": {"categoria": cat_assegnata, "updated_at": datetime.now(timezone.utc).isoformat()}}
            )
            assegnate += 1
            results.append({"nome": prod["nome"], "categoria": cat_assegnata})
        else:
            non_trovate.append(prod["nome"])

    return {
        "assegnate": assegnate,
        "non_trovate": len(non_trovate),
        "lista_non_trovate": non_trovate,
        "risultati": results
    }


@router.get("/stats/margini")
async def get_statistiche_margini():
    """Statistiche margini prodotti"""
    prodotti = await db.prodotti_vendita.find(
        {"attivo": True},
        {"_id": 0}
    ).to_list(1000)
    
    if not prodotti:
        return {"totale_prodotti": 0, "margine_medio": 0, "margine_min": 0, "margine_max": 0, "prodotti_senza_prezzo": 0}
    
    prodotti_con_prezzo = [p for p in prodotti if float(p.get("prezzo_vendita", 0) or 0) > 0]
    prodotti_senza_prezzo = len(prodotti) - len(prodotti_con_prezzo)
    margini = [float(p.get("margine_percentuale", 0) or 0) for p in prodotti_con_prezzo if float(p.get("margine_percentuale", 0) or 0) > 0]
    
    return {
        "totale_prodotti": len(prodotti_con_prezzo),
        "margine_medio": round(sum(margini) / len(margini), 1) if margini else 0,
        "margine_min": min(margini) if margini else 0,
        "margine_max": max(margini) if margini else 0,
        "prodotti_senza_prezzo": prodotti_senza_prezzo
    }
    """Statistiche margini prodotti"""
    prodotti = await db.prodotti_vendita.find(
        {"attivo": True},
        {"_id": 0}
    ).to_list(1000)
    
    if not prodotti:
        return {"totale_prodotti": 0, "margine_medio": 0, "margine_min": 0, "margine_max": 0, "prodotti_senza_prezzo": 0}
    
    prodotti_con_prezzo = [p for p in prodotti if float(p.get("prezzo_vendita", 0) or 0) > 0]
    prodotti_senza_prezzo = len(prodotti) - len(prodotti_con_prezzo)
    margini = [float(p.get("margine_percentuale", 0) or 0) for p in prodotti_con_prezzo if float(p.get("margine_percentuale", 0) or 0) > 0]
    
    return {
        "totale_prodotti": len(prodotti_con_prezzo),
        "margine_medio": round(sum(margini) / len(margini), 1) if margini else 0,
        "margine_min": min(margini) if margini else 0,
        "margine_max": max(margini) if margini else 0,
        "prodotti_senza_prezzo": prodotti_senza_prezzo
    }
