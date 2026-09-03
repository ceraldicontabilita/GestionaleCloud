import logging
import re
_LOG_INIT = logging.getLogger("uvicorn.error")
"""
Router Stampa — endpoint centralizzato per etichette lotto POS 80mm.
Unica fonte di verità per la logica di stampa (allergeni, ordinamento, HTML).
GET /api/stampa/lotto/{id_o_numero_lotto} → HTML pronto per window.print()
"""

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import HTMLResponse
from datetime import datetime, timezone

from app.lotti.db import database as db
from app.lotti.azienda import get_azienda

router = APIRouter(prefix="/stampa", tags=["Stampa"])

# ── Dizionario allergeni (Reg. UE 1169/2011) ─────────────────────────────────
ALLERGENI_KW = {
    "CEREALI/GLUTINE": [
        "glutine",
        "grano",
        "frumento",
        "orzo",
        "segale",
        "avena",
        "farro",
        "semola",
        "farina",
    ],
    "UOVA": ["uov", "tuorlo", "albume"],
    "LATTE": [
        "latte",
        "panna",
        "burro",
        "formaggio",
        "mozzarella",
        "ricotta",
        "parmigiano",
        "pecorino",
        "mascarpone",
    ],
    "ARACHIDI": ["arachide"],
    "SOIA": ["soia"],
    "PESCE": ["pesce", "alici", "acciughe", "tonno", "salmone", "baccalà"],
    "CROSTACEI": ["gamberi", "aragoste", "granchi", "scampi"],
    "FRUTTA A GUSCIO": ["noci", "mandorle", "nocciole", "pistacchio", "pinoli"],
    "SEDANO": ["sedano"],
    "SENAPE": ["senape"],
    "SESAMO": ["sesamo"],
    "SOLFITI": ["solfiti", "anidride solforosa"],
    "LUPINO": ["lupino"],
    "MOLLUSCHI": ["molluschi", "cozze", "vongole", "polpo", "calamari"],
}

POS_CSS = """
  @page { size: 80mm auto; margin: 0; }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: Arial, Helvetica, sans-serif;
    font-size: 8pt; font-weight: 700; line-height: 1.25;
    width: 72mm; padding: 1.5mm 2mm 4mm 2mm;
    color: #000; background: #fff;
    -webkit-print-color-adjust: exact; print-color-adjust: exact;
  }
  .azienda { text-align: center; font-size: 6pt; font-weight: 500; color: #666; margin-bottom: 0.5mm; }
  .titolo-sezione { text-align: center; font-size: 10pt; font-weight: 900; letter-spacing: 2px; text-transform: uppercase; margin-bottom: 0.5mm; }
  .prodotto-nome { text-align: center; font-size: 9pt; font-weight: 900; text-transform: uppercase; letter-spacing: 0.5px; word-break: break-word; margin-bottom: 0.5mm; }
  .lotto-box { border: 2px solid #000; text-align: center; padding: 1mm 1.5mm; font-size: 8pt; font-weight: 900; font-family: 'Courier New', monospace; letter-spacing: 0.5px; margin: 1mm 0; word-break: break-all; }
  .qty-box { text-align: center; font-size: 9pt; font-weight: 900; margin-bottom: 0.5mm; color: #000; }
  .row { display: flex; justify-content: space-between; font-size: 7.5pt; font-weight: 700; padding: 0.5mm 0; border-bottom: 1px solid #aaa; color: #000; gap: 3mm; }
  .row .label { font-weight: 900; white-space: nowrap; }
  .row .val   { font-weight: 900; text-align: right; color: #000; }
  .row.scad .val { text-decoration: underline; }
  .row.frigo .val { border: 1px solid #000; padding: 0.2mm 0.8mm; font-size: 7pt; }
  .sep-solid { border-top: 2px solid #000; margin: 1mm 0; }
  .sep-dash  { border-top: 1px dashed #000; margin: 1mm 0; }
  .ing-title { font-size: 7pt; font-weight: 900; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 0.8mm; }
  .ing { font-size: 6.5pt; font-weight: 700; padding: 0.4mm 0; border-bottom: 1px dotted #666; word-break: break-word; color: #000; }
  .ing.allergene { font-weight: 900; }
  .ing.allergene::before { content: "! "; font-weight: 900; }
  .allergeni-box { border: 2px solid #000; padding: 1.5mm; margin-top: 1mm; background: #fff; }
  .allergeni-title { font-size: 7pt; font-weight: 900; text-transform: uppercase; letter-spacing: 0.3px; text-align: center; border-bottom: 1px solid #000; padding-bottom: 1mm; margin-bottom: 1mm; color: #000; }
  .allergeni-list { font-size: 7.5pt; font-weight: 900; word-break: break-word; text-align: center; color: #000; line-height: 1.4; }
  .no-allergeni { font-size: 7pt; font-weight: 700; text-align: center; margin-top: 1mm; color: #000; }
  .trac-title { font-size: 7pt; font-weight: 900; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 0.8mm; margin-top: 1mm; }
  .trac-row { font-size: 6pt; font-weight: 700; padding: 0.8mm 0; border-bottom: 1px dotted #888; line-height: 1.3; }
  .trac-row .trac-lotto { font-family: 'Courier New', monospace; font-weight: 900; font-size: 6.5pt; }
  .trac-row .trac-fornitore { font-weight: 700; color: #000; }
  .trac-row .trac-scad { font-weight: 900; text-decoration: underline; }
  .trac-non-trovati { font-size: 5.5pt; color: #888; font-style: italic; margin-top: 0.5mm; }
  .etichetta-finale { border: 1.5px solid #000; padding: 1.5mm; margin-top: 1.5mm; font-size: 7.5pt; font-weight: 900; text-align: center; word-break: break-word; line-height: 1.4; }
  .footer { margin-top: 1.5mm; border-top: 1px solid #000; padding-top: 1mm; font-size: 6pt; font-weight: 600; text-align: center; line-height: 1.4; }
"""


def rileva_allergeni(testo: str) -> list:
    t = testo.lower()
    return [nome for nome, kws in ALLERGENI_KW.items() if any(k in t for k in kws)]


def ordina_ingredienti(ingredienti: list, allergeni: list) -> list:
    def ha_allergene(ing: str) -> bool:
        i = ing.lower()
        return any(kw in i for kws in ALLERGENI_KW.values() for kw in kws) or (
            "contiene" in i and "non contiene" not in i
        )

    return sorted(ingredienti, key=lambda x: (0 if ha_allergene(x) else 1, x))


def build_pos_html(lotto: dict, allergeni: list, ingredienti: list, nutri_html: str = "", azienda=None) -> str:
    _az = azienda or {}
    _nome_az = _az.get("ragione_sociale") or "Ceraldi Group S.r.l."
    _ind_az = _az.get("indirizzo") or ""
    data_ora = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M")

    # ── Righe ingredienti ──────────────────────────────────────────────────
    if ingredienti:
        # Mappa ingrediente -> fornitore/fattura (dalla tracciabilità FIFO), così
        # la sezione INGREDIENTI mostra DA DOVE viene ogni ingrediente.
        _ls_map = (lotto.get("lotti_fornitori") or {}).get("lotti_scalati") or []
        trac_map = {}
        for ls in _ls_map:
            k = (ls.get("ingrediente") or ls.get("prodotto") or "").strip().lower()
            if not k:
                continue
            lid = ls.get("lotto_id_fornitore") or ""
            fat = str(ls.get("fattura_ref") or "").strip()
            if fat:
                src = "Fatt. " + fat
            elif lid.startswith("FAT-"):
                src = "Fatt. " + lid.replace("FAT-", "")
            elif ls.get("da_dizionario"):
                src = "MAG"
            elif lid and lid.upper() != "N/D":
                src = "LOT " + lid
            else:
                src = ""
            # DATA della fattura accanto al numero (richiesta Enzo 25/07/2026:
            # sull'etichetta c'era "Fatt. 1/56437" ma non quando è arrivata la
            # merce — davanti all'ASL il numero da solo non basta a datare il
            # lotto d'origine).
            data_f = str(ls.get("data_fattura") or "").strip()
            if data_f and src.startswith("Fatt."):
                src += f" del {data_f}"
            etich = " · ".join(p for p in (ls.get("fornitore") or "", src) if p)
            if etich:
                trac_map.setdefault(k, etich)

        def _trac_for(nome):
            kk = (nome or "").strip().lower()
            if kk in trac_map:
                return trac_map[kk]
            for key, val in trac_map.items():
                if key and (key in kk or kk in key):
                    return val
            return ""

        parti = []
        for i in ingredienti:
            cls = "ing  allergene" if ("contiene" in i.lower() and "non contiene" not in i.lower()) else "ing"
            et = _trac_for(i)
            src_html = f'<span style="font-size:5.5pt;color:#000;font-weight:700;"> — {et}</span>' if et else ""
            parti.append(f'<div class="{cls}">• {i}{src_html}</div>')
        righe_ing = "".join(parti)
    else:
        righe_ing = '<div class="ing">Dati non disponibili</div>'

    # ── Sezione allergeni ──────────────────────────────────────────────────
    if allergeni:
        sezione_allergeni = f"""<div class="allergeni-box">
  <div class="allergeni-title">!!! ALLERGENI (Reg. UE 1169/2011) !!!</div>
  <div class="allergeni-list">{" · ".join(allergeni)}</div>
</div>"""
    else:
        sezione_allergeni = (
            '<div class="no-allergeni">&#10003; Non contiene allergeni dichiarati</div>'
        )

    # ── Sezione tracciabilità ──────────────────────────────────────────────
    lotti_scalati = (lotto.get("lotti_fornitori") or {}).get("lotti_scalati") or []
    ingredienti_non_trovati = (lotto.get("lotti_fornitori") or {}).get(
        "ingredienti_non_trovati"
    ) or []

    sezione_trac = ""
    if lotti_scalati:
        righe_scalati = []
        for ls in lotti_scalati:
            is_fat = (ls.get("lotto_id_fornitore") or "").startswith("FAT-")
            is_diz = ls.get("da_dizionario") is True
            num = (ls.get("lotto_id_fornitore") or "N/D").replace("FAT-", "")
            if is_diz:
                badge = f'<span class="trac-lotto" style="background:#e0f2fe;color:#000;">MAG: {num}</span>'
            elif is_fat:
                badge = f'<span class="trac-lotto" style="background:#fef3c7;color:#000;">FAT: {num}</span>'
            else:
                badge = f'<span class="trac-lotto">LOT: {num}</span>'
            scad_html = (
                f'<span class="trac-scad"> | Scad: {ls["data_scadenza"]}</span>'
                if ls.get("data_scadenza")
                else ""
            )
            fat_data_html = (
                f'<span style="font-size:6pt;color:#000;font-weight:700;"> | Data Fattura: {ls["data_fattura"]}</span>'
                if is_fat and ls.get("data_fattura")
                else ""
            )
            qtà_used = ls.get("quantita_consumata")
            qtà_rim = ls.get("quantita_rimasta")
            unita = ls.get("unita") or ""
            esaurito = " · ⚠ ESAURITO" if ls.get("esaurito") else ""
            qty_txt = f"Qtà usata: {qtà_used} {unita} · " if qtà_used is not None else ""
            qty_txt += (
                f"Rimasto in magazzino: {qtà_rim if qtà_rim is not None else '—'} {unita}{esaurito}"
            )
            semi_html = (
                f'<div style="font-size:5pt;color:#000;">↳ da semilavorato: {ls["_semilavorato"]}</div>'
                if ls.get("_semilavorato")
                else ""
            )
            row_style = ' style="margin-left:3mm;border-left:2px solid #bae6fd;padding-left:1.5mm;"' if ls.get("_semilavorato") else ""
            righe_scalati.append(f"""<div class="trac-row"{row_style}>
  {semi_html}{badge}{scad_html}{fat_data_html}
  <br/><span class="trac-fornitore">{ls.get("fornitore") or "—"}</span>
  <br/><span>{ls.get("prodotto") or ls.get("ingrediente") or "—"}</span>
  <br/><span style="font-size:5.5pt;font-weight:bold;">{qty_txt}</span>
</div>""")
        non_trac_html = (
            f'<div class="trac-non-trovati">Non tracciati: {", ".join(ingredienti_non_trovati)}</div>'
            if ingredienti_non_trovati
            else ""
        )
        sezione_trac = f"""<div class="sep-dash"></div>
<div class="trac-title">Tracciabilità Fornitori (Controllo a Ritroso · Reg. CE 178/2002)</div>
{"".join(righe_scalati)}{non_trac_html}"""
    elif lotto.get("ingredienti_dettaglio"):
        righe_ing_fb = []
        for ing in lotto.get("ingredienti_dettaglio") or []:
            nome_ing = ing if isinstance(ing, str) else (ing.get("nome") or "?")
            righe_ing_fb.append(f"""<div class="trac-row">
  <span class="trac-lotto" style="background:#f3f4f6;color:#374151;">ING</span>
  <br/><span>{nome_ing}</span>
  <br/><span style="font-size:5.5pt;color:#6b7280;">Rimanenza magazzino: verificare manualmente</span>
</div>""")
        sezione_trac = f"""<div class="sep-dash"></div>
<div class="trac-title">Ingredienti (Tracciabilità in elaborazione — Reg. CE 178/2002)</div>
{"".join(righe_ing_fb)}"""

    # ── Campi lotto ────────────────────────────────────────────────────────
    prodotto = lotto.get("prodotto") or lotto.get("prodotto_nome") or ""
    numero_lotto = lotto.get("numero_lotto") or "N/D"
    pezzi = lotto.get("pezzi") or lotto.get("quantita")
    unita = lotto.get("unita") or lotto.get("unita_misura") or "pz"
    qty_box = f'<div class="qty-box">QTA: {pezzi} {unita}</div>' if pezzi else ""
    data_prod = lotto.get("data_produzione") or "—"
    data_scad = lotto.get("data_scadenza") or "—"
    scad_abbattuto = lotto.get("scadenza_abbattuto") or ""
    frigo = lotto.get("frigo_numero") or ""
    allergie_str = " · ".join(allergeni) if allergeni else ""

    ing_section = (
        f'<div class="sep-dash"></div><div class="ing-title">INGREDIENTI + TRACCIABILITA:</div>{righe_ing}'
        if ingredienti
        else ""
    )

    etichetta_finale_extra = f"<br/>CONTIENE: {allergie_str}" if allergeni else ""

    return f"""<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="UTF-8"/>
  <title>Lotto {numero_lotto}</title>
  <style>{POS_CSS}</style>
</head>
<body>
  <div class="titolo-sezione">LOTTO</div>
  <div class="lotto-box">{numero_lotto}</div>
  {qty_box}
  <div class="sep-solid"></div>
  <div class="row"><span class="label">PRODOTTO:</span><span class="val">{data_prod}</span></div>
  <div class="row scad"><span class="label">SCADENZA:</span><span class="val">{data_scad}</span></div>
  {f'<div class="row"><span class="label">SCAD -18°C:</span><span class="val">{scad_abbattuto}</span></div>' if scad_abbattuto else ""}
  {f'<div class="row frigo"><span class="label">FRIGO:</span><span class="val">{frigo}</span></div>' if frigo else ""}
  {ing_section}
  {nutri_html}
  {sezione_allergeni}
  <div class="etichetta-finale">
    {prodotto.upper()} · {data_prod}{etichetta_finale_extra}
  </div>
  <div class="footer">
    Stampato: {data_ora}<br/>
    Reg. CE 178/2002 — {_nome_az}
  </div>
  <script>window.onload = () => {{ setTimeout(() => {{ window.print(); window.onafterprint = () => window.close(); }}, 250); }}</script>
</body>
</html>"""


async def _espandi_ritroso(lotti_scalati, depth=2, visti=None):
    """Tracciabilità a ritroso COMPLETA: se un ingrediente consumato è un
    semilavorato (esiste un lotto di produzione con quel prodotto e una propria
    tracciabilità), aggiunge ricorsivamente i suoi lotti scalati, così si risale
    fino alle fatture e non ci si ferma alla produzione precedente. Best-effort:
    non solleva mai, limitata in profondità per evitare cicli."""
    if depth <= 0 or not lotti_scalati:
        return lotti_scalati or []
    visti = visti if visti is not None else set()
    out = []
    for ls in lotti_scalati:
        out.append(ls)
        nome = (ls.get("prodotto") or ls.get("ingrediente") or "").strip().lower()
        if not nome or nome in visti:
            continue
        visti.add(nome)
        try:
            rx = re.escape(nome[:18])
            semi = await db.lotti.find_one(
                {
                    "$and": [
                        {"$or": [
                            {"prodotto": {"$regex": rx, "$options": "i"}},
                            {"prodotto_nome": {"$regex": rx, "$options": "i"}},
                        ]},
                        {"lotti_fornitori.lotti_scalati.0": {"$exists": True}},
                    ]
                },
                {"_id": 0, "lotti_fornitori": 1, "numero_lotto": 1, "prodotto": 1},
                sort=[("data_produzione", -1)],
            )
        except Exception:
            semi = None
        if semi:
            sub = (semi.get("lotti_fornitori") or {}).get("lotti_scalati") or []
            sub = await _espandi_ritroso(sub, depth - 1, visti)
            origine = ls.get("prodotto") or ls.get("ingrediente") or nome
            for s in sub:
                out.append({**s, "_semilavorato": origine})
    return out


# ── Endpoint ───────────────────────────────────────────────────────────────────
def _esc_enc(s: str) -> bytes:
    """Codifica testo per stampante ESC/POS (codepage CP437), con fallback ASCII
    per i caratteri non rappresentabili. Niente HTML: solo testo per la termica."""
    import unicodedata
    repl = {"·": "-", "–": "-", "—": "-", "’": "'", "€": "EUR", "✓": "OK"}
    out = bytearray()
    for c in s:
        c = repl.get(c, c)
        try:
            out += c.encode("cp437")
        except UnicodeEncodeError:
            d = unicodedata.normalize("NFKD", c).encode("ascii", "ignore")
            out += d if d else b"?"
    return bytes(out)


def build_escpos(lotto: dict, allergeni: list, ingredienti: list, larghezza: int = 48) -> bytes:
    """Etichetta lotto in ESC/POS puro (per Epson di rete via socket :9100).
    Stessi dati dell'etichetta HTML, senza intestazione azienda (c'è il logo)
    e senza il nome prodotto sotto LOTTO (resta in coda)."""
    INIT = b"\x1b\x40"            # ESC @  reset
    CP437 = b"\x1b\x74\x00"       # ESC t 0  codepage
    AL_C = b"\x1b\x61\x01"; AL_L = b"\x1b\x61\x00"   # align center / left
    B_ON = b"\x1b\x45\x01"; B_OFF = b"\x1b\x45\x00"  # bold on/off
    SZ = lambda n: b"\x1d\x21" + bytes([n])          # GS ! n  (0=normale,0x11=2x,0x01=2xh)
    NL = b"\n"
    CUT = b"\n\n\n\x1d\x56\x42\x00"                   # feed + full cut
    sep = _esc_enc("-" * larghezza) + NL

    def line(s="", center=False, bold=False, big=False):
        out = bytearray()
        out += AL_C if center else AL_L
        if big:
            out += SZ(0x11)
        if bold:
            out += B_ON
        out += _esc_enc(s) + NL
        if bold:
            out += B_OFF
        if big:
            out += SZ(0x00)
        return bytes(out)

    prodotto = lotto.get("prodotto") or lotto.get("prodotto_nome") or ""
    numero_lotto = lotto.get("numero_lotto") or "N/D"
    pezzi = lotto.get("pezzi") or lotto.get("quantita")
    unita = lotto.get("unita") or lotto.get("unita_misura") or "pz"
    data_prod = lotto.get("data_produzione") or "—"
    data_scad = lotto.get("data_scadenza") or "—"
    scad_abb = lotto.get("scadenza_abbattuto") or ""
    frigo = lotto.get("frigo_numero") or ""

    # Mappa ingrediente -> "Fornitore - Fatt. X" (dalla tracciabilità, come l'HTML)
    lotti_scalati = (lotto.get("lotti_fornitori") or {}).get("lotti_scalati") or []
    trac = {}
    for ls in lotti_scalati:
        k = (ls.get("ingrediente") or ls.get("prodotto") or "").strip().lower()
        if not k:
            continue
        fat = str(ls.get("fattura_ref") or "").strip()
        lid = ls.get("lotto_id_fornitore") or ""
        src = ("Fatt. " + fat) if fat else (("Fatt. " + lid.replace("FAT-", "")) if lid.startswith("FAT-") else "")
        # stessa aggiunta della stampa HTML: numero fattura + data (25/07/2026)
        data_f = str(ls.get("data_fattura") or "").strip()
        if data_f and src.startswith("Fatt."):
            src += f" del {data_f}"
        et = " - ".join(p for p in ((ls.get("fornitore") or ""), src) if p)
        if et:
            trac[k] = et

    def trac_for(ing):
        kk = ing.lower()
        for k, v in trac.items():
            if k and (k in kk or kk in k):
                return v
        return ""

    buf = bytearray()
    buf += INIT + CP437
    buf += line("LOTTO", center=True, bold=True)
    buf += line(numero_lotto, center=True, big=True)
    if pezzi:
        buf += line(f"QTA: {pezzi} {unita}", center=True, bold=True)
    buf += sep
    buf += line(f"PRODOTTO: {data_prod}")
    buf += line(f"SCADENZA: {data_scad}", bold=True)
    if scad_abb:
        buf += line(f"SCAD -18°C: {scad_abb}")
    if frigo:
        buf += line(f"FRIGO: {frigo}")
    if ingredienti:
        buf += sep
        buf += line("INGREDIENTI + TRACCIABILITA:", bold=True)
        for i in ingredienti:
            buf += line(f"- {i}")
            et = trac_for(i)
            if et:
                buf += line(f"    {et}")
    buf += sep
    if allergeni:
        buf += line("ALLERGENI (Reg. UE 1169/2011):", bold=True)
        buf += line(" - ".join(allergeni), bold=True)
    else:
        buf += line("Non contiene allergeni dichiarati")
    buf += sep
    buf += line(f"{prodotto.upper()} - {data_prod}", center=True, bold=True)
    buf += line(f"Stampato: {datetime.now().strftime('%d/%m/%Y %H:%M')}", center=True)
    buf += line("Reg. CE 178/2002", center=True)
    buf += CUT
    return bytes(buf)


async def _carica_lotto_tracciato(lotto_id: str):
    """Carica il lotto, arricchisce la tracciabilità (FIFO vivo + fattura) e
    calcola ingredienti ordinati + allergeni. Condivisa da stampa HTML ed ESC/POS."""
    lotto = await db.lotti.find_one(
        {"$or": [{"id": lotto_id}, {"numero_lotto": lotto_id}]},
        {"_id": 0},
    )
    if not lotto:
        raise HTTPException(status_code=404, detail=f"Lotto '{lotto_id}' non trovato")

    # Arricchisci ogni lotto consumato col NUMERO FATTURA reale (da lotti_fornitori),
    # così la sezione INGREDIENTI mostra il numero fattura del fornitore.
    _lf = lotto.get("lotti_fornitori") or {}
    _ls_list = _lf.get("lotti_scalati") or []

    # Se la produzione NON ha congelato la tracciabilità (lotti_scalati vuoto),
    # risolvila AL VOLO dal FIFO attivo — stessa fonte di /ricette/{id}/tracciabilita-fifo —
    # così l'etichetta mostra SEMPRE fornitore+fattura, coerente tra tutte le ricette.
    # NON tocca le produzioni che hanno già i lotti reali congelati (record HACCP veri).
    if not _ls_list:
        try:
            from app.lotti.routers.lotti_produzione import peek_lotto_fifo_attivo
            _ric_id = lotto.get("ricetta_id") or lotto.get("ricetta_nome", "")
            _ric = await db.ricette.find_one(
                {"$or": [{"id": _ric_id}, {"nome": _ric_id}]},
                {"_id": 0, "ingredienti_dettaglio": 1},
            ) if _ric_id else None
            _dett = (_ric or {}).get("ingredienti_dettaglio") or lotto.get("ingredienti_dettaglio") or []
            _live = []
            for _d in _dett:
                if not isinstance(_d, dict):
                    _d = {"nome": _d}
                _nome_i = (_d.get("nome") or "").strip()
                if not _nome_i:
                    continue
                _lfatt = await peek_lotto_fifo_attivo(_d)
                if _lfatt:
                    _live.append({
                        "ingrediente": _nome_i,
                        "fornitore": _lfatt.get("fornitore") or "",
                        "lotto_id": _lfatt.get("id") or "",
                        "lotto_id_fornitore": _lfatt.get("lotto_id_fornitore") or "",
                        "data_fattura": _lfatt.get("data_fattura") or "",
                    })
            if _live:
                _ls_list = _live
        except Exception:
            _LOG_INIT.debug("[stampa] FIFO live non disponibile (fallback ignorato)")

    if _ls_list:
        for ls in _ls_list:
            lid = ls.get("lotto_id")
            if lid and not ls.get("fattura_ref"):
                try:
                    doc = await db.lotti_fornitori.find_one(
                        {"id": lid}, {"_id": 0, "fattura_ref": 1, "data_fattura": 1}
                    )
                    if doc:
                        ls["fattura_ref"] = doc.get("fattura_ref") or ""
                        if not ls.get("data_fattura"):
                            ls["data_fattura"] = doc.get("data_fattura") or ""
                except Exception:
                    pass
        lotto = {**lotto, "lotti_fornitori": {**_lf, "lotti_scalati": _ls_list}}

    ingredienti_raw = lotto.get("ingredienti_dettaglio") or []
    ingredienti = [i if isinstance(i, str) else i.get("nome", "") for i in ingredienti_raw if i]
    testo_completo = " ".join(ingredienti) + " " + (lotto.get("allergeni_testo") or "")
    allergeni = rileva_allergeni(testo_completo)
    ingredienti_ordinati = ordina_ingredienti(ingredienti, allergeni)
    return lotto, ingredienti_ordinati, allergeni


@router.get("/lotto/{lotto_id}", response_class=HTMLResponse)
async def stampa_lotto(lotto_id: str, mostra_nutrizionali: bool = False):
    """Genera HTML etichetta POS 80mm per un lotto (per id o numero_lotto).
    Aggiungere ?mostra_nutrizionali=true per includere la tabella nutrizionale.
    """
    lotto, ingredienti_ordinati, allergeni = await _carica_lotto_tracciato(lotto_id)

    # ── Calcola valori nutrizionali se richiesti o se la ricetta li ha ──────
    nutri_html = ""
    ricetta_id = lotto.get("ricetta_id") or lotto.get("ricetta_nome", "")
    if mostra_nutrizionali and ricetta_id:
        try:
            from app.lotti.routers.ricette import get_nutrizionali

            ricetta_doc = await db.ricette.find_one(
                {"$or": [{"id": ricetta_id}, {"nome": ricetta_id}]}, {"_id": 0}
            )
            if ricetta_doc:
                nutri = await get_nutrizionali(ricetta_doc["id"])
                pp = nutri.get("per_porzione", {})
                if pp and pp.get("kcal", 0) > 0:
                    nutri_html = f"""<div class="sep-dash"></div>
<div class="trac-title">VALORI NUTRIZIONALI per porzione</div>
<div class="row"><span class="label">Energia:</span><span class="val">{pp.get('kcal',0)} kcal</span></div>
<div class="row"><span class="label">Grassi:</span><span class="val">{pp.get('grassi',0)} g</span></div>
<div class="row"><span class="label">Carboidrati:</span><span class="val">{pp.get('carb',0)} g</span></div>
<div class="row"><span class="label">Proteine:</span><span class="val">{pp.get('prot',0)} g</span></div>
<div style="font-size:5pt;color:#9ca3af;margin-top:1mm;">* Valori stimati — non da analisi di laboratorio</div>"""
        except Exception:
            _LOG_INIT.debug("[stampa] errore non bloccante ignorato")

    html = build_pos_html(lotto, allergeni, ingredienti_ordinati, nutri_html=nutri_html, azienda=await get_azienda())
    return HTMLResponse(content=html)


@router.get("/lotto/{lotto_id}/escpos")
async def stampa_lotto_escpos(lotto_id: str):
    """Etichetta lotto in ESC/POS puro (byte) per stampa diretta su Epson di rete
    (socket :9100). La invia l'agente locale, che la scrive sul socket della
    stampante mappata. Niente HTML, niente driver Windows."""
    lotto, ingredienti_ordinati, allergeni = await _carica_lotto_tracciato(lotto_id)
    data = build_escpos(lotto, allergeni, ingredienti_ordinati)
    return Response(content=data, media_type="application/octet-stream")


@router.get("/movimento/{movimento_id}", response_class=HTMLResponse)
async def stampa_movimento(movimento_id: str):
    """Distinta di movimentazione POS 80mm — richiesta Enzo 20/07/2026:
    quando manda al banco la giacenza già pronta (es. dal congelatore),
    l'operatore vuole una conferma stampabile di DA DOVE è stata presa la
    merce e che il movimento di tracciabilità è stato registrato."""
    mov = await db.movimenti_lotto.find_one({"id": movimento_id}, {"_id": 0})
    if not mov:
        raise HTTPException(404, "Movimento non trovato")

    def _label_posizione(p):
        if not p:
            return "—"
        return p.get("nome") or p.get("numero") or p.get("tipo") or "—"

    az = await get_azienda()
    _nome_az = (az or {}).get("ragione_sociale") or "Ceraldi Group S.r.l."
    data_ora_evento = (mov.get("data_ora") or "")[:16].replace("T", " ") or "—"
    data_ora_stampa = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M")
    quantita = mov.get("quantita")
    operatore = mov.get("operatore_nome") or "—"

    return HTMLResponse(content=f"""<!DOCTYPE html>
<html lang="it">
<head>
  <meta charset="UTF-8"/>
  <title>Movimento {mov.get('numero_lotto') or movimento_id}</title>
  <style>{POS_CSS}</style>
</head>
<body>
  <div class="titolo-sezione">DISTINTA DI MOVIMENTAZIONE</div>
  <div class="lotto-box">{mov.get('numero_lotto') or '—'}</div>
  <div class="sep-solid"></div>
  <div class="row"><span class="label">DA:</span><span class="val">{_label_posizione(mov.get('posizione_da'))}</span></div>
  <div class="row"><span class="label">A:</span><span class="val">{_label_posizione(mov.get('posizione_a'))}</span></div>
  <div class="row"><span class="label">QUANTITA:</span><span class="val">{quantita if quantita is not None else '—'}</span></div>
  <div class="row"><span class="label">DATA/ORA:</span><span class="val">{data_ora_evento}</span></div>
  <div class="row"><span class="label">OPERATORE:</span><span class="val">{operatore}</span></div>
  <div class="sep-dash"></div>
  <div class="etichetta-finale">
    &#10003; TRACCIABILITA REGISTRATA
  </div>
  <div class="footer">
    Stampato: {data_ora_stampa}<br/>
    Reg. CE 178/2002 — {_nome_az}
  </div>
  <script>window.onload = () => {{ setTimeout(() => {{ window.print(); window.onafterprint = () => window.close(); }}, 250); }}</script>
</body>
</html>""")


@router.get("/report-lotto/{lotto_id}", response_class=HTMLResponse)
async def stampa_report_lotto(lotto_id: str):
    """Report A4 del gemello digitale del lotto (SEPARATO dall'etichetta POS:
    mancava — audit onesto 04/07/2026): dati, ingredienti, provenienza
    fornitori e cronologia completa, pronto per il raccoglitore o per l'ASL."""
    from app.lotti.routers.lotti import get_scheda_completa_lotto
    import html as _html

    # accetta sia id sia numero_lotto (come l'etichetta)
    doc = await db.lotti.find_one(
        {"$or": [{"id": lotto_id}, {"numero_lotto": lotto_id}]}, {"_id": 0, "id": 1}
    )
    if not doc:
        raise HTTPException(404, "Lotto non trovato")
    scheda = await get_scheda_completa_lotto(doc["id"])
    l = scheda["lotto"]
    az = await get_azienda()
    e = _html.escape

    def _riga(label, val):
        return f"<tr><td class='k'>{e(label)}</td><td>{e(str(val if val not in (None, '') else '—'))}</td></tr>"

    dati = "".join([
        _riga("Prodotto", l.get("prodotto")),
        _riga("Numero lotto", l.get("numero_lotto")),
        _riga("Prodotto il", l.get("data_produzione")),
        _riga("Scade il", l.get("data_scadenza")),
        _riga("Quantità prodotta", f"{l.get('pezzi') or l.get('quantita') or '—'} {l.get('unita_misura') or ''}"),
        _riga("Quantità residua", f"{l.get('quantita') if l.get('quantita') is not None else '—'} {l.get('unita_misura') or ''}"),
        _riga("Stato", (l.get("stato_scadenza") or {}).get("label") or l.get("stato") or "—"),
        _riga("Posizione", l.get("frigo_numero") or "—"),
        _riga("Valore economico", f"€ {l.get('valore_economico'):.2f}" if l.get("valore_economico") is not None else "—"),
        _riga("Allergeni", l.get("allergeni_testo") or "—"),
        _riga("Ricetta", (scheda.get("ricetta_collegata") or {}).get("nome") or "—"),
    ])

    ingredienti = "".join(f"<li>{e(i)}</li>" for i in scheda.get("ingredienti") or []) or "<li>—</li>"

    prov = "".join(
        f"<tr><td>{e(s.get('ingrediente') or s.get('prodotto') or '—')}</td>"
        f"<td>{e(s.get('fornitore') or '—')}</td>"
        f"<td>{e(s.get('lotto_id_fornitore') or '—')}</td>"
        f"<td>{e(str(s.get('fattura_ref') or '—'))}</td>"
        f"<td>{e(str(s.get('quantita_consumata') or ''))} {e(s.get('unita') or '')}</td></tr>"
        for s in scheda.get("lotti_fornitori_scalati") or []
    ) or "<tr><td colspan='5'>—</td></tr>"

    cron = "".join(
        f"<tr><td>{e((m.get('data_ora') or '')[:16].replace('T', ' '))}</td>"
        f"<td>{e((m.get('tipo_evento') or '').replace('_', ' '))}</td>"
        f"<td>{e(m.get('motivo') or '')}</td>"
        f"<td>{e(str(m.get('quantita')) if m.get('quantita') is not None else '')}</td>"
        f"<td>{e(m.get('operatore_nome') or '')}</td></tr>"
        for m in scheda.get("movimenti") or []
    ) or "<tr><td colspan='5'>Nessun movimento registrato.</td></tr>"

    html_doc = f"""<!doctype html><html><head><meta charset='utf-8'>
<title>Report lotto {e(str(l.get('numero_lotto') or ''))}</title>
<style>
@page {{ size: A4; margin: 14mm; }}
body {{ font-family: Georgia, serif; color: #2d2a24; font-size: 12px; }}
h1 {{ color: #3f5a4e; border-bottom: 3px solid #5b7a6b; padding-bottom: 6px; font-size: 20px; }}
h2 {{ color: #3f5a4e; font-size: 14px; margin: 16px 0 6px; }}
table {{ width: 100%; border-collapse: collapse; font-size: 11px; }}
td, th {{ border: 1px solid #e6e0d4; padding: 4px 8px; text-align: left; vertical-align: top; }}
th {{ background: #5b7a6b; color: #fff; }}
td.k {{ background: #faf7f0; font-weight: bold; width: 34%; }}
.top {{ display: flex; justify-content: space-between; color: #8a8478; font-size: 10px; margin-bottom: 4px; }}
@media print {{ .noprint {{ display: none; }} }}
</style></head><body>
<div class='top'><span>{e(az.get('ragione_sociale') or 'Ceraldi Group')}</span>
<span>Generato il {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')} UTC</span></div>
<h1>Report lotto — {e(str(l.get('prodotto') or ''))} · {e(str(l.get('numero_lotto') or ''))}</h1>
<table>{dati}</table>
<h2>Ingredienti usati</h2><ul>{ingredienti}</ul>
<h2>Provenienza (lotti fornitori scalati FIFO)</h2>
<table><tr><th>Ingrediente</th><th>Fornitore</th><th>Lotto fornitore</th><th>Fattura</th><th>Quantità</th></tr>{prov}</table>
<h2>Cronologia completa</h2>
<table><tr><th>Data e ora</th><th>Evento</th><th>Motivo</th><th>Quantità</th><th>Operatore</th></tr>{cron}</table>
<button class='noprint' onclick='window.print()' style='margin-top:14px;padding:8px 18px;background:#5b7a6b;color:#fff;border:none;border-radius:8px;font-weight:bold;cursor:pointer;'>Stampa</button>
</body></html>"""
    return HTMLResponse(content=html_doc)
