"""
controllo_dati.py - Cruscotto lettura-only per misurare quanto i moduli
principali sono collegati tra loro.

Non corregge dati e non lancia rebuild: espone solo conteggi, severita e piccoli
campioni per guidare il lavoro operativo su prodotti, fornitori, fatture,
ricette, magazzino, lotti e scheduler.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Query, Depends

from app.lotti.db import database as db
from app.lotti.auth import require_admin

router = APIRouter(prefix="/controllo-dati", tags=["Controllo Dati"])


LINK_FIELDS = (
    "prodotto_master_id",
    "master_id",
    "prodotto_id",
    "prodotto_key",
    "prodotto_dizionario_id",
    "nome_canonico",
    "nome_canc",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [_safe_value(v) for v in value[:10]]
    if isinstance(value, dict):
        return {str(k): _safe_value(v) for k, v in list(value.items())[:12]}
    return str(value)


def _clean_doc(doc: dict | None) -> dict:
    if not doc:
        return {}
    return {str(k): _safe_value(v) for k, v in doc.items() if k != "_id"}


def _missing_or_empty(path: str) -> dict:
    return {
        "$or": [
            {path: {"$exists": False}},
            {path: None},
            {path: ""},
            {path: []},
        ]
    }


def _all_link_fields_missing(prefix: str) -> list[dict]:
    return [_missing_or_empty(f"{prefix}.{field}") for field in LINK_FIELDS]


def _issue_status(count: int, severity: str) -> str:
    if count <= 0:
        return "ok"
    return "critico" if severity == "critica" else "attenzione"


def _build_issue(
    *,
    issue_id: str,
    title: str,
    description: str,
    count: int,
    severity: str,
    owner: str,
    action: str,
    route: str = "",
    samples: list[dict] | None = None,
    total: int | None = None,
) -> dict:
    return {
        "id": issue_id,
        "titolo": title,
        "descrizione": description,
        "conteggio": int(count or 0),
        "totale": total,
        "severita": severity,
        "stato": _issue_status(int(count or 0), severity),
        "area": owner,
        "azione_consigliata": action,
        "route": route,
        "campioni": samples or [],
    }


def _calcola_score(issues: list[dict]) -> int:
    if not issues:
        return 100
    weights = {"critica": 18, "alta": 12, "media": 8, "bassa": 4}
    penalty = 0
    for issue in issues:
        count = int(issue.get("conteggio") or 0)
        if count <= 0:
            continue
        penalty += weights.get(issue.get("severita"), 8)
    return max(0, 100 - penalty)


async def _count(collection: str, filtro: dict | None = None) -> int:
    try:
        return await db[collection].count_documents(filtro or {})
    except Exception:
        return 0


async def _sample(
    collection: str,
    filtro: dict | None = None,
    projection: dict | None = None,
    *,
    limit: int = 5,
    sort: list[tuple[str, int]] | None = None,
) -> list[dict]:
    if limit <= 0:
        return []
    try:
        cursor = db[collection].find(filtro or {}, projection or {"_id": 0})
        if sort:
            cursor = cursor.sort(sort)
        docs = await cursor.limit(limit).to_list(limit)
        return [_clean_doc(d) for d in docs]
    except Exception:
        return []


async def _aggregate_count(collection: str, pipeline: list[dict]) -> int:
    try:
        docs = await db[collection].aggregate([*pipeline, {"$count": "n"}]).to_list(1)
        return int(docs[0].get("n", 0)) if docs else 0
    except Exception:
        return 0


async def _aggregate_sample(
    collection: str,
    pipeline: list[dict],
    *,
    limit: int = 5,
) -> list[dict]:
    if limit <= 0:
        return []
    try:
        docs = await db[collection].aggregate([*pipeline, {"$limit": limit}]).to_list(limit)
        return [_clean_doc(d) for d in docs]
    except Exception:
        return []


async def _overview(limit_campioni: int) -> dict:
    now = datetime.now(timezone.utc)
    since = (now - timedelta(days=7)).isoformat()

    prodotti_totali = await _count("prodotti_master")
    # Esclude dal conteggio le voci NON ordinabili (DDT/trasporto/servizi/non-food):
    # non sono prodotti reali del catalogo (la UI già le nasconde) e falsavano i numeri.
    from .prodotti_master import _RX_NON_ORDINABILI
    _solo_ordinabili = {
        "nome_canonico": {"$not": {"$regex": f"(?i){_RX_NON_ORDINABILI}"}}
    }
    # I prodotti la cui UNICA fonte è prodotti_vendita sono fatti/venduti in casa
    # (es. Crocchè, Frittatina): non hanno fornitore né prezzo d'acquisto per
    # natura — il loro costo deriva dalla ricetta. Contarli come "senza
    # fornitore/prezzo" è un falso positivo: si escludono.
    _non_solo_vendita = {"fonti": {"$ne": ["prodotti_vendita"]}}
    prodotti_senza_fornitore_q = {
        "$and": [
            _solo_ordinabili,
            _non_solo_vendita,
            {
                "$or": [
                    {"fornitori": {"$exists": False}},
                    {"fornitori": []},
                    {"fornitori": ""},
                ]
            },
        ]
    }
    prodotti_senza_prezzo_q = {
        "$and": [
            _solo_ordinabili,
            _non_solo_vendita,
            {
                "$or": [
                    {"ultimo_prezzo": {"$exists": False}},
                    {"ultimo_prezzo": None},
                    {"ultimo_prezzo": ""},
                    {"ultimo_prezzo": {"$lte": 0}},
                ]
            },
        ]
    }

    fatture_totali = await _count("fatture")
    fatture_non_riconciliate_q = {
        "$or": [
            {"fornitore": {"$exists": False}},
            {"fornitore": ""},
            {"fornitore": None},
            {"fornitore": {"$regex": "sconosciut", "$options": "i"}},
            {"piva": {"$exists": False}},
            {"piva": ""},
            {"piva": None},
        ]
    }

    # I fornitori ESCLUSI (vernici, cancelleria, servizi…) non devono entrare
    # nel conteggio: le loro righe non vanno mappate per definizione — contarle
    # gonfiava il numero con voci tipo "CARTA DA PARATO" (segnalato da Enzo
    # 04/07/2026).
    _esclusi_docs = await db.fornitori.find(
        {"escluso": True}, {"_id": 0, "nome": 1}
    ).to_list(500)
    _fornitori_esclusi = [f["nome"] for f in _esclusi_docs if f.get("nome")]

    righe_fattura_pipeline = [
        {"$match": {"fornitore": {"$nin": _fornitori_esclusi}}} if _fornitori_esclusi else {"$match": {}},
        {"$unwind": "$prodotti"},
        {
            "$match": {
                "$and": [
                    {
                        "$or": [
                            {"prodotti.descrizione": {"$exists": True, "$ne": ""}},
                            {"prodotti.nome": {"$exists": True, "$ne": ""}},
                        ]
                    },
                    # Esclude le righe non-prodotto (servizi/riferimenti/non-food)
                    # marcate dal backfill: non sono mappabili a un prodotto.
                    {"prodotti.riga_non_prodotto": {"$ne": True}},
                    *_all_link_fields_missing("prodotti"),
                ]
            }
        },
    ]
    righe_fattura_sample_pipeline = [
        *righe_fattura_pipeline,
        {
            "$project": {
                "_id": 0,
                "id": 1,  # id fattura: serve al deep-link "apri la fattura"
                "numero_fattura": 1,
                "fornitore": 1,
                "descrizione": {"$ifNull": ["$prodotti.descrizione", "$prodotti.nome"]},
                "quantita": "$prodotti.quantita",
                "prezzo": {"$ifNull": ["$prodotti.prezzo", "$prodotti.prezzo_unitario"]},
            }
        },
    ]

    # Il campo reale degli ingredienti è `ingredienti_dettaglio` (oggetti con
    # prodotto_dizionario_id/prezzo_kg). Il vecchio `ingredienti` è una lista di
    # stringhe (solo display) e non può avere link: controllarlo dava un falso
    # "527 non collegati". Si controlla il campo reale.
    ricette_pipeline = [
        {"$unwind": "$ingredienti_dettaglio"},
        {"$match": {"$and": _all_link_fields_missing("ingredienti_dettaglio")}},
    ]
    ricette_sample_pipeline = [
        *ricette_pipeline,
        {
            "$project": {
                "_id": 0,
                "id": 1,  # id ricetta: serve al deep-link "apri la scheda"
                "ricetta": {"$ifNull": ["$nome", "$nome_ricetta"]},
                "ingrediente": {
                    "$ifNull": [
                        "$ingredienti_dettaglio.nome",
                        {"$ifNull": ["$ingredienti_dettaglio.descrizione", "$ingredienti_dettaglio"]},
                    ]
                },
            }
        },
    ]

    lotti_totali = await _count("lotti")
    lotti_senza_traccia_q = {
        "$and": [
            {
                "$or": [
                    {"stato": {"$exists": False}},
                    # vocabolario reale (prima "consumato/chiuso/archiviato",
                    # mai scritti → filtro inefficace): esclude i lotti finiti.
                    {"stato": {"$nin": ["smaltito", "esaurito"]}},
                ]
            },
            _missing_or_empty("ingredienti_dettaglio"),
            _missing_or_empty("ingredienti"),
        ]
    }

    movimenti_senza_prodotto_q = {
        "$and": [
            # I movimenti di "ricostruzione" (rigenerazione giacenze, qty 0) sono
            # record di sistema, non movimenti di prodotto reali: esclusi.
            {"tipo": {"$ne": "ricostruzione"}},
            {
                "$or": [
                    {"prodotto_id": {"$exists": False}},
                    {"prodotto_id": ""},
                    {"prodotto_id": None},
                ]
            },
        ]
    }
    scheduler_failed_q = {
        "$and": [
            {"timestamp": {"$gte": since}},
            {
                "$or": [
                    {"success": False},
                    {"errore": {"$exists": True, "$ne": ""}},
                    {"error": {"$exists": True, "$ne": ""}},
                ]
            },
        ]
    }

    issues = [
        _build_issue(
            issue_id="prodotti_senza_fornitore",
            title="Prodotti senza fornitore",
            description="Record in prodotti_master senza fornitore valorizzato.",
            count=await _count("prodotti_master", prodotti_senza_fornitore_q),
            total=prodotti_totali,
            severity="alta",
            owner="Prodotti",
            route="#prodotti",
            action="Riconciliare aliases/codici e rilanciare il rebuild prodotti_master.",
            samples=await _sample(
                "prodotti_master",
                prodotti_senza_fornitore_q,
                {"_id": 0, "id": 1, "nome_canonico": 1, "fonti": 1, "aliases": 1},
                limit=limit_campioni,
            ),
        ),
        _build_issue(
            issue_id="prodotti_senza_prezzo",
            title="Prodotti senza prezzo",
            description="Record in prodotti_master non utilizzabili per food cost e ordini.",
            count=await _count("prodotti_master", prodotti_senza_prezzo_q),
            total=prodotti_totali,
            severity="media",
            owner="Prodotti",
            route="#prodotti",
            action="Collegare righe fattura/listino o impostare prezzo ultimo affidabile.",
            samples=await _sample(
                "prodotti_master",
                prodotti_senza_prezzo_q,
                {"_id": 0, "id": 1, "nome_canonico": 1, "fornitori": 1, "fonti": 1},
                limit=limit_campioni,
            ),
        ),
        _build_issue(
            issue_id="fatture_non_riconciliate",
            title="Fatture con fornitore debole",
            description="Fatture senza P.IVA o con fornitore mancante/sconosciuto.",
            count=await _count("fatture", fatture_non_riconciliate_q),
            total=fatture_totali,
            severity="critica",
            owner="Fatture",
            route="#fatture",
            action="Normalizzare anagrafica fornitori e riallineare le fatture importate.",
            samples=await _sample(
                "fatture",
                fatture_non_riconciliate_q,
                {"_id": 0, "id": 1, "numero_fattura": 1, "data_fattura": 1, "fornitore": 1, "piva": 1},
                limit=limit_campioni,
                sort=[("created_at", -1)],
            ),
        ),
        _build_issue(
            issue_id="righe_fattura_senza_link",
            title="Righe fattura senza link prodotto",
            description="Righe prodotto prive di id/key verso prodotti_master o dizionario.",
            count=await _aggregate_count("fatture", righe_fattura_pipeline),
            severity="critica",
            owner="Fatture",
            route="#fatture",
            action="Salvare un riferimento prodotto canonico sulle righe fattura durante sync/import.",
            samples=await _aggregate_sample("fatture", righe_fattura_sample_pipeline, limit=limit_campioni),
        ),
        _build_issue(
            issue_id="ricette_ingredienti_senza_link",
            title="Ingredienti ricetta non collegati",
            description="Ingredienti senza riferimento a prodotto master/dizionario.",
            count=await _aggregate_count("ricette", ricette_pipeline),
            severity="critica",
            owner="Ricette",
            route="#ricette",
            action="Mappare ogni ingrediente a un prodotto canonico prima del food cost.",
            samples=await _aggregate_sample("ricette", ricette_sample_pipeline, limit=limit_campioni),
        ),
        _build_issue(
            issue_id="lotti_senza_tracciabilita",
            title="Lotti senza ingredienti tracciati",
            description="Lotti aperti senza ingredienti o dettaglio ingredienti.",
            count=await _count("lotti", lotti_senza_traccia_q),
            total=lotti_totali,
            severity="alta",
            owner="Lotti",
            route="#lotti",
            action="Agganciare produzione/lotti agli ingredienti usati e alle fatture di origine.",
            samples=await _sample(
                "lotti",
                lotti_senza_traccia_q,
                {"_id": 0, "id": 1, "numero_lotto": 1, "prodotto": 1, "prodotto_nome": 1, "data_produzione": 1, "stato": 1},
                limit=limit_campioni,
                sort=[("data_produzione", -1)],
            ),
        ),
        _build_issue(
            issue_id="movimenti_magazzino_senza_prodotto",
            title="Movimenti magazzino senza prodotto",
            description="Movimenti bar/magazzino privi di prodotto_id.",
            count=await _count("magazzino_bar_movimenti", movimenti_senza_prodotto_q),
            severity="media",
            owner="Magazzino",
            route="#magazzino_prodotti",
            action="Rendere obbligatorio prodotto_id su carichi/scarichi e backfillare i movimenti storici.",
            samples=await _sample(
                "magazzino_bar_movimenti",
                movimenti_senza_prodotto_q,
                {"_id": 0, "tipo": 1, "nome": 1, "quantita": 1, "data": 1, "operatore_nome": 1},
                limit=limit_campioni,
                sort=[("data", -1)],
            ),
        ),
        _build_issue(
            issue_id="scheduler_falliti_7g",
            title="Job scheduler falliti negli ultimi 7 giorni",
            description="Log scheduler con success=false o errore valorizzato.",
            count=await _count("scheduler_logs", scheduler_failed_q),
            severity="alta",
            owner="Automazioni",
            route="#dashboard",
            action="Verificare ultimo errore, rilanciare il job e rendere visibile lo stato operativo.",
            samples=await _sample(
                "scheduler_logs",
                scheduler_failed_q,
                {"_id": 0, "job": 1, "timestamp": 1, "success": 1, "errore": 1, "error": 1},
                limit=limit_campioni,
                sort=[("timestamp", -1)],
            ),
        ),
    ]

    summary = {
        "totale_controlli": len(issues),
        "ok": len([i for i in issues if i["stato"] == "ok"]),
        "attenzione": len([i for i in issues if i["stato"] == "attenzione"]),
        "critici": len([i for i in issues if i["stato"] == "critico"]),
        "score_interconnessione": _calcola_score(issues),
    }

    next_actions = [
        "Stabilire prodotti_master come riferimento per righe fattura, ricette e ordini.",
        "Salvare supplier_id/P.IVA canonica su ogni fattura e scheda ricevimento.",
        "Backfillare i riferimenti mancanti prima di rendere obbligatori i campi.",
        "Aggiungere log scheduler strutturati con ultimo esito e retry manuale.",
    ]

    return {
        "aggiornato_il": _now_iso(),
        "riepilogo": summary,
        "controlli": issues,
        "prossime_azioni": next_actions,
    }


@router.get("/overview")
async def overview(limit_campioni: int = Query(5, ge=0, le=20)):
    """Restituisce il quadro di interconnessione dei dati core."""
    return await _overview(limit_campioni)


# Job rimossi dal sistema: i loro log storici falsano il conteggio "job falliti".
_JOB_RIMOSSI = ["gestionale_sync"]


@router.post("/pulisci-log-obsoleti")
async def pulisci_log_obsoleti(_admin=Depends(require_admin)):
    """Cancella gli scheduler_logs dei job che non esistono più (es. gestionale_sync,
    rimosso con la dismissione del sync da gestionalecloud). Non tocca i log dei job attivi."""
    res = await db.scheduler_logs.delete_many({"job": {"$in": _JOB_RIMOSSI}})
    return {"ok": True, "job_rimossi": _JOB_RIMOSSI, "log_cancellati": res.deleted_count}
