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
import json
import logging
import re
import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import asyncpg

logger = logging.getLogger(__name__)

_NOME_OK = re.compile(r"^[A-Za-z0-9_]+$")

# Campi noti per essere pesanti (PDF in base64) su alcune collection: esclusi
# di default dalle letture in blocco di aggregate() quando la pipeline non li
# nomina — vedi SupabaseCollection.aggregate().
_CAMPI_PESANTI = ("pdf_data",)


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
        docs = [d for d in await self._coll._tutti(escludi) if _match(d, self._filtro)]
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
        except StopIteration:
            raise StopAsyncIteration


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
        except StopIteration:
            raise StopAsyncIteration


class SupabaseCollection:
    def __init__(self, db: "SupabaseDatabase", nome: str):
        self._db = db
        self._nome = nome
        self._tab = _tabella(nome)

    async def _assicura_tabella(self):
        if self._tab in self._db._tabelle_pronte:
            return
        async with self._db._pool.acquire() as con:
            await con.execute(
                'CREATE TABLE IF NOT EXISTS public."%s" ('
                ' id text PRIMARY KEY,'
                ' doc jsonb NOT NULL)' % self._tab
            )
            # RLS attiva e nessuna policy: il ruolo anon di PostgREST non legge
            # nulla (su questo progetto anon e' volutamente aperto). La
            # connessione diretta usa il proprietario, che scavalca la RLS.
            await con.execute(
                'ALTER TABLE public."%s" ENABLE ROW LEVEL SECURITY' % self._tab
            )
        self._db._tabelle_pronte.add(self._tab)

    async def _tutti(self, escludi=None) -> List[Dict[str, Any]]:
        """Legge i documenti, togliendo in SQL i campi che non servono.

        `cedolini` tiene il PDF in base64 dentro il documento: leggere tutta la
        collection per filtrarla in Python significava trasferire decine di MB e
        andare in timeout. Con l'esclusione spinta nella query (`doc - 'pdf_data'`)
        gli elenchi tornano leggeri, e il PDF si legge solo quando serve davvero.
        """
        await self._assicura_tabella()
        if escludi:
            campi = ", ".join("'%s'" % c.replace("'", "''") for c in sorted(escludi))
            sql = 'SELECT doc - ARRAY[%s] AS doc FROM public."%s"' % (campi, self._tab)
        else:
            sql = 'SELECT doc FROM public."%s"' % self._tab
        async with self._db._pool.acquire() as con:
            righe = await con.fetch(sql)
        out = []
        for r in righe:
            doc = r["doc"]
            out.append(json.loads(doc) if isinstance(doc, str) else doc)
        return out

    @staticmethod
    def _escludibili(filtro, proiezione) -> List[str]:
        """Campi che la proiezione esclude e che il filtro non usa: si possono
        togliere gia' in SQL senza cambiare il risultato."""
        if not proiezione:
            return []
        esclusi = [k for k, v in proiezione.items() if not v and k != "_id"]
        if not esclusi:
            return []
        usati = set()

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
        return [k for k in esclusi if k not in usati]

    async def find_one(self, filtro=None, proiezione=None, **_):
        escludi = self._escludibili(filtro, proiezione)
        for d in await self._tutti(escludi):
            if _match(d, filtro):
                return _proietta(d, proiezione)
        return None

    def find(self, filtro=None, proiezione=None, **_) -> _Cursore:
        return _Cursore(self, filtro, proiezione)

    async def count_documents(self, filtro=None, **_) -> int:
        return sum(1 for d in await self._tutti() if _match(d, filtro))

    async def estimated_document_count(self, **_) -> int:
        return await self.count_documents(None)

    async def insert_one(self, doc: Dict[str, Any]) -> _Risultato:
        await self._assicura_tabella()
        doc = dict(doc)
        chiave = str(doc.get("id") or doc.get("_id") or uuid.uuid4())
        doc.setdefault("id", chiave)
        async with self._db._pool.acquire() as con:
            await con.execute(
                'INSERT INTO public."%s" (id, doc) VALUES ($1, $2::jsonb)' % self._tab,
                chiave, json.dumps(doc, default=str),
            )
        return _Risultato(0, 0, chiave)

    async def update_one(self, filtro, update, upsert: bool = False, **_) -> _Risultato:
        await self._assicura_tabella()
        esistente = None
        for d in await self._tutti():
            if _match(d, filtro):
                esistente = d
                break

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
                    'INSERT INTO public."%s" (id, doc) VALUES ($1, $2::jsonb) '
                    'ON CONFLICT (id) DO UPDATE SET doc = EXCLUDED.doc' % self._tab,
                    chiave, json.dumps(nuovo, default=str),
                )
            return _Risultato(0, 0, chiave)

        chiave = str(esistente.get("id") or esistente.get("_id"))
        nuovo = _applica_update(esistente, update, inserito=False)
        async with self._db._pool.acquire() as con:
            await con.execute(
                'UPDATE public."%s" SET doc = $2::jsonb WHERE id = $1' % self._tab,
                chiave, json.dumps(nuovo, default=str),
            )
        return _Risultato(1, 1 if nuovo != esistente else 0)

    async def delete_one(self, filtro, **_) -> _Risultato:
        await self._assicura_tabella()
        for d in await self._tutti():
            if _match(d, filtro):
                chiave = str(d.get("id") or d.get("_id"))
                async with self._db._pool.acquire() as con:
                    await con.execute(
                        'DELETE FROM public."%s" WHERE id = $1' % self._tab, chiave
                    )
                return _Risultato(1, 1)
        return _Risultato(0, 0)

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
        docs = [d for d in await self._tutti() if _match(d, filtro)]
        matched = len(docs)
        for d in docs:
            nuovo = _applica_update(d, update, inserito=False)
            if nuovo != d:
                chiave = str(d.get("id") or d.get("_id"))
                async with self._db._pool.acquire() as con:
                    await con.execute(
                        'UPDATE public."%s" SET doc = $2::jsonb WHERE id = $1' % self._tab,
                        chiave, json.dumps(nuovo, default=str),
                    )
                modified += 1
        return _Risultato(matched, modified)

    async def delete_many(self, filtro, **_) -> _Risultato:
        await self._assicura_tabella()
        # stesso limite di concorrenza documentato sopra in update_many: la
        # lista di id viene fissata alla lettura, non ri-verificata alla DELETE.
        chiavi = [str(d.get("id") or d.get("_id")) for d in await self._tutti() if _match(d, filtro)]
        if chiavi:
            async with self._db._pool.acquire() as con:
                await con.execute(
                    'DELETE FROM public."%s" WHERE id = ANY($1::text[])' % self._tab, chiavi
                )
        return _Risultato(len(chiavi), len(chiavi))

    async def distinct(self, campo: str, filtro=None, **_) -> List[Any]:
        visti_set = set()
        out: List[Any] = []
        for d in await self._tutti():
            if not _match(d, filtro):
                continue
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

    def __init__(self, pool: "asyncpg.Pool"):
        self._pool = pool
        self._tabelle_pronte: set = set()
        self._cache: Dict[str, SupabaseCollection] = {}

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
                "WHERE schemaname='public' AND tablename LIKE 'app\\_%'"
            )
        return [r["tablename"][4:] for r in righe]


async def crea_database(dsn: str) -> SupabaseDatabase:
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5, command_timeout=60)
    logger.info("Supabase/Postgres connesso")
    return SupabaseDatabase(pool)
