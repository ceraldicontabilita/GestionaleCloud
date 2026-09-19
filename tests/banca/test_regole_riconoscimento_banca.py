"""Regole di riconoscimento IMPARATE sui movimenti bancari (19/09/2026).

Il titolare vuole poter dire esplicitamente "questo e' di Nexi" per un
movimento che il motore generico (`app.services.categorizzazione_movimenti`)
riconoscerebbe gia' da solo, ma solo genericamente (es. "Commissioni
bancarie"). Coperti qui: creazione di una regola da un movimento reale,
applicazione al prossimo import, una regola specifica che vince sul motore
generico, ed eliminazione che non tocca retroattivamente i movimenti gia'
categorizzati da quella regola.
"""
import asyncio

import pytest
from fastapi import HTTPException

from app.services import regole_riconoscimento_banca as regole
from app.services.categorizzazione_movimenti import categorizza_movimento_bancario
from app.services.archivio_documenti_memoria import MemorySheetsClient
from app.routers.bank import regole_riconoscimento as router_modulo


def _run(coro):
    return asyncio.run(coro)


# --- estrazione del pattern dalla causale -----------------------------------

def test_estrai_pattern_toglie_riferimenti_date_e_importi():
    causale = "COMMISSIONI NEXI PAYMENTS SPA RIF. NX00192837/12345 DEL 12/03/2026 EUR 45,90"
    pattern = regole.estrai_pattern_da_causale(causale)
    assert "NEXI PAYMENTS" in pattern
    assert "NX00192837" not in pattern
    assert "12/03/2026" not in pattern
    assert "45,90" not in pattern


def test_estrai_pattern_causale_semplice_resta_uguale():
    assert regole.estrai_pattern_da_causale("NEXI PAYMENTS") == "NEXI PAYMENTS"


def test_estrai_pattern_causale_troppo_generica_usa_la_causale_intera():
    # dopo aver tolto RIF/data/importo non resta nulla di specifico: si tiene
    # la causale intera normalizzata (caso ambiguo, lasciato al titolare).
    causale = "RIF. 12345/67890 DEL 01/01/2026"
    pattern = regole.estrai_pattern_da_causale(causale)
    assert pattern == regole._normalizza(causale)


# --- CRUD della regola -------------------------------------------------------

def test_crea_regola_pattern_troppo_generico_e_rifiutata():
    """Audit 19/09/2026 su PR #500: un pattern fatto solo di vocabolario
    bancario comune ("COMMISSIONI SU BONIFICI ESTERI", senza il nome del
    circuito/fornitore) combacerebbe anche con le commissioni di una
    controparte diversa da quella per cui e' stato imparato — indovinare,
    non riconoscere. Va rifiutato, non salvato silenziosamente."""
    db = MemorySheetsClient()["regole_pattern_generico"]
    with pytest.raises(ValueError):
        _run(regole.crea_regola(
            db, pattern="COMMISSIONI SU BONIFICI ESTERI", entita_tipo="fornitore",
            entita_id="forn-nexi", entita_nome="Nexi Payments S.p.A.",
        ))
    with pytest.raises(ValueError):
        _run(regole.crea_regola(
            db, pattern=regole._normalizza("RIF. 12345/67890 DEL 01/01/2026"),
            entita_tipo="categoria", entita_nome="Altro",
        ))
    # Un pattern con un nome/servizio specifico dentro resta accettato.
    regola = _run(regole.crea_regola(
        db, pattern="COMMISSIONI NEXI PAYMENTS", entita_tipo="fornitore",
        entita_id="forn-nexi", entita_nome="Nexi Payments S.p.A.",
    ))
    assert regola["pattern"] == "COMMISSIONI NEXI PAYMENTS"


def test_crea_regola_fornitore_richiede_entita_id():
    db = MemorySheetsClient()["regole_crea_fornitore_senza_id"]
    with pytest.raises(ValueError):
        _run(regole.crea_regola(db, pattern="NEXI PAYMENTS", entita_tipo="fornitore", entita_nome="Nexi"))


def test_crea_regola_fornitore_categoria_di_default_fatture():
    db = MemorySheetsClient()["regole_crea_fornitore_default"]
    regola = _run(regole.crea_regola(
        db, pattern="nexi   payments", entita_tipo="fornitore",
        entita_id="forn-nexi", entita_nome="Nexi Payments S.p.A.", creata_da="titolare@test",
    ))
    assert regola["pattern"] == "NEXI PAYMENTS"  # normalizzato
    assert regola["categoria"] == "Fatture"
    assert regola["creata_da"] == "titolare@test"
    salvate = _run(regole.lista_regole(db))
    assert len(salvate) == 1 and salvate[0]["id"] == regola["id"]


def test_crea_regola_categoria_libera_senza_fornitore():
    db = MemorySheetsClient()["regole_crea_categoria_libera"]
    regola = _run(regole.crea_regola(
        db, pattern="QUOTA ASSOCIATIVA CONFCOMMERCIO", entita_tipo="categoria",
        entita_nome="Quota associativa", categoria="Altro",
    ))
    assert regola["entita_id"] is None
    assert regola["categoria"] == "Altro"


def test_elimina_regola_rimuove_solo_quella():
    db = MemorySheetsClient()["regole_elimina"]
    r1 = _run(regole.crea_regola(db, pattern="NEXI", entita_tipo="fornitore", entita_id="forn-1", entita_nome="Nexi"))
    r2 = _run(regole.crea_regola(db, pattern="SUMUP", entita_tipo="fornitore", entita_id="forn-2", entita_nome="SumUp"))
    assert _run(regole.elimina_regola(db, r1["id"])) is True
    rimaste = _run(regole.lista_regole(db))
    assert [r["id"] for r in rimaste] == [r2["id"]]
    assert _run(regole.elimina_regola(db, "non-esiste")) is False


# --- corrispondenza: la piu' specifica vince --------------------------------

def test_trova_regola_sceglie_il_pattern_piu_specifico():
    regole_salvate = [
        {"id": "generica", "pattern": "NEXI", "categoria": "Fatture"},
        {"id": "specifica", "pattern": "NEXI PAYMENTS SPA", "categoria": "Fatture"},
    ]
    trovata = regole.trova_regola_per_descrizione(regole_salvate, "COMMISSIONI NEXI PAYMENTS SPA DEL 12/03")
    assert trovata["id"] == "specifica"


# --- il motore di categorizzazione: una regola vince sul motore generico ----

def test_regola_appresa_vince_sul_motore_generico():
    descrizione = "ADDEBITO COMMISSIONI NEXI PAYMENTS SPA RIF. NX001 DEL 12/03/2026"
    # Da sola, la causale la riconoscerebbe SOLO come "Commissioni bancarie"
    # (parola chiave generica "COMMISSIONI").
    generico = categorizza_movimento_bancario(descrizione, -45.9)
    assert generico.categoria == "Commissioni bancarie"
    assert generico.fornitore_id is None

    regola_nexi = {
        "id": "r-nexi", "pattern": "NEXI PAYMENTS", "entita_tipo": "fornitore",
        "entita_id": "forn-nexi", "entita_nome": "Nexi Payments S.p.A.", "categoria": "Fatture",
    }
    con_regola = categorizza_movimento_bancario(descrizione, -45.9, regole=[regola_nexi])
    assert con_regola.categoria == "Fatture"
    assert con_regola.fornitore_id == "forn-nexi"
    assert con_regola.fornitore_nome == "Nexi Payments S.p.A."
    assert con_regola.regola_id == "r-nexi"
    assert "regola imparata" in con_regola.motivo


def test_nessuna_regola_combacia_ricade_sul_motore_generico():
    esito = categorizza_movimento_bancario(
        "ADDEBITO F24 IVA E RITENUTE", -780.0,
        regole=[{"id": "r-nexi", "pattern": "NEXI PAYMENTS", "entita_tipo": "fornitore",
                 "entita_id": "forn-nexi", "categoria": "Fatture"}],
    )
    assert esito.categoria == "F24"
    assert esito.regola_id is None


# --- endpoint: crea da un movimento, applica subito, elimina non retroattivo -

def _db_router(monkeypatch, nome):
    db = MemorySheetsClient()[nome]
    monkeypatch.setattr(router_modulo.Database, "get_db", staticmethod(lambda: db))
    return db


def test_crea_regola_da_movimento_la_applica_subito(monkeypatch):
    db = _db_router(monkeypatch, "regole_da_movimento")
    _run(db["estratto_conto_movimenti"].insert_one({
        "id": "mov-1", "data": "2026-03-12", "importo": -45.9, "tipo": "uscita",
        "categoria": "Commissioni bancarie", "categoria_auto": True,
        "descrizione_originale": "ADDEBITO COMMISSIONI NEXI PAYMENTS SPA RIF. NX001 DEL 12/03/2026",
    }))

    esito = _run(router_modulo.crea_regola_da_movimento(
        "mov-1",
        {"entita_tipo": "fornitore", "entita_id": "forn-nexi", "entita_nome": "Nexi Payments S.p.A."},
        _admin={"email": "titolare@test"},
    ))

    assert esito["success"] is True
    assert esito["regola"]["entita_id"] == "forn-nexi"
    assert "NEXI PAYMENTS" in esito["regola"]["pattern"]
    mov = _run(db["estratto_conto_movimenti"].find_one({"id": "mov-1"}, {"_id": 0}))
    assert mov["categoria"] == "Fatture"
    assert mov["fornitore_id"] == "forn-nexi"
    assert mov["fornitore"] == "Nexi Payments S.p.A."
    assert mov["regola_riconoscimento_id"] == esito["regola"]["id"]


def test_crea_regola_da_movimento_inesistente_da_404(monkeypatch):
    db = _db_router(monkeypatch, "regole_da_movimento_404")
    with pytest.raises(HTTPException) as exc:
        _run(router_modulo.crea_regola_da_movimento(
            "non-esiste", {"entita_tipo": "categoria", "entita_nome": "Altro"}, _admin={},
        ))
    assert exc.value.status_code == 404


def test_regola_si_applica_al_prossimo_movimento_con_causale_simile(monkeypatch):
    db = _db_router(monkeypatch, "regole_prossimo_movimento")
    _run(db["estratto_conto_movimenti"].insert_one({
        "id": "mov-1", "data": "2026-03-12", "importo": -45.9,
        "descrizione_originale": "ADDEBITO COMMISSIONI NEXI PAYMENTS SPA RIF. NX001 DEL 12/03/2026",
    }))
    _run(router_modulo.crea_regola_da_movimento(
        "mov-1", {"entita_tipo": "fornitore", "entita_id": "forn-nexi", "entita_nome": "Nexi Payments S.p.A."},
        _admin={},
    ))

    # Un movimento successivo, causale simile ma riferimento/data diversi
    # (variabili da un mese all'altro): la regola lo riconosce comunque.
    regole_salvate = _run(regole.carica_regole(db))
    esito = categorizza_movimento_bancario(
        "ADDEBITO COMMISSIONI NEXI PAYMENTS SPA RIF. NX999 DEL 15/04/2026", -52.3,
        regole=regole_salvate,
    )
    assert esito.categoria == "Fatture"
    assert esito.fornitore_id == "forn-nexi"


def test_eliminare_una_regola_non_tocca_i_movimenti_gia_categorizzati(monkeypatch):
    db = _db_router(monkeypatch, "regole_elimina_non_retroattivo")
    _run(db["estratto_conto_movimenti"].insert_one({
        "id": "mov-1", "data": "2026-03-12", "importo": -45.9,
        "descrizione_originale": "ADDEBITO COMMISSIONI NEXI PAYMENTS SPA RIF. NX001 DEL 12/03/2026",
    }))
    creazione = _run(router_modulo.crea_regola_da_movimento(
        "mov-1", {"entita_tipo": "fornitore", "entita_id": "forn-nexi", "entita_nome": "Nexi Payments S.p.A."},
        _admin={},
    ))
    regola_id = creazione["regola"]["id"]

    esito = _run(router_modulo.elimina_regola_riconoscimento(regola_id, _admin={}))
    assert esito["success"] is True

    # Il movimento gia' categorizzato resta come e' (nessun tocco retroattivo).
    mov = _run(db["estratto_conto_movimenti"].find_one({"id": "mov-1"}, {"_id": 0}))
    assert mov["categoria"] == "Fatture"
    assert mov["fornitore_id"] == "forn-nexi"

    # Ma la regola non si applica piu' ai prossimi movimenti.
    regole_rimaste = _run(regole.carica_regole(db))
    assert regole_rimaste == []
    esito_nuovo = categorizza_movimento_bancario(
        "ADDEBITO COMMISSIONI NEXI PAYMENTS SPA RIF. NX777 DEL 20/05/2026", -40.0,
        regole=regole_rimaste,
    )
    assert esito_nuovo.fornitore_id is None
    assert esito_nuovo.categoria == "Commissioni bancarie"  # ricade sul motore generico


def test_elimina_regola_inesistente_da_404(monkeypatch):
    db = _db_router(monkeypatch, "regole_elimina_404")
    with pytest.raises(HTTPException) as exc:
        _run(router_modulo.elimina_regola_riconoscimento("non-esiste", _admin={}))
    assert exc.value.status_code == 404


def test_lista_regole_endpoint(monkeypatch):
    db = _db_router(monkeypatch, "regole_lista_endpoint")
    _run(regole.crea_regola(db, pattern="NEXI", entita_tipo="fornitore", entita_id="f1", entita_nome="Nexi"))
    elenco = _run(router_modulo.get_regole_riconoscimento(_admin={}))
    assert len(elenco) == 1 and elenco[0]["entita_nome"] == "Nexi"


# --- il secondo punto collegato da #498: /force-reimport ---------------------

_INTESTAZIONE_CSV = ("Ragione Sociale;Data contabile;Data valuta;Banca;Rapporto;"
                     "Importo;Divisa;Descrizione;Categoria/sottocategoria;Hashtag")


class _FileCsv:
    def __init__(self, contenuto: bytes, filename: str = "estratto.csv"):
        self.filename = filename
        self._contenuto = contenuto

    async def read(self):
        return self._contenuto


def _csv_riga(descrizione, importo, data="12/03/2026"):
    return (f"CERALDI GROUP S.R.L.;{data};{data};05034 - BANCO BPM S.P.A.;"
            f"5462 - 03406 - 178800005462;{importo};EUR;{descrizione};;")


def test_regola_imparata_vince_sul_motore_generico_in_force_reimport(monkeypatch):
    """Stesso caso dell'/import, sull'altro punto collegato da #498."""
    from app.routers.bank import estratto_conto as ec_modulo

    db = MemorySheetsClient()["force_reimport_regola_appresa"]
    monkeypatch.setattr(ec_modulo.Database, "get_db", staticmethod(lambda: db))
    _run(db["regole_riconoscimento_banca"].insert_one({
        "id": "r-nexi", "pattern": "COMMISSIONI NEXI PAYMENTS", "entita_tipo": "fornitore",
        "entita_id": "forn-nexi", "entita_nome": "Nexi Payments S.p.A.", "categoria": "Fatture",
    }))
    csv_bytes = ("\r\n".join([_INTESTAZIONE_CSV,
                              _csv_riga("ADDEBITO COMMISSIONI NEXI PAYMENTS SPA", "-45,90")])
                 + "\r\n").encode("utf-8")

    _run(ec_modulo.force_reimport_estratto_conto(file=_FileCsv(csv_bytes), _admin={}))

    movimenti = _run(db["estratto_conto_movimenti"].find({}).to_list(100))
    assert len(movimenti) == 1
    assert movimenti[0]["categoria"] == "Fatture"
    assert movimenti[0]["fornitore_id"] == "forn-nexi"
