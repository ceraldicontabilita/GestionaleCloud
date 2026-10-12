"""Credito IVA nel piano: LIPE canonica, calcolo distinto, mai un pagamento."""

from datetime import date
from urllib.parse import quote
from app.services.iva_liquidation_query import money_cents, get_iva_period_snapshot
from app.services.expectation_policy import ExpectationStatus


def quadro_lipe(doc):
    if not doc.get("quadratura_ok") or doc.get("stato") == "sostituita":
        return None
    final = doc.get("iva_da_versare_o_credito")
    sign = doc.get("iva_da_versare_o_credito_segno")
    if final is None or sign not in {"credito", "debito"}:
        return None
    amount = money_cents(final)
    mese = money_cents(doc.get("iva_dovuta_o_credito"))
    mese_sign = doc.get("iva_dovuta_o_credito_segno")
    return {
        "fonte": "LIPE",
        "verificato": True,
        "credito_iniziale_cents": money_cents(doc.get("credito_periodo_precedente"))
        + money_cents(doc.get("credito_anno_precedente")),
        "credito_mese_precedente_cents": money_cents(
            doc.get("credito_periodo_precedente")
        ),
        "credito_anno_precedente_cents": money_cents(
            doc.get("credito_anno_precedente")
        ),
        "riporto_annuale_indicato": doc.get("credito_anno_precedente") is not None,
        "iva_vendite_cents": money_cents(doc.get("iva_esigibile")),
        "iva_acquisti_cents": money_cents(doc.get("iva_detratta")),
        "debito_mese_cents": mese if mese_sign == "debito" else 0,
        "credito_mese_cents": mese if mese_sign == "credito" else 0,
        "altre_rettifiche_cents": money_cents(doc.get("debito_periodo_precedente"))
        + money_cents(doc.get("interessi_trimestrali"))
        - money_cents(doc.get("versamenti_auto"))
        - money_cents(doc.get("crediti_imposta"))
        - money_cents(doc.get("acconto_dovuto")),
        "credito_residuo_cents": amount if sign == "credito" else 0,
        "da_versare_cents": amount if sign == "debito" else 0,
        "documento": {
            "nome": doc.get("nome_file"),
            "protocollo": doc.get("protocollo"),
            "pdf_url": None,
            "pagina": doc.get("source_page"),
        },
    }


async def arricchisci_piano_iva(db, griglia, oggi):
    righe = [r for r in griglia["voci"] if r["voce"]["id"] == "iva_mensile"]
    if not righe:
        return griglia
    anno = griglia["anno"]
    comunicazioni = await db["iva_comunicazioni"].find(
        {"periodo": {"$regex": f"^{anno}-"}, "verificato": True}, {"_id": 0}
    ).to_list(100)
    by_comunicazione = {d["periodo"]: d for d in comunicazioni
                       if d.get("compensazione_comunicata")
                       and d.get("source_message_id")
                       and len(d.get("source_sha256") or "") == 64}
    docs = (
        await db["lipe_periodi"]
        .find({"periodo": {"$regex": f"^{anno}-"}}, {"_id": 0})
        .to_list(None)
    )
    by_period = {}
    for d in sorted(
        docs,
        key=lambda d: (
            str(d.get("aggiornato_at") or ""),
            int(d.get("protocollo") or 0),
        ),
    ):
        if quadro_lipe(d):
            by_period[d["periodo"]] = d
    for r in righe:
        r["voce"][
            "nota"
        ] = "Il credito IVA si riporta mese per mese. LIPE, F24 e quietanza restano prove distinte."
        for c in r["caselle"]:
            mese = int(c["periodo"])
            periodo = f"{anno}-{mese:02d}"
            d = by_period.get(periodo)
            q = quadro_lipe(d) if d else None
            if q:
                # Gli originali si cercano per impronta/id, mai per solo nome.
                digest = d.get("source_sha256")
                if digest:
                    original = await db["documents_inbox"].find_one(
                        {"sha256": digest}, {"id": 1}
                    )
                    if original and original.get("id"):
                        q["documento"]["pdf_url"] = "/api/originale/documento/" + quote(
                            str(original["id"]), safe=""
                        )
                if not q["documento"]["pdf_url"] and d.get("source_document_id"):
                    q["documento"]["pdf_url"] = (
                        "/api/originale/documento_fiscale/"
                        + quote(str(d["source_document_id"]), safe="")
                    )
                if not q["documento"]["pdf_url"] and d.get("drive_file_id"):
                    q["documento"]["pdf_url"] = "/api/originale/drive/" + quote(
                        str(d["drive_file_id"]), safe=""
                    )
                prev = by_period.get(f"{anno}-{mese-1:02d}") if mese > 1 else None
                pq = quadro_lipe(prev) if prev else None
                q["riporto_coerente"] = (
                    None
                    if not pq
                    else q["credito_mese_precedente_cents"]
                    == pq["credito_residuo_cents"]
                )
            elif (anno, mese) < (oggi.year, oggi.month):
                snap = await get_iva_period_snapshot(
                    db, anno=anno, mese=mese, today=oggi
                )
                q = {
                    "fonte": "Gestione IVA",
                    "verificato": snap.get("fonte") == "liquidazione_confermata",
                    "stato_calcolo": snap.get("stato_calcolo"),
                    "documento": None,
                    "credito_iniziale_cents": snap.get("credito_precedente_cents"),
                    "iva_vendite_cents": snap.get("iva_vendite_cents"),
                    "iva_acquisti_cents": snap.get("iva_acquisti_cents"),
                    "credito_residuo_cents": (
                        snap.get("credito_periodo_cents")
                        if snap.get("attendibile")
                        else None
                    ),
                    "da_versare_cents": (
                        snap.get("debito_periodo_cents")
                        if snap.get("attendibile")
                        else None
                    ),
                    "motivi": snap.get("motivi") or [],
                    "lipe_attesa": True,
                }
            if not q:
                c["iva"] = {
                    "fonte": "periodo_non_concluso",
                    "documento": None,
                    "credito_residuo_cents": None,
                    "da_versare_cents": None,
                }
                continue
            c["iva"] = q
            comunicazione = by_comunicazione.get(periodo)
            if comunicazione:
                q["comunicazione"] = {
                    k: comunicazione.get(k) for k in (
                        "oggetto", "data_email", "source_url", "debito_mese_cents",
                        "source_message_id",
                    )
                }
            amount = q.get("da_versare_cents")
            # Senza LIPE o liquidazione confermata non certificare il riporto.
            if not q.get("verificato"):
                if not c["modelli"]:
                    c.update(
                        stato="iva_compensazione_comunicata" if comunicazione else "iva_da_verificare",
                        etichetta_stato=("Debito compensato secondo il commercialista · LIPE attesa"
                                         if comunicazione else "IVA da verificare · LIPE attesa"),
                        giorni_scaduto=None,
                    )
                continue
            if amount == 0:
                c.update(
                    stato="iva_a_credito",
                    etichetta_stato=(
                        "Nessun versamento dovuto · a credito"
                        if q.get("credito_residuo_cents", 0)
                        else "Nessun versamento dovuto · saldo zero"
                    ),
                    credito=str((q.get("credito_residuo_cents") or 0) / 100),
                    importo=None,
                    residuo_cents=0,
                    giorni_scaduto=None,
                    giorni_ritardo=None,
                    expectation_status=ExpectationStatus.NON_APPLICABILE.value,
                    mandatory=False,
                )
                if c["modelli"]:
                    q["versamento_da_verificare"] = True
            elif amount is not None:
                # La LIPE definisce il dovuto; banca/quietanze definiscono il pagato.
                paid = max(
                    0, (c.get("debito_cents") or 0) - (c.get("residuo_cents") or 0)
                )
                residual = max(0, amount - paid)
                c.update(
                    debito_cents=amount,
                    residuo_cents=residual,
                    importo=str(amount / 100),
                    mandatory=True,
                )
                if residual:
                    state = (
                        "scaduto_non_pagato"
                        if c.get("scadenza")
                        and date.fromisoformat(c["scadenza"]) < oggi
                        else "da_pagare"
                    )
                    c.update(
                        stato=state,
                        etichetta_stato=(
                            "IVA da pagare"
                            if c["modelli"]
                            else "IVA da versare · F24 mancante"
                        ),
                        expectation_status=ExpectationStatus.ATTESO.value,
                    )
    # Ricostruire i riepiloghi dopo l'arricchimento, anche per la vista multianno.
    all_cells = [c for r in griglia["voci"] for c in r["caselle"]]
    griglia["conteggi"] = {
        s: sum(c["stato"] == s for c in all_cells)
        for s in {c["stato"] for c in all_cells}
    }
    griglia["mancano"] = [
        m for m in griglia["mancano"] if m["voce"] != "IVA mensile (6001-6012)"
    ]
    for r in righe:
        griglia["mancano"].extend(
            {
                "anno": anno,
                "voce": r["voce"]["etichetta"],
                "codici": [f'60{int(c["periodo"]):02d}'],
                "periodo": c["etichetta_periodo"],
                "scadenza": c["scadenza"],
                "stato": c["stato"],
                "giorni_scaduto": c["giorni_scaduto"],
            }
            for c in r["caselle"]
            if c["mandatory"]
            and c.get("residuo_cents", 0) > 0
            and c.get("scadenza")
            and date.fromisoformat(c["scadenza"]) < oggi
        )
    from app.services.expectation_policy import mandatory_expectations_closed

    griglia["anno_chiuso"] = mandatory_expectations_closed(
        [c for c in all_cells if c["mandatory"]]
    )
    return griglia
