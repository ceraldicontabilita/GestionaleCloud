"""Il beneficiario di un assegno collegato a fatture è il loro fornitore.

Il collegamento (auto-match o «Scegli manualmente») scriveva il fornitore solo
in `fornitore_ragione_sociale`, e la stampa legge `beneficiario`: gli assegni
già collegati prima della correzione escono senza beneficiario. Qui si
ricompilano, da soli nel giro bancario corto, solo se tutte le fatture
collegate sono di un unico fornitore; un beneficiario già scritto non si tocca.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

_VUOTI = {"", "-", "n/a", "non disponibile"}


def _vuoto(valore: Any) -> bool:
    return str(valore or "").strip().lower() in _VUOTI


def _fornitore(fattura: Dict[str, Any]) -> str:
    return str(fattura.get("supplier_name") or fattura.get("cedente_denominazione") or "").strip()


def _id_possibili(fid: Any) -> List[Any]:
    """Su `invoices` l'`id` e' un numero in meta' delle righe e un testo nelle altre."""
    testo = str(fid)
    return [testo, int(testo)] if testo.isdigit() else [testo]


def _chiave(fattura: Dict[str, Any]) -> str:
    return str(
        fattura.get("supplier_id") or fattura.get("supplier_vat") or fattura.get("cedente_piva")
        or _fornitore(fattura).upper()
    )


async def ricompila_beneficiari_da_fatture(db, *, dry_run: bool = False) -> Dict[str, Any]:
    assegni = await db["assegni"].find(
        {},
        {"_id": 0, "id": 1, "numero": 1, "beneficiario": 1, "fatture_collegate": 1,
         "fornitore_ragione_sociale": 1},
    ).to_list(5000)
    da_fare = [a for a in assegni if a.get("fatture_collegate") and _vuoto(a.get("beneficiario"))]

    aggiornati: List[Dict[str, Any]] = []
    ambigui = 0
    for assegno in da_fare:
        fatture = []
        for quota in assegno.get("fatture_collegate") or []:
            fid = quota.get("fattura_id") if isinstance(quota, dict) else None
            if not fid:
                continue
            fattura = await db["invoices"].find_one(
                {"id": {"$in": _id_possibili(fid)}},
                {"_id": 0, "supplier_id": 1, "supplier_name": 1, "supplier_vat": 1,
                 "cedente_denominazione": 1, "cedente_piva": 1},
            )
            if fattura and _fornitore(fattura):
                fatture.append(fattura)
        if not fatture:
            continue
        if len({_chiave(f) for f in fatture}) != 1:
            ambigui += 1
            continue
        nome = _fornitore(fatture[0])
        aggiornati.append({"assegno_id": assegno["id"], "numero": assegno.get("numero"), "beneficiario": nome})
        if dry_run:
            continue
        adesso = datetime.now(timezone.utc).isoformat()
        await db["assegni"].update_one(
            {"id": assegno["id"]},
            {"$set": {"beneficiario": nome, "updated_at": adesso},
             "$push": {"storico": {
                 "at": adesso, "azione": "beneficiario_da_fattura",
                 "campi": {"beneficiario": {"prima": assegno.get("beneficiario"), "dopo": nome}},
                 "motivo": "fornitore della fattura collegata",
             }}},
        )
    return {"esaminati": len(da_fare), "aggiornati": len(aggiornati), "ambigui": ambigui,
            "assegni": aggiornati, "dry_run": dry_run}
