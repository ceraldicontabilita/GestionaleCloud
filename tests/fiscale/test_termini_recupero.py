"""Termini di recupero dei tributi: servizio puro, rotta e ingresso dal database.

Le righe sono quelle vere della vista ``verifica.tabulato_tributi_termini``
(01/10/2026), senza dati personali: codici tributo, periodi, scadenze.
"""
import asyncio
import inspect
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services import termini_recupero as t

OGGI = date(2026, 10, 1)


def _riga(codice, periodo, scadenza, stato, recuperabile, **extra):
    base = {
        "codice": codice, "tributo": extra.pop("tributo", f"Tributo {codice}"), "tipo": "mensile",
        "periodo": periodo, "scadenza": scadenza, "stato": stato,
        "esito": "VERSAMENTO NON TROVATO" if stato == "MANCANTE" else "F24 SENZA QUIETANZA",
        "pagato": None, "date_pagamento": None, "protocolli": None, "ha_f24": stato != "MANCANTE",
        "termine_ordinario": recuperabile, "slittamento_covid": "Nessuno slittamento Covid",
        "recuperabile_entro": recuperabile,
        "situazione_termini": None,
    }
    base.update(extra)
    return base


RIGHE = [
    _riga("3847", "03/2022", "2022-04-16", "MANCANTE", "2026-12-31"),
    _riga("INPS_DIP", "11/2021", "2021-12-16", "MANCANTE", "2026-12-16"),
    _riga("CXX", "02/2026", "2026-03-16", "F24_SENZA_QUIETANZA", "2030-03-16"),
    _riga("INPS_DIP", "10/2020", "2020-11-16", "MANCANTE", "2026-05-17", slittamento_covid="Covid: prescrizione sospesa 182 giorni"),
    _riga("1001", "12/2019", "2020-01-16", "MANCANTE", "2024-12-31"),
    _riga("3918", "12/2022", "2022-12-16", "PAGATO", "2027-12-31", pagato=1234.56, date_pagamento="16/12/2022"),
    _riga("7085", "2019", "2019-12-31", "MANCANTE", None),
]


def test_normalizza_giorni_rimasti_urgenza_e_importo_in_centesimi():
    v = t.normalizza(RIGHE[1], OGGI)
    assert v["situazione"] == t.ANCORA_RECUPERABILE
    assert v["giorni_rimasti"] == 76 and v["urgente"] is True
    lontano = t.normalizza(RIGHE[0], OGGI)
    assert lontano["giorni_rimasti"] == 91 and lontano["urgente"] is True       # sotto 120
    assert t.normalizza(RIGHE[2], OGGI)["urgente"] is False                     # 2030
    pagato = t.normalizza(RIGHE[5], OGGI)
    assert pagato["pagato_cents"] == 123456 and pagato["situazione"] is None
    assert isinstance(pagato["pagato_cents"], int)


def test_il_confine_dei_120_giorni_e_il_giorno_stesso_del_termine():
    # 120 giorni esatti: non urgente; 119: urgente; oggi stesso: ancora recuperabile (0 giorni).
    r120 = _riga("1001", "01/2022", "2022-02-16", "MANCANTE", "2027-01-29")
    r119 = _riga("1001", "02/2022", "2022-03-16", "MANCANTE", "2027-01-28")
    r0 = _riga("1001", "03/2022", "2022-04-16", "MANCANTE", "2026-10-01")
    assert (date(2027, 1, 29) - OGGI).days == 120
    assert t.normalizza(r120, OGGI)["urgente"] is False
    assert t.normalizza(r119, OGGI)["urgente"] is True
    zero = t.normalizza(r0, OGGI)
    assert zero["giorni_rimasti"] == 0 and zero["situazione"] == t.ANCORA_RECUPERABILE and zero["urgente"] is True


def test_senza_termine_resta_da_verificare_mai_ancora_recuperabile():
    v = t.normalizza(RIGHE[6], OGGI)
    assert v["situazione"] == t.DA_VERIFICARE
    assert v["giorni_rimasti"] is None and v["urgente"] is False and v["recuperabile_entro"] is None


def test_filtro_predefinito_solo_versamento_mancante_e_ordine():
    r = t.riepilogo(RIGHE, oggi=OGGI)
    ids = [(v["codice"], v["periodo"]) for v in r["voci"]]
    # prima gli ancora recuperabili per data piu' vicina, poi le scadute (la piu' recente prima), in fondo senza termine
    assert ids == [("INPS_DIP", "11/2021"), ("3847", "03/2022"), ("CXX", "02/2026"),
                   ("INPS_DIP", "10/2020"), ("1001", "12/2019"), ("7085", "2019")]
    assert all(v["stato"] in t.STATI_APERTI for v in r["voci"])          # il pagato non c'e'
    assert r["totale"] == 6 and r["avviso"] == t.AVVISO
    assert r["conteggi"] == {"righe": 7, "aperte": 6, "ancora_recuperabili": 3, "urgenti": 2,
                             "scadute": 2, "da_verificare": 1}
    assert r["primo_termine"] == {"recuperabile_entro": "2026-12-16", "giorni_rimasti": 76,
                                  "codice": "INPS_DIP", "periodo": "11/2021"}


def test_filtri_stato_situazione_codice_e_ricerca():
    assert t.riepilogo(RIGHE, oggi=OGGI, stato="TUTTI")["totale"] == 7
    assert [v["codice"] for v in t.riepilogo(RIGHE, oggi=OGGI, stato="PAGATO")["voci"]] == ["3918"]
    solo_scadute = t.riepilogo(RIGHE, oggi=OGGI, situazione=t.TERMINE_SCADUTO)
    assert {(v["codice"], v["periodo"]) for v in solo_scadute["voci"]} == {("INPS_DIP", "10/2020"), ("1001", "12/2019")}
    assert t.riepilogo(RIGHE, oggi=OGGI, codice="INPS_DIP")["totale"] == 2
    assert [v["codice"] for v in t.riepilogo(RIGHE, oggi=OGGI, cerca="  cxx ")["voci"]] == ["CXX"]
    # i conteggi non dipendono dal filtro: dicono sempre quanto c'e' in tutto
    assert t.riepilogo(RIGHE, oggi=OGGI, codice="CXX")["conteggi"]["aperte"] == 6


def test_nessun_float_e_nessun_calcolo_di_termini_nel_servizio():
    sorgente = inspect.getsource(t)
    assert "float(" not in sorgente
    # il termine arriva dalla vista: il servizio non applica nessuna regola di legge
    assert "timedelta" not in sorgente and "relativedelta" not in sorgente


def test_oggi_usa_il_fuso_di_roma(monkeypatch):
    assert isinstance(t.oggi_roma(), date)


# ── rotta ──────────────────────────────────────────────────────────────────────

class _DbFinto:
    def __init__(self, righe):
        self.righe, self.chiamate = righe, 0

    async def termini_recupero(self):
        self.chiamate += 1
        return self.righe


def _client(monkeypatch, db):
    from app.database import Database
    from app.middleware import performance
    from app.routers.f24 import tributi
    from app.utils.dependencies import get_current_admin_user

    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))
    asyncio.run(performance.svuota_istantanee())
    app = FastAPI()
    app.include_router(tributi.router, prefix="/api/f24")
    app.dependency_overrides[get_current_admin_user] = lambda: {"sub": "a", "role": "admin"}
    return TestClient(app), app, get_current_admin_user


def test_rotta_restituisce_voci_conteggi_e_avviso(monkeypatch):
    db = _DbFinto(RIGHE)
    client, _, _ = _client(monkeypatch, db)
    r = client.get("/api/f24/tributi/termini")
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["totale"] == 6 and corpo["avviso"] == t.AVVISO
    assert corpo["voci"][0]["codice"] == "INPS_DIP" and corpo["voci"][0]["urgente"] is True
    assert corpo["conteggi"]["ancora_recuperabili"] == 3

    # secondo giro: copia pronta, la vista (5 secondi) non si rilegge
    client.get("/api/f24/tributi/termini?situazione=TERMINE_SCADUTO")
    assert db.chiamate == 1


def test_rotta_rifiuta_una_situazione_sconosciuta_e_chiede_il_login_admin(monkeypatch):
    db = _DbFinto(RIGHE)
    client, app, dipendenza = _client(monkeypatch, db)
    assert client.get("/api/f24/tributi/termini?situazione=BOH").status_code == 422
    app.dependency_overrides.pop(dipendenza)
    assert client.get("/api/f24/tributi/termini").status_code in (401, 403)


def test_rotta_con_database_guasto_non_inventa_righe(monkeypatch):
    class _Guasto:
        async def termini_recupero(self):
            raise RuntimeError("gc_termini_recupero: errore remoto")

    client, _, _ = _client(monkeypatch, _Guasto())
    with pytest.raises(RuntimeError):
        client.get("/api/f24/tributi/termini")


# ── ingresso dal database ─────────────────────────────────────────────────────

def test_il_runtime_chiama_la_funzione_gc_e_rifiuta_una_risposta_non_lista():
    from app.services.supabase_runtime_database import SupabaseRuntimeDatabase

    chiamate = []

    class _Falso(SupabaseRuntimeDatabase):
        def __init__(self, risposta):  # noqa: D401 - niente rete
            self.risposta = risposta

        async def _rpc(self, nome, payload):
            chiamate.append((nome, payload))
            return self.risposta

    righe = asyncio.run(_Falso([{"codice": "3847"}, "spazzatura"]).termini_recupero())
    assert righe == [{"codice": "3847"}] and chiamate == [("gc_termini_recupero", {})]
    with pytest.raises(RuntimeError):
        asyncio.run(_Falso({"errore": "x"}).termini_recupero())


def test_la_migrazione_della_funzione_e_nel_repo_e_protegge_l_accesso():
    import pathlib

    sql = next(pathlib.Path("supabase/migrations").glob("*_gc_termini_recupero.sql")).read_text(encoding="utf-8")
    assert "gc_assert_runtime_secret()" in sql                       # senza segreto: accesso negato
    assert "security definer" in sql and "set search_path to 'pg_catalog'" in sql
    assert "revoke all on function public.gc_termini_recupero() from public, anon, authenticated" in sql
    assert "to anon, service_role" in sql
