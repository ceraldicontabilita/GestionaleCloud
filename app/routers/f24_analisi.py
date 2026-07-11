"""
Analisi F24 — classificazione normativa, scadenze/ravvedimenti,
associazione ai cedolini e doppi pagamenti.

Espone via API il motore unico app/engines/tributi_engine.py
(specifica: memoria/SPECIFICA_F24_CEDOLINI_IRES_IRAP_CHAT.md).

Endpoint (montati sotto /api/f24-analisi):
  GET /{f24_id}                     → analisi completa del modello (§11+§20)
  GET /{f24_id}/associazione        → esito §15 verso i cedolini di mese/anno
  GET /doppi-pagamenti              → scansione coppie DM10↔RC01 pagate (§21+§23)
"""
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

from app.database import Database
from app.engines import tributi_engine as te

logger = logging.getLogger(__name__)
router = APIRouter()

# Gli F24 vivono in due collezioni per storia: f24_commercialista (flusso
# riconciliazione/quietanze) e f24_unificato (archivio). Il lookup le prova
# entrambe — il motore lavora sul documento, non sulla collezione.
_COLLEZIONI_F24 = ("f24_commercialista", "f24_unificato")


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
    entrambi i pagamenti risultanti: POSSIBILE DOPPIO PAGAMENTO (§23)."""
    db = Database.get_db()
    ordinari, regolarizzazioni = [], []
    for coll in _COLLEZIONI_F24:
        docs = await db[coll].find({}, {"_id": 0, "pdf_data": 0}).to_list(2000)
        for d in docs:
            causali = te.causali_inps(d)
            if "RC01" in causali:
                regolarizzazioni.append(d)
            elif causali or d.get("sezione_erario"):
                ordinari.append(d)

    anomalie = []
    for rc in regolarizzazioni:
        periodo_rc = te.periodo_prevalente(rc)
        for ordinario in ordinari:
            if te.periodo_prevalente(ordinario) != periodo_rc:
                continue  # il confronto completo è costoso: pre-filtro sul periodo
            esito = te.rileva_doppio_pagamento(ordinario, rc)
            if esito.get("possibile_doppio_pagamento"):
                anomalie.append({
                    "f24_ordinario_id": ordinario.get("id"),
                    "f24_ordinario_file": ordinario.get("file_name") or ordinario.get("filename"),
                    "f24_rc01_id": rc.get("id"),
                    "f24_rc01_file": rc.get("file_name") or rc.get("filename"),
                    "periodo": esito["dettaglio"]["controlli"][1]["rc01"],
                    "quota_potenzialmente_duplicata": esito["quota_potenzialmente_duplicata"],
                    "quota_sanzioni_interessi": esito["quota_sanzioni_interessi"],
                    "messaggio": esito["messaggio"],
                    "stato": esito["stato"],
                })
    return {
        "esaminati_ordinari": len(ordinari),
        "esaminati_rc01": len(regolarizzazioni),
        "possibili_doppi_pagamenti": len(anomalie),
        "anomalie": anomalie,
        "stati_possibili": list(te.STATI_ANOMALIA_DOPPIO_PAGAMENTO),
    }


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

    righe = []
    for i in indici:
        a = analisi[i]
        d = docs[i]
        dup = duplicazione.get(i, "no")
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
            "stato_pagamento": a["stato"],
            "tipo_versamento": a["tipo_versamento"],
            "causali_inps": a["causali_inps"],
            "documento_collegato": {
                "quietanza_id": d.get("quietanza_id"),
                "protocollo_quietanza": d.get("protocollo_quietanza"),
            },
            "possibile_duplicazione": dup,
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
