"""
Checks (Assegni) router - Gestione Assegni.
API per generazione, gestione e collegamento assegni.
"""
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import uuid
import logging
import re

from app.database import Database
from app.models.stati import STATI_PAGATI
from app.routers.bank.assegni_auto_match import _f, _norm_piva, TOLL, MAX_RATE, fornitore_esclude_assegno
from app.services.identity_matching import identita_coincide
from app.services.payment_invoice_matching import (
    amounts_equal_to_cent,
    invoice_reference_equals,
)
from app.services.assegni_fattura_intent import (
    capienza_assegno_fattura,
    fattura_dichiara_assegno,
    importi_assegno_dichiarati,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# Collection name
COLLECTION_ASSEGNI = "assegni"


def _genera_sequenza_carnet(numero_primo: str, quantita: int) -> tuple[List[str], str]:
    """Genera numeri progressivi preservando zeri e formato bancario.

    Sono supportati sia i numeri continui presenti sugli assegni reali
    (``0208770985``), sia il formato storico ``PREFISSO-SUFFISSO``
    (``0208770000-01``). La larghezza non puo' cambiare durante il carnet:
    un overflow richiede un nuovo carnet e non viene salvato in parte.
    """
    valore = str(numero_primo or "").strip()
    if not valore:
        raise ValueError("Inserisci il numero del primo assegno")

    continuo = re.fullmatch(r"\d+", valore)
    if continuo:
        larghezza = len(valore)
        iniziale = int(valore)
        finale = iniziale + quantita - 1
        if len(str(finale)) > larghezza:
            raise ValueError("La progressione supera la lunghezza del numero iniziale")
        numeri = [f"{iniziale + indice:0{larghezza}d}" for indice in range(quantita)]
        return numeri, valore

    separato = re.fullmatch(r"(\d+)-(\d+)", valore)
    if separato:
        prefisso, suffisso = separato.groups()
        larghezza = len(suffisso)
        iniziale = int(suffisso)
        finale = iniziale + quantita - 1
        if len(str(finale)) > larghezza:
            raise ValueError("La progressione supera la lunghezza del suffisso iniziale")
        numeri = [
            f"{prefisso}-{iniziale + indice:0{larghezza}d}"
            for indice in range(quantita)
        ]
        return numeri, prefisso

    raise ValueError(
        "Formato non valido: usa un numero continuo (es. 0208770985) "
        "oppure PREFISSO-SUFFISSO (es. 0208770000-01)"
    )


def _assegno_riferisce_fattura(assegno: Dict[str, Any], fattura: Dict[str, Any]) -> bool:
    """Vero solo se il numero fattura dichiarato sull'assegno coincide."""
    numero_assegno = assegno.get("numero_fattura") or assegno.get("fattura_numero")
    numero_fattura = fattura.get("invoice_number") or fattura.get("numero_documento")
    return invoice_reference_equals(numero_assegno, numero_fattura)


# Stati assegno.
# "assegnato"/"parzialmente_assegnato" sono scritti dal collegamento a fatture
# (auto-matcher in assegni_auto_match.py e endpoint manuale qui sotto) — devono
# essere validi anche qui, altrimenti un PUT generico successivo con questi
# stati verrebbe rifiutato dalla validazione più sotto.
ASSEGNO_STATI = {
    "vuoto": {"label": "Vuoto", "color": "#9e9e9e"},
    "compilato": {"label": "Compilato", "color": "#2196f3"},
    "emesso": {"label": "Emesso", "color": "#ff9800"},
    "parzialmente_assegnato": {"label": "Parzialmente assegnato", "color": "#ff9800"},
    "assegnato": {"label": "Assegnato", "color": "#2196f3"},
    "incassato": {"label": "Incassato", "color": "#4caf50"},
    "annullato": {"label": "Annullato", "color": "#f44336"},
    "scaduto": {"label": "Scaduto", "color": "#795548"}
}


@router.get("/stati")
async def get_assegno_stati() -> Dict[str, Any]:
    """Ritorna gli stati disponibili per gli assegni."""
    return ASSEGNO_STATI


@router.post("/genera")
async def genera_assegni(
    numero_primo: str = Body(
        ...,
        description=(
            "Numero del primo assegno, continuo o con trattino "
            "(es. 0208770985 oppure 0208769182-11)"
        ),
    ),
    quantita: int = Body(10, ge=1, le=100, description="Numero di assegni da generare"),
    anno: Optional[int] = Body(None, ge=2000, le=2100, description="Anno globale del carnet"),
) -> Dict[str, Any]:
    """
    Genera N assegni progressivi a partire dal numero fornito.
    
    Accetta il formato bancario continuo e il formato storico con trattino,
    preservando sempre gli zeri iniziali.
    """
    db = Database.get_db()
    
    try:
        numeri_richiesti, carnet_id = _genera_sequenza_carnet(numero_primo, quantita)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    
    # Verifica se alcuni numeri esistono già
    # Una sola query per tutto il carnet. Il vecchio ciclo eseguiva fino a
    # 100 round-trip Atlas prima ancora di salvare.
    esistenti = await db[COLLECTION_ASSEGNI].find(
        {"numero": {"$in": numeri_richiesti}},
        {"_id": 0, "numero": 1},
    ).to_list(quantita)
    existing_numbers = [a.get("numero") for a in esistenti if a.get("numero")]
    
    if existing_numbers:
        raise HTTPException(
            status_code=400, 
            detail=f"I seguenti numeri esistono già: {', '.join(existing_numbers[:5])}{'...' if len(existing_numbers) > 5 else ''}"
        )
    
    # Genera assegni
    assegni_creati = []
    nuovi_assegni = []
    now = datetime.now(timezone.utc).isoformat()
    anno_carnet = anno or datetime.now(timezone.utc).year
    for numero in numeri_richiesti:
        assegno = {
            "id": str(uuid.uuid4()),
            "numero": numero,
            "carnet_id": carnet_id,
            "anno_creazione": anno_carnet,
            "anno": anno_carnet,
            "stato": "vuoto",
            "importo": None,
            "beneficiario": None,
            "causale": None,
            "data_emissione": None,
            "data_scadenza": None,
            "data_fattura": None,
            "numero_fattura": None,
            "fattura_collegata": None,
            "fatture_collegate": [],  # Lista di fatture (max 4)
            "fornitore_piva": None,
            "note": None,
            "created_at": now,
            "updated_at": now
        }
        nuovi_assegni.append(assegno)
        assegni_creati.append(numero)

    # Salvataggio unico: il carnet compare integralmente senza una latenza di
    # rete per ogni assegno.
    await db[COLLECTION_ASSEGNI].insert_many(nuovi_assegni, ordered=True)
    
    return {
        "success": True,
        "message": f"Generati {quantita} assegni",
        "generati": quantita,
        "carnet_id": carnet_id,
        "anno": anno_carnet,
        "primo": assegni_creati[0],
        "ultimo": assegni_creati[-1],
        "numeri": assegni_creati
    }


@router.get("")
async def list_assegni(
    skip: int = Query(0, ge=0),
    limit: int = Query(1000, ge=1, le=1000),
    stato: Optional[str] = Query(None),
    fornitore_piva: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    anno: Optional[int] = Query(None)
) -> List[Dict[str, Any]]:
    """Lista assegni con filtri."""
    db = Database.get_db()
    
    # Escludi assegni eliminati (soft-delete)
    query = {"entity_status": {"$ne": "deleted"}}
    if anno:
        # data_emissione/data sono stringhe YYYY-MM-DD; gli assegni senza
        # data appartengono all'anno in cui il carnet e' stato creato. Per i
        # record legacy usiamo created_at, evitando che lo stesso carnet
        # vuoto compaia contemporaneamente in tutti gli anni globali.
        query["$and"] = [{"$or": [
            {"data_emissione": {"$regex": f"^{anno}"}},
            {"data": {"$regex": f"^{anno}"}},
            {"anno_creazione": anno},
            {"anno": anno},
            {"$and": [
                {"data_emissione": {"$in": [None, ""]}},
                {"data": {"$in": [None, ""]}},
                {"anno_creazione": {"$exists": False}},
                {"anno": {"$exists": False}},
                {"created_at": {"$regex": f"^{anno}"}},
            ]},
        ]}]
    if stato:
        query["stato"] = stato
    if fornitore_piva:
        query["fornitore_piva"] = fornitore_piva
    if search:
        query["$or"] = [
            {"numero": {"$regex": search, "$options": "i"}},
            {"beneficiario": {"$regex": search, "$options": "i"}}
        ]
    
    # Ordina per data (più recenti prima) invece che per stato alfabetico:
    # con l'ordinamento alfabetico su "stato" (annullato < assegnato <
    # compilato < emesso < incassato < vuoto) gli assegni "emesso" restavano
    # tagliati fuori dalla finestra di un limit fisso se c'erano molti
    # assegni negli stati alfabeticamente precedenti (es. carnet generati in
    # blocco, tutti "vuoto"/"compilato"/"assegnato"). Il frontend riordina
    # comunque per numero all'arrivo (GestioneAssegni.jsx::loadData) — qui
    # conta solo quali record sopravvivono al limit.
    assegni = await db[COLLECTION_ASSEGNI].find(query, {"_id": 0}).sort([
        ("data_emissione", -1),
        ("numero", 1)
    ]).skip(skip).limit(limit).to_list(limit)

    # Arricchimento display: per gli assegni con fattura collegata ma senza
    # beneficiario reale, il frontend mostra il fornitore dedotto dalla
    # fattura (richiesta utente: "conoscendo il numero della fattura è anche
    # noto il fornitore"). Non scriviamo nulla sull'assegno: solo risposta.
    ids_fatture = set()
    numeri_fatture = set()
    ids_movimenti = set()
    for assegno in assegni:
        for chiave in ("fattura_collegata", "fattura_id"):
            if assegno.get(chiave):
                ids_fatture.add(str(assegno[chiave]))
        for link in assegno.get("fatture_collegate") or []:
            if isinstance(link, dict) and link.get("fattura_id"):
                ids_fatture.add(str(link["fattura_id"]))
        for numero in str(assegno.get("numero_fattura") or "").split(","):
            if numero.strip():
                numeri_fatture.add(numero.strip())
        movimento_id = (
            assegno.get("movimento_estratto_conto_id")
            or assegno.get("movimento_id")
            or assegno.get("estratto_conto_id")
        )
        if movimento_id:
            ids_movimenti.add(str(movimento_id))

    condizioni_fatture = []
    if ids_fatture:
        condizioni_fatture.append({"id": {"$in": list(ids_fatture)}})
    if numeri_fatture:
        condizioni_fatture.append({"invoice_number": {"$in": list(numeri_fatture)}})
    fatture = []
    if condizioni_fatture:
        fatture = await db["invoices"].find(
            {"$or": condizioni_fatture},
            {
                "_id": 0, "id": 1, "invoice_number": 1,
                "numero_fattura": 1, "invoice_date": 1, "data_fattura": 1,
                "supplier_name": 1, "cedente_denominazione": 1,
                "total_amount": 1, "importo_totale": 1,
                "importo_pagato": 1, "assegni_collegati": 1,
            },
        ).to_list(5000)

    # Una fattura puo essere rateizzata su piu assegni, ma la somma delle
    # quote non puo superare il totale documento. Cerchiamo i riferimenti
    # anche fuori dalla pagina corrente per esporre i conflitti storici senza
    # modificare o cancellare alcuna prova contabile.
    conflitti_per_fattura: Dict[str, Dict[str, Any]] = {}
    if ids_fatture:
        assegni_collegati = await db[COLLECTION_ASSEGNI].find(
            {
                "entity_status": {"$ne": "deleted"},
                "$or": [
                    {"fattura_collegata": {"$in": list(ids_fatture)}},
                    {"fattura_id": {"$in": list(ids_fatture)}},
                    {"fatture_collegate.fattura_id": {"$in": list(ids_fatture)}},
                ],
            },
            {
                "_id": 0, "id": 1, "numero": 1, "importo": 1,
                "fattura_collegata": 1, "fattura_id": 1,
                "fatture_collegate": 1,
            },
        ).to_list(10000)
        invoice_by_id = {str(f.get("id")): f for f in fatture if f.get("id")}
        for fid in ids_fatture:
            quote_per_assegno: Dict[str, float] = {}
            numeri_per_assegno: Dict[str, str] = {}
            for altro in assegni_collegati:
                aid = str(altro.get("id") or altro.get("numero") or "")
                if not aid:
                    continue
                quote = [
                    _f(link.get("quota"))
                    for link in (altro.get("fatture_collegate") or [])
                    if isinstance(link, dict)
                    and str(link.get("fattura_id") or "") == str(fid)
                    and _f(link.get("quota")) > 0
                ]
                legacy = (
                    str(altro.get("fattura_collegata") or "") == str(fid)
                    or str(altro.get("fattura_id") or "") == str(fid)
                )
                if quote:
                    quote_per_assegno[aid] = round(sum(quote), 2)
                elif legacy and _f(altro.get("importo")) > 0:
                    quote_per_assegno[aid] = round(_f(altro.get("importo")), 2)
                if aid in quote_per_assegno:
                    numeri_per_assegno[aid] = str(altro.get("numero") or aid)

            inv = invoice_by_id.get(str(fid))
            totale = round(_f((inv or {}).get("total_amount") or (inv or {}).get("importo_totale")), 2)
            attribuito = round(sum(quote_per_assegno.values()), 2)
            if totale > 0 and attribuito > totale + TOLL:
                conflitti_per_fattura[str(fid)] = {
                    "fattura_id": str(fid),
                    "numero_fattura": (inv or {}).get("invoice_number") or (inv or {}).get("numero_fattura"),
                    "importo_fattura": totale,
                    "importo_attribuito": attribuito,
                    "assegni": list(numeri_per_assegno.values()),
                }

    per_id = {str(f.get("id")): f for f in fatture if f.get("id")}
    per_numero = {}
    for fattura in fatture:
        numero = fattura.get("invoice_number") or fattura.get("numero_fattura")
        if numero:
            per_numero.setdefault(str(numero), []).append(fattura)

    movimenti = {}
    if ids_movimenti:
        righe_ec = await db["estratto_conto_movimenti"].find(
            {"id": {"$in": list(ids_movimenti)}},
            {"_id": 0, "id": 1, "data": 1, "data_contabile": 1},
        ).to_list(5000)
        movimenti = {str(m.get("id")): m for m in righe_ec if m.get("id")}

    # Il collegamento manuale e' ammesso soltanto per ambiguita' reali gia'
    # registrate dal motore (due o piu' candidati senza prova discriminante).
    # Il frontend non deve aprire il modale per ogni assegno ordinario.
    ids_assegni = [str(a.get("id")) for a in assegni if a.get("id")]
    ambigui_ids = set()
    if ids_assegni:
        proposte = await db["proposte_associazione_assegni"].find(
            {"assegno_id": {"$in": ids_assegni}, "stato": "da_confermare"},
            {"_id": 0, "assegno_id": 1},
        ).to_list(5000)
        ambigui_ids = {
            str(p.get("assegno_id")) for p in proposte if p.get("assegno_id")
        }

    for assegno in assegni:
        assegno["associazione_ambigua"] = str(assegno.get("id")) in ambigui_ids
        collegamenti_ids = []
        for chiave in ("fattura_collegata", "fattura_id"):
            if assegno.get(chiave):
                collegamenti_ids.append(str(assegno[chiave]))
        for link in assegno.get("fatture_collegate") or []:
            if isinstance(link, dict) and link.get("fattura_id"):
                collegamenti_ids.append(str(link["fattura_id"]))
        collegamenti = [
            per_id[fid] for fid in dict.fromkeys(collegamenti_ids) if fid in per_id
        ]
        if not collegamenti:
            for numero in str(assegno.get("numero_fattura") or "").split(","):
                candidate = per_numero.get(numero.strip(), [])
                if len(candidate) == 1:
                    collegamenti.append(candidate[0])

        uniche = {str(f.get("id")): f for f in collegamenti if f.get("id")}
        conflitti = [
            conflitti_per_fattura[fid]
            for fid in dict.fromkeys(collegamenti_ids)
            if fid in conflitti_per_fattura
        ]
        assegno["associazione_conflittuale"] = bool(conflitti)
        assegno["fatture_conflittuali"] = conflitti
        dettagli = [{
            "fattura_id": fattura.get("id"),
            "numero_fattura": fattura.get("invoice_number") or fattura.get("numero_fattura"),
            "data_fattura": fattura.get("invoice_date") or fattura.get("data_fattura"),
            "fornitore": fattura.get("supplier_name") or fattura.get("cedente_denominazione") or "",
        } for fattura in uniche.values()]
        assegno["fatture_dettaglio"] = dettagli
        if dettagli:
            assegno["fornitore_fattura"] = ", ".join(dict.fromkeys(
                d["fornitore"] for d in dettagli if d.get("fornitore")
            ))
            assegno["numero_fattura"] = ", ".join(
                d["numero_fattura"] for d in dettagli if d.get("numero_fattura")
            )
            if len(dettagli) == 1:
                assegno["data_fattura"] = dettagli[0].get("data_fattura")

        movimento_id = str(
            assegno.get("movimento_estratto_conto_id")
            or assegno.get("movimento_id")
            or assegno.get("estratto_conto_id")
            or ""
        )
        movimento = movimenti.get(movimento_id)
        if movimento:
            assegno["data_incasso"] = (
                assegno.get("data_incasso")
                or movimento.get("data") or movimento.get("data_contabile")
            )
            assegno["evidenza_estratto_conto_id"] = movimento_id

        if assegno.get("stato") == "incassato":
            mancanti = []
            if not assegno.get("data_incasso"):
                mancanti.append("data_incasso")
            if not dettagli:
                mancanti.extend(["fornitore", "numero_fattura"])
            assegno["dati_riconciliazione_mancanti"] = mancanti

    return assegni


@router.get("/supporto/fatture-disponibili")
async def fatture_disponibili_per_assegno(
    anno: int = Query(..., ge=2000, le=2100),
    limit: int = Query(1000, ge=1, le=2000),
) -> List[Dict[str, Any]]:
    """Elenco leggero delle fatture aperte associabili a un assegno.

    Evita di caricare migliaia di XML/documenti completi tramite l'endpoint
    generale delle fatture, causa del timeout del modale di associazione.
    """
    db = Database.get_db()
    inizio, fine = f"{anno}-01-01", f"{anno}-12-31"
    query = {
        "$and": [
            {"$or": [
                {"invoice_date": {"$gte": inizio, "$lte": fine}},
                {"data_documento": {"$gte": inizio, "$lte": fine}},
                {"data_fattura": {"$gte": inizio, "$lte": fine}},
            ]},
            {"status": {"$nin": ["deleted", "archived", "paid", "pagato"]}},
            {"payment_status": {"$nin": ["paid", "pagato", "pagata"]}},
            {"stato_pagamento": {"$nin": ["paid", "pagato", "pagata"]}},
            {"pagato": {"$ne": True}},
            {"paid": {"$ne": True}},
        ]
    }
    projection = {
        "_id": 0,
        "id": 1,
        "invoice_key": 1,
        "invoice_number": 1,
        "numero_fattura": 1,
        "numero_documento": 1,
        "invoice_date": 1,
        "data_fattura": 1,
        "data_documento": 1,
        "supplier_name": 1,
        "cedente_denominazione": 1,
        "supplier_vat": 1,
        "cedente_piva": 1,
        "fornitore_partita_iva": 1,
        "total_amount": 1,
        "importo_totale": 1,
        "tipo_documento": 1,
        "document_type": 1,
        "importo_pagato": 1,
        "importo_residuo": 1,
        "pagamento_rate": 1,
    }
    candidati = await db["invoices"].find(
        query, projection
    ).sort("invoice_date", -1).limit(limit * 2).to_list(limit * 2)

    # Difesa sui dati legacy: una sola riga per identita' fiscale.
    risultato: List[Dict[str, Any]] = []
    visti = set()
    for f in candidati:
        numero = f.get("invoice_number") or f.get("numero_fattura") or f.get("numero_documento") or ""
        piva = f.get("supplier_vat") or f.get("cedente_piva") or f.get("fornitore_partita_iva") or ""
        data = f.get("invoice_date") or f.get("data_fattura") or f.get("data_documento") or ""
        totale = f.get("total_amount") if f.get("total_amount") is not None else f.get("importo_totale")
        chiave = f.get("invoice_key") or (
            str(piva).strip().upper(), str(numero).strip().upper(), str(data)[:10], str(totale)
        )
        if chiave in visti:
            continue
        visti.add(chiave)
        risultato.append(f)
        if len(risultato) >= limit:
            break
    return risultato


@router.get("/stats")
async def get_assegni_stats(anno: Optional[int] = Query(None)) -> Dict[str, Any]:
    """Statistiche assegni."""
    db = Database.get_db()
    
    # Escludi assegni eliminati (soft-delete)
    match_filter = {"entity_status": {"$ne": "deleted"}}
    if anno:
        match_filter["$and"] = [{"$or": [
            {"data_emissione": {"$regex": f"^{anno}"}},
            {"data": {"$regex": f"^{anno}"}},
            {"anno_creazione": anno},
            {"anno": anno},
            {"$and": [
                {"data_emissione": {"$in": [None, ""]}},
                {"data": {"$in": [None, ""]}},
                {"anno_creazione": {"$exists": False}},
                {"anno": {"$exists": False}},
                {"created_at": {"$regex": f"^{anno}"}},
            ]},
        ]}]

    filtro_tutti_anno = dict(match_filter)
    if "$and" in match_filter:
        filtro_tutti_anno["$and"] = list(match_filter["$and"])
    operativi = {"$or": [
        {"importo": {"$gt": 0}},
        {"stato": {"$in": [
            "compilato", "emesso", "parzialmente_assegnato", "assegnato",
            "incassato", "annullato", "scaduto",
        ]}},
    ]}
    match_filter.setdefault("$and", []).append(operativi)
    
    pipeline = [
        {"$match": match_filter},
        {"$group": {
            "_id": "$stato",
            "count": {"$sum": 1},
            "totale": {"$sum": {"$ifNull": ["$importo", 0]}}
        }}
    ]
    
    by_stato = await db[COLLECTION_ASSEGNI].aggregate(pipeline).to_list(100)
    
    totale = await db[COLLECTION_ASSEGNI].count_documents(match_filter)
    totale_record = await db[COLLECTION_ASSEGNI].count_documents(filtro_tutti_anno)
    
    return {
        "totale": totale,
        "totale_record": totale_record,
        "carnet_vuoti": max(totale_record - totale, 0),
        "per_stato": {item["_id"]: {"count": item["count"], "totale": item["totale"]} for item in by_stato}
    }


@router.get("/senza-associazione")
async def get_assegni_senza_associazione_v2(
    anno: Optional[int] = Query(None),
) -> Dict[str, Any]:
    """
    Restituisce assegni che hanno importo ma nessun beneficiario/fattura associata.
    Utile per debug e verifica manuale.
    """
    db = Database.get_db()
    
    condizioni = [
        {"entity_status": {"$ne": "deleted"}},
        {"importo": {"$gt": 0}},
        {"$or": [
            {"beneficiario": None},
            {"beneficiario": ""},
            {"beneficiario": "N/A"},
            {"beneficiario": "-"},
            {"$and": [
                {"fattura_id": {"$in": [None, ""]}},
                {"fattura_collegata": {"$in": [None, ""]}},
            ]},
        ]},
    ]
    if anno:
        condizioni.append({"$or": [
            {"data_emissione": {"$regex": f"^{anno}"}},
            {"data": {"$regex": f"^{anno}"}},
            {"anno_creazione": anno},
            {"anno": anno},
            {"created_at": {"$regex": f"^{anno}"}},
        ]})
    assegni = await db[COLLECTION_ASSEGNI].find(
        {"$and": condizioni}, {"_id": 0}
    ).to_list(5000)
    
    # Raggruppa per importo
    from collections import defaultdict
    per_importo = defaultdict(list)
    for a in assegni:
        imp = round(a.get("importo", 0), 2)
        per_importo[imp].append(a.get("numero"))
    
    return {
        "totale": len(assegni),
        "per_importo": {f"€{k:.2f}": {"count": len(v), "numeri": v[:10]} for k, v in sorted(per_importo.items(), key=lambda x: -len(x[1]))}
    }


@router.get("/preview-combinazioni")
async def preview_combinazioni_assegni_v2(
    max_assegni: int = Query(4, ge=2, le=6)
) -> Dict[str, Any]:
    """
    🔎 PREVIEW: Mostra le possibili combinazioni di assegni che potrebbero matchare fatture.
    Non esegue modifiche, solo analisi.
    
    Utile per verificare prima di eseguire l'associazione.
    """
    from itertools import combinations
    db = Database.get_db()
    
    # Carica assegni senza beneficiario
    assegni_senza_ben = await db[COLLECTION_ASSEGNI].find({
        "$or": [
            {"beneficiario": None},
            {"beneficiario": ""},
            {"beneficiario": "N/A"},
            {"beneficiario": "-"}
        ],
        "importo": {"$gt": 0}
    }, {"_id": 0, "numero": 1, "importo": 1}).to_list(100)
    
    # Filtra quelli non cancellati
    assegni_senza_ben = [a for a in assegni_senza_ben if a.get("entity_status") != "deleted"]
    
    if len(assegni_senza_ben) < 2:
        return {
            "assegni_senza_beneficiario": len(assegni_senza_ben),
            "combinazioni_possibili": [],
            "message": "Servono almeno 2 assegni per cercare combinazioni"
        }
    
    # Carica fatture non pagate
    # Escludiamo RID/SDD/addebito diretto: non pagabili con assegno.
    fatture = await db.invoices.find({
        "$and": [
            {"$or": [
                {"status": {"$nin": STATI_PAGATI}},
                {"pagato": {"$ne": True}}
            ]},
            {"total_amount": {"$gt": 0}},
            {"$nor": [
                {"metodo_pagamento": {"$regex": "rid|sdd|addebito", "$options": "i"}},
                {"payment_method": {"$regex": "rid|sdd|addebito", "$options": "i"}},
                {"modalita_pagamento": {"$regex": "rid|sdd|addebito", "$options": "i"}},
            ]},
        ]
    }, {"_id": 0, "invoice_number": 1, "supplier_name": 1, "total_amount": 1}).to_list(10000)

    # Fornitori mai pagabili con assegno (dettato utente 18/07/2026): Amazon,
    # ABC acquedotto, Fastweb, PayPal, Enel, Leasys, Arval — arrivano su carta
    # di credito o addebito bancario, mai su assegno.
    fatture = [f for f in fatture if not fornitore_esclude_assegno(f.get("supplier_name") or "")]

    importi_fatture = {round(float(f.get("total_amount", 0)), 2): f for f in fatture}
    
    # Cerca combinazioni
    possibili_match = []
    importi = [(a.get("numero"), round(float(a.get("importo", 0)), 2)) for a in assegni_senza_ben]
    
    for r in range(2, min(max_assegni + 1, len(importi) + 1)):
        for combo in combinations(importi, r):
            somma = round(sum(imp for _, imp in combo), 2)
            
            # Cerca fattura con questo importo (±1€)
            for delta in [0, -0.01, 0.01, -0.02, 0.02, -0.5, 0.5, -1, 1]:
                imp_cerca = round(somma + delta, 2)
                if imp_cerca in importi_fatture:
                    f = importi_fatture[imp_cerca]
                    possibili_match.append({
                        "assegni": [num for num, _ in combo],
                        "importi": [imp for _, imp in combo],
                        "somma": somma,
                        "fattura": f.get("invoice_number"),
                        "fornitore": f.get("supplier_name", "")[:40],
                        "importo_fattura": f.get("total_amount"),
                        "differenza": round(f.get("total_amount", 0) - somma, 2)
                    })
                    break
    
    return {
        "assegni_senza_beneficiario": len(assegni_senza_ben),
        "fatture_non_pagate": len(fatture),
        "combinazioni_con_match": len(possibili_match),
        "dettagli": possibili_match[:20]  # Primi 20 per non sovraccaricare
    }


@router.get("/verifica-associazioni")
async def verifica_associazioni_assegni(
    anno: Optional[int] = Query(None),
) -> Dict[str, Any]:
    """
    Analizza tutte le associazioni assegno-fattura e identifica quelle problematiche.
    
    PROBLEMI IDENTIFICATI:
    1. Importo assegno diverso da importo fattura anche di un centesimo
    2. Beneficiario assegno diverso da fornitore fattura
    3. Fattura associata non esistente nel database
    4. Fattura associata già pagata
    5. Data assegno molto diversa da data fattura (>180 giorni)
    
    Returns:
        Lista di associazioni problematiche. Le alternative sono suggerite
        solo quando coincidono numero fattura dichiarato e importo al centesimo.
    """
    from thefuzz import fuzz
    
    db = Database.get_db()
    
    # Carica tutti gli assegni con fattura associata
    condizioni = [
        {"entity_status": {"$ne": "deleted"}},
        {"$or": [
            {"fattura_id": {"$exists": True, "$nin": [None, ""]}},
            {"fattura_collegata": {"$exists": True, "$nin": [None, ""]}},
        ]},
    ]
    if anno:
        condizioni.append({"$or": [
            {"data_emissione": {"$regex": f"^{anno}"}},
            {"data": {"$regex": f"^{anno}"}},
            {"anno_creazione": anno},
            {"anno": anno},
            {"created_at": {"$regex": f"^{anno}"}},
        ]})
    assegni = await db[COLLECTION_ASSEGNI].find(
        {"$and": condizioni},
        {"_id": 0}
    ).to_list(10000)
    
    # Carica tutte le fatture per lookup veloce
    fatture_cursor = await db["invoices"].find({}, {"_id": 0}).to_list(50000)
    if len(fatture_cursor) >= 50000:
        logger.warning("verifica_associazioni_assegni_fatture: raggiunto il tetto di 50000 documenti, possibile troncamento")
    fatture_by_id = {f.get("id"): f for f in fatture_cursor}
    
    problemi = []
    statistiche = {
        "totale_assegni_analizzati": len(assegni),
        "associazioni_corrette": 0,
        "problemi_importo": 0,
        "problemi_fornitore": 0,
        "problemi_fattura_mancante": 0,
        "problemi_fattura_pagata": 0,
        "problemi_data": 0
    }
    
    for assegno in assegni:
        assegno_id = assegno.get("id")
        fattura_id = assegno.get("fattura_id") or assegno.get("fattura_collegata")
        numero_assegno = assegno.get("numero_assegno") or assegno.get("numero")
        importo_assegno = float(assegno.get("importo") or 0)
        beneficiario = assegno.get("beneficiario") or ""
        data_assegno = assegno.get("data_emissione") or assegno.get("data")
        
        # Cerca la fattura
        fattura = fatture_by_id.get(fattura_id)
        
        problema = {
            "assegno_id": assegno_id,
            "numero_assegno": numero_assegno,
            "importo_assegno": importo_assegno,
            "beneficiario": beneficiario,
            "data_assegno": data_assegno,
            "fattura_id": fattura_id,
            "problemi": [],
            "suggerimenti": []
        }
        
        # PROBLEMA 1: Fattura non trovata
        if not fattura:
            problema["problemi"].append("Fattura associata non trovata nel database")
            statistiche["problemi_fattura_mancante"] += 1
            
            # Suggerisci solo riferimenti dichiarati con importo identico al centesimo.
            fatture_simili = [
                f for f in fatture_cursor
                if amounts_equal_to_cent(
                    f.get("total_amount") or f.get("importo_totale"),
                    importo_assegno,
                )
                and _assegno_riferisce_fattura(assegno, f)
                and not fornitore_esclude_assegno(f.get("supplier_name") or "")
            ]
            if fatture_simili:
                problema["suggerimenti"] = [
                    {
                        "fattura_id": f.get("id"),
                        "numero": f.get("invoice_number"),
                        "fornitore": (f.get("supplier_name") or "")[:40],
                        "importo": f.get("total_amount"),
                        "match_type": "numero_fattura_e_importo_esatti"
                    }
                    for f in fatture_simili[:5]
                ]
            problemi.append(problema)
            continue
        
        # Dati fattura
        importo_fattura = float(fattura.get("total_amount") or fattura.get("importo_totale") or 0)
        fornitore = fattura.get("supplier_name") or fattura.get("fornitore_ragione_sociale") or ""
        data_fattura = fattura.get("invoice_date") or fattura.get("data_documento") or ""
        fattura_pagata = fattura.get("pagato") or fattura.get("status") == "paid"
        
        problema["fattura_numero"] = fattura.get("invoice_number") or fattura.get("numero_documento")
        problema["fattura_fornitore"] = fornitore
        problema["fattura_importo"] = importo_fattura
        problema["fattura_data"] = data_fattura
        problema["fattura_pagata"] = fattura_pagata
        
        ha_problemi = False
        
        # PROBLEMA 2: importo diverso anche di un solo centesimo.
        differenza_importo = abs(importo_assegno - importo_fattura)
        if not amounts_equal_to_cent(importo_assegno, importo_fattura):
            problema["problemi"].append(f"Importo differisce di €{differenza_importo:.2f}")
            problema["differenza_importo"] = differenza_importo
            statistiche["problemi_importo"] += 1
            ha_problemi = True
        
        # PROBLEMA 3: Fornitore diverso (fuzzy match < 60%)
        if beneficiario and fornitore:
            similarity = fuzz.token_set_ratio(beneficiario.upper(), fornitore.upper())
            if similarity < 60:
                problema["problemi"].append(f"Beneficiario diverso da fornitore (match: {similarity}%)")
                problema["similarity_score"] = similarity
                statistiche["problemi_fornitore"] += 1
                ha_problemi = True
        
        # PROBLEMA 4: Fattura già pagata
        metodo_effettivo = str(fattura.get("metodo_pagamento_effettivo") or "").lower()
        pagamento_coerente = assegno.get("stato") == "incassato" and metodo_effettivo == "assegno"
        if fattura_pagata and not pagamento_coerente:
            problema["problemi"].append("Fattura già marcata come pagata")
            statistiche["problemi_fattura_pagata"] += 1
            ha_problemi = True
        
        # PROBLEMA 5: Data molto diversa (>180 giorni)
        if data_assegno and data_fattura:
            try:
                if isinstance(data_assegno, str):
                    da = datetime.strptime(data_assegno[:10], "%Y-%m-%d")
                else:
                    da = data_assegno
                if isinstance(data_fattura, str):
                    df = datetime.strptime(data_fattura[:10], "%Y-%m-%d")
                else:
                    df = data_fattura
                giorni_differenza = abs((da - df).days)
                if giorni_differenza > 180:
                    problema["problemi"].append(f"Date differiscono di {giorni_differenza} giorni")
                    problema["giorni_differenza"] = giorni_differenza
                    statistiche["problemi_data"] += 1
                    ha_problemi = True
            except Exception:
                pass
        
        if ha_problemi:
            # Cerca fatture alternative suggerite
            suggerimenti = []
            for f in fatture_cursor:
                f_fornitore = f.get("supplier_name") or f.get("fornitore_ragione_sociale") or ""
                f_importo = float(f.get("total_amount") or f.get("importo_totale") or 0)
                f_pagata = f.get("pagato") or f.get("status") == "paid"
                
                if f_pagata or f.get("id") == fattura_id:
                    continue
                if fornitore_esclude_assegno(f_fornitore):
                    continue

                # Numero fattura dichiarato e importo esatto sono entrambi obbligatori.
                if (
                    amounts_equal_to_cent(f_importo, importo_assegno)
                    and _assegno_riferisce_fattura(assegno, f)
                ):
                    similarity = fuzz.token_set_ratio(beneficiario.upper(), f_fornitore.upper()) if beneficiario else 0
                    suggerimenti.append({
                        "fattura_id": f.get("id"),
                        "numero": f.get("invoice_number") or f.get("numero_documento"),
                        "fornitore": f_fornitore[:40],
                        "importo": f_importo,
                        "similarity": similarity,
                        "match_type": "numero_fattura_e_importo_esatti"
                    })
            
            suggerimenti.sort(key=lambda x: x.get("similarity", 0), reverse=True)
            problema["suggerimenti"] = suggerimenti[:5]
            problemi.append(problema)
        else:
            statistiche["associazioni_corrette"] += 1
    
    return {
        "statistiche": statistiche,
        "problemi": problemi,
        "totale_problemi": len(problemi)
    }


@router.put("/correggi-associazione/{assegno_id}")
async def correggi_associazione_assegno(
    assegno_id: str,
    nuova_fattura_id: Optional[str] = Body(None, description="ID della nuova fattura da associare"),
    aggiorna_beneficiario: bool = Body(False, description="Aggiorna beneficiario dal fornitore")
) -> Dict[str, Any]:
    """
    Corregge l'associazione di un assegno con una fattura.
    """
    db = Database.get_db()
    
    assegno = await db[COLLECTION_ASSEGNI].find_one({"id": assegno_id})
    if not assegno:
        raise HTTPException(status_code=404, detail="Assegno non trovato")
    
    vecchia_fattura_id = assegno.get("fattura_id")
    update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}
    
    if nuova_fattura_id:
        fattura = await db["invoices"].find_one({"id": nuova_fattura_id})
        if not fattura:
            raise HTTPException(status_code=404, detail="Fattura non trovata")

        numero_fattura_val = fattura.get("invoice_number") or fattura.get("numero_documento")
        importo_fattura_val = float(fattura.get("total_amount") or fattura.get("importo_totale") or 0)
        importo_assegno_val = float(assegno.get("importo") or 0)
        if not amounts_equal_to_cent(importo_assegno_val, importo_fattura_val):
            raise HTTPException(
                status_code=409,
                detail="Importo assegno e fattura devono coincidere al centesimo",
            )
        piva_assegno = _norm_piva(assegno.get("fornitore_piva"))
        piva_fattura = _norm_piva(
            fattura.get("supplier_vat") or fattura.get("cedente_piva")
            or fattura.get("partita_iva")
        )
        beneficiario = assegno.get("beneficiario") or ""
        fornitore = fattura.get("supplier_name") or fattura.get("fornitore_ragione_sociale") or ""
        if not ((piva_assegno and piva_assegno == piva_fattura)
                or (beneficiario and fornitore and identita_coincide(beneficiario, fornitore))):
            raise HTTPException(status_code=409, detail="Fornitore della fattura non coerente con l'assegno")
        banca_confermata = bool(
            assegno.get("movimento_estratto_conto_id")
            or assegno.get("riconciliato_con_ec")
            or assegno.get("stato") == "incassato"
        )

        update_data["fattura_id"] = nuova_fattura_id
        update_data["pagato"] = banca_confermata
        # Stato canonico: "assegnato" (era "associato", valore NON presente in
        # ASSEGNO_STATI → fuori schema, invisibile ai filtri per stato). Vedi P0.5.
        update_data["stato"] = "assegnato"
        # alias per consistenza GET
        update_data["numero_fattura"] = numero_fattura_val
        update_data["fattura_numero"] = numero_fattura_val
        update_data["data_fattura"] = fattura.get("invoice_date") or fattura.get("data_documento")
        update_data["importo_fattura"] = importo_fattura_val

        scarto = 0.0
        update_data["scarto_fattura_assegno"] = scarto

        if aggiorna_beneficiario:
            update_data["beneficiario"] = fattura.get("supplier_name") or fattura.get("fornitore_ragione_sociale")

        if vecchia_fattura_id:
            await db["invoices"].update_one(
                {"id": vecchia_fattura_id},
                {"$set": {"pagato": False, "status": "imported", "assegno_id": None}}
            )

        # Il collegamento assegno-fattura è un intento; il pagamento diventa
        # reale soltanto con il riscontro dell'estratto conto.
        await db["invoices"].update_one(
            {"id": nuova_fattura_id},
            {"$set": {
                "assegno_id": assegno_id,
                "pagato": banca_confermata,
                "status": "paid" if banca_confermata else "pending",
                "stato_finanziario": "riconciliato" if banca_confermata else "in_attesa_estratto_conto",
                "data_pagamento": (
                    assegno.get("data_incasso") or assegno.get("data_emissione")
                    if banca_confermata else None
                ),
                "metodo_pagamento_effettivo": "assegno",
            }}
        )

        message = f"Associazione corretta per assegno {assegno.get('numero_assegno') or assegno.get('numero')}"
    else:
        update_data["fattura_id"] = None
        update_data["pagato"] = False
        update_data["stato"] = "emesso"
        update_data["numero_fattura"] = None
        update_data["fattura_numero"] = None
        update_data["data_fattura"] = None
        update_data["importo_fattura"] = None
        update_data["scarto_fattura_assegno"] = None

        if vecchia_fattura_id:
            await db["invoices"].update_one(
                {"id": vecchia_fattura_id},
                {"$set": {"pagato": False, "status": "imported", "assegno_id": None}}
            )

        message = f"Associazione rimossa per assegno {assegno.get('numero_assegno') or assegno.get('numero')}"

    await db[COLLECTION_ASSEGNI].update_one({"id": assegno_id}, {"$set": update_data})

    response: Dict[str, Any] = {
        "success": True,
        "message": message,
        "assegno_id": assegno_id,
        "nuova_fattura_id": nuova_fattura_id,
    }
    if nuova_fattura_id:
        response["scarto_fattura_assegno"] = update_data.get("scarto_fattura_assegno")
        response["banca_confermata"] = banca_confermata
    return response


# === ROUTE AUTO-MATCH (statiche — prima delle dinamiche) ===

@router.post("/auto-match")
async def auto_match_assegni(
    dry_run: bool = Query(True, description="Sola anteprima; applicazione con conferma esplicita"),
    anno: Optional[int] = Query(None, ge=2000, le=2100),
) -> Dict[str, Any]:
    """
    🤖 Auto-matcher Assegni ↔ Fatture (4 livelli, N:M, tolleranza ±0,005€).
    Vedi /app/memoria/LOGICA_OPERATIVA.md per i dettagli.
    """
    if not dry_run:
        raise HTTPException(
            status_code=400,
            detail="Auto-match diretto disabilitato: genera l'anteprima e conferma una proposta esplicita",
        )
    from app.routers.bank.assegni_auto_match import run_auto_match
    db = Database.get_db()
    report = await run_auto_match(db, dry_run=dry_run, anno=anno)
    return {
        "success": True,
        **report,
        "totali": {
            "L1": len(report["match_l1"]),
            "L2": len(report["match_l2"]),
            "L3": len(report["match_l3"]),
            "L4": len(report["match_l4"]),
            "ambigui": len(report["ambigui"]),
            "non_trovati": len(report["non_trovati"]),
        },
    }


@router.post("/auto-match/conferma")
async def conferma_auto_match(payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Applica una sola proposta dopo ricalcolo e conferma esplicita."""
    from app.routers.bank.assegni_auto_match import conferma_proposta_match
    try:
        result = await conferma_proposta_match(
            Database.get_db(),
            assegno_ids=payload.get("assegno_ids") or [],
            fattura_ids=payload.get("fattura_ids") or [],
            livello=payload.get("livello") or "",
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"success": True, **result}


@router.get("/ambigui")
async def lista_ambigui(
    anno: Optional[int] = Query(None, ge=2000, le=2100),
) -> Dict[str, Any]:
    """Elenca gli assegni ambigui (più fatture candidate dell'auto-matcher)."""
    from app.routers.bank.assegni_auto_match import run_auto_match
    db = Database.get_db()
    report = await run_auto_match(db, dry_run=True, anno=anno)

    ambigui_dettaglio = []
    for amb in report.get("ambigui", []):
        ass = await db["assegni"].find_one({"id": amb["assegno_id"]}, {"_id": 0})
        if not ass:
            continue
        cands = []
        for c in amb.get("candidates", []):
            inv = await db["invoices"].find_one({"id": c["fattura_id"]}, {"_id": 0})
            if not inv:
                continue
            total = float(inv.get("total_amount") or inv.get("importo_totale") or 0)
            paid = float(inv.get("importo_pagato") or 0)
            cands.append({
                "fattura_id": c["fattura_id"],
                "numero": inv.get("invoice_number") or inv.get("numero_fattura"),
                "data": inv.get("invoice_date") or inv.get("data_fattura"),
                "importo_totale": total,
                "importo_pagato": paid,
                "importo_residuo": round(total - paid, 2),
                "fornitore": inv.get("supplier_name") or inv.get("cedente_denominazione"),
                "payment_status": inv.get("payment_status"),
            })
        ambigui_dettaglio.append({
            "livello": amb.get("livello"),
            "assegno_id": ass.get("id"),
            "assegno_numero": ass.get("numero"),
            "importo": float(ass.get("importo") or 0),
            "data_emissione": ass.get("data_emissione"),
            "fornitore_piva": ass.get("fornitore_piva"),
            "fornitore_ragione_sociale": ass.get("fornitore_ragione_sociale") or ass.get("beneficiario"),
            "carnet_id": ass.get("carnet_id"),
            "candidates": cands,
        })

    # Il riscontro dell'estratto conto genera proposte conservative quando
    # conosce numero assegno e importo ma non il numero fattura. Queste
    # proposte prima rimanevano nel DB e non venivano mostrate dalla pagina.
    proposte_ec = await db["proposte_associazione_assegni"].find(
        {"stato": "da_confermare", "source": "estratto_conto"}, {"_id": 0}
    ).sort("created_at", -1).to_list(2000)
    per_assegno = {a["assegno_id"]: a for a in ambigui_dettaglio}
    for proposta in proposte_ec:
        assegno_id = proposta.get("assegno_id")
        fattura_id = proposta.get("fattura_id")
        if not assegno_id or not fattura_id:
            continue
        ass = await db["assegni"].find_one({"id": assegno_id}, {"_id": 0})
        if not ass or ass.get("fatture_collegate"):
            continue
        data_assegno = str(
            ass.get("data_incasso") or ass.get("data_emissione") or ass.get("data") or ""
        )
        if anno and data_assegno[:4].isdigit() and int(data_assegno[:4]) != anno:
            continue
        inv = await db["invoices"].find_one({"id": fattura_id}, {"_id": 0})
        if not inv or inv.get("pagato") is True:
            continue
        total = float(inv.get("total_amount") or inv.get("importo_totale") or 0)
        paid = float(inv.get("importo_pagato") or 0)
        voce = per_assegno.setdefault(assegno_id, {
            "livello": "EC",
            "origine": "estratto_conto",
            "motivo": (
                "Importo o rata compatibile, ma manca il numero fattura sul pagamento: "
                "selezione manuale obbligatoria"
            ),
            "assegno_id": ass.get("id"),
            "assegno_numero": ass.get("numero"),
            "importo": float(ass.get("importo") or 0),
            "data_emissione": ass.get("data_emissione") or ass.get("data_incasso") or ass.get("data"),
            "fornitore_piva": ass.get("fornitore_piva"),
            "fornitore_ragione_sociale": ass.get("fornitore_ragione_sociale") or ass.get("beneficiario"),
            "numero_fattura_dichiarato": ass.get("numero_fattura"),
            "carnet_id": ass.get("carnet_id"),
            "candidates": [],
        })
        if any(c["fattura_id"] == fattura_id for c in voce["candidates"]):
            continue
        voce["candidates"].append({
            "fattura_id": fattura_id,
            "numero": inv.get("invoice_number") or inv.get("numero_fattura"),
            "data": inv.get("invoice_date") or inv.get("data_fattura"),
            "importo_totale": total,
            "importo_pagato": paid,
            "importo_residuo": round(total - paid, 2),
            "fornitore": inv.get("supplier_name") or inv.get("cedente_denominazione"),
            "fornitore_piva": inv.get("supplier_vat") or inv.get("cedente_piva"),
            "payment_status": inv.get("payment_status"),
        })

    ambigui_dettaglio = [v for v in per_assegno.values() if v.get("candidates")]
    ambigui_dettaglio.sort(
        key=lambda x: (str(x.get("data_emissione") or ""), x.get("assegno_numero") or ""),
        reverse=True,
    )
    return {"success": True, "count": len(ambigui_dettaglio), "ambigui": ambigui_dettaglio}


@router.post("/{assegno_id}/risolvi-ambiguo")
async def risolvi_ambiguo(
    assegno_id: str,
    payload: Dict[str, Any] = Body(...),
) -> Dict[str, Any]:
    """Risolve manualmente un assegno ambiguo collegandolo a 1+ fatture."""
    from app.routers.bank.assegni_auto_match import _apply_match
    fattura_ids = payload.get("fattura_ids") or ([payload["fattura_id"]] if payload.get("fattura_id") else [])
    if not fattura_ids:
        raise HTTPException(status_code=400, detail="fattura_ids è obbligatorio")
    db = Database.get_db()
    ass = await db["assegni"].find_one({"id": assegno_id}, {"_id": 0})
    if not ass:
        raise HTTPException(status_code=404, detail="Assegno non trovato")
    if ass.get("fatture_collegate"):
        raise HTTPException(status_code=400, detail="Assegno già collegato")
    fatture = []
    for fid in fattura_ids:
        inv = await db["invoices"].find_one({"id": fid}, {"_id": 0})
        if not inv:
            raise HTTPException(status_code=404, detail=f"Fattura {fid} non trovata")
        total = float(inv.get("total_amount") or inv.get("importo_totale") or 0)
        paid = float(inv.get("importo_pagato") or 0)
        inv["_residuo"] = round(total - paid, 2)
        fatture.append(inv)
    importo_assegno = round(float(ass.get("importo") or 0), 2)
    if len(fatture) == 1:
        inv = fatture[0]
        rate = [
            round(float(r.get("importo") or 0), 2)
            for r in (inv.get("pagamento_rate") or [])
            if isinstance(r, dict)
        ]
        importo_valido = (
            amounts_equal_to_cent(importo_assegno, inv["_residuo"])
            or any(amounts_equal_to_cent(importo_assegno, rata) for rata in rate)
        )
    else:
        importo_valido = amounts_equal_to_cent(
            importo_assegno, sum(f["_residuo"] for f in fatture)
        )
    if not importo_valido:
        raise HTTPException(
            status_code=409,
            detail=(
                "L'importo dell'assegno deve coincidere al centesimo con la "
                "fattura, una rata XML o la somma delle fatture selezionate"
            ),
        )

    # Se l'assegno e' gia' stato riscontrato in banca, la scelta manuale deve
    # completare anche fattura, estratto conto e Prima Nota esistente. Il
    # percorso generico _apply_match registra invece solo un intento futuro.
    if len(fatture) == 1 and ass.get("incassato_confermato_banca"):
        from app.services.assegni_estratto_conto import collega_assegno_riconciliato_a_fattura
        try:
            res = await collega_assegno_riconciliato_a_fattura(db, ass, fatture[0])
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"success": True, **res}
    res = await _apply_match(db, [ass], fatture, livello="MANUAL", dry_run=False)
    return {"success": True, **res}


@router.get("/proposte-associazione")
async def get_proposte_associazione() -> Dict[str, Any]:
    """Restituisce le proposte di associazione da confermare manualmente."""
    db = Database.get_db()
    
    proposte = await db["proposte_associazione_assegni"].find(
        {"stato": "da_confermare"},
        {"_id": 0}
    ).sort("confidenza", -1).to_list(100)
    
    return {
        "success": True,
        "totale": len(proposte),
        "proposte": proposte
    }


# === ROUTE DINAMICHE (con parametri) - DEVONO STARE DOPO LE STATICHE ===

@router.get("/{assegno_id}")
async def get_assegno(assegno_id: str) -> Dict[str, Any]:
    """Dettaglio singolo assegno."""
    db = Database.get_db()
    
    assegno = await db[COLLECTION_ASSEGNI].find_one(
        {"$or": [{"id": assegno_id}, {"numero": assegno_id}]},
        {"_id": 0}
    )
    
    if not assegno:
        raise HTTPException(status_code=404, detail="Assegno non trovato")
    
    return assegno


@router.put("/{assegno_id}")
async def update_assegno(
    assegno_id: str,
    data: Dict[str, Any] = Body(...)
) -> Dict[str, Any]:
    """
    Aggiorna assegno (compila dati, cambia stato, etc.).
    """
    db = Database.get_db()
    assegno_esistente = await db[COLLECTION_ASSEGNI].find_one(
        {"$or": [{"id": assegno_id}, {"numero": assegno_id}]},
        {"_id": 0},
    )
    if not assegno_esistente:
        raise HTTPException(status_code=404, detail="Assegno non trovato")
    
    # Rimuovi campi non modificabili
    data.pop("id", None)
    data.pop("numero", None)
    data.pop("created_at", None)
    
    # Valida stato se fornito
    if "stato" in data and data["stato"] not in ASSEGNO_STATI:
        raise HTTPException(status_code=400, detail=f"Stato non valido. Valori ammessi: {list(ASSEGNO_STATI.keys())}")
    if (
        assegno_esistente.get("incassato_confermato_banca")
        and data.get("stato") not in (None, "incassato", "annullato")
    ):
        # Una modifica anagrafica non puo' cancellare l'evidenza gia' letta
        # dall'estratto conto.
        data.pop("stato", None)
    
    # Se si compila un assegno vuoto, cambia stato automaticamente
    importo_effettivo = data.get("importo", assegno_esistente.get("importo"))
    riferimento_effettivo = (
        data.get("beneficiario", assegno_esistente.get("beneficiario"))
        or data.get("fornitore_piva", assegno_esistente.get("fornitore_piva"))
        or data.get("numero_fattura", assegno_esistente.get("numero_fattura"))
    )
    if importo_effettivo and riferimento_effettivo:
        if assegno_esistente.get("stato") == "vuoto":
            data["stato"] = "compilato"
    
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    result = await db[COLLECTION_ASSEGNI].update_one(
        {"$or": [{"id": assegno_id}, {"numero": assegno_id}]},
        {"$set": data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Assegno non trovato")

    from app.services.assegni_fattura_intent import prepara_intento_assegno
    intento = await prepara_intento_assegno(db, str(assegno_esistente["id"]))
    
    return {
        "message": "Assegno aggiornato con successo",
        "intento_fattura": intento,
    }


class FatturaQuotaIn(BaseModel):
    fattura_id: str
    # Positiva per una fattura normale, negativa per una nota di credito (TD04)
    # che netta l'importo dovuto — vedi Caso F in memoria/LOGICA_OPERATIVA.md.
    quota: float


class FattureCollegateIn(BaseModel):
    fatture: List[FatturaQuotaIn] = Field(default_factory=list)


async def _aggiorna_stato_intento_fattura(db, fattura_id: str, now: str) -> None:
    """Ricalcola l'intento assegno senza alterare il pagamento reale."""
    inv = await db["invoices"].find_one({"id": fattura_id}, {"_id": 0})
    if not inv:
        return
    links = [x for x in inv.get("assegni_collegati") or [] if isinstance(x, dict)]
    if links or inv.get("riconciliato_con_ec"):
        await db["invoices"].update_one({"id": fattura_id}, {"$set": {
            "metodo_pagamento_previsto": "assegno",
            "metodo_pagamento_override_source": "assegno_compilato",
            "pagamento_specifico_prevale_su_fornitore": True,
            "stato_finanziario": (
                "riconciliato" if inv.get("riconciliato_con_ec")
                else "in_attesa_estratto_conto"
            ),
            "updated_at": now,
        }})
        return
    original = inv.get("metodo_pagamento_fornitore_originale")
    update: Dict[str, Any] = {
        "$set": {"stato_finanziario": "provvisoria", "updated_at": now},
        "$unset": {
            "metodo_pagamento_previsto": "", "metodo_pagamento_override_source": "",
            "pagamento_specifico_prevale_su_fornitore": "",
        },
    }
    if original:
        update["$set"]["metodo_pagamento"] = original
    await db["invoices"].update_one({"id": fattura_id}, update)


@router.put("/{assegno_id}/fatture-collegate")
async def collega_fatture_assegno(assegno_id: str, body: FattureCollegateIn) -> Dict[str, Any]:
    """
    Collega/scollega fatture a un assegno con il modello a quote N:M
    documentato in memoria/LOGICA_OPERATIVA.md: ogni collegamento ha una
    quota in euro (parte dell'importo dell'assegno che paga quella fattura).
    L'importo nominale dell'assegno NON viene mai modificato da qui.

    Sostituisce l'intero set di collegamenti esistenti dell'assegno con
    quello passato (il modale "Collega Fatture" invia sempre la selezione
    finale completa dell'utente): i vecchi collegamenti vengono prima
    annullati sulle rispettive fatture, poi si applicano i nuovi.
    """
    db = Database.get_db()
    now = datetime.now(timezone.utc).isoformat()

    assegno = await db[COLLECTION_ASSEGNI].find_one(
        {"$or": [{"id": assegno_id}, {"numero": assegno_id}]}
    )
    if not assegno:
        raise HTTPException(status_code=404, detail="Assegno non trovato")

    if len(body.fatture) > MAX_RATE:
        raise HTTPException(status_code=400, detail=f"Massimo {MAX_RATE} fatture per assegno")
    if any(abs(f.quota) < 0.005 for f in body.fatture):
        raise HTTPException(status_code=400, detail="Le quote non possono essere zero")

    importo_assegno = _f(assegno.get("importo"))

    # Carica le fatture nuove: devono esistere e appartenere allo stesso fornitore
    fatture_map: Dict[str, Dict[str, Any]] = {}
    for f in body.fatture:
        if f.fattura_id in fatture_map:
            continue
        inv = await db["invoices"].find_one({"id": f.fattura_id}, {"_id": 0})
        if not inv:
            raise HTTPException(status_code=404, detail=f"Fattura {f.fattura_id} non trovata")
        fatture_map[f.fattura_id] = inv

    piva_set = {
        _norm_piva(inv.get("supplier_vat") or inv.get("cedente_piva") or inv.get("partita_iva"))
        for inv in fatture_map.values()
    }
    piva_set.discard("")
    if len(piva_set) > 1:
        raise HTTPException(
            status_code=400,
            detail="Tutte le fatture collegate a uno stesso assegno devono essere dello stesso fornitore",
        )

    somma_quote = round(sum(f.quota for f in body.fatture), 2)
    if body.fatture and not amounts_equal_to_cent(somma_quote, importo_assegno):
        raise HTTPException(
            status_code=400,
            detail=(
                f"La somma delle fatture (€{somma_quote:.2f}) deve coincidere al centesimo "
                f"con l'importo dell'assegno (€{importo_assegno:.2f})"
            ),
        )

    for quota_input in body.fatture:
        inv = fatture_map[quota_input.fattura_id]
        if quota_input.quota > 0:
            disponibile, impegnato, totale_documento = capienza_assegno_fattura(
                inv, assegno.get("id"), quota_input.quota,
            )
            if not disponibile:
                numero = inv.get("invoice_number") or inv.get("numero_fattura") or quota_input.fattura_id
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Fattura {numero} gia attribuita per EUR {impegnato:.2f}: "
                        f"la nuova quota supererebbe il totale di EUR {totale_documento:.2f}"
                    ),
                )
        totale = _f(inv.get("importo_residuo") if inv.get("importo_residuo") is not None
                    else inv.get("total_amount") or inv.get("importo_totale"))
        if not amounts_equal_to_cent(quota_input.quota, totale):
            numero = inv.get("invoice_number") or inv.get("numero_fattura") or quota_input.fattura_id
            raise HTTPException(
                status_code=400,
                detail=(
                    f"La quota della fattura {numero} deve coincidere al centesimo "
                    f"con il suo importo aperto (€{abs(totale):.2f})"
                ),
            )

    # 1) Annulla i vecchi collegamenti sulle fatture precedentemente collegate
    vecchie = assegno.get("fatture_collegate") or []
    for vc in vecchie:
        old_fid = vc.get("fattura_id")
        if not old_fid:
            continue
        await db["invoices"].update_one(
            {"id": old_fid}, {"$pull": {"assegni_collegati": {"assegno_id": assegno["id"]}}}
        )
        await _aggiorna_stato_intento_fattura(db, old_fid, now)

    # 2) Applica i nuovi collegamenti
    fatture_collegate = []
    for f in body.fatture:
        quota = round(f.quota, 2)
        fatture_collegate.append({
            "fattura_id": f.fattura_id,
            "quota": quota,
            "data_collegamento": now,
        })
        inv = fatture_map[f.fattura_id]
        original_method = inv.get("metodo_pagamento") or inv.get("payment_method")
        await db["invoices"].update_one(
            {"id": f.fattura_id},
            {
                "$set": {
                    "metodo_pagamento_fornitore_originale": original_method,
                    "metodo_pagamento": "assegno",
                    "metodo_pagamento_previsto": "assegno",
                    "metodo_pagamento_override_source": "assegno_compilato",
                    "pagamento_specifico_prevale_su_fornitore": True,
                    "stato_finanziario": "in_attesa_estratto_conto",
                    "updated_at": now,
                },
                "$addToSet": {"assegni_collegati": {
                    "assegno_id": assegno["id"],
                    "numero": assegno.get("numero"),
                    "quota": quota,
                    "data_collegamento": now,
                    "match_auto": False,
                    "banca_confermata": False,
                }},
            },
        )
        # Solo le quote positive (fatture normali) generano un movimento banca:
        # una nota di credito (quota negativa, Caso F) netta l'importo dovuto
        # ma non è di per sé un'uscita di denaro.
        # La Prima Nota Banca nasce solo dal movimento reale dell'estratto conto.

    fornitore_piva = next(iter(piva_set), None)
    first_inv = next(iter(fatture_map.values()), None)
    fornitore_nome = (first_inv.get("supplier_name") or first_inv.get("cedente_denominazione")) if first_inv else None
    data_fattura_collegata = (
        first_inv.get("invoice_date")
        or first_inv.get("data_fattura")
        or first_inv.get("data_documento")
    ) if first_inv and len(body.fatture) == 1 else None
    numeri_fatture = ", ".join(
        (fatture_map[f.fattura_id].get("invoice_number") or fatture_map[f.fattura_id].get("numero_fattura") or "")
        for f in body.fatture
    )

    if fatture_collegate:
        nuovo_stato = "assegnato" if abs(somma_quote - importo_assegno) <= TOLL else "parzialmente_assegnato"
    else:
        nuovo_stato = "compilato" if assegno.get("beneficiario") else "vuoto"

    await db[COLLECTION_ASSEGNI].update_one(
        {"id": assegno["id"]},
        {"$set": {
            "fatture_collegate": fatture_collegate,
            "importo_assegnato": somma_quote,
            "fornitore_piva": fornitore_piva or assegno.get("fornitore_piva"),
            "fornitore_ragione_sociale": fornitore_nome or assegno.get("fornitore_ragione_sociale"),
            "beneficiario": fornitore_nome or assegno.get("beneficiario"),
            "numero_fattura": numeri_fatture if fatture_collegate else None,
            "data_fattura": data_fattura_collegata,
            "fattura_collegata": body.fatture[0].fattura_id if len(body.fatture) == 1 else None,
            "stato": nuovo_stato,
            "match_auto": False,
            "metodo_pagamento_previsto": "assegno" if fatture_collegate else None,
            "stato_finanziario": "in_attesa_estratto_conto" if fatture_collegate else None,
            "pagamento_specifico_prevale_su_fornitore": bool(fatture_collegate),
            "updated_at": now,
        }}
    )

    riconciliazione = None
    if fatture_collegate and assegno.get("incassato_confermato_banca"):
        from app.services.assegni_estratto_conto import collega_assegno_riconciliato_a_fatture
        try:
            riconciliazione = await collega_assegno_riconciliato_a_fatture(
                db,
                {**assegno, "fatture_collegate": fatture_collegate},
                [
                    {"fattura": fatture_map[item.fattura_id], "quota": item.quota}
                    for item in body.fatture
                ],
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    return {
        "success": True,
        "assegno_id": assegno["id"],
        "fatture_collegate": fatture_collegate,
        "importo_assegnato": somma_quote,
        "stato": nuovo_stato,
        "riconciliazione_banca": riconciliazione,
    }


@router.post("/{assegno_id}/emetti")
async def emetti_assegno(
    assegno_id: str,
    data_emissione: Optional[str] = Body(None)
) -> Dict[str, str]:
    """
    Emette l'assegno (cambia stato a 'emesso').
    """
    db = Database.get_db()
    
    assegno = await db[COLLECTION_ASSEGNI].find_one(
        {"$or": [{"id": assegno_id}, {"numero": assegno_id}]}
    )
    
    if not assegno:
        raise HTTPException(status_code=404, detail="Assegno non trovato")
    
    if assegno.get("stato") == "vuoto":
        raise HTTPException(status_code=400, detail="Impossibile emettere un assegno vuoto. Compilarlo prima.")
    
    if not data_emissione:
        data_emissione = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    await db[COLLECTION_ASSEGNI].update_one(
        {"_id": assegno["_id"]},
        {"$set": {
            "stato": "emesso",
            "data_emissione": data_emissione,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    return {"message": "Assegno emesso: in attesa del riscontro nell'estratto conto"}


@router.post("/{assegno_id}/incassa")
async def incassa_assegno(
    assegno_id: str,
    data_incasso: Optional[str] = Body(None),
    movimento_estratto_conto_id: Optional[str] = Body(None)
) -> Dict[str, Any]:
    """Segna assegno come incassato e propaga su fattura, scadenzario, prima nota."""
    db = Database.get_db()
    assegno = await db[COLLECTION_ASSEGNI].find_one(
        {"$or": [{"id": assegno_id}, {"numero": assegno_id}]}
    )
    if not assegno:
        raise HTTPException(status_code=404, detail="Assegno non trovato")
    
    if not movimento_estratto_conto_id:
        await db[COLLECTION_ASSEGNI].update_one(
            {"id": assegno["id"]},
            {"$set": {
                "stato": "emesso",
                "incassato_confermato_banca": False,
                "stato_finanziario": "in_attesa_estratto_conto",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }},
        )
        return {
            "message": "Assegno in attesa del movimento reale nell'estratto conto",
            "fattura_chiusa": False,
            "prima_nota_riconciliata": False,
            "confermato_banca": False,
        }

    movimento_ec = await db["estratto_conto_movimenti"].find_one(
        {"id": movimento_estratto_conto_id}, {"_id": 0}
    )
    if not movimento_ec:
        raise HTTPException(status_code=404, detail="Movimento dell'estratto conto non trovato")
    data_incasso = (
        movimento_ec.get("data") or movimento_ec.get("date") or data_incasso
        or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    )

    # 1. Aggiorna stato assegno. "incassato_confermato_banca" distingue un
    # riscontro reale (movimento_estratto_conto_id valorizzato) da un
    # semplice "segna come incassato" manuale senza alcun movimento bancario
    # collegato — prima il campo "incassato" non permetteva questa distinzione,
    # dando l'impressione che ogni assegno incassato fosse verificato in banca.
    set_data = {
        "stato": "incassato",
        "data_incasso": data_incasso,
        "incassato_confermato_banca": True,
        "stato_finanziario": "riconciliato",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    set_data["movimento_estratto_conto_id"] = movimento_estratto_conto_id
    await db[COLLECTION_ASSEGNI].update_one(
        {"id": assegno["id"]},
        {"$set": set_data}
    )
    # 2. Prima nota banca → riconciliata
    if assegno.get("prima_nota_banca_id"):
        await db["prima_nota_banca"].update_one(
            {"id": assegno["prima_nota_banca_id"]},
            {"$set": {"riconciliato": True, "data_riconciliazione": data_incasso,
                      "movimento_estratto_conto_id": movimento_estratto_conto_id,
                      "updated_at": datetime.now(timezone.utc).isoformat()}}
        )
    # 3. Fattura → pagata
    if assegno.get("fattura_collegata"):
        fid = assegno["fattura_collegata"]
        await db["invoices"].update_one(
            {"id": fid},
            {"$set": {"data_ultimo_incasso_assegno": data_incasso,
                      "metodo_pagamento_effettivo": "assegno",
                      "updated_at": datetime.now(timezone.utc).isoformat()}}
        )
        # 4. Scadenzario → chiuso
        # --- EVENT BUS: propaga FATTURA_PAGATA (assegno incassato) ---
        try:
            from app.services.event_bus import propagate_event, EventTypes
            await propagate_event(EventTypes.FATTURA_PAGATA, {
                "fattura_id": fid,
                "metodo_pagamento": "assegno",
                "data_pagamento": data_incasso,
                "importo": assegno.get("importo"),
                "assegno_id": assegno["id"],
                "assegno_numero": assegno.get("numero"),
            }, db, source_module="assegni_incassa")
        except Exception:
            logger.exception("Errore propagazione fattura.pagata (incassa assegno)")
    # 5. Estratto conto → riconciliato
    await db["estratto_conto_movimenti"].update_one(
        {"id": movimento_estratto_conto_id},
        {"$set": {"riconciliato": True, "riconciliato_con": "assegno",
                  "assegno_id": assegno["id"],
                  "riconciliato_at": datetime.now(timezone.utc).isoformat()}}
    )
    return {"message": "Assegno incassato",
            "fattura_chiusa": bool(assegno.get("fattura_collegata")),
            "prima_nota_riconciliata": bool(assegno.get("prima_nota_banca_id")),
            "confermato_banca": bool(movimento_estratto_conto_id)}


@router.post("/{assegno_id}/annulla")
async def annulla_assegno(assegno_id: str) -> Dict[str, str]:
    """Annulla assegno."""
    db = Database.get_db()
    
    result = await db[COLLECTION_ASSEGNI].update_one(
        {"$or": [{"id": assegno_id}, {"numero": assegno_id}]},
        {"$set": {
            "stato": "annullato",
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Assegno non trovato")
    
    return {"message": "Assegno annullato"}


@router.delete("/clear-generated")
async def clear_generated_assegni(stato: str = Query("vuoto")) -> Dict[str, Any]:
    """
    Elimina tutti gli assegni con un determinato stato.
    Default: elimina solo quelli vuoti.
    """
    db = Database.get_db()
    
    if stato not in ASSEGNO_STATI:
        raise HTTPException(status_code=400, detail=f"Stato non valido. Valori ammessi: {list(ASSEGNO_STATI.keys())}")
    
    result = await db[COLLECTION_ASSEGNI].delete_many({"stato": stato})
    
    return {
        "message": f"Eliminati {result.deleted_count} assegni con stato '{stato}'",
        "deleted_count": result.deleted_count
    }


@router.delete("/{assegno_id}")
async def delete_assegno(
    assegno_id: str,
    force: bool = Query(False, description="Forza eliminazione")
) -> Dict[str, Any]:
    """
    Elimina un singolo assegno con validazione.
    
    **Regole:**
    - Non può eliminare assegni emessi o incassati
    - Non può eliminare assegni collegati a fatture
    """
    from app.services.business_rules import BusinessRules, EntityStatus
    from datetime import timezone
    
    db = Database.get_db()
    
    assegno = await db[COLLECTION_ASSEGNI].find_one({"id": assegno_id})
    if not assegno:
        raise HTTPException(status_code=404, detail="Assegno non trovato")
    
    validation = BusinessRules.can_delete_assegno(assegno)
    
    if not validation.is_valid:
        raise HTTPException(
            status_code=400,
            detail={"message": "Eliminazione non consentita", "errors": validation.errors}
        )
    
    # Soft-delete
    await db[COLLECTION_ASSEGNI].update_one(
        {"id": assegno_id},
        {"$set": {
            "entity_status": EntityStatus.DELETED.value,
            "deleted_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    return {"success": True, "message": "Assegno eliminato"}


@router.post("/auto-associa")
async def auto_associa_assegni() -> Dict[str, Any]:
    """
    Auto-associa assegni alle fatture con algoritmo migliorato.
    
    Logica migliorata:
    1. Match esatto per importo (tolleranza 0.5€)
    2. Match per importo + nome fornitore simile (fuzzy matching)
    3. Match multiplo (N assegni = 1 fattura)
    4. Learning: usa associazioni precedenti per suggerire
    5. Match per data (assegno emesso entro 30gg dalla fattura)
    """
    db = Database.get_db()
    from app.database import Collections
    from difflib import SequenceMatcher
    
    def similarity(a: str, b: str) -> float:
        """Calcola similarità tra due stringhe (0-1)."""
        if not a or not b:
            return 0
        a = a.lower().strip()
        b = b.lower().strip()
        return SequenceMatcher(None, a, b).ratio()
    
    def normalize_name(name: str) -> str:
        """Normalizza nome fornitore per confronto."""
        if not name:
            return ""
        name = name.lower().strip()
        # Rimuovi forme giuridiche comuni
        for suffix in [" srl", " s.r.l.", " spa", " s.p.a.", " snc", " sas", " srls"]:
            name = name.replace(suffix, "")
        return name.strip()
    
    # Carica assegni da associare
    assegni_da_associare = await db[COLLECTION_ASSEGNI].find({
        "$or": [
            {"beneficiario": None},
            {"beneficiario": ""},
            {"beneficiario": "N/A"},
            {"fattura_collegata": None}
        ],
        "importo": {"$gt": 0},
        "stato": {"$nin": ["annullato", "incassato"]}
    }, {"_id": 0}).to_list(1000)
    
    # Carica fatture non pagate — SOLO di fornitori che pagano con assegno
    # Carica metodo pagamento fornitori
    metodo_fornitori = {}
    async for f in db[Collections.SUPPLIERS].find({'metodo_pagamento': {'$exists': True}}, {'partita_iva': 1, 'metodo_pagamento': 1}):
        if f.get('partita_iva'):
            metodo_fornitori[f['partita_iva']] = (f.get('metodo_pagamento') or '').lower()
    
    fatture_raw = await db[Collections.INVOICES].find({
        "status": {"$nin": STATI_PAGATI},
        "total_amount": {"$gt": 0}
    }, {"_id": 0}).to_list(5000)
    
    # Filtra: solo fatture di fornitori esplicitamente pagabili con assegno
    # (metodo 'assegno', legacy, o 'misto'). Un metodo NON impostato veniva
    # trattato come "compatibile" per difetto — così qualsiasi fornitore mai
    # configurato (es. Amazon, pagato con carta/bonifico ma senza un metodo
    # esplicito a sistema) finiva tra i candidati assegno solo per
    # coincidenza di importo, cosa che non ha alcun senso pratico (nessuno
    # paga Amazon con un assegno italiano).
    fatture = []
    for f in fatture_raw:
        piva = f.get('supplier_vat', '')
        metodo = metodo_fornitori.get(piva, '')
        if metodo in ['assegno', 'misto']:
            fatture.append(f)
    
    # Carica associazioni storiche per learning
    associazioni_storiche = await db[COLLECTION_ASSEGNI].find({
        "fattura_collegata": {"$ne": None},
        "beneficiario": {"$nin": [None, "", "N/A"]}
    }, {"_id": 0, "importo": 1, "beneficiario": 1, "fattura_collegata": 1}).to_list(5000)
    
    # Crea indice per learning: importo -> fornitori associati
    learning_map = {}
    for ass in associazioni_storiche:
        imp = round(ass.get("importo", 0), 2)
        ben = normalize_name(ass.get("beneficiario", ""))
        if imp > 0 and ben:
            if imp not in learning_map:
                learning_map[imp] = set()
            learning_map[imp].add(ben)
    
    logger.info(f"Auto-associazione: {len(assegni_da_associare)} assegni, {len(fatture)} fatture, {len(learning_map)} pattern appresi")
    
    associazioni = []
    assegni_associati = set()
    fatture_usate = set()
    
    # === FASE 1: Match esatto per importo ===
    for fattura in fatture:
        if fattura.get("id") in fatture_usate:
            continue
        importo_fattura = round(fattura.get("total_amount", 0), 2)
        fornitore_fattura = normalize_name(fattura.get("supplier_name", ""))

        # Tutti gli assegni ancora liberi compatibili per importo (tolleranza
        # 0.5€): prima si prendeva sempre il primo trovato con confidenza
        # 1.0 "finta", anche quando più assegni erano ugualmente compatibili
        # — un caso ambiguo veniva applicato come fosse certo.
        candidati_assegno = [
            a for a in assegni_da_associare
            if a["id"] not in assegni_associati
            and abs(importo_fattura - round(a.get("importo", 0), 2)) < 0.5
        ]
        if not candidati_assegno:
            continue

        assegno = candidati_assegno[0]
        ambiguo = len(candidati_assegno) > 1
        associazioni.append({
            "tipo": "esatto" if not ambiguo else "esatto_ambiguo",
            # Ambiguo → confidenza sotto MIN_CONFIDENCE_AUTO: diventa proposta
            # manuale invece di essere applicato automaticamente come certo.
            "confidenza": 1.0 if not ambiguo else 0.5,
            "assegno_id": assegno["id"],
            "assegno_numero": assegno.get("numero"),
            "fattura_id": fattura.get("id"),
            "fattura_numero": fattura.get("invoice_number"),
            "fornitore": fattura.get("supplier_name"),
            "importo": importo_fattura,
            **({"nota": f"Ambiguo: {len(candidati_assegno)} assegni con importo compatibile "
                         f"({', '.join(a.get('numero', '') for a in candidati_assegno[:5])})"}
               if ambiguo else {}),
        })
        assegni_associati.add(assegno["id"])
        fatture_usate.add(fattura.get("id"))
    
    # === FASE 2: Match con learning (stesso importo + fornitore conosciuto) ===
    for fattura in fatture:
        if fattura.get("id") in fatture_usate:
            continue
        importo_fattura = round(fattura.get("total_amount", 0), 2)
        fornitore_fattura = normalize_name(fattura.get("supplier_name", ""))
        
        # Cerca se questo fornitore è già stato associato a questo importo
        if importo_fattura in learning_map:
            fornitori_noti = learning_map[importo_fattura]
            for fornitore_noto in fornitori_noti:
                if similarity(fornitore_fattura, fornitore_noto) > 0.7:
                    # Cerca assegno con importo simile
                    for assegno in assegni_da_associare:
                        if assegno["id"] in assegni_associati:
                            continue
                        importo_assegno = round(assegno.get("importo", 0), 2)
                        
                        if abs(importo_fattura - importo_assegno) < 1.0:  # Tolleranza 1€
                            associazioni.append({
                                "tipo": "learning",
                                "confidenza": 0.85,
                                "assegno_id": assegno["id"],
                                "assegno_numero": assegno.get("numero"),
                                "fattura_id": fattura.get("id"),
                                "fattura_numero": fattura.get("invoice_number"),
                                "fornitore": fattura.get("supplier_name"),
                                "importo": importo_fattura,
                                "nota": f"Associato via learning (fornitore simile a {fornitore_noto})"
                            })
                            assegni_associati.add(assegno["id"])
                            fatture_usate.add(fattura.get("id"))
                            break
                    break
    
    # === FASE 3: Match multipli (N assegni = 1 fattura grande) ===
    from collections import Counter
    importi_assegni = Counter()
    for a in assegni_da_associare:
        if a["id"] not in assegni_associati:
            imp = round(a.get("importo", 0), 2)
            if imp > 0:
                importi_assegni[imp] += 1
    
    for importo_assegno, count in importi_assegni.items():
        if count <= 1:
            continue
        
        # Cerca fatture che potrebbero corrispondere a N assegni
        for n in range(count, 1, -1):  # Prova da count a 2
            importo_target = round(importo_assegno * n, 2)
            
            for fattura in fatture:
                if fattura.get("id") in fatture_usate:
                    continue
                importo_fattura = round(fattura.get("total_amount", 0), 2)
                
                tolleranza = max(2, importo_target * 0.005)  # 0.5% o minimo 2€
                
                if abs(importo_fattura - importo_target) <= tolleranza:
                    # Trova N assegni con questo importo
                    assegni_match = [a for a in assegni_da_associare 
                                   if abs(round(a.get("importo", 0), 2) - importo_assegno) < 0.5
                                   and a["id"] not in assegni_associati]
                    
                    if len(assegni_match) >= n:
                        for assegno in assegni_match[:n]:
                            associazioni.append({
                                "tipo": "multiplo",
                                "confidenza": 0.8,
                                "assegno_id": assegno["id"],
                                "assegno_numero": assegno.get("numero"),
                                "fattura_id": fattura.get("id"),
                                "fattura_numero": fattura.get("invoice_number"),
                                "fornitore": fattura.get("supplier_name"),
                                "importo": importo_assegno,
                                "nota": f"Fattura €{importo_fattura:.2f} = {n} assegni da €{importo_assegno:.2f}"
                            })
                            assegni_associati.add(assegno["id"])
                        fatture_usate.add(fattura.get("id"))
                        break
    
    # === FASE 4: Match fuzzy per nome (bassa confidenza) ===
    for fattura in fatture:
        if fattura.get("id") in fatture_usate:
            continue
        importo_fattura = round(fattura.get("total_amount", 0), 2)
        fornitore_fattura = normalize_name(fattura.get("supplier_name", ""))
        
        if not fornitore_fattura or len(fornitore_fattura) < 3:
            continue
        
        for assegno in assegni_da_associare:
            if assegno["id"] in assegni_associati:
                continue
            importo_assegno = round(assegno.get("importo", 0), 2)
            causale = normalize_name(assegno.get("causale", "") or assegno.get("note", ""))
            
            # Match importo (tolleranza 2%) E nome simile in causale
            if abs(importo_fattura - importo_assegno) < importo_fattura * 0.02:
                if causale and similarity(fornitore_fattura, causale) > 0.6:
                    associazioni.append({
                        "tipo": "fuzzy",
                        "confidenza": 0.6,
                        "assegno_id": assegno["id"],
                        "assegno_numero": assegno.get("numero"),
                        "fattura_id": fattura.get("id"),
                        "fattura_numero": fattura.get("invoice_number"),
                        "fornitore": fattura.get("supplier_name"),
                        "importo": importo_fattura,
                        "nota": f"Match fuzzy nome (similarity: {similarity(fornitore_fattura, causale):.0%})"
                    })
                    assegni_associati.add(assegno["id"])
                    fatture_usate.add(fattura.get("id"))
                    break
    
    # Nessun collegamento viene applicato dal vecchio motore statistico: non
    # dispone del numero fattura dichiarato sul pagamento. I risultati sono
    # soltanto proposte e la conferma viene rivalidata qui sotto.
    MIN_CONFIDENCE_AUTO = 1.01
    associazioni_auto = []
    proposte_manuali = associazioni
    
    updated = 0
    for assoc in associazioni_auto:
        try:
            nota = assoc.get("nota", f"Pagamento fattura {assoc['fattura_numero']}")

            # Non si inventa mai un beneficiario a partire dal numero fattura:
            # un assegno resta "da associare" finché non ha un beneficiario
            # reale (dallo scan/OCR o inserito a mano). Il collegamento alla
            # fattura viene comunque salvato, ma non finge una compilazione
            # completa che non c'è.
            assegno_corrente = await db[COLLECTION_ASSEGNI].find_one(
                {"id": assoc["assegno_id"]}, {"_id": 0, "beneficiario": 1}
            )
            ha_beneficiario_reale = bool(
                assegno_corrente and (assegno_corrente.get("beneficiario") or "") not in ("", "-", "N/A")
            )

            set_fields = {
                "numero_fattura": assoc["fattura_numero"],
                "fattura_collegata": assoc["fattura_id"],
                "note": nota,
                "match_type": assoc["tipo"],
                "match_confidenza": assoc["confidenza"],
                "associazione_auto": True,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            if ha_beneficiario_reale:
                set_fields["stato"] = "compilato"

            result = await db[COLLECTION_ASSEGNI].update_one(
                {"id": assoc["assegno_id"]},
                {"$set": set_fields}
            )
            if result.modified_count > 0:
                updated += 1
        except Exception as e:
            logger.error(f"Errore associazione assegno {assoc['assegno_numero']}: {e}")
    
    # === SALVA PROPOSTE MANUALI (confidence < 80%) ===
    proposte_salvate = 0
    for proposta in proposte_manuali:
        try:
            proposta_doc = {
                "id": f"prop-{proposta['assegno_id']}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
                "assegno_id": proposta["assegno_id"],
                "assegno_numero": proposta.get("assegno_numero"),
                "fattura_id": proposta["fattura_id"],
                "fattura_numero": proposta.get("fattura_numero"),
                "fornitore": proposta.get("fornitore"),
                "importo": proposta.get("importo"),
                "tipo_match": proposta["tipo"],
                "confidenza": proposta["confidenza"],
                "nota": proposta.get("nota"),
                "stato": "da_confermare",
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await db["proposte_associazione_assegni"].update_one(
                {"assegno_id": proposta["assegno_id"], "fattura_id": proposta["fattura_id"]},
                {"$set": proposta_doc},
                upsert=True
            )
            proposte_salvate += 1
        except Exception as e:
            logger.error(f"Errore salvataggio proposta: {e}")
    
    # Raggruppa per tipo di match
    by_type = {}
    for a in associazioni:
        t = a["tipo"]
        if t not in by_type:
            by_type[t] = 0
        by_type[t] += 1
    
    return {
        "success": True,
        "message": f"Associati automaticamente {updated} assegni (confidence >= 80%), {proposte_salvate} proposte per conferma manuale",
        "associazioni_trovate": len(associazioni),
        "assegni_aggiornati_auto": updated,
        "proposte_manuali": proposte_salvate,
        "per_tipo": by_type,
        "soglia_auto": f"{MIN_CONFIDENCE_AUTO:.0%}",
        "dettagli_auto": sorted(associazioni_auto, key=lambda x: -x.get("confidenza", 0))[:30],
        "dettagli_manuali": sorted(proposte_manuali, key=lambda x: -x.get("confidenza", 0))[:20]
    }


@router.post("/conferma-proposta/{proposta_id}")
async def conferma_proposta_associazione(proposta_id: str) -> Dict[str, Any]:
    """Conferma una proposta di associazione e applica l'associazione."""
    db = Database.get_db()
    
    proposta = await db["proposte_associazione_assegni"].find_one({"id": proposta_id})
    if not proposta:
        raise HTTPException(status_code=404, detail="Proposta non trovata")
    
    # Applica l'associazione. Non si inventa il beneficiario dal numero
    # fattura: se non c'è già un beneficiario reale, l'assegno resta
    # "da associare" pur avendo la fattura collegata.
    assegno_corrente = await db[COLLECTION_ASSEGNI].find_one(
        {"id": proposta["assegno_id"]}, {"_id": 0}
    )
    fattura_corrente = await db["invoices"].find_one(
        {"id": proposta["fattura_id"]}, {"_id": 0}
    )
    if not assegno_corrente or not fattura_corrente:
        raise HTTPException(status_code=409, detail="Assegno o fattura non più disponibili")
    numero = fattura_corrente.get("invoice_number") or fattura_corrente.get("numero_fattura")
    importo_fattura = fattura_corrente.get("importo_residuo")
    if importo_fattura is None:
        importo_fattura = fattura_corrente.get("total_amount") or fattura_corrente.get("importo_totale")
    if not invoice_reference_equals(numero, proposta.get("fattura_numero")):
        raise HTTPException(status_code=409, detail="Numero fattura della proposta non più coerente")
    if not amounts_equal_to_cent(assegno_corrente.get("importo"), importo_fattura):
        raise HTTPException(status_code=409, detail="Importo assegno e fattura non coincidono al centesimo")
    beneficiario = assegno_corrente.get("beneficiario") or ""
    fornitore = fattura_corrente.get("supplier_name") or fattura_corrente.get("cedente_denominazione") or ""
    piva_assegno = _norm_piva(assegno_corrente.get("fornitore_piva"))
    piva_fattura = _norm_piva(
        fattura_corrente.get("supplier_vat") or fattura_corrente.get("cedente_piva")
        or fattura_corrente.get("partita_iva")
    )
    if not ((piva_assegno and piva_assegno == piva_fattura)
            or (beneficiario and fornitore and identita_coincide(beneficiario, fornitore))):
        raise HTTPException(status_code=409, detail="Identità del fornitore non coerente con l'assegno")
    ha_beneficiario_reale = bool(
        assegno_corrente and (assegno_corrente.get("beneficiario") or "") not in ("", "-", "N/A")
    )

    set_fields = {
        "numero_fattura": proposta["fattura_numero"],
        "fattura_collegata": proposta["fattura_id"],
        "note": f"{proposta.get('nota', '')} [Confermato manualmente]",
        "match_type": proposta["tipo_match"],
        "match_confidenza": proposta["confidenza"],
        "associazione_manuale": True,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    if ha_beneficiario_reale:
        set_fields["stato"] = "compilato"

    result = await db[COLLECTION_ASSEGNI].update_one(
        {"id": proposta["assegno_id"]},
        {"$set": set_fields}
    )
    
    # Aggiorna stato proposta
    await db["proposte_associazione_assegni"].update_one(
        {"id": proposta_id},
        {"$set": {"stato": "confermata", "confirmed_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    return {
        "success": True,
        "message": f"Associazione confermata per assegno {proposta.get('assegno_numero')}"
    }


@router.post("/pulisci-beneficiari-fittizi")
async def pulisci_beneficiari_fittizi() -> Dict[str, Any]:
    """
    Una tantum: gli assegni auto-associati in passato avevano un
    beneficiario sintetico "Pag. fatt. X - Y" costruito dal numero
    fattura invece di un vero nome beneficiario. Li riporta allo stato
    reale (da associare) senza perdere il collegamento alla fattura.
    """
    db = Database.get_db()

    candidati = await db[COLLECTION_ASSEGNI].find(
        {"beneficiario": {"$regex": "^Pag\\. fatt\\. "}}, {"_id": 0}
    ).to_list(10000)

    corretti = 0
    for a in candidati:
        result = await db[COLLECTION_ASSEGNI].update_one(
            {"id": a["id"]},
            {"$set": {
                "beneficiario": "",
                "stato": "vuoto",
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        if result.modified_count > 0:
            corretti += 1

    return {
        "success": True,
        "message": f"Corretti {corretti} assegni con beneficiario fittizio (fattura collegata mantenuta)",
        "assegni_corretti": corretti
    }


@router.post("/rifiuta-proposta/{proposta_id}")
async def rifiuta_proposta_associazione(proposta_id: str) -> Dict[str, Any]:
    """Rifiuta una proposta di associazione."""
    db = Database.get_db()
    
    result = await db["proposte_associazione_assegni"].update_one(
        {"id": proposta_id},
        {"$set": {"stato": "rifiutata", "rejected_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Proposta non trovata")
    
    return {"success": True, "message": "Proposta rifiutata"}



@router.post("/sync-da-estratto-conto")
async def sync_assegni_da_estratto_conto(
    movimento_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Sincronizza gli assegni dall'estratto conto.
    
    Cerca movimenti con pattern "ASSEGNO" nella descrizione e li importa
    come assegni nella collection dedicata.
    
    Pattern riconosciuti:
    - VOSTRO ASSEGNO N. XXXXXXXXXX
    - PRELIEVO ASSEGNO N. XXXXXXXXXX
    - PAGAMENTO ASSEGNO
    - VS. ASSEGNO
    """
    # La logica canonica vive nel service condiviso: la stessa funzione viene
    # usata da upload manuale, Documenti/Import e ingest automatico Drive.
    # Il vecchio codice qui sotto resta temporaneamente come riferimento di
    # migrazione ma non viene piu eseguito.
    from app.services.assegni_estratto_conto import sincronizza_assegni_da_estratto_conto
    from app.services.assegni_fattura_intent import riprocessa_intenti_assegni

    db = Database.get_db()
    risultato = await sincronizza_assegni_da_estratto_conto(
        db, movimento_ids=movimento_ids,
    )
    # L'EC puo' arrivare prima o dopo l'XML. Subito dopo il riscontro bancario
    # riesaminiamo gli assegni compilati ancora aperti: se numero/fornitore e
    # importo al centesimo identificano una sola fattura, completiamo l'intera
    # catena senza chiedere all'utente di selezionarla.
    risultato["riprocessamento_fatture"] = await riprocessa_intenti_assegni(db)
    return risultato


    import re
    db = Database.get_db()
    
    risultati = {
        "movimenti_analizzati": 0,
        "assegni_trovati": 0,
        "assegni_creati": 0,
        "assegni_esistenti": 0,
        "errori": [],
        "dettagli": []
    }
    
    # Pattern per estrarre numero assegno - AGGIORNATO per formato banca
    # Formato tipico: "PRELIEVO ASSEGNO - DM 06230 CRA: 42601623084409 NUM: 0208767182"
    # Il numero vero è quello dopo "NUM:", non dopo "CRA:"
    patterns_assegno = [
        r"NUM[:\s]+(\d{10,})",  # Prima cerca NUM: che è il numero reale
        r"ASSEGNO\s*N\.?\s*(\d{10,})",
        r"ASSEGNO\s+(\d{10,})",
        r"VS\.?\s*ASSEGNO\s*N?\.?\s*(\d{10,})",
        r"VOSTRO\s+ASSEGNO\s*N\.?\s*(\d{10,})",
        r"PRELIEVO\s+ASSEGNO\s*N?\.?\s*(\d{10,})",
    ]
    
    # Cerca movimenti con pattern specifici di pagamento assegno
    movimenti = await db.estratto_conto_movimenti.find({
        "$and": [
            {"$or": [
                {"descrizione": {"$regex": "PRELIEVO.*ASSEGNO", "$options": "i"}},
                {"descrizione": {"$regex": "VOSTRO.*ASSEGNO", "$options": "i"}},
                {"descrizione": {"$regex": "VS\\..*ASSEGNO", "$options": "i"}},
                {"descrizione": {"$regex": "PAGAMENTO.*ASSEGNO", "$options": "i"}},
                {"descrizione_originale": {"$regex": "PRELIEVO.*ASSEGNO", "$options": "i"}},
                {"descrizione_originale": {"$regex": "VOSTRO.*ASSEGNO", "$options": "i"}}
            ]},
            {"importo": {"$lt": 0}},  # Solo uscite
            {"descrizione": {"$not": {"$regex": "RILASCIO.*CARNET", "$options": "i"}}}  # Escludi rilascio carnet
        ]
    }, {"_id": 0}).to_list(1000)
    
    risultati["movimenti_analizzati"] = len(movimenti)
    
    for mov in movimenti:
        descrizione = mov.get("descrizione") or mov.get("descrizione_originale") or ""
        
        # Salta se è solo "RILASCIO CARNET ASSEGNI"
        if "RILASCIO CARNET" in descrizione.upper():
            continue
        
        # Estrai numero assegno
        numero_assegno = None
        for pattern in patterns_assegno:
            match = re.search(pattern, descrizione, re.IGNORECASE)
            if match:
                numero_assegno = match.group(1)
                break
        
        if not numero_assegno:
            # Se non trova numero, usa un ID univoco basato sul movimento
            numero_assegno = f"AUTO-{mov.get('id', '')[:8]}"
        
        risultati["assegni_trovati"] += 1
        
        # Verifica se esiste già
        esistente = await db[COLLECTION_ASSEGNI].find_one({
            "$or": [
                {"numero": numero_assegno},
                {"movimento_id": mov.get("id")}
            ]
        })
        
        if esistente:
            risultati["assegni_esistenti"] += 1
            continue
        
        # C3: Prima cerca nel carnet se già compilato/emesso
        assegno_carnet = await db[COLLECTION_ASSEGNI].find_one({
            "$or": [
                {"numero": {"$regex": numero_assegno[-8:] if len(numero_assegno) >= 8 else numero_assegno, "$options": "i"}},
                {"numero": numero_assegno}
            ],
            "stato": {"$in": ["compilato", "emesso"]}
        })
        if assegno_carnet:
            data = mov.get("data") or mov.get("data_pagamento")
            await db[COLLECTION_ASSEGNI].update_one(
                {"id": assegno_carnet["id"]},
                {"$set": {"stato": "incassato", "data_incasso": data,
                          "movimento_estratto_conto_id": mov.get("id"),
                          "incassato_confermato_banca": True,
                          "updated_at": datetime.now(timezone.utc).isoformat()}}
            )
            if assegno_carnet.get("fattura_collegata"):
                fid = assegno_carnet["fattura_collegata"]
                await db["invoices"].update_one({"id": fid},
                    {"$set": {"data_ultimo_incasso_assegno": data,
                              "metodo_pagamento_effettivo": "assegno"}})
                # --- EVENT BUS: propaga FATTURA_PAGATA (sync assegno da EC) ---
                try:
                    from app.services.event_bus import propagate_event, EventTypes
                    await propagate_event(EventTypes.FATTURA_PAGATA, {
                        "fattura_id": fid,
                        "metodo_pagamento": "assegno",
                        "data_pagamento": data,
                        "importo": assegno_carnet.get("importo"),
                        "assegno_id": assegno_carnet["id"],
                        "assegno_numero": assegno_carnet.get("numero"),
                        "movimento_id": mov.get("id"),
                    }, db, source_module="assegni_sync_ec")
                except Exception:
                    logger.exception("Errore propagazione fattura.pagata (sync assegno EC)")
            if assegno_carnet.get("prima_nota_banca_id"):
                await db["prima_nota_banca"].update_one(
                    {"id": assegno_carnet["prima_nota_banca_id"]},
                    {"$set": {"riconciliato": True, "data_riconciliazione": data,
                              "movimento_estratto_conto_id": mov.get("id")}})
            risultati["assegni_riconciliati"] = risultati.get("assegni_riconciliati", 0) + 1
            continue
        
        # Crea assegno
        importo = abs(float(mov.get("importo", 0)))
        data = mov.get("data") or mov.get("data_pagamento")
        
        assegno = {
            "id": str(uuid.uuid4()),
            "numero": numero_assegno,
            "importo": importo,
            "data": data,
            "data_emissione": data,
            "stato": "emesso",
            "beneficiario": mov.get("fornitore") or mov.get("ragione_sociale") or "",
            "descrizione": descrizione,
            "movimento_id": mov.get("id"),
            "fonte": "estratto_conto",
            "banca": mov.get("banca"),
            "confermato": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        try:
            await db[COLLECTION_ASSEGNI].insert_one(assegno)
            risultati["assegni_creati"] += 1
            risultati["dettagli"].append({
                "numero": numero_assegno,
                "importo": importo,
                "data": data,
                "descrizione": descrizione[:50]
            })
        except Exception as e:
            risultati["errori"].append(f"Errore creazione assegno {numero_assegno}: {str(e)}")
    
    return risultati


@router.post("/riprocessa-collegamenti")
async def riprocessa_collegamenti_assegni(
    anno: Optional[int] = Query(None),
    limit: int = Query(10000, ge=1, le=50000),
) -> Dict[str, Any]:
    """Riprocessa in modo sicuro lo storico assegni -> EC -> fatture.

    Non espone una scelta manuale: applica soltanto collegamenti univoci e
    lascia gli ambigui in attesa di nuove evidenze (XML, beneficiario o numero
    fattura). E' idempotente e puo' essere richiamato dopo ogni nuovo import.
    """
    from app.services.assegni_estratto_conto import sincronizza_assegni_da_estratto_conto
    from app.services.assegni_fattura_intent import riprocessa_intenti_assegni

    db = Database.get_db()
    estratto = await sincronizza_assegni_da_estratto_conto(db)
    fatture = await riprocessa_intenti_assegni(db, anno=anno, limit=limit)
    return {
        "success": bool(fatture.get("success", True)) and not estratto.get("errori"),
        "estratto_conto": estratto,
        "fatture": fatture,
        "message": (
            f"Riprocessati {fatture['analizzati']} assegni: "
            f"{fatture['collegati']} collegati automaticamente, "
            f"{fatture['ambigui']} ambigui lasciati in attesa"
        ),
    }


@router.post("/ricostruisci-dati")
async def ricostruisci_dati_assegni(
    dry_run: bool = Query(True, description="Sola anteprima; nessuna modifica ai dati"),
) -> Dict[str, Any]:
    """
    Anteprima prudenziale dei dati recuperabili per gli assegni incompleti.

    Non applica mai associazioni: beneficiario e fattura devono essere confermati
    con gli endpoint espliciti di auto-match/conferma. In particolare, l'importo
    da solo non costituisce prova sufficiente per collegare una fattura.
    """
    import re
    if not dry_run:
        raise HTTPException(
            status_code=400,
            detail="Ricostruzione diretta disabilitata: usa auto-match e conferma una proposta esplicita",
        )
    db = Database.get_db()
    
    risultati = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "assegni_processati": 0,
        "beneficiari_trovati": 0,
        "fatture_associate": 0,
        "errori": [],
        "dry_run": True,
        "nessuna_modifica_applicata": True,
    }
    
    # 1. Carica assegni con dati mancanti
    assegni = await db[COLLECTION_ASSEGNI].find({
        "$or": [
            {"beneficiario": {"$in": [None, "", "-"]}},
            {"numero_fattura": {"$exists": False}},
            {"numero_fattura": None}
        ]
    }, {"_id": 0}).to_list(10000)
    
    if not assegni:
        return {"message": "Tutti gli assegni hanno già i dati completi", **risultati}
    
    risultati["assegni_processati"] = len(assegni)
    
    # 2. Carica dati di supporto
    fatture = await db.invoices.find({}, {
        "_id": 0, "id": 1, "invoice_number": 1, "numero_documento": 1,
        "supplier_name": 1, "fornitore_ragione_sociale": 1,
        "supplier_vat": 1, "fornitore_partita_iva": 1,
        "total_amount": 1, "importo_totale": 1, "pagato": 1
    }).to_list(10000)
    
    fornitori = await db["fornitori"].find({}, {
        "_id": 0, "denominazione": 1, "ragione_sociale": 1, "partita_iva": 1
    }).to_list(10000)
    
    movimenti = await db.estratto_conto_movimenti.find({}, {
        "_id": 0, "id": 1, "descrizione": 1, "descrizione_originale": 1,
        "beneficiario": 1, "controparte": 1
    }).to_list(10000)
    
    def normalizza_importo_match(valore: Any) -> float:
        try:
            return round(float(valore or 0), 2)
        except (TypeError, ValueError):
            return 0.0

    # 3. Crea indici
    # Indice fatture per importo
    fatture_per_importo = {}
    for f in fatture:
        imp = normalizza_importo_match(f.get("total_amount") or f.get("importo_totale"))
        if imp > 0:
            if imp not in fatture_per_importo:
                fatture_per_importo[imp] = []
            fatture_per_importo[imp].append(f)
    
    # Indice fornitori per nome
    fornitori_nomi = {(f.get("denominazione") or f.get("ragione_sociale") or "").upper()[:20]: f for f in fornitori if f.get("denominazione") or f.get("ragione_sociale")}
    
    # Indice movimenti per id
    movimenti_idx = {m.get("id"): m for m in movimenti}

    def normalizza_nome_match(valore: Any) -> str:
        return re.sub(r"[^A-Z0-9]", "", str(valore or "").upper())
    
    # 4. Pattern per estrarre beneficiario
    def estrai_beneficiario(testo):
        if not testo:
            return None
        testo = testo.upper()
        
        # Pattern comuni nei movimenti bancari italiani
        patterns = [
            r"BEN[:\s]+([A-Z][A-Z0-9\s\.\&\'-]+?)(?:\s+(?:CRO|TRN|DATA|IBAN|$))",
            r"VERS[OA]?\s+([A-Z][A-Z0-9\s\.\&\'-]+?)(?:\s+(?:CRO|DATA|$))",
            r"BONIFICO\s+(?:A\s+)?([A-Z][A-Z0-9\s\.\&\'-]+?)(?:\s+(?:CRO|DATA|$))",
            r"PAGAMENTO\s+([A-Z][A-Z0-9\s\.\&\'-]+?)(?:\s+(?:FATT|N\.|$))",
        ]
        
        for p in patterns:
            match = re.search(p, testo)
            if match:
                nome = match.group(1).strip()
                if len(nome) > 3:
                    return nome
        
        # Cerca nomi fornitori noti
        for nome_forn in fornitori_nomi.keys():
            if nome_forn and len(nome_forn) > 5 and nome_forn in testo:
                return fornitori_nomi[nome_forn].get("denominazione") or fornitori_nomi[nome_forn].get("ragione_sociale")
        
        return None
    
    # 5. Processa ogni assegno
    for ass in assegni:
        ass_id = ass.get("id")
        importo = normalizza_importo_match(ass.get("importo"))
        descrizione = ass.get("descrizione", "")
        beneficiario = ass.get("beneficiario")
        mov_id = ass.get("movimento_estratto_conto_id") or ass.get("movimento_id")
        
        aggiornamenti = {}
        
        # a) Trova beneficiario se mancante
        if not beneficiario or beneficiario in ["", "-", None]:
            # Prima prova dalla descrizione assegno
            ben = estrai_beneficiario(descrizione)
            
            # Se non trovato, cerca nel movimento originale
            if not ben and mov_id and mov_id in movimenti_idx:
                mov = movimenti_idx[mov_id]
                ben = mov.get("beneficiario") or mov.get("controparte") or estrai_beneficiario(mov.get("descrizione") or mov.get("descrizione_originale"))
            
            if ben:
                aggiornamenti["beneficiario"] = ben
                risultati["beneficiari_trovati"] += 1
        
        # b) Trova fattura se mancante
        beneficiario_effettivo = beneficiario or aggiornamenti.get("beneficiario")
        if not ass.get("numero_fattura") and importo > 0 and beneficiario_effettivo:
            if importo in fatture_per_importo:
                candidates = fatture_per_importo[importo]
                ben_search = normalizza_nome_match(beneficiario_effettivo)
                candidates_nome = [
                    fatt for fatt in candidates
                    if ben_search and (
                        ben_search in normalizza_nome_match(
                            fatt.get("supplier_name") or fatt.get("fornitore_ragione_sociale") or ""
                        )
                        or normalizza_nome_match(
                            fatt.get("supplier_name") or fatt.get("fornitore_ragione_sociale") or ""
                        ) in ben_search
                    )
                ]

                # L'importo conta soltanto insieme a un beneficiario coerente e
                # a una singola fattura candidata.
                if len(candidates_nome) == 1:
                    fatt = candidates_nome[0]
                    aggiornamenti["fattura_id"] = fatt.get("id")
                    aggiornamenti["numero_fattura"] = fatt.get("invoice_number") or fatt.get("numero_documento")
                    aggiornamenti["fornitore_fattura"] = fatt.get("supplier_name") or fatt.get("fornitore_ragione_sociale")
                    risultati["fatture_associate"] += 1

        # Nessun update: gli aggiornamenti restano una simulazione in memoria.
    
    return risultati



@router.post("/correggi-numeri")
async def correggi_numeri_assegni() -> Dict[str, Any]:
    """
    Corregge i numeri degli assegni estratti erroneamente (CRA invece di NUM).
    
    Il formato bancario è: "PRELIEVO ASSEGNO - DM 06230 CRA: 42601623084409 NUM: 0208767182"
    Il numero corretto è quello dopo "NUM:", non quello dopo "CRA:".
    """
    import re
    db = Database.get_db()
    
    risultati = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "assegni_analizzati": 0,
        "numeri_corretti": 0,
        "errori": []
    }
    
    # Trova assegni con numeri lunghi (probabilmente CRA)
    assegni = await db[COLLECTION_ASSEGNI].find({
        "numero": {"$regex": r"^\d{14,}$"}  # Numeri con 14+ cifre sono probabilmente CRA
    }, {"_id": 0}).to_list(10000)
    
    risultati["assegni_analizzati"] = len(assegni)
    
    for ass in assegni:
        descrizione = ass.get("descrizione", "")
        numero_attuale = ass.get("numero", "")
        
        # Cerca il numero reale dopo "NUM:"
        match = re.search(r"NUM[:\s]+(\d{10,})", descrizione, re.IGNORECASE)
        if match:
            numero_corretto = match.group(1)
            
            if numero_corretto != numero_attuale:
                try:
                    # Salva il vecchio numero come riferimento
                    await db[COLLECTION_ASSEGNI].update_one(
                        {"id": ass["id"]},
                        {"$set": {
                            "numero": numero_corretto,
                            "numero_cra": numero_attuale,  # Salva CRA per riferimento
                            "numero_corretto_automaticamente": True,
                            "updated_at": datetime.now(timezone.utc).isoformat()
                        }}
                    )
                    risultati["numeri_corretti"] += 1
                except Exception as e:
                    risultati["errori"].append(f"Errore update {ass['id']}: {str(e)}")
    
    return risultati



@router.post("/associa-beneficiari-robusto")
async def associa_beneficiari_robusto() -> Dict[str, Any]:
    """
    LOGICA ROBUSTA: Cerca e associa beneficiari agli assegni senza beneficiario.
    
    ALGORITMO:
    1. Per ogni assegno senza beneficiario
    2. Cerca fatture con importo simile (±10€) nella finestra temporale (±30 giorni)
    3. Se trovato match unico, associa
    4. Se trovati più match, cerca di distinguere per fornitore già pagato con altri assegni
    5. Gestisce pagamenti multipli (una fattura pagata con più assegni)
    """
    db = Database.get_db()
    from app.routers.bank.assegni_auto_match import run_auto_match
    return {
        "success": True,
        "sola_lettura": True,
        "message": (
            "Il vecchio abbinamento per importo/data è disattivato. "
            "Sono restituite soltanto proposte con numero fattura esplicito."
        ),
        "anteprima": await run_auto_match(db, dry_run=True),
    }
    
    risultati = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "assegni_analizzati": 0,
        "beneficiari_trovati": 0,
        "fatture_associate": 0,
        "pagamenti_multipli": 0,
        "non_trovati": [],
        "errori": []
    }
    
    # 1. Trova assegni senza beneficiario
    assegni_senza_ben = await db[COLLECTION_ASSEGNI].find({
        "$or": [
            {"beneficiario": None},
            {"beneficiario": ""},
            {"beneficiario": {"$exists": False}}
        ]
    }, {"_id": 0}).to_list(10000)
    
    risultati["assegni_analizzati"] = len(assegni_senza_ben)
    
    # 2. Carica tutte le fatture (collection 'invoices' - fatture ricevute da fornitori)
    fatture = await db.invoices.find({
        "total_amount": {"$gt": 0}
    }, {"_id": 0}).to_list(50000)
    if len(fatture) >= 50000:
        logger.warning("associa_fatture_per_importo_assegni: raggiunto il tetto di 50000 documenti, possibile troncamento")

    # Indice fatture per importo approssimativo (arrotondato)
    fatture_by_importo = {}
    for f in fatture:
        importo = round(float(f.get("total_amount") or f.get("importo_totale") or 0), 0)
        if importo > 0:
            if importo not in fatture_by_importo:
                fatture_by_importo[importo] = []
            fatture_by_importo[importo].append(f)
    
    # 3. Carica fornitori per nome
    fornitori = await db["fornitori"].find({}, {"_id": 0}).to_list(10000)
    fornitori_idx = {}
    for f in fornitori:
        nome = (f.get("ragione_sociale") or f.get("denominazione") or "").upper()
        if nome:
            fornitori_idx[nome] = f
    
    for ass in assegni_senza_ben:
        importo_ass = abs(float(ass.get("importo") or 0))
        data_ass_str = ass.get("data") or ""
        numero_ass = ass.get("numero", "")
        
        if importo_ass == 0:
            continue
        
        # Cerca fatture con importo simile (±10€)
        candidati = []
        for delta in range(-10, 11):
            importo_cerca = round(importo_ass + delta, 0)
            if importo_cerca in fatture_by_importo:
                candidati.extend(fatture_by_importo[importo_cerca])
        
        # Filtra per data (±60 giorni dall'assegno)
        try:
            if data_ass_str:
                data_ass = datetime.fromisoformat(data_ass_str.replace('Z', '+00:00'))
            else:
                data_ass = None
        except Exception:
            data_ass = None
        
        match_trovato = None
        
        if len(candidati) == 1:
            # Match unico!
            match_trovato = candidati[0]
        elif len(candidati) > 1 and data_ass:
            # Più candidati - cerca quello più vicino per data
            candidati_ordinati = []
            for c in candidati:
                data_fatt_str = c.get("invoice_date") or c.get("data_fattura") or ""
                try:
                    data_fatt = datetime.fromisoformat(data_fatt_str.replace('Z', '+00:00'))
                    diff_giorni = abs((data_ass - data_fatt).days)
                    if diff_giorni <= 90:  # Max 90 giorni di differenza
                        candidati_ordinati.append((c, diff_giorni))
                except Exception:
                    pass
            
            if candidati_ordinati:
                candidati_ordinati.sort(key=lambda x: x[1])
                match_trovato = candidati_ordinati[0][0]
        
        if match_trovato:
            fornitore = match_trovato.get("supplier_name") or match_trovato.get("fornitore") or ""
            numero_fatt = match_trovato.get("invoice_number") or match_trovato.get("numero_fattura") or ""
            
            try:
                await db[COLLECTION_ASSEGNI].update_one(
                    {"id": ass["id"]},
                    {"$set": {
                        "beneficiario": fornitore,
                        "fattura_associata": numero_fatt,
                        "fattura_id": match_trovato.get("id"),
                        "importo_fattura": match_trovato.get("total_amount"),
                        "associazione_automatica": True,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
                risultati["beneficiari_trovati"] += 1
                risultati["fatture_associate"] += 1
            except Exception as e:
                risultati["errori"].append(f"Errore update {ass['id']}: {str(e)}")
        else:
            risultati["non_trovati"].append({
                "numero": numero_ass,
                "importo": importo_ass,
                "data": data_ass_str
            })
    
    return risultati


@router.post("/associa-pagamenti-multipli")
async def associa_pagamenti_multipli() -> Dict[str, Any]:
    """
    LOGICA AVANZATA: Gestisce fatture pagate con più assegni.
    
    ALGORITMO:
    1. Raggruppa assegni per beneficiario
    2. Per ogni gruppo, cerca fatture con importo = somma assegni
    3. Se trovato, marca tutti gli assegni come parte dello stesso pagamento
    """
    db = Database.get_db()
    from app.routers.bank.assegni_auto_match import run_auto_match
    return {
        "success": True,
        "sola_lettura": True,
        "message": (
            "Il raggruppamento per solo beneficiario/importo è disattivato. "
            "La somma è valutata soltanto se i numeri fattura sono dichiarati."
        ),
        "anteprima": await run_auto_match(db, dry_run=True),
    }
    
    risultati = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "gruppi_analizzati": 0,
        "pagamenti_multipli_trovati": 0,
        "assegni_collegati": 0,
        "errori": []
    }
    
    # Raggruppa assegni per beneficiario
    pipeline = [
        {"$match": {"beneficiario": {"$exists": True, "$ne": ""}}},
        {"$group": {
            "_id": "$beneficiario",
            "assegni": {"$push": {
                "id": "$id",
                "numero": "$numero",
                "importo": "$importo",
                "data": "$data",
                "fattura_associata": "$fattura_associata"
            }},
            "totale": {"$sum": {"$abs": "$importo"}},
            "count": {"$sum": 1}
        }},
        {"$match": {"count": {"$gt": 1}}}  # Solo beneficiari con più assegni
    ]
    
    gruppi = await db[COLLECTION_ASSEGNI].aggregate(pipeline).to_list(1000)
    risultati["gruppi_analizzati"] = len(gruppi)
    
    for gruppo in gruppi:
        beneficiario = gruppo["_id"]
        totale_assegni = round(float(gruppo["totale"]), 2)
        assegni_gruppo = gruppo["assegni"]
        
        # Cerca fattura con importo uguale al totale degli assegni (±5€)
        fattura_match = await db.invoices.find_one({
            "supplier_name": {"$regex": beneficiario, "$options": "i"},
            "total_amount": {"$gte": totale_assegni - 5, "$lte": totale_assegni + 5}
        }, {"_id": 0})
        
        if fattura_match:
            numero_fatt = fattura_match.get("invoice_number") or ""
            
            # Aggiorna tutti gli assegni del gruppo
            for i, ass in enumerate(assegni_gruppo):
                try:
                    await db[COLLECTION_ASSEGNI].update_one(
                        {"id": ass["id"]},
                        {"$set": {
                            "fattura_associata": numero_fatt,
                            "fattura_id": fattura_match.get("id"),
                            "pagamento_multiplo": True,
                            "pagamento_multiplo_numero": i + 1,
                            "pagamento_multiplo_totale": len(assegni_gruppo),
                            "pagamento_multiplo_importo_fattura": fattura_match.get("total_amount"),
                            "updated_at": datetime.now(timezone.utc).isoformat()
                        }}
                    )
                    risultati["assegni_collegati"] += 1
                except Exception as e:
                    risultati["errori"].append(f"Errore {ass['id']}: {str(e)}")
            
            risultati["pagamenti_multipli_trovati"] += 1
    
    return risultati


MAX_GIORNI_TRA_ASSEGNI_COMBO = 60  # assegni della stessa combinazione non possono avere date troppo lontane tra loro
MAX_GIORNI_ASSEGNO_DOPO_FATTURA = 180  # oltre i 6 mesi la fattura non è più un candidato plausibile


def _parse_data_assegno(a: Dict[str, Any]) -> Optional[datetime]:
    raw = a.get("data_emissione") or a.get("data")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw)[:10])
    except ValueError:
        return None


@router.post("/cerca-combinazioni-assegni")
async def cerca_combinazioni_assegni(
    max_assegni: int = Query(4, ge=2, le=6, description="Numero massimo di assegni per combinazione"),
    tolleranza: float = Query(1.0, ge=0.01, le=10, description="Tolleranza in euro per il match")
) -> Dict[str, Any]:
    """
    🔍 LOGICA AVANZATA: Cerca combinazioni di assegni senza beneficiario che sommati
    corrispondono all'importo di una fattura non pagata.

    CASO D'USO:
    - 3 assegni da €1.663,26 → cerca fattura da €4.989,78 (3 × 1.663,26)
    - Assegni €855,98 + €1.028,82 → cerca fattura da €1.884,80

    ALGORITMO:
    1. Prende tutti gli assegni senza beneficiario
    2. Genera tutte le combinazioni possibili (da 2 a max_assegni elementi)
    3. Scarta le combinazioni i cui assegni hanno date troppo distanti tra loro
       (> MAX_GIORNI_TRA_ASSEGNI_COMBO): due assegni con lo stesso importo ma
       emessi a distanza di mesi non sono verosimilmente lo stesso pagamento.
    4. Per ogni combinazione, calcola la somma
    5. Cerca fatture non pagate con importo corrispondente (± tolleranza) E
       con data fattura antecedente (o di poco successiva) alla data degli
       assegni — un assegno paga una fattura già emessa, non il contrario.
       Se più fatture superano importo+data, la combinazione è ambigua e
       NON viene associata automaticamente (finisce tra i "non associabili").
    6. Se trova un match certo, associa tutti gli assegni della combinazione

    PARAMETRI:
    - max_assegni: numero massimo di assegni per combinazione (default: 4)
    - tolleranza: tolleranza in euro per il match (default: 1.0€)
    """
    from itertools import combinations
    db = Database.get_db()
    from app.routers.bank.assegni_auto_match import run_auto_match
    return {
        "success": True,
        "sola_lettura": True,
        "message": (
            "La ricerca combinatoria legacy non scrive più associazioni per coincidenza. "
            "Usare le proposte conservative numero+somma esatta+fornitore."
        ),
        "anteprima": await run_auto_match(db, dry_run=True),
    }
    
    risultati = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "assegni_analizzati": 0,
        "combinazioni_testate": 0,
        "match_trovati": 0,
        "assegni_associati": 0,
        "dettagli_match": [],
        "assegni_non_associabili": [],
        "combinazioni_ambigue": [],
        "errori": []
    }
    
    # 1. Carica assegni senza beneficiario valido
    assegni_senza_ben = await db[COLLECTION_ASSEGNI].find({
        "$or": [
            {"beneficiario": None},
            {"beneficiario": ""},
            {"beneficiario": "N/A"},
            {"beneficiario": "-"}
        ],
        "importo": {"$gt": 0}
    }, {"_id": 0}).to_list(1000)
    
    # Filtra quelli non cancellati (entity_status potrebbe non esistere)
    assegni_senza_ben = [a for a in assegni_senza_ben if a.get("entity_status") != "deleted"]
    
    risultati["assegni_analizzati"] = len(assegni_senza_ben)
    
    if len(assegni_senza_ben) < 2:
        return {
            **risultati,
            "message": "Meno di 2 assegni senza beneficiario - nessuna combinazione possibile"
        }
    
    # 2. Carica fatture non pagate
    # Escludiamo fatture RID/SDD/addebito diretto: non sono pagabili con assegno.
    fatture_non_pagate = await db.invoices.find({
        "$and": [
            {"$or": [
                {"status": {"$nin": STATI_PAGATI}},
                {"pagato": {"$ne": True}}
            ]},
            {"total_amount": {"$gt": 0}},
            {"$nor": [
                {"metodo_pagamento": {"$regex": "rid|sdd|addebito", "$options": "i"}},
                {"payment_method": {"$regex": "rid|sdd|addebito", "$options": "i"}},
                {"modalita_pagamento": {"$regex": "rid|sdd|addebito", "$options": "i"}},
            ]},
        ]
    }, {"_id": 0, "id": 1, "invoice_number": 1, "supplier_name": 1, "total_amount": 1,
        "metodo_pagamento": 1, "payment_method": 1,
        "invoice_date": 1, "data_fattura": 1}).to_list(10000)
    
    # Crea indice per importo arrotondato
    fatture_per_importo = {}
    for f in fatture_non_pagate:
        imp = round(float(f.get("total_amount", 0)), 2)
        if imp not in fatture_per_importo:
            fatture_per_importo[imp] = []
        fatture_per_importo[imp].append(f)
    
    logger.info(f"Cerca combinazioni: {len(assegni_senza_ben)} assegni, {len(fatture_non_pagate)} fatture non pagate")
    
    # 3. Prepara lista di importi con riferimento agli assegni (+ data, per i
    # controlli temporali sotto — prima ignorata del tutto)
    assegni_con_importo = [
        {"assegno": a, "importo": round(float(a.get("importo", 0)), 2), "data": _parse_data_assegno(a)}
        for a in assegni_senza_ben
        if float(a.get("importo", 0)) > 0
    ]

    def _fattura_compatibile_per_data(fattura: Dict[str, Any], data_assegni: Optional[datetime]) -> bool:
        """Un assegno paga una fattura già emessa: la fattura deve essere
        datata prima (o al più di poco dopo) della data dell'assegno, non il
        contrario. Se una delle due date manca, non blocca il match (dato
        insufficiente) ma non lo garantisce nemmeno."""
        if not data_assegni:
            return True
        data_fatt_raw = fattura.get("invoice_date") or fattura.get("data_fattura")
        if not data_fatt_raw:
            return True
        try:
            data_fatt = datetime.fromisoformat(str(data_fatt_raw)[:10])
        except ValueError:
            return True
        delta_giorni = (data_assegni - data_fatt).days
        # Ammette qualche giorno di anticipo (fattura emessa a ridosso
        # dell'assegno) ma non una fattura emessa DOPO l'assegno, e non oltre
        # ~6 mesi di distanza (oltre quella finestra il match è casuale).
        return -5 <= delta_giorni <= MAX_GIORNI_ASSEGNO_DOPO_FATTURA

    # 4. Genera e testa combinazioni (da 2 a max_assegni)
    assegni_gia_associati = set()

    for num_assegni in range(2, min(max_assegni + 1, len(assegni_con_importo) + 1)):
        for combo in combinations(enumerate(assegni_con_importo), num_assegni):
            # Salta se qualche assegno è già stato associato
            indices = [c[0] for c in combo]
            if any(idx in assegni_gia_associati for idx in indices):
                continue

            # Assegni con lo stesso importo ma emessi a distanza di mesi non
            # sono verosimilmente un unico pagamento combinato — scarta la
            # combinazione invece di abbinarli comunque (prima nessun controllo).
            date_combo = [c[1]["data"] for c in combo if c[1]["data"]]
            if len(date_combo) >= 2 and (max(date_combo) - min(date_combo)).days > MAX_GIORNI_TRA_ASSEGNI_COMBO:
                continue

            risultati["combinazioni_testate"] += 1

            assegni_combo = [c[1]["assegno"] for c in combo]
            somma = sum(c[1]["importo"] for c in combo)
            somma_round = round(somma, 2)
            data_riferimento = max(date_combo) if date_combo else None

            # Cerca fatture con questo importo (con tolleranza) E data compatibile.
            # Se più fatture superano entrambi i filtri, il match è ambiguo:
            # meglio lasciarlo da associare a mano che sceglierne una a caso
            # (comportamento precedente: prendeva sempre la prima trovata).
            candidati = []
            for delta in [0, -0.01, 0.01, -0.02, 0.02, -0.5, 0.5, -1, 1]:
                importo_cerca = round(somma_round + delta, 2)
                for f in fatture_per_importo.get(importo_cerca, []):
                    if _fattura_compatibile_per_data(f, data_riferimento):
                        candidati.append(f)
                if candidati:
                    break

            # Se non trovato con lookup diretto, cerca con range
            if not candidati:
                for f in fatture_non_pagate:
                    imp_fatt = round(float(f.get("total_amount", 0)), 2)
                    if abs(imp_fatt - somma_round) <= tolleranza and _fattura_compatibile_per_data(f, data_riferimento):
                        candidati.append(f)

            fattura_match = candidati[0] if len(candidati) == 1 else None
            if len(candidati) > 1:
                risultati["combinazioni_ambigue"].append({
                    "assegni": [a.get("numero") for a in assegni_combo],
                    "somma_assegni": somma_round,
                    "fatture_candidate": [
                        {"numero": f.get("invoice_number"), "fornitore": f.get("supplier_name"),
                         "importo": f.get("total_amount")}
                        for f in candidati[:5]
                    ],
                })

            if fattura_match:
                # MATCH TROVATO!
                risultati["match_trovati"] += 1
                
                fornitore = fattura_match.get("supplier_name", "")
                numero_fatt = fattura_match.get("invoice_number", "")
                importo_fatt = fattura_match.get("total_amount", 0)
                
                dettaglio = {
                    "tipo": "combinazione",
                    "num_assegni": num_assegni,
                    "assegni": [a.get("numero") for a in assegni_combo],
                    "importi_assegni": [round(float(a.get("importo", 0)), 2) for a in assegni_combo],
                    "somma_assegni": somma_round,
                    "fattura_id": fattura_match.get("id"),
                    "fattura_numero": numero_fatt,
                    "fattura_importo": importo_fatt,
                    "fornitore": fornitore,
                    "differenza": round(importo_fatt - somma_round, 2)
                }
                risultati["dettagli_match"].append(dettaglio)
                
                # Associa tutti gli assegni della combinazione
                for i, ass in enumerate(assegni_combo):
                    try:
                        await db[COLLECTION_ASSEGNI].update_one(
                            {"id": ass["id"]},
                            {"$set": {
                                "beneficiario": fornitore,
                                "fattura_associata": numero_fatt,
                                "fattura_id": fattura_match.get("id"),
                                "pagamento_combinato": True,
                                "combinazione_assegni": [a.get("numero") for a in assegni_combo],
                                "combinazione_numero": i + 1,
                                "combinazione_totale": num_assegni,
                                "importo_fattura_combinata": importo_fatt,
                                "updated_at": datetime.now(timezone.utc).isoformat()
                            }}
                        )
                        risultati["assegni_associati"] += 1
                        assegni_gia_associati.add(indices[i])
                    except Exception as e:
                        risultati["errori"].append(f"Errore update {ass['id']}: {str(e)}")
                
                # Rimuovi fattura dall'indice per evitare doppi match
                if somma_round in fatture_per_importo:
                    fatture_per_importo[somma_round] = [
                        f for f in fatture_per_importo[somma_round] 
                        if f.get("id") != fattura_match.get("id")
                    ]
    
    # 5. Elenco assegni rimasti non associabili
    for idx, item in enumerate(assegni_con_importo):
        if idx not in assegni_gia_associati:
            risultati["assegni_non_associabili"].append({
                "numero": item["assegno"].get("numero"),
                "importo": item["importo"]
            })
    
    return risultati

