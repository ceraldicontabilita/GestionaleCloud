"""
corrispettivi.py — Sezione Corrispettivi (incassi giornalieri).

Stessa logica delle fatture: la collection `corrispettivi` è di proprietà di
Lotti (import controllato, idempotente per data), non sincronizzata dall'ERP.

Questo modulo NON inventa lo schema: il campo data è noto (indice su `data`),
il campo importo viene RILEVATO dal documento reale tra candidati noti (e in
fallback dal campo numerico più grande), e l'endpoint /schema mostra cosa ha
rilevato così è verificabile.

Espone:
- GET  /corrispettivi/schema        → chiavi di un doc reale + campo importo rilevato
- GET  /corrispettivi/andamento     → serie temporale (giorno/settimana/mese) + confronto anno precedente
- GET  /corrispettivi/riepilogo     → oggi/settimana/mese/anno con delta vs anno prima
- POST /corrispettivi               → inserimento/aggiornamento manuale (idempotente per data)
"""

import xml.etree.ElementTree as ET
from datetime import datetime, date, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel
from app.lotti.db import database as db

router = APIRouter(prefix="/corrispettivi", tags=["Corrispettivi"])

# Possibili nomi del campo importo nelle collection corrispettivi reali.
# Non si inventano valori: si sceglie tra questi quello PRESENTE nel documento.
# `totale_giorno` è il campo scritto dall'import XML COR10 (vedi sotto).
CANDIDATI_IMPORTO = [
    "totale_giorno", "importo", "totale", "corrispettivo", "corrispettivi",
    "incasso", "imponibile", "ammontare", "total", "totale_corrispettivi",
]
CANDIDATI_DATA = ["data", "data_corrispettivo", "giorno", "date"]


def _to_float(v) -> float:
    try:
        if isinstance(v, str):
            v = v.replace("€", "").replace(".", "").replace(",", ".").strip() if "," in v else v
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _rileva_campo_importo(doc: dict) -> Optional[str]:
    """Rileva il campo importo da un documento reale, senza inventarlo."""
    for c in CANDIDATI_IMPORTO:
        if c in doc and _to_float(doc[c]) != 0:
            return c
    # fallback: il campo numerico col valore assoluto più grande (escluse le date)
    best, best_val = None, 0.0
    for k, v in doc.items():
        if k in CANDIDATI_DATA or k.startswith("_"):
            continue
        val = abs(_to_float(v))
        if val > best_val:
            best, best_val = k, val
    return best


def _rileva_campo_data(doc: dict) -> Optional[str]:
    for c in CANDIDATI_DATA:
        if c in doc:
            return c
    return None


def _parse_data(v) -> Optional[date]:
    """Normalizza una data (stringa ISO/IT o datetime) in date."""
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v or "").strip()[:10]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


async def _campi_rilevati() -> tuple[Optional[str], Optional[str]]:
    doc = await db.corrispettivi.find_one({}, {"_id": 0})
    if not doc:
        return None, None
    return _rileva_campo_data(doc), _rileva_campo_importo(doc)


# ── Parser corrispettivi telematici Agenzia Entrate (COR10/RT) ────────────────
def _ln(tag: str) -> str:
    """local-name di un tag namespaced ({ns}Nome -> Nome)."""
    return tag.split("}")[-1]


def _txt(root, nome: str) -> Optional[str]:
    for e in root.iter():
        if _ln(e.tag) == nome:
            return (e.text or "").strip()
    return None


def _parse_corrispettivo_xml(content: bytes) -> dict:
    """Estrae da un XML COR10 il totale vendite del giorno.

    'Totale giorno vendite' = PagatoContanti + PagatoElettronico (incasso lordo).
    Giorni inattivi (PeriodoInattivo) → totale 0, data = Dal.
    Fallback se i campi Pagato mancano: somma di (Ammontare + Imposta) dei Riepilogo.
    """
    root = ET.fromstring(content)

    # Giorno inattivo (chiusura)
    inattivo = None
    for e in root.iter():
        if _ln(e.tag) == "PeriodoInattivo":
            inattivo = e
            break
    if inattivo is not None:
        d = _parse_data(_txt(inattivo, "Dal"))
        return {
            "data": d.isoformat() if d else None,
            "totale_giorno": 0.0, "contanti": 0.0, "elettronico": 0.0,
            "n_documenti": 0, "inattivo": True,
            "progressivo": _txt(root, "Progressivo"),
            "dispositivo": _txt(root, "IdDispositivo"),
        }

    d = _parse_data(_txt(root, "DataOraRilevazione"))
    contanti = _to_float(_txt(root, "PagatoContanti"))
    elettronico = _to_float(_txt(root, "PagatoElettronico"))
    totale = round(contanti + elettronico, 2)
    if totale == 0:
        # fallback: imponibile + imposta su tutti i Riepilogo
        tot = 0.0
        for e in root.iter():
            if _ln(e.tag) == "Riepilogo":
                tot += _to_float(_txt(e, "Ammontare")) + _to_float(_txt(e, "Imposta"))
        totale = round(tot, 2)
    return {
        "data": d.isoformat() if d else None,
        "totale_giorno": totale,
        "contanti": contanti,
        "elettronico": elettronico,
        "n_documenti": int(_to_float(_txt(root, "NumeroDocCommerciali"))),
        "inattivo": False,
        "progressivo": _txt(root, "Progressivo"),
        "dispositivo": _txt(root, "IdDispositivo"),
    }


@router.post("/importa-xml")
async def importa_xml(files: list[UploadFile] = File(...)):
    """Import manuale dei corrispettivi telematici (XML COR10), idempotente per
    data. Stessa logica delle fatture: i dati entrano in modo esplicito nel
    perimetro di Lotti, non sincronizzati dall'ERP."""
    risultati = []
    importati = 0
    for f in files:
        try:
            rec = _parse_corrispettivo_xml(await f.read())
        except Exception as e:
            risultati.append({"file": f.filename, "errore": f"XML non valido: {e}"})
            continue
        if not rec.get("data"):
            risultati.append({"file": f.filename, "errore": "data non riconosciuta"})
            continue
        await db.corrispettivi.update_one(
            {"data": rec["data"]},
            {"$set": {**rec, "origine": "xml_rt", "updated_at": datetime.utcnow().isoformat()}},
            upsert=True,
        )
        importati += 1
        risultati.append({"file": f.filename, **rec})
    return {"importati": importati, "totale_file": len(files), "dettaglio": risultati}


@router.get("/schema")
async def schema_corrispettivi():
    """Mostra le chiavi di un documento reale e i campi rilevati (verificabile)."""
    doc = await db.corrispettivi.find_one({}, {"_id": 0})
    if not doc:
        return {"presente": False, "messaggio": "Collection corrispettivi vuota"}
    campo_data, campo_importo = _rileva_campo_data(doc), _rileva_campo_importo(doc)
    n = await db.corrispettivi.count_documents({})
    return {
        "presente": True,
        "documenti": n,
        "chiavi": list(doc.keys()),
        "campo_data_rilevato": campo_data,
        "campo_importo_rilevato": campo_importo,
        "esempio": doc,
    }


async def _serie(campo_data: str, campo_importo: str, dal: date, al: date) -> dict:
    """Somma incassi per giorno tra dal e al (inclusi)."""
    docs = await db.corrispettivi.find({}, {"_id": 0}).to_list(20000)
    per_giorno: dict[str, float] = {}
    for d in docs:
        g = _parse_data(d.get(campo_data))
        if not g or g < dal or g > al:
            continue
        per_giorno[g.isoformat()] = per_giorno.get(g.isoformat(), 0.0) + _to_float(d.get(campo_importo))
    return per_giorno


@router.get("/andamento")
async def andamento(
    da: Optional[str] = None,
    a: Optional[str] = None,
    granularita: str = "giorno",  # giorno | settimana | mese
    confronto_anno_precedente: bool = True,
):
    """Serie temporale degli incassi, con confronto sullo stesso periodo dell'anno
    precedente. Le date assenti default: ultimi 30 giorni."""
    campo_data, campo_importo = await _campi_rilevati()
    if not campo_data or not campo_importo:
        raise HTTPException(404, "Collection corrispettivi vuota o schema non riconosciuto")

    oggi = date.today()
    al = _parse_data(a) or oggi
    dal = _parse_data(da) or (al - timedelta(days=30))

    def aggrega(per_giorno: dict) -> list:
        buckets: dict[str, float] = {}
        for giorno_iso, val in per_giorno.items():
            g = date.fromisoformat(giorno_iso)
            if granularita == "mese":
                k = g.strftime("%Y-%m")
            elif granularita == "settimana":
                iso = g.isocalendar()
                k = f"{iso[0]}-W{iso[1]:02d}"
            else:
                k = giorno_iso
            buckets[k] = round(buckets.get(k, 0.0) + val, 2)
        return [{"periodo": k, "incasso": v} for k, v in sorted(buckets.items())]

    serie = aggrega(await _serie(campo_data, campo_importo, dal, al))
    risultato = {
        "da": dal.isoformat(),
        "a": al.isoformat(),
        "granularita": granularita,
        "campo_importo": campo_importo,
        "serie": serie,
        "totale": round(sum(p["incasso"] for p in serie), 2),
    }
    if confronto_anno_precedente:
        dal_p = dal.replace(year=dal.year - 1)
        al_p = al.replace(year=al.year - 1)
        serie_p = aggrega(await _serie(campo_data, campo_importo, dal_p, al_p))
        tot_p = round(sum(p["incasso"] for p in serie_p), 2)
        risultato["anno_precedente"] = {
            "da": dal_p.isoformat(),
            "a": al_p.isoformat(),
            "serie": serie_p,
            "totale": tot_p,
        }
        risultato["delta_pct"] = (
            round((risultato["totale"] - tot_p) / tot_p * 100, 1) if tot_p else None
        )
    return risultato


@router.get("/riepilogo")
async def riepilogo():
    """Incasso di oggi, settimana, mese e anno, con confronto anno precedente."""
    campo_data, campo_importo = await _campi_rilevati()
    if not campo_data or not campo_importo:
        raise HTTPException(404, "Collection corrispettivi vuota o schema non riconosciuto")
    oggi = date.today()

    async def somma(dal: date, al: date) -> float:
        per_giorno = await _serie(campo_data, campo_importo, dal, al)
        return round(sum(per_giorno.values()), 2)

    inizio_sett = oggi - timedelta(days=oggi.weekday())
    inizio_mese = oggi.replace(day=1)
    inizio_anno = oggi.replace(month=1, day=1)

    async def con_delta(dal, al):
        cur = await somma(dal, al)
        prec = await somma(dal.replace(year=dal.year - 1), al.replace(year=al.year - 1))
        delta = round((cur - prec) / prec * 100, 1) if prec else None
        return {"valore": cur, "anno_precedente": prec, "delta_pct": delta}

    return {
        "campo_importo": campo_importo,
        "oggi": await con_delta(oggi, oggi),
        "settimana": await con_delta(inizio_sett, oggi),
        "mese": await con_delta(inizio_mese, oggi),
        "anno": await con_delta(inizio_anno, oggi),
    }


# ── Correlazione incassi ↔ ordini ──────────────────────────────────────────────
# Stati che rappresentano una spesa reale (ordine effettivamente piazzato/ricevuto),
# non le bozze.
_STATI_SPESA = ["inviato", "inviato_fornitori", "confermato", "ricevuto", "ricevuto_parziale"]


async def _spesa_ordini(dal: date, al: date) -> tuple[float, int]:
    """Spesa per ordini fornitore nel periodo [dal, al]. Usa importo_totale se
    presente, altrimenti somma le righe (quantita * prezzo). Non inventa: legge i
    campi reali con fallback."""
    docs = await db.ordini_fornitori.find(
        {"stato": {"$in": _STATI_SPESA}},
        {"_id": 0, "data_ordine": 1, "created_at": 1, "importo_totale": 1, "prodotti": 1},
    ).to_list(20000)
    tot, n = 0.0, 0
    for o in docs:
        g = _parse_data(o.get("data_ordine") or str(o.get("created_at") or "")[:10])
        if not g or g < dal or g > al:
            continue
        imp = float(o.get("importo_totale") or 0)
        if imp <= 0:
            for r in o.get("prodotti") or []:
                q = _to_float(r.get("quantita"))
                p = _to_float(r.get("prezzo_ultimo")) or _to_float(r.get("prezzo")) or _to_float(r.get("prezzo_kg"))
                imp += q * p
        tot += imp
        n += 1
    return round(tot, 2), n


def _verdetto_correlazione(corrente: dict, precedente: dict) -> tuple[str, Optional[bool]]:
    """Stabilisce se l'aumento degli ordini è giustificato dall'incasso."""
    ic, ip = corrente.get("incidenza_pct"), precedente.get("incidenza_pct")
    if ic is None:
        return ("Nessun incasso nel periodo: impossibile valutare la giustificazione.", None)
    if ip is None:
        return ("Manca lo storico del periodo precedente per il confronto.", None)
    spesa_su = corrente["spesa_ordini"] > precedente["spesa_ordini"] + 0.01
    delta = round(ic - ip, 1)
    if not spesa_su:
        return (f"Spesa ordini stabile o in calo. Incidenza sull'incasso {ic}% (era {ip}%).", True)
    if delta <= 2:
        return (
            f"Ordini in aumento ma in linea con l'incasso: incidenza {ic}% (era {ip}%). Giustificato.",
            True,
        )
    return (
        f"Ordini cresciuti più dell'incasso: incidenza salita a {ic}% (era {ip}%, +{delta} punti). "
        f"Verifica se c'è una festività/ricorrenza imminente o se è un errore.",
        False,
    )


@router.get("/correlazione-ordini")
async def correlazione_ordini(da: Optional[str] = None, a: Optional[str] = None):
    """Confronta incassi (corrispettivi) e spesa per ordini nel periodo, e dice se
    l'aumento degli ordini è giustificato dal venduto. Default: mese corrente."""
    campo_data, campo_importo = await _campi_rilevati()
    if not campo_data or not campo_importo:
        raise HTTPException(404, "Collection corrispettivi vuota o schema non riconosciuto")
    oggi = date.today()
    al = _parse_data(a) or oggi
    dal = _parse_data(da) or oggi.replace(day=1)
    durata = max(0, (al - dal).days)

    async def blocco(d1: date, d2: date) -> dict:
        per_giorno = await _serie(campo_data, campo_importo, d1, d2)
        incasso = round(sum(per_giorno.values()), 2)
        spesa, n = await _spesa_ordini(d1, d2)
        incidenza = round(spesa / incasso * 100, 1) if incasso else None
        return {
            "da": d1.isoformat(), "a": d2.isoformat(),
            "incasso": incasso, "spesa_ordini": spesa, "n_ordini": n,
            "incidenza_pct": incidenza,
        }

    corrente = await blocco(dal, al)
    precedente = await blocco(dal - timedelta(days=durata + 1), dal - timedelta(days=1))
    try:
        anno_prec = await blocco(dal.replace(year=dal.year - 1), al.replace(year=al.year - 1))
    except ValueError:
        anno_prec = None

    messaggio, giustificato = _verdetto_correlazione(corrente, precedente)
    return {
        "periodo": corrente,
        "periodo_precedente": precedente,
        "anno_precedente": anno_prec,
        "giustificato": giustificato,
        "messaggio": messaggio,
    }


# ── Festività e ponti (anticipo ordini) ────────────────────────────────────────
def _pasqua(anno: int) -> date:
    """Domenica di Pasqua (computo di Gauss, rito occidentale)."""
    a = anno % 19
    b = anno // 100
    c = anno % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    L = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * L) // 451
    mese = (h + L - 7 * m + 114) // 31
    giorno = ((h + L - 7 * m + 114) % 31) + 1
    return date(anno, mese, giorno)


def festivita_anno(anno: int) -> list:
    """Festività rilevanti per la pasticceria: nazionali + patrono di Napoli."""
    pasqua = _pasqua(anno)
    fissi = [
        (date(anno, 1, 1), "Capodanno"),
        (date(anno, 1, 6), "Epifania"),
        (pasqua, "Pasqua"),
        (pasqua + timedelta(days=1), "Lunedì dell'Angelo (Pasquetta)"),
        (date(anno, 4, 25), "Festa della Liberazione"),
        (date(anno, 5, 1), "Festa del Lavoro"),
        (date(anno, 6, 2), "Festa della Repubblica"),
        (date(anno, 8, 15), "Ferragosto"),
        (date(anno, 9, 19), "San Gennaio (patrono di Napoli)"),
        (date(anno, 11, 1), "Ognissanti"),
        (date(anno, 12, 8), "Immacolata"),
        (date(anno, 12, 25), "Natale"),
        (date(anno, 12, 26), "Santo Stefano"),
    ]
    return sorted(fissi, key=lambda x: x[0])


def _info_ponte(giorno_festivo: date) -> Optional[dict]:
    """Se la festività crea un 'ponte', restituisce il giorno-ponte consigliato.
    Festivo di martedì → lunedì ponte; di giovedì → venerdì ponte."""
    wd = giorno_festivo.weekday()  # 0=lun .. 6=dom
    if wd == 1:  # martedì
        return {"giorno_ponte": (giorno_festivo - timedelta(days=1)).isoformat(), "tipo": "lunedì di ponte"}
    if wd == 3:  # giovedì
        return {"giorno_ponte": (giorno_festivo + timedelta(days=1)).isoformat(), "tipo": "venerdì di ponte"}
    return None


@router.get("/festivita-imminenti")
async def festivita_imminenti(giorni: int = 21):
    """Festività nei prossimi `giorni` giorni, con rilevamento ponti e promemoria
    di anticipare gli ordini (la consegna potrebbe cadere su un giorno festivo)."""
    oggi = date.today()
    limite = oggi + timedelta(days=max(1, giorni))
    eventi = festivita_anno(oggi.year) + festivita_anno(oggi.year + 1)
    risultato = []
    for giorno, nome in eventi:
        if oggi <= giorno <= limite:
            ponte = _info_ponte(giorno)
            mancanti = (giorno - oggi).days
            giorni_chiusura = [giorno.isoformat()]
            if ponte:
                giorni_chiusura.append(ponte["giorno_ponte"])
            risultato.append({
                "data": giorno.isoformat(),
                "nome": nome,
                "giorni_mancanti": mancanti,
                "giorno_settimana": ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"][giorno.weekday()],
                "ponte": ponte,
                "giorni_senza_consegna": sorted(set(giorni_chiusura)),
                "suggerimento": (
                    f"{nome} tra {mancanti} giorni"
                    + (f" + {ponte['tipo']}" if ponte else "")
                    + ": la consegna cadrebbe a ridosso di un giorno festivo. "
                    "Anticipa un ordine maggiore per non restare scoperto."
                ),
            })
    return {"oggi": oggi.isoformat(), "finestra_giorni": giorni, "festivita": risultato}


# ── Apprendimento storico (previsione anno successivo) ──────────────────────────
@router.get("/previsione")
async def previsione(mese: Optional[int] = None, anno: Optional[int] = None):
    """Previsione incasso per un mese, imparando dallo storico anno-su-anno.
    Default: mese prossimo. Se gli incassi crescono di anno in anno, suggerisce di
    scalare gli ordini della stessa percentuale."""
    campo_data, campo_importo = await _campi_rilevati()
    if not campo_data or not campo_importo:
        raise HTTPException(404, "Collection corrispettivi vuota o schema non riconosciuto")
    oggi = date.today()
    if not mese:
        nxt = (oggi.replace(day=1) + timedelta(days=32)).replace(day=1)
        mese, anno_target = nxt.month, nxt.year
    else:
        anno_target = anno or oggi.year

    docs = await db.corrispettivi.find({}, {"_id": 0}).to_list(20000)
    per_anno: dict[int, float] = {}
    for d in docs:
        g = _parse_data(d.get(campo_data))
        if g and g.month == mese:
            per_anno[g.year] = per_anno.get(g.year, 0.0) + _to_float(d.get(campo_importo))

    anni = sorted(per_anno)
    storico = [{"anno": a, "incasso": round(per_anno[a], 2)} for a in anni]
    # crescita media YoY sugli anni consecutivi disponibili
    crescite = []
    for i in range(1, len(anni)):
        prec, cur = per_anno[anni[i - 1]], per_anno[anni[i]]
        if prec > 0:
            crescite.append((cur - prec) / prec)
    crescita_media = round(sum(crescite) / len(crescite) * 100, 1) if crescite else None

    base = per_anno.get(anno_target - 1)  # anno precedente al target
    if base is None and anni:
        base = per_anno[anni[-1]]
    previsione_incasso = (
        round(base * (1 + (crescita_media or 0) / 100), 2) if base is not None else None
    )

    if crescita_media is None:
        msg = "Storico insufficiente per una previsione (serve almeno un anno di confronto)."
    elif crescita_media > 1:
        msg = (
            f"Gli incassi di questo mese crescono in media del {crescita_media}% all'anno: "
            f"valuta ordini maggiori (~+{crescita_media}%) rispetto all'anno scorso."
        )
    elif crescita_media < -1:
        msg = f"Gli incassi di questo mese calano del {abs(crescita_media)}% all'anno: prudenza sugli ordini."
    else:
        msg = "Incassi stabili anno su anno: mantieni livelli di ordine simili all'anno scorso."

    return {
        "mese": mese,
        "anno_target": anno_target,
        "storico": storico,
        "crescita_media_annua_pct": crescita_media,
        "incasso_atteso": previsione_incasso,
        "suggerimento": msg,
    }


class CorrispettivoManuale(BaseModel):
    data: str  # YYYY-MM-DD
    importo: float


@router.post("")
async def upsert_corrispettivo(payload: CorrispettivoManuale):
    """Inserimento/aggiornamento manuale, idempotente per data (logica fatture)."""
    g = _parse_data(payload.data)
    if not g:
        raise HTTPException(400, "Data non valida (usa YYYY-MM-DD)")
    campo_data, campo_importo = await _campi_rilevati()
    campo_data = campo_data or "data"
    campo_importo = campo_importo or "importo"
    await db.corrispettivi.update_one(
        {campo_data: g.isoformat()},
        {"$set": {campo_data: g.isoformat(), campo_importo: float(payload.importo),
                  "origine": "manuale", "updated_at": datetime.utcnow().isoformat()}},
        upsert=True,
    )
    return {"ok": True, "data": g.isoformat(), "importo": float(payload.importo)}
