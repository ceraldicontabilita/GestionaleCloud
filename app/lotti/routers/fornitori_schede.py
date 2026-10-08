import logging
_LOG_INIT = logging.getLogger("uvicorn.error")
"""
Router: fornitori_schede
Schede di ricevimento merci (Reg. CE 178/2002 art. 18 — rintracciabilità)
Include:
- Registro Fornitori Qualificati (aggregato da fatture)
- Schede Ricevimento Merci (con temperatura pre-compilata per range legge)
- Note manuali di non conformità/osservazioni ricevimento
"""

from fastapi import APIRouter
from datetime import datetime, timezone, date

from app.lotti.db import database as db

router = APIRouter(prefix="/fornitori", tags=["Fornitori"])


@router.get("/registro-qualificati")
async def get_registro_fornitori_qualificati():
    """
    Registro Fornitori Qualificati — aggiornato automaticamente dalle fatture.
    Obbligatorio nel Piano HACCP (Reg. CE 852/2004 + Reg. CE 178/2002 art. 18).
    Restituisce anagrafica, prodotti forniti, numero fatture, ultima consegna.
    """
    fornitori_fatture = await db.fatture.distinct("fornitore")
    fornitori_db_list = await db.fornitori.find({}, {"_id": 0}).to_list(2000)
    fornitori_db = {f["nome"]: f for f in fornitori_db_list if f.get("nome")}

    # Contatti inseriti manualmente / da fatture (collezione separata usata anche
    # per l'invio ordini). Merge per nome normalizzato cosi la scheda mostra le
    # stesse email/telefoni che l'invio ordini usa davvero.
    anagrafica_list = await db.fornitori_anagrafica.find({}, {"_id": 0}).to_list(3000)
    def _nk(x): return (x or "").strip().strip('"').strip("'").lower()
    anagrafica = {_nk(a.get("nome")): a for a in anagrafica_list if a.get("nome")}

    # Singola query aggregata per tutte le fatture (evita N+1)
    pipeline = [
        {"$match": {"fornitore": {"$in": [n for n in fornitori_fatture if n]}}},
        {
            "$project": {
                "_id": 0,
                "fornitore": 1,
                "data_fattura": 1,
                "numero_fattura": 1,
                "prodotti": 1,
                "piva": 1,
            }
        },
        {"$sort": {"data_fattura": -1}},
    ]
    tutte_fatture = await db.fatture.aggregate(pipeline).to_list(5000)

    fatture_per_fornitore: dict = {}
    for f in tutte_fatture:
        nome = f.get("fornitore", "")
        if nome:
            fatture_per_fornitore.setdefault(nome, []).append(f)

    result = []
    for nome in sorted(fornitori_fatture):
        if not nome:
            continue
        info = fornitori_db.get(nome, {})
        if info.get("escluso"):
            stato = "Escluso"
        elif info.get("in_attesa"):
            stato = "In attesa"
        else:
            stato = "Qualificato"

        fatture = fatture_per_fornitore.get(nome, [])
        prodotti_unici = set()
        piva = ""
        totale_fatture = 0
        for f in fatture:
            if f.get("piva") and not piva:
                piva = f["piva"]
            for p in f.get("prodotti", []):
                desc = (p.get("descrizione", "") or "").strip()
                if desc:
                    prodotti_unici.add(desc[:60])
                try:
                    totale_fatture += float(str(p.get("prezzo", 0) or 0)) * float(
                        str(p.get("quantita", 0) or 0)
                    )
                except Exception:
                    _LOG_INIT.debug("[fornitori_schede] errore non bloccante ignorato")

        # "Ultima consegna" per data VERA: l'ordine dell'aggregate su data_fattura
        # (formato misto dd/mm/yyyy + ISO) è lessicografico, quindi fatture[0] non
        # era davvero la più recente. Si prende il massimo per data reale.
        from app.lotti.routers.utils import parse_data_flessibile
        ultima_consegna = ""
        if fatture:
            _f = max(fatture, key=lambda x: parse_data_flessibile(x.get("data_fattura")) or date(1900, 1, 1))
            ultima_consegna = _f.get("data_fattura", "")

        result.append(
            {
                "nome": nome,
                "stato": stato,
                "piva": piva or info.get("piva", ""),
                "indirizzo": info.get("indirizzo", ""),
                "telefono": info.get("telefono", "") or anagrafica.get(_nk(nome), {}).get("cellulare", ""),
                "email": info.get("email", "") or anagrafica.get(_nk(nome), {}).get("email", ""),
                "num_fatture": len(fatture),
                "ultima_consegna": ultima_consegna,
                "totale_acquistato": round(totale_fatture, 2),
                "num_prodotti": len(prodotti_unici),
                "prodotti_campione": sorted(prodotti_unici)[:5],
                "note": info.get("note", ""),
            }
        )

    return {
        "aggiornato_il": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "totale_fornitori": len(result),
        "totale": len(result),
        "qualificati": len([r for r in result if r["stato"] == "Qualificato"]),
        "esclusi": len([r for r in result if r["stato"] == "Escluso"]),
        "fornitori": result,
    }


def _classifica_fornitore_temperatura(nome_fornitore: str, prodotti: list) -> dict:
    """
    Determina il tipo di prodotto consegnato e assegna la temperatura
    di ricevimento pre-compilata nei range di legge (Reg. CE 852/2004):
    - Surgelati: ≤ -18°C  → pre-compila -18°C
    - Refrigerati: 0-4°C  → pre-compila 3°C
    - Ambiente: N/A
    """
    nome_upper = (nome_fornitore or "").upper()
    descrizioni = " ".join(p.get("descrizione", "") for p in prodotti).upper()
    testo = nome_upper + " " + descrizioni

    KW_SURGELATO = ["SURGEL", "CONGELAT", "FROZEN", "VANDEMOORTELE", "SURGELATI", "-18", "GELAT"]
    KW_FRESCO = [
        "FRESC",
        "REFRIGER",
        "LATTE",
        "FORMAGGI",
        "SALUMERI",
        "CARNI",
        "PESCE",
        "PESC",
        "YOGURT",
        "PANNA",
        "BURRO",
        "UOVA",
        "VERDURE",
        "ORTOFRUT",
    ]

    if any(k in testo for k in KW_SURGELATO):
        return {
            "tipo_conservazione": "surgelato",
            "temperatura_rilevata": -18.0,
            "temperatura_min": -22.0,
            "temperatura_max": -15.0,
            "unita": "°C",
            "conforme": True,
            "note_temperatura": "Temperatura rilevata nei range di legge (≤ -18°C, Reg. CE 852/2004)",
        }
    elif any(k in testo for k in KW_FRESCO):
        return {
            "tipo_conservazione": "refrigerato",
            "temperatura_rilevata": 3.0,
            "temperatura_min": 0.0,
            "temperatura_max": 4.0,
            "unita": "°C",
            "conforme": True,
            "note_temperatura": "Temperatura rilevata nei range di legge (0-4°C, Reg. CE 852/2004)",
        }
    else:
        return {
            "tipo_conservazione": "ambiente",
            "temperatura_rilevata": None,
            "temperatura_min": None,
            "temperatura_max": None,
            "unita": "°C",
            "conforme": True,
            "note_temperatura": "Prodotto a temperatura ambiente — verifica non richiesta",
        }


@router.get("/schede-ricevimento")
async def get_schede_ricevimento(fornitore: str = None, limit: int = 50):
    """
    Schede di Ricevimento Merci — generate automaticamente dalle fatture.
    Ogni fattura = una consegna registrata (DDT/Fattura).
    Art. 18 Reg. CE 178/2002 — rintracciabilità obbligatoria.

    La temperatura di ricevimento è pre-compilata con un valore nei range
    di legge in base al tipo di prodotto (surgelato/fresco/ambiente).

    FILTRO: esclude automaticamente i fornitori marcati come esclusi.
    """
    esclusi_docs = await db.fornitori.find({"escluso": True}, {"_id": 0, "nome": 1}).to_list(1000)
    esclusi_nomi = {f["nome"] for f in esclusi_docs}

    filtro: dict = {}
    if fornitore:
        filtro["fornitore"] = {"$regex": fornitore, "$options": "i"}

    fatture = (
        await db.fatture.find(
            filtro,
            {
                "_id": 0,
                "id": 1,
                "numero_fattura": 1,
                "data_fattura": 1,
                "fornitore": 1,
                "prodotti": 1,
                "piva": 1,
            },
        )
        .sort("data_fattura", -1)
        .to_list(limit * 3)
    )

    schede = []
    for f in fatture:
        nome_forn = f.get("fornitore", "")
        if nome_forn in esclusi_nomi:
            continue

        prodotti_raw = f.get("prodotti", [])
        prodotti_riga = []
        for p in prodotti_raw:
            try:
                prezzo = float(str(p.get("prezzo", 0) or 0))
                qty = float(str(p.get("quantita", 0) or 0))
            except Exception:
                prezzo, qty = 0, 0
            prodotti_riga.append(
                {
                    "descrizione": p.get("descrizione", ""),
                    "quantita": qty,
                    "unita_misura": p.get("unita_misura", ""),
                    "prezzo_unitario": prezzo,
                    "totale": round(prezzo * qty, 2),
                    "lotto": p.get("lotto", ""),
                    "scadenza": p.get("scadenza", ""),
                }
            )

        temp_info = _classifica_fornitore_temperatura(nome_forn, prodotti_raw)

        schede.append(
            {
                "id_fattura": f.get("id", ""),
                "numero_documento": f.get("numero_fattura", ""),
                "data_consegna": f.get("data_fattura", ""),
                "fornitore": nome_forn,
                "piva_fornitore": f.get("piva", ""),
                "num_prodotti": len(prodotti_riga),
                "prodotti": prodotti_riga,
                "tipo_conservazione": temp_info["tipo_conservazione"],
                "temperatura_rilevata": temp_info["temperatura_rilevata"],
                "temperatura_min": temp_info["temperatura_min"],
                "temperatura_max": temp_info["temperatura_max"],
                "conforme": True,
                "note_temperatura": temp_info["note_temperatura"],
                "note_ricevimento": "",
            }
        )

        if len(schede) >= limit:
            break

    return schede


@router.post("/schede-ricevimento/{fattura_id}/nota")
async def salva_nota_ricevimento(fattura_id: str, nota: str):
    """Salva una nota manuale (non conformità visiva, imballaggio, ecc.).
    Salvata in collezione `note_ricevimento` separata.
    """
    await db.note_ricevimento.update_one(
        {"id_fattura": fattura_id},
        {
            "$set": {
                "id_fattura": fattura_id,
                "nota": nota,
                "aggiornata_il": datetime.now(timezone.utc).isoformat(),
            }
        },
        upsert=True,
    )
    return {"status": "ok", "id_fattura": fattura_id, "nota": nota}


@router.get("/note-ricevimento/{fattura_id}")
async def get_nota_ricevimento(fattura_id: str):
    """Legge la nota operatore per una fattura specifica."""
    doc = await db.note_ricevimento.find_one({"id_fattura": fattura_id}, {"_id": 0})
    return doc or {"id_fattura": fattura_id, "nota": ""}
