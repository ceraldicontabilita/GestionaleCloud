"""Collegamento anticipato assegno -> fattura.

L'assegno compilato e' una scelta di pagamento della singola fattura e
prevale sul metodo predefinito del fornitore. Prima dell'estratto conto il
collegamento resta un impegno finanziario: non marca la fattura pagata e non
crea una riga bancaria fittizia. La sincronizzazione dell'estratto conto
chiude poi il ciclo e crea/conferma la Prima Nota Banca reale.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


TOLL = 0.005


def _f(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _norm_piva(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _norm_numero(value: Any) -> str:
    value = re.sub(r"\s+", "", str(value or "").upper())
    return re.sub(r"[^A-Z0-9]", "", value)


def _norm_nome(value: Any) -> str:
    value = re.sub(r"[^A-Z0-9 ]", " ", str(value or "").upper())
    parole = [
        p for p in value.split()
        if p not in {"SRL", "SPA", "SNC", "SAS", "SOCIETA", "UNIPERSONALE"}
    ]
    return " ".join(parole)


def _identita_fattura(invoice: Dict[str, Any]) -> Tuple[str, str, str, float]:
    return (
        _norm_piva(invoice.get("supplier_vat") or invoice.get("cedente_piva") or invoice.get("partita_iva")),
        _norm_nome(invoice.get("supplier_name") or invoice.get("cedente_denominazione")),
        _norm_numero(invoice.get("invoice_number") or invoice.get("numero_fattura")),
        round(_f(invoice.get("total_amount") or invoice.get("importo_totale")), 2),
    )


# FatturaPA: MP02 = assegno. E' l'unica prova documentale dello strumento.
MODALITA_ASSEGNO = {"MP02"}


def _modalita_dichiarate(fattura: Dict[str, Any]) -> set:
    """Modalita' FatturaPA dichiarate, da rate e da riepilogo.

    Il campo ``modalita_pagamento_xml`` e' una lista nelle fatture canoniche ma
    una stringa singola nell'indice del report Fatture ricevute: iterare alla
    cieca su una stringa produrrebbe i singoli caratteri e non troverebbe mai
    MP02.
    """
    grezzo = fattura.get("modalita_pagamento_xml")
    valori = [grezzo] if isinstance(grezzo, str) else list(grezzo or [])
    modalita = {str(valore or "").strip().upper() for valore in valori}
    modalita.update(
        str(rata.get("modalita") or "").strip().upper()
        for rata in (fattura.get("pagamento_rate") or [])
        if isinstance(rata, dict)
    )
    modalita.discard("")
    return modalita


def fattura_dichiara_assegno(fattura: Dict[str, Any]) -> bool:
    """Riconosce MP02 come strumento, senza confonderlo con la destinazione.

    ``metodo_pagamento`` e' la destinazione contabile predefinita del fornitore
    (cassa/banca/misto); la prova dello strumento assegno resta invece nei dati
    originali FatturaPA.
    """
    metodo = str(
        fattura.get("metodo_pagamento_previsto")
        or fattura.get("metodo_pagamento_effettivo")
        or ""
    ).lower()
    return bool(_modalita_dichiarate(fattura) & MODALITA_ASSEGNO) or "assegn" in metodo


def rate_assegno_dichiarate(fattura: Dict[str, Any]) -> List[float]:
    """Solo le rate MP02 realmente dichiarate nell'XML, senza fallback.

    Serve al matching: una fattura rateizzata non ha mai il residuo uguale al
    singolo assegno, ma la rata dichiarata si', ed e' una prova. Il fallback al
    totale non va usato qui, perche' su una fattura gia' pagata in parte
    porterebbe ad agganciare un assegno piu' grande del residuo.
    """
    rate = [
        round(_f(rata.get("importo")), 2)
        for rata in (fattura.get("pagamento_rate") or [])
        if isinstance(rata, dict)
        and str(rata.get("modalita") or "").strip().upper() in MODALITA_ASSEGNO
        and _f(rata.get("importo")) > 0
    ]
    return list(dict.fromkeys(rate))


def importi_assegno_dichiarati(fattura: Dict[str, Any]) -> List[float]:
    """Importi delle rate MP02, con fallback prudente al netto/totale."""
    rate = rate_assegno_dichiarate(fattura)
    if rate:
        return rate
    totale = round(_f(
        fattura.get("netto_pagare")
        or fattura.get("total_amount")
        or fattura.get("importo_totale")
        or fattura.get("totale_documento")
    ), 2)
    return [totale] if totale > 0 else []


def capienza_assegno_fattura(
    invoice: Dict[str, Any], assegno_id: Any, quota: Any,
) -> Tuple[bool, float, float]:
    """Impedisce che assegni distinti sovrappaghino la stessa fattura.

    ``importo_pagato`` puo gia includere le quote bancarie confermate: prima
    separiamo la parte pagata da fonti diverse dagli assegni, poi aggiungiamo
    gli impegni degli altri assegni, inclusi quelli in attesa dell'estratto.
    Il link dello stesso assegno e escluso per mantenere l'idempotenza.
    """
    totale = round(_f(invoice.get("total_amount") or invoice.get("importo_totale")), 2)
    quota = round(_f(quota), 2)
    if totale <= 0 or quota <= 0:
        return False, 0.0, totale

    links = [
        link for link in (invoice.get("assegni_collegati") or [])
        if isinstance(link, dict) and _f(link.get("quota")) > 0
    ]
    confermato_assegni = round(sum(
        _f(link.get("quota")) for link in links if link.get("banca_confermata")
    ), 2)
    pagato_non_assegni = round(max(
        0.0, _f(invoice.get("importo_pagato")) - confermato_assegni
    ), 2)
    quote_altri = round(sum(
        _f(link.get("quota")) for link in links
        if str(link.get("assegno_id") or "") != str(assegno_id or "")
    ), 2)
    impegnato = round(pagato_non_assegni + quote_altri, 2)
    return impegnato + quota <= totale + TOLL, impegnato, totale


def _score(assegno: Dict[str, Any], invoice: Dict[str, Any]) -> int:
    piva_i, nome_i, numero_i, importo_i = _identita_fattura(invoice)
    importo_a = round(_f(assegno.get("importo")), 2)
    if importo_a <= 0 or abs(importo_a - importo_i) > TOLL:
        return 0

    anno_i = str(
        invoice.get("anno") or invoice.get("invoice_date")
        or invoice.get("data_fattura") or ""
    )[:4]
    anno_a = str(
        assegno.get("anno") or assegno.get("data_emissione")
        or assegno.get("data") or ""
    )[:4]
    if anno_i.isdigit() and anno_a.isdigit() and anno_i != anno_a:
        return 0

    piva_a = _norm_piva(assegno.get("fornitore_piva"))
    nome_a = _norm_nome(
        assegno.get("fornitore_ragione_sociale") or assegno.get("beneficiario")
    )
    numero_a = _norm_numero(assegno.get("numero_fattura"))
    piva_ok = bool(piva_a and piva_i and piva_a == piva_i)
    nome_ok = bool(nome_a and nome_i and (nome_a == nome_i or nome_a in nome_i or nome_i in nome_a))
    numero_ok = bool(numero_a and numero_i and numero_a == numero_i)

    # L'importo da solo non basta mai. Numero fattura + importo al centesimo
    # e' una prova utilizzabile anche se il beneficiario non e' stato ancora
    # compilato: il chiamante collega solo quando la coppia individua un solo
    # assegno/fattura, altrimenti registra l'ambiguita'.
    if numero_ok and (piva_ok or nome_ok):
        return 100
    if piva_ok and nome_ok:
        return 90
    if numero_ok and piva_ok:
        return 95
    if numero_ok:
        return 80
    return 0


async def _collega(db, assegno: Dict[str, Any], invoice: Dict[str, Any], *, session=None) -> Dict[str, Any]:
    # L'estratto conto puo' essere stato importato prima dell'XML. In quel
    # caso il movimento bancario e' gia' prova ufficiale: il collegamento
    # tardivo deve chiudere la fattura e soprattutto non deve degradare
    # l'assegno da ``incassato`` a ``assegnato``.
    quota = round(_f(assegno.get("importo")), 2)
    disponibile, impegnato, totale = capienza_assegno_fattura(
        invoice, assegno.get("id"), quota,
    )
    if not disponibile:
        return {
            "collegato": False,
            "motivo": "fattura_gia_attribuita",
            "importo_fattura": totale,
            "importo_gia_impegnato": impegnato,
        }

    banca_gia_confermata = bool(
        assegno.get("incassato_confermato_banca")
        and (assegno.get("movimento_estratto_conto_id") or assegno.get("movimento_id"))
    )
    if banca_gia_confermata and session is None:
        from app.services.assegni_estratto_conto import (
            collega_assegno_riconciliato_a_fattura,
        )
        return await collega_assegno_riconciliato_a_fattura(
            db,
            assegno,
            invoice,
            match_auto=True,
            match_livello="INTENTO_ASSEGNO_XML_EC",
        )

    now = datetime.now(timezone.utc).isoformat()
    fid = str(invoice.get("id"))
    numero_fattura = invoice.get("invoice_number") or invoice.get("numero_fattura")
    piva = invoice.get("supplier_vat") or invoice.get("cedente_piva")
    nome = invoice.get("supplier_name") or invoice.get("cedente_denominazione")
    link = {
        "assegno_id": assegno.get("id"),
        "numero": assegno.get("numero"),
        "quota": quota,
        "data_collegamento": now,
        "match_auto": True,
        "match_livello": "INTENTO_ASSEGNO_XML",
        "banca_confermata": False,
    }

    await db["assegni"].update_one(
        {"id": assegno.get("id")},
        {"$set": {
            "fattura_collegata": fid,
            "fattura_id": fid,
            "fatture_collegate": [{
                "fattura_id": fid, "quota": quota, "data_collegamento": now,
                "match_auto": True, "match_livello": "INTENTO_ASSEGNO_XML",
            }],
            "numero_fattura": numero_fattura,
            "fornitore_piva": piva,
            "fornitore_ragione_sociale": nome,
            "beneficiario": assegno.get("beneficiario") or nome,
            "importo_assegnato": quota,
            "stato": "incassato" if banca_gia_confermata else "assegnato",
            "metodo_pagamento_previsto": "assegno",
            "stato_finanziario": (
                "riconciliato" if banca_gia_confermata else "in_attesa_estratto_conto"
            ),
            "pagamento_specifico_prevale_su_fornitore": True,
            "updated_at": now,
        }},
        session=session,
    )
    original_method = invoice.get("metodo_pagamento") or invoice.get("payment_method")
    invoice_update = {
        "metodo_pagamento_fornitore_originale": original_method,
        "metodo_pagamento": "assegno",
        "metodo_pagamento_previsto": "assegno",
        "metodo_pagamento_override_source": "assegno_compilato",
        "pagamento_specifico_prevale_su_fornitore": True,
        "stato_finanziario": "in_attesa_estratto_conto",
        "riconciliato": False,
        "riconciliato_con_ec": False,
        "pagato": False,
        "updated_at": now,
    }
    await db["invoices"].update_one(
        {"id": fid},
        {"$set": invoice_update, "$addToSet": {"assegni_collegati": link}},
        session=session,
    )
    invoice.update(invoice_update)
    invoice.setdefault("assegni_collegati", []).append(link)
    if banca_gia_confermata:
        # Il link preliminare impedisce l'instradamento Cassa/Banca generico
        # dentro la transazione. Il pagamento e le rate vengono completati
        # subito dopo il commit dal chiamante.
        return {
            "collegato": False,
            "completamento_banca_pendente": True,
            "assegno_id": assegno.get("id"),
            "fattura_id": fid,
        }
    return {"collegato": True, "assegno_id": assegno.get("id"), "fattura_id": fid}


async def _registra_ambigui(db, invoice: Dict[str, Any], assegni: List[Dict[str, Any]], *, session=None) -> None:
    now = datetime.now(timezone.utc).isoformat()
    for assegno in assegni:
        doc = {
            "id": f"INTENTO-{assegno.get('id')}-{invoice.get('id')}",
            "assegno_id": assegno.get("id"),
            "assegno_numero": assegno.get("numero"),
            "fattura_id": invoice.get("id"),
            "fattura_numero": invoice.get("invoice_number") or invoice.get("numero_fattura"),
            "fornitore": invoice.get("supplier_name") or invoice.get("cedente_denominazione"),
            "importo": round(_f(assegno.get("importo")), 2),
            "tipo_match": "intento_assegno_xml_ambiguo",
            "confidenza": 0.5,
            "stato": "da_confermare",
            "source": "assegno_compilato",
            "created_at": now,
        }
        await db["proposte_associazione_assegni"].update_one(
            {"id": doc["id"]}, {"$set": doc}, upsert=True, session=session
        )


async def collega_intento_assegno_a_fattura(db, invoice: Dict[str, Any], *, session=None) -> Dict[str, Any]:
    """Collega una fattura appena importata all'assegno anticipato univoco."""
    importo = round(_f(invoice.get("total_amount") or invoice.get("importo_totale")), 2)
    if importo <= 0:
        return {"collegato": False, "motivo": "importo_non_valido"}
    assegni = await db["assegni"].find({
        "importo": {"$gte": importo - TOLL, "$lte": importo + TOLL},
        "stato": {"$nin": ["annullato", "stornato"]},
        "entity_status": {"$ne": "deleted"},
        "$and": [
            {"$or": [
                {"fattura_collegata": {"$in": [None, ""]}},
                {"fattura_collegata": {"$exists": False}},
            ]},
            {"$or": [
                {"fatture_collegate": {"$in": [None, []]}},
                {"fatture_collegate": {"$exists": False}},
            ]},
        ],
    }, {"_id": 0}, session=session).to_list(500)
    scored = [(a, _score(a, invoice)) for a in assegni]
    scored = [(a, score) for a, score in scored if score > 0]
    if not scored:
        return {"collegato": False, "motivo": "nessun_intento_compatibile"}
    best = max(score for _, score in scored)
    migliori = [a for a, score in scored if score == best]
    if len(migliori) != 1:
        await _registra_ambigui(db, invoice, migliori, session=session)
        return {"collegato": False, "motivo": "ambiguo", "candidati": len(migliori)}
    return await _collega(db, migliori[0], invoice, session=session)


async def prepara_intento_assegno(db, assegno_id: str) -> Dict[str, Any]:
    """Memorizza l'intento quando l'utente compila un assegno.

    Se l'XML e' gia presente, collega subito la fattura; altrimenti il record
    assegno resta la fonte che verra' riscontrata al successivo import XML.
    """
    assegno = await db["assegni"].find_one({"id": assegno_id}, {"_id": 0})
    riferimento_presente = bool(
        assegno
        and (
            assegno.get("beneficiario")
            or assegno.get("fornitore_piva")
            or assegno.get("numero_fattura")
        )
    )
    if not assegno or _f(assegno.get("importo")) <= 0 or not riferimento_presente:
        return {"registrato": False}

    now = datetime.now(timezone.utc).isoformat()
    if not assegno.get("fornitore_piva"):
        nome_a = _norm_nome(assegno.get("beneficiario"))
        if nome_a:
            fornitori = await db["fornitori"].find({}, {
                "_id": 0, "partita_iva": 1, "piva": 1, "vat_number": 1,
                "ragione_sociale": 1, "denominazione": 1, "nome": 1,
            }).to_list(10000)
            identici = [f for f in fornitori if _norm_nome(
                f.get("ragione_sociale") or f.get("denominazione") or f.get("nome")
            ) == nome_a]
            if len(identici) == 1:
                assegno["fornitore_piva"] = (
                    identici[0].get("partita_iva") or identici[0].get("piva")
                    or identici[0].get("vat_number")
                )

    intent_fields = {
        "fornitore_piva": assegno.get("fornitore_piva"),
        "metodo_pagamento_previsto": "assegno",
        "stato_finanziario": "in_attesa_xml_o_estratto_conto",
        "pagamento_specifico_prevale_su_fornitore": True,
        "intento_pagamento_registrato_at": now,
        "updated_at": now,
    }
    await db["assegni"].update_one({"id": assegno_id}, {"$set": intent_fields})
    assegno.update(intent_fields)

    importo = round(_f(assegno.get("importo")), 2)
    invoices = await db["invoices"].find({
        "$or": [
            {"total_amount": {"$gte": importo - TOLL, "$lte": importo + TOLL}},
            {"importo_totale": {"$gte": importo - TOLL, "$lte": importo + TOLL}},
        ],
        "entity_status": {"$ne": "deleted"},
        "pagato": {"$ne": True},
    }, {"_id": 0}).to_list(500)
    compatibili = [(inv, _score(assegno, inv)) for inv in invoices]
    compatibili = [(inv, score) for inv, score in compatibili if score > 0]
    if compatibili:
        best = max(score for _, score in compatibili)
        migliori = [inv for inv, score in compatibili if score == best]
        if len(migliori) == 1:
            return {"registrato": True, **(await _collega(db, assegno, migliori[0]))}
        for invoice in migliori:
            await _registra_ambigui(db, invoice, [assegno])
        return {
            "registrato": True,
            "collegato": False,
            "motivo": "ambiguo",
            "candidati": len(migliori),
        }
    return {"registrato": True, "collegato": False, "motivo": "in_attesa_xml"}


async def riprocessa_intenti_assegni(
    db,
    *,
    anno: Optional[int] = None,
    limit: int = 10000,
) -> Dict[str, Any]:
    """Riesamina gli assegni compilati che non hanno ancora una fattura.

    E' il recupero idempotente per i casi in cui estratto conto, assegno e XML
    arrivano in un ordine diverso. Riusa deliberatamente
    :func:`prepara_intento_assegno`: importo da solo non basta, un pareggio non
    viene sciolto e una fattura gia' impegnata non puo' essere sovrapagata.
    """
    limit = max(1, min(int(limit or 10000), 50000))
    condizioni: List[Dict[str, Any]] = [
        {"importo": {"$gt": 0}},
        {"stato": {"$nin": ["annullato", "stornato", "vuoto"]}},
        {"entity_status": {"$ne": "deleted"}},
        {"$or": [
            {"fattura_collegata": {"$in": [None, ""]}},
            {"fattura_collegata": {"$exists": False}},
        ]},
        {"$or": [
            {"fatture_collegate": {"$in": [None, []]}},
            {"fatture_collegate": {"$exists": False}},
        ]},
        {"$or": [
            {"beneficiario": {"$nin": [None, "", "-", "N/A"]}},
            {"fornitore_piva": {"$nin": [None, ""]}},
            {"numero_fattura": {"$nin": [None, ""]}},
        ]},
    ]
    if anno:
        anno_s = str(int(anno))
        condizioni.append({"$or": [
            {"anno": int(anno)},
            {"data_emissione": {"$regex": f"^{anno_s}"}},
            {"data": {"$regex": f"^{anno_s}"}},
            {"data_incasso": {"$regex": f"^{anno_s}"}},
        ]})

    assegni = await db["assegni"].find(
        {"$and": condizioni},
        {"_id": 0, "id": 1, "numero": 1},
    ).limit(limit).to_list(limit)

    esito: Dict[str, Any] = {
        "analizzati": len(assegni),
        "collegati": 0,
        "in_attesa_fattura": 0,
        "ambigui": 0,
        "gia_attribuite": 0,
        "non_compatibili": 0,
        "errori": [],
        "dettagli": [],
    }
    for assegno in assegni:
        try:
            risultato = await prepara_intento_assegno(db, str(assegno["id"]))
        except Exception as exc:  # un record anomalo non blocca l'intero batch
            esito["errori"].append({
                "assegno_id": assegno.get("id"),
                "numero": assegno.get("numero"),
                "errore": str(exc),
            })
            continue

        motivo = risultato.get("motivo")
        if risultato.get("collegato") or risultato.get("riconciliato"):
            esito["collegati"] += 1
        elif motivo == "ambiguo":
            esito["ambigui"] += 1
        elif motivo == "fattura_gia_attribuita":
            esito["gia_attribuite"] += 1
        elif motivo == "in_attesa_xml":
            esito["in_attesa_fattura"] += 1
        else:
            esito["non_compatibili"] += 1

        if len(esito["dettagli"]) < 100:
            esito["dettagli"].append({
                "assegno_id": assegno.get("id"),
                "numero": assegno.get("numero"),
                "collegato": bool(
                    risultato.get("collegato") or risultato.get("riconciliato")
                ),
                "fattura_id": risultato.get("fattura_id"),
                "motivo": motivo,
            })

    esito["success"] = not esito["errori"]
    return esito
