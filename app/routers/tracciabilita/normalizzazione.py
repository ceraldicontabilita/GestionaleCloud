"""
Router per normalizzazione intelligente dei nomi prodotto.
Usa AI per classificare descrizioni fattura → nome canonico + categoria.
Il mapping viene salvato in MongoDB (collezione `nome_mapping`) e riutilizzato.
Nuove fatture vengono processate solo per i prodotti ancora sconosciuti.
"""

import os
import re
import uuid
import asyncio
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter
from app.routers.tracciabilita.server import db


router = APIRouter(prefix="/normalizzazione", tags=["Normalizzazione"])


EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")

# ─── Mappa statica rapida (senza AI) ─────────────────────────────────────────
SINONIMI_STATICI: dict[str, dict] = {
    # Oli
    "olio extravergine oliva": {"nome_canc": "Olio Extravergine di Oliva", "categoria": "Condimenti"},
    "olio evo": {"nome_canc": "Olio Extravergine di Oliva", "categoria": "Condimenti"},
    "olio extra vergine": {"nome_canc": "Olio Extravergine di Oliva", "categoria": "Condimenti"},
    "olio di oliva": {"nome_canc": "Olio di Oliva", "categoria": "Condimenti"},
    "olio di semi": {"nome_canc": "Olio di Semi", "categoria": "Condimenti"},
    # Farine
    "farina 00": {"nome_canc": "Farina 00", "categoria": "Farine e Cereali"},
    "farina 0": {"nome_canc": "Farina 0", "categoria": "Farine e Cereali"},
    "farina tipo 1": {"nome_canc": "Farina Tipo 1", "categoria": "Farine e Cereali"},
    "farina di grano": {"nome_canc": "Farina di Grano", "categoria": "Farine e Cereali"},
    "semola": {"nome_canc": "Semola", "categoria": "Farine e Cereali"},
    # Zuccheri
    "zucchero semolato": {"nome_canc": "Zucchero Semolato", "categoria": "Dolcificanti"},
    "zucchero bianco": {"nome_canc": "Zucchero Semolato", "categoria": "Dolcificanti"},
    "zucchero a velo": {"nome_canc": "Zucchero a Velo", "categoria": "Dolcificanti"},
    "zucchero impalpabile": {"nome_canc": "Zucchero a Velo", "categoria": "Dolcificanti"},
    "zucchero di canna": {"nome_canc": "Zucchero di Canna", "categoria": "Dolcificanti"},
    # Grassi
    "burro": {"nome_canc": "Burro", "categoria": "Latticini e Grassi"},
    "strutto": {"nome_canc": "Strutto", "categoria": "Latticini e Grassi"},
    "margarina": {"nome_canc": "Margarina", "categoria": "Latticini e Grassi"},
    # Uova
    "uova fresche": {"nome_canc": "Uova Fresche", "categoria": "Uova"},
    "uova": {"nome_canc": "Uova", "categoria": "Uova"},
    "tuorlo": {"nome_canc": "Tuorlo d'Uovo", "categoria": "Uova"},
    "albume": {"nome_canc": "Albume d'Uovo", "categoria": "Uova"},
    # Latticini
    "latte": {"nome_canc": "Latte Fresco", "categoria": "Latticini e Grassi"},
    "panna fresca": {"nome_canc": "Panna Fresca", "categoria": "Latticini e Grassi"},
    "panna": {"nome_canc": "Panna", "categoria": "Latticini e Grassi"},
    "ricotta": {"nome_canc": "Ricotta", "categoria": "Formaggi"},
    "mozzarella": {"nome_canc": "Mozzarella", "categoria": "Formaggi"},
    "fior di latte": {"nome_canc": "Fior di Latte", "categoria": "Formaggi"},
    "fiordilatte": {"nome_canc": "Fior di Latte", "categoria": "Formaggi"},
    "provola": {"nome_canc": "Provola", "categoria": "Formaggi"},
    # Lieviti e addensanti
    "lievito di birra": {"nome_canc": "Lievito di Birra", "categoria": "Lieviti e Addensanti"},
    "lievito per dolci": {"nome_canc": "Lievito per Dolci", "categoria": "Lieviti e Addensanti"},
    "lievito": {"nome_canc": "Lievito", "categoria": "Lieviti e Addensanti"},
    # Frutta e verdura
    "pomodori": {"nome_canc": "Pomodori", "categoria": "Frutta e Verdura"},
    "pomodori pelati": {"nome_canc": "Pomodori Pelati", "categoria": "Conserve e Condimenti"},
    "passata di pomodoro": {"nome_canc": "Passata di Pomodoro", "categoria": "Conserve e Condimenti"},
    "arance": {"nome_canc": "Arance", "categoria": "Frutta e Verdura"},
    "limoni": {"nome_canc": "Limoni", "categoria": "Frutta e Verdura"},
    "mele": {"nome_canc": "Mele", "categoria": "Frutta e Verdura"},
    "fragole": {"nome_canc": "Fragole", "categoria": "Frutta e Verdura"},
    # Cioccolato e cacao
    "cacao": {"nome_canc": "Cacao in Polvere", "categoria": "Cioccolato e Cacao"},
    "cioccolato fondente": {"nome_canc": "Cioccolato Fondente", "categoria": "Cioccolato e Cacao"},
    "cioccolato al latte": {"nome_canc": "Cioccolato al Latte", "categoria": "Cioccolato e Cacao"},
    "pasta di cacao": {"nome_canc": "Pasta di Cacao", "categoria": "Cioccolato e Cacao"},
    # Pasta e cereali
    "pasta di mandorle": {"nome_canc": "Pasta di Mandorle", "categoria": "Semilavorati Pasticceria"},
    "pan di spagna": {"nome_canc": "Pan di Spagna", "categoria": "Semilavorati Pasticceria"},
    "crema pasticciera": {"nome_canc": "Crema Pasticciera", "categoria": "Semilavorati Pasticceria"},
    # Bevande
    "rum": {"nome_canc": "Rum", "categoria": "Alcolici e Liquori"},
    "limoncello": {"nome_canc": "Limoncello", "categoria": "Alcolici e Liquori"},
}


def cerca_in_sinonimi_statici(descrizione: str) -> Optional[dict]:
    """Cerca un match nei sinonimi statici. Ritorna None se non trovato."""
    desc = descrizione.lower().strip()
    # Rimuovi peso e codici dalla descrizione
    desc_clean = re.sub(r'\b\d+[\.,]?\d*\s*(kg|g|gr|ml|lt|l|pz|cl)?\b', '', desc).strip()
    desc_clean = re.sub(r'\b[A-Z0-9]{4,}\b', '', desc_clean).strip()  # codici prodotto
    desc_clean = re.sub(r'\s+', ' ', desc_clean).strip()

    # Match esatto
    if desc_clean in SINONIMI_STATICI:
        return SINONIMI_STATICI[desc_clean]

    # Match parziale (la chiave è contenuta nella descrizione o viceversa)
    for chiave, valore in sorted(SINONIMI_STATICI.items(), key=lambda x: -len(x[0])):
        if chiave in desc_clean or desc_clean.startswith(chiave[:10]):
            return valore

    return None


async def normalizza_batch_con_ai(descrizioni: list) -> dict:
    """
    Classifica fino a 20 descrizioni in una sola chiamata AI.
    Ritorna {descrizione: {"nome_canc": str, "categoria": str}} per quelle classificate.
    """
    if not EMERGENT_LLM_KEY or not descrizioni:
        return {}

    batch = descrizioni[:20]
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        import json as _json

        lista = "\n".join(f"{i+1}. {d}" for i, d in enumerate(batch))
        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"norm-batch-{uuid.uuid4()}",
            system_message=(
                "Sei un esperto di prodotti alimentari per ristorazione italiana. "
                "Dato un elenco numerato di descrizioni da fatture fornitore, "
                "rispondi SOLO con un JSON array, uno oggetto per riga: "
                "[{\"i\":1,\"nome_canc\":\"Nome Breve\",\"categoria\":\"Categoria\"}, ...] "
                "Nessuna spiegazione. Il nome canonico: breve (2-4 parole), in italiano. "
                "Categorie valide: Farine e Cereali, Dolcificanti, Latticini e Grassi, "
                "Uova, Formaggi, Frutta e Verdura, Conserve e Condimenti, Cioccolato e Cacao, "
                "Lieviti e Addensanti, Semilavorati Pasticceria, Alcolici e Liquori, "
                "Carni e Salumi, Pesce, Condimenti, Bevande, Varie Alimentari, Non Alimentare."
            )
        ).with_model("anthropic", "claude-haiku-4-5")

        msg = UserMessage(text=f"Classifica questi {len(batch)} prodotti:\n{lista}")
        risposta = await chat.send_message(msg)

        # Parse JSON array dalla risposta
        match = re.search(r'\[.*\]', risposta, re.DOTALL)
        if not match:
            return {}
        items = _json.loads(match.group())
        result = {}
        for item in items:
            idx = int(item.get("i", 0)) - 1
            if 0 <= idx < len(batch) and item.get("nome_canc") and item.get("categoria"):
                result[batch[idx]] = {"nome_canc": item["nome_canc"], "categoria": item["categoria"]}
        return result
    except Exception:
        return {}


async def normalizza_con_ai(descrizione: str) -> Optional[dict]:
    """
    Chiama l'AI per classificare una descrizione fattura.
    Ritorna {"nome_canc": str, "categoria": str} o None se fallisce.
    """
    if not EMERGENT_LLM_KEY:
        return None

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage

        chat = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"norm-{uuid.uuid4()}",
            system_message=(
                "Sei un esperto di prodotti alimentari per la ristorazione italiana. "
                "Dato una descrizione di un prodotto da una fattura fornitore, rispondi SOLO con un JSON "
                "nel formato: {\"nome_canc\": \"Nome Canonico Italiano\", \"categoria\": \"Categoria\"} "
                "senza spiegazioni. Il nome canonico deve essere breve (2-4 parole), in italiano, "
                "nel formato corretto (es. 'Olio Extravergine di Oliva', 'Farina 00', 'Zucchero Semolato'). "
                "La categoria deve essere una di: Farine e Cereali, Dolcificanti, Latticini e Grassi, "
                "Uova, Formaggi, Frutta e Verdura, Conserve e Condimenti, Cioccolato e Cacao, "
                "Lieviti e Addensanti, Semilavorati Pasticceria, Alcolici e Liquori, "
                "Carni e Salumi, Pesce, Condimenti, Bevande, Varie Alimentari, Non Alimentare."
            )
        ).with_model("anthropic", "claude-haiku-4-5")

        msg = UserMessage(text=f"Classifica questo prodotto da fattura: '{descrizione}'")
        risposta = await chat.send_message(msg)

        # Parse JSON dalla risposta
        match = re.search(r'\{[^}]+\}', risposta)
        if match:
            import json
            data = json.loads(match.group())
            if "nome_canc" in data and "categoria" in data:
                return data
    except Exception:
        pass

    return None


async def get_o_crea_mapping(descrizione: str) -> dict:
    """
    Cerca o crea un mapping per la descrizione.
    Priorità: DB → Sinonimi statici → AI
    """
    desc_key = descrizione.lower().strip()[:200]

    # 1. Cerca nel DB
    esistente = await db.nome_mapping.find_one({"descrizione_key": desc_key}, {"_id": 0})
    if esistente:
        return esistente

    # 2. Cerca nei sinonimi statici
    mapping_statico = cerca_in_sinonimi_statici(descrizione)
    if mapping_statico:
        doc = {
            "descrizione_originale": descrizione,
            "descrizione_key": desc_key,
            "nome_canc": mapping_statico["nome_canc"],
            "categoria": mapping_statico["categoria"],
            "fonte": "statico",
            "creato_at": datetime.now(timezone.utc).isoformat()
        }
        await db.nome_mapping.update_one(
            {"descrizione_key": desc_key},
            {"$set": doc},
            upsert=True
        )
        # MODIFICA 5: Propaga nome_canonico al dizionario_prodotti
        if doc.get("nome_canc"):
            try:
                await db.dizionario_prodotti.update_many(
                    {"nome_normalizzato": {"$regex": re.escape(desc_key[:15]), "$options": "i"},
                     "nome_canonico": {"$exists": False}},
                    {"$set": {"nome_canonico": doc["nome_canc"]}}
                )
            except Exception:
                pass
        return doc

    # 3. AI (solo se key disponibile)
    mapping_ai = await normalizza_con_ai(descrizione)
    if mapping_ai:
        doc = {
            "descrizione_originale": descrizione,
            "descrizione_key": desc_key,
            "nome_canc": mapping_ai["nome_canc"],
            "categoria": mapping_ai["categoria"],
            "fonte": "ai",
            "creato_at": datetime.now(timezone.utc).isoformat()
        }
        await db.nome_mapping.update_one(
            {"descrizione_key": desc_key},
            {"$set": doc},
            upsert=True
        )
        # MODIFICA 5: Propaga nome_canonico al dizionario_prodotti
        if doc.get("nome_canc"):
            try:
                await db.dizionario_prodotti.update_many(
                    {"nome_normalizzato": {"$regex": re.escape(desc_key[:15]), "$options": "i"},
                     "nome_canonico": {"$exists": False}},
                    {"$set": {"nome_canonico": doc["nome_canc"]}}
                )
            except Exception:
                pass
        return doc

    return {}


@router.post("/processa-nuovi-prodotti")
async def processa_nuovi_prodotti(limit: int = 50):
    """
    Normalizza i prodotti del dizionario che non hanno ancora un nome canonico.
    Processa solo i NUOVI (non ancora presenti nel nome_mapping).
    """
    # Prendi tutti i prodotti del dizionario
    prodotti = await db.dizionario_prodotti.find(
        {},
        {"_id": 0, "nome_originale": 1, "nome_normalizzato": 1, "fornitore": 1, "prezzo_kg": 1}
    ).to_list(10000)

    # Prendi i mapping già esistenti
    mapping_esistenti_keys = set()
    async for m in db.nome_mapping.find({}, {"descrizione_key": 1, "_id": 0}):
        mapping_esistenti_keys.add(m["descrizione_key"])

    nuovi = [p for p in prodotti if p.get("nome_originale", "").lower()[:200] not in mapping_esistenti_keys]
    nuovi = nuovi[:limit]

    processati = 0
    statici = 0
    ai = 0
    errori = 0

    if nuovi:
        # ── Batch AI: una sola chiamata per tutti i nuovi ──────────────
        desc_list = [p.get("nome_originale", p.get("nome_normalizzato", "")) for p in nuovi if p.get("nome_originale") or p.get("nome_normalizzato")]
        batch_results = await normalizza_batch_con_ai(desc_list)

        for prod in nuovi:
            desc = prod.get("nome_originale", prod.get("nome_normalizzato", ""))
            if not desc:
                continue
            desc_key = desc.lower().strip()[:200]
            try:
                mapping_statico = cerca_in_sinonimi_statici(desc)
                if mapping_statico:
                    doc = {
                        "descrizione_originale": desc,
                        "descrizione_key": desc_key,
                        "nome_canc": mapping_statico["nome_canc"],
                        "categoria": mapping_statico["categoria"],
                        "fonte": "statico",
                        "creato_at": datetime.now(timezone.utc).isoformat()
                    }
                    await db.nome_mapping.update_one({"descrizione_key": desc_key}, {"$set": doc}, upsert=True)
                    statici += 1
                    processati += 1
                elif desc in batch_results:
                    br = batch_results[desc]
                    doc = {
                        "descrizione_originale": desc,
                        "descrizione_key": desc_key,
                        "nome_canc": br["nome_canc"],
                        "categoria": br["categoria"],
                        "fonte": "ai",
                        "creato_at": datetime.now(timezone.utc).isoformat()
                    }
                    await db.nome_mapping.update_one({"descrizione_key": desc_key}, {"$set": doc}, upsert=True)
                    ai += 1
                    processati += 1
                else:
                    errori += 1
            except Exception:
                errori += 1

    # Aggiorna nome_canonico nel dizionario SOLO per i mapping appena creati
    aggiornati_diz = 0
    nuovi_desc_keys = [
        p.get("nome_originale", p.get("nome_normalizzato", "")).lower().strip()[:200]
        for p in nuovi if p.get("nome_originale") or p.get("nome_normalizzato")
    ]
    if nuovi_desc_keys:
        async for m in db.nome_mapping.find(
            {"descrizione_key": {"$in": nuovi_desc_keys}, "nome_canc": {"$exists": True}},
            {"_id": 0, "descrizione_key": 1, "nome_canc": 1, "categoria": 1}
        ):
            nome_canc = m.get("nome_canc")
            desc_key = m.get("descrizione_key", "")
            if nome_canc and desc_key:
                res = await db.dizionario_prodotti.update_many(
                    {"nome_originale": {"$regex": f"^{re.escape(desc_key[:30])}", "$options": "i"}},
                    {"$set": {"nome_canonico": nome_canc, "categoria_canonica": m.get("categoria", "")}}
                )
                aggiornati_diz += res.modified_count

    return {
        "processati": processati,
        "via_sinonimi_statici": statici,
        "via_ai": ai,
        "errori": errori,
        "nuovi_trovati": len(nuovi),
        "aggiornati_dizionario": aggiornati_diz
    }


@router.post("/processa-tutti-aliases")
async def processa_tutti_aliases(limit: int = 200):
    """
    One-shot: per ogni voce dizionario_prodotti, cerca il mapping in nome_mapping
    e propaga nome_canonico + popola aliases[] con nome_normalizzato come alias.
    Processa fino a `limit` voci per chiamata (chiamare più volte se necessario).
    """
    prodotti = await db.dizionario_prodotti.find(
        {"$or": [
            {"aliases": {"$exists": False}},
            {"aliases": {"$size": 0}}
        ]},
        {"_id": 0, "id": 1, "nome_normalizzato": 1, "nome_originale": 1, "nome_canonico": 1}
    ).limit(limit).to_list(limit)

    aggiornati = 0
    for p in prodotti:
        nome_norm = p.get("nome_normalizzato", "").strip()
        nome_orig = p.get("nome_originale", nome_norm).strip()

        mapping = await db.nome_mapping.find_one(
            {"$or": [
                {"descrizione_key": nome_norm[:200]},
                {"descrizione_key": nome_orig.lower()[:200]}
            ]},
            {"_id": 0, "nome_canc": 1}
        )

        alias_set = [nome_norm]
        if nome_orig.lower() != nome_norm:
            alias_set.append(nome_orig.lower())

        update: dict = {"$addToSet": {"aliases": {"$each": alias_set}}}
        if mapping and mapping.get("nome_canc"):
            update["$set"] = {"nome_canonico": mapping["nome_canc"]}

        try:
            await db.dizionario_prodotti.update_one({"id": p["id"]}, update)
            aggiornati += 1
        except Exception:
            pass

    rimanenti = await db.dizionario_prodotti.count_documents(
        {"nome_canonico": {"$exists": False}}
    )
    return {
        "processati": len(prodotti),
        "aggiornati": aggiornati,
        "rimanenti_senza_canonico": rimanenti
    }


@router.get("/mapping")
async def lista_mapping(skip: int = 0, limit: int = 100, fonte: str = ""):
    """Lista tutti i mapping salvati"""
    query = {}
    if fonte:
        query["fonte"] = fonte
    mapping = await db.nome_mapping.find(query, {"_id": 0}).skip(skip).limit(limit).to_list(limit)
    total = await db.nome_mapping.count_documents(query)
    return {"mapping": mapping, "total": total}


@router.get("/prodotti-senza-peso")
async def prodotti_senza_peso(limit: int = 200):
    """
    Prodotti nel dizionario senza peso confezione estratto (peso_confezione = 0 o assente).
    Questi hanno prezzo/kg potenzialmente approssimativo.
    """
    # Considera "senza peso" SOLO prodotti con:
    # - peso mancante
    # - peso ≤ 0.001 kg (praticamente zero, non un valore reale estratto)
    # - unita = "pz" (fallback esplicito senza peso estratto)
    # NON include monoporzioni legittime (es. 9g pesto = 0.009kg, 10g wurstel = 0.01kg)
    prodotti = await db.dizionario_prodotti.find(
        {
            "$or": [
                {"peso_confezione": {"$exists": False}},
                {"peso_confezione": {"$lte": 0.001}},
                {"unita_confezione": "pz"}
            ],
            "prezzo_kg": {"$gt": 0}
        },
        {"_id": 0, "nome_originale": 1, "nome_normalizzato": 1, "fornitore": 1,
         "prezzo_kg": 1, "unita_confezione": 1, "prezzo_confezione": 1}
    ).sort("fornitore", 1).limit(limit).to_list(limit)

    total = await db.dizionario_prodotti.count_documents(
        {"$or": [
            {"peso_confezione": {"$exists": False}},
            {"peso_confezione": {"$lte": 0.001}},
            {"unita_confezione": "pz"}
        ], "prezzo_kg": {"$gt": 0}}
    )

    return {"prodotti": prodotti, "total": total}


@router.post("/correggi-peso/{nome_normalizzato}")
async def correggi_peso_prodotto(nome_normalizzato: str, peso_kg: float, unita: str = "kg"):
    """Corregge manualmente il peso di un prodotto nel dizionario."""
    result = await db.dizionario_prodotti.update_many(
        {"nome_normalizzato": nome_normalizzato},
        {"$set": {
            "peso_confezione": peso_kg,
            "unita_confezione": unita,
            "peso_corretto_manualmente": True,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    return {"aggiornati": result.modified_count}


@router.post("/aggiungi-fornitore-speciale")
async def aggiungi_fornitore_speciale(fornitore: str, tipo: str = "prezzo_per_kg"):
    """
    Aggiunge un fornitore alla configurazione speciale salvata in MongoDB.
    tipo: 'prezzo_per_kg' = Qt=confezioni, Prezzo=€/kg
          'prezzo_per_confezione' = Qt=confezioni, Prezzo=€/confezione (standard)
    """
    doc = {
        "fornitore_lower": fornitore.lower().strip(),
        "fornitore_originale": fornitore.strip(),
        "tipo": tipo,
        "aggiunto_at": datetime.now(timezone.utc).isoformat()
    }
    await db.fornitori_config.update_one(
        {"fornitore_lower": doc["fornitore_lower"]},
        {"$set": doc},
        upsert=True
    )
    return {"success": True, "fornitore": fornitore, "tipo": tipo}


@router.get("/fornitori-config")
async def get_fornitori_config():
    """Lista fornitori con configurazione speciale"""
    config = await db.fornitori_config.find({}, {"_id": 0}).to_list(200)
    return config


@router.delete("/fornitori-config/{fornitore_lower}")
async def rimuovi_fornitore_config(fornitore_lower: str):
    """Rimuove un fornitore dalla configurazione speciale"""
    result = await db.fornitori_config.delete_one({"fornitore_lower": fornitore_lower})
    return {"eliminato": result.deleted_count > 0}
