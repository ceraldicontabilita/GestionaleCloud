import asyncio
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.config import settings
from app.routers import google_drive_oauth as router
from app.services import drive_oauth as oauth
from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.utils.dependencies import get_current_admin_user
from app.utils.logger import OAuthCallbackRedaction


@pytest.fixture
def setup(monkeypatch):
    db = ClientArchivioMemoria()["oauth_test"]
    monkeypatch.setattr(
        settings, "GOOGLE_CLIENT_ID", "client-test.apps.googleusercontent.com"
    )
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "secret-test-privato")
    monkeypatch.setattr(settings, "GOOGLE_REFRESH_TOKEN", None)
    monkeypatch.setattr(
        settings,
        "GOOGLE_REDIRECT_URI",
        "https://impresasemplice.online/api/auth/google/callback",
    )
    monkeypatch.setattr(settings, "GOOGLE_DRIVE_DATI_FOLDER_ID", "folder-originale")
    monkeypatch.setattr(
        settings, "SECRET_KEY", "chiave-di-test-abbastanza-lunga-per-essere-cifrata"
    )
    monkeypatch.setattr(router.Database, "get_db", staticmethod(lambda: db))
    oauth.invalidate_cache()
    return db


def run(coro):
    return asyncio.run(coro)


def test_stato_pkce_sessione_monouso_e_scadenza(setup):
    async def scenario():
        url = await oauth.start_authorization(setup, "sessione-1")
        params = parse_qs(urlparse(url).query)
        assert params["redirect_uri"] == [settings.GOOGLE_REDIRECT_URI]
        assert params["code_challenge_method"] == ["S256"]
        assert settings.GOOGLE_CLIENT_SECRET not in url
        state = params["state"][0]
        with pytest.raises(oauth.DriveOAuthError):
            await oauth.consume_state(setup, state, "sessione-2")
        pending = await oauth.consume_state(setup, state, "sessione-1")
        assert len(oauth.unseal(pending["verifier_encrypted"])) >= 43
        with pytest.raises(oauth.DriveOAuthError):
            await oauth.consume_state(setup, state, "sessione-1")
        url2 = await oauth.start_authorization(setup, "sessione-1")
        state2 = parse_qs(urlparse(url2).query)["state"][0]
        ident = "state:" + hashlib.sha256(state2.encode()).hexdigest()
        await setup[oauth.STATE_COLLECTION].update_one(
            {"id": ident},
            {
                "$set": {
                    "expires_at": (
                        datetime.now(timezone.utc) - timedelta(seconds=1)
                    ).isoformat()
                }
            },
        )
        with pytest.raises(oauth.DriveOAuthError):
            await oauth.consume_state(setup, state2, "sessione-1")

    run(scenario())


def test_grant_cifrato_riletto_e_senza_secret(setup):
    async def scenario():
        proof = await oauth.save_grant(
            setup,
            {"refresh_token": "refresh-test"},
            {"account": "test@example.test", "cartella_id": "folder-originale"},
        )
        assert proof["salvato"] and proof["cifrato"] and proof["riletto"]
        raw = await setup[oauth.COLLECTION].find_one({"id": oauth.GRANT_ID})
        assert "refresh-test" not in repr(
            raw
        ) and settings.GOOGLE_CLIENT_SECRET not in repr(raw)
        creds = oauth.credentials_from_grant(raw)
        assert creds.refresh_token == "refresh-test"
        status = await router.status_data(setup)
        assert (
            status["autorizzazione_salvata"]
            and status["redirect_uri"] == settings.GOOGLE_REDIRECT_URI
        )
        assert "refresh-test" not in repr(
            status
        ) and settings.GOOGLE_CLIENT_SECRET not in repr(status)
        raw["refresh_token_encrypted"] = "corrotto"
        with pytest.raises(oauth.DriveOAuthError):
            oauth.credentials_from_grant(raw)

    run(scenario())


def test_callback_completo_salva_solo_dopo_accesso_provato(setup, monkeypatch):
    app = FastAPI()
    app.include_router(router.router)

    async def admin():
        return {"role": "admin"}

    app.dependency_overrides[get_current_admin_user] = admin

    async def exchange(code, pending):
        assert code == "code-test"
        return {"access_token": "access-test", "refresh_token": "refresh-test"}

    monkeypatch.setattr(oauth, "exchange_code", exchange)
    monkeypatch.setattr(
        oauth,
        "inspect_drive",
        lambda c: {"account": "a@test.test", "cartella_id": "folder-originale"},
    )
    c = TestClient(app, base_url="https://impresasemplice.online")
    c.cookies.set("access_token", "sessione-cookie")
    start = c.get("/api/auth/google/connect", follow_redirects=False)
    assert start.status_code == 303
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    done = c.get(
        "/api/auth/google/callback",
        params={"code": "code-test", "state": state},
        follow_redirects=False,
    )
    assert (
        done.status_code == 303 and done.headers["location"] == "/api/auth/google/drive"
    )
    assert "code-test" not in done.text
    assert c.get("/api/auth/google/status").json()["autorizzazione_salvata"]
    assert (
        c.get(
            "/api/auth/google/callback",
            params={"code": "code-test", "state": state},
            follow_redirects=False,
        ).status_code
        == 400
    )


def test_operatore_non_puo_avviare_oauth(setup):
    app = FastAPI()
    app.include_router(router.router)

    async def deny():
        raise HTTPException(403, "solo admin")

    app.dependency_overrides[get_current_admin_user] = deny
    c = TestClient(app)
    assert c.get("/api/auth/google/connect").status_code == 403
    assert c.get("/api/auth/google/status").status_code == 403
    assert c.post("/api/auth/google/verify").status_code == 403


def test_callback_non_logga_codice_e_stato():
    record = logging.LogRecord(
        "uvicorn.access",
        20,
        "x",
        1,
        '%s - "%s %s HTTP/%s" %d',
        (
            "client",
            "GET",
            "/api/auth/google/callback?code=SEGRETO&state=ALTRO",
            "1.1",
            303,
        ),
        None,
    )
    OAuthCallbackRedaction().filter(record)
    assert "SEGRETO" not in record.getMessage() and "ALTRO" not in record.getMessage()


def test_callback_non_accetta_host_arbitrari(setup, monkeypatch):
    monkeypatch.setattr(
        settings, "GOOGLE_REDIRECT_URI", "https://esempio.test/api/auth/google/callback"
    )
    with pytest.raises(oauth.DriveOAuthError):
        oauth.callback_uri()


def test_loader_drive_sceglie_oauth_verificato_prima_del_service_account(
    setup, monkeypatch
):
    from app.services import drive_credential_probe as probe

    creds = object()
    monkeypatch.setattr(oauth, "load_credentials", lambda: creds)
    monkeypatch.setattr(
        probe, "_can_access", lambda c, f: c is creds and f == "folder-originale"
    )
    monkeypatch.setattr(
        probe,
        "_shared_candidate",
        lambda: (_ for _ in ()).throw(AssertionError("service account non necessario")),
    )
    assert probe.load_credentials_for_folder("folder-originale") == (creds, None)


def test_scambio_codice_usa_pkce_e_non_rivela_errori_google(setup, monkeypatch):
    import httpx

    captured = []
    responses = [
        httpx.Response(
            200,
            json={
                "access_token": "access-test",
                "refresh_token": "refresh-test",
                "scope": oauth.SCOPES[0],
            },
        ),
        httpx.Response(400, text="echo-secret-test-privato"),
    ]

    class Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, data):
            captured.append((url, data))
            return responses.pop(0)

    monkeypatch.setattr(oauth.httpx, "AsyncClient", Client)
    pending = {
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "verifier_encrypted": oauth.seal("verifier-test"),
    }
    result = run(oauth.exchange_code("code-test", pending))
    assert result["refresh_token"] == "refresh-test"
    assert captured[0][0] == oauth.TOKEN_URL
    assert captured[0][1]["code_verifier"] == "verifier-test"
    with pytest.raises(oauth.DriveOAuthError) as err:
        run(oauth.exchange_code("code-test", pending))
    assert "echo-secret" not in str(
        err.value
    ) and settings.GOOGLE_CLIENT_SECRET not in str(err.value)


def test_due_processi_consumano_una_sola_autorizzazione(setup):
    import copy
    from tests.runtime.test_supabase_runtime_database import FakeRestSupabase
    from app.services.supabase_runtime_database import ConcurrentDocumentChange

    async def scenario():
        url = await oauth.start_authorization(setup, "sid")
        state = parse_qs(urlparse(url).query)["state"][0]
        doc = await setup[oauth.STATE_COLLECTION].find_one({})
        shared = {oauth.STATE_COLLECTION: {str(doc["_id"]): copy.deepcopy(doc)}}
        gate = asyncio.Event()
        waiting = 0

        class Process(FakeRestSupabase):
            async def _rpc(self, name, payload):
                nonlocal waiting
                if name == "gc_commit_documents":
                    waiting += 1
                    if waiting == 2:
                        gate.set()
                    await asyncio.wait_for(gate.wait(), 5)
                return await super()._rpc(name, payload)

        a, b = Process(), Process()
        a.remote = b.remote = shared
        results = await asyncio.gather(
            oauth.consume_state(a, state, "sid"),
            oauth.consume_state(b, state, "sid"),
            return_exceptions=True,
        )
        assert sum(isinstance(r, dict) for r in results) == 1
        assert sum(isinstance(r, ConcurrentDocumentChange) for r in results) == 1

    run(scenario())


def test_loader_sincrono_rilegge_grant_persistente(setup, monkeypatch):
    import httpx

    run(
        oauth.save_grant(
            setup,
            {"refresh_token": "refresh-test"},
            {"cartella_id": "folder-originale"},
        )
    )
    grant = run(setup[oauth.COLLECTION].find_one({"id": oauth.GRANT_ID}))
    for key, value in {
        "SUPABASE_URL": "https://database.test",
        "SUPABASE_PUBLISHABLE_KEY": "key-test",
        "SUPABASE_RUNTIME_SECRET": "runtime-test",
    }.items():
        monkeypatch.setattr(settings, key, value)

    def post(url, headers, json, timeout):
        assert json["p_collection"] == oauth.COLLECTION
        assert headers["x-gc-api-key"] == "runtime-test"
        return httpx.Response(200, json=[grant], request=httpx.Request("POST", url))

    monkeypatch.setattr(oauth.httpx, "post", post)
    assert oauth.load_credentials().refresh_token == "refresh-test"


def test_collaudo_salva_e_rilegge_solo_nella_cartella_attuale(setup, monkeypatch):
    stored = {}

    class Reply:
        def __init__(self, result):
            self.result = result

        def execute(self):
            return self.result

    class Service:
        def files(self):
            return self

        def create(self, body, media_body, **kwargs):
            assert body["parents"] == ["folder-originale"]
            stored["content"] = media_body.getbytes(0, media_body.size())
            return Reply(
                {
                    "id": "file-test",
                    "name": body["name"],
                    "webViewLink": "https://drive.google.com/file/d/file-test/view",
                }
            )

        def get_media(self, fileId, **kwargs):
            assert fileId == "file-test"
            return Reply(stored["content"])

        def close(self):
            pass

    monkeypatch.setattr(oauth, "build", lambda *a, **kw: Service())
    result = oauth.write_probe(object())
    assert result["salvato"] and result["riletto"] and result["file_id"] == "file-test"
    assert result["sha256"] == hashlib.sha256(stored["content"]).hexdigest()
