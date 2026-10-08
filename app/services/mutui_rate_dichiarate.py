"""Rate di mutuo «pagate, dichiarato dal titolare».

Il titolare puo' dire che le rate scadute di un mutuo sono state pagate anche
quando non ha gli estratti che lo proverebbero. E' una **dichiarazione**, non
una prova: vive in una collezione sua (``mutui_rate_dichiarate``, una riga per
mutuo e numero di rata, con lo storico), mai dentro il piano (un nuovo PDF del
piano la cancellerebbe) e mai fusa con la prova bancaria.

Ordine delle prove, dalla piu' forte: riga di Prima Nota Banca della rata
(``banca``), quietanza (``quietanza``), estratto annuale della banca
(``estratto_annuale``), dichiarazione del titolare, «Pagata» scritto sul piano
(``piano``, un'istantanea del PDF, non una prova). Una prova successiva
**sostituisce** la dichiarazione (la riga resta con stato
``sostituita_da_prova`` e lo storico), come per le fatture dichiarate
(``pagamenti_dichiarati_titolare``): mai due verita' per la stessa rata.

Nessun effetto contabile: la dichiarazione non scrive nel libro giornale ne'
in Prima Nota. Il movimento vero di una rata entra dalla proiezione bancaria
(``proiezione_bancaria``: numero del mutuo e scadenza in causale) e li' nasce
anche la scrittura; una rata dichiarata e mai provata non inventa ne' costi
ne' movimenti (l'importo del piano e' una stima se il tasso e' variabile).
Anno attivo e anni passati sono trattati allo stesso modo, e l'anteprima dice
quante rate sono dell'anno attivo.

**Una prova regge la rata solo se l'importo torna.** Identita' = numero del
mutuo e scadenza, ma l'importo pagato (riga di banca, quietanza, estratto
annuale) si confronta con quello della rata al centesimo, in ``Decimal``. Il
tasso e' variabile e il piano e' un'istantanea, quindi lo scarto entro
``TOLLERANZA_IMPORTO_CENTS`` (5,00 euro, la soglia «PARZIALE» dell'F24) resta
una prova buona e la differenza si mostra; oltre, la rata e' ``da_verificare``
con la differenza visibile, mai «Pagata»: un pagamento parziale non vale come
pagamento. Sui dati veri lo scarto e' costante (2,75 euro sul mutuo Retail) e
rientra. Un importo non leggibile su un lato non e' una prova.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Optional

from app.services.proiezione_bancaria import _cifre_mutuo, _data_gma

logger = logging.getLogger(__name__)

COLL_DICHIARAZIONI = "mutui_rate_dichiarate"
COLL_PIANI = "mutui_piani_documentali"

STATO_DICHIARATA = "pagata_dichiarata_titolare"
STATO_RITIRATA = "ritirata"
STATO_SOSTITUITA = "sostituita_da_prova"

PROVA_BANCA = "banca"
PROVA_QUIETANZA = "quietanza"
PROVA_ESTRATTO = "estratto_annuale"
PROVA_DICHIARATA = "dichiarata_titolare"
PROVA_PIANO = "piano"
PROVE_REALI = (PROVA_BANCA, PROVA_QUIETANZA, PROVA_ESTRATTO)

# Scarto ammesso fra l'importo della rata sul piano e quello pagato (centesimi).
# Il piano e' l'importo certo solo a tasso fisso, e nel piano non c'e' scritto
# se lo e': finche' nessuno lo dichiara, vale per tutti la stessa tolleranza.
TOLLERANZA_IMPORTO_CENTS = 500

# Motivi a scelta: nessun testo libero salvo «Altro» (le mani sporche).
MOTIVI = {
    "estratti_precedenti_non_disponibili": "Estratti precedenti non disponibili",
    "pagate_da_altro_conto": "Pagate da un altro conto",
    "altro": "Altro (scrivi tu)",
}
MOTIVO_DEFAULT = "estratti_precedenti_non_disponibili"
MOTIVI_RITIRO = {
    "dichiarazione_errata": "Dichiarazione errata",
    "rate_non_pagate": "Le rate non risultano pagate",
    "altro": "Altro (scrivi tu)",
}

_PROIEZIONE_BANCA = {
    "_id": 0, "id": 1, "numero_mutuo": 1, "rata_scadenza": 1, "movimento_bancario_id": 1,
    "status": 1, "entity_status": 1, "data": 1, "importo": 1,
}


def _ora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cents(valore: Any) -> int:
    if valore is None:
        return 0
    try:
        return int((Decimal(str(valore)) * 100).to_integral_value())
    except Exception as exc:  # noqa: BLE001 - dato non leggibile: si dice quale, non si nasconde
        logger.warning("Importo rata mutuo non leggibile (%r, %s): contato 0", valore, type(exc).__name__)
        return 0


def _cents_o_none(valore: Any) -> Optional[int]:
    """Centesimi, oppure ``None`` se il valore manca o non si legge (mai 0 di comodo)."""
    if valore is None or valore == "":
        return None
    try:
        return int((Decimal(str(valore)) * 100).to_integral_value())
    except Exception as exc:  # noqa: BLE001
        logger.warning("Importo mutuo non leggibile (%r, %s): la prova non regge", valore, type(exc).__name__)
        return None


def _importo_leggibile(valore: Any) -> bool:
    if valore is None:
        return False
    try:
        Decimal(str(valore))
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Importo totale rata mutuo non leggibile (%r, %s)", valore, type(exc).__name__)
        return False


def _euro(cents: int) -> str:
    return str((Decimal(cents) / 100).quantize(Decimal("0.01")))


def data_da_testo(valore: Any) -> Optional[date]:
    testo = str(valore or "")[:10]
    for formato in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(testo, formato).date()
        except ValueError:
            continue
    return None


def chiave_dichiarazione(cifre: str, numero_rata: Any) -> str:
    return f"mrd:{cifre}:{int(numero_rata):03d}"


# --------------------------------------------------------------------------
# Prove
# --------------------------------------------------------------------------

async def carica_prove(db) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
    """Prove per mutuo (cifre) e scadenza gg/mm/aaaa: l'elenco di ogni fonte.

    Identita' = numero del mutuo e scadenza, mai l'importo: il tasso e'
    variabile e l'importo addebitato differisce di qualche euro dal piano. Ma
    l'importo pagato resta nella prova (``importo_cents``) e lo confronta
    ``valuta_prove``: chi decide se la rata e' pagata e' ``esito_rata``, non la
    sola presenza della riga. La stessa riga letta due volte (copia, doppia
    chiave scadenza/valuta) conta una volta (``identita``).
    """
    prove: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}

    def _metti(cifre: str, scadenza: str, prova: str, identita: str, importo: Any, **extra: Any) -> None:
        if not cifre or not scadenza:
            return
        elenco = prove.setdefault(cifre, {}).setdefault(scadenza, [])
        if any(p["prova"] == prova and p["identita"] == identita for p in elenco):
            return
        cents = _cents_o_none(importo)
        # Un'uscita puo' essere scritta col segno: l'importo della rata e' sempre positivo.
        elenco.append({"prova": prova, "identita": identita,
                       "importo_cents": abs(cents) if cents is not None else None, **extra})

    righe = await db["prima_nota_banca"].find(
        {"tipo_classificazione_contabile": "rata_mutuo"}, _PROIEZIONE_BANCA,
    ).to_list(None)
    for riga in righe:
        if riga.get("status") in ("deleted", "archived") or riga.get("entity_status") == "deleted":
            continue
        _metti(_cifre_mutuo(riga.get("numero_mutuo")), _data_gma(riga.get("rata_scadenza")), PROVA_BANCA,
               str(riga.get("movimento_bancario_id") or riga.get("id")), riga.get("importo"),
               movimento_bancario_id=riga.get("movimento_bancario_id"),
               prima_nota_banca_id=riga.get("id"), data_pagamento=riga.get("data"))
    quietanze = await db["mutui_quietanze"].find(
        {}, {"_id": 0, "numero_finanziamento": 1, "data_scadenza": 1, "sha256": 1, "importo_totale": 1},
    ).to_list(None)
    for q in quietanze:
        _metti(_cifre_mutuo(q.get("numero_finanziamento")), _data_gma(q.get("data_scadenza")),
               PROVA_QUIETANZA, str(q.get("sha256")), q.get("importo_totale"), sha256=q.get("sha256"))
    estratti = await db["mutui_estratti_annuali"].find(
        {}, {"_id": 0, "numero_finanziamento": 1, "pagamenti": 1, "sha256": 1, "anno": 1},
    ).to_list(None)
    for estratto in estratti:
        cifre = _cifre_mutuo(estratto.get("numero_finanziamento"))
        for pagamento in estratto.get("pagamenti") or []:
            identita = f"{estratto.get('sha256')}:{pagamento.get('data_operazione')}:{pagamento.get('importo')}"
            # La scadenza della rata puo' slittare (festivo): vale sia quella
            # del piano scritta come scadenza sia come valuta.
            for campo in ("data_scadenza", "data_valuta"):
                _metti(cifre, _data_gma(pagamento.get(campo)), PROVA_ESTRATTO, identita,
                       pagamento.get("importo"), sha256=estratto.get("sha256"),
                       anno_estratto=estratto.get("anno"))
    return prove


def valuta_prove(
    proposte: Optional[List[Dict[str, Any]]], importo_rata_cents: Optional[int],
    tolleranza_cents: int = TOLLERANZA_IMPORTO_CENTS,
) -> Dict[str, Any]:
    """Quale prova regge la rata: la piu' forte il cui importo torna.

    Per ogni fonte vale il singolo pagamento, oppure la somma dei pagamenti
    distinti della stessa fonte (rata versata in due tempi). Importo della rata
    o del pagamento mancante: la prova non regge. Se nessuna regge,
    ``non_conforme`` porta la fonte piu' forte con la differenza (pagato meno
    rata, in centesimi) del pagamento piu' vicino.
    """
    non_conforme: Optional[Dict[str, Any]] = None
    for fonte in PROVE_REALI:
        della_fonte = [p for p in (proposte or []) if p["prova"] == fonte]
        if not della_fonte:
            continue
        candidati: List[tuple] = []
        if importo_rata_cents is not None:
            importi = [p["importo_cents"] for p in della_fonte]
            if all(i is not None for i in importi):
                candidati = [(i, p) for i, p in zip(importi, della_fonte)]
                if len(importi) > 1:
                    candidati.append((sum(importi), della_fonte[0]))
        if candidati:
            importo, prova = min(candidati, key=lambda c: abs(c[0] - importo_rata_cents))
            differenza = importo - importo_rata_cents
            if abs(differenza) <= tolleranza_cents:
                return {"vincente": {**prova, "importo_cents": importo, "differenza_cents": differenza},
                        "non_conforme": None}
            if non_conforme is None:
                non_conforme = {"prova": fonte, "importo_cents": importo, "differenza_cents": differenza}
        elif non_conforme is None:
            non_conforme = {"prova": fonte, "importo_cents": None, "differenza_cents": None}
    return {"vincente": None, "non_conforme": non_conforme}


async def carica_dichiarazioni(db) -> Dict[str, Dict[int, Dict[str, Any]]]:
    """Dichiarazioni per mutuo (cifre) e numero di rata, ritirate comprese."""
    righe = await db[COLL_DICHIARAZIONI].find({}, {"_id": 0}).to_list(None)
    per_mutuo: Dict[str, Dict[int, Dict[str, Any]]] = {}
    for riga in righe:
        try:
            per_mutuo.setdefault(str(riga.get("cifre_mutuo")), {})[int(riga.get("numero_rata"))] = riga
        except (TypeError, ValueError):
            logger.warning("Dichiarazione rata mutuo con numero illeggibile: %r", riga.get("id"))
    return per_mutuo


def esito_rata(
    rata: Dict[str, Any], prove_rata: Optional[List[Dict[str, Any]]], dichiarazione: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Stato effettivo della rata: quale prova la regge (la piu' forte vince).

    Una prova con l'importo che non torna (``valuta_prove``) non regge nulla e
    non lascia passare nemmeno la dichiarazione o il «Pagata» del piano:
    ``da_verificare`` con la differenza, finche' un'altra prova o il titolare
    non chiariscono.
    """
    attiva = bool(dichiarazione and dichiarazione.get("stato") == STATO_DICHIARATA)
    importo_rata = _cents_o_none(rata.get("importo_totale"))
    valutazione = valuta_prove(prove_rata, importo_rata)
    vincente = valutazione["vincente"]
    non_conforme = valutazione["non_conforme"]
    if vincente:
        origine = vincente["prova"]
    elif non_conforme:
        origine = None
    elif attiva:
        origine = PROVA_DICHIARATA
    elif rata.get("stato") == "Pagata":
        origine = PROVA_PIANO
    else:
        origine = None
    riferimento = vincente or non_conforme or {}
    return {
        "prova": origine,
        "pagata": origine is not None,
        "da_verificare": bool(non_conforme and not vincente),
        "prova_non_conforme": (non_conforme or {}).get("prova") if not vincente else None,
        "importo_provato_cents": riferimento.get("importo_cents"),
        "differenza_cents": riferimento.get("differenza_cents"),
        "tolleranza_cents": TOLLERANZA_IMPORTO_CENTS,
        "dichiarazione_attiva": attiva,
        # Dichiarata ma ora provata: la prova vince, la dichiarazione resta nello storico.
        "dichiarazione_sostituita": bool(attiva and vincente),
    }


# --------------------------------------------------------------------------
# Anteprima ed esecuzione
# --------------------------------------------------------------------------

def _errore(status: int, code: str, message: str, **details: Any) -> Exception:
    from fastapi import HTTPException

    return HTTPException(status_code=status, detail={"code": code, "message": message, "details": details})


async def _piano_del_mutuo(db, mutuo_id: str) -> Dict[str, Any]:
    from app.routers.mutui import _piani_correnti

    for piano in await _piani_correnti(db):
        if f"mutuo_{piano.get('numero_delibera')}" == mutuo_id:
            return piano
    raise _errore(404, "MUTUO_NON_TROVATO", f"Mutuo {mutuo_id} non trovato", mutuo_id=mutuo_id)


def _limite(data_limite: Any, oggi: date) -> tuple:
    """(limite effettivo, nota). Le rate future non si dichiarano mai."""
    if not data_limite:
        return oggi, None
    richiesta = data_da_testo(data_limite)
    if richiesta is None:
        raise _errore(422, "DATA_LIMITE_NON_VALIDA", "Data limite non leggibile (gg/mm/aaaa)",
                      data_limite=str(data_limite))
    if richiesta > oggi:
        return oggi, "La data limite e' nel futuro: valgono solo le rate scadute fino a oggi."
    return richiesta, None


async def anteprima_dichiarazione(
    db, mutuo_id: str, *, data_limite: Any = None, oggi: Optional[date] = None,
    anno_attivo: Optional[int] = None,
) -> Dict[str, Any]:
    """Quali rate diventerebbero «pagate, dichiarato dal titolare». Non scrive."""
    oggi = oggi or datetime.now(ZoneInfo("Europe/Rome")).date()
    piano = await _piano_del_mutuo(db, mutuo_id)
    cifre = _cifre_mutuo(piano.get("numero_delibera"))
    limite, nota = _limite(data_limite, oggi)
    prove = (await carica_prove(db)).get(cifre, {})
    dichiarazioni = (await carica_dichiarazioni(db)).get(cifre, {})

    candidate: List[Dict[str, Any]] = []
    gruppi: Dict[str, List[int]] = {
        "gia_provate": [], "gia_dichiarate": [], "gia_pagate_sul_piano": [],
        "future_escluse": [], "senza_scadenza": [], "senza_importo": [], "da_verificare": [],
    }
    for rata in sorted(piano.get("rate") or [], key=lambda r: int(r.get("numero_rata") or 0)):
        numero = int(rata.get("numero_rata") or 0)
        scadenza = data_da_testo(rata.get("data_scadenza"))
        if scadenza is None:
            gruppi["senza_scadenza"].append(numero)
            continue
        if scadenza > limite:
            gruppi["future_escluse"].append(numero)
            continue
        esito = esito_rata(rata, prove.get(_data_gma(rata.get("data_scadenza"))), dichiarazioni.get(numero))
        if esito["da_verificare"]:
            # Un pagamento con l'importo diverso non si dichiara pagato: lo decide chi lo guarda.
            gruppi["da_verificare"].append(numero)
        elif esito["prova"] in PROVE_REALI:
            gruppi["gia_provate"].append(numero)
        elif esito["dichiarazione_attiva"]:
            gruppi["gia_dichiarate"].append(numero)
        elif esito["prova"] == PROVA_PIANO:
            gruppi["gia_pagate_sul_piano"].append(numero)
        elif not _importo_leggibile(rata.get("importo_totale")):
            gruppi["senza_importo"].append(numero)
        else:
            candidate.append({**rata, "numero_rata": numero, "_scadenza": scadenza})

    totale = sum(_cents(r.get("importo_totale")) for r in candidate)
    capitale = sum(_cents(r.get("quota_capitale")) for r in candidate)
    interessi = sum(_cents(r.get("quota_interessi")) for r in candidate)
    anno_attivo = anno_attivo if anno_attivo is not None else oggi.year
    n = len(candidate)
    return {
        "dry_run": True,
        "mutuo_id": mutuo_id,
        "numero_delibera": str(piano.get("numero_delibera")),
        "data_limite": limite.isoformat(),
        "nota_data_limite": nota,
        "numero_rate": n,
        "numeri_rata": [r["numero_rata"] for r in candidate],
        "totale_cents": totale,
        "totale": _euro(totale),
        "quota_capitale_cents": capitale,
        "quota_interessi_cents": interessi,
        "valuta": "EUR",
        "prima_scadenza": candidate[0]["_scadenza"].isoformat() if n else None,
        "ultima_scadenza": candidate[-1]["_scadenza"].isoformat() if n else None,
        "di_cui_anno_attivo": sum(1 for r in candidate if r["_scadenza"].year == anno_attivo),
        "anno_attivo": anno_attivo,
        "effetti_contabili": "nessuno",
        **gruppi,
        "frase_conferma": f"DICHIARO PAGATE {n} RATE" if n else None,
        "motivi": MOTIVI,
    }


def _motivo(motivo: Any, motivo_altro: Any, catalogo: Dict[str, str]) -> str:
    chiave = str(motivo or MOTIVO_DEFAULT)
    if chiave not in catalogo:
        raise _errore(422, "MOTIVO_NON_VALIDO", "Motivo non previsto", motivo=chiave, ammessi=sorted(catalogo))
    if chiave == "altro":
        testo = str(motivo_altro or "").strip()
        if not testo:
            raise _errore(422, "MOTIVO_ALTRO_VUOTO", "Con «Altro» scrivi il motivo")
        return f"Altro: {testo[:300]}"
    return catalogo[chiave]


async def dichiara_rate_pagate(
    db, mutuo_id: str, *, data_limite: Any = None, motivo: Any = None, motivo_altro: Any = None,
    dry_run: bool = True, conferma: Optional[str] = None, dichiarato_da: str = "titolare",
    oggi: Optional[date] = None, anno_attivo: Optional[int] = None,
) -> Dict[str, Any]:
    """Segna come pagate (dichiarato) le rate scadute senza prova. `dry_run` per difetto."""
    anteprima = await anteprima_dichiarazione(
        db, mutuo_id, data_limite=data_limite, oggi=oggi, anno_attivo=anno_attivo,
    )
    testo_motivo = _motivo(motivo, motivo_altro, MOTIVI)
    if dry_run:
        return {**anteprima, "motivo": testo_motivo}
    if anteprima["numero_rate"] == 0:
        return {**anteprima, "dry_run": False, "motivo": testo_motivo, "dichiarate": 0}
    if conferma != anteprima["frase_conferma"]:
        raise _errore(409, "CONFERMA_RICHIESTA",
                      "Conferma forte mancante o diversa dall'anteprima",
                      frase_attesa=anteprima["frase_conferma"])
    piano = await _piano_del_mutuo(db, mutuo_id)
    cifre = _cifre_mutuo(piano.get("numero_delibera"))
    rate = {int(r.get("numero_rata") or 0): r for r in piano.get("rate") or []}
    esistenti = (await carica_dichiarazioni(db)).get(cifre, {})
    adesso = _ora()
    scritte = 0
    for numero in anteprima["numeri_rata"]:
        rata = rate[numero]
        precedente = esistenti.get(numero) or {}
        storico = list(precedente.get("storico") or [])
        storico.append({
            "evento": "dichiarata", "at": adesso, "da": dichiarato_da, "motivo": testo_motivo,
            "data_limite": anteprima["data_limite"],
        })
        riga = {
            "id": chiave_dichiarazione(cifre, numero),
            "cifre_mutuo": cifre,
            "mutuo_id": mutuo_id,
            "numero_delibera": anteprima["numero_delibera"],
            "numero_rata": numero,
            "data_scadenza": rata.get("data_scadenza"),
            "importo_totale_cents": _cents(rata.get("importo_totale")),
            "quota_capitale_cents": _cents(rata.get("quota_capitale")),
            "quota_interessi_cents": _cents(rata.get("quota_interessi")),
            "valuta": "EUR",
            "stato": STATO_DICHIARATA,
            "dichiarato_da": dichiarato_da,
            "dichiarato_il": adesso,
            "motivo": testo_motivo,
            "data_limite": anteprima["data_limite"],
            "ritirata_il": None,
            "sostituita_da_prova": None,
            "storico": storico,
            "updated_at": adesso,
        }
        await db[COLL_DICHIARAZIONI].update_one(
            {"id": riga["id"]}, {"$set": riga, "$setOnInsert": {"created_at": adesso}}, upsert=True,
        )
        scritte += 1
    return {**anteprima, "dry_run": False, "motivo": testo_motivo, "dichiarate": scritte}


async def ritira_dichiarazioni(
    db, mutuo_id: str, *, numeri_rata: Optional[List[int]] = None, motivo: Any = None,
    motivo_altro: Any = None, dry_run: bool = True, conferma: Optional[str] = None,
    dichiarato_da: str = "titolare",
) -> Dict[str, Any]:
    """Ritira le dichiarazioni ancora attive: le rate tornano com'erano sul piano."""
    piano = await _piano_del_mutuo(db, mutuo_id)
    cifre = _cifre_mutuo(piano.get("numero_delibera"))
    esistenti = (await carica_dichiarazioni(db)).get(cifre, {})
    voluti = {int(n) for n in numeri_rata} if numeri_rata else None
    da_ritirare = sorted(
        n for n, r in esistenti.items()
        if r.get("stato") == STATO_DICHIARATA and (voluti is None or n in voluti)
    )
    testo_motivo = _motivo(motivo or "dichiarazione_errata", motivo_altro, MOTIVI_RITIRO)
    totale = sum(int(esistenti[n].get("importo_totale_cents") or 0) for n in da_ritirare)
    frase = f"RITIRO DICHIARAZIONE {len(da_ritirare)} RATE" if da_ritirare else None
    esito = {
        "dry_run": dry_run, "mutuo_id": mutuo_id, "numero_rate": len(da_ritirare),
        "numeri_rata": da_ritirare, "totale_cents": totale, "totale": _euro(totale), "valuta": "EUR",
        "motivo": testo_motivo, "frase_conferma": frase, "motivi": MOTIVI_RITIRO, "ritirate": 0,
    }
    if dry_run or not da_ritirare:
        return esito
    if conferma != frase:
        raise _errore(409, "CONFERMA_RICHIESTA", "Conferma forte mancante o diversa dall'anteprima",
                      frase_attesa=frase)
    adesso = _ora()
    for numero in da_ritirare:
        riga = esistenti[numero]
        storico = list(riga.get("storico") or [])
        storico.append({"evento": "ritirata", "at": adesso, "da": dichiarato_da, "motivo": testo_motivo})
        await db[COLL_DICHIARAZIONI].update_one({"id": riga["id"]}, {"$set": {
            "stato": STATO_RITIRATA, "ritirata_il": adesso, "ritirata_da": dichiarato_da,
            "motivo_ritiro": testo_motivo, "storico": storico, "updated_at": adesso,
        }})
    return {**esito, "dry_run": False, "ritirate": len(da_ritirare)}


async def assorbi_dichiarazioni_rate(db) -> Dict[str, int]:
    """Una prova arrivata dopo sostituisce la dichiarazione: la riga resta, con lo storico.

    Idempotente: una dichiarazione gia' sostituita non si tocca. La lettura
    della pagina non dipende da questo passo (la prova vince comunque):
    serve a fissare quando e da che cosa la dichiarazione e' stata superata.
    """
    prove = await carica_prove(db)
    sostituite = 0
    for cifre, per_rata in (await carica_dichiarazioni(db)).items():
        for numero, riga in per_rata.items():
            if riga.get("stato") != STATO_DICHIARATA:
                continue
            prova = valuta_prove(
                prove.get(cifre, {}).get(_data_gma(riga.get("data_scadenza"))),
                riga.get("importo_totale_cents"),
            )["vincente"]
            if not prova:
                continue
            adesso = _ora()
            storico = list(riga.get("storico") or [])
            storico.append({"evento": "sostituita_da_prova", "at": adesso, "prova": prova["prova"]})
            await db[COLL_DICHIARAZIONI].update_one({"id": riga["id"]}, {"$set": {
                "stato": STATO_SOSTITUITA, "sostituita_da_prova": prova["prova"],
                "sostituita_il": adesso, "storico": storico, "updated_at": adesso,
            }})
            sostituite += 1
    return {"sostituite": sostituite}
