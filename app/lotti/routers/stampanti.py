"""Configurazione stampanti di rete.

Anagrafica delle stampanti usate in negozio (banco, magazzino, etichette Lotti
per reparto). Per ognuna si configura: nome, reparto associato, indirizzo di rete
(IP), porta e cosa stampa. I valori (IP/porta) li inserisce l'operatore: qui non si
inventa nulla, la lista parte da 4 stampanti predefinite con IP vuoto.
"""
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.lotti.db import database as db

router = APIRouter(prefix="/stampanti", tags=["Stampanti"])
COLL = db.stampanti_config
CODA = db.coda_stampa


class Stampante(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    nome: str
    reparto: str = ""          # banco | magazzino | rosticceria | pasticceria
    indirizzo_rete: str = ""   # es. 192.168.1.50
    porta: int = 9100          # porta standard stampanti di rete (RAW/JetDirect)
    cosa_stampa: str = ""      # descrizione di cosa stampa
    categorie: list[str] = []  # etichette|ricette|manuale|scontrini|report -> routing automatico
    stampante_windows: str = ""  # nome ESATTO della stampante in Windows (usato dall'agente locale)
    attiva: bool = True


# Stampanti predefinite (IP vuoto: li compila l'operatore nella configurazione).
DEFAULT = [
    {"nome": "Stampante banco", "reparto": "banco", "cosa_stampa": "scontrini / preconto"},
    {"nome": "Stampante magazzino", "reparto": "magazzino", "cosa_stampa": "etichette magazzino"},
    {"nome": "Etichette Lotti — Rosticceria", "reparto": "rosticceria", "cosa_stampa": "etichette lotti reparto rosticceria"},
    {"nome": "Etichette Lotti — Pasticceria", "reparto": "pasticceria", "cosa_stampa": "etichette lotti reparto pasticceria"},
]


@router.get("")
async def lista_stampanti():
    """Lista le stampanti configurate. Se vuota, semina le 4 predefinite (IP vuoto)."""
    docs = await COLL.find({}, {"_id": 0}).to_list(100)
    if not docs:
        clean = [Stampante(**d).dict() for d in DEFAULT]
        await COLL.insert_many([dict(c) for c in clean])  # le copie ricevono _id, non clean
        docs = clean
    return docs


@router.post("")
async def crea_stampante(s: Stampante):
    d = s.dict()
    await COLL.insert_one(dict(d))
    return d


@router.put("/{stampante_id}")
async def aggiorna_stampante(stampante_id: str, dati: dict):
    dati.pop("id", None)
    dati.pop("_id", None)
    if "porta" in dati:
        try:
            dati["porta"] = int(dati["porta"])
        except (TypeError, ValueError):
            dati["porta"] = 9100
    r = await COLL.update_one({"id": stampante_id}, {"$set": dati})
    if r.matched_count == 0:
        raise HTTPException(404, "Stampante non trovata")
    return await COLL.find_one({"id": stampante_id}, {"_id": 0})


@router.delete("/{stampante_id}")
async def elimina_stampante(stampante_id: str):
    r = await COLL.delete_one({"id": stampante_id})
    if r.deleted_count == 0:
        raise HTTPException(404, "Stampante non trovata")
    return {"eliminata": True}


# ── Coda di stampa per l'agente locale ─────────────────────────────────────────
# Il browser non può scegliere la stampante né raggiungere la LAN dal cloud:
# l'app accoda un lavoro (categoria + URL del documento), un piccolo agente sul PC
# del negozio lo preleva e lo stampa sulla stampante mappata a quella categoria.
async def _stampante_per_categoria(categoria: str, reparto: str = "") -> dict:
    stampanti = await COLL.find(
        {"attiva": {"$ne": False}, "categorie": categoria}, {"_id": 0}
    ).to_list(50)
    if reparto:
        for s in stampanti:
            if s.get("reparto") == reparto:
                return s
    return stampanti[0] if stampanti else None


class JobStampa(BaseModel):
    categoria: str            # etichette|ricette|manuale|scontrini|report
    url: str                  # URL completo del documento (con ?token=)
    formato: str = "pdf"      # pdf | html
    titolo: str = ""
    reparto: str = ""


@router.post("/coda")
async def accoda_stampa(job: JobStampa, request: Request):
    """L'app accoda un documento da stampare; risolve subito la stampante mappata.
    Se la stampante è di rete (IP configurato) e il documento è un'etichetta lotto,
    l'instradamento passa automaticamente a ESC/POS diretto (socket :9100)."""
    st = await _stampante_per_categoria(job.categoria, job.reparto)
    d = job.dict()
    if d["url"].startswith("/"):
        # Dentro il gestionale il frontend usa URL relativi (/lotti/api/...):
        # l'agente di stampa sul PC del negozio ha bisogno dell'URL completo.
        d["url"] = str(request.base_url).rstrip("/").removesuffix(request.scope.get("root_path", "") or "") + d["url"]
    if st and st.get("indirizzo_rete") and "/stampa/lotto/" in d["url"] and "/escpos" not in d["url"]:
        base, _, qs = d["url"].partition("?")
        d["url"] = base.rstrip("/") + "/escpos" + (f"?{qs}" if qs else "")
        d["formato"] = "escpos"
    doc = {
        "id": str(uuid.uuid4()),
        **d,
        "stato": "in_attesa",
        "stampante": st,
        "stampante_windows": (st or {}).get("stampante_windows", ""),
        "creato": datetime.now(timezone.utc).isoformat(),
    }
    await CODA.insert_one(dict(doc))
    doc.pop("_id", None)
    return {"ok": True, "job_id": doc["id"], "stampante": st, "instradato": bool(st), "formato": d["formato"]}


@router.get("/coda/pendenti")
async def coda_pendenti(reparto: str = "", limit: int = 50):
    """L'agente locale preleva i lavori da stampare (FIFO)."""
    q = {"stato": "in_attesa"}
    if reparto:
        q["$or"] = [{"reparto": reparto}, {"reparto": ""}]
    jobs = await CODA.find(q, {"_id": 0}).sort("creato", 1).to_list(limit)
    return {"jobs": jobs}


@router.post("/coda/{job_id}/esito")
async def coda_esito(job_id: str, payload: dict):
    """L'agente segnala l'esito (stampato / errore)."""
    ok = bool(payload.get("ok"))
    await CODA.update_one(
        {"id": job_id},
        {"$set": {
            "stato": "stampato" if ok else "errore",
            "errore": payload.get("errore", ""),
            "chiuso": datetime.now(timezone.utc).isoformat(),
        }},
    )
    return {"ok": True}


@router.get("/coda")
async def coda_storico(limit: int = 50):
    """Ultimi lavori di stampa con esito (per controllo)."""
    return await CODA.find({}, {"_id": 0}).sort("creato", -1).to_list(limit)
