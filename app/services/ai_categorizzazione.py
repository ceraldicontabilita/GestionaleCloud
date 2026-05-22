"""
Servizio AI per Categorizzazione Articoli - GPT-5.2

Usa LLM per:
1. Categorizzare articoli non classificati (confidenza 0)
2. Suggerire categoria HACCP e Piano dei Conti
3. Migliorare il pattern matching nel tempo
"""
import os
import logging
import json
from typing import Dict, Any, List
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Categorie HACCP disponibili per il prompt
CATEGORIE_HACCP_AI = {
    "carni_fresche": "Carne bovina, suina, avicola, ovina - rischio alto, 0-4°C",
    "pesce_fresco": "Pesce, molluschi, crostacei freschi - rischio alto, 0-2°C",
    "latticini": "Latte, formaggi, yogurt, panna, burro - rischio alto, 0-4°C",
    "uova": "Uova fresche, tuorli, albumi - rischio alto, 4-8°C",
    "frutta_verdura": "Ortaggi, frutta fresca, erbe aromatiche - rischio medio, 4-8°C",
    "surgelati": "Alimenti congelati e surgelati - rischio medio, ≤-18°C",
    "prodotti_forno": "Pane, dolci, cornetti, pasticceria fresca - rischio medio",
    "farine_cereali": "Farina, semola, cereali, riso, pasta secca - rischio basso",
    "conserve_scatolame": "Pomodori pelati, legumi, tonno, sottoli - rischio basso",
    "bevande_analcoliche": "Acqua, succhi, soft drink, the, caffè - rischio basso",
    "bevande_alcoliche": "Vino, birra, liquori, aperitivi - rischio basso",
    "spezie_condimenti": "Sale, olio, aceto, spezie, aromi - rischio basso",
    "salumi_insaccati": "Prosciutto, salame, mortadella, wurstel - rischio alto",
    "dolciumi_snack": "Cioccolato, caramelle, biscotti, snack - rischio basso",
    "additivi_ingredienti": "Lieviti, addensanti, coloranti, aromi - rischio basso",
    "non_alimentare": "Detersivi, imballaggi, attrezzature, servizi - N/A"
}

CONTI_PIANO_AI = {
    "05.01.01": "Acquisto merci (generico)",
    "05.01.02": "Acquisto materie prime (farine, grassi)",
    "05.01.03": "Acquisto bevande alcoliche",
    "05.01.04": "Acquisto bevande analcoliche",
    "05.01.05": "Acquisto prodotti alimentari",
    "05.01.06": "Acquisto piccola utensileria",
    "05.01.07": "Materiali di consumo e imballaggio",
    "05.01.08": "Prodotti per pulizia e igiene",
    "05.01.09": "Acquisto caffè e affini",
    "05.01.10": "Acquisto surgelati",
    "05.01.11": "Acquisto prodotti da forno",
    "05.01.13": "Additivi e ingredienti alimentari",
    "05.02.01": "Costi per servizi",
    "05.02.05": "Utenze - Energia elettrica",
    "05.02.07": "Telefonia e comunicazioni",
    "05.02.16": "Trasporti su acquisti",
    "05.02.18": "Commissioni bancarie e POS",
    "05.02.22": "Noleggio automezzi",
    "05.02.99": "Altri costi"
}


async def categorizza_articoli_con_ai(
    articoli: List[Dict[str, Any]],
    batch_size: int = 20
) -> List[Dict[str, Any]]:
    """
    Usa GPT-5.2 per categorizzare una lista di articoli.
    
    Args:
        articoli: Lista di dict con 'descrizione' e opzionalmente 'fornitore'
        batch_size: Numero di articoli per batch (per ottimizzare costi)
    
    Returns:
        Lista di categorizzazioni con categoria_haccp, conto, confidenza
    """
    try:
        from app.services.emergent_stub import LlmChat, UserMessage
    except ImportError:
        logger.error("emergentintegrations non installato")
        return []
    
    api_key = os.environ.get('EMERGENT_LLM_KEY')
    if not api_key:
        logger.error("EMERGENT_LLM_KEY non trovata")
        return []
    
    risultati = []
    
    # Processa in batch
    for i in range(0, len(articoli), batch_size):
        batch = articoli[i:i + batch_size]
        
        # Prepara lista descrizioni per il prompt
        descrizioni_text = "\n".join([
            f"{idx+1}. {art.get('descrizione', 'N/A')}" 
            for idx, art in enumerate(batch)
        ])
        
        system_message = f"""Sei un esperto di categorizzazione prodotti per un sistema ERP italiano di bar/pasticceria.
Devi categorizzare prodotti alimentari e non alimentari.

CATEGORIE HACCP DISPONIBILI:
{json.dumps(CATEGORIE_HACCP_AI, indent=2, ensure_ascii=False)}

CONTI PIANO DEI CONTI:
{json.dumps(CONTI_PIANO_AI, indent=2, ensure_ascii=False)}

REGOLE:
1. Analizza la descrizione del prodotto
2. Determina se è alimentare o non alimentare
3. Assegna la categoria HACCP più appropriata
4. Assegna il conto del piano dei conti più appropriato
5. Indica la confidenza (0.6-1.0) basata sulla chiarezza della descrizione

RISPONDI SEMPRE IN JSON VALIDO con questo formato:
[
  {{"indice": 1, "categoria_haccp": "...", "conto": "05.01.xx", "confidenza": 0.8, "ragione": "breve spiegazione"}},
  ...
]"""

        user_prompt = f"""Categorizza questi {len(batch)} prodotti:

{descrizioni_text}

Rispondi SOLO con il JSON array, nessun altro testo."""

        try:
            # Haiku: veloce ed economico per classificazione batch.
            # Sonnet aveva qualità leggermente superiore ma costa ~5x, e per
            # la classificazione dei conti un modello piccolo è sufficiente
            # (l'utente può sempre correggere manualmente la mappatura).
            chat = LlmChat(
                api_key=api_key,
                session_id=f"categorizzazione_{i}",
                system_message=system_message
            ).with_model("anthropic", "claude-haiku-4-5")
            
            response = await chat.send_message(UserMessage(text=user_prompt))
            
            # Parse risposta JSON
            response_text = response.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
            
            categorizzazioni = json.loads(response_text)
            
            # Mappa risultati agli articoli originali
            for cat in categorizzazioni:
                idx = cat.get("indice", 1) - 1
                if 0 <= idx < len(batch):
                    risultati.append({
                        "descrizione": batch[idx].get("descrizione"),
                        "categoria_haccp": cat.get("categoria_haccp", "non_alimentare"),
                        "conto": cat.get("conto", "05.01.01"),
                        "confidenza": cat.get("confidenza", 0.7),
                        "ragione_ai": cat.get("ragione", ""),
                        "categorizzato_da": "claude-sonnet-4.5"
                    })
            
            logger.info(f"Batch {i//batch_size + 1}: {len(categorizzazioni)} articoli categorizzati")
            
        except json.JSONDecodeError as e:
            logger.error(f"Errore parsing JSON risposta AI: {e}")
            continue
        except Exception as e:
            logger.error(f"Errore chiamata AI: {e}")
            continue
    
    return risultati


async def categorizza_singolo_articolo(descrizione: str, fornitore: str = None) -> Dict[str, Any]:
    """
    Categorizza un singolo articolo con AI.
    Utile per categorizzazione on-the-fly durante import.
    """
    risultati = await categorizza_articoli_con_ai([{
        "descrizione": descrizione,
        "fornitore": fornitore
    }], batch_size=1)
    
    if risultati:
        return risultati[0]
    
    return {
        "descrizione": descrizione,
        "categoria_haccp": "non_alimentare",
        "conto": "05.01.01",
        "confidenza": 0.0,
        "categorizzato_da": "fallback"
    }


async def aggiorna_dizionario_con_ai(db, limite: int = 100) -> Dict[str, Any]:
    """
    Trova articoli non classificati nel dizionario e li categorizza con AI.
    Aggiorna direttamente il database.
    
    Args:
        db: Database reference
        limite: Numero massimo di articoli da processare
    
    Returns:
        Statistiche dell'operazione
    """
    # Trova articoli con confidenza 0 (non classificati)
    articoli = await db.dizionario_articoli.find(
        {"confidenza": 0, "categorizzato_da": {"$ne": "gpt-5.2"}},
        {"descrizione": 1, "occorrenze": 1, "_id": 0}
    ).sort("occorrenze", -1).limit(limite).to_list(limite)
    
    if not articoli:
        return {"processed": 0, "updated": 0, "message": "Nessun articolo da categorizzare"}
    
    logger.info(f"Categorizzazione AI di {len(articoli)} articoli...")
    
    # Categorizza con AI
    risultati = await categorizza_articoli_con_ai(articoli)
    
    # Aggiorna database
    updated = 0
    for ris in risultati:
        if ris.get("confidenza", 0) > 0.5:  # Solo se AI è abbastanza sicuro
            await db.dizionario_articoli.update_one(
                {"descrizione": ris["descrizione"]},
                {"$set": {
                    "categoria_haccp": ris["categoria_haccp"],
                    "conto": ris["conto"],
                    "confidenza": ris["confidenza"],
                    "ragione_ai": ris.get("ragione_ai", ""),
                    "categorizzato_da": "claude-sonnet-4.5",
                    "ai_updated_at": __import__("datetime").datetime.now(timezone.utc).isoformat()
                }}
            )
            updated += 1
    
    return {
        "processed": len(articoli),
        "categorized": len(risultati),
        "updated": updated,
        "message": f"AI ha categorizzato {updated} articoli su {len(articoli)}"
    }
