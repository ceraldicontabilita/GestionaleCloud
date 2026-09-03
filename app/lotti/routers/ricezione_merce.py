"""
Scheda Ricezione Merce Avanzata — HACCP
Registra: fornitore, prodotto, lotto fornitore, temperatura ricezione,
conformità imballaggio, conformità etichettatura, azione correttiva, foto etichetta.
"""

from fastapi import APIRouter, HTTPException, Body
from datetime import datetime, timezone, timedelta
import uuid
import logging
import re

from app.lotti.db import database as db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ricezione-merce", tags=["Ricezione Merce"])

SOGLIE_TEMP = {
    "refrigerato": {"min": 0.0, "max": 4.0},
    "congelato": {"min": -25.0, "max": -15.0},
    "fresco": {"min": 0.0, "max": 8.0},
    "ambient": {"min": None, "max": None},
    "surgelato": {"min": -25.0, "max": -18.0},
}


def _check_temperatura(temp, tipo_prodotto):
    """Verifica se la temperatura è conforme in base al tipo prodotto."""
    if temp is None:
        return True  # non misurata = non verifica
    soglia = SOGLIE_TEMP.get(tipo_prodotto, SOGLIE_TEMP["refrigerato"])
    if soglia["min"] is None:
        return True
    return soglia["min"] <= temp <= soglia["max"]


@router.get("/oggi")
async def get_ricezioni_oggi():
    oggi = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    docs = await db.ricezioni_merce.find({"data": oggi}, {"_id": 0}).sort("ora", 1).to_list(200)
    return docs


@router.get("/storico")
async def get_storico_ricezioni(giorni: int = 30, fornitore_id: str = None):
    data_limite = (datetime.now(timezone.utc) - timedelta(days=giorni)).strftime("%Y-%m-%d")
    filtro = {"data": {"$gte": data_limite}}
    if fornitore_id:
        filtro["fornitore_id"] = fornitore_id
    docs = await db.ricezioni_merce.find(filtro, {"_id": 0}).sort("data", -1).to_list(1000)
    return docs


@router.get("/{ricezione_id}")
async def get_ricezione(ricezione_id: str):
    doc = await db.ricezioni_merce.find_one({"id": ricezione_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Ricezione non trovata")
    return doc


@router.post("/registra")
async def registra_ricezione(payload: dict = Body(...)):
    """
    Registra una ricezione merce.
    Payload:
      fornitore_id, fornitore_nome, prodotto, tipo_prodotto (refrigerato/congelato/fresco/ambient/surgelato),
      temperatura_ricezione, lotto_fornitore, data_scadenza_lotto, imballaggio_integro,
      etichetta_conforme, foto_etichetta_url, operatore, note, azione_correttiva
    """
    ora_utc = datetime.now(timezone.utc)

    temperatura = payload.get("temperatura_ricezione")
    tipo_prod = payload.get("tipo_prodotto", "refrigerato")
    temp_ok = _check_temperatura(temperatura, tipo_prod)
    imb_ok = payload.get("imballaggio_integro", True)
    etich_ok = payload.get("etichetta_conforme", True)

    conforme = temp_ok and imb_ok and etich_ok

    doc = {
        "id": str(uuid.uuid4()),
        "data": ora_utc.strftime("%Y-%m-%d"),
        "ora": ora_utc.strftime("%H:%M"),
        "fornitore_id": payload.get("fornitore_id"),
        "fornitore_nome": payload.get("fornitore_nome", ""),
        "prodotto": payload.get("prodotto", ""),
        "tipo_prodotto": tipo_prod,
        "temperatura_ricezione": temperatura,
        "temperatura_conforme": temp_ok,
        "lotto_fornitore": payload.get("lotto_fornitore", ""),
        "data_scadenza_lotto": payload.get("data_scadenza_lotto", ""),
        "imballaggio_integro": imb_ok,
        "etichetta_conforme": etich_ok,
        "foto_etichetta_url": payload.get("foto_etichetta_url", ""),
        "conforme": conforme,
        "azione_correttiva": payload.get("azione_correttiva", "") if not conforme else "",
        "accettato": payload.get("accettato", conforme),  # merce accettata o respinta
        "operatore": payload.get("operatore", ""),
        "note": payload.get("note", ""),
        "creato": ora_utc.isoformat(),
    }

    await db.ricezioni_merce.insert_one({**doc})

    # ── Chiudi ordine fornitore se presente ──────────────────────────────────
    # Cerca l'ordine inviato più recente per questo fornitore e lo marca come ricevuto
    try:
        fornitore_cerca = (doc["fornitore_nome"] or "").strip()[:15]
        if fornitore_cerca and doc.get("accettato", True):
            # Solo ordini realmente INVIATI: una consegna di routine non deve
            # chiudere bozze/confermati mai partiti. Regex escapata: un
            # fornitore con parentesi nel nome faceva fallire la query.
            rx_forn = re.escape(fornitore_cerca)
            ordine_aperto = await db.ordini_fornitori.find_one(
                {
                    "stato": {
                        "$in": ["inviato_fornitori", "inviato_manualmente",
                                "inviato", "ricevuto_parziale"]
                    },
                    "$or": [
                        {"prodotti.fornitore": {"$regex": rx_forn, "$options": "i"}},
                        {"fornitore": {"$regex": rx_forn, "$options": "i"}},
                    ],
                },
                sort=[("created_at", -1)],
            )
            if ordine_aperto:
                # Segna il prodotto specifico come ricevuto nell'ordine
                prodotti_aggiornati = []
                prodotto_ricevuto_nome = (doc["prodotto"] or "").lower()
                almeno_uno_aperto = False

                for p in ordine_aperto.get("prodotti", []):
                    nome_p = (p.get("nome") or "").lower()
                    match = (
                        prodotto_ricevuto_nome in nome_p
                        or nome_p in prodotto_ricevuto_nome
                        or any(w in nome_p for w in prodotto_ricevuto_nome.split() if len(w) > 3)
                    )
                    if match and not p.get("ricevuto"):
                        p["ricevuto"] = True
                        p["ricezione_id"] = doc["id"]
                        p["ricevuto_il"] = ora_utc.isoformat()
                    if not p.get("ricevuto"):
                        almeno_uno_aperto = True
                    prodotti_aggiornati.append(p)

                nuovo_stato = "ricevuto" if not almeno_uno_aperto else "ricevuto_parziale"
                await db.ordini_fornitori.update_one(
                    {"id": ordine_aperto["id"]},
                    {
                        "$set": {
                            "prodotti": prodotti_aggiornati,
                            "stato": nuovo_stato,
                            "ultima_ricezione_id": doc["id"],
                            "ultima_ricezione_il": ora_utc.isoformat(),
                            "updated_at": ora_utc.isoformat(),
                        }
                    },
                )
                doc["ordine_id_aggiornato"] = ordine_aperto["id"]
                doc["ordine_stato"] = nuovo_stato
    except Exception as _oe:
        # Non blocca la ricezione, ma NON resta muto: se la riconciliazione
        # dell'ordine fallisce l'ordine resta "inviato" e i prodotti non
        # risultano ricevuti — va visto nei log, non ingoiato in silenzio.
        logger.warning(f"[Ricezione] Chiusura ordine collegato fallita: {_oe}")

    # Se il lotto è specificato, lo crea automaticamente in lotti_fornitori
    if doc["lotto_fornitore"] and doc["accettato"]:
        lotto_doc = {
            "id": str(uuid.uuid4()),
            "fornitore_id": doc["fornitore_id"],
            "fornitore_nome": doc["fornitore_nome"],
            "prodotto": doc["prodotto"],
            "lotto": doc["lotto_fornitore"],
            "data_ricezione": doc["data"],
            "data_scadenza": doc["data_scadenza_lotto"],
            "quantita": payload.get("quantita", ""),
            "unita": payload.get("unita", ""),
            "note": doc["note"],
            "creato": ora_utc.isoformat(),
        }
        await db.lotti_fornitori.insert_one({**lotto_doc})

    # ── Reclamo automatico se non conforme o respinta ────────────────────────
    if not conforme or not doc.get("accettato", True):
        try:
            from app.lotti.routers.reclami_fornitori import crea_reclamo_da_ricezione

            await crea_reclamo_da_ricezione(doc)
        except Exception as _re:
            logger.warning(f"[Ricezione] Reclamo automatico fallito: {_re}")

    return {
        "success": True,
        "id": doc["id"],
        "conforme": conforme,
        "temp_conforme": temp_ok,
        "ordine_stato": doc.get("ordine_stato"),
    }


@router.patch("/{ricezione_id}")
async def aggiorna_ricezione(ricezione_id: str, payload: dict = Body(...)):
    result = await db.ricezioni_merce.update_one(
        {"id": ricezione_id}, {"$set": {k: v for k, v in payload.items() if k not in ("id", "_id")}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Ricezione non trovata")
    return {"success": True}


@router.delete("/{ricezione_id}")
async def elimina_ricezione(ricezione_id: str):
    await db.ricezioni_merce.delete_one({"id": ricezione_id})
    return {"success": True}


@router.get("/statistiche/riepilogo")
async def statistiche_ricezioni(giorni: int = 30):
    data_limite = (datetime.now(timezone.utc) - timedelta(days=giorni)).strftime("%Y-%m-%d")
    docs = await db.ricezioni_merce.find({"data": {"$gte": data_limite}}, {"_id": 0}).to_list(2000)

    totale = len(docs)
    non_conformi = sum(1 for d in docs if not d.get("conforme", True))
    respinti = sum(1 for d in docs if not d.get("accettato", True))

    return {
        "totale_ricezioni": totale,
        "conformi": totale - non_conformi,
        "non_conformi": non_conformi,
        "merci_respinte": respinti,
        "percentuale_conformita": (
            round((totale - non_conformi) / totale * 100, 1) if totale else 100
        ),
    }


@router.get("/da-fatture/ultimi-arrivi")
async def get_prodotti_da_fatture(giorni: int = 30):
    """
    Legge i lotti fornitori dalle fatture XML recenti e li propone per la ricezione merce.
    Restituisce i prodotti con lotto, scadenza, fornitore per ogni fattura.
    Esclude quelli già registrati come ricezione oggi e i fornitori esclusi.
    """
    data_limite = (datetime.now(timezone.utc) - timedelta(days=giorni)).strftime("%Y-%m-%d")
    oggi = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Fornitori esclusi
    esclusi_docs = await db.fornitori.find({"escluso": True}, {"nome": 1, "_id": 0}).to_list(500)
    esclusi_nomi = {f["nome"].strip().lower() for f in esclusi_docs}

    # Carica lotti fornitori recenti
    lotti = (
        await db.lotti_fornitori.find({"created_at": {"$gte": data_limite}}, {"_id": 0})
        .sort("created_at", -1)
        .to_list(500)
    )

    # Carica ricezioni già fatte
    ricezioni_oggi = await db.ricezioni_merce.find(
        {"data": oggi}, {"lotto_fornitore": 1, "_id": 0}
    ).to_list(200)
    lotti_gia_ricevuti = {r.get("lotto_fornitore", "") for r in ricezioni_oggi}

    result = []
    seen = set()
    for lotto in lotti:
        fornitore = (lotto.get("fornitore", "") or "").strip()
        # Escludi fornitori segnati come esclusi
        if fornitore.lower() in esclusi_nomi:
            continue

        chiave = f"{lotto.get('lotto_id_fornitore','')}-{lotto.get('prodotto_nome','')}"
        if chiave in seen:
            continue
        seen.add(chiave)

        lotto_id = lotto.get("lotto_id_fornitore", "")
        gia_ricevuto = lotto_id in lotti_gia_ricevuti

        # Deduce tipo prodotto dal nome
        nome = (lotto.get("prodotto_nome") or "").lower()
        tipo_prodotto = "refrigerato"
        if any(k in nome for k in ["surgel", "frozen", "congelat"]):
            tipo_prodotto = "surgelato"
        elif any(
            k in nome for k in ["secco", "ambient", "farina", "olio", "sale", "zucchero", "pasta"]
        ):
            tipo_prodotto = "ambient"
        elif any(k in nome for k in ["panna", "burro", "latte", "uova", "formaggi", "yogurt"]):
            tipo_prodotto = "refrigerato"

        result.append(
            {
                "lotto_id": lotto_id,
                "fornitore": fornitore,
                "prodotto_nome": lotto.get("prodotto_nome", ""),
                "data_scadenza": lotto.get("data_scadenza", ""),
                "giorni_alla_scadenza": lotto.get("giorni_alla_scadenza"),
                "fattura_ref": lotto.get("fattura_ref", ""),
                "data_fattura": lotto.get("data_fattura", ""),
                "quantita_disponibile": lotto.get("quantita_disponibile", 0),
                "unita_misura": lotto.get("unita_misura", ""),
                "tipo_prodotto_suggerito": tipo_prodotto,
                "gia_ricevuto_oggi": gia_ricevuto,
            }
        )

    return result
