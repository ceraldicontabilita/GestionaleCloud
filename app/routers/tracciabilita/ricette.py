"""
Router Ricette — estratto da server.py
GET  /api/ricette                    — lista
GET  /api/ricette/{id}               — dettaglio
POST /api/ricette                    — crea
PUT  /api/ricette/{id}               — aggiorna
DELETE /api/ricette/{id}             — elimina
GET  /api/ricette-prezzi             — calcolo costo/pezzo + margine + varianti
PUT  /api/ricette/{id}/prezzo-vendita — imposta prezzo vendita
PUT  /api/ricette/{id}/reparto       — assegna reparto
PUT  /api/ricette/{id}/foto          — salva URL foto
POST /api/ricette/{id}/upload-foto   — upload immagine
PUT  /api/ricette/{id}/ingredienti-dettaglio — aggiorna quantità ingredienti
GET  /api/ricette-libro              — ricettario importato da Excel
GET  /api/ricette/export/pdf         — export HTML stampabile
GET  /api/ricette/export/csv         — export CSV
GET  /api/ricette/export/json        — export JSON
POST /api/ricette/auto-assegna-reparti
POST /api/ricette/pulisci-ingredienti
POST /api/ricette/popola-quantita-esempio
GET  /api/tablet/{reparto}          — prodotti per vista tablet
"""
from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Body
from app.routers.tracciabilita.server import db
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Any
from datetime import datetime, timezone
from pathlib import Path
import os, uuid, re, shutil, mimetypes


ROOT_DIR = Path(__file__).resolve().parent.parent

router = APIRouter(tags=["Ricette"])

# ─── Modelli ──────────────────────────────────────────────────────────────────
class Ricetta(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    nome: str
    ingredienti: List[Any] = []
    ingredienti_dettaglio: List[dict] = []
    componenti: Optional[List[dict]] = []   # BOM: [{tipo, ref_id, nome, quantita, unita_misura}]
    porzioni: Optional[float] = 1
    note: str = ""
    approvata: Optional[bool] = None        # None=vecchia, False=nuova da approvare, True=approvata
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
    componenti: Optional[List[dict]] = []   # BOM composito
    porzioni: int = 1
    note: str = ""
    ricetta_base_id: Optional[str] = None
    ricetta_base_nome: Optional[str] = None
    ingrediente_variante: Optional[dict] = None
    prezzo_vendita: Optional[float] = None
    reparto: Optional[str] = None

# ─── Helper reparti e nomi ────────────────────────────────────────────────────
_PASTICCERIA_KW = ["torta","crema","mousse","cheesecake","mille foglie","profitterol","cannolo",
    "sfogliatella","babà","baba","frolla","crostata","macaron","eclair","choux","gelato","semifreddo",
    "tiramisu","tiramisù","panna cotta","pannacotta","crèpe","crepe","waffle","donut","muffin",
    "cupcake","brownie","cookies","biscotto","biscotti","meringhe","meringa","ganache","glassa",
    "confettura","marmellata","namelaka","cremoso","cornetto","brioche","pasticceria","dolce","dessert",
    "budino","flan","strudel","paris-brest","tronchetto","charlotte","cassata","pastiera","struffoli",
    "zeppole","ciambella","ciambellone","pandoro","panettone","colomba","frittelle","bombolone",
    "maritozzo","diplomatico","zuccotto","gianduja","cremino","mignon","savarin",
]
_ROSTICCERIA_KW = ["pizza","focaccia","calzone","piadina","panino","sandwich","burger","tramezzino",
    "bruschetta","crostino","arancino","arancina","arancini","supplì","frittata","quiche",
    "mozzarella in carrozza","impanata","fritto","frittura","lasagna","lasagne","gnocchi","risotto",
    "polenta","polpetta","polpette","cotoletta","scaloppina","arrosto","pollo","carne","pesce",
    "baccalà","alici","acciughe","polpo","calamari","gamberi","cozze","vongole","frittella salata",
    "torta salata","rustici","panzerotti","vol-au-vent","croissant salato",
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

def _pulisci_nome_ing(nome: str) -> str:
    if not nome:
        return ""
    cleaned = re.sub(r'\s+[A-Z]{1,4}[./][A-Z0-9]{1,10}(?:[./][A-Z0-9]{1,10})*', '', nome, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s+\d+(?:[.,]\d+)?\s*(?:kg|g|ml|l|lt|cl)\b', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s+\d+$', '', cleaned)
    return ' '.join(cleaned.split()).strip()

# ─── Endpoints ────────────────────────────────────────────────────────────────
@router.get("/ricette")
async def get_ricette(search: Optional[str] = Query(None)):
    q = {}
    if search:
        q["nome"] = {"$regex": search, "$options": "i"}
    return await db.ricette.find(q, {"_id": 0}).sort("nome", 1).to_list(500)


@router.get("/ricette-prezzi")
async def get_ricette_prezzi():
    ricette = await db.ricette.find({}, {"_id": 0}).sort("nome", 1).to_list(500)
    dizionario = await db.dizionario_prodotti.find({}, {"_id": 0}).to_list(5000)
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


@router.get("/ricette/export/pdf", response_class=HTMLResponse)
async def export_pdf():
    ricette = await db.ricette.find({}, {"_id": 0}).sort("nome", 1).to_list(1000)
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


@router.get("/ricette/export/csv")
async def export_csv():
    ricette = await db.ricette.find({}, {"_id": 0}).sort("nome", 1).to_list(1000)
    rows = ["ID;Nome;Porzioni;Ingrediente;Quantità;Unità;Data"]
    for r in ricette:
        nome = r.get("nome", "").replace(";", ",")
        rid = r.get("id", "")
        porzioni = r.get("porzioni", 1)
        created = r.get("created_at", "")[:10]
        det = r.get("ingredienti_dettaglio", [])
        simp = r.get("ingredienti", [])
        if det:
            for d in det:
                rows.append(f'"{rid}";"{nome}";{porzioni};"{d.get("nome","")}";"{d.get("quantita","")}";"{d.get("unita","")}";"{created}"')
        elif simp:
            for s in simp:
                rows.append(f'"{rid}";"{nome}";{porzioni};"{s}";"";"";":{created}"')
        else:
            rows.append(f'"{rid}";"{nome}";{porzioni};"";"";"";"{created}"')
    filename = f"ricettario_{datetime.now().strftime('%Y%m%d')}.csv"
    return Response(content="\n".join(rows).encode("utf-8-sig"), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/ricette/export/template-csv")
async def export_template_csv():
    """
    Esporta template CSV compilabile per importare nuove ricette o aggiornare quelle esistenti.
    Formato: AZIONE;ID;Nome;Porzioni;Reparto;Note;Ingrediente_1;Q1;UM1;Ingrediente_2;Q2;UM2;...
    AZIONE: NUOVA = crea nuova, AGGIORNA = aggiorna esistente, SALTA = ignora riga
    """
    import io, csv as _csv

    ricette = await db.ricette.find({}, {"_id": 0}).sort("nome", 1).to_list(1000)

    # Determina il numero massimo di ingredienti
    max_ing = max(
        (len(r.get("ingredienti_dettaglio") or r.get("ingredienti", [])) for r in ricette),
        default=0
    )
    max_ing = max(max_ing, 5)  # minimo 5 colonne ingredienti per template

    output = io.StringIO()
    writer = _csv.writer(output, delimiter=";", quotechar='"', quoting=_csv.QUOTE_MINIMAL)

    # Riga intestazione
    intestazione = ["AZIONE", "ID", "Nome_Ricetta", "Porzioni", "Reparto", "Note", "Allergeni"]
    for i in range(1, max_ing + 1):
        intestazione += [f"Ingrediente_{i}", f"Quantita_{i}", f"Unita_{i}"]
    writer.writerow(intestazione)

    # Riga istruzioni (commentata)
    istruzioni = [
        "# ISTRUZIONI",
        "# (lascia vuoto per nuova)",
        "# Nome obbligatorio",
        "# Numero pezzi per ricetta",
        "# pasticceria/rosticceria/bar",
        "# Note libere",
        "# Es: Glutine|Latte|Uova"
    ]
    while len(istruzioni) < len(intestazione):
        istruzioni.append("")
    writer.writerow(istruzioni)

    # Riga esempio
    esempio = ["NUOVA", "", "Cornetto al Cioccolato", "12", "pasticceria",
               "Ricetta classica", "Glutine|Uova|Latte",
               "Farina 00", "500", "g", "Burro", "200", "g", "Uova", "3", "pz"]
    while len(esempio) < len(intestazione):
        esempio.append("")
    writer.writerow(esempio)

    # Separatore
    writer.writerow(["---DATI ESISTENTI---"] + [""] * (len(intestazione) - 1))

    # Esporta ricette esistenti
    for r in ricette:
        det = r.get("ingredienti_dettaglio") or []
        simp = r.get("ingredienti") or []
        allergeni = "|".join(r.get("allergeni") or [])
        reparto = r.get("reparto") or ""

        riga = [
            "AGGIORNA",
            r.get("id", ""),
            r.get("nome", ""),
            str(r.get("porzioni", 1)),
            reparto,
            (r.get("note", "") or "").replace("\n", " ")[:100],
            allergeni
        ]

        if det:
            for ing in det[:max_ing]:
                nome_ing = ing.get("nome", "")
                qty = ing.get("quantita", "") or ing.get("q", "")
                um = ing.get("unita_misura", "") or ing.get("unita", "") or ing.get("um", "")
                riga += [nome_ing, str(qty), um]
        elif simp:
            for s in simp[:max_ing]:
                riga += [s, "", ""]
        # Padding
        while len(riga) < len(intestazione):
            riga.append("")
        writer.writerow(riga)

    csv_content = output.getvalue()
    filename = f"ricettario_template_{datetime.now().strftime('%Y%m%d')}.csv"
    return Response(
        content=csv_content.encode("utf-8-sig"),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


@router.post("/ricette/import/csv")
async def import_csv_ricette(file: bytes = Body(..., media_type="application/octet-stream"),
                              anteprima: bool = Query(False)):
    """
    Importa ricette da CSV con template. Supporta NUOVA e AGGIORNA.
    Se anteprima=True restituisce solo il piano di importazione senza salvare.
    """
    import io, csv as _csv

    try:
        testo = file.decode("utf-8-sig").strip()
    except Exception:
        raise HTTPException(400, "File non decodificabile. Usare UTF-8.")

    reader = _csv.reader(io.StringIO(testo), delimiter=";")
    righe = list(reader)

    if not righe:
        return {"errore": "File vuoto"}

    # Trova intestazione (prima riga che inizia con AZIONE)
    header_idx = next(
        (i for i, r in enumerate(righe)
         if r and r[0].strip().upper() in ("AZIONE", "ACTION")),
        None
    )
    if header_idx is None:
        raise HTTPException(400, "Intestazione AZIONE non trovata nel file")

    header = [h.strip() for h in righe[header_idx]]
    dati   = righe[header_idx + 1:]

    def get_col(riga, nome):
        try:
            return riga[header.index(nome)].strip() if nome in header else ""
        except (ValueError, IndexError):
            return ""

    # Estrai colonne ingredienti dinamiche
    ing_cols = [h for h in header if h.startswith("Ingrediente_")]

    plan = {"nuove": [], "aggiornate": [], "saltate": [], "errori": []}

    for i, riga in enumerate(dati):
        if not riga or not riga[0].strip():
            continue
        azione = riga[0].strip().upper()
        if azione.startswith("#") or azione.startswith("---"):
            continue
        if azione == "SALTA":
            plan["saltate"].append(get_col(riga, "Nome_Ricetta") or f"riga {i+1}")
            continue

        nome = get_col(riga, "Nome_Ricetta")
        if not nome:
            plan["errori"].append(f"Riga {i+1}: Nome_Ricetta mancante")
            continue

        porzioni = 1
        try:
            porzioni = int(float(get_col(riga, "Porzioni") or "1"))
        except Exception:
            pass

        reparto   = get_col(riga, "Reparto")
        note      = get_col(riga, "Note")
        allergeni_str = get_col(riga, "Allergeni")
        allergeni = [a.strip() for a in allergeni_str.split("|") if a.strip()] if allergeni_str else []
        rid       = get_col(riga, "ID")

        # Estrai ingredienti
        ingredienti_dettaglio = []
        for ic in ing_cols:
            n_idx = header.index(ic)
            num   = int(ic.replace("Ingrediente_", ""))
            q_col = f"Quantita_{num}"
            u_col = f"Unita_{num}"
            nome_ing = riga[n_idx].strip() if n_idx < len(riga) else ""
            qty_raw  = riga[header.index(q_col)].strip() if q_col in header and header.index(q_col) < len(riga) else ""
            um       = riga[header.index(u_col)].strip() if u_col in header and header.index(u_col) < len(riga) else ""
            if nome_ing:
                try:
                    qty = float(qty_raw.replace(",", ".")) if qty_raw else None
                except Exception:
                    qty = None
                ingredienti_dettaglio.append({
                    "nome": nome_ing,
                    "quantita": qty,
                    "unita_misura": um,
                    "unita": um,
                })

        doc = {
            "nome": nome,
            "porzioni": porzioni,
            "reparto": reparto,
            "note": note,
            "allergeni": allergeni,
            "ingredienti": [i["nome"] for i in ingredienti_dettaglio],
            "ingredienti_dettaglio": ingredienti_dettaglio,
        }

        if azione == "NUOVA" or (azione == "AGGIORNA" and not rid):
            plan["nuove"].append({"nome": nome, "doc": doc})
        elif azione == "AGGIORNA" and rid:
            plan["aggiornate"].append({"id": rid, "nome": nome, "doc": doc})
        else:
            plan["errori"].append(f"Azione sconosciuta '{azione}' riga {i+1}")

    if anteprima:
        return {
            "anteprima": True,
            "nuove": len(plan["nuove"]),
            "aggiornate": len(plan["aggiornate"]),
            "saltate": len(plan["saltate"]),
            "errori": plan["errori"],
            "dettaglio_nuove": [p["nome"] for p in plan["nuove"]],
            "dettaglio_aggiornate": [p["nome"] for p in plan["aggiornate"]],
        }

    # Esegui import
    import uuid
    create_count, update_count, err_count = 0, 0, 0

    for item in plan["nuove"]:
        try:
            doc = item["doc"]
            doc["id"] = str(uuid.uuid4())
            doc["created_at"] = datetime.now(timezone.utc).isoformat()
            doc["approvata"] = False   # badge 🆕 NUOVA finché non approvata
            await db.ricette.insert_one({k: v for k, v in doc.items() if k != "_id"})
            create_count += 1
        except Exception as e:
            plan["errori"].append(f"Errore creazione '{item['nome']}': {e}")
            err_count += 1

    for item in plan["aggiornate"]:
        try:
            update_doc = {k: v for k, v in item["doc"].items() if k not in ("id", "created_at", "_id")}
            result = await db.ricette.update_one(
                {"id": item["id"]},
                {"$set": update_doc}
            )
            if result.matched_count > 0:
                update_count += 1
            else:
                plan["errori"].append(f"ID non trovato: {item['id']} ({item['nome']})")
        except Exception as e:
            plan["errori"].append(f"Errore aggiornamento '{item['nome']}': {e}")
            err_count += 1

    return {
        "successo": True,
        "create": create_count,
        "aggiornate": update_count,
        "errori": plan["errori"],
        "totale_errori": len(plan["errori"])
    }


@router.get("/ricette/export/json")
async def export_json():
    import json as _j
    ricette = await db.ricette.find({}, {"_id": 0}).sort("nome", 1).to_list(1000)
    content = _j.dumps({"azienda": "Ceraldi Group", "export_date": datetime.now().isoformat(), "totale": len(ricette), "ricette": ricette}, ensure_ascii=False, indent=2)
    filename = f"ricettario_{datetime.now().strftime('%Y%m%d')}.json"
    return Response(content=content.encode("utf-8"), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/ricette-libro")
async def get_ricette_libro(search: Optional[str] = Query(None)):
    q = {}
    if search:
        q["$or"] = [{"nome": {"$regex": search, "$options": "i"}}, {"ingredienti_testo": {"$regex": search, "$options": "i"}}]
    return await db.ricette_libro.find(q, {"_id": 0}).sort("nome", 1).to_list(500)


@router.get("/ricette-libro/{ricetta_id}")
async def get_ricetta_libro(ricetta_id: str):
    item = await db.ricette_libro.find_one({"id": ricetta_id}, {"_id": 0})
    if not item:
        raise HTTPException(404, "Ricetta non trovata")
    return item


@router.get("/tablet/{reparto}")
async def get_tablet(reparto: str):
    if reparto not in ("pasticceria", "rosticceria", "altro"):
        raise HTTPException(400, "Reparto non valido")
    ricette = await db.ricette.find({"reparto": reparto}, {"_id": 0, "id": 1, "nome": 1, "reparto": 1, "foto_url": 1, "ingredienti_dettaglio": 1, "note": 1}).sort("nome", 1).to_list(200)
    return {"reparto": reparto, "totale": len(ricette), "prodotti": ricette}


@router.get("/ricette/{ricetta_id}", response_model=Ricetta)
async def get_ricetta(ricetta_id: str):
    item = await db.ricette.find_one({"id": ricetta_id}, {"_id": 0})
    if not item:
        raise HTTPException(404, "Ricetta non trovata")
    return item


@router.post("/ricette", response_model=Ricetta)
async def create_ricetta(item: RicettaCreate):
    obj = Ricetta(**item.model_dump())
    doc = obj.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    await db.ricette.insert_one(doc)
    return obj


@router.put("/ricette/{ricetta_id}", response_model=Ricetta)
async def update_ricetta(ricetta_id: str, item: RicettaCreate):
    r = await db.ricette.update_one({"id": ricetta_id}, {"$set": item.model_dump()})
    if r.matched_count == 0:
        raise HTTPException(404, "Ricetta non trovata")
    return await db.ricette.find_one({"id": ricetta_id}, {"_id": 0})


@router.delete("/ricette/{ricetta_id}")
async def delete_ricetta(ricetta_id: str):
    r = await db.ricette.delete_one({"id": ricetta_id})
    if r.deleted_count == 0:
        raise HTTPException(404, "Ricetta non trovata")
    return {"message": "Eliminata con successo"}


@router.put("/ricette/{ricetta_id}/prezzo-vendita")
async def set_prezzo_vendita(ricetta_id: str, prezzo: float = Query(...)):
    await db.ricette.update_one({"id": ricetta_id}, {"$set": {"prezzo_vendita": prezzo}})
    return {"ok": True, "prezzo_vendita": prezzo}


@router.put("/ricette/{ricetta_id}/reparto")
async def aggiorna_reparto(ricetta_id: str, reparto: str = Query(...)):
    if reparto not in ("pasticceria", "rosticceria", "altro"):
        raise HTTPException(400, "Reparto non valido")
    r = await db.ricette.update_one({"id": ricetta_id}, {"$set": {"reparto": reparto}})
    if r.matched_count == 0:
        raise HTTPException(404, "Ricetta non trovata")
    return await db.ricette.find_one({"id": ricetta_id}, {"_id": 0})


@router.put("/ricette/{ricetta_id}/foto")
async def aggiorna_foto(ricetta_id: str, foto_url: str = Query(...)):
    r = await db.ricette.update_one({"id": ricetta_id}, {"$set": {"foto_url": foto_url}})
    if r.matched_count == 0:
        raise HTTPException(404, "Ricetta non trovata")
    return {"success": True}


@router.post("/ricette/{ricetta_id}/upload-foto")
async def upload_foto(ricetta_id: str, file: UploadFile = File(...)):
    mime = file.content_type or ""
    if not mime.startswith("image/"):
        raise HTTPException(400, "File non è un'immagine")
    ext = mimetypes.guess_extension(mime) or ".jpg"
    if ext == ".jpe":
        ext = ".jpg"
    safe_id = ricetta_id.replace("/", "_")
    filename = f"{safe_id}{ext}"
    upload_dir = ROOT_DIR.parent / "frontend" / "public" / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / filename
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    foto_url = f"/uploads/{filename}"
    await db.ricette.update_one({"id": ricetta_id}, {"$set": {"foto_url": foto_url}})
    return {"success": True, "foto_url": foto_url}


@router.put("/ricette/{ricetta_id}/ingredienti-dettaglio")
async def aggiorna_ingredienti_dettaglio(ricetta_id: str, ingredienti_dettaglio: List[dict]):
    r = await db.ricette.update_one({"id": ricetta_id}, {"$set": {"ingredienti_dettaglio": ingredienti_dettaglio}})
    if r.matched_count == 0:
        raise HTTPException(404, "Ricetta non trovata")
    return await db.ricette.find_one({"id": ricetta_id}, {"_id": 0})



@router.patch("/ricette/{ricetta_id}")
async def aggiorna_campo_ricetta(ricetta_id: str, body: dict):
    """Aggiornamento parziale di una ricetta (pezzi_ricetta_base, note, ecc.)."""
    campi_permessi = {"pezzi_ricetta_base", "porzioni", "note", "reparto", "prezzo_vendita", "componenti"}
    update = {k: v for k, v in body.items() if k in campi_permessi}
    if not update:
        raise HTTPException(400, "Nessun campo valido da aggiornare")
    r = await db.ricette.update_one({"id": ricetta_id}, {"$set": update})
    if r.matched_count == 0:
        raise HTTPException(404, "Ricetta non trovata")
    return {"success": True, "aggiornato": update}



@router.post("/ricette/auto-assegna-reparti")
async def auto_assegna_reparti():
    ricette = await db.ricette.find({}, {"_id": 0, "id": 1, "nome": 1}).to_list(500)
    dettaglio = {"pasticceria": [], "rosticceria": [], "altro": []}
    for r in ricette:
        rep = _categorizza_reparto(r.get("nome", ""))
        await db.ricette.update_one({"id": r["id"]}, {"$set": {"reparto": rep}})
        dettaglio[rep].append(r.get("nome", ""))
    return {"aggiornate": len(ricette), "pasticceria": len(dettaglio["pasticceria"]),
            "rosticceria": len(dettaglio["rosticceria"]), "altro": len(dettaglio["altro"]), "dettaglio": dettaglio}


@router.post("/ricette/pulisci-ingredienti")
async def pulisci_ingredienti():
    ricette = await db.ricette.find({}, {"_id": 0}).to_list(1000)
    risultato = {"ricette_processate": 0, "ingredienti_puliti": 0, "esempi": []}
    for r in ricette:
        originali = r.get("ingredienti", [])
        puliti = []
        modificato = False
        for ing in originali:
            p = _pulisci_nome_ing(ing)
            if p and not any(x.lower() == p.lower() for x in puliti):
                puliti.append(p)
            if ing != p:
                modificato = True
                if len(risultato["esempi"]) < 10:
                    risultato["esempi"].append({"originale": ing, "pulito": p})
        if modificato:
            await db.ricette.update_one({"id": r["id"]}, {"$set": {"ingredienti": puliti}})
            risultato["ingredienti_puliti"] += len(originali)
        risultato["ricette_processate"] += 1
    return risultato


@router.post("/ricette/popola-quantita-esempio")
async def popola_quantita_esempio():
    _QS = {
        "farina": {"quantita": 500, "unita": "g"}, "uova": {"quantita": 4, "unita": "pz"},
        "burro": {"quantita": 150, "unita": "g"}, "zucchero": {"quantita": 200, "unita": "g"},
        "latte": {"quantita": 250, "unita": "ml"}, "panna": {"quantita": 200, "unita": "ml"},
        "olio": {"quantita": 100, "unita": "ml"}, "sale": {"quantita": 10, "unita": "g"},
        "lievito": {"quantita": 15, "unita": "g"}, "cacao": {"quantita": 30, "unita": "g"},
        "cioccolato": {"quantita": 100, "unita": "g"}, "ricotta": {"quantita": 250, "unita": "g"},
        "mascarpone": {"quantita": 250, "unita": "g"}, "mozzarella": {"quantita": 200, "unita": "g"},
        "tuorlo": {"quantita": 6, "unita": "pz"}, "albume": {"quantita": 4, "unita": "pz"},
        "miele": {"quantita": 50, "unita": "g"}, "vaniglia": {"quantita": 1, "unita": "bustina"},
    }
    ricette = await db.ricette.find({}, {"_id": 0}).to_list(1000)
    aggiornate = 0
    for r in ricette:
        det = [{"nome": ing, **(next((v for k, v in _QS.items() if k in ing.lower()), {"quantita": "q.b.", "unita": ""}))} for ing in r.get("ingredienti", [])]
        if det:
            await db.ricette.update_one({"id": r["id"]}, {"$set": {"ingredienti_dettaglio": det, "porzioni": 10}})
            aggiornate += 1
    return {"success": True, "aggiornate": aggiornate}


# ─── BOM (Bill of Materials) esploso ─────────────────────────────────────────

async def _esplodi_componente(comp: dict, porzioni_target: float, porzioni_ricetta: float,
                               visitati: set, profondita: int = 0) -> tuple[list, list]:
    """
    Ricorsivamente esplode un componente BOM.
    Ritorna (ingredienti_flat, struttura).
    Anti-loop: interrompe se ref_id già visitato.
    """
    tipo = comp.get("tipo", "ingrediente")
    nome = comp.get("nome", "")
    qt_raw = float(comp.get("quantita", 0) or 0)
    um = comp.get("unita_misura", "g")

    if tipo != "sotto_ricetta":
        # Ingrediente diretto — scala proporzionalmente
        fattore = (porzioni_target / porzioni_ricetta) if porzioni_ricetta > 0 else 1
        qt_scalata = round(qt_raw * fattore, 3)
        item = {"nome": nome, "quantita": qt_scalata, "unita_misura": um}
        return [item], [{"nome": nome, "tipo": "ingrediente", "quantita": qt_scalata, "unita_misura": um}]

    ref_id = comp.get("ref_id", "")
    if ref_id in visitati:
        # Anti-loop
        return [], [{"nome": nome, "tipo": "sotto_ricetta", "warning": "loop rilevato, saltato"}]
    visitati.add(ref_id)

    sotto = await db.ricette.find_one({"id": ref_id}, {"_id": 0})
    if not sotto:
        # Prova per nome
        sotto = await db.ricette.find_one({"nome": {"$regex": f"^{nome}$", "$options": "i"}}, {"_id": 0})
    if not sotto:
        return [], [{"nome": nome, "tipo": "sotto_ricetta", "warning": "ricetta non trovata"}]

    porz_sotto = float(sotto.get("porzioni", 1) or 1)
    # Quante porzioni della sotto-ricetta servono?
    # qt_raw è la quantità della sotto-ricetta espressa nella sua UM.
    # Per semplificare: fattore_scala = (porzioni_target / porzioni_ricetta) * 1
    fattore_globale = (porzioni_target / porzioni_ricetta) if porzioni_ricetta > 0 else 1
    # porzioni della sotto-ricetta da produrre = fattore_globale * qt_raw (trattato come porzioni già scalate)
    porz_target_sotto = qt_raw * fattore_globale

    ing_flat = []
    struttura_figli = []

    componenti_sotto = sotto.get("componenti") or []
    sorgente = componenti_sotto if componenti_sotto else [
        {"tipo": "ingrediente", "nome": i.get("nome", ""), "quantita": float(i.get("quantita", 0) or 0),
         "unita_misura": i.get("unita_misura", "g")}
        for i in sotto.get("ingredienti_dettaglio", [])
    ]

    for figlio in sorgente:
        flat_f, strutt_f = await _esplodi_componente(figlio, porz_target_sotto, porz_sotto, visitati, profondita + 1)
        ing_flat.extend(flat_f)
        struttura_figli.extend(strutt_f)

    struttura_nodo = {
        "nome": nome,
        "tipo": "sotto_ricetta",
        "ricetta_id": ref_id,
        "porzioni_usate": round(porz_target_sotto, 2),
        "ingredienti": struttura_figli,
    }
    return ing_flat, [struttura_nodo]


@router.get("/ricette/{ricetta_id}/bom")
async def get_bom_ricetta(ricetta_id: str, porzioni: float = Query(None)):
    """
    Calcola e restituisce il BOM esploso della ricetta, scalato per N porzioni.
    Supporta ricette composite (con componenti[]) e semplici (ingredienti_dettaglio).
    Anti-loop incluso. Raggruppa ingredienti duplicati sommando le quantità (stessa UM).
    """
    ricetta = await db.ricette.find_one({"id": ricetta_id}, {"_id": 0})
    if not ricetta:
        raise HTTPException(404, "Ricetta non trovata")

    porzioni_base = float(ricetta.get("porzioni", 1) or 1)
    porzioni_target = porzioni if porzioni is not None else porzioni_base
    moltiplicatore = round(porzioni_target / porzioni_base, 4) if porzioni_base > 0 else 1.0

    componenti = ricetta.get("componenti") or []
    if not componenti:
        # Ricetta semplice — usa ingredienti_dettaglio come lista piatta
        componenti = [
            {"tipo": "ingrediente", "nome": i.get("nome", ""), "quantita": float(i.get("quantita", 0) or 0),
             "unita_misura": i.get("unita_misura", "g")}
            for i in ricetta.get("ingredienti_dettaglio", [])
        ]

    visitati = {ricetta_id}  # anti-loop: include la ricetta stessa
    ing_flat_totale = []
    struttura_totale = []

    for comp in componenti:
        flat, strutt = await _esplodi_componente(comp, porzioni_target, porzioni_base, visitati)
        ing_flat_totale.extend(flat)
        struttura_totale.extend(strutt)

    # Raggruppa per (nome, unita_misura)
    raggruppati: dict[tuple, float] = {}
    for ing in ing_flat_totale:
        chiave = (ing["nome"], ing["unita_misura"])
        raggruppati[chiave] = raggruppati.get(chiave, 0.0) + ing["quantita"]

    ingredienti_esplosi = [
        {"nome": nome, "quantita": round(qt, 3), "unita_misura": um}
        for (nome, um), qt in raggruppati.items()
    ]

    return {
        "ricetta_id": ricetta_id,
        "ricetta_nome": ricetta.get("nome", ""),
        "porzioni_richieste": porzioni_target,
        "porzioni_base": porzioni_base,
        "moltiplicatore": moltiplicatore,
        "ingredienti_esplosi": ingredienti_esplosi,
        "struttura": struttura_totale,
        "e_composita": bool(ricetta.get("componenti")),
    }


# ── APPROVAZIONE ─────────────────────────────────────────────────────────────
@router.patch("/ricette/{ricetta_id}/approva")
async def approva_ricetta(ricetta_id: str):
    """Imposta approvata=True sulla ricetta. Rimuove il badge 'NUOVA'."""
    r = await db.ricette.find_one({"id": ricetta_id}, {"_id": 0, "id": 1})
    if not r:
        raise HTTPException(404, "Ricetta non trovata")
    await db.ricette.update_one({"id": ricetta_id}, {"$set": {"approvata": True}})
    return {"success": True, "approvata": True}


# ── VALORI NUTRIZIONALI ───────────────────────────────────────────────────────
# Tabella nutrizionale per 100g (stime ragionevoli — non da laboratorio)
_NUTRI: dict = {
    # Cereali e derivati
    "farina":        {"kcal": 364, "prot": 10.5, "carb": 74.0, "grassi": 0.9},
    "semola":        {"kcal": 362, "prot": 12.5, "carb": 70.0, "grassi": 1.5},
    "riso":          {"kcal": 340, "prot":  6.5, "carb": 80.0, "grassi": 0.4},
    "pasta":         {"kcal": 360, "prot": 13.0, "carb": 71.0, "grassi": 1.5},
    "pane":          {"kcal": 275, "prot":  8.0, "carb": 54.0, "grassi": 1.3},
    "pangrattato":   {"kcal": 350, "prot": 10.0, "carb": 70.0, "grassi": 2.5},
    "amido":         {"kcal": 381, "prot":  0.3, "carb": 94.0, "grassi": 0.0},
    "lievito":       {"kcal": 105, "prot":  8.5, "carb": 18.0, "grassi": 1.0},
    # Latticini
    "latte":         {"kcal":  66, "prot":  3.2, "carb":  4.9, "grassi": 3.9},
    "panna":         {"kcal": 337, "prot":  2.2, "carb":  3.2, "grassi":36.0},
    "burro":         {"kcal": 750, "prot":  0.9, "carb":  0.8, "grassi":83.0},
    "ricotta":       {"kcal": 174, "prot":  9.5, "carb":  2.7, "grassi":13.7},
    "mozzarella":    {"kcal": 280, "prot": 18.7, "carb":  0.7, "grassi":22.4},
    "formaggio":     {"kcal": 380, "prot": 26.0, "carb":  1.0, "grassi":30.0},
    "parmigiano":    {"kcal": 431, "prot": 33.0, "carb":  0.0, "grassi":33.0},
    "mascarpone":    {"kcal": 450, "prot":  5.8, "carb":  4.5, "grassi":44.0},
    "caciocavallo":  {"kcal": 398, "prot": 28.2, "carb":  0.5, "grassi":32.0},
    "yogurt":        {"kcal":  65, "prot":  3.9, "carb":  4.8, "grassi": 3.1},
    # Uova
    "uov":           {"kcal": 143, "prot": 12.4, "carb":  0.9, "grassi":10.6},
    "tuorlo":        {"kcal": 352, "prot": 15.5, "carb":  0.7, "grassi":31.0},
    "albume":        {"kcal":  52, "prot": 10.9, "carb":  0.7, "grassi": 0.2},
    # Dolcificanti
    "zucchero":      {"kcal": 387, "prot":  0.0, "carb": 99.9, "grassi": 0.0},
    "miele":         {"kcal": 304, "prot":  0.4, "carb": 80.0, "grassi": 0.0},
    "sciroppo":      {"kcal": 256, "prot":  0.0, "carb": 67.0, "grassi": 0.0},
    # Oli e grassi
    "olio":          {"kcal": 884, "prot":  0.0, "carb":  0.0, "grassi":100.},
    "lardo":         {"kcal": 820, "prot":  2.2, "carb":  0.0, "grassi":90.0},
    "strutto":       {"kcal": 892, "prot":  0.0, "carb":  0.0, "grassi":99.5},
    # Carni
    "carne":         {"kcal": 215, "prot": 19.0, "carb":  0.0, "grassi":14.5},
    "maiale":        {"kcal": 215, "prot": 19.0, "carb":  0.0, "grassi":14.5},
    "manzo":         {"kcal": 190, "prot": 21.0, "carb":  0.0, "grassi":11.5},
    "pollo":         {"kcal": 190, "prot": 22.0, "carb":  0.0, "grassi":11.0},
    "salsiccia":     {"kcal": 285, "prot": 15.0, "carb":  3.0, "grassi":24.0},
    "salame":        {"kcal": 430, "prot": 25.0, "carb":  0.0, "grassi":37.0},
    "prosciutto":    {"kcal": 268, "prot": 25.7, "carb":  0.5, "grassi":17.8},
    "pancetta":      {"kcal": 358, "prot": 17.5, "carb":  0.0, "grassi":31.5},
    "ragù":          {"kcal": 180, "prot": 14.0, "carb":  5.0, "grassi":11.0},
    # Pesce
    "baccal":        {"kcal": 105, "prot": 24.0, "carb":  0.0, "grassi": 0.5},
    "polpo":         {"kcal":  82, "prot": 14.9, "carb":  2.2, "grassi": 1.0},
    "cozze":         {"kcal":  84, "prot": 12.0, "carb":  3.3, "grassi": 2.4},
    "vongole":       {"kcal":  72, "prot": 10.0, "carb":  2.5, "grassi": 1.6},
    "alici":         {"kcal":  96, "prot": 17.0, "carb":  0.0, "grassi": 3.5},
    "gamberi":       {"kcal":  71, "prot": 13.6, "carb":  0.5, "grassi": 1.1},
    "pesce":         {"kcal": 120, "prot": 20.0, "carb":  0.0, "grassi": 4.0},
    # Verdure
    "pomodoro":      {"kcal":  20, "prot":  1.0, "carb":  3.5, "grassi": 0.2},
    "cipolla":       {"kcal":  40, "prot":  1.0, "carb":  9.0, "grassi": 0.1},
    "aglio":         {"kcal": 149, "prot":  6.4, "carb": 33.0, "grassi": 0.5},
    "patate":        {"kcal":  86, "prot":  2.0, "carb": 19.0, "grassi": 0.1},
    "peperone":      {"kcal":  31, "prot":  1.0, "carb":  6.6, "grassi": 0.4},
    "melanzane":     {"kcal":  25, "prot":  1.1, "carb":  5.1, "grassi": 0.1},
    "zucchine":      {"kcal":  17, "prot":  1.3, "carb":  2.6, "grassi": 0.1},
    "carciofi":      {"kcal":  50, "prot":  3.5, "carb":  7.5, "grassi": 0.2},
    "spinaci":       {"kcal":  31, "prot":  3.4, "carb":  3.5, "grassi": 0.3},
    "friariell":     {"kcal":  35, "prot":  2.9, "carb":  3.1, "grassi": 0.7},
    "insalata":      {"kcal":  15, "prot":  1.4, "carb":  2.0, "grassi": 0.2},
    "verdure":       {"kcal":  30, "prot":  2.0, "carb":  5.0, "grassi": 0.2},
    # Frutta
    "limone":        {"kcal":  29, "prot":  1.1, "carb":  6.5, "grassi": 0.6},
    "arancia":       {"kcal":  47, "prot":  0.9, "carb": 12.0, "grassi": 0.1},
    "uvetta":        {"kcal": 290, "prot":  2.5, "carb": 76.0, "grassi": 0.5},
    # Frutta secca
    "mandorla":      {"kcal": 604, "prot": 22.0, "carb": 19.0, "grassi":53.0},
    "pistacchio":    {"kcal": 562, "prot": 20.0, "carb": 27.0, "grassi":45.0},
    "nocciola":      {"kcal": 628, "prot": 15.0, "carb": 17.0, "grassi":61.0},
    "pinoli":        {"kcal": 688, "prot": 14.0, "carb": 13.0, "grassi":68.0},
    "noci":          {"kcal": 654, "prot": 15.0, "carb": 14.0, "grassi":65.0},
    # Cioccolato
    "cioccolat":     {"kcal": 545, "prot":  7.0, "carb": 56.0, "grassi":34.0},
    "cacao":         {"kcal": 384, "prot": 20.0, "carb": 46.0, "grassi":20.0},
    # Altro
    "acqua":         {"kcal":   0, "prot":  0.0, "carb":  0.0, "grassi": 0.0},
    "sale":          {"kcal":   0, "prot":  0.0, "carb":  0.0, "grassi": 0.0},
    "aceto":         {"kcal":  25, "prot":  0.0, "carb":  5.0, "grassi": 0.0},
    "vino":          {"kcal":  85, "prot":  0.1, "carb":  2.6, "grassi": 0.0},
    "brodo":         {"kcal":  12, "prot":  1.0, "carb":  0.8, "grassi": 0.4},
    "passata":       {"kcal":  28, "prot":  1.5, "carb":  5.8, "grassi": 0.2},
    "concentrato":   {"kcal":  82, "prot":  4.6, "carb": 16.0, "grassi": 0.5},
    "cannella":      {"kcal": 261, "prot":  4.0, "carb": 68.0, "grassi": 3.2},
    "vaniglia":      {"kcal": 288, "prot":  0.1, "carb": 13.0, "grassi": 0.1},
    "rum":           {"kcal": 230, "prot":  0.0, "carb":  0.0, "grassi": 0.0},
    "zafferano":     {"kcal": 310, "prot": 11.4, "carb": 65.4, "grassi": 5.9},
}

_UNITA_A_GRAMMI = {
    "g": 1.0, "gr": 1.0, "kg": 1000.0,
    "ml": 1.0, "l": 1000.0, "cl": 10.0,
    "pz": 50.0, "n": 50.0, "uova": 55.0, "fette": 30.0,
    "cucchiaio": 15.0, "cucchiai": 15.0,
    "cucchiaino": 5.0, "cucchiaini": 5.0,
    "spicchio": 8.0, "rametto": 5.0,
}


def _cerca_nutri(nome: str) -> dict | None:
    n = nome.lower().strip()
    for chiave, valori in _NUTRI.items():
        if chiave in n:
            return valori
    return None


def _converti_grammi(quantita: float, unita: str) -> float:
    u = (unita or "g").lower().strip()
    return quantita * _UNITA_A_GRAMMI.get(u, 1.0)


@router.get("/ricette/{ricetta_id}/nutrizionali")
async def get_nutrizionali(ricetta_id: str):
    """
    Calcola valori nutrizionali per porzione della ricetta.
    Usa una tabella di stima per 100g degli ingredienti comuni.
    Non è un'analisi da laboratorio — è una stima ragionevole.
    """
    r = await db.ricette.find_one({"id": ricetta_id}, {"_id": 0})
    if not r:
        raise HTTPException(404, "Ricetta non trovata")

    porzioni = float(r.get("porzioni", 1) or 1)
    ingredienti = r.get("ingredienti_dettaglio") or []

    tot = {"kcal": 0.0, "prot": 0.0, "carb": 0.0, "grassi": 0.0}
    copertura = 0
    ingredienti_calcolati = []

    for ing in ingredienti:
        nome = ing.get("nome", "")
        q_raw = float(ing.get("quantita") or 0)
        unita = ing.get("unita_misura") or ing.get("unita") or "g"
        if q_raw <= 0:
            continue
        grammi = _converti_grammi(q_raw, unita)
        nutri = _cerca_nutri(nome)
        if nutri:
            fattore = grammi / 100.0
            for k in tot:
                tot[k] += nutri[k] * fattore
            copertura += 1
            ingredienti_calcolati.append({
                "nome": nome,
                "grammi": round(grammi, 1),
                "kcal": round(nutri["kcal"] * fattore, 1),
            })

    per_porzione = {k: round(v / porzioni, 1) for k, v in tot.items()}

    return {
        "ricetta_id": ricetta_id,
        "ricetta_nome": r.get("nome", ""),
        "porzioni": porzioni,
        "ingredienti_coperti": copertura,
        "ingredienti_totali": len(ingredienti),
        "per_porzione": per_porzione,
        "totale_ricetta": {k: round(v, 1) for k, v in tot.items()},
        "dettaglio": ingredienti_calcolati,
        "nota": "Valori stimati non certificati — Fonte: tabelle nutrizionali standard",
    }
