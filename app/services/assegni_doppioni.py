"""Lo stesso assegno registrato due volte: una scheda resta, la copia va in quarantena.

Un numero di assegno esiste una sola volta sul carnet. Due schede con lo
stesso numero (zeri iniziali compresi) e lo stesso importo al centesimo sono
lo stesso assegno letto da due export della banca (data operazione e data
valuta, 1-5 giorni di scarto): in produzione erano 19 coppie, e la copia
orfana a volte portava il collegamento alla fattura che la scheda buona non
aveva. Stesso numero con importo diverso non si tocca: si segnala.

Resta la scheda il cui movimento e' ancora nell'estratto conto, poi quella
con la riga di Prima Nota, poi la piu' vecchia. La copia cede alla scheda
che resta le fatture che solo lei aveva, i riferimenti (Prima Nota,
movimento, proposte, fatture) passano all'id che resta, poi la copia va in
``assegni_quarantena`` con ``duplicato_di`` (``doppioni_archivio``): niente
si cancella senza lasciarne copia.
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from app.services.doppioni_archivio import _ricollega, centesimi, sposta_nella_cartella
from app.utils.id_fattura import filtro_id

logger = logging.getLogger(__name__)

COLL = "assegni"
MOTIVO = "assegno_doppio_stesso_numero_e_importo"
# Collezioni che citano l'assegno per id in un campo semplice.
RIFERIMENTI = (
    ("prima_nota_banca", "assegno_id"),
    ("estratto_conto_movimenti", "assegno_id"),
    ("proposte_associazione_assegni", "assegno_id"),
)


def identita(doc: Dict[str, Any]) -> Optional[Tuple[str, int]]:
    from app.services.carnet_assegni import numero_canonico

    numero = re.sub(r"\D", "", numero_canonico(doc.get("numero")))
    importo = centesimi(doc.get("importo"))
    importo = abs(importo) if importo else None
    if not numero or not importo:
        return None
    return numero, importo


def _fatture(doc: Dict[str, Any]) -> List[str]:
    ids = [str(q.get("fattura_id")) for q in doc.get("fatture_collegate") or []
           if isinstance(q, dict) and q.get("fattura_id")]
    for campo in ("fattura_collegata", "fattura_id"):
        if doc.get(campo) and str(doc[campo]) not in ids:
            ids.append(str(doc[campo]))
    return ids


def _punteggio(doc: Dict[str, Any], movimenti_attivi: set) -> Tuple:
    movimento = doc.get("movimento_estratto_conto_id") or doc.get("movimento_id")
    return (
        0 if movimento and movimento in movimenti_attivi else 1,
        0 if doc.get("prima_nota_banca_id") else 1,
        0 if _fatture(doc) else 1,
        str(doc.get("created_at") or ""),
    )


def gruppi(assegni: List[Dict[str, Any]], movimenti_attivi: set) -> Dict[str, List]:
    """{"unibili": [(resta, copie)], "in_conflitto": [...]} senza scrivere."""
    per_chiave: Dict[Tuple, List[Dict[str, Any]]] = defaultdict(list)
    for a in assegni:
        if a.get("entity_status") == "deleted":
            continue
        chiave = identita(a)
        if chiave and a.get("id"):
            per_chiave[chiave].append(a)
    unibili, in_conflitto = [], []
    for chiave, copie in per_chiave.items():
        if len(copie) < 2:
            continue
        ordinate = sorted(copie, key=lambda d: _punteggio(d, movimenti_attivi))
        resta, altre = ordinate[0], ordinate[1:]
        # Due schede che pagano fatture diverse non si fondono da sole.
        insiemi = {tuple(sorted(_fatture(d))) for d in copie if _fatture(d)}
        if len(insiemi) > 1:
            in_conflitto.append({"numero": chiave[0], "importo": chiave[1] / 100,
                                 "assegni": [d["id"] for d in copie],
                                 "fatture": [list(i) for i in insiemi]})
            continue
        unibili.append((resta, altre))
    return {"unibili": unibili, "in_conflitto": in_conflitto}


async def _cedi_fatture(db, resta: Dict[str, Any], copia: Dict[str, Any]) -> bool:
    """Se solo la copia paga delle fatture, il collegamento passa alla scheda che resta."""
    if _fatture(resta) or not _fatture(copia):
        return False
    campi = {k: copia.get(k) for k in (
        "fatture_collegate", "fattura_collegata", "fattura_id", "numero_fattura", "data_fattura",
        "importo_assegnato", "fornitore_piva", "fornitore_ragione_sociale", "beneficiario",
        "match_livello", "match_auto",
    ) if copia.get(k) not in (None, "", [])}
    await db[COLL].update_one({"id": resta["id"]}, {"$set": campi})
    for fid in _fatture(copia):
        inv = await db["invoices"].find_one(filtro_id(fid), {"_id": 0, "assegni_collegati": 1})
        links = (inv or {}).get("assegni_collegati") or []
        nuovi, cambiato = [], False
        for link in links:
            if isinstance(link, dict) and link.get("assegno_id") == copia["id"]:
                link = {**link, "assegno_id": resta["id"]}
                cambiato = True
            nuovi.append(link)
        if cambiato:
            await db["invoices"].update_one(filtro_id(fid), {"$set": {"assegni_collegati": nuovi}})
    return True


async def unifica(db, *, dry_run: bool = False, actor: str = "sistema") -> Dict[str, Any]:
    assegni = await db[COLL].find({}, {"_id": 0}).to_list(None)
    movimenti = await db["estratto_conto_movimenti"].find(
        {"$or": [{"descrizione": {"$regex": "ASSEGNO", "$options": "i"}},
                 {"descrizione_originale": {"$regex": "ASSEGNO", "$options": "i"}}]},
        {"_id": 0, "id": 1},
    ).to_list(None)
    esito = gruppi(assegni, {m["id"] for m in movimenti if m.get("id")})
    risultato: Dict[str, Any] = {
        "dry_run": dry_run, "coppie": len(esito["unibili"]),
        "copie": sum(len(c) for _, c in esito["unibili"]),
        "fatture_cedute": 0, "riferimenti_ricollegati": 0,
        "in_conflitto": esito["in_conflitto"],
        "esempi": [{"numero": r.get("numero"), "resta": r["id"], "copie": [c["id"] for c in cc]}
                   for r, cc in esito["unibili"][:20]],
    }
    if dry_run:
        return risultato
    for resta, copie in esito["unibili"]:
        for copia in copie:
            if await _cedi_fatture(db, resta, copia):
                risultato["fatture_cedute"] += 1
                resta = await db[COLL].find_one({"id": resta["id"]}, {"_id": 0}) or resta
            for collezione, campo in RIFERIMENTI:
                risultato["riferimenti_ricollegati"] += await _ricollega(
                    db, collezione, campo, copia["id"], resta["id"])
            await sposta_nella_cartella(db, COLL, copia, resta["id"], motivo=MOTIVO, actor=actor)
    if risultato["copie"]:
        logger.info("[assegni] %s copie in %s_quarantena, %s fatture cedute, %s in conflitto",
                    risultato["copie"], COLL, risultato["fatture_cedute"], len(esito["in_conflitto"]))
    return risultato
