"""Mittenti attendibili — collezione canonica unica `mittenti_email` (P2-2).

Prima esistevano DUE collezioni per lo stesso concetto (mittenti fidati per
canale/tipo documento):
  - `mittenti_email`       → pattern / canale / tipo_documento / attivo
                             (gestita dalla CRUD in email_download.py)
  - `mittenti_attendibili` → indirizzo_email / tipo_documento / canale / attivo
                             (letta solo dal verbali_gmail_scanner)

`mittenti_email` è un superset (ha già `tipo_documento`; `indirizzo_email` è solo
un `pattern` esatto), quindi diventa la fonte UNICA. Qui si forniscono:
  - un accessor unico (`senders_attendibili`) che legge la collezione canonica e,
    per retro-compatibilità, unisce la legacy finché non è stata migrata;
  - una migrazione idempotente dei dati legacy (nessuna perdita di configurazioni).
"""
import uuid
from datetime import datetime, timezone
from email.utils import parseaddr
from typing import Any, Dict, List, Optional, Set

COLL = "mittenti_email"


# Mittenti istituzionali gia' previsti dai servizi Verbali/PagoPA, resi
# espliciti nella collezione canonica. Il trasportatore PEC
# `posta-certificata@pec.aruba.it` NON e' attendibile da solo: consegna PEC di
# qualunque origine e causava l'acquisizione di documenti non pertinenti.
BUILTIN_MITTENTI = (
    {
        "pattern": "dimissionitelematiche@pec.lavoro.gov.it",
        "tipo_documento": "dimissioni",
        "descrizione": "Ministero del Lavoro - dimissioni telematiche (modulo recesso rapporto di lavoro)",
    },
    {
        "pattern": "notifica.pl.napoli@pec.it",
        "tipo_documento": "verbale",
        "descrizione": "Polizia Locale Napoli - notifiche verbali",
    },
    {
        "pattern": "asianapoli.protocollo@pec.it",
        "tipo_documento": "verbale",
        "descrizione": "ASIA Napoli - verbali Comune di Napoli",
    },
    {
        "pattern": "ufficiosanzioni@arval.it",
        "tipo_documento": "verbale",
        "descrizione": "Arval - ufficio sanzioni",
    },
    {
        "pattern": "comando.pm@pec.comune.napoli.it",
        "tipo_documento": "verbale",
        "descrizione": "Polizia Municipale Napoli",
    },
    {
        "pattern": "prefettura.napoli@pec.interno.it",
        "tipo_documento": "verbale",
        "descrizione": "Prefettura di Napoli",
    },
    {
        "pattern": "partenopay@ext.comune.napoli.it",
        "tipo_documento": "pagopa",
        "descrizione": "Comune di Napoli - PagoPA",
    },
    {
        "pattern": "noreply-checkout@ricevute.pagopa.it",
        "tipo_documento": "pagopa",
        "descrizione": "Ricevute PagoPA",
    },
    {
        "pattern": "noreply.enelenergia@enel.com",
        "tipo_documento": "bolletta_energia",
        "descrizione": "Enel Energia - bollette e consumi elettrici",
    },
    {
        "pattern": "rosaria.marotta@email.it",
        "tipo_documento": "f24",
        "descrizione": "Studio Marotta - F24 e documenti fiscali",
    },
    {
        "pattern": "inpscomunica@postacert.inps.gov.it",
        "tipo_documento": "dilazione_inps",
        "descrizione": "INPS - dilazione amministrativa (piano di ammortamento in Allegato.zip)",
    },
    {
        "pattern": "noreply@ordersender.biz",
        "tipo_documento": "scheda_tecnica",
        "descrizione": "ME.PA. Alimentari (Order Sender) - schede tecniche dei prodotti acquistati",
    },
)


def _addr(m: Dict[str, Any]) -> str:
    return (m.get("indirizzo_email") or m.get("pattern") or "").strip().lower()


def _sender_address(sender: Any) -> str:
    if isinstance(sender, dict):
        sender = sender.get("email") or sender.get("address") or sender.get("from") or ""
    return parseaddr(str(sender or ""))[1].strip().lower()


async def trusted_sender_rules(db, canale: str = "gmail") -> List[Dict[str, str]]:
    """Carica una sola volta le regole attive.

    La funzione e' pensata per scansioni massive, evitando una query per ogni
    documento. Una regola disattivata non viene mai riabilitata implicitamente.
    """
    channel = str(canale or "gmail").strip().lower()
    rules: Dict[tuple[str, str], Dict[str, str]] = {}
    for collection in (COLL,):
        try:
            query = {
                "$and": [
                    {"$or": [{"canale": channel}, {"canale": {"$exists": False}}]},
                    {"$or": [{"attivo": True}, {"attivo": {"$exists": False}}]},
                ]
            }
            async for item in db[collection].find(query):
                pattern = _addr(item)
                category = str(item.get("tipo_documento") or "generico").strip().lower()
                if pattern:
                    rules[(pattern, category)] = {"pattern": pattern, "tipo_documento": category}
        except Exception:
            continue
    return list(rules.values())


def sender_matches_trusted_rules(
    sender: Any, tipo_documento: Optional[str], rules: List[Dict[str, str]]
) -> bool:
    address = _sender_address(sender)
    category = str(tipo_documento or "").strip().lower()
    if not address:
        return False
    for rule in rules:
        pattern = str(rule.get("pattern") or "").strip().lower()
        rule_category = str(rule.get("tipo_documento") or "generico").strip().lower()
        category_matches = not category or rule_category in {category, "generico"}
        if not category_matches:
            continue
        if pattern == address:
            return True
        if pattern.startswith("*@") and address.endswith(pattern[1:]):
            return True
    return False


async def is_sender_attendibile(
    db, sender: Any, tipo_documento: Optional[str] = None, canale: str = "gmail"
) -> bool:
    rules = await trusted_sender_rules(db, canale=canale)
    return sender_matches_trusted_rules(sender, tipo_documento, rules)


async def senders_attendibili(db, tipo_documento: str, canale: str) -> Set[str]:
    """Insieme degli indirizzi/pattern attendibili per (tipo_documento, canale),
    letti dalla collezione canonica + (back-compat) dalla legacy non ancora
    migrata."""
    filtro = {"tipo_documento": tipo_documento, "canale": canale, "attivo": True}
    out: Set[str] = set()
    async for m in db[COLL].find(filtro):
        a = _addr(m)
        if a:
            out.add(a)
    return out


async def assicura_mittenti_builtin(db) -> Dict[str, Any]:
    """Registra i mittenti istituzionali in modo idempotente.

    Usa solo ``$setOnInsert``: una scelta dell'utente (per esempio disattivare
    un mittente) non viene mai sovrascritta al riavvio.
    """
    inseriti = gia_presenti = 0
    for item in BUILTIN_MITTENTI:
        pattern = item["pattern"].strip().lower()
        result = await db[COLL].update_one(
            {"pattern": pattern, "canale": "gmail"},
            {"$setOnInsert": {
                "id": str(uuid.uuid4()),
                "pattern": pattern,
                "indirizzo_email": pattern,
                "canale": "gmail",
                "tipo_documento": item["tipo_documento"],
                "descrizione": item["descrizione"],
                "attivo": True,
                "builtin": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }},
            upsert=True,
        )
        if result.upserted_id is not None:
            inseriti += 1
        else:
            gia_presenti += 1
    return {"inseriti": inseriti, "gia_presenti": gia_presenti}
