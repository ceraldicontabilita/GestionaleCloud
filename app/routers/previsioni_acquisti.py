"""
Sistema Previsioni Acquisti
Statistiche e previsioni sulle quantità acquistate, dallo storico di magazzino.

Lo storico sta in `acquisti_prodotti`, scritto da
`services/handlers/magazzino_handlers.py` all'import di ogni fattura, con
questa forma (l'unica che esiste sui dati veri):

    {id, prodotto_id, fattura_id, fornitore_id, quantita, prezzo_unitario,
     unita_misura, data}

Fino al 27/09/2026 questo modulo aggregava su campi che **nessuna riga ha**
(`anno`, `descrizione_normalizzata`, `descrizione`, `totale_linea`,
`data_fattura`): ogni statistica e ogni previsione tornava vuota. Ora:

- il prodotto è `prodotto_id`, il nome viene da `warehouse_inventory`;
- l'anno e la data sono quelli della fattura (`invoice_date` via
  `fattura_id`), non `data`, che è il momento dell'elaborazione;
- la spesa è `quantita × prezzo_unitario`;
- contano solo le fatture attive (le copie `archived` raddoppiavano) e mai
  le note di credito, che sono resi e non acquisti.
"""

from fastapi import APIRouter, Query, HTTPException
from typing import Any, Dict, Iterable, List, Optional, Set
from datetime import datetime, timezone
import logging
import re
import uuid

from app.database import Database
from app.services.fattura_attiva import FILTRO_FATTURA_ATTIVA, e_nota_credito

logger = logging.getLogger(__name__)
router = APIRouter()

# Giorni lavorativi annuali per calcolo medie
GIORNI_LAVORATIVI_ANNO = 340
GIORNI_SETTIMANA = 7

COLL_ACQUISTI = "acquisti_prodotti"
COLL_PRODOTTI = "warehouse_inventory"

_PROIEZIONE_FATTURA = {
    "_id": 0, "id": 1, "invoice_date": 1, "supplier_name": 1,
    "tipo_documento": 1, "document_type": 1, "tipoDocumento": 1, "document_role": 1,
}


def _numero(valore: Any) -> float:
    try:
        return float(valore or 0)
    except (TypeError, ValueError):
        return 0.0


async def _righe_acquisto(db, anni: Optional[Set[int]] = None) -> List[Dict[str, Any]]:
    """Le righe dello storico, arricchite con la fattura e il prodotto.

    Tre letture in blocco (storico, fatture, prodotti), mai una per riga.
    Una riga la cui fattura non è attiva, o è una nota di credito, non entra.
    """
    righe = await db[COLL_ACQUISTI].find(
        {"prodotto_id": {"$exists": True, "$nin": [None, ""]}},
        {"_id": 0, "prodotto_id": 1, "fattura_id": 1, "quantita": 1,
         "prezzo_unitario": 1, "unita_misura": 1},
    ).to_list(None)
    fattura_ids = sorted({r.get("fattura_id") for r in righe if r.get("fattura_id")})
    if not fattura_ids:
        return []

    fatture = await db["invoices"].find(
        {"$and": [dict(FILTRO_FATTURA_ATTIVA), {"id": {"$in": fattura_ids}}]},
        _PROIEZIONE_FATTURA,
    ).to_list(None)
    per_fattura = {
        f["id"]: f for f in fatture
        if f.get("id") and not e_nota_credito(f)
    }

    prodotto_ids = sorted({r["prodotto_id"] for r in righe})
    prodotti = await db[COLL_PRODOTTI].find(
        {"id": {"$in": prodotto_ids}},
        {"_id": 0, "id": 1, "nome": 1, "unita_misura": 1},
    ).to_list(None)
    per_prodotto = {p["id"]: p for p in prodotti if p.get("id")}

    risultato = []
    for riga in righe:
        fattura = per_fattura.get(riga.get("fattura_id"))
        if not fattura:
            continue
        data = str(fattura.get("invoice_date") or "")[:10]
        if len(data) < 4 or not data[:4].isdigit():
            continue
        anno = int(data[:4])
        if anni is not None and anno not in anni:
            continue
        prodotto = per_prodotto.get(riga["prodotto_id"], {})
        quantita = _numero(riga.get("quantita"))
        prezzo = _numero(riga.get("prezzo_unitario"))
        risultato.append({
            "prodotto_id": riga["prodotto_id"],
            "nome": prodotto.get("nome") or "",
            "unita_misura": riga.get("unita_misura") or prodotto.get("unita_misura") or "",
            "quantita": quantita,
            "prezzo_unitario": prezzo,
            # La spesa si conosce solo con un prezzo: senza, resta fuori
            # (`costo_disponibile`), mai uno zero spacciato per costo.
            "spesa": round(quantita * prezzo, 2) if prezzo > 0 else 0.0,
            "con_costo": prezzo > 0,
            "data_fattura": data,
            "anno": anno,
            "fornitore": fattura.get("supplier_name") or "",
            "fattura_id": riga.get("fattura_id"),
        })
    return risultato


def _raggruppa(righe: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Per prodotto: quantità, spesa, acquisti, fornitori, date."""
    gruppi: Dict[str, Dict[str, Any]] = {}
    for r in righe:
        g = gruppi.setdefault(r["prodotto_id"], {
            "descrizione": r["nome"],
            "unita_misura": r["unita_misura"],
            "quantita_totale": 0.0,
            "spesa_totale": 0.0,
            "righe_con_costo": 0,
            "num_acquisti": 0,
            "fornitori": [],
            "date_acquisti": [],
            "prezzi": [],
        })
        g["quantita_totale"] += r["quantita"]
        g["spesa_totale"] += r["spesa"]
        g["righe_con_costo"] += 1 if r["con_costo"] else 0
        g["num_acquisti"] += 1
        if r["fornitore"] and r["fornitore"] not in g["fornitori"]:
            g["fornitori"].append(r["fornitore"])
        g["date_acquisti"].append(r["data_fattura"])
        if r["con_costo"]:
            g["prezzi"].append(r["prezzo_unitario"])
    for g in gruppi.values():
        g["quantita_totale"] = round(g["quantita_totale"], 3)
        g["spesa_totale"] = round(g["spesa_totale"], 2)
        g["primo_acquisto"] = min(g["date_acquisti"]) if g["date_acquisti"] else None
        g["ultimo_acquisto"] = max(g["date_acquisti"]) if g["date_acquisti"] else None
        g["prezzo_medio"] = (
            round(sum(g["prezzi"]) / len(g["prezzi"]), 4) if g["prezzi"] else None
        )
    return gruppi


def _cerca(testo: Optional[str], valore: str) -> bool:
    if not testo:
        return True
    return re.search(re.escape(testo), valore or "", re.IGNORECASE) is not None


@router.get("/prodotti")
async def lista_prodotti(
    anno: Optional[int] = Query(None, description="Filtra per anno"),
    fornitore: Optional[str] = Query(None, description="Filtra per fornitore"),
    search: Optional[str] = Query(None, description="Cerca prodotto"),
    limit: int = Query(100, ge=1, le=500)
) -> Dict[str, Any]:
    """
    Lista prodotti acquistati con quantità aggregate.
    """
    db = Database.get_db()
    righe = await _righe_acquisto(db, {anno} if anno else None)
    righe = [
        r for r in righe
        if _cerca(fornitore, r["fornitore"]) and _cerca(search, r["nome"])
    ]
    gruppi = _raggruppa(righe)

    prodotti = []
    for prod_id, g in sorted(gruppi.items(), key=lambda kv: kv[1]["quantita_totale"], reverse=True)[:limit]:
        prodotti.append({
            "id": prod_id,
            "descrizione": g["descrizione"],
            "unita_misura": g["unita_misura"],
            "quantita_totale": g["quantita_totale"],
            "spesa_totale": g["spesa_totale"],
            "righe_con_costo": g["righe_con_costo"],
            "num_acquisti": g["num_acquisti"],
            "fornitori": g["fornitori"][:5],  # Max 5 fornitori
            "primo_acquisto": g["primo_acquisto"],
            "ultimo_acquisto": g["ultimo_acquisto"],
            "prezzo_medio": g["prezzo_medio"],
        })

    return {
        "prodotti": prodotti,
        "totale": len(prodotti),
        "anno_filtro": anno
    }


@router.get("/statistiche")
async def statistiche_acquisti(
    anno: int = Query(..., description="Anno di riferimento"),
    prodotto: Optional[str] = Query(None, description="Filtra per prodotto specifico")
) -> Dict[str, Any]:
    """
    Calcola statistiche dettagliate per previsioni acquisti.

    Per ogni prodotto calcola:
    - Media giornaliera (quantità / 340 giorni)
    - Media settimanale
    - Frequenza acquisti (ogni quanti giorni)
    - Confronto con anno precedente
    """
    db = Database.get_db()
    anno_prec = anno - 1

    righe = [
        r for r in await _righe_acquisto(db, {anno, anno_prec})
        if _cerca(prodotto, r["nome"])
    ]
    correnti = _raggruppa(r for r in righe if r["anno"] == anno)
    precedenti = _raggruppa(r for r in righe if r["anno"] == anno_prec)

    risultati = []
    ordinati = sorted(correnti.items(), key=lambda kv: kv[1]["quantita_totale"], reverse=True)[:100]
    for prod_id, g in ordinati:
        # Calcola giorni effettivi nel periodo
        giorni_periodo = GIORNI_LAVORATIVI_ANNO
        if g.get("primo_acquisto") and g.get("ultimo_acquisto"):
            try:
                primo = datetime.strptime(g["primo_acquisto"], "%Y-%m-%d")
                ultimo = datetime.strptime(g["ultimo_acquisto"], "%Y-%m-%d")
                giorni_periodo = max((ultimo - primo).days, 1)
            except ValueError:
                giorni_periodo = GIORNI_LAVORATIVI_ANNO

        quantita = g["quantita_totale"]
        num_acquisti = g["num_acquisti"]
        media_giornaliera = quantita / GIORNI_LAVORATIVI_ANNO
        media_settimanale = media_giornaliera * GIORNI_SETTIMANA
        # Frequenza acquisti (ogni quanti giorni acquistiamo)
        frequenza_giorni = giorni_periodo / max(num_acquisti, 1)

        q_prec = (precedenti.get(prod_id) or {}).get("quantita_totale", 0)
        if q_prec > 0:
            variazione_pct = ((quantita - q_prec) / q_prec) * 100
            trend = "↑" if variazione_pct > 5 else ("↓" if variazione_pct < -5 else "→")
        else:
            # Un prodotto senza base nell'anno precedente e' "nuovo": +100%
            # sarebbe matematicamente falso (divisione per zero).
            variazione_pct = None
            trend = "nuovo" if quantita > 0 else "→"

        risultati.append({
            "id": prod_id,
            "descrizione": g["descrizione"],
            "unita_misura": g["unita_misura"],
            "quantita_totale": quantita,
            "spesa_totale": g["spesa_totale"],
            "costo_disponibile": g["righe_con_costo"] > 0,
            "num_acquisti": num_acquisti,
            "media_giornaliera": round(media_giornaliera, 2),
            "media_settimanale": round(media_settimanale, 2),
            "frequenza_giorni": round(frequenza_giorni, 1),
            "primo_acquisto": g["primo_acquisto"],
            "ultimo_acquisto": g["ultimo_acquisto"],
            "anno": anno,
            "quantita_anno_corrente": quantita,
            "quantita_anno_prec": q_prec,
            "differenza_quantita": round(quantita - q_prec, 2),
            "variazione_pct": round(variazione_pct, 1) if variazione_pct is not None else None,
            "trend": trend,
        })

    return {
        "statistiche": risultati,
        "anno": anno,
        "anno_confronto": anno_prec,
        "totale_prodotti": len(risultati)
    }


@router.get("/previsioni")
async def previsioni_acquisti(
    anno_riferimento: int = Query(..., description="Anno da usare come riferimento (es: 2025)"),
    settimane_previsione: int = Query(4, ge=1, le=52, description="Settimane da prevedere")
) -> Dict[str, Any]:
    """
    Genera previsioni acquisti basate sullo storico.

    Usa i dati dell'anno di riferimento per proporre gli acquisti da fare
    nelle prossime N settimane.
    """
    db = Database.get_db()
    gruppi = _raggruppa(await _righe_acquisto(db, {anno_riferimento}))

    previsioni = []
    ordinati = sorted(
        ((k, g) for k, g in gruppi.items() if g["quantita_totale"] > 0),
        key=lambda kv: kv[1]["quantita_totale"], reverse=True,
    )[:200]
    for prod_id, g in ordinati:
        quantita = g["quantita_totale"]
        media_settimanale = (quantita / GIORNI_LAVORATIVI_ANNO) * GIORNI_SETTIMANA
        quantita_prevista = media_settimanale * settimane_previsione

        # Frequenza ordini (ogni quante settimane ordinare)
        num_acquisti = g["num_acquisti"]
        settimane_anno = GIORNI_LAVORATIVI_ANNO / GIORNI_SETTIMANA
        frequenza_ordine_settimane = settimane_anno / max(num_acquisti, 1)

        # Costo stimato solo se un prezzo vero c'e': senza, None (mai 0 €).
        prezzo_medio = g["prezzo_medio"]
        costo_stimato = (
            round(quantita_prevista * prezzo_medio, 2) if prezzo_medio is not None else None
        )

        previsioni.append({
            "id": prod_id,
            "prodotto": g["descrizione"],
            "unita_misura": g["unita_misura"],
            "quantita_anno_rif": round(quantita, 2),
            "media_settimanale": round(media_settimanale, 2),
            "quantita_prevista": round(quantita_prevista, 2),
            "frequenza_ordine_settimane": round(frequenza_ordine_settimane, 1),
            "prossimo_ordine_tra_giorni": round(frequenza_ordine_settimane * 7, 0),
            "fornitori_abituali": g["fornitori"][:3],
            "prezzo_medio": round(prezzo_medio, 2) if prezzo_medio is not None else None,
            "costo_stimato": costo_stimato,
        })

    costo_totale = sum(p["costo_stimato"] for p in previsioni if p["costo_stimato"] is not None)

    return {
        "previsioni": previsioni,
        "anno_riferimento": anno_riferimento,
        "settimane_previsione": settimane_previsione,
        "totale_prodotti": len(previsioni),
        "costo_totale_stimato": round(costo_totale, 2),
        "prodotti_senza_prezzo": sum(1 for p in previsioni if p["costo_stimato"] is None),
    }


async def registra_acquisto_da_fattura(db, fattura: Dict[str, Any]) -> Dict[str, int]:
    """Ricostruisce lo storico di una fattura, nella forma del gestore magazzino.

    Il prodotto si riconosce con lo stesso abbinamento a tre livelli di
    `magazzino_handlers` (sola lettura: non crea prodotti né alert); una riga
    senza abbinamento certo non si registra e si conta. Una fattura che ha
    già righe nello storico si salta: il secondo giro dà `nuove = 0`.
    """
    from app.services.handlers.magazzino_handlers import (
        _cerca_prodotto_3_livelli,
        _is_servizio,
    )

    esito = {"registrate": 0, "non_risolte": 0}
    fattura_id = fattura.get("id")
    linee = fattura.get("linee") or fattura.get("lines") or []
    if not fattura_id or not linee:
        return esito
    fornitore_id = fattura.get("supplier_id") or fattura.get("fornitore_id")

    for linea in linee:
        descrizione = str(linea.get("descrizione") or linea.get("description") or "").strip()
        if not descrizione or _is_servizio(descrizione):
            continue
        match = await _cerca_prodotto_3_livelli(descrizione, fornitore_id, db)
        if not (match.get("trovato") and match.get("certezza") == "certo"):
            esito["non_risolte"] += 1
            continue
        await db[COLL_ACQUISTI].insert_one({
            "id": str(uuid.uuid4()),
            "prodotto_id": match["prodotto_id"],
            "fattura_id": fattura_id,
            "fornitore_id": fornitore_id,
            "quantita": _numero(linea.get("quantita") or linea.get("quantity")),
            "prezzo_unitario": _numero(linea.get("prezzo_unitario") or linea.get("unit_price")),
            "unita_misura": linea.get("unita_misura") or linea.get("unit") or "",
            "data": datetime.now(timezone.utc).isoformat(),
            "fonte": "popola_storico",
        })
        esito["registrate"] += 1
    return esito


@router.post("/popola-storico")
async def popola_storico_da_fatture() -> Dict[str, Any]:
    """
    Ricostruisce `acquisti_prodotti` dalle fatture attive che non ci sono ancora.

    Fuori le copie archiviate (ogni fattura 2026 ne ha una) e le note di
    credito. Idempotente: una fattura già nello storico non si rilegge.
    """
    db = Database.get_db()

    gia_presenti = {
        r.get("fattura_id")
        for r in await db[COLL_ACQUISTI].find(
            {"prodotto_id": {"$exists": True, "$nin": [None, ""]}},
            {"_id": 0, "fattura_id": 1},
        ).to_list(None)
        if r.get("fattura_id")
    }

    fatture_attive = await db["invoices"].find(
        dict(FILTRO_FATTURA_ATTIVA),
        {**_PROIEZIONE_FATTURA, "linee": 1, "lines": 1, "supplier_id": 1, "fornitore_id": 1},
    ).to_list(None)

    processate = 0
    gia_nello_storico = 0
    note_credito = 0
    prodotti_registrati = 0
    righe_non_risolte = 0
    errori = 0

    for fattura in fatture_attive:
        if e_nota_credito(fattura):
            note_credito += 1
            continue
        if fattura.get("id") in gia_presenti:
            gia_nello_storico += 1
            continue
        try:
            esito = await registra_acquisto_da_fattura(db, fattura)
            prodotti_registrati += esito["registrate"]
            righe_non_risolte += esito["non_risolte"]
            processate += 1
        except Exception as e:  # noqa: BLE001 - una fattura non ferma le altre
            logger.error("Storico acquisti: fattura %s non letta: %s: %s",
                         fattura.get("id"), type(e).__name__, e)
            errori += 1

    return {
        "success": True,
        "fatture_processate": processate,
        "fatture_gia_nello_storico": gia_nello_storico,
        "note_credito_escluse": note_credito,
        "prodotti_registrati": prodotti_registrati,
        "righe_non_risolte": righe_non_risolte,
        "errori": errori,
        "totale_fatture": len(fatture_attive)
    }


@router.get("/confronto-ordine")
async def confronto_ordine(
    anno_riferimento: int = Query(..., description="Anno di riferimento"),
    prodotto: str = Query(..., description="Nome prodotto"),
    quantita_ordinata: float = Query(..., description="Quantità che vuoi ordinare")
) -> Dict[str, Any]:
    """
    Confronta una quantità da ordinare con la media storica.
    Dice se sei sopra o sotto la media.
    """
    db = Database.get_db()

    righe = [
        r for r in await _righe_acquisto(db, {anno_riferimento})
        if _cerca(prodotto, r["nome"])
    ]
    gruppi = _raggruppa(righe)
    if not gruppi:
        raise HTTPException(status_code=404, detail=f"Prodotto '{prodotto}' non trovato nello storico {anno_riferimento}")
    # Il prodotto piu' acquistato fra quelli che corrispondono alla ricerca.
    risultato = max(gruppi.values(), key=lambda g: g["quantita_totale"])

    quantita_storico = risultato["quantita_totale"]
    num_acquisti = risultato["num_acquisti"]

    # Calcola media per singolo ordine
    media_per_ordine = quantita_storico / max(num_acquisti, 1)

    # Confronta
    differenza = quantita_ordinata - media_per_ordine
    differenza_pct = (differenza / media_per_ordine) * 100 if media_per_ordine > 0 else 0

    if differenza_pct > 20:
        giudizio = "SOPRA MEDIA (+{:.0f}%)".format(differenza_pct)
        emoji = "📈"
        consiglio = "Stai ordinando più del solito. Verifica se necessario."
    elif differenza_pct < -20:
        giudizio = "SOTTO MEDIA ({:.0f}%)".format(differenza_pct)
        emoji = "📉"
        consiglio = "Stai ordinando meno del solito. Potrebbe bastare?"
    else:
        giudizio = "IN LINEA"
        emoji = "✅"
        consiglio = "Quantità in linea con lo storico."

    return {
        "prodotto": risultato["descrizione"],
        "unita_misura": risultato["unita_misura"],
        "quantita_ordinata": quantita_ordinata,
        "media_per_ordine": round(media_per_ordine, 2),
        "differenza": round(differenza, 2),
        "differenza_pct": round(differenza_pct, 1),
        "giudizio": giudizio,
        "emoji": emoji,
        "consiglio": consiglio,
        "storico": {
            "anno": anno_riferimento,
            "quantita_totale": quantita_storico,
            "num_ordini": num_acquisti
        }
    }
