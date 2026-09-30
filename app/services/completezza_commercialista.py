"""Il pacchetto del commercialista e' completo? Tre domande prima dello ZIP.

1. Ogni giorno d'apertura del periodo ha la sua chiusura RT (o e' stato chiuso
   dall'RT col giorno dopo, o e' una chiusura dell'attivita' dichiarata).
2. Ogni fattura attiva del periodo ha il suo originale (Drive o XML salvato).
3. L'estratto conto BPM copre il periodo dall'inizio alla fine.

Non blocca niente: il pacchetto si scarica comunque, ma dice cosa manca invece
di lasciarlo scoprire al commercialista. Un giorno di oggi o di ieri non e'
ancora dovuto (l'XML RT arriva la sera dopo).
"""
from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

GIORNI_ATTESA = 2
MARGINE_ESTRATTO = 4  # weekend e festivi: la banca non registra tutti i giorni


def _giorno(valore: Any) -> str:
    if isinstance(valore, datetime):
        return valore.strftime("%Y-%m-%d")
    return str(valore or "")[:10]


def periodo(anno: int, mese: int, oggi: date) -> Tuple[str, str]:
    """Primo e ultimo giorno dovuto del periodo (mese 0 = anno intero)."""
    if mese:
        inizio = date(anno, mese, 1)
        fine = date(anno, mese, calendar.monthrange(anno, mese)[1])
    else:
        inizio, fine = date(anno, 1, 1), date(anno, 12, 31)
    fine = min(fine, oggi - timedelta(days=GIORNI_ATTESA))
    return inizio.isoformat(), fine.isoformat()


def _giorni(da: str, a: str) -> List[str]:
    giorno, fine = date.fromisoformat(da), date.fromisoformat(a)
    out = []
    while giorno <= fine:
        out.append(giorno.isoformat())
        giorno += timedelta(days=1)
    return out


async def chiusure_rt_mancanti(db, da: str, a: str) -> List[str]:
    from app.routers.pos_corrispettivi_check import (
        _aggrega_corrispettivi_per_giorno, _carica_pos_per_circuito, _giornate_senza_xml,
    )
    from app.services.chiusure_attivita import giorni_chiusi

    if da > a:
        return []
    corrispettivi = await db["corrispettivi"].find(
        {"data": {"$gte": da, "$lte": a + "~"}, "entity_status": {"$ne": "deleted"},
         "status": {"$nin": ["deleted", "archived", "archiviata"]}},
        {"_id": 0, "data": 1, "pagato_elettronico": 1, "pagato_pos": 1, "stato": 1,
         "totale_xml": 1, "totale": 1, "totale_manuale": 1, "source": 1},
    ).to_list(None)
    corr_by_date = _aggrega_corrispettivi_per_giorno(corrispettivi)
    pos = await _carica_pos_per_circuito(db)
    pos_giorno = {g: round(sum(v.values()), 2) for g, v in pos.items() if da <= g <= a}
    giorni = _giorni(da, a)
    chiusa_con, _ = _giornate_senza_xml(giorni, corr_by_date, pos_giorno)
    chiusi = await giorni_chiusi(db, da, a)
    return [g for g in giorni if g not in corr_by_date and g not in chiusa_con and g not in chiusi]


async def fatture_senza_originale(db, da: str, a: str) -> Tuple[int, List[Dict[str, Any]]]:
    from app.services.fattura_attiva import FILTRO_FATTURA_ATTIVA

    fatture = await db["invoices"].find(
        {"$and": [FILTRO_FATTURA_ATTIVA, {"invoice_date": {"$gte": da, "$lte": a + "~"}}]},
        {"_id": 0, "id": 1, "invoice_number": 1, "supplier_name": 1, "invoice_date": 1,
         "drive_file_id": 1, "_payload_stato": 1},
    ).to_list(None)
    mancanti = []
    for f in fatture:
        if f.get("drive_file_id"):
            continue
        stato = f.get("_payload_stato") if isinstance(f.get("_payload_stato"), dict) else {}
        if stato.get("xml_raw") == "pieno" or stato.get("document_original_ref") == "pieno":
            continue
        # Il marcatore non c'e' (o dice vuoto): si guarda il payload, per id.
        completa = await db["invoices"].find_one(
            {"id": f.get("id")}, {"_id": 0, "xml_raw": 1, "document_original_ref": 1})
        if completa and (completa.get("xml_raw") or completa.get("document_original_ref")):
            continue
        mancanti.append({"id": f.get("id"), "numero": f.get("invoice_number"),
                         "fornitore": f.get("supplier_name"),
                         "data": _giorno(f.get("invoice_date"))})
    mancanti.sort(key=lambda r: (r["data"], str(r["numero"])))
    return len(fatture), mancanti


async def copertura_estratto_bpm(db, da: str, a: str) -> Dict[str, Any]:
    movimenti = await db["estratto_conto_movimenti"].find(
        {"data": {"$gte": da, "$lte": a + "~"}}, {"_id": 0, "data": 1}).to_list(None)
    date_viste = sorted(g for g in (_giorno(m.get("data")) for m in movimenti) if g)
    if not date_viste:
        return {"movimenti": 0, "primo": None, "ultimo": None, "completo": da > a}
    primo, ultimo = date_viste[0], date_viste[-1]
    margine = timedelta(days=MARGINE_ESTRATTO)
    completo = (date.fromisoformat(primo) - margine <= date.fromisoformat(da)
                and date.fromisoformat(ultimo) + margine >= date.fromisoformat(a))
    return {"movimenti": len(date_viste), "primo": primo, "ultimo": ultimo, "completo": completo}


async def completezza(db, anno: int, mese: int, *, oggi: Optional[date] = None,
                      dal: Optional[str] = None, al: Optional[str] = None) -> Dict[str, Any]:
    """Completezza del periodo: mese, anno intero (mese=0) o l'intervallo ``dal``/``al`` ISO."""
    riferimento = oggi or datetime.now(timezone.utc).date()
    if dal and al:
        da, a = dal, min(al, (riferimento - timedelta(days=GIORNI_ATTESA)).isoformat())
    else:
        da, a = periodo(anno, mese, riferimento)
    rt = await chiusure_rt_mancanti(db, da, a)
    totale_fatture, senza_originale = await fatture_senza_originale(db, da, a)
    estratto = await copertura_estratto_bpm(db, da, a)
    return {
        "anno": anno, "mese": mese, "dal": da, "al": a,
        "rt": {"mancanti": rt, "completo": not rt},
        "fatture": {"totale": totale_fatture, "senza_originale": senza_originale,
                    "completo": not senza_originale},
        "estratto_bpm": estratto,
        "completo": not rt and not senza_originale and estratto["completo"],
    }


def testo_leggimi(esito: Dict[str, Any]) -> str:
    """Il riassunto che entra nello ZIP, in italiano e senza gergo."""
    def it(g: Optional[str]) -> str:
        return f"{g[8:10]}/{g[5:7]}/{g[:4]}" if g else "-"

    righe = [f"Completezza del pacchetto dal {it(esito['dal'])} al {it(esito['al'])}", ""]
    rt = esito["rt"]["mancanti"]
    righe.append("Chiusure RT: complete." if not rt else
                 f"Chiusure RT mancanti ({len(rt)}): " + ", ".join(it(g) for g in rt))
    fatture = esito["fatture"]
    if fatture["completo"]:
        righe.append(f"Fatture: {fatture['totale']} con l'originale.")
    else:
        righe.append(f"Fatture senza originale ({len(fatture['senza_originale'])} su {fatture['totale']}):")
        righe += [f"  - {f['numero']} {f['fornitore']} del {it(f['data'])}"
                  for f in fatture["senza_originale"]]
    estratto = esito["estratto_bpm"]
    if estratto["completo"]:
        righe.append("Estratto conto BPM: copre il periodo.")
    elif not estratto["movimenti"]:
        righe.append("Estratto conto BPM: nessun movimento nel periodo, estratto da caricare.")
    else:
        righe.append(f"Estratto conto BPM: solo dal {it(estratto['primo'])} al {it(estratto['ultimo'])}.")
    righe += ["", "PACCHETTO COMPLETO" if esito["completo"] else "PACCHETTO INCOMPLETO: vedi sopra."]
    return "\n".join(righe) + "\n"
