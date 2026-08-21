"""Sincronizzazione delle transazioni SumUp.

SumUp e' un circuito POS accanto a Nexi/Numia, non una nuova fonte di ricavo:
il ricavo e' gia' dichiarato dal corrispettivo XML/RT. Queste transazioni
servono a sapere QUANTA parte dell'incasso e' passata dal terminale SumUp,
esattamente come la chiusura serale fa per Nexi.

Il modulo e' diviso in due meta':

- funzioni pure (normalizzazione e aggregazione), verificabili senza rete;
- il client HTTP e la scrittura, che passano dal motore unico.

La sincronizzazione e' idempotente: la chiave e' ``merchant_code`` +
``transaction_id``, quindi riscaricare lo stesso intervallo non duplica nulla.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

GESTORE = "sumup"
COLL_TRANSAZIONI = "sumup_transactions"
COLL_PAYOUT = "sumup_payouts"

# Il giorno contabile e' quello del negozio, non UTC: una vendita delle 23:30
# del 6 agosto appartiene al 6 agosto anche se SumUp la marca 21:30Z.
FUSO_NEGOZIO = ZoneInfo("Europe/Rome")

TIPO_VENDITA = "PAYMENT"
TIPO_RIMBORSO = "REFUND"
TIPO_CHARGEBACK = "CHARGEBACK"

# Solo il riuscito muove denaro. FAILED/CANCELLED/PENDING restano archiviati
# per l'audit ma non entrano in nessun totale.
STATO_VALIDO = "SUCCESSFUL"
STATI_ESCLUSI = {"FAILED", "CANCELLED", "PENDING"}
TIPI_DEDUZIONE_PAYOUT = {
    "CHARGE_BACK_DEDUCTION",
    "REFUND_DEDUCTION",
    "DD_RETURN_DEDUCTION",
    "BALANCE_DEDUCTION",
}

TIMEOUT = 30.0
LIMITE_PAGINE = 200


class SumUpNonConfigurato(RuntimeError):
    """Chiave o merchant code mancanti: meglio fermarsi che scrivere a vuoto."""


# --------------------------------------------------------------------------
# Funzioni pure
# --------------------------------------------------------------------------

def giorno_locale(timestamp: Any) -> str:
    """Giorno contabile Europe/Rome di un istante SumUp (ISO 8601, UTC)."""
    testo = str(timestamp or "").strip()
    if not testo:
        raise ValueError("timestamp SumUp assente")
    if testo.endswith("Z"):
        testo = testo[:-1] + "+00:00"
    momento = datetime.fromisoformat(testo)
    if momento.tzinfo is None:
        # SumUp dichiara UTC: assumerlo esplicitamente evita che il server
        # scriva il giorno secondo il proprio fuso, che puo' cambiare.
        momento = momento.replace(tzinfo=timezone.utc)
    return momento.astimezone(FUSO_NEGOZIO).date().isoformat()


def _importo(valore: Any) -> float:
    try:
        return round(abs(float(valore or 0)), 2)
    except (TypeError, ValueError):
        return 0.0


def chiave_transazione(merchant_code: str, transaction_id: Any) -> str:
    return f"{str(merchant_code or '').strip()}:{str(transaction_id or '').strip()}"


def normalizza_transazione(grezza: Dict[str, Any],
                           merchant_code: str) -> Optional[Dict[str, Any]]:
    """Riduce una transazione SumUp ai campi che contano, o la scarta.

    Una riga senza identificativo o senza data non e' utilizzabile: entrerebbe
    in contabilita' senza poter essere ne' deduplicata ne' attribuita a un
    giorno, che sono le due garanzie su cui si regge tutto il flusso.
    """
    if not isinstance(grezza, dict):
        return None
    transaction_id = (
        grezza.get("id")
        or grezza.get("transaction_id")
        or grezza.get("transaction_code")
    )
    if not transaction_id:
        return None
    timestamp = grezza.get("timestamp") or grezza.get("created_at") or grezza.get("date")
    try:
        data = giorno_locale(timestamp)
    except (ValueError, TypeError):
        return None

    tipo = str(grezza.get("type") or TIPO_VENDITA).strip().upper()
    stato = str(grezza.get("status") or "").strip().upper()
    # Alcune risposte marcano il rimborso solo con lo stato: il tipo resta
    # PAYMENT ma l'operazione e' un reso a tutti gli effetti.
    if stato == "REFUNDED" and tipo == TIPO_VENDITA:
        stato = STATO_VALIDO

    return {
        "chiave": chiave_transazione(merchant_code, transaction_id),
        "merchant_code": str(merchant_code or "").strip(),
        "transaction_id": str(transaction_id),
        "transaction_code": str(grezza.get("transaction_code") or ""),
        "tipo": tipo,
        "stato": stato,
        "data": data,
        "timestamp": str(timestamp),
        "importo": _importo(grezza.get("amount")),
        "rimborsato": _importo(grezza.get("refunded_amount")),
        "valuta": str(grezza.get("currency") or "EUR").upper(),
        "payout_id": str(grezza.get("payout_id") or ""),
        # Serve a non sottrarre due volte lo stesso reso.
        "riferimento": str(
            grezza.get("related_transaction_id")
            or grezza.get("parent_transaction_id")
            or grezza.get("transaction_id_original")
            or ""
        ),
    }


def _valida(transazione: Dict[str, Any]) -> bool:
    return transazione.get("stato") not in STATI_ESCLUSI


def aggrega_per_giorno(transazioni: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Chiusura giornaliera SumUp: vendite riuscite meno rimborsi.

    Il reso puo' arrivare in due forme: come evento ``REFUND`` a se' stante
    oppure come ``refunded_amount`` sul pagamento originale. Sommarle
    entrambe sottrarrebbe due volte lo stesso denaro, quindi il campo vale
    solo per i pagamenti che NON hanno gia' un evento di rimborso collegato.

    Il reso esplicito pesa sul giorno in cui e' avvenuto (e' allora che il
    denaro esce); il ``refunded_amount`` senza evento, non avendo una data
    propria, resta sul giorno del pagamento.
    """
    righe = [t for t in transazioni if isinstance(t, dict) and _valida(t)]

    # Pagamenti che hanno gia' un evento di rimborso dedicato.
    con_evento_di_reso = {
        t.get("riferimento") for t in righe
        if t.get("tipo") == TIPO_RIMBORSO and t.get("riferimento")
    }

    giornate: Dict[str, Dict[str, Any]] = {}

    def _giorno(data: str) -> Dict[str, Any]:
        return giornate.setdefault(data, {
            "data": data,
            "vendite": 0.0,
            "rimborsi": 0.0,
            "chargeback": 0.0,
            "netto": 0.0,
            "transazioni": 0,
        })

    for t in righe:
        tipo = t.get("tipo")
        data = t.get("data")
        if not data:
            continue
        if tipo == TIPO_VENDITA and t.get("stato") == STATO_VALIDO:
            giorno = _giorno(data)
            giorno["vendite"] += t.get("importo") or 0.0
            giorno["transazioni"] += 1
            rimborsato = t.get("rimborsato") or 0.0
            if rimborsato and t.get("transaction_id") not in con_evento_di_reso:
                giorno["rimborsi"] += rimborsato
        elif tipo == TIPO_RIMBORSO:
            _giorno(data)["rimborsi"] += t.get("importo") or 0.0
        elif tipo == TIPO_CHARGEBACK:
            # Non tocca il venduto del giorno: incide sull'accredito, dove
            # viene confrontato con il payout.
            _giorno(data)["chargeback"] += t.get("importo") or 0.0

    for giorno in giornate.values():
        giorno["vendite"] = round(giorno["vendite"], 2)
        giorno["rimborsi"] = round(giorno["rimborsi"], 2)
        giorno["chargeback"] = round(giorno["chargeback"], 2)
        giorno["netto"] = round(giorno["vendite"] - giorno["rimborsi"], 2)
    return giornate


# --------------------------------------------------------------------------
# Client HTTP
# --------------------------------------------------------------------------

# Codice esercente ricavato dalla chiave, memorizzato per non richiederlo a
# ogni sincronizzazione. La chiave fa parte della cache: se viene ruotata o
# sostituita con quella di un altro conto, il codice viene richiesto di nuovo.
_merchant_ricavato: Dict[str, str] = {}


def _chiave() -> str:
    chiave = (settings.SUMUP_API_KEY or "").strip()
    if not chiave:
        raise SumUpNonConfigurato("SUMUP_API_KEY deve essere configurata.")
    return chiave


async def merchant_effettivo() -> str:
    """Codice esercente: quello configurato, altrimenti quello della chiave.

    SUMUP_MERCHANT_CODE resta il valore che comanda. Se non e' impostato non
    ha senso fermarsi: la chiave appartiene a un conto solo e SumUp lo dichiara
    su ``/v0.1/me``. Ricavarlo evita di bloccare tutto per un dato che non e'
    una scelta ma un'identita'.
    """
    configurato = (settings.SUMUP_MERCHANT_CODE or "").strip()
    if configurato:
        return configurato

    chiave = _chiave()
    if chiave in _merchant_ricavato:
        return _merchant_ricavato[chiave]

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        risposta = await client.get(
            f"{settings.SUMUP_API_BASE}/v0.1/me",
            headers={"Authorization": f"Bearer {chiave}"},
        )
    if risposta.status_code != 200:
        raise SumUpNonConfigurato(
            f"SumUp non ha accettato la chiave (HTTP {risposta.status_code}): "
            f"impossibile ricavare il codice esercente."
        )
    codice = str(
        ((risposta.json() or {}).get("merchant_profile") or {}).get("merchant_code") or ""
    ).strip()
    if not codice:
        raise SumUpNonConfigurato(
            "SumUp non ha restituito il codice esercente: imposta "
            "SUMUP_MERCHANT_CODE fra le variabili d'ambiente."
        )
    _merchant_ricavato[chiave] = codice
    logger.info("SumUp: codice esercente ricavato dalla chiave: %s", codice)
    return codice


async def _credenziali() -> tuple:
    return _chiave(), await merchant_effettivo()


def _prossima_pagina(payload: Dict[str, Any]) -> Optional[str]:
    for link in (payload.get("links") or []):
        if isinstance(link, dict) and str(link.get("rel") or "").lower() == "next":
            return link.get("href")
    return None


def _istante_utc(data_locale: date) -> str:
    """Mezzanotte italiana nel formato UTC accettato da SumUp."""
    momento = datetime.combine(data_locale, time.min, tzinfo=FUSO_NEGOZIO)
    return momento.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parametri_intervallo(dal: str, al: str) -> Dict[str, Any]:
    """Intervallo SumUp inclusivo per giorno contabile Europe/Rome.

    L'API Transactions usa ``oldest_time`` e ``newest_time``; il secondo
    limite e' l'inizio del giorno successivo, cosi' l'intera giornata ``al``
    resta compresa anche durante i cambi tra ora solare e legale.
    """
    inizio = date.fromisoformat(dal)
    fine = date.fromisoformat(al)
    if fine < inizio:
        raise ValueError("La data finale SumUp precede quella iniziale.")
    return {
        "oldest_time": _istante_utc(inizio),
        "newest_time": _istante_utc(fine + timedelta(days=1)),
        "order": "ascending",
        "limit": 100,
    }


def _url_pagina_successiva(url_corrente: str, href: str) -> str:
    """Converte anche i link ``next`` relativi di SumUp in URL assoluti."""
    riferimento = str(href or "").strip()
    if not riferimento:
        return ""
    if urlparse(riferimento).scheme:
        return riferimento
    if riferimento.startswith("?"):
        return f"{url_corrente.split('?', 1)[0]}{riferimento}"
    if riferimento.startswith("/"):
        return urljoin(settings.SUMUP_API_BASE.rstrip("/") + "/", riferimento)
    # La documentazione SumUp mostra anche href come semplice query string,
    # ad esempio ``limit=10&oldest_ref=...``.
    if "=" in riferimento and "/" not in riferimento.split("?", 1)[0]:
        return f"{url_corrente.split('?', 1)[0]}?{riferimento.lstrip('?')}"
    return urljoin(url_corrente, riferimento)


async def scarica_transazioni(dal: str, al: str) -> List[Dict[str, Any]]:
    """Storico transazioni nell'intervallo, seguendo la paginazione a cursore."""
    chiave, merchant = await _credenziali()
    url = (f"{settings.SUMUP_API_BASE}/v2.1/merchants/{merchant}"
           f"/transactions/history")
    params: Optional[Dict[str, Any]] = _parametri_intervallo(dal, al)
    headers = {"Authorization": f"Bearer {chiave}"}

    raccolte: List[Dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for _ in range(LIMITE_PAGINE):
            risposta = await client.get(url, params=params, headers=headers)
            risposta.raise_for_status()
            payload = risposta.json() or {}
            raccolte.extend(payload.get("items") or [])
            successiva = _prossima_pagina(payload)
            if not successiva:
                break
            # Il link "next" porta gia' il cursore: i parametri iniziali
            # non vanno riapplicati, altrimenti si torna alla prima pagina.
            url, params = _url_pagina_successiva(url, successiva), None
        else:
            logger.warning(
                "SumUp: raggiunto il limite di %s pagine per %s..%s",
                LIMITE_PAGINE, dal, al,
            )
    return raccolte


async def scarica_payouts(dal: str, al: str) -> List[Dict[str, Any]]:
    """Record finanziari SumUp che hanno mosso la Mastercard aziendale.

    L'endpoint non restituisce un payout gia' aggregato: ogni riga rappresenta
    una vendita o una deduzione e piu' righe condividono lo stesso
    ``reference``. Per questo si richiede il limite massimo documentato e il
    raggruppamento viene eseguito separatamente, senza confronti per importo.
    """
    chiave, merchant = await _credenziali()
    url = (f"{settings.SUMUP_API_BASE}/v1.0/merchants/{merchant}"
           f"/payouts")
    params = {
        "start_date": date.fromisoformat(dal).isoformat(),
        "end_date": date.fromisoformat(al).isoformat(),
        "format": "json",
        "limit": 9999,
        "order": "asc",
    }
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        risposta = await client.get(
            url, params=params,
            headers={"Authorization": f"Bearer {chiave}"},
        )
    risposta.raise_for_status()
    payload = risposta.json() or []
    if not isinstance(payload, list):
        raise ValueError("SumUp payouts: risposta non conforme (attesa lista).")
    return [r for r in payload if isinstance(r, dict)]


def raggruppa_payouts(righe: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Aggrega le righe finanziarie per riferimento Mastercard.

    ``id`` identifica la singola riga; il riferimento identifica invece il
    movimento finanziario composto. La transazione originaria resta provata
    da ``transaction_code``. Mescolare questi tre identificativi era la causa
    per cui nessun payout riusciva a chiudere il credito giornaliero.
    """
    gruppi: Dict[str, List[Dict[str, Any]]] = {}
    for riga in righe:
        if not isinstance(riga, dict):
            continue
        riferimento = str(riga.get("reference") or "").strip()
        if not riferimento:
            identificativo = str(riga.get("id") or "").strip()
            if not identificativo:
                continue
            riferimento = f"record:{identificativo}"
        gruppi.setdefault(riferimento, []).append(riga)

    risultati: List[Dict[str, Any]] = []
    for riferimento, componenti in gruppi.items():
        payout_rows = [
            r for r in componenti
            if str(r.get("type") or "").upper() == "PAYOUT"
        ]
        deduction_rows = [
            r for r in componenti
            if str(r.get("type") or "").upper() in TIPI_DEDUZIONE_PAYOUT
        ]
        date_payout = sorted({str(r.get("date") or "")[:10] for r in componenti})
        statuses = sorted({str(r.get("status") or "").upper() for r in componenti})
        valuta = next((str(r.get("currency") or "EUR").upper()
                       for r in componenti if r.get("currency")), "EUR")
        payout_amount = round(sum(_importo(r.get("amount")) for r in payout_rows), 2)
        deduction_amount = round(sum(_importo(r.get("amount")) for r in deduction_rows), 2)
        commissioni = round(sum(_importo(r.get("fee")) for r in componenti), 2)
        risultati.append({
            "payout_id": riferimento,
            "reference": riferimento,
            "date": date_payout[-1] if date_payout else "",
            "currency": valuta,
            "status": "SUCCESSFUL" if statuses == ["SUCCESSFUL"] else "DA_VERIFICARE",
            "tipi": sorted({str(r.get("type") or "").upper() for r in componenti}),
            "payout_amount": payout_amount,
            "deduction_amount": deduction_amount,
            "movimento_mastercard": round(payout_amount - deduction_amount, 2),
            "fee_total": commissioni,
            "transaction_codes": sorted({
                str(r.get("transaction_code") or "").strip()
                for r in componenti if r.get("transaction_code")
            }),
            "record_ids": sorted({str(r.get("id")) for r in componenti if r.get("id")}),
            "records": len(componenti),
            "solo_rettifica": not payout_rows and bool(deduction_rows),
        })
    return sorted(risultati, key=lambda g: (g.get("date") or "", g["payout_id"]))


def accrediti_payout_per_giorno(
    gruppi: Iterable[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Unifica i movimenti SumUp per data effettiva di accredito.

    Soltanto i gruppi interamente ``SUCCESSFUL`` entrano negli importi. Quelli
    falliti o misti restano visibili come prove da verificare, senza diventare
    accrediti contabili.
    """
    giorni: Dict[str, Dict[str, Any]] = {}
    for gruppo in gruppi:
        data_accredito = str(gruppo.get("date") or "")[:10]
        if len(data_accredito) != 10:
            continue
        giorno = giorni.setdefault(data_accredito, {
            "data": data_accredito,
            "accredito_mastercard": 0.0,
            "commissioni": 0.0,
            "gruppi": 0,
            "rettifiche": 0,
            "da_verificare": 0,
            "payout_ids": [],
        })
        giorno["gruppi"] += 1
        if gruppo.get("solo_rettifica"):
            giorno["rettifiche"] += 1
        payout_id = str(gruppo.get("payout_id") or "")
        if payout_id and payout_id not in giorno["payout_ids"]:
            giorno["payout_ids"].append(payout_id)
        if gruppo.get("status") != STATO_VALIDO:
            giorno["da_verificare"] += 1
            continue
        giorno["accredito_mastercard"] += float(
            gruppo.get("movimento_mastercard") or 0
        )
        giorno["commissioni"] += float(gruppo.get("fee_total") or 0)

    for giorno in giorni.values():
        giorno["accredito_mastercard"] = round(giorno["accredito_mastercard"], 2)
        giorno["commissioni"] = round(giorno["commissioni"], 2)
        giorno["payout_ids"].sort()
    return [giorni[data] for data in sorted(giorni)]


# --------------------------------------------------------------------------
# Scrittura
# --------------------------------------------------------------------------

async def salva_transazioni(db, grezze: Iterable[Dict[str, Any]],
                            merchant_code: str) -> Dict[str, int]:
    """Archivia le transazioni deduplicate. Nessuna scrittura contabile qui.

    Il registro operativo e' un Google Sheet write-through. Scrivere una riga
    alla volta costringeva il runtime a rileggere l'indice del foglio e a
    costruire una richiesta Google per ogni transazione; il recupero di trenta
    giorni poteva quindi superare i 512 MiB del servizio Render. Le nuove
    transazioni vengono inserite in un unico batch e quelle gia' note vengono
    riscritte soltanto quando SumUp ha davvero cambiato un campo (per esempio
    dopo un rimborso).
    """
    now = datetime.now(timezone.utc).isoformat()
    nuove = aggiornate = invariate = scartate = 0
    normalizzate: Dict[str, Dict[str, Any]] = {}
    for grezza in grezze:
        transazione = normalizza_transazione(grezza, merchant_code)
        if transazione is None:
            scartate += 1
            continue
        # L'ultima occorrenza della stessa chiave nella risposta e' quella piu'
        # aggiornata; non deve comunque generare due righe nel foglio.
        normalizzate[transazione["chiave"]] = transazione

    if not normalizzate:
        return {
            "nuove": 0, "aggiornate": 0, "invariate": 0,
            "scartate": scartate,
        }

    collection = db[COLL_TRANSAZIONI]
    cursore = collection.find(
        {"chiave": {"$in": list(normalizzate)}}, {"_id": 0}
    )
    if hasattr(cursore, "to_list"):
        esistenti = await cursore.to_list(len(normalizzate))
    else:
        esistenti = [documento async for documento in cursore]
    per_chiave = {
        str(documento.get("chiave") or ""): documento
        for documento in esistenti
        if documento.get("chiave")
    }

    da_inserire: List[Dict[str, Any]] = []
    da_aggiornare: List[Dict[str, Any]] = []
    for chiave, transazione in normalizzate.items():
        esistente = per_chiave.get(chiave)
        if esistente is None:
            da_inserire.append({
                **transazione, "created_at": now, "updated_at": now,
            })
            continue
        if any(esistente.get(campo) != valore
               for campo, valore in transazione.items()):
            da_aggiornare.append(transazione)
        else:
            invariate += 1

    if da_inserire:
        await collection.insert_many(da_inserire)
        nuove = len(da_inserire)

    # In regime ordinario questa lista contiene zero o poche rettifiche. La
    # prima acquisizione, che e' il caso voluminoso, e' gia' stata scritta con
    # una sola operazione ``insert_many``.
    for transazione in da_aggiornare:
        await collection.update_one(
            {"chiave": transazione["chiave"]},
            {"$set": {**transazione, "updated_at": now}},
        )
        aggiornate += 1

    return {
        "nuove": nuove,
        "aggiornate": aggiornate,
        "invariate": invariate,
        "scartate": scartate,
    }


async def transazioni_del_periodo(db, dal: str, al: str) -> List[Dict[str, Any]]:
    cursore = db[COLL_TRANSAZIONI].find(
        {"data": {"$gte": dal, "$lte": al}}, {"_id": 0}
    )
    if hasattr(cursore, "to_list"):
        return await cursore.to_list(100000)
    return [t async for t in cursore]


async def _transazioni_per_codici(
    db, codici: Iterable[str]
) -> List[Dict[str, Any]]:
    codici = sorted({str(c or "").strip() for c in codici if str(c or "").strip()})
    if not codici:
        return []
    cursore = db[COLL_TRANSAZIONI].find(
        {"transaction_code": {"$in": codici}}, {"_id": 0}
    )
    if hasattr(cursore, "to_list"):
        righe = await cursore.to_list(100000)
    else:
        righe = [t async for t in cursore]
    # Una sincronizzazione ripetuta o un vecchio schema non deve far contare
    # due volte la stessa vendita.
    uniche: Dict[str, Dict[str, Any]] = {}
    for riga in righe:
        chiave = str(riga.get("chiave") or riga.get("transaction_id") or "")
        if chiave:
            uniche[chiave] = riga
    return list(uniche.values())


async def sincronizza_payouts(
    db, dal: str, al: str, *,
    righe: Optional[Iterable[Dict[str, Any]]] = None,
    actor: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Collega vendite -> riferimento payout -> Mastercard SumUp.

    Nessun abbinamento usa l'importo. Il solo legame ammesso e' il
    ``transaction_code`` dichiarato da SumUp; il movimento composto e'
    identificato dal ``reference`` comune alle righe finanziarie.
    """
    from app.services import sumup_payout

    if righe is None:
        righe = await scarica_payouts(dal, al)
    gruppi = raggruppa_payouts(righe)
    risultati: List[Dict[str, Any]] = []
    codici_collegati = 0
    for gruppo in gruppi:
        codici = gruppo.get("transaction_codes") or []
        transazioni = await _transazioni_per_codici(db, codici)
        payout_id = gruppo["payout_id"]
        transazioni_collegate = []
        for transazione in transazioni:
            copia = {**transazione, "payout_id": payout_id}
            transazioni_collegate.append(copia)

        if codici:
            esito_update = await db[COLL_TRANSAZIONI].update_many(
                {"transaction_code": {"$in": codici}},
                {"$set": {
                    "payout_id": payout_id,
                    "payout_date": gruppo.get("date"),
                    "payout_updated_at": datetime.now(timezone.utc).isoformat(),
                }},
            )
            codici_collegati += int(getattr(esito_update, "modified_count", 0) or 0)

        if gruppo.get("solo_rettifica"):
            esito = await sumup_payout.registra_rettifica_payout(
                db, gruppo, transazioni=transazioni_collegate
            )
        else:
            esito = await sumup_payout.registra_payout(
                db,
                {
                    "id": payout_id,
                    "date": gruppo.get("date"),
                    "amount": gruppo.get("payout_amount"),
                    "fee_total": gruppo.get("fee_total"),
                    "currency": gruppo.get("currency"),
                    "status": gruppo.get("status"),
                    "reference": gruppo.get("reference"),
                },
                transazioni=transazioni_collegate,
                actor=actor,
            )
            # Conserva la prova finanziaria aggregata senza salvare chiavi o
            # payload superflui dell'API.
            await db[COLL_PAYOUT].update_one(
                {"payout_id": payout_id},
                {"$set": {
                    "record_ids": gruppo.get("record_ids") or [],
                    "records": gruppo.get("records") or 0,
                    "transaction_codes": codici,
                    "tipi": gruppo.get("tipi") or [],
                    "movimento_mastercard": gruppo.get("movimento_mastercard"),
                    "commissione_api": gruppo.get("fee_total"),
                }},
            )
        risultati.append({
            "payout_id": payout_id,
            "data": gruppo.get("date"),
            "tipo": "rettifica" if gruppo.get("solo_rettifica") else "payout",
            "righe_api": gruppo.get("records") or 0,
            "transazioni_collegate": len(transazioni_collegate),
            "stato_riconciliazione": esito.get("stato_riconciliazione"),
            "quadra": esito.get("quadra"),
        })

    return {
        "success": True,
        "dal": dal,
        "al": al,
        "righe_api": sum(int(g.get("records") or 0) for g in gruppi),
        "gruppi": risultati,
        "payout": sum(g.get("tipo") == "payout" for g in risultati),
        "rettifiche": sum(g.get("tipo") == "rettifica" for g in risultati),
        "transazioni_collegate": codici_collegati,
        "accrediti_per_giorno": accrediti_payout_per_giorno(gruppi),
    }


async def sincronizza(db, dal: str, al: str,
                      *, grezze: Optional[Iterable[Dict[str, Any]]] = None,
                      actor: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Scarica e archivia le evidenze SumUp dell'intervallo.

    Rieseguirla sullo stesso intervallo non produce duplicati: le transazioni
    sono deduplicate per chiave e la chiusura giornaliera aggiorna l'evidenza
    del circuito invece di affiancarne una nuova. Le vendite non generano
    movimenti di Prima Nota: soltanto un payout distinto puo' provare il
    successivo movimento finanziario.
    """
    from app.services.scritture_contabili import (
        FONTE_API,
        registra_chiusura_pos_reale,
    )

    _, merchant = await _credenziali()
    if grezze is None:
        grezze = await scarica_transazioni(dal, al)

    conteggi = await salva_transazioni(db, grezze, merchant)
    # Si riaggrega da database e non dal solo scaricato: cosi' una pagina
    # arrivata in una sincronizzazione precedente resta nel totale del giorno.
    giornate = aggrega_per_giorno(await transazioni_del_periodo(db, dal, al))

    # Una risposta API completa senza transazioni e' uno ZERO accertato, non
    # un dato mancante. Materializziamo quindi anche le giornate vuote
    # dell'intervallo richiesto: la pagina puo' distinguere "0,00 SumUp" da
    # "API non ancora sincronizzata". Una sincronizzazione successiva della
    # stessa giornata aggiorna lo zero in modo idempotente se arrivano vendite.
    corrente = date.fromisoformat(dal)
    ultimo = date.fromisoformat(al)
    while corrente <= ultimo:
        giorno = corrente.isoformat()
        giornate.setdefault(giorno, {
            "data": giorno,
            "vendite": 0.0,
            "rimborsi": 0.0,
            "chargeback": 0.0,
            "netto": 0.0,
            "transazioni": 0,
        })
        corrente += timedelta(days=1)

    scritte: List[Dict[str, Any]] = []
    for data in sorted(giornate):
        giorno = giornate[data]
        esito = await registra_chiusura_pos_reale(
            db, data, giorno["netto"],
            gestore=GESTORE,
            fonte=FONTE_API,
            note=(f"Sincronizzazione API SumUp: {giorno['transazioni']} "
                  f"transazioni, rimborsi {giorno['rimborsi']:.2f}"),
            actor=actor or {"user_id": "api_sumup", "name": "Sincronizzazione SumUp"},
            solo_evidenza=True,
        )
        scritte.append({**giorno, "action": esito.get("action")})

    # I payout sono datati dopo le vendite. Una sincronizzazione storica deve
    # quindi cercare fino a sette giorni oltre il limite richiesto, senza mai
    # spingersi nel futuro.
    fine_payout = min(
        date.today(), date.fromisoformat(al) + timedelta(days=7)
    ).isoformat()
    # Le vendite e i payout provengono da endpoint SumUp distinti e possono
    # avere autorizzazioni diverse. Un errore del solo endpoint payout non deve
    # annullare le chiusure POS gia' verificate e scritte: in quel caso il
    # credito verso SumUp resta esplicitamente in attesa di riconciliazione
    # Mastercard e l'errore viene restituito al chiamante.
    try:
        payouts = await sincronizza_payouts(
            db, dal, fine_payout, actor=actor,
        )
    except (httpx.HTTPError, ValueError, SumUpNonConfigurato) as exc:
        logger.warning(
            "SumUp: transazioni sincronizzate ma payout non disponibili: %s",
            exc,
        )
        payouts = {
            "success": False,
            "dal": dal,
            "al": fine_payout,
            "errore": "Payout Mastercard SumUp non disponibili",
            "dettaglio": str(exc),
            "payouts": [],
        }

    return {
        "success": True,
        "dal": dal,
        "al": al,
        "transazioni": conteggi,
        "giornate": scritte,
        "totale_netto": round(sum(g["netto"] for g in scritte), 2),
        "payouts": payouts,
    }
