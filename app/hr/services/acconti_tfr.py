"""Riepilogo acconti e anticipi TFR per dipendente, per anno.

Le buste registrano acconto erogato/recuperato mese per mese (voci distinte,
sommabili cosi' come sono — vedi `busta_paga_multi_template._acconti_e_anticipazioni`).

L'anticipo TFR e' diverso: il campo "TFR a fondi / Anticipi" e' un PROGRESSIVO,
non un importo del mese. Su Capezzuto compare 3.100 per tre mesi di fila, poi
5.300 per i due successivi: non sono tre anticipi da 3.100 seguiti da due da
5.300, e' un unico anticipo di 3.100 seguito da uno ulteriore di 2.200 (la
differenza). Sommare il valore letto mese per mese lo conta 3-5 volte.

Qui l'evento si ricava dalla DIFFERENZA rispetto al mese precedente in
ordine cronologico: un salto verso l'alto e' un nuovo anticipo, uno verso il
basso e' un recupero/liquidazione. Il primo valore osservato nell'archivio
(nessun mese precedente con cui confrontare) resta segnalato ma marcato come
"pregresso", perche' potrebbe essersi gia' verificato prima dell'inizio dei
cedolini disponibili.
"""
from typing import Any, Dict, List, Optional

from app.hr.database import Collections

_SOGLIA = 1.0   # sotto questa differenza e' arrotondamento, non un evento


def _competenza_ordine(c: Dict[str, Any]):
    return (int(c.get("anno") or 0), int(c.get("mese") or 0))


async def riepilogo_dipendente(db, dipendente_id: str) -> Dict[str, Any]:
    """Acconti e anticipi TFR di un dipendente, per anno."""
    cedolini = await db[Collections.PAYSLIPS].find(
        {"dipendente_id": dipendente_id}, {"_id": 0, "pdf_data": 0}).to_list(2000)
    cedolini = [c for c in cedolini if c.get("anno") and c.get("mese")]
    cedolini.sort(key=_competenza_ordine)

    eventi: List[Dict[str, Any]] = []

    # --- acconto erogato/recuperato: gia' un importo del mese, si somma diretto ---
    for c in cedolini:
        a = c.get("acconti") or {}
        for chiave in ("acconto_erogato", "acconto_recuperato"):
            v = a.get(chiave)
            if v:
                eventi.append({"anno": c["anno"], "competenza": c.get("competenza"),
                               "tipo": chiave, "importo": round(v, 2)})

    # --- anticipo TFR: progressivo, l'evento e' la differenza col mese prima ---
    precedente: Optional[float] = None
    for c in cedolini:
        a = c.get("acconti") or {}
        attuale = a.get("tfr_anticipi_residuo")
        if attuale is None:
            continue
        if precedente is None:
            if attuale >= 50:
                eventi.append({"anno": c["anno"], "competenza": c.get("competenza"),
                               "tipo": "tfr_anticipo_erogato", "importo": round(attuale, 2),
                               "pregresso": True})
        else:
            delta = attuale - precedente
            if delta >= _SOGLIA:
                eventi.append({"anno": c["anno"], "competenza": c.get("competenza"),
                               "tipo": "tfr_anticipo_erogato", "importo": round(delta, 2)})
            elif delta <= -_SOGLIA:
                eventi.append({"anno": c["anno"], "competenza": c.get("competenza"),
                               "tipo": "tfr_anticipo_recuperato", "importo": round(-delta, 2)})
        precedente = attuale

    per_anno: Dict[int, Dict[str, Any]] = {}
    for e in eventi:
        r = per_anno.setdefault(e["anno"], {
            "anno": e["anno"], "acconto_erogato": 0.0, "acconto_recuperato": 0.0,
            "tfr_anticipo_erogato": 0.0, "tfr_anticipo_recuperato": 0.0, "eventi": [],
        })
        r[e["tipo"]] += e["importo"]
        r["eventi"].append(e)

    righe = sorted(per_anno.values(), key=lambda r: r["anno"])
    for r in righe:
        r["acconto_saldo_da_recuperare"] = round(r["acconto_erogato"] - r["acconto_recuperato"], 2)
        for k in ("acconto_erogato", "acconto_recuperato", "tfr_anticipo_erogato", "tfr_anticipo_recuperato"):
            r[k] = round(r[k], 2)
        r["eventi"].sort(key=lambda e: e.get("competenza") or "")

    return {
        "dipendente_id": dipendente_id,
        "totale_acconto_erogato": round(sum(r["acconto_erogato"] for r in righe), 2),
        "totale_acconto_recuperato": round(sum(r["acconto_recuperato"] for r in righe), 2),
        "totale_tfr_anticipato": round(sum(r["tfr_anticipo_erogato"] for r in righe), 2),
        "totale_tfr_recuperato": round(sum(r["tfr_anticipo_recuperato"] for r in righe), 2),
        "per_anno": righe,
    }


async def riepilogo_azienda(db, anno: int = None) -> List[Dict[str, Any]]:
    """Stessa cosa per tutti i dipendenti, un anno alla volta (o tutti)."""
    dipendenti = await db[Collections.EMPLOYEES].find({}, {"_id": 0}).to_list(500)
    out = []
    for d in dipendenti:
        r = await riepilogo_dipendente(db, d["id"])
        righe = [x for x in r["per_anno"] if anno is None or x["anno"] == anno]
        if not righe:
            continue
        out.append({
            "dipendente_id": d["id"], "nome_completo": d.get("nome_completo"),
            "per_anno": righe,
            "totale_tfr_anticipato": round(sum(x["tfr_anticipo_erogato"] for x in righe), 2),
            "totale_acconto_da_recuperare": round(sum(x["acconto_saldo_da_recuperare"] for x in righe), 2),
        })
    out.sort(key=lambda x: -x["totale_tfr_anticipato"])
    return out
