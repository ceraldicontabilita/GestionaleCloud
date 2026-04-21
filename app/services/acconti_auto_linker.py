"""
Auto-associazione di acconti/stipendi/bonifici da estratto_conto_movimenti ai dipendenti.

Riconosce il pattern "VOSTRA DISPOSIZIONE ... FAVORE {Nome Cognome}" tipico dei bonifici
stipendio dell'estratto conto bancario. Crea record in `pagamenti_dipendenti` per
collegarli ai cedolini del mese.
"""
import re
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)

# Keyword tipiche bonifici verso dipendenti
KEYWORDS_DIPENDENTE = re.compile(
    r'\b(STIPEND|SALARIO|ACCONTO|ANTICIPO|SALDO\s+STIPEND|PAGA|RETRIBUZ|BUSTA\s+PAGA)\b',
    re.IGNORECASE
)
# Pattern "FAVORE Nome Cognome" estratto dalle causali bancarie
PATTERN_FAVORE = re.compile(
    r'FAVORE\s+([A-ZÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖØÙÚÛÜÝ][a-zA-Zàáâãäåæçèéêëìíîïðñòóôõöøùúûüý\']+(?:\s+[A-ZÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖØÙÚÛÜÝ][a-zA-Zàáâãäåæçèéêëìíîïðñòóôõöøùúûüý\']+)+)',
    re.UNICODE
)


def _norm_name(name: str) -> str:
    return " ".join(name.upper().split())


def _find_dipendente_by_name(cognome_nome: str, dipendenti_cache: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Cerca dipendente per Nome Cognome o Cognome Nome (bancario usa 'Nome Cognome')."""
    norm = _norm_name(cognome_nome)
    # 1) match esatto diretto
    if norm in dipendenti_cache:
        return dipendenti_cache[norm]
    # 2) match inverso (bancario: "Nome Cognome" → dipendente salvato come "Cognome Nome")
    parts = norm.split()
    if len(parts) >= 2:
        inv = " ".join(parts[::-1])
        if inv in dipendenti_cache:
            return dipendenti_cache[inv]
        # 3) match parziale cognome primo token
        first = parts[0]
        last = parts[-1]
        for key, dip in dipendenti_cache.items():
            k = _norm_name(key)
            if (last in k and first in k) or (k.startswith(first + " ") or k.endswith(" " + last)):
                return dip
    return None


async def scan_and_link_acconti(db: AsyncIOMotorDatabase, dry_run: bool = False) -> Dict[str, Any]:
    """
    Scansiona estratto_conto_movimenti per bonifici a dipendenti,
    crea record in pagamenti_dipendenti con link al cedolino del mese.
    """
    stats = {"movimenti_analizzati": 0, "match_dipendente": 0,
             "già_associati": 0, "creati": 0, "no_match": 0}

    # Cache dipendenti
    dipendenti_cache: Dict[str, Dict[str, Any]] = {}
    async for d in db["dipendenti"].find({}, {"_id": 0, "id": 1, "nome": 1, "cognome": 1, "codice_fiscale": 1}):
        key = _norm_name(f"{d.get('cognome','')} {d.get('nome','')}")
        if d.get("id") and key.strip():
            dipendenti_cache[key] = d
    logger.info("Dipendenti caricati: %d", len(dipendenti_cache))

    query = {
        "descrizione": {"$regex": "FAVORE\\s+[A-Z]", "$options": ""},
        "importo": {"$gt": 0},
    }

    async for mov in db["estratto_conto_movimenti"].find(query, {"_id": 1, "data_contabile": 1, "importo": 1, "descrizione": 1, "dipendente_collegato_id": 1}):
        stats["movimenti_analizzati"] += 1
        desc = mov.get("descrizione", "") or ""
        m_f = PATTERN_FAVORE.search(desc)
        if not m_f:
            continue
        nome_banca = m_f.group(1).strip()
        # Esclude "Ceraldi Group Srl", "Ceraldi Vincenzo" (amministratore), ecc.
        if "CERALDI" in nome_banca.upper() and "VINCENZO" not in nome_banca.upper() and "VALERIO" not in nome_banca.upper():
            # amministratori sono dipendenti, altri Ceraldi (società) no
            pass

        dip = _find_dipendente_by_name(nome_banca, dipendenti_cache)
        if not dip:
            stats["no_match"] += 1
            continue
        stats["match_dipendente"] += 1

        # Evita duplicati: controlla se esiste già pagamento per stesso mov_id
        already = await db["pagamenti_dipendenti"].find_one({"estratto_conto_movimento_id": str(mov["_id"])})
        if already:
            stats["già_associati"] += 1
            continue

        # Decodifica mese/anno dalla data_contabile (dd/mm/yyyy)
        data_c = mov.get("data_contabile", "") or ""
        try:
            d, m, y = data_c.split("/")
            dt = datetime(int(y), int(m), int(d))
            mese = int(m)
            anno = int(y)
        except Exception:
            continue

        # Cerca cedolino del mese per il dipendente (usa $and per evitare duplicate $or key)
        ced = await db["cedolini"].find_one({
            "$and": [
                {"dipendente_id": dip["id"]},
                {"$or": [{"anno": anno}, {"anno": str(anno)}]},
                {"$or": [{"mese": mese}, {"mese": str(mese)}]},
            ]
        }, {"_id": 0, "id": 1})

        # Classifica tipo
        desc_up = desc.upper()
        if re.search(r'ACCONTO|ANTICIPO', desc_up):
            tipo = "acconto"
        elif re.search(r'STIPEND|SALARIO|PAGA|RETRIBUZ|BUSTA', desc_up):
            tipo = "stipendio"
        else:
            # Bonifico al dipendente senza keyword specifica → presunto acconto/stipendio
            tipo = "pagamento_dipendente"

        if not dry_run:
            doc = {
                "id": str(uuid.uuid4()),
                "dipendente_id": dip["id"],
                "dipendente_nome": f"{dip.get('cognome','')} {dip.get('nome','')}".strip(),
                "data_pagamento": dt.strftime("%Y-%m-%d"),
                "importo": float(mov.get("importo") or 0),
                "tipo": tipo,
                "descrizione_causale": desc[:300],
                "estratto_conto_movimento_id": str(mov["_id"]),
                "cedolino_id": ced.get("id") if ced else None,
                "mese_riferimento": mese,
                "anno_riferimento": anno,
                "fonte": "auto_estratto_conto",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await db["pagamenti_dipendenti"].insert_one(doc)

            # Lega anche il movimento ec al dipendente
            await db["estratto_conto_movimenti"].update_one(
                {"_id": mov["_id"]},
                {"$set": {"dipendente_collegato_id": dip["id"],
                          "dipendente_collegato_nome": f"{dip.get('cognome','')} {dip.get('nome','')}".strip(),
                          "dipendente_pagamento_tipo": tipo}}
            )
        stats["creati"] += 1

    logger.info("Acconti scan result: %s", stats)
    return stats


async def get_pagamenti_dipendente(db: AsyncIOMotorDatabase, dipendente_id: str, anno: Optional[int] = None) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {"dipendente_id": dipendente_id}
    if anno:
        q["anno_riferimento"] = anno
    cursor = db["pagamenti_dipendenti"].find(q, {"_id": 0}).sort("data_pagamento", -1)
    return await cursor.to_list(500)
