"""GC-02h — registrazioni HACCP in archivio senza firma verificata.

Decisione del titolare (24/09/2026, «strada A»): segnare, non cancellare.

Una registrazione gia' in archivio che non porta `firma_verificata: True`
(nasce solo dal PIN personale o dalla sessione verificata del tablet, vedi
`servizi/registro_haccp.py`) non attesta chi ha fatto il controllo: il vecchio
calendario automatico ne scriveva a migliaia, con valori sorteggiati e fermi
frigo inventati. Non si toglie niente, perche' un registro non dimentica: il
valore originale resta intatto e accanto gli si mette un segno, il campo
`non_attendibili` del documento. Stampe e schede lo mostrano come «n.a.» e lo
escludono dai conteggi di conformita'.

Una sola regola, in questo modulo; il frontend Lotti la ripete identica in
`frontend_lotti/src/utils/attendibilita.js`.

Si segna:
  - temperature (`temperature[mese][giorno]`): valore numerico semplice;
    oggetto con `temp` non nullo senza firma; oggetto `is_manutenzione` /
    `is_non_usato` (fermi inventati dal vecchio calendario); oggetto
    `is_sanificazione` senza firma;
  - `sanificazione_schede` (`registrazioni[area][giorno]`): «X» senza firma
    verificata in `firme[area][giorno]`;
  - `sanificazione_apparecchi` (`{campo: {numero: [voci]}}`): voce con esito
    (`eseguita` vera o falsa) senza firma verificata.

Non si tocca: giorni `is_chiuso` (chiusure dichiarate), voci `non_rilevato`
(dichiaratamente vuote), caselle aperte dal turno (`stato`), «N/D», e ogni
registrazione firmata. Un valore di forma inattesa non si segna: si riporta
fra le anomalie dell'anteprima.

Una casella segnata smette di essere non attendibile quando oggi contiene un
valore con `firma_verificata: True`: la rilevazione firmata la sostituisce.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional, Tuple

logger = logging.getLogger(__name__)

REGOLA = "GC-02h: registrazione senza firma verificata"
CAMPO = "non_attendibili"
COLLEZIONE_LOG = "haccp_attendibilita_log"

TEMPERATURE = ("temperature_positive", "temperature_negative")
SCHEDE = "sanificazione_schede"
APPARECCHI = "sanificazione_apparecchi"
COLLEZIONI = TEMPERATURE + (SCHEDE, APPARECCHI)
CAMPI_APPARECCHI = ("registrazioni_frigoriferi", "registrazioni_congelatori")

# Categorie da segnare (le righe della tabella della decisione GC-02h)
CAT_VALORE_SEMPLICE = "temperatura_valore_semplice"
CAT_TEMP_SENZA_FIRMA = "temperatura_senza_firma"
CAT_FERMO_INVENTATO = "manutenzione_o_non_usato"
CAT_SANIF_IN_TEMPERATURE = "sanificazione_in_temperature"
CAT_SCHEDA_X = "sanificazione_x_senza_firma"
CAT_APPARECCHIO = "sanificazione_apparecchio_senza_firma"

# Categorie lasciate intatte (contate in anteprima, mai segnate)
NT_CHIUSO = "giorno_chiuso"
NT_NON_RILEVATO = "non_rilevato"
NT_CASELLA_APERTA = "casella_aperta"
NT_ND = "n_d"
NT_FIRMATO = "firmato"


def firmata(valore: Any) -> bool:
    """Firma verificata: solo il booleano vero, mai una stringa o un 1."""
    return isinstance(valore, dict) and valore.get("firma_verificata") is True


def _norm(chiave: Any) -> str:
    """Mese e giorno possono essere salvati come "5", "05" o 5."""
    testo = str(chiave).strip()
    return str(int(testo)) if testo.isdigit() else testo


def _numero(valore: Any) -> bool:
    return isinstance(valore, (int, float)) and not isinstance(valore, bool)


# ── classificazione di una casella ──────────────────────────────────────────


def categoria_temperatura(valore: Any) -> Optional[str]:
    """Categoria da segnare per una casella temperatura, o None se resta com'e'."""
    if _numero(valore):
        return CAT_VALORE_SEMPLICE
    if not isinstance(valore, dict) or firmata(valore):
        return None
    if valore.get("is_chiuso") or valore.get("non_rilevato"):
        return None
    if valore.get("is_manutenzione") or valore.get("is_non_usato"):
        return CAT_FERMO_INVENTATO
    if valore.get("is_sanificazione"):
        return CAT_SANIF_IN_TEMPERATURE
    if valore.get("temp") is not None:
        return CAT_TEMP_SENZA_FIRMA
    return None


def da_segnare_temperatura(valore: Any) -> bool:
    return categoria_temperatura(valore) is not None


def da_segnare_scheda(valore: Any, firma: Any) -> bool:
    """«X» della scheda di sanificazione senza firma verificata accanto."""
    return isinstance(valore, str) and valore.strip() in ("X", "x") and not firmata(firma)


def da_segnare_apparecchio(rec: Any) -> bool:
    """Voce di sanificazione apparecchio con un esito ma senza firma verificata.

    Anche `eseguita: False` e' un esito: il vecchio generatore ne scriveva un
    10% per rendere credibile il resto.
    """
    return (
        isinstance(rec, dict)
        and isinstance(rec.get("eseguita"), bool)
        and not firmata(rec)
    )


def _non_toccata_temperatura(valore: Any) -> Optional[str]:
    if firmata(valore):
        return NT_FIRMATO
    if isinstance(valore, dict):
        if valore.get("is_chiuso"):
            return NT_CHIUSO
        if valore.get("non_rilevato"):
            return NT_NON_RILEVATO
        if "stato" in valore:
            return NT_CASELLA_APERTA
    if valore == "N/D":
        return NT_ND
    return None


def coordinata_apparecchio(rec: dict) -> Optional[str]:
    mese, giorno = rec.get("mese"), rec.get("giorno")
    if mese in (None, "") or giorno in (None, ""):
        data = str(rec.get("data") or "")
        parti = data.split("/")
        if len(parti) == 3 and parti[0].isdigit() and parti[1].isdigit():
            giorno, mese = parti[0], parti[1]
        else:
            return None
    return f"{_norm(mese)}-{_norm(giorno)}"


# ── scorrimento di un documento ─────────────────────────────────────────────


def _scorri(collection: str, doc: dict) -> Iterator[Tuple[str, Tuple[str, ...], Any]]:
    """(esito, coordinata, valore) per ogni casella del documento.

    `esito` e' una categoria da segnare, una da non toccare, oppure
    "anomalia:<descrizione>" per le forme inattese.
    """
    if collection in TEMPERATURE:
        for mese, giorni in (doc.get("temperature") or {}).items():
            if not isinstance(giorni, dict):
                yield "anomalia:mese non strutturato", (str(mese),), giorni
                continue
            for giorno, valore in giorni.items():
                coord = (str(mese), str(giorno))
                cat = categoria_temperatura(valore)
                if cat:
                    yield cat, coord, valore
                    continue
                nt = _non_toccata_temperatura(valore)
                if nt:
                    yield nt, coord, valore
                elif valore not in (None, "") and not (isinstance(valore, dict) and valore.get("temp") is None):
                    yield "anomalia:valore temperatura inatteso", coord, valore
    elif collection == SCHEDE:
        firme = doc.get("firme") or {}
        for area, giorni in (doc.get("registrazioni") or {}).items():
            if not isinstance(giorni, dict):
                yield "anomalia:area non strutturata", (str(area),), giorni
                continue
            firme_area = firme.get(area) if isinstance(firme.get(area), dict) else {}
            for giorno, valore in giorni.items():
                coord = (str(area), str(giorno))
                firma = firme_area.get(str(giorno))
                if da_segnare_scheda(valore, firma):
                    yield CAT_SCHEDA_X, coord, valore
                elif isinstance(valore, dict):
                    # un calendario annidato dentro una casella: non si
                    # interpreta, si mostra
                    yield "anomalia:valore annidato nella casella", coord, valore
                elif valore == "N/D":
                    yield NT_ND, coord, valore
                elif isinstance(valore, str) and valore.strip() in ("X", "x"):
                    yield NT_FIRMATO, coord, valore
    elif collection == APPARECCHI:
        for campo in CAMPI_APPARECCHI:
            gruppi = doc.get(campo) or {}
            if not isinstance(gruppi, dict):
                yield "anomalia:registrazioni apparecchi non strutturate", (campo,), gruppi
                continue
            for numero, voci in gruppi.items():
                for rec in voci if isinstance(voci, list) else []:
                    if not isinstance(rec, dict):
                        continue
                    mg = coordinata_apparecchio(rec)
                    coord = (campo, str(numero), mg or "")
                    if da_segnare_apparecchio(rec):
                        if mg is None:
                            yield "anomalia:voce apparecchio senza data", coord, rec
                        else:
                            yield CAT_APPARECCHIO, coord, rec
                    elif firmata(rec):
                        yield NT_FIRMATO, coord, rec


CATEGORIE_DA_SEGNARE = (
    CAT_VALORE_SEMPLICE, CAT_TEMP_SENZA_FIRMA, CAT_FERMO_INVENTATO,
    CAT_SANIF_IN_TEMPERATURE, CAT_SCHEDA_X, CAT_APPARECCHIO,
)


def celle_da_segnare(collection: str, doc: dict) -> dict:
    """Coordinate delle caselle da segnare, nella forma del campo `celle`.

    temperature `{mese: [giorni]}`, schede `{area: [giorni]}`,
    apparecchi `{campo: {numero: ["mese-giorno", ...]}}`.
    """
    celle: dict = {}
    for esito, coord, _valore in _scorri(collection, doc):
        if esito not in CATEGORIE_DA_SEGNARE:
            continue
        _aggiungi(celle, coord)
    return _ordina(celle)


def _aggiungi(celle: dict, coord: Tuple[str, ...]) -> None:
    if len(coord) == 3:
        lista = celle.setdefault(coord[0], {}).setdefault(coord[1], [])
    else:
        lista = celle.setdefault(coord[0], [])
    if coord[-1] not in lista:
        lista.append(coord[-1])


def _ordina(celle: dict) -> dict:
    def chiave(x):
        parti = str(x).split("-")
        return tuple(int(p) if p.isdigit() else 0 for p in parti), str(x)

    out = {}
    for k, v in celle.items():
        if isinstance(v, dict):
            out[k] = {n: sorted(lst, key=chiave) for n, lst in v.items()}
        else:
            out[k] = sorted(v, key=chiave)
    return out


def _coordinate(celle: Any) -> set:
    """Insieme di tuple normalizzate a partire dal campo `celle`."""
    risultato = set()
    for k, v in (celle or {}).items():
        if isinstance(v, dict):
            for numero, lista in v.items():
                for mg in lista or []:
                    risultato.add((str(k), _norm(numero), str(mg)))
        elif isinstance(v, list):
            for g in v:
                risultato.add((_norm(k), _norm(g)))
    return risultato


def _coordinata_norm(coordinate: Tuple[Any, ...]) -> tuple:
    if len(coordinate) == 3:
        campo, numero, mg = coordinate
        return (str(campo), _norm(numero), str(mg))
    a, g = coordinate
    return (_norm(a), _norm(g))


def e_non_attendibile(doc: dict, coordinate: Tuple[Any, ...], valore_attuale: Any) -> bool:
    """La casella e' segnata e il valore di oggi non e' firmato.

    `valore_attuale`: per le temperature la casella, per le schede la voce
    `firme[area][giorno]`, per gli apparecchi la voce della lista.
    """
    return non_attendibile_in(caselle_segnate(doc), coordinate, valore_attuale)


def caselle_segnate(doc: dict) -> set:
    """Le coordinate segnate di un documento, da calcolare una volta per scheda."""
    segno = (doc or {}).get(CAMPO)
    return _coordinate(segno.get("celle")) if isinstance(segno, dict) else set()


def non_attendibile_in(segnate: set, coordinate: Tuple[Any, ...], valore_attuale: Any) -> bool:
    """Come `e_non_attendibile`, con le coordinate gia' lette dal documento."""
    if not segnate or firmata(valore_attuale):
        return False
    return _coordinata_norm(coordinate) in segnate


def unisci_celle(esistenti: Any, nuove: dict) -> dict:
    """Unione idempotente: un segno messo non si toglie."""
    celle: dict = {}
    for sorgente in (esistenti or {}, nuove or {}):
        for k, v in sorgente.items():
            if isinstance(v, dict):
                for numero, lista in v.items():
                    for mg in lista or []:
                        _aggiungi(celle, (str(k), str(numero), str(mg)))
            elif isinstance(v, list):
                for g in v:
                    _aggiungi(celle, (str(k), str(g)))
    return _ordina(celle)


# ── anteprima e scrittura ───────────────────────────────────────────────────


async def _documenti(db, collection: str) -> List[dict]:
    return await getattr(db, collection).find({}, {"_id": 0}).to_list(None)


def _anno(doc: dict) -> str:
    return str(doc.get("anno") or "?")


async def anteprima(db) -> Dict[str, Any]:
    """Cosa verrebbe segnato, per collezione, anno e categoria. Non scrive."""
    per_collezione: Dict[str, Dict[str, Dict[str, Dict[str, int]]]] = {}
    per_categoria: Dict[str, Dict[str, int]] = {
        c: {"da_segnare": 0, "gia_segnati": 0} for c in CATEGORIE_DA_SEGNARE
    }
    non_toccati: Dict[str, int] = {}
    anomalie: List[dict] = []
    documenti_da_aggiornare = 0

    for collection in COLLEZIONI:
        for doc in await _documenti(db, collection):
            anno = _anno(doc)
            gia = _coordinate(((doc.get(CAMPO) or {}).get("celle")))
            nuove = False
            for esito, coord, valore in _scorri(collection, doc):
                if esito.startswith("anomalia:"):
                    anomalie.append({
                        "collezione": collection, "anno": anno, "id": doc.get("id"),
                        "coordinata": list(coord), "motivo": esito.split(":", 1)[1],
                        "valore": str(valore)[:200],
                    })
                    continue
                if esito not in CATEGORIE_DA_SEGNARE:
                    non_toccati[esito] = non_toccati.get(esito, 0) + 1
                    continue
                stato = "gia_segnati" if _coordinata_norm(coord) in gia else "da_segnare"
                nuove = nuove or stato == "da_segnare"
                per_categoria[esito][stato] += 1
                (per_collezione.setdefault(collection, {}).setdefault(anno, {})
                 .setdefault(esito, {"da_segnare": 0, "gia_segnati": 0}))[stato] += 1
            documenti_da_aggiornare += 1 if nuove else 0

    return {
        "regola": REGOLA,
        "totale_da_segnare": sum(v["da_segnare"] for v in per_categoria.values()),
        "totale_gia_segnati": sum(v["gia_segnati"] for v in per_categoria.values()),
        "documenti_da_aggiornare": documenti_da_aggiornare,
        "per_categoria": per_categoria,
        "per_collezione": per_collezione,
        "non_toccati": non_toccati,
        "anomalie": anomalie,
    }


async def segna(db, attore: Optional[dict], dry_run: bool = True) -> Dict[str, Any]:
    """Aggiunge il segno alle caselle non attendibili. Mai tocca un valore.

    Scrive solo `$set: {non_attendibili: ...}` e solo sui documenti che hanno
    caselle nuove da segnare: la seconda esecuzione non modifica niente.
    """
    prima = await anteprima(db)
    attore = attore or {}
    firmatario = {"id": str(attore.get("id") or ""), "nome": str(attore.get("nome") or "")}
    ora = datetime.now(timezone.utc).isoformat()
    documenti: List[dict] = []

    for collection in COLLEZIONI:
        for doc in await _documenti(db, collection):
            segno = doc.get(CAMPO) if isinstance(doc.get(CAMPO), dict) else {}
            esistenti = segno.get("celle") or {}
            unione = unisci_celle(esistenti, celle_da_segnare(collection, doc))
            if _coordinate(unione) == _coordinate(esistenti):
                continue
            aggiunte = len(_coordinate(unione) - _coordinate(esistenti))
            documenti.append({
                "collezione": collection, "id": doc.get("id"), "anno": doc.get("anno"),
                "celle_aggiunte": aggiunte,
            })
            if dry_run:
                continue
            if not doc.get("id"):
                raise ValueError(f"{collection}: documento senza id, non si segna per filtro")
            nuovo_segno = {
                "regola": REGOLA,
                "segnato_il": ora,
                "segnato_da": firmatario,
                "celle": unione,
            }
            if segno.get("segnato_il"):
                nuovo_segno["primo_segno_il"] = segno.get("primo_segno_il") or segno["segnato_il"]
            await getattr(db, collection).update_one(
                {"id": doc["id"]}, {"$set": {CAMPO: nuovo_segno}}
            )

    esito = {
        "dry_run": dry_run,
        "regola": REGOLA,
        "caselle_segnate": sum(d["celle_aggiunte"] for d in documenti),
        "documenti_modificati": 0 if dry_run else len(documenti),
        "documenti": documenti,
        "anteprima": prima,
    }
    if not dry_run:
        await getattr(db, COLLEZIONE_LOG).insert_one({
            "id": str(uuid.uuid4()),
            "regola": REGOLA,
            "eseguito_il": ora,
            "eseguito_da": firmatario,
            "caselle_segnate": esito["caselle_segnate"],
            "documenti_modificati": esito["documenti_modificati"],
            "per_categoria": prima["per_categoria"],
            "documenti": documenti,
        })
        logger.info(
            "GC-02h: %s caselle segnate su %s documenti da %s",
            esito["caselle_segnate"], esito["documenti_modificati"], firmatario.get("nome"),
        )
    return esito
