"""
Analisi F24 — classificazione normativa, scadenze/ravvedimenti,
associazione ai cedolini e doppi pagamenti.

Espone via API il motore unico app/engines/tributi_engine.py
(specifica: la specifica del titolare (non è nel repository: vale il codice)).

Endpoint (montati sotto /api/f24-analisi):
  GET /{f24_id}                     → analisi completa del modello (§11+§20)
  GET /{f24_id}/associazione        → esito §15 verso i cedolini di mese/anno
  GET /doppi-pagamenti              → scansione coppie DM10↔RC01 pagate (§21+§23), con lo stato scelto
  PUT /doppi-pagamenti/{id}/stato   → decisione del titolare (admin, motivo obbligatorio)
  POST /doppi-pagamenti/rileva      → crea le anomalie nuove (admin, dry_run per difetto)
"""
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.database import Database
from app.engines import tributi_engine as te
from app.services import f24_anomalie as fa
from app.utils.dependencies import get_current_admin_user

logger = logging.getLogger(__name__)
router = APIRouter()

# Consolidamento F24 (P1 §5.1): collezione canonica UNICA `f24_unificato`. La
# vecchia `f24_commercialista` (letterale) è stata migrata qui in modo non
# distruttivo (app/scripts/migra_f24_unificato.py); leggere entrambe dopo la
# migrazione avrebbe contato due volte lo stesso F24. Il motore lavora sul
# documento, non sulla collezione.
_COLLEZIONI_F24 = ("f24_unificato",)


async def _trova_f24(db, f24_id: str) -> Optional[Dict[str, Any]]:
    for coll in _COLLEZIONI_F24:
        doc = await db[coll].find_one({"id": f24_id}, {"_id": 0, "pdf_data": 0})
        if doc:
            doc["_collezione"] = coll
            return doc
    return None


@router.get("/doppi-pagamenti")
async def scan_doppi_pagamenti() -> Dict[str, Any]:
    """Cerca coppie F24 ordinario (DM10) ↔ RC01 dello stesso periodo con
    entrambi i pagamenti risultanti: POSSIBILE DOPPIO PAGAMENTO (§23).
    Lo stato di ogni coppia e' quello scelto dal titolare, se c'e'."""
    db = Database.get_db()
    scansione = fa.trova_coppie_doppio_pagamento(await fa._leggi_f24(db))
    anomalie = await fa.unisci_stati_salvati(db, scansione["anomalie"])
    return {
        "esaminati_ordinari": scansione["esaminati_ordinari"],
        "esaminati_rc01": scansione["esaminati_rc01"],
        "possibili_doppi_pagamenti": len(anomalie),
        "da_verificare": sum(1 for a in anomalie if a["stato"] == fa.STATO_APERTO),
        "anomalie": anomalie,
        "stati_possibili": list(te.STATI_ANOMALIA_DOPPIO_PAGAMENTO),
    }


class StatoAnomalia(BaseModel):
    stato: str
    motivo: Optional[str] = None


@router.put("/doppi-pagamenti/{anomalia_id}/stato")
async def imposta_stato_doppio_pagamento(
    anomalia_id: str,
    corpo: StatoAnomalia,
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Il titolare decide l'anomalia scegliendo lo stato da una lista. Il motivo e'
    obbligatorio per ogni stato che non sia «da_verificare»."""
    db = Database.get_db()
    autore = str(_admin.get("email") or _admin.get("username") or _admin.get("id") or "admin")
    try:
        doc = await fa.imposta_stato(db, anomalia_id, corpo.stato, corpo.motivo, autore)
    except fa.StatoNonValido as exc:
        raise HTTPException(status_code=422, detail={
            "code": "STATO_ANOMALIA_NON_VALIDO", "message": str(exc), "details": exc.dettagli,
        })
    if doc is None:
        raise HTTPException(status_code=404, detail="Anomalia non trovata")
    return {"id": anomalia_id, "stato": doc["stato"], "storico": doc["storico"]}


@router.post("/doppi-pagamenti/rileva")
async def rileva_doppi_pagamenti(
    dry_run: bool = Query(True, description="True = solo anteprima, non scrive anomalie ne' alert"),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Crea le anomalie di doppio pagamento nuove (una per coppia, mai duplicate)."""
    return await fa.rileva_doppi_pagamenti(Database.get_db(), dry_run=dry_run)


def _movimenti_banca_f24(f24: Dict[str, Any]) -> list:
    """Id dei movimenti di estratto conto che hanno pagato il modello, nei
    nomi scritti dal registro unico F24/banca (PR 12):
    ``movimento_bancario_id`` (patch_pagamento_banca), ``allocazioni_banca[]
    .movimento_id`` (pagamenti parziali/multipli), ``movimento_bancario.id``."""
    ids: list = []
    principale = f24.get("movimento_bancario_id")
    if principale:
        ids.append(str(principale))
    for alloc in f24.get("allocazioni_banca") or []:
        if isinstance(alloc, dict) and alloc.get("movimento_id"):
            ids.append(str(alloc["movimento_id"]))
    movimento = f24.get("movimento_bancario")
    if isinstance(movimento, dict) and (movimento.get("id") or movimento.get("fingerprint")):
        ids.append(str(movimento.get("id") or movimento.get("fingerprint")))
    visti: list = []
    for mid in ids:
        if mid not in visti:
            visti.append(mid)
    return visti


@router.get("/tabella")
async def tabella_analisi(anno: Optional[int] = Query(None, ge=2000, le=2100)) -> Dict[str, Any]:
    """Tabella §20 della specifica: una riga per F24 con periodo di
    competenza, scadenza naturale, data effettiva di pagamento, giorni di
    ritardo, stato, tipo versamento, causale INPS, documento collegato,
    possibile duplicazione e motivazione automatica."""
    db = Database.get_db()

    docs: list = []
    for coll in _COLLEZIONI_F24:
        for d in await db[coll].find({}, {"_id": 0, "pdf_data": 0}).to_list(2000):
            d["_collezione"] = coll
            docs.append(d)

    # Pre-analisi di tutti i modelli (funzioni pure, nessun altro accesso DB)
    analisi: Dict[int, Dict[str, Any]] = {}
    for i, d in enumerate(docs):
        analisi[i] = te.classifica_f24(d)

    if anno:
        indici = [i for i in analisi
                  if (analisi[i]["periodo_prevalente"] or "").endswith(str(anno))]
    else:
        indici = list(analisi.keys())

    # Duplicazioni: coppie ordinario ↔ RC01 sullo stesso periodo (una passata)
    duplicazione: Dict[int, str] = {}
    rc01_idx = [i for i in indici if "RC01" in analisi[i]["causali_inps"]]
    ordinari_idx = [i for i in indici if i not in rc01_idx]
    for ir in rc01_idx:
        for io in ordinari_idx:
            if analisi[io]["periodo_prevalente"] != analisi[ir]["periodo_prevalente"]:
                continue
            esito = te.rileva_doppio_pagamento(docs[io], docs[ir])
            if esito.get("possibile_doppio_pagamento"):
                duplicazione[ir] = "da_verificare"
                duplicazione[io] = "da_verificare"
            elif esito["dettaglio"].get("collegati"):
                duplicazione.setdefault(ir, "collegato_no_duplicato")
                duplicazione.setdefault(io, "collegato_no_duplicato")

    # Audit 03/09/2026 §6 (PR 16): dal modello F24 si deve arrivare alla
    # quietanza e all'addebito bancario. La quietanza puo' vivere in
    # `fiscal_documents` (PDF servito da /api/fiscal/documents/{id}/content)
    # o nella collezione storica `quietanze_f24`: una sola query per fonte.
    quietanza_ids = sorted({
        str(docs[i].get("quietanza_id")) for i in indici if docs[i].get("quietanza_id")
    })
    fonte_quietanza: Dict[str, str] = {}
    if quietanza_ids:
        for coll in ("fiscal_documents", "quietanze_f24"):
            try:
                trovate = await db[coll].find(
                    {"id": {"$in": quietanza_ids}}, {"_id": 0, "id": 1}
                ).to_list(len(quietanza_ids))
            except Exception as exc:  # noqa: BLE001 - arricchimento, mai bloccante
                logger.warning("Quietanze non leggibili da %s: %s", coll, exc)
                trovate = []
            for q in trovate:
                fonte_quietanza.setdefault(str(q.get("id")), coll)

    righe = []
    for i in indici:
        a = analisi[i]
        d = docs[i]
        dup = duplicazione.get(i, "no")
        quietanza_id = d.get("quietanza_id")
        fonte = fonte_quietanza.get(str(quietanza_id)) if quietanza_id else None
        movimenti_banca = _movimenti_banca_f24(d)
        motivi = []
        if a["tipo_versamento"] != "ordinario":
            motivi.append(f"{a['tipo_versamento']} (causali: {', '.join(a['causali_inps']) or '—'})")
        if a["stato"] == "pagato_in_ritardo":
            motivi.append(f"pagato con {a['giorni_ritardo']} giorni di ritardo "
                          f"rispetto alla scadenza naturale {a['scadenza_naturale']}")
        elif a["stato"] == "pagato_nei_termini":
            motivi.append("pagato nei termini")
        elif a["stato"] == "non_pagato":
            motivi.append("scadenza naturale superata senza pagamento risultante")
        # L'F24 del commercialista pagato con un ravvedimento non e' «non
        # pagato»: resta com'e', col legame al modello e alla quietanza.
        ravv = d.get("ravvedimento") or {}
        stato_pagamento = a["stato"]
        if ravv.get("stato") == "RAVVEDUTO":
            stato_pagamento = "ravveduto"
            motivi = [m for m in motivi if not m.startswith("scadenza naturale superata")]
            motivi.append("ravveduto: " + str(ravv.get("motivazione") or ""))
        if d.get("ravvedimento_di"):
            motivi.append(f"ravvedimento di {len(d['ravvedimento_di'])} F24 del commercialista")
        if dup == "da_verificare":
            motivi.append("POSSIBILE DOPPIO PAGAMENTO con il modello collegato: verificare")
        elif dup == "collegato_no_duplicato":
            motivi.append("collegato a regolarizzazione dello stesso debito (non sommare due volte)")

        righe.append({
            "f24_id": d.get("id"),
            "file": d.get("file_name") or d.get("filename"),
            "collezione": d.get("_collezione"),
            "periodo_competenza": a["periodo_prevalente"],
            "scadenza_naturale": a["scadenza_naturale"],
            "data_pagamento": a["data_pagamento"],
            "giorni_ritardo": a["giorni_ritardo"],
            "stato_pagamento": stato_pagamento,
            "tipo_versamento": a["tipo_versamento"],
            "causali_inps": a["causali_inps"],
            "codici_tributo": sorted({
                str(r.get("codice_tributo") or r.get("causale") or "").strip()
                for sezione in ("sezione_erario", "sezione_inps", "sezione_regioni", "sezione_imu")
                for r in (d.get(sezione) or [])
                if isinstance(r, dict) and (r.get("codice_tributo") or r.get("causale"))
            }),
            "documento_collegato": {
                "quietanza_id": quietanza_id,
                "protocollo_quietanza": d.get("protocollo_quietanza"),
                "quietanza_fonte": fonte,
                # Il file vero, mai la scheda JSON: per le quietanze in
                # `quietanze_f24` il PDF lo serve lo stesso lettore dell'F24.
                "quietanza_url": (
                    f"/api/fiscal/documents/{quietanza_id}/content"
                    if fonte == "fiscal_documents"
                    else f"/api/f24-public/pdf/{quietanza_id}"
                    if fonte == "quietanze_f24" else None
                ),
                "f24_pdf_url": f"/api/f24-public/pdf/{d.get('id')}" if d.get("id") else None,
                "movimento_bancario_id": movimenti_banca[0] if movimenti_banca else None,
                "movimenti_bancari_ids": movimenti_banca,
                "pagamento_verificato_banca": bool(d.get("pagamento_verificato_banca")),
                "data_pagamento_effettivo": d.get("data_pagamento_effettivo"),
            },
            "possibile_duplicazione": dup,
            "ravvedimento": {
                "f24_ravvedimento_id": ravv.get("f24_ravvedimento_id"),
                "f24_ravvedimento_pdf_url": (
                    f"/api/f24-public/pdf/{ravv['f24_ravvedimento_id']}" if ravv.get("f24_ravvedimento_id") else None),
                "quietanza_ids": ravv.get("quietanza_ids") or [],
                "quietanza_pdf_url": (
                    f"/api/f24-public/pdf/{ravv['quietanza_ids'][0]}" if ravv.get("quietanza_ids") else None),
                "importo_ravvedimento": ravv.get("importo_ravvedimento"),
                "data_pagamento": ravv.get("data_pagamento"),
            } if ravv.get("stato") == "RAVVEDUTO" else None,
            "etichetta": d.get("etichetta"),
            "ravvedimento_di": [
                {"f24_id": oid, "pdf_url": f"/api/f24-public/pdf/{oid}"} for oid in d.get("ravvedimento_di") or []
            ],
            "saldo_finale": a["saldo_finale"],
            "motivazione": "; ".join(motivi) or "versamento ordinario",
        })

    # Più recenti in alto (periodo MM/YYYY → ordinabile come YYYYMM)
    def _chiave(r):
        p = r["periodo_competenza"] or "00/0000"
        mese, anno_p = p.split("/")
        return (anno_p, mese)

    righe.sort(key=_chiave, reverse=True)
    return {"totale": len(righe), "anno": anno, "righe": righe}


@router.get("/{f24_id}")
async def analisi_f24(f24_id: str) -> Dict[str, Any]:
    """Analisi completa: righe classificate (natura/ente/deducibilità),
    totali per natura, periodo prevalente, scadenza naturale, giorni di
    ritardo, stato pagamento e tipo versamento."""
    db = Database.get_db()
    f24 = await _trova_f24(db, f24_id)
    if not f24:
        raise HTTPException(status_code=404, detail="F24 non trovato")
    analisi = te.classifica_f24(f24)
    return {"f24_id": f24_id, "collezione": f24.pop("_collezione", None),
            "file": f24.get("file_name") or f24.get("filename"), **analisi}


@router.get("/{f24_id}/associazione")
async def associazione_cedolini(
    f24_id: str,
    mese: int = Query(..., ge=1, le=12),
    anno: int = Query(..., ge=2000, le=2100),
) -> Dict[str, Any]:
    """Esito e motivazione leggibile dell'associazione F24 ↔ cedolini di
    un mese (§15): periodo, causali, regolarizzazioni, date."""
    db = Database.get_db()
    f24 = await _trova_f24(db, f24_id)
    if not f24:
        raise HTTPException(status_code=404, detail="F24 non trovato")
    esito = te.valuta_associazione_cedolini(f24, mese, anno)
    return {"f24_id": f24_id, **esito}
