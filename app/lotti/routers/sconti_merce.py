"""
Router per gestione Sconti Merce.
Registra prodotti ricevuti come sconto (merce gratuita) dai fornitori.
Permette il riepilogo mensile e annuale del valore ricevuto.
"""

from datetime import datetime, timezone, date
from typing import Optional
import uuid
import logging
_LOG_INIT = logging.getLogger("uvicorn.error")
import re

from fastapi import Depends, APIRouter, HTTPException, Query
from pydantic import BaseModel
from app.lotti.db import database as db
# 25/07/2026 (TRANCHE 2 sicurezza): gli import e le sincronizzazioni di
# MASSA riscrivono cataloghi e listini interi. Riservati all'amministratore.
from app.lotti.auth import require_admin

router = APIRouter(prefix="/sconti-merce", tags=["Sconti Merce"])


class ScontoMerce(BaseModel):
    data: str  # Data ricezione (dd/mm/yyyy)
    fornitore: str
    prodotto: str
    cartoni: float = 0  # Numero cartoni/colli ricevuti
    pezzi_per_cartone: float = 0  # Pezzi per cartone (opzionale)
    pezzi_totali: float = 0  # Totale pezzi (calcolato o inserito)
    valore_unitario: float = 0  # Valore di listino per unità/cartone
    valore_totale: float = 0  # Valore totale sconto
    fattura_riferimento: str = ""  # Numero fattura collegata (opzionale)
    note: str = ""


class ScontoResponse(ScontoMerce):
    id: str
    mese: int
    anno: int
    created_at: str


@router.get("/")
async def get_sconti(
    fornitore: Optional[str] = Query(None),
    mese: Optional[int] = Query(None),
    anno: Optional[int] = Query(None),
    solo_attivi: bool = Query(True, description="Filtra solo fornitori non esclusi"),
    limit: int = Query(200, le=1000),
):
    """Lista sconti merce con filtri opzionali"""
    query = {}
    if fornitore:
        query["fornitore"] = {"$regex": fornitore, "$options": "i"}
    if mese:
        query["mese"] = mese
    if anno:
        query["anno"] = anno

    # ordine per data VERA (data = data_fattura, formato misto): il sort del DB
    # era lessicografico e il limit poteva tagliare le righe più recenti.
    from app.lotti.routers.utils import parse_data_flessibile
    _tutti = await db.sconti_merce.find(query, {"_id": 0}).to_list(5000)
    _tutti.sort(key=lambda s: parse_data_flessibile(s.get("data")) or date.min, reverse=True)
    sconti = _tutti[:limit]

    # OPT-IN: mostra SOLO i fornitori con flag 'monitora_sconti' attivo.
    # (logica separata e indipendente da 'escluso', che riguarda l'import magazzino)
    if solo_attivi:
        import re as _re
        def _n(s):
            return _re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()
        monitorati = await db.fornitori.find(
            {"monitora_sconti": True}, {"_id": 0, "nome": 1}
        ).to_list(1000)
        chiavi = [_n(f.get("nome", "")) for f in monitorati if f.get("nome")]

        def _ok(forn):
            fn = _n(forn)
            return any(k and (k == fn or k in fn or fn in k) for k in chiavi)

        sconti = [s for s in sconti if _ok(s.get("fornitore", ""))]

    return sconti


@router.post("/", response_model=ScontoResponse)
async def crea_sconto(sconto: ScontoMerce):
    """Registra un nuovo sconto merce"""
    doc = sconto.model_dump()
    doc["id"] = str(uuid.uuid4())

    # Calcola pezzi totali se non forniti
    if doc["pezzi_totali"] == 0 and doc["cartoni"] > 0 and doc["pezzi_per_cartone"] > 0:
        doc["pezzi_totali"] = round(doc["cartoni"] * doc["pezzi_per_cartone"], 2)

    # Calcola valore totale se non fornito
    if doc["valore_totale"] == 0 and doc["valore_unitario"] > 0:
        unita = doc["cartoni"] if doc["cartoni"] > 0 else doc["pezzi_totali"]
        doc["valore_totale"] = round(doc["valore_unitario"] * unita, 2)

    # Estrai mese e anno dalla data
    try:
        if "/" in doc["data"]:
            parti = doc["data"].split("/")
            doc["giorno"] = int(parti[0])
            doc["mese"] = int(parti[1])
            doc["anno"] = int(parti[2])
        else:
            dt = datetime.fromisoformat(doc["data"])
            doc["mese"] = dt.month
            doc["anno"] = dt.year
    except Exception:
        now = datetime.now(timezone.utc)
        doc["mese"] = now.month
        doc["anno"] = now.year

    doc["created_at"] = datetime.now(timezone.utc).isoformat()

    await db.sconti_merce.insert_one(doc)
    if "_id" in doc:
        del doc["_id"]
    return doc


@router.put("/{sconto_id}")
async def aggiorna_sconto(sconto_id: str, sconto: ScontoMerce):
    """Aggiorna uno sconto esistente"""
    existing = await db.sconti_merce.find_one({"id": sconto_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Sconto non trovato")

    doc = sconto.model_dump()

    if doc["pezzi_totali"] == 0 and doc["cartoni"] > 0 and doc["pezzi_per_cartone"] > 0:
        doc["pezzi_totali"] = round(doc["cartoni"] * doc["pezzi_per_cartone"], 2)

    if doc["valore_totale"] == 0 and doc["valore_unitario"] > 0:
        unita = doc["cartoni"] if doc["cartoni"] > 0 else doc["pezzi_totali"]
        doc["valore_totale"] = round(doc["valore_unitario"] * unita, 2)

    try:
        if "/" in doc["data"]:
            parti = doc["data"].split("/")
            doc["mese"] = int(parti[1])
            doc["anno"] = int(parti[2])
    except Exception:
        _LOG_INIT.debug("[sconti_merce] errore non bloccante ignorato")

    doc["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.sconti_merce.update_one({"id": sconto_id}, {"$set": doc})
    return {"success": True}


@router.delete("/{sconto_id}")
async def elimina_sconto(sconto_id: str):
    """Elimina uno sconto"""
    result = await db.sconti_merce.delete_one({"id": sconto_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Sconto non trovato")
    return {"success": True}


@router.post("/importa-da-fatture")
async def importa_sconti_da_fatture(_admin=Depends(require_admin)):
    """
    Scansiona tutte le fatture nel DB e importa come 'sconto merce'
    tutti i prodotti con TipoCessionePrestazione=SC (prezzo €0.00).
    Tenta di valorizzare trovando il prezzo del prodotto identico nella stessa fattura.
    """
    fatture = await db.fatture.find({}, {"_id": 0}).to_list(10000)

    importati = 0
    saltati = 0
    valorizzati = 0

    for fattura in fatture:
        fornitore = fattura.get("fornitore", "").strip()
        if not fornitore:
            continue

        numero_fattura = fattura.get("numero_fattura", "")
        data_fattura = fattura.get("data_fattura", "")
        prodotti_fattura = fattura.get("prodotti", [])

        # Costruisci due indici dalla fattura:
        # 1. Per nome descrizione (uppercase)
        # 2. Per codice EN/COD_FORNITORE
        prezzi_per_nome: dict = {}
        prezzi_per_codice: dict = {}  # chiave: codice_valore
        for p in prodotti_fattura:
            pr = float(p.get("prezzo", 0) or 0)
            qt = float(p.get("quantita", 0) or 0)
            if pr <= 0:
                continue
            nome = (p.get("descrizione", "") or p.get("nome", "")).strip().upper()
            if nome:
                prezzi_per_nome[nome] = {
                    "prezzo_unitario": pr,
                    "prezzo_totale": pr * qt if qt else pr,
                    "quantita": qt,
                }
            # Codici alternativi
            codici_alt = p.get("codici_alternativi", {})
            for codice_tipo, codice_val in codici_alt.items():
                if codice_val:
                    prezzi_per_codice[codice_val.strip()] = {
                        "prezzo_unitario": pr,
                        "prezzo_totale": pr * qt if qt else pr,
                        "quantita": qt,
                        "descrizione": nome,
                    }
            # Anche codice_articolo principale
            codice_art = (p.get("codice_articolo", "") or "").strip()
            if codice_art:
                prezzi_per_codice[codice_art] = {
                    "prezzo_unitario": pr,
                    "prezzo_totale": pr * qt if qt else pr,
                    "quantita": qt,
                    "descrizione": nome,
                }

        for prod in prodotti_fattura:
            prezzo = float(prod.get("prezzo", 0) or 0)
            if prezzo > 0:
                continue  # È una riga normale, non uno sconto

            nome_prodotto = (prod.get("descrizione", "") or prod.get("nome", "")).strip()
            if not nome_prodotto:
                continue

            # Controlla se già importato
            esistente = await db.sconti_merce.find_one(
                {
                    "fornitore": fornitore,
                    "prodotto": nome_prodotto,
                    "fattura_riferimento": numero_fattura,
                }
            )
            if esistente:
                saltati += 1
                continue

            # Calcola mese/anno dalla data fattura
            mese, anno = 1, datetime.now(timezone.utc).year
            giorno = 1
            try:
                if "/" in data_fattura:
                    parti = data_fattura.split("/")
                    if len(parti) == 3:
                        giorno = int(parti[0])
                        mese = int(parti[1])
                        anno = int(parti[2][-4:])
                elif "-" in data_fattura:
                    parti = data_fattura.split("-")
                    anno = int(parti[0])
                    mese = int(parti[1])
                    giorno = int(parti[2][:2]) if len(parti) > 2 else 1
            except Exception:
                _LOG_INIT.debug("[sconti_merce] errore non bloccante ignorato")

            # Quantità e unità di misura
            quantita_raw = prod.get("quantita", 0)
            try:
                quantita = float(str(quantita_raw).strip()) if quantita_raw else 0.0
            except Exception:
                quantita = 0.0

            unita_misura = (prod.get("unita_misura", "") or "").strip()

            cartoni = 0.0
            pezzi_totali = 0.0
            pezzi_per_cartone = 0.0
            if unita_misura.upper() in ("CF", "PZ", "NR", "N", "PCS", "CONF"):
                pezzi_totali = quantita
            else:
                cartoni = quantita
                # Calcola pezzi/cartone dal nome (es. "90G 4.95KG" → 55 pz)
                ppc = calcola_pezzi_da_nome(nome_prodotto)
                if ppc:
                    pezzi_per_cartone = float(ppc)
                    pezzi_totali = float(ppc) * cartoni

            # Prova a valorizzare:
            # 1. Match per codice EN/COD_FORNITORE (più preciso)
            # 2. Match per nome esatto
            # 3. Match per prime 2 parole (fuzzy)
            valore_unitario = 0.0
            valore_totale = 0.0
            trovato_in_fattura = False
            match_method = ""

            # 1. Match per codice
            codici_sc = prod.get("codici_alternativi", {})
            codice_art_sc = (prod.get("codice_articolo", "") or "").strip()
            tutti_codici_sc = list(codici_sc.values()) + ([codice_art_sc] if codice_art_sc else [])
            for codice in tutti_codici_sc:
                if codice and codice in prezzi_per_codice:
                    ref = prezzi_per_codice[codice]
                    valore_unitario = ref["prezzo_unitario"]
                    valore_totale = (
                        round(valore_unitario * quantita, 4) if quantita > 0 else valore_unitario
                    )
                    trovato_in_fattura = True
                    match_method = f"codice {codice}"
                    valorizzati += 1
                    break

            # 2. Match per nome esatto
            if not trovato_in_fattura:
                nome_upper = nome_prodotto.upper()
                if nome_upper in prezzi_per_nome:
                    ref = prezzi_per_nome[nome_upper]
                    valore_unitario = ref["prezzo_unitario"]
                    valore_totale = (
                        round(valore_unitario * quantita, 4) if quantita > 0 else valore_unitario
                    )
                    trovato_in_fattura = True
                    match_method = "nome esatto"
                    valorizzati += 1

            # 3. Match per prime 2 parole
            if not trovato_in_fattura:
                nome_upper = nome_prodotto.upper()
                for nome_fat, ref in prezzi_per_nome.items():
                    if nome_sc_simile(nome_upper, nome_fat):
                        valore_unitario = ref["prezzo_unitario"]
                        valore_totale = (
                            round(valore_unitario * quantita, 4)
                            if quantita > 0
                            else valore_unitario
                        )
                        trovato_in_fattura = True
                        match_method = f"nome parziale (vs {nome_fat[:30]})"
                        valorizzati += 1
                        break

            note_parts = [f"Sconto merce da fattura {numero_fattura}"]
            if trovato_in_fattura:
                note_parts.append(
                    f"Valorizzato via {match_method}: €{valore_unitario:.2f}/u × {quantita}"
                )
            else:
                note_parts.append("Valore non trovato — inserire manualmente")
            if unita_misura:
                note_parts.append(f"U.M.: {unita_misura}")

            doc = {
                "id": str(uuid.uuid4()),
                "data": data_fattura,
                "giorno": giorno,
                "fornitore": fornitore,
                "prodotto": nome_prodotto,
                "cartoni": cartoni,
                "pezzi_per_cartone": pezzi_per_cartone,
                "pezzi_totali": pezzi_totali,
                "valore_unitario": valore_unitario,
                "valore_totale": valore_totale,
                "fattura_riferimento": numero_fattura,
                "unita_misura": unita_misura,
                "note": " | ".join(note_parts),
                "mese": mese,
                "anno": anno,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.sconti_merce.insert_one(doc)
            importati += 1

    return {
        "success": True,
        "importati": importati,
        "valorizzati_automaticamente": valorizzati,
        "saltati_gia_presenti": saltati,
        "fatture_analizzate": len(fatture),
    }


def calcola_pezzi_da_nome(nome: str):
    """Estrae pezzi/cartone dal nome prodotto tipo '90G 4.95KG' → 55 pz"""
    import re

    m = re.search(r"(\d+(?:[,\.]\d+)?)\s*G\s+(\d+(?:[,\.]\d+)?)\s*KG", nome.upper())
    if m:
        try:
            peso_pz = float(m.group(1).replace(",", "."))
            peso_cart_kg = float(m.group(2).replace(",", "."))
            if peso_pz > 0:
                return round((peso_cart_kg * 1000) / peso_pz)
        except Exception:
            _LOG_INIT.debug("[sconti_merce] errore non bloccante ignorato")
    return None


def nome_sc_simile(nome_sc: str, nome_fat: str) -> bool:
    """Verifica similarità tra nome prodotto sconto e fattura (match prime 2 parole)"""
    w_sc = nome_sc.split()
    w_fat = nome_fat.split()
    if len(w_sc) < 2 or len(w_fat) < 2:
        return False
    return w_sc[0] == w_fat[0] and w_sc[1] == w_fat[1]


@router.post("/valorizza-da-fatture")
async def valorizza_sconti_esistenti(_admin=Depends(require_admin)):
    """
    Per tutti gli sconti con valore_totale=0, cerca il prezzo di listino in:
    1. La fattura di riferimento (stessa fattura)
    2. Tutte le fatture dello stesso fornitore (stesso prodotto pagato in altro ordine)
    Usa match per: codice articolo > nome esatto > prime 3 parole comuni
    """
    sconti_da_valorizzare = await db.sconti_merce.find({"valore_totale": 0}, {"_id": 0}).to_list(
        5000
    )

    aggiornati = 0
    non_trovati = 0

    for sconto in sconti_da_valorizzare:
        num_fat = sconto.get("fattura_riferimento", "")
        fornitore = sconto.get("fornitore", "")
        nome_prodotto = sconto.get("prodotto", "").strip().upper()
        quantita = float(sconto.get("cartoni", 0) or sconto.get("pezzi_totali", 0) or 0)
        if not nome_prodotto:
            non_trovati += 1
            continue

        # Costruisci mappa prezzi: prima da fattura specifica, poi da tutte le fatture del fornitore
        # Pipeline MongoDB: raggruppa per prodotto→ prende il prezzo medio dell'ultima fattura
        pipeline = [
            {"$match": {"fornitore": {"$regex": re.escape(fornitore[:15]), "$options": "i"}}},
            {"$unwind": "$prodotti"},
            {
                "$addFields": {
                    "prezzo_num": {
                        "$toDouble": {
                            "$convert": {
                                "input": {
                                    "$trim": {"input": {"$ifNull": ["$prodotti.prezzo", "0"]}}
                                },
                                "to": "double",
                                "onError": 0.0,
                                "onNull": 0.0,
                            }
                        }
                    }
                }
            },
            {"$match": {"prezzo_num": {"$gt": 0}}},
            {
                "$group": {
                    "_id": {"$toUpper": {"$trim": {"input": "$prodotti.descrizione"}}},
                    "prezzo_unitario": {"$avg": "$prezzo_num"},
                    "fattura": {"$last": "$numero_fattura"},
                }
            },
            {"$project": {"_id": 1, "prezzo_unitario": 1, "fattura": 1}},
        ]
        prezzi_docs = await db.fatture.aggregate(pipeline).to_list(2000)
        prezzi_map = {d["_id"]: d["prezzo_unitario"] for d in prezzi_docs if d.get("_id")}

        # Match 1: nome esatto
        valore_trovato = 0.0
        valore_unitario = 0.0
        match_desc = ""

        if nome_prodotto in prezzi_map:
            valore_unitario = prezzi_map[nome_prodotto]
            match_desc = "nome esatto"
        else:
            # Match 2: prime 3 parole
            parole_sc = nome_prodotto.split()[:3]
            for nome_fat, pr_fat in prezzi_map.items():
                parole_fat = nome_fat.split()[:3]
                if parole_sc == parole_fat:
                    valore_unitario = pr_fat
                    match_desc = f"prime 3 parole (vs {nome_fat[:35]})"
                    break

            if not valore_unitario:
                # Match 3: prime 2 parole + almeno 1 parola comune successiva
                for nome_fat, pr_fat in prezzi_map.items():
                    if nome_sc_simile(nome_prodotto, nome_fat):
                        valore_unitario = pr_fat
                        match_desc = f"parole comuni (vs {nome_fat[:35]})"
                        break

        if valore_unitario > 0:
            valore_trovato = (
                round(valore_unitario * quantita, 4) if quantita > 0 else valore_unitario
            )
            nota_aggiunta = f"Valorizzato via {match_desc}: €{valore_unitario:.2f}/u"
            if quantita:
                nota_aggiunta += f" × {quantita} = €{valore_trovato:.2f}"
            await db.sconti_merce.update_one(
                {"id": sconto["id"]},
                {
                    "$set": {
                        "valore_unitario": valore_unitario,
                        "valore_totale": valore_trovato,
                        "note": (sconto.get("note", "") + " | " + nota_aggiunta).strip(" |"),
                    }
                },
            )
            aggiornati += 1
        else:
            non_trovati += 1

    return {
        "success": True,
        "aggiornati": aggiornati,
        "non_trovati_in_fattura": non_trovati,
        "totale_analizzati": len(sconti_da_valorizzare),
    }


@router.get("/prodotti-fornitore")
async def prodotti_per_fornitore(fornitore: Optional[str] = Query(None)):
    """
    Restituisce la lista di prodotti (descrizioni) trovati nelle fatture
    per un determinato fornitore attivo. Usato per il datalist nel form.
    """
    if not fornitore or not fornitore.strip():
        return []

    forn_input = fornitore.strip().lower()

    # Trova il nome esatto del fornitore nel DB fatture (matching parziale case-insensitive)
    pipeline = [
        {"$match": {"fornitore": {"$regex": forn_input, "$options": "i"}}},
        {"$unwind": "$prodotti"},
        {"$group": {"_id": "$prodotti.descrizione"}},
        {"$match": {"_id": {"$nin": [None, ""]}}},
        {"$sort": {"_id": 1}},
        {"$limit": 500},
    ]
    docs = await db.fatture.aggregate(pipeline).to_list(500)
    prodotti = sorted({d["_id"].strip() for d in docs if d.get("_id") and d["_id"].strip()})
    return prodotti


@router.get("/riepilogo/mensile")
async def riepilogo_mensile(anno: int = Query(...)):
    """Riepilogo sconti merce per ogni mese dell'anno"""
    MESI = [
        "",
        "Gennaio",
        "Febbraio",
        "Marzo",
        "Aprile",
        "Maggio",
        "Giugno",
        "Luglio",
        "Agosto",
        "Settembre",
        "Ottobre",
        "Novembre",
        "Dicembre",
    ]

    pipeline = [
        {"$match": {"anno": anno}},
        {
            "$group": {
                "_id": "$mese",
                "valore_totale": {"$sum": "$valore_totale"},
                "num_righe": {"$sum": 1},
                "cartoni_totali": {"$sum": "$cartoni"},
                "pezzi_totali": {"$sum": "$pezzi_totali"},
                "fornitori": {"$addToSet": "$fornitore"},
            }
        },
        {"$sort": {"_id": 1}},
    ]
    result = await db.sconti_merce.aggregate(pipeline).to_list(12)

    mesi_data = {}
    for r in result:
        mese_num = r["_id"]
        mesi_data[mese_num] = {
            "mese": mese_num,
            "nome_mese": MESI[mese_num] if mese_num <= 12 else str(mese_num),
            "valore_totale": round(r["valore_totale"], 2),
            "num_righe": r["num_righe"],
            "cartoni_totali": round(r["cartoni_totali"], 2),
            "pezzi_totali": round(r["pezzi_totali"], 2),
            "num_fornitori": len(r["fornitori"]),
        }

    # Completa con mesi vuoti
    riepilogo = []
    for m in range(1, 13):
        if m in mesi_data:
            riepilogo.append(mesi_data[m])
        else:
            riepilogo.append(
                {
                    "mese": m,
                    "nome_mese": MESI[m],
                    "valore_totale": 0,
                    "num_righe": 0,
                    "cartoni_totali": 0,
                    "pezzi_totali": 0,
                    "num_fornitori": 0,
                }
            )

    totale_anno = sum(r["valore_totale"] for r in riepilogo)
    return {"anno": anno, "mesi": riepilogo, "totale_anno": round(totale_anno, 2)}


@router.get("/riepilogo/fornitori")
async def riepilogo_per_fornitore(
    anno: Optional[int] = Query(None), mese: Optional[int] = Query(None)
):
    """Riepilogo sconti per fornitore"""
    match = {}
    if anno:
        match["anno"] = anno
    if mese:
        match["mese"] = mese

    pipeline = [
        {"$match": match} if match else {"$match": {}},
        {
            "$group": {
                "_id": "$fornitore",
                "valore_totale": {"$sum": "$valore_totale"},
                "cartoni_totali": {"$sum": "$cartoni"},
                "pezzi_totali": {"$sum": "$pezzi_totali"},
                "num_righe": {"$sum": 1},
                "prodotti": {"$addToSet": "$prodotto"},
            }
        },
        {"$sort": {"valore_totale": -1}},
    ]
    result = await db.sconti_merce.aggregate(pipeline).to_list(100)

    for r in result:
        r["fornitore"] = r.pop("_id", "")
        r["valore_totale"] = round(r["valore_totale"], 2)
        r["cartoni_totali"] = round(r["cartoni_totali"], 2)
        r["pezzi_totali"] = round(r["pezzi_totali"], 2)
        r["num_prodotti"] = len(r.pop("prodotti", []))

    return result
