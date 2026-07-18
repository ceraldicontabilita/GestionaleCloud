"""
FINANZIAMENTO SOCI — prima nota dei finanziamenti (richiesta utente 18/07/2026).

Una scheda personale per ognuno dei quattro soci:
Vincenzo Ceraldi, Giuseppina Pane, Antonietta Ceraldi, Valerio Ceraldi.

Regole (dettate dall'utente):
- bonifico IN ENTRATA in estratto conto con il nome di un socio →
  APPORTO nella sua scheda personale;
- bonifico IN USCITA verso un socio: si legge la causale OGNI VOLTA —
  solo se parla di rimborso/restituzione/finanziamento è un RIMBORSO
  nella scheda del socio corrispondente (gli stipendi ai soci dipendenti
  NON sono rimborsi e vengono ignorati).

La scansione è idempotente (chiave = riga di estratto conto) e i dati
finiscono nella collezione `finanziamenti_soci_movimenti`. Nessuna
scrittura in prima_nota_cassa/banca: è un registro analitico separato.
"""
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

COLLECTION = "finanziamenti_soci_movimenti"

# I quattro soci (lista dettata dall'utente il 18/07/2026).
SOCI: List[Dict[str, Any]] = [
    {"id": "vincenzo_ceraldi", "nome": "Vincenzo Ceraldi", "tokens": ("CERALDI", "VINCENZO")},
    {"id": "giuseppina_pane", "nome": "Giuseppina Pane", "tokens": ("PANE", "GIUSEPPINA")},
    {"id": "antonietta_ceraldi", "nome": "Antonietta Ceraldi", "tokens": ("CERALDI", "ANTONIETTA")},
    {"id": "valerio_ceraldi", "nome": "Valerio Ceraldi", "tokens": ("CERALDI", "VALERIO")},
]

# Causali che qualificano un'uscita verso un socio come RIMBORSO del
# finanziamento (altrimenti l'uscita viene ignorata: stipendi, rimborsi
# spese generici non c'entrano col finanziamento soci).
_RE_RIMBORSO = re.compile(r"RIMBORS\w*\s+(?:FINANZIAMENT|SOC)|RESTITUZ|FINANZIAMENT", re.IGNORECASE)


def socio_in_testo(testo: str) -> Optional[Dict[str, Any]]:
    """Riconosce un socio dal testo della causale (entrambi i token del nome)."""
    t = (testo or "").upper()
    for s in SOCI:
        if all(tok in t for tok in s["tokens"]):
            return s
    return None


def _descrizione_ec(doc: Dict[str, Any]) -> str:
    return doc.get("descrizione_originale") or doc.get("descrizione") or ""


def _data_ec(doc: Dict[str, Any]) -> str:
    return str(doc.get("data_contabile") or doc.get("data") or "")[:10]


def _verso_ec(doc: Dict[str, Any]) -> Optional[str]:
    """entrata/uscita gestendo sia lo schema ABS+tipo sia quello con segno."""
    tipo = doc.get("tipo")
    if tipo in ("entrata", "uscita"):
        return tipo
    importo = doc.get("importo")
    if importo is None:
        return None
    return "entrata" if float(importo) > 0 else "uscita"


def _id_ec(doc: Dict[str, Any]) -> str:
    return str(doc.get("id") or doc.get("_id") or "")


async def scan_finanziamenti_da_ec(db, anno: Optional[int] = None) -> Dict[str, Any]:
    """Estrae apporti e rimborsi soci dall'estratto conto (idempotente)."""
    stats = {
        "righe_esaminate": 0,
        "apporti_nuovi": 0,
        "rimborsi_nuovi": 0,
        "gia_presenti": 0,
        "uscite_ignorate_causale": 0,
        "per_socio": {s["id"]: 0 for s in SOCI},
    }

    query: Dict[str, Any] = {}
    if anno:
        query["$or"] = [
            {"data_contabile": {"$gte": f"{anno}-01-01", "$lte": f"{anno}-12-31"}},
            {"data": {"$gte": f"{anno}-01-01", "$lte": f"{anno}-12-31"}},
        ]

    gia_importati = set()
    async for m in db[COLLECTION].find({}, {"estratto_conto_id": 1, "_id": 0}):
        if m.get("estratto_conto_id"):
            gia_importati.add(m["estratto_conto_id"])

    cursor = db["estratto_conto_movimenti"].find(query)
    async for doc in cursor:
        stats["righe_esaminate"] += 1
        descr = _descrizione_ec(doc)
        socio = socio_in_testo(descr)
        if not socio:
            continue
        verso = _verso_ec(doc)
        if verso is None:
            continue
        if verso == "uscita" and not _RE_RIMBORSO.search(descr):
            # Causale letta ogni volta: senza rimborso/restituzione/
            # finanziamento NON è un rimborso soci (es. stipendio).
            stats["uscite_ignorate_causale"] += 1
            continue
        ec_id = _id_ec(doc)
        if not ec_id or ec_id in gia_importati:
            stats["gia_presenti"] += 1
            continue

        tipo_mov = "apporto" if verso == "entrata" else "rimborso"
        movimento = {
            "id": str(uuid.uuid4()),
            "socio_id": socio["id"],
            "socio_nome": socio["nome"],
            "tipo": tipo_mov,
            "importo": round(abs(float(doc.get("importo") or 0)), 2),
            "data": _data_ec(doc),
            "descrizione": descr,
            "estratto_conto_id": ec_id,
            "source": "estratto_conto_auto",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if movimento["importo"] <= 0 or not movimento["data"]:
            continue
        await db[COLLECTION].insert_one(movimento)
        gia_importati.add(ec_id)
        stats["per_socio"][socio["id"]] += 1
        stats["apporti_nuovi" if tipo_mov == "apporto" else "rimborsi_nuovi"] += 1

    return stats


async def schede_soci(db, anno: Optional[int] = None) -> Dict[str, Any]:
    """Le quattro schede personali: apporti, rimborsi, saldo e movimenti."""
    query: Dict[str, Any] = {}
    if anno:
        query["data"] = {"$gte": f"{anno}-01-01", "$lte": f"{anno}-12-31"}

    per_socio: Dict[str, List[Dict[str, Any]]] = {s["id"]: [] for s in SOCI}
    async for m in db[COLLECTION].find(query, {"_id": 0}):
        per_socio.setdefault(m.get("socio_id", ""), []).append(m)

    schede = []
    tot_apporti = tot_rimborsi = 0.0
    for s in SOCI:
        movs = sorted(per_socio.get(s["id"], []), key=lambda m: m.get("data", ""), reverse=True)
        apporti = round(sum(m["importo"] for m in movs if m["tipo"] == "apporto"), 2)
        rimborsi = round(sum(m["importo"] for m in movs if m["tipo"] == "rimborso"), 2)
        tot_apporti += apporti
        tot_rimborsi += rimborsi
        schede.append({
            "socio_id": s["id"],
            "nome": s["nome"],
            "apporti": apporti,
            "rimborsi": rimborsi,
            "saldo": round(apporti - rimborsi, 2),
            "movimenti": movs,
        })

    return {
        "anno": anno,
        "schede": schede,
        "totale": {
            "apporti": round(tot_apporti, 2),
            "rimborsi": round(tot_rimborsi, 2),
            "saldo": round(tot_apporti - tot_rimborsi, 2),
        },
    }
