"""
Handler Eventi Magazzino — Gestionale Ceraldi Group
=====================================================
Copre le specifiche di Magazzino_Acquisti_Prodotti.txt:
- Matching prodotto 3 livelli (esatto → normalizzato → fuzzy)
- Normalizzazione nomi prodotto
- Auto-creazione prodotto se non trovato
- Alert sotto scorta, prodotto incompleto, duplicato
- Aggiornamento dizionario prodotti (auto-learning)
- Aggiornamento giacenze da fatture merce
"""
import logging
import re
import uuid
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


async def on_fattura_righe_magazzino(event: Dict[str, Any], db) -> Optional[Dict]:
    """
    Quando una fattura con righe merce viene importata, per ogni riga:
    1. Tenta match con prodotto esistente (3 livelli)
    2. Se trovato → aggiorna storico + giacenza
    3. Se non trovato → crea prodotto + alert incompleto
    4. Aggiorna dizionario prodotti
    """
    fattura_id = event.get("fattura_id")
    fornitore_id = event.get("fornitore_id")
    fornitore_nome = event.get("fornitore_ragione_sociale", "")
    righe = event.get("righe", [])

    if not righe:
        return None

    risultati = {"risolte": 0, "create": 0, "dubbie": 0, "servizi": 0}

    for riga in righe:
        desc = riga.get("descrizione", "")
        qta = riga.get("quantita", 0)
        prezzo = riga.get("prezzo_unitario", 0)
        udm = riga.get("unita_misura", "")

        if not desc:
            continue

        # Classificazione: merce o servizio?
        if _is_servizio(desc):
            risultati["servizi"] += 1
            continue

        # --- MATCHING 3 LIVELLI ---
        match = await _cerca_prodotto_3_livelli(desc, fornitore_id, db)

        if match["trovato"] and match["certezza"] == "certo":
            # Aggiorna storico acquisti + giacenza
            await _aggiorna_prodotto_esistente(
                match["prodotto_id"], qta, prezzo, udm, fattura_id, fornitore_id, db
            )
            # Aggiorna dizionario con eventuale nuovo alias
            await _aggiorna_dizionario(desc, match["prodotto_id"], match["nome_canonico"], fornitore_id, db)
            risultati["risolte"] += 1

        elif match["trovato"] and match["certezza"] == "probabile":
            # Alert match dubbio
            from app.services.alert_engine import genera_alert
            await genera_alert(
                "MAG_MATCH_DUBBIO", fattura_id, "invoices",
                f"Riga '{desc[:50]}' → prodotto '{match.get('nome_canonico', '')}' (match probabile)",
                db, extra={"riga_desc": desc, "prodotto_id": match["prodotto_id"]}
            )
            risultati["dubbie"] += 1

        else:
            # Crea nuovo prodotto
            nuovo_id = await _crea_prodotto_nuovo(desc, qta, prezzo, udm, fornitore_id, fornitore_nome, db)
            risultati["create"] += 1

    # Audit
    from app.services.audit_logger import log_evento
    await log_evento(
        modulo="magazzino", azione="righe_processate", entita_id=fattura_id,
        entita_collection="invoices", db=db,
        nuovo_stato=risultati,
        fonte="fattura_import",
        dettaglio=f"{len(righe)} righe: {risultati['risolte']} risolte, {risultati['create']} nuove, {risultati['dubbie']} dubbie, {risultati['servizi']} servizi"
    )

    return {"action": "magazzino_processato", "risultati": risultati}


async def on_verifica_sotto_scorta(event: Dict[str, Any], db) -> Optional[Dict]:
    """
    Verifica periodica: genera alert MAG_SOTTO_SCORTA per prodotti
    con giacenza ≤ giacenza minima.
    """
    from app.services.alert_engine import genera_alert, risolvi_alert

    cursor = db["warehouse_inventory"].find(
        {
            "giacenza_minima": {"$exists": True, "$gt": 0},
            "attivo": {"$ne": False}
        },
        {"_id": 0, "id": 1, "nome": 1, "giacenza": 1, "giacenza_minima": 1}
    )

    sotto_scorta = 0
    ripristinati = 0
    async for prod in cursor:
        giacenza = prod.get("giacenza", 0) or 0
        minima = prod.get("giacenza_minima", 0) or 0
        prod_id = prod.get("id", "")

        if giacenza <= minima:
            await genera_alert(
                "MAG_SOTTO_SCORTA", prod_id, "warehouse_inventory",
                f"Prodotto '{prod.get('nome', '')}': giacenza {giacenza} ≤ minimo {minima}",
                db
            )
            sotto_scorta += 1
        else:
            # Se era sotto scorta e ora è ok → risolvi
            r = await risolvi_alert("MAG_SOTTO_SCORTA", prod_id, db)
            if r > 0:
                ripristinati += 1

    return {"action": "sotto_scorta_verificato", "sotto_scorta": sotto_scorta, "ripristinati": ripristinati}


# ============================================================
# FUNZIONI INTERNE
# ============================================================

async def _cerca_prodotto_3_livelli(descrizione: str, fornitore_id: str, db) -> Dict:
    """Matching prodotto su 3 livelli: esatto → normalizzato → fuzzy."""

    # LIVELLO 1: match esatto per codice o nome
    existing = await db["warehouse_inventory"].find_one(
        {"$or": [
            {"nome": descrizione},
            {"codice_articolo_fornitore": descrizione},
        ]},
        {"_id": 0, "id": 1, "nome": 1}
    )
    if existing:
        return {"trovato": True, "certezza": "certo", "prodotto_id": existing["id"], "nome_canonico": existing.get("nome", "")}

    # LIVELLO 2: nome normalizzato
    norm = _normalizza_nome_prodotto(descrizione)
    if len(norm) >= 5:
        existing = await db["warehouse_inventory"].find_one(
            {"nome_normalizzato": norm},
            {"_id": 0, "id": 1, "nome": 1}
        )
        if existing:
            return {"trovato": True, "certezza": "certo", "prodotto_id": existing["id"], "nome_canonico": existing.get("nome", "")}

    # Cerca nel dizionario prodotti (alias)
    alias = await db["dizionario_prodotti"].find_one(
        {"$or": [
            {"alias": descrizione},
            {"alias": norm},
            {"nomi_visti_fattura": descrizione},
        ]},
        {"_id": 0, "prodotto_id": 1, "nome_canonico": 1}
    )
    if alias:
        return {"trovato": True, "certezza": "certo", "prodotto_id": alias["prodotto_id"], "nome_canonico": alias.get("nome_canonico", "")}

    # LIVELLO 3: fuzzy (prima 10 caratteri della normalizzazione)
    if len(norm) >= 8:
        prefix = norm[:10]
        candidates = await db["warehouse_inventory"].find(
            {"nome_normalizzato": {"$regex": f"^{re.escape(prefix)}", "$options": "i"}},
            {"_id": 0, "id": 1, "nome": 1, "nome_normalizzato": 1}
        ).limit(3).to_list(3)

        if len(candidates) == 1:
            return {"trovato": True, "certezza": "probabile", "prodotto_id": candidates[0]["id"], "nome_canonico": candidates[0].get("nome", "")}
        elif len(candidates) > 1:
            return {"trovato": True, "certezza": "probabile", "prodotto_id": candidates[0]["id"], "nome_canonico": candidates[0].get("nome", "")}

    return {"trovato": False, "certezza": ""}


def _normalizza_nome_prodotto(testo: str) -> str:
    """Normalizza nome prodotto: minuscolo, senza punteggiatura, unità separate."""
    if not testo:
        return ""
    t = testo.lower().strip()
    t = re.sub(r'[^\w\s]', ' ', t)
    t = re.sub(r'\b(gr|kg|lt|ml|pz|ct|cf)\b\.?', lambda m: m.group(1), t)
    t = re.sub(r'(\d+)\s*(gr|g|kg|lt|l|ml|pz|ct|cf)\b', r'\1 \2', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def _is_servizio(descrizione: str) -> bool:
    """Euristica: la riga è un servizio/costo, non merce."""
    desc = (descrizione or "").upper()
    keywords = ["TRASPORTO", "CONSEGNA", "SERVIZIO", "CANONE", "NOLEGGIO",
                "CONSULENZA", "MANUTENZIONE", "PULIZIA", "AFFITTO", "CONTRIBUTO",
                "COMMISSIONE", "ASSICURAZIONE", "ABBONAMENTO"]
    return any(kw in desc for kw in keywords)


async def _aggiorna_prodotto_esistente(prod_id, qta, prezzo, udm, fattura_id, fornitore_id, db):
    """Aggiorna giacenza e storico acquisti di un prodotto esistente."""
    update = {
        "ultimo_acquisto_data": datetime.now(timezone.utc).isoformat(),
        "ultimo_acquisto_fattura_id": fattura_id,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    if prezzo and prezzo > 0:
        update["ultimo_prezzo"] = prezzo
    if fornitore_id:
        update["ultimo_fornitore_id"] = fornitore_id

    inc = {}
    if qta and qta > 0:
        inc["giacenza"] = qta

    update_query = {"$set": update}
    if inc:
        update_query["$inc"] = inc

    await db["warehouse_inventory"].update_one({"id": prod_id}, update_query)

    # Salva in storico acquisti
    await db["acquisti_prodotti"].insert_one({
        "id": str(uuid.uuid4()),
        "prodotto_id": prod_id,
        "fattura_id": fattura_id,
        "fornitore_id": fornitore_id,
        "quantita": qta,
        "prezzo_unitario": prezzo,
        "unita_misura": udm,
        "data": datetime.now(timezone.utc).isoformat(),
    })


async def _crea_prodotto_nuovo(desc, qta, prezzo, udm, fornitore_id, fornitore_nome, db) -> str:
    """Crea un nuovo prodotto e genera alert di configurazione incompleta."""
    prod_id = str(uuid.uuid4())
    norm = _normalizza_nome_prodotto(desc)

    await db["warehouse_inventory"].insert_one({
        "id": prod_id,
        "nome": desc,
        "nome_normalizzato": norm,
        "giacenza": qta or 0,
        "giacenza_minima": None,
        "ultimo_prezzo": prezzo,
        "unita_misura": udm,
        "fornitore_principale_id": fornitore_id,
        "fornitore_principale_nome": fornitore_nome,
        "attivo": True,
        "categoria": None,
        "configurato": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    # Alert prodotto incompleto
    from app.services.alert_engine import genera_alert
    await genera_alert(
        "MAG_PRODOTTO_INCOMPLETO", prod_id, "warehouse_inventory",
        f"Nuovo prodotto '{desc[:50]}' creato da fattura. "
        f"Mancano giacenza minima e categoria.",
        db
    )

    # Aggiorna dizionario
    await _aggiorna_dizionario(desc, prod_id, desc, fornitore_id, db)

    return prod_id


async def _aggiorna_dizionario(desc_fattura, prodotto_id, nome_canonico, fornitore_id, db):
    """Aggiorna il dizionario prodotti con il nome visto in fattura."""
    await db["dizionario_prodotti"].update_one(
        {"prodotto_id": prodotto_id},
        {
            "$set": {
                "nome_canonico": nome_canonico,
                "prodotto_id": prodotto_id,
                "updated_at": datetime.now(timezone.utc).isoformat()
            },
            "$addToSet": {
                "nomi_visti_fattura": desc_fattura,
                "fornitori": fornitore_id
            }
        },
        upsert=True
    )
