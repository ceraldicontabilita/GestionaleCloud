"""Migrazione (19/09/2026) di app/hr/routers/tfr.py al motore unico
`app/services/registrazione_contabile.registra_scrittura_semplice`.

Prima, le 4 scritture TFR (accantonamento, liquidazione-fondo,
liquidazione-ritenute, acconto) erano `insert_one` diretti su
`movimenti_contabili`: record piatti senza `righe` dare/avere,
`numero_registrazione` o `idempotency`, in violazione della regola
"Motore unico Prima Nota... non aggiungere altri punti di scrittura"
(CLAUDE.md, sezione "Regole contabili vincolanti").

Verifica per ognuna delle 4 scritture:
(a) dare == avere;
(b) la stessa chiave naturale (stesso accantonamento/liquidazione/acconto)
    non crea una seconda scrittura se richiamata due volte;
(c) `numero_registrazione` valorizzato e progressivo;
(d) i campi originali (tipo, dipendente_id, importo, dettaglio) restano
    leggibili come prima, per non rompere i lettori esistenti
    (es. app/routers/tfr.py ERP-level, riepilogo-aziendale).
"""
import asyncio

import pytest

from app.hr.routers import tfr as mod


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


class _FakeCollection:
    def __init__(self, docs=None):
        self.docs = docs or []

    def _match(self, d, query):
        for k, v in (query or {}).items():
            if isinstance(v, dict) and "$exists" in v:
                if v["$exists"] and k not in d:
                    return False
                if not v["$exists"] and k in d:
                    return False
                continue
            if d.get(k) != v:
                return False
        return True

    async def find_one(self, query=None, projection=None, sort=None):
        candidati = [d for d in self.docs if self._match(d, query or {})]
        if sort:
            campo, direzione = sort[0]
            candidati = sorted(
                [d for d in candidati if campo in d],
                key=lambda d: d[campo], reverse=(direzione == -1),
            )
        return dict(candidati[0]) if candidati else None

    def find(self, query=None, projection=None):
        candidati = [dict(d) for d in self.docs if self._match(d, query or {})]
        return _FakeCursor(candidati)

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def update_one(self, query, update, upsert=False):
        for d in self.docs:
            if self._match(d, query):
                if "$set" in update:
                    d.update(update["$set"])
                return
        if upsert:
            nuovo = dict(query)
            nuovo.update(update.get("$set", {}))
            self.docs.append(nuovo)


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *a, **k):
        return self

    async def to_list(self, n=None):
        return list(self._docs[:n] if n else self._docs)


class _FakeDb(dict):
    def __missing__(self, k):
        self[k] = _FakeCollection()
        return self[k]


DIPENDENTE = {
    "id": "dip-1",
    "nome_completo": "Mario Rossi",
    "tfr_accantonato": 5000.0,
}


def _db_con_dipendente(**overrides):
    db = _FakeDb()
    dip = dict(DIPENDENTE, **overrides)
    db["dipendenti"].docs.append(dip)
    return db


def _righe_per_tipo(db, tipo):
    return [m for m in db["movimenti_contabili"].docs if m.get("tipo") == tipo]


def _assert_bilanciata(movimento):
    dare = sum(r.get("dare", 0) for r in movimento["righe"])
    avere = sum(r.get("avere", 0) for r in movimento["righe"])
    assert dare == pytest.approx(avere)
    assert movimento["totale_dare"] == pytest.approx(movimento["totale_avere"])


# ---------------------------------------------------------------------------
# 1. Accantonamento
# ---------------------------------------------------------------------------

def test_accantonamento_scrittura_bilanciata_e_idempotente(monkeypatch):
    db = _db_con_dipendente(tfr_accantonato=0.0)
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))

    input_data = mod.AccantonamentoTFRInput(
        dipendente_id="dip-1", anno=2026, retribuzione_annua=27000.0, indice_istat=1.0,
    )

    _run(mod.registra_accantonamento_tfr(input_data))
    movimenti = _righe_per_tipo(db, "tfr_accantonamento")
    assert len(movimenti) == 1
    mov = movimenti[0]
    _assert_bilanciata(mov)
    assert mov["numero_registrazione"] == 1
    # campi originali leggibili come prima (lettori esistenti)
    assert mov["dipendente_id"] == "dip-1"
    assert mov["anno"] == 2026
    assert mov["importo"] == pytest.approx(27000.0 / 13.5)
    assert "quota_annuale" in mov["dettaglio"]
    conti = {r["conto_codice"] for r in mov["righe"]}
    assert conti == {"67.01.07.01", "29.01.01"}

    # richiamare lo stesso accantonamento (stesso dipendente+anno) non deve
    # creare una seconda scrittura: da audit 19/09/2026 l'endpoint stesso
    # rifiuta la ripetizione prima di scrivere in tfr_accantonamenti, quindi
    # il motore contabile non viene nemmeno richiamato una seconda volta.
    esito2 = _run(mod.registra_accantonamento_tfr(input_data))
    assert esito2["gia_registrato"] is True
    movimenti_dopo = _righe_per_tipo(db, "tfr_accantonamento")
    assert len(movimenti_dopo) == 1


def test_accantonamento_numero_registrazione_progressivo(monkeypatch):
    db = _db_con_dipendente(tfr_accantonato=0.0)
    db["dipendenti"].docs.append({"id": "dip-2", "nome_completo": "Anna Bianchi", "tfr_accantonato": 0.0})
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))

    _run(mod.registra_accantonamento_tfr(mod.AccantonamentoTFRInput(
        dipendente_id="dip-1", anno=2026, retribuzione_annua=20000.0)))
    _run(mod.registra_accantonamento_tfr(mod.AccantonamentoTFRInput(
        dipendente_id="dip-2", anno=2026, retribuzione_annua=18000.0)))

    movimenti = sorted(_righe_per_tipo(db, "tfr_accantonamento"),
                        key=lambda m: m["numero_registrazione"])
    assert [m["numero_registrazione"] for m in movimenti] == [1, 2]


def test_accantonamento_ripetuto_con_dati_diversi_non_diverge(monkeypatch):
    """Audit 19/09/2026 (finding 2): prima, un secondo POST /accantonamento
    per lo stesso dipendente+anno ma con una retribuzione_annua diversa
    inseriva un secondo record in tfr_accantonamenti e sommava una seconda
    volta su dipendenti.tfr_accantonato, mentre l'idempotenza del motore
    bloccava solo movimenti_contabili: tre fonti divergenti. Ora il secondo
    POST si ferma prima di toccare qualsiasi cosa."""
    db = _db_con_dipendente(tfr_accantonato=0.0)
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))

    esito1 = _run(mod.registra_accantonamento_tfr(mod.AccantonamentoTFRInput(
        dipendente_id="dip-1", anno=2026, retribuzione_annua=20000.0)))
    tfr_dopo_primo = db["dipendenti"].docs[0]["tfr_accantonato"]

    # stesso dipendente+anno, retribuzione diversa: prima di questo fix
    # avrebbe aggiunto un secondo record e un secondo incremento del saldo.
    esito2 = _run(mod.registra_accantonamento_tfr(mod.AccantonamentoTFRInput(
        dipendente_id="dip-1", anno=2026, retribuzione_annua=99999.0)))

    assert esito2["gia_registrato"] is True
    assert esito2["accantonamento_id"] == esito1["accantonamento_id"]
    assert len(db["tfr_accantonamenti"].docs) == 1
    assert len(_righe_per_tipo(db, "tfr_accantonamento")) == 1
    assert db["dipendenti"].docs[0]["tfr_accantonato"] == pytest.approx(tfr_dopo_primo)


def test_accantonamento_totale_negativo_rifiutato(monkeypatch):
    """Audit 19/09/2026 (finding 1): un indice ISTAT molto negativo (es.
    errore di digitazione) puo' rendere la rivalutazione piu' negativa
    della quota annuale. Passato cosi' al motore, DARE Quote TFR e AVERE
    Fondo TFR sarebbero entrambi negativi e uguali in valore assoluto: la
    scrittura quadrerebbe (dare == avere) ma sarebbe contabilmente
    invertita. Va rifiutato prima di scrivere, senza alcun effetto
    collaterale."""
    from fastapi import HTTPException

    db = _db_con_dipendente(tfr_accantonato=5000.0)
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))

    input_data = mod.AccantonamentoTFRInput(
        dipendente_id="dip-1", anno=2026, retribuzione_annua=1000.0, indice_istat=-50.0,
    )
    # quota_annuale = 1000/13.5 = 74.07; tasso = (1.5 - 50*0.75)/100 = -0.3585;
    # rivalutazione = 5000 * -0.3585 = -1792.5; totale = 74.07 - 1792.5 < 0.
    with pytest.raises(HTTPException) as exc:
        _run(mod.registra_accantonamento_tfr(input_data))
    assert exc.value.status_code == 400

    assert db["tfr_accantonamenti"].docs == []
    assert _righe_per_tipo(db, "tfr_accantonamento") == []
    assert db["dipendenti"].docs[0]["tfr_accantonato"] == 5000.0


# ---------------------------------------------------------------------------
# 2 e 3. Liquidazione (fondo + ritenute)
# ---------------------------------------------------------------------------

def test_liquidazione_fondo_e_ritenute_bilanciate_e_idempotenti(monkeypatch):
    db = _db_con_dipendente(tfr_accantonato=3000.0)
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))

    input_data = mod.LiquidazioneTFRInput(
        dipendente_id="dip-1", data_liquidazione="2026-06-30", motivo="dimissioni",
    )
    esito = _run(mod.liquida_tfr(input_data))
    liquidazione_id = esito["liquidazione_id"]

    fondo = _righe_per_tipo(db, "tfr_liquidazione")
    ritenute = _righe_per_tipo(db, "ritenuta_tfr")
    assert len(fondo) == 1
    assert len(ritenute) == 1  # ALIQUOTA_TFR = 23% > 0
    _assert_bilanciata(fondo[0])
    _assert_bilanciata(ritenute[0])

    assert fondo[0]["liquidazione_id"] == liquidazione_id
    assert fondo[0]["dipendente_id"] == "dip-1"
    assert {r["conto_codice"] for r in fondo[0]["righe"]} == {"29.01.01", "39.07.05"}
    assert {r["conto_codice"] for r in ritenute[0]["righe"]} == {"39.07.05", "35.03.15"}

    assert fondo[0]["numero_registrazione"] != ritenute[0]["numero_registrazione"]

    # Richiamare registra_scrittura_semplice con la STESSA liquidazione (stessa
    # chiave naturale) non deve duplicare, anche se liquida_tfr non ha guardia
    # propria per "stessa liquidazione due volte": la idempotenza è nel motore.
    from app.services.registrazione_contabile import registra_scrittura_semplice, riga, _C_FONDO_TFR, _C_PERSONALE_LIQUIDAZIONE
    esito2 = _run(registra_scrittura_semplice(
        db,
        movimento={"tipo": "tfr_liquidazione", "liquidazione_id": liquidazione_id},
        righe=[riga(_C_FONDO_TFR, dare=1), riga(_C_PERSONALE_LIQUIDAZIONE, avere=1)],
        chiave_naturale={"tipo": "tfr_liquidazione", "liquidazione_id": liquidazione_id},
    ))
    assert esito2["gia_presente"] is True
    assert len(_righe_per_tipo(db, "tfr_liquidazione")) == 1


def test_liquidazione_senza_ritenute_non_scrive_seconda_scrittura(monkeypatch):
    """Se ALIQUOTA_TFR fosse 0 (o l'importo di ritenute nullo) la seconda
    scrittura non deve comparire: verificato forzando ritenute=0 a livello di
    modulo per isolare il comportamento del ramo `if ritenute > 0`."""
    db = _db_con_dipendente(tfr_accantonato=1000.0)
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
    monkeypatch.setattr(mod, "ALIQUOTA_TFR", 0.0)

    _run(mod.liquida_tfr(mod.LiquidazioneTFRInput(
        dipendente_id="dip-1", data_liquidazione="2026-06-30", motivo="pensionamento",
    )))
    assert len(_righe_per_tipo(db, "tfr_liquidazione")) == 1
    assert len(_righe_per_tipo(db, "ritenuta_tfr")) == 0


# ---------------------------------------------------------------------------
# 4. Acconto TFR
# ---------------------------------------------------------------------------

def test_acconto_tfr_scrittura_bilanciata_e_idempotente(monkeypatch):
    db = _db_con_dipendente(tfr_accantonato=2000.0)
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))

    input_data = mod.AccontoInput(
        dipendente_id="dip-1", tipo="tfr", importo=500.0, data="2026-05-10",
    )
    esito = _run(mod.registra_acconto(input_data))
    acconto_id = esito["acconto_id"]

    movimenti = _righe_per_tipo(db, "acconto_tfr")
    assert len(movimenti) == 1
    mov = movimenti[0]
    _assert_bilanciata(mov)
    assert mov["numero_registrazione"] == 1
    assert mov["acconto_id"] == acconto_id
    assert mov["dipendente_id"] == "dip-1"
    assert mov["importo"] == 500.0
    assert {r["conto_codice"] for r in mov["righe"]} == {"29.01.01", "39.07.05"}

    # Un acconto non-TFR non deve produrre nessuna scrittura contabile.
    _run(mod.registra_acconto(mod.AccontoInput(
        dipendente_id="dip-1", tipo="ferie", importo=100.0, data="2026-05-11",
    )))
    assert len(_righe_per_tipo(db, "acconto_tfr")) == 1


def test_acconto_tfr_chiave_naturale_e_specifica_dell_acconto(monkeypatch):
    """Chiamare `registra_scrittura_semplice` due volte con lo stesso
    `acconto_id` (retry di rete sullo stesso POST, pattern di cespiti.py) non
    duplica la scrittura."""
    db = _db_con_dipendente(tfr_accantonato=2000.0)
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))

    from app.services.registrazione_contabile import registra_scrittura_semplice, riga, _C_FONDO_TFR, _C_PERSONALE_LIQUIDAZIONE

    async def _doppio():
        await registra_scrittura_semplice(
            db,
            movimento={"tipo": "acconto_tfr", "acconto_id": "acc-1", "importo": 200.0},
            righe=[riga(_C_FONDO_TFR, dare=200.0), riga(_C_PERSONALE_LIQUIDAZIONE, avere=200.0)],
            chiave_naturale={"tipo": "acconto_tfr", "acconto_id": "acc-1"},
        )
        return await registra_scrittura_semplice(
            db,
            movimento={"tipo": "acconto_tfr", "acconto_id": "acc-1", "importo": 200.0},
            righe=[riga(_C_FONDO_TFR, dare=200.0), riga(_C_PERSONALE_LIQUIDAZIONE, avere=200.0)],
            chiave_naturale={"tipo": "acconto_tfr", "acconto_id": "acc-1"},
        )

    esito2 = _run(_doppio())
    assert esito2["gia_presente"] is True
    assert len(_righe_per_tipo(db, "acconto_tfr")) == 1
