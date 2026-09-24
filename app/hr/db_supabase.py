"""Adattatore Mongo -> Postgres/Supabase.

L'app e' scritta contro motor (269 punti chiamano `Database.get_db()`), ma il
cluster MongoDB non esiste piu'. Invece di riscrivere tutti i chiamanti, qui
c'e' un sottoinsieme dell'API di motor appoggiato a Postgres: ogni collection
diventa una tabella `app_<nome>` con una colonna `doc jsonb`.

Le collection in gioco sono piccole (dipendenti, users, tablet_operatori: decine
di documenti), quindi il filtro Mongo viene applicato in Python sui documenti
letti: niente traduzione query->SQL da mantenere, e il comportamento e' quello
di Mongo anche sugli operatori annidati.

Coperto: $ne $exists $in $nin $gt $gte $lt $lte $or $and, proiezioni
include/exclude, $set $setOnInsert $unset $inc $push, upsert, update_many,
delete_many, distinct, aggregate (sottoinsieme: $match $group $addFields
$sort $limit $skip, con accumulatori $sum/$avg/$first/$last/$push ed
espressioni $ifNull/$cond/$toUpper/$toLower/$toDate/$month — il sottoinsieme
usato davvero in questo repo, non un motore Mongo generico).
NON coperto: indici, find_one_and_*, bulk write, altri stage/operatori
aggregate oltre a quelli elencati sopra (sollevano NotImplementedError).
"""
import asyncio
import json
import logging
import os
import re
import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Set, Tuple

import asyncpg

logger = logging.getLogger(__name__)

_NOME_OK = re.compile(r"^[A-Za-z0-9_]+$")

# Campi noti per essere pesanti (PDF/file in base64) su alcune collection:
# la copia in memoria di ogni tabella non li contiene (vengono letti per id
# solo quando una lettura li vuole davvero) e aggregate() li esclude dalle
# letture in blocco quando la pipeline non li nomina.
_CAMPI_PESANTI = ("pdf_data", "file_data")

# Cache in memoria per tabella (17/09/2026). Prima ogni find/find_one/count/
# update rileggeva l'intera tabella da Postgres e filtrava in Python:
# pg_stat_statements dal 01/09 contava 218.000 letture complete di
# app_paghe_mensili e letture da 8 s l'una di app_bonifici (PDF de-toastati
# per poi buttarli). Ora ogni tabella letta resta in memoria nella versione
# leggera (senza _CAMPI_PESANTI); prima di servirla si legge UNA firma per
# tutte le tabelle in cache (conteggio + xmin massimo: cambia a ogni
# insert/update/delete, anche fatti fuori dall'app) al piu' ogni _FIRMA_TTL s;
# firma diversa → rilettura leggera di quella tabella. Le scritture di questo
# processo aggiornano la copia e ribasano la firma. Se la firma non e'
# disponibile si torna alla lettura diretta (mai un dato parziale), salvo la
# finestra di grazia. HR_RUNTIME_CACHE=0 la spegne.
_FIRMA_TTL = 15.0
_FIRMA_GRAZIA = 120.0
_IDRATAZIONE_LOTTO = 100


def _cache_attiva() -> bool:
    return os.environ.get("HR_RUNTIME_CACHE", "1").strip().lower() not in {"0", "false", "no", "off"}


def _campi_usati(filtro: Any) -> Set[str]:
    """Campi (di primo livello) letti da un filtro Mongo."""
    usati: Set[str] = set()

    def raccogli(f):
        if not isinstance(f, dict):
            return
        for k, v in f.items():
            if k in ("$or", "$and"):
                for sub in (v or []):
                    raccogli(sub)
            elif not k.startswith("$"):
                usati.add(k.split(".")[0])

    raccogli(filtro)
    return usati


def _tabella(collection: str) -> str:
    if not _NOME_OK.match(collection):
        raise ValueError("nome collection non valido: %r" % collection)
    return "app_" + collection.lower()


class _Mancante:
    """Sentinella: campo assente, diverso da None (Mongo li distingue)."""

    def __repr__(self) -> str:
        return "<mancante>"


_MANCANTE = _Mancante()


def _get(doc: Dict[str, Any], path: str) -> Any:
    cur: Any = doc
    for parte in path.split("."):
        if not isinstance(cur, dict) or parte not in cur:
            return _MANCANTE
        cur = cur[parte]
    return cur


def _confronta(valore: Any, cond: Any) -> bool:
    """Applica una condizione Mongo a un singolo valore."""
    if isinstance(cond, dict) and any(k.startswith("$") for k in cond):
        # $options accompagna $regex e viene letto li', non come operatore a se'
        flags = re.I if "i" in (cond.get("$options") or "") else 0
        for op, atteso in cond.items():
            presente = valore is not _MANCANTE
            if op == "$options":
                continue
            if op == "$eq":
                if not (presente and valore == atteso):
                    return False
            elif op == "$ne":
                if presente and valore == atteso:
                    return False
            elif op == "$exists":
                if presente != bool(atteso):
                    return False
            elif op == "$in":
                # Mongo: un campo assente equivale a null per $in — se None e'
                # tra i valori richiesti, un documento senza il campo combacia
                # comunque (es. contratti vecchi senza "stato" in
                # {"stato": {"$in": [..., None]}}).
                if presente:
                    if valore not in atteso:
                        return False
                elif None not in atteso:
                    return False
            elif op == "$nin":
                if presente and valore in atteso:
                    return False
            elif op in ("$gt", "$gte", "$lt", "$lte"):
                if not presente:
                    return False
                try:
                    if op == "$gt" and not valore > atteso:
                        return False
                    if op == "$gte" and not valore >= atteso:
                        return False
                    if op == "$lt" and not valore < atteso:
                        return False
                    if op == "$lte" and not valore <= atteso:
                        return False
                except TypeError:
                    return False
            elif op == "$regex":
                if not (presente and isinstance(valore, str)
                        and re.search(atteso, valore, flags)):
                    return False
            else:
                raise NotImplementedError("operatore non supportato: " + op)
        return True
    return valore is not _MANCANTE and valore == cond


def _match(doc: Dict[str, Any], filtro: Optional[Dict[str, Any]]) -> bool:
    if not filtro:
        return True
    for chiave, cond in filtro.items():
        if chiave == "$or":
            if not any(_match(doc, sub) for sub in cond):
                return False
        elif chiave == "$and":
            if not all(_match(doc, sub) for sub in cond):
                return False
        elif chiave.startswith("$"):
            raise NotImplementedError("operatore top-level non supportato: " + chiave)
        else:
            if not _confronta(_get(doc, chiave), cond):
                return False
    return True


def _proietta(doc: Dict[str, Any], proj: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not proj:
        return doc
    campi = {k: v for k, v in proj.items() if k != "_id"}
    if campi and all(bool(v) for v in campi.values()):        # include
        out = {k: doc[k] for k in campi if k in doc}
    elif campi:                                                # exclude
        out = {k: v for k, v in doc.items() if k not in campi}
    else:
        out = dict(doc)
    if proj.get("_id", 1):
        if "_id" in doc:
            out.setdefault("_id", doc["_id"])
    else:
        out.pop("_id", None)
    return out


def _applica_update(doc: Dict[str, Any], update: Dict[str, Any],
                    inserito: bool) -> Dict[str, Any]:
    if not any(k.startswith("$") for k in update):
        return dict(update)                                    # replace completo
    nuovo = dict(doc)
    for op, campi in update.items():
        if op == "$set":
            nuovo.update(campi)
        elif op == "$setOnInsert":
            if inserito:
                nuovo.update(campi)
        elif op == "$unset":
            for k in campi:
                nuovo.pop(k, None)
        elif op == "$inc":
            for k, delta in campi.items():
                nuovo[k] = (nuovo.get(k) or 0) + delta
        elif op == "$push":
            # Solo forma semplice {campo: valore}: nessun $each/$slice/$position,
            # non usati da nessun chiamante in questo repo.
            for k, v in campi.items():
                # dict(doc) e' una copia shallow: senza list(...) qui sotto,
                # `lista` sarebbe lo STESSO oggetto lista di `doc[k]", quindi
                # l'append muterebbe anche il documento originale e il confronto
                # `nuovo != doc` usato per il change-detection risulterebbe
                # sempre uguale, facendo saltare l'UPDATE in update_many (trovato
                # da una review automatica prima del deploy).
                lista = list(nuovo.get(k)) if isinstance(nuovo.get(k), list) else []
                lista.append(v)
                nuovo[k] = lista
        else:
            raise NotImplementedError("update non supportato: " + op)
    return nuovo


def _truthy(v: Any) -> bool:
    """Verita' in stile Mongo per $cond: null/mancante/false/0/"" sono falsi."""
    return bool(v) if v is not None and v is not _MANCANTE else False


def _parse_data(v: Any):
    """Converte una stringa data/ora ISO in datetime, per $toDate/$month."""
    if isinstance(v, (datetime, date)):
        return v
    if isinstance(v, str):
        try:
            return datetime.fromisoformat(v[:19])
        except ValueError:
            return None
    return None


def _eval_expr(doc: Dict[str, Any], expr: Any) -> Any:
    """Valuta un'espressione di aggregazione Mongo (sottoinsieme usato in questo repo)."""
    if isinstance(expr, str) and expr.startswith("$"):
        v = _get(doc, expr[1:])
        return None if v is _MANCANTE else v
    if isinstance(expr, dict) and len(expr) == 1 and next(iter(expr)).startswith("$"):
        op, arg = next(iter(expr.items()))
        if op == "$ifNull":
            a, b = arg
            v = _eval_expr(doc, a)
            return v if v is not None else _eval_expr(doc, b)
        if op == "$cond":
            if isinstance(arg, list):
                condv, thenv, elsev = arg
            else:
                condv, thenv, elsev = arg["if"], arg["then"], arg["else"]
            return _eval_expr(doc, thenv) if _truthy(_eval_expr(doc, condv)) else _eval_expr(doc, elsev)
        if op == "$toUpper":
            v = _eval_expr(doc, arg[0] if isinstance(arg, list) else arg)
            return v.upper() if isinstance(v, str) else v
        if op == "$toLower":
            v = _eval_expr(doc, arg[0] if isinstance(arg, list) else arg)
            return v.lower() if isinstance(v, str) else v
        if op == "$toDate":
            return _parse_data(_eval_expr(doc, arg[0] if isinstance(arg, list) else arg))
        if op == "$month":
            d = _eval_expr(doc, arg[0] if isinstance(arg, list) else arg)
            d = d if isinstance(d, (datetime, date)) else _parse_data(d)
            return d.month if d else None
        raise NotImplementedError("espressione aggregate non supportata: " + op)
    if isinstance(expr, dict):
        # dizionario letterale a piu' chiavi (es. _id composto): valutato campo per campo
        return {k: _eval_expr(doc, v) for k, v in expr.items()}
    return expr  # letterale (numero, stringa semplice, bool, None, lista...)


def _eval_group_id(doc: Dict[str, Any], id_expr: Any) -> Any:
    if isinstance(id_expr, dict) and any(k.startswith("$") for k in id_expr):
        return _eval_expr(doc, id_expr)
    if isinstance(id_expr, dict):
        return {k: _eval_expr(doc, v) for k, v in id_expr.items()}
    return _eval_expr(doc, id_expr)


def _applica_accumulatore(docs: List[Dict[str, Any]], spec: Any) -> Any:
    if not (isinstance(spec, dict) and len(spec) == 1):
        raise NotImplementedError("accumulatore aggregate non riconosciuto: %r" % (spec,))
    op, expr = next(iter(spec.items()))
    if op == "$sum":
        tot = 0
        for d in docs:
            if expr == 1:
                tot += 1
                continue
            v = _eval_expr(d, expr)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                tot += v
        return tot
    if op == "$avg":
        vals = [v for v in (_eval_expr(d, expr) for d in docs)
                if isinstance(v, (int, float)) and not isinstance(v, bool)]
        return (sum(vals) / len(vals)) if vals else None
    if op == "$first":
        return _eval_expr(docs[0], expr) if docs else None
    if op == "$last":
        return _eval_expr(docs[-1], expr) if docs else None
    if op == "$push":
        return [_eval_expr(d, expr) for d in docs]
    raise NotImplementedError("accumulatore aggregate non supportato: " + op)


def _chiave_ordine(v: Any):
    """Chiave d'ordinamento che non mescola i tipi.

    I numeri restano numeri: stringere tutto a stringa metterebbe il mese 3
    dopo l'11. Il primo elemento raggruppa per tipo cosi' che valori
    disomogenei nella stessa colonna non facciano esplodere il confronto.
    """
    if v is _MANCANTE or v is None:
        return (0, 0)
    if isinstance(v, bool):
        return (1, int(v))
    if isinstance(v, (int, float)):
        return (2, v)
    return (3, str(v))


class _Risultato:
    """Un solo tipo di risultato per update/delete (motor ne ha due,
    UpdateResult e DeleteResult): deleted_count == matched_count per le
    cancellazioni, cosi' i chiamanti scritti contro l'uno o l'altro attributo
    funzionano entrambi (es. repositories/base_repository.py legge
    deleted_count — mancava, trovato da una review automatica)."""
    def __init__(self, matched: int, modified: int, upserted_id: Any = None):
        self.matched_count = matched
        self.modified_count = modified
        self.deleted_count = matched
        self.upserted_id = upserted_id


class _Cursore:
    """Cursore compatibile con motor: `await cur.to_list(n)` e `async for`."""

    def __init__(self, coll, filtro, proj, limite=None, ordina=None):
        self._coll, self._filtro, self._proj = coll, filtro, proj
        self._limite, self._ordina = limite, ordina
        self._iter = None

    def sort(self, chiave, direzione=1):
        # motor accetta sia sort("anno", -1) sia sort([("anno", -1), ("mese", -1)])
        if isinstance(chiave, (list, tuple)) and not isinstance(chiave, str):
            self._ordina = [tuple(c) for c in chiave]
        else:
            self._ordina = [(chiave, direzione)]
        return self

    def limit(self, n):
        self._limite = n
        return self

    async def _materializza(self) -> List[Dict[str, Any]]:
        escludi = self._coll._escludibili(self._filtro, self._proj)
        # Un campo su cui si ordina va letto, anche se la proiezione lo esclude:
        # l'ordinamento avviene qui, dopo la lettura.
        chiavi_ordine = {k.split(".")[0] for k, _ in (self._ordina or [])}
        escludi = [k for k in escludi if k not in chiavi_ordine]
        docs = await self._coll._seleziona(self._filtro, escludi)
        # ordinamenti multipli: si applicano dal meno al piu' significativo
        for chiave, direzione in reversed(self._ordina or []):
            docs.sort(key=lambda d, k=chiave: _chiave_ordine(_get(d, k)),
                      reverse=direzione < 0)
        if self._limite:
            docs = docs[: self._limite]
        return [_proietta(d, self._proj) for d in docs]

    async def to_list(self, length: Optional[int] = None) -> List[Dict[str, Any]]:
        docs = await self._materializza()
        return docs[:length] if length else docs

    def __aiter__(self):
        self._iter = None
        return self

    async def __anext__(self):
        if self._iter is None:
            self._iter = iter(await self._materializza())
        try:
            return next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class _CursoreAggregato:
    """Cursore per `aggregate()`: stesse due modalita' di consumo di _Cursore
    (`await cur.to_list(n)` e `async for`), ma materializza eseguendo in Python
    la pipeline invece di un filtro/proiezione singoli."""

    def __init__(self, coll, pipeline: List[Dict[str, Any]], escludi: Optional[List[str]] = None):
        self._coll, self._pipeline, self._escludi = coll, pipeline, escludi or []
        self._iter = None

    async def _materializza(self) -> List[Dict[str, Any]]:
        docs = await self._coll._tutti(self._escludi)
        for stage in self._pipeline:
            if len(stage) != 1:
                raise NotImplementedError("stage aggregate non riconosciuto: %r" % (stage,))
            op, arg = next(iter(stage.items()))
            if op == "$match":
                docs = [d for d in docs if _match(d, arg)]
            elif op == "$addFields":
                nuovi = []
                for d in docs:
                    d2 = dict(d)
                    for k, expr in arg.items():
                        d2[k] = _eval_expr(d2, expr)
                    nuovi.append(d2)
                docs = nuovi
            elif op == "$group":
                id_expr = arg.get("_id")
                acc_specs = {k: v for k, v in arg.items() if k != "_id"}
                gruppi: Dict[str, Dict[str, Any]] = {}
                ordine: List[str] = []
                for d in docs:
                    gid = _eval_group_id(d, id_expr)
                    chiave = json.dumps(gid, sort_keys=True, default=str)
                    if chiave not in gruppi:
                        gruppi[chiave] = {"_id": gid, "_docs": []}
                        ordine.append(chiave)
                    gruppi[chiave]["_docs"].append(d)
                docs = []
                for chiave in ordine:
                    g = gruppi[chiave]
                    riga = {"_id": g["_id"]}
                    for campo, spec in acc_specs.items():
                        riga[campo] = _applica_accumulatore(g["_docs"], spec)
                    docs.append(riga)
            elif op == "$sort":
                for chiave, direzione in reversed(list(arg.items())):
                    docs = sorted(docs, key=lambda d, k=chiave: _chiave_ordine(_get(d, k)),
                                  reverse=direzione < 0)
            elif op == "$limit":
                docs = docs[:arg]
            elif op == "$skip":
                docs = docs[arg:]
            else:
                raise NotImplementedError("stage aggregate non supportato: " + op)
        return docs

    async def to_list(self, length: Optional[int] = None) -> List[Dict[str, Any]]:
        docs = await self._materializza()
        return docs[:length] if length else docs

    def __aiter__(self):
        self._iter = None
        return self

    async def __anext__(self):
        if self._iter is None:
            self._iter = iter(await self._materializza())
        try:
            return next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class SupabaseCollection:
    def __init__(self, db: "SupabaseDatabase", nome: str):
        self._db = db
        self._nome = nome
        self._tab = _tabella(nome)
        # copia leggera della tabella: id → documento senza _CAMPI_PESANTI;
        # _pesanti: id → campi pesanti presenti nella riga (da idratare per id)
        self._cache: Optional[Dict[str, Dict[str, Any]]] = None
        self._pesanti: Dict[str, Set[str]] = {}
        self._cache_firma: Optional[Tuple[int, int]] = None
        self._cache_lock = asyncio.Lock()

    @property
    def _sql_tab(self) -> str:
        return f'{self._db._schema_sql}."{self._tab}"'

    async def _assicura_tabella(self):
        if self._tab in self._db._tabelle_pronte:
            return
        async with self._db._pool.acquire() as con:
            # 17/09/2026: prima qui partivano SEMPRE un CREATE TABLE IF NOT
            # EXISTS e un ALTER TABLE ... ENABLE ROW LEVEL SECURITY, anche a
            # tabella gia' pronta: ogni DDL fa ricaricare lo schema a
            # PostgREST, che per un paio di minuti risponde 503 «Could not
            # query the database for the schema cache» a TUTTE le RPC del
            # gestionale (visto a ogni avvio dell'istanza, 29 tabelle HR =
            # 58 DDL). Ora si guarda il catalogo e si esegue il DDL solo se
            # manca davvero qualcosa.
            stato = await con.fetchrow(
                "SELECT c.relrowsecurity FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = $1 AND c.relname = $2 AND c.relkind = 'r'",
                self._db._schema, self._tab,
            )
            if stato is None:
                await con.execute(
                    'CREATE TABLE IF NOT EXISTS %s ('
                    ' id text PRIMARY KEY,'
                    ' doc jsonb NOT NULL)' % self._sql_tab
                )
            if stato is None or not stato["relrowsecurity"]:
                # RLS attiva e nessuna policy: il ruolo anon di PostgREST non
                # legge nulla (su questo progetto anon e' volutamente aperto).
                # La connessione diretta usa il proprietario, che scavalca la RLS.
                await con.execute(
                    'ALTER TABLE %s ENABLE ROW LEVEL SECURITY' % self._sql_tab
                )
        self._db._tabelle_pronte.add(self._tab)

    async def _tutti_sql(self, escludi=None) -> List[Dict[str, Any]]:
        """Lettura diretta da Postgres, togliendo in SQL i campi che non servono.

        `cedolini` tiene il PDF in base64 dentro il documento: leggere tutta la
        collection per filtrarla in Python significava trasferire decine di MB e
        andare in timeout. Con l'esclusione spinta nella query (`doc - 'pdf_data'`)
        gli elenchi tornano leggeri, e il PDF si legge solo quando serve davvero.
        """
        await self._assicura_tabella()
        if escludi:
            campi = ", ".join("'%s'" % c.replace("'", "''") for c in sorted(escludi))
            sql = 'SELECT doc - ARRAY[%s] AS doc FROM %s' % (campi, self._sql_tab)
        else:
            sql = 'SELECT doc FROM %s' % self._sql_tab
        async with self._db._pool.acquire() as con:
            righe = await con.fetch(sql)
        out = []
        for r in righe:
            doc = r["doc"]
            out.append(json.loads(doc) if isinstance(doc, str) else doc)
        return out

    # ----- cache leggera per tabella --------------------------------------

    async def _leggeri(self) -> Optional[List[Dict[str, Any]]]:
        """Copia leggera allineata alla firma remota; None = cache non usabile."""
        firma = await self._db._firma(self._tab)
        if firma is None:
            return None
        async with self._cache_lock:
            if self._cache is None or firma != self._cache_firma:
                await self._carica_cache()
                self._cache_firma = firma
            return list(self._cache.values())

    async def _carica_cache(self) -> None:
        await self._assicura_tabella()
        campi = ", ".join("'%s'" % c for c in _CAMPI_PESANTI)
        presenza = ", ".join("(doc ? '%s') AS p%d" % (c, i) for i, c in enumerate(_CAMPI_PESANTI))
        sql = 'SELECT id, (doc - ARRAY[%s]) AS doc, %s FROM %s' % (campi, presenza, self._sql_tab)
        async with self._db._pool.acquire() as con:
            righe = await con.fetch(sql)
        cache: Dict[str, Dict[str, Any]] = {}
        pesanti: Dict[str, Set[str]] = {}
        for r in righe:
            doc = r["doc"]
            doc = json.loads(doc) if isinstance(doc, str) else doc
            chiave = str(r["id"])
            cache[chiave] = doc
            presenti = {c for i, c in enumerate(_CAMPI_PESANTI) if r["p%d" % i]}
            if presenti:
                pesanti[chiave] = presenti
        self._cache, self._pesanti = cache, pesanti

    async def _idrata(self, docs: List[Dict[str, Any]], escludi) -> List[Dict[str, Any]]:
        """Aggiunge ai documenti (copie) i campi pesanti che hanno in tabella,
        letti per id a lotti: mai l'intera tabella con i PDF."""
        escludi = set(escludi or ())
        per_id: Dict[str, Dict[str, Any]] = {}
        campi: Set[str] = set()
        for d in docs:
            chiave = str(d.get("id") or d.get("_id"))
            presenti = self._pesanti.get(chiave)
            if not presenti:
                continue
            necessari = presenti - escludi
            if necessari:
                per_id[chiave] = d
                campi |= necessari
        if not per_id:
            return docs
        colonne = sorted(campi)
        sql = 'SELECT id, %s FROM %s WHERE id = ANY($1::text[])' % (
            ", ".join("doc -> '%s' AS c%d" % (c, i) for i, c in enumerate(colonne)),
            self._sql_tab,
        )
        chiavi = list(per_id)
        for inizio in range(0, len(chiavi), _IDRATAZIONE_LOTTO):
            lotto = chiavi[inizio:inizio + _IDRATAZIONE_LOTTO]
            async with self._db._pool.acquire() as con:
                righe = await con.fetch(sql, lotto)
            for r in righe:
                destinazione = per_id.get(str(r["id"]))
                if destinazione is None:
                    continue
                for i, c in enumerate(colonne):
                    v = r["c%d" % i]
                    if v is None:
                        continue
                    destinazione[c] = json.loads(v) if isinstance(v, str) else v
        return docs

    async def _seleziona(self, filtro, escludi=None, completi: bool = True,
                         limite: Optional[int] = None) -> List[Dict[str, Any]]:
        """Documenti che soddisfano il filtro (copie). Con completi=True
        portano anche i campi pesanti non esclusi (idratati per id); con
        completi=False li tralasciano sempre (conteggi, cancellazioni)."""
        escludi = list(escludi or [])
        usati = _campi_usati(filtro)
        if usati & set(_CAMPI_PESANTI):
            # il filtro guarda dentro un campo pesante: serve la riga intera,
            # e il campo citato deve arrivare anche se poi va tolto
            escludi_sql = [c for c in escludi if c not in usati]
            docs = [d for d in await self._tutti_sql(escludi_sql) if _match(d, filtro)]
            if len(escludi_sql) != len(escludi):
                docs = [{k: v for k, v in d.items() if k not in escludi} for d in docs]
            return docs[:limite] if limite else docs
        leggeri = await self._leggeri()
        if leggeri is None:
            docs = [d for d in await self._tutti_sql(escludi) if _match(d, filtro)]
            return docs[:limite] if limite else docs
        scelti = [dict(d) for d in leggeri if _match(d, filtro)]
        if limite:
            scelti = scelti[:limite]
        if completi:
            scelti = await self._idrata(scelti, escludi)
        if escludi:
            scelti = [{k: v for k, v in d.items() if k not in escludi} for d in scelti]
        return scelti

    async def _tutti(self, escludi=None) -> List[Dict[str, Any]]:
        """Tutti i documenti (copie), senza i campi in `escludi`."""
        escludi = list(escludi or [])
        leggeri = await self._leggeri()
        if leggeri is None:
            return await self._tutti_sql(escludi)
        docs = await self._idrata([dict(d) for d in leggeri], escludi)
        if escludi:
            docs = [{k: v for k, v in d.items() if k not in escludi} for d in docs]
        return docs

    async def _scrivi_cache(self, chiave: str, doc: Dict[str, Any]) -> None:
        """Scrittura di questo processo gia' confermata da Postgres."""
        if self._cache is None:
            return
        self._cache[chiave] = {k: v for k, v in doc.items() if k not in _CAMPI_PESANTI}
        presenti = {c for c in _CAMPI_PESANTI if c in doc}
        if presenti:
            self._pesanti[chiave] = presenti
        else:
            self._pesanti.pop(chiave, None)
        await self._ribasa()

    async def _rimuovi_cache(self, chiavi: List[str]) -> None:
        if self._cache is None:
            return
        for chiave in chiavi:
            self._cache.pop(chiave, None)
            self._pesanti.pop(chiave, None)
        await self._ribasa()

    async def _ribasa(self) -> None:
        """Dopo una scrittura propria la firma remota e' cambiata: la si
        rilegge subito cosi' la copia (gia' aggiornata) resta valida. Se non
        si riesce, la copia viene buttata: alla prossima lettura si ricarica."""
        try:
            firma = await self._db._firma_singola(self._tab)
        except Exception as exc:  # noqa: BLE001 - mai una cache non allineata
            logger.warning("HR firma di %s non rileggibile (%s): cache scartata", self._tab, exc)
            self._cache = None
            return
        self._cache_firma = firma
        self._db._firme[self._tab] = firma

    @staticmethod
    def _escludibili(filtro, proiezione) -> List[str]:
        """Campi che la proiezione esclude e che il filtro non usa: si possono
        togliere gia' in SQL senza cambiare il risultato."""
        if not proiezione:
            return []
        esclusi = [k for k, v in proiezione.items() if not v and k != "_id"]
        if not esclusi:
            return []
        usati = _campi_usati(filtro)
        return [k for k in esclusi if k not in usati]

    async def find_one(self, filtro=None, proiezione=None, **_):
        escludi = self._escludibili(filtro, proiezione)
        docs = await self._seleziona(filtro, escludi, limite=1)
        return _proietta(docs[0], proiezione) if docs else None

    def find(self, filtro=None, proiezione=None, **_) -> _Cursore:
        return _Cursore(self, filtro, proiezione)

    async def count_documents(self, filtro=None, **_) -> int:
        return len(await self._seleziona(filtro, list(_CAMPI_PESANTI), completi=False))

    async def estimated_document_count(self, **_) -> int:
        return await self.count_documents(None)

    async def insert_one(self, doc: Dict[str, Any]) -> _Risultato:
        await self._assicura_tabella()
        doc = dict(doc)
        chiave = str(doc.get("id") or doc.get("_id") or uuid.uuid4())
        doc.setdefault("id", chiave)
        async with self._db._pool.acquire() as con:
            await con.execute(
                'INSERT INTO %s (id, doc) VALUES ($1, $2::jsonb)' % self._sql_tab,
                chiave, json.dumps(doc, default=str),
            )
        await self._scrivi_cache(chiave, doc)
        return _Risultato(0, 0, chiave)

    async def update_one(self, filtro, update, upsert: bool = False, **_) -> _Risultato:
        await self._assicura_tabella()
        # documento COMPLETO (campi pesanti idratati per id): viene riscritto
        # per intero, senza il PDF lo cancellerebbe
        trovati = await self._seleziona(filtro, limite=1)
        esistente = trovati[0] if trovati else None

        if esistente is None:
            if not upsert:
                return _Risultato(0, 0)
            base = {k: v for k, v in (filtro or {}).items()
                    if not k.startswith("$") and not isinstance(v, dict)}
            nuovo = _applica_update(base, update, inserito=True)
            chiave = str(nuovo.get("id") or nuovo.get("_id") or uuid.uuid4())
            nuovo.setdefault("id", chiave)
            async with self._db._pool.acquire() as con:
                await con.execute(
                    'INSERT INTO %s (id, doc) VALUES ($1, $2::jsonb) '
                    'ON CONFLICT (id) DO UPDATE SET doc = EXCLUDED.doc' % self._sql_tab,
                    chiave, json.dumps(nuovo, default=str),
                )
            await self._scrivi_cache(chiave, nuovo)
            return _Risultato(0, 0, chiave)

        chiave = str(esistente.get("id") or esistente.get("_id"))
        nuovo = _applica_update(esistente, update, inserito=False)
        async with self._db._pool.acquire() as con:
            await con.execute(
                'UPDATE %s SET doc = $2::jsonb WHERE id = $1' % self._sql_tab,
                chiave, json.dumps(nuovo, default=str),
            )
        await self._scrivi_cache(chiave, nuovo)
        return _Risultato(1, 1 if nuovo != esistente else 0)

    async def delete_one(self, filtro, **_) -> _Risultato:
        await self._assicura_tabella()
        trovati = await self._seleziona(filtro, list(_CAMPI_PESANTI), completi=False, limite=1)
        if not trovati:
            return _Risultato(0, 0)
        chiave = str(trovati[0].get("id") or trovati[0].get("_id"))
        async with self._db._pool.acquire() as con:
            await con.execute(
                'DELETE FROM %s WHERE id = $1' % self._sql_tab, chiave
            )
        await self._rimuovi_cache([chiave])
        return _Risultato(1, 1)

    async def update_many(self, filtro, update, **_) -> _Risultato:
        await self._assicura_tabella()
        matched = modified = 0
        # Materializza PRIMA di aprire la connessione di scrittura: _tutti()
        # acquisisce a sua volta dal pool, e tenerne una ferma (inutilizzata)
        # mentre se ne aspetta una seconda puo' esaurire il pool (5 connessioni)
        # sotto concorrenza e bloccare fino al command_timeout di 60s (trovato
        # da una review automatica prima del deploy).
        # NOTA (trovato dal 4o giro di review, non risolto qui): tra la lettura
        # sopra e la UPDATE qui sotto, una modifica concorrente allo stesso
        # documento (da un'altra richiesta) verrebbe sovrascritta insieme al
        # resto del documento — stesso limite gia' presente da sempre in
        # update_one/delete_one (letti-poi-scritti senza lock). Non e' una
        # regressione di update_many/delete_many: e' il design dell'intero
        # adattatore (collection piccole, pochi utenti admin/responsabile
        # turni concorrenti). Risolverlo davvero servirebbe row lock/merge
        # JSONB lato SQL per ogni punto di scrittura, non solo qui: fuori
        # scope per un fix mirato, da valutare se in futuro la concorrenza
        # reale aumenta.
        docs = await self._seleziona(filtro)
        matched = len(docs)
        for d in docs:
            nuovo = _applica_update(d, update, inserito=False)
            if nuovo != d:
                chiave = str(d.get("id") or d.get("_id"))
                async with self._db._pool.acquire() as con:
                    await con.execute(
                        'UPDATE %s SET doc = $2::jsonb WHERE id = $1' % self._sql_tab,
                        chiave, json.dumps(nuovo, default=str),
                    )
                await self._scrivi_cache(chiave, nuovo)
                modified += 1
        return _Risultato(matched, modified)

    async def delete_many(self, filtro, **_) -> _Risultato:
        await self._assicura_tabella()
        # stesso limite di concorrenza documentato sopra in update_many: la
        # lista di id viene fissata alla lettura, non ri-verificata alla DELETE.
        chiavi = [
            str(d.get("id") or d.get("_id"))
            for d in await self._seleziona(filtro, list(_CAMPI_PESANTI), completi=False)
        ]
        if chiavi:
            async with self._db._pool.acquire() as con:
                await con.execute(
                    'DELETE FROM %s WHERE id = ANY($1::text[])' % self._sql_tab, chiavi
                )
            await self._rimuovi_cache(chiavi)
        return _Risultato(len(chiavi), len(chiavi))

    async def distinct(self, campo: str, filtro=None, **_) -> List[Any]:
        visti_set = set()
        out: List[Any] = []
        if campo.split(".")[0] in _CAMPI_PESANTI:
            docs = await self._seleziona(filtro)
        else:
            docs = await self._seleziona(filtro, list(_CAMPI_PESANTI), completi=False)
        for d in docs:
            v = _get(d, campo)
            if v is _MANCANTE:
                continue
            # Mongo: se il campo e' un array, distinct restituisce gli elementi
            # unici al suo interno, non l'array intero come valore unico
            # (trovato dal 6o giro di review; nessun chiamante attuale usa
            # distinct su un campo-array, ma il comportamento va allineato).
            valori = v if isinstance(v, list) else [v]
            for singolo in valori:
                chiave = json.dumps(singolo, sort_keys=True, default=str) if isinstance(singolo, (dict, list)) else singolo
                if chiave not in visti_set:
                    visti_set.add(chiave)
                    out.append(singolo)
        return out

    def aggregate(self, pipeline: List[Dict[str, Any]], **_) -> _CursoreAggregato:
        # aggregate() legge sempre l'intera collection prima di applicare la
        # pipeline in Python (niente pushdown SQL) — su `cedolini`, che tiene
        # il PDF in base64 dentro il documento, questo trasferirebbe decine di
        # MB per una pipeline che magari somma solo un campo numerico (stesso
        # problema di `_tutti()` gia' documentato sopra; trovato da una review
        # automatica sulle pipeline di tfr.py/cedolini.py/buste_paga.py). Ma
        # va escluso SOLO se una stage a valle scarta comunque la forma del
        # documento originale: tra le stage supportate, solo $group lo fa
        # ($match/$addFields/$sort/$limit/$skip restituiscono i documenti
        # originali intatti, quindi un campo pesante assente dal testo della
        # pipeline andrebbe comunque nel risultato — trovato dal terzo giro
        # di review). Anche con $group, se il campo compare da qualche parte
        # nella pipeline (es. un accumulatore che lo legge) si legge per
        # intero: mai un risultato silenziosamente sbagliato.
        ha_stage_che_scarta_forma = any("$group" in stage for stage in pipeline)
        if ha_stage_che_scarta_forma:
            pipeline_json = json.dumps(pipeline, default=str)
            escludi = [c for c in _CAMPI_PESANTI if c not in pipeline_json]
        else:
            escludi = []
        return _CursoreAggregato(self, pipeline, escludi)


class SupabaseDatabase:
    """Sta al posto dell'oggetto database di motor: `db["dipendenti"]`."""

    def __init__(self, pool: "asyncpg.Pool", schema: str = "public"):
        if not _NOME_OK.fullmatch(schema):
            raise ValueError("schema Postgres HR non valido: %r" % schema)
        self._pool = pool
        self._schema = schema
        self._schema_sql = '"' + schema + '"'
        self._tabelle_pronte: set = set()
        self._cache: Dict[str, SupabaseCollection] = {}
        # firme (righe, xmin massimo) delle tabelle in cache, lette insieme
        self._firme: Dict[str, Tuple[int, int]] = {}
        self._firme_at: Optional[float] = None
        self._firme_buone_at: Optional[float] = None
        self._firme_lock = asyncio.Lock()
        self._tabelle_in_cache: Set[str] = set()
        self._cache_attiva = _cache_attiva()

    def _sql_firma(self, tabelle) -> str:
        return " UNION ALL ".join(
            "SELECT '%s' AS t, count(*)::bigint AS n, coalesce(max(xmin::text::bigint), 0)::bigint AS x "
            "FROM %s.\"%s\"" % (t, self._schema_sql, t)
            for t in tabelle
        )

    async def _firma_singola(self, tab: str) -> Tuple[int, int]:
        async with self._pool.acquire() as con:
            righe = await con.fetch(self._sql_firma([tab]))
        r = righe[0]
        return int(r["n"]), int(r["x"])

    async def _firma(self, tab: str) -> Optional[Tuple[int, int]]:
        """Firma della tabella, letta con quelle di tutte le tabelle in cache
        al piu' ogni _FIRMA_TTL secondi. None = non disponibile: il chiamante
        legge direttamente da Postgres (mai un dato parziale)."""
        if not self._cache_attiva:
            return None
        loop = asyncio.get_running_loop()
        async with self._firme_lock:
            now = loop.time()
            if (
                self._firme_at is not None
                and now - self._firme_at < _FIRMA_TTL
                and tab in self._firme
            ):
                return self._firme[tab]
            tabelle = sorted(self._tabelle_in_cache | {tab})
            try:
                async with self._pool.acquire() as con:
                    righe = await con.fetch(self._sql_firma(tabelle))
            except Exception as exc:  # noqa: BLE001 - la cache non deve mai bloccare una lettura
                eta = None if self._firme_buone_at is None else now - self._firme_buone_at
                if eta is not None and eta < _FIRMA_GRAZIA and tab in self._firme:
                    logger.warning("HR firma tabelle non disponibile (%s): cache mantenuta (%.0f s)", exc, eta)
                    self._firme_at = now
                    return self._firme[tab]
                logger.warning("HR firma tabelle non disponibile (%s): lettura diretta", exc)
                return None
            self._firme = {str(r["t"]): (int(r["n"]), int(r["x"])) for r in righe}
            self._firme_at = now
            self._firme_buone_at = now
            self._tabelle_in_cache.update(tabelle)
            return self._firme.get(tab)

    def __getitem__(self, nome: str) -> SupabaseCollection:
        if nome not in self._cache:
            self._cache[nome] = SupabaseCollection(self, nome)
        return self._cache[nome]

    def __getattr__(self, nome: str) -> SupabaseCollection:
        if nome.startswith("_"):
            raise AttributeError(nome)
        return self[nome]

    async def list_collection_names(self) -> List[str]:
        async with self._pool.acquire() as con:
            righe = await con.fetch(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname=$1 AND tablename LIKE 'app\\_%'",
                self._schema,
            )
        return [r["tablename"][4:] for r in righe]


async def crea_database(dsn: str, schema: str = "public") -> SupabaseDatabase:
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5, command_timeout=60)
    logger.info("Supabase/Postgres connesso")
    return SupabaseDatabase(pool, schema=schema)
