"""Classificazione prudente degli export bancari non ufficiali.

Questa fase non paga fatture, cedolini o assegni e non chiude il POS. Crea
soltanto un abbinamento operativo verificabile, che il PDF ufficiale potra'
promuovere a riconciliazione definitiva.
"""
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, Optional

from app.services.bank_evidence import STATO_ATTESA_UFFICIALE


def classifica_movimento_operativo(movimento: Dict[str, Any]) -> Optional[str]:
    testo = " ".join(str(movimento.get(k) or "") for k in (
        "categoria", "descrizione", "descrizione_originale"
    )).upper()
    tipo = str(movimento.get("tipo") or "").lower()
    if "ASSEGNO" in testo:
        return "assegno"
    if any(token in testo for token in ("STIPEND", "SALAR", "CEDOLIN", "EMOLUMENT")):
        return "cedolino"
    if tipo == "entrata" and any(token in testo for token in (
        "POS", "NUMIA", "NEXI", "BANCOMAT", "CARTE"
    )):
        return "pos"
    if tipo == "uscita" and any(token in testo for token in (
        "FATT", "SDD", "SEPA", "BONIFICO", "FORNITOR"
    )):
        return "fattura"
    return None


def _numero_assegno(testo: str) -> Optional[str]:
    match = re.search(r"ASSEGNO\D{0,20}(\d{5,16})", testo.upper())
    return match.group(1) if match else None


async def _candidato_univoco(db, movimento: Dict[str, Any], tipo: str) -> Optional[Dict[str, str]]:
    importo = abs(float(movimento.get("importo") or 0))
    testo = (movimento.get("descrizione_originale") or movimento.get("descrizione") or "").upper()
    if tipo == "assegno":
        numero = _numero_assegno(testo)
        if not numero:
            return None
        doc = await db["assegni"].find_one(
            {"$or": [{"numero": numero}, {"assegno_numero": numero}]}, {"_id": 0, "id": 1}
        )
        return {"collection": "assegni", "id": doc.get("id")} if doc and doc.get("id") else None

    if tipo == "fattura":
        docs = await db["invoices"].find({
            "pagato": {"$ne": True},
            "$or": [
                {"total_amount": {"$gte": importo - 0.01, "$lte": importo + 0.01}},
                {"importo_totale": {"$gte": importo - 0.01, "$lte": importo + 0.01}},
                {"importo_residuo": {"$gte": importo - 0.01, "$lte": importo + 0.01}},
            ],
        }, {"_id": 0, "id": 1, "supplier_name": 1, "invoice_number": 1,
            "fornitore_ragione_sociale": 1, "numero_fattura": 1}).to_list(20)
        forti = []
        testo_norm = re.sub(r"[^A-Z0-9]", "", testo)
        for doc in docs:
            numero = re.sub(r"[^A-Z0-9]", "", str(
                doc.get("invoice_number") or doc.get("numero_fattura") or ""
            ).upper()).lstrip("0")
            nome = str(doc.get("supplier_name") or doc.get("fornitore_ragione_sociale") or "").upper()
            tokens = [x for x in re.sub(r"[^A-Z0-9]", " ", nome).split() if len(x) >= 5]
            if (numero and len(numero) >= 4 and numero in testo_norm) or any(x in testo for x in tokens[:5]):
                forti.append(doc)
        return ({"collection": "invoices", "id": forti[0]["id"]}
                if len(forti) == 1 and forti[0].get("id") else None)

    collection = "prima_nota_salari" if tipo == "cedolino" else "prima_nota_cassa"
    query = {
        "importo": {"$gte": importo - 0.01, "$lte": importo + 0.01},
        "riconciliato": {"$ne": True},
    }
    if tipo == "pos":
        query["categoria"] = "POS"
    docs = await db[collection].find(query, {"_id": 0, "id": 1}).to_list(3)
    return ({"collection": collection, "id": docs[0]["id"]}
            if len(docs) == 1 and docs[0].get("id") else None)


async def annota_movimenti_operativi(db, ids: Iterable[str]) -> Dict[str, int]:
    ids = [item for item in ids if item]
    result = {"analizzati": 0, "classificati": 0, "abbinati_provvisori": 0}
    if not ids:
        return result
    movimenti = await db["estratto_conto_movimenti"].find(
        {"id": {"$in": ids}}, {"_id": 0}
    ).to_list(len(ids))
    now = datetime.now(timezone.utc).isoformat()
    for movimento in movimenti:
        result["analizzati"] += 1
        tipo = classifica_movimento_operativo(movimento)
        update: Dict[str, Any] = {
            "stato_riconciliazione": STATO_ATTESA_UFFICIALE,
            "in_attesa_estratto_ufficiale": True,
            "riconciliato": False,
            "updated_at": now,
        }
        if tipo:
            result["classificati"] += 1
            update["tipo_candidato_operativo"] = tipo
            candidato = await _candidato_univoco(db, movimento, tipo)
            if candidato:
                result["abbinati_provvisori"] += 1
                update.update({
                    "riconciliato_provvisoriamente": True,
                    "candidato_operativo": candidato,
                })
        await db["estratto_conto_movimenti"].update_one(
            {"id": movimento.get("id")}, {"$set": update}
        )
    return result
