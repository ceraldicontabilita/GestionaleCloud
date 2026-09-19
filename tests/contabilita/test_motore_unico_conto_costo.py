"""Consolidamento motore conti (19/09/2026).

Prima di questo cambio esistevano 4 motori scollegati per scegliere il conto
costo di una riga fattura (audit di sola lettura, verificato via codice
reale): il motore "povero" `determina_conti_fattura` (8 regole hardcoded,
fallback quasi sempre 05.01.01), l'UI Excel `regole_categorizzazione.py` (le
correzioni scritte da li' non avevano alcun effetto sulla registrazione), il
motore "ricco" `categorizzazione_contabile.py` (usato solo dall'endpoint
manuale `/ricategorizza-fatture`) e la facciata morta
`classificazione_unificata.py`.

Questi test dimostrano che `determina_conti_fattura` e' ora l'UNICO motore:
regole utente (Excel) > motore ricco > fallback 05.01.01, e che il cambio non
tocca le fatture gia' registrate.
"""
import asyncio

import app.routers.accounting.piano_conti as pcmod
import app.services.registrazione_contabile as motore


# ── Fake DB async minimale (stesso pattern di test_p1_registrazione_contabile,
# esteso con `find().to_list()` per le collezioni delle regole utente e per i
# cespiti, che il vecchio test non doveva mai interrogare davvero perche'
# monkeypatchava `determina_conti_fattura`). ──────────────────────────────────

class _Cursor:
    def __init__(self, docs):
        self._docs = list(docs)

    async def to_list(self, n):
        return list(self._docs[:n])


def _match(doc, k, v):
    if isinstance(v, dict) and "$exists" in v:
        return (k in doc) == v["$exists"]
    if isinstance(v, dict) and "$ne" in v:
        return doc.get(k) != v["$ne"]
    return doc.get(k) == v


class _Coll:
    def __init__(self):
        self.docs = []

    def find(self, query=None, projection=None):
        query = query or {}
        return _Cursor([d for d in self.docs if all(_match(d, k, v) for k, v in query.items())])

    async def find_one(self, query, proj=None, sort=None):
        cand = [d for d in self.docs if all(_match(d, k, v) for k, v in (query or {}).items())]
        if sort:
            key, direction = sort[0]
            cand.sort(key=lambda d: d.get(key) or 0, reverse=(direction < 0))
        return dict(cand[0]) if cand else None

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def update_one(self, query, update, upsert=False):
        for d in self.docs:
            if all(_match(d, k, v) for k, v in query.items()):
                d.update(update.get("$set", {}))
                return
        if upsert:
            nd = dict(query)
            nd.update(update.get("$set", {}))
            self.docs.append(nd)


class _Db:
    def __init__(self):
        self.colls = {}

    def __getitem__(self, name):
        return self.colls.setdefault(name, _Coll())


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


def _fattura_energia(fornitore="FORNITORE SCONOSCIUTO SRL"):
    return {
        "supplier_name": fornitore,
        "linee": [{"descrizione": "Consumo energia elettrica gennaio", "prezzo_totale": 150.0}],
    }


# ── 1. Il motore ricco riconosce dalla DESCRIZIONE, non serve il nome fornitore ──

def test_motore_ricco_sceglie_conto_energia_non_generico():
    """Una fattura di un fornitore qualunque, con "Energia elettrica" in
    descrizione, prima finiva SEMPRE su 05.01.01 (le 4 regole hardcoded del
    vecchio motore riconoscevano solo il NOME fornitore ENEL/ENI/EDISON/...).
    Ora usa il motore ricco e finisce sul conto giusto."""
    db = _Db()
    conti = _run(pcmod.determina_conti_fattura(db, _fattura_energia()))
    assert conti["costo"]["codice"] == "05.02.05"
    assert conti["costo"]["codice"] != "05.01.01"


# ── 2. Una regola utente scritta dall'Excel per FORNITORE vince sul motore ricco ──

def test_regola_utente_fornitore_ha_precedenza_sul_motore_ricco():
    """Prima del consolidamento, `determina_conti_fattura` leggeva la
    collezione `regole_categorizzazione` (singolare, MAI scritta dalla pagina
    Excel): questa regola, scritta esattamente come la scrive
    `POST /api/regole/fornitore`, sarebbe stata invisibile al vecchio motore
    (avrebbe comunque vinto solo la regex ENEL/ENI/... hardcoded, o il
    fallback 05.01.01). Ora la regola utente vince anche sul motore ricco,
    che per questa stessa descrizione sceglierebbe "Energia elettrica"."""
    db = _Db()
    db["regole_categorizzazione_fornitori"].docs.append({
        "pattern": "generico", "categoria": "consulenze", "attivo": True,
    })
    fattura = _fattura_energia(fornitore="FORNITORE GENERICO SRL")

    conti = _run(pcmod.determina_conti_fattura(db, fattura))

    assert conti["costo"]["codice"] == "05.02.12"  # consulenze (regole_categorie/DEFAULT_CATEGORIE)


# ── 2b. Una regola utente per DESCRIZIONE si applica quando il motore ricco non trova nulla ──

def test_regola_utente_descrizione_applicata_se_motore_ricco_non_trova_nulla():
    db = _Db()
    db["regole_categorizzazione_descrizioni"].docs.append({
        "pattern": "xylophonia", "categoria": "consulenze", "attivo": True,
    })
    fattura = {
        "supplier_name": "SCONOSCIUTO SRL",
        "linee": [{"descrizione": "Xylophonia premium plus", "prezzo_totale": 80.0}],
    }

    conti = _run(pcmod.determina_conti_fattura(db, fattura))

    assert conti["costo"]["codice"] == "05.02.12"


# ── 3. Nessun match da nessuna parte → fallback invariato 05.01.01 ──────────

def test_fallback_generico_se_nessun_match():
    db = _Db()
    fattura = {
        "supplier_name": "SCONOSCIUTO SRL",
        "linee": [{"descrizione": "Xylophonia premium plus", "prezzo_totale": 50.0}],
    }
    conti = _run(pcmod.determina_conti_fattura(db, fattura))
    assert conti["costo"]["codice"] == "05.01.01"


def test_fallback_generico_senza_linee_fattura():
    db = _Db()
    fattura = {"supplier_name": "SCONOSCIUTO SRL"}
    conti = _run(pcmod.determina_conti_fattura(db, fattura))
    assert conti["costo"]["codice"] == "05.01.01"


# ── 4. Dare = Avere resta quadrato qualunque sia il conto costo scelto ──────

def test_registra_fattura_quadra_anche_con_conto_scelto_dal_motore_ricco():
    db = _Db()
    fattura = {
        "id": "ENERGY1", "total_amount": 122.0, "total_tax": 22.0,
        "iva_detraibile": 22.0, "invoice_date": "2026-05-01",
        "supplier_name": "FORNITORE ENERGIA SCONOSCIUTO SRL",
        "linee": [{"descrizione": "Consumo energia elettrica", "prezzo_totale": 100.0}],
    }

    r = _run(motore.registra_fattura(db, fattura))

    assert r["stato"] == "registrato"
    mov = r["movimento"]
    assert round(mov["totale_dare"], 2) == round(mov["totale_avere"], 2) == 122.0
    conti_usati = {riga["conto_codice"] for riga in mov["righe"]}
    assert "05.02.05" in conti_usati       # energia elettrica, non il fallback
    assert "05.01.01" not in conti_usati


# ── 5. Una fattura GIA' registrata prima del cambio non viene ri-registrata ──
#      né riclassificata col nuovo motore (idempotenza).

def test_fattura_gia_registrata_non_viene_riclassificata():
    db = _Db()
    # Scrittura pre-esistente col vecchio conto generico, come se fosse stata
    # registrata prima del consolidamento del motore.
    db["movimenti_contabili"].docs.append({
        "id": "OLD1", "tipo": "fattura_acquisto", "fattura_id": "OLD_INV",
        "righe": [{"conto_codice": "05.01.01", "conto_nome": "Acquisto merci",
                   "dare": 100.0, "avere": 0}],
        "numero_registrazione": 1, "anno": 2026,
    })
    fattura = {
        "id": "OLD_INV", "total_amount": 122.0, "total_tax": 22.0,
        "iva_detraibile": 22.0, "invoice_date": "2026-05-01",
        "supplier_name": "FORNITORE ENERGIA SCONOSCIUTO SRL",
        "linee": [{"descrizione": "Consumo energia elettrica", "prezzo_totale": 100.0}],
    }

    r = _run(motore.registra_fattura(db, fattura))

    assert r["stato"] == "gia_registrato"
    assert r["movimento_id"] == "OLD1"
    assert len(db["movimenti_contabili"].docs) == 1
    assert db["movimenti_contabili"].docs[0]["righe"][0]["conto_codice"] == "05.01.01"
