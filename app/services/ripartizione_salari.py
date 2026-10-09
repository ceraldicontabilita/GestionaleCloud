"""Quote dei pagamenti sulle buste, senza duplicare il movimento bancario.

Prima le destinazioni scelte, poi la competenza documentata, infine il
residuo più antico. Il denaro non ancora utilizzabile rimane un acconto.
La prima nota cronologica conserva sempre il pagamento intero alla sua data.
"""
from copy import deepcopy


def ripartisci_movimenti(registro):
    from app.services.posizione_dipendente import ZERO, importo, _fine_mese

    debiti, saldati = {}, set()
    for mv in registro:
        comp = tuple(mv["competenza"]) if mv.get("competenza") else None
        if mv["tipo"] == "busta" and comp:
            valore = importo(mv.get("dare"))
            precedente = debiti.get(comp, ZERO)
            debiti[comp] = None if valore is None or precedente is None else precedente + valore
        saldati.update(tuple(p) for p in (mv.get("link", {}).get("periodi_saldati") or []))
    residui = dict(debiti)
    for comp in saldati:
        residui[comp] = ZERO
    ordine = sorted(debiti, key=lambda p: (_fine_mese(*p), p))
    out = [deepcopy(mv) for mv in registro
           if mv["tipo"] not in ("bonifico", "acconto") or not mv.get("avere")]
    pagamenti = [mv for mv in registro if mv["tipo"] in ("bonifico", "acconto") and mv.get("avere")]
    pagamenti.sort(key=lambda mv: (mv["data"], str(mv.get("link", {}).get("key") or
                         mv.get("link", {}).get("acconto_id") or
                         mv.get("link", {}).get("bonifico_da_associare_id") or mv["descrizione"])))
    scelte_non_applicate = []
    for mv in pagamenti:
        if mv.get("link", {}).get("periodi_saldati"):
            out.append(deepcopy(mv))
            continue
        totale = importo(mv["avere"])
        restante = totale
        quote = {}

        def assegna(comp, limite=None, motivo="residuo più antico", esplicito=False):
            nonlocal restante
            if restante <= ZERO or comp in saldati:
                return
            residuo = residui.get(comp)
            if residuo is None and not esplicito:
                return  # netto assente non significa zero né un debito inventato
            quota = min(restante, residuo if residuo is not None else restante)
            if limite is not None:
                quota = min(quota, max(ZERO, importo(limite) or ZERO))
            if quota <= ZERO:
                return
            precedente, _ = quote.get(comp, (ZERO, motivo))
            quote[comp] = (precedente + quota, motivo)
            restante -= quota
            if residuo is not None:
                residui[comp] -= quota

        scelte = mv.get("link", {}).get("destinazioni_salari") or []
        for scelta in scelte:
            comp = (int(scelta["anno"]), int(scelta["mese"]))
            prima = restante
            assegna(comp, scelta.get("importo"), "cedolino scelto", esplicito=True)
            if prima - restante < importo(scelta["importo"]):
                scelte_non_applicate.append({"key": mv.get("link", {}).get("key"), "competenza": comp})
        if not scelte and mv.get("competenza"):
            assegna(tuple(mv["competenza"]), motivo="competenza del pagamento", esplicito=True)
        for comp in ordine:
            assegna(comp)
        for comp, (quota, motivo) in quote.items():
            riga = deepcopy(mv)
            riga.update(competenza=comp, avere=quota)
            riga["link"].update(importo_pagamento=float(totale), quota_salari=float(quota),
                                criterio_ripartizione=motivo)
            out.append(riga)
        if restante > ZERO:
            riga = deepcopy(mv)
            riga.update(competenza=None, avere=restante,
                        avviso="Acconto disponibile per il prossimo cedolino")
            riga["link"].update(importo_pagamento=float(totale), acconto_disponibile=float(restante))
            out.append(riga)
    return {"movimenti": out, "residui": residui, "scelte_non_applicate": scelte_non_applicate}


def valida_destinazioni(destinazioni, totale, periodi):
    from app.services.posizione_dipendente import ZERO, importo

    if not isinstance(destinazioni, list) or len(destinazioni) > 500:
        raise ValueError("Elenco dei cedolini non valido")
    out, visti, somma = [], set(), ZERO
    for d in destinazioni:
        try:
            anno, mese = int(d["anno"]), int(d["mese"])
            quota = importo(d["importo"])
        except (KeyError, TypeError, ValueError):
            raise ValueError("Indica cedolino e quota da assegnare") from None
        if (anno, mese) not in periodi or (anno, mese) in visti or quota is None or quota <= ZERO:
            raise ValueError("Cedolino inesistente, ripetuto o quota non valida")
        visti.add((anno, mese))
        somma += quota
        out.append({"anno": anno, "mese": mese, "importo": float(quota)})
    if somma > importo(totale):
        raise ValueError("Le quote superano l'importo del pagamento")
    return out


def indice_quote(registro, esiti=()):
    """Proiezione per mese della medesima prima nota (nessuna nuova scrittura)."""
    prove = {e.get("key"): e for e in esiti if e.get("key")}
    indice = {}
    for mv in ripartisci_movimenti(registro)["movimenti"]:
        if mv["tipo"] not in ("bonifico", "acconto") or not mv.get("avere") or not mv.get("competenza"):
            continue
        link = mv.get("link", {})
        prova = prove.get(link.get("key"), {})
        indice.setdefault(tuple(mv["competenza"]), []).append({
            **prova, "importo": float(mv["avere"]), "data": mv["data"],
            "causale": prova.get("causale") or mv["descrizione"],
            "quota_tipo": mv["tipo"], "importo_pagamento": link.get("importo_pagamento", float(mv["avere"])),
            "criterio_ripartizione": link.get("criterio_ripartizione"),
        })
    return indice
