"""
test_registri_buchi.py — TRANCHE 1 del piano esecutivo (25/07/2026):
i buchi nei registri diventano un dato dichiarato, non una cella muta.

Tutto su MONGO DI PROVA (mongomock-motor, DB "Gestionale_Test"): nessuna
connessione di rete, MAI il database di produzione `Gestionale`.

Copre:
  1. Giorni passati senza rilevazione marcati a database come "non rilevato"
     col motivo (temperature positive e negative), SENZA inventare temperature
     e SENZA riscrivere niente di esistente.
  2. Prudenza: oggi non si marca (giornata aperta), non si marca prima della
     prima rilevazione mai fatta, il secondo giro è idempotente.
  3. Sanificazione: il giorno passato senza registrazioni diventa "N/D", e
     "N/D" NON viene contato come sanificazione eseguita nel report.
  4. Stampa: il giorno marcato compare come "N/D" col motivo nel tooltip.
"""
import os
os.environ.setdefault("AUTH_SECRET", "test-secret-non-usare-in-prod")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "Gestionale_Test")  # SOLO db di prova

import asyncio
import importlib
import pkgutil
from datetime import datetime, timedelta, timezone

import pytest
from mongomock_motor import AsyncMongoMockClient


def run(coro):
    """Nella suite intera qualche test eseguito prima CHIUDE il ciclo asincrono:
    `get_event_loop()` alzava "There is no current event loop" e questi test
    fallivano solo in esecuzione completa (da soli passavano). Se il ciclo non
    c'è più, se ne apre uno nuovo."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("ciclo chiuso")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


@pytest.fixture()
def dbmock(monkeypatch):
    import app.lotti.routers as routers  # noqa
    cli = AsyncMongoMockClient()
    db = cli["Gestionale_Test"]
    for m in pkgutil.iter_modules(routers.__path__):
        try:
            mod = importlib.import_module(f"app.lotti.routers.{m.name}")
        except Exception:
            continue
        if hasattr(mod, "db"):
            monkeypatch.setattr(mod, "db", db, raising=False)
    import app.lotti.db as dbmod
    monkeypatch.setattr(dbmod, "database", db, raising=False)
    import app.lotti.azienda as azienda
    monkeypatch.setattr(azienda, "db", db, raising=False)
    return db


OGGI = datetime.now(timezone.utc).date()
ANNO = OGGI.year


def _giorno(delta_giorni: int):
    """Data di N giorni fa, con mese/giorno come stringhe (schema reale)."""
    d = OGGI - timedelta(days=delta_giorni)
    return d, str(d.month), str(d.day)


def _lettura(temp: float):
    return {"temp": temp, "operatore": "Mario", "note": "", "auto": True,
            "soglie": {"min": 0.0, "max": 4.0}}


def _scheda_con_buco(numero: int = 1):
    """Scheda con lettura 6 giorni fa e 1 giorno fa; in mezzo, buchi.
    Se le date cadono in due anni diversi (fine dicembre) il test resta
    valido: si marcano solo i giorni dell'anno della scheda."""
    d6, m6, g6 = _giorno(6)
    d1, m1, g1 = _giorno(1)
    temperature = {}
    temperature.setdefault(m6, {})[g6] = _lettura(2.5)
    temperature.setdefault(m1, {})[g1] = _lettura(3.0)
    return {
        "anno": ANNO, "frigorifero_numero": numero,
        "frigorifero_nome": f"Frigo {numero}",
        "temp_min": 0.0, "temp_max": 4.0,
        "temperature": temperature,
    }


# ── 1. I giorni scoperti vengono dichiarati ────────────────────────────────
def test_giorni_scoperti_marcati_con_motivo(dbmock):
    from app.lotti.routers.haccp_auto import marca_giorni_non_rilevati, MOTIVO_NON_RILEVATO

    run(dbmock.temperature_positive.insert_one(_scheda_con_buco()))
    esito = run(marca_giorni_non_rilevati(giorni_indietro=45))

    # tra 6 giorni fa e 1 giorno fa ci sono 4 giorni scoperti (5,4,3,2)
    assert esito["temperature_positive"] == 4, esito

    doc = run(dbmock.temperature_positive.find_one({"frigorifero_numero": 1}))
    _, m4, g4 = _giorno(4)
    marcato = doc["temperature"][m4][g4]
    assert marcato["non_rilevato"] is True
    assert marcato["motivo"] == MOTIVO_NON_RILEVATO
    # NESSUNA temperatura inventata
    assert marcato["temp"] is None


def test_letture_esistenti_mai_riscritte(dbmock):
    from app.lotti.routers.haccp_auto import marca_giorni_non_rilevati

    run(dbmock.temperature_positive.insert_one(_scheda_con_buco()))
    run(marca_giorni_non_rilevati(giorni_indietro=45))

    doc = run(dbmock.temperature_positive.find_one({"frigorifero_numero": 1}))
    _, m6, g6 = _giorno(6)
    assert doc["temperature"][m6][g6]["temp"] == 2.5
    assert not doc["temperature"][m6][g6].get("non_rilevato")


def test_oggi_non_viene_marcato(dbmock):
    """La giornata di oggi è ancora aperta: nessuno l'ha 'saltata'."""
    from app.lotti.routers.haccp_auto import marca_giorni_non_rilevati

    run(dbmock.temperature_positive.insert_one(_scheda_con_buco()))
    run(marca_giorni_non_rilevati(giorni_indietro=45))

    doc = run(dbmock.temperature_positive.find_one({"frigorifero_numero": 1}))
    _, m_oggi, g_oggi = _giorno(0)
    assert doc["temperature"].get(m_oggi, {}).get(g_oggi) is None


def test_scheda_mai_usata_non_viene_riempita(dbmock):
    """Un apparecchio senza NESSUNA rilevazione non ha buchi da dichiarare:
    non è stato saltato, semplicemente non è mai stato in uso."""
    from app.lotti.routers.haccp_auto import marca_giorni_non_rilevati

    run(dbmock.temperature_negative.insert_one({
        "anno": ANNO, "congelatore_numero": 9, "congelatore_nome": "Nuovo",
        "temp_min": -22.0, "temp_max": -18.0, "temperature": {},
    }))
    esito = run(marca_giorni_non_rilevati(giorni_indietro=45))
    assert esito["temperature_negative"] == 0

    doc = run(dbmock.temperature_negative.find_one({"congelatore_numero": 9}))
    assert doc["temperature"] == {}


def test_secondo_giro_non_aggiunge_nulla(dbmock):
    """Idempotenza: rilanciare il recupero non moltiplica i marcatori."""
    from app.lotti.routers.haccp_auto import marca_giorni_non_rilevati

    run(dbmock.temperature_positive.insert_one(_scheda_con_buco()))
    primo = run(marca_giorni_non_rilevati(giorni_indietro=45))
    secondo = run(marca_giorni_non_rilevati(giorni_indietro=45))
    assert primo["temperature_positive"] == 4
    assert secondo["temperature_positive"] == 0


def test_congelatori_coperti_come_i_frigoriferi(dbmock):
    from app.lotti.routers.haccp_auto import marca_giorni_non_rilevati

    d6, m6, g6 = _giorno(6)
    d1, m1, g1 = _giorno(1)
    temperature = {}
    temperature.setdefault(m6, {})[g6] = {"temp": -20.0, "soglie": {"min": -22.0, "max": -18.0}}
    temperature.setdefault(m1, {})[g1] = {"temp": -19.5, "soglie": {"min": -22.0, "max": -18.0}}
    run(dbmock.temperature_negative.insert_one({
        "anno": ANNO, "congelatore_numero": 2, "congelatore_nome": "Pozzetto",
        "temp_min": -22.0, "temp_max": -18.0, "temperature": temperature,
    }))
    esito = run(marca_giorni_non_rilevati(giorni_indietro=45))
    assert esito["temperature_negative"] == 4


# ── 2. Sanificazione: "non fatto" ≠ "non registrato" ───────────────────────
def _scheda_sanificazione():
    d6, _, g6 = _giorno(6)
    d1, _, g1 = _giorno(1)
    if d6.month != d1.month:
        pytest.skip("mese a cavallo: la scheda sanificazione è mensile")
    return {
        "anno": ANNO, "mese": d1.month,
        "registrazioni": {
            "Pavimentazione": {g6: "X", g1: "X"},
            "Tagliere, Coltelli": {g6: "X", g1: "X"},
        },
    }, g6, g1


def test_sanificazione_giorno_scoperto_diventa_nd(dbmock):
    from app.lotti.routers.haccp_auto import marca_giorni_non_rilevati

    scheda, g6, g1 = _scheda_sanificazione()
    run(dbmock.sanificazione_schede.insert_one(scheda))
    run(marca_giorni_non_rilevati(giorni_indietro=45))

    doc = run(dbmock.sanificazione_schede.find_one({"anno": ANNO}))
    _, _, g4 = _giorno(4)
    assert doc["registrazioni"]["Pavimentazione"][g4] == "N/D"
    # i giorni davvero registrati restano "X"
    assert doc["registrazioni"]["Pavimentazione"][g6] == "X"
    assert doc["registrazioni"]["Pavimentazione"][g1] == "X"


def test_nd_non_conta_come_sanificazione_eseguita(dbmock):
    """Il report contava QUALUNQUE valore non vuoto come 'fatto': con "N/D"
    a database avrebbe dichiarato conformi giorni in cui non è stato fatto
    niente."""
    from app.lotti.routers.report_haccp import load_sanificazioni

    d1, _, g1 = _giorno(1)
    _, _, g4 = _giorno(4)
    run(dbmock.sanificazione_schede.insert_one({
        "anno": ANNO, "mese": d1.month,
        "registrazioni": {"Pavimentazione": {g1: "X", g4: "N/D"}},
    }))
    rows = run(load_sanificazioni(ANNO, d1.month))
    giorni = {r["giorno"] for r in rows}
    assert g1 in giorni
    assert g4 not in giorni, "«N/D» non è una sanificazione eseguita"


# ── 3. La stampa dichiara il motivo ────────────────────────────────────────
def test_stampa_mostra_nd_col_motivo(dbmock):
    from app.lotti.routers.haccp_auto import marca_giorni_non_rilevati, MOTIVO_NON_RILEVATO
    from app.lotti.routers.report_haccp import load_temperature, table_temperature

    run(dbmock.temperature_positive.insert_one(_scheda_con_buco()))
    run(marca_giorni_non_rilevati(giorni_indietro=45))

    d4, _, _ = _giorno(4)
    apps, _flat = run(load_temperature(dbmock.temperature_positive, ANNO, d4.month, "positive"))
    html = table_temperature(apps, ANNO, d4.month, 0.0, 4.0)
    assert "N/D" in html
    assert MOTIVO_NON_RILEVATO in html, "il motivo del buco deve essere scritto in stampa"


def test_stampa_non_dichiara_conforme_un_giorno_non_rilevato(dbmock):
    """Il marcatore non deve gonfiare la percentuale di conformità."""
    from app.lotti.routers.haccp_auto import marca_giorni_non_rilevati
    from app.lotti.routers.report_haccp import load_temperature

    run(dbmock.temperature_positive.insert_one(_scheda_con_buco()))
    run(marca_giorni_non_rilevati(giorni_indietro=45))

    d1, _, _ = _giorno(1)
    _apps, flat = run(load_temperature(dbmock.temperature_positive, ANNO, d1.month, "positive"))
    # solo le letture VERE del mese finiscono nel conteggio
    assert all(r["valore"] is not None for r in flat)
    assert len(flat) <= 2


# ── 4. Registro tracciabilità: dichiara quante righe mostra ────────────────
def test_registro_tracciabilita_dichiara_il_troncamento(dbmock):
    from app.lotti.routers.utils import get_registro_tracciabilita

    # `ingredienti` sono nomi (stringhe); il dizionario è la forma che
    # arriva da certe proposte automatiche e prima mandava in errore 500
    # l'intero registro richiesto dall'ASL.
    run(dbmock.ricette.insert_one({
        "nome": "Sfogliatella", "ingredienti": ["Farina 00", "Zucchero semolato"],
    }))
    run(dbmock.ricette.insert_one({
        "nome": "Babà", "ingredienti": [{"nome": "Farina 00", "quantita": 1}],
    }))
    fatture = []
    for i in range(60):
        fatture.append({
            "fornitore": f"Fornitore {i}", "numero_fattura": f"F{i:04d}",
            "data_fattura": "01/07/2026",
            "prodotti": [
                {"descrizione": f"Farina 00 sacco {j}", "quantita": 1} for j in range(10)
            ],
        })
    run(dbmock.fatture.insert_many(fatture))

    resp = run(get_registro_tracciabilita())
    html = resp.body.decode("utf-8")
    assert "Mostrate le prime 500 righe di" in html
    assert "scarica il CSV" in html
