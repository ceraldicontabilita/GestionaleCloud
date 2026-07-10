"""
Admin Rollback — elimina dati per intervallo di tempo, per sezione.

Strumento per l'admin per fare controlli di precisione: elimina i dati di un
periodo (es. ultima settimana) da una sezione, poi re-importa e verifica che
i calcoli tornino corretti. NON è un rollback vero (non ripristina backup,
elimina soltanto) — il nome riflette l'uso previsto dall'utente.

Sicurezza: ogni endpoint di cancellazione richiede ruolo admin
(get_current_admin_user) — stesso pattern usato per gli altri endpoint
distruttivi del gestionale (vedi memoria/endpoints/README.md item #26).
Ogni cancellazione richiede un periodo esplicito (mai "elimina tutto" senza
un intervallo) ed espone prima un endpoint di sola conta, cosicché il
frontend possa mostrare "stai per eliminare N record" prima di chiedere
conferma.
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any, List
from datetime import datetime, timezone, timedelta
import logging

from app.database import Database
from app.utils.dependencies import get_current_admin_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin/rollback", tags=["Admin Rollback"])

# ── Periodi consentiti ────────────────────────────────────────────────────
# Due tipi: "relativo" (ultimi N giorni da oggi, utile per i controlli di
# precisione su dati appena importati) e "anno" (intero anno solare — più
# utile di "N anni fa" quando si vuole svuotare un anno preciso senza dover
# calcolare a mente quanti anni indietro sia rispetto a oggi).
PERIODI = {
    "1g": {"label": "1 giorno", "tipo": "relativo", "giorni": 1},
    "1s": {"label": "1 settimana", "tipo": "relativo", "giorni": 7},
    "1m": {"label": "1 mese", "tipo": "relativo", "giorni": 30},
    "2023": {"label": "Anno 2023", "tipo": "anno", "anno": 2023},
    "2024": {"label": "Anno 2024", "tipo": "anno", "anno": 2024},
    "2025": {"label": "Anno 2025", "tipo": "anno", "anno": 2025},
}

# ── Sezioni: collezione/i + campi data candidati (provati in OR) ──────────
# Più campi per collezione perché nel gestionale convenzioni diverse
# convivono per storia (vedi memoria/endpoints/*.md) — usare $or su tutti i
# nomi plausibili è più sicuro che indovinarne uno solo e perdere righe.
SEZIONI: Dict[str, Dict[str, Any]] = {
    "corrispettivi": {
        "label": "Corrispettivi",
        "collezioni": [{"nome": "corrispettivi", "campi_data": ["data"]}],
    },
    "fatture": {
        "label": "Fatture (emesse e ricevute)",
        "collezioni": [{"nome": "invoices", "campi_data": ["invoice_date", "data_documento", "data_ricezione"]}],
    },
    "paypal": {
        "label": "Dati PayPal",
        "collezioni": [
            {"nome": "paypal_transactions", "campi_data": ["date", "data"]},
            {"nome": "paypal_statements", "campi_data": ["data", "date"]},
        ],
    },
    "cedolini": {
        "label": "Cedolini",
        "collezioni": [{"nome": "cedolini", "campi_data": ["data"], "mese_anno": True}],
    },
    "prima_nota_cassa": {
        "label": "Prima Nota Cassa",
        "collezioni": [{"nome": "prima_nota_cassa", "campi_data": ["data"]}],
    },
    "prima_nota_banca": {
        "label": "Prima Nota Banca / Estratto Conto",
        "collezioni": [
            {"nome": "prima_nota_banca", "campi_data": ["data"]},
            {"nome": "estratto_conto_movimenti", "campi_data": ["data"]},
        ],
    },
    "f24": {
        "label": "F24",
        "collezioni": [{"nome": "f24_unificato", "campi_data": ["data_scadenza", "data_versamento", "data"]}],
    },
    "assegni": {
        "label": "Assegni",
        "collezioni": [{"nome": "assegni", "campi_data": ["data_emissione", "data"]}],
    },
    "verbali_noleggio": {
        "label": "Verbali Noleggio",
        "collezioni": [{"nome": "verbali_noleggio", "campi_data": ["data", "data_verbale"]}],
    },
    "bonifici": {
        "label": "Archivio Bonifici",
        "collezioni": [{"nome": "bonifici_transfers", "campi_data": ["data"]}],
    },
    "magazzino": {
        "label": "Magazzino (movimenti)",
        "collezioni": [{"nome": "warehouse_movements", "campi_data": ["data"]}],
    },
}


def _range_periodo(periodo: str) -> "tuple[str, str]":
    """Ritorna (data_da, data_a) in formato YYYY-MM-DD per il periodo scelto.

    Periodi "relativo": [oggi - N giorni, oggi]. Periodi "anno": tutto
    l'anno solare [1 gennaio, 31 dicembre] indipendentemente da oggi.
    """
    if periodo not in PERIODI:
        raise HTTPException(
            status_code=400,
            detail=f"Periodo non valido: {periodo!r}. Usare uno tra: {', '.join(PERIODI.keys())}",
        )
    cfg = PERIODI[periodo]
    if cfg["tipo"] == "anno":
        anno = cfg["anno"]
        return f"{anno:04d}-01-01", f"{anno:04d}-12-31"

    oggi = datetime.now(timezone.utc)
    cutoff = oggi - timedelta(days=cfg["giorni"])
    return cutoff.strftime("%Y-%m-%d"), oggi.strftime("%Y-%m-%d")


def _valida_sezione(sezione: str) -> Dict[str, Any]:
    if sezione not in SEZIONI:
        raise HTTPException(
            status_code=400,
            detail=f"Sezione non valida: {sezione!r}. Usare una tra: {', '.join(SEZIONI.keys())}",
        )
    return SEZIONI[sezione]


def _query_periodo(collezione_cfg: Dict[str, Any], cutoff_str: str, oggi_str: str) -> Dict[str, Any]:
    """Costruisce la query Mongo per 'documenti nell'intervallo [cutoff, oggi]'.

    Prova tutti i campi data candidati in OR. Per le collezioni con
    convenzione mese/anno (es. cedolini) aggiunge anche un OR sui mesi
    dell'intervallo, per non perdere righe che non hanno un campo data
    stringa valorizzato.
    """
    or_clauses: List[Dict[str, Any]] = [
        {campo: {"$gte": cutoff_str, "$lte": oggi_str}}
        for campo in collezione_cfg["campi_data"]
    ]

    if collezione_cfg.get("mese_anno"):
        cutoff_dt = datetime.strptime(cutoff_str, "%Y-%m-%d")
        oggi_dt = datetime.strptime(oggi_str, "%Y-%m-%d")
        mesi_anni = set()
        cursor_dt = cutoff_dt.replace(day=1)
        while cursor_dt <= oggi_dt:
            mesi_anni.add((cursor_dt.year, cursor_dt.month))
            cursor_dt = (cursor_dt.replace(day=28) + timedelta(days=4)).replace(day=1)
        for anno, mese in mesi_anni:
            or_clauses.append({"anno": anno, "mese": mese})

    return {"$or": or_clauses}


@router.get("/sezioni")
async def lista_sezioni() -> Dict[str, Any]:
    """Elenco delle sezioni disponibili e dei periodi selezionabili, per il frontend."""
    return {
        "sezioni": [
            {"chiave": k, "label": v["label"], "collezioni": [c["nome"] for c in v["collezioni"]]}
            for k, v in SEZIONI.items()
        ],
        "periodi": [{"chiave": k, "label": v["label"]} for k, v in PERIODI.items()],
    }


@router.get("/{sezione}/conta")
async def conta_da_eliminare(sezione: str, periodo: str) -> Dict[str, Any]:
    """Conta (senza eliminare) quanti documenti verrebbero cancellati.

    Usato dal frontend per mostrare "stai per eliminare N record" prima
    della conferma. Nessun requisito di ruolo: è una sola lettura.
    """
    cutoff_str, oggi_str = _range_periodo(periodo)
    sezione_cfg = _valida_sezione(sezione)
    db = Database.get_db()

    dettaglio = []
    totale = 0
    for coll_cfg in sezione_cfg["collezioni"]:
        query = _query_periodo(coll_cfg, cutoff_str, oggi_str)
        count = await db[coll_cfg["nome"]].count_documents(query)
        dettaglio.append({"collezione": coll_cfg["nome"], "count": count})
        totale += count

    return {
        "success": True,
        "sezione": sezione,
        "periodo": periodo,
        "data_da": cutoff_str,
        "data_a": oggi_str,
        "totale": totale,
        "dettaglio": dettaglio,
    }


@router.delete("/{sezione}")
async def elimina_periodo(
    sezione: str,
    periodo: str,
    admin_user: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Elimina i documenti della sezione nell'intervallo [oggi - periodo, oggi].

    Solo admin. Richiede sempre un periodo esplicito (nessuna cancellazione
    illimitata). Ogni cancellazione viene loggata con utente, sezione,
    periodo e conteggio per collezione.
    """
    cutoff_str, oggi_str = _range_periodo(periodo)
    sezione_cfg = _valida_sezione(sezione)
    db = Database.get_db()

    dettaglio = []
    totale_eliminati = 0
    for coll_cfg in sezione_cfg["collezioni"]:
        query = _query_periodo(coll_cfg, cutoff_str, oggi_str)
        result = await db[coll_cfg["nome"]].delete_many(query)
        dettaglio.append({"collezione": coll_cfg["nome"], "eliminati": result.deleted_count})
        totale_eliminati += result.deleted_count

    logger.warning(
        f"[ADMIN ROLLBACK] {admin_user.get('email', admin_user.get('sub', '?'))} ha eliminato "
        f"{totale_eliminati} documenti da '{sezione}' (periodo {periodo}, {cutoff_str}..{oggi_str}): "
        f"{dettaglio}"
    )

    return {
        "success": True,
        "sezione": sezione,
        "periodo": periodo,
        "data_da": cutoff_str,
        "data_a": oggi_str,
        "totale_eliminati": totale_eliminati,
        "dettaglio": dettaglio,
    }


# ── Pulizia cartella DRIVE fatture per anno ────────────────────────────────
# Complemento del rollback (richiesta utente 10/07): eliminati i dati di un
# anno dal gestionale, i file XML/P7M restano su Drive e la sincronizzazione
# oraria + la quadratura li REIMPORTEREBBERO. Questi endpoint scandiscono la
# cartella indicata (sottocartelle incluse, quindi anche "Elaborate"),
# leggono l'anno dalla data del documento dentro l'XML e spostano nel
# CESTINO Drive i file degli anni scelti (recuperabili 30 giorni).
from pydantic import BaseModel


class PuliziaDriveRequest(BaseModel):
    folder: str          # ID o URL completo della cartella Drive
    anni: List[int]      # es. [2023, 2024, 2025]


@router.post("/drive-fatture/conta")
async def conta_drive_fatture(req: PuliziaDriveRequest) -> Dict[str, Any]:
    """Conta (senza toccare nulla) i file fattura degli anni scelti nella cartella."""
    from app.services.drive_pulizia import pulizia_fatture_drive
    return await pulizia_fatture_drive(req.folder, req.anni, dry_run=True)


@router.post("/drive-fatture/elimina")
async def elimina_drive_fatture(
    req: PuliziaDriveRequest,
    admin_user: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Sposta nel cestino Drive i file fattura degli anni scelti. Solo admin."""
    from app.services.drive_pulizia import pulizia_fatture_drive
    esito = await pulizia_fatture_drive(req.folder, req.anni, dry_run=False)
    logger.warning(
        f"[ADMIN ROLLBACK DRIVE] {admin_user.get('email', admin_user.get('sub', '?'))} "
        f"ha cestinato {esito.get('eliminati', 0)} file fattura dalla cartella Drive "
        f"{esito.get('folder_id')} (anni {esito.get('anni')}, "
        f"esaminati {esito.get('esaminati', 0)}, non determinati {esito.get('non_determinati', 0)})"
    )
    return esito
