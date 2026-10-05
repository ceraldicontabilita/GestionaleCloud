"""Colazioni B&B: il titolare entra con la sessione del gestionale, mai con un PIN suo.

Il token lo emette il database (`bb_tit_sessione_apri`) dietro la chiave di
runtime che ha solo questo backend; qui si verifica che l'endpoint lo chieda
soltanto per un amministratore e che non sia pubblico.

Gli ordini mattutini dell'albergatore sono l'eccezione dichiarata: l'albergatore
non ha un JWT dell'ERP, porta il token `tk:` di Supabase e l'handler lo verifica
con `bb_alb_stato`. Quei due percorsi stanno in `PUBLIC_PATHS` con il motivo, e
qui si prova che il middleware li lascia passare e che un token finto torna 401.
"""
import asyncio

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.middleware.authentication import PUBLIC_PATHS
from app.routers import colazioni
from app.utils.dependencies import get_current_admin_user

# percorso -> motivo per cui sta in PUBLIC_PATHS (la credenziale e' il token
# tk: dell'albergatore, verificato dentro l'handler da bb_alb_stato)
PUBBLICI_MOTIVATI = {
    "/api/colazioni/ordini-prodotti/albergatore": "token tk: dell'albergatore verificato da bb_alb_stato",
    "/api/colazioni/ordini-prodotti/albergatore/elenco": "token tk: dell'albergatore verificato da bb_alb_stato",
    "/api/colazioni/ricariche/sumup": "token tk: verificato dalla preparazione atomica della ricarica",
    "/api/colazioni/ricariche/sumup/sincronizza": "token tk: verificato da bb_alb_portafoglio",
    "/api/colazioni/ricariche/sumup/webhook": "evento riletto e verificato tramite API SumUp autenticata",
    "/api/colazioni/menu-ospite/catalogo": "codice voucher e giornata verificati da bb_menu_ospite",
    "/api/colazioni/menu-ospite/ordine": "codice voucher, giornata e prezzi verificati da bb_ospite_menu_salva",
}


def _client(monkeypatch, admin: bool, esito=None):
    app = FastAPI()
    app.include_router(colazioni.router, prefix="/api/colazioni")

    async def _admin():
        if not admin:
            raise HTTPException(status_code=403, detail="Admin access required")
        return {"id": "1", "role": "admin"}

    app.dependency_overrides[get_current_admin_user] = _admin

    async def _finto():
        return esito

    monkeypatch.setattr(colazioni, "_apri_sessione_supabase", _finto)
    return TestClient(app)


def test_admin_riceve_il_token(monkeypatch):
    c = _client(monkeypatch, True, {"token": "tk:abc", "scade": "2026-10-01T00:00:00Z"})
    r = c.post("/api/colazioni/accesso")
    assert r.status_code == 200
    assert r.json() == {"token": "tk:abc", "scade": "2026-10-01T00:00:00Z"}


def test_chi_non_e_admin_non_riceve_niente(monkeypatch):
    c = _client(monkeypatch, False, {"token": "tk:abc"})
    assert c.post("/api/colazioni/accesso").status_code == 403


def test_risposta_senza_token_e_un_errore(monkeypatch):
    c = _client(monkeypatch, True, {})
    assert c.post("/api/colazioni/accesso").status_code == 502


def test_senza_configurazione_supabase_risponde_503(monkeypatch):
    for nome in ("SUPABASE_URL", "SUPABASE_PUBLISHABLE_KEY", "SUPABASE_RUNTIME_SECRET"):
        monkeypatch.setattr(colazioni.settings, nome, None, raising=False)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(colazioni._apri_sessione_supabase())
    assert exc.value.status_code == 503


def test_solo_gli_endpoint_dell_albergatore_sono_pubblici_e_con_motivo():
    pubblici = {p for p in PUBLIC_PATHS if p.startswith("/api/colazioni")}
    assert pubblici == set(PUBBLICI_MOTIVATI), (
        "un percorso /api/colazioni nuovo in PUBLIC_PATHS deve avere qui il suo motivo")
    assert "/api/colazioni/accesso" not in PUBLIC_PATHS
    assert all(PUBBLICI_MOTIVATI.values())


def test_l_endpoint_e_registrato_nel_gestionale():
    from app.main import app

    percorsi = {getattr(r, "path", "") for r in app.routes}
    assert "/api/colazioni/accesso" in percorsi


def _client_gestionale(monkeypatch, token_valido: str):
    """TestClient su app.main:app: passa dal middleware globale, non dal solo router."""
    from app.main import app
    from app.lotti.servizi import ordini_hotel

    async def contesto(sid, token):
        if token != token_valido:
            raise HTTPException(status_code=401, detail="Sessione albergatore non valida")
        return ({}, {"struttura": {"nome": "Hotel Centro"}})

    async def lista(filtro, limite):
        return [{"id": "ORD-1", "struttura_id": filtro.get("struttura_id"), "righe": [], "totale": 0}]

    monkeypatch.setattr(colazioni, "_contesto_ordine_albergatore", contesto)
    monkeypatch.setattr(ordini_hotel, "lista_ordini", lista)
    return TestClient(app)


def test_elenco_ordini_passa_dal_middleware_con_il_token_dell_albergatore(monkeypatch):
    c = _client_gestionale(monkeypatch, "tk:buono")
    r = c.post("/api/colazioni/ordini-prodotti/albergatore/elenco", json={"sid": "hotel-1", "p": "tk:buono"})
    assert r.status_code == 200, r.text
    assert r.json()["ordini"][0]["id"] == "ORD-1"


def test_un_token_finto_dell_albergatore_e_rifiutato_dall_handler(monkeypatch):
    c = _client_gestionale(monkeypatch, "tk:buono")
    r = c.post("/api/colazioni/ordini-prodotti/albergatore/elenco", json={"sid": "hotel-1", "p": "tk:finto"})
    assert r.status_code == 401
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    domani = (datetime.now(ZoneInfo("Europe/Rome")).date() + timedelta(days=1)).isoformat()
    r = c.post("/api/colazioni/ordini-prodotti/albergatore",
               json={"sid": "hotel-1", "p": "tk:finto", "data_consegna": domani, "ora_ritiro": "07:00",
                     "righe": [{"chiave": "interno:p1", "quantita": 1}]})
    assert r.status_code == 401, r.text


def test_gli_altri_endpoint_colazioni_restano_chiusi_dal_middleware(monkeypatch):
    c = _client_gestionale(monkeypatch, "tk:buono")
    assert c.post("/api/colazioni/accesso").status_code == 401
    assert c.get("/api/colazioni/ordini-prodotti").status_code == 401
    assert c.get("/api/colazioni/catalogo-prodotti").status_code == 401
