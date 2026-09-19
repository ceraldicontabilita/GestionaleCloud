"""
test_auth_permessi.py
──────────────────────
Test PURI del modello di autenticazione (fase 2 ristrutturazione 24/07/2026):
niente MongoDB, niente rete — AUTH_SECRET impostato via env così il secret
non viene cercato nel DB.

Coprono: token assente/scaduto/manomesso, ruolo nel token, whitelist delle
scritture tablet, rotte pubbliche, e la protezione require_admin sugli
endpoint sensibili (a livello di firma: gli endpoint distruttivi DEVONO
dichiarare la dipendenza).
"""
import os
os.environ.setdefault("AUTH_SECRET", "test-secret-non-usare-in-prod")

import asyncio
import inspect
import pytest

from app.lotti.auth import (
    make_token, verify_token, auth_dependency, PUBLIC_PREFIXES,
    _scrittura_tablet_consentita,
)
from fastapi import HTTPException


class FintaRichiesta:
    """Request minimale per auth_dependency (solo ciò che usa)."""
    def __init__(self, method="GET", path="/api/qualcosa", token=None, query=None):
        self.method = method
        self.headers = {"authorization": f"Bearer {token}"} if token else {}
        self.query_params = query or {}
        self.state = type("S", (), {})()
        self._path = path

    @property
    def url(self):
        return type("U", (), {"path": self._path})()


def _run(coro):
    return asyncio.run(coro)


# ── Token ───────────────────────────────────────────────────────────────────
def test_token_valido_roundtrip():
    t = make_token("op1", "Mario", "operatore")
    data = verify_token(t)
    assert data and data["sub"] == "op1" and data["ruolo"] == "operatore"


def test_token_manomesso_rifiutato():
    t = make_token("op1", "Mario", "operatore")
    assert verify_token(t[:-2] + "xx") is None
    assert verify_token("") is None
    assert verify_token("non-un-jwt") is None


def test_token_scaduto_rifiutato():
    t = make_token("op1", "Mario", "operatore", ore=-1)
    assert verify_token(t) is None


def test_secret_stabile_derivato_da_supabase(monkeypatch):
    import app.lotti.auth as auth
    monkeypatch.delenv("AUTH_SECRET", raising=False)
    monkeypatch.setenv("LOTTI_DB_SECRET", "segreto-db-di-test")
    primo = auth._secret()
    auth._RUNTIME_SECRET = None
    secondo = auth._secret()
    assert primo == secondo
    assert primo != "segreto-db-di-test"


# ── Gate globale (auth_dependency) ──────────────────────────────────────────
def test_scrittura_senza_token_bloccata():
    req = FintaRichiesta(method="POST", path="/api/fatture/dedup")
    with pytest.raises(HTTPException) as exc:
        _run(auth_dependency(req))
    assert exc.value.status_code == 401


def test_scrittura_con_token_passa():
    t = make_token("op1", "Mario", "operatore")
    req = FintaRichiesta(method="POST", path="/api/ricette", token=t)
    assert _run(auth_dependency(req)) is None  # nessuna eccezione


def test_rotte_pubbliche_passano_senza_token():
    for p in ("/api/health", "/api/foto/abc", "/api/auth/login"):
        req = FintaRichiesta(method="GET", path=p)
        assert _run(auth_dependency(req)) is None
    # /api/foto è pubblica perché i tag <img> non mandano l'header
    assert any(p.startswith("/api/foto") for p in PUBLIC_PREFIXES)


def test_whitelist_tablet_solo_gesti_operativi():
    # il timbro temperatura del tablet passa senza token…
    assert _scrittura_tablet_consentita("/api/temperature-positive/scheda/2026/frigo1/registra", "POST")
    # …ma la RICONFIGURAZIONE della scheda (limiti temperatura) NO
    assert not _scrittura_tablet_consentita("/api/temperature-positive/scheda/2026/frigo1/config", "PUT")
    # creazione lotto da tablet sì, cancellazione no
    assert _scrittura_tablet_consentita("/api/lotti", "POST")
    assert not _scrittura_tablet_consentita("/api/lotti", "DELETE")
    assert not _scrittura_tablet_consentita("/api/fatture/dedup", "POST")


# ── require_admin dichiarato sugli endpoint sensibili ───────────────────────
def _ha_require_admin(fn):
    return "require_admin" in inspect.getsource(fn).split("\n)")[0] or \
           any("require_admin" in str(p.default) for p in inspect.signature(fn).parameters.values())


@pytest.mark.parametrize("modulo,funzione", [
    ("app.lotti.routers.fatture", "dedup_fatture") ,
])
def test_placeholder_import(modulo, funzione):
    # segnaposto: la verifica di copertura è nel test sotto, per firma
    assert modulo


def test_endpoint_distruttivi_dichiarano_require_admin():
    """Gli endpoint distruttivi/di configurazione protetti nella fase 2
    devono continuare a dichiarare Depends(require_admin): questa è la
    rete di sicurezza contro regressioni future."""
    import importlib
    da_verificare = [
        ("app.lotti.routers.scheduler", ("/start", "/stop", "/run-pulizia-lotti-now")),
        ("app.lotti.routers.fatture", ("/dedup", "/importa-annulla")),
        ("app.lotti.routers.lotti_fornitori", ("/reimporta-da-fatture", "/pulizia-scaduti")),
        ("app.lotti.routers.temperature_positive", ("/scheda/{anno}/{frigorifero}/config",)),
        ("app.lotti.routers.temperature_negative", ("/scheda/{anno}/{congelatore}/config",)),
        # 25/07/2026: chi riscrive registri HACCP STORICI deve essere admin.
        # Prima un dipendente (o un tablet lasciato acceso) poteva sostituire
        # un anno intero di temperature o rigenerare dati retroattivi.
        ("app.lotti.routers.temperature_positive", ('router.put("/scheda/{anno}/{frigorifero}")',
                                          "/popola-con-chiusure/{anno}")),
        ("app.lotti.routers.temperature_negative", ('router.put("/scheda/{anno}/{congelatore}")',
                                          "/popola-con-chiusure/{anno}")),
        ("app.lotti.routers.haccp_auto", ("/popola-temperature", "/popola-sanificazione",
                                "/popola-tutto", "/genera-oggi")),
        # 25/07/2026: rinominare un frigorifero riscrive il nome su TUTTI i
        # controlli temperatura già registrati (update_many sullo storico):
        # è una modifica ai registri, non una preferenza di visualizzazione.
        # La lettura (GET) resta libera: serve ai tablet di reparto.
        # 25/07/2026 (TRANCHE 2): import e sincronizzazioni di MASSA. Ognuno
        # riscrive cataloghi o listini interi in un colpo solo.
        ("app.lotti.routers.acquaviva", ("/import-listino-2026", "/import-listino-pdf",
                               "/sync-prezzi", "/import-alpha")),
        ("app.lotti.routers.listino", ("/sync-da-fatture",)),
        ("app.lotti.routers.sconti_merce", ("/importa-da-fatture", "/valorizza-da-fatture")),
        # Nascondere un avviso del Supervisore è una decisione del titolare.
        ("app.lotti.routers.supervisor_operativo", ("/alerts/{alert_id}/silenzia",)),
        # 25/07/2026 — Enzo: «il dipendente deve solo produrre e vedere le
        # ricette, tutto il resto lo guardo io e lo utilizzo io». Cancellare un
        # lotto è la cosa più definitiva che si possa fare alla tracciabilità.
        ("app.lotti.routers.lotti", ('router.delete("/{lotto_id}")',)),
        ("app.lotti.routers.lotti_fornitori", ('router.delete("/{lotto_id}")',)),
        ("app.lotti.routers.attrezzature", ('router.post("/frigo")',
                                  'router.post("/congelatore")',
                                  "/frigo/{numero}/rinomina",
                                  "/congelatore/{numero}/rinomina",
                                  'router.delete("/frigo/{numero}")',
                                  'router.delete("/congelatore/{numero}")')),
    ]
    os.environ.setdefault("MONGO_URL", "mongodb://x")
    os.environ.setdefault("DB_NAME", "test")
    for nome_modulo, paths in da_verificare:
        mod = importlib.import_module(nome_modulo)
        src = inspect.getsource(mod)
        for p in paths:
            # ogni decorator col path deve avere require_admin nella def subito dopo
            # una voce che contiene già "router." è cercata alla lettera:
            # serve quando lo stesso path esiste in GET (libero) e in PUT (admin)
            ago = p if p.startswith("router.") else f'"{p}"'
            idx = src.find(ago)
            assert idx > 0, f"{nome_modulo}: path {p} non trovato"
            blocco = src[idx: idx + 600]
            assert "require_admin" in blocco, f"{nome_modulo} {p}: manca require_admin"
