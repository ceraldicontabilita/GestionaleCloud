"""La memoria fiscale passa dall'importatore e non dal PUT anagrafico."""
import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.suppliers_module import router
from app.routers.suppliers_module import base
from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.utils.dependencies import get_current_admin_user, get_current_user


def _client(*, admin=False, user=False):
    app = FastAPI()
    app.include_router(router, prefix="/api/suppliers")
    if admin:
        app.dependency_overrides[get_current_admin_user] = lambda: {"role": "admin"}
    elif user:
        app.dependency_overrides[get_current_user] = lambda: {"role": "dipendente"}
    return TestClient(app)


def test_memoria_fiscale_richiede_admin():
    for path, method in (
        ("/api/suppliers/profili-fiscali/memoria", "get"),
        ("/api/suppliers/profili-fiscali/importa", "post"),
    ):
        assert getattr(_client(), method)(path).status_code == 401
        assert getattr(_client(user=True), method)(path).status_code == 403


def test_memoria_scaricabile_e_registrata_prima_del_dettaglio(monkeypatch):
    from app.services import fiscalita_fornitore

    memoria = {"versione": 1, "profili": [{"partita_iva": "01234567890"}]}
    monkeypatch.setattr(fiscalita_fornitore, "carica_memoria", lambda: memoria)
    response = _client(admin=True).get("/api/suppliers/profili-fiscali/memoria")
    assert response.status_code == 200
    assert response.json() == memoria
    assert 'filename="profili_fiscali_fornitori.json"' in response.headers["content-disposition"]
    paths = [route.path for route in router.routes]
    assert paths.index("/profili-fiscali/memoria") < paths.index("/{supplier_id}")
    assert paths.index("/profili-fiscali/importa") < paths.index("/{supplier_id}")


def test_importazione_default_anteprima_e_cache_solo_dopo_applicazione(monkeypatch):
    from app.database import Database
    from app.services import fiscalita_fornitore

    db = object()
    called = []
    cleared = []

    async def importa(database, dry_run=True):
        assert database is db
        called.append(dry_run)
        return {"dry_run": dry_run, "da_aggiornare": 1, "aggiornate": 0 if dry_run else 1}

    async def clear(pattern):
        cleared.append(pattern)

    monkeypatch.setattr(Database, "get_db", classmethod(lambda cls: db))
    monkeypatch.setattr(fiscalita_fornitore, "importa_memoria", importa)
    monkeypatch.setattr(base.cache, "clear_pattern", clear)
    client = _client(admin=True)
    preview = client.post("/api/suppliers/profili-fiscali/importa")
    assert preview.status_code == 200
    assert preview.json()["dry_run"] is True
    assert cleared == []
    applied = client.post("/api/suppliers/profili-fiscali/importa?dry_run=false")
    assert applied.status_code == 200
    assert applied.json()["aggiornate"] == 1
    assert called == [True, False]
    assert cleared == [base.SUPPLIERS_CACHE_KEY]


def test_put_generico_non_sovrascrive_regola_o_fonti_fiscali(monkeypatch):
    async def scenario():
        from app.database import Database

        db = ClientArchivioMemoria()["fiscal_profile_put_guard"]
        originale = {"regola_iva": "noleggio_veicoli", "fonti": [{"url": "https://fonte.test"}]}
        await db["fornitori"].insert_one({
            "id": "s1", "ragione_sociale": "Fornitore", "profilo_fiscale": originale,
        })

        async def clear(_pattern):
            return None

        monkeypatch.setattr(Database, "get_db", classmethod(lambda cls: db))
        monkeypatch.setattr(base.cache, "clear_pattern", clear)
        response = await base.update_supplier("s1", {
            "email": "nuova@example.test",
            "profilo_fiscale": {"regola_iva": "merci_attivita"},
            "profilo_fiscale.regola_iva": "ordinaria",
            "profilo_fiscale_importato_il": "inventato",
        })
        saved = response["supplier"]
        assert saved["email"] == "nuova@example.test"
        assert saved["profilo_fiscale"] == originale
        assert "profilo_fiscale.regola_iva" not in saved
        assert "profilo_fiscale_importato_il" not in saved

    asyncio.run(scenario())
