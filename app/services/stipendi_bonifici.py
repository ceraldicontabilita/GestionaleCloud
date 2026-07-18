"""
Associazione automatica bonifici stipendio ↔ dipendenti (richiesta utente
18/07/2026): "il sistema automaticamente quando legge in estratto conto il
nome del dipendente deve associare il pagamento al dipendente".

L'estratto conto Banco BPM scrive i bonifici come:
  "VOSTRA DISPOSIZIONE - VS.DISP. RIF. MB0B.../90553586 FAVORE Lesina
   Angela - ADD.TOT - lesina Angela"
Il nome dopo FAVORE viene confrontato con le righe stipendio pendenti di
`prima_nota_salari` (generate dai cedolini/distinte): stesso insieme di
token del nome (in qualunque ordine, case-insensitive), così "Pocci
Salvatore" combacia con "POCCI SALVATORE" ma non con altri Ceraldi.
Le righe COMM.SU BONIFICI (commissioni) non sono mai pagamenti stipendio.
"""
import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# nome dopo FAVORE, fermandosi a " - " (ADD.TOT/ADD.SPE) o fine stringa
_FAVORE_RE = re.compile(r"FAVORE\s+([A-Za-zÀ-ÿ'\. ]+?)(?:\s+NOTPROVIDE\b.*)?\s*(?:-|$)", re.I)


def _tokens(nome: str) -> frozenset:
    return frozenset(t for t in re.split(r"[^a-zà-ÿ']+", (nome or "").lower()) if len(t) > 1)


def estrai_nome_favore(descrizione: str) -> Optional[str]:
    """Il beneficiario del bonifico dalla descrizione dell'estratto conto."""
    if not descrizione or "COMM" in descrizione.upper()[:30]:
        return None  # le commissioni su bonifico non sono il pagamento
    m = _FAVORE_RE.search(descrizione)
    return m.group(1).strip() if m else None


def _nome_riga_stipendio(riga: Dict[str, Any]) -> str:
    nome = (riga.get("dipendente") or riga.get("dipendente_nome") or "").strip()
    if nome:
        return nome
    m = re.search(r"Stipendio\s+(.+?)\s*[-–]?\s*\d{2}/\d{4}", riga.get("descrizione") or "")
    return m.group(1).strip() if m else ""


def _importo_atteso(riga: Dict[str, Any]) -> float:
    return float(riga.get("importo_busta") or riga.get("importo") or 0)


async def associa_bonifici_stipendi(
    db, stipendio_id: Optional[str] = None
) -> Dict[str, Any]:
    """Associa i bonifici in estratto conto alle righe stipendio pendenti.

    Con `stipendio_id` lavora sulla sola riga indicata (bottone Conferma in
    Riconciliazione → Stipendi); senza, su tutte le pendenti (scheduler).
    """
    filtro = {"riconciliato": {"$ne": True}}
    if stipendio_id:
        filtro["id"] = stipendio_id
    righe = await db["prima_nota_salari"].find(filtro, {"_id": 0}).to_list(2000)

    per_nome: Dict[frozenset, List[Dict[str, Any]]] = {}
    for r in righe:
        toks = _tokens(_nome_riga_stipendio(r))
        if toks:
            per_nome.setdefault(toks, []).append(r)
    for gruppo in per_nome.values():
        gruppo.sort(key=lambda r: (r.get("anno") or 0, r.get("mese") or 0))

    # NB: l'import dell'estratto conto salva l'importo in valore ASSOLUTO
    # con campo tipo "entrata"/"uscita" — mai filtrare per importo negativo.
    movimenti = await db["estratto_conto_movimenti"].find(
        {"riconciliato": {"$ne": True},
         "$or": [{"descrizione": {"$regex": "FAVORE", "$options": "i"}},
                 {"descrizione_originale": {"$regex": "FAVORE", "$options": "i"}}]},
        {"_id": 0, "id": 1, "data": 1, "importo": 1, "tipo": 1,
         "descrizione": 1, "descrizione_originale": 1},
    ).sort("data", 1).to_list(10000)

    now = datetime.now(timezone.utc).isoformat()
    associati = righe_completate = 0
    dettaglio: List[Dict[str, Any]] = []

    for mov in movimenti:
        importo_grezzo = float(mov.get("importo") or 0)
        e_uscita = mov.get("tipo") == "uscita" or importo_grezzo < 0
        if not e_uscita:
            continue
        nome = estrai_nome_favore(
            mov.get("descrizione_originale") or mov.get("descrizione") or "")
        if not nome:
            continue
        gruppo = per_nome.get(_tokens(nome))
        if not gruppo:
            continue

        pendenti = [r for r in gruppo if not r.get("riconciliato")]
        if not pendenti:
            continue
        importo_mov = abs(importo_grezzo)
        mese_mov = (mov.get("data") or "")[:7]

        # priorità: stesso importo della busta → stesso mese → più vecchia
        riga = next((r for r in pendenti
                     if _importo_atteso(r) and abs(_importo_atteso(r) - importo_mov) < 0.01),
                    None)
        if riga is None:
            riga = next((r for r in pendenti
                         if f"{r.get('anno')}-{int(r.get('mese') or 0):02d}" == mese_mov),
                        pendenti[0])

        bonifici = float(riga.get("importo_bonifico") or 0) + importo_mov
        atteso = _importo_atteso(riga)
        completa = (not atteso) or bonifici >= atteso - 0.01

        await db["estratto_conto_movimenti"].update_one(
            {"id": mov["id"]},
            {"$set": {
                "riconciliato": True,
                "tipo_riconciliazione": "stipendio_auto_nome",
                "stipendio_id": riga["id"],
                "dipendente": _nome_riga_stipendio(riga),
                "categoria": "Stipendi",
                "data_riconciliazione": now,
            }})
        upd = {
            "importo_bonifico": round(bonifici, 2),
            "data_pagamento": (mov.get("data") or "")[:10],
            "pagato_con": "bonifico",
            "updated_at": now,
        }
        if completa:
            upd["riconciliato"] = True
        await db["prima_nota_salari"].update_one(
            {"id": riga["id"]},
            {"$set": upd, "$push": {"movimenti_bancari_ids": mov["id"]}})
        riga["importo_bonifico"] = bonifici
        riga["riconciliato"] = completa

        associati += 1
        if completa:
            righe_completate += 1
        if len(dettaglio) < 40:
            dettaglio.append({
                "dipendente": _nome_riga_stipendio(riga),
                "data_bonifico": (mov.get("data") or "")[:10],
                "importo": importo_mov,
                "stipendio_id": riga["id"],
                "riga_completata": completa,
            })

    return {
        "bonifici_associati": associati,
        "righe_stipendio_completate": righe_completate,
        "righe_pendenti_esaminate": len(righe),
        "dettaglio": dettaglio,
    }
