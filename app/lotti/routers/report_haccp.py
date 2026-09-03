"""
Report HACCP mensile in HTML.
L'endpoint e usato dal bottone Report PDF: /api/report-haccp/mensile.
"""

from collections import defaultdict
from datetime import datetime
from html import escape
from pathlib import Path
import calendar

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse

from app.lotti.db import database as db
from app.lotti.azienda import get_azienda

ROOT_DIR = Path(__file__).parent.parent
router = APIRouter(prefix="/report-haccp", tags=["Report HACCP"])

MESI_IT = [
    "",
    "Gennaio",
    "Febbraio",
    "Marzo",
    "Aprile",
    "Maggio",
    "Giugno",
    "Luglio",
    "Agosto",
    "Settembre",
    "Ottobre",
    "Novembre",
    "Dicembre",
]


def h(value) -> str:
    return escape(str(value if value is not None else ""))


def fmt_data(value) -> str:
    if not value:
        return "-"
    text = str(value)
    try:
        if "T" in text:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).strftime("%d/%m/%Y")
        if "-" in text[:10]:
            dt = datetime.fromisoformat(text[:10])
            return dt.strftime("%d/%m/%Y")
        return text
    except Exception:
        return text


def parse_date(value):
    if not value:
        return None
    text = str(value)
    try:
        if "-" in text[:10]:
            return datetime.fromisoformat(text[:10])
        if "/" in text:
            return datetime.strptime(text[:10], "%d/%m/%Y")
    except Exception:
        return None
    return None


def to_float(value):
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", "."))
    except Exception:
        return None


def normalize_temp(value):
    if isinstance(value, dict):
        mattina = value.get("mattina")
        if mattina in (None, ""):
            mattina = value.get("temp", value.get("temperatura"))
        return {
            "mattina": mattina,
            "sera": value.get("sera", ""),
            "note": value.get("note", ""),
            "operatore": value.get("operatore", ""),
            # Giorno DICHIARATO non rilevato (scritto dal job di recupero
            # quando il server è rimasto giù): non è un buco muto, ha un
            # motivo scritto che finisce nel tooltip della stampa.
            "non_rilevato": bool(value.get("non_rilevato")),
            "motivo": value.get("motivo") or "",
            # soglie CONGELATE alla registrazione (audit 24/07/2026): la
            # conformità storica si valuta su queste, non sulle soglie correnti
            "soglie": value.get("soglie") if isinstance(value.get("soglie"), dict) else None,
        }
    return {
        "mattina": value, "sera": "", "note": "", "operatore": "",
        "soglie": None, "non_rilevato": False, "motivo": "",
    }


def limiti_record(item, default_min, default_max):
    """Soglie da usare per UN record: quelle salvate nel record se presenti,
    altrimenti quelle correnti dell'apparecchio."""
    soglie = item.get("soglie") if isinstance(item, dict) else None
    if isinstance(soglie, dict):
        t_min = soglie.get("min", default_min)
        t_max = soglie.get("max", default_max)
        if t_min is not None and t_max is not None:
            return float(t_min), float(t_max)
    return default_min, default_max


def in_range(value, min_ok, max_ok):
    number = to_float(value)
    if number is None:
        return None
    return min_ok <= number <= max_ok


async def load_temperature(collection, anno, mese, kind):
    records = await collection.find({"anno": anno}, {"_id": 0}).to_list(500)
    apps = []
    flat = []
    default_min, default_max = (0.0, 4.0) if kind == "positive" else (-22.0, -18.0)

    for rec in records:
        if kind == "positive":
            nome = (
                rec.get("frigorifero_nome") or f"Frigorifero N.{rec.get('frigorifero_numero', '?')}"
            )
        else:
            nome = (
                rec.get("congelatore_nome")
                or rec.get("frigorifero_nome")
                or f"Congelatore N.{rec.get('congelatore_numero', rec.get('frigorifero_numero', '?'))}"
            )

        temp_min = float(rec.get("temp_min", default_min) or default_min)
        temp_max = float(rec.get("temp_max", default_max) or default_max)
        giorni_raw = (rec.get("temperature") or {}).get(str(mese), {})
        giorni = {}

        for giorno, value in giorni_raw.items():
            item = normalize_temp(value)
            giorni[str(giorno)] = item
            rec_min, rec_max = limiti_record(item, temp_min, temp_max)
            for fascia in ("mattina", "sera"):
                val = item.get(fascia)
                ok = in_range(val, rec_min, rec_max)
                if ok is None:
                    continue
                flat.append(
                    {
                        "apparecchio": nome,
                        "giorno": str(giorno),
                        "fascia": fascia,
                        "valore": val,
                        "conforme": ok,
                    }
                )

        # AUDIT 24/07/2026: l'apparecchio compare SEMPRE nel registro, anche
        # con zero rilevazioni nel mese (prima la riga veniva SALTATA e il
        # buco spariva dalla stampa) — i giorni mancanti sono resi come
        # "N/D = Dato non disponibile" da table_temperature.
        apps.append({"nome": nome, "min_ok": temp_min, "max_ok": temp_max, "giorni": giorni})

    return apps, flat


async def load_sanificazioni(anno, mese):
    rows = []

    schede = await db.sanificazione_schede.find({"anno": anno, "mese": mese}, {"_id": 0}).to_list(
        500
    )
    for doc in schede:
        operatore = doc.get("operatore_responsabile") or doc.get("operatore") or "-"
        for area, giorni in (doc.get("registrazioni") or {}).items():
            if not isinstance(giorni, dict):
                continue
            for giorno, value in giorni.items():
                # "N/D" (giorno dichiarato non registrato dal recupero) NON è
                # una sanificazione eseguita: prima qualunque valore non vuoto
                # veniva contato come fatto.
                if value in ("X", "x", "1", 1, True):
                    rows.append(
                        {
                            "area": area,
                            "giorno": str(giorno),
                            "prodotto": doc.get("prodotto") or "Registrato in scheda sanificazione",
                            "operatore": operatore,
                            "conforme": True,
                        }
                    )

    apparecchi = await db.sanificazione_apparecchi.find({"anno": anno}, {"_id": 0}).to_list(500)
    for doc in apparecchi:
        for campo, prefisso in (
            ("registrazioni_frigoriferi", "Frigorifero"),
            ("registrazioni_congelatori", "Congelatore"),
        ):
            for idx, lista in enumerate(doc.get(campo) or [], start=1):
                for rec in lista or []:
                    rec_mese = rec.get("mese")
                    if rec_mese is None:
                        parsed = parse_date(rec.get("data"))
                        rec_mese = parsed.month if parsed else None
                    if rec_mese != mese or not rec.get("eseguita"):
                        continue
                    rows.append(
                        {
                            "area": rec.get("apparecchio") or f"{prefisso} {idx}",
                            "giorno": str(
                                rec.get("giorno")
                                or (
                                    parse_date(rec.get("data")).day
                                    if parse_date(rec.get("data"))
                                    else ""
                                )
                            ),
                            "prodotto": rec.get("prodotto") or rec.get("prodotto_usato") or "-",
                            "operatore": rec.get("operatore") or "-",
                            "conforme": bool(rec.get("eseguita", True)),
                        }
                    )

    return rows


def table_temperature(apps, anno, mese, default_min, default_max):
    n_giorni = calendar.monthrange(anno, mese)[1]
    if not apps:
        return '<div class="empty-msg">Nessuna temperatura registrata per questo mese.</div>'

    header = (
        '<th class="first">Apparecchio</th>'
        + "".join(f"<th>{d}</th>" for d in range(1, n_giorni + 1))
        + "<th>%</th>"
    )
    body = ""
    for app in apps:
        min_ok = app.get("min_ok", default_min)
        max_ok = app.get("max_ok", default_max)
        ok_count = 0
        total = 0
        cells = f'<td class="first"><b>{h(app["nome"])}</b><br><small>{min_ok:g} / {max_ok:g} °C</small></td>'

        for day in range(1, n_giorni + 1):
            item = app["giorni"].get(str(day))
            if not item:
                # Mai celle vuote: il giorno senza rilevazione è dichiarato
                cells += '<td class="empty" title="Dato non disponibile">N/D</td>'
                continue
            if item.get("non_rilevato"):
                # Giorno marcato a database dal recupero: il motivo è scritto,
                # non si finge che il dato non sia mai esistito.
                motivo = h(item.get("motivo") or "Nessuna rilevazione registrata")
                cells += f'<td class="empty" title="{motivo}">N/D</td>'
                continue

            values = []
            css = "ok"
            rec_min, rec_max = limiti_record(item, min_ok, max_ok)
            for key in ("mattina", "sera"):
                value = item.get(key)
                ok = in_range(value, rec_min, rec_max)
                if ok is None:
                    continue
                total += 1
                ok_count += 1 if ok else 0
                css = "ko" if not ok else css
                values.append(f"{to_float(value):.1f}")

            if values:
                cells += f'<td class="{css}">{"<br>".join(values)}</td>'
            else:
                cells += '<td class="empty" title="Dato non disponibile">N/D</td>'

        pct = round((ok_count / total) * 100) if total else 0
        cells += f'<td class="pct">{pct}%<br><small>{ok_count}/{total}</small></td>'
        body += f"<tr>{cells}</tr>"

    legenda = '<div class="note" style="margin-top:4px">N/D = Dato non disponibile (nessuna rilevazione registrata per quel giorno).</div>'
    return f'<table class="calendar"><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table>{legenda}'


def table_sanificazioni(rows, anno, mese):
    n_giorni = calendar.monthrange(anno, mese)[1]
    if not rows:
        return '<div class="empty-msg">Nessuna sanificazione registrata per questo mese.</div>'

    grouped = defaultdict(dict)
    details = []
    for row in rows:
        area = str(row.get("area") or "-")
        day = str(row.get("giorno") or "")
        if day:
            grouped[area][day] = row
        details.append(row)

    header = (
        '<th class="first">Area / Apparecchio</th>'
        + "".join(f"<th>{d}</th>" for d in range(1, n_giorni + 1))
        + "<th>Tot.</th>"
    )
    body = ""
    for area in sorted(grouped):
        done = 0
        cells = f'<td class="first"><b>{h(area)}</b></td>'
        for day in range(1, n_giorni + 1):
            rec = grouped[area].get(str(day))
            if rec:
                done += 1
                cells += (
                    '<td class="ok">✓</td>'
                    if rec.get("conforme", True)
                    else '<td class="ko">✗</td>'
                )
            else:
                cells += '<td class="empty">.</td>'
        cells += f'<td class="pct">{done}</td>'
        body += f"<tr>{cells}</tr>"

    detail_rows = "".join(
        f"<tr><td>{h(r.get('giorno'))}</td><td>{h(r.get('area'))}</td><td>{h(r.get('prodotto'))}</td><td>{h(r.get('operatore'))}</td></tr>"
        for r in sorted(
            details, key=lambda x: (int(x.get("giorno") or 0), str(x.get("area") or ""))
        )
    )
    detail_table = f"<table><thead><tr><th>Giorno</th><th>Area</th><th>Prodotto</th><th>Operatore</th></tr></thead><tbody>{detail_rows}</tbody></table>"
    return f'<table class="calendar"><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table><h3>Dettaglio sanificazioni</h3>{detail_table}'


def table_anomalie(rows):
    if not rows:
        return '<div class="empty-msg">Nessuna anomalia registrata.</div>'
    body = ""
    for row in rows:
        body += (
            f"<tr><td>{h(fmt_data(row.get('data_rilevazione') or row.get('data')))}</td>"
            f"<td>{h(row.get('attrezzatura') or row.get('tipo') or '-')}</td>"
            f"<td>{h((row.get('descrizione') or '-')[:140])}</td>"
            f"<td>{h(row.get('stato') or '-')}</td>"
            f"<td>{h((row.get('azione_correttiva') or '-')[:120])}</td></tr>"
        )
    return f"<table><thead><tr><th>Data</th><th>Attrezzatura</th><th>Descrizione</th><th>Stato</th><th>Azione correttiva</th></tr></thead><tbody>{body}</tbody></table>"


def table_lotti(rows):
    if not rows:
        return '<div class="empty-msg">Nessuna produzione registrata.</div>'
    body = ""
    for row in sorted(rows, key=lambda x: x.get("data_produzione") or x.get("data") or ""):
        body += (
            f"<tr><td><b>{h(row.get('numero_lotto') or str(row.get('id', ''))[:8])}</b></td>"
            f"<td>{h(row.get('prodotto') or row.get('ricetta_nome') or row.get('nome') or '-')}</td>"
            f"<td>{h(row.get('quantita') or row.get('pezzi_prodotti') or row.get('pezzi') or '-')}</td>"
            f"<td>{h(fmt_data(row.get('data_produzione') or row.get('data')))}</td>"
            f"<td>{h(fmt_data(row.get('data_scadenza') or row.get('scadenza')))}</td></tr>"
        )
    return f"<table><thead><tr><th>Lotto</th><th>Prodotto</th><th>Pezzi</th><th>Produzione</th><th>Scadenza</th></tr></thead><tbody>{body}</tbody></table>"


@router.get("/mensile", response_class=HTMLResponse)
async def report_haccp_mensile(
    anno: int = Query(..., description="Anno del report"),
    mese: int = Query(..., ge=1, le=12, description="Mese del report (1-12)"),
):
    nome_mese = MESI_IT[mese]

    temp_pos_apps, temp_pos_flat = await load_temperature(
        db.temperature_positive, anno, mese, "positive"
    )
    temp_neg_apps, temp_neg_flat = await load_temperature(
        db.temperature_negative, anno, mese, "negative"
    )
    san_mese = await load_sanificazioni(anno, mese)

    # Limiti alzati (audit 24/07/2026): 1000/2000 troncavano il registro appena
    # l'archivio cresceva — il report mensile perdeva righe in silenzio.
    anomalie_records = await db.anomalie.find({}, {"_id": 0}).to_list(20000)
    anomalie_mese = []
    for row in anomalie_records:
        dt = parse_date(
            row.get("data_segnalazione") or row.get("data_rilevazione") or row.get("data")
        )
        if dt and dt.year == anno and dt.month == mese:
            anomalie_mese.append(row)

    lotti_records = await db.lotti.find({}, {"_id": 0}).sort("created_at", -1).to_list(50000)
    lotti_mese = []
    for row in lotti_records:
        dt = parse_date(row.get("data_produzione") or row.get("data"))
        if dt and dt.year == anno and dt.month == mese:
            lotti_mese.append(row)

    pos_ok = sum(1 for r in temp_pos_flat if r["conforme"])
    neg_ok = sum(1 for r in temp_neg_flat if r["conforme"])
    pos_pct = round(pos_ok / len(temp_pos_flat) * 100) if temp_pos_flat else 0
    neg_pct = round(neg_ok / len(temp_neg_flat) * 100) if temp_neg_flat else 0
    san_ok = sum(1 for r in san_mese if r.get("conforme", True))
    anomalie_chiuse = sum(
        1 for a in anomalie_mese if str(a.get("stato", "")).lower() in ("chiusa", "risolta")
    )
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M")

    def stat(value, label, extra=""):
        return f'<div class="stat {extra}"><b>{h(value)}</b><span>{h(label)}</span></div>'

    css = """
    <style>
      *{box-sizing:border-box} body{font-family:Arial,sans-serif;color:#172033;margin:0;padding:18px;font-size:11px;background:white}
      .header{text-align:center;border-bottom:3px solid #273b7a;padding-bottom:12px;margin-bottom:12px}.header h1{margin:0;color:#273b7a;font-size:21px}.muted{color:#64748b}.meta{display:flex;justify-content:space-between;margin:10px 0 14px;color:#64748b;font-size:10px}
      .stats{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:14px 0 18px}.stat{border:1px solid #dbe4f0;background:#f8fafc;border-radius:7px;padding:10px;text-align:center}.stat b{display:block;font-size:21px;color:#273b7a}.stat span{display:block;font-size:9px;color:#64748b}.okstat{background:#ecfdf5;border-color:#a7f3d0}.warnstat{background:#fff7ed;border-color:#fed7aa}
      .section{margin:0 0 20px;page-break-inside:avoid}.title{background:#273b7a;color:#fff;padding:7px 10px;border-radius:6px 6px 0 0;font-size:12px;font-weight:bold;display:flex;justify-content:space-between}.green{background:#166534}.red{background:#b91c1c}.violet{background:#6d28d9}.orange{background:#c2410c}
      .note{background:#f8fafc;border-left:4px solid #94a3b8;padding:6px 9px;color:#475569;font-size:10px} table{width:100%;border-collapse:collapse} th{background:#eaf1fb;color:#273b7a;text-align:left;font-size:9px;padding:5px;border:1px solid #d7e0ec} td{font-size:9px;padding:5px;border:1px solid #e2e8f0;vertical-align:middle} tr:nth-child(even) td{background:#f8fafc}
      .calendar{table-layout:fixed}.calendar th,.calendar td{text-align:center;padding:3px 1px}.calendar .first{width:135px;text-align:left;padding:5px}.calendar small{font-size:7px;color:#64748b}.ok{background:#bbf7d0!important;color:#166534;font-weight:bold}.ko{background:#fecaca!important;color:#991b1b;font-weight:bold}.empty{background:#f8fafc!important;color:#cbd5e1}.pct{font-weight:bold;color:#273b7a}.empty-msg{border:1px solid #e2e8f0;background:#f8fafc;padding:12px;color:#64748b;font-style:italic} h3{margin:10px 0 5px;font-size:11px;color:#273b7a}.firma{display:flex;justify-content:space-between;margin-top:35px}.firma div{border-top:1px solid #94a3b8;width:220px;text-align:center;padding-top:5px;color:#64748b}.print{position:fixed;right:20px;bottom:20px;background:#273b7a;color:white;border:0;border-radius:8px;padding:10px 16px;font-weight:bold;cursor:pointer}
      @media print{.print{display:none}body{padding:8px}@page{size:A4 landscape;margin:10mm}}
    </style>
    """

    az = await get_azienda()
    html = f"""<!doctype html>
<html lang="it"><head><meta charset="utf-8"><title>Report HACCP - {h(nome_mese)} {anno}</title>{css}</head>
<body>
<button class="print" onclick="window.print()">Stampa / Salva PDF</button>
<div class="header"><h1>REGISTRO HACCP MENSILE</h1><div class="muted">{h(az['ragione_sociale'])} - {h(az['indirizzo'])}</div><h2>{h(nome_mese)} {anno}</h2></div>
<div class="meta"><span>Generato il: {h(now_str)}</span><span>Documento interno HACCP</span></div>
<div class="stats">
  {stat(len(temp_pos_flat) + len(temp_neg_flat), "Rilevazioni temperature")}
  {stat(f"{pos_pct}%", "Conformita frigoriferi", "okstat" if pos_pct >= 95 else "warnstat")}
  {stat(f"{neg_pct}%", "Conformita congelatori", "okstat" if neg_pct >= 95 else "warnstat")}
  {stat(len(san_mese), "Sanificazioni")}
  {stat(len(anomalie_mese), "Anomalie", "warnstat" if anomalie_mese else "okstat")}
  {stat(anomalie_chiuse, "Anomalie chiuse", "okstat")}
  {stat(len(lotti_mese), "Lotti prodotti")}
  {stat(f"{san_ok}/{len(san_mese)}", "Sanificazioni conformi", "okstat" if san_ok == len(san_mese) else "warnstat")}
</div>
<div class="section"><div class="title green"><span>Temperature positive - frigoriferi</span><span>{len(temp_pos_flat)} rilevazioni</span></div><div class="note">Dati letti da temperature_positive, campo temperature[mese][giorno].temp oppure mattina/sera.</div>{table_temperature(temp_pos_apps, anno, mese, 0, 4)}</div>
<div class="section"><div class="title red"><span>Temperature negative - congelatori</span><span>{len(temp_neg_flat)} rilevazioni</span></div><div class="note">Dati letti da temperature_negative, campo temperature[mese][giorno].temp oppure mattina/sera.</div>{table_temperature(temp_neg_apps, anno, mese, -22, -18)}</div>
<div class="section"><div class="title violet"><span>Piano di sanificazione</span><span>{len(san_mese)} registrazioni</span></div><div class="note">Dati letti da sanificazione_schede e sanificazione_apparecchi.</div>{table_sanificazioni(san_mese, anno, mese)}</div>
<div class="section"><div class="title orange"><span>Anomalie e non conformita</span><span>{len(anomalie_mese)} registrate</span></div>{table_anomalie(anomalie_mese)}</div>
<div class="section"><div class="title"><span>Lotti di produzione</span><span>{len(lotti_mese)} lotti</span></div>{table_lotti(lotti_mese)}</div>
<div class="firma"><div>Responsabile HACCP</div><div>Titolare / Direttore</div></div>
</body></html>"""
    return HTMLResponse(content=html)


@router.get("/ingredienti-non-mappati")
async def ingredienti_non_mappati():
    # (rimosso il sys.path.insert(ROOT_DIR) storico: il modulo vive nel
    # pacchetto app.lotti e l'import assoluto basta)
    from app.lotti.routers.food_cost import trova_prodotto_dizionario

    prodotti = await db.dizionario_prodotti.find({}, {"_id": 0}).to_list(10000)
    dizionario = {p["nome_normalizzato"].lower(): p for p in prodotti}
    ricette = await db.ricette.find(
        {"ingredienti_dettaglio": {"$exists": True, "$ne": []}},
        {"_id": 0, "nome": 1, "id": 1, "ingredienti_dettaglio": 1},
    ).to_list(200)

    mancanti_map = {}
    totale_ingredienti = 0
    trovati = 0

    for ricetta in ricette:
        for ing in ricetta.get("ingredienti_dettaglio", []):
            nome = ing.get("nome", "").strip()
            if not nome or len(nome) <= 1 or "#ref" in nome.lower() or nome.startswith("="):
                continue
            totale_ingredienti += 1
            prod = trova_prodotto_dizionario(nome, dizionario)
            if prod:
                trovati += 1
            else:
                if nome not in mancanti_map:
                    mancanti_map[nome] = {"ingrediente": nome, "ricette": [], "count": 0}
                if ricetta["nome"] not in mancanti_map[nome]["ricette"]:
                    mancanti_map[nome]["ricette"].append(ricetta["nome"])
                mancanti_map[nome]["count"] += 1

    mancanti_list = sorted(mancanti_map.values(), key=lambda x: -x["count"])
    return {
        "totale_ingredienti": totale_ingredienti,
        "trovati": trovati,
        "non_trovati": len(mancanti_list),
        "percentuale_copertura": (
            round(trovati / totale_ingredienti * 100, 1) if totale_ingredienti else 0
        ),
        "ingredienti_mancanti": mancanti_list,
    }
