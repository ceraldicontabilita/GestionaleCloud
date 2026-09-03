"""
Router per gestione fatture: CRUD, importa-xml, visualizza fattura HTML, backfill lotti.
"""

import re
import io
import zipfile
import uuid
import logging
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List

from fastapi import APIRouter, HTTPException, UploadFile, File, BackgroundTasks, Request, Depends, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from app.lotti.db import database as db
from app.lotti.auth import require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/fatture", tags=["Fatture"])

# MongoDB connection (stessa logica degli altri router)
# XSL per visualizzazione Assosoftware
XSL_PATH = Path(__file__).parent.parent / "static" / "FoglioStileAssoSoftware.xsl"


def set_database(database):
    """Permette override del db dall'esterno (compatibilità)."""
    global db
    db = database


# ──────────────────────────────────────────────────────────────────────────────
# ARCHIVIO OPERATIVO LOTTI
# GestionaleCloud e Lotti usano database separati. Il ponte in
# routers/gestionale_fatture.py riceve una proiezione read-only con source_id e
# source_hash; questo router applica poi la normale pipeline HACCP sul database
# di Lotti. Non esiste più alcuna dipendenza da una collection condivisa.
# ──────────────────────────────────────────────────────────────────────────────

# ── Modello ──────────────────────────────────────────────────────────────────
class FatturaImportata(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    fornitore: str
    piva: str = ""
    numero_fattura: str
    data_fattura: str
    prodotti: List[dict] = []
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── CRUD Base ────────────────────────────────────────────────────────────────
@router.get("/anni")
async def anni_fatture(escludi_fornitori: bool = True):
    """Anni disponibili (da data_fattura), decrescente — popola il selettore
    «anno» in cima alla lista. Richiesta Enzo 20/07/2026: leggere i dati per anno."""
    date = await db.fatture.distinct("data_fattura")
    anni = set()
    for s in date:
        s = (s or "").strip()
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
            try:
                anni.add(datetime.strptime(s, fmt).year)
                break
            except Exception:
                continue
    return sorted((a for a in anni if a >= 2000), reverse=True)


@router.get("")
async def get_fatture(escludi_fornitori: bool = True, limit: int = 2000, mesi: int = 6, anno: int = 0):
    """Lista le fatture importate, ordinate per data fattura decrescente.
    REGOLA: questa app è operativa e mostra al massimo gli ultimi `mesi` (default 6);
    lo storico completo resta nel database per il gestionale Cloud. mesi=0 = tutte.
    anno>0 = tutte le fatture di quell'anno (ignora `mesi`); il filtro sull'anno è
    applicato anche in $match sul DB così lo storico grande non viene troncato."""
    nomi_esclusi = set()
    if escludi_fornitori:
        fornitori_esclusi_docs = await db.fornitori.find({"escluso": True}, {"nome": 1}).to_list(1000)
        nomi_esclusi = {f["nome"].lower().strip() for f in fornitori_esclusi_docs}
    # La lista usa solo i metadati: proiettare tutto (righe prodotti + xml_raw
    # intero) trasferiva decine di MB da Atlas a ogni apertura della pagina.
    pipeline = []
    if anno and anno > 0:
        # data_fattura è in formati misti: ISO (2026-07-20) → anno all'inizio,
        # oppure dd/mm/yyyy e dd-mm-yyyy → anno in fondo. Copro entrambi.
        y = str(int(anno))
        pipeline.append({"$match": {"$or": [
            {"data_fattura": {"$regex": f"^{y}[-/]"}},
            {"data_fattura": {"$regex": f"[-/]{y}$"}},
        ]}})
    pipeline.append(
        {"$project": {
            "_id": 0, "id": 1, "numero_fattura": 1, "data_fattura": 1,
            "fornitore": 1, "created_at": 1, "importo_totale": 1, "totale": 1,
            "num_prodotti": {"$size": {"$ifNull": ["$prodotti", []]}},
            "has_xml": {"$eq": [{"$type": "$xml_raw"}, "string"]},
        }},
    )
    items = await db.fatture.aggregate(pipeline).to_list(limit * 3)
    if nomi_esclusi:
        items = [f for f in items if f.get("fornitore", "").lower().strip() not in nomi_esclusi]

    def _chiave_data(f):
        s = (f.get("data_fattura") or "").strip()
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
            try:
                return datetime.strptime(s, fmt)
            except Exception:
                logger.debug("[fatture] errore non bloccante ignorato")
        ca = f.get("created_at")
        if isinstance(ca, datetime):
            return ca.replace(tzinfo=None)
        try:
            return datetime.fromisoformat(str(ca)).replace(tzinfo=None)
        except Exception:
            return datetime.min

    items.sort(key=_chiave_data, reverse=True)
    if anno and anno > 0:
        # sicurezza: tiene solo l'anno richiesto (il $match copre già i formati
        # noti; questo scarta eventuali date fuori formato agganciate dal regex)
        items = [f for f in items if _chiave_data(f).year == int(anno)]
    elif mesi and mesi > 0:
        cutoff = datetime.now() - timedelta(days=int(mesi) * 30.5)
        items = [f for f in items if _chiave_data(f) >= cutoff]
    return items[:limit]


@router.get("/{fattura_id}/impatto")
async def impatto_fattura(fattura_id: str):
    """Schermata di impatto prima dell'eliminazione (tranche 4)."""
    f = await db.fatture.find_one({"id": fattura_id}, {"_id": 0, "numero_fattura": 1, "fornitore": 1})
    if not f:
        raise HTTPException(404, "Fattura non trovata")
    return await _impatto_fattura(f)


async def _impatto_fattura(f: dict) -> dict:
    lotti = await db.lotti_fornitori.find(
        {"fattura_ref": f.get("numero_fattura"), "fornitore": f.get("fornitore")},
        {"_id": 0, "id": 1, "quantita_disponibile": 1, "quantita_acquistata": 1, "storico_utilizzi": 1},
    ).to_list(500)
    movimentati = [l for l in lotti if (l.get("storico_utilizzi") or [])
                   or float(l.get("quantita_disponibile") or 0) < float(l.get("quantita_acquistata") or 0)]
    produzioni = sorted({u.get("lotto_produzione") for l in movimentati
                         for u in (l.get("storico_utilizzi") or []) if u.get("lotto_produzione")})
    residuo = sum(float(l.get("quantita_disponibile") or 0) for l in lotti)
    return {
        "lotti": len(lotti), "lotti_ids": [l["id"] for l in lotti],
        "movimentati": len(movimentati), "produzioni": len(produzioni),
        "produzioni_lotti": produzioni[:20],
        "giacenza_residua": round(residuo, 3),
        "eliminabile": not movimentati,
    }


@router.delete("/{fattura_id}")
async def delete_fattura(fattura_id: str, conferma: bool = Query(False), _admin=Depends(require_admin)):
    """Eliminazione SICURA (tranche 4): senza collegamenti si elimina; con
    lotti mai movimentati serve conferma (e si eliminano insieme); con lotti
    consumati/produzioni collegate NON si elimina → annullamento logico."""
    f = await db.fatture.find_one({"id": fattura_id}, {"_id": 0, "numero_fattura": 1, "fornitore": 1})
    if not f:
        raise HTTPException(404, "Fattura non trovata")
    imp = await _impatto_fattura(f)
    if imp["movimentati"]:
        raise HTTPException(409,
            f"Fattura già utilizzata ({imp['movimentati']} lotti movimentati, "
            f"{imp['produzioni']} produzioni collegate): NON eliminabile. "
            f"Usa l'annullamento logico (POST /fatture/{fattura_id}/annulla).")
    if imp["lotti"] and not conferma:
        raise HTTPException(409,
            f"Questa fattura ha generato {imp['lotti']} lotti (mai movimentati, "
            f"giacenza residua {imp['giacenza_residua']}): ripeti con conferma=true "
            f"per eliminare fattura e lotti insieme.")
    if imp["lotti_ids"]:
        await db.lotti_fornitori.delete_many({"id": {"$in": imp["lotti_ids"]}})
    result = await db.fatture.delete_one({"id": fattura_id})
    return {"success": True, "lotti_eliminati": len(imp["lotti_ids"]),
            "fatture_eliminate": result.deleted_count}


@router.post("/{fattura_id}/annulla")
async def annulla_fattura(fattura_id: str, motivo: str = Query(..., min_length=3), _admin=Depends(require_admin)):
    """Annullamento LOGICO (tranche 4): la fattura resta in archivio marcata
    annullata; i suoi lotti non ancora consumati vengono chiusi (esauriti)
    così il FIFO non li usa più. Nessuna cancellazione fisica."""
    f = await db.fatture.find_one({"id": fattura_id}, {"_id": 0, "numero_fattura": 1, "fornitore": 1})
    if not f:
        raise HTTPException(404, "Fattura non trovata")
    adesso = datetime.now(timezone.utc).isoformat()
    await db.fatture.update_one({"id": fattura_id}, {"$set": {
        "annullata": True, "annullata_il": adesso, "annullata_motivo": motivo}})
    r = await db.lotti_fornitori.update_many(
        {"fattura_ref": f.get("numero_fattura"), "fornitore": f.get("fornitore"),
         "esaurito": {"$ne": True}},
        {"$set": {"esaurito": True, "stato": "annullata_fattura",
                  "annullato_il": adesso, "annullato_motivo": motivo}})
    return {"success": True, "annullata": True, "lotti_chiusi": r.modified_count}

@router.get("/{fattura_id}/visualizza", response_class=HTMLResponse)
async def visualizza_fattura_html(fattura_id: str):
    """Trasforma la fattura XML con foglio stile Assosoftware."""
    try:
        from lxml import etree
    except ImportError:
        raise HTTPException(status_code=500, detail="lxml non disponibile")

    fattura = await db.fatture.find_one({"id": fattura_id})
    if not fattura:
        fattura = await db.fatture.find_one({"numero_fattura": fattura_id})
    if not fattura:
        raise HTTPException(status_code=404, detail="Fattura non trovata")

    xml_raw = fattura.get("xml_raw", "")
    if not xml_raw:
        return HTMLResponse(
            content=_genera_html_fallback(fattura), media_type="text/html; charset=utf-8"
        )

    if not XSL_PATH.exists():
        raise HTTPException(status_code=500, detail=f"File XSL non trovato: {XSL_PATH}")

    try:
        xml_bytes = xml_raw.encode("utf-8")
        if xml_bytes.startswith(b"\xef\xbb\xbf"):
            xml_bytes = xml_bytes[3:]
        xml_doc = etree.fromstring(xml_bytes)
        xsl_doc = etree.parse(str(XSL_PATH))
        transform = etree.XSLT(xsl_doc)
        result_tree = transform(xml_doc)
        html_output = str(result_tree)
        if not html_output or len(html_output) < 100:
            return HTMLResponse(
                content=_genera_html_fallback(fattura), media_type="text/html; charset=utf-8"
            )
        return HTMLResponse(content=html_output, media_type="text/html; charset=utf-8")
    except Exception as e:
        return HTMLResponse(
            content=_genera_html_fallback(fattura, str(e)), media_type="text/html; charset=utf-8"
        )


def _genera_html_fallback(fattura: dict, errore: str = None) -> str:
    """Genera una visualizzazione HTML semplice dai dati parsati della fattura."""
    num = fattura.get("numero_fattura", "N/D")
    forn = fattura.get("fornitore", "N/D")
    piva = fattura.get("piva", "N/D")
    data = fattura.get("data_fattura", "N/D")
    prodotti = fattura.get("prodotti", [])

    prodotti_html = ""
    totale = 0
    for p in prodotti:
        descrizione = p.get("descrizione", p.get("nome", ""))
        qty = p.get("quantita", 0)
        um = p.get("unita_misura", "")
        prezzo = p.get("prezzo_unitario", 0)
        importo = float(qty or 0) * float(prezzo or 0)
        totale += importo
        prodotti_html += f"""
        <tr>
            <td style="padding:6px;border-bottom:1px solid #eee;">{descrizione}</td>
            <td style="padding:6px;border-bottom:1px solid #eee;text-align:center;">{qty} {um}</td>
            <td style="padding:6px;border-bottom:1px solid #eee;text-align:right;">€{float(prezzo or 0):.4f}</td>
            <td style="padding:6px;border-bottom:1px solid #eee;text-align:right;">€{importo:.2f}</td>
        </tr>"""

    nota = (
        f'<div style="background:#fff3cd;border:1px solid #ffc107;padding:8px;margin:8px 0;font-size:11px;">'
        f"<b>Nota:</b> Visualizzazione XML non disponibile ({errore}). Dati estratti dal database.</div>"
        if errore
        else '<div style="background:#fff3cd;border:1px solid #ffc107;padding:8px;margin:8px 0;font-size:11px;">'
        "<b>Nota:</b> Fattura importata senza XML originale.</div>"
    )

    return f"""<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <title>Fattura N. {num}</title>
    <style>
        body {{ font-family: Arial, sans-serif; font-size: 13px; max-width: 900px; margin: 20px auto; padding: 20px; }}
        .header {{ border: 2px solid #1a3a6b; padding: 15px; margin-bottom: 15px; }}
        .header h1 {{ color: #1a3a6b; margin: 0 0 5px; font-size: 18px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 15px; }}
        thead th {{ background: #1a3a6b; color: white; padding: 8px; text-align: left; font-size: 12px; }}
        .totale {{ font-weight: bold; text-align: right; padding: 10px 6px; border-top: 2px solid #333; }}
        .print-btn {{ position: fixed; top: 10px; right: 10px; background: #1a3a6b; color: white; border: none; padding: 8px 16px; cursor: pointer; border-radius: 4px; }}
    </style>
</head>
<body>
    <button class="print-btn" onclick="window.print()">Stampa</button>
    {nota}
    <div class="header">
        <h1>FATTURA ELETTRONICA N. {num}</h1>
        <table style="border:none;">
            <tr><td style="width:120px;color:#666;">Fornitore:</td><td><b>{forn}</b></td></tr>
            <tr><td style="color:#666;">P.IVA:</td><td>{piva}</td></tr>
            <tr><td style="color:#666;">Data:</td><td>{data}</td></tr>
        </table>
    </div>
    <table>
        <thead><tr><th>Descrizione</th><th>Qtà</th><th>Prezzo Unit.</th><th>Importo</th></tr></thead>
        <tbody>{prodotti_html}</tbody>
        <tfoot><tr><td colspan="3" class="totale">TOTALE IMPONIBILE:</td><td class="totale">€{totale:.2f}</td></tr></tfoot>
    </table>
</body>
</html>"""


# ── Import XML manuale ────────────────────────────────────────────────────────
async def _carico_magazzino_bar_da_fattura(prodotti, numero_fattura, fornitore):
    """Aggancio fattura -> magazzino bar. Per ogni riga che corrisponde a un prodotto
    bar (per nome) o a una categoria bar (allowlist), incrementa lo stock. Le materie
    prime (farine, latticini, uova...) NON entrano qui: restano nei lotti. Idempotente
    per numero fattura. Non solleva mai: l'ingestione fattura non deve rompersi."""
    try:
        if numero_fattura:
            gia = await db.magazzino_bar_movimenti.find_one(
                {"fattura_ref": numero_fattura, "origine": "fattura"}, {"_id": 1}
            )
            if gia:
                return {"caricati": 0, "creati": 0, "gia_fatto": True}
        from app.lotti.routers.prodotti_master import normalize_nome
        try:
            from app.lotti.routers.listino import _categoria
        except Exception:
            def _categoria(_x):
                return None
        BAR_CAT = {
            "ACQUA": "Bibite", "BIBITE": "Bibite", "SUCCHI": "Bibite", "SCIROPPI": "Bibite",
            "BIRRE": "Bibite", "VINO": "Vini e Bevande", "PROSECCO": "Vini e Bevande",
            "LIQUORI": "Liquori", "AMARI": "Liquori", "CAFFE": "Caffe",
            "MONOUSO": "Monouso", "IMBALLAGGI": "Imballaggi",
        }
        prods = await db.magazzino_bar_prodotti.find({}, {"_id": 0}).to_list(2000)
        idx = {}
        for p in prods:
            k = normalize_nome(p.get("nome", ""))
            if k:
                idx.setdefault(k, p)
        caricati = 0
        creati = 0
        # Classificatore UNICO (classificatore_alimenti): niente servizi,
        # niente non-food fisico (candeggina, cavi, monitor...) in giacenza.
        from app.lotti.routers.classificatore_alimenti import e_merce_alimentare
        for prodotto in (prodotti or []):
            desc = re.sub(r"\s+", " ", (prodotto.get("descrizione") or "").strip())
            if not desc:
                continue
            if not e_merce_alimentare(desc):
                continue  # servizio o non-alimentare -> resta solo in fattura (statistica)
            try:
                qt = float(str(prodotto.get("quantita", "1") or "1").replace(",", ".").strip())
            except Exception:
                qt = 0
            if qt <= 0:
                continue
            norm = normalize_nome(desc)
            prod = idx.get(norm)
            if not prod:
                cat = (_categoria(desc) or "").upper()
                if cat not in BAR_CAT:
                    continue  # materia prima -> resta nei lotti
                cat_bar = BAR_CAT[cat]
                try:
                    from app.lotti.routers.magazzino_bar import _risolvi_cat
                    cat_bar = await _risolvi_cat(cat_bar)
                except Exception:
                    logger.debug("[fatture] errore non bloccante ignorato")
                prod = {
                    "id": str(uuid.uuid4()), "nome": desc, "categoria": cat_bar,
                    "fornitore": fornitore or "",
                    "unita": (prodotto.get("unita_misura") or "pz").lower(), "stock": 0,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                await db.magazzino_bar_prodotti.insert_one(dict(prod))
                idx[norm] = prod
                creati += 1
            ppc = float(prod.get("pezzi_per_collo", 1) or 1)
            pezzi = qt * ppc if ppc > 1 else qt
            from app.lotti.routers.magazzino_bar import applica_movimento_stock
            nuovo, _mov = await applica_movimento_stock(
                prod, pezzi, "carico", "Sistema (fattura)",
                nota=("Carico da fattura " + (numero_fattura or "") + " - " + (fornitore or "")).strip(),
                extra={"quantita_colli": (qt if ppc > 1 else None), "origine": "fattura",
                       "fattura_ref": numero_fattura or ""},
            )
            prod["stock"] = nuovo
            caricati += 1
        return {"caricati": caricati, "creati": creati}
    except Exception as e:
        import logging
        logging.getLogger("fatture").exception("carico bar da fattura: %s", e)
        return {"errore": str(e)[:140]}


class _UF:
    """File caricato già letto in memoria (usabile dentro un BackgroundTask)."""
    def __init__(self, filename, content):
        self.filename = filename
        self._content = content

    async def read(self):
        return self._content


def _estrai_xml(raw: bytes) -> bytes:
    """Estrae la porzione XML della FatturaElettronica da un allegato grezzo:
    XML semplice, oppure file .p7m firmato (busta PKCS#7) da cui si ritaglia il
    blocco <FatturaElettronica>. Gestisce qualunque prefisso namespace della
    radice (es. <ns3:FatturaElettronica>) e il caso busta base64.
    Helper puro condiviso da import e prescan."""
    # Solo l'XML GREZZO (con dichiarazione all'inizio) si restituisce così com'è.
    # NON basta "FatturaElettronica nei primi 400 byte": nei .p7m firmati con
    # busta DER piccola l'XML inizia subito, e quella scorciatoia restituiva il
    # BINARIO firmato intero → il parser falliva ("not well-formed, line 1").
    # Bug reale trovato su una fattura Villa Sandi (.xml.p7m). Ora i p7m passano
    # SEMPRE per _carve, che ritaglia il blocco <?xml…</FatturaElettronica>.
    _s = raw.lstrip()
    if _s[:5] == b"<?xml" or re.match(rb"<([A-Za-z0-9._-]+:)?FatturaElettronica[\s>]", _s):
        return raw

    def _carve(b: bytes):
        i = b.find(b"<?xml")
        if i < 0:
            m = re.search(rb"<([A-Za-z0-9._-]+:)?FatturaElettronica[\s>]", b)
            i = m.start() if m else -1
        if i < 0:
            return None
        last = None
        for mm in re.finditer(rb"FatturaElettronica\s*>", b):
            last = mm
        return b[i:last.end()] if last else b[i:]

    out = _carve(raw)
    if out is not None:
        return out
    # Fallback: alcune buste .p7m/allegati arrivano codificate base64
    try:
        import base64 as _b64
        out = _carve(_b64.b64decode(raw, validate=False))
        if out is not None:
            return out
    except Exception:
        pass
    return raw


@router.post("/importa-xml")
async def importa_fattura_xml(files: List[UploadFile] = File(...), job_id: str = None):
    """Importa fatture XML e aggiorna automaticamente le materie prime."""
    from app.lotti.routers.xml_helpers import parse_fattura_xml, fuzzy_match

    risultati = {
        "fatture_processate": 0,
        "fatture_duplicate_saltate": 0,
        "fatture_saltate_escluse": 0,
        "prodotti_trovati": 0,
        "materie_aggiornate": 0,
        "nuove_materie": 0,
        "match_ingredienti": [],
        "errori": [],
    }

    fornitori_esclusi_docs = await db.fornitori.find({"escluso": True}, {"nome": 1}).to_list(5000)
    fornitori_esclusi = {f["nome"].lower() for f in fornitori_esclusi_docs}
    fornitori_solomag_docs = await db.fornitori.find({"tipo_fornitura": "solo_magazzino"}, {"nome": 1}).to_list(5000)
    fornitori_solo_magazzino = {f["nome"].lower() for f in fornitori_solomag_docs}

    ricette = await db.ricette.find({}, {"_id": 0}).to_list(5000)
    ingredienti_ricette = {}
    for ricetta in ricette:
        for ing in ricetta.get("ingredienti", []):
            ing_lower = ing.lower().strip()
            if ing_lower not in ingredienti_ricette:
                ingredienti_ricette[ing_lower] = ing

    mappature = await db.mappature.find({}, {"_id": 0}).to_list(10000)
    mappa_prodotto_ingrediente = {
        m.get("prodotto_fattura", "").lower(): m.get("ingrediente_ricetta", "") for m in mappature
    }

    def rileva_allergeni_materia(testo: str) -> str:
        testo_low = testo.lower()
        allergeni = []
        if any(
            k in testo_low
            for k in ["farina", "grano", "frumento", "semola", "glutine", "pasta", "orzo"]
        ):
            allergeni.append("Cereali contenenti glutine")
        if any(k in testo_low for k in ["uova", "uovo", "tuorlo", "albume"]):
            allergeni.append("Uova")
        if any(
            k in testo_low
            for k in [
                "latte",
                "burro",
                "panna",
                "formaggio",
                "mozzarella",
                "ricotta",
                "lattosio",
                "caseina",
            ]
        ):
            allergeni.append("Latte e derivati")
        if any(k in testo_low for k in ["soia", "soy", "lecitina di soia"]):
            allergeni.append("Soia")
        if any(k in testo_low for k in ["nocciole", "mandorle", "pistacchio", "noci", "pinoli"]):
            allergeni.append("Frutta a guscio")
        return ("Contiene: " + ", ".join(allergeni)) if allergeni else "non contiene allergeni"

    # ── Espansione allegati: accetta XML singoli, archivi ZIP (anche con più XML
    #    dentro) e file .p7m firmati (estrae la porzione XML via _estrai_xml module-level) ──
    _expanded = []
    for _up in files:
        _raw = await _up.read()
        _nome = (_up.filename or "").lower()
        if _nome.endswith(".zip") or _raw[:2] == b"PK":
            try:
                with zipfile.ZipFile(io.BytesIO(_raw)) as _zf:
                    for _zi in _zf.namelist():
                        _low = _zi.lower()
                        if _zi.endswith("/") or not (_low.endswith(".xml") or _low.endswith(".p7m")):
                            continue
                        _expanded.append(_UF(_zi.split("/")[-1], _estrai_xml(_zf.read(_zi))))
            except Exception as _e:
                risultati["errori"].append(f"{_up.filename}: ZIP non valido ({str(_e)[:60]})")
        else:
            _expanded.append(_UF(_up.filename, _estrai_xml(_raw)))

    if not _expanded and not risultati["errori"]:
        risultati["errori"].append("Nessun file .xml trovato negli allegati")

    for _idx, file in enumerate(_expanded):
        if job_id and _idx % 5 == 0:
            try:
                await db.import_jobs.update_one(
                    {"id": job_id},
                    {"$set": {"processed": _idx, "ok": risultati["fatture_processate"], "errori": risultati["errori"][-60:]}},
                )
            except Exception:
                logger.debug("[fatture] errore non bloccante ignorato")
        try:
            content = await file.read()
            fattura_data = parse_fattura_xml(content)

            if not fattura_data["fornitore"]:
                risultati["errori"].append(f"{file.filename}: Fornitore non trovato")
                continue

            if fattura_data["fornitore"].lower() in fornitori_esclusi:
                risultati["fatture_saltate_escluse"] += 1
                continue

            # Tri-stato fornitura: "solo_magazzino" crea i lotti_fornitori CON flag
            # solo_magazzino=True (così popolano il Magazzino con giacenza) ma restano
            # FUORI da Materie Prime/ricette (flag filtrato la, guard ricette sotto).
            is_solo_mag = fattura_data["fornitore"].lower() in fornitori_solo_magazzino

            data_fmt = fattura_data["data_fattura"]
            if "-" in data_fmt:
                try:
                    data_fmt = datetime.strptime(data_fmt, "%Y-%m-%d").strftime("%d/%m/%Y")
                except (ValueError, TypeError):
                    pass

            # Una fattura puo arrivare dal caricamento manuale, dal vecchio Drive
            # oppure dal ponte GestionaleCloud. Prima di applicare qualunque
            # effetto additivo (giacenze, numero acquisti, lotti) riconosciamo lo
            # stesso XML tramite SHA-256 e usciamo senza rielaborarlo.
            xml_sha256 = hashlib.sha256(content).hexdigest()
            if fattura_data.get("piva"):
                chiave_esistente = {
                    "numero_fattura": fattura_data.get("numero_fattura", ""),
                    "piva": fattura_data.get("piva", ""),
                }
            else:
                chiave_esistente = {
                    "fornitore": fattura_data.get("fornitore", ""),
                    "numero_fattura": fattura_data.get("numero_fattura", ""),
                    "data_fattura": data_fmt,
                }
            esistente = await db.fatture.find_one(
                chiave_esistente,
                {"_id": 0, "id": 1, "xml_raw": 1, "haccp_xml_sha256": 1},
            )
            hash_esistente = (esistente or {}).get("haccp_xml_sha256", "")
            if not hash_esistente and (esistente or {}).get("xml_raw"):
                hash_esistente = hashlib.sha256(
                    str(esistente["xml_raw"]).encode("utf-8")
                ).hexdigest()
            if esistente and hash_esistente == xml_sha256:
                await db.fatture.update_one(
                    chiave_esistente,
                    {"$set": {
                        "haccp_xml_sha256": xml_sha256,
                        "haccp_pipeline_version": 1,
                        "haccp_ultimo_duplicato_ignorato": datetime.now(timezone.utc).isoformat(),
                    }},
                )
                risultati["fatture_duplicate_saltate"] += 1
                continue

            risultati["fatture_processate"] += 1
            risultati["prodotti_trovati"] += len(fattura_data["prodotti"])

            fattura = FatturaImportata(
                fornitore=fattura_data["fornitore"],
                piva=fattura_data["piva"],
                numero_fattura=fattura_data["numero_fattura"],
                data_fattura=data_fmt,
                prodotti=fattura_data["prodotti"],
            )
            fattura_dict = fattura.model_dump()
            fattura_dict["created_at"] = fattura_dict["created_at"].isoformat()
            fattura_dict["xml_raw"] = content.decode("utf-8", errors="replace")
            fattura_dict["haccp_xml_sha256"] = xml_sha256
            fattura_dict["haccp_pipeline_version"] = 1

            # Chiave anti-duplicato: DEVE combaciare con l'indice unico del DB
            # `uniq_numero_piva` (numero_fattura + piva) nel database di Lotti.
            # Se usassi fornitore+numero+data e la
            # stessa fattura è già presente con il fornitore/data scritti in modo
            # leggermente diverso, l'upsert non la troverebbe e l'inserimento
            # sbatterebbe sull'indice unico → E11000 (era la causa dei "268 in errore").
            # Con piva presente uso numero+piva; senza piva ricado sulla vecchia chiave.
            if fattura.piva:
                chiave_fattura = {"numero_fattura": fattura.numero_fattura, "piva": fattura.piva}
            else:
                chiave_fattura = {
                    "fornitore": fattura.fornitore,
                    "numero_fattura": fattura.numero_fattura,
                    "data_fattura": data_fmt,
                }
            # id e created_at NON vanno sovrascritti su un documento già esistente
            # (potrebbe esistere per un precedente import): solo all'inserimento.
            set_doc = {k: v for k, v in fattura_dict.items() if k not in ("id", "created_at")}
            on_insert = {"id": fattura_dict.get("id"), "created_at": fattura_dict.get("created_at")}
            try:
                await db.fatture.update_one(
                    chiave_fattura,
                    {"$set": set_doc, "$setOnInsert": on_insert},
                    upsert=True,
                )
            except DuplicateKeyError:
                # Esiste già con lo stesso numero+piva ma la chiave non l'ha
                # agganciata. TRANCHE 4 (24/07/2026): se la P.IVA MANCA,
                # l'identità del fornitore è debole — prima il $set qui sotto
                # SOVRASCRIVEVA la fattura di un ALTRO fornitore con lo stesso
                # numero. Ora: aggiorno solo se il fornitore combacia;
                # altrimenti conservo ENTRAMBE (piva surrogata "ND:<fornitore>")
                # e segnalo "possibile duplicato — verifica richiesta".
                _norm_f = lambda s: " ".join((s or "").lower().split())  # noqa: E731
                esistente = await db.fatture.find_one(
                    {"numero_fattura": fattura.numero_fattura, "piva": fattura.piva},
                    {"_id": 0, "fornitore": 1})
                stesso_fornitore = esistente and _norm_f(esistente.get("fornitore")) == _norm_f(fattura.fornitore)
                if fattura.piva or stesso_fornitore:
                    await db.fatture.update_one(
                        {"numero_fattura": fattura.numero_fattura, "piva": fattura.piva},
                        {"$set": set_doc},
                    )
                else:
                    set2 = dict(set_doc)
                    set2["piva"] = ("ND:" + _norm_f(fattura.fornitore))[:60]
                    set2["verifica_richiesta"] = True
                    await db.fatture.update_one(
                        {"numero_fattura": fattura.numero_fattura, "piva": set2["piva"]},
                        {"$set": set2, "$setOnInsert": on_insert},
                        upsert=True,
                    )
                    risultati["errori"].append(
                        f"Possibile duplicato — verifica richiesta: fattura {fattura.numero_fattura} "
                        f"di {fattura.fornitore} (numero già presente per un altro fornitore senza P.IVA; conservate entrambe)")

            # Crea fornitore se nuovo
            if not await db.fornitori.find_one({"nome": fattura_data["fornitore"]}):
                await db.fornitori.insert_one(
                    {
                        "id": str(uuid.uuid4()),
                        "nome": fattura_data["fornitore"],
                        "piva": fattura_data["piva"],
                        "escluso": False,
                        "in_attesa": True,
                        "first_seen": datetime.now(timezone.utc).isoformat(),
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
            elif fattura_data["piva"]:
                await db.fornitori.update_one(
                    {"nome": fattura_data["fornitore"], "piva": {"$exists": False}},
                    {"$set": {"piva": fattura_data["piva"]}},
                )

            # Aggiorna/crea scheda anagrafica fornitore (email, cellulare, ultima fattura)
            await db.fornitori_anagrafica.update_one(
                {"nome": fattura_data["fornitore"]},
                {
                    "$set": {
                        "nome": fattura_data["fornitore"],
                        "piva": fattura_data.get("piva", ""),
                        "ultima_fattura": data_fmt,
                        "n_fatture": await db.fatture.count_documents(
                            {"fornitore": fattura_data["fornitore"]}
                        ),
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                },
                upsert=True,
            )

            # Estrai contatti dal XML (email, telefono, PEC)
            try:
                xml_str = content.decode("utf-8", errors="replace")
                import re as _re

                xml_emails = _re.findall(r"<Email>(.*?)</Email>", xml_str)
                xml_tels = _re.findall(r"<Telefono>(.*?)</Telefono>", xml_str)
                xml_faxes = _re.findall(r"<Fax>(.*?)</Fax>", xml_str)
                all_emails = _re.findall(r"[\w.+-]+@[\w.-]+\.\w{2,}", xml_str)
                # Filtra: non salvare la propria PEC come contatto fornitore
                fornitore_emails = [
                    e
                    for e in (xml_emails + all_emails)
                    if "ceraldi" not in e.lower() and "legalmail" not in e.lower()
                ]
                if fornitore_emails or xml_tels:
                    contact_update = {}
                    if fornitore_emails:
                        contact_update["email"] = fornitore_emails[0]
                    if xml_tels:
                        contact_update["cellulare"] = xml_tels[0]
                    if xml_faxes:
                        contact_update["fax"] = xml_faxes[0]
                    if contact_update:
                        contact_update["fonte_contatto"] = "fattura_xml"
                        await db.fornitori_anagrafica.update_one(
                            {"nome": fattura_data["fornitore"]}, {"$set": contact_update}
                        )
            except Exception:
                logger.debug("[fatture] errore non bloccante ignorato")
            for idx, prodotto in enumerate(fattura_data["prodotti"]):
                desc = re.sub(r"\s+", " ", prodotto.get("descrizione", "").strip())
                if not desc:
                    continue
                lotto_data = prodotto.get("_lotto_data", {})
                lotto_id = lotto_data.get("lotto_id_fornitore") if lotto_data else None
                data_scad = lotto_data.get("data_scadenza", "") if lotto_data else ""
                giorni_scad = None
                try:
                    if data_scad and "/" in data_scad:
                        dt_s = datetime.strptime(data_scad, "%d/%m/%Y")
                        giorni_scad = (dt_s - datetime.now()).days
                except Exception:
                    logger.debug("[fatture] errore non bloccante ignorato")
                try:
                    qt = float(str(prodotto.get("quantita", "1") or "1").replace(",", ".").strip())
                    if qt <= 0:
                        qt = 1.0
                except (ValueError, TypeError):
                    qt = 1.0
                try:
                    prezzo = float(
                        str(prodotto.get("prezzo_unitario") or prodotto.get("prezzo", "0") or "0")
                        .replace(",", ".")
                        .strip()
                    )
                except (ValueError, TypeError):
                    prezzo = 0.0
                # Chiave univoca: fattura + fornitore + descrizione prodotto
                chiave = {
                    "fattura_ref": fattura_data.get("numero_fattura", ""),
                    "fornitore": fattura_data["fornitore"],
                    "prodotto_nome": desc,
                }
                exists = await db.lotti_fornitori.find_one(chiave, {"_id": 0, "id": 1})
                if not exists:
                    await db.lotti_fornitori.insert_one(
                        {
                            "id": str(uuid.uuid4()),
                            "fornitore": fattura_data["fornitore"],
                            "prodotto_nome": desc,
                            "prodotto_nome_norm": desc.lower(),
                            "lotto_id_fornitore": lotto_id
                            or f"{fattura_data.get('numero_fattura','')}-{idx}",
                            "data_scadenza": data_scad,
                            "giorni_alla_scadenza": giorni_scad,
                            "scaduto": (giorni_scad is not None and giorni_scad < 0),
                            "quantita_originale": (
                                lotto_data.get("quantita_originale", qt) if lotto_data else qt
                            ),
                            "quantita_acquistata": qt,
                            "quantita_disponibile": qt,
                            "unita_misura": (prodotto.get("unita_misura") or "PZ").upper(),
                            "prezzo_unitario": prezzo,
                            "fattura_ref": fattura_data.get("numero_fattura", ""),
                            "data_fattura": data_fmt,
                            "solo_magazzino": is_solo_mag,
                            "esaurito": False,
                            "created_at": datetime.now(timezone.utc).isoformat(),
                        }
                    )
                    risultati["nuove_materie"] += 1

            # Aggancio magazzino bar (carico stock da fattura)
            try:
                _bar = await _carico_magazzino_bar_da_fattura(
                    fattura_data["prodotti"], fattura_data.get("numero_fattura", ""), fattura_data["fornitore"])
                risultati.setdefault("magazzino_bar", {"caricati": 0, "creati": 0})
                risultati["magazzino_bar"]["caricati"] += (_bar or {}).get("caricati", 0)
                risultati["magazzino_bar"]["creati"] += (_bar or {}).get("creati", 0)
            except Exception:
                logger.debug("[fatture] errore non bloccante ignorato")
            # Aggiorna listino prezzi per fornitore (sync con listino_prodotti)
            for prodotto in fattura_data["prodotti"]:
                try:
                    desc = re.sub(r"\s+", " ", (prodotto.get("descrizione") or "").strip().upper())
                    if not desc or len(desc) < 3:
                        continue
                    pr = float(
                        str(prodotto.get("prezzo_unitario") or prodotto.get("prezzo", "0") or "0")
                        .replace(",", ".")
                        .strip()
                    )
                    if pr <= 0:
                        continue
                    fornitore = fattura_data["fornitore"]
                    # Upsert: aggiorna il prezzo di questo fornitore per il prodotto
                    existing = await db.listino_prodotti.find_one(
                        {"nome": desc}, {"_id": 0, "id": 1, "prezzi": 1}
                    )
                    if existing:
                        prezzi_upd = dict(existing.get("prezzi", {}))
                        prezzi_upd[fornitore] = round(pr, 4)
                        from app.lotti.routers.listino import _best_fornitore_affidabile
                        best = _best_fornitore_affidabile(prezzi_upd)
                        await db.listino_prodotti.update_one(
                            {"nome": desc},
                            {
                                "$set": {
                                    "prezzi": prezzi_upd,
                                    "miglior_fornitore": best,
                                    "updated_at": datetime.now(timezone.utc).isoformat(),
                                }
                            },
                        )
                    else:
                        from app.lotti.routers.listino import _categoria

                        prezzi_new = {fornitore: round(pr, 4)}
                        um = (prodotto.get("unita_misura") or "PZ").upper()
                        await db.listino_prodotti.insert_one(
                            {
                                "id": str(uuid.uuid4()),
                                "nome": desc,
                                "categoria": _categoria(desc),
                                "conf": um,
                                "prezzi": prezzi_new,
                                "miglior_fornitore": fornitore,
                                "preferito": False,
                                "custom": False,
                                "created_at": datetime.now(timezone.utc).isoformat(),
                            }
                        )
                except Exception as e:
                    logger.warning(f"[fatture] Aggiornamento contatto fornitore fallito: {e}")
            for prodotto in fattura_data["prodotti"]:
                try:
                    desc = prodotto.get("descrizione", "").strip()
                    desc_norm = re.sub(r"\s+", " ", desc.lower().strip())
                    if not desc_norm:
                        continue
                    mapping = await db.nome_mapping.find_one(
                        {"descrizione_key": desc_norm[:200]}, {"_id": 0, "nome_canc": 1}
                    )
                    if mapping and mapping.get("nome_canc"):
                        nome_canc_norm = mapping["nome_canc"].lower().strip()
                        await db.dizionario_prodotti.update_one(
                            {
                                "nome_normalizzato": {
                                    "$regex": re.escape(nome_canc_norm[:15]),
                                    "$options": "i",
                                }
                            },
                            {"$addToSet": {"aliases": desc_norm}},
                        )
                    else:
                        await db.dizionario_prodotti.update_one(
                            {"nome_normalizzato": desc_norm},
                            {"$addToSet": {"aliases": desc_norm}},
                        )
                except Exception:
                    logger.debug("[fatture] errore non bloccante ignorato")

            # Match ingredienti <-> prodotti fattura
            for prodotto in fattura_data["prodotti"]:
                if is_solo_mag:
                    continue  # solo_magazzino: niente match con gli ingredienti ricetta
                desc = prodotto.get("descrizione", "")
                desc_lower = desc.lower()
                ingrediente_mappato = mappa_prodotto_ingrediente.get(desc_lower)

                if not ingrediente_mappato:
                    for ing_lower, ing_originale in ingredienti_ricette.items():
                        if fuzzy_match(ing_lower, desc_lower, soglia=70):
                            ingrediente_mappato = ing_originale
                            await db.mappature.update_one(
                                {"prodotto_fattura": desc},
                                {
                                    "$set": {
                                        "id": str(uuid.uuid4()),
                                        "prodotto_fattura": desc,
                                        "ingrediente_ricetta": ing_originale,
                                        "fornitore": fattura_data["fornitore"],
                                        "created_at": datetime.now(timezone.utc).isoformat(),
                                    }
                                },
                                upsert=True,
                            )
                            break

                if ingrediente_mappato:
                    allergeni = rileva_allergeni_materia(desc)
                    descrizione_completa = f"{desc}  {allergeni} - {fattura_data['fornitore']} n° fatt {fattura_data['numero_fattura']} - {data_fmt}"

                    # Aggiorna allergeni_testo nel lotto fornitore corrispondente (se presente)
                    await db.lotti_fornitori.update_many(
                        {
                            "fornitore": fattura_data["fornitore"],
                            "data_fattura": data_fmt,
                            "prodotto_nome": {"$regex": re.escape(desc[:20]), "$options": "i"},
                        },
                        {
                            "$set": {
                                "allergeni_testo": allergeni,
                                "ingrediente_mappato": ingrediente_mappato,
                            }
                        },
                    )

                    risultati["match_ingredienti"].append(
                        {
                            "prodotto_fattura": desc[:50],
                            "ingrediente": ingrediente_mappato,
                            "fornitore": fattura_data["fornitore"],
                            "fattura": fattura_data["numero_fattura"],
                        }
                    )
                    risultati["materie_aggiornate"] += 1

            # ── Bug 3 fix: aggiorna dizionario_prodotti (giacenze + conteggio_acquisti) ──
            # pec_import lo faceva, l'import XML manuale no — ora allineati
            for prodotto in fattura_data["prodotti"]:
                try:
                    fattura_ctx = {
                        "fornitore": fattura_data.get("fornitore", ""),
                        "piva": fattura_data.get("piva", ""),
                    }
                    prod_norm = {
                        "descrizione": (prodotto.get("descrizione") or "").strip(),
                        "quantita": prodotto.get("quantita", 1),
                        "prezzo": prodotto.get("prezzo_unitario") or prodotto.get("prezzo", 0),
                        "unita_misura": prodotto.get("unita_misura") or "PZ",
                    }
                    if prod_norm["descrizione"] and len(prod_norm["descrizione"]) >= 3:
                        await aggiorna_dizionario_prodotto(prod_norm, fattura_ctx, fattura_data.get("id", ""))
                except Exception as _de:
                    logger.debug(f"[fatture] aggiorna_dizionario skip: {_de}")

            # ── Riconciliazione automatica fattura ↔ ordine ──
            try:
                from app.lotti.routers.ordini_fornitori import riconcilia_fattura_con_ordine

                await riconcilia_fattura_con_ordine(
                    fornitore=fattura_data.get("fornitore", ""),
                    prodotti_fattura=fattura_data.get("prodotti", []),
                    fattura_id=fattura_data.get("id", ""),
                    data_fattura=data_fmt,
                )
            except Exception as _re:
                logger.debug(f"[fatture] riconciliazione ordine skip: {_re}")

        except Exception as e:
            risultati["errori"].append(f"{file.filename}: {str(e)}")

    # Trigger pipeline + aggiornamento ricette automatico
    if risultati["fatture_processate"] > 0:
        try:
            from app.lotti.routers.pipeline import esegui_pipeline_post_import
            from app.lotti.routers.aggiornamento_ricette import aggiorna_ricette_da_fattura
            import asyncio

            asyncio.create_task(
                esegui_pipeline_post_import(
                    motivo=f"xml_manuale_{risultati['fatture_processate']}_fatture"
                )
            )

            # Aggiorna ingredienti ricette con i dati delle fatture appena importate
            # Per ogni fattura processata, aggiorna le ricette che usano quegli ingredienti
            for file in files:
                try:
                    # Rileggi la fattura appena salvata dal DB per avere l'id
                    pass  # fatto nel loop sopra: la fattura è già in DB
                except Exception:
                    logger.debug("[fatture] errore non bloccante ignorato")

            # Aggiorna ricette per tutte le fatture processate (dalle ultime N)
            fatture_recenti = (
                await db.fatture.find({}, {"_id": 0})
                .sort("created_at", -1)
                .to_list(risultati["fatture_processate"])
            )

            for fatt in fatture_recenti:
                try:
                    res = await aggiorna_ricette_da_fattura(fatt)
                    if res.get("aggiornate", 0) > 0:
                        risultati.setdefault("ricette_aggiornate", 0)
                        risultati["ricette_aggiornate"] += res["aggiornate"]
                        risultati.setdefault("match_ingredienti_ricette", [])
                        risultati["match_ingredienti_ricette"].extend(res.get("match", []))
                except Exception as e:
                    logger.warning(f"[fatture] aggiornamento ricette fallito: {e}")

        except Exception as e:
            logger.warning(f"[fatture] Avvio pipeline post-import fallito: {e}")

    if job_id:
        try:
            await db.import_jobs.update_one(
                {"id": job_id},
                {"$set": {"stato": "completato", "processed": len(_expanded),
                          "ok": risultati["fatture_processate"], "errori": risultati["errori"],
                          "fine": datetime.now(timezone.utc).isoformat()}},
            )
        except Exception:
            logger.debug("[fatture] errore non bloccante ignorato")
    from app.lotti.eventi import publish
    await publish("FATTURA_IMPORTATA", {
        "fatture": risultati.get("fatture_processate", 0),
        "righe": risultati.get("prodotti_trovati", 0),
    })
    return risultati


async def _run_import_job(job_id, f_list):
    try:
        await importa_fattura_xml(f_list, job_id=job_id)
    except Exception as e:
        try:
            await db.import_jobs.update_one(
                {"id": job_id},
                {"$set": {"stato": "errore", "errore_fatale": str(e)[:200], "fine": datetime.now(timezone.utc).isoformat()}},
            )
        except Exception:
            logger.debug("[fatture] errore non bloccante ignorato")


@router.post("/prescan-fornitori")
async def prescan_fornitori(files: List[UploadFile] = File(...)):
    """Pre-scansione SENZA import: estrae i fornitori distinti dagli allegati
    (XML / ZIP / .p7m) e ritorna quelli ancora DA CLASSIFICARE (sconosciuti, in
    attesa o senza tipo_fornitura). Non scrive nulla: serve al frontend per far
    classificare i fornitori nuovi PRIMA di importare (così non inquinano catalogo,
    lotti e giacenze). La classificazione avviene poi via POST /fornitori/tipo-fornitura."""
    from app.lotti.routers.xml_helpers import parse_fattura_xml

    raws = []
    for up in files:
        raw = await up.read()
        nome = (up.filename or "").lower()
        if nome.endswith(".zip") or raw[:2] == b"PK":
            try:
                with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                    for zi in zf.namelist():
                        low = zi.lower()
                        if zi.endswith("/") or not (low.endswith(".xml") or low.endswith(".p7m")):
                            continue
                        raws.append(_estrai_xml(zf.read(zi)))
            except Exception:
                logger.debug("[fatture] prescan: zip non valido ignorato")
        else:
            raws.append(_estrai_xml(raw))

    distinti = {}  # nome → piva (prima occorrenza)
    for content in raws:
        try:
            d = parse_fattura_xml(content)
        except Exception:
            continue
        nm = (d.get("fornitore") or "").strip()
        if nm:
            distinti.setdefault(nm, d.get("piva") or "")

    da_classificare = []
    for nm, piva in distinti.items():
        info = await db.fornitori.find_one(
            {"$or": [
                {"nome": nm},
                {"nome": {"$regex": f"^{re.escape(nm)}$", "$options": "i"}},
            ]},
            {"_id": 0, "nome": 1, "escluso": 1, "in_attesa": 1, "tipo_fornitura": 1, "approvato_il": 1},
        )
        if not info:
            stato = "sconosciuto"
        elif info.get("in_attesa"):
            stato = "in_attesa"
        elif not info.get("tipo_fornitura"):
            stato = "non_classificato"
        else:
            stato = "ok"
        if stato != "ok":
            da_classificare.append({
                "fornitore": nm,
                "piva": piva,
                "stato": stato,
                "tipo_fornitura": (info or {}).get("tipo_fornitura") or "",
            })
    da_classificare.sort(key=lambda x: x["fornitore"].lower())
    return {"totale_fornitori": len(distinti), "da_classificare": da_classificare}


@router.post("/importa-async")
async def importa_async(files: List[UploadFile] = File(...), background: BackgroundTasks = None):
    """Avvia l'import in background e ritorna subito un job_id da interrogare via polling."""
    f_list = [_UF(up.filename, await up.read()) for up in files]
    job_id = str(uuid.uuid4())
    await db.import_jobs.insert_one({
        "id": job_id,
        "total": len(f_list),
        "processed": 0,
        "ok": 0,
        "errori": [],
        "stato": "in_corso",
        "inizio": datetime.now(timezone.utc).isoformat(),
    })
    if background is not None:
        background.add_task(_run_import_job, job_id, f_list)
    return {"job_id": job_id, "total": len(f_list)}


@router.get("/importa-job-attivo")
async def importa_job_attivo():
    """Ultimo job di importazione ancora in corso (per riprendere la barra dopo un reload).
    Auto-pulizia: i job 'in_corso' più vecchi di 30 minuti sono considerati
    interrotti (es. riavvio/sleep del server su Render free che uccide il task in
    background) e vengono chiusi, così la barra non resta accesa all'infinito."""
    j = await db.import_jobs.find_one({"stato": "in_corso"}, {"_id": 0}, sort=[("inizio", -1)])
    if not j:
        return {}
    try:
        inizio = datetime.fromisoformat(str(j.get("inizio", "")).replace("Z", "+00:00"))
        eta_min = (datetime.now(timezone.utc) - inizio).total_seconds() / 60
    except Exception:
        eta_min = 0
    if eta_min > 30:
        await db.import_jobs.update_one(
            {"id": j["id"]},
            {"$set": {"stato": "interrotto", "errore": "job stantio (riavvio server)"}},
        )
        return {}
    return j


@router.post("/importa-annulla")
async def importa_annulla(_admin=Depends(require_admin)):
    """Ferma/azzera i job di import 'in_corso' (sblocca una barra rimasta accesa)."""
    r = await db.import_jobs.update_many(
        {"stato": "in_corso"}, {"$set": {"stato": "interrotto", "errore": "annullato dall'utente"}}
    )
    return {"ok": True, "interrotti": r.modified_count}


@router.get("/importa-job/{job_id}")
async def importa_job_stato(job_id: str):
    j = await db.import_jobs.find_one({"id": job_id}, {"_id": 0})
    if not j:
        raise HTTPException(status_code=404, detail="job non trovato")
    return j


@router.post("/dedup")
async def dedup_fatture(_admin=Depends(require_admin)):
    """Rimuove le fatture duplicate già presenti in DB, raggruppando per la
    chiave canonica (regola Enzo): fornitore + numero_fattura + data_fattura —
    identica alla chiave di import/sync (single rule). Tiene il documento più
    completo (con prodotti) e più recente, elimina gli altri. Usare una tantum
    dopo aver corretto la chiave di import."""
    from collections import defaultdict

    gruppi = defaultdict(list)
    async for f in db.fatture.find({}, {"_id": 1, "id": 1, "numero_fattura": 1, "data_fattura": 1, "fornitore": 1, "prodotti": 1, "created_at": 1}):
        key = (f.get("fornitore") or "", f.get("numero_fattura") or "", f.get("data_fattura") or "")
        gruppi[key].append(f)

    rimossi = 0
    gruppi_dup = 0
    for key, docs in gruppi.items():
        if len(docs) <= 1:
            continue
        gruppi_dup += 1
        # tieni quello con più prodotti, a parità il più recente.
        # created_at può essere str (isoformat) o datetime BSON su doc vecchi:
        # forziamo str per un confronto omogeneo (niente TypeError).
        docs.sort(key=lambda d: (len(d.get("prodotti") or []), str(d.get("created_at") or "")), reverse=True)
        da_eliminare = [d["_id"] for d in docs[1:]]
        res = await db.fatture.delete_many({"_id": {"$in": da_eliminare}})
        rimossi += res.deleted_count

    return {"gruppi_duplicati": gruppi_dup, "fatture_rimosse": rimossi, "fatture_residue": await db.fatture.count_documents({})}

# ── Ricostruzione giacenze bar da fatture XML ────────────────────────────────
async def _esegui_ricostruzione_giacenze():
    """Corpo della ricostruzione (gira in background: ~20-30 min su Render free).
    Stato live in db.sistema_stato chiave 'ricostruzione_giacenze'."""
    from app.lotti.routers.lotti_produzione import _parse_data_fattura
    await db.sistema_stato.update_one(
        {"chiave": "ricostruzione_giacenze"},
        {"$set": {"stato": "in_corso", "avviata": datetime.now(timezone.utc).isoformat(),
                  "fatture_fatte": 0, "esito": None}}, upsert=True)
    await db.magazzino_bar_prodotti.update_many({}, {"$set": {"stock": 0}})
    # i carichi-fattura verranno riapplicati: via i vecchi (anche per l'idempotenza
    # per numero fattura); gli altri movimenti restano come storico.
    res_del = await db.magazzino_bar_movimenti.delete_many({"origine": "fattura"})
    await db.magazzino_bar_movimenti.insert_one({
        "id": str(uuid.uuid4()), "tipo": "ricostruzione", "quantita": 0,
        "nota": "Giacenze ricostruite da zero sommando le fatture XML in ordine di data",
        "operatore_nome": "titolare", "data": datetime.now(timezone.utc).isoformat(),
    })

    fatture = await db.fatture.find(
        {}, {"_id": 0, "prodotti": 1, "numero_fattura": 1, "fornitore": 1, "piva": 1, "data_fattura": 1}
    ).to_list(8000)
    fatture.sort(key=lambda f: _parse_data_fattura(f.get("data_fattura") or ""))

    # Dedup FORTE in memoria: lo stesso documento può esistere in più copie
    # (re-import / allineamenti). Chiave: numero normalizzato + P.IVA.
    visti = set()
    uniche = []
    for f in fatture:
        chiave = (str(f.get("numero_fattura") or "").strip().upper(),
                  str(f.get("piva") or f.get("fornitore") or "").strip().upper())
        if chiave in visti:
            continue
        visti.add(chiave)
        uniche.append(f)
    doc_doppi = len(fatture) - len(uniche)
    fatture = uniche

    lavorate, righe_caricate, prodotti_creati = 0, 0, 0
    for i, f in enumerate(fatture):
        r = await _carico_magazzino_bar_da_fattura(
            f.get("prodotti") or [], f.get("numero_fattura") or "", f.get("fornitore") or "")
        if isinstance(r, dict):
            lavorate += 1
            righe_caricate += int(r.get("caricati", 0) or 0)
            prodotti_creati += int(r.get("creati", 0) or 0)
        if i % 50 == 0:
            await db.sistema_stato.update_one(
                {"chiave": "ricostruzione_giacenze"},
                {"$set": {"fatture_fatte": i + 1, "fatture_totali": len(fatture)}})

    esito = {"fatture_in_ordine_di_data": len(fatture), "doc_doppi_saltati": doc_doppi,
             "fatture_lavorate": lavorate,
             "righe_caricate": righe_caricate, "prodotti_creati": prodotti_creati,
             "movimenti_fattura_azzerati": res_del.deleted_count}
    await db.sistema_stato.update_one(
        {"chiave": "ricostruzione_giacenze"},
        {"$set": {"stato": "completata", "completata": datetime.now(timezone.utc).isoformat(),
                  "fatture_fatte": len(fatture), "esito": esito}})


@router.post("/ricostruisci-giacenze-bar")
async def ricostruisci_giacenze_bar(request: Request, background_tasks: BackgroundTasks, forza: bool = False):
    """AVVIA in background la ricostruzione da zero delle giacenze bar sommando
    tutte le fatture XML in ordine di data. Risposta immediata; stato live su
    GET /fatture/ricostruisci-giacenze-bar/stato. Solo titolare (X-Admin-Pin)."""
    from app.lotti.routers.ordini_fornitori import _richiedi_admin
    await _richiedi_admin(request)
    st = await db.sistema_stato.find_one({"chiave": "ricostruzione_giacenze"}, {"_id": 0})
    if st and st.get("stato") == "in_corso" and not forza:
        # se un deploy ha ucciso la corsa, lo stato resta "in_corso": riavvia con ?forza=true
        return {"ok": True, "gia_in_corso": True, "stato": st,
                "nota": "Se la corsa è stata interrotta da un deploy, rilancia con ?forza=true"}
    background_tasks.add_task(_esegui_ricostruzione_giacenze)
    return {"ok": True, "avviata": True,
            "nota": "Ricostruzione avviata in background (~20-30 min). Stato: GET /fatture/ricostruisci-giacenze-bar/stato"}


@router.get("/ricostruisci-giacenze-bar/stato")
async def stato_ricostruzione_giacenze():
    st = await db.sistema_stato.find_one({"chiave": "ricostruzione_giacenze"}, {"_id": 0})
    return st or {"stato": "mai_eseguita"}



def _norm_piva(v: str) -> str:
    """Normalizza una P.IVA per il confronto: maiuscolo, senza spazi, senza prefisso IT."""
    p = (v or "").strip().upper().replace(" ", "")
    if p.startswith("IT"):
        p = p[2:]
    return p


@router.post("/backfill-fornitore-debole")
async def backfill_fornitore_debole():
    """Ricollega le fatture con fornitore mancante/sconosciuto: ricava il NOME del
    fornitore dalla P.IVA usando (1) l'anagrafica db.fornitori e (2) — quando lì manca —
    ALTRE fatture con la STESSA P.IVA che hanno già il fornitore valorizzato (stesso
    fornitore, fatture diverse: capita quando solo una fattura arriva senza intestazione
    leggibile). Il rebuild di prodotti_master legge il fornitore dalla testata fattura,
    quindi dopo questo va rilanciato il rebuild. Non tocca le fatture che hanno già un
    fornitore valido."""
    # Mappa P.IVA → nome dall'anagrafica fornitori
    piva2nome: dict[str, str] = {}
    async for fd in db.fornitori.find({}, {"_id": 0, "nome": 1, "piva": 1, "partita_iva": 1}):
        nome = (fd.get("nome") or "").strip()
        if not nome:
            continue
        for pk in ("piva", "partita_iva"):
            pv = _norm_piva(fd.get(pk) or "")
            if pv and len(pv) >= 8 and pv not in piva2nome:
                piva2nome[pv] = nome
    # Fallback: P.IVA note solo dentro altre fatture (stessa P.IVA, fornitore già scritto
    # su un'ALTRA fattura) — non richiede anagrafica esterna, i dati sono già in db.fatture.
    da_fatture = 0
    async for fd in db.fatture.find(
        {"fornitore": {"$nin": [None, ""]}, "piva": {"$nin": [None, ""]}},
        {"_id": 0, "fornitore": 1, "piva": 1},
    ):
        nome = (fd.get("fornitore") or "").strip()
        if not nome or re.search("sconosciut", nome, re.IGNORECASE):
            continue
        pv = _norm_piva(fd.get("piva") or "")
        if pv and len(pv) >= 8 and pv not in piva2nome:
            piva2nome[pv] = nome
            da_fatture += 1
    debole_q = {"$or": [
        {"fornitore": {"$exists": False}},
        {"fornitore": ""},
        {"fornitore": None},
        {"fornitore": {"$regex": "sconosciut", "$options": "i"}},
    ]}
    fatture = await db.fatture.find(
        debole_q, {"_id": 1, "numero_fattura": 1, "piva": 1, "fornitore": 1}
    ).to_list(100000)
    ricollegate = senza_piva = piva_non_in_anagrafica = 0
    esempi = []
    for f in fatture:
        pv = _norm_piva(f.get("piva") or "")
        if not pv or len(pv) < 8:
            senza_piva += 1
            continue
        nome = piva2nome.get(pv)
        if not nome:
            piva_non_in_anagrafica += 1
            continue
        await db.fatture.update_one({"_id": f["_id"]}, {"$set": {"fornitore": nome}})
        ricollegate += 1
        if len(esempi) < 15:
            esempi.append({"numero": f.get("numero_fattura"), "piva": pv, "nuovo_fornitore": nome})
    return {
        "ok": True,
        "fatture_fornitore_debole": len(fatture),
        "ricollegate": ricollegate,
        "senza_piva": senza_piva,
        "piva_non_in_anagrafica": piva_non_in_anagrafica,
        "piva_trovate_via_altre_fatture": da_fatture,
        "nota": "Rilancia POST /prodotti-master/rebuild per propagare il fornitore al catalogo.",
        "esempi": esempi,
    }


@router.post("/riparse-fornitore-mancante")
async def riparse_fornitore_mancante():
    """
    Recupera il NOME del fornitore per le fatture che hanno P.IVA ma fornitore
    vuoto, ri-parsando l'XML grezzo (xml_raw) col parser corretto: ora gestisce
    le ditte individuali (Nome+Cognome) e isola il blocco CedentePrestatore.
    Non inventa nulla: il nome esce dall'XML reale della fattura.
    """
    from app.lotti.routers.xml_helpers import parse_fattura_xml

    recuperate = senza_xml = xml_senza_nome = 0
    esempi = []
    irrisolte = []
    fatture = await db.fatture.find(
        {"$or": [{"fornitore": {"$in": ["", None]}}, {"fornitore": {"$exists": False}}]},
        {"_id": 1, "numero_fattura": 1, "piva": 1, "fornitore": 1, "xml_raw": 1},
    ).to_list(100000)
    for f in fatture:
        xml_raw = f.get("xml_raw")
        if not xml_raw:
            senza_xml += 1
            irrisolte.append({"numero": f.get("numero_fattura"), "piva": f.get("piva"), "motivo": "nessun xml_raw"})
            continue
        try:
            xb = xml_raw.encode("utf-8") if isinstance(xml_raw, str) else xml_raw
            parsed = parse_fattura_xml(xb)
        except Exception as e:
            irrisolte.append({"numero": f.get("numero_fattura"), "piva": f.get("piva"), "motivo": f"parse: {str(e)[:40]}"})
            continue
        nome = (parsed.get("fornitore") or "").strip()
        if not nome:
            xml_senza_nome += 1
            irrisolte.append({"numero": f.get("numero_fattura"), "piva": f.get("piva"), "motivo": "xml senza nome"})
            continue
        await db.fatture.update_one({"_id": f["_id"]}, {"$set": {"fornitore": nome}})
        recuperate += 1
        if len(esempi) < 20:
            esempi.append({"numero": f.get("numero_fattura"), "piva": f.get("piva"), "nuovo_fornitore": nome})
    return {
        "ok": True,
        "fatture_senza_nome": len(fatture),
        "recuperate_da_xml": recuperate,
        "senza_xml": senza_xml,
        "xml_senza_nome": xml_senza_nome,
        "esempi": esempi,
        "irrisolte": irrisolte[:30],
        "nota": "Poi POST /prodotti-master/rebuild per propagare il fornitore al catalogo.",
    }


# ── Dizionario prodotti per Food Cost (spostata da pec_import) ───────────────
async def aggiorna_dizionario_prodotto(prodotto: dict, fattura_data: dict, fattura_id: str):
    """Aggiorna dizionario prodotti per Food Cost"""
    from app.lotti.routers.xml_helpers import calcola_prezzo_quantita_kg
    descrizione = prodotto.get("descrizione", "").strip()
    if not descrizione:
        return

    nome_normalizzato = descrizione.lower()
    nome_normalizzato = re.sub(r"\s+", " ", nome_normalizzato)

    try:
        quantita = float(str(prodotto.get("quantita", "1")).replace(",", "."))
        prezzo = float(str(prodotto.get("prezzo", "0")).replace(",", "."))
    except Exception:
        quantita = 1
        prezzo = 0
        # prezzo/quantità non parsabili → food cost a zero per questo prodotto:
        # va segnalato, non azzerato in silenzio (era un buco muto).
        logger.warning(
            f"[Dizionario] prezzo/quantità non parsabili per '{descrizione[:60]}' "
            f"(qta={prodotto.get('quantita')!r}, prezzo={prodotto.get('prezzo')!r}) "
            f"→ salvato con prezzo 0: food cost da verificare."
        )

    # Letto PRIMA del calcolo: serve alla PRIORITÀ 0 di calcola_prezzo_quantita_kg (regola
    # già nota per questo prodotto) e viene riusato sotto per decidere insert/update —
    # una sola query, stesso documento (bug corretto 01/07/2026: vedi STATO.md).
    prodotto_esistente = await db.dizionario_prodotti.find_one(
        {"nome_normalizzato": nome_normalizzato}
    )

    calcolo = calcola_prezzo_quantita_kg(
        quantita=quantita,
        prezzo=prezzo,
        unita_misura_fattura=prodotto.get("unita_misura"),
        descrizione=descrizione,
        regola_nota=prodotto_esistente,
    )
    prezzo_kg = calcolo["prezzo_kg"]
    quantita_kg = calcolo["quantita_kg"]
    peso_confezione_det = calcolo["peso_confezione_det"]
    unita_confezione_det = calcolo["unita_confezione_det"]
    tipo_quantita_det = calcolo["tipo_quantita_det"]

    # Controllo di plausibilità: la PRIORITÀ 0 (regola_nota già salvata) vince
    # sempre in calcola_prezzo_quantita_kg, ma se il fornitore in QUESTA fattura
    # ha cambiato confezionamento (es. da secchiello 5kg a vaschette 125g) la
    # regola vecchia produce un prezzo_kg sballato di uno o più ordini di
    # grandezza — è la causa concreta di alert tipo "prezzo diminuito del 99%"
    # che sono in realtà solo un mismatch di unità di misura, non un vero
    # cambio prezzo. Se lo scostamento supera 10x rispetto all'ultimo prezzo
    # noto, non fidarsi della regola nota per QUESTA riga: ricalcola ignorandola.
    if (
        prodotto_esistente
        and calcolo["fonte"] in ("regola_nota_confezioni", "regola_nota_totale")
        and prezzo_kg
    ):
        prezzo_vecchio_check = float(
            prodotto_esistente.get("prezzo_kg") or prodotto_esistente.get("ultimo_prezzo_kg") or 0
        )
        if prezzo_vecchio_check > 0 and (
            prezzo_kg > prezzo_vecchio_check * 10 or prezzo_kg < prezzo_vecchio_check / 10
        ):
            calcolo = calcola_prezzo_quantita_kg(
                quantita=quantita,
                prezzo=prezzo,
                unita_misura_fattura=prodotto.get("unita_misura"),
                descrizione=descrizione,
                regola_nota=None,
            )
            prezzo_kg = calcolo["prezzo_kg"]
            quantita_kg = calcolo["quantita_kg"]
            peso_confezione_det = calcolo["peso_confezione_det"]
            unita_confezione_det = calcolo["unita_confezione_det"]
            tipo_quantita_det = calcolo["tipo_quantita_det"]

    if prodotto_esistente:
        nuovo_totale = prodotto_esistente.get("quantita_totale_kg", 0) + quantita_kg
        prezzo_vecchio = float(
            prodotto_esistente.get("prezzo_kg") or prodotto_esistente.get("ultimo_prezzo_kg") or 0
        )

        set_fields = {
            "quantita_totale_kg": round(nuovo_totale, 3),
            "quantita_disponibile_kg": round(
                nuovo_totale - prodotto_esistente.get("quantita_usata_kg", 0), 3
            ),
            "prezzo_precedente_kg": prezzo_vecchio,
            "ultima_fattura": fattura_id,
            "ultima_fattura_data": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "data_aggiornamento": datetime.now(timezone.utc).isoformat(),
            # ultimo acquisto COME IN FATTURA (riga XML): servono alla pagina
            # Dizionario per far riconoscere il prodotto a Enzo senza ricerche
            # (richiesta 04/07/2026: "prezzo, quantità — litro/boccione/cartone
            # — e unità di misura accanto alla riga")
            "ultimo_prezzo_riga": prezzo,
            "ultima_quantita_riga": quantita,
            "ultima_unita_riga": (prodotto.get("unita_misura") or "").strip(),
        }
        # Prezzo corrente = ultimo acquisto reale in fattura. prezzo_kg è il campo
        # letto da food-cost/ricette/riordini/confronto: senza questo update
        # restava congelato al primo prezzo storico. Le righe omaggio (prezzo 0 →
        # prezzo_kg None) NON azzerano il prezzo noto.
        if prezzo_kg:
            set_fields["ultimo_prezzo_kg"] = prezzo_kg
            set_fields["prezzo_kg"] = prezzo_kg
        # Aliquota IVA dall'XML (serve ai totali degli ordini fornitori)
        try:
            iva_riga = float(str(prodotto.get("iva", "") or "").replace(",", "."))
            if iva_riga > 0:
                set_fields["iva_pct"] = iva_riga
        except (TypeError, ValueError):
            pass
        # Non sovrascrivere un peso già corretto a mano da Enzo; altrimenti salva/aggiorna
        # il peso (+tipo_quantita) determinato ora, così resta memorizzato per la
        # PRIORITÀ 0 della prossima fattura (il "motore che si ricorda" richiesto da Enzo).
        if peso_confezione_det and not prodotto_esistente.get("peso_corretto_manualmente"):
            set_fields["peso_confezione"] = peso_confezione_det
            set_fields["unita_confezione"] = unita_confezione_det
            if tipo_quantita_det:
                set_fields["tipo_quantita"] = tipo_quantita_det

        await db.dizionario_prodotti.update_one(
            {"nome_normalizzato": nome_normalizzato},
            {
                "$set": set_fields,
                "$inc": {"conteggio_acquisti": 1},
            },
        )

        # ── Alert variazione prezzo > 5% ─────────────────────────────────────
        if prezzo_vecchio and prezzo_kg and prezzo_vecchio > 0:
            delta_pct = ((prezzo_kg - prezzo_vecchio) / prezzo_vecchio) * 100
            # Uno scostamento >90% (prezzo che crolla/esplode di oltre 10x) non è
            # mai un vero cambio prezzo in pasticceria: è quasi certamente un
            # mismatch di unità di misura sfuggito al ricalcolo sopra. Non
            # generare un alert-spazzatura ("prezzo diminuito del 99.9%") che
            # confonde e non serve: solo un log per diagnosi.
            if abs(delta_pct) >= 90.0:
                logger.warning(
                    f"[PrezzoAlert] scartato delta implausibile per '{nome_normalizzato}': "
                    f"{prezzo_vecchio:.3f} -> {prezzo_kg:.3f} €/kg ({delta_pct:.1f}%) — "
                    f"probabile mismatch unità di misura, non un vero cambio prezzo."
                )
            elif abs(delta_pct) >= 5.0:
                nome_display = (
                    prodotto_esistente.get("nome_canonico") or nome_normalizzato or ""
                ).title()
                direzione = "aumentato" if delta_pct > 0 else "diminuito"
                segno = "+" if delta_pct > 0 else ""
                ricette_impattate = await db.ricette.find(
                    {
                        "ingredienti": {
                            "$elemMatch": {"$regex": nome_normalizzato[:15], "$options": "i"}
                        }
                    },
                    {"_id": 0, "nome": 1},
                ).to_list(5)
                note_ricette = ""
                if ricette_impattate:
                    note_ricette = (
                        f" Ricette: {', '.join(r['nome'] for r in ricette_impattate[:3])}."
                    )
                await db.alert_prezzi.insert_one(
                    {
                        "id": str(uuid.uuid4()),
                        "tipo": "PREZZO_INGREDIENTE",
                        "titolo": f"{nome_display}: prezzo {direzione} del {segno}{delta_pct:.1f}%",
                        "descrizione": (
                            f"'{nome_display}' è passato da €{prezzo_vecchio:.3f}/kg a €{prezzo_kg:.3f}/kg "
                            f"({segno}{delta_pct:.1f}%).{note_ricette} Verificare il food cost."
                        ),
                        "priorita": "alta" if abs(delta_pct) >= 15 else "media",
                        # Un alert di prezzo riguarda un INGREDIENTE, non una ricetta
                        # specifica: "comparatore" apre la pagina che mostra davvero
                        # quel prodotto, non una ricetta a caso.
                        "route": "comparatore",
                        "valore": round(delta_pct, 1),
                        "nome_ingrediente": nome_display,
                        "prezzo_vecchio": prezzo_vecchio,
                        "prezzo_nuovo": prezzo_kg,
                        "ricette_impattate": [r["nome"] for r in ricette_impattate],
                        "creato_il": datetime.now(timezone.utc).isoformat(),
                        "letto": False,
                    }
                )
                logger.info(f"[PrezzoAlert] {nome_display}: {segno}{delta_pct:.1f}%")
    else:
        # Auto-classifica subito il canonico (L1→L2, niente LLM per non rallentare l'import).
        _canonico_auto = ""
        try:
            from app.lotti.routers.ingredienti import match_livello1, match_livello2
            _canonico_auto = (await match_livello1(descrizione)) or match_livello2(descrizione) or ""
        except Exception:
            _canonico_auto = ""
        await db.dizionario_prodotti.insert_one(
            {
                "id": str(uuid.uuid4()),
                "nome_originale": descrizione,
                "nome_normalizzato": nome_normalizzato,
                "ingrediente_canonico": _canonico_auto,
                "fornitore": fattura_data.get("fornitore"),
                "fornitore_piva": fattura_data.get("piva"),
                "prezzo_kg": prezzo_kg,
                "ultimo_prezzo_kg": prezzo_kg,
                **({"iva_pct": float(str(prodotto.get("iva")).replace(",", "."))}
                   if str(prodotto.get("iva") or "").replace(",", ".").replace(".", "", 1).isdigit()
                   else {}),
                "quantita_totale_kg": round(quantita_kg, 3),
                "quantita_usata_kg": 0,
                "quantita_disponibile_kg": round(quantita_kg, 3),
                "ultima_fattura": fattura_id,
                "ultima_fattura_data": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "ultimo_prezzo_riga": prezzo,
                "ultima_quantita_riga": quantita,
                "ultima_unita_riga": (prodotto.get("unita_misura") or "").strip(),
                "conteggio_acquisti": 1,
                "data_creazione": datetime.now(timezone.utc).isoformat(),
                **({"peso_confezione": peso_confezione_det,
                    "unita_confezione": unita_confezione_det,
                    **({"tipo_quantita": tipo_quantita_det} if tipo_quantita_det else {})}
                   if peso_confezione_det else {}),
            }
        )


# ── Backfill aliquote IVA dai XML già archiviati ──────────────────────────────
@router.post("/backfill-iva")
async def backfill_iva():
    """Una tantum: rilegge gli xml_raw delle fatture archiviate, estrae
    l'AliquotaIVA di ogni riga e la salva su dizionario_prodotti.iva_pct
    (ultima aliquota vista per prodotto). Serve ai totali degli ordini."""
    from app.lotti.routers.xml_helpers import parse_fattura_xml
    aggiornati = 0
    esaminate = 0
    per_nome: dict = {}
    async for f in db.fatture.find({"xml_raw": {"$exists": True, "$nin": [None, ""]}},
                                     {"_id": 0, "xml_raw": 1, "data_fattura": 1}):
        esaminate += 1
        try:
            dati = parse_fattura_xml(f["xml_raw"].encode("utf-8", errors="replace"))
        except Exception:
            continue
        for r in dati.get("prodotti", []):
            desc = (r.get("descrizione") or "").strip().lower()
            iva_raw = str(r.get("iva") or "").replace(",", ".")
            try:
                iva = float(iva_raw)
            except ValueError:
                continue
            if desc and iva > 0:
                per_nome[desc] = iva  # l'ultima vista vince
    for nome_norm, iva in per_nome.items():
        res = await db.dizionario_prodotti.update_one(
            {"nome_normalizzato": nome_norm}, {"$set": {"iva_pct": iva}})
        aggiornati += res.modified_count
    return {"ok": True, "fatture_esaminate": esaminate,
            "prodotti_con_iva": len(per_nome), "dizionario_aggiornati": aggiornati}


# ── Backfill codici articolo dai XML già archiviati ───────────────────────────
@router.post("/backfill-codici-articolo")
async def backfill_codici_articolo():
    """Una tantum: rilegge gli xml_raw delle fatture archiviate ed estrae il
    CodiceArticolo di ogni riga (il parser lo salva solo dagli import nuovi).
    Il codice del fornitore è identico a quello dei suoi cataloghi (Bindi,
    Il Pasticcere, Tre Marie, Saima...): con questo backfill l'aggancio
    prezzo<->catalogo diventa deterministico anche per gli acquisti passati."""
    from app.lotti.routers.xml_helpers import parse_fattura_xml
    esaminate = 0
    fatture_agg = 0
    righe_agg = 0
    async for f in db.fatture.find(
        {"xml_raw": {"$exists": True, "$nin": [None, ""]}},
        {"_id": 0, "id": 1, "xml_raw": 1, "prodotti": 1},
    ):
        esaminate += 1
        try:
            dati = parse_fattura_xml(f["xml_raw"].encode("utf-8", errors="replace"))
        except Exception:
            continue
        codici = {}
        for r in dati.get("prodotti", []):
            desc = (r.get("descrizione") or "").strip().lower()
            cod = (r.get("codice_articolo") or "").strip()
            if desc and cod:
                codici[desc] = cod
        if not codici:
            continue
        prods = f.get("prodotti") or []
        changed = False
        for p in prods:
            if not isinstance(p, dict) or p.get("codice_articolo"):
                continue
            cod = codici.get((p.get("descrizione") or "").strip().lower())
            if cod:
                p["codice_articolo"] = cod
                righe_agg += 1
                changed = True
        if changed:
            await db.fatture.update_one({"id": f["id"]}, {"$set": {"prodotti": prods}})
            fatture_agg += 1
    return {"ok": True, "fatture_esaminate": esaminate,
            "fatture_aggiornate": fatture_agg, "righe_con_codice": righe_agg}


# ── Recupero link righe-fattura → prodotto ─────────────────────────────────────
# Le fatture rimappate da invoices non portano i campi-link. Backfill idempotente:
# imposta nome_canonico (via normalizzatore del progetto) sulle righe prive di
# QUALSIASI campo-link, così "Righe fattura senza link prodotto" torna a posto.
@router.post("/ricollega-righe")
async def ricollega_righe_fatture():
    from app.lotti.routers.prodotti_master import normalize_nome
    _LINK = ("prodotto_master_id", "master_id", "prodotto_id", "prodotto_key",
             "prodotto_dizionario_id", "nome_canonico", "nome_canc")
    fatture_agg = 0
    righe_agg = 0
    async for f in db.fatture.find({}, {"id": 1, "prodotti": 1}):
        prods = f.get("prodotti") or []
        changed = False
        for p in prods:
            if not isinstance(p, dict):
                continue
            if any(p.get(k) for k in _LINK):
                continue
            desc = (p.get("descrizione") or "").strip()
            if len(desc) < 2:
                continue
            nc = normalize_nome(desc)
            if not nc:
                continue
            p["nome_canonico"] = nc
            p["prodotto_key"] = re.sub(r"[^a-z0-9]+", " ", nc.lower()).strip()
            changed = True
            righe_agg += 1
        if changed and f.get("id"):
            await db.fatture.update_one({"id": f["id"]}, {"$set": {"prodotti": prods}})
            fatture_agg += 1
    return {"ok": True, "fatture_aggiornate": fatture_agg, "righe_collegate": righe_agg}
