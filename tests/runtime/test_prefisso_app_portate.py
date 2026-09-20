"""Guardia: `/lotti`, `/menu` e `/hr` aprono la loro app, non il gestionale.

Verificato in produzione il 20/09/2026: tutti e tre i prefissi **nudi**
rispondevano 200 servendo `<title>Ceraldi ERP</title>`, cioe' la SPA dell'ERP.
Solo con la barra finale (`/lotti/`) si arrivava davvero a Lotti.

La causa non e' l'ordine dei mount, che e' corretto: Starlette compila
`Mount("/lotti")` nella regex `^/lotti/(?P<path>.*)$`, che **richiede** la
barra. Il prefisso nudo non trova quindi nessun mount, e viene raccolto dal
catch-all `/{full_path:path}` della SPA dell'ERP. Nemmeno il `redirect_slashes`
di Starlette puo' salvarlo: quella rete scatta solo quando NESSUNA rotta
corrisponde, e il catch-all corrisponde sempre.

Per il titolare il sintomo era: «apro /lotti e mi ritrovo nel gestionale».
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app

PREFISSI = ("lotti", "menu", "hr")


@pytest.fixture(scope="module")
def client():
    # Nessuno startup: interessa solo la tabella delle rotte.
    with TestClient(app, follow_redirects=False) as _client:
        yield _client


@pytest.mark.parametrize("prefisso", PREFISSI)
def test_il_prefisso_nudo_rimanda_alla_app_portata(prefisso):
    risposta = TestClient(app, follow_redirects=False).get(f"/{prefisso}")
    assert risposta.status_code == 307, (
        f"/{prefisso} ha risposto {risposta.status_code} invece di rimandare a "
        f"/{prefisso}/: senza il redirect la richiesta cade nel catch-all della "
        "SPA dell'ERP e l'utente vede il gestionale al posto della sua app."
    )
    assert risposta.headers["location"] == f"/{prefisso}/"


@pytest.mark.parametrize("prefisso", PREFISSI)
def test_il_redirect_conserva_la_query(prefisso):
    """`/menu?x=1` deve restare `/menu/?x=1`.

    Un redirect che butta la query perde i parametri del link con cui l'utente
    e' arrivato, e la pagina di destinazione non li trova piu'.
    """
    risposta = TestClient(app, follow_redirects=False).get(
        f"/{prefisso}?tavolo=7&lang=it"
    )

    assert risposta.headers["location"] == f"/{prefisso}/?tavolo=7&lang=it"


@pytest.mark.parametrize("prefisso", PREFISSI)
def test_il_prefisso_nudo_non_serve_la_spa_dell_erp(prefisso):
    """Il controllo che descrive il guasto vero, non il suo rimedio.

    Se domani qualcuno togliesse il redirect e rimettesse il catch-all davanti,
    il test sopra si potrebbe soddisfare con un 307 verso un posto qualsiasi:
    questo invece guarda cosa riceve l'utente.
    """
    risposta = TestClient(app).get(f"/{prefisso}")  # segue i redirect
    corpo = risposta.text[:4000]

    assert "<title>Ceraldi ERP</title>" not in corpo, (
        f"/{prefisso} serve ancora la SPA del gestionale. Chi apre "
        f"gestionalecloud.onrender.com/{prefisso} deve trovare la sua app."
    )


def test_le_api_delle_app_portate_non_passano_dal_redirect():
    """Il redirect vale per il prefisso nudo, non per le rotte sotto di esso.

    `/lotti/api/health` deve continuare a essere servita dal mount: se il
    redirect la intercettasse, ogni chiamata API dell'app portata farebbe un
    giro in piu' e le POST perderebbero il corpo.
    """
    risposta = TestClient(app, follow_redirects=False).get("/lotti/api/health")

    assert risposta.status_code != 307, (
        "Il redirect del prefisso nudo sta intercettando anche le rotte figlie."
    )
