"""
Router Fornitori Learning - Gestione associazioni fornitore-keywords
Permette di memorizzare e apprendere le categorie dei fornitori
"""
from fastapi import APIRouter, HTTPException, Body
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone
from pydantic import BaseModel, Field
import logging
import re

from app.database import Database

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Fornitori Learning"])

# Collezione Drive/Sheets
COLL_FORNITORI_KEYWORDS = "fornitori_keywords"


class FornitoreKeywordsCreate(BaseModel):
    """Schema per creare/aggiornare associazione fornitore"""
    fornitore_nome: str
    keywords: List[str]
    centro_costo_suggerito: Optional[str] = None
    centri_costo_ammessi: List[str] = Field(default_factory=list)
    note: Optional[str] = None


class FornitoreKeywordsResponse(BaseModel):
    """Schema risposta fornitore"""
    id: str
    fornitore_nome: str
    fornitore_nome_normalizzato: str
    keywords: List[str]
    centro_costo_suggerito: Optional[str]
    centri_costo_ammessi: List[str] = Field(default_factory=list)
    note: Optional[str]
    fatture_count: int
    totale_fatture: float
    created_at: str
    updated_at: str


# MOTORE UNICO: la normalizzazione vive nel servizio (usata anche dal
# classificatore all'import) — qui solo il re-export per compatibilità.
from app.services.learning_machine_cdc import normalizza_nome_fornitore  # noqa: E402


def _nome_da_config(config: Dict[str, Any]) -> str:
    """Nome fornitore da un documento fornitori_keywords, QUALUNQUE schema.

    Nella collection convivono due schemi per storia: i salvataggi della
    pagina Learning ({fornitore_nome, fornitore_nome_normalizzato}) e i
    documenti auto-creati dall'event bus ({ragione_sociale, fornitore_id}).
    L'accesso diretto config["fornitore_nome"] mandava in errore la
    riclassifica appena c'era un documento auto (bug segnalato l'11/07:
    'la riclassifica non funziona')."""
    return (config.get("fornitore_nome") or config.get("ragione_sociale") or "").strip()


@router.get("/stats")
async def get_learning_stats() -> Dict[str, Any]:
    """
    Statistiche complete della Learning Machine.
    """
    db = Database.get_db()

    # Conta i fornitori DAVVERO configurati (con centro di costo scelto o
    # keywords): i documenti auto-creati dall'event bus senza configurazione
    # gonfiavano il contatore "CONFIGURATI" senza classificare nulla.
    fornitori_con_keywords = await db[COLL_FORNITORI_KEYWORDS].count_documents({
        "$or": [
            {"centro_costo_suggerito": {"$nin": [None, ""]}},
            {"keywords.0": {"$exists": True}},
        ]
    })

    # Conta fornitori totali (da fatture)
    fornitori_unici = await db["invoices"].distinct("supplier_name")
    totale_fornitori = len([f for f in fornitori_unici if f])

    # Conta fatture
    totale_fatture = await db["invoices"].count_documents({})
    fatture_classificate = await db["invoices"].count_documents({
        "centro_costo_id": {"$exists": True, "$nin": [None, ""]}
    })

    # Conta F24
    totale_f24 = await db["f24_unificato"].count_documents({})
    f24_classificati = await db["f24_unificato"].count_documents({
        "centro_costo_id": {"$exists": True, "$nin": [None, ""]}
    })

    perc_fatture = round(fatture_classificate / max(totale_fatture, 1) * 100, 1)
    perc_f24 = round(f24_classificati / max(totale_f24, 1) * 100, 1)

    return {
        "fornitori_con_keywords": fornitori_con_keywords,
        "totale_fornitori": totale_fornitori,
        "copertura_fornitori": round(fornitori_con_keywords / max(totale_fornitori, 1) * 100, 1),
        "totale_fatture": totale_fatture,
        "fatture_classificate": fatture_classificate,
        "percentuale_fatture": perc_fatture,
        "totale_f24": totale_f24,
        "f24_classificati": f24_classificati,
        "percentuale_f24": perc_f24
    }


@router.get("/lista")
async def lista_fornitori_keywords() -> Dict[str, Any]:
    """
    Lista tutti i fornitori con keywords configurate
    """
    db = Database.get_db()

    fornitori = await db[COLL_FORNITORI_KEYWORDS].find(
        {}, {"_id": 0}
    ).sort("fatture_count", -1).to_list(5000)

    # Normalizza i DUE schemi presenti in collection: i documenti auto-creati
    # dall'event bus (ragione_sociale) escono con gli stessi campi dei
    # salvataggi della pagina, così il frontend li mostra correttamente.
    for f in fornitori:
        if not f.get("fornitore_nome"):
            f["fornitore_nome"] = f.get("ragione_sociale") or ""
        if not f.get("fornitore_nome_normalizzato"):
            f["fornitore_nome_normalizzato"] = normalizza_nome_fornitore(f["fornitore_nome"])
        f.setdefault("keywords", [])
        f.setdefault("centro_costo_suggerito", None)
        f.setdefault("centri_costo_ammessi", [])
        f.setdefault("modalita_classificazione", "per_contenuto")
        f["configurato"] = bool(f.get("centro_costo_suggerito") or f.get("keywords"))

    return {
        "totale": len(fornitori),
        "fornitori": fornitori
    }


@router.get("/non-classificati")
async def fornitori_non_classificati(limit: int = 50) -> Dict[str, Any]:
    """
    Lista i fornitori in 'Altri costi non classificati' che non hanno keywords configurate.
    Mostra i totali REALI del fornitore (tutte le fatture), non solo quelle non classificate.
    """
    db = Database.get_db()

    # Trova fornitori già configurati
    configurati = await db[COLL_FORNITORI_KEYWORDS].distinct("fornitore_nome_normalizzato")

    # Aggrega fornitori non classificati.
    # NB: una fattura è "da classificare" anche quando NON ha alcun centro
    # di costo (handler mai girato / import vecchio) — prima si contavano
    # solo quelle marcate esplicitamente 'Altri costi non classificati' e
    # il contatore 'DA CLASSIFICARE' risultava bugiardo (2 su centinaia).
    pipeline = [
        {"$match": {
            "$or": [
                {"centro_costo_nome": "Altri costi non classificati"},
                {"centro_costo_id": {"$exists": False}},
                {"centro_costo_id": None},
                {"centro_costo_id": ""},
            ],
            "supplier_name": {"$nin": [None, ""]}
        }},
        {"$group": {
            "_id": "$supplier_name",
            "count_non_class": {"$sum": 1},
            "esempio_linee": {"$first": "$linee"}
        }},
        {"$sort": {"count_non_class": -1}},
        {"$limit": limit}
    ]

    fornitori_raw = await db["invoices"].aggregate(pipeline).to_list(limit)

    # Per ogni fornitore, calcola i totali REALI (tutte le fatture)
    fornitori = []
    for f in fornitori_raw:
        nome_norm = normalizza_nome_fornitore(f["_id"])
        if nome_norm not in configurati:
            # Calcola totali REALI (tutte le fatture del fornitore)
            totali = await db["invoices"].aggregate([
                {"$match": {"supplier_name": f["_id"]}},
                {"$group": {
                    "_id": None,
                    "count": {"$sum": 1},
                    "totale": {"$sum": "$total_amount"}
                }}
            ]).to_list(1)

            count_reale = totali[0]["count"] if totali else f["count_non_class"]
            totale_reale = totali[0]["totale"] if totali else 0

            # Estrai prime descrizioni linee per aiutare l'utente
            descrizioni = []
            if f.get("esempio_linee"):
                for linea in f["esempio_linee"][:3]:
                    if isinstance(linea, dict):
                        desc = linea.get("descrizione") or linea.get("description", "")
                        if desc:
                            descrizioni.append(desc[:100])

            fornitori.append({
                "fornitore_nome": f["_id"],
                "fornitore_nome_normalizzato": nome_norm,
                "fatture_count": count_reale,  # Totale REALE
                "fatture_non_classificate": f["count_non_class"],
                "totale_fatture": round(totale_reale, 2),  # Totale REALE
                "esempio_descrizioni": descrizioni
            })

    # Ordina per numero fatture reali
    fornitori.sort(key=lambda x: x["fatture_count"], reverse=True)

    return {
        "totale": len(fornitori),
        "fornitori": fornitori
    }


@router.post("/salva")
async def salva_fornitore_keywords(data: FornitoreKeywordsCreate) -> Dict[str, Any]:
    """
    Salva o aggiorna le keywords associate a un fornitore.
    Questo permette alla Learning Machine di classificare correttamente le fatture future.
    """
    db = Database.get_db()

    nome_norm = normalizza_nome_fornitore(data.fornitore_nome)

    # Conta fatture per questo fornitore (re.escape: i nomi con punti,
    # parentesi o '+' rompevano la regex e il salvataggio falliva)
    import re as _re
    nome_regex = _re.escape(data.fornitore_nome)
    fatture_count = await db["invoices"].count_documents({
        "supplier_name": {"$regex": nome_regex, "$options": "i"}
    })
    totale = 0
    pipeline = [
        {"$match": {"supplier_name": {"$regex": nome_regex, "$options": "i"}}},
        {"$group": {"_id": None, "tot": {"$sum": "$total_amount"}}}
    ]
    agg = await db["invoices"].aggregate(pipeline).to_list(1)
    if agg:
        totale = agg[0].get("tot", 0)

    # Un fornitore non identifica una categoria: grossisti e marketplace
    # vendono normalmente prodotti molto diversi. Le nuove configurazioni
    # lavorano quindi per contenuto della singola fattura.
    from app.services.learning_machine_cdc import FORNITORE_MISTO
    centro_costo = data.centro_costo_suggerito or FORNITORE_MISTO
    centri_ammessi = list(dict.fromkeys(
        c.strip() for c in data.centri_costo_ammessi if c and c.strip()
    ))

    # Documento da salvare
    keywords_pulite = []
    for keyword in data.keywords:
        keywords_pulite.extend(_estrai_frasi_da_descrizione(keyword))
    keywords_pulite = list(dict.fromkeys(k for k in keywords_pulite if len(k) > 3))

    doc = {
        "id": f"fk_{nome_norm.replace(' ', '_')}",
        "fornitore_nome": data.fornitore_nome,
        "fornitore_nome_normalizzato": nome_norm,
        "keywords": keywords_pulite,
        "centro_costo_suggerito": centro_costo,
        "centri_costo_ammessi": centri_ammessi,
        "modalita_classificazione": "per_contenuto",
        "note": data.note,
        "fatture_count": fatture_count,
        "totale_fatture": round(totale, 2),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }

    # Upsert
    existing = await db[COLL_FORNITORI_KEYWORDS].find_one(
        {"fornitore_nome_normalizzato": nome_norm},
        {"_id": 0}
    )

    if existing:
        await db[COLL_FORNITORI_KEYWORDS].update_one(
            {"fornitore_nome_normalizzato": nome_norm},
            {"$set": doc}
        )
        return {"success": True, "message": "Fornitore aggiornato", "fornitore": doc}
    else:
        doc["created_at"] = datetime.now(timezone.utc).isoformat()
        # Copia del doc per evitare che insert_one aggiunga _id all'originale
        doc_to_insert = doc.copy()
        await db[COLL_FORNITORI_KEYWORDS].insert_one(doc_to_insert)
        return {"success": True, "message": "Fornitore creato", "fornitore": doc}


@router.delete("/{fornitore_id}")
async def elimina_fornitore_keywords(fornitore_id: str) -> Dict[str, Any]:
    """Elimina le keywords di un fornitore"""
    db = Database.get_db()

    result = await db[COLL_FORNITORI_KEYWORDS].delete_one({"id": fornitore_id})

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Fornitore non trovato")

    return {"success": True, "message": "Fornitore eliminato"}


@router.post("/riclassifica-con-keywords")
async def riclassifica_con_keywords_personalizzate() -> Dict[str, Any]:
    """
    Riclassifica le fatture usando le keywords personalizzate dei fornitori.
    Applica le associazioni memorizzate per migliorare la classificazione automatica.
    """
    db = Database.get_db()

    # Carica tutte le keywords configurate
    keywords_config = await db[COLL_FORNITORI_KEYWORDS].find({}).to_list(5000)

    if not keywords_config:
        return {
            "success": False,
            "message": "Nessun fornitore configurato. Aggiungi prima le keywords ai fornitori."
        }

    import re
    import app.services.learning_machine_cdc as lm

    riclassificate = 0
    saltati_non_configurati = 0
    dettaglio = []

    for config in keywords_config:
        # Schema-tolerant: config["fornitore_nome"] esplodeva (KeyError →
        # errore 500 sul bottone 'Riclassifica Fatture') appena in collection
        # c'era un documento auto-creato dall'event bus.
        fornitore_nome = _nome_da_config(config)
        keywords = config.get("keywords", [])
        centro_suggerito = config.get("centro_costo_suggerito")
        centri_ammessi = config.get("centri_costo_ammessi") or []

        if not fornitore_nome or (not keywords and not centro_suggerito):
            saltati_non_configurati += 1
            continue

        nome_escaped = re.escape(fornitore_nome)

        fatture = await db["invoices"].find({
            "$and": [
                {"$or": [
                    {"supplier_name": {"$regex": nome_escaped, "$options": "i"}},
                    {"fornitore_nome": {"$regex": nome_escaped, "$options": "i"}}
                ]},
                {"$or": [
                    {"centro_costo_nome": "Altri costi non classificati"},
                    {"centro_costo_id": {"$exists": False}},
                    {"centro_costo_id": None},
                    {"centro_costo_id": ""}
                ]}
            ]
        }).to_list(5000)

        misto = (
            config.get("modalita_classificazione", "per_contenuto") != "fornitore_fisso"
            or centro_suggerito == lm.FORNITORE_MISTO
        )
        ultimo_cdc_nome = None
        cambiate = 0
        for fatt in fatture:
            fonte = "keywords_personalizzate"
            if misto:
                # Fornitore MISTO (es. Amazon): ogni fattura è classificata
                # dal SUO contenuto (righe), mai dal fornitore. Se il
                # contenuto non decide, resta in "da classificare".
                cdc_id, cdc_config, _ = lm.classifica_fattura_per_centro_costo(
                    "", fatt.get("descrizione", ""), fatt.get("linee") or [],
                    centri_ammessi=centri_ammessi,
                )
                if cdc_id == "99_ALTRI_COSTI" or not lm.contenuto_decide_con_margine(
                    "", fatt.get("descrizione", ""), fatt.get("linee") or [],
                    centri_ammessi=centri_ammessi,
                ):
                    continue
                fonte = "contenuto_fattura"
            else:
                # 1) centro di costo scelto dall'utente (chiave o codice —
                #    risolutore UNICO del servizio)
                cdc_id, cdc_config = lm.risolvi_centro_costo(centro_suggerito)

                if not cdc_config:
                    # 2) classificazione standard pesata con le keywords
                    testo = " ".join(keywords)
                    cdc_id, cdc_config, _ = lm.classifica_fattura_per_centro_costo(
                        fornitore_nome, testo, []
                    )

                # Se il risultato è di nuovo "Altri costi", non è una riclassifica
                if cdc_id == "99_ALTRI_COSTI" and fatt.get("centro_costo_id"):
                    continue

            await db["invoices"].update_one(
                {"_id": fatt["_id"]},
                {"$set": {
                    "centro_costo_id": cdc_id,
                    "centro_costo": lm.settore_di(cdc_id),  # settore (CDC-01..04/99)
                    "centro_costo_nome": cdc_config["nome"],
                    "classificazione_fonte": fonte
                }}
            )
            riclassificate += 1
            cambiate += 1
            ultimo_cdc_nome = cdc_config["nome"]

        if cambiate:
            dettaglio.append({
                "fornitore": fornitore_nome,
                "fatture_riclassificate": cambiate,
                "nuovo_centro_costo": ultimo_cdc_nome
            })

    return {
        "success": True,
        "totale_riclassificate": riclassificate,
        "fornitori_saltati_non_configurati": saltati_non_configurati,
        "dettaglio": dettaglio
    }


@router.post("/classifica-da-contenuto")
async def classifica_da_contenuto(
    soglia: float = 0.3, limite: int = 4000
) -> Dict[str, Any]:
    """Classificazione AUTOMATICA di massa leggendo le RIGHE XML di ogni
    fattura (richiesta utente 11/07: "per una classificazione vera devi
    leggere le linee dell'XML e classificare automaticamente; a me devono
    restare solo le ambigue").

    Per ogni fattura non classificata:
      1. configurazione del fornitore (learning) se esiste — vince sempre;
      2. altrimenti il CONTENUTO delle righe decide, ma viene applicato
         SOLO se la confidenza supera la soglia;
      3. sotto soglia → resta "da classificare" (ambigua): mai a caso.
    """
    db = Database.get_db()
    import app.services.learning_machine_cdc as lm

    configurazioni = await lm.carica_configurazioni_learning(db)

    fatture = await db["invoices"].find(
        {"$or": [
            {"centro_costo_nome": "Altri costi non classificati"},
            {"centro_costo_id": {"$exists": False}},
            {"centro_costo_id": None},
            {"centro_costo_id": ""},
        ]},
        {"_id": 1, "supplier_name": 1, "descrizione": 1, "linee": 1}
    ).to_list(limite)

    esito = {"esaminate": len(fatture), "classificate": 0, "ambigue": 0,
             "per_centro": {}, "soglia": soglia}

    for f in fatture:
        cdc_id, cdc_config, conf, fonte = await lm.classifica_fattura_con_learning(
            db, f.get("supplier_name", ""), f.get("descrizione", ""),
            f.get("linee") or [], configurazioni=configurazioni,
        )
        # "Sicura" = configurazione del fornitore, oppure il contenuto
        # decide con MARGINE netto (unico centro che matcha, o distacco 2x
        # sul secondo, o confidenza sopra soglia). Altrimenti resta ambigua.
        sicura = (fonte == "keywords_personalizzate"
                  or (cdc_id != "99_ALTRI_COSTI"
                      and lm.contenuto_decide_con_margine(
                          "", f.get("descrizione", ""),
                          f.get("linee") or [], soglia_confidenza=soglia)))
        if not sicura:
            esito["ambigue"] += 1
            continue
        await db["invoices"].update_one(
            {"_id": f["_id"]},
            {"$set": {
                "centro_costo_id": cdc_id,
                "centro_costo": lm.settore_di(cdc_id),  # settore (CDC-01..04/99)
                "centro_costo_nome": cdc_config["nome"],
                "classificazione_confidence": conf,
                "classificazione_fonte": fonte,
            }}
        )
        esito["classificate"] += 1
        esito["per_centro"][cdc_config["nome"]] = esito["per_centro"].get(cdc_config["nome"], 0) + 1

    return {"success": True, **esito}


@router.post("/classifica-ai")
async def classifica_ambigue_con_ai(limite: int = 25) -> Dict[str, Any]:
    """Classificazione INTELLIGENTE delle sole fatture ambigue: manda a
    Claude le righe della fattura e l'elenco dei centri di costo, e applica
    la scelta solo se il modello è confidente. Le indecise restano tali.

    Usa la stessa configurazione della Chat (ANTHROPIC_API_KEY)."""
    import json as _json
    import os
    import app.services.learning_machine_cdc as lm

    if not os.getenv("ANTHROPIC_API_KEY", "").strip():
        return {"success": False,
                "message": "ANTHROPIC_API_KEY non configurata: la classificazione AI "
                           "usa lo stesso motore della Chat intelligente."}

    db = Database.get_db()
    fatture = await db["invoices"].find(
        {"$or": [
            {"centro_costo_nome": "Altri costi non classificati"},
            {"centro_costo_id": {"$exists": False}},
            {"centro_costo_id": None},
            {"centro_costo_id": ""},
        ]},
        {"_id": 0, "id": 1, "supplier_name": 1, "linee": 1}
    ).to_list(max(1, min(limite, 50)))

    if not fatture:
        return {"success": True, "message": "Nessuna fattura ambigua da classificare",
                "classificate": 0, "ancora_ambigue": 0}

    centri = [{"id": k, "nome": v["nome"]} for k, v in lm.CENTRI_COSTO.items()]
    voci = []
    for f in fatture:
        righe = [
            (l.get("descrizione") or l.get("description") or "")[:120]
            for l in (f.get("linee") or [])[:6] if isinstance(l, dict)
        ]
        voci.append({"id": f.get("id"), "fornitore": f.get("supplier_name", ""),
                     "righe": [r for r in righe if r]})

    prompt = (
        "Classifica queste fatture di un bar/pasticceria nei centri di costo. "
        "Rispondi SOLO con un array JSON di oggetti "
        '{"id", "centro_costo_id", "confidenza" (0-1), "motivo" (breve)}. '
        'Se il contenuto non basta per decidere usa centro_costo_id="AMBIGUA". '
        "Non inventare centri fuori elenco.\n\n"
        f"CENTRI DI COSTO: {_json.dumps(centri, ensure_ascii=False)}\n\n"
        f"FATTURE: {_json.dumps(voci, ensure_ascii=False)}"
    )

    try:
        import anthropic
        from app.services.chat_ai_engine import _model_name  # stesso modello della Chat
        client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY", "").strip())
        resp = await client.messages.create(
            model=_model_name(), max_tokens=4000,
            messages=[{"role": "user", "content": prompt}],
        )
        testo = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        inizio, fine = testo.find("["), testo.rfind("]")
        decisioni = _json.loads(testo[inizio:fine + 1]) if inizio >= 0 else []
    except Exception as e:
        logger.error(f"Classificazione AI fallita: {e}")
        return {"success": False, "message": f"Errore chiamata AI: {e}"}

    classificate = 0
    dettaglio = []
    for d in decisioni:
        cdc_id, cdc_config = lm.risolvi_centro_costo(d.get("centro_costo_id"))
        if not cdc_config or float(d.get("confidenza") or 0) < 0.6:
            continue
        res = await db["invoices"].update_one(
            {"id": d.get("id")},
            {"$set": {
                "centro_costo_id": cdc_id,
                "centro_costo": lm.settore_di(cdc_id),  # settore (CDC-01..04/99)
                "centro_costo_nome": cdc_config["nome"],
                "classificazione_confidence": float(d.get("confidenza") or 0),
                "classificazione_fonte": "ai",
                "classificazione_motivo": str(d.get("motivo") or "")[:200],
            }}
        )
        if res.matched_count:
            classificate += 1
            dettaglio.append({"id": d.get("id"), "centro": cdc_config["nome"],
                              "motivo": str(d.get("motivo") or "")[:120]})

    return {"success": True, "esaminate": len(fatture), "classificate": classificate,
            "ancora_ambigue": len(fatture) - classificate, "dettaglio": dettaglio}


# Parole scartate dalla proposta keyword: oltre alle congiunzioni, i termini
# di DOCUMENTO/LOGISTICA (ddt, bolle, spedizione, riferimenti...) che non
# dicono nulla sulla merce (richiesta utente 11/07: 'elimina dalla proposta
# i bollettini, i DDT, le cose che non sono materie prime') e i descrittori
# di taglia/unità di misura che spezzano il nome prodotto (richiesta utente
# 15/07: 'gilet unisex taglia XXL' deve proporre 'gilet unisex', non
# frammenti come 'unisex' o 'taglia').
_KEYWORD_STOP_WORDS = {
    "di", "da", "per", "con", "il", "la", "i", "le", "un", "una", "e", "o",
    "in", "su", "del", "della", "dei", "delle", "al", "alla", "ai", "alle",
    "n.", "nr.", "art.",
    # termini di documento/logistica, mai keyword di merce
    "ddt", "d.d.t.", "bolla", "bolle", "bollettino", "bollettini",
    "documento", "documenti", "trasporto", "spedizione", "spedizioni",
    "consegna", "consegne", "ordine", "ordini", "fattura", "fatture",
    "riferimento", "rif", "rif.", "codice", "articolo", "articoli",
    "colli", "collo", "porto", "vettore", "imballo", "imballaggio",
    "resa", "pagamento", "totale", "sconto", "omaggio", "cauzione",
    "acconto", "saldo", "iva", "imponibile", "aliquota", "listino",
    "contributo", "conai", "spese", "costi", "diritti", "segreteria",
    "periodo", "mese", "anno", "data", "numero", "cliente", "fornitore",
    # unità di misura e descrittori di taglia: separano il prodotto dal
    # resto della riga invece di far parte del nome
    "pz", "pz.", "pzi", "kg", "kg.", "gr", "gr.", "g", "g.", "lt", "lt.",
    "l", "ml", "ml.", "cm", "cm.", "mm", "mm.", "cf", "cf.", "conf",
    "confezione", "confezioni", "pacco", "pacchi", "cartone", "cartoni",
    "taglia", "taglie", "colore", "colori", "misura", "misure",
    "xs", "s", "m", "l", "xl", "xxl", "xxxl", "preventivo", "preventivi",
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
    "gen", "feb", "mar", "apr", "mag", "giu", "lug", "ago", "set",
    "ott", "nov", "dic", "protocollo", "protocol", "lotto", "lotti",
    "scadenza", "scadenze", "decorrenza", "emissione", "emesso", "emessa",
    "ricevuta", "ricevute", "destinazione", "causale", "allegato", "allegati",
    "merce", "merci", "vario", "varia", "vari", "varie",
}


def _estrai_frasi_da_descrizione(desc: str) -> List[str]:
    """Segmenta una descrizione riga fattura in frasi complete di senso
    compiuto, invece di singole parole: le parole "di contenuto" restano
    unite finché non incontrano uno stop-word/unità-di-misura/taglia, che
    chiude il segmento corrente. Così "GILET UNISEX TAGLIA XXL" produce
    "gilet unisex" (una frase) invece di tre parole isolate, e "AMARENA
    VISCIOLA INTERA KG 5" produce "amarena visciola intera"."""
    if not desc:
        return []
    frasi: List[str] = []
    corrente: List[str] = []
    # Barre, underscore e trattini sono separatori tipici di date e codici DDT.
    testo = re.sub(r"[/_|\\-]+", " ", desc.lower())
    for token in testo.split():
        parola = token.strip(".,;:!?()[]{}\"'<>#")
        if not parola:
            continue
        scarta = (
            parola in _KEYWORD_STOP_WORDS
            # Date, numeri documento, codici articolo e quantità non sono
            # categorie merceologiche e non devono diventare suggerimenti.
            or any(c.isdigit() for c in parola)
            or len(parola) < 2
        )
        if scarta:
            if corrente:
                frasi.append(" ".join(corrente))
                corrente = []
        else:
            corrente.append(parola)
    if corrente:
        frasi.append(" ".join(corrente))
    return frasi


@router.get("/suggerisci-keywords/{fornitore_nome}")
async def suggerisci_keywords(fornitore_nome: str) -> Dict[str, Any]:
    """
    Suggerisce keywords basandosi sulle descrizioni delle linee fattura del
    fornitore. Aiuta l'utente a configurare rapidamente le keywords.

    Le keyword proposte sono FRASI complete (es. "amarena visciola", "gilet
    unisex"), non parole singole isolate — bug segnalato dall'utente
    15/07/2026: lo split per singola parola produceva frammenti senza senso
    ("unisex", "preventivo", "taglia XXL" come parole a sé stanti).
    """
    db = Database.get_db()

    # Trova fatture del fornitore
    fatture = await db["invoices"].find(
        {"supplier_name": {"$regex": fornitore_nome, "$options": "i"}},
        {"_id": 0, "linee": 1, "descrizione": 1}
    ).limit(20).to_list(20)

    frasi_frequenza: Dict[str, int] = {}

    for fatt in fatture:
        candidate = []
        if fatt.get("descrizione"):
            candidate.append(fatt["descrizione"])
        for linea in fatt.get("linee", []):
            if isinstance(linea, dict):
                desc = linea.get("descrizione") or linea.get("description", "")
                if desc:
                    candidate.append(desc)

        for testo in candidate:
            for frase in _estrai_frasi_da_descrizione(testo):
                # Scarta frasi troppo corte per essere utili (una singola
                # lettera/sigla residua) tenendo comunque le parole singole
                # di senso compiuto (es. "cornetti").
                if len(frase) <= 3:
                    continue
                frasi_frequenza[frase] = frasi_frequenza.get(frase, 0) + 1

    # Ordina per frequenza e specificità, poi elimina i doppioni semantici.
    ordinate = sorted(
        frasi_frequenza.items(), key=lambda x: (x[1], len(x[0])), reverse=True
    )
    keywords_suggerite = []
    for frase, frequenza in ordinate:
        if any(
            (f" {frase} " in f" {presente} " or f" {presente} " in f" {frase} ")
            and frequenza <= freq_presente
            for presente, freq_presente in keywords_suggerite
        ):
            continue
        keywords_suggerite.append((frase, frequenza))
        if len(keywords_suggerite) == 12:
            break

    return {
        "fornitore": fornitore_nome,
        "keywords_suggerite": [k for k, _ in keywords_suggerite],
        "frequenze": {k: v for k, v in keywords_suggerite}
    }


@router.get("/centri-costo-disponibili")
async def centri_costo_disponibili() -> List[Dict[str, str]]:
    """
    Lista i centri di costo disponibili per la selezione
    """
    import app.services.learning_machine_cdc as lm

    # Prima voce: fornitore MISTO (es. Amazon) — ogni fattura classificata
    # dal suo contenuto, mai dal fornitore (richiesta utente 11/07)
    return [
        {"id": lm.FORNITORE_MISTO,
         "nome": "🧩 Fornitore misto — classifica ogni fattura dal contenuto",
         "codice": "MISTO"},
    ] + [
        {"id": cdc_id, "nome": config["nome"], "codice": config["codice"]}
        for cdc_id, config in lm.CENTRI_COSTO.items()
    ]



# ============================================
# ASSOCIAZIONE FORNITORI → MAGAZZINO
# ============================================

# Mappa centri di costo → categorie magazzino
# Chiavi allineate ai codici reali di CENTRI_COSTO (prima alcune — 1.4_LATTE,
# 1.5_PANE, 1.7_SALUMI, 7.3_PULIZIA_IGIENE — non esistevano e cadevano su "altro").
CDC_TO_MAGAZZINO_CATEGORIA = {
    "1.1_CAFFE_BEVANDE_CALDE": "caffe",
    "1.2_BEVANDE_FREDDE_ALCOLICI": "bevande",
    "1.3_MATERIE_PRIME_PASTICCERIA": "dolci",
    "1.4_PRODOTTI_SEMIFINITI": "dolci",
    "1.5_GELATI_GRANITE": "gelato",
    "1.6_PRODOTTI_CONFEZIONATI": "snack",
    "1.8_MATERIE_PRIME_CUCINA": "alimentari",
    "2.1_ENERGIA_ELETTRICA": "utenze",
    "5.3_PICCOLE_ATTREZZATURE": "attrezzature",
    "12.1_PULIZIA_LOCALE": "pulizia",
    "13.1_IMBALLAGGI": "packaging",
}


@router.post("/associa-magazzino")
async def associa_fornitori_magazzino() -> Dict[str, Any]:
    """
    Associa i prodotti nel magazzino ai fornitori configurati.
    Aggiorna ogni categoria dal contenuto del singolo prodotto.
    Questo permette di:
    - Sapere da chi compri la Coca Cola
    - Categorizzare correttamente i prodotti
    - Calcolare le giacenze per fornitore
    """
    db = Database.get_db()
    import app.services.learning_machine_cdc as lm

    # Carica fornitori configurati
    fornitori_config = await db[COLL_FORNITORI_KEYWORDS].find({}).to_list(5000)

    if not fornitori_config:
        return {"success": False, "message": "Nessun fornitore configurato"}

    aggiornati = 0
    dettaglio = []

    for config in fornitori_config:
        fornitore_nome = _nome_da_config(config)
        if not fornitore_nome:
            continue
        keywords = config.get("keywords", [])
        centri_ammessi = config.get("centri_costo_ammessi") or []

        # Trova prodotti di questo fornitore nel magazzino
        prodotti = await db["warehouse_inventory"].find({
            "fornitori": {"$regex": fornitore_nome, "$options": "i"}
        }).to_list(5000)

        for prod in prodotti:
            # Classifica ogni prodotto dal proprio contenuto: lo stesso
            # grossista può fornire vino, bicchieri e detergenti.
            if prod.get("categoria") == "altro" or not prod.get("categoria"):
                descrizione_prodotto = " ".join(str(prod.get(k) or "") for k in (
                    "nome", "descrizione", "prodotto", "articolo"
                ))
                cdc_id, _, _ = lm.classifica_fattura_per_centro_costo(
                    "", descrizione_prodotto, [], centri_ammessi=centri_ammessi
                )
                categoria_magazzino = CDC_TO_MAGAZZINO_CATEGORIA.get(cdc_id)
                if not categoria_magazzino:
                    continue
                await db["warehouse_inventory"].update_one(
                    {"_id": prod["_id"]},
                    {"$set": {
                        "categoria": categoria_magazzino,
                        "fornitore_principale": fornitore_nome,
                        "keywords_fornitore": keywords,
                        "centro_costo_fornitore": cdc_id,
                        "classificazione_fonte": "contenuto_prodotto",
                    }}
                )
                aggiornati += 1

        if prodotti:
            dettaglio.append({
                "fornitore": fornitore_nome,
                "prodotti_trovati": len(prodotti),
                "categorie_assegnate_per_prodotto": True
            })

    return {
        "success": True,
        "prodotti_aggiornati": aggiornati,
        "dettaglio": dettaglio
    }


@router.get("/prodotti-per-fornitore/{fornitore_nome}")
async def prodotti_per_fornitore(fornitore_nome: str) -> Dict[str, Any]:
    """
    Lista tutti i prodotti associati a un fornitore nel magazzino.
    Utile per verificare cosa compri da ciascun fornitore.
    """
    db = Database.get_db()

    prodotti = await db["warehouse_inventory"].find(
        {"fornitori": {"$regex": fornitore_nome, "$options": "i"}},
        {"_id": 0, "nome": 1, "categoria": 1, "giacenza": 1, "unita_misura": 1, "prezzi": 1}
    ).sort("nome", 1).to_list(100)

    # Raggruppa per categoria
    per_categoria = {}
    for p in prodotti:
        cat = p.get("categoria", "altro")
        if cat not in per_categoria:
            per_categoria[cat] = []
        per_categoria[cat].append(p)

    return {
        "fornitore": fornitore_nome,
        "totale_prodotti": len(prodotti),
        "per_categoria": per_categoria,
        "prodotti": prodotti[:50]  # Primi 50
    }


@router.get("/giacenze-fornitore/{fornitore_nome}")
async def giacenze_fornitore(fornitore_nome: str) -> Dict[str, Any]:
    """
    Calcola giacenze totali per un fornitore.
    Es: "Quante Coca Cola ho in magazzino?"
    """
    db = Database.get_db()

    # Aggregazione per calcolare giacenze
    pipeline = [
        {"$match": {"fornitori": {"$regex": fornitore_nome, "$options": "i"}}},
        {"$group": {
            "_id": "$categoria",
            "totale_prodotti": {"$sum": 1},
            "giacenza_totale": {"$sum": "$giacenza"},
            "valore_stimato": {"$sum": {"$multiply": ["$giacenza", {"$ifNull": [{"$avg": ["$prezzi.min", "$prezzi.max"]}, 0]}]}}
        }},
        {"$sort": {"totale_prodotti": -1}}
    ]

    stats = await db["warehouse_inventory"].aggregate(pipeline).to_list(5000)

    totale_giacenza = sum(s.get("giacenza_totale", 0) for s in stats)
    totale_valore = sum(s.get("valore_stimato", 0) for s in stats)

    return {
        "fornitore": fornitore_nome,
        "giacenza_totale": totale_giacenza,
        "valore_stimato": round(totale_valore, 2),
        "per_categoria": stats
    }



# ============================================
# CLASSIFICAZIONE F24 (Learning Machine)
# ============================================

@router.post("/classifica-f24")
async def classifica_f24_automatica() -> Dict[str, Any]:
    """
    Classifica automaticamente i documenti F24 nei centri di costo appropriati,
    basandosi sui codici tributo presenti in ciascun documento.

    Es:
    - Codici 60xx (IVA) → Centro costo "IVA periodica"
    - Codici 10xx (ritenute dipendenti) → "Costo del personale"
    - Codici 391x (IMU) → "IMU"
    - ecc.
    """
    db = Database.get_db()

    import app.services.learning_machine_cdc as lm
    import importlib
    importlib.reload(lm)

    # Trova tutti i documenti F24 non ancora classificati
    f24s = await db["f24_unificato"].find(
        {
            "status": {"$ne": "eliminato"},
            "$or": [
                {"centro_costo_id": {"$exists": False}},
                {"centro_costo_id": None},
                {"centro_costo_id": ""}
            ]
        }
    ).to_list(5000)

    if not f24s:
        return {
            "success": True,
            "message": "Tutti gli F24 sono già classificati",
            "classificati": 0
        }

    classificati = 0
    dettaglio = []

    for f24 in f24s:
        # Classifica usando la nuova funzione
        cdc_id, cdc_config, tipo_tributo = lm.classifica_f24_per_centro_costo(f24)

        # Aggiorna il documento
        await db["f24_unificato"].update_one(
            {"_id": f24["_id"]},
            {"$set": {
                "centro_costo_id": cdc_id,
                "centro_costo_nome": cdc_config["nome"],
                "centro_costo_codice": cdc_config["codice"],
                "tipo_tributo_principale": tipo_tributo,
                "classificazione_fonte": "learning_machine"
            }}
        )
        classificati += 1

        dettaglio.append({
            "id": str(f24.get("id", f24.get("_id"))),
            "anno": f24.get("anno"),
            "tipo_tributo": tipo_tributo,
            "centro_costo": cdc_config["nome"]
        })

    return {
        "success": True,
        "classificati": classificati,
        "dettaglio": dettaglio[:20]  # Primi 20 per brevità
    }


@router.get("/f24-statistiche")
async def f24_statistiche() -> Dict[str, Any]:
    """
    Statistiche sulla classificazione degli F24.
    """
    db = Database.get_db()

    # Conta totali
    totale = await db["f24_unificato"].count_documents({"status": {"$ne": "eliminato"}})
    classificati = await db["f24_unificato"].count_documents({
        "status": {"$ne": "eliminato"},
        "centro_costo_id": {"$exists": True, "$nin": [None, ""]}
    })

    # Aggregazione per centro di costo
    pipeline = [
        {"$match": {"status": {"$ne": "eliminato"}, "centro_costo_nome": {"$exists": True}}},
        {"$group": {
            "_id": "$centro_costo_nome",
            "count": {"$sum": 1},
            "totale_importo": {"$sum": "$saldo_finale"}
        }},
        {"$sort": {"count": -1}}
    ]

    per_cdc = await db["f24_unificato"].aggregate(pipeline).to_list(5000)

    return {
        "totale_f24": totale,
        "classificati": classificati,
        "non_classificati": totale - classificati,
        "per_centro_costo": per_cdc
    }


@router.post("/riclassifica-f24/{f24_id}")
async def riclassifica_singolo_f24(f24_id: str, data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """
    Riclassifica manualmente un singolo F24.

    Body:
        - centro_costo_id: ID del centro di costo da assegnare
    """
    db = Database.get_db()

    import app.services.learning_machine_cdc as lm

    centro_costo_id = data.get("centro_costo_id")
    if not centro_costo_id:
        raise HTTPException(status_code=400, detail="centro_costo_id richiesto")

    # Risolutore UNICO del servizio (chiave interna o codice bilancio)
    centro_costo_id, cdc_config = lm.risolvi_centro_costo(centro_costo_id)
    if not cdc_config:
        raise HTTPException(status_code=400, detail=f"Centro di costo '{data.get('centro_costo_id')}' non trovato")

    result = await db["f24_unificato"].update_one(
        {"id": f24_id},
        {"$set": {
            "centro_costo_id": centro_costo_id,
            "centro_costo_nome": cdc_config["nome"],
            "centro_costo_codice": cdc_config["codice"],
            "classificazione_fonte": "manuale"
        }}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="F24 non trovato")

    return {
        "success": True,
        "message": f"F24 classificato come '{cdc_config['nome']}'"
    }
