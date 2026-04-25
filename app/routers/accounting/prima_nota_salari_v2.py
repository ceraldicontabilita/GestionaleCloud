"""Prima Nota Salari V2 — Task 5 roadmap acconti.

Vista DARE/AVERE per dipendente, mese per mese, calcolata on-the-fly da:
- cedolini (DARE: netto della busta paga)
- acconti_dipendenti (AVERE: acconti dati al dipendente, indicizzati per data)
- estratto_conto_movimenti (AVERE: bonifici stipendio non legati ad acconti)

Logica anti-duplicazione:
- Se un acconto è riconciliato_banca (ha movimento_bancario_id), il movimento
  bancario corrispondente NON viene mostrato come bonifico separato — viene
  contato solo come "Acconto" per non duplicare l'evento finanziario
- I bonifici estratto-conto verso il dipendente che NON sono già linkati ad
  alcun acconto compaiono come "Bonifico" (tipicamente stipendio mensile)

Criterio di assegnazione mese:
- Cedolini: per (mese, anno) del cedolino stesso
- Acconti: per data dell'acconto (criterio di cassa: "quando ho dato i soldi")
- Bonifici: per data del movimento bancario

NB: Lo scalato_su_anno_mese di un acconto può essere diverso dal mese di
prima nota perché un acconto del 28 aprile può essere scalato sul cedolino
di maggio. In prima nota lo vediamo ad APRILE (data), in coerenza col modello
cassa/banca.

Endpoint:
- GET /api/prima-nota-salari/dipendente/{id}?anno=YYYY     (dettaglio mensile)
- GET /api/prima-nota-salari/collettiva?anno=YYYY[&mese=]   (matrice tutti i dip)

Niente nuova collection: calcolo live, fonti già esistenti.
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import logging

from app.database import Database
from app.utils.error_handler import handle_errors

logger = logging.getLogger(__name__)
router = APIRouter()

# Collections
COLL_DIPENDENTI = "dipendenti"
COLL_CEDOLINI = "cedolini"
COLL_ACCONTI = "acconti_dipendenti"
COLL_MOVIMENTI = "estratto_conto_movimenti"

MESI_NOMI = [
    "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
    "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre",
]


# ============================================================================
# HELPERS
# ============================================================================

def _parse_data_iso(value: Any) -> Optional[datetime]:
    """Converte stringa 'YYYY-MM-DD' o datetime in datetime, None se invalida."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d")
        except (ValueError, TypeError):
            return None
    return None


def _netto_da_cedolino(cedolino: Dict[str, Any]) -> float:
    """Estrae il netto dal cedolino (vari campi possibili a seconda del flusso)."""
    for key in ("netto", "netto_mese", "netto_in_busta", "netto_da_pagare"):
        v = cedolino.get(key)
        if v is not None:
            try:
                return float(v)
            except (ValueError, TypeError):
                pass
    # Fallback: cerca dentro importi_finali se presente (parsing AI)
    importi = cedolino.get("importi_finali") or {}
    if isinstance(importi, dict):
        for key in ("netto_in_busta", "netto_da_pagare"):
            v = importi.get(key)
            if v is not None:
                try:
                    return float(v)
                except (ValueError, TypeError):
                    pass
    enhanced = cedolino.get("enhanced_parsing") or {}
    if isinstance(enhanced, dict):
        importi = enhanced.get("importi_finali") or {}
        if isinstance(importi, dict):
            for key in ("netto_in_busta", "netto_da_pagare"):
                v = importi.get(key)
                if v is not None:
                    try:
                        return float(v)
                    except (ValueError, TypeError):
                        pass
    return 0.0


def _label_acconto(a: Dict[str, Any]) -> str:
    """Genera la label leggibile per una riga acconto in prima nota."""
    tipo = (a.get("tipo") or "stipendio").capitalize()
    natura = a.get("natura_acconto") or "su_futuro"
    bonifico = a.get("tipo_bonifico") or "standard"
    suffix = ""
    if a.get("stato") == "riconciliato_banca":
        suffix = " ✓ banca"
    elif a.get("stato") == "scalato_su_cedolino":
        suffix = " ✓ scalato"
    natura_short = "pregr." if natura == "su_pregresso" else ""
    bonifico_short = "⚡" if bonifico == "istantaneo" else ""
    parts = [tipo]
    if natura_short:
        parts.append(natura_short)
    if bonifico_short:
        parts.append(bonifico_short)
    return f"Acconto {' '.join(parts).strip()}{suffix}"


async def _trova_dipendente(db, dipendente_id: str) -> Optional[Dict[str, Any]]:
    """Trova dipendente per id o codice fiscale."""
    return await db[COLL_DIPENDENTI].find_one(
        {"$or": [{"id": dipendente_id}, {"codice_fiscale": dipendente_id}]},
        {"_id": 0},
    )


async def _bonifici_dipendente_anno(
    db, nome: str, cognome: str, anno: int
) -> List[Dict[str, Any]]:
    """Cerca movimenti bancari verso il dipendente nell'anno.

    Match descrizione: pattern standard 'VOSTRA DISPOSIZIONE FAVORE COGNOME NOME'
    oppure varianti — cerco sia cognome che nome per filtro permissivo, poi
    confermo match con regex sulla parte 'FAVORE'.
    """
    if not (nome and cognome):
        return []

    cognome_upper = cognome.strip().upper()

    # Costruisco pattern per matchare il cognome dopo 'FAVORE'
    # Pattern bancario standard italiano per bonifici stipendio
    query = {
        "data_contabile_obj": {
            "$gte": datetime(anno, 1, 1),
            "$lte": datetime(anno, 12, 31, 23, 59, 59),
        },
        "$or": [
            {"tipo": "uscita"},
            {"importo": {"$lt": 0}},
        ],
        # Match permissivo: cognome appare nella descrizione
        "descrizione": {"$regex": cognome_upper, "$options": "i"},
    }

    movimenti = await db[COLL_MOVIMENTI].find(query, {"_id": 0}).to_list(2000)
    return movimenti


# ============================================================================
# ENDPOINT 1: PER DIPENDENTE (vista anno con accordion mensile)
# ============================================================================

@router.get(
    "/dipendente/{dipendente_id}",
    summary="Prima nota salari di un dipendente per un anno (accordion mensile)",
)
@handle_errors
async def prima_nota_per_dipendente(
    dipendente_id: str,
    anno: int = Query(..., ge=2020, le=2030),
) -> Dict[str, Any]:
    """Restituisce la prima nota salari del dipendente per ogni mese dell'anno.

    Per ogni mese:
    - DARE: netto del cedolino (se presente)
    - AVERE: lista di acconti (per data) + bonifici stipendio non già linkati
    - Saldo del mese (DARE - AVERE)
    - Stato: 'quadrato' se saldo == 0 (con tolleranza 0.01€), 'aperto' altrimenti
    """
    db = Database.get_db()

    dip = await _trova_dipendente(db, dipendente_id)
    if not dip:
        raise HTTPException(status_code=404, detail="Dipendente non trovato")

    real_id = dip.get("id")
    cf = dip.get("codice_fiscale", "")
    nome = dip.get("nome", "")
    cognome = dip.get("cognome", "")

    # 1) Tutti i cedolini dell'anno
    cedolini_anno = await db[COLL_CEDOLINI].find(
        {
            "$or": [
                {"dipendente_id": real_id},
                {"codice_fiscale": cf} if cf else {"_id": None},
            ],
            "anno": anno,
        },
        {"_id": 0},
    ).to_list(50)

    # 2) Tutti gli acconti del dipendente nell'anno
    # Filtro per data inizio/fine anno
    data_min_str = f"{anno}-01-01"
    data_max_str = f"{anno}-12-31"
    acconti_anno = await db[COLL_ACCONTI].find(
        {
            "$or": [
                {"dipendente_id": real_id},
                {"codice_fiscale": cf} if cf else {"_id": None},
            ],
            "data": {"$gte": data_min_str, "$lte": data_max_str},
        },
        {"_id": 0},
    ).to_list(500)

    # 3) Bonifici dal cognome del dipendente (filtro server-side parziale)
    bonifici_anno = await _bonifici_dipendente_anno(db, nome, cognome, anno)

    # Set di movimento_id già "consumati" da acconti riconciliati_banca
    movimenti_consumati = {
        a.get("movimento_bancario_id")
        for a in acconti_anno
        if a.get("movimento_bancario_id")
    }

    # Costruisci la mappa mensile
    mesi: Dict[int, Dict[str, Any]] = {
        m: {
            "mese": m,
            "mese_nome": MESI_NOMI[m - 1],
            "dare": [],
            "avere": [],
            "totale_dare": 0.0,
            "totale_avere": 0.0,
            "saldo": 0.0,
            "stato": "vuoto",
        }
        for m in range(1, 13)
    }

    # DARE: cedolini
    for c in cedolini_anno:
        mese = c.get("mese")
        if not mese or mese < 1 or mese > 12:
            continue
        netto = _netto_da_cedolino(c)
        if netto <= 0:
            continue
        mesi[mese]["dare"].append({
            "tipo": "cedolino",
            "data": f"{anno}-{str(mese).zfill(2)}-01",  # data simbolica
            "label": f"Busta paga {MESI_NOMI[mese - 1]}",
            "importo": round(netto, 2),
            "ref_id": c.get("id"),
            "ref_collection": "cedolini",
        })

    # AVERE: acconti (per data)
    for a in acconti_anno:
        data = _parse_data_iso(a.get("data"))
        if not data:
            continue
        if data.year != anno:
            continue
        mese = data.month
        importo = abs(float(a.get("importo", 0) or 0))
        if importo <= 0:
            continue
        mesi[mese]["avere"].append({
            "tipo": "acconto",
            "data": a.get("data"),
            "label": _label_acconto(a),
            "importo": round(importo, 2),
            "ref_id": a.get("id"),
            "ref_collection": "acconti_dipendenti",
            "natura_acconto": a.get("natura_acconto") or "su_futuro",
            "stato_acconto": a.get("stato") or "registrato",
            "scalato_su_anno_mese": a.get("scalato_su_anno_mese"),
            "movimento_bancario_id": a.get("movimento_bancario_id"),
        })

    # AVERE: bonifici estratto-conto NON consumati da acconti
    for m in bonifici_anno:
        mov_id = m.get("id")
        if mov_id in movimenti_consumati:
            continue  # già rappresentato come acconto

        data_obj = m.get("data_contabile_obj")
        if isinstance(data_obj, str):
            data_obj = _parse_data_iso(data_obj)
        if not data_obj:
            continue
        if data_obj.year != anno:
            continue

        # Verifica che la descrizione abbia il pattern bonifico stipendio
        descrizione = (m.get("descrizione") or "").upper()
        cognome_upper = cognome.upper()
        if cognome_upper not in descrizione:
            continue  # falso positivo del filtro permissivo

        importo = abs(float(m.get("importo", 0) or 0))
        if importo <= 0:
            continue

        mese = data_obj.month
        # Determina label: se descrizione contiene parole chiave da stipendio
        is_stipendio = any(k in descrizione for k in ("STIPENDIO", "VOSTRA DISPOSIZIONE"))
        label = "Bonifico stipendio" if is_stipendio else "Bonifico"

        mesi[mese]["avere"].append({
            "tipo": "bonifico",
            "data": data_obj.strftime("%Y-%m-%d"),
            "label": label,
            "importo": round(importo, 2),
            "ref_id": mov_id,
            "ref_collection": "estratto_conto_movimenti",
            "descrizione": (m.get("descrizione") or "")[:120],
        })

    # Calcola totali e stato per ogni mese
    for mese in range(1, 13):
        m = mesi[mese]
        # Ordina dare/avere per data
        m["dare"].sort(key=lambda x: x["data"])
        m["avere"].sort(key=lambda x: x["data"])
        # Totali
        m["totale_dare"] = round(sum(d["importo"] for d in m["dare"]), 2)
        m["totale_avere"] = round(sum(a["importo"] for a in m["avere"]), 2)
        m["saldo"] = round(m["totale_dare"] - m["totale_avere"], 2)
        # Stato
        if not m["dare"] and not m["avere"]:
            m["stato"] = "vuoto"
        elif abs(m["saldo"]) < 0.01:
            m["stato"] = "quadrato"
        elif m["saldo"] > 0:
            # Azienda deve ancora pagare (cedolino non ancora bonificato)
            m["stato"] = "in_pagamento"
        else:
            # AVERE > DARE: o cedolino non ancora arrivato, o acconti in eccesso
            m["stato"] = "anticipato"

    # Riepilogo annuale
    totale_dare_anno = round(sum(m["totale_dare"] for m in mesi.values()), 2)
    totale_avere_anno = round(sum(m["totale_avere"] for m in mesi.values()), 2)
    saldo_anno = round(totale_dare_anno - totale_avere_anno, 2)

    return {
        "dipendente": {
            "id": real_id,
            "nome": nome,
            "cognome": cognome,
            "nome_completo": f"{cognome} {nome}".strip(),
            "codice_fiscale": cf,
        },
        "anno": anno,
        "mesi": [mesi[m] for m in range(1, 13)],
        "riepilogo": {
            "totale_dare": totale_dare_anno,
            "totale_avere": totale_avere_anno,
            "saldo": saldo_anno,
            "mesi_quadrati": sum(1 for m in mesi.values() if m["stato"] == "quadrato"),
            "mesi_in_pagamento": sum(1 for m in mesi.values() if m["stato"] == "in_pagamento"),
            "mesi_anticipati": sum(1 for m in mesi.values() if m["stato"] == "anticipato"),
            "mesi_vuoti": sum(1 for m in mesi.values() if m["stato"] == "vuoto"),
        },
    }


# ============================================================================
# ENDPOINT 2: COLLETTIVA (matrice tutti dipendenti × tutti i mesi)
# ============================================================================

@router.get(
    "/collettiva",
    summary="Vista collettiva: matrice di tutti i dipendenti per un anno (eventualmente filtrata su un mese)",
)
@handle_errors
async def prima_nota_collettiva(
    anno: int = Query(..., ge=2020, le=2030),
    mese: Optional[int] = Query(None, ge=1, le=12),
    solo_attivi: bool = Query(default=True, description="Se true, esclude dipendenti dimessi"),
) -> Dict[str, Any]:
    """Vista collettiva: matrice dipendenti × mesi, ogni cella ha saldo + stato.

    Se 'mese' è specificato, restituisce un solo mese ma con il dettaglio
    completo DARE/AVERE per ogni dipendente. Altrimenti, restituisce l'anno
    intero ma con solo i totali per mese (senza dettaglio righe).
    """
    db = Database.get_db()

    # Carica dipendenti
    dip_query: Dict[str, Any] = {}
    if solo_attivi:
        dip_query["$or"] = [
            {"dimissionato": {"$ne": True}},
            {"dimissionato": {"$exists": False}},
        ]
    dipendenti = await db[COLL_DIPENDENTI].find(
        dip_query, {"_id": 0, "id": 1, "nome": 1, "cognome": 1, "codice_fiscale": 1}
    ).to_list(500)

    # Per la vista collettiva è più efficiente pre-caricare tutti i dati
    # in 3 query e poi raggrupparli, invece di chiamare l'endpoint per dipendente
    # 500 volte. Useremo aggregazioni MongoDB dove possibile.

    # Costruisci index dipendenti per id e per cognome
    dipendenti_by_id: Dict[str, Dict[str, Any]] = {d["id"]: d for d in dipendenti if d.get("id")}
    dipendenti_by_cognome: Dict[str, Dict[str, Any]] = {}
    for d in dipendenti:
        if d.get("cognome"):
            dipendenti_by_cognome[d["cognome"].strip().upper()] = d

    # Range temporale
    if mese:
        data_min = datetime(anno, mese, 1)
        # Ultimo giorno del mese
        if mese == 12:
            data_max = datetime(anno, 12, 31, 23, 59, 59)
        else:
            data_max = datetime(anno, mese + 1, 1)
        cedolini_filter_mese = {"mese": mese, "anno": anno}
        data_min_str = data_min.strftime("%Y-%m-%d")
        data_max_str = data_max.strftime("%Y-%m-%d") if mese == 12 else (
            datetime(anno, mese + 1, 1).strftime("%Y-%m-%d")
        )
    else:
        data_min = datetime(anno, 1, 1)
        data_max = datetime(anno, 12, 31, 23, 59, 59)
        cedolini_filter_mese = {"anno": anno}
        data_min_str = f"{anno}-01-01"
        data_max_str = f"{anno}-12-31"

    # Carica cedolini, acconti, movimenti in batch
    cedolini = await db[COLL_CEDOLINI].find(cedolini_filter_mese, {"_id": 0}).to_list(5000)
    acconti = await db[COLL_ACCONTI].find(
        {"data": {"$gte": data_min_str, "$lte": data_max_str}},
        {"_id": 0},
    ).to_list(5000)
    movimenti = await db[COLL_MOVIMENTI].find(
        {
            "data_contabile_obj": {"$gte": data_min, "$lte": data_max},
            "$or": [{"tipo": "uscita"}, {"importo": {"$lt": 0}}],
        },
        {"_id": 0},
    ).to_list(20000)

    # Set movimenti consumati da acconti riconciliati
    movimenti_consumati = {
        a.get("movimento_bancario_id")
        for a in acconti
        if a.get("movimento_bancario_id")
    }

    # Aggrega per dipendente_id × mese
    # struttura: { dip_id: { mese: { totale_dare, totale_avere, n_dare, n_avere } } }
    agg: Dict[str, Dict[int, Dict[str, Any]]] = {}

    def _bucket(dip_id: str, m: int) -> Dict[str, Any]:
        if dip_id not in agg:
            agg[dip_id] = {}
        if m not in agg[dip_id]:
            agg[dip_id][m] = {
                "mese": m,
                "totale_dare": 0.0,
                "totale_avere": 0.0,
                "n_voci_dare": 0,
                "n_voci_avere": 0,
            }
        return agg[dip_id][m]

    # DARE: cedolini
    for c in cedolini:
        dip_id = c.get("dipendente_id")
        cf = c.get("codice_fiscale")
        m = c.get("mese")
        if not m or m < 1 or m > 12:
            continue
        # Se non ho dipendente_id, prova match via CF
        if not dip_id and cf:
            for d in dipendenti:
                if d.get("codice_fiscale") == cf:
                    dip_id = d["id"]
                    break
        if not dip_id or dip_id not in dipendenti_by_id:
            continue
        netto = _netto_da_cedolino(c)
        if netto <= 0:
            continue
        b = _bucket(dip_id, m)
        b["totale_dare"] += netto
        b["n_voci_dare"] += 1

    # AVERE: acconti
    for a in acconti:
        data = _parse_data_iso(a.get("data"))
        if not data or data.year != anno:
            continue
        if mese and data.month != mese:
            continue
        dip_id = a.get("dipendente_id")
        if not dip_id or dip_id not in dipendenti_by_id:
            continue
        importo = abs(float(a.get("importo", 0) or 0))
        if importo <= 0:
            continue
        b = _bucket(dip_id, data.month)
        b["totale_avere"] += importo
        b["n_voci_avere"] += 1

    # AVERE: bonifici (con match cognome)
    for mov in movimenti:
        if mov.get("id") in movimenti_consumati:
            continue
        descrizione = (mov.get("descrizione") or "").upper()
        # Trova cognome match
        matched_dip = None
        for cognome_upper, d in dipendenti_by_cognome.items():
            if cognome_upper in descrizione:
                matched_dip = d
                break
        if not matched_dip:
            continue
        dip_id = matched_dip["id"]

        data_obj = mov.get("data_contabile_obj")
        if isinstance(data_obj, str):
            data_obj = _parse_data_iso(data_obj)
        if not data_obj:
            continue
        if data_obj.year != anno:
            continue
        if mese and data_obj.month != mese:
            continue
        importo = abs(float(mov.get("importo", 0) or 0))
        if importo <= 0:
            continue
        b = _bucket(dip_id, data_obj.month)
        b["totale_avere"] += importo
        b["n_voci_avere"] += 1

    # Costruisci response: lista dipendenti con i loro mesi
    risultati: List[Dict[str, Any]] = []
    mesi_da_includere = [mese] if mese else list(range(1, 13))

    for d in sorted(dipendenti, key=lambda x: (x.get("cognome", ""), x.get("nome", ""))):
        dip_id = d["id"]
        mesi_dip = []
        totale_dare_anno = 0.0
        totale_avere_anno = 0.0
        for m in mesi_da_includere:
            bucket = agg.get(dip_id, {}).get(m, {
                "mese": m, "totale_dare": 0.0, "totale_avere": 0.0,
                "n_voci_dare": 0, "n_voci_avere": 0,
            })
            dare = round(bucket["totale_dare"], 2)
            avere = round(bucket["totale_avere"], 2)
            saldo = round(dare - avere, 2)
            # Stato
            if dare == 0 and avere == 0:
                stato = "vuoto"
            elif abs(saldo) < 0.01:
                stato = "quadrato"
            elif saldo > 0:
                stato = "in_pagamento"
            else:
                stato = "anticipato"
            mesi_dip.append({
                "mese": m,
                "mese_nome": MESI_NOMI[m - 1],
                "totale_dare": dare,
                "totale_avere": avere,
                "saldo": saldo,
                "stato": stato,
                "n_voci_dare": bucket["n_voci_dare"],
                "n_voci_avere": bucket["n_voci_avere"],
            })
            totale_dare_anno += dare
            totale_avere_anno += avere

        # Skippa dipendenti senza alcun movimento nel periodo
        if totale_dare_anno == 0 and totale_avere_anno == 0:
            continue

        risultati.append({
            "dipendente_id": dip_id,
            "nome": d.get("nome", ""),
            "cognome": d.get("cognome", ""),
            "nome_completo": f"{d.get('cognome', '')} {d.get('nome', '')}".strip(),
            "mesi": mesi_dip,
            "totale_dare": round(totale_dare_anno, 2),
            "totale_avere": round(totale_avere_anno, 2),
            "saldo": round(totale_dare_anno - totale_avere_anno, 2),
        })

    return {
        "anno": anno,
        "mese": mese,
        "totale_dipendenti": len(risultati),
        "totali_globali": {
            "dare": round(sum(r["totale_dare"] for r in risultati), 2),
            "avere": round(sum(r["totale_avere"] for r in risultati), 2),
            "saldo": round(sum(r["saldo"] for r in risultati), 2),
        },
        "dipendenti": risultati,
    }
