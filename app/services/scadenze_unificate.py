"""Proiezione in sola lettura di scadenze e prove. Nessun pagamento sintetico.

L'anno della lista è quello della scadenza, non quello del pagamento. I modelli
e le quietanze passano dal Piano tributi (che deduplica e confronta le righe);
le rate restano obblighi distinti e non vengono sommate al capitale del piano.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from zoneinfo import ZoneInfo
from urllib.parse import quote

from app.config import settings
from app.document_repository import metadata_projection
from app.services import piano_tributi as piano
from app.services import f24_controllo_incrociato as registro_f24
from app.services.piano_iva import arricchisci_piano_iva


def oggi_roma():
    return datetime.now(ZoneInfo("Europe/Rome")).date()


def data_iso(value):
    try:
        return date.fromisoformat(str(value)[:10]).isoformat() if value else None
    except ValueError:
        return None


def cents(value):
    if value is None or value == "":
        return None
    try:
        amount = Decimal(str(value))
        return (
            int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            if amount.is_finite()
            else None
        )
    except (InvalidOperation, ValueError, TypeError):
        return None


def originale(tipo, id_):
    return f'/api/originale/{tipo}/{quote(str(id_), safe="")}' if id_ else None


def documenti(*items):
    seen = set()
    result = []
    for d in items:
        if d and d.get("url") and d["url"] not in seen:
            seen.add(d["url"])
            result.append(d)
    return result


def riga_tributo(voce, cell, anno):
    state = cell["stato"]
    if voce.get("natura") == "credito" or state in (
        piano.CREDITO_ASSENTE,
        piano.CREDITO_USATO,
        piano.NESSUN_F24,
    ):
        return None
    # Le ricorrenze opzionali senza alcuna prova non diventano debiti certi.
    if not cell.get("mandatory") and not cell.get("modelli") and state == piano.FUTURO:
        return None
    due, residual = cell.get("debito_cents"), cell.get("residuo_cents")
    settled = state in (piano.PAGATO, piano.PAGATO_QUIETANZA, "iva_a_credito")
    code = list(voce.get("codici") or [])
    if voce.get("id") == "iva_mensile":
        code = [f"60{int(cell['periodo']):02d}"]
    models = cell.get("modelli") or []
    docs = documenti(
        *(
            {"url": q.get("pdf_url"), "titolo": "Quietanza di pagamento"}
            for q in cell.get("quietanze_pagamento") or []
        ),
        *(
            {
                "url": m.get("pdf_url"),
                "titolo": (
                    "Quietanza"
                    if m.get("tipo_documento") == "quietanza"
                    else "Modello F24"
                ),
            }
            for m in models
        ),
        {
            "url": ((cell.get("iva") or {}).get("documento") or {}).get("pdf_url"),
            "titolo": "Liquidazione IVA",
        },
    )
    gruppo = voce.get("gruppo")
    kind = (
        "IVA"
        if voce.get("id") == "iva_mensile"
        else gruppo if gruppo in ("INPS", "INAIL", "IMU", "IRES", "IRAP") else "F24"
    )
    uncertain = state in (
        piano.DA_VERIFICARE_A_MANO,
        piano.DA_CONFERMARE_BANCA,
        "iva_da_verificare",
        "iva_compensazione_comunicata",
    )
    iva = cell.get("iva") or {}
    uncertain = (
        uncertain
        or iva.get("fonte") == "LIPE_da_verificare"
        or bool(iva.get("versamento_da_verificare"))
    )
    return {
        "id": cell.get("source_fact_id")
        or f"tributo:{voce['id']}:{anno}:{cell['periodo']}",
        "anno_competenza": anno,
        "periodo": cell.get("etichetta_periodo"),
        "data": data_iso(cell.get("scadenza")),
        "tipo": kind,
        "codici": code,
        "descrizione": voce.get("etichetta") or " / ".join(code),
        "source": "tributo",
        "stato": state,
        "stato_label": cell.get("etichetta_stato"),
        "pagata": settled,
        "completata": settled,
        "importo_cents": due,
        "pagato_cents": (
            cell["pagato_cents"]
            if "pagato_cents" in cell
            else (
                max(0, due - residual)
                if due is not None and residual is not None
                else None
            )
        ),
        "residuo_cents": 0 if settled else residual,
        "da_verificare": uncertain
        or (not settled and residual is None and state != piano.FUTURO),
        "conteggiabile": not uncertain,
        "monetaria": True,
        "documenti": docs,
        "f24_ids": sorted({m["f24_id"] for m in models if m.get("f24_id")}),
        "note": " · ".join(filter(None, [voce.get("nota"), cell.get("slittamento")])),
        "atteso_da_buste": cell.get("atteso_da_buste"),
        "dettaglio_url": "/situazione-fiscale/piano",
    }


async def carica_scadenze(db, anno, oggi=None):
    oggi = oggi or oggi_roma()
    semaphore = asyncio.Semaphore(4)

    async def read(coll, query=None):
        async with semaphore:
            return (
                await db[coll]
                .find(query or {}, metadata_projection(coll))
                .to_list(None)
            )

    company = {"company_id": settings.FISCAL_COMPANY_ID}
    (
        registry,
        voci,
        attesi,
        inps,
        plans,
        installments,
        payments,
        notifications,
        receipts,
        claims,
    ) = await asyncio.gather(
        registro_f24.carica_registro(db, strict=True),
        piano.voci_piano(db, scrivi=False),
        piano.attesi_dai_prospetti(db),
        read("dilazioni_inps"),
        read("tax_rate_plans", company),
        read("tax_rate_installments", company),
        read("tax_payments", company),
        read("notifiche_scadenze"),
        read("ricevute_pagopa"),
        read("cartelle_pagamento"),
    )
    modelli = piano._modelli_con_righe(registry)
    active = [v for v in voci if v.get("attivo", True)]
    rows = []
    warnings = []
    # Dicembre è dovuto a gennaio dell'anno successivo. Lo stesso registro
    # viene letto una sola volta per entrambe le griglie.
    for year in (anno - 1, anno):
        grid = piano._griglia_anno(active, registry, modelli, year, oggi, attesi)
        # LIPE già documentate; niente ricalcolo di migliaia di XML alla sola
        # apertura della lista. Le stime si consultano in Gestione IVA.
        grid = await arricchisci_piano_iva(db, grid, oggi, ricalcola_mancanti=False)
        for entry in grid["voci"]:
            for cell in entry["caselle"]:
                row = riga_tributo(entry["voce"], cell, year)
                if row:
                    rows.append(row)
        for entry in grid["fuori_piano"]:
            voce = {
                "id": f"extra:{entry['sezione']}:{entry['codice']}",
                "codici": [entry["codice"]],
                "etichetta": entry.get("descrizione") or f"Tributo {entry['codice']}",
            }
            row = riga_tributo(voce, entry["casella"], year)
            if row and entry["codice"] == "DLPI" and not row["pagata"]:
                # Il modello DLPI potrebbe coprire una o più rate già esposte.
                # Mantenerlo visibile senza sommare due volte un debito che
                # richiede l'identificazione della dilazione.
                row.update(
                    conteggiabile=False,
                    da_verificare=True,
                    note="Modello DLPI da confrontare con le rate INPS; escluso dal totale per evitare duplicazioni.",
                )
            if row:
                rows.append(row)

    quietanze = {q["id"]: q for q in registry["quietanze"]}
    for plan in inps:
        rates = plan.get("rate") or []
        bad = bool(
            plan.get("avvertenze")
            or not plan.get("quadra")
            or plan.get("pagamenti_non_previsti")
        )
        if bad:
            warnings.append(
                {
                    "id": plan["id"],
                    "messaggio": f"INPS {plan.get('rif')}: "
                    + "; ".join(
                        plan.get("avvertenze") or ["Piano o pagamenti da verificare"]
                    ),
                    "url": "/situazione-fiscale/dilazioni-inps",
                }
            )
        for rate in rates:
            qids = rate.get("quietanza_ids") or []
            proven = (
                rate.get("stato") == "PAGATA"
                and bool(qids)
                and all(q in quietanze for q in qids)
            )
            different = rate.get("versamento_diverso") or {}
            amount = rate.get("importo_cents")
            uncertain = (
                bad or bool(different) or (rate.get("stato") == "PAGATA" and not proven)
            )
            rows.append(
                {
                    "id": f"{plan['id']}:rata:{rate['numero']}",
                    "data": data_iso(rate.get("scadenza")),
                    "anno_competenza": anno,
                    "tipo": "INPS",
                    "source": "rata_inps",
                    "descrizione": f"Dilazione INPS {plan.get('rif')} · rata {rate['numero']}",
                    "importo_cents": amount,
                    "pagato_cents": amount if proven else None if different else 0,
                    "residuo_cents": 0 if proven else None if uncertain else amount,
                    "pagata": proven,
                    "completata": proven,
                    "da_verificare": uncertain,
                    "stato_label": (
                        "Pagata (quietanza)"
                        if proven
                        else (
                            "Rata da verificare"
                            if uncertain
                            else "Pagamento non riscontrato"
                        )
                    ),
                    "conteggiabile": not uncertain,
                    "monetaria": True,
                    "note": "; ".join(plan.get("avvertenze") or [])
                    + (
                        f" · Versamento di importo diverso: € {different.get('importo_cents',0)/100:.2f}, da attribuire"
                        if different
                        else ""
                    ),
                    "documenti": documenti(
                        {
                            "url": originale("documento", plan.get("documento_id")),
                            "titolo": "Piano INPS",
                        },
                        *(
                            {"url": originale("quietanza", q), "titolo": "Quietanza"}
                            for q in qids + different.get("quietanza_ids", [])
                        ),
                    ),
                    "dettaglio_url": "/situazione-fiscale/dilazioni-inps",
                }
            )

    by_installment = {
        (i.get("rate_plan_id"), i.get("installment_number")): i for i in installments
    }
    by_payment = {p["id"]: p for p in payments}
    for plan in plans:
        bad = bool(
            plan.get("requires_review")
            or any(value is False for value in (plan.get("quadratura") or {}).values())
        )
        if bad:
            warnings.append(
                {
                    "id": plan["id"],
                    "messaggio": f"AdeR {plan.get('plan_reference')}: riferimenti o quadratura da verificare",
                    "url": "/situazione-fiscale/ader",
                }
            )
        for rate in plan.get("installments") or []:
            record = by_installment.get((plan["id"], rate["number"]), {})
            payment = by_payment.get(record.get("payment_id"), {})
            amount = rate.get("amount_cents")
            paid = (
                cents(payment.get("operation_amount") or payment.get("amount"))
                if payment.get("documentary_evidence")
                else None
            )
            proven = (
                record.get("status") == "PAID_DOCUMENTED"
                and paid is not None
                and amount is not None
                and paid >= amount
            )
            rows.append(
                {
                    "id": record.get("id") or f"{plan['id']}:rata:{rate['number']}",
                    "data": data_iso(rate.get("due_date")),
                    "anno_competenza": anno,
                    "tipo": "ADER",
                    "source": "rata_ader",
                    "descrizione": f"AdeR {plan.get('plan_reference')} · rata {rate['number']}",
                    "importo_cents": amount,
                    "pagato_cents": paid,
                    "residuo_cents": (
                        0
                        if proven
                        else (
                            None
                            if bad or amount is None
                            else max(0, amount - (paid or 0))
                        )
                    ),
                    "pagata": proven,
                    "completata": proven,
                    "conteggiabile": not bad,
                    "monetaria": True,
                    "da_verificare": bad,
                    "stato_label": (
                        "Pagata (ricevuta)"
                        if proven
                        else (
                            "Piano da verificare"
                            if bad
                            else "Pagamento non riscontrato"
                        )
                    ),
                    "documenti": documenti(
                        {
                            "url": originale(
                                "documento_fiscale", plan.get("source_document_id")
                            ),
                            "titolo": "Piano AdeR",
                        },
                        {
                            "url": originale(
                                "documento_fiscale", payment.get("document_id")
                            ),
                            "titolo": "Ricevuta di pagamento",
                        },
                    ),
                    "dettaglio_url": "/situazione-fiscale/ader",
                }
            )

    # Il calendario aggiunge gli adempimenti (dichiarazioni, comunicazioni),
    # non un secondo debito per gli stessi tributi già nel Piano.
    from app.routers.fiscalita_italiana import _leggi_calendario_anno

    for year in (anno - 1, anno):
        for item in await _leggi_calendario_anno(db, year):
            if item.get("categoria") == "versamento":
                continue
            rows.append(
                {
                    "id": f"calendario:{year}:{item['id']}",
                    "data": data_iso(item.get("data")),
                    "anno_competenza": year,
                    "tipo": "ADEMPIMENTO",
                    "source": "calendario",
                    "descrizione": item.get("descrizione"),
                    "monetaria": False,
                    "conteggiabile": False,
                    "completata": bool(item.get("completato")),
                    "stato_label": (
                        "Completato nel calendario"
                        if item.get("completato")
                        else "Adempimento da verificare"
                    ),
                    "da_verificare": not item.get("completato"),
                    "note": item.get("note_completamento") or item.get("note"),
                    "documenti": documenti(
                        {
                            "url": originale("quietanza", item.get("quietanza_id")),
                            "titolo": "Quietanza",
                        }
                    ),
                    "dettaglio_url": "/contabilita/calendario",
                }
            )

    invoice_ids = {n["fattura_id"] for n in notifications if n.get("fattura_id")}
    valid_invoices = set()
    if invoice_ids:
        from app.constants.fattura_attiva import FILTRO_FATTURA_ATTIVA

        found = (
            await db["invoices"]
            .find(
                {"id": {"$in": sorted(invoice_ids)}, **FILTRO_FATTURA_ATTIVA},
                {"id": 1, "_id": 0},
            )
            .to_list(None)
        )
        valid_invoices = {i["id"] for i in found}
    for n in notifications:
        amount = (
            n.get("importo_cents")
            if n.get("importo_cents") is not None
            else cents(n.get("importo"))
        )
        rows.append(
            {
                **{
                    k: n.get(k)
                    for k in (
                        "id",
                        "tipo",
                        "descrizione",
                        "note",
                        "completata",
                        "priorita",
                        "dipendente_id",
                        "documento_id",
                        "fattura_id",
                    )
                },
                "tipo": n.get("tipo") or "CUSTOM",
                "source": "custom",
                "data": data_iso(n.get("data_scadenza")),
                "anno_competenza": (
                    int(str(n.get("data_scadenza", ""))[:4])
                    if str(n.get("data_scadenza", ""))[:4].isdigit()
                    else None
                ),
                "importo_cents": amount,
                "fattura_id": (
                    n.get("fattura_id")
                    if n.get("fattura_id") in valid_invoices
                    else None
                ),
                "residuo_cents": 0 if n.get("completata") else amount,
                "monetaria": amount is not None
                or n.get("tipo")
                in ("FATTURA", "IVA", "F24", "INPS", "INAIL", "IMU", "IRES", "IRAP"),
                "da_verificare": amount is not None and amount < 0,
                "conteggiabile": amount is not None and amount >= 0,
                "stato_label": (
                    "Completata" if n.get("completata") else "Promemoria aperto"
                ),
                "documenti": documenti(
                    {
                        "url": originale("documento", n.get("documento_id")),
                        "titolo": "Documento del promemoria",
                    }
                ),
                "dettaglio_url": (
                    f"/hr/dipendenti/anagrafica?dip={quote(str(n['dipendente_id']),safe='')}"
                    if n.get("dipendente_id")
                    else None
                ),
            }
        )

    # Fuori piano può presentare lo stesso obbligo in due anni: fonte/periodo
    # identificano la riga. Nessuna deduplicazione per solo importo o data.
    unique = {}
    for r in rows:
        if r.get("data"):
            if not r["data"].startswith(f"{anno}-"):
                continue
        elif r.get("anno_competenza") != anno:
            continue
        unique.setdefault(r["id"], r)
    result = list(unique.values())
    for row in result:
        due = data_iso(row.get("data"))
        days = (date.fromisoformat(due) - oggi).days if due else None
        closed = bool(row.get("pagata") or row.get("completata"))
        row.update(
            giorni_mancanti=days,
            urgente=not closed and days is not None and days <= 3,
            importo=(
                row.get("importo_cents") / 100
                if row.get("importo_cents") is not None
                else None
            ),
        )
        row["da_verificare"] = bool(row.get("da_verificare") or not due)
    result.sort(key=lambda r: (r.get("data") or "9999", str(r["id"])))
    pending_receipts = sum(
        not (
            r.get("verbale_id")
            or r.get("avvisi_collegati")
            or r.get("stato") == "associata"
        )
        for r in receipts
    )
    panels = [
        {
            "id": "ricevute",
            "titolo": "Ricevute da associare",
            "conteggio": pending_receipts,
            "url": "/riconciliazione/pagopa",
        },
        {
            "id": "cartelle",
            "titolo": "Cartelle da verificare",
            "conteggio": sum(
                r.get("expectation_status") == "DA_VERIFICARE" for r in claims
            ),
            "url": "/situazione-fiscale/ader",
        },
        {
            "id": "piani",
            "titolo": "Piani con segnalazioni",
            "conteggio": len(warnings),
            "url": "/situazione-fiscale/ader",
        },
    ]
    return {
        "righe": result,
        "segnalazioni": warnings,
        "documenti_da_verificare": panels,
        "documenti_periodo": "Archivio completo, tutti gli anni",
    }


def seleziona(
    proiezione, *, anno, oggi, mese=None, tipo=None, stato=None, include_chiuse=False
):
    rows = proiezione["righe"]
    if mese:
        rows = [r for r in rows if r.get("data") and int(r["data"][5:7]) == mese]
    if tipo:
        rows = (
            [r for r in rows if r.get("source") == "custom"]
            if tipo == "CUSTOM"
            else [r for r in rows if r.get("tipo") == tipo]
        )
    if stato == "da_verificare":
        rows = [r for r in rows if r.get("da_verificare")]
    elif stato == "scadute":
        rows = [
            r
            for r in rows
            if not (r.get("completata") or r.get("pagata"))
            and r.get("giorni_mancanti") is not None
            and r["giorni_mancanti"] < 0
        ]
    elif stato == "chiuse":
        rows = [r for r in rows if r.get("completata") or r.get("pagata")]
    elif stato == "aperte" or not include_chiuse:
        rows = [r for r in rows if not (r.get("completata") or r.get("pagata"))]
    open_rows = [r for r in rows if not (r.get("completata") or r.get("pagata"))]
    known = [
        r
        for r in open_rows
        if r.get("conteggiabile") and r.get("residuo_cents") is not None
    ]
    total = sum(max(0, r["residuo_cents"]) for r in known)
    return rows, {
        "urgenti": sum(bool(r.get("urgente")) for r in open_rows),
        "prossimi_7_giorni": sum(
            r.get("giorni_mancanti") is not None and 0 <= r["giorni_mancanti"] <= 7
            for r in open_rows
        ),
        "totale_importo_cents": total,
        "totale_importo": total / 100,
        "importi_non_disponibili": sum(
            r.get("monetaria") and r.get("residuo_cents") is None for r in open_rows
        ),
        "da_verificare": sum(bool(r.get("da_verificare")) for r in rows),
        "aperte": len(open_rows),
        "anno": anno,
    }
