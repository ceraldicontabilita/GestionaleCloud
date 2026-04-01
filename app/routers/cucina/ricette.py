"""
Router Cucina — Ricette
Adattato da /tmp/ceraldi_zip/unificazione_v2/backend/ricette.py
prefix: /cucina  (paths interni: /ricette, /ricette/{id}, ecc.)
"""
from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Body
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Any
from datetime import datetime, timezone, timedelta
import os, uuid, re, shutil, mimetypes

from app.database import Database

router = APIRouter(prefix="", tags=["Cucina Ricette"])

# ─── Modelli ──────────────────────────────────────────────────────────────────
class Ricetta(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    nome: str
    ingredienti: List[Any] = []
    ingredienti_dettaglio: List[dict] = []
    componenti: Optional[List[dict]] = []
    porzioni: Optional[float] = 1
    note: str = ""
    approvata: Optional[bool] = None
    costo_totale: Optional[float] = None
    costo_porzione: Optional[float] = None
    completezza: Optional[str] = None
    ricetta_base_id: Optional[str] = None
    ricetta_base_nome: Optional[str] = None
    ingrediente_variante: Optional[dict] = None
    prezzo_vendita: Optional[float] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RicettaCreate(BaseModel):
    nome: str
    ingredienti: List[Any] = []
    ingredienti_dettaglio: List[dict] = []
    componenti: Optional[List[dict]] = []
    porzioni: int = 1
    note: str = ""
    ricetta_base_id: Optional[str] = None
    ricetta_base_nome: Optional[str] = None
    ingrediente_variante: Optional[dict] = None
    prezzo_vendita: Optional[float] = None
    reparto: Optional[str] = None


# ─── Helper ───────────────────────────────────────────────────────────────────
_PASTICCERIA_KW = ["torta","crema","mousse","cheesecake","mille foglie","profitterol","cannolo",
    "sfogliatella","babà","baba","frolla","crostata","macaron","eclair","choux","gelato","semifreddo",
    "tiramisu","tiramisù","panna cotta","pannacotta","crèpe","crepe","waffle","donut","muffin",
    "cupcake","brownie","cookies","biscotto","biscotti","meringhe","meringa","ganache","glassa",
    "cornetto","brioche","pasticceria","dolce","dessert","budino","flan","zeppole","ciambella",
]
_ROSTICCERIA_KW = ["pizza","focaccia","calzone","piadina","panino","sandwich","burger","tramezzino",
    "bruschetta","arancino","arancini","supplì","frittata","quiche","impanata","fritto","lasagna",
    "gnocchi","risotto","polenta","polpetta","cotoletta","arrosto","pollo","carne","pesce",
    "baccalà","alici","polpo","calamari","gamberi","cozze","vongole","torta salata","rustici",
    "panzerotti","vol-au-vent",
]


def _categorizza_reparto(nome: str) -> str:
    n = nome.lower()
    for kw in _PASTICCERIA_KW:
        if kw in n:
            return "pasticceria"
    for kw in _ROSTICCERIA_KW:
        if kw in n:
            return "rosticceria"
    return "altro"


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/ricette/stats")
async def get_ricette_stats():
    db = Database.get_db()
    sette_fa = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    totale = await db["ricette"].count_documents({})
    nuove_settimana = await db["ricette"].count_documents({"created_at": {"$gte": sette_fa}})
    da_approvare = await db["ricette"].count_documents({"approvata": {"$ne": True}})
    return {
        "totale": totale,
        "nuove_settimana": nuove_settimana,
        "da_approvare": da_approvare
    }


@router.get("/ricette/export/pdf", response_class=HTMLResponse)
async def export_pdf():
    db = Database.get_db()
    ricette = await db["ricette"].find({}, {"_id": 0}).sort("nome", 1).to_list(1000)
    idx = "".join(f'<div class="ii">{i+1}. {r.get("nome","")}</div>' for i, r in enumerate(ricette))
    cards = []
    for i, r in enumerate(ricette, 1):
        det = r.get("ingredienti_dettaglio", [])
        simp = r.get("ingredienti", [])
        por = r.get("porzioni", 0)
        note = r.get("note", "")
        if det:
            ing_html = "<table class='t'><tr><th>Ingrediente</th><th>Qtà</th><th>U</th></tr>" + "".join(f"<tr><td>{d.get('nome','')}</td><td>{d.get('quantita','')}</td><td>{d.get('unita','')}</td></tr>" for d in det) + "</table>"
        elif simp:
            ing_html = "<div class='is'>" + "".join(f"<span class='i'>{s}</span>" for s in simp) + "</div>"
        else:
            ing_html = "<p style='color:#999'>Nessun ingrediente</p>"
        por_html = f"<span class='p'>{por} porzioni</span>" if por else ""
        nota_html = f"<div class='note'>{note}</div>" if note else ""
        cards.append(f"<div class='r'><div class='rh'><h3>{i}. {r.get('nome','')}</h3>{por_html}</div><div class='rb'>{ing_html}{nota_html}</div></div>")
    data_gen = datetime.now().strftime('%d/%m/%Y %H:%M')
    html = f"""<!DOCTYPE html><html lang="it"><head><meta charset="UTF-8"><title>Ricettario</title>
<style>@page{{size:A4;margin:15mm}}body{{font-family:Arial;font-size:11pt;color:#333}}
h1{{color:#2e7d32;text-align:center}}.r{{border:1px solid #ddd;border-radius:8px;margin:12px 0;page-break-inside:avoid}}
.rh{{background:#4caf50;color:white;padding:8px 12px;border-radius:8px 8px 0 0;display:flex;justify-content:space-between;align-items:center}}
.rh h3{{margin:0;font-size:13pt}}.p{{background:rgba(255,255,255,0.2);padding:2px 8px;border-radius:10px;font-size:9pt}}
.rb{{padding:12px}}.t{{width:100%;border-collapse:collapse}}.t th{{background:#f5f5f5;padding:6px;border-bottom:2px solid #4caf50;text-align:left}}
.t td{{padding:6px;border-bottom:1px solid #eee}}.is{{display:flex;flex-wrap:wrap;gap:6px}}.i{{background:#f5f5f5;padding:4px 10px;border-radius:12px;font-size:10pt}}
.ii{{padding:2px 0;border-bottom:1px dotted #ddd;font-size:10pt}}.note{{font-style:italic;color:#666;padding:8px;background:#fff8e1;border-radius:4px;margin-top:8px}}
#idx{{column-count:3;column-gap:20px}}@media print{{button{{display:none}}}}
</style></head><body>
<h1>RICETTARIO — Ceraldi Group S.R.L.</h1>
<p style="text-align:center;color:#666">Generato il {data_gen} | {len(ricette)} ricette</p>
<div style="text-align:center;margin:16px"><button onclick="window.print()" style="padding:10px 24px;background:#4caf50;color:white;border:none;border-radius:6px;font-size:13pt;cursor:pointer">Stampa / Salva PDF</button></div>
<h2>Indice</h2><div id="idx">{idx}</div>
<div style="page-break-before:always"></div><h2>Dettaglio</h2>
{"".join(cards)}
<p style="text-align:center;margin-top:24px;color:#999;font-size:9pt">Conforme Reg. CE 178/2002</p>
</body></html>"""
    return HTMLResponse(content=html)


@router.get("/ricette")
async def get_ricette(search: Optional[str] = Query(None)):
    db = Database.get_db()
    q = {}
    if search:
        q["nome"] = {"$regex": search, "$options": "i"}
    return await db["ricette"].find(q, {"_id": 0}).sort("nome", 1).to_list(500)


@router.get("/ricette-prezzi")
async def get_ricette_prezzi():
    db = Database.get_db()
    ricette = await db["ricette"].find({}, {"_id": 0}).sort("nome", 1).to_list(500)
    dizionario = await db["dizionario_prodotti"].find({}, {"_id": 0}).to_list(5000)
    diz_map = {(d.get("nome_normalizzato") or "").lower(): d.get("prezzo_kg", 0) or 0 for d in dizionario}

    def _pkg(nome: str) -> float:
        nl = nome.lower().strip()
        if nl in diz_map:
            return diz_map[nl]
        for k, v in diz_map.items():
            if nl in k or k in nl:
                return v
        return 0

    risultati = []
    for r in ricette:
        if r.get("ricetta_base_id"):
            continue
        costo_tot = r.get("costo_totale") or 0
        porzioni = max(float(r.get("porzioni") or 1), 1)
        costo_pezzo = costo_tot / porzioni if costo_tot else 0
        prezzo_vendita = r.get("prezzo_vendita") or 0
        margine = ((prezzo_vendita - costo_pezzo) / prezzo_vendita * 100) if prezzo_vendita > 0 and costo_pezzo > 0 else 0
        varianti = [v for v in ricette if v.get("ricetta_base_id") == r["id"]]
        varianti_out = []
        for v in sorted(varianti, key=lambda x: x["nome"]):
            ing_var = v.get("ingrediente_variante") or {}
            costo_var_extra = 0
            if ing_var.get("quantita") and ing_var.get("nome"):
                costo_var_extra = (float(ing_var.get("quantita") or 0) / 1000) * (ing_var.get("costo_unitario") or _pkg(ing_var["nome"]))
            costo_var_pezzo = costo_pezzo + costo_var_extra
            pv_var = v.get("prezzo_vendita") or prezzo_vendita
            margine_var = ((pv_var - costo_var_pezzo) / pv_var * 100) if pv_var > 0 and costo_var_pezzo > 0 else 0
            varianti_out.append({
                "id": v["id"], "nome": v["nome"], "ingrediente_variante": ing_var,
                "costo_variante_extra": round(costo_var_extra, 4), "costo_pezzo": round(costo_var_pezzo, 4),
                "prezzo_vendita": pv_var, "margine_pct": round(margine_var, 1),
            })
        risultati.append({
            "id": r["id"], "nome": r["nome"], "porzioni": porzioni,
            "costo_totale": costo_tot, "costo_pezzo": round(costo_pezzo, 4),
            "prezzo_vendita": prezzo_vendita, "margine_pct": round(margine, 1),
            "reparto": r.get("reparto", ""), "varianti": varianti_out,
        })
    return risultati


@router.get("/tablet/{reparto}")
async def get_tablet(reparto: str):
    if reparto not in ("pasticceria", "rosticceria", "altro"):
        raise HTTPException(400, "Reparto non valido")
    db = Database.get_db()
    ricette = await db["ricette"].find(
        {"reparto": reparto},
        {"_id": 0, "id": 1, "nome": 1, "reparto": 1, "foto_url": 1, "ingredienti_dettaglio": 1, "note": 1}
    ).sort("nome", 1).to_list(200)
    return {"reparto": reparto, "totale": len(ricette), "prodotti": ricette}


@router.get("/ricette/{ricetta_id}")
async def get_ricetta(ricetta_id: str):
    db = Database.get_db()
    item = await db["ricette"].find_one({"id": ricetta_id}, {"_id": 0})
    if not item:
        raise HTTPException(404, "Ricetta non trovata")
    return item


@router.post("/ricette")
async def create_ricetta(item: RicettaCreate):
    db = Database.get_db()
    obj = Ricetta(**item.model_dump())
    doc = obj.model_dump()
    doc["created_at"] = doc["created_at"].isoformat()
    await db["ricette"].insert_one(doc)
    doc.pop("_id", None)
    return obj


@router.put("/ricette/{ricetta_id}")
async def update_ricetta(ricetta_id: str, item: RicettaCreate):
    db = Database.get_db()
    r = await db["ricette"].update_one({"id": ricetta_id}, {"$set": item.model_dump()})
    if r.matched_count == 0:
        raise HTTPException(404, "Ricetta non trovata")
    return await db["ricette"].find_one({"id": ricetta_id}, {"_id": 0})


@router.delete("/ricette/{ricetta_id}")
async def delete_ricetta(ricetta_id: str):
    db = Database.get_db()
    r = await db["ricette"].delete_one({"id": ricetta_id})
    if r.deleted_count == 0:
        raise HTTPException(404, "Ricetta non trovata")
    return {"message": "Eliminata con successo"}


@router.put("/ricette/{ricetta_id}/prezzo-vendita")
async def set_prezzo_vendita(ricetta_id: str, prezzo: float = Query(...)):
    db = Database.get_db()
    await db["ricette"].update_one({"id": ricetta_id}, {"$set": {"prezzo_vendita": prezzo}})
    return {"ok": True, "prezzo_vendita": prezzo}


@router.put("/ricette/{ricetta_id}/reparto")
async def aggiorna_reparto(ricetta_id: str, reparto: str = Query(...)):
    if reparto not in ("pasticceria", "rosticceria", "altro"):
        raise HTTPException(400, "Reparto non valido")
    db = Database.get_db()
    r = await db["ricette"].update_one({"id": ricetta_id}, {"$set": {"reparto": reparto}})
    if r.matched_count == 0:
        raise HTTPException(404, "Ricetta non trovata")
    return await db["ricette"].find_one({"id": ricetta_id}, {"_id": 0})


@router.put("/ricette/{ricetta_id}/foto")
async def aggiorna_foto(ricetta_id: str, foto_url: str = Query(...)):
    db = Database.get_db()
    r = await db["ricette"].update_one({"id": ricetta_id}, {"$set": {"foto_url": foto_url}})
    if r.matched_count == 0:
        raise HTTPException(404, "Ricetta non trovata")
    return {"success": True}


@router.put("/ricette/{ricetta_id}/ingredienti-dettaglio")
async def aggiorna_ingredienti_dettaglio(ricetta_id: str, ingredienti_dettaglio: List[dict]):
    db = Database.get_db()
    r = await db["ricette"].update_one({"id": ricetta_id}, {"$set": {"ingredienti_dettaglio": ingredienti_dettaglio}})
    if r.matched_count == 0:
        raise HTTPException(404, "Ricetta non trovata")
    return await db["ricette"].find_one({"id": ricetta_id}, {"_id": 0})


@router.patch("/ricette/{ricetta_id}/approva")
async def approva_ricetta(ricetta_id: str):
    db = Database.get_db()
    r = await db["ricette"].find_one({"id": ricetta_id}, {"_id": 0, "id": 1})
    if not r:
        raise HTTPException(404, "Ricetta non trovata")
    await db["ricette"].update_one({"id": ricetta_id}, {"$set": {"approvata": True}})
    return {"success": True, "approvata": True}


@router.patch("/ricette/{ricetta_id}")
async def aggiorna_campo_ricetta(ricetta_id: str, body: dict):
    db = Database.get_db()
    campi_permessi = {"pezzi_ricetta_base", "porzioni", "note", "reparto", "prezzo_vendita", "componenti"}
    update = {k: v for k, v in body.items() if k in campi_permessi}
    if not update:
        raise HTTPException(400, "Nessun campo valido da aggiornare")
    r = await db["ricette"].update_one({"id": ricetta_id}, {"$set": update})
    if r.matched_count == 0:
        raise HTTPException(404, "Ricetta non trovata")
    return {"success": True, "aggiornato": update}


@router.post("/ricette/auto-assegna-reparti")
async def auto_assegna_reparti():
    db = Database.get_db()
    ricette = await db["ricette"].find({}, {"_id": 0, "id": 1, "nome": 1}).to_list(500)
    dettaglio = {"pasticceria": [], "rosticceria": [], "altro": []}
    for r in ricette:
        rep = _categorizza_reparto(r.get("nome", ""))
        await db["ricette"].update_one({"id": r["id"]}, {"$set": {"reparto": rep}})
        dettaglio[rep].append(r.get("nome", ""))
    return {
        "aggiornate": len(ricette),
        "pasticceria": len(dettaglio["pasticceria"]),
        "rosticceria": len(dettaglio["rosticceria"]),
        "altro": len(dettaglio["altro"])
    }
