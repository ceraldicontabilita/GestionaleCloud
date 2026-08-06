"""Handler cespiti — reagisce a fattura.created per creare automaticamente i
cespiti dalle righe fattura che superano la soglia e riconoscono una
categoria ammortizzabile nota. Richiesta utente 15/07/2026: le attrezzature
individuate nelle fatture XML devono confluire da sole nel registro cespiti,
non solo con lo scan manuale ("Scan Fatture XML" in Cespiti & TFR).

Riusa la STESSA logica di POST /api/cespiti/scan-fatture (keyword map,
soglia 200€, stesso schema di cespite) in modo che scan manuale e trigger
automatico non divergano mai: il manuale resta utile per il backfill di
fatture importate prima di questo handler.
"""
import logging
from datetime import date, datetime, timezone
from typing import Any, Dict
from uuid import uuid4

logger = logging.getLogger(__name__)

SOGLIA_VALORE = 200


async def handler_auto_cespite_da_fattura(payload: Dict[str, Any], db) -> Dict[str, Any]:
    if db is None:
        return {"skipped": True, "reason": "db non disponibile"}

    from app.routers.cespiti import classify_asset, CATEGORIE_CESPITI, _source_key_fattura

    righe = payload.get("righe_linee") or []
    if not righe:
        return {"skipped": True, "reason": "nessuna riga fattura"}

    fattura_id = payload.get("fattura_id")
    if not fattura_id:
        return {"skipped": True, "reason": "fattura_id mancante: provenienza non verificabile"}
    fornitore = payload.get("fornitore_ragione_sociale")
    data_acquisto = str(payload.get("data_documento") or "")[:10]
    try:
        data_acquisto = date.fromisoformat(data_acquisto).isoformat()
    except (TypeError, ValueError):
        return {"skipped": True, "reason": "data_documento mancante o non valida"}
    anno_acquisto = int(data_acquisto[:4])

    creati = []
    occorrenze = {}
    for riga in righe:
        descrizione = str(riga.get("descrizione") or riga.get("description") or "").strip()
        try:
            prezzo = float(riga.get("prezzo_totale") or riga.get("importo") or riga.get("price_total") or 0)
        except (TypeError, ValueError):
            continue
        if not descrizione or prezzo < SOGLIA_VALORE:
            continue

        categoria = classify_asset(descrizione, prezzo)
        if not categoria:
            continue

        signature = (" ".join(descrizione.casefold().split()), round(prezzo, 2))
        occorrenza = occorrenze.get(signature, 0)
        occorrenze[signature] = occorrenza + 1
        source_key = _source_key_fattura(fattura_id, descrizione, prezzo, occorrenza)
        esistente = await db["cespiti"].find_one({"source_key": source_key})
        if not esistente:
            # Compatibilita con i record antecedenti alla source_key, ma solo
            # nella stessa fattura: acquisti distinti non vanno confusi.
            esistente = await db["cespiti"].find_one({
                "fattura_id": fattura_id,
                "source_key": {"$exists": False},
                "descrizione": descrizione[:200],
                "valore_acquisto": round(prezzo, 2),
            })
        if esistente:
            continue

        cat_info = CATEGORIE_CESPITI.get(categoria, {"descrizione": categoria, "coefficiente": 15, "vita_utile": 7})
        cespite = {
            "id": str(uuid4()),
            "descrizione": descrizione[:200],
            "categoria": categoria,
            "categoria_descrizione": cat_info["descrizione"],
            "coefficiente_ammortamento": cat_info["coefficiente"],
            "vita_utile_anni": cat_info["vita_utile"],
            "data_acquisto": data_acquisto,
            "anno_acquisto": anno_acquisto,
            "valore_acquisto": round(prezzo, 2),
            "valore_residuo": round(prezzo, 2),
            "fondo_ammortamento": 0,
            "fornitore": fornitore,
            "fattura_id": fattura_id,
            "numero_fattura": payload.get("numero_documento"),
            "source_key": source_key,
            "provenienza": "fattura_xml",
            "data_entrata_funzione": None,
            "anno_entrata_funzione": None,
            "provenienza_entrata_funzione": "da_confermare",
            "note": "Auto-estratto da fattura XML (automatico all'import)",
            "stato": "attivo",
            "ammortamento_completato": False,
            "piano_ammortamento": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        result = await db["cespiti"].update_one(
            {"source_key": source_key},
            {"$setOnInsert": cespite.copy()},
            upsert=True,
        )
        if result.upserted_id is not None:
            creati.append(cespite["id"])

    if not creati:
        return {"skipped": True, "reason": "nessuna riga sopra soglia con categoria riconosciuta"}

    logger.info(f"[HandlerCespiti] Fattura {fattura_id}: {len(creati)} cespiti auto-creati")
    return {"cespiti_creati": creati}
