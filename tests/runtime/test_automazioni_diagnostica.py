from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.routers import admin
from app.utils.dependencies import get_current_user


def test_diagnostica_scheduler_non_avvia_job_ed_e_riservata_all_admin():
    app = FastAPI()
    app.include_router(admin.router, prefix="/api/admin")
    app.dependency_overrides[get_current_user] = lambda: {
        "role": "operator",
        "user_id": "test",
    }
    client = TestClient(app)
    assert client.get("/api/admin/automazioni/stato").status_code == 403
    app.dependency_overrides[get_current_user] = lambda: {
        "role": "admin",
        "user_id": "test",
    }
    from app.scheduler import scheduler

    before = scheduler.running
    response = client.get("/api/admin/automazioni/stato")
    assert response.status_code == 200
    assert response.json()["scheduler_in_esecuzione"] == before
    assert scheduler.running == before
