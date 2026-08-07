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
- CASSA uscita "POS <CIRCUITO> Verso Banca" = il POS REALE del terminale,
  UNA RIGA PER CIRCUITO (POS NUMIA inserito a mano, POS SUMUP scritto
  dall'API). I circuiti non si fondono mai in un'unica riga.
- NIENTE FALLBACK XML (decisione utente 07/08/2026, che SUPERA la regola
  del 18/07/2026): senza dati reali dei terminali l'uscita POS non si
  scrive affatto e la giornata resta "attende_chiusura_pos_reale". L'XML è
  la fonte fiscale del corrispettivo e non sa quanta parte sia passata da
  Numia e quanta da SumUp: usarlo produceva un trasferimento indistinto
  che nessun accredito poteva riconciliare.
- BANCA entrata  = la STESSA cifra del suo circuito, come CREDITO verso il
  gestore (source "trasferimento_pos", conto 15.07.xx), non come denaro già
  sul conto. MAI una seconda registrazione indipendente.
- L'ACCREDITO dell'estratto conto NON crea mai un'entrata: RICONCILIA il
  trasferimento del suo giorno di vendita (causale NUMIA "DEL gg/mm/aa").
- L'elettronico XML resta il confronto FISCALE: la differenza col POS
  reale è il "NON BATTUTO" (battuto in meno sul registratore), esposto
  con saldo progressivo in Coerenza POS per recuperarlo nei giorni dopo.
"""
import logging
import re
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


GESTORE_POS_DEFAULT = conti_pos.NUMIA


def normalizza_gestore_pos(valore: Any) -> str:
    """Nome canonico del circuito POS.

    Le righe storiche senza campo, o con il vecchio nome "nexi", appartengono
    tutte a NUMIA: e' l'unico provider POS esistito finora. L'alias evita di
    dover riscrivere la contabilita' gia' registrata.
    """
    return conti_pos.normalizza(valore)


def filtro_gestore_pos(gestore: str) -> Dict[str, Any]:
    """Filtro Mongo per gestore.

    Le chiusure gia' registrate non hanno il campo ``gestore``: appartengono
    tutte a Nexi, unico terminale fino ad ora. Vanno quindi intercettate dal
    filtro del gestore predefinito, altrimenti un secondo inserimento
    creerebbe una riga parallela e raddoppierebbe il POS del giorno.
    """
    gestore = normalizza_gestore_pos(gestore)
    if gestore == GESTORE_POS_DEFAULT:
        # Comprende il nome storico "nexi" e le righe senza campo: sono tutte
        # dello stesso terminale. Ometterle creerebbe una riga parallela e
        # raddoppierebbe il POS del giorno.
        return {"$or": [
            {"gestore": {"$in": [gestore, "nexi", None, ""]}},
            {"gestore": {"$exists": False}},
        ]}
    return {"gestore": gestore}


# Fonti del dato POS, in ordine di attendibilita' crescente (decisione utente
# 07/08/2026). Il manuale alimenta subito la Prima Nota ma resta provvisorio:
# quando arriva l'Excel ufficiale o il terminale, la nuova evidenza CONFERMA
# se coincide e SEGNALA se no. Mai una sovrascrittura silenziosa, mai un
# secondo movimento: sono evidenze successive dello stesso ciclo.
FONTE_MANUALE = "manuale"
FONTE_EXCEL = "excel"
FONTE_TERMINALE = "terminale"
FONTE_API = "api"
PRIORITA_FONTE = {FONTE_MANUALE: 1, FONTE_EXCEL: 2, FONTE_TERMINALE: 3, FONTE_API: 3}

STATO_PROVVISORIO = "provvisorio_operativo"
STATO_CONFERMATO = "confermato"
STATO_DIFFERENZA = "differenza_da_verificare"


def valuta_evidenza(precedente: Optional[Dict[str, Any]], importo: float,
                    fonte: str) -> Dict[str, Any]:
    """Confronta la nuova evidenza con quella gia' registrata.

    Ritorna l'importo che deve finire in Prima Nota, lo stato del dato e tutti
    i valori visti per fonte. Il valore precedente non viene mai perso: se le
    due evidenze divergono resta consultabile accanto alla nuova, e la
    giornata si dichiara da verificare invece di far sparire il disaccordo.
    """
    fonte = str(fonte or FONTE_MANUALE).strip().lower()
    importo = round(float(importo), 2)
    valori = dict((precedente or {}).get("valori_per_fonte") or {})
    # Il documento precedente puo' essere anteriore a questa tracciatura:
    # senza questo innesto il valore gia' registrato andrebbe perso proprio
    # nel caso che conta, cioe' quando le due evidenze non coincidono.
    fonte_gia_nota = str((precedente or {}).get("fonte_dato") or "").strip().lower()
    if fonte_gia_nota and fonte_gia_nota not in valori:
        precedente_importo = (precedente or {}).get("importo")
        if precedente_importo is not None:
            valori[fonte_gia_nota] = round(float(precedente_importo), 2)
    valori[fonte] = importo

    fonte_prec = str((precedente or {}).get("fonte_dato") or "").strip().lower()
    importo_prec = (precedente or {}).get("importo")
    if precedente is None or importo_prec is None or not fonte_prec:
        stato = (STATO_PROVVISORIO if fonte == FONTE_MANUALE
                 else STATO_CONFERMATO)
        return {"importo": importo, "fonte_dato": fonte, "stato_dato": stato,
                "valori_per_fonte": valori, "differenza": None}

    importo_prec = round(float(importo_prec), 2)
    differenza = round(importo - importo_prec, 2)
    if fonte == fonte_prec or abs(differenza) <= 0.01:
        # Stessa fonte che si corregge, oppure evidenza che conferma.
        stato = (STATO_PROVVISORIO if fonte == FONTE_MANUALE == fonte_prec
                 else STATO_CONFERMATO)
        vincente = importo if fonte == fonte_prec else max(
            (importo, fonte), (importo_prec, fonte_prec),
            key=lambda v: PRIORITA_FONTE.get(v[1], 0))[0]
        return {"importo": vincente, "fonte_dato": fonte,
                "stato_dato": stato, "valori_per_fonte": valori,
                "differenza": 0.0 if fonte != fonte_prec else None}

    # Fonti diverse con importi diversi: vince la piu' attendibile, ma il
    # disaccordo resta scritto e la giornata va verificata a mano.
    piu_attendibile = max(
        (importo, fonte), (importo_prec, fonte_prec),
        key=lambda v: PRIORITA_FONTE.get(v[1], 0))
    return {
        "importo": piu_attendibile[0],
        "fonte_dato": piu_attendibile[1],
        "stato_dato": STATO_DIFFERENZA,
        "valori_per_fonte": valori,
        "differenza": differenza,
    }


async def pos_reale_del_giorno(db, data: str) -> Dict[str, Any]:
    """POS reale del giorno, scomposto per circuito.

    Si costruisce ESCLUSIVAMENTE da fonti reali — chiusure dei terminali,
    API ufficiali, statement dei provider. Mai dall'elettronico XML: l'XML e'
    la fonte fiscale dei corrispettivi e non sa dire quanto sia passato da
    Nexi e quanto da SumUp (decisione utente 07/08/2026).

    Ritorna sempre la scomposizione, cosi' chi la usa non puo' confondere
    "600 in tutto" con "500 Nexi + 100 SumUp"::

        {"per_circuito": {"nexi": 500.0, "sumup": 100.0},
         "nexi": 500.0, "sumup": 100.0, "altri": 0.0,
         "totale_pos_reale": 600.0, "disponibile": True}

    ``disponibile`` e' False quando nessun terminale ha ancora risposto: in
    quel caso ``totale_pos_reale`` e' None e la giornata resta in attesa,
    perche' un dato mancante non e' uno zero.
    """
    per_circuito: Dict[str, float] = {}
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
        for circuito, componenti in per_gestore.items():
            trovata = True
            # Un inserimento/correzione dalla UI e' un totale giornaliero e
            # prevale sugli eventuali componenti storici importati da CSV.
            override = next((c for c in reversed(componenti)
                             if c.get("source") == "inserimento_manuale_terminale"), None)
            if override is not None:
                valore = override.get("importo")
                parziale = float(valore if valore is not None
                                 else override.get("totale") or 0)
            else:
                parziale = sum(float(c.get("importo") or c.get("totale") or 0)
                               for c in componenti)
            per_circuito[circuito] = round(
                per_circuito.get(circuito, 0.0) + parziale, 2)
        if not trovata:
            # Chiusure importate in prima_nota_banca con source
            # import_manuale_pos (vecchio flusso pos.xlsx). E' comunque una
            # fonte REALE — l'export del terminale — non l'XML.
            for c in await _leggi_tutti(db["prima_nota_banca"].find(
                    {"data": data, "source": "import_manuale_pos"},
                    {"_id": 0, "importo": 1})):
                trovata = True
                per_circuito[GESTORE_POS_DEFAULT] = round(
                    per_circuito.get(GESTORE_POS_DEFAULT, 0.0)
                    + float(c.get("importo") or 0), 2)
    except AttributeError:
        # backend/fake senza le collezioni delle chiusure
        return {"per_circuito": {}, "totale_pos_reale": None,
                "disponibile": False, "nexi": None, "sumup": None, "altri": 0.0}

    noti = set(conti_pos.circuiti_attivi())
    esito: Dict[str, Any] = {
        "per_circuito": dict(per_circuito),
        # Zero e' un valore valido: significa che quel terminale non ha
        # incassato. Solo l'assenza totale di fonti lascia il dato indefinito.
        "totale_pos_reale": round(sum(per_circuito.values()), 2) if trovata else None,
        "disponibile": trovata,
        "altri": round(sum(v for c, v in per_circuito.items() if c not in noti), 2),
    }
    for circuito in noti:
        esito[circuito] = per_circuito.get(circuito)
    return esito


async def chiusura_pos_del_giorno(db, data: str) -> Optional[float]:
    """Solo il TOTALE del POS reale del giorno, o None se nessuna fonte.

    Comodita' per chi deve confrontare un unico numero. Chi deve scrivere in
    contabilita' usa ``pos_reale_del_giorno``: i circuiti non condividono mai
    un trasferimento, quindi servono gli importi separati.
    """
    return (await pos_reale_del_giorno(db, data))["totale_pos_reale"]


async def registra_chiusura_pos_reale(
    db,
    data: str,
    importo: float,
    *,
    gestore: str = GESTORE_POS_DEFAULT,
    fonte: str = FONTE_MANUALE,
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
        filtro_chiusura,
        {"_id": 0, "importo": 1, "totale": 1, "id": 1,
         "fonte_dato": 1, "valori_per_fonte": 1},
    )
    # L'evidenza nuova non sovrascrive mai in silenzio quella gia' registrata:
    # conferma se coincide, segnala se no, e conserva entrambi i valori.
    evidenza = valuta_evidenza(precedente_doc, importo, fonte)
    importo = evidenza["importo"]
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
        "fonte_dato": evidenza["fonte_dato"],
        "stato_dato": evidenza["stato_dato"],
        "valori_per_fonte": evidenza["valori_per_fonte"],
        "differenza_fonti": evidenza["differenza"],
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
            {"categoria": {"$in": conti_pos.CATEGORIE_USCITA_POS}},
            {"category": {"$in": conti_pos.CATEGORIE_USCITA_POS}},
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
        descrizione_cassa = (
            f"POS {conti_pos.sigla(gestore)} {conti_pos.data_italiana(data)}"
            " -> Banca (chiusura terminale)")
        cassa_fields = {
            "importo": importo,
            "amount": importo,
            "categoria": conti_pos.categoria_uscita_pos(gestore),
            "category": conti_pos.categoria_uscita_pos(gestore),
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
                "categoria": conti_pos.categoria_uscita_pos(gestore),
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
        descrizione_banca = (f"Credito verso {etichetta_circuito} — POS "
                             f"{conti_pos.data_italiana(data)}")
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
        "fonte_dato": evidenza["fonte_dato"],
        "stato_dato": evidenza["stato_dato"],
        "differenza_fonti": evidenza["differenza"],
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

    # USCITA POS: si costruisce SOLO dai terminali reali, mai dall'XML.
    #
    # Fino al 07/08/2026 qui c'era `quota_pos = chiusura or elettronico`: in
    # assenza di chiusura si usava l'elettronico XML. Vietato dall'utente, e a
    # ragione: l'XML e' la fonte fiscale del corrispettivo e non sa quanta
    # parte sia passata da Nexi e quanta da SumUp. Usarlo produceva un
    # trasferimento unico e indistinto, che nessun accredito avrebbe potuto
    # riconciliare. Senza dati reali non si inventa l'uscita: la giornata
    # resta in attesa e viene riprocessata quando i terminali rispondono.
    reale = await pos_reale_del_giorno(db, data)
    if not reale["disponibile"]:
        esito["pos_stato"] = "attende_chiusura_pos_reale"
        esito["pos_reale"] = None
        await _marca_stato_pos(db, data, "attende_chiusura_pos_reale")
        return esito

    esito["pos_stato"] = "pos_reale_disponibile"
    esito["pos_reale"] = reale["per_circuito"]
    await _marca_stato_pos(db, data, "pos_reale_disponibile")

    filtro_attivo = {
        "status": {"$nin": ["deleted", "archived"]},
        "entity_status": {"$ne": "deleted"},
    }
    scritti = {}
    for circuito, importo in sorted(reale["per_circuito"].items()):
        if importo <= 0:
            continue
        # Ogni circuito ha il SUO trasferimento: Nexi e SumUp non ne
        # condividono mai uno, perche' li accreditano conti diversi.
        gestore_filtro = filtro_gestore_pos(circuito)
        cassa_query = {
            "data": data, "tipo": "uscita",
            "categoria": {"$in": conti_pos.CATEGORIE_USCITA_POS},
            "$and": [gestore_filtro], **filtro_attivo,
        }
        banca_query = {
            "data": data, "tipo": "entrata", "categoria": "Corrispettivi POS",
            "$and": [gestore_filtro], **filtro_attivo,
        }
        cassa_esistente = await db["prima_nota_cassa"].find_one(cassa_query)
        banca_esistente = await db["prima_nota_banca"].find_one(banca_query)
        trasferimento_id = (
            (cassa_esistente or {}).get("trasferimento_id")
            or (banca_esistente or {}).get("trasferimento_id")
            or str(uuid.uuid4())
        )
        etichetta_circuito = conti_pos.etichetta(circuito)
        comune = {
            "corrispettivo_id": corr_doc.get("id"),
            "data": data, "importo": importo,
            "quota_pos_fonte": "terminale_reale",
            "gestore": circuito, "circuito": circuito.upper(),
            "trasferimento_id": trasferimento_id,
            "anno": anno, "mese": mese,
        }
        cassa_pos_id, _ = await _scrivi_se_assente(db, "cassa", cassa_query, {
            **comune, "tipo": "uscita",
            "descrizione": (f"POS {conti_pos.sigla(circuito)} "
                            f"{conti_pos.data_italiana(data)} → Banca"),
            "categoria": conti_pos.categoria_uscita_pos(circuito),
            "source": "corrispettivo_import",
        })
        # Contropartita speculare: stessa operazione, secondo registro. Non e'
        # denaro in banca ma un credito verso il gestore, che l'accredito
        # reale chiudera'.
        banca_pos_id, _ = await _scrivi_se_assente(db, "banca", banca_query, {
            **comune, "tipo": "entrata",
            "descrizione": (f"Credito verso {etichetta_circuito} — POS "
                            f"{conti_pos.data_italiana(data)}"),
            "categoria": "Corrispettivi POS", "source": "trasferimento_pos",
            "natura": NATURA_CREDITO_POS,
            "conto_contabile": conti_pos.conto_credito(circuito),
            "conto_nome": conti_pos.descrizione_conto(
                conti_pos.conto_credito(circuito)),
            "giorno_vendita": data,
            "riconciliato": False,
            "in_transito": True,
        })
        scritti[circuito] = {"cassa": cassa_pos_id, "banca": banca_pos_id}
        esito["prima_nota_cassa_uscita_pos_id"] = cassa_pos_id
        esito["prima_nota_banca_id"] = banca_pos_id
    esito["trasferimenti_pos"] = scritti
    return esito


async def _marca_stato_pos(db, data: str, stato: str) -> None:
    """Annota sul corrispettivo se il POS reale e' arrivato o si attende.

    E' un'informazione di servizio per la Coerenza POS e il riprocessamento:
    se non si riesce a scriverla, la registrazione contabile deve comunque
    andare a buon fine. Un'annotazione non puo' far fallire una scrittura.
    """
    try:
        await db["corrispettivi"].update_one(
            {"data": data}, {"$set": {"pos_stato": stato}},
        )
    except Exception:
        logger.debug("Stato POS non annotato per %s", data, exc_info=True)


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

    # Dal 07/08/2026 i trasferimenti sono per circuito (Numia E SumUp nello
    # stesso giorno). L'accredito con causale NUMIA deve agganciare il
    # trasferimento NUMIA: senza questo filtro poteva prendere quello SumUp
    # del medesimo giorno e "riconciliare" il circuito sbagliato.
    trasferimento = await db["prima_nota_banca"].find_one({
        "source": "trasferimento_pos",
        "$and": [
            {"$or": [{"giorno_vendita": giorno_vendita}, {"data": giorno_vendita}]},
            filtro_gestore_pos(conti_pos.NUMIA),
        ],
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


def raggruppa_accrediti_pos_per_giorno(
    movimenti: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Somma gli accrediti Numia usando il giorno vendita nella causale.

    Le copie provenienti da estratti sovrapposti restano come prove, ma non
    vengono sommate due volte. Commissioni e accrediti privi di ``DEL
    gg/mm/aa`` non sono chiusure POS utilizzabili.
    """
    from app.services.pos_evidence import (
        _e_accredito_pos_numia_con_giorno,
        _giorno_operazione_pos,
    )

    unici: Dict[tuple, Dict[str, Any]] = {}
    for mov in movimenti:
        descr = str(mov.get("descrizione_originale") or mov.get("descrizione") or "")
        if not _e_accredito_pos_numia_con_giorno(descr):
            continue
        importo = abs(float(mov.get("importo") or mov.get("amount") or 0))
        if importo <= 0:
            continue
        giorno = _giorno_operazione_pos(descr, str(mov.get("data") or ""))
        chiave = (
            str(mov.get("data") or mov.get("data_contabile") or "")[:10],
            giorno,
            int(round(importo * 100)),
            re.sub(r"[^a-z0-9]+", "", descr.lower()),
            re.sub(r"[^a-z0-9]+", "", str(mov.get("rapporto") or "").lower()),
        )
        corrente = unici.get(chiave)
        if corrente is None or len(descr) > len(str(
            corrente.get("descrizione_originale") or corrente.get("descrizione") or ""
        )):
            unici[chiave] = mov

    out: Dict[str, Dict[str, Any]] = {}
    for mov in unici.values():
        descr = str(mov.get("descrizione_originale") or mov.get("descrizione") or "")
        giorno = _giorno_operazione_pos(descr, str(mov.get("data") or ""))
        item = out.setdefault(giorno, {"totale": 0.0, "estratto_conto_ids": []})
        item["totale"] += abs(float(mov.get("importo") or mov.get("amount") or 0))
        mov_id = str(mov.get("id") or mov.get("_id") or "")
        if mov_id and mov_id not in item["estratto_conto_ids"]:
            item["estratto_conto_ids"].append(mov_id)
    for item in out.values():
        item["totale"] = round(item["totale"], 2)
        item["estratto_conto_ids"].sort()
    return out


async def recupera_pos_storico_da_estratto(db, anno: int) -> Dict[str, Any]:
    """Popola Numia da EC solo quando non esiste la chiusura serale manuale."""
    movimenti = await _leggi_tutti(
        db["estratto_conto_movimenti"].find(query_accrediti_pos_ec(anno), {"_id": 0}),
        20000,
    )
    gruppi = raggruppa_accrediti_pos_per_giorno(movimenti)
    creati = aggiornati = saltati_manuali = 0
    dettagli = []
    for giorno, evidenza in sorted(gruppi.items()):
        filtro = {"data": giorno, **filtro_gestore_pos(conti_pos.NUMIA)}
        precedente = await db["chiusure_pos_manuali"].find_one(filtro, {"_id": 0})
        if precedente and not precedente.get("recupero_storico_estratto"):
            saltati_manuali += 1
            continue
        esito = await registra_chiusura_pos_reale(
            db,
            giorno,
            evidenza["totale"],
            gestore=conti_pos.NUMIA,
            fonte=FONTE_EXCEL,
            note="Recupero storico dagli accrediti POS dell'estratto conto",
            actor={"sub": "system-pos-bank-backfill"},
        )
        await db["chiusure_pos_manuali"].update_one(
            filtro,
            {"$set": {
                "recupero_storico_estratto": True,
                "estratto_conto_ids": evidenza["estratto_conto_ids"],
            }},
        )
        if precedente:
            aggiornati += int(esito.get("action") != "noop")
        else:
            creati += 1
        dettagli.append({"data": giorno, **evidenza, "action": esito.get("action")})
    return {
        "anno": anno,
        "giorni_bancari": len(gruppi),
        "creati": creati,
        "aggiornati": aggiornati,
        "saltati_per_chiusura_manuale": saltati_manuali,
        "dettagli": dettagli,
    }
