"""
run_locale_test.py — Avvia il backend in LOCALE su un Mongo FINTO (mongomock),
per collaudi visivi/funzionali senza toccare la produzione.

USO (dalla cartella backend/):
    AUTH_SECRET=test MONGO_URL=mongodb://localhost:27017 DB_NAME=Gestionale_Test \
        python run_locale_test.py

- Il database è SEMPRE mongomock (`Gestionale_Test`): nessuna connessione di
  rete viene mai aperta, il db di produzione `Gestionale` è irraggiungibile.
- Seeda dati di prova realistici (operatori, ricette, lotti, fatture,
  attrezzature) così il frontend buildato con
  REACT_APP_BACKEND_URL=http://127.0.0.1:8001 mostra pagine piene.
- PIN di prova: 9999 (Enzo, amministratore) e 1111 (Mario, operatore).

Stesso pattern della fixture `dbmock` di tests/test_e2e_flussi.py.
"""
import os

os.environ.setdefault("AUTH_SECRET", "test-secret-non-usare-in-prod")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ["DB_NAME"] = "Gestionale_Test"  # SOLO db di prova, sempre
os.environ.pop("ANTHROPIC_API_KEY", None)
# la build di collaudo gira su http://127.0.0.1:3001 (python -m http.server)
os.environ.setdefault("CORS_ORIGINS", "http://127.0.0.1:3001,http://localhost:3001")

import asyncio
import importlib
import pkgutil
import uuid
from datetime import datetime, timedelta, timezone

from mongomock_motor import AsyncMongoMockClient


def _patch_tutto():
    """Punta il `db` di TUTTI i moduli (server, routers.*, servizi.*, db.py)
    sul mongomock e spegne scheduler/bus eventi collaterali."""
    # Shim: mongomock non conosce l'espressione aggregate {$type: "$campo"}
    # (usata da GET /api/fatture per has_xml). Qui la emuliamo al minimo.
    import mongomock.aggregate as _magg
    _orig_parse = _magg._Parser.parse

    def _parse_con_type(self, expression):
        if isinstance(expression, dict) and len(expression) == 1 and "$type" in expression:
            try:
                val = _orig_parse(self, expression["$type"])
            except Exception:
                return "missing"
            if val is None:
                return "null"
            if isinstance(val, bool):
                return "bool"
            if isinstance(val, str):
                return "string"
            if isinstance(val, int):
                return "int"
            if isinstance(val, float):
                return "double"
            if isinstance(val, (list, tuple)):
                return "array"
            if isinstance(val, dict):
                return "object"
            return type(val).__name__
        return _orig_parse(self, expression)

    _magg._Parser.parse = _parse_con_type

    cli = AsyncMongoMockClient()
    db = cli["Gestionale_Test"]

    import app.lotti.server as server  # importa e monta tutti i router
    server.db = db

    import app.lotti.db as dbmod
    dbmod.database = db

    import app.lotti.routers as routers
    for m in pkgutil.iter_modules(routers.__path__):
        try:
            mod = importlib.import_module(f"app.lotti.routers.{m.name}")
        except Exception:
            continue
        if hasattr(mod, "db"):
            mod.db = db
    try:
        import app.lotti.servizi as servizi
        for m in pkgutil.iter_modules(servizi.__path__):
            try:
                mod = importlib.import_module(f"app.lotti.servizi.{m.name}")
            except Exception:
                continue
            if hasattr(mod, "db"):
                mod.db = db
    except Exception:
        pass

    # niente scheduler (keep-warm/ping di rete inutili in locale)
    import app.lotti.routers.scheduler as sched
    sched.setup_scheduler = lambda: None
    # niente seed massivo di ricette solo-nome / download foto dal web
    import app.lotti.routers.ricette as ric
    async def _no_seed():
        return None

    ric.seed_ricette_solo_nome = _no_seed

    return server, db


def _gg(giorni: int) -> str:
    """Data italiana dd/mm/yyyy a N giorni da oggi."""
    return (datetime.now() + timedelta(days=giorni)).strftime("%d/%m/%Y")


def _iso(giorni: int) -> str:
    return (datetime.now() + timedelta(days=giorni)).strftime("%Y-%m-%d")


# PIN del BANCO DI PROVA (database finto, mai la produzione): servono a chi
# esegue i collaudi automatici e non danno accesso a nulla di reale.
PIN_ADMIN_BANCO = "9999"
PIN_OPERATORE_BANCO = "1111"


async def _seed(db):
    now = datetime.now(timezone.utc).isoformat()

    # ── Operatori del banco. 25/07/2026: nemmeno qui si scrive un PIN in
    # chiaro — si salva l'hash bcrypt e l'impronta di ricerca, esattamente
    # come in produzione, così il banco collauda il percorso VERO.
    from app.lotti.routers.tablet_operatori import _hash_pin, _pin_lookup
    await db.tablet_operatori.insert_many([
        {"id": "op-enzo", "nome": "Enzo", "ruolo": "amministratore", "attivo": True,
         "pin": _hash_pin(PIN_ADMIN_BANCO), "pin_lookup": _pin_lookup(PIN_ADMIN_BANCO)},
        {"id": "op-mario", "nome": "Mario", "ruolo": "operatore", "attivo": True,
         "pin": _hash_pin(PIN_OPERATORE_BANCO), "pin_lookup": _pin_lookup(PIN_OPERATORE_BANCO)},
    ])

    # ── Ricette (ingredienti_dettaglio con unita_misura, foto_url null) ────
    def ricetta(nome, ing, porzioni=12, prezzo=None):
        return {
            "id": "ric-" + nome.lower().replace(" ", "-"),
            "nome": nome, "reparto": "pasticceria", "porzioni": porzioni,
            "ingredienti": [i[0] for i in ing],
            "ingredienti_dettaglio": [
                {"nome": n, "quantita": q, "unita_misura": u} for (n, q, u) in ing
            ],
            "allergeni": ["glutine", "latte", "uova"],
            "allergeni_auto": ["glutine", "latte", "uova"],
            "foto_url": None, "approvata": True, "stagionale": False,
            "prezzo_vendita": prezzo, "note": "",
            "created_at": now, "updated_at": now,
        }

    await db.ricette.insert_many([
        ricetta("Sfogliatella riccia", [("Farina 00", 500, "g"), ("Ricotta", 400, "g"), ("Semola", 250, "g"), ("Zucchero", 200, "g"), ("Strutto", 150, "g")], 12, 2.5),
        ricetta("Baba al rum", [("Farina manitoba", 500, "g"), ("Uova", 6, "pz"), ("Burro", 150, "g"), ("Zucchero", 90, "g"), ("Rum", 200, "ml")], 15, 2.0),
        ricetta("Pastiera napoletana", [("Grano cotto", 580, "g"), ("Ricotta", 500, "g"), ("Zucchero", 400, "g"), ("Uova", 5, "pz"), ("Acqua di fiori d'arancio", 30, "ml")], 8, 22.0),
        ricetta("Torta caprese", [("Cioccolato fondente", 250, "g"), ("Mandorle", 250, "g"), ("Burro", 200, "g"), ("Uova", 5, "pz"), ("Zucchero", 200, "g")], 10, 18.0),
    ])

    # ── Lotti di produzione (uno bloccato da richiamo, uno scaduto) ────────
    richiamo_id = "richiamo-test-1"
    await db.lotti.insert_many([
        {"id": "lp-1", "numero_lotto": "SFO-240726-01", "prodotto": "Sfogliatella riccia",
         "fornitore": "Produzione interna", "quantita": 24, "unita_misura": "pz",
         "data_produzione": _gg(-1), "data_scadenza": _gg(2), "frigo_numero": "Frigo 1",
         "stato": "attivo", "consumato": False,
         # NB: nei LOTTI ingredienti_dettaglio è una lista di STRINGHE
         # (righe etichetta), diversamente dalle ricette (vedi routers/lotti.py)
         "ingredienti_dettaglio": [
             "Farina 00", "Ricotta (contiene: latte)", "Zucchero", "Strutto",
         ],
         "allergeni": ["glutine", "latte"], "costo_pezzo": 0.85, "created_at": now},
        {"id": "lp-2", "numero_lotto": "BAB-240725-01", "prodotto": "Baba al rum",
         "fornitore": "Produzione interna", "quantita": 15, "unita_misura": "pz",
         "data_produzione": _gg(-2), "data_scadenza": _gg(5), "frigo_numero": "Frigo 2",
         "stato": "attivo", "consumato": False, "ingredienti_dettaglio": [],
         "allergeni": ["glutine", "uova"], "costo_pezzo": 0.7, "created_at": now},
        {"id": "lp-3", "numero_lotto": "PAS-240720-01", "prodotto": "Pastiera napoletana",
         "fornitore": "Produzione interna", "quantita": 3, "unita_misura": "pz",
         "data_produzione": _gg(-6), "data_scadenza": _gg(-1), "frigo_numero": "Frigo 1",
         "stato": "attivo", "consumato": False, "ingredienti_dettaglio": [],
         "allergeni": ["glutine", "latte", "uova"], "costo_pezzo": 6.5, "created_at": now},
        {"id": "lp-4", "numero_lotto": "CAP-240723-01", "prodotto": "Torta caprese",
         "fornitore": "Produzione interna", "quantita": 6, "unita_misura": "pz",
         "data_produzione": _gg(-3), "data_scadenza": _gg(1), "frigo_numero": "Congelatore 1",
         "stato": "bloccato_richiamo", "richiamo_ref": richiamo_id, "consumato": False,
         "ingredienti_dettaglio": [], "allergeni": ["uova", "frutta a guscio"],
         "costo_pezzo": 5.2, "created_at": now},
        {"id": "lp-5", "numero_lotto": "SFO-240724-02", "prodotto": "Sfogliatella riccia",
         "fornitore": "Produzione interna", "quantita": 8, "unita_misura": "pz",
         "data_produzione": _gg(-4), "data_scadenza": _gg(0), "frigo_numero": "Frigo 3",
         "stato": "attivo", "consumato": False, "ingredienti_dettaglio": [],
         "allergeni": ["glutine", "latte"], "costo_pezzo": 0.85, "created_at": now},
    ])
    await db.richiami_eseguiti.insert_one({
        "id": richiamo_id, "ingrediente": "mandorle", "filtri": {},
        "lotti_coinvolti": [{"id": "lp-4", "numero_lotto": "CAP-240723-01",
                             "prodotto": "Torta caprese", "quantita": 6, "frigo_numero": "Congelatore 1"}],
        "n_lotti": 1, "motivo": "allerta fornitore mandorle (aflatossine)",
        "operatore_id": "op-enzo", "operatore_nome": "Enzo",
        "stato": "aperto", "azione_correttiva": None,
        "data_ora_apertura": now, "data_ora_chiusura": None,
    })
    await db.blocchi_lotti.insert_one({
        "id": str(uuid.uuid4()), "lotto_id": "lp-4", "azione": "blocco",
        "motivazione": "allerta fornitore mandorle (aflatossine)",
        "richiamo_ref": richiamo_id, "operatore_nome": "Enzo", "data_ora": now,
    })

    # ── Lotti fornitori (uno a CARTONE per il caso conversione mancante) ───
    def lf(i, prodotto, fornitore, qta, um, gg_fatt, gg_scad, prezzo, fattura):
        return {"id": f"lf-{i}", "fornitore": fornitore,
                "prodotto_nome": prodotto, "prodotto_nome_norm": prodotto.lower(),
                "lotto_id_fornitore": f"L{i}-2026", "tipo_tracciabilita": "lotto_fornitore",
                "data_scadenza": _gg(gg_scad), "scaduto": gg_scad < 0,
                "quantita_originale": qta, "quantita_acquistata": qta,
                "quantita_disponibile": qta * 0.7, "unita_misura": um,
                "prezzo_unitario": prezzo, "fattura_ref": fattura,
                "data_fattura": _gg(gg_fatt), "esaurito": False, "created_at": now}

    await db.lotti_fornitori.insert_many([
        lf(1, "Farina 00", "Molino Caputo", 100, "KG", -10, 90, 0.8, "451/A"),
        lf(2, "Ricotta di pecora", "Caseificio Vannulo", 20, "KG", -3, 4, 6.5, "452/A"),
        lf(3, "Burro bavarese", "Granarolo", 25, "KG", -7, 30, 9.2, "451/A"),
        lf(4, "Acqua Ferrarelle 1L", "Bevande Sud", 5, "CT", -2, 300, 4.8, "453/A"),
        lf(5, "Cioccolato fondente 70%", "Icam", 15, "KG", -15, 180, 11.0, "451/A"),
    ])

    # ── Fatture ────────────────────────────────────────────────────────────
    await db.fatture.insert_many([
        {"id": "fat-1", "fornitore": "Molino Caputo", "numero_fattura": "451/A",
         "data_fattura": _iso(-10), "piva": "01234567890", "importo_totale": 512.30,
         "prodotti": [
             {"descrizione": "FARINA 00 SACCO KG 25", "codice": "F0025", "quantita": 4,
              "unita": "KG", "prezzo_unitario": 20.0, "iva": 4, "totale": 80.0,
              "lotto": "L1-2026", "scadenza": _iso(90)},
             {"descrizione": "BURRO BAVARESE PANETTO 1KG", "codice": "BB01", "quantita": 25,
              "unita": "KG", "prezzo_unitario": 9.2, "iva": 4, "totale": 230.0,
              "lotto": "L3-2026", "scadenza": _iso(30)},
             {"descrizione": "CIOCCOLATO FONDENTE 70% KG", "codice": "CF70", "quantita": 15,
              "unita": "KG", "prezzo_unitario": 11.0, "iva": 10, "totale": 165.0,
              "lotto": "L5-2026", "scadenza": _iso(180)},
         ], "created_at": now},
        {"id": "fat-2", "fornitore": "Bevande Sud", "numero_fattura": "453/A",
         "data_fattura": _iso(-2), "piva": "09876543210", "importo_totale": 158.40,
         "prodotti": [
             {"descrizione": "ACQUA FERRARELLE 1L CT X12", "codice": "AF12", "quantita": 5,
              "unita": "CT", "prezzo_unitario": 4.8, "iva": 22, "totale": 24.0,
              "lotto": "L4-2026", "scadenza": _iso(300)},
         ], "created_at": now},
    ])

    # ── Fornitori (chiave = nome) ──────────────────────────────────────────
    await db.fornitori.insert_many([
        {"nome": "Molino Caputo", "stato": "attivo", "escluso": False, "in_attesa": False,
         "piva": "01234567890", "num_fatture": 12, "ultima_fattura": _iso(-10), "updated_at": now},
        {"nome": "Caseificio Vannulo", "stato": "attivo", "escluso": False, "in_attesa": False,
         "piva": "05555555555", "num_fatture": 4, "ultima_fattura": _iso(-3), "updated_at": now},
        {"nome": "Bevande Sud", "stato": "attivo", "escluso": False, "in_attesa": False,
         "piva": "09876543210", "num_fatture": 7, "ultima_fattura": _iso(-2), "updated_at": now},
    ])

    # ── Attrezzature (frigo/congelatori) ───────────────────────────────────
    await db.attrezzature_config.insert_many([
        {"tipo": "frigo", "numero": 1, "nome": "Frigo 1 — Banco pasticceria", "attivo": True},
        {"tipo": "frigo", "numero": 2, "nome": "Frigo 2 — Laboratorio", "attivo": True},
        {"tipo": "frigo", "numero": 3, "nome": "Frigo 3 — Rosticceria", "attivo": True},
        {"tipo": "congelatore", "numero": 1, "nome": "Congelatore 1", "attivo": True},
        {"tipo": "congelatore", "numero": 2, "nome": "Abbattitore", "attivo": True},
    ])

    # ── Dizionario prodotti ────────────────────────────────────────────────
    await db.dizionario_prodotti.insert_many([
        {"id": "dz-1", "nome_normalizzato": "farina 00", "nome_originale": "FARINA 00 SACCO KG 25",
         "fornitore": "Molino Caputo", "data_fattura": _iso(-10), "peso_confezione": 25,
         "unita_confezione": "KG", "prezzo_confezione": 20.0, "prezzo_kg": 0.8,
         "quantita_disponibile_kg": 70, "quantita_totale_kg": 100, "quantita_usata_kg": 30,
         "aliases": ["farina 00 sacco kg 25"], "ultimo_aggiornamento": now},
        {"id": "dz-2", "nome_normalizzato": "ricotta di pecora", "nome_originale": "RICOTTA PECORA SECCHIELLO 2KG",
         "fornitore": "Caseificio Vannulo", "data_fattura": _iso(-3), "peso_confezione": 2,
         "unita_confezione": "KG", "prezzo_confezione": 13.0, "prezzo_kg": 6.5,
         "quantita_disponibile_kg": 14, "quantita_totale_kg": 20, "quantita_usata_kg": 6,
         "aliases": ["ricotta pecora secchiello 2kg"], "ultimo_aggiornamento": now},
        {"id": "dz-3", "nome_normalizzato": "cioccolato fondente 70%", "nome_originale": "CIOCCOLATO FONDENTE 70% KG",
         "fornitore": "Icam", "data_fattura": _iso(-15), "peso_confezione": 1,
         "unita_confezione": "KG", "prezzo_confezione": 11.0, "prezzo_kg": 11.0,
         "quantita_disponibile_kg": 10.5, "quantita_totale_kg": 15, "quantita_usata_kg": 4.5,
         "aliases": ["cioccolato fondente 70% kg"], "ultimo_aggiornamento": now},
    ])

    # ── Registri HACCP con un BUCO voluto ──────────────────────────────────
    # Servono per collaudare la tranche 1: letture 6 giorni fa e 1 giorno fa,
    # in mezzo quattro giorni senza niente (come se il server fosse rimasto
    # giù). Il recupero deve dichiararli "non rilevato", non riempirli.
    oggi_d = datetime.now(timezone.utc).date()

    def _cella(temp, tmin, tmax):
        return {"temp": temp, "operatore": "Pocci Salvatore", "note": "",
                "timestamp": now, "auto": True, "allarme": False,
                "soglie": {"min": tmin, "max": tmax}}

    def _temperature(valori, tmin, tmax):
        out = {}
        for giorni_fa, temp in valori:
            d = oggi_d - timedelta(days=giorni_fa)
            out.setdefault(str(d.month), {})[str(d.day)] = _cella(temp, tmin, tmax)
        return out

    await db.temperature_positive.insert_many([
        {"id": f"tp-{n}", "anno": oggi_d.year, "frigorifero_numero": n,
         "frigorifero_nome": nome, "temp_min": 0.0, "temp_max": 4.0,
         "temperature": _temperature([(6, 2.4), (1, 3.1)], 0.0, 4.0)}
        for n, nome in ((1, "Frigo 1 — Banco pasticceria"),
                        (2, "Frigo 2 — Laboratorio"),
                        (3, "Frigo 3 — Rosticceria"))
    ])
    await db.temperature_negative.insert_many([
        {"id": f"tn-{n}", "anno": oggi_d.year, "congelatore_numero": n,
         "congelatore_nome": nome, "temp_min": -22.0, "temp_max": -18.0,
         "temperature": _temperature([(6, -19.8), (1, -20.2)], -22.0, -18.0)}
        for n, nome in ((1, "Congelatore 1"), (2, "Abbattitore"))
    ])
    _g6 = str((oggi_d - timedelta(days=6)).day)
    _g1 = str((oggi_d - timedelta(days=1)).day)
    await db.sanificazione_schede.insert_one({
        "id": "san-1", "anno": oggi_d.year, "mese": oggi_d.month,
        "operatore_responsabile": "Capezzuto Maria",
        "registrazioni": {
            "Pavimentazione": {_g6: "X", _g1: "X"},
            "Tagliere, Coltelli": {_g6: "X", _g1: "X"},
            "Attrezzature Laboratorio": {_g6: "X", _g1: "X"},
        },
    })

    print("[SEED] dati di prova inseriti in Gestionale_Test (mongomock)")


def main():
    server, db = _patch_tutto()
    asyncio.run(_seed(db))

    import uvicorn
    uvicorn.run(server.app, host="127.0.0.1", port=8001, log_level="warning")


if __name__ == "__main__":
    main()
