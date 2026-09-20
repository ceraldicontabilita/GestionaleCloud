"""Contratti di sicurezza del bootstrap Supabase e dell'health check."""
import asyncio
import json

import pytest

from app.config import Settings
from app.database import Database
from app.main import health_check
from app.services.auth_secret import initialize_auth_secret
from app.services.archivio_documenti_memoria import ClientArchivioMemoria


def test_cors_produzione_senza_origin_esplicito_e_chiuso():
    cfg = Settings(
        ENVIRONMENT="production", CORS_ALLOWED_ORIGINS="",
        CORS_ORIGINS="*", ALLOWED_ORIGINS="*", FRONTEND_URL=None,
        ALLOW_CREDENTIALS=True,
    )
    assert cfg.get_cors_origins() == []


def _supabase_ok_kwargs() -> dict:
    return {
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_test",
        "SUPABASE_RUNTIME_SECRET": "runtime-secret-test",
    }


def test_fail_fast_accetta_fallback_cors_same_origin(monkeypatch):
    monkeypatch.setenv("FAIL_FAST_SECRETS", "true")
    cfg = Settings(
        ENVIRONMENT="production", SECRET_KEY="x" * 64,
        CORS_ALLOWED_ORIGINS="", ALLOW_CREDENTIALS=True,
        **_supabase_ok_kwargs(),
    )
    cfg.validate_startup()


def test_fail_fast_rifiuta_cors_wildcard_con_credenziali(monkeypatch):
    monkeypatch.setenv("FAIL_FAST_SECRETS", "true")
    cfg = Settings(
        ENVIRONMENT="production", SECRET_KEY="x" * 64,
        CORS_ALLOWED_ORIGINS="*", ALLOW_CREDENTIALS=True,
        **_supabase_ok_kwargs(),
    )
    with pytest.raises(RuntimeError, match="CORS wildcard"):
        cfg.validate_startup()


def test_fail_fast_rifiuta_backend_non_supabase(monkeypatch):
    """Supabase e' l'unico backend supportato: il vecchio 'sheets' e
    qualunque altro valore restano invalidi."""
    monkeypatch.setenv("FAIL_FAST_SECRETS", "true")
    cfg = Settings(
        ENVIRONMENT="production", SECRET_KEY="x" * 64,
        DATA_BACKEND="sheets", CORS_ALLOWED_ORIGINS="",
    )
    with pytest.raises(RuntimeError, match="DATA_BACKEND non supportato"):
        cfg.validate_startup()


def test_fail_fast_richiede_le_credenziali_supabase(monkeypatch):
    monkeypatch.setenv("FAIL_FAST_SECRETS", "true")
    cfg = Settings(
        ENVIRONMENT="production", SECRET_KEY="x" * 64,
        DATA_BACKEND="supabase", CORS_ALLOWED_ORIGINS="",
        SUPABASE_URL=None, SUPABASE_PUBLISHABLE_KEY=None,
        SUPABASE_RUNTIME_SECRET=None,
    )
    with pytest.raises(RuntimeError, match="DATA_BACKEND=supabase richiede"):
        cfg.validate_startup()


def test_fail_fast_accetta_credenziali_supabase_complete(monkeypatch):
    monkeypatch.setenv("FAIL_FAST_SECRETS", "true")
    cfg = Settings(
        ENVIRONMENT="production", SECRET_KEY="x" * 64,
        DATA_BACKEND="supabase", CORS_ALLOWED_ORIGINS="",
        **_supabase_ok_kwargs(),
    )
    cfg.validate_startup()


def test_health_check_non_dichiara_healthy_senza_database(monkeypatch):
    monkeypatch.setattr(Database, "db", None)
    response = asyncio.run(health_check())
    payload = json.loads(response.body)
    assert response.status_code == 503
    assert payload["status"] == "unhealthy"
    assert payload["database"] == "disconnected"


def test_health_check_verifica_idratazione_generica(monkeypatch):
    """L'health check idrata da qualunque archivio esponga hydration_result;
    qui si usa il document store generico in-memory come doppio di test."""
    database = ClientArchivioMemoria()["health"]
    database.hydration_result = {
        "spreadsheet_id": "SHEET-1",
        "fogli": [{"valide": 2920, "numero_errori": 0}],
    }
    monkeypatch.setattr(Database, "db", database)
    response = asyncio.run(health_check())
    assert response["status"] == "healthy"
    assert response["database"] == "connected"
    assert response["storage"] == "supabase"
    assert response["hydrated_rows"] == 2920
    assert response["hydration_errors"] == 0
    assert response["salari_sync"] == "not_started"


def test_health_check_segnala_righe_escluse_senza_nascondere_i_dati(monkeypatch):
    database = ClientArchivioMemoria()["health_degraded"]
    database.hydration_result = {
        "spreadsheet_id": "SHEET-1",
        "fogli": [{"valide": 100, "numero_errori": 2}],
    }
    monkeypatch.setattr(Database, "db", database)

    response = asyncio.run(health_check())

    assert response["status"] == "degraded"
    assert response["database"] == "connected"
    assert response["hydrated_rows"] == 100
    assert response["hydration_errors"] == 2


def test_health_check_verifica_idratazione_supabase(monkeypatch):
    from app.config import settings
    from app.main import settings as main_settings
    from app.services.supabase_runtime_database import SupabaseRuntimeDatabase

    assert main_settings is settings  # stesso singleton importato da main.py
    monkeypatch.setattr(settings, "DATA_BACKEND", "supabase")

    database = SupabaseRuntimeDatabase("test", {
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_test",
        "SUPABASE_RUNTIME_SECRET": "runtime-secret-test",
    })
    database.hydration_result = {
        "fogli": [{"collezione": "fatture", "valide": 15234, "numero_errori": 0}],
    }
    async def fake_rpc(function_name, payload):
        if function_name == "gc_collection_catalog":
            return [{"collection": "fatture", "row_count": 15234}]
        if function_name == "gc_runtime_health_probe":
            # probe atomica (scrittura + cancellazione in una sola RPC):
            # il health check non deve piu' passare da upsert/delete separati
            assert str(payload["p_probe_id"]).startswith("health:")
            return True
        if function_name in {"gc_fetch_collection", "gc_fetch_collection_after"}:
            return []
        raise AssertionError(function_name)

    monkeypatch.setattr(database, "_rpc", fake_rpc)
    monkeypatch.setattr(Database, "db", database)

    response = asyncio.run(health_check())

    assert response["status"] == "healthy"
    assert response["storage"] == "supabase"
    assert response["hydrated_rows"] == 15234
    assert response["hydration_errors"] == 0


def test_health_check_supabase_prima_dellidratazione_e_unhealthy(monkeypatch):
    from app.config import settings
    from app.services.supabase_runtime_database import SupabaseRuntimeDatabase

    monkeypatch.setattr(settings, "DATA_BACKEND", "supabase")

    database = SupabaseRuntimeDatabase("test", {
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_test",
        "SUPABASE_RUNTIME_SECRET": "runtime-secret-test",
    })
    # hydrate() non e' ancora stato chiamato: hydration_result resta None
    # (attributo reale, non una CollezioneDocumenti delegata da __getattr__).
    monkeypatch.setattr(Database, "db", database)

    response = asyncio.run(health_check())
    payload = json.loads(response.body)

    assert response.status_code == 503
    assert payload["status"] == "unhealthy"
    assert payload["database"] == "unreachable"


def _database_supabase_idratata(monkeypatch):
    from app.config import settings
    from app.services.supabase_runtime_database import SupabaseRuntimeDatabase

    monkeypatch.setattr(settings, "DATA_BACKEND", "supabase")
    database = SupabaseRuntimeDatabase("test", {
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_test",
        "SUPABASE_RUNTIME_SECRET": "runtime-secret-test",
    })
    database.hydration_result = {
        "fogli": [{"collezione": "fatture", "valide": 10, "numero_errori": 0}],
    }

    async def fake_rpc(function_name, payload):
        if function_name == "gc_runtime_health_probe":
            raise RuntimeError(
                "Supabase RPC gc_runtime_health_probe fallita (HTTP 500): "
                "canceling statement due to statement timeout"
            )
        if function_name in {"gc_fetch_collection", "gc_fetch_collection_after"}:
            return []
        raise AssertionError(function_name)

    monkeypatch.setattr(database, "_rpc", fake_rpc)
    monkeypatch.setattr(Database, "db", database)
    return database


def test_health_check_probe_in_timeout_resta_200_degraded(monkeypatch):
    """17/09/2026: Render usa /api/health come health check. Un 503 a ogni
    statement timeout della probe faceva riavviare l'istanza in ciclo
    (sei riavvii in dieci minuti, sito in 502). Processo vivo + catalogo
    verificato = 200, con il guasto dell'archivio dichiarato nel corpo."""
    _database_supabase_idratata(monkeypatch)

    response = asyncio.run(health_check())

    assert not hasattr(response, "status_code")  # dict => HTTP 200
    assert response["status"] == "degraded"
    assert response["database"] == "unreachable"
    assert response["archivio"] == "failed"
    assert "statement timeout" in response["archivio_errore"]
    assert response["hydrated_rows"] == 10


def test_health_check_risponde_entro_il_budget_se_la_probe_resta_appesa(monkeypatch):
    """17/09/2026: Render riavviava l'istanza ogni ~9 minuti (SIGTERM pulito,
    memoria < 1 GB): il suo health check scadeva perche' la probe Supabase
    restava appesa fino allo statement timeout. La liveness ha un budget."""
    import time

    from app import main as main_mod

    database = _database_supabase_idratata(monkeypatch)

    async def probe_lenta():
        await asyncio.sleep(5)
        return {"write_path": "verified"}

    monkeypatch.setattr(database, "health_probe", probe_lenta)
    monkeypatch.setattr(main_mod, "_HEALTH_PROBE_TIMEOUT", 0.05)

    t0 = time.monotonic()
    response = asyncio.run(health_check())
    durata = time.monotonic() - t0

    assert durata < 1.0
    assert not hasattr(response, "status_code")  # 200
    assert response["status"] == "degraded"
    assert response["archivio"] == "failed"
    assert "oltre" in response["archivio_errore"]


def test_health_check_strict_con_probe_in_timeout_e_503(monkeypatch):
    _database_supabase_idratata(monkeypatch)

    response = asyncio.run(health_check(strict=True))
    payload = json.loads(response.body)

    assert response.status_code == 503
    assert payload["status"] == "unhealthy"
    assert payload["archivio"] == "failed"
    assert "statement timeout" in payload["archivio_errore"]


def test_riparazioni_dati_startup_disabilitate_per_default():
    cfg = Settings()
    assert cfg.DATA_BACKEND == "supabase"
    assert cfg.RUN_STARTUP_DATA_REPAIRS is False
    assert cfg.RUN_STARTUP_INDEX_MIGRATIONS is False
    assert cfg.RUN_STARTUP_SEED_DATA is False


def test_settings_non_fa_io_e_bootstrap_secret_e_condiviso():
    cfg_a = Settings(SECRET_KEY=None)
    cfg_b = Settings(SECRET_KEY=None)
    assert cfg_a.auth_secret_source == "ephemeral"
    assert cfg_b.auth_secret_source == "ephemeral"
    db = ClientArchivioMemoria()["auth_bootstrap_test"]
    assert asyncio.run(initialize_auth_secret(db, cfg_a)) == "archivio"
    assert asyncio.run(initialize_auth_secret(db, cfg_b)) == "archivio"
    assert cfg_a.SECRET_KEY == cfg_b.SECRET_KEY
    assert cfg_a.auth_secret_source == "archivio"


def test_secret_esplicito_non_viene_sovrascritto_dall_archivio():
    explicit = "x" * 64
    cfg = Settings(SECRET_KEY=explicit)
    db = ClientArchivioMemoria()["auth_explicit_test"]
    asyncio.run(db["sistema_stato"].insert_one({
        "_id": "auth_secret", "chiave": "auth_secret", "valore": "y" * 64,
    }))
    assert asyncio.run(initialize_auth_secret(db, cfg)) == "configured"
    assert cfg.SECRET_KEY == explicit


def test_runtime_non_ripiega_se_hydrate_fallisce(monkeypatch):
    from app.config import settings

    class BrokenSupabaseRuntime:
        def __init__(self, *_args, **_kwargs):
            pass

        async def hydrate(self):
            raise RuntimeError("registro Supabase non disponibile")

    monkeypatch.setattr(settings, "DATA_BACKEND", "supabase")
    monkeypatch.setattr(
        "app.services.supabase_runtime_database.SupabaseRuntimeDatabase",
        BrokenSupabaseRuntime,
    )
    monkeypatch.setattr(Database, "client", None)
    monkeypatch.setattr(Database, "db", None)
    with pytest.raises(RuntimeError, match="registro Supabase non disponibile"):
        asyncio.run(Database.connect_db())
    assert Database.client is None
    assert Database.db is None


def test_runtime_supabase_avvia_e_chiude_senza_driver_separato(monkeypatch):
    from app.config import settings

    class WorkingSupabaseRuntime:
        instance = None

        def __init__(self, *_args, **_kwargs):
            self.closed = False
            WorkingSupabaseRuntime.instance = self

        async def hydrate(self):
            return {"fogli": []}

        def close(self):
            self.closed = True

    monkeypatch.setattr(settings, "DATA_BACKEND", "supabase")
    monkeypatch.setattr(
        "app.services.supabase_runtime_database.SupabaseRuntimeDatabase",
        WorkingSupabaseRuntime,
    )
    monkeypatch.setattr(Database, "client", None)
    monkeypatch.setattr(Database, "db", None)

    asyncio.run(Database.connect_db())

    runtime = WorkingSupabaseRuntime.instance
    assert Database.client is runtime
    assert Database.db is runtime

    asyncio.run(Database.close_db())
    assert runtime.closed is True
    assert Database.client is None
    assert Database.db is None


def test_health_check_riusa_la_probe_fra_chiamate_ravvicinate(monkeypatch):
    """17/09/2026 (terzo giro): Render chiama /api/health ogni pochi secondi e
    ogni probe e' una scrittura+cancellazione su Supabase (130 in 13 minuti
    a database saturo). Una sola probe per finestra, esito condiviso."""
    from app.config import settings
    from app.services.supabase_runtime_database import SupabaseRuntimeDatabase

    monkeypatch.setattr(settings, "DATA_BACKEND", "supabase")
    database = SupabaseRuntimeDatabase("test", {
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_PUBLISHABLE_KEY": "sb_publishable_test",
        "SUPABASE_RUNTIME_SECRET": "runtime-secret-test",
    })
    database.hydration_result = {"fogli": [{"collezione": "fatture", "valide": 1, "numero_errori": 0}]}
    probe = []

    async def fake_rpc(function_name, payload):
        if function_name == "gc_runtime_health_probe":
            probe.append(payload["p_probe_id"])
            return True
        if function_name in {"gc_fetch_collection", "gc_fetch_collection_after"}:
            return []
        raise AssertionError(function_name)

    monkeypatch.setattr(database, "_rpc", fake_rpc)
    monkeypatch.setattr(Database, "db", database)

    async def scenario():
        prima = await health_check()
        seconda = await health_check()
        terza = await health_check()
        return prima, seconda, terza

    prima, seconda, terza = asyncio.run(scenario())
    assert prima["status"] == seconda["status"] == terza["status"] == "healthy"
    assert len(probe) == 1


def test_health_check_non_lancia_una_seconda_probe_mentre_la_prima_e_appesa(monkeypatch):
    from app import main as main_mod

    database = _database_supabase_idratata(monkeypatch)
    avviate = []

    async def probe_lenta():
        avviate.append(1)
        await asyncio.sleep(0.3)
        return {"write_path": "verified"}

    monkeypatch.setattr(database, "health_probe", probe_lenta)
    monkeypatch.setattr(main_mod, "_HEALTH_PROBE_TIMEOUT", 0.05)

    async def scenario():
        prima = await health_check()
        seconda = await health_check()
        await asyncio.sleep(0.4)
        terza = await health_check()
        return prima, seconda, terza

    prima, seconda, terza = asyncio.run(scenario())
    assert prima["archivio"] == "failed" and "oltre" in prima["archivio_errore"]
    assert seconda["archivio"] == "failed"
    # la probe appesa ha finito: il suo esito viene raccolto, non rilanciata
    assert terza["archivio"] == "verified" and terza["status"] == "healthy"
    assert len(avviate) == 1
