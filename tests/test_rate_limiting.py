"""Rate limiting (audit sicurezza 19/07/2026, commento in app/main.py):
il Limiter era istanziato ma senza SlowAPIMiddleware default_limits non
veniva mai applicato — nessun endpoint aveva un limite di richieste reale.
Prima di questo file, zero test verificavano che il rate limiting fosse
davvero montato e davvero bloccasse."""
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address


def test_slowapi_middleware_montato_su_app_reale():
    """Verifica di presenza sull'app reale (stessa logica di
    test_middleware_montato_in_app per AuthenticationMiddleware): senza
    questo middleware, default_limits del Limiter è carta straccia."""
    import app.main as main_mod
    stack = [m.cls.__name__ for m in main_mod.app.user_middleware]
    assert "SlowAPIMiddleware" in stack, (
        "SlowAPIMiddleware NON è montato: il rate limiting non viene mai applicato"
    )


def _app_con_stesso_limite_di_produzione():
    """App minima isolata (nessun DB, nessun lifespan) con la STESSA
    configurazione di rate limiting usata in app/main.py (200/minute),
    per verificare dal vivo che il limite scatti davvero, senza pagare il
    costo/rischio di avviare l'app completa con connessione Mongo."""
    app = FastAPI()
    limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    @app.get("/ping")
    async def ping():
        return {"pong": True}

    return app


def test_rate_limit_scatta_oltre_la_soglia():
    """Con limite 200/minute, la 201ª richiesta dallo stesso client nello
    stesso minuto deve ricevere 429, non 200."""
    app = _app_con_stesso_limite_di_produzione()
    client = TestClient(app)

    status_codes = [client.get("/ping").status_code for _ in range(205)]

    assert status_codes[:200] == [200] * 200, "le prime 200 richieste devono passare"
    assert 429 in status_codes[200:], (
        f"nessun 429 tra le richieste 201-205: {status_codes[200:]} "
        "— il rate limiting non sta bloccando nulla"
    )
