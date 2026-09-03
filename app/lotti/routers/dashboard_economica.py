"""
Dashboard economica — Tranche 4 (HACCP features, 04/07/2026).

Punto 4 delle 7 macro-funzionalità richieste: valore lotti attivi/in
scadenza/smaltiti, costo spreco giornaliero/mensile, margine per prodotto/
reparto, prodotti più costosi/meno redditizi, variazione prezzi materie
prime, fornitori con maggiore incidenza.

Principio: AGGREGARE quello che esiste già (valore/semaforo lotto da
Tranche 0, report-sprechi di vendita_banco.py, margini già calcolati in
prodotti_vendita.py), non ricalcolare la stessa logica in un posto nuovo.
Le uniche aggregazioni davvero nuove sono: valore economico dei lotti
smaltiti/attivi (nessuno le sommava prima), margine per reparto (serviva
un join prodotti_vendita→ricette.reparto che non esisteva), fornitori per
spesa totale nel periodo.
"""
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Query

from app.lotti.db import database as db

router = APIRouter(prefix="/dashboard-economica", tags=["Dashboard Economica"])


def _fine_mese(anno: int, mese: int) -> date:
    if mese == 12:
        return date(anno, 12, 31)
    return date(anno, mese + 1, 1) - timedelta(days=1)


async def _valore_lotti() -> dict:
    """Valore economico dei lotti attivi e di quelli in scadenza (rosso/
    arancione/giallo), riusando l'arricchimento centralizzato di Tranche 0
    — nessun ricalcolo del semaforo o del costo qui."""
    from app.lotti.servizi.lotto_arricchimento_service import arricchisci_lotto

    from app.lotti.routers.utils import FILTRO_LOTTO_APERTO
    docs = await db.lotti.find(dict(FILTRO_LOTTO_APERTO), {"_id": 0}).to_list(5000)
    attivi = [arricchisci_lotto(dict(d)) for d in docs if (d.get("quantita") or 0) > 0]

    valore_totale = round(sum(l["valore_economico"] or 0 for l in attivi), 2)
    in_scadenza = [l for l in attivi if l["stato_scadenza"]["colore"] in ("rosso", "arancione", "giallo")]
    valore_in_scadenza = round(sum(l["valore_economico"] or 0 for l in in_scadenza), 2)
    top_scadenza = sorted(in_scadenza, key=lambda l: -(l["valore_economico"] or 0))[:20]
    # drill-down anche sul tile "valore lotti attivi" (era l'unico non
    # cliccabile — audit onesto 04/07/2026)
    top_attivi = sorted(attivi, key=lambda l: -(l["valore_economico"] or 0))[:20]

    return {
        "valore_totale_lotti_attivi": valore_totale,
        "n_lotti_attivi": len(attivi),
        "valore_lotti_in_scadenza": valore_in_scadenza,
        "n_lotti_in_scadenza": len(in_scadenza),
        "lotti_in_scadenza_dettaglio": top_scadenza,
        "lotti_attivi_dettaglio": top_attivi,
    }


async def _valore_smaltiti(data_da: str, data_a: str) -> dict:
    """Valore dei lotti smaltiti nel periodo — costo_pezzo × quantità
    residua al momento dello smaltimento (lo smaltimento non azzera
    `quantita`, vedi lotti_produzione.py::smalti_lotto, quindi il dato
    rappresenta davvero quanto è stato buttato)."""
    docs = await db.lotti.find(
        {"stato": "smaltito", "data_smaltimento": {"$gte": data_da, "$lte": data_a + "T23:59:59"}},
        {"_id": 0},
    ).to_list(5000)
    righe = []
    totale = 0.0
    for d in docs:
        costo_pezzo = d.get("costo_pezzo")
        quantita = d.get("quantita") or 0
        valore = round(costo_pezzo * quantita, 2) if costo_pezzo is not None else None
        if valore:
            totale += valore
        righe.append({
            "prodotto": d.get("prodotto"), "numero_lotto": d.get("numero_lotto"),
            "quantita": quantita, "valore": valore,
            "data_smaltimento": d.get("data_smaltimento"), "motivo": d.get("motivo_smaltimento"),
        })
    righe.sort(key=lambda r: -(r["valore"] or 0))
    return {"valore_totale": round(totale, 2), "n_lotti": len(righe), "dettaglio": righe[:20]}


async def _costo_spreco_periodo(data_da: str, data_a: str, raggruppamento: str) -> dict:
    """Spreco totale = invenduto al banco (già calcolato da
    vendita_banco.report-sprechi) + lotti smaltiti nello stesso periodo
    (mai sommati insieme prima d'ora)."""
    from app.lotti.routers.vendita_banco import get_report_sprechi
    report = await get_report_sprechi(raggruppamento=raggruppamento, data_da=data_da, data_a=data_a)
    costo_banco = round(report.get("kpi", {}).get("costo_totale_sprecato", 0) or 0, 2)
    smaltiti = await _valore_smaltiti(data_da, data_a)

    # Dettaglio per il drill-down (tile "spreco oggi" — era l'unico senza):
    # aggrega i prodotti invenduti al banco su tutte le righe del periodo.
    per_prodotto: dict = {}
    for r in report.get("righe") or []:
        prodotti = r.get("prodotti") or []
        if isinstance(prodotti, dict):
            prodotti = list(prodotti.values())
        for p in prodotti:
            nome = p.get("prodotto") or p.get("nome") or "?"
            g = per_prodotto.setdefault(nome, {"prodotto": nome, "pezzi_invenduto": 0, "costo_sprecato": 0.0})
            g["pezzi_invenduto"] += p.get("pezzi_invenduto") or 0
            g["costo_sprecato"] = round(g["costo_sprecato"] + (p.get("costo_sprecato") or 0), 2)
    dettaglio_banco = sorted(per_prodotto.values(), key=lambda x: -x["costo_sprecato"])[:15]

    return {
        "costo_banco_invenduto": costo_banco,
        "costo_lotti_smaltiti": smaltiti["valore_totale"],
        "costo_totale": round(costo_banco + smaltiti["valore_totale"], 2),
        "dettaglio_banco": dettaglio_banco,
        "dettaglio_smaltiti": smaltiti["dettaglio"][:15],
    }


async def _margini() -> dict:
    """Margine per prodotto (ricalcolato da prezzo/costo correnti, stesso
    calcolo di GET /prodotti-vendita/ per non avere due fonti di verità che
    divergono) e per reparto (join prodotti_vendita→ricette.reparto, che
    non esisteva)."""
    prodotti = await db.prodotti_vendita.find(
        {"attivo": True},
        {"_id": 0, "id": 1, "nome": 1, "categoria": 1, "ricetta_id": 1, "prezzo_vendita": 1, "costo_produzione": 1},
    ).to_list(3000)

    ricetta_ids = [p["ricetta_id"] for p in prodotti if p.get("ricetta_id")]
    reparto_per_ricetta = {}
    if ricetta_ids:
        docs = await db.ricette.find(
            {"id": {"$in": ricetta_ids}}, {"_id": 0, "id": 1, "reparto": 1}
        ).to_list(len(ricetta_ids))
        reparto_per_ricetta = {d["id"]: (d.get("reparto") or "altro") for d in docs}

    validi = []
    for p in prodotti:
        pv = float(p.get("prezzo_vendita") or 0)
        cp = float(p.get("costo_produzione") or 0)
        if pv <= 0 or cp <= 0:
            continue
        margine_euro = round(pv - cp, 2)
        margine_pct = round((margine_euro / pv) * 100, 1)
        validi.append({
            "nome": p.get("nome"), "categoria": p.get("categoria") or "",
            "reparto": reparto_per_ricetta.get(p.get("ricetta_id"), "altro"),
            # ricetta_id: serve al drill-down riga→scheda ricetta nella dashboard
            "ricetta_id": p.get("ricetta_id"),
            "prezzo_vendita": pv, "costo_produzione": cp,
            "margine_euro": margine_euro, "margine_percentuale": margine_pct,
        })

    piu_costosi = sorted(validi, key=lambda p: -p["costo_produzione"])[:15]
    meno_redditizi = sorted(validi, key=lambda p: p["margine_percentuale"])[:15]

    per_reparto: dict = {}
    for p in validi:
        r = per_reparto.setdefault(p["reparto"], {"reparto": p["reparto"], "n_prodotti": 0,
                                                    "margine_euro_totale": 0.0, "somma_margine_pct": 0.0})
        r["n_prodotti"] += 1
        r["margine_euro_totale"] += p["margine_euro"]
        r["somma_margine_pct"] += p["margine_percentuale"]
    margine_reparto = [{
        "reparto": r["reparto"], "n_prodotti": r["n_prodotti"],
        "margine_euro_totale": round(r["margine_euro_totale"], 2),
        "margine_percentuale_medio": round(r["somma_margine_pct"] / r["n_prodotti"], 1),
    } for r in per_reparto.values()]
    margine_reparto.sort(key=lambda r: -r["margine_euro_totale"])

    return {
        "prodotti_piu_costosi": piu_costosi,
        "prodotti_meno_redditizi": meno_redditizi,
        "margine_per_reparto": margine_reparto,
        "n_prodotti_con_margine": len(validi),
    }


async def _variazione_prezzi_materie_prime(soglia: float = 15.0, limit: int = 15) -> list:
    """Stessa logica di raggruppamento di ingredienti.prezzi-alert (delta
    di prezzo tra fornitori per lo stesso ingrediente canonico), ma con i
    nomi leggibili per la dashboard invece della mappa product_id→delta
    usata per i badge di OrdiniFornitoriView."""
    prodotti = await db.dizionario_prodotti.find(
        {"prezzo_kg": {"$gte": 0.50, "$lte": 200.0}, "ingrediente_canonico": {"$exists": True, "$nin": [None, ""]}},
        {"_id": 0, "ingrediente_canonico": 1, "nome_canonico": 1, "nome_display": 1, "prezzo_kg": 1, "fornitore": 1},
    ).to_list(5000)

    per_canonico: dict = {}
    for p in prodotti:
        canc = (p.get("ingrediente_canonico") or "").strip()
        if not canc:
            continue
        fornitore = p.get("fornitore") or ""
        prezzo = float(p.get("prezzo_kg") or 0)
        g = per_canonico.setdefault(canc, {"nome": p.get("nome_display") or p.get("nome_canonico") or canc, "prezzi": {}})
        if fornitore not in g["prezzi"] or g["prezzi"][fornitore] > prezzo:
            g["prezzi"][fornitore] = prezzo

    righe = []
    for g in per_canonico.values():
        prezzi = list(g["prezzi"].values())
        if len(prezzi) < 2:
            continue
        p_min, p_max = min(prezzi), max(prezzi)
        if p_min <= 0:
            continue
        delta = (p_max - p_min) / p_min * 100
        if soglia <= delta <= 300:
            righe.append({"ingrediente": g["nome"], "prezzo_min_kg": p_min, "prezzo_max_kg": p_max, "variazione_pct": round(delta, 1)})
    righe.sort(key=lambda r: -r["variazione_pct"])
    return righe[:limit]


async def _fornitori_maggiore_incidenza(data_da: str, data_a: str, limit: int = 15) -> list:
    """Spesa totale per fornitore nel periodo, da `fatture` — non esisteva
    nessuna aggregazione di questo tipo.
    NOTA: fatture.data_fattura è in formato MISTO (dd/mm/yyyy dall'import,
    ISO storico) — il filtro periodo va fatto su date VERE in Python, un
    $gte/$lte tra stringhe prendeva un sottoinsieme quasi casuale (stessa
    famiglia di bug bonificata il 04/07/2026)."""
    from app.lotti.routers.utils import parse_data_flessibile
    d_da = parse_data_flessibile(data_da)
    d_a = parse_data_flessibile(data_a)
    docs = await db.fatture.find(
        {}, {"_id": 0, "fornitore": 1, "importo_totale": 1, "data_fattura": 1},
    ).to_list(20000)
    per_fornitore: dict = {}
    for d in docs:
        dd = parse_data_flessibile(d.get("data_fattura"))
        if not dd or (d_da and dd < d_da) or (d_a and dd > d_a):
            continue
        f = (d.get("fornitore") or "Sconosciuto").strip() or "Sconosciuto"
        per_fornitore[f] = per_fornitore.get(f, 0) + float(d.get("importo_totale") or 0)
    totale = sum(per_fornitore.values()) or 1.0
    righe = [{"fornitore": f, "spesa": round(v, 2), "incidenza_pct": round(v / totale * 100, 1)}
             for f, v in per_fornitore.items()]
    righe.sort(key=lambda r: -r["spesa"])
    return righe[:limit]


@router.get("/riepilogo")
async def riepilogo(mese: Optional[str] = Query(None, description="YYYY-MM, default mese corrente")):
    """Un'unica risposta con tutti i KPI della dashboard economica + i
    dettagli sottostanti (già inclusi, non serve un secondo giro di
    chiamate per il drill-down su liste corte come queste)."""
    oggi = date.today()
    if mese:
        anno_m, mese_m = int(mese[:4]), int(mese[5:7])
    else:
        anno_m, mese_m = oggi.year, oggi.month

    inizio_mese = date(anno_m, mese_m, 1)
    fine_mese_calcolata = _fine_mese(anno_m, mese_m)
    fine_mese = min(fine_mese_calcolata, oggi) if (anno_m, mese_m) == (oggi.year, oggi.month) else fine_mese_calcolata
    oggi_iso = oggi.isoformat()

    valore_lotti = await _valore_lotti()
    spreco_oggi = await _costo_spreco_periodo(oggi_iso, oggi_iso, "giorno")
    spreco_mese = await _costo_spreco_periodo(inizio_mese.isoformat(), fine_mese.isoformat(), "mese")
    smaltiti_mese = await _valore_smaltiti(inizio_mese.isoformat(), fine_mese.isoformat())
    margini = await _margini()
    variazioni = await _variazione_prezzi_materie_prime()
    fornitori = await _fornitori_maggiore_incidenza(inizio_mese.isoformat(), fine_mese.isoformat())

    return {
        "periodo_mese": f"{anno_m:04d}-{mese_m:02d}",
        **valore_lotti,
        "valore_lotti_smaltiti_mese": smaltiti_mese["valore_totale"],
        "lotti_smaltiti_mese_dettaglio": smaltiti_mese["dettaglio"],
        "costo_spreco_giorno": spreco_oggi["costo_totale"],
        "dettaglio_spreco_giorno": spreco_oggi,
        "costo_spreco_mese": spreco_mese["costo_totale"],
        "dettaglio_spreco_mese": spreco_mese,
        **margini,
        "variazione_prezzi_materie_prime": variazioni,
        "fornitori_maggiore_incidenza": fornitori,
    }
