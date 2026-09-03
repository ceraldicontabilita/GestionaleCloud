"""Verifica della tranche CCNL applicata, dalla paga base scritta sulle buste.

La busta paga riporta paga base e contingenza come tariffa ORARIA (es.
"PAGA BASE 5,93890"), non l'importo mensile. Moltiplicando per il divisore
orario del CCNL (172 per il Turismo, verificato sulle buste Ceraldi: la
contingenza di tabella diviso quella oraria del cedolino da' 172 su 115/115
buste controllate) si ottiene la paga base mensile applicata, confrontabile
con la tabella in vigore.

Il confronto e' per livello, non per persona: uno scarto comune a piu' livelli
e' la firma di una tranche di rinnovo precedente, non di un errore. Uno scarto
che riguarda un solo livello, o una sola persona dentro un livello altrimenti
in linea, e' il caso da segnalare.
"""
from typing import Any, Dict, List, Optional

from app.hr.database import Collections
from app.hr.services.ccnl import CCNL, CCNLNonDisponibile, divisore_orario


def _num(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


async def verifica_tranche(db, ccnl_id: str = "turismo_pubblici_esercizi",
                           mesi_recenti: int = 12) -> Dict[str, Any]:
    """Confronta la paga base applicata (dalle buste) col tabellare, per livello.

    Usa solo le buste degli ultimi `mesi_recenti` competenze in archivio, per
    non mescolare tranche diverse nello stesso conto.
    """
    c = CCNL.get(ccnl_id)
    if not c or not c["tabelle_caricate"]:
        raise CCNLNonDisponibile(f"Tabelle non caricate per {ccnl_id!r}")

    # Solo i dipendenti attivi: la paga di chi e' cessato smette di essere
    # aggiornata quando finisce il rapporto, non prima. Mescolarli agli attivi
    # nella stessa media fa sembrare un livello "indietro sulla tranche" quando
    # in realta' e' solo pieno di ex-dipendenti fermi alla loro ultima busta.
    attivi = {d["id"] for d in await db[Collections.EMPLOYEES].find(
        {"stato": "attivo"}, {"_id": 0, "id": 1}).to_list(500)}

    cedolini = await db[Collections.PAYSLIPS].find(
        {"tipo_cedolino": {"$in": ["ordinario", None]}},
        {"_id": 0, "pdf_data": 0}).to_list(3000)
    cedolini = [x for x in cedolini if x.get("dipendente_id") in attivi]

    competenze = sorted({(int(x.get("anno") or 0), int(x.get("mese") or 0))
                         for x in cedolini if x.get("anno")}, reverse=True)
    recenti = set(competenze[:mesi_recenti])

    per_livello: Dict[str, List[Dict[str, Any]]] = {}
    for x in cedolini:
        chiave = (int(x.get("anno") or 0), int(x.get("mese") or 0))
        if chiave not in recenti:
            continue
        r = x.get("retribuzione") or {}
        pb_oraria = _num(r.get("paga_base_oraria"))
        pb_mensile = _num(r.get("paga_base_mensile"))
        livello = str(x.get("livello") or "")
        if livello not in c["livelli"]:
            continue
        if pb_mensile is None and pb_oraria is not None:
            div = divisore_orario(40, ccnl_id)
            pb_mensile = round(pb_oraria * div, 2)
        if pb_mensile is None:
            continue
        per_livello.setdefault(livello, []).append({
            "dipendente_nome": x.get("dipendente_nome"),
            "dipendente_id": x.get("dipendente_id"),
            "competenza": f"{chiave[0]}-{chiave[1]:02d}",
            "paga_base_applicata": pb_mensile,
        })

    righe = []
    for livello, voci in per_livello.items():
        tabellare = c["livelli"][livello][1]        # (contingenza, PAGA BASE, totale)
        valori = [v["paga_base_applicata"] for v in voci]
        media = round(sum(valori) / len(valori), 2)
        rapporto = round(media / tabellare * 100, 1) if tabellare else None
        righe.append({
            "livello": livello,
            "descrizione": c["descrizioni"].get(livello, ""),
            "buste": len(voci),
            "paga_base_applicata_media": media,
            "paga_base_tabellare": tabellare,
            "percentuale_sul_tabellare": rapporto,
            "dettaglio": voci,
        })
    righe.sort(key=lambda r: -r["buste"])

    # Tranche comune: la percentuale che ricorre su piu' livelli con piu' buste.
    da_percentuale: Dict[float, int] = {}
    for r in righe:
        if r["percentuale_sul_tabellare"] is not None and r["buste"] >= 3:
            p = round(r["percentuale_sul_tabellare"])
            da_percentuale[p] = da_percentuale.get(p, 0) + r["buste"]
    tranche_comune = max(da_percentuale, key=da_percentuale.get) if da_percentuale else None

    anomali = [r["livello"] for r in righe
              if r["percentuale_sul_tabellare"] is not None and r["buste"] >= 3
              and tranche_comune is not None
              and abs(round(r["percentuale_sul_tabellare"]) - tranche_comune) >= 2]

    return {
        "ccnl": ccnl_id,
        "competenze_analizzate": sorted(recenti),
        "tranche_comune_percentuale": tranche_comune,
        "livelli_fuori_linea": anomali,
        "per_livello": righe,
    }
