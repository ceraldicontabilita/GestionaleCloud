"""Profilo retributivo del dipendente: cedolini + bonifici + CCNL.

Mette insieme le tre fonti che finora vivevano separate:

  cedolini  -> livello, lordo, netto dovuto   (letti dai PDF col parser)
  bonifici  -> quanto e' stato pagato davvero (dall'estratto conto)
  ccnl.py   -> quanto spetterebbe a quel livello

Serve a due cose: precompilare il contratto senza digitare importi a mano, e
accorgersi degli scostamenti — un livello pagato sotto il minimo tabellare, o
un bonifico che non torna col netto della busta.
"""
from typing import Any, Dict, List, Optional

from app.hr.database import Collections
from app.hr.services.ccnl import (
    CCNLNonDisponibile, retribuzione_per_livello, suggerisci_livello,
)


def _num(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(str(v).replace("€", "").replace(",", ".").strip())
    except (TypeError, ValueError):
        return None


def _media(valori: List[float]) -> Optional[float]:
    v = [x for x in valori if x is not None]
    return round(sum(v) / len(v), 2) if v else None


async def profilo(db, dipendente: Dict[str, Any], ccnl_id: Optional[str] = None,
                  ultimi_mesi: int = 12) -> Dict[str, Any]:
    """Fotografia retributiva di un dipendente, dalle sue ultime buste e dai suoi bonifici."""
    dip_id = dipendente.get("id")
    cf = (dipendente.get("codice_fiscale") or "").strip()

    ors: List[Dict[str, Any]] = [{"dipendente_id": dip_id}]
    if cf:
        ors += [{"codice_fiscale": cf}, {"codice_fiscale": cf.upper()}]

    cedolini = await db[Collections.PAYSLIPS].find(
        {"$or": ors}, {"_id": 0, "pdf_data": 0}).to_list(2000)
    # Solo le buste ordinarie con importi leggibili: le pagine presenze e le
    # mensilita' aggiuntive falserebbero le medie.
    utili = [c for c in cedolini
             if _num(c.get("netto")) is not None
             and (c.get("tipo_cedolino") or "ordinario") == "ordinario"]
    utili.sort(key=lambda c: (int(c.get("anno") or 0), int(c.get("mese") or 0)), reverse=True)
    recenti = utili[:ultimi_mesi]

    ultimo = recenti[0] if recenti else None
    livello = str(ultimo.get("livello")) if ultimo and ultimo.get("livello") else None
    if not livello:
        for c in recenti:
            if c.get("livello"):
                livello = str(c["livello"])
                break

    lordo_medio = _media([_num(c.get("lordo")) for c in recenti])
    netto_medio = _media([_num(c.get("netto")) for c in recenti])

    bonifici = await db["bonifici"].find(
        {"dipendente_id": dip_id, "categoria": "DIPENDENTE"}, {"_id": 0}).to_list(1000)
    bonifici.sort(key=lambda b: str(b.get("data") or ""), reverse=True)
    pagato_medio = _media([_num(b.get("importo")) for b in bonifici[:ultimi_mesi]])

    abbinati = [b for b in bonifici if b.get("cedolino_id")]
    scarti = [_num(b.get("scarto_vs_netto")) for b in abbinati]
    scarti = [s for s in scarti if s is not None]

    out: Dict[str, Any] = {
        "dipendente_id": dip_id,
        "nome_completo": dipendente.get("nome_completo"),
        "codice_fiscale": cf or None,
        "livello_rilevato": livello,
        "cedolini_totali": len(cedolini),
        "cedolini_con_importi": len(utili),
        "ultima_busta": (f"{ultimo.get('anno')}-{int(ultimo.get('mese') or 0):02d}"
                         if ultimo else None),
        "lordo_medio": lordo_medio,
        "netto_medio": netto_medio,
        "bonifici_totali": len(bonifici),
        "bonifici_abbinati": len(abbinati),
        "pagato_medio": pagato_medio,
        "scarto_medio_vs_netto": _media([abs(s) for s in scarti]),
        "bonifici_esatti": sum(1 for s in scarti if abs(s) < 0.01),
        "avvisi": [],
    }

    # --- confronto col CCNL -------------------------------------------------
    ore_note = _num(dipendente.get("ore_settimanali")) is not None
    ore = _num(dipendente.get("ore_settimanali")) or 40
    if livello:
        try:
            r = retribuzione_per_livello(livello, ccnl_id, ore)
            out["ccnl"] = r
            atteso = r["mensile_lordo"]          # gia' riproporzionato sulle ore
            # Il confronto regge solo se le buste sono confrontabili con la
            # tabella: i minimi caricati sono dell'ultima tranche, e la media di
            # pochi cedolini o di mesi parziali (assunzione o cessazione a meta'
            # mese) sta sotto il mensile pieno senza che nessuno sia sottopagato.
            anno_ultima = int(ultimo.get("anno") or 0) if ultimo else 0
            attendibile = len(recenti) >= 6 and anno_ultima >= 2025
            out["confronto_attendibile"] = attendibile
            if not attendibile and lordo_medio is not None:
                out["avvisi"].append({
                    "tipo": "confronto_non_attendibile",
                    "messaggio": (f"Solo {len(recenti)} buste utili, l'ultima del "
                                  f"{anno_ultima or '?'}: la media comprende mesi parziali "
                                  "e i minimi caricati sono dell'ultima tranche. "
                                  "Il confronto col tabellare non fa testo."),
                })
            if attendibile and ore_note and lordo_medio is not None and atteso:
                # Le ore contrattuali le sappiamo (arrivano dal Libro Unico):
                # il minimo e' calcolato su quelle, quindi lo scarto e' reale e
                # non c'e' piu' nulla da attribuire a un part-time ignoto.
                out["percentuale_sul_minimo"] = round(lordo_medio / atteso * 100, 1)
                if lordo_medio < atteso - 1:
                    out["avvisi"].append({
                        "tipo": "sotto_tabellare",
                        "messaggio": (f"Lordo medio {lordo_medio:.2f} € contro un minimo di "
                                      f"{atteso:.2f} € per il livello {r['livello']} a "
                                      f"{ore:g} ore settimanali: mancano "
                                      f"{atteso - lordo_medio:.2f} €."),
                    })
            elif lordo_medio is not None and atteso and lordo_medio < atteso - 1:
                # Un lordo sotto il tabellare quasi sempre vuol dire part-time, non
                # sottopaga: senza le ore contrattuali non possiamo distinguerli, e
                # gridare "sotto il minimo" su ogni part-time renderebbe l'avviso
                # inutile. Si segnala la percentuale e si alza la voce solo quando
                # il divario e' piccolo, cioe' incompatibile con un part-time vero.
                pieno = atteso
                perc = round(lordo_medio / pieno * 100, 1)
                out["percentuale_su_tempo_pieno"] = perc
                if perc >= 90:
                    out["avvisi"].append({
                        "tipo": "sotto_tabellare",
                        "messaggio": (f"Lordo medio {lordo_medio:.2f} € contro {pieno:.2f} € "
                                      f"del livello {r['livello']} a tempo pieno: mancano "
                                      f"{pieno - lordo_medio:.2f} € ({perc}%). Troppo vicino "
                                      "al pieno per essere part-time: da verificare."),
                    })
                else:
                    out["avvisi"].append({
                        "tipo": "verosimile_part_time",
                        "messaggio": (f"Lordo medio {lordo_medio:.2f} €, pari al {perc}% del "
                                      f"livello {r['livello']} a tempo pieno ({pieno:.2f} €). "
                                      "Coerente con un part-time: indicare le ore "
                                      "settimanali in anagrafica per il confronto esatto."),
                    })
        except CCNLNonDisponibile as e:
            out["avvisi"].append({"tipo": "ccnl_non_disponibile", "messaggio": str(e)})
    elif lordo_medio is not None:
        # Nessun livello sulle buste: lo si deduce dal lordo effettivo.
        try:
            out["livello_suggerito"] = suggerisci_livello(lordo_medio, ccnl_id, ore)
            out["avvisi"].append({
                "tipo": "livello_dedotto",
                "messaggio": ("Nessun livello leggibile sulle buste: suggerito "
                              f"{out['livello_suggerito']['livello_suggerito']}° dal lordo medio."),
            })
        except CCNLNonDisponibile as e:
            out["avvisi"].append({"tipo": "ccnl_non_disponibile", "messaggio": str(e)})

    if netto_medio is not None and pagato_medio is not None:
        delta = round(pagato_medio - netto_medio, 2)
        out["scarto_pagato_vs_dovuto"] = delta
        if abs(delta) > max(20.0, netto_medio * 0.05):
            out["avvisi"].append({
                "tipo": "pagato_diverso_dal_netto",
                "messaggio": (f"Media pagata {pagato_medio:.2f} € contro un netto medio di "
                              f"{netto_medio:.2f} €: scostamento {delta:+.2f} €. "
                              "Possibili acconti, arretrati o pagamenti parziali."),
            })

    if not utili:
        out["avvisi"].append({
            "tipo": "nessun_importo",
            "messaggio": "Nessuna busta con importi leggibili: il contratto va compilato a mano.",
        })
    return out
