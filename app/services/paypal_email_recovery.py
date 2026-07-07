"""
Recupero automatico delle fatture mancanti per i fornitori PayPal non
mappati (tipicamente fornitori esteri: MongoDB, RTA, SaaS vari — non
emettono mai fattura elettronica XML, quindi Drive/PEC-SDI non li
troveranno MAI, a prescindere da quanto tempo passa).

Invece di richiedere un click manuale per ciascun fornitore, questo modulo
scansiona da solo la posta per tutti i fornitori non mappati e allega ciò
che trova, sia dopo ogni sync PayPal sia in un job giornaliero.
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
import logging

logger = logging.getLogger(__name__)

COLL_TENTATIVI = "email_search_attempts"
# Sotto questo numero di giorni dall'ultimo tentativo (senza risultato), non
# ricerca di nuovo lo stesso fornitore: evita di martellare l'IMAP ogni
# giorno per un fornitore la cui fattura non arriverà mai via email.
GIORNI_MIN_TRA_TENTATIVI = 7


async def _trova_account_non_mappati(db) -> List[Dict[str, Any]]:
    """Stessa logica di aggregazione di /api/paypal-api/account-ids-non-mappati,
    ma senza lo scoring dei candidati fornitore (qui serve solo nome/email
    controparte per la ricerca email)."""
    pipeline = [
        {"$match": {
            "paypal_account_id": {"$exists": True, "$nin": [None, ""]},
            "importo": {"$lt": 0},
        }},
        {"$sort": {"nome_controparte": -1}},
        {"$group": {
            "_id": "$paypal_account_id",
            "nome_controparte": {"$first": "$nome_controparte"},
            "email_controparte": {"$first": "$email_controparte"},
        }},
    ]
    aggregates = await db["paypal_transactions"].aggregate(pipeline).to_list(500)

    mapped_ids = set()
    async for f in db["fornitori"].find(
        {"paypal_account_id": {"$ne": None}}, {"_id": 0, "paypal_account_id": 1}
    ):
        if f.get("paypal_account_id"):
            mapped_ids.add(f["paypal_account_id"])

    return [a for a in aggregates if a["_id"] not in mapped_ids]


async def recupera_fatture_mancanti_email(db, forza: bool = False) -> Dict[str, Any]:
    """
    Per ogni fornitore PayPal non mappato, cerca ed allega la fattura dalla
    posta (stessa pipeline di Documenti Inbox). Salta i fornitori già
    cercati senza esito nell'ultima settimana, a meno di forza=True.
    """
    from app.services.gmail_search import get_gmail_credentials
    from app.services.email_document_downloader import download_documents_from_email

    non_mappati = await _trova_account_non_mappati(db)
    if not non_mappati:
        return {"account_esaminati": 0, "cercati": 0, "documenti_trovati": 0, "dettaglio": []}

    user, pwd, _ = await get_gmail_credentials(db)
    if not user or not pwd:
        logger.warning("[PayPal Email Recovery] Nessun account Gmail configurato")
        return {"account_esaminati": len(non_mappati), "cercati": 0,
                "documenti_trovati": 0, "errore": "Nessun account Gmail configurato"}

    soglia = (datetime.now(timezone.utc) - timedelta(days=GIORNI_MIN_TRA_TENTATIVI)).isoformat()
    cercati = 0
    documenti_trovati = 0
    dettaglio = []

    for account in non_mappati:
        account_id = account["_id"]
        nome = (account.get("nome_controparte") or "").strip()
        email = (account.get("email_controparte") or "").strip()
        if not nome and not email:
            continue

        if not forza:
            tentativo = await db[COLL_TENTATIVI].find_one(
                {"tipo": "paypal_account", "chiave": account_id}, {"_id": 0, "ultima_ricerca": 1}
            )
            if tentativo and tentativo.get("ultima_ricerca", "") > soglia:
                continue

        parola_chiave = nome.split()[0] if nome else ""
        try:
            risultato = await download_documents_from_email(
                db, user, pwd,
                since_days=365,
                search_keywords=[parola_chiave] if parola_chiave else None,
                allowed_senders=[email] if email else None,
            )
        except Exception:
            logger.exception("[PayPal Email Recovery] Errore ricerca per %s", account_id)
            continue

        cercati += 1
        n_doc = risultato.get("stats", {}).get("new_documents", 0)
        documenti_trovati += n_doc
        dettaglio.append({
            "paypal_account_id": account_id,
            "nome_controparte": nome,
            "cercato_per": parola_chiave or email,
            "documenti_trovati": n_doc,
        })

        await db[COLL_TENTATIVI].update_one(
            {"tipo": "paypal_account", "chiave": account_id},
            {"$set": {
                "tipo": "paypal_account",
                "chiave": account_id,
                "ultima_ricerca": datetime.now(timezone.utc).isoformat(),
                "ultimo_esito_documenti": n_doc,
            }},
            upsert=True,
        )

    return {
        "account_esaminati": len(non_mappati),
        "cercati": cercati,
        "documenti_trovati": documenti_trovati,
        "dettaglio": dettaglio,
    }
