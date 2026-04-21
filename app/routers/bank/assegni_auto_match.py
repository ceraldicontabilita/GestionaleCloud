"""
Auto-matcher Assegni ↔ Fatture (4 livelli, N:M, tolleranza ±0,005€).

Implementa la logica documentata in /app/memoria/LOGICA_OPERATIVA.md §8.

LIVELLI:
- L1 match secco: 1 assegno = 1 fattura stesso importo (±0,005€)
- L2 match di gruppo: N assegni uguali stesso fornitore = 1 fattura divisa in parti uguali
  (finestra max 4 mesi tra primo e ultimo assegno, stesso carnet, max 4 rate)
- L3 match di somma: 2-4 assegni di importi DIVERSI stesso fornitore = 1 fattura
- L4 match inverso: 1 assegno = 2-4 fatture dello stesso fornitore

REGOLE:
- Vincolo rigido: P.IVA fornitore deve combaciare
- Tolleranza ±0,005€ (mezzo centesimo) SALVO L2 dove serve ±0,005€ × N per
  compensare l'arrotondamento della divisione
- Il matcher è CONSERVATIVO: se trova più candidate valide, non decide e
  segnala "ambiguo" nella lista delle proposte da confermare
- Idempotente: rilanciarlo non crea match duplicati

OUTPUT:
{
  "processati": N assegni analizzati,
  "match_l1": [...],
  "match_l2": [...],
  "match_l3": [...],
  "match_l4": [...],
  "ambigui": [...],
  "non_trovati": [...],
  "movimenti_banca_creati": N,
  "fatture_aggiornate": N,
}
"""
from __future__ import annotations

from datetime import datetime, timezone
from itertools import combinations
from typing import Any, Dict, List, Optional, Tuple
import logging
import uuid

logger = logging.getLogger(__name__)

TOLL = 0.005  # mezzo centesimo
MAX_RATE = 4


# ─────────────────────────────── helpers ───────────────────────────────

def _f(v: Any) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _norm_piva(v: Any) -> str:
    return (str(v or "").strip()).replace(" ", "")


def _is_paid_status(s: Any) -> bool:
    if not s:
        return False
    s = str(s).lower()
    return s in {"paid", "pagata", "pagato"}


async def _load_assegni_to_match(db) -> List[Dict[str, Any]]:
    """Assegni da processare: hanno importo > 0, non sono annullati,
    e NON hanno fatture collegate (fatture_collegate vuoto).
    Lo stato 'incassato' è OK: indica solo che la banca ha addebitato,
    non che l'assegno sia stato collegato a una fattura."""
    cursor = db["assegni"].find({
        "importo": {"$gt": 0},
        "stato": {"$nin": ["annullato"]},
        "$or": [
            {"fatture_collegate": {"$in": [None, []]}},
            {"fatture_collegate": {"$exists": False}},
        ],
    }, {"_id": 0})
    return await cursor.to_list(10000)


def _normalize_ragione_sociale(s: str) -> str:
    if not s:
        return ""
    s = str(s).lower().strip()
    for suffix in [" s.r.l.", " srl", " s.p.a.", " spa", " s.n.c.", " snc",
                   " s.a.s.", " sas", " srls", " unipersonale", "-unipersonale",
                   "&", " e "]:
        s = s.replace(suffix, " ")
    return " ".join(s.split())


async def _enrich_assegni_con_piva(db, assegni: List[Dict[str, Any]]) -> int:
    """
    Per gli assegni senza fornitore_piva ma con beneficiario, prova a risolvere
    la P.IVA cercando nel DB fornitori per ragione_sociale/denominazione.
    Scrive direttamente sugli assegni (persistente).
    Ritorna il numero di assegni arricchiti.
    """
    # carica fornitori (index locale)
    fornitori = await db["fornitori"].find({}, {"_id": 0, "id": 1, "partita_iva": 1,
                                               "vat_number": 1, "ragione_sociale": 1,
                                               "denominazione": 1, "name": 1}).to_list(5000)
    index_fornitori: Dict[str, str] = {}
    for f in fornitori:
        piva = _norm_piva(f.get("partita_iva") or f.get("vat_number"))
        if not piva:
            continue
        for key_name in (f.get("ragione_sociale"), f.get("denominazione"), f.get("name")):
            norm = _normalize_ragione_sociale(key_name)
            if norm:
                index_fornitori[norm] = piva

    enriched = 0
    for ass in assegni:
        if _norm_piva(ass.get("fornitore_piva")):
            continue
        benef = ass.get("beneficiario") or ""
        norm = _normalize_ragione_sociale(benef)
        if not norm:
            continue
        piva = index_fornitori.get(norm)
        if not piva:
            # fallback: substring match (se norm è prefisso di qualche chiave)
            for k, v in index_fornitori.items():
                if norm in k or k in norm:
                    piva = v
                    break
        if piva:
            ass["fornitore_piva"] = piva
            ass["fornitore_ragione_sociale"] = benef
            await db["assegni"].update_one(
                {"id": ass["id"]},
                {"$set": {"fornitore_piva": piva, "fornitore_ragione_sociale": benef}}
            )
            enriched += 1
    return enriched


async def _load_open_invoices_by_piva(db) -> Dict[str, List[Dict[str, Any]]]:
    """Fatture aperte/parziali raggruppate per P.IVA fornitore.
    Esclude pagate, annullate, eliminate. Applica eventuali note credito."""
    invoices = await db["invoices"].find({
        "$and": [
            {"$or": [
                {"total_amount": {"$gt": 0}},
                {"importo_totale": {"$gt": 0}},
            ]},
            {"payment_status": {"$nin": ["paid", "cancelled"]}},
            {"entity_status": {"$ne": "deleted"}},
        ]
    }, {"_id": 0}).to_list(20000)

    by_piva: Dict[str, List[Dict[str, Any]]] = {}
    for inv in invoices:
        if _is_paid_status(inv.get("payment_status")) or _is_paid_status(inv.get("pagato")):
            continue
        piva = _norm_piva(inv.get("supplier_vat") or inv.get("cedente_id_fiscale") or inv.get("partita_iva"))
        if not piva:
            continue
        total = _f(inv.get("total_amount") or inv.get("importo_totale"))
        paid = _f(inv.get("importo_pagato") or 0)
        residuo = round(total - paid, 2)
        if residuo <= TOLL:
            continue
        # Esclude note credito (importo negativo)
        if total < 0:
            continue
        inv["_residuo"] = residuo
        by_piva.setdefault(piva, []).append(inv)
    return by_piva


def _within_4_months(dates: List[str]) -> bool:
    """True se l'intervallo tra prima e ultima data è ≤ 4 mesi (~125 giorni)."""
    parsed = []
    for d in dates:
        if not d:
            continue
        try:
            parsed.append(datetime.fromisoformat(str(d)[:10]))
        except (ValueError, TypeError):
            pass
    if len(parsed) < 2:
        return True
    diff = (max(parsed) - min(parsed)).days
    return diff <= 125


# ──────────────────────── singoli livelli di matching ────────────────────────

def _dedup_candidates(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Se le candidate sono duplicati (stesso invoice_number + supplier_vat + importo),
    ritorna solo la più vecchia. Gestisce i duplicati storici nel DB."""
    if len(candidates) <= 1:
        return candidates
    groups: Dict[Tuple[str, str, float], List[Dict[str, Any]]] = {}
    for c in candidates:
        key = (
            str(c.get("invoice_number") or c.get("numero") or ""),
            _norm_piva(c.get("supplier_vat") or c.get("cedente_id_fiscale")),
            round(c["_residuo"], 2),
        )
        groups.setdefault(key, []).append(c)
    # se esiste un gruppo univoco → usa il più vecchio in quel gruppo
    unique_groups = [g for g in groups.values()]
    if len(unique_groups) == 1:
        # Tutti i candidati sono duplicati dello stesso documento
        g = unique_groups[0]
        g_sorted = sorted(g, key=lambda x: str(x.get("invoice_date") or x.get("created_at") or "9999"))
        return [g_sorted[0]]
    # più gruppi distinti → davvero ambiguo
    return candidates


def _try_l1(assegno: Dict[str, Any], fatture: List[Dict[str, Any]]) -> Tuple[str, Optional[List[Dict[str, Any]]]]:
    """L1: 1 assegno = 1 fattura, importo uguale (±0,005€).
    Ritorna: ("ok", [fattura]) | ("ambiguous", [candidates]) | ("miss", None)."""
    imp = round(_f(assegno.get("importo")), 2)
    candidates = [f for f in fatture if abs(f["_residuo"] - imp) <= TOLL]
    candidates = _dedup_candidates(candidates)
    if len(candidates) == 1:
        return "ok", candidates
    if len(candidates) > 1:
        return "ambiguous", candidates
    return "miss", None


def _try_l2(
    assegni_gruppo: List[Dict[str, Any]], fatture: List[Dict[str, Any]]
) -> Tuple[str, Optional[Tuple[Dict[str, Any], List[Dict[str, Any]]]]]:
    """L2: N assegni uguali stesso fornitore = 1 fattura divisa in parti uguali.
    Input: lista di assegni dello stesso fornitore, già filtrati per stesso importo (±TOLL).
    - N in [2..4]
    - finestra 4 mesi tra il primo e l'ultimo
    - stesso carnet
    """
    n = len(assegni_gruppo)
    if n < 2 or n > MAX_RATE:
        return "miss", None
    carnets = {a.get("carnet_id") for a in assegni_gruppo if a.get("carnet_id")}
    if len(carnets) > 1:
        return "miss", None
    dates = [a.get("data_emissione") for a in assegni_gruppo]
    if not _within_4_months(dates):
        return "miss", None

    somma = round(sum(_f(a.get("importo")) for a in assegni_gruppo), 2)
    # tolleranza cumulativa
    tol = TOLL * n
    candidates = [f for f in fatture if abs(f["_residuo"] - somma) <= tol]
    if len(candidates) == 1:
        return "ok", (candidates[0], assegni_gruppo)
    if len(candidates) > 1:
        return "ambiguous", (candidates[0], assegni_gruppo)
    return "miss", None


def _try_l3(
    assegni_forn: List[Dict[str, Any]], fatture: List[Dict[str, Any]]
) -> List[Tuple[Dict[str, Any], List[Dict[str, Any]]]]:
    """L3: 2..4 assegni di importi diversi dello stesso fornitore = 1 fattura.
    Finestra 60 giorni, stesso carnet non obbligatorio."""
    found: List[Tuple[Dict[str, Any], List[Dict[str, Any]]]] = []
    used_ids: set = set()
    # prova prima combinazioni più grandi (N=4 poi 3 poi 2) per "assorbire" meglio
    for n in range(MAX_RATE, 1, -1):
        if len(assegni_forn) < n:
            continue
        for combo in combinations(assegni_forn, n):
            if any(a["id"] in used_ids for a in combo):
                continue
            imp_list = [round(_f(a.get("importo")), 2) for a in combo]
            # escludi le combinazioni dove tutti gli importi sono uguali (è L2)
            if len(set(imp_list)) == 1:
                continue
            # finestra temporale 60 giorni
            dates = [a.get("data_emissione") for a in combo]
            try:
                parsed = [datetime.fromisoformat(str(d)[:10]) for d in dates if d]
                if len(parsed) >= 2 and (max(parsed) - min(parsed)).days > 60:
                    continue
            except (ValueError, TypeError):
                continue
            somma = round(sum(imp_list), 2)
            candidates = [f for f in fatture if abs(f["_residuo"] - somma) <= TOLL]
            if len(candidates) == 1:
                used_ids.update(a["id"] for a in combo)
                found.append((candidates[0], list(combo)))
                break  # questa fattura è stata presa
    return found


def _try_l4(
    assegno: Dict[str, Any], fatture: List[Dict[str, Any]]
) -> Tuple[str, Optional[List[Dict[str, Any]]]]:
    """L4: 1 assegno = 2..4 fatture dello stesso fornitore (somma == importo assegno)."""
    imp = round(_f(assegno.get("importo")), 2)
    if len(fatture) < 2:
        return "miss", None
    # Limita combinazioni per performance: ordina per residuo desc, top 10 fatture
    top = sorted(fatture, key=lambda f: -f["_residuo"])[:10]
    for n in range(2, MAX_RATE + 1):
        found_combo = None
        ambiguous = False
        for combo in combinations(top, n):
            somma = round(sum(f["_residuo"] for f in combo), 2)
            if abs(somma - imp) <= TOLL:
                if found_combo is None:
                    found_combo = list(combo)
                else:
                    ambiguous = True
                    break
        if ambiguous:
            return "ambiguous", found_combo
        if found_combo:
            return "ok", found_combo
    return "miss", None


# ──────────────────────── applica il match al DB ────────────────────────

async def _apply_match(
    db,
    assegni_match: List[Dict[str, Any]],
    fatture_match: List[Dict[str, Any]],
    *,
    livello: str,
    dry_run: bool,
) -> Dict[str, Any]:
    """Collega N assegni a M fatture (N:M). Calcola le quote in modo consistente.

    Strategia:
    - Se 1 assegno ↔ 1 fattura: quota = importo assegno (o residuo fattura se minore)
    - Se N assegni ↔ 1 fattura: ogni assegno ha quota = proprio importo (assorbono la fattura)
    - Se 1 assegno ↔ N fatture: ogni fattura prende quota = proprio residuo
    """
    now = datetime.now(timezone.utc).isoformat()
    movimenti_banca = 0

    # Caso 1 assegno → 1+ fatture (L1 e L4)
    if len(assegni_match) == 1:
        assegno = assegni_match[0]
        importo_ass = round(_f(assegno.get("importo")), 2)
        fatture_collegate = []
        quote_assegnate_totale = 0.0
        for f in fatture_match:
            quota = round(min(f["_residuo"], importo_ass - quote_assegnate_totale), 2)
            if quota <= TOLL:
                continue
            fatture_collegate.append({
                "fattura_id": f.get("id"),
                "quota": quota,
                "data_collegamento": now,
                "match_auto": True,
                "match_livello": livello,
            })
            quote_assegnate_totale = round(quote_assegnate_totale + quota, 2)

        if dry_run:
            return {"dry_run": True, "assegno_id": assegno.get("id"), "fatture": fatture_collegate}

        await db["assegni"].update_one(
            {"id": assegno["id"]},
            {"$set": {
                "fatture_collegate": fatture_collegate,
                "importo_assegnato": quote_assegnate_totale,
                "fornitore_piva": _norm_piva(
                    fatture_match[0].get("supplier_vat") or
                    fatture_match[0].get("cedente_id_fiscale") or
                    fatture_match[0].get("partita_iva")
                ),
                "fornitore_ragione_sociale": fatture_match[0].get("supplier_name") or
                                              fatture_match[0].get("cedente_denominazione"),
                "stato": "assegnato" if abs(quote_assegnate_totale - importo_ass) <= TOLL else "parzialmente_assegnato",
                "match_auto": True,
                "match_livello": livello,
                "updated_at": now,
            }}
        )

        # Aggiorna fatture
        for fc in fatture_collegate:
            await _aggiorna_fattura(db, fc["fattura_id"], fc["quota"], assegno)
            movimenti_banca += await _crea_mov_banca(db, assegno, fc["quota"], fc["fattura_id"])

        return {
            "assegno_id": assegno.get("id"),
            "assegno_numero": assegno.get("numero"),
            "fatture": fatture_collegate,
            "movimenti_banca": movimenti_banca,
            "livello": livello,
        }

    # Caso N assegni → 1 fattura (L2 e L3)
    if len(fatture_match) == 1:
        fattura = fatture_match[0]
        residuo_fatt = fattura["_residuo"]
        assegni_collegati_result = []

        if dry_run:
            return {"dry_run": True, "fattura_id": fattura.get("id"),
                    "assegni": [a.get("id") for a in assegni_match], "livello": livello}

        quota_totale = 0.0
        for ass in assegni_match:
            imp = round(_f(ass.get("importo")), 2)
            quota = round(min(imp, residuo_fatt - quota_totale), 2)
            if quota <= TOLL:
                continue
            fatture_collegate_ass = [{
                "fattura_id": fattura.get("id"),
                "quota": quota,
                "data_collegamento": now,
                "match_auto": True,
                "match_livello": livello,
            }]
            quota_totale = round(quota_totale + quota, 2)

            await db["assegni"].update_one(
                {"id": ass["id"]},
                {"$set": {
                    "fatture_collegate": fatture_collegate_ass,
                    "importo_assegnato": quota,
                    "fornitore_piva": _norm_piva(
                        fattura.get("supplier_vat") or fattura.get("cedente_id_fiscale") or fattura.get("partita_iva")
                    ),
                    "fornitore_ragione_sociale": fattura.get("supplier_name") or fattura.get("cedente_denominazione"),
                    "stato": "assegnato" if abs(quota - imp) <= TOLL else "parzialmente_assegnato",
                    "match_auto": True,
                    "match_livello": livello,
                    "updated_at": now,
                }}
            )
            assegni_collegati_result.append({"assegno_id": ass["id"], "quota": quota})
            movimenti_banca += await _crea_mov_banca(db, ass, quota, fattura.get("id"))

        # Aggiorna fattura cumulando tutte le quote
        await _aggiorna_fattura_bulk(db, fattura.get("id"), quota_totale, assegni_match)

        return {
            "fattura_id": fattura.get("id"),
            "fattura_numero": fattura.get("invoice_number"),
            "assegni": assegni_collegati_result,
            "movimenti_banca": movimenti_banca,
            "livello": livello,
        }

    return {"error": "caso match non gestito"}


async def _aggiorna_fattura(db, fattura_id: str, quota: float, assegno: Dict[str, Any]) -> None:
    """Aggiunge la quota al pagato della fattura + assegni_collegati[]."""
    inv = await db["invoices"].find_one({"id": fattura_id}, {"_id": 0})
    if not inv:
        return
    total = _f(inv.get("total_amount") or inv.get("importo_totale"))
    nuovo_pagato = round(_f(inv.get("importo_pagato", 0)) + quota, 2)
    nuovo_stato = "paid" if abs(nuovo_pagato - total) <= TOLL else ("partial" if nuovo_pagato > TOLL else "aperta")

    await db["invoices"].update_one(
        {"id": fattura_id},
        {
            "$set": {
                "importo_pagato": nuovo_pagato,
                "importo_residuo": round(max(0, total - nuovo_pagato), 2),
                "payment_status": nuovo_stato,
                "pagato": nuovo_stato == "paid",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            "$push": {
                "assegni_collegati": {
                    "assegno_id": assegno.get("id"),
                    "numero": assegno.get("numero"),
                    "quota": quota,
                    "data_collegamento": datetime.now(timezone.utc).isoformat(),
                    "match_auto": True,
                }
            },
        },
    )


async def _aggiorna_fattura_bulk(db, fattura_id: str, quota_tot: float, assegni: List[Dict[str, Any]]) -> None:
    """Come _aggiorna_fattura ma per N assegni che vanno sulla stessa fattura (L2/L3)."""
    inv = await db["invoices"].find_one({"id": fattura_id}, {"_id": 0})
    if not inv:
        return
    total = _f(inv.get("total_amount") or inv.get("importo_totale"))
    nuovo_pagato = round(_f(inv.get("importo_pagato", 0)) + quota_tot, 2)
    nuovo_stato = "paid" if abs(nuovo_pagato - total) <= TOLL else ("partial" if nuovo_pagato > TOLL else "aperta")

    now = datetime.now(timezone.utc).isoformat()
    pushes = [{
        "assegno_id": a.get("id"),
        "numero": a.get("numero"),
        "quota": round(_f(a.get("importo")), 2),
        "data_collegamento": now,
        "match_auto": True,
    } for a in assegni]

    await db["invoices"].update_one(
        {"id": fattura_id},
        {
            "$set": {
                "importo_pagato": nuovo_pagato,
                "importo_residuo": round(max(0, total - nuovo_pagato), 2),
                "payment_status": nuovo_stato,
                "pagato": nuovo_stato == "paid",
                "updated_at": now,
            },
            "$push": {"assegni_collegati": {"$each": pushes}},
        },
    )


async def _crea_mov_banca(db, assegno: Dict[str, Any], quota: float, fattura_id: str) -> int:
    """Crea un movimento in prima_nota_banca tipo 'uscita_assegno'. Idempotente.
    Ritorna 1 se creato, 0 se già presente."""
    # idempotenza: stesso assegno_id + fattura_id
    existing = await db["prima_nota_banca"].find_one({
        "assegno_id": assegno.get("id"),
        "invoice_id": fattura_id,
        "tipo": "uscita",
        "categoria": "Assegni",
    })
    if existing:
        return 0

    data_em = assegno.get("data_emissione") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    mov = {
        "id": str(uuid.uuid4()),
        "data": str(data_em)[:10],
        "date": str(data_em)[:10],
        "tipo": "uscita",
        "type": "uscita",
        "importo": round(quota, 2),
        "amount": round(quota, 2),
        "descrizione": f"Assegno n. {assegno.get('numero', '')} - {assegno.get('fornitore_ragione_sociale', '')}".strip(" -"),
        "description": f"Assegno n. {assegno.get('numero', '')}",
        "categoria": "Assegni",
        "category": "Assegni",
        "assegno_id": assegno.get("id"),
        "assegno_numero": assegno.get("numero"),
        "invoice_id": fattura_id,
        "source": "assegno_auto_match",
        "riconciliato": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db["prima_nota_banca"].insert_one(mov.copy())
    return 1


# ─────────────────────────── ORCHESTRATORE ───────────────────────────

async def run_auto_match(db, *, dry_run: bool = False) -> Dict[str, Any]:
    """Esegue l'auto-match a 4 livelli. Ritorna report dettagliato."""
    assegni = await _load_assegni_to_match(db)
    # Arricchisci assegni senza P.IVA usando il DB fornitori
    enriched = await _enrich_assegni_con_piva(db, assegni)
    inv_by_piva = await _load_open_invoices_by_piva(db)

    report: Dict[str, Any] = {
        "assegni_processati": len(assegni),
        "assegni_arricchiti_piva": enriched,
        "fatture_disponibili": sum(len(v) for v in inv_by_piva.values()),
        "match_l1": [], "match_l2": [], "match_l3": [], "match_l4": [],
        "ambigui": [], "non_trovati": [],
        "movimenti_banca_creati": 0,
        "dry_run": dry_run,
    }

    # Index assegno per P.IVA
    assegni_by_piva: Dict[str, List[Dict[str, Any]]] = {}
    for a in assegni:
        piva = _norm_piva(a.get("fornitore_piva"))
        # Se P.IVA sul check non c'è, proviamo ad inferirla dal beneficiario: non affidabile
        # → queste senza piva non possono essere matchate in sicurezza
        if not piva:
            report["non_trovati"].append({"assegno_id": a.get("id"), "numero": a.get("numero"),
                                          "motivo": "P.IVA fornitore mancante sull'assegno"})
            continue
        assegni_by_piva.setdefault(piva, []).append(a)

    matched_ids: set = set()

    # ── LIVELLO 1: assegno per assegno, cerca fattura singola di uguale importo
    for piva, lista_ass in assegni_by_piva.items():
        fatture = inv_by_piva.get(piva, [])
        if not fatture:
            continue
        for ass in lista_ass:
            if ass["id"] in matched_ids:
                continue
            status, cands = _try_l1(ass, [f for f in fatture if f.get("id") not in _used_invoice_ids(report)])
            if status == "ok":
                res = await _apply_match(db, [ass], cands, livello="L1", dry_run=dry_run)
                report["match_l1"].append(res)
                report["movimenti_banca_creati"] += res.get("movimenti_banca", 0)
                matched_ids.add(ass["id"])
            elif status == "ambiguous":
                report["ambigui"].append({
                    "livello": "L1",
                    "assegno_id": ass.get("id"),
                    "assegno_numero": ass.get("numero"),
                    "candidates": [{"fattura_id": c.get("id"), "numero": c.get("invoice_number"),
                                    "importo": c["_residuo"]} for c in cands],
                })

    # ── LIVELLO 2: N assegni uguali → 1 fattura (fornitore × importo uguale)
    for piva, lista_ass in assegni_by_piva.items():
        non_match = [a for a in lista_ass if a["id"] not in matched_ids]
        if len(non_match) < 2:
            continue
        # raggruppa per importo (arrotondato 2 decimali)
        groups: Dict[float, List[Dict[str, Any]]] = {}
        for a in non_match:
            imp = round(_f(a.get("importo")), 2)
            groups.setdefault(imp, []).append(a)
        fatture = inv_by_piva.get(piva, [])
        for imp, grp in groups.items():
            if len(grp) < 2:
                continue
            fatture_disp = [f for f in fatture if f.get("id") not in _used_invoice_ids(report)]
            # prova con il gruppo intero, poi con sottogruppi
            for n in range(min(len(grp), MAX_RATE), 1, -1):
                sub = grp[:n]
                status, payload = _try_l2(sub, fatture_disp)
                if status == "ok":
                    fattura, assegni_sub = payload
                    res = await _apply_match(db, assegni_sub, [fattura], livello="L2", dry_run=dry_run)
                    report["match_l2"].append(res)
                    report["movimenti_banca_creati"] += res.get("movimenti_banca", 0)
                    for a in assegni_sub:
                        matched_ids.add(a["id"])
                    break

    # ── LIVELLO 3: N assegni diversi → 1 fattura
    for piva, lista_ass in assegni_by_piva.items():
        non_match = [a for a in lista_ass if a["id"] not in matched_ids]
        if len(non_match) < 2:
            continue
        fatture_disp = [f for f in inv_by_piva.get(piva, []) if f.get("id") not in _used_invoice_ids(report)]
        risultati_l3 = _try_l3(non_match, fatture_disp)
        for fattura, combo in risultati_l3:
            res = await _apply_match(db, combo, [fattura], livello="L3", dry_run=dry_run)
            report["match_l3"].append(res)
            report["movimenti_banca_creati"] += res.get("movimenti_banca", 0)
            for a in combo:
                matched_ids.add(a["id"])

    # ── LIVELLO 4: 1 assegno → N fatture
    for piva, lista_ass in assegni_by_piva.items():
        fatture = inv_by_piva.get(piva, [])
        for ass in lista_ass:
            if ass["id"] in matched_ids:
                continue
            fatture_disp = [f for f in fatture if f.get("id") not in _used_invoice_ids(report)]
            if len(fatture_disp) < 2:
                continue
            status, combo = _try_l4(ass, fatture_disp)
            if status == "ok":
                res = await _apply_match(db, [ass], combo, livello="L4", dry_run=dry_run)
                report["match_l4"].append(res)
                report["movimenti_banca_creati"] += res.get("movimenti_banca", 0)
                matched_ids.add(ass["id"])
            elif status == "ambiguous":
                report["ambigui"].append({
                    "livello": "L4",
                    "assegno_id": ass.get("id"),
                    "assegno_numero": ass.get("numero"),
                    "candidates": [{"fattura_id": c.get("id"), "numero": c.get("invoice_number"),
                                    "importo": c["_residuo"]} for c in (combo or [])],
                })

    # assegni non trovati
    for piva, lista_ass in assegni_by_piva.items():
        for ass in lista_ass:
            if ass["id"] not in matched_ids:
                already_reported = any(
                    (x.get("assegno_id") == ass["id"]) for x in report["non_trovati"] + report["ambigui"]
                )
                if not already_reported:
                    report["non_trovati"].append({
                        "assegno_id": ass.get("id"),
                        "numero": ass.get("numero"),
                        "importo": _f(ass.get("importo")),
                        "fornitore_piva": piva,
                    })

    report["fatture_aggiornate"] = (
        len(report["match_l1"]) + len(report["match_l2"]) +
        len(report["match_l3"]) + len(report["match_l4"])
    )
    return report


def _used_invoice_ids(report: Dict[str, Any]) -> set:
    """Raccoglie tutti gli id fattura già usati dal matcher."""
    used: set = set()
    for k in ("match_l1", "match_l2", "match_l3", "match_l4"):
        for m in report.get(k, []):
            fid = m.get("fattura_id")
            if fid:
                used.add(fid)
            for fc in (m.get("fatture") or []):
                if fc.get("fattura_id"):
                    used.add(fc["fattura_id"])
    return used
