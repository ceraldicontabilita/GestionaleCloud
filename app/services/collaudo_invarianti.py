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


async def check_fatture_banca_senza_ec(db) -> Dict[str, Any]:
    """REGOLA UTENTE 18/07: una fattura risulta pagata per banca SOLO se
    riconciliata con un movimento reale (estratto conto / PayPal / carta)."""
    esempi, count = [], 0
    righe = await db["prima_nota_banca"].find(
        {**_ATTIVO, "tipo": "uscita",
         "fattura_id": {"$exists": True, "$nin": [None, ""]},
         "$and": [{"$or": [{"estratto_conto_id": None},
                           {"estratto_conto_id": {"$exists": False}},
                           {"estratto_conto_id": ""}]}]},
        {"_id": 0, "id": 1, "fattura_id": 1, "data": 1, "importo": 1,
         "descrizione": 1, "source": 1, "riconciliato": 1},
    ).to_list(5000)
    for r in righe:
        if r.get("riconciliato"):
            continue  # riconciliata con PayPal/carta da altro flusso
        count += 1
        if len(esempi) < 5:
            esempi.append(_es(r, ["data", "importo", "descrizione", "source"]))
    return {"nome": "fatture_banca_senza_estratto_conto", "violazioni": count,
            "descrizione": "Pagamenti fattura in Prima Nota Banca senza movimento "
                           "di estratto conto collegato (regola 18/07: mai pagata "
                           "banca senza riscontro)", "esempi": esempi}


async def check_ec_dangling_e_duplicati(db) -> Dict[str, Any]:
    """Un addebito reale = una riga: ogni estratto_conto_id referenziato deve
    esistere e comparire in UNA sola riga banca attiva."""
    ec_ids = {m["id"] async for m in db["estratto_conto_movimenti"].find({}, {"_id": 0, "id": 1})}
    visti: Dict[str, int] = {}
    dangling, duplicati, esempi = 0, 0, []
    async for r in db["prima_nota_banca"].find(
            {**_ATTIVO, "estratto_conto_id": {"$exists": True, "$nin": [None, ""]}},
            {"_id": 0, "id": 1, "estratto_conto_id": 1, "data": 1, "importo": 1, "descrizione": 1}):
        eid = r["estratto_conto_id"]
        visti[eid] = visti.get(eid, 0) + 1
        if eid not in ec_ids:
            dangling += 1
            if len(esempi) < 5:
                esempi.append({**_es(r, ["data", "importo", "descrizione"]), "problema": "estratto_conto_id inesistente"})
    for eid, n in visti.items():
        if n > 1:
            duplicati += n - 1
            if len(esempi) < 5:
                esempi.append({"estratto_conto_id": eid, "righe_attive": n, "problema": "stesso addebito su più righe"})
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
    """Fatture il cui prima_nota_id punta a una riga soft-deletata: risultano
    pagate ma il movimento non esiste più."""
    count, esempi = 0, []
    async for f in db["invoices"].find(
            {"pagato": True, "prima_nota_id": {"$exists": True, "$nin": [None, ""]},
             "status": {"$nin": ["deleted", "archived"]}},
            {"_id": 0, "id": 1, "invoice_number": 1, "supplier_name": 1,
             "prima_nota_id": 1, "prima_nota_tipo": 1, "total_amount": 1}):
        pn_id = f["prima_nota_id"]
        viva = False
        for coll in ("prima_nota_banca", "prima_nota_cassa"):
            r = await db[coll].find_one({"id": pn_id, **_ATTIVO}, {"_id": 0, "id": 1})
            if r:
                viva = True
                break
        if not viva:
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
