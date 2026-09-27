"""Versamenti e prelievi di contante: riconosciuti dall'estratto conto.

Il titolare: «non devo far riparare niente all'applicazione — nell'estratto
conto c'e' il segno, la descrizione e l'importo, quindi non vedo perche'
dovrebbe sbagliare». Ha ragione, e questo modulo sostituisce il vecchio
comando «Ripara versamenti», che era un bottone da premere a mano e che il
15/09/2026 era stato spento perche' sbagliava.

**Perche' sbagliava, e perche' qui non succede.** In Prima Nota Cassa una
gamba del versamento puo' esserci gia': non scritta a mano — il titolare non
ne registra nessuno a mano (20/09/2026) — ma portata dall'integrazione
legacy, che il 15/09/2026 ha importato 18 righe «Versamento contanti in
banca» dall'archivio CeraldiFatture. Il vecchio codice creava comunque la
gamba di cassa, e il contante usciva due volte. Qui la gamba si cerca
**prima**: se c'e' gia' si collega, non si riscrive.

E si collega **solo a una riga che si dichiara versamento** (categoria di
trasferimento, oppure la parola in descrizione). Cercarla per solo importo e
data, come faceva la prima versione di questo modulo, e' la stessa regola
vietata altrove: il giorno in cui un pagamento fornitore in contanti coincide
d'importo con un versamento, quella riga verrebbe presa, la sua categoria
sovrascritta con `trasferimento_interno` e il pagamento sparirebbe come tale.

Le due gambe:
- **versamento** (entrata in banca): uscita da Cassa, entrata in Banca;
- **prelievo** (uscita dalla banca): uscita da Banca, entrata in Cassa.

Sono due movimenti speculari collegati da `trasferimento_collegato_id`, con
categoria `trasferimento_interno` e lo stesso `operation_id`, come prescrive
CLAUDE.md — non un flag sul singolo movimento.

Uno **storno** non e' un secondo versamento: e' una rettifica della banca, e
resta fuori.

**Un versamento e' un'operazione della banca, non una riga d'archivio.** Lo
stesso versamento arriva dal vecchio archivio, dai CSV «Elenco entrate/uscite»
e dalla lettura diretta della banca: tre righe di estratto conto, un solo
contante uscito. Fino al 26/09/2026 il motore scriveva una coppia per copia
(44 uscite di cassa per 27 versamenti). Ora conta le operazioni vere per
giorno e importo (il massimo per fonte), tiene altrettante coppie, toglie per
id le gambe in piu' nate dai motori e non tocca quelle scritte a mano.

Rileggere lo stesso estratto, o riceverne un'altra copia, non scrive niente.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.services.mapping_piano_conti import conto_tesoreria
from app.services.scritture_contabili import scrivi_movimento_se_assente

logger = logging.getLogger(__name__)

CATEGORIA = "trasferimento_interno"
# Giorni fra l'uscita del contante dal negozio e la data di contabilizzazione
# in banca. Tre coprono anche il versamento del venerdi' registrato il lunedi'.
GIORNI_TOLLERANZA = 3

#: Le categorie con cui una riga di Prima Nota **dichiara** di essere una
#: gamba di trasferimento. Misurate in produzione il 20/09/2026: 80 righe
#: `trasferimento_interno` e 36 `Versamento Banca`, nessun altro valore.
CATEGORIE_TRASFERIMENTO = frozenset({"trasferimento_interno", "versamento banca"})

#: Chi non ha la categoria lo dice nella descrizione: le 18 righe legacy sono
#: «Versamento contanti in banca — Da estratto conto».
PAROLE_TRASFERIMENTO = ("versament", "prelev", "preliev")


def _data_iso(doc: Dict[str, Any]) -> str:
    grezza = str(doc.get("data") or doc.get("date") or doc.get("data_contabile") or "")
    if len(grezza) >= 10 and grezza[4] == "-":
        return grezza[:10]
    if len(grezza) == 10 and grezza[2] == "/":
        giorno, mese, anno = grezza.split("/")
        return f"{anno}-{mese}-{giorno}"
    return grezza[:10]


def _importo(doc: Dict[str, Any]) -> float:
    try:
        return round(abs(float(doc.get("importo") or doc.get("amount") or 0)), 2)
    except (TypeError, ValueError):
        return 0.0


def _verso(doc: Dict[str, Any]) -> str:
    valore = str(doc.get("tipo") or doc.get("type") or "").strip().lower()
    if valore in {"entrata", "credito", "credit", "dare"}:
        return "entrata"
    if valore in {"uscita", "debito", "debit", "avere"}:
        return "uscita"
    try:
        return "entrata" if float(doc.get("importo") or 0) > 0 else "uscita"
    except (TypeError, ValueError):
        return ""


def _id_ec(doc: Dict[str, Any]) -> str:
    for campo in ("id", "movement_id", "transaction_id", "_id"):
        valore = doc.get(campo)
        if valore:
            return str(valore)
    return ""


def classifica(movimento_ec: Dict[str, Any]) -> Optional[str]:
    """«versamento», «prelievo» o None. Il riconoscimento e' uno solo.

    Le funzioni stanno in `routers/bank/estratto_conto.py` perche' le usa
    anche la categorizzazione: qui si importano, non si riscrivono.
    """
    from app.routers.bank.estratto_conto import (
        is_prelievo_contanti,
        is_storno_versamento,
        is_versamento_contanti,
    )

    descrizione = str(
        movimento_ec.get("descrizione_originale")
        or movimento_ec.get("descrizione")
        or movimento_ec.get("description")
        or ""
    )
    if is_storno_versamento(descrizione):
        return None

    verso = _verso(movimento_ec)
    # Il segno deve concordare con la causale: un «versamento» in uscita non
    # e' un versamento, e trattarlo come tale ribalterebbe il movimento.
    if is_versamento_contanti(descrizione) and verso == "entrata":
        return "versamento"
    if is_prelievo_contanti(descrizione) and verso == "uscita":
        return "prelievo"
    return None


def _si_dichiara_trasferimento(riga: Dict[str, Any]) -> bool:
    """`True` se questa riga di Prima Nota dice di essere un trasferimento.

    Una riga che non lo dice non viene agganciata: si crea la gamba nuova.
    Meglio una gamba in piu' da verificare che un pagamento fornitore
    trasformato in versamento senza che nessuno se ne accorga.
    """
    categoria = str(riga.get("categoria") or "").strip().lower()
    if categoria in CATEGORIE_TRASFERIMENTO:
        return True
    testo = " ".join(
        str(riga.get(campo) or "")
        for campo in ("categoria", "descrizione", "description", "causale", "dettaglio")
    ).lower()
    return any(parola in testo for parola in PAROLE_TRASFERIMENTO)


#: Chi scrive le gambe da solo. Solo queste righe si possono togliere quando
#: sono in piu' rispetto alle operazioni vere della banca: una riga scritta a
#: mano non si tocca mai, si segnala.
SOURCES_MOTORE = frozenset({
    "estratto_conto_versamento", "estratto_conto_prelievo",
    "legacy_versamenti", "riconciliazione_ec_versamento",
})
#: La gamba bancaria che nasce dalla registrazione manuale in cassa, prima che
#: la banca contabilizzi: porta la data del negozio, non quella della banca.
SOURCE_ATTESA_BANCA = "versamento_cassa_in_attesa"
MOTIVO_DOPPIONE = "doppione_versamento_contanti"
MOTIVO_NON_NOSTRO = "versamento_non_nostro_stornato_dalla_banca"

#: Versamenti che la banca ha accreditato per errore sul nostro conto e poi
#: stornato: il contante non e' mai uscito dalla nostra cassa, quindi non
#: nasce nessuna gamba. Si elencano uno per uno, per decisione del titolare:
#: uno storno non si abbina da solo a un versamento per solo importo.
#: Chiave: (giorno di contabilizzazione, importo in centesimi, verso).
VERSAMENTI_ANNULLATI = {
    # Titolare, 26/09/2026: il cassiere di un altro cliente lo ha versato sul
    # nostro conto; stornato il 13/07 con «STORNO SCRITTURE - STORNO PER
    # ERRATO CONTO». «Elimina questo movimento, non serve averlo».
    ("2026-07-10", 310000, "versamento"): "errore del cassiere BPM, stornato il 13/07/2026",
}

_ATTIVO = {"status": {"$nin": ["deleted", "archived"]}}
_CAMPI_PRIMA_NOTA = {
    "_id": 0, "id": 1, "data": 1, "importo": 1, "tipo": 1, "categoria": 1,
    "descrizione": 1, "description": 1, "causale": 1, "dettaglio": 1, "source": 1,
    "operation_id": 1, "trasferimento_collegato_id": 1, "prima_nota_cassa_id": 1,
    "estratto_conto_id": 1, "movimento_ec_id": 1, "provvisorio": 1,
}


def _fonte_ec(movimento_ec: Dict[str, Any]) -> str:
    """Da quale export viene la riga: le copie di fonti diverse sono la stessa
    operazione, le righe uguali della stessa fonte sono operazioni diverse."""
    return str(
        movimento_ec.get("source_filename")
        or movimento_ec.get("fonte")
        or movimento_ec.get("fonte_documento")
        or ""
    )


def _nel_raggio(data: str, centro: str, giorni: int) -> bool:
    try:
        a = datetime.strptime(data, "%Y-%m-%d")
        b = datetime.strptime(centro, "%Y-%m-%d")
    except ValueError:
        return False
    return abs((a - b).days) <= giorni


def _ordine_di_tenuta(riga: Dict[str, Any]) -> tuple:
    """Quale gamba tenere quando ce ne sono piu' delle operazioni vere.

    Prima quella scritta a mano (non e' nostra da togliere), poi quella gia'
    collegata all'altra gamba, poi la piu' recente delle fonti automatiche
    (la stessa che il giro scriverebbe oggi), infine l'id: stesso esito a ogni giro.
    """
    source = str(riga.get("source") or "")
    rango = {"estratto_conto_versamento": 0, "estratto_conto_prelievo": 0,
             "legacy_versamenti": 1, "riconciliazione_ec_versamento": 2}
    return (
        source in SOURCES_MOTORE,
        not (riga.get("trasferimento_collegato_id") or riga.get("prima_nota_cassa_id")),
        rango.get(source, 0),
        str(riga.get("id") or ""),
    )


def _gruppi(movimenti: List[Dict[str, Any]], anno: Optional[int], conteggi: Dict[str, int],
            esiti: List[Dict[str, Any]]) -> Dict[tuple, List[Dict[str, Any]]]:
    """Le righe di estratto conto riconosciute, per operazione (giorno, importo, verso)."""
    gruppi: Dict[tuple, List[Dict[str, Any]]] = {}
    for movimento_ec in movimenti:
        if str(movimento_ec.get("status") or "") in {"deleted", "archived"}:
            continue
        tipo = classifica(movimento_ec)
        if not tipo:
            continue
        conteggi["esaminati"] += 1
        data = _data_iso(movimento_ec)
        importo = _importo(movimento_ec)
        ec_id = _id_ec(movimento_ec)
        if not data or importo <= 0 or not ec_id:
            # Senza una delle tre non c'e' prova: si segnala, non si indovina.
            conteggi["senza_data_o_importo"] += 1
            esiti.append({"ec_id": ec_id, "tipo": tipo, "esito": "dati_insufficienti",
                          "data": data, "importo": importo})
            continue
        if anno and not data.startswith(f"{anno}-"):
            continue
        gruppi.setdefault((data, int(round(importo * 100)), tipo), []).append(movimento_ec)
    return gruppi


def _quante_operazioni(righe: List[Dict[str, Any]]) -> int:
    """Quanti versamenti veri ci sono dietro le righe dello stesso giorno e importo.

    Lo stesso versamento arriva dal vecchio archivio, dai CSV della banca e
    dalla lettura diretta (Enable Banking): tre righe, un versamento. Due
    versamenti uguali lo stesso giorno invece compaiono due volte **nello
    stesso export**. Il numero vero e' quindi il massimo per fonte, come in
    ``doppioni_estratto_conto.accoppia``.
    """
    per_fonte: Dict[str, int] = {}
    for riga in righe:
        chiave = _fonte_ec(riga)
        per_fonte[chiave] = per_fonte.get(chiave, 0) + 1
    return max(per_fonte.values())


async def _togli_doppione(db, collezione: str, riga: Dict[str, Any], adesso: str,
                          motivo: str = MOTIVO_DOPPIONE) -> None:
    """Soft delete per id: la riga resta per audit, esce da elenchi e saldi."""
    await db[collezione].update_one(
        {"id": riga["id"]},
        {"$set": {"status": "deleted", "deleted_at": adesso,
                  "deleted_reason": motivo, "deleted_by": "versamenti_contanti"}},
    )


async def riconosci_versamenti(
    db, *, anno: Optional[int] = None, dry_run: bool = True,
    giorni_tolleranza: int = GIORNI_TOLLERANZA,
) -> Dict[str, Any]:
    """Una coppia cassa/banca per ogni versamento o prelievo vero dell'estratto conto.

    Per ogni operazione (giorno, importo, verso) conta quante ce ne sono
    davvero (``_quante_operazioni``), tiene altrettante gambe gia' scritte,
    toglie quelle in piu' nate dai motori e scrive le mancanti. Rieseguirlo
    non scrive niente. ``dry_run`` per difetto: dice cosa farebbe.
    """
    from app.database import Collections

    movimenti = await db[Collections.BANK_STATEMENTS].find({}, {"_id": 0}).to_list(50000)
    esiti: List[Dict[str, Any]] = []
    conteggi = {
        "esaminati": 0, "versamenti": 0, "prelievi": 0, "copie_estratto_conto": 0,
        "gambe_cassa_create": 0, "gambe_cassa_collegate": 0, "gambe_banca_create": 0,
        "gia_registrati": 0, "senza_data_o_importo": 0,
        "doppioni_banca_tolti": 0, "doppioni_cassa_tolti": 0, "da_verificare": 0,
        "annullati_dal_titolare": 0,
    }
    gruppi = _gruppi(movimenti, anno, conteggi, esiti)
    if not gruppi:
        return {"dry_run": dry_run, "anno": anno, "giorni_tolleranza": giorni_tolleranza,
                **conteggi, "movimenti": esiti[:500],
                "eseguito_il": datetime.now(timezone.utc).isoformat()}

    # Una lettura per registro, non una per movimento.
    banca = await db["prima_nota_banca"].find(_ATTIVO, _CAMPI_PRIMA_NOTA).to_list(None)
    cassa = await db["prima_nota_cassa"].find(_ATTIVO, _CAMPI_PRIMA_NOTA).to_list(None)
    cassa_per_id = {r.get("id"): r for r in cassa if r.get("id")}
    usate: set = set()
    adesso = datetime.now(timezone.utc).isoformat()

    for (data, centesimi, tipo), righe in sorted(gruppi.items()):
        importo = centesimi / 100
        n = _quante_operazioni(righe)
        conteggi["copie_estratto_conto"] += len(righe) - n
        annullato = VERSAMENTI_ANNULLATI.get((data, centesimi, tipo))
        if annullato:
            n -= 1
            conteggi["annullati_dal_titolare"] += 1
            esiti.append({"tipo": tipo, "data": data, "importo": importo,
                          "esito": "annullato_dal_titolare", "motivo": annullato})
        motivo_extra = MOTIVO_NON_NOSTRO if annullato else MOTIVO_DOPPIONE
        conteggi["versamenti" if tipo == "versamento" else "prelievi"] += n
        tipo_cassa, tipo_banca = ("uscita", "entrata") if tipo == "versamento" else ("entrata", "uscita")
        righe = sorted(righe, key=lambda r: (_fonte_ec(r) != "enable_banking", _id_ec(r)))
        descrizione = str(righe[0].get("descrizione_originale") or righe[0].get("descrizione") or "")

        def _stessa(riga, verso):
            return (riga.get("id") not in usate and riga.get("tipo") == verso
                    and abs(_importo(riga) - importo) <= 0.005 and _si_dichiara_trasferimento(riga))

        # ── gambe bancarie: stesso giorno; l'attesa manuale entro la finestra
        candidati_banca = sorted(
            (r for r in banca if _stessa(r, tipo_banca) and (
                _data_iso(r) == data
                or (r.get("source") == SOURCE_ATTESA_BANCA and not r.get("estratto_conto_id")
                    and _nel_raggio(_data_iso(r), data, giorni_tolleranza)))),
            key=_ordine_di_tenuta,
        )
        tenute_banca = candidati_banca[:n]
        for extra in candidati_banca[n:]:
            if extra.get("source") in SOURCES_MOTORE:
                conteggi["doppioni_banca_tolti"] += 1
                esiti.append({"tipo": tipo, "data": data, "importo": importo,
                              "esito": "doppione_banca_tolto", "id": extra.get("id")})
                if not dry_run:
                    await _togli_doppione(db, "prima_nota_banca", extra, adesso, motivo_extra)
            else:
                conteggi["da_verificare"] += 1
                esiti.append({"tipo": tipo, "data": data, "importo": importo,
                              "esito": "banca_in_piu_scritta_a_mano", "id": extra.get("id")})
        usate.update(r.get("id") for r in candidati_banca)

        # ── gambe di cassa: quelle collegate alle gambe bancarie tenute, poi
        # quelle dello stesso giorno che si dichiarano trasferimento.
        collegate = []
        for b in tenute_banca:
            for cid in (b.get("trasferimento_collegato_id"), b.get("prima_nota_cassa_id")):
                c = cassa_per_id.get(cid)
                if c is not None and _stessa(c, tipo_cassa) and c not in collegate:
                    collegate.append(c)
        operazioni_tenute = {b.get("operation_id") for b in tenute_banca if b.get("operation_id")}
        ids_banca_tenute = {b.get("id") for b in tenute_banca}
        stesso_giorno = sorted(
            (c for c in cassa if c not in collegate and _stessa(c, tipo_cassa) and (
                _data_iso(c) == data
                or c.get("trasferimento_collegato_id") in ids_banca_tenute
                or (c.get("operation_id") and c.get("operation_id") in operazioni_tenute))),
            key=_ordine_di_tenuta,
        )
        candidati_cassa = collegate + stesso_giorno
        tenute_cassa = candidati_cassa[:n]
        for extra in candidati_cassa[n:]:
            if extra.get("source") in SOURCES_MOTORE:
                conteggi["doppioni_cassa_tolti"] += 1
                esiti.append({"tipo": tipo, "data": data, "importo": importo,
                              "esito": "doppione_cassa_tolto", "id": extra.get("id")})
                if not dry_run:
                    await _togli_doppione(db, "prima_nota_cassa", extra, adesso, motivo_extra)
            else:
                conteggi["da_verificare"] += 1
                esiti.append({"tipo": tipo, "data": data, "importo": importo,
                              "esito": "cassa_in_piu_scritta_a_mano", "id": extra.get("id")})
        usate.update(c.get("id") for c in candidati_cassa)

        # ── accoppia le tenute e scrive le mancanti
        cassa_libere = list(tenute_cassa)
        for indice in range(n):
            b = tenute_banca[indice] if indice < len(tenute_banca) else None
            c = None
            if b is not None:
                for candidata in cassa_libere:
                    if candidata.get("id") in (b.get("trasferimento_collegato_id"), b.get("prima_nota_cassa_id")) \
                            or candidata.get("trasferimento_collegato_id") == b.get("id"):
                        c = candidata
                        break
            if c is None and cassa_libere:
                # Una gamba di cassa gia' collegata a un'altra banca non si ruba.
                c = next((x for x in cassa_libere if not x.get("trasferimento_collegato_id")
                          or x.get("trasferimento_collegato_id") == (b or {}).get("id")), None)
            if c is None:
                # La cassa scritta a mano il giorno in cui il contante esce dal negozio.
                c = next((x for x in cassa if x.get("id") not in usate and _stessa(x, tipo_cassa)
                          and not x.get("trasferimento_collegato_id") and not x.get("operation_id")
                          and _nel_raggio(_data_iso(x), data, giorni_tolleranza)), None)
                if c is not None:
                    usate.add(c.get("id"))
            if c is not None and c in cassa_libere:
                cassa_libere.remove(c)

            ec = righe[indice] if indice < len(righe) else righe[0]
            ec_id = _id_ec(ec)
            operazione = ((b or {}).get("operation_id") or (c or {}).get("operation_id")
                          or f"{tipo}:{ec_id}")
            esito = {"ec_id": ec_id, "tipo": tipo, "data": data, "importo": importo}
            if b is not None and b.get("source") == SOURCE_ATTESA_BANCA and not dry_run:
                # L'attesa diventa il movimento: data della banca, prova collegata.
                await db["prima_nota_banca"].update_one({"id": b["id"]}, {"$set": {
                    "data": data, "estratto_conto_id": ec_id, "provvisorio": False,
                    "riconciliato": True, "updated_at": adesso}})
                b = {**b, "source": "", "estratto_conto_id": ec_id}
            if b is not None and c is not None and b.get("trasferimento_collegato_id") == c.get("id") \
                    and c.get("trasferimento_collegato_id") == b.get("id"):
                conteggi["gia_registrati"] += 1
                esiti.append({**esito, "esito": "gia_registrato", "id_cassa": c["id"], "id_banca": b["id"]})
                continue

            if dry_run:
                esiti.append({**esito, "esito": "scriverebbe", "banca_esistente_id": (b or {}).get("id", ""),
                              "cassa_esistente_id": (c or {}).get("id", "")})
                continue

            comune = {
                "data": data, "importo": importo, "categoria": CATEGORIA,
                "operation_id": operazione, "movimento_ec_id": ec_id,
                "source": f"estratto_conto_{tipo}",
            }
            verso_banca = "contanti dalla cassa" if tipo == "versamento" else "contanti verso la cassa"
            verso_cassa = "contanti in banca" if tipo == "versamento" else "contanti dalla banca"
            if b is None:
                id_banca, _ = await scrivi_movimento_se_assente(
                    db, "banca", {"operation_id": operazione},
                    # La contropartita di un trasferimento interno e' l'altro
                    # conto di tesoreria: dalla categoria non si deduce.
                    {**comune, "tipo": tipo_banca,
                     "conto_contropartita": conto_tesoreria("cassa"),
                     "descrizione": f"{tipo.capitalize()} {verso_banca} — {descrizione}".strip(" —")},
                )
                conteggi["gambe_banca_create"] += 1
            else:
                id_banca = b["id"]
            if c is None:
                id_cassa, _ = await scrivi_movimento_se_assente(
                    db, "cassa", {"operation_id": operazione},
                    {**comune, "tipo": tipo_cassa, "trasferimento_collegato_id": id_banca,
                     "conto_contropartita": conto_tesoreria("banca"),
                     "descrizione": f"{tipo.capitalize()} {verso_cassa} — {descrizione}".strip(" —")},
                )
                conteggi["gambe_cassa_create"] += 1
                esito["esito"] = "creata"
            else:
                id_cassa = c["id"]
                await db["prima_nota_cassa"].update_one({"id": id_cassa}, {"$set": {
                    "operation_id": operazione, "movimento_ec_id": c.get("movimento_ec_id") or ec_id,
                    "trasferimento_collegato_id": id_banca, "categoria": CATEGORIA}})
                conteggi["gambe_cassa_collegate"] += 1
                esito["esito"] = "collegata"
            await db["prima_nota_banca"].update_one({"id": id_banca}, {"$set": {
                "trasferimento_collegato_id": id_cassa, "operation_id": operazione}})
            esiti.append({**esito, "id_cassa": id_cassa, "id_banca": id_banca})

    return {
        "dry_run": dry_run,
        "anno": anno,
        "giorni_tolleranza": giorni_tolleranza,
        **conteggi,
        "movimenti": esiti[:500],
        "eseguito_il": adesso,
    }
