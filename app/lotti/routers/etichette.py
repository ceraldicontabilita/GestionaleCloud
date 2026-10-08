"""
Router Etichette — Genera etichette allergeni per banco (Reg. UE 1169/2011).
Scadenzario pagamenti fornitori.
"""

from datetime import datetime
from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse

from app.lotti.db import database as db

router = APIRouter(prefix="/etichette", tags=["Etichette"])


@router.get("/lotto/{lotto_id}", response_class=HTMLResponse)
async def etichetta_lotto(lotto_id: str):
    """
    Etichetta stampabile di un lotto prodotto, con la tracciabilità completa:
    prodotto, numero lotto, date, allergeni, E i lotti fornitori di ogni ingrediente
    (per i controlli ASL: da qui si risale a quale lotto fornitore è stato usato).
    """
    lotto = await db.lotti.find_one({"id": lotto_id}, {"_id": 0})
    if not lotto:
        return HTMLResponse("<h3 style='font-family:sans-serif;padding:40px'>Lotto non trovato</h3>", status_code=404)

    scalati = (lotto.get("lotti_fornitori") or {}).get("lotti_scalati") or []
    righe_ing = ""
    for s in scalati:
        ing = s.get("prodotto") or s.get("ingrediente") or "—"
        forn = s.get("fornitore") or "—"
        lottof = s.get("lotto_id_fornitore") or "—"
        righe_ing += f"""<tr>
            <td style="padding:6px 8px;border-bottom:1px solid #e6e0d4">{ing}</td>
            <td style="padding:6px 8px;border-bottom:1px solid #e6e0d4">{forn}</td>
            <td style="padding:6px 8px;border-bottom:1px solid #e6e0d4;font-family:monospace;font-weight:700;color:#3f5a4e">{lottof}</td>
        </tr>"""
    if not righe_ing:
        righe_ing = '<tr><td colspan="3" style="padding:10px;text-align:center;color:#9aa593">Nessun lotto fornitore tracciato</td></tr>'

    allergeni = lotto.get("allergeni_testo") or "—"
    prodotto = lotto.get("prodotto", "—")
    numero = lotto.get("numero_lotto", "—")
    d_prod = lotto.get("data_produzione", "—")
    d_scad = lotto.get("data_scadenza", "—")
    qta = lotto.get("quantita", "")
    um = lotto.get("unita_misura", "")
    conserv = lotto.get("conservazione_note") or ""

    html = f"""<!DOCTYPE html><html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Etichetta {numero}</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600&family=Plus+Jakarta+Sans:wght@400;600;700&display=swap');
  * {{ margin:0; box-sizing:border-box }}
  body {{ font-family:'Plus Jakarta Sans',sans-serif; background:#faf7f0; color:#2a3329; padding:16px }}
  .label {{ max-width:420px; margin:0 auto; background:#fffefb; border:2px solid #5b7a6b; border-radius:16px; overflow:hidden }}
  .head {{ background:#5b7a6b; color:#fff; padding:16px 18px }}
  .head h1 {{ font-family:'Fraunces',serif; font-size:22px; font-weight:600; line-height:1.2 }}
  .head .lot {{ font-family:monospace; font-size:14px; margin-top:6px; opacity:.95 }}
  .body {{ padding:16px 18px }}
  .grid {{ display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-bottom:14px }}
  .cell .l {{ font-size:10px; text-transform:uppercase; letter-spacing:.04em; color:#6b7669 }}
  .cell .v {{ font-size:15px; font-weight:700; color:#2a3329 }}
  .sec-title {{ font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:.05em; color:#5b7a6b; margin:14px 0 6px }}
  table {{ width:100%; border-collapse:collapse; font-size:12px }}
  th {{ text-align:left; padding:6px 8px; background:#e8efe9; color:#3f5a4e; font-size:10px; text-transform:uppercase }}
  .allerg {{ background:#f7ecdc; border:1px solid #ecd6b8; border-radius:8px; padding:10px; font-size:12px; color:#7d5526 }}
  .allerg b {{ text-transform:uppercase }}
  .foot {{ text-align:center; padding:10px; font-size:10px; color:#9aa593; border-top:1px solid #e6e0d4 }}
  @media print {{ body{{background:#fff;padding:0}} .noprint{{display:none}} }}
  .btn {{ display:block; width:100%; max-width:420px; margin:14px auto 0; padding:13px; background:#5b7a6b; color:#fff; border:none; border-radius:12px; font-family:inherit; font-size:15px; font-weight:700; cursor:pointer }}
</style></head>
<body>
  <div class="label">
    <div class="head">
      <h1>{prodotto}</h1>
      <div class="lot">Lotto: {numero}</div>
    </div>
    <div class="body">
      <div class="grid">
        <div class="cell"><div class="l">Produzione</div><div class="v">{d_prod}</div></div>
        <div class="cell"><div class="l">Scadenza</div><div class="v">{d_scad}</div></div>
        <div class="cell"><div class="l">Quantità</div><div class="v">{qta} {um}</div></div>
        <div class="cell"><div class="l">Conservazione</div><div class="v" style="font-size:12px">{conserv or '—'}</div></div>
      </div>

      <div class="sec-title">⚠ Allergeni</div>
      <div class="allerg">{allergeni}</div>

      <div class="sec-title">Tracciabilità ingredienti — lotti fornitori</div>
      <table>
        <thead><tr><th>Ingrediente</th><th>Fornitore</th><th>Lotto fornitore</th></tr></thead>
        <tbody>{righe_ing}</tbody>
      </table>
    </div>
    <div class="foot">Ceraldi Group — Tracciabilità HACCP · Reg. UE 1169/2011</div>
  </div>
  <button class="btn noprint" onclick="window.print()">🖨 Stampa etichetta</button>
</body></html>"""
    return HTMLResponse(content=html)


@router.get("/allergeni/{ricetta_id}", response_class=HTMLResponse)
async def etichetta_allergeni(ricetta_id: str):
    """Genera etichetta allergeni stampabile per un prodotto (Reg. UE 1169/2011)."""
    ricetta = await db.ricette.find_one({"id": ricetta_id}, {"_id": 0})
    if not ricetta:
        return HTMLResponse("<h1>Ricetta non trovata</h1>", status_code=404)

    allergeni = ricetta.get("allergeni", [])
    nome = ricetta.get("nome", "")

    ALLERGENI_ICONS = {
        "Glutine": "🌾",
        "Crostacei": "🦐",
        "Uova": "🥚",
        "Pesce": "🐟",
        "Arachidi": "🥜",
        "Soia": "🫘",
        "Latte": "🥛",
        "Frutta a guscio": "🌰",
        "Sedano": "🥬",
        "Senape": "🌿",
        "Sesamo": "🌱",
        "Anidride solforosa": "💨",
        "Lupini": "🌼",
        "Molluschi": "🦑",
    }

    allergeni_html = ""
    if allergeni:
        for a in allergeni:
            icon = ALLERGENI_ICONS.get(a, "⚠️")
            allergeni_html += f'<span class="allergen">{icon} <b>{a}</b></span>\n'
    else:
        allergeni_html = (
            '<p style="color: green; font-weight: bold;">✓ Non contiene allergeni dichiarati</p>'
        )

    ingredienti = ricetta.get("ingredienti_dettaglio", [])
    ing_list = ", ".join([i.get("nome", "") for i in ingredienti if i.get("nome")])

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>Etichetta — {nome}</title>
<style>
@media print {{ @page {{ margin: 5mm; size: 100mm 70mm; }} body {{ margin: 0; }} }}
body {{ font-family: Arial, sans-serif; padding: 8px; max-width: 100mm; }}
h1 {{ font-size: 16px; margin: 0 0 4px; text-transform: capitalize; border-bottom: 2px solid #f97316; padding-bottom: 4px; }}
.allergen {{ display: inline-block; background: #fef2f2; border: 1px solid #fca5a5; border-radius: 4px; padding: 2px 6px; margin: 2px; font-size: 11px; }}
.ingredients {{ font-size: 9px; color: #666; margin-top: 6px; line-height: 1.3; }}
.footer {{ font-size: 8px; color: #999; margin-top: 6px; border-top: 1px solid #eee; padding-top: 3px; }}
</style></head><body>
<h1>{nome}</h1>
<div style="margin: 6px 0;">{allergeni_html}</div>
<div class="ingredients"><b>Ingredienti:</b> {ing_list or "Vedi scheda prodotto"}</div>
<div class="footer">Reg. UE 1169/2011 — Ceraldi Group S.R.L. — {datetime.now().strftime("%d/%m/%Y")}</div>
<script>window.onload=()=>window.print();</script>
</body></html>"""
    return HTMLResponse(html)


@router.get("/allergeni-batch", response_class=HTMLResponse)
async def etichette_allergeni_batch(reparto: str = Query("tutti")):
    """Genera TUTTE le etichette allergeni per il reparto (stampa multipla)."""
    filtro = {}
    if reparto != "tutti":
        filtro["reparto"] = reparto

    ricette = await db.ricette.find(filtro, {"_id": 0}).to_list(200)

    ALLERGENI_ICONS = {
        "Glutine": "🌾",
        "Crostacei": "🦐",
        "Uova": "🥚",
        "Pesce": "🐟",
        "Arachidi": "🥜",
        "Soia": "🫘",
        "Latte": "🥛",
        "Frutta a guscio": "🌰",
        "Sedano": "🥬",
        "Senape": "🌿",
        "Sesamo": "🌱",
        "Anidride solforosa": "💨",
        "Lupini": "🌼",
        "Molluschi": "🦑",
    }

    cards = ""
    for r in sorted(ricette, key=lambda x: x.get("nome", "")):
        allergeni = r.get("allergeni", [])
        nome = r.get("nome", "")

        all_html = ""
        if allergeni:
            for a in allergeni:
                icon = ALLERGENI_ICONS.get(a, "⚠️")
                all_html += f'<span class="a">{icon} {a}</span> '
        else:
            all_html = '<span style="color:green">✓ Senza allergeni</span>'

        cards += f"""
        <div class="card">
            <h2>{nome}</h2>
            <div class="allergeni">{all_html}</div>
        </div>"""

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>Etichette Allergeni — {reparto}</title>
<style>
@media print {{ @page {{ margin: 5mm; }} }}
body {{ font-family: Arial, sans-serif; margin: 0; padding: 10px; }}
.card {{ border: 1.5px solid #e5e7eb; border-radius: 8px; padding: 8px 10px; margin-bottom: 6px; page-break-inside: avoid; }}
h2 {{ font-size: 14px; margin: 0 0 4px; text-transform: capitalize; }}
.a {{ display: inline-block; background: #fef2f2; border: 1px solid #fca5a5; border-radius: 3px; padding: 1px 5px; font-size: 10px; margin: 1px; }}
.allergeni {{ line-height: 1.6; }}
</style></head><body>
<h1 style="font-size:16px;border-bottom:2px solid #f97316;padding-bottom:4px;">
    Registro Allergeni — {reparto.title()} — {datetime.now().strftime("%d/%m/%Y")}
    <span style="float:right;font-size:11px;color:#999;">Reg. UE 1169/2011</span>
</h1>
{cards}
<script>window.onload=()=>window.print();</script>
</body></html>"""
    return HTMLResponse(html)
