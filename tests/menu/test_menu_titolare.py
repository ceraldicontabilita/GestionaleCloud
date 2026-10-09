"""L'informativa del menu clienti legge il titolare dall'anagrafica azienda
unica (`app/lotti/azienda.py`): nessun dato scritto a mano nel frontend."""
import asyncio

from app.menu.routes import menu_routes


def test_titolare_dall_anagrafica_azienda(monkeypatch):
    import app.lotti.azienda as azienda

    async def finta():
        return {"ragione_sociale": "Prova S.r.l.", "indirizzo": "Via Uno 1", "partita_iva": "01234567890",
                "email": "", "telefono": "081", "codice_destinatario": "SEGRETO", "responsabile_haccp": "X"}

    monkeypatch.setattr(azienda, "get_azienda", finta)
    dati = asyncio.run(menu_routes.titolare_del_trattamento())
    assert dati == {"ragione_sociale": "Prova S.r.l.", "indirizzo": "Via Uno 1",
                    "partita_iva": "01234567890", "email": "", "telefono": "081"}


def test_rotta_pubblica_registrata():
    assert any(getattr(r, "path", "") == "/api/menu/titolare" for r in menu_routes.router.routes)
