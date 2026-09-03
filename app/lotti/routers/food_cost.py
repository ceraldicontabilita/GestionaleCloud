from fastapi import APIRouter, HTTPException, Query, Body, Request, Depends
from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import List, Optional, Any
from datetime import datetime, timezone, timedelta, date
import re
import logging
_LOG_INIT = logging.getLogger("uvicorn.error")
import uuid

router = APIRouter(prefix="/food-cost", tags=["Food Cost"])

# Categorie del reparto bar/bevande: si acquistano e si confrontano a
# CARTONE/UNITÀ, mai a kg/litro (segnalato da Enzo 02/07/2026 — un rum da
# 2L si paga a bottiglia, non "al chilo"). Fonte UNICA in routers.utils.
from app.lotti.routers.utils import CATEGORIE_BEVANDE_A_UNITA as CATEGORIE_VENDUTE_A_UNITA  # noqa: E402
from app.lotti.auth import require_admin
from app.lotti.allergeni import (
    ALLERGENI_14,
    MAPPA_ALLERGENI,
    estrai_nomi_ingredienti,
    normalizza_allergeni,
    rileva_allergeni,
)

# MongoDB connection
# ==================== MODELS ====================


class ProdottoDizionario(BaseModel):
    """Prodotto nel dizionario prezzi centralizzato con inventario"""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    nome_originale: str  # Nome dalla fattura
    nome_normalizzato: str  # Nome pulito per ricerca
    peso_confezione: float  # Peso/volume della confezione
    unita_confezione: str = "kg"  # kg, lt, pz
    prezzo_confezione: float  # Prezzo unitario dalla fattura (netto IVA)
    prezzo_kg: float  # Prezzo per kg/lt calcolato
    quantita_totale_kg: float = 0  # Quantità totale disponibile in kg/lt
    quantita_usata_kg: float = 0  # Quantità già usata nelle ricette
    quantita_disponibile_kg: float = 0  # Quantità rimanente
    fornitore: str = ""
    data_fattura: str = ""
    ultimo_aggiornamento: str = ""


class IngredienteConQuantita(BaseModel):
    """Ingrediente con quantità per ricetta — accetta stringhe numeriche e q.b. dal DB"""

    model_config = ConfigDict(extra="ignore")
    nome: str
    quantita: Any = 0
    unita_misura: str = "g"
    prodotto_dizionario_id: Optional[str] = None
    prezzo_kg: Optional[float] = None
    costo_calcolato: Optional[float] = None
    costo_per_pezzo: Optional[float] = None
    is_acquaviva: Optional[bool] = False

    @field_validator("quantita", mode="before")
    @classmethod
    def coerce_quantita(cls, v: Any) -> Any:
        if v is None or v == "":
            return 0
        if isinstance(v, (int, float)):
            return v
        if isinstance(v, str):
            v_clean = v.strip().lower()
            if v_clean in ("q.b.", "q.b", "qb", "quanto basta", "q. b."):
                return "q.b."
            try:
                return float(v.replace(",", "."))
            except ValueError:
                return "q.b."
        return v

    @field_validator("prezzo_kg", "costo_calcolato", mode="before")
    @classmethod
    def coerce_optional_float(cls, v: Any) -> Optional[float]:
        if v is None or v == "":
            return None
        if isinstance(v, str):
            try:
                return float(v.replace(",", "."))
            except ValueError:
                return None
        return v


class AggiornaIngredienteRicetta(BaseModel):
    """Payload per aggiornare ingredienti di una ricetta"""

    ricetta_id: str
    ingredienti_dettaglio: List[IngredienteConQuantita]


class UsaRicettaRequest(BaseModel):
    """Request per usare una ricetta e scalare le quantità"""

    ricetta_id: str
    porzioni: int = 1  # Numero di porzioni da preparare


# ==================== DIZIONARIO PRODOTTI ====================


async def get_fornitori_esclusi():
    """Ottiene la lista dei nomi dei fornitori esclusi. Unione di db.fornitori
    (che il gestionale Cloud può risovrascrivere) e fornitori_decisioni (le
    decisioni di Enzo, di sola proprietà di Lotti — fix 23/07/2026): così
    un fornitore escluso resta escluso anche se il DB condiviso viene
    riscritto prima dell'auto-riparazione della lista fornitori."""
    fornitori_esclusi_docs = await db.fornitori.find(
        {"escluso": True}, {"nome": 1, "_id": 0}
    ).to_list(2000)
    nomi = {f["nome"].lower().strip() for f in fornitori_esclusi_docs if f.get("nome")}
    async for d in db.fornitori_decisioni.find({"escluso": True}, {"_id": 0, "nome": 1}):
        if d.get("nome"):
            nomi.add(d["nome"].lower().strip())
    return sorted(nomi)


@router.get("/dizionario")
async def get_dizionario(
    search: str = Query(None, description="Cerca prodotti"),
    escludi_fornitori: bool = Query(True, description="Escludi prodotti di fornitori esclusi"),
    senza_canonico: bool = Query(False, description="Solo prodotti senza ingrediente_canonico (da associare)"),
    solo_completi: bool = Query(False, description="Solo fornitori Magazzino+Lotti (tipo_fornitura completo)"),
    solo_esclusi: bool = Query(False, description="Solo le righe escluse a mano dal battesimo (per rivederle/ripristinarle)"),
    proponi_canonici: bool = Query(True, description="Calcola le proposte di nome canonico"),
    skip: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=2000),
):
    """
    Ottiene il dizionario prodotti centralizzato.
    Esclude automaticamente i prodotti dei fornitori esclusi.
    Con solo_completi=true restano SOLO le righe dei fornitori che alimentano
    magazzino e lotti (richiesta Enzo 04/07/2026: sono le uniche che servono
    al matching esatto nelle ricette). Le righe senza canonico ricevono una
    PROPOSTA automatica (proposta_canonico) da confermare o correggere.
    Le righe con escluso_ricette=true (escluse a mano o per famiglia: bevande,
    alcolici, vini — richiesta Enzo 23/07/2026) NON compaiono mai, tranne con
    solo_esclusi=true (la vista dedicata per rivederle e ripristinarle).
    """
    query = {"escluso_ricette": True} if solo_esclusi else {"escluso_ricette": {"$ne": True}}
    if solo_esclusi:
        senza_canonico = False  # la vista esclusi mostra tutte le escluse, associate o no

    # Filtra per ricerca
    if search and len(search) >= 2:
        query["nome_normalizzato"] = {"$regex": search.lower(), "$options": "i"}

    if senza_canonico:
        query["$or"] = [
            {"ingrediente_canonico": {"$in": [None, ""]}},
            {"nome_canonico": {"$in": [None, ""]}},
        ]

    # Fornitori da nascondere: esclusi + (con solo_completi) i solo-magazzino.
    # Non troncare l'elenco: tutti i fornitori esclusi devono sparire dal
    # dizionario. Il confronto viene fatto in Python dopo una singola lettura:
    # $expr/$not/$in non e' supportato dal mirror Mongo del document store
    # Supabase, mentre centinaia di regex in $nor rendevano la pagina lenta.
    nascosti = set()
    if escludi_fornitori:
        nascosti.update(await get_fornitori_esclusi())
    if solo_completi:
        # via i fornitori solo-magazzino (bibite ecc.): niente lotti/ricette.
        # Il default per chi non ha il campo è "completo", quindi si ESCLUDONO
        # i non-completi invece di includere i completi.
        non_completi = await db.fornitori.find(
            {"tipo_fornitura": {"$in": ["solo_magazzino", "escluso"]}},
            {"_id": 0, "nome": 1},
        ).to_list(2000)
        nascosti.update(f["nome"].lower().strip() for f in non_completi if f.get("nome"))
        async for d in db.fornitori_decisioni.find(
            {"tipo_fornitura": {"$in": ["solo_magazzino", "escluso"]}}, {"_id": 0, "nome": 1}
        ):
            if d.get("nome"):
                nascosti.add(d["nome"].lower().strip())
    cursor = db.dizionario_prodotti.find(query, {"_id": 0}).sort(
        [("ultima_fattura_data", -1), ("nome_normalizzato", 1)]
    )
    if nascosti:
        candidati_totale = await db.dizionario_prodotti.count_documents(query)
        candidati = await cursor.to_list(max(candidati_totale, 1))
        filtrati = [
            p for p in candidati
            if str(p.get("fornitore") or "").strip().lower() not in nascosti
        ]
        totale = len(filtrati)
        prodotti = filtrati[skip:skip + limit]
    else:
        totale = await db.dizionario_prodotti.count_documents(query)
        prodotti = await cursor.skip(skip).limit(limit).to_list(limit)

    # PROPOSTA di nome canonico per le righe scoperte: Enzo conferma con un
    # tocco o corregge ("van." → Vaniglia), senza dover riconoscere da solo
    # le sigle dei fornitori (richiesta 04/07/2026).
    try:
        from app.lotti.routers.ingredienti import match_livello2
        if proponi_canonici:
            for p in prodotti:
                if not (p.get("ingrediente_canonico") or p.get("nome_canonico")):
                    prop = match_livello2(p.get("nome_originale") or p.get("nome_normalizzato") or "")
                    if prop:
                        p["proposta_canonico"] = prop
    except Exception:
        logging.getLogger(__name__).debug("[dizionario] proposta canonico non bloccante fallita")

    return {"totale": totale, "skip": skip, "limit": limit, "prodotti": prodotti}


@router.get("/dizionario/canonici")
async def get_canonici_dizionario():
    """Elenco dei nomi canonici già usati (per l'autocomplete della pagina
    Dizionario: evita refusi tipo Vaniglia/vaniglia quando Enzo scrive a mano)."""
    canonici = await db.dizionario_prodotti.distinct("ingrediente_canonico")
    return sorted({c.strip() for c in canonici if c and c.strip()})


# ── Esclusione righe dal battesimo (richiesta Enzo 23/07/2026) ────────────────
# Nel Dizionario finiscono anche righe che non c'entrano con le ricette
# (segnaletica, bevande, alcolici, vini...): battezzarle è lavoro inutile.
# L'esclusione è REVERSIBILE (vista "Escluse" → Ripristina) e non tocca i
# prezzi né lo storico: la riga semplicemente esce dalla coda da battezzare
# (pagina + promemoria DATI4 del Supervisore).

FAMIGLIE_ESCLUSIONE_DIZIONARIO = {
    "bevande": ["acqua", "bibita", "bibite", "succo", "succhi", "sciroppo",
                "coca", "cola", "aranciata", "gassosa", "chinotto", "tonica",
                "cedrata", "limonata", "spremuta", "energy", "red bull",
                "redbull", "ginger", "estathe", "the freddo", "te freddo"],
    "alcolici": ["birra", "birre", "liquore", "liquori", "amaro", "amari",
                 "rum", "gin", "vodka", "whisky", "whiskey", "grappa",
                 "aperol", "campari", "sambuca", "limoncello", "brandy",
                 "cognac", "vermouth", "vermut", "bitter", "aperitivo"],
    "vini": ["vino", "vini", "spumante", "prosecco", "champagne",
             "franciacorta", "lambrusco", "falanghina", "aglianico",
             "moscato", "brut", "greco di tufo"],
}


def _regex_famiglia(famiglia: str):
    """Regex OR a parole intere per le keyword della famiglia (case-insensitive).
    Parole intere (\\b) per non agganciare per sbaglio ingredienti veri:
    es. 'vino' non deve prendere 'uva sultanina', 'rum' non 'strumento'."""
    parole = FAMIGLIE_ESCLUSIONE_DIZIONARIO.get(famiglia) or []
    if not parole:
        return None
    return "|".join(rf"\b{re.escape(p)}\b" for p in parole)


@router.post("/dizionario/escludi")
async def dizionario_escludi_riga(payload: dict = Body(...)):
    """Esclude (o ripristina, con escluso=false) UNA riga dal battesimo."""
    riga_id = (payload.get("id") or "").strip()
    escluso = bool(payload.get("escluso", True))
    if not riga_id:
        raise HTTPException(status_code=400, detail="id riga mancante")
    upd = ({"escluso_ricette": True, "escluso_motivo": (payload.get("motivo") or "manuale")[:60],
            "escluso_il": datetime.now(timezone.utc).isoformat()}
           if escluso else
           {"escluso_ricette": False, "escluso_motivo": "", "escluso_il": ""})
    res = await db.dizionario_prodotti.update_one({"id": riga_id}, {"$set": upd})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Riga non trovata")
    return {"ok": True, "id": riga_id, "escluso": escluso}


@router.post("/dizionario/escludi-famiglia")
async def dizionario_escludi_famiglia(payload: dict = Body(...)):
    """Esclude in blocco le righe che appartengono a una famiglia (bevande /
    alcolici / vini). Con anteprima=true NON scrive nulla: ritorna quante
    righe verrebbero escluse e alcuni esempi, così Enzo conferma a colpo
    sicuro (le parole a doppio uso, es. 'amaro', si vedono prima)."""
    famiglia = (payload.get("famiglia") or "").strip().lower()
    anteprima = bool(payload.get("anteprima", False))
    rx = _regex_famiglia(famiglia)
    if not rx:
        raise HTTPException(status_code=400,
                            detail=f"Famiglia sconosciuta: usa una tra {sorted(FAMIGLIE_ESCLUSIONE_DIZIONARIO)}")
    query = {
        "escluso_ricette": {"$ne": True},
        "$or": [
            {"nome_normalizzato": {"$regex": rx, "$options": "i"}},
            {"nome_originale": {"$regex": rx, "$options": "i"}},
        ],
    }
    if anteprima:
        righe = await db.dizionario_prodotti.find(
            query, {"_id": 0, "nome_originale": 1, "nome_normalizzato": 1}
        ).to_list(3000)
        esempi = [r.get("nome_originale") or r.get("nome_normalizzato") or "?" for r in righe[:8]]
        return {"famiglia": famiglia, "quante": len(righe), "esempi": esempi}
    res = await db.dizionario_prodotti.update_many(
        query,
        {"$set": {"escluso_ricette": True, "escluso_motivo": f"famiglia:{famiglia}",
                   "escluso_il": datetime.now(timezone.utc).isoformat()}},
    )
    return {"ok": True, "famiglia": famiglia, "escluse": res.modified_count}


@router.post("/backfill-dati-riga-dizionario")
async def backfill_dati_riga_dizionario(request: Request):
    """Una tantum (idempotente): riempie prezzo/quantità/unità DI RIGA sulle
    voci storiche del Dizionario leggendo la fattura più RECENTE che le cita.
    I campi nuovi (ultimo_prezzo_riga & co., 04/07/2026) si popolano da soli
    a ogni import: questo backfill serve solo per lo storico pre-modifica.
    Lanciabile dal bottone admin nella pagina Dizionario. Il secondo run non
    trova più voci scoperte e non tocca nulla."""
    ruolo = (getattr(request.state, "user", None) or {}).get("ruolo", "")
    if ruolo != "amministratore":
        raise HTTPException(403, "Operazione riservata all'amministratore")
    from app.lotti.routers.utils import parse_data_flessibile

    filtro_scoperte = {"$or": [
        {"ultimo_prezzo_riga": {"$exists": False}},
        {"ultimo_prezzo_riga": None},
    ]}
    totale = await db.dizionario_prodotti.count_documents({})
    docs = await db.dizionario_prodotti.find(
        filtro_scoperte, {"_id": 0, "nome_normalizzato": 1}
    ).to_list(30000)
    mancanti = {d["nome_normalizzato"] for d in docs if d.get("nome_normalizzato")}
    if not mancanti:
        return {"ok": True, "aggiornati": 0, "senza_fattura_trovata": 0,
                "totale_righe": totale, "righe_scoperte": 0}

    # Il dizionario contiene DUE famiglie di chiavi (debito noto, vedi STATO.md):
    # - descrizione grezza minuscola (import fattura-per-fattura);
    # - normalizza_nome_prodotto() minuscolo (sincronizza-fatture: toglie pesi,
    #   codici lotto, moltiplicatori — "FARINA KG.25 X4" → "farina").
    # Il match deve provarle ENTRAMBE, altrimenti le righe della seconda
    # famiglia non si aggancerebbero mai (bug reale: primo run = 0 aggiornati).
    fatture = await db.fatture.find(
        {}, {"_id": 0, "data_fattura": 1, "prodotti": 1}
    ).to_list(20000)
    # dalla più recente: la PRIMA occorrenza trovata è l'ultimo acquisto
    fatture.sort(key=lambda f: parse_data_flessibile(f.get("data_fattura")) or date.min, reverse=True)

    aggiornati = 0
    for f in fatture:
        if not mancanti:
            break
        for p in f.get("prodotti") or []:
            desc = (p.get("descrizione") or "").strip()
            if not desc:
                continue
            nn_grezzo = re.sub(r"\s+", " ", desc.lower())
            nn_pulito = normalizza_nome_prodotto(desc).lower()
            chiavi = {c for c in (nn_grezzo, nn_pulito) if c and c in mancanti}
            if not chiavi:
                continue
            try:
                prezzo = float(str(p.get("prezzo", "0")).replace(",", "."))
            except (ValueError, TypeError):
                prezzo = 0.0
            try:
                qta = float(str(p.get("quantita", "1")).replace(",", "."))
            except (ValueError, TypeError):
                qta = 1.0
            if prezzo <= 0:
                # riga contabile/omaggio: lasciala a una fattura più vecchia con prezzo vero
                continue
            for chiave in chiavi:
                res = await db.dizionario_prodotti.update_many(
                    {"nome_normalizzato": chiave, **filtro_scoperte},
                    {"$set": {
                        "ultimo_prezzo_riga": prezzo,
                        "ultima_quantita_riga": qta,
                        "ultima_unita_riga": (p.get("unita_misura") or "").strip(),
                    }},
                )
                mancanti.discard(chiave)
                aggiornati += res.modified_count

    return {"ok": True, "aggiornati": aggiornati, "senza_fattura_trovata": len(mancanti),
            "totale_righe": totale, "righe_scoperte": len(docs)}


# ── Dedup Dizionario (doppioni a doppia chiave) ─────────────────────────────
# Debito noto: il Dizionario contiene lo STESSO prodotto due volte, con due
# nome_normalizzato diversi — la descrizione grezza ("farina 00 kg.25", scritta
# dall'import) e la forma pulita ("farina 00", scritta dalla vecchia
# sincronizzazione). I due doppioni hanno prezzi diversi e confondono
# comparatore/food-cost. Qui li si UNISCE nel record più ricco.

def _chiave_dedup(doc: dict) -> str:
    """Chiave di raggruppamento: la forma pulita del nome (senza pesi/lotti).
    Due righe che collassano sulla stessa chiave sono lo stesso prodotto."""
    base = (doc.get("nome_originale") or doc.get("nome_normalizzato") or "").strip()
    return normalizza_nome_prodotto(base).lower().strip()


def _punteggio_keeper(doc: dict) -> tuple:
    """Il record da TENERE è il più ricco: prima chi ha un canonico confermato,
    poi le correzioni manuali, poi più acquisti, poi chi ha il prezzo di riga."""
    return (
        1 if (doc.get("ingrediente_canonico") or doc.get("nome_canonico")) else 0,
        1 if doc.get("peso_corretto_manualmente") else 0,
        1 if (doc.get("scorta_minima") or 0) else 0,
        int(doc.get("conteggio_acquisti") or 0),
        1 if doc.get("ultimo_prezzo_riga") is not None else 0,
    )


async def _gruppi_duplicati() -> list:
    """Gruppi (>=2 righe) di dizionario_prodotti che sono lo stesso prodotto."""
    tutti = await db.dizionario_prodotti.find({}, {"_id": 0}).to_list(30000)
    per_chiave: dict = {}
    for d in tutti:
        k = _chiave_dedup(d)
        if k:
            per_chiave.setdefault(k, []).append(d)
    gruppi = []
    for k, docs in per_chiave.items():
        if len(docs) < 2:
            continue
        docs_ordinati = sorted(docs, key=_punteggio_keeper, reverse=True)
        gruppi.append({"chiave": k, "tieni": docs_ordinati[0], "unisci": docs_ordinati[1:]})
    return gruppi


@router.get("/dizionario/duplicati")
async def dizionario_duplicati_preview():
    """ANTEPRIMA (sola lettura, non cambia nulla): elenca i doppioni del
    Dizionario e cosa verrebbe unito. Serve alla card prima di applicare."""
    gruppi = await _gruppi_duplicati()
    def _riassunto(d):
        return {
            "id": d.get("id"),
            "nome_normalizzato": d.get("nome_normalizzato"),
            "canonico": d.get("ingrediente_canonico") or d.get("nome_canonico") or "",
            "prezzo_kg": d.get("prezzo_kg"),
            "ultimo_prezzo_riga": d.get("ultimo_prezzo_riga"),
            "conteggio_acquisti": d.get("conteggio_acquisti") or 0,
            "manuale": bool(d.get("peso_corretto_manualmente")),
        }
    out = [{"chiave": g["chiave"], "tieni": _riassunto(g["tieni"]),
            "unisci": [_riassunto(x) for x in g["unisci"]]} for g in gruppi]
    return {"gruppi_doppioni": len(out), "righe_da_unire": sum(len(g["unisci"]) for g in gruppi),
            "dettaglio": out[:200]}


@router.post("/dizionario/dedup")
async def dizionario_dedup(request: Request):
    """Unisce i doppioni nel record più ricco (solo amministratore, idempotente).
    Riempie i campi mancanti del keeper dagli altri, somma i conteggi acquisti,
    RIPUNTA i collegamenti delle ricette (prodotto_dizionario_id) sul keeper, poi
    elimina i doppioni. Un secondo run non trova più gruppi e non tocca nulla."""
    ruolo = (getattr(request.state, "user", None) or {}).get("ruolo", "")
    if ruolo != "amministratore":
        raise HTTPException(403, "Operazione riservata all'amministratore")

    gruppi = await _gruppi_duplicati()
    gruppi_uniti = 0
    righe_eliminate = 0
    ricette_ripuntate = 0
    for g in gruppi:
        keeper = g["tieni"]
        keep_id = keeper.get("id")
        if not keep_id:
            continue
        patch: dict = {}
        # riempi i buchi del keeper dagli altri record
        for altro in g["unisci"]:
            for campo in ("ingrediente_canonico", "nome_canonico", "ultimo_prezzo_riga",
                          "ultima_quantita_riga", "ultima_unita_riga", "iva_pct",
                          "peso_confezione", "unita_confezione", "tipo_quantita"):
                if not (keeper.get(campo) or patch.get(campo)) and altro.get(campo) not in (None, "", 0):
                    patch[campo] = altro.get(campo)
            if (altro.get("scorta_minima") or 0) > (patch.get("scorta_minima") or keeper.get("scorta_minima") or 0):
                patch["scorta_minima"] = altro.get("scorta_minima")
        # somma i conteggi acquisti di tutto il gruppo
        tot_acq = int(keeper.get("conteggio_acquisti") or 0) + sum(
            int(a.get("conteggio_acquisti") or 0) for a in g["unisci"])
        patch["conteggio_acquisti"] = tot_acq
        if patch:
            await db.dizionario_prodotti.update_one({"id": keep_id}, {"$set": patch})

        ids_da_eliminare = [a.get("id") for a in g["unisci"] if a.get("id")]
        # ripunta le ricette che riferivano i doppioni sul keeper
        if ids_da_eliminare:
            res_ric = await db.ricette.update_many(
                {"ingredienti_dettaglio.prodotto_dizionario_id": {"$in": ids_da_eliminare}},
                {"$set": {"ingredienti_dettaglio.$[el].prodotto_dizionario_id": keep_id}},
                array_filters=[{"el.prodotto_dizionario_id": {"$in": ids_da_eliminare}}],
            )
            ricette_ripuntate += res_ric.modified_count
            res_del = await db.dizionario_prodotti.delete_many({"id": {"$in": ids_da_eliminare}})
            righe_eliminate += res_del.deleted_count
        gruppi_uniti += 1

    return {"ok": True, "gruppi_uniti": gruppi_uniti, "righe_eliminate": righe_eliminate,
            "ricette_ripuntate": ricette_ripuntate}


@router.post("/backfill-prezzo-kg-anomali")
async def backfill_prezzo_kg_anomali(soglia_eur_kg: float = 500.0):
    """Una tantum: ricalcola prezzo_kg SOLO per i prodotti con un valore
    palesemente implausibile (oltre soglia_eur_kg €/kg — quasi nessun
    ingrediente di pasticceria/bar costa così tanto), usando la logica
    aggiornata di calcola_prezzo_quantita_kg (supporto CL, moltiplicatore
    cartone CTX24/X6 — bug corretto il 02/07/2026, vedi STATO.md). Questi
    valori restavano sbagliati per sempre perché prezzo_kg si aggiorna solo
    quando arriva una NUOVA fattura per quel prodotto, mai retroattivamente.
    Non tocca i prodotti già con un prezzo ragionevole (nessun rischio per
    dati già corretti) e applica il nuovo valore solo se più basso di quello
    attuale (il bug gonfia sempre, non sgonfia mai)."""
    from app.lotti.routers.xml_helpers import calcola_prezzo_quantita_kg

    sospetti = await db.dizionario_prodotti.find(
        {"prezzo_kg": {"$gt": soglia_eur_kg}},
        {"_id": 0, "nome_normalizzato": 1, "nome_originale": 1, "ultimo_prezzo_fattura": 1, "prezzo_kg": 1},
    ).to_list(2000)

    corretti = []
    non_risolti = []
    for p in sospetti:
        prezzo_raw = float(p.get("ultimo_prezzo_fattura") or 0)
        desc = p.get("nome_originale") or p.get("nome_normalizzato") or ""
        if prezzo_raw <= 0 or not desc:
            non_risolti.append(p.get("nome_normalizzato"))
            continue
        calcolo = calcola_prezzo_quantita_kg(
            quantita=1, prezzo=prezzo_raw, unita_misura_fattura="", descrizione=desc, regola_nota=None,
        )
        nuovo_prezzo_kg = calcolo.get("prezzo_kg")
        if nuovo_prezzo_kg and nuovo_prezzo_kg > 0 and nuovo_prezzo_kg < p["prezzo_kg"]:
            await db.dizionario_prodotti.update_one(
                {"nome_normalizzato": p["nome_normalizzato"]},
                {"$set": {
                    "prezzo_kg": round(nuovo_prezzo_kg, 4),
                    "ultimo_prezzo_kg": round(nuovo_prezzo_kg, 4),
                    "prezzo_precedente_kg": round(nuovo_prezzo_kg, 4),
                }},
            )
            corretti.append({"nome": p.get("nome_normalizzato"), "prima": p["prezzo_kg"], "dopo": round(nuovo_prezzo_kg, 4)})
        else:
            non_risolti.append(p.get("nome_normalizzato"))

    # Le vecchie notifiche "-99%"/"+900%" per questi prodotti sono a loro volta
    # un artefatto dello stesso bug: risolvile (non cancellarle, per
    # tracciabilità) così spariscono dal Supervisore invece di restare per sempre.
    res_alert = await db.alert_prezzi.update_many(
        {"letto": False, "$or": [{"valore": {"$gte": 90}}, {"valore": {"$lte": -90}}]},
        {"$set": {"letto": True, "risolto_da_backfill": True}},
    )

    return {
        "ok": True,
        "sospetti_trovati": len(sospetti),
        "corretti": len(corretti),
        "dettaglio_corretti": corretti[:50],
        "non_risolti": non_risolti[:50],
        "alert_prezzo_risolti": res_alert.modified_count,
    }


@router.get("/dizionario/search")
async def search_dizionario(
    q: str = Query(..., min_length=2),
    escludi_fornitori: bool = Query(True, description="Escludi prodotti di fornitori esclusi"),
    solo_acquaviva: bool = Query(False, description="Mostra solo prodotti Acquaviva"),
):
    """
    Ricerca prodotti nel dizionario per autocompletamento.
    Restituisce max 20 risultati ordinati per rilevanza.
    Esclude automaticamente i fornitori esclusi.
    """
    from app.lotti.routers.utils import stems_ricerca
    stems = stems_ricerca(q)
    if stems:
        # Motore unico: match per radici (singolare/plurale unificati)
        query = {"$and": [{"nome_normalizzato": {"$regex": re.escape(s), "$options": "i"}} for s in stems]}
    else:
        query = {"nome_normalizzato": {"$regex": re.escape(q.lower()), "$options": "i"}}

    if solo_acquaviva:
        query["fornitore"] = {"$regex": "acquaviva|vandemoortele", "$options": "i"}

    # Escludi fornitori esclusi (solo se non stiamo filtrando per acquaviva)
    if escludi_fornitori and not solo_acquaviva:
        fornitori_esclusi = await get_fornitori_esclusi()
        if fornitori_esclusi:
            query["$nor"] = [
                {"fornitore": {"$regex": f"^{re.escape(f)}$", "$options": "i"}}
                for f in fornitori_esclusi[:50]
            ]

    prodotti = await db.dizionario_prodotti.find(query, {"_id": 0}).limit(20).to_list(20)

    # Ordina per match migliore (inizia con la query)
    def sort_key(p):
        nome = p.get("nome_normalizzato", "").lower()
        if nome.startswith(q.lower()):
            return (0, nome)
        return (1, nome)

    prodotti.sort(key=sort_key)

    # Arricchisci con costo_per_pezzo se disponibile
    for p in prodotti:
        if not p.get("costo_per_pezzo") and p.get("peso_pezzo_g") and p.get("prezzo_kg"):
            peso_kg = float(p["peso_pezzo_g"]) / 1000
            p["costo_per_pezzo"] = round(peso_kg * float(p["prezzo_kg"]), 4)
        # Arricchisci con nome_canonico da nome_mapping se non presente nel documento
        if not p.get("nome_canonico"):
            try:
                mapping = await db.nome_mapping.find_one(
                    {"descrizione_key": p.get("nome_normalizzato", "")[:200]},
                    {"_id": 0, "nome_canc": 1},
                )
                if mapping and mapping.get("nome_canc"):
                    p["nome_canonico"] = mapping["nome_canc"]
            except Exception:
                _LOG_INIT.debug("[food_cost] errore non bloccante ignorato")
        p["nome_display"] = p.get("nome_canonico") or p.get("nome_normalizzato", "")

    # Deduplicazione per nome_display: mostra una sola voce per nome canonico
    visti: dict = {}
    prodotti_dedup = []
    for p in prodotti:
        nc_key = p.get("nome_display", "").lower().strip()
        if nc_key not in visti:
            visti[nc_key] = True
            prodotti_dedup.append(p)

    return prodotti_dedup


@router.get("/confronto-prodotto")
async def confronto_prodotto(q: str = Query(..., min_length=2)):
    """Pagina prodotto SEMPLICE (richiesta Enzo): cerco «coca cola» e ottengo,
    raggruppato per nome canonico, l'ULTIMO prezzo di ogni fornitore, ordinato
    dal più conveniente. Il frontend evidenzia il migliore e lo aggiunge al
    carrello ordini. I dati vengono SOLO dalle fatture reali (dizionario)."""
    from app.lotti.routers.utils import stems_ricerca, parse_data_flessibile

    stems = stems_ricerca(q)
    if stems:
        query = {"$and": [{"nome_normalizzato": {"$regex": re.escape(s), "$options": "i"}} for s in stems]}
    else:
        query = {"nome_normalizzato": {"$regex": re.escape(q.lower()), "$options": "i"}}

    esclusi = set(await get_fornitori_esclusi())
    docs = await db.dizionario_prodotti.find(query, {"_id": 0}).to_list(800)

    # canonico: dal documento o dal nome_mapping (memorizzato con «correggi-mapping»)
    mappings = {}
    keys = list({(d.get("nome_normalizzato") or "")[:200] for d in docs})
    for blocco in range(0, len(keys), 400):
        async for m in db.nome_mapping.find(
            {"descrizione_key": {"$in": keys[blocco:blocco + 400]}}, {"_id": 0, "descrizione_key": 1, "nome_canc": 1}
        ):
            if m.get("nome_canc"):
                mappings[m["descrizione_key"]] = m["nome_canc"].strip()

    def _canonico(d):
        c = (d.get("ingrediente_canonico") or d.get("nome_canonico") or "").strip()
        return c or mappings.get((d.get("nome_normalizzato") or "")[:200], "")

    gruppi: dict = {}
    for d in docs:
        forn = (d.get("fornitore") or "").strip()
        if forn and forn.lower() in esclusi:
            continue
        can = _canonico(d)
        chiave = (can or d.get("nome_normalizzato") or "").lower().strip()
        if not chiave:
            continue
        prezzo_riga = d.get("ultimo_prezzo_riga")
        prezzo_kg = d.get("prezzo_kg")
        prezzo = prezzo_riga if prezzo_riga not in (None, 0) else prezzo_kg
        if prezzo in (None, 0):
            continue
        data = d.get("ultima_fattura_data") or d.get("data_fattura") or ""
        row = {
            "fornitore": forn or "?",
            "prezzo": round(float(prezzo), 4),
            "unita": (d.get("ultima_unita_riga") or "").strip() or "kg",
            "prezzo_kg": round(float(prezzo_kg), 4) if prezzo_kg else None,
            "data": data,
            "prodotto_id": d.get("id"),
            "nome_riga": d.get("nome_originale") or d.get("nome_normalizzato") or "",
            "nome_normalizzato": d.get("nome_normalizzato") or "",
            "canonico": can,
        }
        g = gruppi.setdefault(chiave, {"canonico": can, "nome": can or (d.get("nome_normalizzato") or ""), "per_forn": {}})
        if not g["canonico"] and can:
            g["canonico"] = can
            g["nome"] = can
        prev = g["per_forn"].get(forn)
        if not prev or (parse_data_flessibile(data) or date.min) >= (parse_data_flessibile(prev["data"]) or date.min):
            g["per_forn"][forn] = row

    out = []
    for g in gruppi.values():
        righe = list(g["per_forn"].values())
        # cheapest first: confronto equo sul €/kg quando c'è, altrimenti sul prezzo riga
        righe.sort(key=lambda r: (r["prezzo_kg"] if r["prezzo_kg"] else r["prezzo"]))
        out.append({"canonico": g["canonico"], "nome": g["nome"],
                    "senza_canonico": not g["canonico"], "n_fornitori": len(righe), "righe": righe})
    out.sort(key=lambda x: (0 if x["nome"].lower().startswith(q.lower()) else 1, x["nome"].lower()))
    return {"q": q, "prodotti": out[:40]}


@router.get("/confronto-prezzi")
async def confronto_prezzi(
    q: str = Query("", description="Ricerca (motore unico a radici)"),
    categoria: str = Query("", description="Filtra per categoria"),
    solo_confrontabili: bool = Query(False, description="Solo prodotti con almeno 2 fornitori"),
    limit: int = Query(200, ge=1, le=500),
):
    """Confronto prezzi per prodotto canonico sui dati REALI degli acquisti.

    Raggruppa dizionario_prodotti (prezzi solo da fatture XML) per nome
    canonico (nome_canonico > ingrediente_canonico > nome_normalizzato) e per
    ogni gruppo elenca il prezzo più recente di ciascun fornitore.
    Bevande/alcolici (acqua, birre, vino, prosecco, liquori, amari, sciroppi,
    succhi, bibite) NON hanno un prezzo al kg/litro significativo per chi
    acquista: si comprano e si confrontano a CARTONE/UNITÀ, non a peso (un
    rum Bacardi da 2L si paga a bottiglia, non "al chilo" — segnalato da
    Enzo 02/07/2026). Per queste categorie il confronto usa il prezzo di
    fattura per confezione (ultimo_prezzo_fattura), non prezzo_kg.
    Ricerca con stems_ricerca: lo stesso motore di tutte le altre ricerche.
    """
    from app.lotti.routers.utils import stems_ricerca
    from app.lotti.routers.listino import _categoria as _categoria_listino

    filtro: dict = {"prezzo_kg": {"$gt": 0}}
    esclusi = await get_fornitori_esclusi()
    if esclusi:
        filtro["$nor"] = [
            {"fornitore": {"$regex": f"^{re.escape(f)}$", "$options": "i"}}
            for f in esclusi[:50]
        ]
    docs = await db.dizionario_prodotti.find(
        filtro,
        {
            "_id": 0, "nome_normalizzato": 1, "nome_originale": 1,
            "nome_canonico": 1, "ingrediente_canonico": 1, "fornitore": 1,
            "prezzo_kg": 1, "prezzo_confezione": 1, "peso_confezione": 1,
            "unita_confezione": 1, "categoria": 1, "categoria_canonica": 1,
            "ultima_fattura_data": 1, "data_fattura": 1, "conteggio_acquisti": 1,
            "ultimo_prezzo_fattura": 1,
        },
    ).to_list(10000)

    rx_serv = re.compile(
        r"spese|trasporto|bolli|conai|cauzion|omaggi|arrotondament|acconto|buoni pasto",
        re.IGNORECASE,
    )
    # Un fornitore non più usato da mesi non deve competere nel confronto con
    # prezzi "attuali": i listini aumentano, un prezzo vecchio non è più reale.
    cutoff_data = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%d")
    gruppi: dict = {}
    for p in docs:
        nn = (p.get("nome_normalizzato") or "").strip()
        if not nn or rx_serv.search(nn):
            continue
        # Solo nome_canonico (mappatura per singolo prodotto/SKU) o il nome
        # normalizzato: MAI ingrediente_canonico, che è una macro-categoria
        # (es. "Liquori" raggruppa grappa/rum/vodka/gin di marche diverse) —
        # va bene per il costo ricetta ma mescolerebbe prodotti diversi qui.
        nome = (p.get("nome_canonico") or nn).strip()
        forn = (p.get("fornitore") or "Sconosciuto").strip()
        data_raw = str(p.get("ultima_fattura_data") or p.get("data_fattura") or "")
        # normalizza dd/mm/yyyy → ISO: il confronto lessicografico su formati
        # misti eleggeva come "recente" la data col numero di giorno più alto
        mdt = re.match(r"^(\d{2})/(\d{2})/(\d{4})", data_raw)
        data = f"{mdt.group(3)}-{mdt.group(2)}-{mdt.group(1)}" if mdt else data_raw[:10]
        if data and len(data) == 10 and data < cutoff_data:
            continue  # ultima fattura di questo fornitore più vecchia di 3 mesi
        g = gruppi.setdefault(
            nome.lower(),
            {"nome": nome, "categoria": "", "varianti": {}, "acquisti": 0},
        )
        if not g["categoria"]:
            g["categoria"] = (p.get("categoria_canonica") or p.get("categoria") or "").strip()
        g["acquisti"] += int(p.get("conteggio_acquisti") or 0)
        v = g["varianti"].get(forn)
        if not v or data > v["data"]:
            g["varianti"][forn] = {
                "fornitore": forn,
                "nome_fattura": (p.get("nome_originale") or nn).strip(),
                "prezzo_kg": round(float(p["prezzo_kg"]), 4),
                "prezzo_confezione": round(float(p.get("prezzo_confezione") or 0), 4),
                # Prezzo grezzo di fattura per confezione/cartone (sempre presente,
                # aggiornato ad ogni import) — è quello che conta per bevande/alcolici,
                # dove il kg/litro non è l'unità con cui si acquista davvero.
                "prezzo_unita_fattura": round(float(p.get("ultimo_prezzo_fattura") or 0), 4),
                "peso_confezione": p.get("peso_confezione") or 0,
                "unita": (p.get("unita_confezione") or "kg").strip() or "kg",
                "data": data,
            }

    stems = stems_ricerca(q) if q else []
    out = []
    categorie: dict = {}
    for g in gruppi.values():
        cat = (g["categoria"] or _categoria_listino(g["nome"]) or "ALTRO").upper()
        vendita_a_unita = cat in CATEGORIE_VENDUTE_A_UNITA
        chiave_prezzo = "prezzo_unita_fattura" if vendita_a_unita else "prezzo_kg"
        varianti = sorted(
            g["varianti"].values(),
            key=lambda v: v[chiave_prezzo] if v[chiave_prezzo] > 0 else float("inf"),
        )
        if stems:
            testo = " ".join(
                [g["nome"]] + [f"{v['fornitore']} {v['nome_fattura']}" for v in varianti]
            ).lower()
            if not all(s in testo for s in stems):
                continue
        categorie[cat] = categorie.get(cat, 0) + 1
        if solo_confrontabili and len(varianti) < 2:
            continue
        if categoria and categoria.lower() != cat.lower():
            continue
        best, worst = varianti[0], varianti[-1]
        risparmio_pct = (
            round((1 - best[chiave_prezzo] / worst[chiave_prezzo]) * 100)
            if len(varianti) >= 2 and worst[chiave_prezzo] > 0 and best[chiave_prezzo] > 0
            else 0
        )
        out.append({
            "nome": g["nome"],
            "categoria": cat,
            "unita": best["unita"],
            # Bevande/alcolici: si confrontano a cartone/confezione, non a kg/l
            # (Enzo 02/07/2026) — il frontend mostra "€/cartone" invece di "€/kg".
            "vendita_a_unita": vendita_a_unita,
            "n_fornitori": len(varianti),
            "acquisti": g["acquisti"],
            "miglior_fornitore": best["fornitore"],
            "miglior_prezzo_kg": best["prezzo_kg"],
            "miglior_prezzo_confezione": best["prezzo_unita_fattura"],
            "risparmio_pct": risparmio_pct,
            "varianti": varianti,
        })
    out.sort(key=lambda x: (-x["n_fornitori"], -x["acquisti"], x["nome"].lower()))
    return {
        "totale": len(out),
        "prodotti": out[:limit],
        "categorie": sorted(categorie.items(), key=lambda kv: -kv[1]),
    }


@router.get("/semilavorati-acquaviva")
async def get_semilavorati_acquaviva(q: str = Query("", description="Ricerca per nome")):
    """
    Restituisce i prodotti semilavorati Acquaviva dal catalogo prodotti_vendita,
    arricchiti con costo_per_pezzo calcolato dal dizionario.
    Usato nel form ricetta per aggiungere prodotti Acquaviva come ingredienti.
    """
    query: dict = {"fonte": "acquaviva", "attivo": True}
    if q and len(q) >= 2:
        query["nome"] = {"$regex": q, "$options": "i"}

    prodotti = await db.prodotti_vendita.find(query, {"_id": 0}).sort("nome", 1).to_list(500)

    result = []
    for p in prodotti:
        costo_pezzo = float(p.get("costo_produzione") or 0)
        peso_g = float(p.get("peso_pezzo_g") or 0)
        pz_cart = int(p.get("pezzi_cartone") or 0)

        # Se costo_pezzo non disponibile ma abbiamo prezzo_cartone + pz_cart
        if costo_pezzo <= 0 and pz_cart > 0:
            cart = float(p.get("costo_produzione_cartone") or 0)
            if cart > 0:
                costo_pezzo = round(cart / pz_cart, 4)

        # Calcola prezzo_kg equivalente per compatibilità con il form ricette
        prezzo_kg_equiv = 0.0
        if peso_g > 0 and costo_pezzo > 0:
            prezzo_kg_equiv = round(costo_pezzo / (peso_g / 1000), 4)

        result.append(
            {
                "id": p.get("id"),
                "nome_normalizzato": p.get("nome", "").lower(),
                "nome_display": p.get("nome"),
                "fornitore": "Dolciaria Acquaviva",
                "codice": p.get("codice_prodotto", ""),
                "peso_pezzo_g": peso_g,
                "pezzi_cartone": pz_cart,
                "costo_per_pezzo": costo_pezzo,
                "prezzo_kg": prezzo_kg_equiv,
                "immagine_url": p.get("immagine_url", ""),
                "categoria": p.get("categoria", ""),
                "fonte": "acquaviva",
                "is_acquaviva": True,
            }
        )

    return result


@router.post("/dizionario/manuale")
async def aggiungi_prezzo_manuale(data: dict):
    """
    Aggiunge o aggiorna un ingrediente con prezzo manuale nel dizionario.
    Per ingredienti acquistati in contanti o non presenti nelle fatture.
    Payload: { nome, prezzo_kg, note }
    """
    nome = str(data.get("nome", "")).strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome obbligatorio")

    prezzo_kg = float(data.get("prezzo_kg", 0) or 0)
    if prezzo_kg <= 0:
        raise HTTPException(status_code=400, detail="Prezzo/kg deve essere > 0")

    nome_norm = nome.lower().strip()
    doc = {
        "id": str(uuid.uuid4()),
        "nome_originale": nome,
        "nome_normalizzato": nome_norm,
        "peso_confezione": 1.0,
        "unita_confezione": "kg",
        "prezzo_confezione": prezzo_kg,
        "prezzo_kg": prezzo_kg,
        "quantita_totale_kg": 0,
        "quantita_usata_kg": 0,
        "quantita_disponibile_kg": 0,
        "fornitore": data.get("fornitore", "Manuale"),
        "note": data.get("note", "Prezzo inserito manualmente"),
        "data_fattura": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "ultimo_aggiornamento": datetime.now(timezone.utc).isoformat(),
        "inserito_manualmente": True,
    }

    # Upsert per nome_normalizzato
    existing = await db.dizionario_prodotti.find_one(
        {"nome_normalizzato": nome_norm}, {"_id": 0, "id": 1}
    )
    if existing:
        doc["id"] = existing["id"]

    await db.dizionario_prodotti.update_one(
        {"nome_normalizzato": nome_norm}, {"$set": doc}, upsert=True
    )
    return {
        "success": True,
        "prodotto": nome,
        "prezzo_kg": prezzo_kg,
        "aggiornato": existing is not None,
    }


# ── Suggerimento INTELLIGENTE degli ingredienti dal nome della ricetta ──────────
# KB curata (ricette tipiche napoletane/italiane) come base affidabile; se è
# configurata ANTHROPIC_API_KEY si usa Claude per ricette non in elenco.
_INGREDIENTI_TIPICI = {
    # ── Pasticceria napoletana / classica ──
    "sfogliatella": [("Farina", 250, "g"), ("Semola rimacinata", 250, "g"), ("Ricotta", 500, "g"), ("Zucchero", 200, "g"), ("Canditi", 100, "g"), ("Cannella", 2, "g"), ("Strutto", 150, "g"), ("Uova", 1, "pz")],
    "pastiera": [("Grano cotto", 400, "g"), ("Ricotta", 500, "g"), ("Zucchero", 350, "g"), ("Uova", 5, "pz"), ("Canditi", 100, "g"), ("Acqua di fiori d'arancio", 20, "ml"), ("Farina", 250, "g"), ("Strutto", 125, "g")],
    "baba": [("Farina", 250, "g"), ("Uova", 4, "pz"), ("Burro", 80, "g"), ("Zucchero", 30, "g"), ("Lievito di birra", 10, "g"), ("Rum", 100, "ml"), ("Sale", 3, "g")],
    "zeppola": [("Farina", 250, "g"), ("Uova", 4, "pz"), ("Burro", 70, "g"), ("Acqua", 250, "ml"), ("Crema pasticcera", 400, "g"), ("Amarene", 100, "g"), ("Zucchero a velo", 30, "g"), ("Sale", 2, "g")],
    "coda di aragosta": [("Farina", 300, "g"), ("Strutto", 120, "g"), ("Zucchero", 60, "g"), ("Crema pasticcera", 300, "g"), ("Panna", 200, "ml"), ("Zucchero a velo", 20, "g")],
    "cannolo": [("Farina", 250, "g"), ("Ricotta", 500, "g"), ("Zucchero", 180, "g"), ("Gocce di cioccolato", 80, "g"), ("Canditi", 50, "g"), ("Strutto", 50, "g"), ("Marsala", 30, "ml"), ("Pistacchi", 30, "g")],
    "delizia al limone": [("Pan di Spagna", 400, "g"), ("Limoni", 3, "pz"), ("Panna", 300, "ml"), ("Latte", 250, "ml"), ("Uova", 3, "pz"), ("Zucchero", 180, "g"), ("Limoncello", 40, "ml"), ("Farina", 60, "g")],
    "caprese": [("Mandorle", 250, "g"), ("Cioccolato fondente", 200, "g"), ("Burro", 200, "g"), ("Zucchero", 200, "g"), ("Uova", 5, "pz"), ("Cacao amaro", 20, "g")],
    "cassata": [("Pan di Spagna", 300, "g"), ("Ricotta", 500, "g"), ("Zucchero", 250, "g"), ("Canditi", 150, "g"), ("Pasta di mandorle", 200, "g"), ("Gocce di cioccolato", 80, "g"), ("Zucchero a velo", 100, "g")],
    "graffa": [("Farina", 400, "g"), ("Patate", 200, "g"), ("Uova", 2, "pz"), ("Burro", 80, "g"), ("Zucchero", 150, "g"), ("Lievito di birra", 15, "g"), ("Latte", 100, "ml"), ("Sale", 5, "g")],
    "struffoli": [("Farina", 400, "g"), ("Uova", 4, "pz"), ("Zucchero", 50, "g"), ("Miele", 300, "g"), ("Burro", 50, "g"), ("Canditi", 80, "g"), ("Confettini colorati", 40, "g"), ("Limoni", 1, "pz")],
    "roccoco": [("Farina", 400, "g"), ("Mandorle", 200, "g"), ("Zucchero", 300, "g"), ("Canditi", 100, "g"), ("Pisto (spezie)", 10, "g"), ("Ammoniaca per dolci", 5, "g"), ("Acqua", 80, "ml")],
    "mostacciolo": [("Farina", 400, "g"), ("Zucchero", 200, "g"), ("Miele", 100, "g"), ("Cacao amaro", 50, "g"), ("Pisto (spezie)", 10, "g"), ("Cioccolato fondente", 300, "g"), ("Ammoniaca per dolci", 5, "g")],
    "migliaccio": [("Semolino", 200, "g"), ("Ricotta", 350, "g"), ("Latte", 500, "ml"), ("Uova", 4, "pz"), ("Zucchero", 250, "g"), ("Burro", 50, "g"), ("Limoni", 1, "pz"), ("Vaniglia", 2, "g")],
    "chiacchiere": [("Farina", 500, "g"), ("Uova", 3, "pz"), ("Zucchero", 70, "g"), ("Burro", 50, "g"), ("Vino bianco", 40, "ml"), ("Zucchero a velo", 60, "g"), ("Sale", 3, "g")],
    "fiocco di neve": [("Farina", 350, "g"), ("Latte", 200, "ml"), ("Zucchero", 90, "g"), ("Lievito di birra", 10, "g"), ("Ricotta", 250, "g"), ("Panna", 200, "ml"), ("Zucchero a velo", 40, "g")],
    "pasticciotto": [("Farina", 500, "g"), ("Strutto", 200, "g"), ("Zucchero", 200, "g"), ("Uova", 4, "pz"), ("Crema pasticcera", 500, "g"), ("Amarene", 80, "g")],
    "diplomatico": [("Pasta sfoglia", 400, "g"), ("Pan di Spagna", 300, "g"), ("Crema pasticcera", 500, "g"), ("Panna", 150, "ml"), ("Bagna al liquore", 80, "ml"), ("Zucchero a velo", 40, "g")],
    "millefoglie": [("Pasta sfoglia", 500, "g"), ("Crema pasticcera", 500, "g"), ("Panna", 250, "ml"), ("Zucchero a velo", 50, "g")],
    "profiterole": [("Farina", 150, "g"), ("Uova", 4, "pz"), ("Burro", 100, "g"), ("Acqua", 250, "ml"), ("Panna", 400, "ml"), ("Cioccolato fondente", 300, "g"), ("Zucchero", 80, "g")],
    "bigne": [("Farina", 150, "g"), ("Uova", 4, "pz"), ("Burro", 100, "g"), ("Acqua", 250, "ml"), ("Crema pasticcera", 400, "g"), ("Sale", 2, "g")],
    "crostata": [("Farina", 400, "g"), ("Burro", 200, "g"), ("Zucchero", 160, "g"), ("Uova", 2, "pz"), ("Confettura", 350, "g"), ("Limoni", 1, "pz"), ("Sale", 2, "g")],
    "torta di mele": [("Farina", 300, "g"), ("Mele", 4, "pz"), ("Uova", 3, "pz"), ("Zucchero", 180, "g"), ("Burro", 120, "g"), ("Latte", 100, "ml"), ("Lievito per dolci", 16, "g"), ("Cannella", 2, "g")],
    "strudel": [("Pasta sfoglia", 400, "g"), ("Mele", 4, "pz"), ("Zucchero", 100, "g"), ("Uvetta", 60, "g"), ("Pinoli", 40, "g"), ("Cannella", 3, "g"), ("Pangrattato", 40, "g"), ("Burro", 50, "g")],
    "tiramisu": [("Savoiardi", 300, "g"), ("Mascarpone", 500, "g"), ("Uova", 4, "pz"), ("Zucchero", 100, "g"), ("Caffe espresso", 300, "ml"), ("Cacao amaro", 20, "g")],
    "cheesecake": [("Biscotti secchi", 250, "g"), ("Burro", 120, "g"), ("Formaggio spalmabile", 500, "g"), ("Panna", 200, "ml"), ("Zucchero", 150, "g"), ("Gelatina in fogli", 10, "g"), ("Confettura", 150, "g")],
    "sacher": [("Cioccolato fondente", 350, "g"), ("Burro", 150, "g"), ("Uova", 6, "pz"), ("Zucchero", 150, "g"), ("Farina", 150, "g"), ("Confettura di albicocche", 200, "g")],
    "torta della nonna": [("Farina", 400, "g"), ("Burro", 200, "g"), ("Zucchero", 200, "g"), ("Uova", 3, "pz"), ("Crema pasticcera", 500, "g"), ("Pinoli", 60, "g"), ("Zucchero a velo", 30, "g")],
    "pan di spagna": [("Uova", 6, "pz"), ("Zucchero", 180, "g"), ("Farina", 180, "g"), ("Vaniglia", 2, "g"), ("Sale", 2, "g")],
    "crema pasticcera": [("Latte", 500, "ml"), ("Uova", 4, "pz"), ("Zucchero", 150, "g"), ("Amido di mais", 40, "g"), ("Vaniglia", 2, "g"), ("Limoni", 1, "pz")],
    "crema chantilly": [("Panna", 500, "ml"), ("Zucchero a velo", 80, "g"), ("Vaniglia", 2, "g")],
    "mousse al cioccolato": [("Cioccolato fondente", 300, "g"), ("Panna", 400, "ml"), ("Uova", 3, "pz"), ("Zucchero", 80, "g"), ("Burro", 40, "g")],
    "semifreddo": [("Panna", 500, "ml"), ("Uova", 4, "pz"), ("Zucchero", 150, "g"), ("Meringa", 100, "g")],
    "plumcake": [("Farina", 300, "g"), ("Burro", 180, "g"), ("Zucchero", 180, "g"), ("Uova", 4, "pz"), ("Latte", 80, "ml"), ("Lievito per dolci", 16, "g"), ("Vaniglia", 2, "g")],
    "muffin": [("Farina", 300, "g"), ("Zucchero", 150, "g"), ("Uova", 2, "pz"), ("Burro", 120, "g"), ("Latte", 150, "ml"), ("Lievito per dolci", 16, "g"), ("Gocce di cioccolato", 120, "g")],
    "ciambellone": [("Farina", 400, "g"), ("Uova", 4, "pz"), ("Zucchero", 250, "g"), ("Olio di semi", 120, "ml"), ("Latte", 150, "ml"), ("Lievito per dolci", 16, "g"), ("Limoni", 1, "pz")],
    "brioche": [("Farina", 500, "g"), ("Uova", 3, "pz"), ("Burro", 150, "g"), ("Zucchero", 90, "g"), ("Latte", 150, "ml"), ("Lievito di birra", 15, "g"), ("Sale", 8, "g")],
    "cornetto": [("Farina", 500, "g"), ("Burro", 250, "g"), ("Zucchero", 60, "g"), ("Lievito di birra", 15, "g"), ("Uova", 1, "pz"), ("Latte", 150, "ml"), ("Sale", 10, "g")],
    "croissant": [("Farina", 500, "g"), ("Burro", 280, "g"), ("Zucchero", 55, "g"), ("Lievito di birra", 15, "g"), ("Latte", 150, "ml"), ("Sale", 10, "g")],
    "veneziana": [("Farina", 500, "g"), ("Burro", 120, "g"), ("Zucchero", 120, "g"), ("Uova", 3, "pz"), ("Lievito di birra", 15, "g"), ("Crema pasticcera", 300, "g"), ("Granella di zucchero", 50, "g")],
    "tronchetto": [("Pan di Spagna", 400, "g"), ("Panna", 300, "ml"), ("Cioccolato fondente", 250, "g"), ("Burro", 100, "g"), ("Zucchero", 100, "g"), ("Cacao amaro", 20, "g")],
    "zuppa inglese": [("Pan di Spagna", 400, "g"), ("Crema pasticcera", 500, "g"), ("Cacao amaro", 30, "g"), ("Alchermes", 80, "ml"), ("Panna", 150, "ml")],
    # ── Rosticceria napoletana ──
    "arancino": [("Riso", 500, "g"), ("Ragu", 300, "g"), ("Piselli", 100, "g"), ("Fiordilatte", 150, "g"), ("Uova", 2, "pz"), ("Pangrattato", 150, "g"), ("Parmigiano", 80, "g"), ("Olio di semi", 500, "ml")],
    "crocche": [("Patate", 800, "g"), ("Uova", 2, "pz"), ("Fiordilatte", 150, "g"), ("Parmigiano", 60, "g"), ("Prezzemolo", 10, "g"), ("Pangrattato", 150, "g"), ("Olio di semi", 500, "ml"), ("Sale", 8, "g")],
    "frittatina": [("Pasta (bucatini)", 400, "g"), ("Besciamella", 300, "g"), ("Piselli", 100, "g"), ("Prosciutto cotto", 100, "g"), ("Fiordilatte", 100, "g"), ("Uova", 2, "pz"), ("Pangrattato", 150, "g"), ("Olio di semi", 500, "ml")],
    "rustico": [("Pasta sfoglia", 400, "g"), ("Prosciutto cotto", 150, "g"), ("Fiordilatte", 200, "g"), ("Uova", 1, "pz")],
    "pizzetta": [("Farina", 500, "g"), ("Pomodoro", 300, "g"), ("Fiordilatte", 200, "g"), ("Lievito di birra", 10, "g"), ("Olio extravergine", 30, "ml"), ("Sale", 10, "g")],
    "panzerotto": [("Farina", 500, "g"), ("Pomodoro", 250, "g"), ("Fiordilatte", 250, "g"), ("Lievito di birra", 10, "g"), ("Olio di semi", 500, "ml"), ("Sale", 10, "g")],
    "casatiello": [("Farina", 500, "g"), ("Strutto", 150, "g"), ("Salame", 150, "g"), ("Formaggio (provolone)", 150, "g"), ("Pecorino", 80, "g"), ("Uova", 4, "pz"), ("Lievito di birra", 15, "g"), ("Pepe", 5, "g"), ("Sale", 10, "g")],
    "tortano": [("Farina", 500, "g"), ("Strutto", 150, "g"), ("Salame", 150, "g"), ("Formaggio (provolone)", 150, "g"), ("Uova sode", 3, "pz"), ("Lievito di birra", 15, "g"), ("Pepe", 5, "g"), ("Sale", 10, "g")],
    "danubio": [("Farina", 500, "g"), ("Latte", 200, "ml"), ("Burro", 80, "g"), ("Uova", 2, "pz"), ("Prosciutto cotto", 150, "g"), ("Formaggio (provolone)", 150, "g"), ("Lievito di birra", 12, "g"), ("Zucchero", 20, "g"), ("Sale", 8, "g")],
    "parigina": [("Farina", 500, "g"), ("Pomodoro", 250, "g"), ("Prosciutto cotto", 150, "g"), ("Fiordilatte", 200, "g"), ("Pasta sfoglia", 300, "g"), ("Lievito di birra", 10, "g"), ("Sale", 10, "g")],
    "panino napoletano": [("Farina", 500, "g"), ("Strutto", 100, "g"), ("Salame", 120, "g"), ("Prosciutto cotto", 120, "g"), ("Formaggio (provolone)", 150, "g"), ("Uova", 2, "pz"), ("Lievito di birra", 12, "g"), ("Pepe", 4, "g")],
    # ── Bar ──
    "caffe freddo": [("Caffe espresso", 300, "ml"), ("Zucchero", 60, "g"), ("Acqua", 200, "ml")],
    "crema di caffe": [("Caffe espresso", 200, "ml"), ("Panna", 250, "ml"), ("Zucchero", 100, "g")],
    "granita di limone": [("Limoni", 4, "pz"), ("Zucchero", 200, "g"), ("Acqua", 500, "ml")],
    "cioccolata calda": [("Latte", 500, "ml"), ("Cacao amaro", 50, "g"), ("Cioccolato fondente", 100, "g"), ("Zucchero", 60, "g"), ("Amido di mais", 15, "g")],
}

# Parole vuote che non distinguono una ricetta dall'altra nel match KB
_KB_STOPWORDS = {"di", "al", "alla", "allo", "ai", "agli", "alle", "con", "e", "ed",
                 "la", "il", "lo", "le", "gli", "un", "una", "del", "della", "in", "da", "per"}


def _norm_kb(s: str) -> str:
    import unicodedata as _u
    s = _u.normalize("NFD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9 ]+", " ", s).strip()


def _radice_kb(parola: str) -> str:
    """Radice grezza per far combaciare singolare/plurale/genere italiani:
    'coda'/'code' → 'cod', 'pistacchio'/'pistacchi' → 'pistacc' (le vocali
    finali cadono a scalare, poi la h dei plurali in -chi/-ghe:
    'fiocco'/'fiocchi' → 'fiocc')."""
    r = parola
    while len(r) > 3 and r[-1] in "aeiou":
        r = r[:-1]
    if len(r) > 3 and r.endswith("h"):
        r = r[:-1]
    return r


def _radici_kb(s: str) -> set:
    return {_radice_kb(w) for w in _norm_kb(s).split() if w and w not in _KB_STOPWORDS}


def _kb_lookup(nome: str):
    """Cerca la ricetta in base curata. Un'entrata combacia se TUTTE le sue
    parole significative compaiono nel nome (per radice: 'code di aragosta
    al cioccolato' → 'coda di aragosta'). Vince l'entrata più specifica."""
    n = _norm_kb(nome)
    radici_nome = _radici_kb(nome)
    migliore, specificita = None, 0
    for k, v in _INGREDIENTI_TIPICI.items():
        radici_k = _radici_kb(k)
        combacia = (k in n) or (n and n in k) or (radici_k and radici_k <= radici_nome)
        if combacia and len(radici_k) > specificita:
            migliore, specificita = v, len(radici_k)
    if migliore:
        return [{"nome": a, "quantita": b, "unita": c} for a, b, c in migliore]
    return None


# ── Gusti/farciture letti dal NOME (Enzo 23/07/2026: "babà panna e pistacchio
# → dovevi inserire la panna e il pistacchio"). Parola nel nome → ingrediente
# da AGGIUNGERE alla proposta base. Le chiavi vengono ridotte a radice con la
# STESSA funzione usata sul nome, così singolare/plurale combaciano sempre.
_GUSTI_PAROLE = {
    # dolce
    "pistacchio": ("Pistacchio", 150, "g"),
    "panna": ("Panna", 200, "ml"),
    "nocciola": ("Nocciole", 150, "g"),
    "nutella": ("Crema di nocciole", 150, "g"),
    "gianduia": ("Crema di nocciole", 150, "g"),
    "amarena": ("Amarene", 100, "g"),
    "fragola": ("Fragole", 150, "g"),
    "fragoline": ("Fragoline", 150, "g"),
    "limone": ("Limoni", 1, "pz"),
    "limoncello": ("Limoncello", 50, "ml"),
    "caffe": ("Caffe espresso", 100, "ml"),
    "crema": ("Crema pasticcera", 300, "g"),
    "ricotta": ("Ricotta", 250, "g"),
    "cioccolato": ("Cioccolato fondente", 150, "g"),
    "mela": ("Mele", 2, "pz"),
    "albicocca": ("Confettura di albicocche", 150, "g"),
    "bosco": ("Frutti di bosco", 150, "g"),
    "mandorla": ("Mandorle", 100, "g"),
    "cocco": ("Cocco", 80, "g"),
    "vaniglia": ("Vaniglia", 2, "g"),
    "miele": ("Miele", 80, "g"),
    "yogurt": ("Yogurt", 250, "g"),
    "cannella": ("Cannella", 3, "g"),
    "marmellata": ("Confettura", 200, "g"),
    "confettura": ("Confettura", 200, "g"),
    "castagna": ("Crema di castagne", 150, "g"),
    "zabaione": ("Zabaione", 200, "g"),
    "ciliegia": ("Ciliegie", 100, "g"),
    "rum": ("Rum", 50, "ml"),
    # salato
    "wurstel": ("Wurstel", 200, "g"),
    "friarielli": ("Friarielli", 200, "g"),
    "salsiccia": ("Salsiccia", 200, "g"),
    "funghi": ("Funghi", 150, "g"),
    "prosciutto": ("Prosciutto cotto", 100, "g"),
    "spinaci": ("Spinaci", 150, "g"),
    "zucchine": ("Zucchine", 150, "g"),
    "melanzane": ("Melanzane", 150, "g"),
    "scarola": ("Scarola", 200, "g"),
    "salmone": ("Salmone", 100, "g"),
    "tonno": ("Tonno", 100, "g"),
    "carciofi": ("Carciofi", 150, "g"),
    "pomodorini": ("Pomodorini", 150, "g"),
}

# radice → ingrediente (stessa riduzione applicata al nome della ricetta)
_GUSTI_NOME = {_radice_kb(k): v for k, v in _GUSTI_PAROLE.items()}


def _arricchisci_da_nome(nome: str, ingredienti: list) -> list:
    """Aggiunge alla proposta gli ingredienti DETTATI DAL NOME della ricetta
    ("babà panna e pistacchio" → base babà + Panna + Pistacchio), saltando
    quelli già presenti (per radice: 'Rum' non si raddoppia su 'babà al rum')."""
    if not ingredienti:
        return ingredienti
    radici_nome = _radici_kb(nome)
    radici_presenti = set()
    for i in ingredienti:
        radici_presenti |= _radici_kb(i.get("nome") or "")
    # caso speciale: "cioccolato bianco" non deve diventare fondente
    bianco = "bianc" in radici_nome
    extra = []
    for radice, (nome_ing, qta, unita) in _GUSTI_NOME.items():
        if radice not in radici_nome:
            continue
        if radice == "cioccolat" and bianco:
            nome_ing = "Cioccolato bianco"
        radici_ing = _radici_kb(nome_ing)
        if radice in radici_presenti or (radici_ing & radici_presenti):
            continue  # c'è già nella base (es. la coda di aragosta ha già la panna)
        extra.append({"nome": nome_ing, "quantita": qta, "unita": unita})
        radici_presenti |= radici_ing
        if len(extra) >= 4:
            break
    return ingredienti + extra


class SuggerisciReq(BaseModel):
    nome_ricetta: str
    porzioni: int = 10


async def _proponi_ingredienti_per_nome(nome: str, porzioni: int = 10) -> dict:
    """Motore unico della proposta ingredienti dal NOME della ricetta.
    Ordine delle fonti: 1) Claude (se ANTHROPIC_API_KEY è configurata);
    2) base curata delle ricette napoletane; 3) la ricetta PIÙ SIMILE già in
    archivio. In coda, i gusti scritti nel nome entrano sempre.
    Estratto dall'endpoint (25/07/2026) per riusarlo nella compilazione di
    massa: unica logica, un solo posto da correggere."""
    import os

    class _R:  # compat con il corpo storico (req.porzioni)
        pass

    req = _R()
    req.porzioni = porzioni

    ingredienti = None
    fonte = "kb"
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        try:
            import asyncio
            from anthropic import Anthropic
            # timeout esplicito: senza, una chiamata appesa tiene il bottone
            # «Proponi» su "Penso…" per sempre (l'utente la vede come rotta)
            client = Anthropic(api_key=key, timeout=25.0, max_retries=1)
            prompt = (
                f"Sei un esperto di pasticceria e rosticceria italiana e napoletana. "
                f"Per la ricetta \"{nome}\" elenca gli ingredienti tipici per circa {req.porzioni} porzioni. "
                f"Rispondi SOLO con un array JSON di oggetti con chiavi: nome (stringa), quantita (numero), "
                f"unita (g, ml oppure pz). Nessun testo prima o dopo l'array."
            )
            # client sincrono: la chiamata (secondi) va in un thread, non deve
            # bloccare l'event loop dell'intera app
            msg = await asyncio.to_thread(
                client.messages.create,
                model="claude-haiku-4-5-20251001",
                max_tokens=700,
                messages=[{"role": "user", "content": prompt}],
            )
            txt = "".join(getattr(b, "text", "") for b in msg.content)
            m = re.search(r"\[.*\]", txt, re.S)
            if m:
                arr = _json.loads(m.group(0))
                ingredienti = [
                    {"nome": str(x.get("nome", "")).strip(),
                     "quantita": float(x.get("quantita") or 0),
                     "unita": str(x.get("unita") or "g")}
                    for x in arr if x.get("nome")
                ] or None
                fonte = "ai"
            else:
                logging.getLogger("uvicorn.error").warning(
                    f"[AI ingredienti] '{nome}': risposta senza array JSON: {txt[:200]!r}")
        except Exception as e:
            logging.getLogger("uvicorn.error").warning(f"[AI ingredienti] '{nome}': {type(e).__name__}: {e}")
    else:
        logging.getLogger("uvicorn.error").warning("[AI ingredienti] ANTHROPIC_API_KEY non configurata: uso solo base curata")

    if not ingredienti:
        ingredienti = _kb_lookup(nome)
        fonte = "kb"

    if not ingredienti:
        # FALLBACK DALLE RICETTE DI ENZO (23/07/2026: "se clicco proponi per
        # alcuni dolci non mi permette di inserire in automatico"): quando AI
        # e base curata non conoscono il dolce, si propone la ricetta PIÙ
        # SIMILE già in archivio (es. "coda di aragosta al cioccolato" parte
        # dagli ingredienti di "coda di aragosta alla panna"). La fonte è
        # dichiarata nel messaggio, così si vede da dove arrivano.
        parole = {p for p in re.split(r"[^a-zà-ù0-9]+", nome.lower()) if len(p) > 3}
        if parole:
            tutte = await db.ricette.find(
                {"ingredienti_dettaglio.0": {"$exists": True}},
                {"_id": 0, "nome": 1, "ingredienti_dettaglio": 1},
            ).to_list(3000)
            migliore, punteggio = None, 0
            for r in tutte:
                if (r.get("nome") or "").strip().lower() == nome.lower():
                    continue  # mai proporre la ricetta a se stessa
                rp = {p for p in re.split(r"[^a-zà-ù0-9]+", (r.get("nome") or "").lower()) if len(p) > 3}
                s = len(rp & parole)
                if s > punteggio:
                    migliore, punteggio = r, s
            # con 2+ parole significative nel nome servono almeno 2 parole in
            # comune ("torta di mele" NON deve pescare "torta caprese")
            soglia = 2 if len(parole) >= 2 else 1
            if migliore and punteggio >= soglia:
                ingredienti = [
                    {"nome": (i.get("nome") or "").strip(),
                     "quantita": float(i.get("quantita") or 0),
                     "unita": i.get("unita_misura") or i.get("unita") or "g"}
                    for i in migliore.get("ingredienti_dettaglio") or []
                    if (i.get("nome") or "").strip()
                ]
                fonte = f"dalla tua ricetta «{migliore['nome']}»"

    if not ingredienti:
        return {"ok": False, "fonte": "nessuna", "ingredienti": [],
                "messaggio": "Nessun suggerimento automatico: aggiungi gli ingredienti a mano (l'autocomplete pesca dalle fatture)."}
    # I gusti scritti nel NOME entrano sempre nella proposta ("babà panna e
    # pistacchio" → base babà + Panna + Pistacchio), qualunque sia la fonte.
    ingredienti = _arricchisci_da_nome(nome, ingredienti)
    return {"ok": True, "fonte": fonte, "ingredienti": ingredienti[:20]}


@router.post("/suggerisci-ingredienti")
async def suggerisci_ingredienti(req: SuggerisciReq):
    """Propone gli ingredienti tipici di una ricetta dal suo NOME (intelligenza):
    es. 'sfogliatella' → semola, ricotta, zucchero... Usa Claude se la chiave è
    configurata, altrimenti una base curata. Best-effort: non solleva."""
    nome = (req.nome_ricetta or "").strip()
    if not nome:
        raise HTTPException(400, "Nome ricetta mancante")
    return await _proponi_ingredienti_per_nome(nome, req.porzioni or 10)


# ── Compilazione di MASSA (richiesta Enzo 25/07/2026) ────────────────────────
# ── Normalizzazione a 1 kg dell'ingrediente base (richiesta Enzo 25/07/2026)
# "se trovi 150 g di farina la porti a 1 kg; se trovi 500 g di riso lo porti a
# 1 kg — così per bucatini, ragù, besciamella…". Serve a lavorare con dosi da
# laboratorio invece che con le dosi domestiche delle ricette trovate.
#
# L'ingrediente BASE è quello che REGGE la preparazione, e nella pratica è
# quello che pesa di più: nella besciamella il latte (500 g) e non la farina
# (50 g), negli arancini il riso (500 g) e non la farina della panatura.
# L'elenco qui sotto NON è una priorità assoluta (sarebbe sbagliato: darebbe
# la farina alla besciamella) ma serve solo a decidere quando due ingredienti
# pesano quasi uguale — a parità, vince quello che dà il nome alla lavorazione.
INGREDIENTI_BASE_PRIORITA = [
    # primi piatti / rosticceria
    "riso", "bucatini", "spaghetti", "pasta", "paccheri", "ziti", "penne",
    "patate", "melanzane",
    # impasti
    "farina", "semola", "semolino", "farina 00",
    # creme e salse
    "latte", "besciamella", "passata", "pomodoro", "carne macinata", "macinato",
    "ricotta", "panna", "mascarpone", "cioccolato",
    # base dolci
    "zucchero", "burro", "uova",
]

# Unità che pesano: solo su queste ha senso il riferimento "1 kg"
_UNITA_PESO_NORM = {"g", "gr", "grammi", "kg", "ml", "l", "lt", "litri", "cl"}


def _in_grammi(quantita: float, unita: str) -> float:
    """Quantità in grammi (i liquidi 1:1, come nel resto dell'app)."""
    u = (unita or "g").lower().strip()
    if u in ("kg", "l", "lt", "litri"):
        return float(quantita) * 1000
    if u == "cl":
        return float(quantita) * 10
    if u in ("g", "gr", "grammi", "ml"):
        return float(quantita)
    return 0.0


def _priorita_nome(nome: str) -> int:
    """Posizione nell'elenco dei nomi noti (più basso = più "base"). 999 se
    sconosciuto: serve solo a decidere le parità di peso."""
    n = (nome or "").lower()
    for idx, chiave in enumerate(INGREDIENTI_BASE_PRIORITA):
        if chiave in n:
            return idx
    return 999


def _scegli_ingrediente_base(ingredienti: list[dict]) -> dict | None:
    """L'ingrediente su cui si calcola il riferimento di 1 kg: quello che pesa
    di più. A parità sostanziale di peso (entro il 20%) vince quello che dà il
    nome alla lavorazione, secondo INGREDIENTI_BASE_PRIORITA."""
    pesabili = [
        i for i in ingredienti
        if (i.get("unita") or i.get("unita_misura") or "g").lower().strip() in _UNITA_PESO_NORM
        and float(i.get("quantita") or 0) > 0
    ]
    if not pesabili:
        return None
    peso = lambda i: _in_grammi(i.get("quantita") or 0, i.get("unita") or i.get("unita_misura"))  # noqa: E731
    massimo = max(peso(i) for i in pesabili)
    # candidati "quasi pari" al più pesante: fra questi decide il nome
    vicini = [i for i in pesabili if peso(i) >= massimo * 0.8]
    return min(vicini, key=lambda i: (_priorita_nome(i.get("nome")), -peso(i)))


def normalizza_a_un_kg(ingredienti: list[dict], riferimento_g: float = 1000.0) -> dict:
    """Riscala TUTTE le quantità così che l'ingrediente base arrivi a 1 kg.

    Esempi voluti dal titolare: 150 g di farina → 1 kg (tutto ×6,67);
    500 g di riso → 1 kg (tutto ×2).
    Gli ingredienti a pezzi vengono moltiplicati e arrotondati a intero (mai
    sotto 1). Ritorna {ingredienti, base, fattore}: se non c'è una base
    pesabile non si tocca niente (mai conversioni inventate)."""
    base = _scegli_ingrediente_base(ingredienti or [])
    if not base:
        return {"ingredienti": ingredienti, "base": None, "fattore": 1.0}
    base_g = _in_grammi(base.get("quantita") or 0, base.get("unita") or base.get("unita_misura"))
    if base_g <= 0:
        return {"ingredienti": ingredienti, "base": None, "fattore": 1.0}
    fattore = riferimento_g / base_g
    if abs(fattore - 1.0) < 0.01:
        return {"ingredienti": ingredienti, "base": base.get("nome"), "fattore": 1.0}

    fuori = []
    for i in ingredienti:
        q = float(i.get("quantita") or 0)
        u = (i.get("unita") or i.get("unita_misura") or "g").lower().strip()
        nuovo = dict(i)
        if q > 0:
            if u in _UNITA_PESO_NORM:
                val = q * fattore
                nuovo["quantita"] = round(val, 1 if val < 100 else 0)
            else:
                # pezzi/confezioni: si moltiplicano e si arrotondano
                nuovo["quantita"] = max(1, int(round(q * fattore)))
        fuori.append(nuovo)
    return {"ingredienti": fuori, "base": base.get("nome"), "fattore": round(fattore, 3)}


class DoseProduzioneReq(BaseModel):
    """Quanto se ne produce OGGI, espresso sull'ingrediente di riferimento."""
    quantita_base: float
    unita: str = "kg"


@router.post("/ricetta/{ricetta_id}/dose-produzione")
async def dose_produzione(ricetta_id: str, req: DoseProduzioneReq):
    """Riscala TUTTA la ricetta a partire da quanto ingrediente base si usa
    oggi (richiesta Enzo 25/07/2026: "6,5 kg di farina per i cornetti e tutto
    il resto si adegua"). NON salva nulla: è il conto per il banco di lavoro.

    L'ingrediente di riferimento è lo stesso della normalizzazione a 1 kg:
    quello che pesa di più (farina per i cornetti, bucatini per le frittatine,
    riso per gli arancini, latte per la crema)."""
    ric = await db.ricette.find_one({"id": ricetta_id}, {"_id": 0})
    if not ric:
        raise HTTPException(404, "Ricetta non trovata")
    ingredienti = [
        {"nome": i.get("nome"), "quantita": i.get("quantita"),
         "unita": i.get("unita_misura") or i.get("unita") or "g"}
        for i in (ric.get("ingredienti_dettaglio") or [])
        if (i.get("nome") or "").strip()
    ]
    if not ingredienti:
        raise HTTPException(400, "La ricetta non ha ingredienti con dosi")

    grammi_voluti = _in_grammi(req.quantita_base, req.unita)
    if grammi_voluti <= 0:
        raise HTTPException(400, "Indica quanto ingrediente base usi oggi (kg o g)")

    norm = normalizza_a_un_kg(ingredienti, riferimento_g=grammi_voluti)
    if not norm["base"]:
        raise HTTPException(
            400,
            "Non riesco a capire l'ingrediente di riferimento: nessun ingrediente "
            "ha un peso (kg/g/l/ml). Correggi le dosi della ricetta.",
        )
    porzioni_base = float(ric.get("porzioni") or 1) or 1
    return {
        "ricetta": ric.get("nome"),
        "base": norm["base"],
        "fattore": norm["fattore"],
        "porzioni_stimate": max(1, int(round(porzioni_base * norm["fattore"]))),
        "ingredienti": norm["ingredienti"],
    }


def _ricetta_e_rivendita(r: dict) -> bool:
    """Prodotto COMPRATO e rivenduto (colazione, gelati confezionati…): non ha
    una ricetta da compilare, va saltato."""
    return bool(r.get("fornitore_rivendita") or r.get("rivendita") or r.get("acquistato"))


@router.get("/ricette-senza-ingredienti")
def _ricetta_senza_quantita(r: dict) -> bool:
    """Ha gli ingredienti ma NESSUNA quantità utile: il food cost non si può
    calcolare (richiesta Enzo 25/07/2026: vanno compilate anche queste)."""
    det = r.get("ingredienti_dettaglio") or []
    if not det:
        return False
    return not any(float(i.get("quantita") or 0) > 0 for i in det)


async def ricette_senza_ingredienti():
    """Elenco delle ricette da compilare, escluse quelle di rivendita:
    - motivo "senza_ingredienti": non hanno proprio ingredienti;
    - motivo "senza_quantita": hanno gli ingredienti ma nessuna dose."""
    tutte = await db.ricette.find(
        {}, {"_id": 0, "id": 1, "nome": 1, "reparto": 1, "porzioni": 1,
             "ingredienti_dettaglio": 1, "ingredienti": 1,
             "fornitore_rivendita": 1, "rivendita": 1, "acquistato": 1},
    ).to_list(5000)
    vuote = []
    for r in tutte:
        if _ricetta_e_rivendita(r):
            continue
        if not (r.get("ingredienti_dettaglio") or r.get("ingredienti")):
            motivo = "senza_ingredienti"
        elif _ricetta_senza_quantita(r):
            motivo = "senza_quantita"
        else:
            continue
        vuote.append({"id": r.get("id"), "nome": r.get("nome"),
                      "reparto": r.get("reparto") or "", "motivo": motivo})
    return {
        "totale_ricette": len(tutte),
        "da_compilare": len(vuote),
        "senza_ingredienti": sum(1 for v in vuote if v["motivo"] == "senza_ingredienti"),
        "senza_quantita": sum(1 for v in vuote if v["motivo"] == "senza_quantita"),
        "ricette": vuote,
    }


class ProponiTutteReq(BaseModel):
    limite: int = 15          # quante ricette per chiamata (l'AI impiega secondi)
    solo_anteprima: bool = False
    # Porta l'ingrediente base a 1 kg (150 g di farina → 1 kg, 500 g di riso →
    # 1 kg…): dosi da laboratorio invece che dosi domestiche.
    normalizza_un_kg: bool = True


@router.post("/proponi-ingredienti-tutte")
async def proponi_ingredienti_tutte(req: ProponiTutteReq, _admin=Depends(require_admin)):
    """Compila in automatico gli ingredienti delle ricette che ne sono PRIVE,
    usando lo stesso motore del bottone «Proponi» (Claude → base curata →
    ricetta più simile in archivio).

    Regole (volute dal titolare):
      - NON tocca mai una ricetta che ha già ingredienti: nessuna sovrascrittura;
      - salta i prodotti di rivendita (comprati, non preparati);
      - ogni ricetta compilata resta marcata `ingredienti_origine="automatica"`
        con la fonte e la data, così si vede cosa è stato proposto dalla
        macchina e va ricontrollato;
      - lavora a blocchi (`limite`) perché ogni proposta AI richiede secondi:
        il frontend richiama finché `restanti` non è 0.
    """
    elenco = await ricette_senza_ingredienti()
    da_fare = elenco["ricette"]
    if req.solo_anteprima:
        return {"da_compilare": len(da_fare), "ricette": da_fare[: req.limite], "compilate": 0}

    blocco = da_fare[: max(1, min(req.limite, 50))]
    compilate, senza_proposta = [], []
    for r in blocco:
        nome = (r.get("nome") or "").strip()
        if not nome:
            continue
        doc = await db.ricette.find_one({"id": r["id"]}, {"_id": 0, "porzioni": 1})
        porzioni = int(float((doc or {}).get("porzioni") or 10) or 10)
        esito = await _proponi_ingredienti_per_nome(nome, porzioni)
        ingredienti = esito.get("ingredienti") or []
        if not ingredienti:
            senza_proposta.append(nome)
            continue

        # DOSI DA LABORATORIO: l'ingrediente base sale a 1 kg e tutto il resto
        # si riscala di conseguenza (Enzo 25/07/2026).
        base, fattore = None, 1.0
        if req.normalizza_un_kg:
            norm = normalizza_a_un_kg(ingredienti)
            ingredienti = norm["ingredienti"]
            base, fattore = norm["base"], norm["fattore"]

        campi = {
            "ingredienti_dettaglio": [
                {"nome": i["nome"], "quantita": i.get("quantita") or 0,
                 "unita_misura": i.get("unita") or i.get("unita_misura") or "g"}
                for i in ingredienti
            ],
            "ingredienti": [i["nome"] for i in ingredienti],
            "ingredienti_origine": "automatica",
            "ingredienti_fonte": esito.get("fonte") or "",
            "ingredienti_proposti_il": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if base and fattore and fattore != 1.0:
            campi["dose_riferimento"] = f"1 kg di {base}"
            campi["dose_fattore"] = fattore
            # le porzioni seguono le dosi, altrimenti il costo/porzione mente
            campi["porzioni"] = max(1, int(round(porzioni * fattore)))
        await db.ricette.update_one({"id": r["id"]}, {"$set": campi})
        compilate.append({"nome": nome, "fonte": esito.get("fonte"),
                          "quanti": len(ingredienti), "motivo": r.get("motivo"),
                          "base": base, "fattore": fattore})

    restanti = max(0, len(da_fare) - len(blocco))
    return {
        "compilate": len(compilate),
        "dettaglio": compilate,
        "senza_proposta": senza_proposta,
        "restanti": restanti,
    }


class LeggiFotoReq(BaseModel):
    immagine_base64: str
    media_type: str = "image/jpeg"


@router.post("/leggi-ingredienti-foto")
async def leggi_ingredienti_foto(req: LeggiFotoReq):
    """AI-visione: riceve la FOTO di un'etichetta/confezione (base64) e ne estrae
    la lista ingredienti pronta per l'editor ricetta. Ritorna lo stesso formato di
    /suggerisci-ingredienti: {ok, fonte, ingredienti:[{nome,quantita,unita}]}."""
    import os
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise HTTPException(503, "AI-visione non disponibile (manca ANTHROPIC_API_KEY)")
    img = (req.immagine_base64 or "").strip()
    media_type = req.media_type or "image/jpeg"
    if not img:
        raise HTTPException(400, "Immagine mancante")
    if img.startswith("data:"):
        try:
            media_type = img.split(";")[0].split(":")[1]
            img = img.split(",", 1)[1]
        except Exception:
            pass
    try:
        import httpx
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 900,
                    "messages": [{"role": "user", "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": img}},
                        {"type": "text", "text": (
                            "Leggi l'etichetta/confezione alimentare in foto ed estrai la lista degli INGREDIENTI. "
                            "Rispondi SOLO con un array JSON di oggetti con chiavi: nome (stringa), quantita (numero, "
                            "0 se non indicata), unita (g, ml oppure pz). Niente testo prima o dopo l'array."
                        )},
                    ]}],
                },
            )
        txt = "".join(b.get("text", "") for b in (r.json().get("content") or []) if b.get("type") == "text")
    except Exception as e:
        raise HTTPException(502, f"AI-visione fallita: {str(e)[:120]}")
    m = re.search(r"\[.*\]", txt or "", re.S)
    if not m:
        return {"ok": False, "fonte": "ai-foto", "ingredienti": [],
                "messaggio": "Nessun ingrediente leggibile dalla foto."}
    try:
        arr = _json.loads(m.group(0))
    except Exception:
        return {"ok": False, "fonte": "ai-foto", "ingredienti": [],
                "messaggio": "Etichetta non interpretabile, riprova con una foto più nitida."}
    ingredienti = [
        {"nome": str(x.get("nome", "")).strip(),
         "quantita": float(x.get("quantita") or 0),
         "unita": str(x.get("unita") or "g")}
        for x in arr if isinstance(x, dict) and x.get("nome")
    ]
    if not ingredienti:
        return {"ok": False, "fonte": "ai-foto", "ingredienti": [],
                "messaggio": "Nessun ingrediente leggibile dalla foto."}
    return {"ok": True, "fonte": "ai-foto", "ingredienti": ingredienti[:30]}


@router.get("/dizionario/manuali")
async def get_prezzi_manuali():
    """Restituisce tutti i prezzi inseriti manualmente"""
    prodotti = (
        await db.dizionario_prodotti.find({"inserito_manualmente": True}, {"_id": 0})
        .sort("nome_normalizzato", 1)
        .to_list(500)
    )
    return prodotti


@router.delete("/dizionario/manuale/{nome_normalizzato}")
async def elimina_prezzo_manuale(nome_normalizzato: str, _admin=Depends(require_admin)):
    """Elimina un prezzo manuale dal dizionario"""
    result = await db.dizionario_prodotti.delete_one(
        {"nome_normalizzato": nome_normalizzato, "inserito_manualmente": True}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Prodotto non trovato o non è manuale")
    return {"success": True}


@router.post("/dizionario")
async def add_prodotto_dizionario(prodotto: ProdottoDizionario):
    """Aggiunge o aggiorna un prodotto nel dizionario"""
    prodotto_dict = prodotto.model_dump()
    prodotto_dict["ultimo_aggiornamento"] = datetime.now(timezone.utc).isoformat()
    prodotto_dict["nome_normalizzato"] = prodotto.nome_normalizzato.lower().strip()

    # Calcola prezzo/kg se non fornito
    if prodotto.peso_confezione > 0:
        prodotto_dict["prezzo_kg"] = round(prodotto.prezzo_confezione / prodotto.peso_confezione, 4)

    await db.dizionario_prodotti.update_one(
        {"nome_normalizzato": prodotto_dict["nome_normalizzato"]},
        {"$set": prodotto_dict},
        upsert=True,
    )
    return {"status": "ok", "prodotto": prodotto_dict}


@router.put("/dizionario/{prodotto_id}")
async def update_prodotto_dizionario(prodotto_id: str, prodotto: ProdottoDizionario):
    """Aggiorna un prodotto esistente nel dizionario"""
    prodotto_dict = prodotto.model_dump()
    prodotto_dict["ultimo_aggiornamento"] = datetime.now(timezone.utc).isoformat()

    if prodotto.peso_confezione > 0:
        prodotto_dict["prezzo_kg"] = round(prodotto.prezzo_confezione / prodotto.peso_confezione, 4)

    result = await db.dizionario_prodotti.update_one({"id": prodotto_id}, {"$set": prodotto_dict})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Prodotto non trovato")
    return {"status": "ok"}


@router.patch("/dizionario/{prodotto_id}/scorta-minima")
async def aggiorna_scorta_minima(
    prodotto_id: str, scorta_minima: float = Query(..., ge=0, description="Scorta minima in kg")
):
    """Aggiorna la scorta minima di un prodotto nel dizionario."""
    result = await db.dizionario_prodotti.update_one(
        {"id": prodotto_id},
        {
            "$set": {
                "scorta_minima": scorta_minima,
                "ultimo_aggiornamento": datetime.now(timezone.utc).isoformat(),
            }
        },
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Prodotto non trovato")
    return {"status": "ok", "scorta_minima": scorta_minima}


@router.patch("/dizionario/{prodotto_id}/aggiorna")
async def aggiorna_campi_dizionario(
    prodotto_id: str,
    campi: dict = Body(...),
    _admin=Depends(require_admin),
):
    """Aggiornamento parziale e flessibile di un prodotto del dizionario
    (es. attivo, is_<fornitore>, ...). Usato dal Catalogo Fornitore per
    aggiungere/rimuovere un prodotto dalle ricette."""
    if not isinstance(campi, dict) or not campi:
        return {"status": "ok", "modificato": False}
    aggiorna = {k: v for k, v in campi.items() if k not in ("id", "_id")}
    aggiorna["ultimo_aggiornamento"] = datetime.now(timezone.utc).isoformat()
    result = await db.dizionario_prodotti.update_one({"id": prodotto_id}, {"$set": aggiorna})
    if result.matched_count == 0:
        # SAIMA e MEPA provengono ancora dal catalogo storico
        # ``dizionario_ingredienti``. Quando l'amministratore sceglie "Usa in
        # ricetta" promuoviamo quel documento nella sorgente canonica del food
        # cost, mantenendo lo stesso id e senza modificare il catalogo sorgente.
        # In questo modo l'azione rapida funziona anche al primo utilizzo e i
        # successivi aggiornamenti restano idempotenti.
        legacy = await db.dizionario_ingredienti.find_one(
            {"id": prodotto_id}, {"_id": 0}
        )
        if not legacy:
            raise HTTPException(status_code=404, detail="Prodotto non trovato")
        documento = {**legacy, **aggiorna, "id": prodotto_id}
        nome = str(
            documento.get("nome") or documento.get("descrizione") or ""
        ).strip()
        documento.setdefault("nome_normalizzato", nome.lower())
        await db.dizionario_prodotti.update_one(
            {"id": prodotto_id}, {"$set": documento}, upsert=True
        )
    return {"status": "ok", "modificato": True}


@router.delete("/dizionario/{prodotto_id}")
async def delete_prodotto_dizionario(prodotto_id: str, _admin=Depends(require_admin)):
    """Elimina un prodotto dal dizionario e lo aggiunge alla blacklist."""
    prodotto = await db.dizionario_prodotti.find_one({"id": prodotto_id}, {"_id": 0})
    if not prodotto:
        raise HTTPException(status_code=404, detail="Prodotto non trovato")

    # Aggiungi alla blacklist permanente (per nome normalizzato)
    nome = (prodotto.get("nome") or prodotto.get("descrizione") or "").strip()
    if nome:
        await db.prodotti_blacklist.update_one(
            {"nome_normalizzato": nome.lower()},
            {
                "$set": {
                    "nome_originale": nome,
                    "nome_normalizzato": nome.lower(),
                    "eliminato_at": datetime.now(timezone.utc).isoformat(),
                    "motivo": "eliminato_manualmente",
                }
            },
            upsert=True,
        )

    await db.dizionario_prodotti.delete_one({"id": prodotto_id})
    return {"status": "ok", "blacklistato": nome}


@router.post("/sincronizza-fatture")
async def sincronizza_dizionario_da_fatture(
    request: Request,
    azzera: bool = Query(
        False, description="Se True, azzera il dizionario prima della sincronizzazione"
    ),
):
    """
    Popola/aggiorna il dizionario prodotti dalle fatture.
    Estrae: nome prodotto, peso confezione, prezzo, prezzo/kg.
    ESCLUDE AUTOMATICAMENTE I FORNITORI ESCLUSI.
    Se azzera=True, cancella tutti i dati prima di ripopolare.

    LOGICA PREZZI:
    - Alcuni fornitori (es. F.lli Fiorentino) esprimono:
      - Quantità = numero di SACCHI/CONFEZIONI
      - Prezzo = prezzo per KG (già unitario!)
    - Altri fornitori esprimono:
      - Quantità = KG totali
      - Prezzo = prezzo per KG

    Euristica: Se quantità è molto alta (>50) e c'è un peso nella descrizione,
    probabilmente la quantità è in sacchi e il prezzo è già per kg.
    """
    # Azzera se richiesto — operazione DISTRUTTIVA (cancella scorte minime,
    # canonici confermati, alias, righe inserite a mano senza fattura): la
    # può lanciare SOLO l'amministratore, non un token dipendente.
    if azzera:
        ruolo = (getattr(request.state, "user", None) or {}).get("ruolo", "")
        if ruolo != "amministratore":
            raise HTTPException(403, "Azzeramento dizionario riservato all'amministratore")
        await db.dizionario_prodotti.delete_many({})

    # Ottieni fornitori esclusi
    fornitori_esclusi = await get_fornitori_esclusi()

    # Ottieni blacklist prodotti eliminati manualmente
    blacklist_docs = await db.prodotti_blacklist.find({}, {"nome_normalizzato": 1}).to_list(5000)
    blacklist = {doc["nome_normalizzato"] for doc in blacklist_docs}

    fatture = await db.fatture.find({}, {"_id": 0}).to_list(50000)

    stats = {
        "prodotti_aggiunti": 0,
        "prodotti_aggiornati": 0,
        "prodotti_rimossi": 0,
        "prodotti_trovati": 0,
        "prodotti_saltati_blacklist": 0,
        "fornitori_esclusi": len(fornitori_esclusi),
        "prodotti_senza_peso": [],
        "errori": [],
    }

    # Prima rimuovi dal dizionario i prodotti di fornitori ora esclusi
    if fornitori_esclusi:
        for fornitore_escluso in fornitori_esclusi:
            result = await db.dizionario_prodotti.delete_many(
                {"fornitore": {"$regex": f"^{re.escape(fornitore_escluso)}$", "$options": "i"}}
            )
            stats["prodotti_rimossi"] += result.deleted_count

    prodotti_processati = {}

    # Fornitori che esprimono SEMPRE: Qt=numero confezioni, Prezzo=€/kg
    # → prezzo_kg = prezzo_unitario, quantita_kg = qt * peso_confezione
    FORNITORI_PREZZO_PER_KG = {
        "f.lli fiorentino",
        "fiorentino",
        "granzuccheri",
        "saima",
    }

    for fattura in fatture:
        fornitore = fattura.get("fornitore", "")
        fornitore_lower = fornitore.lower().strip()
        data_fattura = fattura.get("data_fattura", "")

        # SALTA fornitori esclusi
        if fornitore_lower in fornitori_esclusi:
            continue

        # Questo fornitore usa sempre prezzo per kg direttamente
        fornitore_usa_prezzo_per_kg = any(f in fornitore_lower for f in FORNITORI_PREZZO_PER_KG)

        for prodotto in fattura.get("prodotti", []):
            descrizione = prodotto.get("descrizione", "").strip()
            quantita_str = str(prodotto.get("quantita", "0")).strip()
            prezzo_str = str(prodotto.get("prezzo", "0")).strip()
            unita_misura_xml = str(prodotto.get("unita_misura", "") or "").strip().upper()

            if not descrizione:
                continue

            # Salta voci contabili/non-prodotti: liquidazioni, sconti, contributi, obblighi, imballi
            VOCI_NON_PRODOTTO = {
                "liquidaz",
                "liquidazione",
                "abbuono",
                "sconto",
                "reso ",
                "contributo",
                "obbligo",
                "obj ",
                "obiettivo",
                "nota credito",
                "diritto fisso",
                "diritto di",
                "imballo",
                "vuoto a perdere",
                "spese trasporto",
                "spese di trasporto",
                "rimborso",
                "commissione",
                "provvigione",
                "acconto",
                "saldo",
            }
            descrizione_lower = descrizione.lower()
            if any(k in descrizione_lower for k in VOCI_NON_PRODOTTO):
                continue

            # Parse valori numerici (gestisce spazi e formato italiano/anglosassone)
            try:
                quantita = float(quantita_str.replace(" ", "").replace(",", "."))
                prezzo_unitario = float(prezzo_str.replace(" ", "").replace(",", "."))
            except (ValueError, AttributeError):
                continue

            if quantita <= 0 or prezzo_unitario <= 0:
                continue

            # ─── LOGICA PREZZI/UNITÀ ─────────────────────────────────────────────────
            #
            # PRIORITÀ 0: Fornitori speciali (Fiorentino, Granzuccheri)
            #   Qt = numero confezioni, Prezzo = già per KG
            #   → prezzo_kg = prezzo_unitario, qt_kg = qt * peso_confezione_da_desc
            #
            # PRIORITÀ 1: UnitaMisura XML esplicita KG/LT
            #   Qt già in kg/lt, prezzo per kg/lt
            #
            # PRIORITÀ 2: UnitaMisura XML = pezzi (NR/PZ/BT/ecc.)
            #   Qt in pezzi, serve peso dalla descrizione
            #
            # PRIORITÀ 3: UM assente + peso trovato in descrizione
            #   Qt = confezioni, prezzo = per confezione → prezzo_kg = pr/peso
            #
            # PRIORITÀ 4: Fallback — assume kg con prezzo diretto
            # ─────────────────────────────────────────────────────────────────────────

            UM_KG_LT = {"KG", "LT", "L"}
            UM_PEZZI = {"NR", "PZ", "BT", "SC", "CT", "CF", "NR.", "KAR", "ST", "FS", "CS"}

            # ─── REGOLA PRINCIPALE ────────────────────────────────────────────────
            # 1. Il parser della DESCRIZIONE è SEMPRE la fonte del peso fisico
            #    della confezione (GR.10, G500, KG 1.5, ecc.)
            # 2. L'UnitaMisura XML dice solo come è espressa la Qt in fattura:
            #    - KG/LT → Qt già in kg/lt, prezzo per kg/lt
            #    - NR/PZ/ecc. → Qt in confezioni, prezzo per confezione
            #    - assente → trattata come confezioni
            # 3. Se il parser non trova peso → prodotto senza peso (manuale)
            # ─────────────────────────────────────────────────────────────────────

            # Estrai sempre il peso dalla descrizione
            peso_desc = estrai_peso_e_unita(descrizione)  # (valore, unità) o None

            # Converti peso in kg per uniformità
            def to_kg(val, unit):
                if unit in ("kg", "l", "lt"):
                    return round(val, 6)
                elif unit == "g":
                    return round(val / 1000, 6)
                elif unit == "ml":
                    return round(val / 1000, 6)
                elif unit == "cl":
                    # 1 cl = 0,01 l: mancava e il valore tornava tale e quale
                    # (una bottiglia "75 CL" diventava 75 kg) — fix 25/07/2026
                    return round(val / 100, 6)
                elif unit == "dl":
                    return round(val / 10, 6)
                return val

            if fornitore_usa_prezzo_per_kg and unita_misura_xml not in UM_KG_LT:
                # FORNITORI SPECIALI (Fiorentino, Granzuccheri, Saima):
                # Il prezzo in fattura è già €/kg. Qt = numero confezioni.
                if peso_desc:
                    peso_val, peso_unit = peso_desc
                    peso_confezione = to_kg(peso_val, peso_unit)
                    unita = "kg"
                    prezzo_kg = prezzo_unitario
                    quantita_kg_fattura = quantita * peso_confezione
                else:
                    # Nessun peso in descrizione → Qt è già in kg (es. STRUTTO RAFFINATO)
                    peso_confezione = 1.0
                    unita = "kg"
                    prezzo_kg = prezzo_unitario
                    quantita_kg_fattura = quantita

            elif unita_misura_xml in UM_KG_LT:
                # Qt già in kg/lt dal XML → prezzo per kg.
                # Usa peso da descrizione se disponibile, altrimenti 1kg
                if peso_desc:
                    peso_val, peso_unit = peso_desc
                    peso_confezione = to_kg(peso_val, peso_unit)
                    unita = "kg"
                    prezzo_kg = prezzo_unitario
                    quantita_kg_fattura = quantita
                else:
                    peso_confezione = 1.0
                    unita = unita_misura_xml.lower()
                    prezzo_kg = prezzo_unitario
                    quantita_kg_fattura = quantita

            elif unita_misura_xml in UM_PEZZI or not unita_misura_xml:
                # Qt in confezioni (NR, PZ, ecc.) o UM assente.
                # Il peso della confezione DEVE venire dalla descrizione.
                if peso_desc:
                    peso_val, peso_unit = peso_desc
                    peso_confezione = to_kg(peso_val, peso_unit)
                    unita = "kg"
                    prezzo_kg = (
                        round(prezzo_unitario / peso_confezione, 4)
                        if peso_confezione > 0
                        else prezzo_unitario
                    )
                    quantita_kg_fattura = quantita * peso_confezione
                else:
                    # Peso non trovato in descrizione → senza peso (manuale)
                    peso_confezione = 1.0
                    unita = "pz"
                    prezzo_kg = prezzo_unitario
                    quantita_kg_fattura = quantita
                    desc_short = descrizione[:80].strip()
                    if desc_short not in [p["descrizione"] for p in stats["prodotti_senza_peso"]]:
                        stats["prodotti_senza_peso"].append(
                            {
                                "descrizione": desc_short,
                                "fornitore": fornitore,
                                "prezzo": prezzo_unitario,
                            }
                        )
            else:
                # UM non riconosciuta → tratta come confezioni con parser descrizione
                if peso_desc:
                    peso_val, peso_unit = peso_desc
                    peso_confezione = to_kg(peso_val, peso_unit)
                    unita = "kg"
                    prezzo_kg = (
                        round(prezzo_unitario / peso_confezione, 4)
                        if peso_confezione > 0
                        else prezzo_unitario
                    )
                    quantita_kg_fattura = quantita * peso_confezione
                else:
                    peso_confezione = 1.0
                    unita = "pz"
                    prezzo_kg = prezzo_unitario
                    quantita_kg_fattura = quantita
                    desc_short = descrizione[:80].strip()
                    if desc_short not in [p["descrizione"] for p in stats["prodotti_senza_peso"]]:
                        stats["prodotti_senza_peso"].append(
                            {
                                "descrizione": desc_short,
                                "fornitore": fornitore,
                                "prezzo": prezzo_unitario,
                            }
                        )

            # Sanity check: prezzo/kg non deve essere assurdo (< 0.001 o > 5000)
            if prezzo_kg < 0.001 or prezzo_kg > 5000:
                continue

            # Nome normalizzato
            nome_norm = normalizza_nome_prodotto(descrizione)

            if not nome_norm or prezzo_kg <= 0:
                continue

            # Controlla blacklist — prodotti eliminati manualmente non vengono re-importati
            if nome_norm.lower() in blacklist or descrizione.strip().lower() in blacklist:
                stats["prodotti_saltati_blacklist"] += 1
                continue

            quantita_kg_fattura = round(quantita_kg_fattura, 3)

            # Aggiorna o crea il prodotto nel dizionario
            key = nome_norm.lower()
            stats["prodotti_trovati"] += 1
            if key not in prodotti_processati:
                prodotti_processati[key] = {
                    "id": str(uuid.uuid4()),
                    "nome_originale": descrizione[:200].strip(),
                    "nome_normalizzato": nome_norm.lower(),
                    "peso_confezione": peso_confezione,
                    "unita_confezione": unita,
                    "prezzo_confezione": prezzo_unitario,
                    "prezzo_kg": round(prezzo_kg, 4),
                    "quantita_totale_kg": round(quantita_kg_fattura, 3),
                    "fornitore": fornitore,
                    "data_fattura": data_fattura,
                    "ultimo_aggiornamento": datetime.now(timezone.utc).isoformat(),
                }
            else:
                # Accumula la quantità da più fatture
                prodotti_processati[key]["quantita_totale_kg"] = round(
                    prodotti_processati[key].get("quantita_totale_kg", 0) + quantita_kg_fattura, 3
                )
                # Aggiorna prezzo se più conveniente
                if prezzo_kg < prodotti_processati[key]["prezzo_kg"]:
                    prodotti_processati[key]["prezzo_kg"] = round(prezzo_kg, 4)
                    prodotti_processati[key]["prezzo_confezione"] = prezzo_unitario

    # Salva nel database e calcola quantità disponibile
    for nome_norm, prodotto in prodotti_processati.items():
        # Recupera quantità già usata dal database esistente
        existing = await db.dizionario_prodotti.find_one({"nome_normalizzato": nome_norm})
        quantita_usata = existing.get("quantita_usata_kg", 0) if existing else 0

        prodotto["quantita_usata_kg"] = quantita_usata
        prodotto["quantita_disponibile_kg"] = round(
            max(0, prodotto["quantita_totale_kg"] - quantita_usata), 3
        )

        # NON rigenerare l'id di una riga già esistente: le ricette collegano
        # l'ingrediente al dizionario via prodotto_dizionario_id, e riscriverlo
        # a ogni sincronizzazione rendeva orfani TUTTI quei legami (e 404 le
        # PATCH scorta-minima/aggiorna). L'id nuovo vale solo per le righe nuove.
        if existing and existing.get("id"):
            prodotto.pop("id", None)

        # REGOLA: i valori corretti a mano da Enzo non si toccano MAI. Prima
        # questa sincronizzazione riscriveva peso/unità/prezzi con l'euristica
        # lasciando il flag manuale attivo: il dato sbagliato restava poi
        # protetto per sempre come se fosse una correzione umana.
        if existing and existing.get("peso_corretto_manualmente"):
            for campo in ("peso_confezione", "unita_confezione", "tipo_quantita",
                          "prezzo_kg", "prezzo_confezione"):
                prodotto.pop(campo, None)

        result = await db.dizionario_prodotti.update_one(
            {"nome_normalizzato": nome_norm}, {"$set": prodotto}, upsert=True
        )
        if result.upserted_id:
            stats["prodotti_aggiunti"] += 1
        elif result.modified_count > 0:
            stats["prodotti_aggiornati"] += 1

    # Limita prodotti senza peso
    stats["prodotti_senza_peso"] = stats["prodotti_senza_peso"][:100]

    return {
        "status": "ok",
        "prodotti_trovati": stats["prodotti_trovati"],
        "prodotti_aggiunti": stats["prodotti_aggiunti"],
        "prodotti_aggiornati": stats["prodotti_aggiornati"],
        "prodotti_rimossi": stats["prodotti_rimossi"],
        "fornitori_esclusi": stats["fornitori_esclusi"],
        "totale_dizionario": len(prodotti_processati),
        "prodotti_senza_peso_count": len(stats["prodotti_senza_peso"]),
        "prodotti_senza_peso": stats["prodotti_senza_peso"][:20],
    }


# ==================== CALCOLO FOOD COST ====================


@router.get("/calcola/{ricetta_id}")
async def calcola_food_cost_ricetta(ricetta_id: str):
    """
    Calcola il food cost dettagliato di una ricetta.
    Usa gli ingredienti con quantità se presenti.
    """
    ricetta = await db.ricette.find_one({"id": ricetta_id}, {"_id": 0})
    if not ricetta:
        raise HTTPException(status_code=404, detail="Ricetta non trovata")

    # Carica dizionario prodotti
    prodotti = await db.dizionario_prodotti.find({}, {"_id": 0}).to_list(10000)
    dizionario = {p["nome_normalizzato"].lower(): p for p in prodotti}

    ingredienti_result = []
    costo_totale = 0
    ingredienti_mancanti = []

    # Usa ingredienti_dettaglio se disponibile
    if ricetta.get("ingredienti_dettaglio"):
        for ing in ricetta["ingredienti_dettaglio"]:
            nome = ing.get("nome", "").strip()
            quantita_raw = ing.get("quantita", 0)
            unita = ing.get("unita_misura", "g")

            # Converti quantità
            try:
                quantita = float(str(quantita_raw).replace(",", ".")) if quantita_raw else 0
            except (ValueError, TypeError):
                quantita = 0

            # Cerca nel dizionario
            prodotto = trova_prodotto_dizionario(nome, dizionario)

            # Determina se la quantità è "q.b." o non numerica
            qb = str(quantita_raw).strip().lower() in ("q.b.", "qb", "q.b", "quanto basta", "")

            if prodotto and quantita > 0:
                prezzo_kg = float(prodotto.get("prezzo_kg", 0) or 0)
                costo_per_pezzo = float(prodotto.get("costo_per_pezzo", 0) or 0)
                # Per unità "pz": usa costo_per_pezzo se disponibile, altrimenti prezzo_kg/1000*50g default
                unita_lower = (unita or "g").lower().strip()
                # REGOLA ENZO: le bevande/alcolici si contano a bottiglia/cartone,
                # MAI a kg. Qui il food cost usava comunque prezzo_kg (audit
                # quantità/unità §3): un amaro o uno sciroppo entravano in ricetta
                # con un prezzo al chilo che non esiste. Fix 25/07/2026.
                a_unita = _e_bevanda_a_unita(nome, prodotto)
                motivo_non_calcolabile = None
                if a_unita:
                    if costo_per_pezzo > 0:
                        costo = quantita * costo_per_pezzo
                        quantita_kg = 0
                    else:
                        # Nessun prezzo a bottiglia/cartone: non si inventa un
                        # €/kg — l'ingrediente resta senza costo e viene segnalato.
                        costo = 0
                        quantita_kg = 0
                        motivo_non_calcolabile = "bevanda senza prezzo a confezione"
                elif unita_lower in ("pz", "pezzi", "pezzo", "nr", "n") and costo_per_pezzo > 0:
                    costo = quantita * costo_per_pezzo
                    quantita_kg = quantita * (float(prodotto.get("peso_pezzo_g", 50) or 50) / 1000)
                elif unita_lower in UNITA_A_CONFEZIONE:
                    # cartone/cassa/bottiglia senza prezzo a confezione: converti_in_kg
                    # torna 0 di proposito, quindi il costo sarebbe 0 in silenzio.
                    if costo_per_pezzo > 0:
                        costo = quantita * costo_per_pezzo
                    else:
                        costo = 0
                        motivo_non_calcolabile = "manca il peso o il prezzo della confezione"
                    quantita_kg = 0
                else:
                    # Converti quantità in kg
                    quantita_kg = converti_in_kg(quantita, unita, nome)
                    costo = quantita_kg * prezzo_kg

                riga_ing = {
                    "nome": nome,
                    "quantita": quantita,
                    "unita": unita,
                    "prodotto_dizionario": prodotto.get("nome_normalizzato"),
                    "prezzo_kg": None if a_unita else prezzo_kg,
                    "costo": None if motivo_non_calcolabile else round(costo, 2),
                }
                if a_unita:
                    riga_ing["prezzo_confezione"] = costo_per_pezzo or None
                    riga_ing["a_unita"] = True
                if motivo_non_calcolabile:
                    riga_ing["costo_non_calcolabile"] = motivo_non_calcolabile
                    if nome:
                        ingredienti_mancanti.append(f"{nome} ({motivo_non_calcolabile})")
                ingredienti_result.append(riga_ing)
                costo_totale += costo
            elif prodotto and qb:
                # Trovato nel dizionario ma quantità "q.b." — mostra info prezzo senza calcolare costo
                prezzo_kg = float(prodotto.get("prezzo_kg", 0) or 0)
                ingredienti_result.append(
                    {
                        "nome": nome,
                        "quantita": "q.b.",
                        "unita": unita,
                        "prodotto_dizionario": prodotto.get("nome_normalizzato"),
                        "prezzo_kg": prezzo_kg,
                        "costo": None,  # non calcolabile senza quantità
                    }
                )
            else:
                ingredienti_result.append(
                    {
                        "nome": nome,
                        "quantita": quantita,
                        "unita": unita,
                        "prodotto_dizionario": None,
                        "prezzo_kg": None,
                        "costo": None,
                    }
                )
                if nome:
                    ingredienti_mancanti.append(nome)
    else:
        # Fallback: ingredienti senza quantità (supporta sia str che dict)
        for nome_raw in ricetta.get("ingredienti", []):
            nome = nome_raw.get("nome", "") if isinstance(nome_raw, dict) else nome_raw
            if not nome:
                continue
            prodotto = trova_prodotto_dizionario(nome, dizionario)
            ingredienti_result.append(
                {
                    "nome": nome,
                    "quantita": None,
                    "unita": None,
                    "prodotto_dizionario": prodotto.get("nome_normalizzato") if prodotto else None,
                    "prezzo_kg": float(prodotto.get("prezzo_kg", 0)) if prodotto else None,
                    "costo": None,
                }
            )
            if not prodotto:
                ingredienti_mancanti.append(nome)

    porzioni = ricetta.get("porzioni", 1) or 1

    return {
        "ricetta_id": ricetta_id,
        "nome": ricetta.get("nome", ""),
        "ingredienti": ingredienti_result,
        "costo_totale": round(costo_totale, 2),
        "porzioni": porzioni,
        "costo_porzione": round(costo_totale / porzioni, 2) if porzioni > 0 else 0,
        "ingredienti_mancanti": ingredienti_mancanti,
        "completezza": f"{len(ingredienti_result) - len(ingredienti_mancanti)}/{len(ingredienti_result)}",
    }


@router.get("/ultimi-prodotti-ricevuti")
async def ultimi_prodotti_ricevuti(limit: int = Query(20, le=100)):
    """
    Ultimi prodotti ricevuti dalle fatture XML, ordinati per data fattura reale (più recente prima).
    Usato dal pannello laterale della pagina ricette.
    """
    prodotti = await db.dizionario_prodotti.find(
        {"data_fattura": {"$nin": [None, ""]}},
        {
            "_id": 0,
            "nome_normalizzato": 1,
            "nome_originale": 1,
            "prezzo_kg": 1,
            "fornitore": 1,
            "data_fattura": 1,
            "id": 1,
        },
    ).to_list(10000)

    def parse_dt(val):
        txt = str(val or "")
        try:
            if "-" in txt[:10]:
                return datetime.fromisoformat(txt[:10])
            if "/" in txt:
                return datetime.strptime(txt[:10], "%d/%m/%Y")
        except Exception:
            return datetime.min
        return datetime.min

    prodotti.sort(key=lambda p: parse_dt(p.get("data_fattura")), reverse=True)
    return prodotti[:limit]


@router.post("/riallinea-ingredienti/{ricetta_id}")
async def riallinea_ingredienti_ricetta(
    ricetta_id: str,
    forza: bool = Query(False, description="Forza riallineamento ignorando finestra 15gg"),
):
    """
    Riallinea gli ingredienti della ricetta all'ultimo prodotto disponibile nel dizionario.
    Logica finestra 15 giorni:
    - Scatta solo se sono passati >= 15 giorni dall'ultimo riallineamento (campo ingredienti_aggiornati_il)
    - Se entro 15 giorni non arriva nessuna fattura nuova, mantiene il vecchio ingrediente (nessun azzeramento)
    - Un ingrediente viene sostituito solo se nel dizionario esiste un prodotto con data_fattura PIU' RECENTE
      di quella attualmente agganciata alla riga ricetta.
    Da chiamare all'apertura della ricetta (al volo).
    """
    ricetta = await db.ricette.find_one({"id": ricetta_id}, {"_id": 0})
    if not ricetta:
        raise HTTPException(status_code=404, detail="Ricetta non trovata")

    FINESTRA_GIORNI = 15
    oggi = datetime.now(timezone.utc)

    # 1. Controllo finestra temporale
    ultimo_refresh = ricetta.get("ingredienti_aggiornati_il")
    giorni_trascorsi = None
    if ultimo_refresh:
        try:
            dt = datetime.fromisoformat(str(ultimo_refresh).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            giorni_trascorsi = (oggi - dt).days
        except Exception:
            giorni_trascorsi = None

    deve_riallineare = forza or giorni_trascorsi is None or giorni_trascorsi >= FINESTRA_GIORNI

    if not deve_riallineare:
        return {
            "riallineato": False,
            "motivo": f"Ricetta aggiornata {giorni_trascorsi} giorni fa (< {FINESTRA_GIORNI}gg). Nessuna modifica.",
            "giorni_alla_prossima": FINESTRA_GIORNI - giorni_trascorsi,
            "ingredienti_sostituiti": [],
        }

    # 2. Carica dizionario completo
    prodotti = await db.dizionario_prodotti.find({}, {"_id": 0}).to_list(10000)
    dizionario = {p["nome_normalizzato"].lower(): p for p in prodotti}

    def data_prodotto(prod):
        """Estrae la data fattura più recente di un prodotto dizionario."""
        for campo in ("data_fattura", "ultima_fattura", "ultimo_aggiornamento"):
            val = prod.get(campo)
            if val:
                try:
                    txt = str(val)
                    if "T" in txt:
                        return datetime.fromisoformat(txt.replace("Z", "+00:00")).replace(
                            tzinfo=None
                        )
                    if "-" in txt[:10]:
                        return datetime.fromisoformat(txt[:10])
                    if "/" in txt:
                        return datetime.strptime(txt[:10], "%d/%m/%Y")
                except Exception:
                    continue
        return None

    ingredienti = ricetta.get("ingredienti_dettaglio") or []
    sostituiti = []

    for ing in ingredienti:
        nome = (ing.get("nome") or "").strip()
        if not nome:
            continue

        # Prodotto attualmente agganciato
        id_attuale = ing.get("prodotto_dizionario_id")
        prod_attuale = next((p for p in prodotti if p.get("id") == id_attuale), None)
        data_attuale = data_prodotto(prod_attuale) if prod_attuale else None

        # Miglior prodotto candidato dal dizionario (match per nome)
        candidato = trova_prodotto_dizionario(nome, dizionario)
        if not candidato:
            continue

        data_candidato = data_prodotto(candidato)

        # Sostituisci solo se il candidato ha una fattura PIU' RECENTE (o se prima non c'era nulla)
        sostituire = False
        if candidato.get("id") != id_attuale:
            if data_attuale is None and data_candidato is not None:
                sostituire = True
            elif (
                data_attuale is not None
                and data_candidato is not None
                and data_candidato > data_attuale
            ):
                sostituire = True
            elif id_attuale is None:
                sostituire = True

        if sostituire:
            vecchio_prezzo = ing.get("prezzo_kg")
            nuovo_prezzo = float(candidato.get("prezzo_kg", 0) or 0)
            ing["prodotto_dizionario_id"] = candidato.get("id")
            ing["prezzo_kg"] = nuovo_prezzo
            # ricalcola costo
            try:
                q = float(str(ing.get("quantita", 0)).replace(",", "."))
                q_kg = converti_in_kg(q, ing.get("unita_misura", "g"), ing.get("nome", ""))
                ing["costo_calcolato"] = round(q_kg * nuovo_prezzo, 4)
            except Exception:
                _LOG_INIT.debug("[food_cost] errore non bloccante ignorato")
            sostituiti.append(
                {
                    "ingrediente": nome,
                    "vecchio_prodotto": (
                        prod_attuale.get("nome_normalizzato") if prod_attuale else None
                    ),
                    "nuovo_prodotto": candidato.get("nome_normalizzato"),
                    "vecchio_prezzo_kg": vecchio_prezzo,
                    "nuovo_prezzo_kg": nuovo_prezzo,
                    "fornitore": candidato.get("fornitore", ""),
                }
            )

    # 3. Salva sempre il timestamp (anche se 0 sostituzioni: la finestra riparte)
    costo_totale = sum(float(i.get("costo_calcolato", 0) or 0) for i in ingredienti)
    porzioni = ricetta.get("porzioni", 1) or 1
    await db.ricette.update_one(
        {"id": ricetta_id},
        {
            "$set": {
                "ingredienti_dettaglio": ingredienti,
                "ingredienti_aggiornati_il": oggi.isoformat(),
                "costo_totale": round(costo_totale, 2),
                "costo_porzione": round(costo_totale / porzioni, 2) if porzioni else 0,
            }
        },
    )

    return {
        "riallineato": True,
        "ingredienti_sostituiti": sostituiti,
        "n_sostituiti": len(sostituiti),
        "costo_totale": round(costo_totale, 2),
        "giorni_trascorsi": giorni_trascorsi,
    }


@router.post("/ricalcola-costi-tutte-ricette")
async def ricalcola_costi_tutte_ricette():
    """Ricalcola e salva il costo di tutte le ricette nel DB."""
    prodotti = await db.dizionario_prodotti.find({"prezzo_kg": {"$gt": 0}}, {"_id": 0}).to_list(
        10000
    )
    dizionario = {p["nome_normalizzato"].lower(): p for p in prodotti}
    aggiornate = 0
    con_costo = 0
    async for ricetta in db.ricette.find({}, {"_id": 0}):
        costo_totale = 0
        ing_trovati = 0
        ing_totali = 0
        ings_aggiornati = list(ricetta.get("ingredienti_dettaglio", []))
        for idx, ing in enumerate(ings_aggiornati):
            nome = (ing.get("nome") or "").strip()
            quantita_raw = ing.get("quantita", 0)
            unita = ing.get("unita_misura", "g") or "g"
            ing_totali += 1
            try:
                quantita = float(str(quantita_raw).replace(",", ".")) if quantita_raw else 0
            except (ValueError, TypeError):
                quantita = 0
            if (
                str(quantita_raw).strip().lower() in ("q.b.", "qb", "q.b", "quanto basta", "")
                or quantita == 0
            ):
                continue
            prodotto = trova_prodotto_dizionario(nome, dizionario)
            if prodotto and float(prodotto.get("prezzo_kg", 0) or 0) > 0:
                prezzo_kg = float(prodotto["prezzo_kg"])
                costo_calc = round(converti_in_kg(quantita, unita, nome) * prezzo_kg, 4)
                costo_totale += costo_calc
                ing_trovati += 1
                # Aggiorna il prezzo nel documento ingrediente
                ings_aggiornati[idx] = dict(ing)
                ings_aggiornati[idx]["prezzo_kg"] = round(prezzo_kg, 4)
                ings_aggiornati[idx]["costo_calcolato"] = costo_calc
                ings_aggiornati[idx]["prodotto_dizionario_id"] = prodotto.get("id")
        porzioni = ricetta.get("porzioni", 1) or 1
        update_ops = {
            "costo_totale": round(costo_totale, 4),
            "costo_porzione": round(costo_totale / porzioni, 4),
            "completezza": f"{ing_trovati}/{ing_totali}",
        }
        # Aggiorna anche i prezzi_kg degli ingredienti
        if ings_aggiornati:
            update_ops["ingredienti_dettaglio"] = ings_aggiornati
        await db.ricette.update_one({"id": ricetta["id"]}, {"$set": update_ops})
        aggiornate += 1
        if costo_totale > 0:
            con_costo += 1
    return {
        "success": True,
        "ricette_aggiornate": aggiornate,
        "con_costo": con_costo,
        "senza_costo": aggiornate - con_costo,
    }


@router.post("/auto-mappa-ingredienti")
async def auto_mappa_ingredienti(ricetta_id: Optional[str] = None):
    """
    Mappa automaticamente gli ingredienti non mappati con il dizionario prodotti.
    Se ricetta_id è specificato, mappa solo quella ricetta.
    Altrimenti mappa TUTTE le ricette con ingredienti senza prezzo.
    Salva il prezzo_kg e prodotto_dizionario_id nel DB.
    """
    prodotti = await db.dizionario_prodotti.find({"prezzo_kg": {"$gt": 0}}, {"_id": 0}).to_list(
        10000
    )
    dizionario = {p["nome_normalizzato"].lower(): p for p in prodotti}

    if ricetta_id:
        ricette = await db.ricette.find({"id": ricetta_id}, {"_id": 0}).to_list(1)
    else:
        ricette = await db.ricette.find({}, {"_id": 0}).to_list(5000)

    risultati = {
        "ricette_elaborate": 0,
        "ingredienti_mappati": 0,
        "ingredienti_non_trovati": [],
        "ricette_aggiornate": [],
    }

    for ricetta in ricette:
        ings = ricetta.get("ingredienti_dettaglio", [])
        if not ings:
            continue

        modified = False
        costo_totale = 0
        ing_trovati = 0

        for i, ing in enumerate(ings):
            nome = (ing.get("nome") or "").strip()
            if not nome:
                continue

            quantita_raw = ing.get("quantita", 0)
            try:
                quantita = float(str(quantita_raw).replace(",", ".")) if quantita_raw else 0
            except (ValueError, TypeError):
                quantita = 0

            unita = ing.get("unita_misura") or ing.get("unita", "g")

            # Se ha già prezzo_kg salvato e prodotto_id, salta (già mappato)
            if ing.get("prezzo_kg") and ing.get("prodotto_dizionario_id"):
                if quantita > 0:
                    costo_totale += converti_in_kg(quantita, unita, nome) * float(ing["prezzo_kg"])
                    ing_trovati += 1
                continue

            # Cerca nel dizionario
            prodotto = trova_prodotto_dizionario(nome, dizionario)

            if prodotto and float(prodotto.get("prezzo_kg", 0) or 0) > 0:
                prezzo_kg = float(prodotto["prezzo_kg"])
                costo = None
                if quantita > 0:
                    costo = round(converti_in_kg(quantita, unita, nome) * prezzo_kg, 4)
                    costo_totale += costo
                    ing_trovati += 1

                ings[i] = {
                    **ing,
                    "prodotto_dizionario_id": prodotto.get("id"),
                    "prezzo_kg": prezzo_kg,
                    "costo_calcolato": costo,
                }
                modified = True
                risultati["ingredienti_mappati"] += 1
            else:
                # Non trovato
                chiave = f"{ricetta.get('nome','?')} → {nome}"
                if chiave not in risultati["ingredienti_non_trovati"]:
                    risultati["ingredienti_non_trovati"].append(chiave)

        if modified:
            porzioni = ricetta.get("porzioni", 1) or 1
            completezza = f"{ing_trovati}/{len([x for x in ings if (x.get('nome') or '').strip()])}"
            await db.ricette.update_one(
                {"id": ricetta["id"]},
                {
                    "$set": {
                        "ingredienti_dettaglio": ings,
                        "costo_totale": round(costo_totale, 4),
                        "costo_porzione": round(costo_totale / porzioni, 4),
                        "completezza": completezza,
                    }
                },
            )
            risultati["ricette_aggiornate"].append(ricetta.get("nome", "?"))

        risultati["ricette_elaborate"] += 1

    return {
        "success": True,
        "ricette_elaborate": risultati["ricette_elaborate"],
        "ricette_aggiornate": len(risultati["ricette_aggiornate"]),
        "ingredienti_mappati": risultati["ingredienti_mappati"],
        "ingredienti_non_trovati_count": len(risultati["ingredienti_non_trovati"]),
        "ingredienti_non_trovati": risultati["ingredienti_non_trovati"][:30],
        "ricette_aggiornate_nomi": risultati["ricette_aggiornate"],
    }


@router.post("/auto-rileva-allergeni-tutte")
async def auto_rileva_allergeni_tutte(force: bool = False):
    """
    Analizza automaticamente gli ingredienti di TUTTE le ricette e suggerisce
    gli allergeni presenti in base al nome degli ingredienti (Reg. UE 1169/2011).
    Se force=True sovrascrive anche le ricette che hanno già allergeni.
    Di default aggiorna TUTTE le ricette (non salta quelle già con allergeni).
    """
    # Mappa parole-chiave → allergene (Allegato II Reg. UE 1169/2011)

    ricette = await db.ricette.find(
        {},
        {
            "_id": 0,
            "id": 1,
            "nome": 1,
            "allergeni": 1,
            "ingredienti_dettaglio": 1,
            "ingredienti": 1,
            "componenti": 1,
            "allergeni_auto": 1,
            "allergeni_verificato": 1,
            "allergeni_da_confermare": 1,
        },
    ).to_list(2000)

    aggiornate = 0
    skippate = 0
    risultati = []

    for ricetta in ricette:
        nomi_ing = estrai_nomi_ingredienti(ricetta)
        allergeni_trovati, _ = rileva_allergeni(nomi_ing)
        manuali_confermati = (
            ricetta.get("allergeni_verificato") is True
            and ricetta.get("allergeni_da_confermare") is False
        )

        # Aggiorna il calcolo automatico senza cancellare una decisione umana già
        # confermata. ``force=True`` resta disponibile per il ricalcolo esplicito.
        # allergeni_verificato: SENZA questo flag l'alert A1 del Supervisore restava
        # acceso per sempre anche dopo il rilevamento (bug segnalato da Enzo 03/07/2026).
        # allergeni_da_confermare: l'automatismo COMPILA ma non VERIFICA (decisione
        # Enzo 04/07/2026 — davanti a un'ispezione "verificato" deve voler dire che
        # un umano ha guardato): resta True finché Enzo non salva la ricetta a mano.
        aggiornamento = {"allergeni_auto": allergeni_trovati}
        if force or not manuali_confermati:
            aggiornamento["allergeni"] = allergeni_trovati
            aggiornamento["allergeni_verificato"] = bool(nomi_ing)
            aggiornamento["allergeni_da_confermare"] = bool(nomi_ing)
        await db.ricette.update_one({"id": ricetta["id"]}, {"$set": aggiornamento})
        aggiornate += 1
        if allergeni_trovati:
            risultati.append({"nome": ricetta.get("nome"), "allergeni": allergeni_trovati})
        else:
            skippate += 1  # conta come senza allergeni rilevati

    return {
        "status": "ok",
        "aggiornate": aggiornate,
        "con_allergeni": len(risultati),
        "senza_allergeni_trovati": skippate,
        "dettaglio": risultati,
    }


@router.post("/auto-rileva-allergeni-ricetta/{ricetta_id}")
async def auto_rileva_allergeni_singola(
    ricetta_id: str,
    data: Optional[dict] = None,
):
    """Suggerisce allergeni per una singola ricetta senza sovrascrivere (solo anteprima)."""
    ricetta = await db.ricette.find_one({"id": ricetta_id}, {"_id": 0})
    if not ricetta:
        raise HTTPException(404, "Ricetta non trovata")

    override = None
    if data is not None:
        if "ingredienti_dettaglio" in data:
            override = data.get("ingredienti_dettaglio") or []
        elif "ingredienti" in data:
            override = data.get("ingredienti") or []
    nomi_ing = estrai_nomi_ingredienti(ricetta, override=override)
    allergeni_trovati, trovati_da = rileva_allergeni(nomi_ing)

    return {
        "ricetta_id": ricetta_id,
        "nome": ricetta.get("nome"),
        "allergeni_suggeriti": allergeni_trovati,
        "trovati_da": trovati_da,
        "ingredienti_analizzati": nomi_ing,
    }


@router.post("/aggiorna-allergeni-ricetta")
async def aggiorna_allergeni_ricetta(data: dict):
    """Salva la lista degli allergeni (14 UE) e la dichiarazione nutrizionale per una ricetta."""
    ricetta_id = data.get("ricetta_id")
    allergeni = normalizza_allergeni(data.get("allergeni", []))
    nutrizionale = data.get(
        "nutrizionale", {}
    )  # {kcal, grassi, saturi, carboidrati, zuccheri, proteine, sale}
    if not ricetta_id:
        raise HTTPException(400, "ricetta_id mancante")
    result = await db.ricette.update_one(
        {"id": ricetta_id}, {"$set": {"allergeni": allergeni, "nutrizionale": nutrizionale,
                                       "allergeni_verificato": True,
                                       # salvataggio UMANO: la conferma che l'automatismo non può dare
                                       "allergeni_da_confermare": False}}
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Ricetta non trovata")
    return {"status": "ok", "allergeni": allergeni}


@router.post("/backfill-allergeni-da-confermare")
async def backfill_allergeni_da_confermare(request: Request):
    """Una tantum (idempotente): le ricette già marcate 'verificate' PRIMA della
    distinzione umano/automatismo (04/07/2026) non hanno traccia di CHI le ha
    verificate → per prudenza tornano tutte 'da confermare' una volta sola.
    Enzo le conferma aprendole e salvando dal tab allergeni. Il secondo run non
    trova più documenti senza il campo e non tocca nulla."""
    ruolo = (getattr(request.state, "user", None) or {}).get("ruolo", "")
    if ruolo != "amministratore":
        raise HTTPException(403, "Operazione riservata all'amministratore")
    res = await db.ricette.update_many(
        {"allergeni_verificato": True, "allergeni_da_confermare": {"$exists": False}},
        {"$set": {"allergeni_da_confermare": True}},
    )
    return {"ok": True, "marcate_da_confermare": res.modified_count}


@router.get("/registro-allergeni")
async def get_registro_allergeni():
    """Restituisce la matrice allergeni per tutte le ricette (per registro stampabile)."""
    ricette = await db.ricette.find(
        {}, {"_id": 0, "id": 1, "nome": 1, "allergeni": 1, "categoria": 1}
    ).to_list(1000)
    return {
        "allergeni_14": ALLERGENI_14,
        "ricette": [
            {
                "id": r["id"],
                "nome": r.get("nome", ""),
                "categoria": r.get("categoria", ""),
                "allergeni": r.get("allergeni", []),
            }
            for r in ricette
        ],
    }


@router.post("/aggiorna-ingredienti-ricetta")
async def aggiorna_ingredienti_ricetta(data: AggiornaIngredienteRicetta):
    """Aggiorna gli ingredienti di una ricetta con quantità e riferimenti al dizionario."""
    ricetta = await db.ricette.find_one({"id": data.ricetta_id}, {"_id": 0})
    if not ricetta:
        raise HTTPException(status_code=404, detail="Ricetta non trovata")

    # Carica dizionario
    prodotti = await db.dizionario_prodotti.find({}, {"_id": 0}).to_list(10000)
    dizionario = {p["nome_normalizzato"].lower(): p for p in prodotti}

    ingredienti_dettaglio = []
    costo_totale = 0

    for ing in data.ingredienti_dettaglio:
        prodotto = None
        if ing.prodotto_dizionario_id:
            prodotto = await db.dizionario_prodotti.find_one(
                {"id": ing.prodotto_dizionario_id}, {"_id": 0}
            )

        if not prodotto:
            prodotto = trova_prodotto_dizionario(ing.nome, dizionario)

        prezzo_kg = None
        costo = None
        qty_numeric = isinstance(ing.quantita, (int, float)) and ing.quantita > 0

        if prodotto and qty_numeric:
            prezzo_kg = float(prodotto.get("prezzo_kg", 0) or 0)
            quantita_kg = converti_in_kg(float(ing.quantita), ing.unita_misura, ing.nome)
            costo = round(quantita_kg * prezzo_kg, 2)
            costo_totale += costo
        elif prodotto:
            prezzo_kg = float(prodotto.get("prezzo_kg", 0) or 0)

        ingredienti_dettaglio.append(
            {
                "nome": ing.nome,
                "quantita": ing.quantita,
                "unita_misura": ing.unita_misura,
                "prodotto_dizionario_id": (
                    prodotto.get("id") if prodotto else (ing.prodotto_dizionario_id or None)
                ),
                "prezzo_kg": prezzo_kg or (ing.prezzo_kg if hasattr(ing, "prezzo_kg") else None),
                "costo_calcolato": costo,
                "costo_per_pezzo": getattr(ing, "costo_per_pezzo", None),
                "is_acquaviva": getattr(ing, "is_acquaviva", False),
            }
        )

    # Aggiorna ricetta
    await db.ricette.update_one(
        {"id": data.ricetta_id},
        {
            "$set": {
                "ingredienti_dettaglio": ingredienti_dettaglio,
                "costo_totale": round(costo_totale, 2),
                "costo_porzione": round(costo_totale / (ricetta.get("porzioni", 1) or 1), 2),
            }
        },
    )

    return {
        "status": "ok",
        "costo_totale": round(costo_totale, 2),
        "ingredienti": ingredienti_dettaglio,
    }


@router.post("/rinomina-ingrediente")
async def rinomina_ingrediente(
    nome_vecchio: str,
    nome_nuovo: str,
    solo_ricette_ids: str = None,  # IDs separati da virgola, o None per tutte
):
    """
    Rinomina un ingrediente in tutte le ricette (o in un sottoinsieme).
    Utile per correggere ingredienti non mappati dal tab Non Mappati.
    """
    filtro = {"ingredienti_dettaglio.nome": nome_vecchio}
    if solo_ricette_ids:
        ids = [x.strip() for x in solo_ricette_ids.split(",") if x.strip()]
        filtro["id"] = {"$in": ids}

    ricette = await db.ricette.find(
        filtro, {"_id": 0, "id": 1, "nome": 1, "ingredienti_dettaglio": 1}
    ).to_list(200)

    aggiornate = []
    for r in ricette:
        ings = r.get("ingredienti_dettaglio", [])
        modificato = False
        for i, ing in enumerate(ings):
            if ing.get("nome") == nome_vecchio:
                ings[i]["nome"] = nome_nuovo
                modificato = True
        if modificato:
            # Aggiorna anche la lista ingredienti (legacy)
            lista = [nome_nuovo if x == nome_vecchio else x for x in r.get("ingredienti", [])]
            await db.ricette.update_one(
                {"id": r["id"]}, {"$set": {"ingredienti_dettaglio": ings, "ingredienti": lista}}
            )
            aggiornate.append(r["nome"])

    return {
        "success": True,
        "nome_vecchio": nome_vecchio,
        "nome_nuovo": nome_nuovo,
        "ricette_aggiornate": aggiornate,
        "count": len(aggiornate),
    }


@router.post("/salva-porzioni-ricetta")
async def salva_porzioni_ricetta(ricetta_id: str, porzioni_base: int):
    """Salva il numero di pezzi/porzioni base della ricetta"""
    ricetta = await db.ricette.find_one({"id": ricetta_id})
    if not ricetta:
        raise HTTPException(status_code=404, detail="Ricetta non trovata")
    await db.ricette.update_one(
        {"id": ricetta_id},
        {"$set": {"porzioni": porzioni_base, "updated_at": datetime.now(timezone.utc).isoformat()}},
    )
    return {"success": True, "porzioni_base": porzioni_base}


@router.post("/usa-ricetta")
async def usa_ricetta(request: UsaRicettaRequest):
    """
    Usa una ricetta e scala le quantità dal magazzino.
    Deduce le quantità degli ingredienti dal dizionario prodotti.
    Se prodotto_dizionario_id manca, cerca per nome nel dizionario.
    """
    ricetta = await db.ricette.find_one({"id": request.ricetta_id}, {"_id": 0})
    if not ricetta:
        raise HTTPException(status_code=404, detail="Ricetta non trovata")

    ingredienti_dettaglio = ricetta.get("ingredienti_dettaglio", [])
    if not ingredienti_dettaglio:
        raise HTTPException(status_code=400, detail="Ricetta senza ingredienti dettagliati")

    # Carica dizionario per ricerca per nome
    prodotti_list = await db.dizionario_prodotti.find({}, {"_id": 0}).to_list(10000)
    dizionario = {p["nome_normalizzato"].lower(): p for p in prodotti_list}

    # Calcola quantità da scalare per ogni ingrediente
    ingredienti_scalati = []
    errori = []

    for ing in ingredienti_dettaglio:
        nome_ing = ing.get("nome", "").strip()

        # Verifica quantità valida
        quantita_raw = ing.get("quantita", 0)
        try:
            quantita_base = float(str(quantita_raw).replace(",", ".")) if quantita_raw else 0
        except (ValueError, TypeError):
            errori.append(f"{nome_ing}: quantità non valida ({quantita_raw})")
            continue

        if quantita_base <= 0:
            continue  # Salta ingredienti senza quantità (es. "q.b.")

        # Trova prodotto: prima per ID, poi per nome
        prodotto_id = ing.get("prodotto_dizionario_id")
        prodotto = None

        if prodotto_id:
            prodotto = await db.dizionario_prodotti.find_one({"id": prodotto_id}, {"_id": 0})

        if not prodotto and nome_ing:
            # Cerca per nome nel dizionario
            prodotto = trova_prodotto_dizionario(nome_ing, dizionario)

        if not prodotto:
            errori.append(f"{nome_ing}: non trovato nel dizionario")
            continue

        # Converti quantità in kg
        unita = ing.get("unita_misura") or ing.get("unita", "g")
        quantita = quantita_base * request.porzioni
        quantita_kg = converti_in_kg(quantita, unita, nome_ing)

        disponibile = prodotto.get("quantita_disponibile_kg", 0)
        if quantita_kg > disponibile:
            errori.append(
                f"{nome_ing}: richiesti {quantita_kg:.3f}kg, disponibili {disponibile:.3f}kg"
            )
            continue

        # Scala la quantità
        nuova_usata = prodotto.get("quantita_usata_kg", 0) + quantita_kg
        nuova_disponibile = prodotto.get("quantita_totale_kg", 0) - nuova_usata

        await db.dizionario_prodotti.update_one(
            {"id": prodotto["id"]},
            {
                "$set": {
                    "quantita_usata_kg": round(nuova_usata, 3),
                    "quantita_disponibile_kg": round(max(0, nuova_disponibile), 3),
                }
            },
        )

        ingredienti_scalati.append(
            {
                "nome": nome_ing,
                "prodotto_trovato": prodotto.get("nome_normalizzato"),
                "quantita_usata_kg": round(quantita_kg, 3),
                "disponibile_dopo": round(max(0, nuova_disponibile), 3),
            }
        )

    if errori and not ingredienti_scalati:
        raise HTTPException(status_code=400, detail="; ".join(errori))

    return {
        "status": "ok",
        "ricetta": ricetta.get("nome"),
        "porzioni": request.porzioni,
        "ingredienti_scalati": ingredienti_scalati,
        "avvisi": errori,
    }


@router.get("/ricette-riepilogo")
async def get_ricette_con_costi():
    """Ottiene tutte le ricette con riepilogo costi"""
    ricette = await db.ricette.find({}, {"_id": 0}).to_list(5000)
    prodotti = await db.dizionario_prodotti.find({}, {"_id": 0}).to_list(10000)
    dizionario = {p["nome_normalizzato"].lower(): p for p in prodotti}

    risultati = []
    for ricetta in ricette:
        costo_totale = 0
        ingredienti_con_prezzo = 0
        ingredienti_totali = 0

        if ricetta.get("ingredienti_dettaglio"):
            for ing in ricetta["ingredienti_dettaglio"]:
                nome_ing = (ing.get("nome") or "").strip()
                if not nome_ing:
                    continue
                ingredienti_totali += 1
                prezzo_ing = ing.get("prezzo_kg")
                costo_ing = ing.get("costo_calcolato")

                if costo_ing is not None and costo_ing > 0:
                    costo_totale += costo_ing
                    ingredienti_con_prezzo += 1
                elif prezzo_ing and prezzo_ing > 0:
                    # Ha prezzo ma quantità q.b. o 0 — conta come "con prezzo" ma non contribuisce al costo
                    ingredienti_con_prezzo += 1
                elif nome_ing:
                    # Nessun prezzo salvato — prova al volo
                    prodotto = trova_prodotto_dizionario(nome_ing, dizionario)
                    if prodotto and float(prodotto.get("prezzo_kg", 0) or 0) > 0:
                        try:
                            quantita_raw = ing.get("quantita", 0)
                            qb = str(quantita_raw).strip().lower() in (
                                "q.b.",
                                "qb",
                                "q.b",
                                "quanto basta",
                                "",
                            )
                            if not qb:
                                quantita = float(str(quantita_raw).replace(",", "."))
                                prezzo_kg = float(prodotto.get("prezzo_kg", 0))
                                quantita_kg = converti_in_kg(quantita, ing.get("unita_misura", "g"), ing.get("nome", ""))
                                costo_totale += quantita_kg * prezzo_kg
                            ingredienti_con_prezzo += 1
                        except Exception:
                            _LOG_INIT.debug("[food_cost] errore non bloccante ignorato")
        else:
            ingredienti_totali = len(ricetta.get("ingredienti", []))
            for nome in ricetta.get("ingredienti", []):
                if trova_prodotto_dizionario(nome, dizionario):
                    ingredienti_con_prezzo += 1

        porzioni = ricetta.get("porzioni", 1) or 1

        risultati.append(
            {
                "id": ricetta.get("id"),
                "nome": ricetta.get("nome"),
                "ingredienti_totali": ingredienti_totali,
                "ingredienti_con_prezzo": ingredienti_con_prezzo,
                "costo_totale": round(costo_totale, 2),
                "costo_porzione": round(costo_totale / porzioni, 2) if porzioni > 0 else 0,
                "completezza": f"{ingredienti_con_prezzo}/{ingredienti_totali}",
            }
        )

    return risultati


# ==================== HELPER FUNCTIONS ====================


def estrai_peso_e_unita(descrizione: str) -> Optional[tuple]:
    """
    Estrae peso e unità dalla descrizione del prodotto in fattura.
    Ritorna (peso_confezione_in_kg_o_lt, unita) o None se non trovato.

    IMPORTANTE: Ritorna None per descrizioni come "IN SACCHI 25 KG" dove
    il peso nella descrizione descrive il contenuto del sacco, NON il peso
    della confezione da acquistare (in quel caso Qt è già in KG).

    Gestisce pattern come:
      DA KG.25, KG 25, 25KG, x 5kg, x 2.5 kg   → kg per confezione
      GR.400, 400G, 400GR, G.500               → kg (grammi convertiti)
      L.5, 5L, 5LT, 2lt, x 2lt                → lt per confezione
      ML.500, 500ML                             → lt (ml convertiti)
    """
    desc = descrizione.upper()

    # Pattern "SACCHI": la parola SACCHI indica che il peso è del sacco,
    # non della confezione acquistata → Qt è già in KG totali → ritorna None
    if re.search(r"\bSACCH[IO]\b", desc):
        return None

    # KG: "DA KG.25", "x 5 KG", "x 25KG", "5KG", "5 KG"
    # NON: solo "KG" senza numero (es. "PECORINO KG")
    # Ordine: prima "x NNN KG" poi "NNN KG" poi "KG.NNN"
    kg_patterns = [
        r"[Xx]\s*(\d+(?:[.,]\d+)?)\s*KG\.?\b",  # x 25 KG, x 2.5KG
        r"(?:DA\s+)?KG\.?\s*(\d+(?:[.,]\d+)?)",  # DA KG.25, KG.25, KG 25
        r"(\d+(?:[.,]\d+)?)\s*KG\.?\b",  # 25KG, 25 KG, 25 KG.
    ]
    for pattern in kg_patterns:
        match = re.search(pattern, desc)
        if match:
            try:
                peso = float(match.group(1).replace(",", "."))
                if 0 < peso <= 2000:
                    return (peso, "kg")
            except ValueError:
                continue

    # ML: prima dei grammi per evitare falsi match su "G"
    ml_patterns = [
        r"(\d+(?:[.,]\d+)?)\s*ML\b",
        r"ML\.?\s*(\d+(?:[.,]\d+)?)",
    ]
    for pattern in ml_patterns:
        match = re.search(pattern, desc)
        if match:
            try:
                ml = float(match.group(1).replace(",", "."))
                if 0 < ml <= 100000:
                    return (ml / 1000, "lt")
            except ValueError:
                continue

    # Grammi: "GR.400", "400GR", "G.500", "400G" — non deve matchare "M.G. 82%"
    # Richiediamo che GR/G sia preceduto da spazio o inizio stringa (non da altra lettera)
    g_patterns = [
        r"(?<![A-Z])(?:GR|G)\.?\s*(\d+(?:[.,]\d+)?)(?!\s*[\d%])",
        r"(\d+(?:[.,]\d+)?)\s*(?:GR|G)\b(?!\s*%)",
    ]
    for pattern in g_patterns:
        match = re.search(pattern, desc)
        if match:
            try:
                grammi = float(match.group(1).replace(",", "."))
                if 0 < grammi <= 100000:
                    return (grammi / 1000, "kg")
            except ValueError:
                continue

    # Litri: "L.5", "5L", "LT.5", "5LT", "x 2lt"
    l_patterns = [
        r"[Xx]\s*(\d+(?:[.,]\d+)?)\s*L[T]?\b",  # x 2lt, x 5LT
        r"(\d+(?:[.,]\d+)?)\s*L[T]?\b",  # 5L, 5LT, 2lt
        r"L[T]?\.?\s*(\d+(?:[.,]\d+)?)",  # L.5, LT.5
    ]
    for pattern in l_patterns:
        match = re.search(pattern, desc)
        if match:
            try:
                litri = float(match.group(1).replace(",", "."))
                if 0 < litri <= 10000:
                    return (litri, "lt")
            except ValueError:
                continue

    return None


def normalizza_nome_prodotto(descrizione: str) -> str:
    """Pulisce e normalizza il nome del prodotto"""
    if not descrizione:
        return ""

    testo = descrizione.strip()

    # Rimuovi newline e spazi multipli
    testo = re.sub(r"\s+", " ", testo)

    # Rimuovi info lotto/scadenza dopo // (es: "// F2005 Scadenza 05/2027" o "// Lotto F2005 Scadenza 05/2027")
    testo = re.sub(r"\s*//.*$", "", testo, flags=re.IGNORECASE)

    # Rimuovi pesi e quantità
    testo = re.sub(r"\s*(?:DA\s+)?KG\.?\s*\d+(?:[.,]\d+)?", "", testo, flags=re.IGNORECASE)
    testo = re.sub(r"\s*\d+(?:[.,]\d+)?\s*KG\b", "", testo, flags=re.IGNORECASE)
    testo = re.sub(r"\s*(?:G|GR)\.?\s*\d+", "", testo, flags=re.IGNORECASE)
    testo = re.sub(r"\s*\d+\s*(?:G|GR)\b", "", testo, flags=re.IGNORECASE)
    testo = re.sub(r"\s*(?:L|LT)\.?\s*\d+(?:[.,]\d+)?", "", testo, flags=re.IGNORECASE)
    testo = re.sub(r"\s*\d+(?:[.,]\d+)?\s*(?:L|LT)\b", "", testo, flags=re.IGNORECASE)
    testo = re.sub(r"\s*ML\.?\s*\d+", "", testo, flags=re.IGNORECASE)
    testo = re.sub(r"\s*\d+\s*ML\b", "", testo, flags=re.IGNORECASE)

    # Rimuovi codici lotto (L.xxx, L.F.xxx, F2005, ecc.)
    testo = re.sub(r"\s+L\.?F?\.?\d*/?[\w\-]*", "", testo, flags=re.IGNORECASE)
    testo = re.sub(r"\s+[A-Z]\d{3,}", "", testo)  # es: F2005, B1234

    # Rimuovi moltiplicatori (x96, x20, X5)
    testo = re.sub(r"\s*[xX]\s*\d+", "", testo)

    # Rimuovi date
    testo = re.sub(r"\s*\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}", "", testo)

    # Rimuovi codici alfanumerici finali
    testo = re.sub(r"\s*-\s*\d{5,}$", "", testo)

    return testo.strip()[:100]


def trova_prodotto_dizionario(nome: str, dizionario: dict) -> Optional[dict]:
    """
    Cerca un prodotto nel dizionario con match multi-livello.
    Priorità: esatto > inizia con > parole chiave > contenuto parziale.
    Preferisce sempre prodotti con prezzo > 0.
    """
    if not nome:
        return None

    # Tabella alias: nomi comuni usati nelle ricette → keyword da cercare nel dizionario
    ALIAS = {
        "zucchero semolato": "zucchero raf.sem",
        "zucchero semol": "zucchero raf.sem",
        "zucchero bianco": "zucchero raf.sem",
        "zucchero": "zucchero",
        "semola": "semola",
        "farina 00": "farina 00",
        "farina 0": "farina 0",
        "uova": "uova",
        "uovo": "uova",
        "burro": "burro",
        "sale": "sale fino",
        "olio": "olio extravergine",
        "olio evo": "olio extravergine",
        "latte": "latte",
        "panna": "panna",
        "lievito": "lievito",
        "lievito di birra": "lievito birra",
        "strutto": "strutto",
        "ricotta": "ricotta",
        "cioccolato": "cioccolato",
        "cacao": "cacao",
        "vaniglia": "vaniglia",
        "miele": "miele",
        "limone": "limone",
        "cannella": "cannella",
        "margarina": "margar",
        "margarina crema": "margar",
        "tuorlo": "tuorlo",
        "tuorlo d'uovo": "tuorlo",
        "albume": "albume",
        "fecola": "fecola",
        "fecola di patate": "fecola",
        "amido": "amido",
        "amido di mais": "amido mais",
        "acqua": "acqua",
        "olio di semi": "olio di semi",
        "olio di girasole": "girasole",
        "aceto": "aceto",
        "pasta frolla": "pasta frolla",
        "pasta sfoglia": "pasta sfoglia",
        "gelatina": "gelatina",
        "colla di pesce": "colla di pesce",
        "wrustel": "wurstel",
        "capperi": "capperi",
        "fiori di zucca": "fiori",
        "provola": "provola",
        "prosciutto cotto": "prosciutto cotto",
        "prosciutto crudo": "prosciutto crudo",
        "porchetta": "porchetta",
        "p.cotto": "prosciutto cotto",
        "p.crudo": "prosciutto crudo",
        "melanzane": "melanzane",
        "zucchine": "zucchine",
        "peperoni": "peperoni",
        "pomodori": "pomodori",
        "patate": "patate",
        "cipolle": "cipolla",
        "aglio": "aglio",
        "basilico": "basilico",
        "prezzemolo": "prezzemolo",
        "mozzarella": "mozzarella",
        "parmigiano": "parmigiano",
        "pancetta": "pancetta",
        "guanciale": "guanciale",
        "mortadella": "mortadella",
        "salsiccia": "salsiccia",
        "pasta": "pasta",
        # Abbreviazioni e nomi speciali fornitori
        "farina 00 caputo rinforz.": "farina 00",
        "farina 00 caputo rinforz": "farina 00",
        "farina caputo rinforzo": "farina 00",
        "caputo rinforz": "farina 00",
        "margar wienercreme": "margar",
        "wienercreme": "margar",
        "est.zuppa inglese": "zuppa inglese",
        "est. zuppa inglese": "zuppa inglese",
        "estratto zuppa inglese": "zuppa inglese",
        "zuppa inglese": "zuppa inglese",
        "crema chantilly": "panna",
        "beurre": "burro",
        "fioretto": "farina",
        "frumento tenero": "farina",
        "frumento duro": "semola",
        "lievito madre": "lievito",
        "pasta madre": "lievito",
        "glucosio": "glucosio",
        "sciroppo glucosio": "glucosio",
        "invertzucker": "zucchero invertito",
        "zucchero invertito": "zucchero",
        "trealosio": "zucchero",
        "sorbitolo": "sorbitolo",
        "alcol": "alcol",
        "alcool": "alcol",
        "rum": "rum",
        "liquore": "liquore",
        "pasta di mandorle": "pasta mandorle",
        "frangipane": "pasta mandorle",
        "pistacchio": "pistacchio",
        "mandorle": "mandorle",
        "nocciole": "nocciole",
        "noci": "noci",
        "uvetta": "uvetta",
        "canditi": "canditi",
        "arancia candita": "canditi arancia",
        "cedro candito": "canditi cedro",
        "ciliegie candite": "canditi ciliegie",
        "frutta candita": "canditi",
    }

    nome_lower = nome.lower().strip()
    # Applica alias se presente (cerca anche versioni con/senza punti)
    nome_no_punti = re.sub(r"\.", "", nome_lower).strip()
    # Rimuovi peso/quantità dal nome per trovare l'alias
    nome_per_alias = re.sub(
        r"\b\d+[\.,]?\d*\s*(g|kg|gr|ml|lt|l|pz|pzz)?\b", "", nome_lower, flags=re.IGNORECASE
    ).strip()
    # Rimuovi anche unità standalone (es. "kg" senza numero come in "zucchero semolato kg 1")
    nome_per_alias = re.sub(
        r"\s+\b(kg|gr|ml|lt|pz|pzz|g)\b\s*", " ", nome_per_alias, flags=re.IGNORECASE
    ).strip()
    nome_per_alias = re.sub(r"\s+", " ", nome_per_alias).strip()
    nome_ricerca = (
        ALIAS.get(nome_lower) or ALIAS.get(nome_no_punti) or ALIAS.get(nome_per_alias) or nome_lower
    )

    # Normalizza: rimuovi pesi/quantità dal nome ingrediente e punti abbreviativi
    nome_clean = re.sub(
        r"\b\d+[\.,]?\d*\s*(g|kg|gr|ml|lt|l|pz|pzz)?\b", "", nome_ricerca, flags=re.IGNORECASE
    ).strip()
    nome_clean = re.sub(r"\s+", " ", nome_clean).strip()
    # Versione senza punti per confronti con chiavi dizionario
    nome_clean_no_punti = re.sub(r"\.+", " ", nome_clean).strip()
    nome_clean_no_punti = re.sub(r"\s+", " ", nome_clean_no_punti).strip()
    parole = [p for p in nome_clean_no_punti.split() if len(p) >= 3]

    # 1. Match esatto
    if nome_clean in dizionario:
        return dizionario[nome_clean]
    if nome_lower in dizionario:
        return dizionario[nome_lower]

    # 1b. Match con chiavi dizionario normalizzate senza punti
    # Crea dizionario chiave-senza-punti → chiave originale
    diz_no_punti = {re.sub(r"\.+", " ", k).replace("  ", " "): k for k in dizionario}
    if nome_clean_no_punti in diz_no_punti:
        return dizionario[diz_no_punti[nome_clean_no_punti]]

    # 2. Il nome dell'ingrediente inizia con le stesse parole del prodotto
    # ES: "semola" deve matchare "semola media xxl mad", NON "ciabattina con semola"
    # Tie-break dei match: prima i prodotti CON un prezzo (prezzo>0), poi il PIÙ
    # ECONOMICO. Prima si usava -prezzo, che a parità di priorità faceva vincere
    # il prezzo più ALTO: "farina" agganciava "farina di mandorle €12.9/kg" al
    # posto della "farina 00 €0.62" → food cost gonfiato in modo sistematico e
    # silenzioso. `_pref` mette gli omonimi cari in fondo e i senza-prezzo per
    # ultimi, coerente col commento originale ("preferenza prezzo > 0").
    def _pref(p):
        return p if p > 0 else float("inf")

    candidati_esatti = []  # (priorità, _pref(prezzo), chiave, prodotto)
    for key, prod in dizionario.items():
        prezzo = float(prod.get("prezzo_kg", 0) or 0)
        key_no_punti = re.sub(r"\.+", " ", key).replace("  ", " ").strip()

        if key.startswith(nome_clean) or key_no_punti.startswith(nome_clean_no_punti):
            candidati_esatti.append((0, _pref(prezzo), key, prod))
        elif parole and (key.startswith(parole[0]) or key_no_punti.startswith(parole[0])):
            match_count = sum(1 for p in parole if p in key or p in key_no_punti)
            if match_count >= max(1, len(parole) // 2):
                candidati_esatti.append((1, _pref(prezzo), key, prod))
        elif parole and len(parole[0]) >= 5:
            prefix = parole[0][:6]
            if key.startswith(prefix) or key_no_punti.startswith(prefix):
                candidati_esatti.append((2, _pref(prezzo), key, prod))

    if candidati_esatti:
        candidati_esatti.sort(key=lambda x: (x[0], x[1]))
        return candidati_esatti[0][3]

    # 3. Tutte le parole chiave dell'ingrediente compaiono nel key del dizionario
    # ES: "zucchero semolato" deve trovare "zucchero semolato kg1", NON "zucchero a velo"
    if len(parole) >= 2:
        multi_word_matches = []
        for key, prod in dizionario.items():
            prezzo = float(prod.get("prezzo_kg", 0) or 0)
            if all(p in key for p in parole):
                multi_word_matches.append((_pref(prezzo), key, prod))
        if multi_word_matches:
            multi_word_matches.sort()
            return multi_word_matches[0][2]

    # 4. Match contenuto: nome_ingrediente è sottostringa del key (con preferenza prezzo > 0)
    contenuto_matches = []
    for key, prod in dizionario.items():
        prezzo = float(prod.get("prezzo_kg", 0) or 0)
        if nome_clean in key:
            posizione = key.find(nome_clean)
            contenuto_matches.append((posizione, _pref(prezzo), key, prod))

    if contenuto_matches:
        contenuto_matches.sort(key=lambda x: (x[0], x[1]))
        return contenuto_matches[0][3]

    # 5. Match inverso: il key è contenuto nel nome ingrediente
    inverso_matches = []
    for key, prod in dizionario.items():
        prezzo = float(prod.get("prezzo_kg", 0) or 0)
        if key in nome_clean and len(key) >= 4:
            inverso_matches.append((-len(key), _pref(prezzo), key, prod))

    if inverso_matches:
        inverso_matches.sort()
        return inverso_matches[0][3]

    # 5b. Match parola chiave: ogni parola significativa dell'ingrediente compare nel key
    # ES: "melanzane" deve trovare "berni melanzane filetti" anche se non inizia con "melanzane"
    if parole:
        parola_principale = max(parole, key=len)  # parola più lunga = più specifica
        if len(parola_principale) >= 5:
            keyword_matches = []
            for key, prod in dizionario.items():
                prezzo = float(prod.get("prezzo_kg", 0) or 0)
                if parola_principale in key:
                    keyword_matches.append((_pref(prezzo), key, prod))
            if keyword_matches:
                keyword_matches.sort()
                return keyword_matches[0][2]

    # 6. Fallback: prima parola (almeno 4 caratteri) con preferenza a prodotti con prezzo
    prima_parola = nome_clean.split()[0] if nome_clean.split() else ""
    if prima_parola and len(prima_parola) >= 4:
        fallback = []
        for key, prod in dizionario.items():
            prezzo = float(prod.get("prezzo_kg", 0) or 0)
            if key.startswith(prima_parola):
                fallback.append((_pref(prezzo), key, prod))
        if fallback:
            fallback.sort()
            return fallback[0][2]

    return None


# Unità "a confezione": NON sono una massa e non si convertono in kg senza il
# peso reale del prodotto (regola Enzo: mai conversioni inventate). Prima
# finivano nel ramo default e venivano divise per 1000 — cioè "1 cartone = 1
# grammo", con food cost praticamente azzerato senza che nessuno se ne
# accorgesse (audit quantità/unità, fix 25/07/2026).
UNITA_A_CONFEZIONE = {
    "cf", "conf", "confezione", "confezioni", "ct", "cartone", "cartoni",
    "collo", "colli", "cassa", "casse", "bott", "bottiglia", "bottiglie",
    "kar", "pacco", "pacchi", "busta", "buste", "vaschetta", "vaschette",
}


def _e_bevanda_a_unita(nome: str, prodotto: dict | None = None) -> bool:
    """True se l'ingrediente è del reparto bar (acqua, birre, vino, prosecco,
    liquori, amari, sciroppi, succhi, bibite): si compra e si conta a
    bottiglia/cartone, MAI a kg (regola Enzo). Categoria dal dizionario se
    c'è, altrimenti dedotta dal nome con lo stesso classificatore del listino."""
    cat = ((prodotto or {}).get("categoria") or "").upper()
    if not cat:
        try:
            from app.lotti.routers.listino import _categoria as _cat_listino
            cat = (_cat_listino(nome or "") or "").upper()
        except Exception:
            cat = ""
    return cat in CATEGORIE_VENDUTE_A_UNITA


def converti_in_kg(quantita: float, unita: str, nome: str = "") -> float:
    """Converte una quantità nell'unità base (kg o lt).
    I PEZZI usano il peso reale del pezzo (regola uova di Enzo: uovo 60 g,
    tuorlo 19 g, albume 33 g; altrimenti 50 g generici) — prima venivano
    trattati come grammi: "5 pz" diventava 0,005 kg.
    Le unità a confezione (cartone, cassa, bottiglia…) restituiscono 0: senza
    il peso reale NON si inventa una conversione (chi chiama deve accorgersene
    e chiedere il peso, vedi coda "prodotto_senza_peso")."""
    if not quantita:
        return 0

    unita = (unita or "g").lower().strip()

    if unita in ["kg", "kilogrammi", "lt", "litri", "l"]:
        return quantita
    elif unita in ["g", "gr", "grammi", "ml"]:
        return quantita / 1000
    elif unita in ["cl"]:
        # 1 cl = 0,01 l — prima finiva nel default (÷1000): errore ×10
        return quantita / 100
    elif unita in ["dl"]:
        return quantita / 10
    elif unita in UNITA_A_CONFEZIONE:
        return 0
    elif unita in ["pz", "pezzi", "pz.", "n", "nr", "unita", "unità"]:
        n = (nome or "").lower()
        if "tuorl" in n:
            peso_g = 19.0
        elif "album" in n:
            peso_g = 33.0
        elif "uov" in n:
            peso_g = 60.0
        else:
            peso_g = 50.0
        return quantita * peso_g / 1000
    else:
        # Default: assume grammi per ingredienti
        return quantita / 1000


# ==================== STAMPA SCHEDA RICETTA ====================


@router.get("/stampa-ricetta/{ricetta_id}")
async def stampa_scheda_ricetta(ricetta_id: str):
    """Genera una scheda ricetta stampabile in formato HTML con food cost."""
    from fastapi.responses import HTMLResponse

    ricetta = await db.ricette.find_one(
        {"$or": [{"id": ricetta_id}, {"ricetta_id": ricetta_id}]}, {"_id": 0}
    )
    if not ricetta:
        raise HTTPException(status_code=404, detail="Ricetta non trovata")

    prodotti = await db.dizionario_prodotti.find({}, {"_id": 0}).to_list(10000)
    dizionario = {p["nome_normalizzato"].lower(): p for p in prodotti}

    ingredienti_dettaglio = ricetta.get("ingredienti_dettaglio", [])
    costo_totale = 0
    rows = ""

    for ing in ingredienti_dettaglio:
        nome = ing.get("nome", "").strip()
        if not nome:
            continue
        quantita_raw = ing.get("quantita", 0)
        unita = ing.get("unita_misura") or ing.get("unita", "g")
        try:
            qt = float(str(quantita_raw).replace(",", ".")) if quantita_raw else 0
        except (ValueError, TypeError):
            qt = 0

        prodotto = trova_prodotto_dizionario(nome, dizionario)
        prezzo_kg = float(prodotto.get("prezzo_kg", 0)) if prodotto else 0
        prodotto_nome = prodotto.get("nome_normalizzato", "-") if prodotto else "-"

        costo_ing = converti_in_kg(qt, unita, nome) * prezzo_kg if qt > 0 else 0
        costo_totale += costo_ing
        qt_display = (
            f"{str(quantita_raw)} {unita}" if str(quantita_raw) not in ("0", "") else "q.b."
        )
        costo_display = f"€{costo_ing:.3f}" if costo_ing > 0 else "-"
        color = "color:#276749" if prodotto else "color:#9b2c2c"
        trovato = prodotto_nome[:35] if prodotto else "Non in dizionario"

        rows += f"""<tr>
          <td style="padding:6px 8px;border-bottom:1px solid #e2e8f0;font-weight:500">{nome}</td>
          <td style="padding:6px 8px;border-bottom:1px solid #e2e8f0;text-align:center">{qt_display}</td>
          <td style="padding:6px 8px;border-bottom:1px solid #e2e8f0;font-size:11px;{color}">{trovato}</td>
          <td style="padding:6px 8px;border-bottom:1px solid #e2e8f0;text-align:right;font-weight:500">{costo_display}</td>
        </tr>"""

    porzioni = ricetta.get("porzioni", ricetta.get("pezzi_ricetta_base", 100)) or 100
    costo_per_pezzo = costo_totale / porzioni if porzioni > 0 else 0
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    note_html = (
        ricetta.get("procedimento")
        or ricetta.get("note")
        or "<i style='color:#aaa'>Nessuna nota inserita.</i>"
    )

    html = f"""<!DOCTYPE html>
<html lang="it"><head><meta charset="UTF-8">
<title>Scheda Ricetta – {ricetta.get('nome','')}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:Arial,sans-serif;color:#1a1a1a;background:white;padding:24px;max-width:800px;margin:0 auto}}
.hdr{{border-bottom:3px solid #e07b3c;padding-bottom:12px;margin-bottom:20px}}
.hdr h1{{font-size:22px;color:#c05621;text-transform:capitalize}}
.hdr .meta{{font-size:11px;color:#718096;margin-top:4px}}
.sec{{font-size:13px;font-weight:bold;color:#744210;background:#fefcbf;padding:6px 10px;border-left:3px solid #e07b3c;margin:16px 0 8px}}
table{{width:100%;border-collapse:collapse;font-size:12px}}
th{{background:#fff3e0;padding:6px 8px;text-align:left;font-weight:600;color:#744210;border-bottom:2px solid #e07b3c}}
tr:nth-child(even) td{{background:#fffaf0}}
.cost-box{{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:16px 0}}
.cost-item{{background:#f7fafc;border:1px solid #e2e8f0;border-radius:8px;padding:12px;text-align:center}}
.cost-item .val{{font-size:20px;font-weight:bold;color:#2c5282}}
.cost-item .lbl{{font-size:10px;color:#718096;margin-top:2px}}
.firma{{margin-top:32px;border-top:1px solid #e2e8f0;padding-top:16px;display:flex;justify-content:space-between}}
.firma-box{{border-top:1px solid #aaa;width:180px;text-align:center;padding-top:4px;font-size:10px;color:#555}}
.print-btn{{position:fixed;bottom:20px;right:20px;background:#e07b3c;color:white;border:none;padding:10px 18px;border-radius:8px;cursor:pointer;font-size:14px;box-shadow:0 4px 12px rgba(0,0,0,.2)}}
@media print{{.print-btn{{display:none}}}}
</style></head><body>
<button class="print-btn" onclick="window.print()">Stampa / Salva PDF</button>
<div class="hdr"><h1>{ricetta.get('nome','')}</h1>
<div class="meta">Porzioni base: {porzioni} pz &nbsp;|&nbsp; Generata: {now_str} &nbsp;|&nbsp; Ceraldi Group S.R.L.</div></div>
<div class="cost-box">
  <div class="cost-item"><div class="val">€{costo_totale:.3f}</div><div class="lbl">Costo Totale ({porzioni} pz)</div></div>
  <div class="cost-item"><div class="val">€{costo_per_pezzo:.3f}</div><div class="lbl">Costo per Pezzo</div></div>
  <div class="cost-item"><div class="val">{len(ingredienti_dettaglio)}</div><div class="lbl">Ingredienti</div></div>
</div>
<div class="sec">Ingredienti</div>
<table><thead><tr><th>Ingrediente</th><th>Quantità</th><th>Prodotto Dizionario</th><th style="text-align:right">Costo</th></tr></thead>
<tbody>{rows}
<tr style="font-weight:bold;background:#fff3e0">
  <td colspan="3" style="padding:8px;text-align:right;color:#744210">TOTALE FOOD COST</td>
  <td style="padding:8px;text-align:right;color:#276749;font-size:14px">€{costo_totale:.3f}</td>
</tr></tbody></table>
<div class="sec">Note / Procedimento</div>
<div style="background:#f9f9f9;border:1px solid #e2e8f0;border-radius:6px;padding:12px;font-size:12px;line-height:1.6;min-height:80px">{note_html}</div>
<div class="firma"><div class="firma-box">Chef / Responsabile Ricetta</div><div class="firma-box">Responsabile HACCP</div></div>
</body></html>"""

    return HTMLResponse(content=html)


# ==================== CALCOLO NUTRIZIONALE USDA ====================

import json as _json
import pathlib as _pathlib
import unicodedata as _unicodedata

from app.lotti.db import database as db


def _carica_usda() -> list:
    """Carica il database USDA dal file JSON."""
    _db_path = _pathlib.Path(__file__).parent.parent / "data" / "usda_nutrizionale.json"
    with open(_db_path, "r", encoding="utf-8") as f:
        return _json.load(f)


def _normalizza(testo: str) -> str:
    """Normalizza testo per confronto: minuscolo, senza accenti, senza punteggiatura."""
    t = testo.lower().strip()
    t = _unicodedata.normalize("NFD", t)
    t = "".join(c for c in t if _unicodedata.category(c) != "Mn")
    return t


def _trova_voce_usda(nome_ingrediente: str, db_usda: list) -> dict | None:
    """
    Cerca la voce USDA più adatta per un ingrediente.
    Confronta per alias con match esatto prima, poi parziale.
    """
    nome_n = _normalizza(nome_ingrediente)
    # Esatto su alias
    for voce in db_usda:
        for alias in voce["aliases"]:
            if _normalizza(alias) == nome_n:
                return voce
    # Parziale: alias contenuto nel nome ingrediente
    for voce in db_usda:
        for alias in voce["aliases"]:
            if _normalizza(alias) in nome_n or nome_n in _normalizza(alias):
                return voce
    return None


@router.post("/calcola-nutrizionale/{ricetta_id}")
async def calcola_nutrizionale_ricetta(ricetta_id: str):
    """
    Calcola automaticamente i valori nutrizionali per 100g di prodotto finito
    basandosi sugli ingredienti della ricetta e il database USDA.

    Restituisce:
      - valori_nutrizionali: {kcal, kj, grassi, saturi, carboidrati, zuccheri, fibre, proteine, sale}
      - copertura: % ingredienti trovati nel DB USDA
      - ingredienti_non_trovati: lista ingredienti senza corrispondenza USDA
    """
    ricetta = await db.ricette.find_one({"id": ricetta_id}, {"_id": 0})
    if not ricetta:
        raise HTTPException(404, "Ricetta non trovata")

    # Se la ricetta ha componenti[], usa il BOM esploso come sorgente ingredienti
    if ricetta.get("componenti"):
        from app.lotti.routers.ricette import _esplodi_componente

        porzioni_base = float(ricetta.get("porzioni", 1) or 1)
        visitati = {ricetta_id}
        ing_flat_totale = []
        for comp in ricetta["componenti"]:
            flat, _ = await _esplodi_componente(comp, porzioni_base, porzioni_base, visitati)
            ing_flat_totale.extend(flat)
        # Deduplica per (nome, um)
        raggruppati: dict = {}
        for ing in ing_flat_totale:
            chiave = (ing["nome"], ing["unita_misura"])
            raggruppati[chiave] = raggruppati.get(chiave, 0.0) + ing["quantita"]
        ingredienti = [
            {"nome": n, "quantita": qt, "unita_misura": um} for (n, um), qt in raggruppati.items()
        ]
    else:
        ingredienti = ricetta.get("ingredienti_dettaglio", [])

    if not ingredienti:
        raise HTTPException(422, "Ricetta senza ingredienti dettaglio")

    db_usda = _carica_usda()
    campi = [
        "kcal",
        "kj",
        "grassi",
        "saturi",
        "carboidrati",
        "zuccheri",
        "fibre",
        "proteine",
        "sale",
    ]

    # Calcola peso totale usato (g) - solo ingredienti con unita peso
    UNITA_PESO = {"g", "gr", "kg", "ml", "cl", "dl", "l", "lt", "litri", "grammi", "chili"}

    peso_totale_g = 0.0
    contributi = []  # lista di (nome, gram_g, voce_usda | None)
    non_trovati = []

    for ing in ingredienti:
        nome = ing.get("nome_ingrediente") or ing.get("nome") or ""
        qt = float(ing.get("quantita", 0) or 0)
        unita = str(ing.get("unita_misura") or ing.get("unita", "g") or "g").lower().strip()

        # Converte in grammi
        if unita in ("kg", "chili"):
            gram_g = qt * 1000
        elif unita in ("l", "lt", "litri"):
            gram_g = qt * 1000
        elif unita in ("dl",):
            gram_g = qt * 100
        elif unita in ("cl",):
            gram_g = qt * 10
        elif unita in ("ml",):
            gram_g = qt
        elif unita in ("g", "gr", "grammi"):
            gram_g = qt
        else:
            # unità non peso (pz, n., cucchiai ecc.) – escludi dal calcolo nutrizionale
            non_trovati.append(f"{nome} ({unita})")
            continue

        peso_totale_g += gram_g
        voce = _trova_voce_usda(nome, db_usda)
        if voce:
            contributi.append((nome, gram_g, voce))
        else:
            contributi.append((nome, gram_g, None))
            non_trovati.append(nome)

    if peso_totale_g == 0:
        raise HTTPException(422, "Nessun ingrediente con unità di peso (g/kg/ml/l)")

    # Calcola valori per 100g di prodotto finito
    totali = {c: 0.0 for c in campi}
    ingredienti_mappati = 0

    for nome, gram_g, voce in contributi:
        if voce is None:
            continue
        ingredienti_mappati += 1
        fattore = gram_g / peso_totale_g  # contributo relativo
        for campo in campi:
            totali[campo] += fattore * voce["per_100g"].get(campo, 0.0)

    # Arrotondamento
    valori = {c: round(totali[c], 1) for c in campi}

    # Copertura %
    totale_ing_peso = len(contributi)
    copertura = round(
        (ingredienti_mappati / totale_ing_peso * 100) if totale_ing_peso > 0 else 0, 1
    )

    # Salva in DB
    await db.ricette.update_one({"id": ricetta_id}, {"$set": {"nutrizionale": valori}})

    return {
        "ricetta_id": ricetta_id,
        "valori_nutrizionali": valori,
        "copertura_percentuale": copertura,
        "ingredienti_non_trovati": non_trovati,
        "peso_totale_g": round(peso_totale_g, 1),
        "ingredienti_analizzati": totale_ing_peso,
        "ingredienti_mappati": ingredienti_mappati,
    }


@router.get("/nutrizionale/{ricetta_id}")
async def get_nutrizionale_ricetta(ricetta_id: str):
    """Restituisce i valori nutrizionali salvati per una ricetta."""
    ricetta = await db.ricette.find_one(
        {"id": ricetta_id}, {"_id": 0, "nutrizionale": 1, "nome": 1}
    )
    if not ricetta:
        raise HTTPException(404, "Ricetta non trovata")
    return {
        "ricetta_id": ricetta_id,
        "nome": ricetta.get("nome", ""),
        "valori_nutrizionali": ricetta.get("nutrizionale", {}),
    }


@router.get("/storico-prezzi")
async def get_storico_prezzi(nome: str, limit: int = 6):
    """
    Storico ultimi N prezzi per un ingrediente, estratto da lotti_fornitori.
    Restituisce lista ordinata per data con prezzo_kg, data_fattura, fornitore.
    """
    query = {
        "$or": [
            {"prodotto_nome_norm": {"$regex": re.escape(nome.lower().strip()), "$options": "i"}},
            {"prodotto_nome": {"$regex": re.escape(nome.strip()), "$options": "i"}},
        ],
        "prezzo_unitario": {"$gt": 0},
        "data_fattura": {"$exists": True, "$nin": [None, ""]},
    }
    cursor = db.lotti_fornitori.find(
        query,
        {
            "_id": 0,
            "prezzo_unitario": 1,
            "data_fattura": 1,
            "fornitore": 1,
            "unita_misura": 1,
            "prodotto_nome": 1,
        },
    )
    docs = await cursor.to_list(100)
    # Filtra e ordina per data
    voci = []
    for d in docs:
        data_str = d.get("data_fattura", "")
        if not data_str:
            continue
        try:
            if "/" in str(data_str):
                parts = str(data_str).split("/")
                if len(parts) == 3:
                    data_str = f"{parts[2]}-{parts[1]}-{parts[0]}"
            dt = datetime.fromisoformat(str(data_str)[:10])
        except Exception:
            continue
        voci.append(
            {
                "data": dt.isoformat()[:10],
                "prezzo": round(float(d.get("prezzo_unitario", 0)), 4),
                "fornitore": d.get("fornitore", ""),
            }
        )
    voci.sort(key=lambda x: x["data"])
    # Dedup: tieni solo l'ultimo per giorno/fornitore
    seen = set()
    unici = []
    for v in reversed(voci):
        k = (v["data"], v["fornitore"])
        if k not in seen:
            seen.add(k)
            unici.append(v)
    unici.reverse()
    return {"nome": nome, "storico": unici[-limit:]}
