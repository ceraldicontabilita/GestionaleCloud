"""
COLLAUDO AUTOMATICO — invarianti contabili (richiesta utente 18/07/2026:
"costruisci il collaudo automatico").

Regole che nel gestionale DEVONO essere sempre vere. Ogni violazione è un
difetto reale da mostrare, non un caso da sistemare in silenzio: il
collaudo NON corregge nulla, fotografa. Il report finisce in
`collaudo_report` e ogni check violato genera/aggiorna un alert
COLLAUDO_INVARIANTE (idempotente); un check tornato pulito risolve
l'alert. Gira ogni notte dallo scheduler e a richiesta da
POST /api/collaudo/esegui.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

COLL_REPORT = "collaudo_report"

_ATTIVO = {"status": {"$nin": ["deleted", "archived"]}}


def _es(riga: Dict[str, Any], campi: List[str]) -> Dict[str, Any]:
    return {k: riga.get(k) for k in campi if riga.get(k) is not None}


def _fattura_id_riga_banca(riga: Dict[str, Any]) -> str:
    return str(riga.get("invoice_id") or riga.get("fattura_id") or "").strip()


def _importo_assoluto(valore: Any) -> float:
    try:
        return round(abs(float(valore or 0)), 2)
    except (TypeError, ValueError):
        return 0.0


def gruppo_multi_fattura_valido(
    righe: List[Dict[str, Any]], movimento_ec: Dict[str, Any] | None,
) -> bool:
    """Riconosce una ripartizione reale di un unico bonifico su più fatture."""
    if not movimento_ec or len(righe) < 2:
        return False
    if movimento_ec.get("riconciliato") is not True:
        return False
    if movimento_ec.get("tipo_riconciliazione") != "fatture_multiple_causale":
        return False
    if any(r.get("source") != "ric_auto_multi_fattura_causale" for r in righe):
        return False
    fatture = [_fattura_id_riga_banca(r) for r in righe]
    if any(not fattura_id for fattura_id in fatture):
        return False
    if len(set(fatture)) != len(fatture):
        return False
    totale_quote = round(sum(_importo_assoluto(r.get("importo")) for r in righe), 2)
    totale_ec = _importo_assoluto(movimento_ec.get("importo"))
    return totale_ec > 0 and abs(totale_quote - totale_ec) <= 0.01


async def check_fatture_banca_senza_ec(db) -> Dict[str, Any]:
    """REGOLA UTENTE 18/07: una fattura risulta pagata per banca SOLO se
    riconciliata con un movimento reale (estratto conto / PayPal / carta)."""
    from app.services.prima_nota_integrity import CAMPI_EVIDENZA_BANCA

    esempi, count = [], 0
    projection = {
        "_id": 0, "id": 1, "fattura_id": 1, "invoice_id": 1,
        "data": 1, "importo": 1,
        "descrizione": 1, "source": 1,
        **{campo: 1 for campo in CAMPI_EVIDENZA_BANCA},
    }
    righe = await db["prima_nota_banca"].find(
        {**_ATTIVO, "tipo": "uscita", "$or": [
            {"fattura_id": {"$exists": True, "$nin": [None, ""]}},
            {"invoice_id": {"$exists": True, "$nin": [None, ""]}},
        ]},
        projection,
    ).to_list(5000)
    for r in righe:
        if any(r.get(campo) not in (None, "") for campo in CAMPI_EVIDENZA_BANCA):
            continue
        count += 1
        if len(esempi) < 5:
            esempi.append(_es(r, ["data", "importo", "descrizione", "source"]))
    return {"nome": "fatture_banca_senza_estratto_conto", "violazioni": count,
            "descrizione": "Pagamenti fattura in Prima Nota Banca senza movimento "
                           "di estratto conto collegato (regola 18/07: mai pagata "
                           "banca senza riscontro)", "esempi": esempi}


async def check_ec_dangling_e_duplicati(db) -> Dict[str, Any]:
    """Un addebito reale = una riga: ogni estratto_conto_id referenziato deve
    esistere e comparire in UNA sola riga banca attiva, salvo una ripartizione
    multi-fattura esplicita e quadrata al centesimo."""
    movimenti_ec = {
        m["id"]: m async for m in db["estratto_conto_movimenti"].find(
            {}, {"_id": 0, "id": 1, "importo": 1, "riconciliato": 1,
                 "tipo_riconciliazione": 1}
        ) if m.get("id")
    }
    visti: Dict[str, List[Dict[str, Any]]] = {}
    dangling, duplicati, esempi = 0, 0, []
    async for r in db["prima_nota_banca"].find(
            {**_ATTIVO, "estratto_conto_id": {"$exists": True, "$nin": [None, ""]}},
            {"_id": 0, "id": 1, "estratto_conto_id": 1, "data": 1,
             "importo": 1, "descrizione": 1, "source": 1,
             "invoice_id": 1, "fattura_id": 1}):
        eid = r["estratto_conto_id"]
        visti.setdefault(eid, []).append(r)
        if eid not in movimenti_ec:
            dangling += 1
            if len(esempi) < 5:
                esempi.append({**_es(r, ["data", "importo", "descrizione"]), "problema": "estratto_conto_id inesistente"})
    for eid, righe in visti.items():
        if len(righe) > 1 and not gruppo_multi_fattura_valido(righe, movimenti_ec.get(eid)):
            duplicati += len(righe) - 1
            if len(esempi) < 5:
                esempi.append({"estratto_conto_id": eid, "righe_attive": len(righe), "problema": "stesso addebito su più righe"})
    return {"nome": "banca_ec_dangling_o_duplicati", "violazioni": dangling + duplicati,
            "descrizione": "Righe banca collegate a movimenti EC inesistenti o "
                           "stesso addebito registrato più volte", "esempi": esempi}


async def check_pos_giornaliero(db) -> Dict[str, Any]:
    """Accrediti POS in estratto conto (per giorno di VENDITA dalla
    descrizione NUMIA) vs il riferimento operativo del giorno: la CHIUSURA
    MANUALE serale del terminale quando trascritta (regola utente
    18/07/2026: 'quello è il vero incasso POS'), altrimenti l'elettronico
    dei corrispettivi XML (confronto fiscale)."""
    from app.routers.pos_corrispettivi_check import _giorno_operazione_pos
    anno = datetime.now(timezone.utc).year
    xml: Dict[str, float] = {}
    async for c in db["corrispettivi"].find(
            {"data": {"$regex": f"^{anno}"}}, {"_id": 0, "data": 1, "pagato_elettronico": 1}):
        xml[c["data"]] = xml.get(c["data"], 0) + float(c.get("pagato_elettronico") or 0)
    chiusure: Dict[str, float] = {}
    async for c in db["chiusure_pos_manuali"].find(
            {"data": {"$regex": f"^{anno}"}}, {"_id": 0, "data": 1, "importo": 1, "totale": 1}):
        chiusure[c["data"]] = chiusure.get(c["data"], 0) + float(c.get("importo") or c.get("totale") or 0)
    for g in chiusure:
        if chiusure[g] > 0:
            xml[g] = chiusure[g]  # la chiusura manuale è il riferimento operativo
    ec: Dict[str, float] = {}
    async for m in db["estratto_conto_movimenti"].find(
            {"data": {"$regex": f"^{anno}"}, "tipo": {"$ne": "uscita"},
             "$or": [{"categoria": {"$regex": "Incasso tramite POS", "$options": "i"}},
                     {"descrizione_originale": {"$regex": "NUMIA|INC\\.POS|INCAS\\. TRAMITE", "$options": "i"}}]},
            {"_id": 0, "data": 1, "importo": 1, "descrizione_originale": 1, "descrizione": 1}):
        g = _giorno_operazione_pos(m.get("descrizione_originale") or m.get("descrizione") or "", m.get("data", ""))
        ec[g] = ec.get(g, 0) + abs(float(m.get("importo") or 0))
    oggi = datetime.now(timezone.utc).date().isoformat()
    limite = (datetime.now(timezone.utc) - timedelta(days=4)).date().isoformat()
    peggiori = []
    count = 0
    for g in sorted(set(xml) | set(ec)):
        if g >= limite or g > oggi:
            continue  # accrediti ancora in transito
        diff = abs(xml.get(g, 0) - ec.get(g, 0))
        if diff > max(xml.get(g, 0) * 0.02, 5):
            count += 1
            peggiori.append({"giorno": g, "xml": round(xml.get(g, 0), 2),
                             "banca": round(ec.get(g, 0), 2), "differenza": round(diff, 2)})
    peggiori.sort(key=lambda x: -x["differenza"])
    return {"nome": "pos_xml_vs_banca_giornaliero", "violazioni": count,
            "descrizione": "Giorni con scostamento tra elettronico XML e accrediti "
                           "POS in banca oltre il 2% (attribuiti al giorno di vendita)",
            "esempi": peggiori[:5]}


async def check_documenti_fuori_whitelist(db) -> Dict[str, Any]:
    """La lista mittenti è il vangelo: in archivio non deve esserci nulla da
    mittenti non in lista, né file tecnici PEC/SDI."""
    from app.services.email_full_download import CATEGORY_COLLECTIONS
    from app.services.email_document_downloader import FILE_TECNICI_PEC_RE, FILE_FATTURA_SDI_RE
    from app.services.mittenti import _addr
    trusted = set()
    async for m in db["mittenti_email"].find({"attivo": True}):
        a = _addr(m)
        if a:
            trusted.add(a.lower())
    count, esempi = 0, []
    for coll in sorted(set(CATEGORY_COLLECTIONS.values())) + ["documents_inbox"]:
        async for d in db[coll].find(
                {}, {"_id": 0, "email_from": 1, "from": 1, "mittente": 1, "sender": 1,
                     "filename": 1, "file_name": 1}):
            nome_file = (d.get("filename") or d.get("file_name") or "").strip()
            mitt = (d.get("email_from") or d.get("from") or d.get("mittente") or d.get("sender") or "").lower()
            tecnico = bool(nome_file) and bool(
                FILE_TECNICI_PEC_RE.search(nome_file) or FILE_FATTURA_SDI_RE.match(nome_file))
            fuori_lista = bool(mitt) and not any(s in mitt for s in trusted)
            if tecnico or fuori_lista:
                count += 1
                if len(esempi) < 5:
                    esempi.append({"collezione": coll, "file": nome_file[:50],
                                   "mittente": mitt[:50],
                                   "problema": "file tecnico SDI" if tecnico else "mittente fuori lista"})
    return {"nome": "documenti_fuori_whitelist", "violazioni": count,
            "descrizione": "Documenti in archivio da mittenti non in lista o file "
                           "tecnici PEC/SDI (da pulire con pulizia-non-attendibili)",
            "esempi": esempi}


async def check_badge_status(db) -> Dict[str, Any]:
    n = await db["documents_inbox"].count_documents(
        {"$or": [{"processed": True}, {"xml_processed": True}],
         "status": {"$in": ["nuovo", "da_processare"]}})
    return {"nome": "badge_status_incoerente", "violazioni": n,
            "descrizione": "Documenti processati che mostrano ancora badge NUOVO",
            "esempi": []}


async def check_ritenute_scadute(db) -> Dict[str, Any]:
    oggi = datetime.now(timezone.utc).date().isoformat()
    esempi, count = [], 0
    async for r in db["ritenute_acconto"].find(
            {"stato": {"$in": ["scaduta_da_versare", "pagata_in_ritardo_senza_ravvedimento"]}},
            {"_id": 0, "fornitore": 1, "importo": 1, "scadenza": 1, "stato": 1}):
        if (r.get("scadenza") or "9999") <= oggi:
            count += 1
            if len(esempi) < 5:
                esempi.append(r)
    return {"nome": "ritenute_scadute_o_senza_ravvedimento", "violazioni": count,
            "descrizione": "Ritenute d'acconto oltre la scadenza senza F24 pagato "
                           "(o pagate tardi senza ravvedimento)", "esempi": esempi}


async def check_fatture_duplicate(db) -> Dict[str, Any]:
    pipeline = [
        {"$match": {"status": {"$nin": ["deleted", "archived"]}, "total_amount": {"$gt": 0}}},
        {"$group": {"_id": {"p": "$supplier_vat", "n": "$invoice_number", "d": "$invoice_date"},
                    "count": {"$sum": 1}}},
        {"$match": {"count": {"$gt": 1}, "_id.n": {"$nin": [None, ""]}}},
    ]
    gruppi = await db["invoices"].aggregate(pipeline).to_list(200)
    esempi = [{"piva": g["_id"].get("p"), "numero": g["_id"].get("n"),
               "data": g["_id"].get("d"), "copie": g["count"]} for g in gruppi[:5]]
    return {"nome": "fatture_duplicate_attive", "violazioni": len(gruppi),
            "descrizione": "Stessa fattura (P.IVA+numero+data) presente più volte "
                           "tra le attive", "esempi": esempi}


async def check_prima_nota_link_rotti(db) -> Dict[str, Any]:
    """Fatture pagate senza alcuna riga attiva di Prima Nota.

    Copre tutti gli alias storici: pagato/paid/stato_pagamento e
    prima_nota_id/prima_nota_cassa_id/prima_nota_banca_id.
    """
    from app.services.prima_nota_integrity import (
        filtro_fatture_marcate_pagate,
        trova_movimento_prima_nota_attivo,
    )

    count, esempi = 0, []
    async for f in db["invoices"].find(
            filtro_fatture_marcate_pagate(),
            {"_id": 0, "id": 1, "invoice_key": 1,
             "invoice_number": 1, "supplier_name": 1,
             "prima_nota_id": 1, "prima_nota_tipo": 1,
             "prima_nota_cassa_id": 1, "prima_nota_banca_id": 1,
             "total_amount": 1}):
        if not await trova_movimento_prima_nota_attivo(db, f):
            count += 1
            if len(esempi) < 5:
                esempi.append(_es(f, ["invoice_number", "supplier_name", "total_amount"]))
    return {"nome": "fatture_pagate_con_movimento_cancellato", "violazioni": count,
            "descrizione": "Fatture marcate pagate il cui movimento di Prima Nota "
                           "è stato eliminato", "esempi": esempi}


async def check_salari_riconciliati_senza_banca(db) -> Dict[str, Any]:
    count, esempi = 0, []
    async for r in db["prima_nota_salari"].find(
            {"riconciliato": True,
             "movimenti_bancari_ids": {"$in": [None, []]},
             "movimento_bancario_id": {"$in": [None, ""]}},
            {"_id": 0, "dipendente": 1, "mese": 1, "anno": 1, "importo_busta": 1}):
        count += 1
        if len(esempi) < 5:
            esempi.append(r)
    return {"nome": "salari_riconciliati_senza_bonifico", "violazioni": count,
            "descrizione": "Righe stipendio riconciliate senza alcun movimento "
                           "bancario collegato", "esempi": esempi}


async def check_movimenti_malformati(db) -> Dict[str, Any]:
    count, esempi = 0, []
    for coll in ("prima_nota_cassa", "prima_nota_banca"):
        async for r in db[coll].find(
                {**_ATTIVO,
                 "$or": [{"importo": {"$lte": 0}}, {"importo": {"$in": [None, ""]}},
                         {"data": {"$in": [None, ""]}},
                         {"tipo": {"$nin": ["entrata", "uscita"]}}]},
                {"_id": 0, "id": 1, "data": 1, "importo": 1, "tipo": 1, "descrizione": 1}):
            count += 1
            if len(esempi) < 5:
                esempi.append({"collezione": coll, **_es(r, ["data", "importo", "tipo", "descrizione"])})
    return {"nome": "movimenti_prima_nota_malformati", "violazioni": count,
            "descrizione": "Movimenti attivi con importo non positivo, data vuota "
                           "o tipo non valido", "esempi": esempi}


async def check_trasferimento_pos_speculare(db) -> Dict[str, Any]:
    """REGOLA CANONICA POS (18/07/2026): per ogni giorno, l'uscita cassa
    'POS Verso Banca' e l'entrata banca 'trasferimento_pos' sono la STESSA
    operazione: stessi importi, mai una senza l'altra."""
    anno = datetime.now(timezone.utc).year
    cassa: Dict[str, float] = {}
    async for m in db["prima_nota_cassa"].find(
            {**_ATTIVO, "tipo": "uscita", "categoria": "POS Verso Banca",
             "data": {"$regex": f"^{anno}"}},
            {"_id": 0, "data": 1, "importo": 1}):
        cassa[m["data"]] = cassa.get(m["data"], 0) + float(m.get("importo") or 0)
    banca: Dict[str, float] = {}
    async for m in db["prima_nota_banca"].find(
            {**_ATTIVO, "tipo": "entrata",
             "source": {"$in": ["trasferimento_pos", "corrispettivo_pos"]},
             "data": {"$regex": f"^{anno}"}},
            {"_id": 0, "data": 1, "importo": 1}):
        banca[m["data"]] = banca.get(m["data"], 0) + float(m.get("importo") or 0)
    count, esempi = 0, []
    for g in sorted(set(cassa) | set(banca)):
        diff = abs(cassa.get(g, 0) - banca.get(g, 0))
        if diff > 0.01:
            count += 1
            if len(esempi) < 5:
                esempi.append({"giorno": g, "uscita_cassa": round(cassa.get(g, 0), 2),
                               "entrata_banca": round(banca.get(g, 0), 2)})
    return {"nome": "trasferimento_pos_speculare", "violazioni": count,
            "descrizione": "Giorni in cui uscita cassa POS ed entrata banca del "
                           "trasferimento non coincidono (regola canonica: stessa "
                           "operazione su due registri)", "esempi": esempi}


async def check_trascrizione_corrispettivo_manuale(db) -> Dict[str, Any]:
    """REGOLA CANONICA (integrazione utente 18/07/2026): l'XML è anche il
    controllo di TRASCRIZIONE del corrispettivo battuto a mano la sera —
    se il manuale differisce dall'XML la cassa risulta sbilanciata e non
    reale. Ogni giorno con totale_manuale ≠ totale XML è un'anomalia."""
    anno = datetime.now(timezone.utc).year
    count, esempi = 0, []
    async for c in db["corrispettivi"].find(
            {"data": {"$regex": f"^{anno}"},
             "totale_manuale": {"$exists": True, "$nin": [None, 0]}},
            {"_id": 0, "data": 1, "totale": 1, "totale_manuale": 1}):
        xml_tot = float(c.get("totale") or 0)
        man = float(c.get("totale_manuale") or 0)
        if xml_tot > 0 and abs(xml_tot - man) > 0.01:
            count += 1
            if len(esempi) < 5:
                esempi.append({"giorno": c.get("data"),
                               "manuale": round(man, 2), "xml": round(xml_tot, 2),
                               "differenza": round(man - xml_tot, 2)})
    return {"nome": "trascrizione_corrispettivo_manuale", "violazioni": count,
            "descrizione": "Corrispettivi serali battuti a mano che NON coincidono "
                           "con l'XML del registratore (anomalia di trascrizione: "
                           "cassa sbilanciata non reale)", "esempi": esempi}


async def check_assegni_integrita(db) -> Dict[str, Any]:
    """Assegni operativi sempre tracciabili fino a fattura ed estratto conto."""
    attivi = await db["assegni"].find(
        {"entity_status": {"$ne": "deleted"}},
        {"_id": 0, "id": 1, "numero": 1, "stato": 1, "importo": 1,
         "beneficiario": 1, "fattura_id": 1, "fattura_collegata": 1,
         "movimento_estratto_conto_id": 1, "incassato_confermato_banca": 1},
    ).to_list(20000)
    fatture_ids = {
        str(a.get("fattura_id") or a.get("fattura_collegata"))
        for a in attivi if a.get("fattura_id") or a.get("fattura_collegata")
    }
    ec_ids = {
        str(a.get("movimento_estratto_conto_id"))
        for a in attivi if a.get("movimento_estratto_conto_id")
    }
    fatture = await db["invoices"].find(
        {"id": {"$in": list(fatture_ids)}}, {"_id": 0, "id": 1}
    ).to_list(max(len(fatture_ids), 1))
    movimenti = await db["estratto_conto_movimenti"].find(
        {"id": {"$in": list(ec_ids)}}, {"_id": 0, "id": 1}
    ).to_list(max(len(ec_ids), 1))
    fatture_esistenti = {str(f.get("id")) for f in fatture}
    ec_esistenti = {str(m.get("id")) for m in movimenti}
    uso_ec: Dict[str, int] = {}
    problemi: List[Dict[str, Any]] = []

    def aggiungi(a, motivo):
        if len(problemi) < 5:
            problemi.append({"assegno_id": a.get("id"), "numero": a.get("numero"), "motivo": motivo})

    stati_operativi = {"compilato", "emesso", "assegnato", "parzialmente_assegnato", "incassato"}
    count = 0
    for a in attivi:
        stato = str(a.get("stato") or "").lower()
        importo = float(a.get("importo") or 0)
        beneficiario = str(a.get("beneficiario") or "").strip().lower()
        fid = a.get("fattura_id") or a.get("fattura_collegata")
        ec_id = a.get("movimento_estratto_conto_id")
        if stato in stati_operativi and importo > 0 and beneficiario in {"", "-", "n/a", "non disponibile"}:
            count += 1
            aggiungi(a, "beneficiario mancante")
        if fid and str(fid) not in fatture_esistenti:
            count += 1
            aggiungi(a, "fattura collegata inesistente")
        if stato == "incassato":
            if not ec_id or str(ec_id) not in ec_esistenti or a.get("incassato_confermato_banca") is not True:
                count += 1
                aggiungi(a, "incassato senza riscontro valido in estratto conto")
            if not fid:
                count += 1
                aggiungi(a, "incassato senza fattura collegata")
        if ec_id:
            uso_ec[str(ec_id)] = uso_ec.get(str(ec_id), 0) + 1

    duplicati_ec = sum(n - 1 for n in uso_ec.values() if n > 1)
    count += duplicati_ec
    if duplicati_ec and len(problemi) < 5:
        problemi.append({"motivo": "movimento estratto conto usato da piu assegni", "duplicati": duplicati_ec})
    return {
        "nome": "assegni_fatture_estratto_conto_integrita",
        "violazioni": count,
        "descrizione": "Assegni operativi senza beneficiario/fattura/prova bancaria o con movimento EC riutilizzato",
        "esempi": problemi,
    }


async def check_liquidazioni_iva_integrita(db) -> Dict[str, Any]:
    """Ricalcola i vincoli persistiti delle liquidazioni IVA confermate."""
    docs = await db["liquidazioni_iva"].find({}, {"_id": 0}).sort(
        [("periodo", 1), ("versione", 1)]
    ).to_list(5000)
    count = 0
    esempi: List[Dict[str, Any]] = []

    def problema(doc, motivo):
        nonlocal count
        count += 1
        if len(esempi) < 5:
            esempi.append({"liquidazione_id": doc.get("id"), "periodo": doc.get("periodo"), "motivo": motivo})

    coppie: Dict[tuple, int] = {}
    confermate_periodo: Dict[str, List[Dict[str, Any]]] = {}
    for doc in docs:
        key = (doc.get("periodo"), doc.get("versione"))
        coppie[key] = coppie.get(key, 0) + 1
        if doc.get("stato") in {"CONFERMATA", "TRASMESSA"}:
            confermate_periodo.setdefault(str(doc.get("periodo")), []).append(doc)
    for key, n in coppie.items():
        if n > 1:
            problema({"periodo": key[0], "id": None}, f"versione {key[1]} duplicata ({n} record)")
    for periodo, gruppi in confermate_periodo.items():
        if len(gruppi) > 1:
            problema(gruppi[-1], f"{len(gruppi)} liquidazioni confermate nello stesso periodo")

    for doc in [d for d in docs if d.get("stato") in {"CONFERMATA", "TRASMESSA"}]:
        atteso = round(float(doc.get("iva_vendite") or 0) - float(doc.get("iva_acquisti") or 0)
                       - float(doc.get("credito_precedente") or 0), 2)
        if abs(atteso - float(doc.get("saldo") or 0)) > 0.01:
            problema(doc, "formula saldo IVA incoerente")
        debito = max(atteso, 0)
        credito = max(-atteso, 0)
        if abs(debito - float(doc.get("debito_periodo") or 0)) > 0.01 or abs(credito - float(doc.get("credito_periodo") or 0)) > 0.01:
            problema(doc, "credito/debito periodo incoerente con il saldo")

        incluse = [f for f in doc.get("fatture_incluse", []) if f.get("id")]
        ids = [f["id"] for f in incluse]
        invs = await db["invoices"].find(
            {"id": {"$in": ids}},
            {"_id": 0, "id": 1, "iva_utilizzata": 1, "liquidazione_id": 1,
             "periodo_iva_utilizzato": 1, "importo_iva_utilizzato": 1},
        ).to_list(max(len(ids), 1))
        per_id = {f.get("id"): f for f in invs}
        valide = [
            per_id.get(fid) for fid in ids
            if per_id.get(fid)
            and per_id[fid].get("iva_utilizzata") is True
            and per_id[fid].get("liquidazione_id") == doc.get("id")
            and per_id[fid].get("periodo_iva_utilizzato") == doc.get("periodo")
        ]
        if len(valide) != len(ids):
            problema(doc, "fatture incluse non interamente marcate nella liquidazione")
        iva_marcata = round(sum(float(f.get("importo_iva_utilizzato") or 0) for f in valide), 2)
        if abs(iva_marcata - float(doc.get("iva_acquisti") or 0)) > 0.01:
            problema(doc, "IVA acquisti diversa dalla somma marcata sulle fatture")

    return {
        "nome": "liquidazioni_iva_integrita",
        "violazioni": count,
        "descrizione": "Formula, versioni, credito/debito e fatture marcate delle liquidazioni IVA",
        "esempi": esempi,
    }


async def check_fatture_iva_classificazione(db) -> Dict[str, Any]:
    """Segnala IVA acquisti non classificata o numericamente impossibile.

    L'IVA esposta in fattura non e' automaticamente detraibile. I documenti
    ancora ``DA_VERIFICARE`` restano fuori dalle liquidazioni, ma devono
    comparire nel collaudo notturno finche' non sono stati valutati. Sono
    inoltre violazioni i valori detraibili negativi o superiori all'IVA del
    documento e gli stati operativi privi di un importo esplicito.
    """
    docs = await db["invoices"].find(
        {"status": {"$nin": ["deleted", "archived"]}},
        {
            "_id": 0, "id": 1, "invoice_number": 1, "supplier_name": 1,
            "iva": 1, "total_iva": 1, "iva_totale": 1, "iva_documento": 1,
            "iva_detraibile": 1, "stato_detrazione_iva": 1,
        },
    ).to_list(50000)
    count = 0
    esempi: List[Dict[str, Any]] = []
    stati_operativi = {"DA_INSERIRE", "RINVIATA", "INSERITA_IN_LIQUIDAZIONE"}

    def valore(doc, *nomi):
        for nome in nomi:
            if doc.get(nome) is not None:
                try:
                    return round(float(doc[nome]), 2)
                except (TypeError, ValueError):
                    return None
        return 0.0

    def problema(doc, motivo):
        nonlocal count
        count += 1
        if len(esempi) < 5:
            esempi.append({
                "fattura_id": doc.get("id"),
                "numero": doc.get("invoice_number"),
                "fornitore": doc.get("supplier_name"),
                "motivo": motivo,
            })

    for doc in docs:
        iva_documento = valore(doc, "iva_documento", "iva", "total_iva", "iva_totale")
        iva_detraibile = valore(doc, "iva_detraibile")
        stato = str(doc.get("stato_detrazione_iva") or "").upper()
        if iva_documento is None or iva_detraibile is None:
            problema(doc, "importo IVA non numerico")
            continue
        if iva_detraibile < 0:
            problema(doc, "IVA detraibile negativa")
        elif iva_documento >= 0 and iva_detraibile > iva_documento + 0.01:
            problema(doc, "IVA detraibile superiore all'IVA del documento")
        if iva_documento > 0 and stato == "DA_VERIFICARE":
            problema(doc, "detraibilita IVA ancora da verificare")
        elif stato in stati_operativi and "iva_detraibile" not in doc:
            problema(doc, "stato operativo senza IVA detraibile esplicita")

    return {
        "nome": "fatture_iva_classificazione",
        "violazioni": count,
        "descrizione": "Fatture con detraibilita IVA irrisolta o importi IVA incoerenti",
        "esempi": esempi,
    }


async def check_f24_pagati_senza_banca(db) -> Dict[str, Any]:
    """F24 dichiarati pagati ma privi di riferimento+data dell'addebito."""
    from app.services.f24_payment_evidence import ha_evidenza_bancaria

    docs = await db["f24_unificato"].find(
        {"$or": [
            {"status": {"$in": ["paid", "pagato"]}},
            {"stato_pagamento": "PAGATO"},
            {"pagato": True},
        ]},
        {"_id": 0, "pdf_data": 0},
    ).to_list(50000)
    incoerenti = [doc for doc in docs if not ha_evidenza_bancaria(doc)]
    return {
        "nome": "f24_pagati_senza_prova_bancaria",
        "violazioni": len(incoerenti),
        "descrizione": "F24 marcati pagati senza movimento bancario identificato e datato",
        "esempi": [
            {
                "f24_id": d.get("id"),
                "file": d.get("file_name") or d.get("filename"),
                "status": d.get("status"),
                "stato_pagamento": d.get("stato_pagamento"),
                "quietanza_id": d.get("quietanza_id"),
            }
            for d in incoerenti[:5]
        ],
    }


CHECKS = [
    check_fatture_banca_senza_ec,
    check_trasferimento_pos_speculare,
    check_trascrizione_corrispettivo_manuale,
    check_ec_dangling_e_duplicati,
    check_pos_giornaliero,
    check_documenti_fuori_whitelist,
    check_badge_status,
    check_ritenute_scadute,
    check_fatture_duplicate,
    check_prima_nota_link_rotti,
    check_salari_riconciliati_senza_banca,
    check_movimenti_malformati,
    check_assegni_integrita,
    check_fatture_iva_classificazione,
    check_liquidazioni_iva_integrita,
    check_f24_pagati_senza_banca,
]


async def esegui_collaudo(db, genera_alerts: bool = True) -> Dict[str, Any]:
    """Esegue tutti i check (sola lettura) e salva il report."""
    from app.services.alert_engine import genera_alert, risolvi_alert

    inizio = datetime.now(timezone.utc)
    risultati: List[Dict[str, Any]] = []
    for check in CHECKS:
        try:
            risultati.append(await check(db))
        except Exception as e:
            logger.exception(f"Collaudo: check {check.__name__} fallito")
            risultati.append({"nome": check.__name__, "violazioni": -1,
                             "descrizione": f"CHECK IN ERRORE: {e}", "esempi": []})

    totale_violazioni = sum(r["violazioni"] for r in risultati if r["violazioni"] > 0)
    report = {
        "id": inizio.strftime("collaudo-%Y%m%d-%H%M%S"),
        "eseguito_at": inizio.isoformat(),
        "durata_ms": int((datetime.now(timezone.utc) - inizio).total_seconds() * 1000),
        "checks": risultati,
        "checks_totali": len(risultati),
        "checks_violati": sum(1 for r in risultati if r["violazioni"] > 0),
        "checks_in_errore": sum(1 for r in risultati if r["violazioni"] < 0),
        "violazioni_totali": totale_violazioni,
    }
    await db[COLL_REPORT].insert_one(dict(report))

    if genera_alerts:
        for r in risultati:
            try:
                if r["violazioni"] > 0:
                    await genera_alert(
                        "COLLAUDO_INVARIANTE", r["nome"], COLL_REPORT,
                        f"{r['descrizione']}: {r['violazioni']} violazioni", db,
                        extra={"check": r["nome"], "violazioni": r["violazioni"],
                               "esempi": r["esempi"]})
                else:
                    # check tornato pulito: chiudi l'eventuale alert aperto
                    await risolvi_alert("COLLAUDO_INVARIANTE", r["nome"], db,
                                        resolved_by="collaudo")
            except Exception:
                logger.exception(f"Collaudo: alert per {r['nome']} non gestito")

    return report
