"""
MOTORE UNICO DI SCRITTURA CONTABILE — Fase A (decisione utente 18/07/2026:
"subito, per gradi").

Ogni movimento di Prima Nota deve nascere da qui: un solo punto che valida
e scrive, così le regole del modello non possono divergere tra i flussi.
La migrazione è graduale: i writer storici vengono portati qui uno alla
volta (primo: corrispettivi/POS) e un test-guardia vieta di aggiungerne
di nuovi altrove.

REGOLA CANONICA POS (utente, 18/07/2026 — confermata a voce e definitiva):
- CASSA entrata  = totale corrispettivo del giorno (contanti + POS, da XML);
- CASSA uscita "POS Verso Banca" = il POS REALE della CHIUSURA MANUALE
  serale del terminale ("quello che esce dal terminale è il vero incasso
  POS"); fallback: elettronico XML solo se la chiusura non è trascritta;
- BANCA entrata  = la STESSA cifra, come puro TRASFERIMENTO cassa→banca
  (contropartita speculare, stessa operazione su due registri, source
  "trasferimento_pos"). MAI una seconda registrazione indipendente.
- L'ACCREDITO dell'estratto conto NON crea mai un'entrata: RICONCILIA il
  trasferimento del suo giorno di vendita (causale NUMIA "DEL gg/mm/aa").
- L'elettronico XML resta il confronto FISCALE: la differenza col POS
  reale è il "NON BATTUTO" (battuto in meno sul registratore), esposto
  con saldo progressivo in Coerenza POS per recuperarlo nei giorni dopo.
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.services import conti_pos

logger = logging.getLogger(__name__)

REGISTRI = {"cassa": "prima_nota_cassa", "banca": "prima_nota_banca"}

# Marca le righe che sono CREDITI verso un gestore di incassi e non denaro
# gia' sul conto. Serve a tenerle fuori dai saldi bancari reali senza doverle
# riconoscere dal codice di conto, che puo' cambiare.
NATURA_CREDITO_POS = "credito_pos"


class ScritturaNonValida(ValueError):
    pass


def _valida(mov: Dict[str, Any]) -> None:
    data = str(mov.get("data") or "")
    if len(data) < 10 or data[4] != "-":
        raise ScritturaNonValida(f"data non valida: {data!r}")
    if float(mov.get("importo") or 0) <= 0:
        raise ScritturaNonValida(f"importo non positivo: {mov.get('importo')!r}")
    if mov.get("tipo") not in ("entrata", "uscita"):
        raise ScritturaNonValida(f"tipo non valido: {mov.get('tipo')!r}")
    if not mov.get("categoria"):
        raise ScritturaNonValida("categoria mancante")
    if not mov.get("source"):
        raise ScritturaNonValida("source mancante (tracciabilità obbligatoria)")


def _prepara_documento(mov: Dict[str, Any]) -> Dict[str, Any]:
    """Valida un movimento e riempie i campi con default stabili (id,
    alias amount/date/type/category/description, created_at). Estratta da
    scrivi_movimento per essere riusabile anche da chi deve scrivere con
    un upsert atomico invece di un insert diretto (vedi registra_corrispettivo)."""
    _valida(mov)
    doc = dict(mov)
    doc.setdefault("id", str(uuid.uuid4()))
    doc["importo"] = round(float(doc["importo"]), 2)
    doc.setdefault("amount", doc["importo"])
    doc.setdefault("date", doc["data"])
    doc.setdefault("type", doc["tipo"])
    doc.setdefault("category", doc["categoria"])
    doc.setdefault("description", doc.get("descrizione", ""))
    doc.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    return doc


async def scrivi_movimento(db, registro: str, mov: Dict[str, Any]) -> str:
    """Unico punto di INSERT nei registri di Prima Nota: valida e scrive.
    Ritorna l'id del movimento creato."""
    if registro not in REGISTRI:
        raise ScritturaNonValida(f"registro sconosciuto: {registro}")
    doc = _prepara_documento(mov)
    await db[REGISTRI[registro]].insert_one(dict(doc))
    return doc["id"]


async def _scrivi_se_assente(db, registro: str, query_esistente: Dict[str, Any],
                              mov: Dict[str, Any]) -> tuple:
    """Come scrivi_movimento, ma con la guardia di idempotenza (query_esistente)
    applicata in UNA SOLA operazione atomica verso MongoDB (find_one_and_update
    con upsert=True), non in due chiamate separate (find_one poi insert_one).

    Prima di questa funzione, registra_corrispettivo faceva le due chiamate
    separatamente: due richieste concorrenti per lo stesso corrispettivo
    potevano superare entrambe il controllo "esiste già?" prima che una delle
    due avesse scritto, creando un movimento duplicato in Prima Nota Cassa
    (vietato dalla regola canonica POS). L'upsert atomico chiede al database
    stesso di fare "controlla e scrivi" come un'unica azione indivisibile.

    Ritorna (id_movimento, era_gia_esistente).
    """
    if registro not in REGISTRI:
        raise ScritturaNonValida(f"registro sconosciuto: {registro}")
    doc = _prepara_documento(mov)
    precedente = await db[REGISTRI[registro]].find_one_and_update(
        query_esistente,
        {"$setOnInsert": doc},
        upsert=True,
    )
    if precedente:
        return precedente.get("id"), True
    return doc["id"], False


async def _leggi_tutti(cursor, n: int = 100):
    """Compat: cursori Motor reali (async for) e fake dei test (to_list)."""
    if hasattr(cursor, "to_list"):
        return await cursor.to_list(n)
    return [c async for c in cursor]


GESTORE_POS_DEFAULT = "nexi"


def normalizza_gestore_pos(valore: Any) -> str:
    """Normalizza il gestore POS. Le righe storiche senza campo sono Nexi."""
    return str(valore or "").strip().lower() or GESTORE_POS_DEFAULT


def filtro_gestore_pos(gestore: str) -> Dict[str, Any]:
    """Filtro Mongo per gestore.

    Le chiusure gia' registrate non hanno il campo ``gestore``: appartengono
    tutte a Nexi, unico terminale fino ad ora. Vanno quindi intercettate dal
    filtro del gestore predefinito, altrimenti un secondo inserimento
    creerebbe una riga parallela e raddoppierebbe il POS del giorno.
    """
    gestore = normalizza_gestore_pos(gestore)
    if gestore == GESTORE_POS_DEFAULT:
        return {"$or": [
            {"gestore": gestore},
            {"gestore": {"$in": [None, ""]}},
            {"gestore": {"$exists": False}},
        ]}
    return {"gestore": gestore}


async def chiusura_pos_del_giorno(db, data: str) -> Optional[float]:
    """POS reale del giorno: somma dei terminali (Nexi, SumUp, ...).

    Con piu' gestori il totale e' la somma dei loro totali. L'inserimento
    manuale prevale sui componenti storici *dello stesso gestore*, mai su
    quelli degli altri: diversamente una correzione su un terminale
    cancellerebbe l'incasso dell'altro.
    """
    tot = 0.0
    trovata = False
    try:
        righe = await _leggi_tutti(db["chiusure_pos_manuali"].find(
            {"data": data},
            {"_id": 0, "importo": 1, "totale": 1, "source": 1, "gestore": 1},
        ))
        per_gestore: Dict[str, List[Dict[str, Any]]] = {}
        for riga in righe:
            per_gestore.setdefault(
                normalizza_gestore_pos(riga.get("gestore")), []
            ).append(riga)
        for componenti in per_gestore.values():
            trovata = True
            # Un inserimento/correzione dalla UI e' un totale giornaliero e
            # prevale sugli eventuali componenti storici importati da CSV.
            override = next((c for c in reversed(componenti)
                             if c.get("source") == "inserimento_manuale_terminale"), None)
            if override is not None:
                valore = override.get("importo")
                tot += float(valore if valore is not None
                             else override.get("totale") or 0)
                continue
            for c in componenti:
                tot += float(c.get("importo") or c.get("totale") or 0)
        if not trovata:
            # fallback storico: chiusure importate in prima_nota_banca con
            # source import_manuale_pos (vecchio flusso pos.xlsx)
            for c in await _leggi_tutti(db["prima_nota_banca"].find(
                    {"data": data, "source": "import_manuale_pos"},
                    {"_id": 0, "importo": 1})):
                trovata = True
                tot += float(c.get("importo") or 0)
    except AttributeError:
        return None  # backend/fake senza le collezioni delle chiusure
    # Zero e' un valore manuale valido: significa che il terminale non ha
    # registrato pagamenti elettronici. Non deve far scattare il fallback al
    # valore XML, altrimenti Prima Nota tornerebbe a usare proprio il dato
    # fiscale che l'operatore ha corretto.
    return round(tot, 2) if trovata else None


async def registra_chiusura_pos_reale(
    db,
    data: str,
    importo: float,
    *,
    gestore: str = GESTORE_POS_DEFAULT,
    note: str = "",
    actor: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Salva il POS reale letto dal terminale e riallinea Prima Nota.

    Il dato manuale e' la fonte operativa canonica. L'elettronico XML resta
    invariato sul corrispettivo e viene usato soltanto per il confronto
    fiscale. In un'unica operazione logica vengono mantenuti coerenti:

    - ``chiusure_pos_manuali``: verita' manuale del terminale;
    - uscita ``POS Verso Banca`` in Prima Nota Cassa;
    - trasferimento atteso speculare in Prima Nota Banca, che verra'
      riconciliato dall'estratto conto reale.

    L'importo zero e' esplicito: archivia gli eventuali trasferimenti
    sintetici del giorno e impedisce il fallback al valore XML.

    Con piu' circuiti (Nexi/Numia, SumUp, ...) ``importo`` e' la chiusura del
    singolo ``gestore`` e ogni circuito ha la SUA coppia uscita-cassa /
    entrata-banca, con un ``trasferimento_id`` proprio: gli accrediti arrivano
    separati (NUMIA sul conto BPM, payout sul conto SumUp) e una riga unica
    col totale non sarebbe riconciliabile con nessuno dei due.

    Restano invece sul TOTALE del giorno, perche' descrivono la giornata e non
    il singolo terminale, il riparto contanti/elettronico dell'entrata Cassa e
    ``corrispettivi.pos_reale_serale``. L'entrata Cassa resta una sola, quella
    del corrispettivo XML: nessun circuito genera un secondo ricavo.
    """
    data = str(data or "")[:10]
    try:
        datetime.strptime(data, "%Y-%m-%d")
    except (TypeError, ValueError):
        raise ScritturaNonValida(f"data non valida: {data!r}")
    try:
        importo = round(float(importo), 2)
    except (TypeError, ValueError):
        raise ScritturaNonValida(f"importo non numerico: {importo!r}")
    if importo < 0:
        raise ScritturaNonValida("l'importo POS reale non puo' essere negativo")

    actor = actor or {}
    now = datetime.now(timezone.utc).isoformat()
    user_id = actor.get("sub") or actor.get("user_id") or "unknown"
    user_email = actor.get("email") or ""
    user_name = actor.get("name") or user_email or user_id

    gestore = normalizza_gestore_pos(gestore)
    # Solo le righe di QUESTO terminale: senza il filtro, registrare SumUp
    # sovrascriverebbe la chiusura Nexi dello stesso giorno.
    filtro_chiusura = {"data": data, **filtro_gestore_pos(gestore)}
    precedente_doc = await db["chiusure_pos_manuali"].find_one(
        filtro_chiusura, {"_id": 0, "importo": 1, "totale": 1, "id": 1}
    )
    importo_precedente = None
    if precedente_doc is not None:
        importo_precedente = round(float(
            precedente_doc.get("importo")
            if precedente_doc.get("importo") is not None
            else precedente_doc.get("totale") or 0
        ), 2)

    chiusura_id = (precedente_doc or {}).get("id") or str(uuid.uuid4())
    campi_chiusura = {
        "importo": importo,
        "totale": importo,
        "gestore": gestore,
        "source": "inserimento_manuale_terminale",
        "note": note,
        "updated_at": now,
        "updated_by": user_id,
    }
    # Niente upsert con ``$or``: Mongo non sa dedurre il documento da creare
    # da un filtro alternativo. Il ramo viene deciso qui, esplicitamente.
    if precedente_doc is not None:
        await db["chiusure_pos_manuali"].update_one(
            {"id": chiusura_id}, {"$set": campi_chiusura}
        )
    else:
        await db["chiusure_pos_manuali"].insert_one({
            **campi_chiusura,
            "id": chiusura_id,
            "data": data,
            "created_at": now,
        })

    # Prima Nota vede una sola uscita POS al giorno: il totale dei terminali.
    totale_giorno = await chiusura_pos_del_giorno(db, data)
    if totale_giorno is None:
        totale_giorno = importo

    corr = await db["corrispettivi"].find_one(
        {"data": data}, {"_id": 0, "id": 1, "totale": 1,
                         "pagato_elettronico": 1}
    )
    corr_id = (corr or {}).get("id")
    # Non sovrascrivere mai pagato_elettronico: e' il valore fiscale XML.
    await db["corrispettivi"].update_one(
        {"data": data},
        {"$set": {"pos_reale_serale": totale_giorno,
                  "pos_reale_fonte": "terminale_manuale",
                  "pos_reale_updated_at": now}},
    )

    filtro_attivo = {"status": {"$nin": ["deleted", "archived"]}}
    # Ogni circuito ha la SUA coppia uscita-cassa / entrata-banca: gli accrediti
    # arrivano separati (NUMIA sul conto BPM, payout sul conto SumUp) e una riga
    # unica col totale non sarebbe riconciliabile con nessuno dei due.
    # ``and_gestore`` isola le righe di questo circuito; per Nexi comprende
    # anche quelle storiche prive del campo, che sono sue.
    and_gestore = [filtro_gestore_pos(gestore)]
    cassa_query = {
        "data": data,
        "tipo": "uscita",
        "$and": and_gestore + [{"$or": [
            {"categoria": "POS Verso Banca"},
            {"category": "POS Verso Banca"},
            {"source": {"$in": ["corrispettivo_import",
                                  "conferma_corrispettivo_manuale"]}},
        ]}],
        **filtro_attivo,
    }
    banca_query = {
        "data": data,
        "source": {"$in": ["trasferimento_pos", "chiusura_pos_mobile",
                             "corrispettivo_pos"]},
        "$and": and_gestore,
        **filtro_attivo,
    }
    cassa_mov = await db["prima_nota_cassa"].find_one(cassa_query)
    banca_mov = await db["prima_nota_banca"].find_one(banca_query)
    trasferimento_id = (
        (cassa_mov or {}).get("trasferimento_id")
        or (banca_mov or {}).get("trasferimento_id")
        or str(uuid.uuid4())
    )

    cassa_id = (cassa_mov or {}).get("id")
    banca_id = (banca_mov or {}).get("id")

    circuito = gestore.upper()
    # Zero archivia SOLO la coppia di questo circuito: se SumUp e' a zero ma
    # Nexi no, il trasferimento Nexi del giorno deve restare in piedi.
    if importo == 0:
        motivo = "chiusura_terminale_pos_zero"
        if cassa_mov:
            await db["prima_nota_cassa"].update_one(
                {"id": cassa_id},
                {"$set": {"status": "deleted", "deleted": True,
                          "deleted_reason": motivo, "deleted_at": now,
                          "updated_at": now}},
            )
        if banca_mov:
            await db["prima_nota_banca"].update_one(
                {"id": banca_id},
                {"$set": {"status": "deleted", "deleted": True,
                          "deleted_reason": motivo, "deleted_at": now,
                          "updated_at": now}},
            )
    else:
        descrizione_cassa = f"POS {circuito} {data} -> Banca (chiusura terminale)"
        cassa_fields = {
            "importo": importo,
            "amount": importo,
            "categoria": "POS Verso Banca",
            "category": "POS Verso Banca",
            "descrizione": descrizione_cassa,
            "description": descrizione_cassa,
            "gestore": gestore,
            "circuito": circuito,
            "quota_pos_fonte": "chiusura_manuale",
            "trasferimento_id": trasferimento_id,
            "updated_at": now,
            "status": "active",
            "deleted": False,
        }
        if corr_id:
            cassa_fields["corrispettivo_id"] = corr_id
        if cassa_mov:
            await db["prima_nota_cassa"].update_one(
                {"id": cassa_id}, {"$set": cassa_fields}
            )
        else:
            nuovo_movimento_cassa = {
                "data": data,
                "tipo": "uscita",
                "importo": importo,
                "categoria": "POS Verso Banca",
                "descrizione": cassa_fields["descrizione"],
                "source": "corrispettivo_import",
                "gestore": gestore,
                "circuito": circuito,
                "quota_pos_fonte": "chiusura_manuale",
                "trasferimento_id": trasferimento_id,
            }
            if corr_id:
                nuovo_movimento_cassa["corrispettivo_id"] = corr_id
            cassa_id = await scrivi_movimento(
                db, "cassa", nuovo_movimento_cassa
            )

        accreditato = round(float((banca_mov or {}).get("accreditato_ec") or 0), 2)
        quadrato = accreditato > 0 and abs(accreditato - importo) <= 0.01
        # Non e' denaro in banca: e' un credito verso il gestore, con un conto
        # e un saldo propri. Diventera' liquidita' solo quando il gestore
        # versera' davvero — su BPM per Nexi, sulla Mastercard per SumUp.
        etichetta_circuito = conti_pos.etichetta(gestore)
        descrizione_banca = f"Credito verso {etichetta_circuito} — POS {data}"
        banca_fields = {
            "importo": importo,
            "amount": importo,
            "categoria": "Corrispettivi POS",
            "category": "Corrispettivi POS",
            "descrizione": descrizione_banca,
            "description": descrizione_banca,
            "source": "trasferimento_pos",
            "natura": NATURA_CREDITO_POS,
            "conto_contabile": conti_pos.conto_credito(gestore),
            "conto_nome": conti_pos.descrizione_conto(
                conti_pos.conto_credito(gestore)),
            "gestore": gestore,
            "circuito": circuito,
            "quota_pos_fonte": "chiusura_manuale",
            "trasferimento_id": trasferimento_id,
            "giorno_vendita": data,
            "riconciliato": quadrato,
            # Credito POS atteso finche' l'accredito reale non lo conferma:
            # il saldo contabile lo comprende, ma resta marcato come non
            # ancora transitato sul conto.
            "in_transito": not quadrato,
            "stato_riconciliazione": "riconciliato" if quadrato else "da_verificare",
            "updated_at": now,
            "status": "active",
            "deleted": False,
        }
        if corr_id:
            banca_fields["corrispettivo_id"] = corr_id
        if banca_mov:
            await db["prima_nota_banca"].update_one(
                {"id": banca_id}, {"$set": banca_fields}
            )
        else:
            nuovo_movimento_banca = {
                "data": data,
                "tipo": "entrata",
                "importo": importo,
                "categoria": "Corrispettivi POS",
                "descrizione": banca_fields["descrizione"],
                "source": "trasferimento_pos",
                "natura": NATURA_CREDITO_POS,
                "conto_contabile": conti_pos.conto_credito(gestore),
                "conto_nome": conti_pos.descrizione_conto(
                    conti_pos.conto_credito(gestore)),
                "gestore": gestore,
                "circuito": circuito,
                "quota_pos_fonte": "chiusura_manuale",
                "trasferimento_id": trasferimento_id,
                "giorno_vendita": data,
                "riconciliato": False,
                "in_transito": True,
            }
            if corr_id:
                nuovo_movimento_banca["corrispettivo_id"] = corr_id
            banca_id = await scrivi_movimento(
                db, "banca", nuovo_movimento_banca
            )

    # Anche i metadati dell'entrata Cassa devono riflettere il terminale
    # reale, pur lasciando intatto l'importo totale del corrispettivo.
    entrata_cassa = await db["prima_nota_cassa"].find_one({
        "data": data,
        "tipo": "entrata",
        "categoria": "Corrispettivi",
        **filtro_attivo,
    })
    if entrata_cassa:
        totale = round(float(entrata_cassa.get("importo") or 0), 2)
        await db["prima_nota_cassa"].update_one(
            {"id": entrata_cassa.get("id")},
            {"$set": {
                "pagato_elettronico": totale_giorno,
                "pagato_contanti": round(totale - totale_giorno, 2),
                "dettaglio.elettronico": totale_giorno,
                "dettaglio.contanti": round(totale - totale_giorno, 2),
                "quota_pos_fonte": "chiusura_manuale",
                "updated_at": now,
            }},
        )

    action = "created" if importo_precedente is None else (
        "noop" if abs(importo_precedente - importo) < 0.01 else "updated"
    )
    if action != "noop":
        try:
            await db["pos_chiusure_audit"].insert_one({
                "id": str(uuid.uuid4()),
                "collection_target": "chiusure_pos_manuali",
                "data_riferimento": data,
                "gestore": gestore,
                "action": action,
                "importo_precedente": importo_precedente,
                "importo_nuovo": importo,
                "delta": round(importo - (importo_precedente or 0), 2),
                "user_id": user_id,
                "user_email": user_email,
                "user_name": user_name,
                "note": note,
                "origine": "coerenza_pos_inline",
                "timestamp": now,
            })
        except Exception:
            logger.exception("Audit chiusura POS reale fallito")

    return {
        "success": True,
        "action": action,
        "data": data,
        "gestore": gestore,
        "importo": importo,
        "importo_precedente": importo_precedente,
        "importo_totale_giorno": totale_giorno,
        "chiusura_id": chiusura_id,
        "prima_nota_cassa_id": cassa_id,
        "prima_nota_banca_id": banca_id,
        "trasferimento_id": trasferimento_id if totale_giorno > 0 else None,
    }


async def registra_corrispettivo(db, corr_doc: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """Scritture del corrispettivo giornaliero secondo il MODELLO POS.

    REGOLA CANONICA: cassa (entrata totale + uscita POS reale) e banca
    (trasferimento speculare della stessa cifra). L'accredito EC non crea
    nulla: riconcilia il trasferimento (riconcilia_accredito_pos_ec)."""
    data = corr_doc.get("data") or corr_doc.get("data_operazione") or ""
    contanti = float(corr_doc.get("pagato_contanti") or 0)
    elettronico = float(corr_doc.get("pagato_elettronico") or corr_doc.get("pagato_pos") or 0)
    totale = float(corr_doc.get("totale") or corr_doc.get("totale_complessivo")
                   or corr_doc.get("importo") or corr_doc.get("totale_giornaliero")
                   or (contanti + elettronico) or 0)
    if contanti == 0 and elettronico == 0 and totale > 0:
        contanti = totale

    anno = int(data[:4]) if data[:4].isdigit() else datetime.now().year
    mese = int(data[5:7]) if len(data) >= 7 and data[5:7].isdigit() else datetime.now().month
    matricola = corr_doc.get("matricola_rt") or corr_doc.get("id_dispositivo") or None

    esito: Dict[str, Optional[str]] = {
        "prima_nota_cassa_id": None,
        "prima_nota_cassa_uscita_pos_id": None,
        "prima_nota_banca_id": None,  # trasferimento speculare (se quota POS > 0)
    }
    if not data or totale <= 0:
        return esito

    # IDEMPOTENZA (stessa guardia storica, chiave data+matricola) — ERP-001
    # (19/07/2026): in un'UNICA operazione atomica (find_one_and_update con
    # upsert=True), non più in due chiamate separate find_one + insert_one.
    # Due richieste concorrenti per lo stesso corrispettivo non possono più
    # superare entrambe il controllo prima che una delle due abbia scritto.
    cassa_id, gia_esistente = await _scrivi_se_assente(
        db, "cassa",
        {
            "data": data, "tipo": "entrata", "categoria": "Corrispettivi",
            "matricola_rt": matricola,
            "source": {"$in": ["corrispettivo_import", "corrispettivi_sync",
                                "corrispettivo_xml", "xml_import", "manuale_da_xml",
                                "corrispettivo_manuale"]},
            # Una vecchia scrittura soft-deleted/archiviata non deve bloccare
            # la rigenerazione del movimento attivo. Senza questi filtri il
            # rebuild poteva trovare il residuo storico e non inserire nulla
            # di visibile in Prima Nota (caso reale 03/04/2026).
            "status": {"$nin": ["deleted", "archived"]},
            "entity_status": {"$ne": "deleted"},
        },
        {
            "corrispettivo_id": corr_doc.get("id"),
            "data": data, "tipo": "entrata", "importo": totale,
            "descrizione": f"Corrispettivi {data}",
            "categoria": "Corrispettivi", "source": "corrispettivo_import",
            "anno": anno, "mese": mese, "matricola_rt": matricola,
            "imponibile": round(float(corr_doc.get("totale_imponibile") or 0), 2),
            "iva": round(float(corr_doc.get("totale_iva") or 0), 2),
            "contanti": round(contanti, 2), "elettronico": round(elettronico, 2),
            "dettaglio": {"contanti": round(contanti, 2),
                          "elettronico": round(elettronico, 2),
                          "matricola_rt": corr_doc.get("matricola_rt", ""),
                          "numero_documenti": corr_doc.get("numero_documenti", 0)},
        },
    )
    esito["prima_nota_cassa_id"] = cassa_id
    if gia_esistente:
        esito["gia_esistente"] = True

    # USCITA POS: la chiusura manuale serale è il dato operativo vero;
    # l'elettronico XML è solo il fallback quando non è stata trascritta.
    chiusura = await chiusura_pos_del_giorno(db, data)
    quota_pos = chiusura if chiusura is not None else elettronico
    fonte_quota = "chiusura_manuale" if chiusura is not None else "xml"
    if quota_pos > 0:
        filtro_attivo = {
            "status": {"$nin": ["deleted", "archived"]},
            "entity_status": {"$ne": "deleted"},
        }
        cassa_query = {
            "data": data, "tipo": "uscita", "categoria": "POS Verso Banca",
            **filtro_attivo,
        }
        banca_query = {
            "data": data, "tipo": "entrata", "categoria": "Corrispettivi POS",
            **filtro_attivo,
        }
        cassa_esistente = await db["prima_nota_cassa"].find_one(cassa_query)
        banca_esistente = await db["prima_nota_banca"].find_one(banca_query)
        trasferimento_id = (
            (cassa_esistente or {}).get("trasferimento_id")
            or (banca_esistente or {}).get("trasferimento_id")
            or str(uuid.uuid4())
        )
        cassa_pos_id, _ = await _scrivi_se_assente(db, "cassa", cassa_query, {
            "corrispettivo_id": corr_doc.get("id"),
            "data": data, "tipo": "uscita", "importo": quota_pos,
            "descrizione": (f"POS {data} → Banca"
                            + (" (chiusura terminale)" if fonte_quota == "chiusura_manuale"
                               else " (da XML)")),
            "categoria": "POS Verso Banca", "source": "corrispettivo_import",
            "quota_pos_fonte": fonte_quota,
            "trasferimento_id": trasferimento_id,
            "anno": anno, "mese": mese,
        })
        esito["prima_nota_cassa_uscita_pos_id"] = cassa_pos_id
        # REGOLA CANONICA: contropartita speculare in banca — stessa
        # operazione, secondo registro. L'accredito EC la riconcilierà.
        banca_pos_id, _ = await _scrivi_se_assente(db, "banca", banca_query, {
            "corrispettivo_id": corr_doc.get("id"),
            "data": data, "tipo": "entrata", "importo": quota_pos,
            "descrizione": (f"POS {data} da cassa"
                            + (" (chiusura terminale)" if fonte_quota == "chiusura_manuale"
                               else " (da XML)")),
            "categoria": "Corrispettivi POS", "source": "trasferimento_pos",
            "quota_pos_fonte": fonte_quota,
            "trasferimento_id": trasferimento_id,
            "giorno_vendita": data,
            "riconciliato": False,
            "anno": anno, "mese": mese,
        })
        esito["prima_nota_banca_id"] = banca_pos_id
    return esito


async def riconcilia_accredito_pos_ec(db, mov_ec: Dict[str, Any]) -> bool:
    """REGOLA CANONICA: l'accredito POS dell'estratto conto NON crea
    un'entrata — riconcilia il TRASFERIMENTO del suo giorno di vendita
    (accumulando i circuiti: bancomat, carte, Amex arrivano separati).
    Ritorna True se ha agganciato un trasferimento."""
    from app.services.pos_evidence import (
        _e_accredito_pos_numia_con_giorno,
        _giorno_operazione_pos,
    )

    ec_id = mov_ec.get("id")
    if not ec_id:
        return False
    data_acc = (mov_ec.get("data") or "")[:10]
    descr = mov_ec.get("descrizione_originale") or mov_ec.get("descrizione") or ""
    if not _e_accredito_pos_numia_con_giorno(descr):
        return False
    giorno_vendita = _giorno_operazione_pos(descr, data_acc)
    importo = abs(float(mov_ec.get("importo") or 0))

    trasferimento = await db["prima_nota_banca"].find_one({
        "source": "trasferimento_pos",
        "$or": [{"giorno_vendita": giorno_vendita}, {"data": giorno_vendita}],
        "status": {"$nin": ["deleted", "archived"]},
    })
    if not trasferimento:
        # nessun trasferimento per quel giorno (corrispettivo mancante?):
        # l'EC resta non riconciliato e il collaudo lo evidenzierà
        return False

    # Lo scheduler riesamina le righe aperte. Sommare il valore gia'
    # memorizzato duplicava lo stesso accredito a ogni passaggio. La fonte di
    # verita' sono gli ID dell'estratto conto: ricalcola sempre il gruppo.
    estratto_conto_ids = list(dict.fromkeys([
        *(trasferimento.get("estratto_conto_ids") or []), ec_id,
    ]))
    accrediti_collegati = await db["estratto_conto_movimenti"].find(
        {"id": {"$in": estratto_conto_ids}},
        {"_id": 0, "id": 1, "importo": 1},
    ).to_list(len(estratto_conto_ids))
    importi_per_id = {
        str(riga.get("id")): abs(float(riga.get("importo") or 0))
        for riga in accrediti_collegati
        if riga.get("id")
    }
    # Utile anche nei test e negli import transazionali, dove la riga appena
    # passata potrebbe non essere ancora riletta dalla query.
    importi_per_id.setdefault(str(ec_id), importo)
    accreditato = round(sum(importi_per_id.values()), 2)
    atteso = float(trasferimento.get("importo") or 0)
    # In contabilita una differenza non e una riconciliazione. La vecchia
    # tolleranza del 2% (minimo 5 euro) produceva falsi positivi anche per
    # scarti importanti. Ammettiamo solo l'arrotondamento di un centesimo.
    riconciliato = abs(accreditato - atteso) <= 0.01
    await db["prima_nota_banca"].update_one(
        {"id": trasferimento["id"]},
        {"$set": {"accreditato_ec": accreditato,
                  "riconciliato": bool(riconciliato),
                  "tipo_riconciliazione": "accredito_pos_ec" if riconciliato else None,
                  "data_ultimo_accredito": data_acc},
         "$addToSet": {"estratto_conto_ids": ec_id}})

    dettagli = {"prima_nota_id": trasferimento["id"],
                "giorno_vendita": giorno_vendita,
                "importo_atteso": round(atteso, 2),
                "importo_accreditato": accreditato,
                "differenza": round(accreditato - atteso, 2)}
    if riconciliato:
        await db["estratto_conto_movimenti"].update_many(
            {"id": {"$in": estratto_conto_ids}},
            {"$set": {"riconciliato": True,
                      "tipo_riconciliazione": "accredito_pos_trasferimento",
                      "dettagli_riconciliazione": dettagli},
             "$unset": {"stato_riconciliazione": ""}})
    else:
        # Le singole righe NUMIA sono state associate al giorno, ma il gruppo
        # resta da verificare finche la loro somma non coincide col POS.
        await db["estratto_conto_movimenti"].update_many(
            {"id": {"$in": estratto_conto_ids}},
            {"$set": {"riconciliato": False,
                      "stato_riconciliazione": "da_verificare",
                      "tipo_riconciliazione": "accredito_pos_non_quadrato",
                      "dettagli_riconciliazione": dettagli}})
    return True


def query_accrediti_pos_ec(anno: int) -> Dict[str, Any]:
    """Filtro canonico per riconoscere gli accrediti POS nell'estratto conto."""
    return {
        "data": {"$regex": f"^{anno}"},
        "tipo": {"$ne": "uscita"},
        "$or": [
            {"descrizione_originale": {
                "$regex": "(?:INC\\.POS|INCAS\\. TRAMITE P\\.O\\.S).*NUMIA.*DEL [0-9]{2}/[0-9]{2}/[0-9]{2}",
                "$options": "i",
            }},
            {"descrizione": {
                "$regex": "(?:INC\\.POS|INCAS\\. TRAMITE P\\.O\\.S).*NUMIA.*DEL [0-9]{2}/[0-9]{2}/[0-9]{2}",
                "$options": "i",
            }},
        ],
    }
