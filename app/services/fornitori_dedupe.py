"""
Deduplica fornitori: l'unico motore (classificazione, fusione, giro).

Identita' di un fornitore: P.IVA normalizzata -> codice fiscale -> nome.
Gli alias servono solo da supporto. Tre esiti, mai di piu':

- **CERTO**: stessa P.IVA normalizzata (senza spazi, prefisso IT, zeri
  iniziali) oppure stesso codice fiscale senza P.IVA diverse. Si fonde da solo.
- **PROBABILE da solo**: nome uguale o quasi (refusi tollerati: «DISTRBUZIONE»)
  fra un fornitore con P.IVA/CF e uno **senza** P.IVA e senza CF, con un solo
  candidato. Il perdente non ha niente indicizzato per P.IVA, quindi i suoi
  riferimenti per id si riassegnano senza perdere nulla. Si fonde da solo.
- **DA DECIDERE**: tutto il resto (piu' candidati, due senza P.IVA, nome solo
  simile). Resta in un elenco in sola lettura; la scelta e' del titolare.

Due P.IVA valide diverse **non si fondono mai**, nemmeno a mano: o sono due
aziende o una P.IVA e' sbagliata e va corretta prima.

La fusione non cancella niente: il perdente resta con `status='unificato'` e
`merged_into`; il vincente conserva alias, IBAN, id precedenti e uno
`storico_fusioni`. La validazione P.IVA sta in `piva_validazione.py`.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.constants.metodi_pagamento import metodo_non_configurato
from app.database import Database, Collections
from app.services.piva_validazione import (
    chiave_confronto, normalizza_piva, piva_valida,
)

logger = logging.getLogger(__name__)

# Sotto questa soglia due nomi non si considerano nemmeno candidati.
SOGLIA_CANDIDATI = 0.80
# Sopra questa soglia (solo refusi) il nome basta per la fusione da solo.
SOGLIA_REFUSO = 0.92
# Compatibilita' col vecchio nome della costante.
SOGLIA_FUZZY_NOME = SOGLIA_CANDIDATI

_FORME_SOCIETARIE = re.compile(
    r"\b(s\.?r\.?l\.?s?|s\.?p\.?a\.?|s\.?n\.?c\.?|s\.?a\.?s\.?|s\.?s\.?|ditta individuale|"
    r"societa'? (a responsabilita'? limitata|per azioni)|unipersonale|a socio unico)\b",
    re.IGNORECASE,
)

# Riferimenti per id fornitore: (collezione, campo). Cambiano di id, non di P.IVA.
RIFERIMENTI_ID: Tuple[Tuple[str, str], ...] = (
    (Collections.INVOICES, "supplier_id"),
    ("scadenziario_fornitori", "fornitore_id"),
    ("acquisti_prodotti", "fornitore_id"),
    ("metodi_pagamento_storico", "fornitore_id"),
    ("fornitori_keywords", "fornitore_id"),
    ("alerts", "fornitore_id"),
    ("estratto_conto_movimenti", "fornitore_id"),
    ("supplier_update_proposals", "supplier_id"),
    # il debito aperto di una fattura si legge per fornitore: la partita segue l'anagrafica vincente
    ("partite_aperte", "controparte_id"),
)
# Riferimenti per P.IVA testuale (campo `fornitore_piva`).
RIFERIMENTI_PIVA: Tuple[str, ...] = (
    "prima_nota_cassa", "prima_nota_banca", "pagamenti", "assegni",
    "scadenziario_fornitori", "alerts",
)
# Collezioni che contano come «uso» del fornitore nel punteggio del vincente.
_USI = (
    (Collections.INVOICES, "supplier_id"),
    ("scadenziario_fornitori", "fornitore_id"),
    ("acquisti_prodotti", "fornitore_id"),
)
_VUOTI = (None, "", [], {}, 0)


# ── normalizzazione ────────────────────────────────────────────────────────

def _norm_piva(s: Optional[str]) -> str:
    """Compatibilita': la normalizzazione vive in `piva_validazione`."""
    return normalizza_piva(s)


def _norm_nome(s: Optional[str]) -> str:
    """Denominazione per il confronto: minuscolo, senza forma societaria,
    senza punteggiatura, spazi collassati."""
    if not s:
        return ""
    n = _FORME_SOCIETARIE.sub(" ", str(s).lower())
    n = re.sub(r"[^\w\s]", " ", n)
    n = re.sub(r"\bcoop\b", "cooperativa", n)
    n = re.sub(r"\bsoc\b", "sociale", n)
    n = re.sub(r"\b(societa|società)\b", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def _get_piva(d: Dict[str, Any]) -> str:
    return normalizza_piva(d.get("partita_iva") or d.get("piva") or d.get("vat_number"))


def _get_cf(d: Dict[str, Any]) -> str:
    return re.sub(r"[^0-9A-Z]", "", str(d.get("codice_fiscale") or "").upper())


def _get_nome(d: Dict[str, Any]) -> str:
    return d.get("ragione_sociale") or d.get("denominazione") or d.get("nome") or d.get("name") or ""


def _nomi(d: Dict[str, Any]) -> List[str]:
    visti: List[str] = []
    for k in ("ragione_sociale", "denominazione", "nome", "name"):
        v = str(d.get(k) or "").strip()
        if v and v not in visti:
            visti.append(v)
    return visti


def _filtro_id(valore: Any, campo: str = "id") -> Dict[str, Any]:
    """Un id puo' stare come testo o come numero (180 fornitori su 188)."""
    testo = str(valore)
    valori: List[Any] = [testo]
    if testo.isdigit():
        valori.append(int(testo))
    return {campo: valori[0]} if len(valori) == 1 else {campo: {"$in": valori}}


def _score_completezza(d: Dict[str, Any]) -> int:
    """Punteggio di completezza: il record piu' ricco diventa il vincente."""
    score = 0
    for k in ("partita_iva", "codice_fiscale", "iban", "metodo_pagamento",
              "indirizzo", "cap", "comune", "provincia", "telefono", "email",
              "centro_costo_id"):
        if d.get(k) not in _VUOTI:
            score += 2
    if not metodo_non_configurato(d.get("metodo_pagamento")):
        score += 5
    score += int(d.get("fatture_count") or 0)
    return score


# ── classificazione ────────────────────────────────────────────────────────

def _info(rec: Dict[str, Any], usi: Dict[str, int]) -> Dict[str, Any]:
    nome = _get_nome(rec)
    norm = _norm_nome(nome)
    piva = _get_piva(rec)
    return {
        "id": rec.get("id"),
        "nome": nome,
        "norm": norm,
        "tokens": frozenset(t[:-1] if len(t) >= 6 and t[-1] in "aeio" else t for t in norm.split()),
        "partita_iva": piva,
        "chiave_piva": chiave_confronto(piva),
        "piva_valida": piva_valida(piva),
        "codice_fiscale": _get_cf(rec),
        "usi": int(usi.get(str(rec.get("id")), 0)),
        "punteggio": _score_completezza(rec) + 3 * int(usi.get(str(rec.get("id")), 0)),
        "record": rec,
    }


def _somiglianza(a: Dict[str, Any], b: Dict[str, Any]) -> Tuple[str, float]:
    """('uguale'|'sottoinsieme'|'refuso'|'simile'|'', punteggio)."""
    na, nb = a["norm"], b["norm"]
    if not na or not nb:
        return "", 0.0
    if na == nb or a["tokens"] == b["tokens"]:
        return "uguale", 1.0
    corto, lungo = (a["tokens"], b["tokens"]) if len(a["tokens"]) <= len(b["tokens"]) else (b["tokens"], a["tokens"])
    if len(corto) >= 2 and corto <= lungo:
        return "sottoinsieme", 0.95
    r = SequenceMatcher(None, na, nb).ratio()
    if r >= SOGLIA_REFUSO:
        return "refuso", r
    if r >= SOGLIA_CANDIDATI:
        return "simile", r
    return "", r


def _pubblico(i: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": i["id"], "nome": i["nome"], "partita_iva": i["partita_iva"] or None,
        "codice_fiscale": i["codice_fiscale"] or None, "usi": i["usi"],
        "piva_valida": i["piva_valida"],
    }


def _piva_diverse(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    return bool(a["chiave_piva"] and b["chiave_piva"] and a["chiave_piva"] != b["chiave_piva"])


def _vincente(infos: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    return sorted(infos, key=lambda i: (-i["punteggio"], not i["piva_valida"], str(i["id"])))[0]


def classifica(records: List[Dict[str, Any]], usi: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
    """Classifica i doppioni su una lista di fornitori (funzione pura, testabile)."""
    usi = usi or {}
    infos = [_info(r, usi) for r in records if r.get("id") not in (None, "") and not r.get("merged_into")]

    # ---- certi: union-find su P.IVA e CF ----
    padre = list(range(len(infos)))

    def trova(x: int) -> int:
        while padre[x] != x:
            padre[x] = padre[padre[x]]
            x = padre[x]
        return x

    def unisci(x: int, y: int) -> None:
        padre[trova(x)] = trova(y)

    for chiave in ("chiave_piva", "codice_fiscale"):
        visti: Dict[str, int] = {}
        for n, i in enumerate(infos):
            k = i[chiave]
            if chiave == "codice_fiscale" and len(k) < 11:
                continue
            if not k:
                continue
            if k in visti:
                unisci(n, visti[k])
            else:
                visti[k] = n
    gruppi: Dict[int, List[Dict[str, Any]]] = {}
    for n, i in enumerate(infos):
        gruppi.setdefault(trova(n), []).append(i)

    certi: List[Dict[str, Any]] = []
    da_decidere: List[Dict[str, Any]] = []
    fusi_ids: set = set()
    for membri in gruppi.values():
        if len(membri) < 2:
            continue
        pive = {m["chiave_piva"] for m in membri if m["chiave_piva"]}
        if len(pive) > 1:
            da_decidere.append({
                "fornitori": [_pubblico(m) for m in membri],
                "motivo": "Stesso codice fiscale ma partite IVA diverse: sono due aziende o una P.IVA e' sbagliata.",
                "consigliato": None,
            })
            fusi_ids.update(str(m["id"]) for m in membri)
            continue
        win = _vincente(membri)
        perdenti = [m for m in membri if m is not win]
        motivo = "Stessa P.IVA" if pive else "Stesso codice fiscale"
        certi.append({"vincente": win, "perdenti": perdenti, "motivo": motivo,
                      "chiave": next(iter(pive)) if pive else win["codice_fiscale"],
                      "tipo": "partita_iva_identica" if pive else "codice_fiscale_identico"})
        fusi_ids.update(str(m["id"]) for m in membri)

    # ---- probabili e da decidere: sui soli fornitori non gia' in un gruppo certo ----
    # Il rappresentante di un gruppo certo partecipa ancora al confronto per nome.
    rapp = {str(c["vincente"]["id"]) for c in certi}
    resto = [i for i in infos if str(i["id"]) not in fusi_ids or str(i["id"]) in rapp]
    archi: Dict[int, List[Tuple[int, str, float]]] = {n: [] for n in range(len(resto))}
    for x in range(len(resto)):
        for y in range(x + 1, len(resto)):
            a, b = resto[x], resto[y]
            if _piva_diverse(a, b):
                continue
            forza, punteggio = _somiglianza(a, b)
            if forza:
                archi[x].append((y, forza, punteggio))
                archi[y].append((x, forza, punteggio))

    probabili: List[Dict[str, Any]] = []
    for x, i in enumerate(resto):
        senza_identita = not i["chiave_piva"] and not i["codice_fiscale"]
        if not senza_identita or str(i["id"]) in fusi_ids - rapp:
            continue
        # Un solo candidato «forte» (nome uguale, contenuto o con un refuso): i
        # nomi solo «simili» non contano contro di lui, non lo rendono ambiguo.
        forti = [a for a in archi[x] if a[1] != "simile"]
        if len(forti) != 1:
            continue
        y, forza, punteggio = forti[0]
        w = resto[y]
        if not w["chiave_piva"] and not w["codice_fiscale"]:
            continue
        probabili.append({"vincente": w, "perdente": i, "motivo": f"Nome {forza} e un solo candidato",
                          "somiglianza": round(punteggio, 3)})
    # Un perdente non puo' essere anche il vincente di un altro: se capita, torna da decidere.
    perdenti_p = {str(p["perdente"]["id"]) for p in probabili}
    probabili = [p for p in probabili if str(p["vincente"]["id"]) not in perdenti_p]
    perdenti_p = {str(p["perdente"]["id"]) for p in probabili}
    auto_ids = perdenti_p

    # Cluster del «da decidere»: archi fra i fornitori che restano.
    rimasti = [n for n, i in enumerate(resto) if str(i["id"]) not in auto_ids]
    padre2 = {n: n for n in rimasti}

    def trova2(x: int) -> int:
        while padre2[x] != x:
            padre2[x] = padre2[padre2[x]]
            x = padre2[x]
        return x

    for x in rimasti:
        for y, _forza, _p in archi[x]:
            if y in padre2:
                padre2[trova2(x)] = trova2(y)
    cluster: Dict[int, List[int]] = {}
    for n in rimasti:
        cluster.setdefault(trova2(n), []).append(n)
    for membri_n in cluster.values():
        if len(membri_n) < 2:
            continue
        membri = [resto[n] for n in membri_n]
        con_piva = [m for m in membri if m["chiave_piva"]]
        senza = [m for m in membri if not m["chiave_piva"]]
        if len(con_piva) > 1:
            motivo = "Un fornitore senza P.IVA con piu' candidati che hanno P.IVA diverse."
        elif not con_piva:
            motivo = "Nessuno dei due ha la P.IVA: serve la tua scelta."
        elif len(senza) > 1:
            motivo = "Piu' fornitori senza P.IVA somigliano allo stesso."
        else:
            motivo = "Nome solo simile, non uguale: serve conferma."
        da_decidere.append({
            "fornitori": [_pubblico(m) for m in membri],
            "motivo": motivo,
            "consigliato": _vincente(con_piva or membri)["id"] if len(con_piva) <= 1 else None,
        })

    return {
        "certi": certi,
        "probabili": probabili,
        "da_decidere": da_decidere,
        "totali": {
            "certi": sum(len(c["perdenti"]) for c in certi),
            "gruppi_certi": len(certi),
            "probabili": len(probabili),
            "da_decidere": len(da_decidere),
        },
    }


async def _carica(db) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    records = await db[Collections.SUPPLIERS].find(
        {"merged_into": {"$exists": False}}, {"_id": 0}
    ).to_list(10000)
    usi: Dict[str, int] = {}
    esistenti = set(await db.list_collection_names())
    for coll, campo in _USI:
        if coll not in esistenti:
            continue
        for d in await db[coll].find({campo: {"$exists": True}}, {"_id": 0, campo: 1}).to_list(200000):
            v = d.get(campo)
            if v not in (None, ""):
                usi[str(v)] = usi.get(str(v), 0) + 1
    return records, usi


async def classifica_duplicati(db=None) -> Dict[str, Any]:
    db = db or Database.get_db()
    records, usi = await _carica(db)
    return classifica(records, usi)


async def trova_duplicati() -> Dict[str, Any]:
    """Gruppi sospetti (forma storica): certezza «alta» = certi, «media» = il resto."""
    cl = await classifica_duplicati()
    gruppi: List[Dict[str, Any]] = []
    for c in cl["certi"]:
        gruppi.append({
            "tipo": c["tipo"], "chiave": c["chiave"], "certezza": "alta",
            "fornitori": [c["vincente"]["record"]] + [p["record"] for p in c["perdenti"]],
        })
    for p in cl["probabili"]:
        gruppi.append({
            "tipo": "denominazione_simile", "chiave": p["vincente"]["norm"], "certezza": "media",
            "fornitori": [p["vincente"]["record"], p["perdente"]["record"]],
        })
    for d in cl["da_decidere"]:
        gruppi.append({
            "tipo": "denominazione_simile", "chiave": d["motivo"], "certezza": "media",
            "fornitori": [{"id": f["id"], "nome": f["nome"], "partita_iva": f["partita_iva"]} for f in d["fornitori"]],
        })
    return {
        "totale_gruppi": len(gruppi),
        "totale_duplicati": sum(len(g["fornitori"]) - 1 for g in gruppi),
        "gruppi": gruppi,
    }


async def da_decidere() -> Dict[str, Any]:
    """Elenco in sola lettura per la pagina Fornitori."""
    cl = await classifica_duplicati()
    return {"count": len(cl["da_decidere"]), "gruppi": cl["da_decidere"], "totali": cl["totali"]}


# ── fusione ────────────────────────────────────────────────────────────────

def varianti_piva(piva: Any) -> List[str]:
    raw = str(piva or "").strip()
    norm = normalizza_piva(raw)
    out: List[str] = []
    for v in (raw, norm, f"IT{norm}" if norm.isdigit() else ""):
        if v and v not in out:
            out.append(v)
    return out


async def _migra_riferimenti(
    db, from_id: Any, to_id: Any,
    piva_da: Optional[str] = None, piva_a: Optional[str] = None,
) -> Dict[str, Any]:
    """Ripunta per id (e per P.IVA testuale se cambia) tutto cio' che cita il perdente.

    Un riferimento per P.IVA va ripuntato solo se la P.IVA del perdente e'
    diversa da quella del vincente (stessa P.IVA scritta in altro modo
    compresa): altrimenti converge da solo.
    """
    stats: Dict[str, Any] = {
        "fatture_migrate": 0, "scadenze_migrate": 0,
        "prima_nota_cassa_migrati": 0, "prima_nota_banca_migrati": 0,
        "pagamenti_migrati": 0, "assegni_migrati": 0, "altri_migrati": {},
    }
    esistenti = set(await db.list_collection_names())
    nomi_stat = {Collections.INVOICES: "fatture_migrate", "scadenziario_fornitori": "scadenze_migrate"}
    for coll, campo in RIFERIMENTI_ID:
        if coll not in esistenti:
            continue
        res = await db[coll].update_many(_filtro_id(from_id, campo), {"$set": {campo: to_id}})
        n = int(res.modified_count or 0)
        if coll in nomi_stat:
            stats[nomi_stat[coll]] = n
        elif n:
            stats["altri_migrati"][coll] = n

    if piva_da and piva_a and str(piva_da) != str(piva_a):
        varianti = [v for v in varianti_piva(piva_da) if v != str(piva_a)]
        if varianti:
            filtro = ({"fornitore_piva": varianti[0]} if len(varianti) == 1
                      else {"fornitore_piva": {"$in": varianti}})
            nomi_piva = {"prima_nota_cassa": "prima_nota_cassa_migrati",
                         "prima_nota_banca": "prima_nota_banca_migrati",
                         "pagamenti": "pagamenti_migrati", "assegni": "assegni_migrati"}
            for coll in RIFERIMENTI_PIVA:
                if coll not in esistenti:
                    continue
                res = await db[coll].update_many(filtro, {"$set": {"fornitore_piva": piva_a}})
                n = int(res.modified_count or 0)
                if coll in nomi_piva:
                    stats[nomi_piva[coll]] = n
                elif n:
                    stats["altri_migrati"][coll] = stats["altri_migrati"].get(coll, 0) + n
    return stats


async def _invalida_cache() -> None:
    try:
        from app.middleware.performance import cache
        from app.routers.suppliers_module.common import SUPPLIERS_CACHE_KEY
        await cache.clear_pattern(SUPPLIERS_CACHE_KEY)
    except Exception as exc:  # la cache scade da sola: non blocca la fusione
        logger.warning("Fornitori: cache non svuotata (%s: %s)", type(exc).__name__, exc)


async def merge_fornitori(target_id: Any, duplicate_id: Any, soft: bool = True,
                          motivo: str = "manuale") -> Dict[str, Any]:
    """Unifica `duplicate_id` dentro `target_id`, senza cancellare niente.

    - I campi vuoti del vincente si completano con quelli del perdente.
    - Alias (nomi del perdente), IBAN diverso (`iban_alternativi`), id
      precedenti e uno `storico_fusioni` restano sul vincente.
    - Fatture, scadenze, acquisti, metodi, parole chiave, alert, movimenti e
      proposte passano per id al vincente; le righe indicizzate per P.IVA
      seguono se la P.IVA del perdente e' diversa.
    - Il perdente resta con `status='unificato'` e `merged_into`.
    - Due P.IVA valide diverse: rifiutato.
    """
    if not soft:
        raise ValueError("La cancellazione di un fornitore non e' ammessa: la fusione e' sempre soft")
    db = Database.get_db()
    coll = db[Collections.SUPPLIERS]
    if str(target_id) == str(duplicate_id):
        raise ValueError("target_id e duplicate_id sono uguali")
    target = await coll.find_one(_filtro_id(target_id), {"_id": 0})
    dup = await coll.find_one(_filtro_id(duplicate_id), {"_id": 0})
    if not target or not dup:
        raise ValueError("Target o duplicato non trovati")
    if dup.get("merged_into") or target.get("merged_into"):
        raise ValueError("Uno dei due fornitori e' gia' stato unificato")
    p_t, p_d = _get_piva(target), _get_piva(dup)
    if chiave_confronto(p_t) and chiave_confronto(p_d) and chiave_confronto(p_t) != chiave_confronto(p_d) \
            and piva_valida(p_t) and piva_valida(p_d):
        raise ValueError("Partite IVA valide diverse: non sono lo stesso fornitore (correggi prima la P.IVA)")

    ora = datetime.now(timezone.utc).isoformat()
    aggiornamento: Dict[str, Any] = {}
    gestiti = ("id", "_id", "created_at", "merged_into", "status", "alias", "id_precedenti",
               "storico_fusioni", "iban_alternativi", "fatture_count", "updated_at")
    for k, v in dup.items():
        if k in gestiti or v in _VUOTI:
            continue
        if target.get(k) in _VUOTI:
            aggiornamento[k] = v

    conflitti = []
    for k in ("iban", "metodo_pagamento", "esclude_magazzino", "codice_fiscale", "partita_iva"):
        a, b = target.get(k), dup.get(k)
        if a not in _VUOTI and b not in _VUOTI and str(a) != str(b):
            conflitti.append({"campo": k, "tenuto": a, "scartato": b})
    if dup.get("iban") not in _VUOTI and target.get("iban") not in _VUOTI \
            and str(dup["iban"]) != str(target["iban"]):
        alt = list(target.get("iban_alternativi") or [])
        if dup["iban"] not in alt:
            alt.append(dup["iban"])
        aggiornamento["iban_alternativi"] = alt

    n_t = {_norm_nome(n) for n in _nomi(target)}
    alias = [str(a) for a in (target.get("alias") or [])]
    for n in _nomi(dup) + [str(a) for a in (dup.get("alias") or [])]:
        if _norm_nome(n) not in n_t and n not in alias:
            alias.append(n)
    if alias != list(target.get("alias") or []):
        aggiornamento["alias"] = alias
    precedenti = [str(x) for x in (target.get("id_precedenti") or [])]
    for x in [dup.get("id")] + list(dup.get("id_precedenti") or []):
        if x not in (None, "") and str(x) not in precedenti:
            precedenti.append(str(x))
    aggiornamento["id_precedenti"] = precedenti

    conteggio_dup = int(dup.get("fatture_count") or 0)
    if conteggio_dup:
        aggiornamento["fatture_count"] = int(target.get("fatture_count") or 0) + conteggio_dup

    piva_finale = aggiornamento.get("partita_iva") or aggiornamento.get("piva") or p_t or None
    stats = await _migra_riferimenti(db, dup.get("id"), target.get("id"),
                                     dup.get("partita_iva") or dup.get("piva"),
                                     target.get("partita_iva") or target.get("piva") or piva_finale)

    storico = list(target.get("storico_fusioni") or [])
    storico.append({"da": dup.get("id"), "nome": _get_nome(dup), "quando": ora, "motivo": motivo,
                    "campi_aggiunti": sorted(k for k in aggiornamento if k not in ("storico_fusioni", "updated_at")),
                    "conflitti": conflitti, "migrazione": stats})
    aggiornamento["storico_fusioni"] = storico
    aggiornamento["updated_at"] = ora
    await coll.update_one(_filtro_id(target.get("id")), {"$set": aggiornamento})
    segno_perdente: Dict[str, Any] = {
        "merged_into": target.get("id"), "status": "unificato", "merged_at": ora,
        "merged_motivo": motivo, "updated_at": ora,
    }
    if chiave_confronto(p_d) and chiave_confronto(p_d) == chiave_confronto(p_t):
        # Stessa P.IVA del vincente: chi cerca per P.IVA deve trovare solo lui.
        # Il valore resta scritto in `piva_unificata` e nello storico del vincente.
        segno_perdente["piva_unificata"] = p_d
        for campo in ("partita_iva", "piva", "vat_number", "vat", "match_key"):
            if dup.get(campo) not in _VUOTI:
                segno_perdente[campo] = ""
    await coll.update_one(_filtro_id(dup.get("id")), {"$set": segno_perdente})
    logger.info("Merge fornitori: %s -> %s (%s). Stats: %s", dup.get("id"), target.get("id"), motivo, stats)
    return {
        "success": True, "target_id": target.get("id"), "duplicate_id": dup.get("id"),
        "action": "soft_merged",
        "campi_aggiunti_al_target": sorted(k for k in aggiornamento if k not in ("storico_fusioni", "updated_at")),
        "conflitti": conflitti, "stats_migrazione": stats,
    }


# ── P.IVA mancante ricavata dalle fatture ──────────────────────────────────

async def completa_piva_da_fatture(db=None, dry_run: bool = False) -> Dict[str, Any]:
    """Un fornitore senza P.IVA la riceve dalle sue fatture, solo se e' una sola.

    Fonte: `supplier_id` della fattura; in mancanza, nome identico (normalizzato).
    P.IVA diverse fra le fatture, o non valide: non si tocca (resta la segnalazione).
    """
    db = db or Database.get_db()
    senza = await db[Collections.SUPPLIERS].find(
        {"merged_into": {"$exists": False}}, {"_id": 0}).to_list(10000)
    senza = [f for f in senza if f.get("id") not in (None, "") and not _get_piva(f)]
    if not senza:
        return {"completati": 0, "dry_run": dry_run, "elenco": []}
    per_id: Dict[str, set] = {}
    per_nome: Dict[str, set] = {}
    fatture = await db[Collections.INVOICES].find(
        {}, {"_id": 0, "supplier_id": 1, "supplier_name": 1, "cedente_denominazione": 1,
             "supplier_vat": 1, "cedente_piva": 1}).to_list(200000)
    for d in fatture:
        p = normalizza_piva(d.get("cedente_piva") or d.get("supplier_vat"))
        if not p or not piva_valida(p):
            continue
        if d.get("supplier_id") not in (None, ""):
            per_id.setdefault(str(d["supplier_id"]), set()).add(p)
        n = _norm_nome(d.get("supplier_name") or d.get("cedente_denominazione"))
        if n:
            per_nome.setdefault(n, set()).add(p)
    elenco, ora = [], datetime.now(timezone.utc).isoformat()
    for f in senza:
        cand = per_id.get(str(f["id"])) or per_nome.get(_norm_nome(_get_nome(f))) or set()
        if len(cand) != 1:
            continue
        piva = next(iter(cand))
        elenco.append({"id": f["id"], "nome": _get_nome(f), "partita_iva": piva})
        if not dry_run:
            storico = list(f.get("storico_piva") or [])
            storico.append({"quando": ora, "valore": piva, "fonte": "fatture"})
            await db[Collections.SUPPLIERS].update_one(_filtro_id(f["id"]), {"$set": {
                "partita_iva": piva, "piva": piva, "match_key": piva,
                "piva_fonte": "fatture", "storico_piva": storico, "updated_at": ora}})
    return {"completati": len(elenco), "dry_run": dry_run, "elenco": elenco}


async def riallinea_fatture_orfane(db=None, dry_run: bool = False) -> Dict[str, Any]:
    """Fatture il cui `supplier_id` non esiste piu': si ripuntano per P.IVA, se univoca."""
    db = db or Database.get_db()
    forn = await db[Collections.SUPPLIERS].find(
        {"merged_into": {"$exists": False}}, {"_id": 0}).to_list(10000)
    ids = {str(f.get("id")) for f in forn if f.get("id") not in (None, "")}
    per_piva: Dict[str, List[Any]] = {}
    for f in forn:
        k = chiave_confronto(_get_piva(f))
        if k and f.get("id") not in (None, ""):
            per_piva.setdefault(k, []).append(f["id"])
    fatture = await db[Collections.INVOICES].find(
        {"supplier_id": {"$exists": True}}, {"_id": 0, "id": 1, "supplier_id": 1,
                                             "cedente_piva": 1, "supplier_vat": 1}).to_list(200000)
    ripuntate = 0
    orfane: Dict[Any, Any] = {}
    for d in fatture:
        sid = d.get("supplier_id")
        if sid in (None, "") or str(sid) in ids:
            continue
        cand = per_piva.get(chiave_confronto(d.get("cedente_piva") or d.get("supplier_vat")), [])
        if len(cand) == 1:
            orfane[sid] = cand[0]
    for sid, nuovo in orfane.items():
        if dry_run:
            ripuntate += 1
            continue
        res = await db[Collections.INVOICES].update_many(
            _filtro_id(sid, "supplier_id"), {"$set": {"supplier_id": nuovo}})
        ripuntate += int(res.modified_count or 0)
    return {"fatture_ripuntate": ripuntate, "id_orfani": len(orfane), "dry_run": dry_run}


# ── giro ───────────────────────────────────────────────────────────────────

async def giro_unifica_fornitori(dry_run: bool = False) -> Dict[str, Any]:
    """Completa le P.IVA, fonde certi e probabili da soli, elenca il resto.

    Idempotente: il secondo giro non trova niente da fare.
    """
    db = Database.get_db()
    completamento = await completa_piva_da_fatture(db, dry_run=dry_run)
    cl = await classifica_duplicati(db)
    fusi: List[Dict[str, Any]] = []
    coppie = [(c["vincente"], p, c["motivo"]) for c in cl["certi"] for p in c["perdenti"]]
    coppie += [(p["vincente"], p["perdente"], p["motivo"]) for p in cl["probabili"]]
    for win, per, motivo in coppie:
        voce = {"target_id": win["id"], "duplicate_id": per["id"], "nome": per["nome"], "motivo": motivo}
        if dry_run:
            fusi.append({**voce, "dry_run": True})
            continue
        try:
            res = await merge_fornitori(win["id"], per["id"], motivo=f"automatico: {motivo}")
            fusi.append({**voce, "stats": res["stats_migrazione"]})
        except ValueError as exc:
            logger.warning("Fornitori: fusione %s -> %s saltata (%s: %s)",
                           per["id"], win["id"], type(exc).__name__, exc)
    orfane = await riallinea_fatture_orfane(db, dry_run=dry_run)
    if fusi and not dry_run:
        await _invalida_cache()
    return {
        "dry_run": dry_run,
        "piva_completate": completamento["completati"],
        "certi": cl["totali"]["certi"],
        "probabili": cl["totali"]["probabili"],
        "fusi": fusi,
        "da_decidere": cl["totali"]["da_decidere"],
        "fatture_ripuntate": orfane["fatture_ripuntate"],
    }


async def auto_merge_tutti(dry_run: bool = True) -> Dict[str, Any]:
    """Compatibilita' con l'endpoint: lo stesso giro dello scheduler."""
    esito = await giro_unifica_fornitori(dry_run=dry_run)
    return {**esito, "merges": esito["fusi"], "totale_merges": len(esito["fusi"]),
            "gruppi_analizzati": esito["certi"] + esito["probabili"] + esito["da_decidere"]}
