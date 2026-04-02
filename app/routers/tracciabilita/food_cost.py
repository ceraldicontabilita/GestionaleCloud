from fastapi import APIRouter, HTTPException, Query
from app.routers.tracciabilita.server import db
from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import List, Optional, Any
from datetime import datetime, timezone
import os
import re
import uuid

router = APIRouter(prefix="/food-cost", tags=["Food Cost"])

# MongoDB connection
mongo_url = os.environ.get('MONGO_URL')


# ==================== MODELS ====================

class ProdottoDizionario(BaseModel):
    """Prodotto nel dizionario prezzi centralizzato con inventario"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    nome_originale: str  # Nome dalla fattura
    nome_normalizzato: str  # Nome pulito per ricerca
    peso_confezione: float  # Peso/volume della confezione
    unita_confezione: str = "kg"  # kg, lt, pz
    prezzo_confezione: float  # Prezzo unitario dalla fattura (netto IVA)
    prezzo_kg: float  # Prezzo per kg/lt calcolato
    quantita_totale_kg: float = 0  # Quantità totale disponibile in kg/lt
    quantita_usata_kg: float = 0  # Quantità già usata nelle ricette
    quantita_disponibile_kg: float = 0  # Quantità rimanente
    fornitore: str = ""
    data_fattura: str = ""
    ultimo_aggiornamento: str = ""


class IngredienteConQuantita(BaseModel):
    """Ingrediente con quantità per ricetta — accetta stringhe numeriche dal DB"""
    model_config = ConfigDict(extra="ignore")
    nome: str
    quantita: float
    unita_misura: str = "g"
    prodotto_dizionario_id: Optional[str] = None
    prezzo_kg: Optional[float] = None
    costo_calcolato: Optional[float] = None

    @field_validator("quantita", mode="before")
    @classmethod
    def coerce_quantita(cls, v: Any) -> float:
        if isinstance(v, str):
            try:
                return float(v.replace(",", "."))
            except ValueError:
                raise ValueError(f"Quantità non valida: {v}")
        return v

    @field_validator("prezzo_kg", "costo_calcolato", mode="before")
    @classmethod
    def coerce_optional_float(cls, v: Any) -> Optional[float]:
        if v is None or v == "":
            return None
        if isinstance(v, str):
            try:
                return float(v.replace(",", "."))
            except ValueError:
                return None
        return v


class AggiornaIngredienteRicetta(BaseModel):
    """Payload per aggiornare ingredienti di una ricetta"""
    ricetta_id: str
    ingredienti_dettaglio: List[IngredienteConQuantita]


class UsaRicettaRequest(BaseModel):
    """Request per usare una ricetta e scalare le quantità"""
    ricetta_id: str
    porzioni: int = 1  # Numero di porzioni da preparare


# ==================== DIZIONARIO PRODOTTI ====================

async def get_fornitori_esclusi():
    """Ottiene la lista dei nomi dei fornitori esclusi"""
    fornitori_esclusi_docs = await db.fornitori.find({"escluso": True}, {"nome": 1, "_id": 0}).to_list(1000)
    return [f["nome"].lower().strip() for f in fornitori_esclusi_docs]


@router.get("/dizionario")
async def get_dizionario(
    search: str = Query(None, description="Cerca prodotti"),
    escludi_fornitori: bool = Query(True, description="Escludi prodotti di fornitori esclusi")
):
    """
    Ottiene il dizionario prodotti centralizzato.
    Esclude automaticamente i prodotti dei fornitori esclusi.
    """
    query = {}
    
    # Filtra per ricerca
    if search and len(search) >= 2:
        query["nome_normalizzato"] = {"$regex": search.lower(), "$options": "i"}
    
    # Escludi fornitori esclusi
    if escludi_fornitori:
        fornitori_esclusi = await get_fornitori_esclusi()
        if fornitori_esclusi:
            # Escludi prodotti con fornitore nella lista esclusi (case-insensitive)
            query["$nor"] = [{"fornitore": {"$regex": f"^{re.escape(f)}$", "$options": "i"}} for f in fornitori_esclusi[:50]]
    
    prodotti = await db.dizionario_prodotti.find(query, {"_id": 0}).sort("nome_normalizzato", 1).to_list(500)
    return prodotti


@router.get("/dizionario/search")
async def search_dizionario(
    q: str = Query(..., min_length=2),
    escludi_fornitori: bool = Query(True, description="Escludi prodotti di fornitori esclusi"),
    solo_acquaviva: bool = Query(False, description="Mostra solo prodotti Acquaviva")
):
    """
    Ricerca prodotti nel dizionario per autocompletamento.
    Restituisce max 20 risultati ordinati per rilevanza.
    Esclude automaticamente i fornitori esclusi.
    """
    query = {"nome_normalizzato": {"$regex": q.lower(), "$options": "i"}}

    if solo_acquaviva:
        query["fornitore"] = {"$regex": "acquaviva|vandemoortele", "$options": "i"}
    
    # Escludi fornitori esclusi (solo se non stiamo filtrando per acquaviva)
    if escludi_fornitori and not solo_acquaviva:
        fornitori_esclusi = await get_fornitori_esclusi()
        if fornitori_esclusi:
            query["$nor"] = [{"fornitore": {"$regex": f"^{re.escape(f)}$", "$options": "i"}} for f in fornitori_esclusi[:50]]
    
    prodotti = await db.dizionario_prodotti.find(query, {"_id": 0}).limit(20).to_list(20)
    
    # Ordina per match migliore (inizia con la query)
    def sort_key(p):
        nome = p.get("nome_normalizzato", "").lower()
        if nome.startswith(q.lower()):
            return (0, nome)
        return (1, nome)
    
    prodotti.sort(key=sort_key)

    # Arricchisci con costo_per_pezzo se disponibile
    for p in prodotti:
        if not p.get("costo_per_pezzo") and p.get("peso_pezzo_g") and p.get("prezzo_kg"):
            peso_kg = float(p["peso_pezzo_g"]) / 1000
            p["costo_per_pezzo"] = round(peso_kg * float(p["prezzo_kg"]), 4)
        # Arricchisci con nome_canonico da nome_mapping se non presente nel documento
        if not p.get("nome_canonico"):
            try:
                mapping = await db.nome_mapping.find_one(
                    {"descrizione_key": p.get("nome_normalizzato", "")[:200]},
                    {"_id": 0, "nome_canc": 1}
                )
                if mapping and mapping.get("nome_canc"):
                    p["nome_canonico"] = mapping["nome_canc"]
            except Exception:
                pass
        p["nome_display"] = p.get("nome_canonico") or p.get("nome_normalizzato", "")

    # Deduplicazione per nome_display: mostra una sola voce per nome canonico
    visti: dict = {}
    prodotti_dedup = []
    for p in prodotti:
        nc_key = p.get("nome_display", "").lower().strip()
        if nc_key not in visti:
            visti[nc_key] = True
            prodotti_dedup.append(p)

    return prodotti_dedup


@router.get("/semilavorati-acquaviva")
async def get_semilavorati_acquaviva(q: str = Query("", description="Ricerca per nome")):
    """
    Restituisce i prodotti semilavorati Acquaviva dal catalogo prodotti_vendita,
    arricchiti con costo_per_pezzo calcolato dal dizionario.
    Usato nel form ricetta per aggiungere prodotti Acquaviva come ingredienti.
    """
    query: dict = {"fonte": "acquaviva", "attivo": True}
    if q and len(q) >= 2:
        query["nome"] = {"$regex": q, "$options": "i"}

    prodotti = await db.prodotti_vendita.find(query, {"_id": 0}).sort("nome", 1).to_list(500)

    result = []
    for p in prodotti:
        costo_pezzo = float(p.get("costo_produzione") or 0)
        peso_g = float(p.get("peso_pezzo_g") or 0)
        pz_cart = int(p.get("pezzi_cartone") or 0)

        # Se costo_pezzo non disponibile ma abbiamo prezzo_cartone + pz_cart
        if costo_pezzo <= 0 and pz_cart > 0:
            cart = float(p.get("costo_produzione_cartone") or 0)
            if cart > 0:
                costo_pezzo = round(cart / pz_cart, 4)

        # Calcola prezzo_kg equivalente per compatibilità con il form ricette
        prezzo_kg_equiv = 0.0
        if peso_g > 0 and costo_pezzo > 0:
            prezzo_kg_equiv = round(costo_pezzo / (peso_g / 1000), 4)

        result.append({
            "id": p.get("id"),
            "nome_normalizzato": p.get("nome", "").lower(),
            "nome_display": p.get("nome"),
            "fornitore": "Dolciaria Acquaviva",
            "codice": p.get("codice_prodotto", ""),
            "peso_pezzo_g": peso_g,
            "pezzi_cartone": pz_cart,
            "costo_per_pezzo": costo_pezzo,
            "prezzo_kg": prezzo_kg_equiv,
            "immagine_url": p.get("immagine_url", ""),
            "categoria": p.get("categoria", ""),
            "fonte": "acquaviva",
            "is_acquaviva": True,
        })

    return result


@router.post("/dizionario/manuale")
async def aggiungi_prezzo_manuale(data: dict):
    """
    Aggiunge o aggiorna un ingrediente con prezzo manuale nel dizionario.
    Per ingredienti acquistati in contanti o non presenti nelle fatture.
    Payload: { nome, prezzo_kg, note }
    """
    nome = str(data.get("nome", "")).strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome obbligatorio")

    prezzo_kg = float(data.get("prezzo_kg", 0) or 0)
    if prezzo_kg <= 0:
        raise HTTPException(status_code=400, detail="Prezzo/kg deve essere > 0")

    nome_norm = nome.lower().strip()
    doc = {
        "id": str(uuid.uuid4()),
        "nome_originale": nome,
        "nome_normalizzato": nome_norm,
        "peso_confezione": 1.0,
        "unita_confezione": "kg",
        "prezzo_confezione": prezzo_kg,
        "prezzo_kg": prezzo_kg,
        "quantita_totale_kg": 0,
        "quantita_usata_kg": 0,
        "quantita_disponibile_kg": 0,
        "fornitore": data.get("fornitore", "Manuale"),
        "note": data.get("note", "Prezzo inserito manualmente"),
        "data_fattura": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "ultimo_aggiornamento": datetime.now(timezone.utc).isoformat(),
        "inserito_manualmente": True
    }

    # Upsert per nome_normalizzato
    existing = await db.dizionario_prodotti.find_one({"nome_normalizzato": nome_norm}, {"_id": 0, "id": 1})
    if existing:
        doc["id"] = existing["id"]

    await db.dizionario_prodotti.update_one(
        {"nome_normalizzato": nome_norm},
        {"$set": doc},
        upsert=True
    )
    return {"success": True, "prodotto": nome, "prezzo_kg": prezzo_kg, "aggiornato": existing is not None}


@router.get("/dizionario/manuali")
async def get_prezzi_manuali():
    """Restituisce tutti i prezzi inseriti manualmente"""
    prodotti = await db.dizionario_prodotti.find(
        {"inserito_manualmente": True},
        {"_id": 0}
    ).sort("nome_normalizzato", 1).to_list(500)
    return prodotti


@router.delete("/dizionario/manuale/{nome_normalizzato}")
async def elimina_prezzo_manuale(nome_normalizzato: str):
    """Elimina un prezzo manuale dal dizionario"""
    result = await db.dizionario_prodotti.delete_one({
        "nome_normalizzato": nome_normalizzato,
        "inserito_manualmente": True
    })
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Prodotto non trovato o non è manuale")
    return {"success": True}


@router.post("/dizionario")
async def add_prodotto_dizionario(prodotto: ProdottoDizionario):
    """Aggiunge o aggiorna un prodotto nel dizionario"""
    prodotto_dict = prodotto.model_dump()
    prodotto_dict["ultimo_aggiornamento"] = datetime.now(timezone.utc).isoformat()
    prodotto_dict["nome_normalizzato"] = prodotto.nome_normalizzato.lower().strip()
    
    # Calcola prezzo/kg se non fornito
    if prodotto.peso_confezione > 0:
        prodotto_dict["prezzo_kg"] = round(prodotto.prezzo_confezione / prodotto.peso_confezione, 4)
    
    await db.dizionario_prodotti.update_one(
        {"nome_normalizzato": prodotto_dict["nome_normalizzato"]},
        {"$set": prodotto_dict},
        upsert=True
    )
    return {"status": "ok", "prodotto": prodotto_dict}


@router.put("/dizionario/{prodotto_id}")
async def update_prodotto_dizionario(prodotto_id: str, prodotto: ProdottoDizionario):
    """Aggiorna un prodotto esistente nel dizionario"""
    prodotto_dict = prodotto.model_dump()
    prodotto_dict["ultimo_aggiornamento"] = datetime.now(timezone.utc).isoformat()
    
    if prodotto.peso_confezione > 0:
        prodotto_dict["prezzo_kg"] = round(prodotto.prezzo_confezione / prodotto.peso_confezione, 4)
    
    result = await db.dizionario_prodotti.update_one(
        {"id": prodotto_id},
        {"$set": prodotto_dict}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Prodotto non trovato")
    return {"status": "ok"}


@router.patch("/dizionario/{prodotto_id}/scorta-minima")
async def aggiorna_scorta_minima(
    prodotto_id: str,
    scorta_minima: float = Query(..., ge=0, description="Scorta minima in kg")
):
    """Aggiorna la scorta minima di un prodotto nel dizionario."""
    result = await db.dizionario_prodotti.update_one(
        {"id": prodotto_id},
        {"$set": {"scorta_minima": scorta_minima, "ultimo_aggiornamento": datetime.now(timezone.utc).isoformat()}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Prodotto non trovato")
    return {"status": "ok", "scorta_minima": scorta_minima}


@router.delete("/dizionario/{prodotto_id}")
async def delete_prodotto_dizionario(prodotto_id: str):
    """Elimina un prodotto dal dizionario e lo aggiunge alla blacklist."""
    prodotto = await db.dizionario_prodotti.find_one({"id": prodotto_id}, {"_id": 0})
    if not prodotto:
        raise HTTPException(status_code=404, detail="Prodotto non trovato")

    # Aggiungi alla blacklist permanente (per nome normalizzato)
    nome = (prodotto.get("nome") or prodotto.get("descrizione") or "").strip()
    if nome:
        await db.prodotti_blacklist.update_one(
            {"nome_normalizzato": nome.lower()},
            {"$set": {
                "nome_originale": nome,
                "nome_normalizzato": nome.lower(),
                "eliminato_at": datetime.now(timezone.utc).isoformat(),
                "motivo": "eliminato_manualmente"
            }},
            upsert=True
        )

    await db.dizionario_prodotti.delete_one({"id": prodotto_id})
    return {"status": "ok", "blacklistato": nome}


@router.post("/sincronizza-fatture")
async def sincronizza_dizionario_da_fatture(azzera: bool = Query(False, description="Se True, azzera il dizionario prima della sincronizzazione")):
    """
    Popola/aggiorna il dizionario prodotti dalle fatture.
    Estrae: nome prodotto, peso confezione, prezzo, prezzo/kg.
    ESCLUDE AUTOMATICAMENTE I FORNITORI ESCLUSI.
    Se azzera=True, cancella tutti i dati prima di ripopolare.
    
    LOGICA PREZZI:
    - Alcuni fornitori (es. F.lli Fiorentino) esprimono:
      - Quantità = numero di SACCHI/CONFEZIONI
      - Prezzo = prezzo per KG (già unitario!)
    - Altri fornitori esprimono:
      - Quantità = KG totali
      - Prezzo = prezzo per KG
    
    Euristica: Se quantità è molto alta (>50) e c'è un peso nella descrizione,
    probabilmente la quantità è in sacchi e il prezzo è già per kg.
    """
    # Azzera se richiesto
    if azzera:
        await db.dizionario_prodotti.delete_many({})

    # Ottieni fornitori esclusi
    fornitori_esclusi = await get_fornitori_esclusi()

    # Ottieni blacklist prodotti eliminati manualmente
    blacklist_docs = await db.prodotti_blacklist.find({}, {"nome_normalizzato": 1}).to_list(5000)
    blacklist = {doc["nome_normalizzato"] for doc in blacklist_docs}

    fatture = await db.fatture.find({}, {"_id": 0}).to_list(50000)

    stats = {
        "prodotti_aggiunti": 0,
        "prodotti_aggiornati": 0,
        "prodotti_rimossi": 0,
        "prodotti_trovati": 0,
        "prodotti_saltati_blacklist": 0,
        "fornitori_esclusi": len(fornitori_esclusi),
        "prodotti_senza_peso": [],
        "errori": []
    }
    
    # Prima rimuovi dal dizionario i prodotti di fornitori ora esclusi
    if fornitori_esclusi:
        for fornitore_escluso in fornitori_esclusi:
            result = await db.dizionario_prodotti.delete_many({
                "fornitore": {"$regex": f"^{re.escape(fornitore_escluso)}$", "$options": "i"}
            })
            stats["prodotti_rimossi"] += result.deleted_count
    
    prodotti_processati = {}

    # Fornitori che esprimono SEMPRE: Qt=numero confezioni, Prezzo=€/kg
    # → prezzo_kg = prezzo_unitario, quantita_kg = qt * peso_confezione
    FORNITORI_PREZZO_PER_KG = {
        "f.lli fiorentino", "fiorentino", "granzuccheri", "saima",
    }

    for fattura in fatture:
        fornitore = fattura.get("fornitore", "")
        fornitore_lower = fornitore.lower().strip()
        data_fattura = fattura.get("data_fattura", "")

        # SALTA fornitori esclusi
        if fornitore_lower in fornitori_esclusi:
            continue

        # Questo fornitore usa sempre prezzo per kg direttamente
        fornitore_usa_prezzo_per_kg = any(f in fornitore_lower for f in FORNITORI_PREZZO_PER_KG)

        for prodotto in fattura.get("prodotti", []):
            descrizione = prodotto.get("descrizione", "").strip()
            quantita_str = str(prodotto.get("quantita", "0")).strip()
            prezzo_str = str(prodotto.get("prezzo", "0")).strip()
            unita_misura_xml = str(prodotto.get("unita_misura", "") or "").strip().upper()

            if not descrizione:
                continue

            # Salta voci contabili/non-prodotti: liquidazioni, sconti, contributi, obblighi, imballi
            VOCI_NON_PRODOTTO = {
                "liquidaz", "liquidazione", "abbuono", "sconto", "reso ",
                "contributo", "obbligo", "obj ", "obiettivo", "nota credito",
                "diritto fisso", "diritto di", "imballo", "vuoto a perdere",
                "spese trasporto", "spese di trasporto", "rimborso",
                "commissione", "provvigione", "acconto", "saldo",
            }
            descrizione_lower = descrizione.lower()
            if any(k in descrizione_lower for k in VOCI_NON_PRODOTTO):
                continue

            # Parse valori numerici (gestisce spazi e formato italiano/anglosassone)
            try:
                quantita = float(quantita_str.replace(" ", "").replace(",", "."))
                prezzo_unitario = float(prezzo_str.replace(" ", "").replace(",", "."))
            except (ValueError, AttributeError):
                continue

            if quantita <= 0 or prezzo_unitario <= 0:
                continue

            # ─── LOGICA PREZZI/UNITÀ ─────────────────────────────────────────────────
            #
            # PRIORITÀ 0: Fornitori speciali (Fiorentino, Granzuccheri)
            #   Qt = numero confezioni, Prezzo = già per KG
            #   → prezzo_kg = prezzo_unitario, qt_kg = qt * peso_confezione_da_desc
            #
            # PRIORITÀ 1: UnitaMisura XML esplicita KG/LT
            #   Qt già in kg/lt, prezzo per kg/lt
            #
            # PRIORITÀ 2: UnitaMisura XML = pezzi (NR/PZ/BT/ecc.)
            #   Qt in pezzi, serve peso dalla descrizione
            #
            # PRIORITÀ 3: UM assente + peso trovato in descrizione
            #   Qt = confezioni, prezzo = per confezione → prezzo_kg = pr/peso
            #
            # PRIORITÀ 4: Fallback — assume kg con prezzo diretto
            # ─────────────────────────────────────────────────────────────────────────

            UM_KG_LT = {"KG", "LT", "L"}
            UM_PEZZI = {"NR", "PZ", "BT", "SC", "CT", "CF", "NR.", "KAR", "ST", "FS", "CS"}

            # ─── REGOLA PRINCIPALE ────────────────────────────────────────────────
            # 1. Il parser della DESCRIZIONE è SEMPRE la fonte del peso fisico
            #    della confezione (GR.10, G500, KG 1.5, ecc.)
            # 2. L'UnitaMisura XML dice solo come è espressa la Qt in fattura:
            #    - KG/LT → Qt già in kg/lt, prezzo per kg/lt
            #    - NR/PZ/ecc. → Qt in confezioni, prezzo per confezione
            #    - assente → trattata come confezioni
            # 3. Se il parser non trova peso → prodotto senza peso (manuale)
            # ─────────────────────────────────────────────────────────────────────

            # Estrai sempre il peso dalla descrizione
            peso_desc = estrai_peso_e_unita(descrizione)  # (valore, unità) o None

            # Converti peso in kg per uniformità
            def to_kg(val, unit):
                if unit in ("kg", "l", "lt"):
                    return round(val, 6)
                elif unit == "g":
                    return round(val / 1000, 6)
                elif unit == "ml":
                    return round(val / 1000, 6)
                return val

            if fornitore_usa_prezzo_per_kg and unita_misura_xml not in UM_KG_LT:
                # FORNITORI SPECIALI (Fiorentino, Granzuccheri, Saima):
                # Il prezzo in fattura è già €/kg. Qt = numero confezioni.
                if peso_desc:
                    peso_val, peso_unit = peso_desc
                    peso_confezione = to_kg(peso_val, peso_unit)
                    unita = "kg"
                    prezzo_kg = prezzo_unitario
                    quantita_kg_fattura = quantita * peso_confezione
                else:
                    # Nessun peso in descrizione → Qt è già in kg (es. STRUTTO RAFFINATO)
                    peso_confezione = 1.0
                    unita = "kg"
                    prezzo_kg = prezzo_unitario
                    quantita_kg_fattura = quantita

            elif unita_misura_xml in UM_KG_LT:
                # Qt già in kg/lt dal XML → prezzo per kg.
                # Usa peso da descrizione se disponibile, altrimenti 1kg
                if peso_desc:
                    peso_val, peso_unit = peso_desc
                    peso_confezione = to_kg(peso_val, peso_unit)
                    unita = "kg"
                    prezzo_kg = prezzo_unitario
                    quantita_kg_fattura = quantita
                else:
                    peso_confezione = 1.0
                    unita = unita_misura_xml.lower()
                    prezzo_kg = prezzo_unitario
                    quantita_kg_fattura = quantita

            elif unita_misura_xml in UM_PEZZI or not unita_misura_xml:
                # Qt in confezioni (NR, PZ, ecc.) o UM assente.
                # Il peso della confezione DEVE venire dalla descrizione.
                if peso_desc:
                    peso_val, peso_unit = peso_desc
                    peso_confezione = to_kg(peso_val, peso_unit)
                    unita = "kg"
                    prezzo_kg = round(prezzo_unitario / peso_confezione, 4) if peso_confezione > 0 else prezzo_unitario
                    quantita_kg_fattura = quantita * peso_confezione
                else:
                    # Peso non trovato in descrizione → senza peso (manuale)
                    peso_confezione = 1.0
                    unita = "pz"
                    prezzo_kg = prezzo_unitario
                    quantita_kg_fattura = quantita
                    desc_short = descrizione[:80].strip()
                    if desc_short not in [p["descrizione"] for p in stats["prodotti_senza_peso"]]:
                        stats["prodotti_senza_peso"].append({
                            "descrizione": desc_short,
                            "fornitore": fornitore,
                            "prezzo": prezzo_unitario
                        })
            else:
                # UM non riconosciuta → tratta come confezioni con parser descrizione
                if peso_desc:
                    peso_val, peso_unit = peso_desc
                    peso_confezione = to_kg(peso_val, peso_unit)
                    unita = "kg"
                    prezzo_kg = round(prezzo_unitario / peso_confezione, 4) if peso_confezione > 0 else prezzo_unitario
                    quantita_kg_fattura = quantita * peso_confezione
                else:
                    peso_confezione = 1.0
                    unita = "pz"
                    prezzo_kg = prezzo_unitario
                    quantita_kg_fattura = quantita
                    desc_short = descrizione[:80].strip()
                    if desc_short not in [p["descrizione"] for p in stats["prodotti_senza_peso"]]:
                        stats["prodotti_senza_peso"].append({
                            "descrizione": desc_short,
                            "fornitore": fornitore,
                            "prezzo": prezzo_unitario
                        })

            # Sanity check: prezzo/kg non deve essere assurdo (< 0.001 o > 5000)
            if prezzo_kg < 0.001 or prezzo_kg > 5000:
                continue

            # Nome normalizzato
            nome_norm = normalizza_nome_prodotto(descrizione)

            if not nome_norm or prezzo_kg <= 0:
                continue

            # Controlla blacklist — prodotti eliminati manualmente non vengono re-importati
            if nome_norm.lower() in blacklist or descrizione.strip().lower() in blacklist:
                stats["prodotti_saltati_blacklist"] += 1
                continue

            quantita_kg_fattura = round(quantita_kg_fattura, 3)
            
            # Aggiorna o crea il prodotto nel dizionario
            key = nome_norm.lower()
            stats["prodotti_trovati"] += 1
            if key not in prodotti_processati:
                prodotti_processati[key] = {
                    "id": str(uuid.uuid4()),
                    "nome_originale": descrizione[:200].strip(),
                    "nome_normalizzato": nome_norm.lower(),
                    "peso_confezione": peso_confezione,
                    "unita_confezione": unita,
                    "prezzo_confezione": prezzo_unitario,
                    "prezzo_kg": round(prezzo_kg, 4),
                    "quantita_totale_kg": round(quantita_kg_fattura, 3),
                    "fornitore": fornitore,
                    "data_fattura": data_fattura,
                    "ultimo_aggiornamento": datetime.now(timezone.utc).isoformat()
                }
            else:
                # Accumula la quantità da più fatture
                prodotti_processati[key]["quantita_totale_kg"] = round(
                    prodotti_processati[key].get("quantita_totale_kg", 0) + quantita_kg_fattura, 3
                )
                # Aggiorna prezzo se più conveniente
                if prezzo_kg < prodotti_processati[key]["prezzo_kg"]:
                    prodotti_processati[key]["prezzo_kg"] = round(prezzo_kg, 4)
                    prodotti_processati[key]["prezzo_confezione"] = prezzo_unitario
    
    # Salva nel database e calcola quantità disponibile
    for nome_norm, prodotto in prodotti_processati.items():
        # Recupera quantità già usata dal database esistente
        existing = await db.dizionario_prodotti.find_one({"nome_normalizzato": nome_norm})
        quantita_usata = existing.get("quantita_usata_kg", 0) if existing else 0
        
        prodotto["quantita_usata_kg"] = quantita_usata
        prodotto["quantita_disponibile_kg"] = round(
            max(0, prodotto["quantita_totale_kg"] - quantita_usata), 3
        )
        
        result = await db.dizionario_prodotti.update_one(
            {"nome_normalizzato": nome_norm},
            {"$set": prodotto},
            upsert=True
        )
        if result.upserted_id:
            stats["prodotti_aggiunti"] += 1
        elif result.modified_count > 0:
            stats["prodotti_aggiornati"] += 1
    
    # Limita prodotti senza peso
    stats["prodotti_senza_peso"] = stats["prodotti_senza_peso"][:100]
    
    return {
        "status": "ok",
        "prodotti_trovati": stats["prodotti_trovati"],
        "prodotti_aggiunti": stats["prodotti_aggiunti"],
        "prodotti_aggiornati": stats["prodotti_aggiornati"],
        "prodotti_rimossi": stats["prodotti_rimossi"],
        "fornitori_esclusi": stats["fornitori_esclusi"],
        "totale_dizionario": len(prodotti_processati),
        "prodotti_senza_peso_count": len(stats["prodotti_senza_peso"]),
        "prodotti_senza_peso": stats["prodotti_senza_peso"][:20]
    }


# ==================== CALCOLO FOOD COST ====================

@router.get("/calcola/{ricetta_id}")
async def calcola_food_cost_ricetta(ricetta_id: str):
    """
    Calcola il food cost dettagliato di una ricetta.
    Usa gli ingredienti con quantità se presenti.
    """
    ricetta = await db.ricette.find_one({"id": ricetta_id}, {"_id": 0})
    if not ricetta:
        raise HTTPException(status_code=404, detail="Ricetta non trovata")
    
    # Carica dizionario prodotti
    prodotti = await db.dizionario_prodotti.find({}, {"_id": 0}).to_list(10000)
    dizionario = {p["nome_normalizzato"].lower(): p for p in prodotti}
    
    ingredienti_result = []
    costo_totale = 0
    ingredienti_mancanti = []
    
    # Usa ingredienti_dettaglio se disponibile
    if ricetta.get("ingredienti_dettaglio"):
        for ing in ricetta["ingredienti_dettaglio"]:
            nome = ing.get("nome", "").strip()
            quantita_raw = ing.get("quantita", 0)
            unita = ing.get("unita_misura", "g")
            
            # Converti quantità
            try:
                quantita = float(str(quantita_raw).replace(",", ".")) if quantita_raw else 0
            except (ValueError, TypeError):
                quantita = 0
            
            # Cerca nel dizionario
            prodotto = trova_prodotto_dizionario(nome, dizionario)
            
            # Determina se la quantità è "q.b." o non numerica
            qb = str(quantita_raw).strip().lower() in ("q.b.", "qb", "q.b", "quanto basta", "")
            
            if prodotto and quantita > 0:
                prezzo_kg = float(prodotto.get("prezzo_kg", 0) or 0)
                costo_per_pezzo = float(prodotto.get("costo_per_pezzo", 0) or 0)
                # Per unità "pz": usa costo_per_pezzo se disponibile, altrimenti prezzo_kg/1000*50g default
                unita_lower = (unita or "g").lower().strip()
                if unita_lower in ("pz", "pezzi", "pezzo", "nr", "n") and costo_per_pezzo > 0:
                    costo = quantita * costo_per_pezzo
                    quantita_kg = quantita * (float(prodotto.get("peso_pezzo_g", 50) or 50) / 1000)
                else:
                    # Converti quantità in kg
                    quantita_kg = converti_in_kg(quantita, unita)
                    costo = quantita_kg * prezzo_kg
                
                ingredienti_result.append({
                    "nome": nome,
                    "quantita": quantita,
                    "unita": unita,
                    "prodotto_dizionario": prodotto.get("nome_normalizzato"),
                    "prezzo_kg": prezzo_kg,
                    "costo": round(costo, 2)
                })
                costo_totale += costo
            elif prodotto and qb:
                # Trovato nel dizionario ma quantità "q.b." — mostra info prezzo senza calcolare costo
                prezzo_kg = float(prodotto.get("prezzo_kg", 0) or 0)
                ingredienti_result.append({
                    "nome": nome,
                    "quantita": "q.b.",
                    "unita": unita,
                    "prodotto_dizionario": prodotto.get("nome_normalizzato"),
                    "prezzo_kg": prezzo_kg,
                    "costo": None  # non calcolabile senza quantità
                })
            else:
                ingredienti_result.append({
                    "nome": nome,
                    "quantita": quantita,
                    "unita": unita,
                    "prodotto_dizionario": None,
                    "prezzo_kg": None,
                    "costo": None
                })
                if nome:
                    ingredienti_mancanti.append(nome)
    else:
        # Fallback: ingredienti senza quantità (supporta sia str che dict)
        for nome_raw in ricetta.get("ingredienti", []):
            nome = nome_raw.get("nome", "") if isinstance(nome_raw, dict) else nome_raw
            if not nome:
                continue
            prodotto = trova_prodotto_dizionario(nome, dizionario)
            ingredienti_result.append({
                "nome": nome,
                "quantita": None,
                "unita": None,
                "prodotto_dizionario": prodotto.get("nome_normalizzato") if prodotto else None,
                "prezzo_kg": float(prodotto.get("prezzo_kg", 0)) if prodotto else None,
                "costo": None
            })
            if not prodotto:
                ingredienti_mancanti.append(nome)
    
    porzioni = ricetta.get("porzioni", 1) or 1
    
    return {
        "ricetta_id": ricetta_id,
        "nome": ricetta.get("nome", ""),
        "ingredienti": ingredienti_result,
        "costo_totale": round(costo_totale, 2),
        "porzioni": porzioni,
        "costo_porzione": round(costo_totale / porzioni, 2) if porzioni > 0 else 0,
        "ingredienti_mancanti": ingredienti_mancanti,
        "completezza": f"{len(ingredienti_result) - len(ingredienti_mancanti)}/{len(ingredienti_result)}"
    }


@router.post("/ricalcola-costi-tutte-ricette")
async def ricalcola_costi_tutte_ricette():
    """Ricalcola e salva il costo di tutte le ricette nel DB."""
    prodotti = await db.dizionario_prodotti.find({"prezzo_kg": {"$gt": 0}}, {"_id": 0}).to_list(10000)
    dizionario = {p["nome_normalizzato"].lower(): p for p in prodotti}
    aggiornate = 0
    con_costo = 0
    async for ricetta in db.ricette.find({}, {"_id": 0}):
        costo_totale = 0
        ing_trovati = 0
        ing_totali = 0
        ings_aggiornati = list(ricetta.get("ingredienti_dettaglio", []))
        for idx, ing in enumerate(ings_aggiornati):
            nome = (ing.get("nome") or "").strip()
            quantita_raw = ing.get("quantita", 0)
            unita = ing.get("unita_misura", "g") or "g"
            ing_totali += 1
            try:
                quantita = float(str(quantita_raw).replace(",", ".")) if quantita_raw else 0
            except (ValueError, TypeError):
                quantita = 0
            if str(quantita_raw).strip().lower() in ("q.b.", "qb", "q.b", "quanto basta", "") or quantita == 0:
                continue
            prodotto = trova_prodotto_dizionario(nome, dizionario)
            if prodotto and float(prodotto.get("prezzo_kg", 0) or 0) > 0:
                prezzo_kg = float(prodotto["prezzo_kg"])
                costo_calc = round(converti_in_kg(quantita, unita) * prezzo_kg, 4)
                costo_totale += costo_calc
                ing_trovati += 1
                # Aggiorna il prezzo nel documento ingrediente
                ings_aggiornati[idx] = dict(ing)
                ings_aggiornati[idx]["prezzo_kg"] = round(prezzo_kg, 4)
                ings_aggiornati[idx]["costo_calcolato"] = costo_calc
                ings_aggiornati[idx]["prodotto_dizionario_id"] = prodotto.get("id")
        porzioni = ricetta.get("porzioni", 1) or 1
        update_ops = {
            "costo_totale": round(costo_totale, 4),
            "costo_porzione": round(costo_totale / porzioni, 4),
            "completezza": f"{ing_trovati}/{ing_totali}"
        }
        # Aggiorna anche i prezzi_kg degli ingredienti
        if ings_aggiornati:
            update_ops["ingredienti_dettaglio"] = ings_aggiornati
        await db.ricette.update_one(
            {"id": ricetta["id"]},
            {"$set": update_ops}
        )
        aggiornate += 1
        if costo_totale > 0:
            con_costo += 1
    return {"success": True, "ricette_aggiornate": aggiornate, "con_costo": con_costo, "senza_costo": aggiornate - con_costo}


@router.post("/auto-mappa-ingredienti")
async def auto_mappa_ingredienti(ricetta_id: Optional[str] = None):
    """
    Mappa automaticamente gli ingredienti non mappati con il dizionario prodotti.
    Se ricetta_id è specificato, mappa solo quella ricetta.
    Altrimenti mappa TUTTE le ricette con ingredienti senza prezzo.
    Salva il prezzo_kg e prodotto_dizionario_id nel DB.
    """
    prodotti = await db.dizionario_prodotti.find({"prezzo_kg": {"$gt": 0}}, {"_id": 0}).to_list(10000)
    dizionario = {p["nome_normalizzato"].lower(): p for p in prodotti}

    if ricetta_id:
        ricette = await db.ricette.find({"id": ricetta_id}, {"_id": 0}).to_list(1)
    else:
        ricette = await db.ricette.find({}, {"_id": 0}).to_list(5000)

    risultati = {
        "ricette_elaborate": 0,
        "ingredienti_mappati": 0,
        "ingredienti_non_trovati": [],
        "ricette_aggiornate": []
    }

    for ricetta in ricette:
        ings = ricetta.get("ingredienti_dettaglio", [])
        if not ings:
            continue

        modified = False
        costo_totale = 0
        ing_trovati = 0

        for i, ing in enumerate(ings):
            nome = (ing.get("nome") or "").strip()
            if not nome:
                continue

            quantita_raw = ing.get("quantita", 0)
            try:
                quantita = float(str(quantita_raw).replace(",", ".")) if quantita_raw else 0
            except (ValueError, TypeError):
                quantita = 0

            unita = ing.get("unita_misura") or ing.get("unita", "g")

            # Se ha già prezzo_kg salvato e prodotto_id, salta (già mappato)
            if ing.get("prezzo_kg") and ing.get("prodotto_dizionario_id"):
                if quantita > 0:
                    costo_totale += converti_in_kg(quantita, unita) * float(ing["prezzo_kg"])
                    ing_trovati += 1
                continue

            # Cerca nel dizionario
            prodotto = trova_prodotto_dizionario(nome, dizionario)

            if prodotto and float(prodotto.get("prezzo_kg", 0) or 0) > 0:
                prezzo_kg = float(prodotto["prezzo_kg"])
                costo = None
                if quantita > 0:
                    costo = round(converti_in_kg(quantita, unita) * prezzo_kg, 4)
                    costo_totale += costo
                    ing_trovati += 1

                ings[i] = {
                    **ing,
                    "prodotto_dizionario_id": prodotto.get("id"),
                    "prezzo_kg": prezzo_kg,
                    "costo_calcolato": costo
                }
                modified = True
                risultati["ingredienti_mappati"] += 1
            else:
                # Non trovato
                chiave = f"{ricetta.get('nome','?')} → {nome}"
                if chiave not in risultati["ingredienti_non_trovati"]:
                    risultati["ingredienti_non_trovati"].append(chiave)

        if modified:
            porzioni = ricetta.get("porzioni", 1) or 1
            completezza = f"{ing_trovati}/{len([x for x in ings if (x.get('nome') or '').strip()])}"
            await db.ricette.update_one(
                {"id": ricetta["id"]},
                {"$set": {
                    "ingredienti_dettaglio": ings,
                    "costo_totale": round(costo_totale, 4),
                    "costo_porzione": round(costo_totale / porzioni, 4),
                    "completezza": completezza
                }}
            )
            risultati["ricette_aggiornate"].append(ricetta.get("nome", "?"))

        risultati["ricette_elaborate"] += 1

    return {
        "success": True,
        "ricette_elaborate": risultati["ricette_elaborate"],
        "ricette_aggiornate": len(risultati["ricette_aggiornate"]),
        "ingredienti_mappati": risultati["ingredienti_mappati"],
        "ingredienti_non_trovati_count": len(risultati["ingredienti_non_trovati"]),
        "ingredienti_non_trovati": risultati["ingredienti_non_trovati"][:30],
        "ricette_aggiornate_nomi": risultati["ricette_aggiornate"]
    }


@router.post("/auto-rileva-allergeni-tutte")
async def auto_rileva_allergeni_tutte(force: bool = False):
    """
    Analizza automaticamente gli ingredienti di TUTTE le ricette e suggerisce
    gli allergeni presenti in base al nome degli ingredienti (Reg. UE 1169/2011).
    Se force=True sovrascrive anche le ricette che hanno già allergeni.
    Di default aggiorna TUTTE le ricette (non salta quelle già con allergeni).
    """
    # Mappa parole-chiave → allergene (Allegato II Reg. UE 1169/2011)
    MAPPA_ALLERGENI = {
        "Glutine": [
            "farina", "frumento", "grano", "glutine", "semola", "orzo", "segale", "avena",
            "farro", "kamut", "spelta", "pasta", "pane", "pangrattato", "biscotto",
            "crackers", "cereali", "amido di frumento", "malto", "lievito madre",
            "sfoglia", "brioche", "pan", "pizza"
        ],
        "Uova": [
            "uova", "uovo", "albume", "tuorlo", "maionese", "meringa", "frittata",
            "pasta all'uovo", "pasta uovo", "crema pasticcera", "crème brûlée"
        ],
        "Latte": [
            "latte", "panna", "burro", "formaggio", "mozzarella", "ricotta", "yogurt",
            "yoghurt", "mascarpone", "grana", "parmigiano", "pecorino", "provolone",
            "brie", "emmental", "scamorza", "stracchino", "besciamella", "crema",
            "latticini", "latte in polvere", "caseina", "siero di latte"
        ],
        "Frutta a guscio": [
            "mandorle", "mandorla", "nocciole", "nocciola", "noci", "noce",
            "pistacchi", "pistacchio", "anacardi", "anacardio", "pinoli", "pinolo",
            "noci pecan", "noci del brasile", "macadamia", "arachidi"  # nota: arachidi separato
        ],
        "Arachidi": [
            "arachidi", "arachide", "burro di arachidi", "groundnut"
        ],
        "Soia": [
            "soia", "soy", "tofu", "tempeh", "edamame", "latte di soia", "salsa di soia"
        ],
        "Pesce": [
            "pesce", "baccalà", "merluzzo", "salmone", "tonno", "acciughe", "acciuga",
            "alice", "sardine", "sgombro", "branzino", "orata", "spigola", "vongola",
            "sugo al pesce", "pasta al tonno"
        ],
        "Crostacei": [
            "gamberi", "gambero", "gamberetti", "scampi", "aragosta", "granchio",
            "granchi", "astice", "mazzancolle"
        ],
        "Molluschi": [
            "cozze", "cozza", "ostriche", "ostrica", "vongole", "vongola", "polpo",
            "calamari", "calamaro", "seppie", "seppia", "lumache", "frutti di mare"
        ],
        "Sedano": [
            "sedano", "sedano rapa", "rabano", "rapa"
        ],
        "Senape": [
            "senape", "mostarda"
        ],
        "Sesamo": [
            "sesamo", "tahina", "tahini", "semi di sesamo"
        ],
        "Anidride solforosa": [
            "vino", "aceto", "solfiti", "anidride solforosa", "frutta secca",
            "frutta disidratata", "uva passa", "albicocche secche", "succo di frutta"
        ],
        "Lupini": [
            "lupini", "lupino", "farina di lupino"
        ],
    }

    ricette = await db.ricette.find(
        {},
        {"_id": 0, "id": 1, "nome": 1, "allergeni": 1, "ingredienti_dettaglio": 1, "ingredienti": 1}
    ).to_list(2000)

    aggiornate = 0
    skippate = 0
    risultati = []

    for ricetta in ricette:
        # Con force=False: aggiorna comunque tutte, ma segna quelle già con allergeni manuali
        aveva_allergeni = bool(ricetta.get("allergeni") and not ricetta.get("allergeni_auto"))
        if aveva_allergeni and not force:
            # Rilevazione comunque, ma non sovrascrive se impostati manualmente
            pass  # Continua con il rilevamento

        # Raccoglie tutti i nomi ingredienti in minuscolo
        nomi_ing = set()
        for ing in (ricetta.get("ingredienti_dettaglio") or []):
            nome = (ing.get("nome") or "").lower().strip()
            if nome:
                nomi_ing.add(nome)
        for ing_name in (ricetta.get("ingredienti") or []):
            if isinstance(ing_name, str):
                nomi_ing.add(ing_name.lower().strip())

        # Rileva allergeni presenti
        allergeni_trovati = []
        for allergene, keywords in MAPPA_ALLERGENI.items():
            for kw in keywords:
                if any(kw in nome for nome in nomi_ing):
                    if allergene not in allergeni_trovati:
                        allergeni_trovati.append(allergene)
                    break

        # Aggiorna DB — sovrascrive sempre (comportamento atteso dal tasto "auto-rileva")
        await db.ricette.update_one(
            {"id": ricetta["id"]},
            {"$set": {"allergeni": allergeni_trovati, "allergeni_auto": True}}
        )
        aggiornate += 1
        if allergeni_trovati:
            risultati.append({"nome": ricetta.get("nome"), "allergeni": allergeni_trovati})
        else:
            skippate += 1  # conta come senza allergeni rilevati

    return {
        "status": "ok",
        "aggiornate": aggiornate,
        "con_allergeni": len(risultati),
        "senza_allergeni_trovati": skippate,
        "dettaglio": risultati
    }


@router.post("/auto-rileva-allergeni-ricetta/{ricetta_id}")
async def auto_rileva_allergeni_singola(ricetta_id: str):
    """Suggerisce allergeni per una singola ricetta senza sovrascrivere (solo anteprima)."""
    MAPPA_ALLERGENI = {
        "Glutine": ["farina","frumento","grano","glutine","semola","orzo","segale","avena","farro","pasta","pane","pangrattato","sfoglia","pizza"],
        "Uova": ["uova","uovo","albume","tuorlo","maionese","pasta all'uovo","crema pasticcera"],
        "Latte": ["latte","panna","burro","formaggio","mozzarella","ricotta","yogurt","mascarpone","grana","parmigiano","pecorino","besciamella","crema","latticini"],
        "Frutta a guscio": ["mandorle","mandorla","nocciole","nocciola","noci","noce","pistacchi","pistacchio","pinoli","anacardi"],
        "Arachidi": ["arachidi","arachide"],
        "Soia": ["soia","tofu","edamame"],
        "Pesce": ["pesce","baccalà","merluzzo","salmone","tonno","acciughe","alice","sardine"],
        "Crostacei": ["gamberi","gambero","scampi","aragosta","granchio","mazzancolle"],
        "Molluschi": ["cozze","ostriche","vongole","polpo","calamari","seppie","frutti di mare"],
        "Sedano": ["sedano"],
        "Senape": ["senape","mostarda"],
        "Sesamo": ["sesamo","tahina"],
        "Anidride solforosa": ["vino","aceto","solfiti","frutta secca","uva passa"],
        "Lupini": ["lupini","lupino"],
    }
    ricetta = await db.ricette.find_one({"id": ricetta_id}, {"_id": 0})
    if not ricetta:
        raise HTTPException(404, "Ricetta non trovata")

    nomi_ing = set()
    for ing in (ricetta.get("ingredienti_dettaglio") or []):
        nome = (ing.get("nome") or "").lower().strip()
        if nome:
            nomi_ing.add(nome)

    allergeni_trovati = []
    trovati_da = {}
    for allergene, keywords in MAPPA_ALLERGENI.items():
        for kw in keywords:
            matched = [n for n in nomi_ing if kw in n]
            if matched:
                if allergene not in allergeni_trovati:
                    allergeni_trovati.append(allergene)
                    trovati_da[allergene] = matched
                break

    return {
        "ricetta_id": ricetta_id,
        "nome": ricetta.get("nome"),
        "allergeni_suggeriti": allergeni_trovati,
        "trovati_da": trovati_da,
        "ingredienti_analizzati": list(nomi_ing)
    }


@router.post("/aggiorna-allergeni-ricetta")
async def aggiorna_allergeni_ricetta(data: dict):
    """Salva la lista degli allergeni (14 UE) e la dichiarazione nutrizionale per una ricetta."""
    ricetta_id = data.get("ricetta_id")
    allergeni = data.get("allergeni", [])          # lista di stringhe
    nutrizionale = data.get("nutrizionale", {})    # {kcal, grassi, saturi, carboidrati, zuccheri, proteine, sale}
    if not ricetta_id:
        raise HTTPException(400, "ricetta_id mancante")
    result = await db.ricette.update_one(
        {"id": ricetta_id},
        {"$set": {"allergeni": allergeni, "nutrizionale": nutrizionale}}
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Ricetta non trovata")
    return {"status": "ok", "allergeni": allergeni}


@router.get("/registro-allergeni")
async def get_registro_allergeni():
    """Restituisce la matrice allergeni per tutte le ricette (per registro stampabile)."""
    ALLERGENI_14 = [
        "Glutine", "Crostacei", "Uova", "Pesce", "Arachidi", "Soia",
        "Latte", "Frutta a guscio", "Sedano", "Senape", "Sesamo",
        "Anidride solforosa", "Lupini", "Molluschi"
    ]
    ricette = await db.ricette.find({}, {"_id": 0, "id": 1, "nome": 1, "allergeni": 1, "categoria": 1}).to_list(1000)
    return {
        "allergeni_14": ALLERGENI_14,
        "ricette": [
            {
                "id": r["id"],
                "nome": r.get("nome", ""),
                "categoria": r.get("categoria", ""),
                "allergeni": r.get("allergeni", [])
            }
            for r in ricette
        ]
    }


@router.post("/aggiorna-ingredienti-ricetta")
async def aggiorna_ingredienti_ricetta(data: AggiornaIngredienteRicetta):
    """Aggiorna gli ingredienti di una ricetta con quantità e riferimenti al dizionario."""
    ricetta = await db.ricette.find_one({"id": data.ricetta_id}, {"_id": 0})
    if not ricetta:
        raise HTTPException(status_code=404, detail="Ricetta non trovata")
    
    # Carica dizionario
    prodotti = await db.dizionario_prodotti.find({}, {"_id": 0}).to_list(10000)
    dizionario = {p["nome_normalizzato"].lower(): p for p in prodotti}
    
    ingredienti_dettaglio = []
    costo_totale = 0
    
    for ing in data.ingredienti_dettaglio:
        prodotto = None
        if ing.prodotto_dizionario_id:
            prodotto = await db.dizionario_prodotti.find_one({"id": ing.prodotto_dizionario_id}, {"_id": 0})
        
        if not prodotto:
            prodotto = trova_prodotto_dizionario(ing.nome, dizionario)
        
        prezzo_kg = None
        costo = None
        
        if prodotto and ing.quantita > 0:
            prezzo_kg = float(prodotto.get("prezzo_kg", 0) or 0)
            quantita_kg = converti_in_kg(ing.quantita, ing.unita_misura)
            costo = round(quantita_kg * prezzo_kg, 2)
            costo_totale += costo
        
        ingredienti_dettaglio.append({
            "nome": ing.nome,
            "quantita": ing.quantita,
            "unita_misura": ing.unita_misura,
            "prodotto_dizionario_id": prodotto.get("id") if prodotto else None,
            "prezzo_kg": prezzo_kg,
            "costo_calcolato": costo
        })
    
    # Aggiorna ricetta
    await db.ricette.update_one(
        {"id": data.ricetta_id},
        {"$set": {
            "ingredienti_dettaglio": ingredienti_dettaglio,
            "costo_totale": round(costo_totale, 2),
            "costo_porzione": round(costo_totale / (ricetta.get("porzioni", 1) or 1), 2)
        }}
    )
    
    return {
        "status": "ok",
        "costo_totale": round(costo_totale, 2),
        "ingredienti": ingredienti_dettaglio
    }


@router.post("/rinomina-ingrediente")
async def rinomina_ingrediente(
    nome_vecchio: str,
    nome_nuovo: str,
    solo_ricette_ids: str = None  # IDs separati da virgola, o None per tutte
):
    """
    Rinomina un ingrediente in tutte le ricette (o in un sottoinsieme).
    Utile per correggere ingredienti non mappati dal tab Non Mappati.
    """
    filtro = {"ingredienti_dettaglio.nome": nome_vecchio}
    if solo_ricette_ids:
        ids = [x.strip() for x in solo_ricette_ids.split(",") if x.strip()]
        filtro["id"] = {"$in": ids}
    
    ricette = await db.ricette.find(filtro, {"_id": 0, "id": 1, "nome": 1, "ingredienti_dettaglio": 1}).to_list(200)
    
    aggiornate = []
    for r in ricette:
        ings = r.get("ingredienti_dettaglio", [])
        modificato = False
        for i, ing in enumerate(ings):
            if ing.get("nome") == nome_vecchio:
                ings[i]["nome"] = nome_nuovo
                modificato = True
        if modificato:
            # Aggiorna anche la lista ingredienti (legacy)
            lista = [nome_nuovo if x == nome_vecchio else x for x in r.get("ingredienti", [])]
            await db.ricette.update_one(
                {"id": r["id"]},
                {"$set": {"ingredienti_dettaglio": ings, "ingredienti": lista}}
            )
            aggiornate.append(r["nome"])
    
    return {
        "success": True,
        "nome_vecchio": nome_vecchio,
        "nome_nuovo": nome_nuovo,
        "ricette_aggiornate": aggiornate,
        "count": len(aggiornate)
    }


@router.post("/salva-porzioni-ricetta")
async def salva_porzioni_ricetta(ricetta_id: str, porzioni_base: int):
    """Salva il numero di pezzi/porzioni base della ricetta"""
    ricetta = await db.ricette.find_one({"id": ricetta_id})
    if not ricetta:
        raise HTTPException(status_code=404, detail="Ricetta non trovata")
    await db.ricette.update_one(
        {"id": ricetta_id},
        {"$set": {"porzioni": porzioni_base, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    return {"success": True, "porzioni_base": porzioni_base}


@router.post("/usa-ricetta")
async def usa_ricetta(request: UsaRicettaRequest):
    """
    Usa una ricetta e scala le quantità dal magazzino.
    Deduce le quantità degli ingredienti dal dizionario prodotti.
    Se prodotto_dizionario_id manca, cerca per nome nel dizionario.
    """
    ricetta = await db.ricette.find_one({"id": request.ricetta_id}, {"_id": 0})
    if not ricetta:
        raise HTTPException(status_code=404, detail="Ricetta non trovata")
    
    ingredienti_dettaglio = ricetta.get("ingredienti_dettaglio", [])
    if not ingredienti_dettaglio:
        raise HTTPException(status_code=400, detail="Ricetta senza ingredienti dettagliati")
    
    # Carica dizionario per ricerca per nome
    prodotti_list = await db.dizionario_prodotti.find({}, {"_id": 0}).to_list(10000)
    dizionario = {p["nome_normalizzato"].lower(): p for p in prodotti_list}
    
    # Calcola quantità da scalare per ogni ingrediente
    ingredienti_scalati = []
    errori = []
    
    for ing in ingredienti_dettaglio:
        nome_ing = ing.get("nome", "").strip()
        
        # Verifica quantità valida
        quantita_raw = ing.get("quantita", 0)
        try:
            quantita_base = float(str(quantita_raw).replace(",", ".")) if quantita_raw else 0
        except (ValueError, TypeError):
            errori.append(f"{nome_ing}: quantità non valida ({quantita_raw})")
            continue
        
        if quantita_base <= 0:
            continue  # Salta ingredienti senza quantità (es. "q.b.")
        
        # Trova prodotto: prima per ID, poi per nome
        prodotto_id = ing.get("prodotto_dizionario_id")
        prodotto = None
        
        if prodotto_id:
            prodotto = await db.dizionario_prodotti.find_one({"id": prodotto_id}, {"_id": 0})
        
        if not prodotto and nome_ing:
            # Cerca per nome nel dizionario
            prodotto = trova_prodotto_dizionario(nome_ing, dizionario)
        
        if not prodotto:
            errori.append(f"{nome_ing}: non trovato nel dizionario")
            continue
        
        # Converti quantità in kg
        unita = ing.get("unita_misura") or ing.get("unita", "g")
        quantita = quantita_base * request.porzioni
        quantita_kg = converti_in_kg(quantita, unita)
        
        disponibile = prodotto.get("quantita_disponibile_kg", 0)
        if quantita_kg > disponibile:
            errori.append(f"{nome_ing}: richiesti {quantita_kg:.3f}kg, disponibili {disponibile:.3f}kg")
            continue
        
        # Scala la quantità
        nuova_usata = prodotto.get("quantita_usata_kg", 0) + quantita_kg
        nuova_disponibile = prodotto.get("quantita_totale_kg", 0) - nuova_usata
        
        await db.dizionario_prodotti.update_one(
            {"id": prodotto["id"]},
            {"$set": {
                "quantita_usata_kg": round(nuova_usata, 3),
                "quantita_disponibile_kg": round(max(0, nuova_disponibile), 3)
            }}
        )
        
        ingredienti_scalati.append({
            "nome": nome_ing,
            "prodotto_trovato": prodotto.get("nome_normalizzato"),
            "quantita_usata_kg": round(quantita_kg, 3),
            "disponibile_dopo": round(max(0, nuova_disponibile), 3)
        })
    
    if errori and not ingredienti_scalati:
        raise HTTPException(status_code=400, detail="; ".join(errori))
    
    return {
        "status": "ok",
        "ricetta": ricetta.get("nome"),
        "porzioni": request.porzioni,
        "ingredienti_scalati": ingredienti_scalati,
        "avvisi": errori
    }


@router.get("/ricette-riepilogo")
async def get_ricette_con_costi():
    """Ottiene tutte le ricette con riepilogo costi"""
    ricette = await db.ricette.find({}, {"_id": 0}).to_list(5000)
    prodotti = await db.dizionario_prodotti.find({}, {"_id": 0}).to_list(10000)
    dizionario = {p["nome_normalizzato"].lower(): p for p in prodotti}
    
    risultati = []
    for ricetta in ricette:
        costo_totale = 0
        ingredienti_con_prezzo = 0
        ingredienti_totali = 0
        
        if ricetta.get("ingredienti_dettaglio"):
            for ing in ricetta["ingredienti_dettaglio"]:
                nome_ing = (ing.get("nome") or "").strip()
                if not nome_ing:
                    continue
                ingredienti_totali += 1
                prezzo_ing = ing.get("prezzo_kg")
                costo_ing = ing.get("costo_calcolato")

                if costo_ing is not None and costo_ing > 0:
                    costo_totale += costo_ing
                    ingredienti_con_prezzo += 1
                elif prezzo_ing and prezzo_ing > 0:
                    # Ha prezzo ma quantità q.b. o 0 — conta come "con prezzo" ma non contribuisce al costo
                    ingredienti_con_prezzo += 1
                elif nome_ing:
                    # Nessun prezzo salvato — prova al volo
                    prodotto = trova_prodotto_dizionario(nome_ing, dizionario)
                    if prodotto and float(prodotto.get("prezzo_kg", 0) or 0) > 0:
                        try:
                            quantita_raw = ing.get("quantita", 0)
                            qb = str(quantita_raw).strip().lower() in ("q.b.", "qb", "q.b", "quanto basta", "")
                            if not qb:
                                quantita = float(str(quantita_raw).replace(",", "."))
                                prezzo_kg = float(prodotto.get("prezzo_kg", 0))
                                quantita_kg = converti_in_kg(quantita, ing.get("unita_misura", "g"))
                                costo_totale += quantita_kg * prezzo_kg
                            ingredienti_con_prezzo += 1
                        except Exception:
                            pass
        else:
            ingredienti_totali = len(ricetta.get("ingredienti", []))
            for nome in ricetta.get("ingredienti", []):
                if trova_prodotto_dizionario(nome, dizionario):
                    ingredienti_con_prezzo += 1
        
        porzioni = ricetta.get("porzioni", 1) or 1
        
        risultati.append({
            "id": ricetta.get("id"),
            "nome": ricetta.get("nome"),
            "ingredienti_totali": ingredienti_totali,
            "ingredienti_con_prezzo": ingredienti_con_prezzo,
            "costo_totale": round(costo_totale, 2),
            "costo_porzione": round(costo_totale / porzioni, 2) if porzioni > 0 else 0,
            "completezza": f"{ingredienti_con_prezzo}/{ingredienti_totali}"
        })
    
    return risultati


# ==================== HELPER FUNCTIONS ====================

def estrai_peso_e_unita(descrizione: str) -> Optional[tuple]:
    """
    Estrae peso e unità dalla descrizione del prodotto in fattura.
    Ritorna (peso_confezione_in_kg_o_lt, unita) o None se non trovato.

    IMPORTANTE: Ritorna None per descrizioni come "IN SACCHI 25 KG" dove
    il peso nella descrizione descrive il contenuto del sacco, NON il peso
    della confezione da acquistare (in quel caso Qt è già in KG).

    Gestisce pattern come:
      DA KG.25, KG 25, 25KG, x 5kg, x 2.5 kg   → kg per confezione
      GR.400, 400G, 400GR, G.500               → kg (grammi convertiti)
      L.5, 5L, 5LT, 2lt, x 2lt                → lt per confezione
      ML.500, 500ML                             → lt (ml convertiti)
    """
    desc = descrizione.upper()

    # Pattern "SACCHI": la parola SACCHI indica che il peso è del sacco,
    # non della confezione acquistata → Qt è già in KG totali → ritorna None
    if re.search(r'\bSACCH[IO]\b', desc):
        return None

    # KG: "DA KG.25", "x 5 KG", "x 25KG", "5KG", "5 KG"
    # NON: solo "KG" senza numero (es. "PECORINO KG")
    # Ordine: prima "x NNN KG" poi "NNN KG" poi "KG.NNN"
    kg_patterns = [
        r'[Xx]\s*(\d+(?:[.,]\d+)?)\s*KG\.?\b',          # x 25 KG, x 2.5KG
        r'(?:DA\s+)?KG\.?\s*(\d+(?:[.,]\d+)?)',          # DA KG.25, KG.25, KG 25
        r'(\d+(?:[.,]\d+)?)\s*KG\.?\b',                  # 25KG, 25 KG, 25 KG.
    ]
    for pattern in kg_patterns:
        match = re.search(pattern, desc)
        if match:
            try:
                peso = float(match.group(1).replace(",", "."))
                if 0 < peso <= 2000:
                    return (peso, "kg")
            except ValueError:
                continue

    # ML: prima dei grammi per evitare falsi match su "G"
    ml_patterns = [
        r'(\d+(?:[.,]\d+)?)\s*ML\b',
        r'ML\.?\s*(\d+(?:[.,]\d+)?)',
    ]
    for pattern in ml_patterns:
        match = re.search(pattern, desc)
        if match:
            try:
                ml = float(match.group(1).replace(",", "."))
                if 0 < ml <= 100000:
                    return (ml / 1000, "lt")
            except ValueError:
                continue

    # Grammi: "GR.400", "400GR", "G.500", "400G" — non deve matchare "M.G. 82%"
    # Richiediamo che GR/G sia preceduto da spazio o inizio stringa (non da altra lettera)
    g_patterns = [
        r'(?<![A-Z])(?:GR|G)\.?\s*(\d+(?:[.,]\d+)?)(?!\s*[\d%])',
        r'(\d+(?:[.,]\d+)?)\s*(?:GR|G)\b(?!\s*%)',
    ]
    for pattern in g_patterns:
        match = re.search(pattern, desc)
        if match:
            try:
                grammi = float(match.group(1).replace(",", "."))
                if 0 < grammi <= 100000:
                    return (grammi / 1000, "kg")
            except ValueError:
                continue

    # Litri: "L.5", "5L", "LT.5", "5LT", "x 2lt"
    l_patterns = [
        r'[Xx]\s*(\d+(?:[.,]\d+)?)\s*L[T]?\b',     # x 2lt, x 5LT
        r'(\d+(?:[.,]\d+)?)\s*L[T]?\b',             # 5L, 5LT, 2lt
        r'L[T]?\.?\s*(\d+(?:[.,]\d+)?)',             # L.5, LT.5
    ]
    for pattern in l_patterns:
        match = re.search(pattern, desc)
        if match:
            try:
                litri = float(match.group(1).replace(",", "."))
                if 0 < litri <= 10000:
                    return (litri, "lt")
            except ValueError:
                continue

    return None


def normalizza_nome_prodotto(descrizione: str) -> str:
    """Pulisce e normalizza il nome del prodotto"""
    if not descrizione:
        return ""
    
    testo = descrizione.strip()
    
    # Rimuovi newline e spazi multipli
    testo = re.sub(r'\s+', ' ', testo)
    
    # Rimuovi info lotto/scadenza dopo // (es: "// F2005 Scadenza 05/2027" o "// Lotto F2005 Scadenza 05/2027")
    testo = re.sub(r'\s*//.*$', '', testo, flags=re.IGNORECASE)
    
    # Rimuovi pesi e quantità
    testo = re.sub(r'\s*(?:DA\s+)?KG\.?\s*\d+(?:[.,]\d+)?', '', testo, flags=re.IGNORECASE)
    testo = re.sub(r'\s*\d+(?:[.,]\d+)?\s*KG\b', '', testo, flags=re.IGNORECASE)
    testo = re.sub(r'\s*(?:G|GR)\.?\s*\d+', '', testo, flags=re.IGNORECASE)
    testo = re.sub(r'\s*\d+\s*(?:G|GR)\b', '', testo, flags=re.IGNORECASE)
    testo = re.sub(r'\s*(?:L|LT)\.?\s*\d+(?:[.,]\d+)?', '', testo, flags=re.IGNORECASE)
    testo = re.sub(r'\s*\d+(?:[.,]\d+)?\s*(?:L|LT)\b', '', testo, flags=re.IGNORECASE)
    testo = re.sub(r'\s*ML\.?\s*\d+', '', testo, flags=re.IGNORECASE)
    testo = re.sub(r'\s*\d+\s*ML\b', '', testo, flags=re.IGNORECASE)
    
    # Rimuovi codici lotto (L.xxx, L.F.xxx, F2005, ecc.)
    testo = re.sub(r'\s+L\.?F?\.?\d*/?[\w\-]*', '', testo, flags=re.IGNORECASE)
    testo = re.sub(r'\s+[A-Z]\d{3,}', '', testo)  # es: F2005, B1234
    
    # Rimuovi moltiplicatori (x96, x20, X5)
    testo = re.sub(r'\s*[xX]\s*\d+', '', testo)
    
    # Rimuovi date
    testo = re.sub(r'\s*\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}', '', testo)
    
    # Rimuovi codici alfanumerici finali
    testo = re.sub(r'\s*-\s*\d{5,}$', '', testo)
    
    return testo.strip()[:100]


def trova_prodotto_dizionario(nome: str, dizionario: dict) -> Optional[dict]:
    """
    Cerca un prodotto nel dizionario con match multi-livello.
    Priorità: esatto > inizia con > parole chiave > contenuto parziale.
    Preferisce sempre prodotti con prezzo > 0.
    """
    if not nome:
        return None

    # Tabella alias: nomi comuni usati nelle ricette → keyword da cercare nel dizionario
    ALIAS = {
        "zucchero semolato": "zucchero raf.sem",
        "zucchero semol": "zucchero raf.sem",
        "zucchero bianco": "zucchero raf.sem",
        "zucchero": "zucchero",
        "semola": "semola",
        "farina 00": "farina 00",
        "farina 0": "farina 0",
        "uova": "uova",
        "uovo": "uova",
        "burro": "burro",
        "sale": "sale fino",
        "olio": "olio extravergine",
        "olio evo": "olio extravergine",
        "latte": "latte",
        "panna": "panna",
        "lievito": "lievito",
        "lievito di birra": "lievito birra",
        "strutto": "strutto",
        "ricotta": "ricotta",
        "cioccolato": "cioccolato",
        "cacao": "cacao",
        "vaniglia": "vaniglia",
        "miele": "miele",
        "limone": "limone",
        "cannella": "cannella",
        "margarina": "margar",
        "margarina crema": "margar",
        "tuorlo": "tuorlo",
        "tuorlo d'uovo": "tuorlo",
        "albume": "albume",
        "fecola": "fecola",
        "fecola di patate": "fecola",
        "amido": "amido",
        "amido di mais": "amido mais",
        "acqua": "acqua",
        "olio di semi": "olio di semi",
        "olio di girasole": "girasole",
        "aceto": "aceto",
        "pasta frolla": "pasta frolla",
        "pasta sfoglia": "pasta sfoglia",
        "gelatina": "gelatina",
        "colla di pesce": "colla di pesce",
        "wrustel": "wurstel",
        "capperi": "capperi",
        "fiori di zucca": "fiori",
        "provola": "provola",
        "prosciutto cotto": "prosciutto cotto",
        "prosciutto crudo": "prosciutto crudo",
        "porchetta": "porchetta",
        "p.cotto": "prosciutto cotto",
        "p.crudo": "prosciutto crudo",
        "melanzane": "melanzane",
        "zucchine": "zucchine",
        "peperoni": "peperoni",
        "pomodori": "pomodori",
        "patate": "patate",
        "cipolle": "cipolla",
        "aglio": "aglio",
        "basilico": "basilico",
        "prezzemolo": "prezzemolo",
        "mozzarella": "mozzarella",
        "parmigiano": "parmigiano",
        "pancetta": "pancetta",
        "guanciale": "guanciale",
        "mortadella": "mortadella",
        "salsiccia": "salsiccia",
        "pasta": "pasta",
        # Abbreviazioni e nomi speciali fornitori
        "farina 00 caputo rinforz.": "farina 00",
        "farina 00 caputo rinforz": "farina 00",
        "farina caputo rinforzo": "farina 00",
        "caputo rinforz": "farina 00",
        "margar wienercreme": "margar",
        "wienercreme": "margar",
        "est.zuppa inglese": "zuppa inglese",
        "est. zuppa inglese": "zuppa inglese",
        "estratto zuppa inglese": "zuppa inglese",
        "zuppa inglese": "zuppa inglese",
        "crema chantilly": "panna",
        "beurre": "burro",
        "fioretto": "farina",
        "frumento tenero": "farina",
        "frumento duro": "semola",
        "lievito madre": "lievito",
        "pasta madre": "lievito",
        "glucosio": "glucosio",
        "sciroppo glucosio": "glucosio",
        "invertzucker": "zucchero invertito",
        "zucchero invertito": "zucchero",
        "trealosio": "zucchero",
        "sorbitolo": "sorbitolo",
        "alcol": "alcol",
        "alcool": "alcol",
        "rum": "rum",
        "liquore": "liquore",
        "pasta di mandorle": "pasta mandorle",
        "frangipane": "pasta mandorle",
        "pistacchio": "pistacchio",
        "mandorle": "mandorle",
        "nocciole": "nocciole",
        "noci": "noci",
        "uvetta": "uvetta",
        "canditi": "canditi",
        "arancia candita": "canditi arancia",
        "cedro candito": "canditi cedro",
        "ciliegie candite": "canditi ciliegie",
        "frutta candita": "canditi",
    }

    nome_lower = nome.lower().strip()
    # Applica alias se presente (cerca anche versioni con/senza punti)
    nome_no_punti = re.sub(r'\.', '', nome_lower).strip()
    # Rimuovi peso/quantità dal nome per trovare l'alias
    nome_per_alias = re.sub(r'\b\d+[\.,]?\d*\s*(g|kg|gr|ml|lt|l|pz|pzz)?\b', '', nome_lower, flags=re.IGNORECASE).strip()
    # Rimuovi anche unità standalone (es. "kg" senza numero come in "zucchero semolato kg 1")
    nome_per_alias = re.sub(r'\s+\b(kg|gr|ml|lt|pz|pzz|g)\b\s*', ' ', nome_per_alias, flags=re.IGNORECASE).strip()
    nome_per_alias = re.sub(r'\s+', ' ', nome_per_alias).strip()
    nome_ricerca = (ALIAS.get(nome_lower) or ALIAS.get(nome_no_punti)
                    or ALIAS.get(nome_per_alias) or nome_lower)
    
    # Normalizza: rimuovi pesi/quantità dal nome ingrediente e punti abbreviativi
    nome_clean = re.sub(r'\b\d+[\.,]?\d*\s*(g|kg|gr|ml|lt|l|pz|pzz)?\b', '', nome_ricerca, flags=re.IGNORECASE).strip()
    nome_clean = re.sub(r'\s+', ' ', nome_clean).strip()
    # Versione senza punti per confronti con chiavi dizionario
    nome_clean_no_punti = re.sub(r'\.+', ' ', nome_clean).strip()
    nome_clean_no_punti = re.sub(r'\s+', ' ', nome_clean_no_punti).strip()
    parole = [p for p in nome_clean_no_punti.split() if len(p) >= 3]

    # 1. Match esatto
    if nome_clean in dizionario:
        return dizionario[nome_clean]
    if nome_lower in dizionario:
        return dizionario[nome_lower]

    # 1b. Match con chiavi dizionario normalizzate senza punti
    # Crea dizionario chiave-senza-punti → chiave originale
    diz_no_punti = {re.sub(r'\.+', ' ', k).replace('  ', ' '): k for k in dizionario}
    if nome_clean_no_punti in diz_no_punti:
        return dizionario[diz_no_punti[nome_clean_no_punti]]
    
    # 2. Il nome dell'ingrediente inizia con le stesse parole del prodotto
    # ES: "semola" deve matchare "semola media xxl mad", NON "ciabattina con semola"
    candidati_esatti = []  # (priorità, prezzo, chiave, prodotto)
    for key, prod in dizionario.items():
        prezzo = float(prod.get("prezzo_kg", 0) or 0)
        key_no_punti = re.sub(r'\.+', ' ', key).replace('  ', ' ').strip()

        if key.startswith(nome_clean) or key_no_punti.startswith(nome_clean_no_punti):
            candidati_esatti.append((0, -prezzo, key, prod))
        elif parole and (key.startswith(parole[0]) or key_no_punti.startswith(parole[0])):
            match_count = sum(1 for p in parole if p in key or p in key_no_punti)
            if match_count >= max(1, len(parole) // 2):
                candidati_esatti.append((1, -prezzo, key, prod))
        elif parole and len(parole[0]) >= 5:
            prefix = parole[0][:6]
            if key.startswith(prefix) or key_no_punti.startswith(prefix):
                candidati_esatti.append((2, -prezzo, key, prod))
    
    if candidati_esatti:
        candidati_esatti.sort(key=lambda x: (x[0], x[1]))
        return candidati_esatti[0][3]
    
    # 3. Tutte le parole chiave dell'ingrediente compaiono nel key del dizionario
    # ES: "zucchero semolato" deve trovare "zucchero semolato kg1", NON "zucchero a velo"
    if len(parole) >= 2:
        multi_word_matches = []
        for key, prod in dizionario.items():
            prezzo = float(prod.get("prezzo_kg", 0) or 0)
            if all(p in key for p in parole):
                multi_word_matches.append((-prezzo, key, prod))
        if multi_word_matches:
            multi_word_matches.sort()
            return multi_word_matches[0][2]
    
    # 4. Match contenuto: nome_ingrediente è sottostringa del key (con preferenza prezzo > 0)
    contenuto_matches = []
    for key, prod in dizionario.items():
        prezzo = float(prod.get("prezzo_kg", 0) or 0)
        if nome_clean in key:
            posizione = key.find(nome_clean)
            contenuto_matches.append((posizione, -prezzo, key, prod))
    
    if contenuto_matches:
        contenuto_matches.sort(key=lambda x: (x[0], x[1]))
        return contenuto_matches[0][3]
    
    # 5. Match inverso: il key è contenuto nel nome ingrediente
    inverso_matches = []
    for key, prod in dizionario.items():
        prezzo = float(prod.get("prezzo_kg", 0) or 0)
        if key in nome_clean and len(key) >= 4:
            inverso_matches.append((-len(key), -prezzo, key, prod))
    
    if inverso_matches:
        inverso_matches.sort()
        return inverso_matches[0][3]
    
    # 5b. Match parola chiave: ogni parola significativa dell'ingrediente compare nel key
    # ES: "melanzane" deve trovare "berni melanzane filetti" anche se non inizia con "melanzane"
    if parole:
        parola_principale = max(parole, key=len)  # parola più lunga = più specifica
        if len(parola_principale) >= 5:
            keyword_matches = []
            for key, prod in dizionario.items():
                prezzo = float(prod.get("prezzo_kg", 0) or 0)
                if parola_principale in key:
                    keyword_matches.append((-prezzo, key, prod))
            if keyword_matches:
                keyword_matches.sort()
                return keyword_matches[0][2]
    
    # 6. Fallback: prima parola (almeno 4 caratteri) con preferenza a prodotti con prezzo
    prima_parola = nome_clean.split()[0] if nome_clean.split() else ""
    if prima_parola and len(prima_parola) >= 4:
        fallback = []
        for key, prod in dizionario.items():
            prezzo = float(prod.get("prezzo_kg", 0) or 0)
            if key.startswith(prima_parola):
                fallback.append((-prezzo, key, prod))
        if fallback:
            fallback.sort()
            return fallback[0][2]
    
    return None


def converti_in_kg(quantita: float, unita: str) -> float:
    """Converte una quantità nell'unità base (kg o lt)"""
    if not quantita:
        return 0
    
    unita = (unita or "g").lower().strip()
    
    if unita in ["kg", "kilogrammi", "lt", "litri", "l"]:
        return quantita
    elif unita in ["g", "gr", "grammi", "ml"]:
        return quantita / 1000
    else:
        # Default: assume grammi per ingredienti
        return quantita / 1000


# ==================== STAMPA SCHEDA RICETTA ====================

@router.get("/stampa-ricetta/{ricetta_id}")
async def stampa_scheda_ricetta(ricetta_id: str):
    """Genera una scheda ricetta stampabile in formato HTML con food cost."""
    from fastapi.responses import HTMLResponse

    ricetta = await db.ricette.find_one(
        {"$or": [{"id": ricetta_id}, {"ricetta_id": ricetta_id}]},
        {"_id": 0}
    )
    if not ricetta:
        raise HTTPException(status_code=404, detail="Ricetta non trovata")

    prodotti = await db.dizionario_prodotti.find({}, {"_id": 0}).to_list(10000)
    dizionario = {p["nome_normalizzato"].lower(): p for p in prodotti}

    ingredienti_dettaglio = ricetta.get("ingredienti_dettaglio", [])
    costo_totale = 0
    rows = ""

    for ing in ingredienti_dettaglio:
        nome = ing.get("nome", "").strip()
        if not nome:
            continue
        quantita_raw = ing.get("quantita", 0)
        unita = ing.get("unita_misura") or ing.get("unita", "g")
        try:
            qt = float(str(quantita_raw).replace(",", ".")) if quantita_raw else 0
        except (ValueError, TypeError):
            qt = 0

        prodotto = trova_prodotto_dizionario(nome, dizionario)
        prezzo_kg = float(prodotto.get("prezzo_kg", 0)) if prodotto else 0
        prodotto_nome = prodotto.get("nome_normalizzato", "-") if prodotto else "-"

        costo_ing = converti_in_kg(qt, unita) * prezzo_kg if qt > 0 else 0
        costo_totale += costo_ing
        qt_display = f"{str(quantita_raw)} {unita}" if str(quantita_raw) not in ("0","") else "q.b."
        costo_display = f"€{costo_ing:.3f}" if costo_ing > 0 else "-"
        color = "color:#276749" if prodotto else "color:#9b2c2c"
        trovato = prodotto_nome[:35] if prodotto else "Non in dizionario"

        rows += f"""<tr>
          <td style="padding:6px 8px;border-bottom:1px solid #e2e8f0;font-weight:500">{nome}</td>
          <td style="padding:6px 8px;border-bottom:1px solid #e2e8f0;text-align:center">{qt_display}</td>
          <td style="padding:6px 8px;border-bottom:1px solid #e2e8f0;font-size:11px;{color}">{trovato}</td>
          <td style="padding:6px 8px;border-bottom:1px solid #e2e8f0;text-align:right;font-weight:500">{costo_display}</td>
        </tr>"""

    porzioni = ricetta.get("porzioni", ricetta.get("pezzi_ricetta_base", 100)) or 100
    costo_per_pezzo = costo_totale / porzioni if porzioni > 0 else 0
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    note_html = ricetta.get("procedimento") or ricetta.get("note") or "<i style='color:#aaa'>Nessuna nota inserita.</i>"

    html = f"""<!DOCTYPE html>
<html lang="it"><head><meta charset="UTF-8">
<title>Scheda Ricetta – {ricetta.get('nome','')}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:Arial,sans-serif;color:#1a1a1a;background:white;padding:24px;max-width:800px;margin:0 auto}}
.hdr{{border-bottom:3px solid #e07b3c;padding-bottom:12px;margin-bottom:20px}}
.hdr h1{{font-size:22px;color:#c05621;text-transform:capitalize}}
.hdr .meta{{font-size:11px;color:#718096;margin-top:4px}}
.sec{{font-size:13px;font-weight:bold;color:#744210;background:#fefcbf;padding:6px 10px;border-left:3px solid #e07b3c;margin:16px 0 8px}}
table{{width:100%;border-collapse:collapse;font-size:12px}}
th{{background:#fff3e0;padding:6px 8px;text-align:left;font-weight:600;color:#744210;border-bottom:2px solid #e07b3c}}
tr:nth-child(even) td{{background:#fffaf0}}
.cost-box{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:16px 0}}
.cost-item{{background:#f7fafc;border:1px solid #e2e8f0;border-radius:8px;padding:12px;text-align:center}}
.cost-item .val{{font-size:20px;font-weight:bold;color:#2c5282}}
.cost-item .lbl{{font-size:10px;color:#718096;margin-top:2px}}
.firma{{margin-top:32px;border-top:1px solid #e2e8f0;padding-top:16px;display:flex;justify-content:space-between}}
.firma-box{{border-top:1px solid #aaa;width:180px;text-align:center;padding-top:4px;font-size:10px;color:#555}}
.print-btn{{position:fixed;bottom:20px;right:20px;background:#e07b3c;color:white;border:none;padding:10px 18px;border-radius:8px;cursor:pointer;font-size:14px;box-shadow:0 4px 12px rgba(0,0,0,.2)}}
@media print{{.print-btn{{display:none}}}}
</style></head><body>
<button class="print-btn" onclick="window.print()">Stampa / Salva PDF</button>
<div class="hdr"><h1>{ricetta.get('nome','')}</h1>
<div class="meta">Porzioni base: {porzioni} pz &nbsp;|&nbsp; Generata: {now_str} &nbsp;|&nbsp; Ceraldi Group S.R.L.</div></div>
<div class="cost-box">
  <div class="cost-item"><div class="val">€{costo_totale:.3f}</div><div class="lbl">Costo Totale ({porzioni} pz)</div></div>
  <div class="cost-item"><div class="val">€{costo_per_pezzo:.3f}</div><div class="lbl">Costo per Pezzo</div></div>
  <div class="cost-item"><div class="val">{len(ingredienti_dettaglio)}</div><div class="lbl">Ingredienti</div></div>
</div>
<div class="sec">Ingredienti</div>
<table><thead><tr><th>Ingrediente</th><th>Quantità</th><th>Prodotto Dizionario</th><th style="text-align:right">Costo</th></tr></thead>
<tbody>{rows}
<tr style="font-weight:bold;background:#fff3e0">
  <td colspan="3" style="padding:8px;text-align:right;color:#744210">TOTALE FOOD COST</td>
  <td style="padding:8px;text-align:right;color:#276749;font-size:14px">€{costo_totale:.3f}</td>
</tr></tbody></table>
<div class="sec">Note / Procedimento</div>
<div style="background:#f9f9f9;border:1px solid #e2e8f0;border-radius:6px;padding:12px;font-size:12px;line-height:1.6;min-height:80px">{note_html}</div>
<div class="firma"><div class="firma-box">Chef / Responsabile Ricetta</div><div class="firma-box">Responsabile HACCP</div></div>
</body></html>"""

    return HTMLResponse(content=html)


# ==================== CALCOLO NUTRIZIONALE USDA ====================

import json as _json
import pathlib as _pathlib
import unicodedata as _unicodedata

def _carica_usda() -> list:
    """Carica il database USDA dal file JSON."""
    _db_path = _pathlib.Path(__file__).parent.parent / "data" / "usda_nutrizionale.json"
    with open(_db_path, "r", encoding="utf-8") as f:
        return _json.load(f)

def _normalizza(testo: str) -> str:
    """Normalizza testo per confronto: minuscolo, senza accenti, senza punteggiatura."""
    t = testo.lower().strip()
    t = _unicodedata.normalize("NFD", t)
    t = "".join(c for c in t if _unicodedata.category(c) != "Mn")
    return t

def _trova_voce_usda(nome_ingrediente: str, db_usda: list) -> dict | None:
    """
    Cerca la voce USDA più adatta per un ingrediente.
    Confronta per alias con match esatto prima, poi parziale.
    """
    nome_n = _normalizza(nome_ingrediente)
    # Esatto su alias
    for voce in db_usda:
        for alias in voce["aliases"]:
            if _normalizza(alias) == nome_n:
                return voce
    # Parziale: alias contenuto nel nome ingrediente
    for voce in db_usda:
        for alias in voce["aliases"]:
            if _normalizza(alias) in nome_n or nome_n in _normalizza(alias):
                return voce
    return None


@router.post("/calcola-nutrizionale/{ricetta_id}")
async def calcola_nutrizionale_ricetta(ricetta_id: str):
    """
    Calcola automaticamente i valori nutrizionali per 100g di prodotto finito
    basandosi sugli ingredienti della ricetta e il database USDA.

    Restituisce:
      - valori_nutrizionali: {kcal, kj, grassi, saturi, carboidrati, zuccheri, fibre, proteine, sale}
      - copertura: % ingredienti trovati nel DB USDA
      - ingredienti_non_trovati: lista ingredienti senza corrispondenza USDA
    """
    ricetta = await db.ricette.find_one({"id": ricetta_id}, {"_id": 0})
    if not ricetta:
        raise HTTPException(404, "Ricetta non trovata")

    # Se la ricetta ha componenti[], usa il BOM esploso come sorgente ingredienti
    if ricetta.get("componenti"):
        from routers.ricette import _esplodi_componente
        porzioni_base = float(ricetta.get("porzioni", 1) or 1)
        visitati = {ricetta_id}
        ing_flat_totale = []
        for comp in ricetta["componenti"]:
            flat, _ = await _esplodi_componente(comp, porzioni_base, porzioni_base, visitati)
            ing_flat_totale.extend(flat)
        # Deduplica per (nome, um)
        raggruppati: dict = {}
        for ing in ing_flat_totale:
            chiave = (ing["nome"], ing["unita_misura"])
            raggruppati[chiave] = raggruppati.get(chiave, 0.0) + ing["quantita"]
        ingredienti = [
            {"nome": n, "quantita": qt, "unita_misura": um}
            for (n, um), qt in raggruppati.items()
        ]
    else:
        ingredienti = ricetta.get("ingredienti_dettaglio", [])

    if not ingredienti:
        raise HTTPException(422, "Ricetta senza ingredienti dettaglio")

    db_usda = _carica_usda()
    campi = ["kcal", "kj", "grassi", "saturi", "carboidrati", "zuccheri", "fibre", "proteine", "sale"]

    # Calcola peso totale usato (g) - solo ingredienti con unita peso
    UNITA_PESO = {"g", "gr", "kg", "ml", "cl", "dl", "l", "lt", "litri", "grammi", "chili"}

    peso_totale_g = 0.0
    contributi = []  # lista di (nome, gram_g, voce_usda | None)
    non_trovati = []

    for ing in ingredienti:
        nome = ing.get("nome_ingrediente") or ing.get("nome") or ""
        qt = float(ing.get("quantita", 0) or 0)
        unita = str(ing.get("unita_misura") or ing.get("unita", "g") or "g").lower().strip()

        # Converte in grammi
        if unita in ("kg", "chili"):
            gram_g = qt * 1000
        elif unita in ("l", "lt", "litri"):
            gram_g = qt * 1000
        elif unita in ("dl",):
            gram_g = qt * 100
        elif unita in ("cl",):
            gram_g = qt * 10
        elif unita in ("ml",):
            gram_g = qt
        elif unita in ("g", "gr", "grammi"):
            gram_g = qt
        else:
            # unità non peso (pz, n., cucchiai ecc.) – escludi dal calcolo nutrizionale
            non_trovati.append(f"{nome} ({unita})")
            continue

        peso_totale_g += gram_g
        voce = _trova_voce_usda(nome, db_usda)
        if voce:
            contributi.append((nome, gram_g, voce))
        else:
            contributi.append((nome, gram_g, None))
            non_trovati.append(nome)

    if peso_totale_g == 0:
        raise HTTPException(422, "Nessun ingrediente con unità di peso (g/kg/ml/l)")

    # Calcola valori per 100g di prodotto finito
    totali = {c: 0.0 for c in campi}
    ingredienti_mappati = 0

    for nome, gram_g, voce in contributi:
        if voce is None:
            continue
        ingredienti_mappati += 1
        fattore = gram_g / peso_totale_g  # contributo relativo
        for campo in campi:
            totali[campo] += fattore * voce["per_100g"].get(campo, 0.0)

    # Arrotondamento
    valori = {c: round(totali[c], 1) for c in campi}

    # Copertura %
    totale_ing_peso = len(contributi)
    copertura = round((ingredienti_mappati / totale_ing_peso * 100) if totale_ing_peso > 0 else 0, 1)

    # Salva in DB
    await db.ricette.update_one(
        {"id": ricetta_id},
        {"$set": {"nutrizionale": valori}}
    )

    return {
        "ricetta_id": ricetta_id,
        "valori_nutrizionali": valori,
        "copertura_percentuale": copertura,
        "ingredienti_non_trovati": non_trovati,
        "peso_totale_g": round(peso_totale_g, 1),
        "ingredienti_analizzati": totale_ing_peso,
        "ingredienti_mappati": ingredienti_mappati
    }


@router.get("/nutrizionale/{ricetta_id}")
async def get_nutrizionale_ricetta(ricetta_id: str):
    """Restituisce i valori nutrizionali salvati per una ricetta."""
    ricetta = await db.ricette.find_one({"id": ricetta_id}, {"_id": 0, "nutrizionale": 1, "nome": 1})
    if not ricetta:
        raise HTTPException(404, "Ricetta non trovata")
    return {
        "ricetta_id": ricetta_id,
        "nome": ricetta.get("nome", ""),
        "valori_nutrizionali": ricetta.get("nutrizionale", {})
    }


@router.get("/storico-prezzi")
async def get_storico_prezzi(nome: str, limit: int = 6):
    """
    Storico ultimi N prezzi per un ingrediente, estratto da lotti_fornitori.
    Restituisce lista ordinata per data con prezzo_kg, data_fattura, fornitore.
    """
    query = {
        "$or": [
            {"prodotto_nome_norm": {"$regex": re.escape(nome.lower().strip()), "$options": "i"}},
            {"prodotto_nome": {"$regex": re.escape(nome.strip()), "$options": "i"}},
        ],
        "prezzo_unitario": {"$gt": 0},
        "data_fattura": {"$exists": True, "$ne": None, "$ne": ""},
    }
    cursor = db.lotti_fornitori.find(query, {"_id": 0, "prezzo_unitario": 1, "data_fattura": 1, "fornitore": 1, "unita_misura": 1, "prodotto_nome": 1})
    docs = await cursor.to_list(100)
    # Filtra e ordina per data
    voci = []
    for d in docs:
        data_str = d.get("data_fattura", "")
        if not data_str:
            continue
        try:
            if "/" in str(data_str):
                parts = str(data_str).split("/")
                if len(parts) == 3:
                    data_str = f"{parts[2]}-{parts[1]}-{parts[0]}"
            dt = datetime.fromisoformat(str(data_str)[:10])
        except Exception:
            continue
        voci.append({
            "data": dt.isoformat()[:10],
            "prezzo": round(float(d.get("prezzo_unitario", 0)), 4),
            "fornitore": d.get("fornitore", ""),
        })
    voci.sort(key=lambda x: x["data"])
    # Dedup: tieni solo l'ultimo per giorno/fornitore
    seen = set()
    unici = []
    for v in reversed(voci):
        k = (v["data"], v["fornitore"])
        if k not in seen:
            seen.add(k)
            unici.append(v)
    unici.reverse()
    return {"nome": nome, "storico": unici[-limit:]}

