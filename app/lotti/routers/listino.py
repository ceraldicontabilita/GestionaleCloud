"""
listino.py — Listino Prezzi Merci
Schema semplice: ogni prodotto ha i prezzi di tutti i fornitori embedded.
  { nome, categoria, conf, prezzi: {fornitore: prezzo}, miglior_fornitore }

Sync automatico da lotti_fornitori (import XML) → aggiorna prezzi.
"""

import re
import logging
_LOG_INIT = logging.getLogger("uvicorn.error")
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict
from fastapi import Depends, APIRouter, HTTPException
from pydantic import BaseModel
from app.lotti.db import database as db
from app.lotti.routers.classificatore_alimenti import e_merce_alimentare as _e_merce
from app.lotti.azienda import get_azienda, riga_dettaglio
import io
from fastapi.responses import StreamingResponse
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
# 25/07/2026 (TRANCHE 2 sicurezza): gli import e le sincronizzazioni di
# MASSA riscrivono cataloghi e listini interi. Riservati all'amministratore.
from app.lotti.auth import require_admin

router = APIRouter(prefix="/listino", tags=["Listino Prezzi"])


async def _fornitori_esclusi() -> set:
    """Nomi (lower/strip) dei fornitori marcati escluso:True — il listino
    di vendita non deve mai mostrare i loro prodotti (es. ferramenta,
    manutenzione, servizi non alimentari)."""
    docs = await db.fornitori.find({"escluso": True}, {"_id": 0, "nome": 1}).to_list(2000)
    return {(d.get("nome") or "").strip().lower() for d in docs if d.get("nome")}

# ── Categorie default (ereditato da listino-prezzi-merci) ─────────────────────
CATEGORIE_ORDINATE = [
    "ACQUA",
    "BIBITE",
    "BIRRE",
    "VINO",
    "PROSECCO",
    "LIQUORI",
    "AMARI",
    "SCIROPPI",
    "SUCCHI",
    "DOLCIFICANTI",
    "CAFFE",
    "FARINE",
    "LATTICINI",
    "UOVA",
    "GRASSI",
    "ZUCCHERI",
    "CREME",
    "CIOCCOLATO",
    "LIEVITI",
    "FRUTTA_SECCA",
    "MONOUSO",
    "IMBALLAGGI",
    "PULIZIA",
    "ATTREZZATURE",
    "ALTRO",
]

# Mappa descrizione → categoria (per il sync da XML)
_CAT_KEYWORDS: list[tuple[str, list[str]]] = [
    ("ACQUA", ["acqua"]),
    ("BIRRE", ["birra", "heineken", "moretti", "peroni", "carlsberg"]),
    ("VINO", ["vino rosso", "vino bianco", "vino", "chianti"]),
    ("PROSECCO", ["prosecco", "spumante", "champagne"]),
    (
        "LIQUORI",
        [
            "vodka",
            "gin",
            "rum",
            "whisky",
            "tequila",
            "grappa",
            "passoa",
            "aperol",
            "campari",
            "punt",
        ],
    ),
    ("AMARI", ["amaro", "averna", "montenegro", "fernet", "jefferson"]),
    # ZUCCHERI PRIMA di SCIROPPI: "sciroppo di glucosio" è pasticceria,
    # non una bibita (segnalato da Enzo 02/07/2026)
    ("ZUCCHERI", ["glucosio", "destrosio", "fruttosio", "maltosio"]),
    # MONOUSO PRIMA di CAFFE: "CUCCHIAINO CAFFE'" è monouso, non caffè
    ("MONOUSO", ["bicchier", "piatto", "posate", "cannucce", "tovagliolo",
                  "tovagliett", "cucchia", "palett", "stuzzicadent", "agitator"]),
    ("SCIROPPI", ["sciroppo"]),
    ("SUCCHI", ["succo", "estathe", "yoga", "ace"]),
    (
        "BIBITE",
        [
            "coca",
            "fanta",
            "sprite",
            "sanbitter",
            "tonica",
            "schweppes",
            "san pellegrino",
            "lete",
            "ferrarelle",
            "sorgesana",
            "natia",
        ],
    ),
    ("DOLCIFICANTI", ["dolcific", "stevia", "zuccher", "slim"]),
    ("CAFFE", ["caffe", "caffè", "kimbo", "lavazza", "illy", "espresso"]),
    ("FARINE", ["farin", "semola", "grano", "frumento", "cereali", "amido"]),
    ("LATTICINI", ["latte", "burro", "panna", "formaggio", "mozzarella", "ricotta", "mascarpone"]),
    ("UOVA", ["uov", "tuorlo", "albume"]),
    ("GRASSI", ["olio", "margarina", "strutto"]),
    (
        "CREME",
        ["crema", "pasta pistacchi", "nuppy", "ripieno", "farcia", "confettura", "marmellata"],
    ),
    ("CIOCCOLATO", ["cioccolato", "cacao", "glassa", "copertura", "fondente"]),
    ("LIEVITI", ["lievito", "bicarbonato"]),
    ("FRUTTA_SECCA", ["nocciola", "mandorla", "pistacchio", "noce", "pinoli", "uvetta", "canditi"]),
    ("IMBALLAGGI", ["vaschett", "scatol", "sacchetto", "pellicola", "carta forno", "cartone"]),
    ("PULIZIA", ["detersivo", "detergente", "sanificante", "disinfettante", "candeggina"]),
    ("ATTREZZATURE", ["calice", "vetreria", "bicchiere cristallo", "shaker", "misurino"]),
]


def _categoria(nome: str) -> str:
    n = nome.lower()
    for cat, kws in _CAT_KEYWORDS:
        if any(k in n for k in kws):
            return cat
    return "ALTRO"


def _norm(nome: str) -> str:
    # "*" a inizio riga è un marcatore/nota di alcuni fornitori in fattura
    # (non fa parte del nome prodotto): senza toglierlo crea un doppione
    # separato dello stesso prodotto invece di aggiornare quello esistente.
    n = re.sub(r"^\*+\s*", "", nome.strip())
    return re.sub(r"\s+", " ", n.upper())


def _prezzo_affidabile(ps: list) -> float:
    """Prezzo più basso tra quelli raccolti per un fornitore, scartando gli
    outlier implausibili (vedi utils.valore_affidabile, il motore unico anti-
    outlier prezzi condiviso da tutto il progetto)."""
    from app.lotti.routers.utils import valore_affidabile
    scelto = valore_affidabile(ps)
    return round(scelto, 4) if scelto is not None else 0.0


def _best_fornitore(prezzi: dict) -> str:
    if not prezzi:
        return ""
    return min(prezzi.items(), key=lambda x: x[1])[0]


def _best_fornitore_affidabile(prezzi: dict) -> str:
    """Come _best_fornitore, ma con la stessa protezione anti-outlier di
    _prezzo_affidabile (utils.valore_affidabile): qui `prezzi` ha UN prezzo
    per fornitore (l'ultima fattura vista), quindi non c'è uno storico da cui
    calcolare la mediana per fornitore — si usa invece la mediana TRA i
    fornitori come riferimento per scartare un minimo implausibile."""
    from app.lotti.routers.utils import valore_affidabile
    if not prezzi:
        return ""
    scelto = valore_affidabile(list(prezzi.items()), chiave=1)
    return scelto[0] if scelto else ""


# ── Modelli ────────────────────────────────────────────────────────────────────
class ProdottoCreate(BaseModel):
    nome: str
    categoria: str = "ALTRO"
    conf: str = "PZ"
    prezzi: Dict[str, float] = {}
    custom: bool = False


class ProdottoUpdate(BaseModel):
    nome: Optional[str] = None
    categoria: Optional[str] = None
    conf: Optional[str] = None
    prezzi: Optional[Dict[str, float]] = None
    preferito: Optional[bool] = None
    custom: Optional[bool] = None


# ── GET prodotti ───────────────────────────────────────────────────────────────
@router.get("/prodotti")
async def get_prodotti(
    categoria: Optional[str] = None,
    search: Optional[str] = None,
    preferiti: bool = False,
):
    query: dict = {}
    if categoria and categoria not in ("Tutti", "tutti", ""):
        query["categoria"] = categoria
    if preferiti:
        query["preferito"] = True
    if search:
        query["nome"] = {"$regex": re.escape(search), "$options": "i"}

    docs = await db.listino_prodotti.find(query, {"_id": 0}).sort("nome", 1).to_list(2000)
    return [d for d in docs if _e_merce(d.get("nome", ""), d.get("categoria", ""))]


# ── GET categorie ──────────────────────────────────────────────────────────────
@router.get("/categorie")
async def get_categorie():
    presenti = await db.listino_prodotti.distinct("categoria")
    ordinate = [c for c in CATEGORIE_ORDINATE if c in presenti]
    extra = [c for c in presenti if c not in ordinate]
    return {"categorie": ordinate + sorted(extra)}


# ── POST crea prodotto ─────────────────────────────────────────────────────────
@router.post("/prodotti")
async def crea_prodotto(p: ProdottoCreate):
    nome_norm = _norm(p.nome)
    exists = await db.listino_prodotti.find_one({"nome": nome_norm}, {"_id": 0, "id": 1})
    if exists:
        raise HTTPException(409, f"Prodotto '{nome_norm}' già esistente")
    doc = {
        "id": str(uuid.uuid4()),
        "nome": nome_norm,
        "categoria": p.categoria.upper(),
        "conf": p.conf.upper(),
        "prezzi": p.prezzi,
        "miglior_fornitore": _best_fornitore(p.prezzi),
        "preferito": False,
        "custom": p.custom,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.listino_prodotti.insert_one({**doc})
    return doc


# ── PUT aggiorna prodotto ──────────────────────────────────────────────────────
@router.put("/prodotti/{prodotto_id}")
async def aggiorna_prodotto(prodotto_id: str, p: ProdottoUpdate):
    upd: dict = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if p.nome is not None:
        upd["nome"] = _norm(p.nome)
    if p.categoria is not None:
        upd["categoria"] = p.categoria.upper()
    if p.conf is not None:
        upd["conf"] = p.conf.upper()
    if p.preferito is not None:
        upd["preferito"] = p.preferito
    if p.custom is not None:
        upd["custom"] = p.custom
    if p.prezzi is not None:
        upd["prezzi"] = p.prezzi
        upd["miglior_fornitore"] = _best_fornitore(p.prezzi)
    r = await db.listino_prodotti.update_one({"id": prodotto_id}, {"$set": upd})
    if r.matched_count == 0:
        raise HTTPException(404, "Prodotto non trovato")
    doc = await db.listino_prodotti.find_one({"id": prodotto_id}, {"_id": 0})
    return doc


# ── PATCH aggiorna prezzo singolo fornitore ────────────────────────────────────
@router.patch("/prodotti/{prodotto_id}/prezzo")
async def aggiorna_prezzo(prodotto_id: str, fornitore: str, prezzo: float):
    doc = await db.listino_prodotti.find_one({"id": prodotto_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Prodotto non trovato")
    prezzi = dict(doc.get("prezzi", {}))
    if prezzo <= 0:
        prezzi.pop(fornitore, None)
    else:
        prezzi[fornitore] = round(prezzo, 4)
    await db.listino_prodotti.update_one(
        {"id": prodotto_id},
        {
            "$set": {
                "prezzi": prezzi,
                "miglior_fornitore": _best_fornitore(prezzi),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        },
    )
    doc = await db.listino_prodotti.find_one({"id": prodotto_id}, {"_id": 0})
    return doc


# ── PATCH toggle preferito ────────────────────────────────────────────────────
@router.patch("/prodotti/{prodotto_id}/preferito")
async def toggle_preferito(prodotto_id: str):
    doc = await db.listino_prodotti.find_one({"id": prodotto_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Prodotto non trovato")
    nuovo = not doc.get("preferito", False)
    await db.listino_prodotti.update_one({"id": prodotto_id}, {"$set": {"preferito": nuovo}})
    return {"preferito": nuovo}


# ── DELETE prodotto ────────────────────────────────────────────────────────────
@router.delete("/prodotti/{prodotto_id}")
async def elimina_prodotto(prodotto_id: str):
    r = await db.listino_prodotti.delete_one({"id": prodotto_id})
    if r.deleted_count == 0:
        raise HTTPException(404, "Prodotto non trovato")
    return {"ok": True}


# ── POST sync da fatture XML (lotti_fornitori) ─────────────────────────────────
@router.post("/sync-da-fatture")
async def sync_da_fatture(_admin=Depends(require_admin)):
    """
    Legge tutti i lotti_fornitori con prezzo > 0 e costruisce/aggiorna
    listino_prodotti con i prezzi per fornitore.
    """
    lotti = await db.lotti_fornitori.find(
        {"prezzo_unitario": {"$gt": 0}},
        {"_id": 0, "prodotto_nome": 1, "fornitore": 1, "prezzo_unitario": 1, "unita_misura": 1},
    ).to_list(50000)
    esclusi = await _fornitori_esclusi()

    # Raggruppa: nome_norm → {fornitore: [prezzi]}
    gruppi: dict[str, dict] = {}
    for lotto in lotti:
        nome_raw = lotto.get("prodotto_nome") or ""
        nome = _norm(nome_raw)
        if not nome or len(nome) < 3:
            continue
        if not _e_merce(nome_raw):
            continue  # candeggina, cavi, servizi... il listino e' solo vendita alimenti
        fornitore = (lotto.get("fornitore") or "").strip()
        if fornitore.lower() in esclusi:
            continue
        prezzo = float(lotto.get("prezzo_unitario") or 0)
        if prezzo <= 0 or not fornitore:
            continue
        if nome not in gruppi:
            gruppi[nome] = {
                "conf": (lotto.get("unita_misura") or "PZ").upper(),
                "prezzi_lista": {},  # fornitore → [prezzi]
            }
        gruppi[nome]["prezzi_lista"].setdefault(fornitore, []).append(prezzo)

    inseriti = 0
    aggiornati = 0

    for nome, info in gruppi.items():
        # Prezzo più basso per fornitore (miglior offerta storica), scartando
        # gli outlier implausibili — vedi _prezzo_affidabile.
        prezzi = {forn: _prezzo_affidabile(ps) for forn, ps in info["prezzi_lista"].items()}
        categoria = _categoria(nome)
        miglior = _best_fornitore(prezzi)

        exists = await db.listino_prodotti.find_one(
            {"nome": nome}, {"_id": 0, "id": 1, "prezzi": 1}
        )
        if exists:
            # Merge prezzi: non sovrascrive prezzi inseriti manualmente se non ci sono aggiornamenti
            prezzi_attuali = dict(exists.get("prezzi", {}))
            prezzi_attuali.update(prezzi)  # XML aggiorna/aggiunge
            await db.listino_prodotti.update_one(
                {"nome": nome},
                {
                    "$set": {
                        "prezzi": prezzi_attuali,
                        "miglior_fornitore": _best_fornitore(prezzi_attuali),
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                },
            )
            aggiornati += 1
        else:
            await db.listino_prodotti.insert_one(
                {
                    "id": str(uuid.uuid4()),
                    "nome": nome,
                    "categoria": categoria,
                    "conf": info["conf"],
                    "prezzi": prezzi,
                    "miglior_fornitore": miglior,
                    "preferito": False,
                    "custom": False,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            inseriti += 1

    totale = await db.listino_prodotti.count_documents({})
    # Pulizia: rimuove dal listino le voci non-alimentari entrate dai sync precedenti.
    tutti = await db.listino_prodotti.find({}, {"_id": 0, "id": 1, "nome": 1, "categoria": 1}).to_list(5000)
    da_togliere = [d["id"] for d in tutti if d.get("id") and not _e_merce(d.get("nome", ""), d.get("categoria", ""))]
    rimossi = 0
    if da_togliere:
        res = await db.listino_prodotti.delete_many({"id": {"$in": da_togliere}})
        rimossi = res.deleted_count
        totale = await db.listino_prodotti.count_documents({})
    return {
        "ok": True,
        "inseriti": inseriti,
        "aggiornati": aggiornati,
        "rimossi_non_alimentari": rimossi,
        "totale": totale,
        "message": f"Sync completato: {inseriti} nuovi, {aggiornati} aggiornati. Totale: {totale} prodotti nel listino.",
    }


# ── GET report spesa ──────────────────────────────────────────────────────────
@router.get("/report")
async def report_spesa():
    """Spesa totale per fornitore estratta da ordini_fornitori."""
    now = datetime.now(timezone.utc)
    mese = now.strftime("%m/%Y")

    ordini = await db.ordini_fornitori.find(
        {"stato": {"$in": ["inviato", "inviato_fornitori"]}},
        {"_id": 0, "fornitore": 1, "importo_totale": 1, "created_at": 1, "prodotti": 1},
    ).to_list(5000)

    per_fornitore: dict[str, float] = {}
    mese_totale = 0.0
    mese_count = 0

    for o in ordini:
        forn = o.get("fornitore", "—")
        tot = float(o.get("importo_totale") or 0)
        ca = o.get("created_at", "")
        per_fornitore[forn] = per_fornitore.get(forn, 0) + tot
        try:
            if mese in ca or (
                ca and datetime.fromisoformat(ca.replace("Z", "")).strftime("%m/%Y") == mese
            ):
                mese_totale += tot
                mese_count += 1
        except Exception:
            _LOG_INIT.debug("[listino] errore non bloccante ignorato")

    # Top 10 prodotti per spesa (da lotti_fornitori)
    pipeline = [
        {"$match": {"prezzo_unitario": {"$gt": 0}}},
        {
            "$group": {
                "_id": "$prodotto_nome",
                "spesa_totale": {
                    "$sum": {"$multiply": ["$quantita_acquistata", "$prezzo_unitario"]}
                },
                "fornitore": {"$first": "$fornitore"},
            }
        },
        {"$sort": {"spesa_totale": -1}},
        {"$limit": 10},
    ]
    top_raw = await db.lotti_fornitori.aggregate(pipeline).to_list(10)
    top_prodotti = [
        {"nome": t["_id"], "spesa": round(t["spesa_totale"], 2), "fornitore": t["fornitore"]}
        for t in top_raw
    ]

    return {
        "mese": mese,
        "mese_totale": round(mese_totale, 2),
        "mese_ordini": mese_count,
        "per_fornitore": {
            k: round(v, 2) for k, v in sorted(per_fornitore.items(), key=lambda x: -x[1])
        },
        "top_prodotti": top_prodotti,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Listino scontato → PDF professionale (dati Ceraldi Group) + invio email
# ══════════════════════════════════════════════════════════════════════════════
_VIOLA = colors.HexColor("#5b7a6b")  # salvia (nome storico)
_NAVY = colors.HexColor("#3f5a4e")   # verde scuro brand

def _prezzo_base(prod: dict, fonte: Optional[str]) -> float:
    prezzi = prod.get("prezzi") or {}
    if fonte and fonte not in ("best", "migliore", ""):
        try:
            return float(prezzi.get(fonte) or 0)
        except Exception:
            return 0.0
    mf = prod.get("miglior_fornitore")
    if mf and prezzi.get(mf) is not None:
        return float(prezzi[mf])
    vals = [float(v) for v in prezzi.values() if v]
    return min(vals) if vals else 0.0


def _calc_prezzo(base: float, sconto: float, con_iva: bool, iva: float) -> float:
    p = base * (1 - (sconto or 0) / 100.0)
    if con_iva:
        p = p * (1 + (iva or 22) / 100.0)
    return round(p, 2)


async def _prodotti_listino(categoria: Optional[str] = None):
    query: dict = {}
    if categoria and categoria not in ("Tutti", "tutti", ""):
        query["categoria"] = categoria
    docs = await db.listino_prodotti.find(query, {"_id": 0}).sort("nome", 1).to_list(3000)
    return [d for d in docs if (d.get("prezzi") or {})]


def _genera_pdf_listino(prodotti, sconto, con_iva, iva, fonte, destinatario="", azienda=None):
    az = azienda or {}
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=1.3 * cm, bottomMargin=1.1 * cm,
                            leftMargin=1.4 * cm, rightMargin=1.4 * cm)
    ss = getSampleStyleSheet()
    H = ParagraphStyle("H", parent=ss["Title"], textColor=_NAVY, fontSize=19, spaceAfter=2, alignment=0)
    sub = ParagraphStyle("sub", parent=ss["Normal"], textColor=colors.HexColor("#64748b"), fontSize=9)
    small = ParagraphStyle("small", parent=ss["Normal"], fontSize=7.5, textColor=colors.HexColor("#94a3b8"))
    el = []
    el.append(Paragraph(f"<b>{az.get('ragione_sociale', 'Ceraldi Group S.r.l.')}</b>", H))
    riga2 = riga_dettaglio(az)
    if riga2:
        el.append(Paragraph(riga2, sub))
    el.append(Spacer(1, 6))
    el.append(HRFlowable(width="100%", thickness=2, color=_VIOLA))
    el.append(Spacer(1, 8))
    el.append(Paragraph("Listino prezzi", ParagraphStyle("t2", parent=ss["Heading2"], textColor=_VIOLA, spaceAfter=2)))
    info = [f"Data: {datetime.now().strftime('%d/%m/%Y')}"]
    if destinatario:
        info.append(f"Spett.le {destinatario}")
    if sconto:
        info.append(f"Sconto {int(sconto) if float(sconto).is_integer() else sconto}%")
    info.append("Prezzi IVA inclusa" if con_iva else "Prezzi IVA esclusa")
    el.append(Paragraph(" — ".join(info), sub))
    el.append(Spacer(1, 10))
    data = [["Prodotto", "Conf.", "Prezzo €"]]
    for p in prodotti:
        base = _prezzo_base(p, fonte)
        if base <= 0:
            continue
        prezzo = _calc_prezzo(base, sconto, con_iva, iva)
        data.append([p.get("nome", ""), (p.get("conf", "") or ""), f"{prezzo:.2f}"])
    tbl = Table(data, colWidths=[11.5 * cm, 2.4 * cm, 3.0 * cm], repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("ALIGN", (2, 1), (2, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f6f4fb")]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e6e0f0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    el.append(tbl)
    el.append(Spacer(1, 10))
    el.append(Paragraph(
        f"Generato il {datetime.now().strftime('%d/%m/%Y %H:%M')} — {len(data) - 1} prodotti. "
        f"Prezzi indicativi salvo conferma.", small))
    doc.build(el)
    return buf.getvalue()


class GenPdfReq(BaseModel):
    sconto: float = 0
    con_iva: bool = False
    iva: float = 22
    fonte: Optional[str] = "best"
    categoria: Optional[str] = None


class InviaListinoReq(GenPdfReq):
    destinatari: list = []   # [{"nome","email"}] oppure ["email", ...]


@router.post("/genera-pdf")
async def genera_pdf(req: GenPdfReq):
    prodotti = await _prodotti_listino(req.categoria)
    if not prodotti:
        raise HTTPException(400, "Nessun prodotto con prezzo nel listino")
    azienda = await get_azienda()
    pdf = _genera_pdf_listino(prodotti, req.sconto, req.con_iva, req.iva, req.fonte, azienda=azienda)
    return StreamingResponse(io.BytesIO(pdf), media_type="application/pdf",
                             headers={"Content-Disposition": 'attachment; filename="listino_ceraldi.pdf"'})


@router.post("/invia")
async def invia_listino(req: InviaListinoReq):
    """Invio email rimosso: il listino va scaricato come PDF (GET .../listino/pdf)
    e inviato manualmente. L'endpoint resta per compatibilità del frontend."""
    prodotti = await _prodotti_listino(req.categoria)
    if not prodotti:
        raise HTTPException(400, "Nessun prodotto con prezzo nel listino")
    if not req.destinatari:
        raise HTTPException(400, "Nessun destinatario selezionato")
    falliti = [{"nome": (d.get("nome") if isinstance(d, dict) else "") or
                ((d.get("email") if isinstance(d, dict) else d) or ""),
                "errore": "Invio email rimosso: scarica il PDF del listino e invia a mano"}
               for d in req.destinatari]
    return {"inviati": [], "falliti": falliti,
            "prodotti": len([p for p in prodotti if _prezzo_base(p, req.fonte) > 0])}


# ══════════════════════════════════════════════════════════════════════════════
# LISTINI CALCOLATI — best / media / ultimo prezzo, con filtro e sconto
# Prezzo preso così com'è in fattura (per cassa/pezzo come registrato).
# ══════════════════════════════════════════════════════════════════════════════
def _parse_data_fatt(s):
    s = (s or "").strip()
    for f in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, f)
        except Exception:
            pass
    return None


def _norm_desc(s):
    s = (s or "").upper().lstrip("* ")
    s = re.sub(r"^\d{5,}\s*", "", s)
    s = re.sub(r"\s*\|.*$", "", s)
    s = re.sub(r"[^A-Z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


_RX_ANALC = re.compile(r"0[,.]0|analcolic|senza alcol|tourtel|forst 0", re.I)


async def _calcola_righe(modo, fornitore, categoria, prodotto, sconto, analcoliche=None):
    """Aggrega le righe-fattura per prodotto e calcola il prezzo secondo `modo`.
    Filtro: uno tra fornitore / categoria / prodotto (anche combinabili)."""
    cat_map = {}
    async for d in db.listino_prodotti.find({}, {"_id": 0, "nome": 1, "categoria": 1}):
        cat_map[_norm_desc(d.get("nome", ""))] = d.get("categoria", "")
    catU = categoria.upper() if categoria else None
    prodN = _norm_desc(prodotto) if prodotto else None
    fornL = fornitore.lower() if fornitore else None

    agg = {}
    # Righe amministrative (spese bolli, trasporti, storni...) fuori dal listino:
    # stessi filtri ufficiali del catalogo (visto live: "SPESE BOLLI" nel listino Kimbo).
    from app.lotti.routers.prodotti_master import _RX_NON_ORDINABILI
    from app.lotti.routers.classificatore_alimenti import e_servizio
    rx_junk = re.compile(_RX_NON_ORDINABILI, re.IGNORECASE)
    esclusi = await _fornitori_esclusi()

    async for f in db.fatture.find({}, {"_id": 0, "fornitore": 1, "data_fattura": 1, "prodotti": 1}):
        forn = f.get("fornitore", "") or ""
        if forn.strip().lower() in esclusi:
            continue
        if fornL and fornL not in forn.lower():
            continue
        dt = _parse_data_fatt(f.get("data_fattura"))
        for p in (f.get("prodotti") or []):
            desc = p.get("descrizione", "")
            key = _norm_desc(desc)
            if not key:
                continue
            if rx_junk.search(desc) or e_servizio(desc):
                continue
            if prodN and prodN not in key:
                continue
            cat = cat_map.get(key, "")
            if catU:
                if (cat or "").upper() != catU:
                    continue
                if analcoliche is True and not _RX_ANALC.search(desc):
                    continue
                if analcoliche is False and _RX_ANALC.search(desc):
                    continue
            try:
                pr = float(str(p.get("prezzo", "")).replace(",", "."))
            except Exception:
                continue
            if pr <= 0:
                continue
            a = agg.setdefault(key, {"nome": desc.strip(), "dated": [], "cat": cat})
            a["dated"].append((dt, pr, forn))

    fac = 1 - (sconto or 0) / 100.0
    righe = []
    for key, a in agg.items():
        prezzi = [x[1] for x in a["dated"]]
        if not prezzi:
            continue
        dd = [x for x in a["dated"] if x[0]]
        ult = max(dd, key=lambda x: x[0]) if dd else a["dated"][-1]
        if modo == "best":
            # Stessa protezione anti-outlier di sync_da_fatture: un min() alla
            # cieca qui riproporrebbe lo stesso caso "Birra Corona 0,37€" nella
            # sezione Genera&Esporta (modo=best), che aggrega gli stessi prezzi
            # storici da fattura ma con una pipeline separata.
            base = _prezzo_affidabile(prezzi); data = ""
        elif modo == "media":
            base = sum(prezzi) / len(prezzi); data = ""
        else:
            base = ult[1]; data = ult[0].strftime("%d/%m/%Y") if ult[0] else ""
        righe.append({
            "nome": a["nome"], "categoria": a["cat"], "fornitore": ult[2],
            "prezzo": round(base * fac, 2), "prezzo_pieno": round(base, 2),
            "data_ultimo": ult[0].strftime("%d/%m/%Y") if ult[0] else "",
            "data": data, "acquisti": len(prezzi),
        })
    righe.sort(key=lambda r: ((r["categoria"] or "~"), r["nome"]))
    return righe


@router.get("/calcola")
async def calcola_listino(
    modo: str = "ultimo",
    fornitore: Optional[str] = None,
    categoria: Optional[str] = None,
    prodotto: Optional[str] = None,
    sconto: float = 0,
    analcoliche: Optional[bool] = None,
):
    if modo not in ("best", "media", "ultimo"):
        raise HTTPException(400, "modo deve essere best | media | ultimo")
    righe = await _calcola_righe(modo, fornitore, categoria, prodotto, sconto, analcoliche)
    return {"modo": modo, "sconto": sconto, "totale": len(righe), "righe": righe}


@router.get("/fornitori-elenco")
async def fornitori_elenco():
    forn = await db.fatture.distinct("fornitore")
    esclusi = await _fornitori_esclusi()
    return {"fornitori": sorted([f for f in forn if f and f.strip().lower() not in esclusi])}


@router.get("/calcola-pdf")
async def calcola_listino_pdf(
    modo: str = "ultimo",
    fornitore: Optional[str] = None,
    categoria: Optional[str] = None,
    prodotto: Optional[str] = None,
    sconto: float = 0,
    analcoliche: Optional[bool] = None,
):
    if modo not in ("best", "media", "ultimo"):
        raise HTTPException(400, "modo deve essere best | media | ultimo")
    righe = await _calcola_righe(modo, fornitore, categoria, prodotto, sconto, analcoliche)
    modo_lbl = {"best": "Miglior prezzo", "media": "Media prezzi", "ultimo": "Ultimo prezzo"}[modo]
    filtro_lbl = []
    if categoria:
        filtro_lbl.append(f"categoria {categoria}" + (" analcoliche" if analcoliche else (" alcoliche" if analcoliche is False else "")))
    if fornitore:
        filtro_lbl.append(f"fornitore {fornitore}")
    if prodotto:
        filtro_lbl.append(f"prodotto '{prodotto}'")
    filtro_txt = " · ".join(filtro_lbl) if filtro_lbl else "tutti i prodotti"

    VIOLA = colors.HexColor("#5b7a6b"); NAVY = colors.HexColor("#3f5a4e")  # salvia/verde brand
    GRIGIO = colors.HexColor("#F3F0FB"); LINEA = colors.HexColor("#D9CFF2")
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=1.3 * cm, bottomMargin=1.3 * cm,
                            leftMargin=1.3 * cm, rightMargin=1.3 * cm, title="Listino prezzi")
    ss = getSampleStyleSheet()
    H = ParagraphStyle("H", parent=ss["Title"], textColor=NAVY, fontSize=17, spaceAfter=2, alignment=0)
    SUB = ParagraphStyle("SUB", parent=ss["Normal"], textColor=colors.HexColor("#6B6B6B"), fontSize=9)
    CELL = ParagraphStyle("CELL", parent=ss["Normal"], fontSize=8.3, leading=10, textColor=NAVY)
    CELLF = ParagraphStyle("CELLF", parent=ss["Normal"], fontSize=7.6, leading=9.4, textColor=colors.HexColor("#555555"))
    DT = ParagraphStyle("DT", parent=ss["Normal"], fontSize=8, leading=10, textColor=colors.HexColor("#444"), alignment=1)
    PRZ = ParagraphStyle("PRZ", parent=ss["Normal"], fontSize=8.6, leading=10, textColor=NAVY, alignment=2, fontName="Helvetica-Bold")
    HEADc = ParagraphStyle("HEADc", parent=CELL, fontName="Helvetica-Bold")
    sc_txt = f" · sconto {int(sconto)}%" if sconto else ""
    el = [Paragraph("CERALDI GROUP", ParagraphStyle("BR", parent=ss["Normal"], textColor=VIOLA, fontSize=9, fontName="Helvetica-Bold", spaceAfter=1)),
          Paragraph(f"Listino — {modo_lbl}", H),
          Paragraph(f"{datetime.now().strftime('%d/%m/%Y')} · {filtro_txt} · {len(righe)} prodotti{sc_txt}", SUB),
          Spacer(1, 0.25 * cm)]
    dati = [[Paragraph("Prodotto", HEADc), Paragraph("Fornitore", CELLF), Paragraph("Ult. acq.", DT), Paragraph("Prezzo", PRZ)]]
    for r in righe:
        prezzo = f"€ {r['prezzo']:.2f}"
        dati.append([Paragraph(r["nome"], CELL), Paragraph(r.get("fornitore", "") or "—", CELLF),
                     Paragraph(r.get("data_ultimo", "") or "—", DT), Paragraph(prezzo, PRZ)])
    t = Table(dati, colWidths=[9.4 * cm, 4.4 * cm, 2.2 * cm, 2.4 * cm], repeatRows=1)
    sty = [("LINEBELOW", (0, 0), (-1, -1), 0.4, LINEA), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
           ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
           ("LEFTPADDING", (0, 0), (-1, -1), 6), ("BACKGROUND", (0, 0), (-1, 0), GRIGIO)]
    for i in range(1, len(dati)):
        if i % 2 == 0:
            sty.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#FBFAFE")))
    t.setStyle(TableStyle(sty))
    el.append(t)
    doc.build(el)
    buf.seek(0)
    fname = f"listino_{modo}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
    return StreamingResponse(buf, media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="{fname}"'})
