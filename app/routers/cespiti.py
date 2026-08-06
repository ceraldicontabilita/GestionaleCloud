"""
Router Cespiti - Gestione Beni Ammortizzabili
Anagrafica cespiti, calcolo ammortamenti, dismissioni
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from typing import Dict, Any, List, Optional, Literal
from datetime import date, datetime, timezone
from uuid import uuid4
import hashlib
import logging

from app.database import Database
from app.utils.error_handler import handle_errors

router = APIRouter()
logger = logging.getLogger(__name__)

# ============================================
# COEFFICIENTI AMMORTAMENTO FISCALI
# DM 31/12/1988 - Settore Ristorazione
# ============================================

CATEGORIE_CESPITI = {
    "fabbricati": {
        "descrizione": "Fabbricati",
        "coefficiente": 3,
        "vita_utile": 33
    },
    "impianti_generici": {
        "descrizione": "Impianti generici (elettrico, idraulico)",
        "coefficiente": 8,
        "vita_utile": 13
    },
    "impianti_cucina": {
        "descrizione": "Impianti specifici cucina",
        "coefficiente": 12,
        "vita_utile": 8
    },
    "attrezzature": {
        "descrizione": "Attrezzature (piccola attrezzatura)",
        "coefficiente": 25,
        "vita_utile": 4
    },
    "mobili_arredi": {
        "descrizione": "Mobili e arredi",
        "coefficiente": 10,
        "vita_utile": 10
    },
    "automezzi": {
        "descrizione": "Autoveicoli da trasporto",
        "coefficiente": 20,
        "vita_utile": 5
    },
    "autovetture": {
        "descrizione": "Autovetture e motoveicoli",
        "coefficiente": 25,
        "vita_utile": 4
    },
    "macchine_ufficio": {
        "descrizione": "Macchine ufficio elettroniche",
        "coefficiente": 20,
        "vita_utile": 5
    },
    "software": {
        "descrizione": "Software / diritti di utilizzazione",
        "coefficiente": 33.33,
        "vita_utile": 3,
        "bene_immateriale": True,
    },
    "frigoriferi": {
        "descrizione": "Frigoriferi e congelatori",
        "coefficiente": 12,
        "vita_utile": 8
    },
    "forni": {
        "descrizione": "Forni e piastre",
        "coefficiente": 12,
        "vita_utile": 8
    }
}

FONTI_AMMORTAMENTO = {
    "beni_materiali": "DM 31/12/1988, Gruppo XIX; DPR 917/1986, art. 102",
    "beni_immateriali": "DPR 917/1986, art. 103",
    "url_dm": (
        "https://www.gazzettaufficiale.it/atto/serie_generale/caricaArticolo?"
        "art.codiceRedazionale=088A0017&art.dataPubblicazioneGazzetta=1989-02-02&"
        "art.flagTipoArticolo=19&art.idArticolo=1&art.idGruppo=0&"
        "art.idSottoArticolo=1&art.idSottoArticolo1=10&art.progressivo=0&art.versione=1"
    ),
}


# ============================================
# MODELLI
# ============================================

class CespiteInput(BaseModel):
    descrizione: str
    categoria: str  # chiave di CATEGORIE_CESPITI
    data_acquisto: str  # YYYY-MM-DD
    # L'art. 102 TUIR fa decorrere l'ammortamento dall'entrata in funzione,
    # non dalla sola data fattura. Per gli inserimenti manuali la prova deve
    # quindi essere dichiarata esplicitamente; l'estrazione automatica dalle
    # fatture lascia invece il campo da verificare.
    data_entrata_funzione: str  # YYYY-MM-DD
    valore_acquisto: float = Field(gt=0)
    fornitore: Optional[str] = None
    numero_fattura: Optional[str] = None
    ubicazione: Optional[str] = None
    note: Optional[str] = None

    @field_validator("data_acquisto", "data_entrata_funzione")
    @classmethod
    def valida_data_iso(cls, value: str) -> str:
        try:
            date.fromisoformat(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("Data non valida: usare YYYY-MM-DD") from exc
        return value


class DismissioneInput(BaseModel):
    cespite_id: str
    data_dismissione: str  # YYYY-MM-DD
    tipo: Literal["vendita", "eliminazione", "permuta"]
    prezzo_vendita: Optional[float] = Field(default=0, ge=0)
    note: Optional[str] = None

    @field_validator("data_dismissione")
    @classmethod
    def valida_data_dismissione(cls, value: str) -> str:
        try:
            date.fromisoformat(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("Data dismissione non valida: usare YYYY-MM-DD") from exc
        return value


def _today() -> date:
    """Punto unico e testabile per la data operativa corrente."""
    return datetime.now(timezone.utc).date()


def _source_key_fattura(
    fattura_id: str,
    descrizione: str,
    prezzo: float,
    occorrenza: int,
) -> str:
    """Identita stabile fattura-riga per deduplicare senza confondere due
    acquisti distinti dello stesso bene allo stesso prezzo.

    L'occorrenza distingue due righe identiche nella stessa fattura; la chiave
    non contiene dati leggibili del documento ed e sicura per un indice unico.
    """
    normalized = " ".join(descrizione.casefold().split())
    raw = f"{fattura_id}|{normalized}|{round(float(prezzo), 2):.2f}|{occorrenza}"
    return "fattura_riga:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ============================================
# ENDPOINT
# ============================================

@router.get("/categorie")
@handle_errors
async def get_categorie_cespiti() -> Dict[str, Any]:
    """Restituisce le categorie disponibili con coefficienti."""
    return {
        "fonti_normative": FONTI_AMMORTAMENTO,
        "categorie": [
            {
                "codice": k,
                "descrizione": v["descrizione"],
                "coefficiente": v["coefficiente"],
                "vita_utile_anni": v["vita_utile"],
                "bene_immateriale": bool(v.get("bene_immateriale")),
            }
            for k, v in CATEGORIE_CESPITI.items()
        ]
    }


@router.post("/")
@handle_errors
async def crea_cespite(cespite: CespiteInput) -> Dict[str, Any]:
    """Registra un nuovo cespite ammortizzabile."""
    db = Database.get_db()
    
    if cespite.categoria not in CATEGORIE_CESPITI:
        raise HTTPException(
            status_code=400, 
            detail=f"Categoria non valida. Categorie disponibili: {list(CATEGORIE_CESPITI.keys())}"
        )
    
    cat_info = CATEGORIE_CESPITI[cespite.categoria]
    coeff = cat_info["coefficiente"]
    
    # Anno di acquisto
    anno_acquisto = int(cespite.data_acquisto[:4])
    data_entrata_funzione = date.fromisoformat(cespite.data_entrata_funzione)
    if data_entrata_funzione < date.fromisoformat(cespite.data_acquisto):
        raise HTTPException(
            status_code=400,
            detail="L'entrata in funzione non puo precedere la data di acquisto",
        )
    
    nuovo_cespite = {
        "id": str(uuid4()),
        "descrizione": cespite.descrizione,
        "categoria": cespite.categoria,
        "categoria_descrizione": cat_info["descrizione"],
        "coefficiente_ammortamento": coeff,
        "vita_utile_anni": cat_info["vita_utile"],
        "data_acquisto": cespite.data_acquisto,
        "anno_acquisto": anno_acquisto,
        "data_entrata_funzione": cespite.data_entrata_funzione,
        "anno_entrata_funzione": data_entrata_funzione.year,
        "provenienza_entrata_funzione": "conferma_manuale",
        "valore_acquisto": cespite.valore_acquisto,
        "valore_residuo": cespite.valore_acquisto,
        "fondo_ammortamento": 0,
        "fornitore": cespite.fornitore,
        "numero_fattura": cespite.numero_fattura,
        "ubicazione": cespite.ubicazione,
        "note": cespite.note,
        "stato": "attivo",
        "ammortamento_completato": False,
        "piano_ammortamento": [],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db["cespiti"].insert_one(nuovo_cespite.copy())
    from app.services.audit_logger import log_evento
    await log_evento(
        modulo="cespiti",
        azione="creato",
        entita_id=nuovo_cespite["id"],
        entita_collection="cespiti",
        db=db,
        nuovo_stato={
            "categoria": nuovo_cespite["categoria"],
            "valore_acquisto": nuovo_cespite["valore_acquisto"],
            "data_entrata_funzione": nuovo_cespite["data_entrata_funzione"],
        },
        fonte="pagina_cespiti",
        dettaglio="Cespite inserito manualmente con entrata in funzione confermata",
    )
    
    return {
        "success": True,
        "cespite_id": nuovo_cespite["id"],
        "messaggio": f"Cespite '{cespite.descrizione}' registrato",
        "dettaglio": {
            "valore": cespite.valore_acquisto,
            "coefficiente": coeff,
            "quota_annua_ordinaria": round(cespite.valore_acquisto * coeff / 100, 2),
            "quota_primo_anno": round(
                cespite.valore_acquisto * coeff / (100 if cat_info.get("bene_immateriale") else 200),
                2,
            ),
            "anni_ammortamento_stimati": cat_info["vita_utile"]
        }
    }


@router.get("/")
@handle_errors
async def lista_cespiti(
    attivi: bool = Query(True, description="Solo cespiti attivi"),
    categoria: str = Query(None, description="Filtra per categoria")
) -> List[Dict[str, Any]]:
    """Lista cespiti con stato ammortamento."""
    db = Database.get_db()
    
    query = {}
    if attivi:
        query["stato"] = "attivo"
    if categoria:
        query["categoria"] = categoria
    
    cespiti = await db["cespiti"].find(query, {"_id": 0}).sort("data_acquisto", -1).to_list(1000)
    
    return cespiti


@router.get("/riepilogo")
@handle_errors
async def get_riepilogo_cespiti() -> Dict[str, Any]:
    """Riepilogo totale cespiti per categoria."""
    db = Database.get_db()
    
    # Aggregazione per categoria
    pipeline = [
        {"$match": {"stato": "attivo"}},
        {"$group": {
            "_id": "$categoria",
            "num_cespiti": {"$sum": 1},
            "valore_acquisto_totale": {"$sum": "$valore_acquisto"},
            "fondo_ammortamento_totale": {"$sum": "$fondo_ammortamento"},
            "valore_residuo_totale": {"$sum": "$valore_residuo"}
        }},
        {"$sort": {"valore_acquisto_totale": -1}}
    ]
    
    per_categoria = await db["cespiti"].aggregate(pipeline).to_list(100)
    
    # Totali generali
    totale_valore = sum(c["valore_acquisto_totale"] for c in per_categoria)
    totale_fondo = sum(c["fondo_ammortamento_totale"] for c in per_categoria)
    totale_residuo = sum(c["valore_residuo_totale"] for c in per_categoria)
    totale_cespiti = sum(c["num_cespiti"] for c in per_categoria)
    da_verificare = await db["cespiti"].count_documents({
        "stato": "attivo",
        "$or": [
            {"data_entrata_funzione": {"$exists": False}},
            {"data_entrata_funzione": None},
            {"data_entrata_funzione": ""},
        ],
    })
    
    # Arricchisci con info categoria
    for cat in per_categoria:
        cat_code = cat["_id"]
        if cat_code in CATEGORIE_CESPITI:
            cat["descrizione"] = CATEGORIE_CESPITI[cat_code]["descrizione"]
            cat["coefficiente"] = CATEGORIE_CESPITI[cat_code]["coefficiente"]
        cat["valore_acquisto_totale"] = round(cat["valore_acquisto_totale"], 2)
        cat["fondo_ammortamento_totale"] = round(cat["fondo_ammortamento_totale"], 2)
        cat["valore_residuo_totale"] = round(cat["valore_residuo_totale"], 2)
    
    return {
        "totali": {
            "num_cespiti": totale_cespiti,
            "valore_acquisto": round(totale_valore, 2),
            "fondo_ammortamento": round(totale_fondo, 2),
            "valore_netto_contabile": round(totale_residuo, 2),
            "percentuale_ammortizzata": round(totale_fondo / totale_valore * 100, 1) if totale_valore > 0 else 0,
            "entrata_funzione_da_verificare": da_verificare,
        },
        "per_categoria": per_categoria
    }


@router.get("/calcolo/{anno}")
@handle_errors
async def calcola_ammortamenti_anno(anno: int) -> Dict[str, Any]:
    """
    Calcola ammortamenti per tutti i cespiti attivi per l'anno.
    NON registra, solo preview.
    """
    db = Database.get_db()
    
    cespiti = await db["cespiti"].find(
        {"stato": "attivo", "ammortamento_completato": False},
        {"_id": 0}
    ).to_list(1000)
    
    ammortamenti = []
    da_verificare = []
    totale = 0
    
    for cespite in cespiti:
        valore = cespite["valore_acquisto"]
        coeff_memorizzato = float(cespite["coefficiente_ammortamento"])
        regola_categoria = CATEGORIE_CESPITI.get(cespite.get("categoria"), {})
        coeff_massimo = float(regola_categoria.get("coefficiente", coeff_memorizzato))
        coeff = min(coeff_memorizzato, coeff_massimo)
        fondo = cespite.get("fondo_ammortamento", 0)
        data_entrata_funzione = cespite.get("data_entrata_funzione")
        if not data_entrata_funzione:
            da_verificare.append({
                "cespite_id": cespite.get("id"),
                "descrizione": cespite.get("descrizione"),
                "motivo": "data_entrata_funzione_mancante",
            })
            continue
        try:
            anno_entrata_funzione = date.fromisoformat(str(data_entrata_funzione)[:10]).year
        except ValueError:
            da_verificare.append({
                "cespite_id": cespite.get("id"),
                "descrizione": cespite.get("descrizione"),
                "motivo": "data_entrata_funzione_non_valida",
            })
            continue
        if anno_entrata_funzione > anno:
            continue
        
        # Verifica se già ammortizzato per quest'anno
        piano = cespite.get("piano_ammortamento", [])
        gia_ammortizzato = any(p.get("anno") == anno for p in piano)
        
        if gia_ammortizzato:
            continue
        
        # Quota ordinaria
        quota_ordinaria = valore * coeff / 100
        
        # Primo anno: dimezzata (prassi fiscale)
        primo_anno = anno == anno_entrata_funzione
        if primo_anno and not regola_categoria.get("bene_immateriale"):
            quota = quota_ordinaria / 2
        else:
            quota = quota_ordinaria
        
        # Non superare valore residuo
        valore_residuo = valore - fondo
        quota = min(quota, valore_residuo)
        
        if quota > 0:
            ammortamenti.append({
                "cespite_id": cespite["id"],
                "descrizione": cespite["descrizione"],
                "categoria": cespite["categoria"],
                "valore_acquisto": valore,
                "fondo_precedente": round(fondo, 2),
                "quota_anno": round(quota, 2),
                "nuovo_fondo": round(fondo + quota, 2),
                "nuovo_residuo": round(valore_residuo - quota, 2),
                "completato": (valore_residuo - quota) <= 0.01,
                "primo_anno": primo_anno,
                "data_entrata_funzione": data_entrata_funzione,
                "coefficiente_applicato": coeff,
                "coefficiente_memorizzato": coeff_memorizzato,
                "coefficiente_massimo_fiscale": coeff_massimo,
            })
            totale += quota
    
    return {
        "anno": anno,
        "preview": True,
        "ammortamenti": ammortamenti,
        "totale_ammortamenti": round(totale, 2),
        "num_cespiti": len(ammortamenti),
        "da_verificare": da_verificare,
        "num_da_verificare": len(da_verificare),
        "fonte_normativa": "DPR 917/1986, artt. 102-103; DM 31/12/1988, Gruppo XIX",
    }


@router.get("/calcolo-rateo/{anno}/{mese}")
@handle_errors
async def calcola_rateo_ammortamenti(anno: int, mese: int) -> Dict[str, Any]:
    """
    Ammortamenti a rateo mensile per un bilancio provvisorio (infra-annuale).

    Rateo lineare da inizio anno: quota_mese = quota annuale ordinaria / 12
    (la stessa quota, primo anno dimezzato incluso, di calcola_ammortamenti_anno);
    il rateo al mese richiesto è quota_mese moltiplicata per i mesi trascorsi
    dall'inizio dell'anno. Solo preview, NON registra nulla: i cespiti sono
    ammortizzati definitivamente solo da POST /registra/{anno}, a fine anno.
    """
    if mese < 1 or mese > 12:
        raise HTTPException(status_code=400, detail="Mese non valido (1-12)")

    db = Database.get_db()

    cespiti = await db["cespiti"].find(
        {"stato": "attivo", "ammortamento_completato": False},
        {"_id": 0}
    ).to_list(1000)

    rateo_cespiti = []
    da_verificare = []
    totale = 0

    for cespite in cespiti:
        data_entrata_funzione = cespite.get("data_entrata_funzione")
        if not data_entrata_funzione:
            da_verificare.append({
                "cespite_id": cespite.get("id"),
                "motivo": "data_entrata_funzione_mancante",
            })
            continue
        try:
            anno_entrata_funzione = date.fromisoformat(str(data_entrata_funzione)[:10]).year
        except ValueError:
            da_verificare.append({
                "cespite_id": cespite.get("id"),
                "motivo": "data_entrata_funzione_non_valida",
            })
            continue
        if anno_entrata_funzione > anno:
            continue

        valore = cespite["valore_acquisto"]
        coeff_memorizzato = float(cespite["coefficiente_ammortamento"])
        regola_categoria = CATEGORIE_CESPITI.get(cespite.get("categoria"), {})
        coeff_massimo = float(regola_categoria.get("coefficiente", coeff_memorizzato))
        coeff = min(coeff_memorizzato, coeff_massimo)
        fondo = cespite.get("fondo_ammortamento", 0)
        valore_residuo = valore - fondo

        piano = cespite.get("piano_ammortamento", [])
        if any(p.get("anno") == anno for p in piano):
            continue  # già ammortizzato definitivamente per questo anno

        quota_ordinaria = valore * coeff / 100
        primo_anno = anno_entrata_funzione == anno
        quota_annua = (
            quota_ordinaria / 2
            if primo_anno and not regola_categoria.get("bene_immateriale")
            else quota_ordinaria
        )
        quota_mensile = quota_annua / 12
        rateo = min(quota_mensile * mese, valore_residuo)

        if rateo > 0:
            rateo_cespiti.append({
                "cespite_id": cespite["id"],
                "descrizione": cespite["descrizione"],
                "categoria": cespite["categoria"],
                "quota_annua_ordinaria": round(quota_annua, 2),
                "quota_mensile": round(quota_mensile, 2),
                "mesi_rateo": mese,
                "rateo_al_mese": round(rateo, 2),
            })
            totale += rateo

    return {
        "anno": anno,
        "mese": mese,
        "preview": True,
        "rateo_lineare_da_inizio_anno": True,
        "cespiti": rateo_cespiti,
        "totale_rateo": round(totale, 2),
        "num_cespiti": len(rateo_cespiti),
        "da_verificare": da_verificare,
        "num_da_verificare": len(da_verificare),
    }


@router.get("/verifica/{anno}")
@handle_errors
async def verifica_coerenza_ammortamenti(anno: int) -> Dict[str, Any]:
    """Controllo read-only tra registro cespiti e scrittura annuale.

    Non corregge e non completa nulla: mette in evidenza beni senza prova
    dell'entrata in funzione, quote registrate e possibili duplicazioni della
    scrittura riepilogativa.
    """
    db = Database.get_db()
    cespiti = await db["cespiti"].find(
        {"stato": "attivo"},
        {
            "_id": 0,
            "id": 1,
            "categoria": 1,
            "coefficiente_ammortamento": 1,
            "data_entrata_funzione": 1,
            "piano_ammortamento": 1,
        },
    ).to_list(5000)
    movimenti = await db["movimenti_contabili"].find(
        {"tipo": "ammortamento", "anno": anno},
        {"_id": 0, "id": 1, "importo": 1},
    ).to_list(100)

    senza_entrata_funzione = 0
    coefficienti_oltre_massimo = 0
    coefficienti_oltre_massimo_con_quote = 0
    quote_registrate = []
    id_ammortizzati = set()
    for cespite in cespiti:
        if not cespite.get("data_entrata_funzione"):
            senza_entrata_funzione += 1
        regola = CATEGORIE_CESPITI.get(cespite.get("categoria"), {})
        massimo = regola.get("coefficiente")
        memorizzato = float(cespite.get("coefficiente_ammortamento") or 0)
        oltre_massimo = massimo is not None and memorizzato > float(massimo) + 0.001
        if oltre_massimo:
            coefficienti_oltre_massimo += 1
        quota_anno = next(
            (q for q in (cespite.get("piano_ammortamento") or []) if q.get("anno") == anno),
            None,
        )
        if quota_anno:
            quote_registrate.append(float(quota_anno.get("quota") or quota_anno.get("quota_anno") or 0))
            id_ammortizzati.add(cespite.get("id"))
            if oltre_massimo:
                coefficienti_oltre_massimo_con_quote += 1

    totale_quote = round(sum(quote_registrate), 2)
    totale_movimenti = round(sum(float(m.get("importo") or 0) for m in movimenti), 2)
    differenza = round(totale_movimenti - totale_quote, 2)
    critiche = []
    avvisi = []
    if len(movimenti) > 1:
        critiche.append("scritture_ammortamento_duplicate")
    if abs(differenza) > 0.01:
        critiche.append("totale_scrittura_diverso_dalle_quote")
    if coefficienti_oltre_massimo_con_quote:
        critiche.append("quote_registrate_con_coefficiente_oltre_massimo")
    elif coefficienti_oltre_massimo:
        avvisi.append("coefficienti_oltre_massimo_da_correggere")
    if senza_entrata_funzione:
        avvisi.append("entrata_in_funzione_da_confermare")

    return {
        "success": True,
        "anno": anno,
        "modalita": "sola_lettura",
        "cespiti_attivi": len(cespiti),
        "cespiti_ammortizzati": len(id_ammortizzati),
        "entrata_funzione_da_verificare": senza_entrata_funzione,
        "coefficienti_oltre_massimo": coefficienti_oltre_massimo,
        "coefficienti_oltre_massimo_con_quote": coefficienti_oltre_massimo_con_quote,
        "scritture_contabili": len(movimenti),
        "totale_quote_registro": totale_quote,
        "totale_movimenti_contabili": totale_movimenti,
        "differenza": differenza,
        "critiche": critiche,
        "avvisi": avvisi,
        "stato": "critico" if critiche else ("da_verificare" if avvisi else "coerente"),
        "scritture_eseguite": 0,
    }


# ============================================
# AUTO-SCAN: Estrai cespiti da righe fatture XML
# (Must be before /{cespite_id} route to avoid catch-all conflict)
# ============================================

KEYWORD_CATEGORY_MAP = [
    (["forno", "piastra cottura"], "forni"),
    (["frigo", "congelator", "abbattitore"], "frigoriferi"),
    (["computer", "stampante", "monitor", "pc ", "notebook", "tablet"], "macchine_ufficio"),
    (["sfogliatric", "planetaria", "impastatric", "pastocrema"], "impianti_cucina"),
    (["lavastoviglie", "lavapiatti", "lavabicchier", "lavaoggetti"], "attrezzature"),
    (["mobile", "arredo", "poltroncin", "sedia", "tavol", "banco", "armadio", "vetrina"], "mobili_arredi"),
    (["impianto", "climatizz", "condizionat"], "impianti_generici"),
]

EXCLUDE_KEYWORDS = [
    "caffe", "caffè", "kimbo", "grani", "capsul", "omaggio", "storno",
    "acconto", "anticip", "consulenz", "compensi", "noleggio",
    "canone", "abbonament", "rifatturaz", "penalita", "sinistro",
    "manutenzione ordinaria", "riparazion", "intervento lavori",
    "wi-fi", "sim ", "telefon", "cover", "custodia"
]


def classify_asset(descrizione: str, prezzo: float):
    desc_lower = descrizione.lower()
    for excl in EXCLUDE_KEYWORDS:
        if excl in desc_lower:
            return None
    for keywords, categoria in KEYWORD_CATEGORY_MAP:
        for kw in keywords:
            if kw in desc_lower:
                return categoria
    if prezzo >= 2000:
        for kw in ["supporto", "cappa", "scaffal", "contenitor"]:
            if kw in desc_lower:
                return "attrezzature"
    return None


@router.post("/scan-fatture")
@handle_errors
async def scan_fatture_per_cespiti(
    soglia_valore: float = Query(200, description="Valore minimo"),
    dry_run: bool = Query(True, description="Preview senza salvare")
) -> Dict[str, Any]:
    """Scansiona righe fatture XML per identificare potenziali cespiti.
    
    Legge da invoices[*].righe[*] (campo nested, dove sono importate le righe XML).
    Fallback: se `righe` è vuoto, usa `invoices.notes`/`description` per il riconoscimento.
    """
    db = Database.get_db()

    # Esistenti (dedup)
    existing = await db["cespiti"].find(
        {},
        {"_id": 0, "source_key": 1, "fattura_id": 1, "descrizione": 1, "valore_acquisto": 1},
    ).to_list(5000)
    existing_source_keys = {c.get("source_key") for c in existing if c.get("source_key")}
    existing_legacy = {
        (
            str(c.get("fattura_id") or ""),
            str(c.get("descrizione") or "")[:200],
            round(float(c.get("valore_acquisto") or 0), 2),
        )
        for c in existing
        if not c.get("source_key") and c.get("fattura_id")
    }

    nuovi_cespiti: List[Dict[str, Any]] = []
    seen = set()

    # Itera le fatture passive non annullate — collezione canonica unica invoices
    # (§5.4: fatture_passive consolidata in invoices).
    processed_total = 0
    for coll_name in ("invoices",):
        if coll_name not in await db.list_collection_names():
            continue
        cursor = db[coll_name].find({
            "entity_status": {"$ne": "deleted"},
            "$or": [
                {"total_amount": {"$gt": soglia_valore}},
                {"importo_totale": {"$gt": soglia_valore}},
            ],
        }, {"_id": 0})

        async for inv in cursor:
            processed_total += 1
            righe = inv.get("righe") or inv.get("linee") or inv.get("lines") or []
            fattura_id = inv.get("id") or inv.get("invoice_key")
            data_fattura = inv.get("invoice_date") or inv.get("data_fattura") or inv.get("data")
            try:
                data_acquisto = date.fromisoformat(str(data_fattura or "")[:10]).isoformat()
            except (TypeError, ValueError):
                # Una data inventata altererebbe decorrenza e bilancio: il
                # documento resta escluso finche la fattura non e corretta.
                continue
            anno_acquisto = int(data_acquisto[:4])
            fornitore = inv.get("supplier_name") or inv.get("cedente_denominazione")
            numero_fattura = inv.get("invoice_number") or inv.get("numero_fattura")

            if not fattura_id:
                continue

            # Se non ci sono righe, usa total_amount come riga unica
            if not righe:
                total = float(inv.get("total_amount") or inv.get("importo_totale") or 0)
                desc = f"{fornitore or 'Fornitore ignoto'} — Fatt. {inv.get('invoice_number') or inv.get('numero_fattura') or ''}".strip(" -")
                righe = [{"descrizione": desc, "prezzo_totale": total}]

            occorrenze = {}
            for riga in righe:
                descrizione = str(riga.get("descrizione") or riga.get("description") or "").strip()
                try:
                    prezzo = float(riga.get("prezzo_totale") or riga.get("importo") or riga.get("price_total") or 0)
                except (TypeError, ValueError):
                    continue
                if not descrizione or prezzo < soglia_valore:
                    continue

                categoria = classify_asset(descrizione, prezzo)
                if not categoria:
                    continue

                signature = (" ".join(descrizione.casefold().split()), round(prezzo, 2))
                occorrenza = occorrenze.get(signature, 0)
                occorrenze[signature] = occorrenza + 1
                source_key = _source_key_fattura(fattura_id, descrizione, prezzo, occorrenza)
                legacy_key = (str(fattura_id), descrizione[:200], round(prezzo, 2))
                if source_key in seen or source_key in existing_source_keys or legacy_key in existing_legacy:
                    continue
                seen.add(source_key)

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
                    "numero_fattura": numero_fattura,
                    "source_key": source_key,
                    "provenienza": "fattura_xml",
                    "data_entrata_funzione": None,
                    "anno_entrata_funzione": None,
                    "provenienza_entrata_funzione": "da_confermare",
                    "note": "Auto-estratto da fattura XML",
                    "stato": "attivo",
                    "ammortamento_completato": False,
                    "piano_ammortamento": [],
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                nuovi_cespiti.append(cespite)

    if dry_run:
        return {
            "preview": True,
            "num_potenziali_cespiti": len(nuovi_cespiti),
            "valore_totale": round(sum(c["valore_acquisto"] for c in nuovi_cespiti), 2),
            "cespiti": [
                {"descrizione": c["descrizione"][:80], "categoria": c["categoria"],
                 "valore_acquisto": c["valore_acquisto"], "fornitore": c.get("fornitore")}
                for c in nuovi_cespiti[:100]
            ],
        }

    creati = 0
    if nuovi_cespiti:
        for cespite in nuovi_cespiti:
            result = await db["cespiti"].update_one(
                {"source_key": cespite["source_key"]},
                {"$setOnInsert": cespite.copy()},
                upsert=True,
            )
            if result.upserted_id is not None:
                creati += 1
        if creati:
            from app.services.audit_logger import log_evento
            await log_evento(
                modulo="cespiti",
                azione="backfill_fatture",
                entita_id=f"scan_{datetime.now(timezone.utc).isoformat()}",
                entita_collection="cespiti",
                db=db,
                nuovo_stato={"cespiti_creati": creati},
                fonte="fatture_xml",
                dettaglio="Backfill cespiti confermato dopo anteprima",
            )

    return {
        "success": True,
        "cespiti_creati": creati,
        "valore_totale": round(sum(c["valore_acquisto"] for c in nuovi_cespiti), 2),
        "messaggio": f"Estratti {creati} cespiti dalle fatture XML; entrata in funzione da confermare",
    }



@router.get("/{cespite_id}")
@handle_errors
async def get_cespite(cespite_id: str) -> Dict[str, Any]:
    """Dettaglio singolo cespite con piano ammortamento."""
    db = Database.get_db()
    
    cespite = await db["cespiti"].find_one(
        {"id": cespite_id},
        {"_id": 0}
    )
    
    if not cespite:
        raise HTTPException(status_code=404, detail="Cespite non trovato")
    
    return cespite


@router.post("/registra/{anno}")
@handle_errors
async def registra_ammortamenti_anno(anno: int, conferma: bool) -> Dict[str, Any]:
    """
    Registra gli ammortamenti calcolati in contabilità.
    Aggiorna i cespiti e crea movimenti contabili.
    """
    if not conferma:
        raise HTTPException(
            status_code=400,
            detail="Conferma esplicita obbligatoria dopo l'anteprima",
        )
    if _today() < date(anno, 12, 31):
        raise HTTPException(
            status_code=409,
            detail=f"La registrazione definitiva {anno} e disponibile dal 31/12/{anno}",
        )

    db = Database.get_db()
    calcolo = await calcola_ammortamenti_anno(anno)
    if calcolo.get("num_da_verificare", 0):
        raise HTTPException(
            status_code=409,
            detail=(
                f"{calcolo['num_da_verificare']} cespiti senza data di entrata in funzione: "
                "confermare le date prima della registrazione"
            ),
        )

    movimento_esistente = await db["movimenti_contabili"].find_one(
        {"tipo": "ammortamento", "anno": anno},
        {"_id": 0},
    )
    if len(calcolo["ammortamenti"]) == 0:
        return {
            "success": True,
            "anno": anno,
            "messaggio": "Nessun ammortamento da registrare",
            "totale_registrato": 0,
            "movimento_id": (movimento_esistente or {}).get("id"),
            "gia_registrato": bool(movimento_esistente),
        }

    pending_ids = {a["cespite_id"] for a in calcolo["ammortamenti"]}
    if movimento_esistente:
        ids_documentati = {
            r.get("cespite_id")
            for r in movimento_esistente.get("dettaglio") or []
            if r.get("cespite_id")
        }
        if not ids_documentati or not pending_ids.issubset(ids_documentati):
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Esiste gia una scrittura di ammortamento {anno}; "
                    "i nuovi cespiti richiedono rettifica controllata, non un secondo movimento"
                ),
            )
        movimento = movimento_esistente
    else:
        # La scrittura riepilogativa viene creata prima delle quote: in caso di
        # interruzione il retry riconosce il suo dettaglio e completa soltanto
        # i cespiti mancanti. Il vecchio ordine poteva aggiornare i beni e poi
        # fallire nella risposta, lasciando uno stato non recuperabile.
        from app.services.registrazione_contabile import (
            registra_scrittura_semplice,
            riga,
            _C_AMMORTAMENTO,
            _C_FONDO_AMMORTAMENTO,
        )
        imp = round(calcolo["totale_ammortamenti"], 2)
        movimento = await registra_scrittura_semplice(
            db,
            movimento={
                "data": f"{anno}-12-31",
                "descrizione": f"Ammortamenti cespiti {anno}",
                "tipo": "ammortamento",
                "importo": imp,
                "anno": anno,
                "num_cespiti": len(calcolo["ammortamenti"]),
                "dettaglio": [
                    {
                        "cespite_id": a["cespite_id"],
                        "descrizione": a["descrizione"],
                        "quota": a["quota_anno"],
                    }
                    for a in calcolo["ammortamenti"]
                ],
            },
            righe=[
                riga(_C_AMMORTAMENTO, dare=imp, descrizione=f"Quote ammortamento {anno}"),
                riga(_C_FONDO_AMMORTAMENTO, avere=imp, descrizione="Accantonamento a fondo"),
            ],
            chiave_naturale={"tipo": "ammortamento", "anno": anno},
        )

    aggiornati = 0
    for amm in calcolo["ammortamenti"]:
        quota_record = {
            "anno": anno,
            "quota": amm["quota_anno"],
            "fondo_dopo": amm["nuovo_fondo"],
            "residuo_dopo": amm["nuovo_residuo"],
            "primo_anno": amm["primo_anno"],
            "data_registrazione": datetime.now(timezone.utc).isoformat()
        }
        
        result = await db["cespiti"].update_one(
            {
                "id": amm["cespite_id"],
                "piano_ammortamento": {"$not": {"$elemMatch": {"anno": anno}}},
            },
            {
                "$set": {
                    "fondo_ammortamento": amm["nuovo_fondo"],
                    "valore_residuo": amm["nuovo_residuo"],
                    "ammortamento_completato": amm["completato"],
                },
                "$push": {"piano_ammortamento": quota_record},
            },
        )
        aggiornati += int(result.modified_count > 0)

    from app.services.audit_logger import log_evento
    await log_evento(
        modulo="cespiti",
        azione="ammortamenti_registrati",
        entita_id=str(movimento["id"]),
        entita_collection="movimenti_contabili",
        db=db,
        nuovo_stato={"anno": anno, "cespiti_aggiornati": aggiornati},
        fonte="chiusura_esercizio",
        dettaglio=f"Registrazione definitiva ammortamenti {anno}",
    )

    # NB: l'ammortamento è un costo NON monetario: registrarlo anche in
    # prima_nota_cassa come "uscita" (come faceva il blocco rimosso qui)
    # abbassava il saldo cassa reale di migliaia di euro mai usciti dalla
    # cassa (bug #9 audit memoria/endpoints/README.md). Resta solo il
    # movimento contabile in movimenti_contabili, che è la sede corretta.

    return {
        "success": True,
        "anno": anno,
        "totale_registrato": calcolo["totale_ammortamenti"],
        "cespiti_ammortizzati": aggiornati,
        "movimento_id": movimento["id"],
        "messaggio": f"Ammortamenti {anno} registrati in contabilità"
    }


@router.post("/dismissione")
@handle_errors
async def dismetti_cespite(input_data: DismissioneInput) -> Dict[str, Any]:
    """
    Dismette un cespite per vendita, eliminazione o permuta.
    Calcola eventuale plus/minusvalenza.
    """
    db = Database.get_db()
    
    cespite = await db["cespiti"].find_one(
        {"id": input_data.cespite_id},
        {"_id": 0}
    )
    
    if not cespite:
        raise HTTPException(status_code=404, detail="Cespite non trovato")
    
    if input_data.data_dismissione < str(cespite.get("data_acquisto") or "")[:10]:
        raise HTTPException(
            status_code=400,
            detail="La dismissione non puo precedere l'acquisto",
        )
    
    valore_residuo = cespite.get("valore_residuo", 0)
    prezzo_vendita = input_data.prezzo_vendita or 0
    
    # Calcola plus/minusvalenza
    if input_data.tipo == "vendita":
        plusminusvalenza = prezzo_vendita - valore_residuo
    else:
        plusminusvalenza = -valore_residuo  # Eliminazione = perdita totale residuo
    
    tipo_risultato = "plusvalenza" if plusminusvalenza > 0 else ("minusvalenza" if plusminusvalenza < 0 else "pareggio")
    dismissione_key = "dismissione:" + hashlib.sha256(
        (
            f"{input_data.cespite_id}|{input_data.data_dismissione}|"
            f"{input_data.tipo}|{round(prezzo_vendita, 2):.2f}"
        ).encode("utf-8")
    ).hexdigest()
    dismissione_esistente = cespite.get("dismissione") or {}
    retry_identico = (
        cespite.get("stato") == "dismesso"
        and dismissione_esistente.get("dismissione_key") == dismissione_key
    )
    if cespite.get("stato") != "attivo" and not retry_identico:
        raise HTTPException(status_code=409, detail="Cespite gia dismesso con dati diversi")
    
    # Aggiorna cespite
    dismissione_record = {
        "data": input_data.data_dismissione,
        "tipo": input_data.tipo,
        "prezzo_vendita": prezzo_vendita,
        "valore_residuo_al_momento": valore_residuo,
        "plusminusvalenza": round(plusminusvalenza, 2),
        "tipo_risultato": tipo_risultato,
        "dismissione_key": dismissione_key,
        "note": input_data.note,
        "data_registrazione": datetime.now(timezone.utc).isoformat()
    }
    
    if not retry_identico:
        await db["cespiti"].update_one(
            {"id": input_data.cespite_id, "stato": "attivo"},
            {
                "$set": {
                    "stato": "dismesso",
                    "dismissione": dismissione_record
                }
            }
        )
    
    # Registra movimento contabile
    descrizione_mov = f"Dismissione cespite: {cespite['descrizione']}"
    if input_data.tipo == "vendita":
        descrizione_mov += f" - Vendita €{prezzo_vendita}"
    
    movimento = {
        "id": str(uuid4()),
        "data": input_data.data_dismissione,
        "descrizione": descrizione_mov,
        "tipo": f"dismissione_cespite_{tipo_risultato}",
        "importo": abs(plusminusvalenza),
        # Plusvalenza = componente positivo in AVERE; minusvalenza = costo in
        # DARE. Il vecchio codice esponeva il segno al contrario.
        "segno": "avere" if plusminusvalenza > 0 else ("dare" if plusminusvalenza < 0 else None),
        "cespite_id": input_data.cespite_id,
        "dettaglio": dismissione_record,
        "dismissione_key": dismissione_key,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    movimento_esistente = await db["movimenti_contabili"].find_one(
        {"dismissione_key": dismissione_key},
        {"_id": 0, "id": 1},
    )
    if movimento_esistente:
        movimento["id"] = movimento_esistente["id"]
    else:
        await db["movimenti_contabili"].update_one(
            {"dismissione_key": dismissione_key},
            {"$setOnInsert": movimento.copy()},
            upsert=True,
        )

    # La plus/minusvalenza non e un movimento monetario. L'eventuale incasso
    # deve arrivare dall'estratto conto e venire riconciliato con il documento
    # di vendita: creare qui una riga Cassa/Banca duplicava la prima nota e,
    # inoltre, usava l'importo della plus/minusvalenza invece del corrispettivo.
    if not retry_identico:
        from app.services.audit_logger import log_evento
        await log_evento(
            modulo="cespiti",
            azione="dismesso",
            entita_id=input_data.cespite_id,
            entita_collection="cespiti",
            db=db,
            vecchio_stato={"stato": "attivo", "valore_residuo": valore_residuo},
            nuovo_stato={"stato": "dismesso", "dismissione": dismissione_record},
            fonte="pagina_cespiti",
            dettaglio="Dismissione registrata senza generare movimenti monetari artificiali",
        )
    
    return {
        "success": True,
        "gia_registrato": retry_identico,
        "movimento_id": movimento["id"],
        "messaggio": f"Cespite '{cespite['descrizione']}' dismesso",
        "dettaglio": {
            "valore_residuo": round(valore_residuo, 2),
            "prezzo_vendita": prezzo_vendita,
            "plusminusvalenza": round(plusminusvalenza, 2),
            "tipo_risultato": tipo_risultato
        }
    }


class CespiteUpdate(BaseModel):
    descrizione: Optional[str] = None
    fornitore: Optional[str] = None
    numero_fattura: Optional[str] = None
    ubicazione: Optional[str] = None
    note: Optional[str] = None
    valore_acquisto: Optional[float] = Field(default=None, gt=0)
    data_acquisto: Optional[str] = None
    data_entrata_funzione: Optional[str] = None

    @field_validator("data_acquisto", "data_entrata_funzione")
    @classmethod
    def valida_date_update(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("Data non valida: usare YYYY-MM-DD") from exc
        return value


@router.put("/{cespite_id}")
@handle_errors
async def aggiorna_cespite(cespite_id: str, update_data: CespiteUpdate) -> Dict[str, Any]:
    """
    Aggiorna i dati di un cespite esistente.
    Non permette modifica della categoria o del coefficiente.
    """
    db = Database.get_db()
    
    # Verifica che il cespite esista
    cespite = await db["cespiti"].find_one({"id": cespite_id}, {"_id": 0})
    if not cespite:
        raise HTTPException(status_code=404, detail="Cespite non trovato")
    
    # Prepara i campi da aggiornare
    update_fields = {}
    update_dict = update_data.model_dump(exclude_unset=True)
    
    for key, value in update_dict.items():
        if value is not None:
            update_fields[key] = value

    piano = cespite.get("piano_ammortamento") or []
    campi_contabili = {"valore_acquisto", "data_acquisto"}
    if piano and campi_contabili.intersection(update_fields):
        raise HTTPException(
            status_code=409,
            detail="Valore e data di acquisto non sono modificabili dopo quote registrate; serve una rettifica tracciata",
        )
    
    # Se viene aggiornato il valore acquisto, ricalcola il residuo
    if "valore_acquisto" in update_fields:
        nuovo_valore = update_fields["valore_acquisto"]
        fondo = cespite.get("fondo_ammortamento", 0)
        if nuovo_valore < fondo:
            raise HTTPException(
                status_code=400,
                detail="Il valore di acquisto non puo essere inferiore al fondo ammortamento",
            )
        update_fields["valore_residuo"] = nuovo_valore - fondo
    
    # Se viene aggiornata la data acquisto, aggiorna anche anno
    if "data_acquisto" in update_fields:
        update_fields["anno_acquisto"] = int(update_fields["data_acquisto"][:4])

    if "data_entrata_funzione" in update_fields:
        data_acquisto = update_fields.get("data_acquisto") or cespite.get("data_acquisto")
        if data_acquisto and update_fields["data_entrata_funzione"] < str(data_acquisto)[:10]:
            raise HTTPException(
                status_code=400,
                detail="L'entrata in funzione non puo precedere la data di acquisto",
            )
        anno_funzione = int(update_fields["data_entrata_funzione"][:4])
        anni_registrati = [p.get("anno") for p in piano if isinstance(p.get("anno"), int)]
        if anni_registrati and anno_funzione > min(anni_registrati):
            raise HTTPException(
                status_code=409,
                detail="L'entrata in funzione indicata e successiva a una quota gia registrata",
            )
        update_fields["anno_entrata_funzione"] = anno_funzione
        update_fields["provenienza_entrata_funzione"] = "conferma_manuale"
    
    if not update_fields:
        return {"success": True, "messaggio": "Nessun campo da aggiornare"}
    
    update_fields["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db["cespiti"].update_one(
        {"id": cespite_id},
        {"$set": update_fields}
    )
    from app.services.audit_logger import log_evento
    await log_evento(
        modulo="cespiti",
        azione="aggiornato",
        entita_id=cespite_id,
        entita_collection="cespiti",
        db=db,
        vecchio_stato={k: cespite.get(k) for k in update_fields if k != "updated_at"},
        nuovo_stato={k: v for k, v in update_fields.items() if k != "updated_at"},
        fonte="pagina_cespiti",
        dettaglio="Dati cespite aggiornati con tracciamento",
    )
    
    return {
        "success": True,
        "messaggio": f"Cespite '{cespite['descrizione']}' aggiornato",
        "campi_aggiornati": list(update_fields.keys())
    }


@router.delete("/{cespite_id}")
@handle_errors
async def elimina_cespite(cespite_id: str) -> Dict[str, Any]:
    """
    Archivia un cespite senza cancellare la prova storica.
    Non permette l'eliminazione se ci sono ammortamenti registrati.
    """
    db = Database.get_db()
    
    # Verifica che il cespite esista
    cespite = await db["cespiti"].find_one({"id": cespite_id}, {"_id": 0})
    if not cespite:
        raise HTTPException(status_code=404, detail="Cespite non trovato")
    
    # Verifica che non ci siano ammortamenti registrati
    piano = cespite.get("piano_ammortamento", [])
    if len(piano) > 0:
        raise HTTPException(
            status_code=400, 
            detail=f"Impossibile eliminare: {len(piano)} quote di ammortamento già registrate. Usare la dismissione invece."
        )
    
    now = datetime.now(timezone.utc).isoformat()
    result = await db["cespiti"].update_one(
        {"id": cespite_id, "entity_status": {"$ne": "deleted"}},
        {"$set": {
            "stato": "archiviato",
            "entity_status": "deleted",
            "deleted_at": now,
            "deleted_reason": "archiviazione_manuale",
        }},
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=409, detail="Cespite gia archiviato o non modificabile")

    from app.services.audit_logger import log_evento
    await log_evento(
        modulo="cespiti",
        azione="archiviato",
        entita_id=cespite_id,
        entita_collection="cespiti",
        db=db,
        vecchio_stato={"stato": cespite.get("stato"), "entity_status": cespite.get("entity_status")},
        nuovo_stato={"stato": "archiviato", "entity_status": "deleted", "deleted_at": now},
        fonte="pagina_cespiti",
        dettaglio="Soft-delete: il record resta disponibile per audit e ripristino tecnico",
    )
    
    return {
        "success": True,
        "messaggio": f"Cespite '{cespite['descrizione']}' archiviato",
        "cespite_eliminato": {
            "id": cespite_id,
            "descrizione": cespite["descrizione"],
            "valore_acquisto": cespite.get("valore_acquisto", 0)
        }
    }

# (scan endpoint moved above /{cespite_id} routes)
