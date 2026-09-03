"""
Router Schede Tecniche — associa un link a scheda tecnica/sicurezza a ogni prodotto
del dizionario (alimentari e non: detersivi, brillantanti, ecc.).

Per i controlli ASL: ogni prodotto deve poter esibire la sua scheda tecnica.
Il link viene salvato (non il file). La ricerca del link è assistita da Claude.

Collection: schede_tecniche
  - prodotto_key:  chiave normalizzata del prodotto (match con dizionario)
  - nome_prodotto: nome leggibile
  - url:           link alla scheda (PDF o pagina)
  - tipo:          "tecnica" | "sicurezza"
  - verificato:    bool (l'utente ha confermato che il link è corretto)
  - fonte:         dominio del link
  - aggiornato_at: ISO timestamp
"""

import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from fastapi import APIRouter, Body, HTTPException, Query, Depends

from app.lotti.db import database as db
from app.lotti.auth import require_admin

router = APIRouter(prefix="/schede-tecniche", tags=["Schede Tecniche"])


def _key(nome: str) -> str:
    return re.sub(r"\s+", " ", (nome or "").strip().lower())


# ── Filtro alimentari ────────────────────────────────────────────────────────
# Nelle schede tecniche servono SOLO prodotti alimentari. L'import XML inserisce
# anche righe non alimentari (stoviglie, attrezzi, pulizia) e frammenti di fattura.
# Regola conservativa: si esclude solo cio' che e' NON-alimentare con certezza
# (nome che identifica un oggetto/attrezzo/pulizia o un frammento di fattura).
# In caso di dubbio il prodotto viene MANTENUTO.
_NONFOOD_OGGETTI = re.compile(
    r"(coltell|forbic|\bcalice\b|calici|bicchier|drink timeless|elysia|rock bar|"
    r"paravent|cannucc|brillantant|detersiv|deterg\.?\s*lavastov|sgrassat|\bsapone\b|"
    r"bobina allumini|rotolo allumini|sottotorta|pirottin|tovagli|\bguant|asciugaman|"
    r"fazzolett|spazzol|\bscop[ae]\b|ruoto pastiera|pastierina allum|vassoi|posat|"
    r"caraff|shaker|coperchi)", re.I)
_NONFOOD_JUNK = re.compile(
    r"(^\s*\d{5}\s+\w|acconto|fornitura di n|spese di trasport|nota credito|"
    r"napoli\s+na\s*$|^\s*\d+\s*-\s*bar\b|p\.?\s*iva|partita iva|causale)", re.I)


def _is_non_alimentare(nome: str) -> bool:
    """True se il prodotto NON e' alimentare con ragionevole certezza."""
    n = (nome or "").lower()
    if not n.strip():
        return False
    if _NONFOOD_JUNK.search(n):
        return True
    if _NONFOOD_OGGETTI.search(n):
        return True
    return False


@router.get("/prodotti")
async def lista_prodotti_con_schede(
    solo_senza: bool = Query(False, description="Solo prodotti senza scheda"),
    q: str = Query(None, description="Filtro testo sul nome"),
    limit: int = Query(500, le=2000),
    includi_non_alimentari: bool = Query(False, description="Includi anche i prodotti non alimentari (stoviglie, pulizia, ecc.)"),
):
    """
    Elenco di tutti i prodotti del dizionario (alimentari + non), con lo stato
    della scheda tecnica associata (se presente).
    """
    prodotti = await db.dizionario_prodotti.find(
        {}, {"_id": 0, "id": 1, "nome_normalizzato": 1, "nome_originale": 1,
             "fornitore": 1, "ingrediente_canonico": 1}
    ).to_list(10000)
    # Fuori la spazzatura fatture (omaggi, sconti, trasporti…): non sono prodotti
    from app.lotti.routers.prodotti_master import _RX_NON_ORDINABILI
    import re as _re
    prodotti = [p for p in prodotti
                if not _re.search(_RX_NON_ORDINABILI,
                                  (p.get("nome_normalizzato") or p.get("nome_originale") or "").lower())]

    # Mappa schede esistenti per prodotto_key
    schede = await db.schede_tecniche.find({}, {"_id": 0}).to_list(10000)
    per_key = {}
    for s in schede:
        k = s.get("prodotto_key")
        if not k:
            continue
        per_key.setdefault(k, []).append(s)

    out = []
    visti = set()
    for p in prodotti:
        nome = p.get("nome_normalizzato") or p.get("nome_originale") or ""
        key = _key(nome)
        if not key or key in visti:
            continue
        visti.add(key)
        if not includi_non_alimentari and _is_non_alimentare(nome):
            continue
        sk = per_key.get(key, [])
        if solo_senza and sk:
            continue
        if q and q.lower() not in nome.lower():
            continue
        out.append({
            "prodotto_key": key,
            "nome": nome,
            "fornitore": p.get("fornitore", ""),
            "categoria": p.get("ingrediente_canonico", ""),
            "schede": sk,
            "ha_scheda": len(sk) > 0,
        })

    out.sort(key=lambda x: (x["ha_scheda"], x["nome"]))
    return {"totale": len(out), "prodotti": out[:limit]}


@router.post("/salva")
async def salva_scheda(payload: dict = Body(...)):
    """
    Salva (o aggiorna) il link a una scheda tecnica per un prodotto.
    Body: {prodotto_key, nome_prodotto, url, tipo, verificato}
    """
    key = _key(payload.get("prodotto_key") or payload.get("nome_prodotto"))
    url = (payload.get("url") or "").strip()
    if not key or not url:
        raise HTTPException(400, "prodotto_key e url obbligatori")
    if not url.startswith("http"):
        raise HTTPException(400, "URL non valido (deve iniziare con http)")

    tipo = payload.get("tipo", "tecnica")
    doc = {
        "prodotto_key": key,
        "nome_prodotto": payload.get("nome_prodotto", key),
        "url": url,
        "tipo": tipo,
        "verificato": bool(payload.get("verificato", False)),
        "fonte": urlparse(url).netloc,
        "aggiornato_at": datetime.now(timezone.utc).isoformat(),
    }
    # Upsert per (prodotto_key + tipo): una tecnica e una sicurezza per prodotto
    await db.schede_tecniche.update_one(
        {"prodotto_key": key, "tipo": tipo},
        {"$set": doc},
        upsert=True,
    )
    return {"ok": True, "scheda": doc}


@router.delete("/elimina")
async def elimina_scheda(prodotto_key: str = Query(...), tipo: str = Query("tecnica"), _admin=Depends(require_admin)):
    res = await db.schede_tecniche.delete_one({"prodotto_key": _key(prodotto_key), "tipo": tipo})
    return {"ok": True, "eliminati": res.deleted_count}


@router.get("/da-proporre")
async def schede_da_proporre(giorni: int = Query(30, description="Prodotti aggiunti negli ultimi N giorni")):
    """
    Prodotti NUOVI (arrivati da fatture recenti) che non hanno ancora una scheda tecnica.
    Usato per proporre all'utente: 'Vuoi cercare la scheda di questo nuovo prodotto?'
    """
    prodotti = await db.dizionario_prodotti.find(
        {}, {"_id": 0, "nome_normalizzato": 1, "nome_originale": 1, "fornitore": 1, "data_fattura": 1}
    ).to_list(10000)

    schede_keys = set(
        s.get("prodotto_key") for s in await db.schede_tecniche.find({}, {"_id": 0, "prodotto_key": 1}).to_list(10000)
    )
    schede_keys.discard(None)

    def recente(val):
        if not val:
            return False
        try:
            txt = str(val)
            if "/" in txt:
                d = datetime.strptime(txt[:10], "%d/%m/%Y")
            else:
                d = datetime.fromisoformat(txt[:10])
            return (datetime.now() - d).days <= giorni
        except Exception:
            return False

    proposte = []
    visti = set()
    for p in prodotti:
        nome = p.get("nome_normalizzato") or p.get("nome_originale") or ""
        key = _key(nome)
        if not key or key in visti or key in schede_keys:
            continue
        if recente(p.get("data_fattura")):
            visti.add(key)
            proposte.append({
                "prodotto_key": key,
                "nome": nome,
                "fornitore": p.get("fornitore", ""),
                "data_fattura": p.get("data_fattura", ""),
            })

    return {"totale": len(proposte), "proposte": proposte}


@router.get("/query-ricerca")
async def query_ricerca(nome: str = Query(...)):
    """
    Restituisce una query Google pronta e l'URL di ricerca per trovare la scheda.
    L'utente clicca, trova il PDF, e incolla il link in /salva.
    """
    q = f"scheda tecnica sicurezza {nome} PDF"
    from urllib.parse import quote_plus
    return {
        "query": q,
        "google_url": f"https://www.google.com/search?q={quote_plus(q)}",
    }


# ════════════════════════════════════════════════════════════════════════════
# FONTI PRODUTTORE + SCRAPING COMPOSIZIONE (richiesta Enzo)
# Sezione Impostazioni: i prodotti senza produttore noto vengono elencati; Enzo
# inserisce il sito del produttore reale (es. zuppa inglese -> www.elenka.it) e il
# sistema fa scraping per estrarre composizione/ingredienti/coloranti/allergeni,
# da ereditare poi nel prodotto finito (modello allergeni a cascata).
# ════════════════════════════════════════════════════════════════════════════
import urllib.request as _urlreq
import html as _html

_ALLERGENI_KW = {
    "glutine": "Glutine", "frumento": "Glutine", "grano": "Glutine", "orzo": "Glutine",
    "segale": "Glutine", "farro": "Glutine", "kamut": "Glutine", "avena": "Glutine", "semola": "Glutine",
    "latte": "Latte", "lattosio": "Latte", "burro": "Latte", "panna": "Latte",
    "formaggio": "Latte", "caseina": "Latte", "siero di latte": "Latte",
    "uovo": "Uova", "uova": "Uova", "albume": "Uova", "tuorlo": "Uova",
    "soia": "Soia", "arachid": "Arachidi",
    "mandorl": "Frutta a guscio", "nocciol": "Frutta a guscio", "pistacch": "Frutta a guscio",
    "anacard": "Frutta a guscio", "noci": "Frutta a guscio",
    "sesamo": "Sesamo", "sedano": "Sedano", "senape": "Senape",
    "solfiti": "Solfiti", "anidride solforosa": "Solfiti", "lupino": "Lupino",
    "pesce": "Pesce", "crostacei": "Crostacei", "molluschi": "Molluschi",
}
# Coloranti azoici che per legge richiedono l'avvertenza "puo' influire su attivita'/attenzione bambini"
_COLORANTI_AZOICI = {"e102", "e104", "e110", "e122", "e124", "e129"}


def _estrai_da_testo(txt: str) -> dict:
    """Estrae composizione/additivi/coloranti/allergeni da testo grezzo (HTML ripulito,
    OCR, o incollato). Preferisce la dichiarazione ITALIANA."""
    txt = _html.unescape(re.sub(r"\s+", " ", txt or "")).strip()
    cand = []
    for m in re.finditer(
        r"(?i)ingredient[ie]\s*(?:\([a-z]{2}\))?\s*[:\.]?\s*(.{10,600}?)"
        r"(?=\b(modalit|modo d|conservaz|consigli|istruzioni|valori|allergen|scadenz|dosagg|peso|formato|confezion|recension|categor|ingredient)\b|$)",
        txt,
    ):
        cand.append(m.group(1).strip(" ."))
    _en = re.compile(r"(?i)\b(sugar|syrup|flavour|flavor|dyes|water|wheat|milk|eggs?)\b")
    comp_raw = next((c for c in cand if not _en.search(c)), (cand[0] if cand else ""))
    comp = [p.strip(" .") for p in re.split(r"[;,]", comp_raw) if 1 < len(p.strip(" .")) < 90]
    low = comp_raw.lower()
    additivi = sorted({re.sub(r"\s", "", c).upper() for c in re.findall(r"e\s?\d{3}[a-z]?", low)})
    coloranti = [e for e in additivi if e[1:4].isdigit() and 100 <= int(e[1:4]) <= 199]
    # Allergeni: ignora le menzioni NEGATE ("senza glutine", "privo di lattosio",
    # "non contiene...", "gluten free") per non segnalare un allergene assente.
    low_allerg = re.sub(
        r"(?i)\b(?:senza|privo di|priva di|privi di|prive di|non contiene|assenza di)\b[^,;.]{0,30}",
        " ", low,
    )
    low_allerg = re.sub(r"(?i)\b(?:gluten|lactose)[\s-]?free\b", " ", low_allerg)
    allergeni = sorted({v for k, v in _ALLERGENI_KW.items() if k in low_allerg})
    avviso = [c for c in coloranti if c.lower() in _COLORANTI_AZOICI]
    return {
        "composizione": comp,
        "composizione_raw": comp_raw[:600],
        "additivi": additivi,
        "coloranti": coloranti,
        "allergeni": allergeni,
        "avviso_coloranti_azoici": avviso,
    }


def _scrape_composizione(url: str) -> dict:
    """Scarica la pagina e prova a estrarre la dichiarazione ingredienti in modo euristico."""
    req = _urlreq.Request(url, headers={"User-Agent": "Mozilla/5.0 (LottiHACCP scraper)"})
    raw = _urlreq.urlopen(req, timeout=20).read().decode("utf-8", "replace")
    txt = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw)
    txt = re.sub(r"(?is)<[^>]+>", " ", txt)
    return _estrai_da_testo(txt)


@router.get("/senza-produttore")
async def prodotti_senza_produttore(limit: int = Query(500, le=2000), q: str = Query(None)):
    """Prodotti alimentari per cui NON e' ancora indicato il sito del produttore
    (nessuna scheda tipo='produttore'). Enzo assegna l'URL del produttore reale."""
    from app.lotti.routers.prodotti_master import _RX_NON_ORDINABILI
    import re as _re

    prodotti = await db.dizionario_prodotti.find(
        {}, {"_id": 0, "nome_normalizzato": 1, "nome_originale": 1, "fornitore": 1}
    ).to_list(10000)
    con_prod = {
        s.get("prodotto_key")
        for s in await db.schede_tecniche.find({"tipo": "produttore"}, {"_id": 0, "prodotto_key": 1}).to_list(10000)
    }
    out, visti = [], set()
    for p in prodotti:
        nome = p.get("nome_normalizzato") or p.get("nome_originale") or ""
        key = _key(nome)
        if not key or key in visti:
            continue
        visti.add(key)
        if _is_non_alimentare(nome):
            continue
        if _re.search(_RX_NON_ORDINABILI, nome.lower()):
            continue
        if key in con_prod:
            continue
        if q and q.lower() not in nome.lower():
            continue
        out.append({"prodotto_key": key, "nome": nome, "fornitore": p.get("fornitore", "")})
    out.sort(key=lambda x: x["nome"])
    return {"totale": len(out), "prodotti": out[:limit]}


@router.post("/scrape")
async def scrape_scheda(payload: dict = Body(...)):
    """Scarica la pagina del produttore ed estrae composizione/coloranti/allergeni.
    Se prodotto_key e' presente (e salva!=False) salva il risultato come scheda tipo='produttore'.
    Body: {url, prodotto_key?, nome_prodotto?, produttore?, salva?}"""
    url = (payload.get("url") or "").strip()
    if not url.startswith("http"):
        raise HTTPException(400, "URL non valido (deve iniziare con http)")
    try:
        dati = _scrape_composizione(url)
    except Exception as e:
        raise HTTPException(502, f"scraping fallito: {str(e)[:120]}")

    key = _key(payload.get("prodotto_key") or payload.get("nome_prodotto") or "")
    if key and payload.get("salva", True):
        doc = {
            "prodotto_key": key,
            "nome_prodotto": payload.get("nome_prodotto", key),
            "url": url,
            "tipo": "produttore",
            "produttore": payload.get("produttore", ""),
            "fonte": urlparse(url).netloc,
            "composizione": dati["composizione"],
            "composizione_raw": dati["composizione_raw"],
            "additivi": dati["additivi"],
            "coloranti": dati["coloranti"],
            "allergeni": dati["allergeni"],
            "avviso_coloranti_azoici": dati["avviso_coloranti_azoici"],
            "verificato": False,
            "aggiornato_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.schede_tecniche.update_one(
            {"prodotto_key": key, "tipo": "produttore"}, {"$set": doc}, upsert=True
        )
        return {"ok": True, "salvato": True, "scheda": doc}
    return {"ok": True, "salvato": False, **dati}


@router.post("/parse-etichetta")
async def parse_etichetta(payload: dict = Body(...)):
    """Interpreta un TESTO grezzo (da OCR gratuito lato browser o incollato a mano) ed estrae
    composizione/coloranti/allergeni con lo stesso motore dello scraping. Se prodotto_key e'
    presente (e salva!=False) salva come scheda tipo='produttore'.
    Body: {testo, prodotto_key?, nome_prodotto?, produttore?, fonte?, salva?}"""
    testo = (payload.get("testo") or "").strip()
    if len(testo) < 5:
        raise HTTPException(400, "testo mancante o troppo corto")
    dati = _estrai_da_testo(testo)
    key = _key(payload.get("prodotto_key") or payload.get("nome_prodotto") or "")
    if key and payload.get("salva", True):
        doc = {
            "prodotto_key": key,
            "nome_prodotto": payload.get("nome_prodotto", key),
            "url": "",
            "tipo": "produttore",
            "produttore": payload.get("produttore", ""),
            "fonte": payload.get("fonte", "foto-etichetta"),
            "composizione": dati["composizione"],
            "composizione_raw": dati["composizione_raw"],
            "additivi": dati["additivi"],
            "coloranti": dati["coloranti"],
            "allergeni": dati["allergeni"],
            "avviso_coloranti_azoici": dati["avviso_coloranti_azoici"],
            "verificato": False,
            "aggiornato_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.schede_tecniche.update_one(
            {"prodotto_key": key, "tipo": "produttore"}, {"$set": doc}, upsert=True
        )
        return {"ok": True, "salvato": True, "scheda": doc}
    return {"ok": True, "salvato": False, **dati}


@router.post("/leggi-foto-ai")
async def leggi_foto_ai(payload: dict = Body(...)):
    """Fallback AI-visione per etichette difficili: riceve la FOTO (base64) e usa il
    modello multimodale per trascrivere il testo (in particolare la dichiarazione
    'Ingredienti:', additivi/coloranti E-numbers, allergeni); poi estrae
    composizione/coloranti/allergeni con lo STESSO motore _estrai_da_testo e salva come
    scheda tipo='produttore' (come /parse-etichetta). Usato solo quando l'OCR gratuito
    del browser resta povero. Body: {immagine_base64, media_type?, prodotto_key?,
    nome_prodotto?, produttore?, salva?}"""
    import os as _osx
    api_key = _osx.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise HTTPException(503, "AI-visione non disponibile (manca ANTHROPIC_API_KEY)")
    img = (payload.get("immagine_base64") or "").strip()
    media_type = payload.get("media_type") or "image/jpeg"
    if not img:
        raise HTTPException(400, "immagine mancante")
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
                headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 1024,
                    "messages": [{"role": "user", "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": img}},
                        {"type": "text", "text": (
                            "Trascrivi TUTTO il testo leggibile di questa etichetta alimentare, in italiano. "
                            "Mantieni in particolare la riga che inizia con 'Ingredienti:' con l'elenco completo, "
                            "additivi e coloranti (codici E...), e le diciture sugli allergeni. "
                            "Rispondi SOLO con il testo trascritto, senza commenti."
                        )},
                    ]}],
                },
            )
        txt = "".join(b.get("text", "") for b in (r.json().get("content") or []) if b.get("type") == "text")
    except Exception as e:
        raise HTTPException(502, f"AI-visione fallita: {str(e)[:120]}")
    txt = (txt or "").strip()
    if len(txt) < 5:
        return {"ok": False, "testo_ocr": txt, "nota": "Nessun testo leggibile dall'immagine"}
    dati = _estrai_da_testo(txt)
    key = _key(payload.get("prodotto_key") or payload.get("nome_prodotto") or "")
    if key and payload.get("salva", True):
        doc = {
            "prodotto_key": key,
            "nome_prodotto": payload.get("nome_prodotto", key),
            "url": "",
            "tipo": "produttore",
            "produttore": payload.get("produttore", ""),
            "fonte": payload.get("fonte", "foto-etichetta-ai"),
            "composizione": dati["composizione"],
            "composizione_raw": dati["composizione_raw"],
            "additivi": dati["additivi"],
            "coloranti": dati["coloranti"],
            "allergeni": dati["allergeni"],
            "avviso_coloranti_azoici": dati["avviso_coloranti_azoici"],
            "verificato": False,
            "aggiornato_at": datetime.now(timezone.utc).isoformat(),
        }
        await db.schede_tecniche.update_one(
            {"prodotto_key": key, "tipo": "produttore"}, {"$set": doc}, upsert=True
        )
        return {"ok": True, "salvato": True, "scheda": doc, "testo_ocr": txt}
    return {"ok": True, "salvato": False, "testo_ocr": txt, **dati}
import os as _os
import json as _json

_SCHEDE_BASE = None


def _carica_schede_base():
    """Carica (una volta) le schede precaricate da data/schede_prodotti.json."""
    global _SCHEDE_BASE
    if _SCHEDE_BASE is not None:
        return _SCHEDE_BASE
    try:
        p = _os.path.join(_os.path.dirname(__file__), "..", "data", "schede_prodotti.json")
        with open(p, encoding="utf-8") as f:
            _SCHEDE_BASE = (_json.load(f) or {}).get("schede", [])
    except Exception:
        _SCHEDE_BASE = []
    return _SCHEDE_BASE


async def risolvi_scheda(nome: str) -> dict:
    """Logica condivisa: scheda SALVATA (db.schede_tecniche tipo=produttore) oppure
    composizione BASE da schede_prodotti.json quando un alias e' contenuto nel nome.
    Riusata da /scheda (SchedaFonteModal) e dalla cascata allergeni delle ricette."""
    key = _key(nome)
    salvata = await db.schede_tecniche.find_one({"prodotto_key": key, "tipo": "produttore"}, {"_id": 0})
    if salvata:
        return {"trovata": True, "fonte": "salvata", "scheda": salvata}

    low = key
    for s in _carica_schede_base():
        for al in s.get("match_aliases", []):
            if al and al.lower() in low:
                comp = s.get("composizione")
                allerg_base = list(s.get("allergeni") or [])
                if not comp and s.get("composizione_varianti"):
                    v = s["composizione_varianti"][0]
                    comp = v.get("composizione")
                    allerg_base = list(v.get("allergeni") or allerg_base)
                dati = _estrai_da_testo("Ingredienti: " + ", ".join(comp or []))
                allerg = sorted(set(dati["allergeni"]) | set(allerg_base))
                return {
                    "trovata": True,
                    "fonte": "base",
                    "scheda": {
                        "prodotto_key": key,
                        "produttore": s.get("produttore") or s.get("marca", ""),
                        "impiego": s.get("impiego", ""),
                        "composizione": comp or [],
                        "additivi": dati["additivi"],
                        "coloranti": dati["coloranti"],
                        "allergeni": allerg,
                        "avviso_coloranti_azoici": dati["avviso_coloranti_azoici"],
                        "fonte_url": s.get("sito_produttore") or s.get("fonte", ""),
                    },
                }
    return {"trovata": False}


@router.get("/scheda")
async def scheda_prodotto(nome: str = Query(...)):
    """Scheda 'produttore' di un prodotto (salvata o base). Usata da SchedaFonteModal."""
    return await risolvi_scheda(nome)


# ════════════════════════════════════════════════════════════════════════════
# RICERCA WEB AUTOMATICA (richiesta Enzo, 02/07/2026)
# Flusso: descrizione ESATTA della riga fattura XML → ricerca web con quella
# stringa → identificazione certa del prodotto commerciale (es. "FARINA 00
# CAPUTO RINFORZ." = farina 00 rinforzata Caputo, per pizza/lievitati, NON
# farina generica) → link alla scheda tecnica del produttore + composizione →
# nome canonico imparato in nome_mapping (L1), così le fatture successive
# risolvono da sole. La scheda salvata entra nella cascata allergeni ricette
# (risolvi_scheda), quindi la ricetta espone anche il link.
# ════════════════════════════════════════════════════════════════════════════

def _estrai_json(testo: str) -> dict:
    """Estrae l'ULTIMO oggetto JSON piatto dal testo di risposta del modello."""
    matches = re.findall(r"\{[^{}]*\}", testo or "", re.S)
    for raw in reversed(matches):
        try:
            return _json.loads(raw)
        except Exception:
            continue
    return {}


async def _identifica_con_ricerca_web(descrizione: str, fornitore: str = "",
                                      tipo: str = "alimento") -> dict:
    """Chiede al modello (con strumento di ricerca web server-side Anthropic) di
    cercare la descrizione esatta della fattura e identificare il prodotto.
    tipo='alimento' → prodotto_identificato, marca, nome_canonico, impiego,
    url_scheda, ingredienti_testo, confidenza (alta|media|bassa).
    tipo='chimico' (detersivi, richiesta Enzo per HACCP) → prodotto_identificato,
    marca, url_scheda (scheda di SICUREZZA), principi_attivi, pericoli,
    velenoso, confidenza."""
    api_key = _os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise HTTPException(503, "Ricerca web non disponibile (manca ANTHROPIC_API_KEY)")
    contesto_forn = f' Il fornitore della fattura è "{fornitore}".' if fornitore else ""
    if tipo == "chimico":
        prompt = (
            "Sei il responsabile HACCP di una pasticceria italiana. Questa è la descrizione "
            f'ESATTA di una riga di fattura elettronica XML: «{descrizione}».{contesto_forn} '
            "È un prodotto CHIMICO/DETERSIVO usato nel laboratorio. Cerca sul web per "
            "identificarlo con certezza, preferendo la SCHEDA DI SICUREZZA (SDS) o la "
            "pagina del produttore. "
            "Poi rispondi SOLO con un oggetto JSON con questi campi (tutti stringhe): "
            '{"prodotto_identificato": "nome commerciale completo", '
            '"marca": "produttore/marca", '
            '"url_scheda": "URL scheda di sicurezza (SDS) o pagina produttore, altrimenti vuoto", '
            '"principi_attivi": "principi attivi separati da punto e virgola, es. ipoclorito di sodio 5%", '
            '"pericoli": "indicazioni di pericolo per l\'uomo separate da punto e virgola, es. provoca ustioni; nocivo se ingerito", '
            '"velenoso": "sì se tossico/velenoso per l\'uomo, no altrimenti", '
            '"confidenza": "alta se hai trovato il prodotto esatto, media se plausibile, bassa se incerto"}. '
            "NON inventare: se non trovi il prodotto esatto, usa confidenza bassa e lascia vuoti i campi dubbi."
        )
    else:
        prompt = (
            "Sei l'assistente HACCP di una pasticceria italiana. Questa è la descrizione "
            f'ESATTA di una riga di fattura elettronica XML: «{descrizione}».{contesto_forn} '
            "Cerca sul web questa descrizione (o le sue parole chiave: marca + tipo prodotto) "
            "per identificare CON CERTEZZA il prodotto commerciale reale, preferendo la "
            "scheda tecnica o la pagina prodotto del PRODUTTORE. "
            "Poi rispondi SOLO con un oggetto JSON con questi campi (tutti stringhe): "
            '{"prodotto_identificato": "nome commerciale completo del prodotto", '
            '"marca": "produttore/marca", '
            '"nome_canonico": "nome cucina atomico e pulito, es. Farina 00 / Burro / Margarina", '
            '"impiego": "uso principale se noto, es. pizza, dolci, sfoglia, altrimenti vuoto", '
            '"url_scheda": "URL scheda tecnica o pagina prodotto del produttore, altrimenti vuoto", '
            '"ingredienti_testo": "dichiarazione ingredienti trovata, altrimenti vuoto", '
            '"pezzi_per_cartone": "quanti pezzi contiene un cartone/collo secondo la scheda, SOLO il numero, altrimenti vuoto", '
            '"peso_pezzo_g": "peso di UN pezzo in grammi secondo la scheda, SOLO il numero, altrimenti vuoto", '
            '"confidenza": "alta se hai trovato il prodotto esatto, media se plausibile, bassa se incerto"}. '
            "Per pezzi_per_cartone e peso_pezzo_g cerca nella scheda tecnica le voci "
            "formato/confezione/imballo (es. 'cartone da 48 pz', '80 g/pezzo', '52x80g'). "
            "NON inventare: se non trovi il prodotto esatto, usa confidenza bassa e lascia vuoti i campi dubbi."
        )
    try:
        import httpx
        async with httpx.AsyncClient(timeout=90) as c:
            r = await c.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": api_key, "anthropic-version": "2023-06-01",
                         "content-type": "application/json"},
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 1500,
                    "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
        data = r.json()
        if r.status_code != 200:
            raise HTTPException(502, f"ricerca web fallita: {str(data.get('error', {}).get('message', r.status_code))[:120]}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"ricerca web fallita: {str(e)[:120]}")
    txt = "".join(b.get("text", "") for b in (data.get("content") or []) if b.get("type") == "text")
    res = _estrai_json(txt)
    if not res.get("prodotto_identificato"):
        return {"confidenza": "bassa", "prodotto_identificato": "", "marca": "",
                "nome_canonico": "", "impiego": "", "url_scheda": "", "ingredienti_testo": ""}
    return res


@router.post("/ricerca-web")
async def ricerca_web(payload: dict = Body(...)):
    """Identifica un prodotto partendo dalla descrizione ESATTA della fattura XML
    tramite ricerca web, e (se confidenza alta) salva scheda tecnica con link +
    impara il mapping descrizione→canonico. Body: {descrizione, fornitore?, salva?}.
    Con salva=False restituisce solo la proposta, non scrive nulla."""
    descrizione = (payload.get("descrizione") or payload.get("nome_prodotto") or "").strip()
    if len(descrizione) < 4:
        raise HTTPException(400, "descrizione mancante o troppo corta")
    fornitore = (payload.get("fornitore") or "").strip()
    salva = bool(payload.get("salva", True))
    from app.lotti.routers.classificatore_alimenti import RX_DETERSIVI
    tipo = payload.get("tipo") or ("chimico" if RX_DETERSIVI.search(descrizione) else "alimento")

    res = await _identifica_con_ricerca_web(descrizione, fornitore, tipo=tipo)
    confidenza = (res.get("confidenza") or "bassa").lower()
    url = (res.get("url_scheda") or "").strip()

    if tipo == "chimico":
        # Detersivi: scheda di SICUREZZA (principi attivi, pericoli), MAI mapping
        # ingredienti — un detersivo non deve entrare nel matching delle ricette.
        principi = [p.strip() for p in (res.get("principi_attivi") or "").split(";") if p.strip()]
        pericoli = [p.strip() for p in (res.get("pericoli") or "").split(";") if p.strip()]
        salvato_scheda = False
        if salva and confidenza == "alta" and (url.startswith("http") or principi or pericoli):
            doc = {
                "prodotto_key": _key(descrizione),
                "nome_prodotto": descrizione,
                "url": url,
                "tipo": "sicurezza",
                "produttore": res.get("marca", ""),
                "fonte": urlparse(url).netloc if url.startswith("http") else "ricerca-web",
                "principi_attivi": principi,
                "pericoli": pericoli,
                "velenoso": (res.get("velenoso") or "").strip().lower() in ("sì", "si", "yes", "true"),
                "verificato": False,
                "aggiornato_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.schede_tecniche.update_one(
                {"prodotto_key": doc["prodotto_key"], "tipo": "sicurezza"},
                {"$set": doc}, upsert=True,
            )
            salvato_scheda = True
        return {
            "ok": True,
            "tipo": "chimico",
            "descrizione": descrizione,
            "prodotto_identificato": res.get("prodotto_identificato", ""),
            "marca": res.get("marca", ""),
            "url_scheda": url,
            "principi_attivi": principi,
            "pericoli": pericoli,
            "velenoso": (res.get("velenoso") or "").strip().lower() in ("sì", "si", "yes", "true"),
            "confidenza": confidenza,
            "salvato_scheda": salvato_scheda,
            "salvato_mapping": False,
        }

    # Nome canonico: PRIMA il vocabolario controllato (match_livello2 su canonico
    # proposto + nome identificato: restituisce solo chiavi di INGREDIENTI_CANONICI,
    # es. "Burro", "Farina tipo 0"), POI il nome libero consolidato come fallback.
    # Motivo: un canonico libero tipo "Burro biologico" entrerebbe in nome_mapping
    # (L1, che vince su L2) e spezzerebbe il match FIFO con le ricette che dicono
    # "Burro" — il vocabolario controllato tiene fatture e ricette sulla stessa lingua.
    canonico = ""
    try:
        from app.lotti.routers.ingredienti import _consolida_canonico, match_livello2, _impara_mapping
        testo_match = f'{res.get("nome_canonico") or ""} {res.get("prodotto_identificato") or ""}'.strip()
        # PRODOTTI FINITI comprati (cornetti/sfogliatelle/tappi...): il canonico
        # resta il NOME DEL PRODOTTO, non il vocabolario ingredienti — visto nel
        # primo test live: "CRNT MLTCER BER" prendeva canonico "Frutti di bosco"
        # (il gusto!) e le ricette coi frutti di bosco veri avrebbero pescato i
        # cornetti nel FIFO.
        _RX_PRODOTTO_FINITO = re.compile(
            r"croissant|cornett|sfogliatell|tapp[oi]|coda d.aragosta|ciambell|"
            r"bab[aà]|brioche|saccottin|fagottin|treccia|danish|muffin|plumcake|"
            r"donut|krapfen|bombolon|polacca|rustico|panzerott|panino|tramezzin",
            re.IGNORECASE,
        )
        if _RX_PRODOTTO_FINITO.search(testo_match):
            canonico = _consolida_canonico((res.get("nome_canonico") or "").strip()) or ""
        else:
            canonico = match_livello2(testo_match) or ""
            if not canonico:
                canonico = _consolida_canonico((res.get("nome_canonico") or "").strip()) or ""
    except Exception:
        _impara_mapping = None  # noqa: F841

    # Composizione: prima dal testo ingredienti trovato, poi scrape dell'URL
    dati = None
    if res.get("ingredienti_testo"):
        dati = _estrai_da_testo("Ingredienti: " + res["ingredienti_testo"])
    if (not dati or not dati.get("composizione")) and url.startswith("http"):
        try:
            import asyncio as _aio
            dati = await _aio.to_thread(_scrape_composizione, url)
        except Exception:
            dati = dati or None

    salvato_scheda = False
    salvato_mapping = False
    if salva and confidenza == "alta":
        key = _key(descrizione)
        if url.startswith("http") or (dati and dati.get("composizione")):
            doc = {
                "prodotto_key": key,
                "nome_prodotto": descrizione,
                "url": url,
                "tipo": "produttore",
                "produttore": res.get("marca", ""),
                "impiego": res.get("impiego", ""),
                "pezzi_per_cartone": res.get("pezzi_per_cartone", ""),
                "peso_pezzo_g": res.get("peso_pezzo_g", ""),
                "fonte": urlparse(url).netloc if url.startswith("http") else "ricerca-web",
                "composizione": (dati or {}).get("composizione", []),
                "composizione_raw": (dati or {}).get("composizione_raw", ""),
                "additivi": (dati or {}).get("additivi", []),
                "coloranti": (dati or {}).get("coloranti", []),
                "allergeni": (dati or {}).get("allergeni", []),
                "avviso_coloranti_azoici": (dati or {}).get("avviso_coloranti_azoici", []),
                "verificato": False,
                "aggiornato_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.schede_tecniche.update_one(
                {"prodotto_key": key, "tipo": "produttore"}, {"$set": doc}, upsert=True
            )
            salvato_scheda = True
        # Formato confezione dalla scheda (richiesta Enzo 02/07: "quanti pezzi
        # ci sono per cartone"): diventa REGOLA NOTA nel dizionario, la stessa
        # che calcola_prezzo_quantita_kg usa con priorità 0, e che consente di
        # sapere i pezzi veri di ogni riga fattura (cartoni × pezzi/cartone).
        def _num(v):
            try:
                x = float(str(v).replace(",", ".").strip())
                return x if x > 0 else None
            except Exception:
                return None
        ppc = _num(res.get("pezzi_per_cartone"))
        peso_g = _num(res.get("peso_pezzo_g"))
        if confidenza == "alta" and (ppc or peso_g):
            upd = {}
            if ppc:
                upd["pezzi_per_cartone"] = ppc
                upd["pezzi_per_cartone_fonte"] = "scheda-tecnica-web"
            if peso_g:
                upd["peso_pezzo_g"] = peso_g
                # peso_confezione (kg) solo se mancante: mai sovrascrivere dati fattura
                upd_peso_kg = round((ppc or 1) * peso_g / 1000, 3)
            await db.dizionario_prodotti.update_many(
                {"$or": [{"nome_originale": descrizione},
                         {"nome_normalizzato": _key(descrizione)}]},
                {"$set": upd},
            )
            if peso_g:
                await db.dizionario_prodotti.update_many(
                    {"$or": [{"nome_originale": descrizione},
                             {"nome_normalizzato": _key(descrizione)}],
                     "$and": [{"$or": [{"peso_confezione": {"$exists": False}},
                                        {"peso_confezione": None},
                                        {"peso_confezione": 0}]}]},
                    {"$set": {"peso_confezione": upd_peso_kg,
                              "tipo_quantita": "conteggio_confezioni"}},
                )
        if canonico and _impara_mapping:
            await _impara_mapping(descrizione, canonico)
            # Completa il dizionario SOLO dove il canonico manca (mai sovrascrivere)
            await db.dizionario_prodotti.update_many(
                {"$and": [
                    {"$or": [{"nome_originale": descrizione},
                             {"nome_normalizzato": _key(descrizione)}]},
                    {"$or": [{"ingrediente_canonico": {"$exists": False}},
                             {"ingrediente_canonico": ""},
                             {"ingrediente_canonico": None}]},
                ]},
                {"$set": {"ingrediente_canonico": canonico,
                          **({"impiego": res.get("impiego")} if res.get("impiego") else {})}},
            )
            salvato_mapping = True

    return {
        "ok": True,
        "descrizione": descrizione,
        "prodotto_identificato": res.get("prodotto_identificato", ""),
        "marca": res.get("marca", ""),
        "nome_canonico": canonico or res.get("nome_canonico", ""),
        "impiego": res.get("impiego", ""),
        "url_scheda": url,
        "confidenza": confidenza,
        "composizione": (dati or {}).get("composizione", []),
        "allergeni": (dati or {}).get("allergeni", []),
        "coloranti": (dati or {}).get("coloranti", []),
        "pezzi_per_cartone": res.get("pezzi_per_cartone", ""),
        "peso_pezzo_g": res.get("peso_pezzo_g", ""),
        "salvato_scheda": salvato_scheda,
        "salvato_mapping": salvato_mapping,
    }


async def _coda_ricerca_web(q: str = None, impara: bool = False) -> list:
    """Coda di lavoro per la ricerca web: TUTTE le righe fattura distinte (fonte
    di verità: db.fatture.prodotti), ordinate per frequenza d'acquisto, MENO:
    non-alimentari/amministrative (filtri ufficiali), righe già mappate
    (nome_mapping), righe con scheda già salvata, righe già tentate 2 volte o
    già risolte. Si auto-aggiorna: le righe nuove di ogni import XML entrano
    da sole al giro successivo.
    Due regole di Enzo (02/07/2026):
    - se il matcher locale (L2) risolve già la riga, NIENTE ricerca web: con
      impara=True il mapping viene salvato subito, gratis (è il caso verdure/
      ortofrutta: "Peperoni L.031-..." ha il lotto privato del venditore,
      introvabile sul web, ma L2 la risolve in "Peperoni");
    - i DETERSIVI entrano in coda con tipo='chimico': per l'HACCP serve la
      scheda di sicurezza (principi attivi, pericoli per l'uomo)."""
    from app.lotti.routers.prodotti_master import _RX_NON_ORDINABILI
    from app.lotti.routers.classificatore_alimenti import e_non_food_certo, RX_DETERSIVI
    from app.lotti.routers.ingredienti import match_livello2, _impara_mapping

    grouped = await db.fatture.aggregate([
        {"$unwind": "$prodotti"},
        {"$project": {
            "d": {"$trim": {"input": {"$toLower": {"$ifNull": ["$prodotti.descrizione", ""]}}}},
            "orig": "$prodotti.descrizione",
            "fornitore": 1,
        }},
        {"$match": {"d": {"$ne": ""}}},
        {"$group": {"_id": "$d", "n": {"$sum": 1},
                    "descrizione": {"$first": "$orig"},
                    "fornitore": {"$first": "$fornitore"}}},
        {"$sort": {"n": -1}},
    ]).to_list(20000)

    mappate = {m.get("descrizione_key") for m in await db.nome_mapping.find(
        {}, {"_id": 0, "descrizione_key": 1}).to_list(100000)}
    con_scheda = {s.get("prodotto_key") for s in await db.schede_tecniche.find(
        {"tipo": {"$in": ["produttore", "sicurezza"]}},
        {"_id": 0, "prodotto_key": 1}).to_list(100000)}
    tentate = {t.get("key") for t in await db.ricerca_web_tentativi.find(
        {"$or": [{"salvato": True}, {"tentativi": {"$gte": 2}},
                 {"escluso": True}]},  # escluso = flag manuale di Enzo (mai cercare)
        {"_id": 0, "key": 1}).to_list(100000)}
    # flag "cerca" di Enzo: la riga va cercata ANCHE se i filtri automatici la
    # scarterebbero (il flag manuale vince sui filtri)
    forzate = {t.get("key") for t in await db.ricerca_web_tentativi.find(
        {"fonte_flag": "enzo", "escluso": False},
        {"_id": 0, "key": 1}).to_list(100000)}

    coda, visti = [], set()
    rx_junk = re.compile(_RX_NON_ORDINABILI, re.IGNORECASE)
    for g in grouped:
        desc = (g.get("descrizione") or "").strip()
        key = _key(desc)
        if not key or key in visti or len(desc) < 5:
            continue
        visti.add(key)
        if key in mappate or key in con_scheda or key in tentate:
            continue
        if q and q.lower() not in desc.lower():
            continue
        chimico = bool(RX_DETERSIVI.search(desc))
        if not chimico and key not in forzate:
            if _is_non_alimentare(desc) or e_non_food_certo(desc) or rx_junk.search(desc):
                continue
            # risolvibile in locale? niente web: impara il mapping e passa oltre
            canonico_l2 = match_livello2(desc)
            if canonico_l2:
                if impara:
                    await _impara_mapping(desc, canonico_l2)
                continue
        coda.append({"descrizione": desc, "fornitore": g.get("fornitore") or "",
                     "occorrenze": g.get("n", 1),
                     "tipo": "chimico" if chimico else "alimento"})
    return coda


async def esegui_ricerca_web_batch(limit: int = 3, q: str = None, budget_s: int = 65) -> dict:
    """Processa i primi `limit` elementi della coda (più frequenti prima) con
    stop a `budget_s` secondi. Ogni tentativo viene memorizzato in
    ricerca_web_tentativi (max 2 tentativi per riga, poi si smette di provarci:
    niente retry infiniti sulle righe non identificabili). Riusata da endpoint
    e job scheduler — un solo motore."""
    import time as _time
    coda = await _coda_ricerca_web(q=q, impara=True)
    inizio = _time.monotonic()
    risultati = []
    salvati = 0
    for cand in coda[:max(0, limit)]:
        if _time.monotonic() - inizio > budget_s:
            break
        try:
            r = await ricerca_web({"descrizione": cand["descrizione"],
                                   "fornitore": cand["fornitore"],
                                   "tipo": cand.get("tipo"), "salva": True})
        except HTTPException as e:
            r = {"descrizione": cand["descrizione"], "errore": str(e.detail)}
        ok_salvato = bool(r.get("salvato_mapping") or r.get("salvato_scheda"))
        salvati += 1 if ok_salvato else 0
        await db.ricerca_web_tentativi.update_one(
            {"key": _key(cand["descrizione"])},
            {"$set": {
                "key": _key(cand["descrizione"]),
                "descrizione": cand["descrizione"],
                "esito": r.get("confidenza") or ("errore" if r.get("errore") else "?"),
                "salvato": ok_salvato,
                "ultimo_at": datetime.now(timezone.utc).isoformat(),
            }, "$inc": {"tentativi": 1}},
            upsert=True,
        )
        risultati.append(r)
    return {
        "ok": True,
        "in_coda": len(coda),
        "processati": len(risultati),
        "salvati": salvati,
        "risultati": risultati,
    }


@router.post("/ricerca-web-batch")
async def ricerca_web_batch(
    limit: int = Query(3, le=5, description="Quanti prodotti processare (budget tempo Render)"),
    q: str = Query(None, description="Filtro testo sul nome"),
):
    """Esegue la ricerca web sulle righe fattura in coda (le più frequenti prima).
    Max 5 per chiamata e stop dopo ~65s per il timeout Render; lo stesso motore
    gira anche da solo nello scheduler (job ricerca_web_prodotti)."""
    return await esegui_ricerca_web_batch(limit=limit, q=q)


@router.post("/ricerca-web-flag")
async def ricerca_web_flag(payload: dict = Body(...)):
    """Applica il file-checklist di Enzo: `cerca` = righe DA cercare (rientrano
    in coda anche se erano state sospese: tentativi azzerati), `escludi` =
    righe da NON cercare MAI (flag manuale permanente, vince su tutto).
    Body: {cerca: [descrizioni], escludi: [descrizioni]}."""
    cerca = [str(d).strip() for d in (payload.get("cerca") or []) if str(d).strip()]
    escludi = [str(d).strip() for d in (payload.get("escludi") or []) if str(d).strip()]
    if not cerca and not escludi:
        raise HTTPException(400, "nessuna descrizione in cerca/escludi")
    now = datetime.now(timezone.utc).isoformat()
    for d in escludi:
        await db.ricerca_web_tentativi.update_one(
            {"key": _key(d)},
            {"$set": {"key": _key(d), "descrizione": d, "escluso": True,
                      "fonte_flag": "enzo", "ultimo_at": now}},
            upsert=True,
        )
    for d in cerca:
        await db.ricerca_web_tentativi.update_one(
            {"key": _key(d)},
            {"$set": {"key": _key(d), "descrizione": d, "escluso": False,
                      "tentativi": 0, "salvato": False,
                      "fonte_flag": "enzo", "ultimo_at": now}},
            upsert=True,
        )
    return {"ok": True, "esclusi": len(escludi), "da_cercare": len(cerca)}


@router.get("/ricerca-web-stato")
async def ricerca_web_stato(full: bool = Query(False, description="True = coda completa (per la checklist di Enzo)")):
    """Avanzamento della campagna di identificazione: quante righe restano in
    coda, quante tentate, quante salvate. Per monitorare il lavoro in background.
    Con full=true restituisce la coda intera (serve a generare la checklist
    che Enzo compila coi flag)."""
    coda = await _coda_ricerca_web()
    tentati = await db.ricerca_web_tentativi.count_documents({})
    salvati = await db.ricerca_web_tentativi.count_documents({"salvato": True})
    esauriti = await db.ricerca_web_tentativi.count_documents(
        {"salvato": {"$ne": True}, "tentativi": {"$gte": 2}, "escluso": {"$ne": True}})
    ultimi = await db.ricerca_web_tentativi.find(
        {}, {"_id": 0}).sort("ultimo_at", -1).to_list(10)
    sospese = await db.ricerca_web_tentativi.find(
        {"salvato": {"$ne": True}, "tentativi": {"$gte": 2}, "escluso": {"$ne": True}},
        {"_id": 0, "descrizione": 1, "esito": 1}).to_list(1000) if full else []
    return {"in_coda": len(coda), "tentati_totali": tentati, "salvati": salvati,
            "non_identificabili": esauriti, "ultimi_tentativi": ultimi,
            "prossimi": coda[:10],
            **({"coda": coda, "sospese": sospese} if full else {})}
