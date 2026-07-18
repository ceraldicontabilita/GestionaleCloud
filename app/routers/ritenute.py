"""
RITENUTE D'ACCONTO — richiesta utente 18/07/2026.

"Tra le fatture se trovi RT01 Ritenuta persone fisiche devi crearmi una
sezione ritenute: nella fattura c'è un importo, lo memorizzi e mi ricordi
che è da pagare entro il giorno 16 del mese successivo. La commercialista
invia un F24 con codice tributo 1040: lo trovi e lo associ. Se l'importo è
pagato leggendo l'estratto conto, riconcili con flag pagato alla scadenza;
altrimenti scrivi la data reale di pagamento. Se il pagamento non è
puntuale, guarda se nell'F24 c'è il codice tributo del ravvedimento e
scrivi 'pagato con ravvedimento'."

Flusso: la fattura XML con DatiRitenuta (RT01 persone fisiche / RT02
società) genera una riga in `ritenute_acconto` con scadenza il 16 del mese
successivo alla data fattura. La riconciliazione cerca l'F24 con codice
1040 e stesso importo, ne legge lo stato di pagamento (quietanza/estratto
conto — mai ricostruito, come da SPECIFICA F24) e classifica: puntuale,
con ravvedimento (codici 8906 sanzione + 1989 interessi), in ritardo senza
ravvedimento (alert).
"""
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query

from app.database import Database
from app.utils.error_handler import handle_errors

logger = logging.getLogger(__name__)
router = APIRouter()

COLLECTION = "ritenute_acconto"

# Ravvedimento operoso per ritenute (fonte: Agenzia delle Entrate,
# risoluzioni sui codici tributo; logica art. 13 D.Lgs. 472/1997):
# la sanzione ridotta e gli interessi legali si versano nello STESSO F24
# del tributo tardivo, con codici dedicati.
CODICI_RAVVEDIMENTO_RITENUTE = {
    "8906": "Sanzione pecuniaria sostituti d'imposta (ravvedimento su ritenute, es. 1040)",
    "1989": "Interessi sul ravvedimento - IRPEF e ritenute",
}
LOGICA_RAVVEDIMENTO = (
    "Ravvedimento operoso (art. 13 D.Lgs. 472/1997): se la ritenuta non è "
    "versata entro il 16 del mese successivo, si può regolarizzare pagando "
    "il tributo (1040) più la sanzione ridotta (codice 8906) e gli "
    "interessi legali (codice 1989) nello stesso F24. Sanzione ridotta: "
    "0,083%/giorno fino a 14 giorni (ravvedimento sprint), 1,25% entro 30 "
    "giorni, 1,39% entro 90 giorni, 3,125% entro 1 anno."
)

TIPI_RITENUTA = {"RT01": "Ritenuta persone fisiche", "RT02": "Ritenuta persone giuridiche"}


def _scadenza_16_mese_successivo(data_iso: str) -> str:
    anno, mese = int(data_iso[:4]), int(data_iso[5:7])
    mese += 1
    if mese == 13:
        mese, anno = 1, anno + 1
    return f"{anno}-{mese:02d}-16"


def _estrai_dati_ritenuta(xml_raw) -> Optional[Dict[str, Any]]:
    """Estrae DatiRitenuta dall'XML (regex: regge anche i .p7m sporchi)."""
    if not xml_raw:
        return None
    testo = xml_raw if isinstance(xml_raw, str) else str(xml_raw)
    blocco = re.search(r"<DatiRitenuta>(.*?)</DatiRitenuta>", testo, re.S)
    if not blocco:
        return None
    b = blocco.group(1)

    def campo(tag):
        m = re.search(rf"<{tag}>\s*([^<]+?)\s*</{tag}>", b)
        return m.group(1) if m else None

    try:
        importo = float(campo("ImportoRitenuta") or 0)
    except ValueError:
        return None
    if importo <= 0:
        return None
    return {
        "tipo": campo("TipoRitenuta") or "RT01",
        "importo": round(importo, 2),
        "aliquota": campo("AliquotaRitenuta"),
        "causale": campo("CausalePagamento"),
    }


def _tributi_di(f24: Dict[str, Any]) -> List[Dict[str, Any]]:
    """f24_unificato ha più schemi coesistenti: normalizza la lista tributi."""
    out = []
    for t in (f24.get("tributi") or f24.get("righe") or f24.get("dettaglio_tributi") or []):
        if isinstance(t, dict):
            out.append({
                "codice": str(t.get("codice") or t.get("codice_tributo") or "").strip(),
                "importo": float(t.get("importo") or t.get("importo_debito") or t.get("debito") or 0),
            })
    for c in (f24.get("codici_tributo") or []):
        out.append({"codice": str(c).strip(), "importo": None})
    return out


def _data_pagamento_f24(f24: Dict[str, Any]) -> Optional[str]:
    for k in ("data_pagamento", "data_versamento", "data_quietanza", "data_addebito"):
        if f24.get(k):
            return str(f24[k])[:10]
    ric = f24.get("riconciliazione") or {}
    if isinstance(ric, dict) and ric.get("data"):
        return str(ric["data"])[:10]
    return None


def _f24_risulta_pagato(f24: Dict[str, Any]) -> bool:
    if _data_pagamento_f24(f24):
        return True
    stato = str(f24.get("stato") or f24.get("stato_pagamento") or "").lower()
    return bool(f24.get("pagato")) or stato in ("pagato", "quietanzato", "pagata")


async def _riconcilia_ritenuta(db, rit: Dict[str, Any]) -> Dict[str, Any]:
    """Cerca l'F24 col codice 1040 e lo stesso importo; classifica lo stato."""
    oggi = datetime.now(timezone.utc).date().isoformat()
    upd: Dict[str, Any] = {}

    f24_match = None
    tributo_1040 = None
    async for f24 in db["f24_unificato"].find({}, {"_id": 0}):
        for t in _tributi_di(f24):
            if t["codice"] == "1040" and (
                t["importo"] is None or abs(t["importo"] - rit["importo"]) < 0.01
            ):
                f24_match = f24
                tributo_1040 = t
                break
        if f24_match:
            break

    if not f24_match:
        upd["stato"] = "scaduta_da_versare" if oggi > rit["scadenza"] else "da_pagare"
        upd["f24_id"] = None
        return upd

    upd["f24_id"] = f24_match.get("id")
    upd["f24_descrizione"] = (f24_match.get("descrizione") or f24_match.get("filename") or "")[:120]

    if not _f24_risulta_pagato(f24_match):
        upd["stato"] = "f24_associato_da_pagare"
        return upd

    data_pag = _data_pagamento_f24(f24_match) or rit["scadenza"]
    upd["data_pagamento"] = data_pag
    if data_pag <= rit["scadenza"]:
        upd["stato"] = "pagata_puntuale"
    else:
        codici = {t["codice"] for t in _tributi_di(f24_match)}
        if codici & set(CODICI_RAVVEDIMENTO_RITENUTE):
            upd["stato"] = "pagata_con_ravvedimento"
        else:
            upd["stato"] = "pagata_in_ritardo_senza_ravvedimento"
    return upd


@router.post("/scan")
@handle_errors
async def scan_ritenute(anno: int = Query(2026)) -> Dict[str, Any]:
    """Estrae le ritenute dalle fatture XML dell'anno (idempotente per
    fattura) e le riconcilia con gli F24 disponibili."""
    db = Database.get_db()
    fatture = await db["invoices"].find(
        {"invoice_date": {"$regex": f"^{anno}"},
         "status": {"$nin": ["deleted", "archived"]},
         "xml_raw": {"$regex": "DatiRitenuta"}},
        {"_id": 0, "id": 1, "invoice_number": 1, "invoice_date": 1,
         "supplier_name": 1, "supplier_vat": 1, "cedente_piva": 1, "xml_raw": 1},
    ).to_list(5000)

    nuove = aggiornate = 0
    for f in fatture:
        dati = _estrai_dati_ritenuta(f.get("xml_raw"))
        if not dati:
            continue
        base = {
            "fattura_id": f["id"],
            "numero_fattura": f.get("invoice_number"),
            "data_fattura": (f.get("invoice_date") or "")[:10],
            "fornitore": f.get("supplier_name"),
            "piva": f.get("supplier_vat") or f.get("cedente_piva"),
            "tipo": dati["tipo"],
            "tipo_label": TIPI_RITENUTA.get(dati["tipo"], dati["tipo"]),
            "importo": dati["importo"],
            "aliquota": dati["aliquota"],
            "causale": dati["causale"],
            "scadenza": _scadenza_16_mese_successivo((f.get("invoice_date") or "")[:10]),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        esistente = await db[COLLECTION].find_one({"fattura_id": f["id"]})
        rit = {**base, "id": esistente["id"] if esistente else str(uuid.uuid4())}
        upd = await _riconcilia_ritenuta(db, rit)
        rit.update(upd)
        if esistente:
            await db[COLLECTION].update_one({"id": rit["id"]}, {"$set": rit})
            aggiornate += 1
        else:
            rit["created_at"] = rit["updated_at"]
            await db[COLLECTION].insert_one(dict(rit))
            nuove += 1

    return {"anno": anno, "fatture_con_ritenuta": len(fatture),
            "nuove": nuove, "aggiornate": aggiornate}


@router.get("")
@handle_errors
async def lista_ritenute(anno: int = Query(2026)) -> Dict[str, Any]:
    """Sezione Ritenute: elenco con scadenze, F24 associato e stato."""
    db = Database.get_db()
    ritenute = await db[COLLECTION].find(
        {"data_fattura": {"$regex": f"^{anno}"}}, {"_id": 0}
    ).sort("scadenza", -1).to_list(2000)
    oggi = datetime.now(timezone.utc).date().isoformat()
    per_stato: Dict[str, int] = {}
    for r in ritenute:
        # lo stato "da_pagare" scivola in "scaduta" col passare del tempo
        if r.get("stato") == "da_pagare" and oggi > (r.get("scadenza") or "9999"):
            r["stato"] = "scaduta_da_versare"
        per_stato[r.get("stato") or "?"] = per_stato.get(r.get("stato") or "?", 0) + 1
    return {
        "anno": anno,
        "ritenute": ritenute,
        "totale_importo": round(sum(r.get("importo", 0) for r in ritenute), 2),
        "per_stato": per_stato,
        "logica_ravvedimento": LOGICA_RAVVEDIMENTO,
    }


@router.get("/codici-ravvedimento")
@handle_errors
async def codici_ravvedimento() -> Dict[str, Any]:
    """Sezione codici tributo: i codici del ravvedimento e la logica."""
    return {"codici": CODICI_RAVVEDIMENTO_RITENUTE, "logica": LOGICA_RAVVEDIMENTO}
