"""
Router: fornitori_qualifica
Sistema qualifica HACCP dei fornitori — validità 12 mesi.
Include:
- Lista in attesa di verifica
- Approvazione singola / batch / auto
- Rinnovo annuale + gestione scadenze
"""

from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone, timedelta

from app.lotti.db import database as db

router = APIRouter(prefix="/fornitori", tags=["Fornitori"])


@router.get("/qualifica/in-attesa")
async def get_qualifica_in_attesa():
    """Lista fornitori_qualifica con stato in_attesa_verifica — solo non esclusi."""
    esclusi_docs = await db.fornitori.find({"escluso": True}, {"_id": 0, "nome": 1}).to_list(1000)
    esclusi_nomi = {f["nome"] for f in esclusi_docs}

    docs = (
        await db.fornitori_qualifica.find(
            {"stato": "in_attesa_verifica"},
            {
                "_id": 0,
                "nome_fornitore": 1,
                "piva": 1,
                "categoria": 1,
                "num_fatture": 1,
                "ultima_consegna": 1,
                "totale_acquistato": 1,
                "prodotti_campione": 1,
                "stato": 1,
            },
        )
        .sort("nome_fornitore", 1)
        .to_list(200)
    )

    return [d for d in docs if d.get("nome_fornitore", "") not in esclusi_nomi]


@router.patch("/qualifica/{piva}/approva")
async def approva_qualifica_fornitore(piva: str, includi: bool = True):
    """Approva o esclude un fornitore dalla qualifica HACCP."""
    nuovo_stato = "qualificato" if includi else "escluso"
    await db.fornitori_qualifica.update_one(
        {"piva": piva},
        {"$set": {"stato": nuovo_stato, "approvato_il": datetime.now(timezone.utc).isoformat()}},
    )
    doc_q = await db.fornitori_qualifica.find_one({"piva": piva})
    if doc_q:
        nome = doc_q.get("nome_fornitore", "")
        if nome:
            await db.fornitori.update_one(
                {"nome": nome}, {"$set": {"in_attesa": False, "escluso": not includi}}, upsert=True
            )
    return {"ok": True, "piva": piva, "stato": nuovo_stato}


@router.post("/qualifica/approva-batch")
async def approva_batch_qualifica(payload: dict):
    """Approva in batch. Body: {"pive": ["IT123", "IT456"], "includi": true}"""
    pive = payload.get("pive", [])
    includi = payload.get("includi", True)
    if not pive:
        return {"aggiornati": 0}
    nuovo_stato = "qualificato" if includi else "escluso"
    result = await db.fornitori_qualifica.update_many(
        {"piva": {"$in": pive}},
        {"$set": {"stato": nuovo_stato, "approvato_il": datetime.now(timezone.utc).isoformat()}},
    )
    docs = await db.fornitori_qualifica.find(
        {"piva": {"$in": pive}}, {"_id": 0, "nome_fornitore": 1}
    ).to_list(500)
    for doc in docs:
        nome = doc.get("nome_fornitore", "")
        if nome:
            await db.fornitori.update_one(
                {"nome": nome}, {"$set": {"in_attesa": False, "escluso": not includi}}, upsert=True
            )
    return {"aggiornati": result.modified_count, "stato": nuovo_stato}


@router.post("/qualifica/auto-qualifica-tutti")
async def auto_qualifica_tutti_attivi():
    """Qualifica automatica di tutti i fornitori in 'in_attesa_verifica'.
    Ogni fornitore con fatture inviate è considerato qualificato.
    Solo esclusi manualmente rimangono esclusi.
    """
    docs_in_attesa = await db.fornitori_qualifica.find(
        {"stato": "in_attesa_verifica"}, {"_id": 0, "piva": 1, "nome_fornitore": 1}
    ).to_list(500)

    aggiornati = 0
    for doc in docs_in_attesa:
        piva = doc.get("piva", "")
        nome = doc.get("nome_fornitore", "")
        fornitore = await db.fornitori.find_one({"nome": nome}, {"escluso": 1})
        if fornitore and fornitore.get("escluso"):
            continue
        await db.fornitori_qualifica.update_one(
            {"piva": piva},
            {
                "$set": {
                    "stato": "qualificato",
                    "approvato_il": datetime.now(timezone.utc).isoformat(),
                    "auto_qualificato": True,
                }
            },
        )
        await db.fornitori.update_one(
            {"nome": nome}, {"$set": {"in_attesa": False, "escluso": False}}, upsert=True
        )
        aggiornati += 1

    return {
        "aggiornati": aggiornati,
        "messaggio": f"{aggiornati} fornitori qualificati automaticamente",
    }


# ── Rinnovo qualifica annuale ──────────────────────────────────────────────


@router.get("/qualifica/scadenze-rinnovo")
async def get_scadenze_rinnovo_qualifica(giorni_soglia: int = 30):
    """Lista fornitori con qualifica in scadenza o già scaduta (12 mesi)."""
    ora = datetime.now(timezone.utc)

    tutti = await db.fornitori_qualifica.find(
        {"stato": "qualificato", "approvato_il": {"$exists": True}}, {"_id": 0}
    ).to_list(500)

    in_scadenza = []
    scadute = []

    for f in tutti:
        approvato_il_str = f.get("approvato_il", "")
        if not approvato_il_str:
            continue
        try:
            approvato_il = datetime.fromisoformat(approvato_il_str.replace("Z", "+00:00"))
        except Exception:
            continue

        scadenza = approvato_il + timedelta(days=365)
        giorni_rimasti = (scadenza - ora).days

        entry = {
            **{k: v for k, v in f.items() if k != "_id"},
            "approvato_il": approvato_il_str,
            "scadenza_qualifica": scadenza.strftime("%Y-%m-%d"),
            "giorni_alla_scadenza": giorni_rimasti,
        }

        if giorni_rimasti < 0:
            scadute.append(entry)
        elif giorni_rimasti <= giorni_soglia:
            in_scadenza.append(entry)

    return {
        "scadute": sorted(scadute, key=lambda x: x["giorni_alla_scadenza"]),
        "in_scadenza": sorted(in_scadenza, key=lambda x: x["giorni_alla_scadenza"]),
        "totale_problemi": len(scadute) + len(in_scadenza),
    }


@router.post("/qualifica/{piva}/rinnova")
async def rinnova_qualifica_fornitore(piva: str, note: str = ""):
    """Rinnova la qualifica annuale (resetta il timer 12 mesi)."""
    ora = datetime.now(timezone.utc)
    r = await db.fornitori_qualifica.update_one(
        {"piva": piva},
        {
            "$set": {
                "stato": "qualificato",
                "approvato_il": ora.isoformat(),
                "note_rinnovo": note,
                "rinnovato_il": ora.isoformat(),
                "updated_at": ora.isoformat(),
            }
        },
    )
    if r.matched_count == 0:
        raise HTTPException(404, "Fornitore non trovato")
    return {"ok": True, "nuova_scadenza": (ora + timedelta(days=365)).strftime("%Y-%m-%d")}
