"""
RITENUTE D'ACCONTO — richiesta utente 18/07/2026.

"Tra le fatture se trovi RT01 Ritenuta persone fisiche devi crearmi una
sezione ritenute: nella fattura c'è un importo, lo memorizzi e mi ricordi
che è da pagare entro il giorno 16 del mese successivo. La commercialista
invia un F24 con codice tributo 1040: lo trovi e lo associ. Se l'importo è
pagato leggendo l'estratto conto, riconcili con flag pagato alla scadenza;
altrimenti scrivi la data reale di pagamento. Se il pagamento non è
puntuale, guarda se nell'F24 c'è il codice tributo del ravvedimento e
scrivi 'pagato con ravvedimento'."

Flusso: la fattura XML con DatiRitenuta (RT01 persone fisiche / RT02
società) genera una riga in `ritenute_acconto` con scadenza il 16 del mese
successivo alla data fattura. La riconciliazione cerca l'F24 con codice
1040 e stesso importo, ne legge lo stato di pagamento (quietanza/estratto
conto — mai ricostruito, come da SPECIFICA F24) e classifica: puntuale,
con ravvedimento (codici 8906 sanzione + 1989 interessi), in ritardo senza
ravvedimento (alert).
"""
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query

from app.database import Database
from app.utils.error_handler import handle_errors
from app.services.f24_payment_evidence import stato_evidenza_pagamento
from app.services.f24_canonico import normalizza_righe_tributo

logger = logging.getLogger(__name__)
router = APIRouter()

COLLECTION = "ritenute_acconto"

# Ravvedimento operoso per ritenute (fonte: Agenzia delle Entrate,
# risoluzioni sui codici tributo; logica art. 13 D.Lgs. 472/1997):
# la sanzione ridotta e gli interessi legali si versano nello STESSO F24
# del tributo tardivo, con codici dedicati.
CODICI_RAVVEDIMENTO_RITENUTE = {
    "8906": "Sanzione pecuniaria sostituti d'imposta (ravvedimento su ritenute, es. 1040)",
    "8948": "Sanzione ravvedimento ritenute su redditi di lavoro autonomo",
    "1989": "Interessi sul ravvedimento - IRPEF e ritenute",
}
LOGICA_RAVVEDIMENTO = (
    "Ravvedimento operoso (art. 13 D.Lgs. 472/1997): se la ritenuta non è "
    "versata entro il 16 del mese successivo, si può regolarizzare pagando "
    "il tributo (1040) più la sanzione ridotta (codice 8948 per lavoro "
    "autonomo; 8906 nei flussi storici) e gli "
    "interessi legali (codice 1989) nello stesso F24. Sanzione ridotta: "
    "0,083%/giorno fino a 14 giorni (ravvedimento sprint), 1,25% entro 30 "
    "giorni, 1,39% entro 90 giorni, 3,125% entro 1 anno."
)

TIPI_RITENUTA = {"RT01": "Ritenuta persone fisiche", "RT02": "Ritenuta persone giuridiche"}


def _scadenza_16_mese_successivo(data_iso: str) -> str:
    anno, mese = int(data_iso[:4]), int(data_iso[5:7])
    mese += 1
    if mese == 13:
        mese, anno = 1, anno + 1
    return f"{anno}-{mese:02d}-16"


def _isola_body_xml(xml_raw: str, body_index: int) -> str:
    """Isola il testo del body_index-esimo <FatturaElettronicaBody> dentro
    xml_raw. Un file FatturaPA raggruppato condivide lo stesso xml_raw fra
    più fatture (vedi xml_body_index): senza isolare il body giusto, una
    fattura SENZA ritenuta poteva ereditare la <DatiRitenuta> di un'altra
    fattura nello stesso file (bug reale, review Codex PR #71). Stesso
    stile regex tollerante del resto del modulo (NON un parse XML vero:
    xml_raw può derivare da un .p7m "sporco")."""
    # Prefisso di namespace opzionale (es. <p:FatturaElettronicaBody>,
    # <ns2:FatturaElettronicaBody>): xml_raw è il testo ORIGINALE non
    # ripulito (a differenza della copia di lavoro del parser, che invece
    # normalizza via clean_xml_namespaces) — un file con tag prefissati
    # senza questa tolleranza non veniva isolato affatto, facendo
    # ricomparire il bug per l'esatto caso che gli altri percorsi
    # (parser/vista XSLT) già gestiscono (bug reale, review Codex PR #71).
    blocchi = re.findall(
        r"<(?:\w+:)?FatturaElettronicaBody\b.*?</(?:\w+:)?FatturaElettronicaBody\s*>", xml_raw, re.S
    )
    if not blocchi:
        return xml_raw  # formato inatteso/singolo body: comportamento invariato
    if 0 <= body_index < len(blocchi):
        return blocchi[body_index]
    return blocchi[0]


def _estrai_dati_ritenuta(xml_raw, body_index: int = 0) -> Optional[Dict[str, Any]]:
    """Estrae DatiRitenuta dall'XML (regex: regge anche i .p7m sporchi).
    body_index seleziona il body giusto quando xml_raw è condiviso da più
    fatture di un file raggruppato."""
    if not xml_raw:
        return None
    testo = xml_raw if isinstance(xml_raw, str) else str(xml_raw)
    testo = _isola_body_xml(testo, body_index)
    blocco = re.search(r"<DatiRitenuta>(.*?)</DatiRitenuta>", testo, re.S)
    if not blocco:
        return None
    b = blocco.group(1)

    def campo(tag):
        m = re.search(rf"<{tag}>\s*([^<]+?)\s*</{tag}>", b)
        return m.group(1) if m else None

    try:
        importo = float(campo("ImportoRitenuta") or 0)
    except ValueError:
        return None
    if importo <= 0:
        return None
    return {
        "tipo": campo("TipoRitenuta") or "RT01",
        "importo": round(importo, 2),
        "aliquota": campo("AliquotaRitenuta"),
        "causale": campo("CausalePagamento"),
    }


def _tributi_di(f24: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Compatibilità router sulla vista canonica delle righe F24."""
    out = [{
        "indice": row["ordinal"] - 1,
        "sezione": row["section"],
        "codice": row["tax_code"],
        "importo": row["debit_amount"],
        "periodo": row["reference_period"],
    } for row in normalizza_righe_tributo(f24)]
    codici_presenti = {row["codice"] for row in out}
    for c in (f24.get("codici_tributo") or []):
        codice = c.get("codice") if isinstance(c, dict) else c
        codice = str(codice or "").strip()
        if codice and codice not in codici_presenti:
            codici_presenti.add(codice)
            out.append({
                "indice": len(out), "sezione": "codici_tributo",
                "codice": codice, "importo": None, "periodo": None,
            })
    return out


def _data_pagamento_f24(f24: Dict[str, Any]) -> Optional[str]:
    evidenza = stato_evidenza_pagamento(f24)
    data = evidenza.get("data_versamento_documentale") or evidenza.get("data_pagamento")
    return str(data)[:10] if data else None


def _periodo_ritenuta(rit: Dict[str, Any]) -> Optional[str]:
    periodo = str(rit.get("periodo_ritenuta") or "").strip()
    if re.fullmatch(r"\d{4}-\d{2}", periodo):
        return periodo
    data = str(rit.get("data_fattura") or "")[:7]
    return data if re.fullmatch(r"\d{4}-\d{2}", data) else None


def _id_f24(f24: Dict[str, Any]) -> str:
    return str(
        f24.get("id") or f24.get("document_id") or f24.get("sha256")
        or f24.get("filename") or f24.get("file_name") or ""
    )


async def _carica_f24(db) -> List[Dict[str, Any]]:
    return [doc async for doc in db["f24_unificato"].find({}, {"_id": 0})]


async def _riconcilia_ritenuta(
    db,
    rit: Dict[str, Any],
    *,
    ritenute_periodo: Optional[List[Dict[str, Any]]] = None,
    f24_docs: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Associa la riga 1040 corretta, distinguendo F24 e prova bancaria.

    Una riga 1040 può coprire una sola ritenuta oppure la somma delle
    ritenute dello stesso periodo. Gli altri tributi dell'F24 non vengono
    confusi con la quota 1040 e l'addebito bancario resta prova dell'intero
    modello, non della singola ritenuta.
    """
    oggi = datetime.now(timezone.utc).date().isoformat()
    upd: Dict[str, Any] = {
        "f24_id": None,
        "f24_descrizione": None,
        "f24_tributo_indice": None,
        "f24_tributo_sezione": None,
        "f24_periodo": None,
        "f24_importo_tributo": None,
        "f24_associazione_tipo": None,
        "f24_quota_ritenuta": None,
        "f24_multi_tributo": False,
        "stato_evidenza_pagamento": None,
        "movimento_bancario_f24_id": None,
        "data_pagamento": None,
        "f24_candidati": [],
    }
    periodo = _periodo_ritenuta(rit)
    gruppo = [
        r for r in (ritenute_periodo or [rit])
        if _periodo_ritenuta(r) == periodo
    ] if periodo else [rit]
    importo = round(float(rit.get("importo") or 0), 2)
    totale_gruppo = round(sum(float(r.get("importo") or 0) for r in gruppo), 2)
    stesso_importo = sum(
        1 for r in gruppo if abs(float(r.get("importo") or 0) - importo) <= 0.01
    )

    candidati = []
    for f24 in (f24_docs if f24_docs is not None else await _carica_f24(db)):
        for tributo in _tributi_di(f24):
            if tributo["codice"] != "1040" or tributo["importo"] is None:
                continue
            periodo_riga = tributo.get("periodo")
            if periodo and periodo_riga and periodo != periodo_riga:
                continue

            tipo = None
            # Una riga senza periodo può essere usata solo per un importo
            # individuale univoco, mai per un'aggregazione mensile.
            if abs(tributo["importo"] - importo) <= 0.01 and stesso_importo == 1:
                tipo = "singola"
            if (
                len(gruppo) > 1
                and periodo
                and periodo_riga == periodo
                and abs(tributo["importo"] - totale_gruppo) <= 0.01
            ):
                tipo = "aggregata"
            if not tipo:
                continue
            score = 100 + (30 if periodo_riga == periodo and periodo else 0)
            candidati.append({
                "f24": f24,
                "tributo": tributo,
                "tipo": tipo,
                "score": score,
            })

    if not candidati:
        upd["stato"] = "scaduta_da_versare" if oggi > rit["scadenza"] else "da_pagare"
        upd["f24_id"] = None
        return upd

    max_score = max(c["score"] for c in candidati)
    migliori = [c for c in candidati if c["score"] == max_score]
    identita = {
        (_id_f24(c["f24"]), c["tributo"]["indice"], c["tipo"])
        for c in migliori
    }
    if len(identita) != 1:
        upd.update({
            "stato": "da_verificare_associazione_f24",
            "f24_id": None,
            "f24_candidati": sorted({_id_f24(c["f24"]) for c in migliori if _id_f24(c["f24"])}),
        })
        return upd

    scelto = migliori[0]
    f24_match = scelto["f24"]
    tributo_1040 = scelto["tributo"]
    evidenza = stato_evidenza_pagamento(f24_match)
    upd["f24_id"] = _id_f24(f24_match)
    upd["f24_descrizione"] = (f24_match.get("descrizione") or f24_match.get("filename") or "")[:120]
    upd["f24_tributo_indice"] = tributo_1040["indice"]
    upd["f24_tributo_sezione"] = tributo_1040["sezione"]
    upd["f24_periodo"] = tributo_1040.get("periodo")
    upd["f24_importo_tributo"] = tributo_1040["importo"]
    upd["f24_associazione_tipo"] = scelto["tipo"]
    upd["f24_quota_ritenuta"] = importo
    upd["f24_multi_tributo"] = len(_tributi_di(f24_match)) > 1
    upd["stato_evidenza_pagamento"] = evidenza["stato"]
    upd["movimento_bancario_f24_id"] = evidenza.get("movimento_bancario_id")

    if not evidenza["versato_documentalmente"]:
        upd["stato"] = "f24_associato_da_pagare"
        return upd

    data_pag = _data_pagamento_f24(f24_match) or rit["scadenza"]
    upd["data_pagamento"] = data_pag
    if data_pag <= rit["scadenza"]:
        upd["stato"] = "pagata_puntuale"
    else:
        codici = {t["codice"] for t in _tributi_di(f24_match)}
        codici_quietanza = {
            str(codice) for codice in (f24_match.get("codici_ravvedimento") or [])
        }
        if (
            f24_match.get("ravveduto") is True
            or codici & set(CODICI_RAVVEDIMENTO_RITENUTE)
            or codici_quietanza & set(CODICI_RAVVEDIMENTO_RITENUTE)
        ):
            upd["stato"] = "pagata_con_ravvedimento"
        else:
            upd["stato"] = "pagata_in_ritardo_senza_ravvedimento"
    return upd


async def riconcilia_ritenute_esistenti(db) -> Dict[str, Any]:
    """Ricalcola le ritenute gia censite quando cambia la prova F24.

    E' richiamata dall'import canonico delle quietanze: l'utente non deve
    premere manualmente "Aggiorna" per vedere la prova documentale.
    """
    ritenute = await db[COLLECTION].find({}, {"_id": 0}).to_list(10000)
    if not ritenute:
        return {"analizzate": 0, "aggiornate": 0}
    f24_docs = await _carica_f24(db)
    aggiornate = 0
    for rit in ritenute:
        upd = await _riconcilia_ritenuta(
            db, rit, ritenute_periodo=ritenute, f24_docs=f24_docs,
        )
        result = await db[COLLECTION].update_one({"id": rit["id"]}, {"$set": upd})
        aggiornate += int(getattr(result, "modified_count", 0) > 0)
    return {"analizzate": len(ritenute), "aggiornate": aggiornate,
            "f24_analizzati": len(f24_docs)}


@router.post("/scan")
@handle_errors
async def scan_ritenute(anno: int = Query(2026)) -> Dict[str, Any]:
    """Estrae le ritenute dalle fatture XML dell'anno (idempotente per
    fattura) e le riconcilia con gli F24 disponibili."""
    db = Database.get_db()
    fatture = await db["invoices"].find(
        {"invoice_date": {"$regex": f"^{anno}"},
         "status": {"$nin": ["deleted", "archived"]},
         "xml_raw": {"$regex": "DatiRitenuta"}},
        {"_id": 0, "id": 1, "invoice_number": 1, "invoice_date": 1,
         "supplier_name": 1, "supplier_vat": 1, "cedente_piva": 1, "xml_raw": 1,
         "xml_body_index": 1},
    ).to_list(5000)

    nuove = aggiornate = 0
    for f in fatture:
        dati = _estrai_dati_ritenuta(f.get("xml_raw"), f.get("xml_body_index") or 0)
        if not dati:
            continue
        base = {
            "fattura_id": f["id"],
            "numero_fattura": f.get("invoice_number"),
            "data_fattura": (f.get("invoice_date") or "")[:10],
            "fornitore": f.get("supplier_name"),
            "piva": f.get("supplier_vat") or f.get("cedente_piva"),
            "tipo": dati["tipo"],
            "tipo_label": TIPI_RITENUTA.get(dati["tipo"], dati["tipo"]),
            "importo": dati["importo"],
            "aliquota": dati["aliquota"],
            "causale": dati["causale"],
            "periodo_ritenuta": (f.get("invoice_date") or "")[:7],
            "scadenza": _scadenza_16_mese_successivo((f.get("invoice_date") or "")[:10]),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        esistente = await db[COLLECTION].find_one({"fattura_id": f["id"]})
        rit = {**base, "id": esistente["id"] if esistente else str(uuid.uuid4())}
        if esistente:
            await db[COLLECTION].update_one({"id": rit["id"]}, {"$set": rit})
            aggiornate += 1
        else:
            rit["created_at"] = rit["updated_at"]
            await db[COLLECTION].insert_one(dict(rit))
            nuove += 1

    # Seconda fase: dopo aver acquisito tutte le ritenute, una singola riga
    # 1040 dell'F24 può essere riconosciuta come somma del periodo.
    ritenute_anno = await db[COLLECTION].find(
        {"data_fattura": {"$regex": f"^{anno}"}}, {"_id": 0}
    ).to_list(5000)
    f24_docs = await _carica_f24(db)
    for rit in ritenute_anno:
        upd = await _riconcilia_ritenuta(
            db, rit, ritenute_periodo=ritenute_anno, f24_docs=f24_docs
        )
        await db[COLLECTION].update_one({"id": rit["id"]}, {"$set": upd})

    return {"anno": anno, "fatture_con_ritenuta": len(fatture),
            "nuove": nuove, "aggiornate": aggiornate,
            "f24_analizzati": len(f24_docs)}


@router.get("")
@handle_errors
async def lista_ritenute(anno: int = Query(2026)) -> Dict[str, Any]:
    """Sezione Ritenute: elenco con scadenze, F24 associato e stato."""
    db = Database.get_db()
    ritenute = await db[COLLECTION].find(
        {"data_fattura": {"$regex": f"^{anno}"}}, {"_id": 0}
    ).sort("scadenza", -1).to_list(2000)
    oggi = datetime.now(timezone.utc).date().isoformat()
    per_stato: Dict[str, int] = {}
    for r in ritenute:
        # lo stato "da_pagare" scivola in "scaduta" col passare del tempo
        if r.get("stato") == "da_pagare" and oggi > (r.get("scadenza") or "9999"):
            r["stato"] = "scaduta_da_versare"
        per_stato[r.get("stato") or "?"] = per_stato.get(r.get("stato") or "?", 0) + 1
    return {
        "anno": anno,
        "ritenute": ritenute,
        "totale_importo": round(sum(r.get("importo", 0) for r in ritenute), 2),
        "per_stato": per_stato,
        "logica_ravvedimento": LOGICA_RAVVEDIMENTO,
    }


@router.get("/codici-ravvedimento")
@handle_errors
async def codici_ravvedimento() -> Dict[str, Any]:
    """Sezione codici tributo: i codici del ravvedimento e la logica."""
    return {"codici": CODICI_RAVVEDIMENTO_RITENUTE, "logica": LOGICA_RAVVEDIMENTO}
