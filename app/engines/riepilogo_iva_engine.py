"""
Riepilogo annuale IVA e controlli automatici (logica pura).

Fonte di verità: memoria/SPECIFICA_IVA.md §16-18.

Non tocca il database: riceve la lista delle fatture di acquisto arricchite
(campi IVA già calcolati) e, opzionalmente, le liquidazioni mensili confermate
dell'anno; produce il riepilogo per categoria (§16), i totali del calcolo
annuale (§17) e l'elenco delle anomalie bloccanti/di avviso (§18).
"""
from typing import Any, Dict, List, Optional

TIPI_NOTA_CREDITO = ("TD04", "TD08")


def _iva(f: Dict[str, Any]) -> float:
    val = f.get("iva_detraibile")
    if val is None:
        val = f.get("iva")
    try:
        return round(float(val or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def _is_nota_credito(f: Dict[str, Any]) -> bool:
    return str(f.get("tipo_documento") or "").upper() in TIPI_NOTA_CREDITO


def riepilogo_categorie(fatture: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    """Classifica l'IVA delle fatture nelle categorie del §16.

    Ritorna {categoria: {"iva": totale, "conteggio": n}}.
    Ogni fattura contribuisce a UNA sola categoria per non fare doppioni.
    """
    cat = {
        "disponibile": [0.0, 0],
        "utilizzata": [0.0, 0],
        "non_utilizzata": [0.0, 0],
        "indetraibile": [0.0, 0],
        "rettificata": [0.0, 0],
        "recuperata_annualmente": [0.0, 0],
        "rinviata": [0.0, 0],
        "da_verificare": [0.0, 0],
    }

    for f in fatture:
        if _is_nota_credito(f):
            continue
        iva = _iva(f)
        stato = f.get("stato_detrazione_iva")
        if f.get("iva_utilizzata") is True:
            key = "utilizzata"
        elif stato == "INDETRAIBILE":
            key = "indetraibile"
        elif stato == "RETTIFICATA":
            key = "rettificata"
        elif stato == "RECUPERATA_IN_DICHIARAZIONE_ANNUALE":
            key = "recuperata_annualmente"
        elif stato == "RINVIATA":
            key = "rinviata"
        elif stato == "DA_VERIFICARE":
            key = "da_verificare"
        else:
            key = "non_utilizzata"
        cat[key][0] = round(cat[key][0] + iva, 2)
        cat[key][1] += 1

    # "disponibile" = potenzialmente detraibile (tutto ciò che non è
    # indetraibile/rettificato/da verificare): utilizzata + non utilizzata +
    # rinviata + recuperabile.
    disp_iva = round(
        cat["utilizzata"][0] + cat["non_utilizzata"][0]
        + cat["rinviata"][0] + cat["recuperata_annualmente"][0], 2
    )
    disp_n = (cat["utilizzata"][1] + cat["non_utilizzata"][1]
              + cat["rinviata"][1] + cat["recuperata_annualmente"][1])
    cat["disponibile"] = [disp_iva, disp_n]

    return {k: {"iva": v[0], "conteggio": v[1]} for k, v in cat.items()}


def calcolo_annuale(
    fatture: List[Dict[str, Any]],
    liquidazioni_confermate: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Totali del calcolo annuale (§17).

    IVA annuale detraibile = IVA già utilizzata nelle liquidazioni
      + IVA recuperabile non ancora utilizzata
      - IVA rettificata o resa indetraibile.
    Parte dalle liquidazioni confermate per l'IVA vendite e il credito finale.
    """
    cat = riepilogo_categorie(fatture)
    liq = liquidazioni_confermate or []

    iva_vendite = round(sum(float(l.get("iva_vendite") or 0) for l in liq), 2)
    iva_acquisti_utilizzata = cat["utilizzata"]["iva"]
    iva_recuperabile = round(
        cat["non_utilizzata"]["iva"] + cat["rinviata"]["iva"]
        + cat["recuperata_annualmente"]["iva"], 2
    )
    iva_detraibile_annuale = round(iva_acquisti_utilizzata + iva_recuperabile, 2)

    # Saldo annuale dalle liquidazioni confermate (debito - credito).
    debito = round(sum(float(l.get("debito_periodo") or 0) for l in liq), 2)
    credito = round(sum(float(l.get("credito_periodo") or 0) for l in liq), 2)
    saldo_finale = round(debito - credito, 2)

    return {
        "iva_vendite": iva_vendite,
        "iva_acquisti_utilizzata": iva_acquisti_utilizzata,
        "iva_recuperabile_non_utilizzata": iva_recuperabile,
        "iva_indetraibile": cat["indetraibile"]["iva"],
        "iva_rettificata": cat["rettificata"]["iva"],
        "iva_detraibile_annuale": iva_detraibile_annuale,
        "totale_debito": debito,
        "totale_credito": credito,
        "saldo_finale": saldo_finale,
        "credito_finale": round(-saldo_finale, 2) if saldo_finale < 0 else 0.0,
        "debito_finale": saldo_finale if saldo_finale > 0 else 0.0,
        "liquidazioni_confermate": len(liq),
    }


def rileva_anomalie(fatture: List[Dict[str, Any]], mese_corrente: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
    """Anomalie §18. Ritorna {"bloccanti": [...], "avvisi": [...]}.

    Ogni anomalia: {tipo, fattura_id, messaggio}. `mese_corrente` ('YYYY-MM')
    serve per l'avviso "non utilizzata da molti mesi" (>3 mesi fa).
    """
    bloccanti: List[Dict[str, Any]] = []
    avvisi: List[Dict[str, Any]] = []

    def _add(lista, tipo, f, messaggio):
        lista.append({
            "tipo": tipo,
            "fattura_id": f.get("id") or f.get("_id"),
            "invoice_number": f.get("invoice_number"),
            "supplier_name": f.get("supplier_name"),
            "messaggio": messaggio,
        })

    for f in fatture:
        iva = _iva(f)
        periodo = f.get("periodo_iva_attribuito")

        # ── Bloccanti ──
        if iva < 0:
            _add(bloccanti, "iva_negativa", f, "Importo IVA negativo o incoerente")
        if f.get("annullata") is True and f.get("iva_utilizzata") is True:
            _add(bloccanti, "annullata_utilizzata", f,
                 "Documento annullato ma con IVA risultante utilizzata")
        # Retroattribuzione dic→anno precedente: periodo attribuito < anno ricezione
        dr = str(f.get("data_ricezione") or "")[:4]
        if periodo and dr and periodo[:4] < dr:
            _add(bloccanti, "retroattribuzione_anno", f,
                 f"IVA attribuita a {periodo} ma ricevuta nel {dr}: retroattribuzione all'anno precedente")

        # ── Avvisi ──
        if not f.get("data_operazione") and not f.get("data_documento"):
            _add(avvisi, "data_operazione_mancante", f, "Data operazione/documento mancante")
        if not f.get("data_ricezione"):
            _add(avvisi, "data_ricezione_mancante", f, "Data ricezione SDI mancante")
        if f.get("stato_detrazione_iva") == "DA_VERIFICARE":
            _add(avvisi, "da_verificare", f, "Fattura con dati incompleti o incoerenti (da verificare)")
        # §18: fattura (immediata) emessa/trasmessa oltre 12 giorni dall'operazione.
        # Controllo documentale sul fornitore, non tocca il periodo IVA.
        data_tx = f.get("data_trasmissione_sdi")
        if data_tx:
            from app.engines.iva_engine import controllo_emissione_12_giorni
            chk = controllo_emissione_12_giorni(
                f.get("data_operazione") or f.get("data_documento"), data_tx
            )
            if chk.get("anomalia"):
                _add(avvisi, "emessa_oltre_12_giorni", f, chk["messaggio"])
        if mese_corrente and periodo and f.get("iva_utilizzata") is not True and iva > 0:
            # non utilizzata da più di 3 mesi
            try:
                ap = int(periodo[:4]) * 12 + int(periodo[5:7])
                am = int(mese_corrente[:4]) * 12 + int(mese_corrente[5:7])
                if am - ap > 3:
                    _add(avvisi, "non_utilizzata_da_mesi", f,
                         f"IVA di {periodo} ancora non utilizzata: valutare il recupero annuale")
            except (ValueError, IndexError):
                pass

    return {"bloccanti": bloccanti, "avvisi": avvisi}
