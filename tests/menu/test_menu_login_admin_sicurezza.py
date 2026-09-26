"""Menu: un solo ingresso amministrativo, derivato dalla sessione ERP."""

from fastapi import HTTPException

from app.menu.routes import qrcode_routes


def test_non_esiste_login_pin_autonomo() -> None:
    percorsi = {(route.path, tuple(route.methods or ())) for route in qrcode_routes.router.routes}
    assert not any(path == "/api/qrcode/login" for path, _methods in percorsi)
    assert any(path == "/api/qrcode/session" and "GET" in methods for path, methods in percorsi)


def test_token_malformato_risponde_401_non_500(monkeypatch) -> None:
    """PyJWT solleva InvalidTokenError, non JWTError (python-jose)."""
    import jwt as _jwt

    assert not hasattr(_jwt, "JWTError"), "PyJWT non espone JWTError"
    monkeypatch.setattr(qrcode_routes, "SECRET_KEY", "segreto-di-prova")

    import asyncio

    try:
        asyncio.run(qrcode_routes.verify_token("Bearer non-e-un-token"))
    except HTTPException as exc:
        assert exc.status_code == 401
    else:  # pragma: no cover
        raise AssertionError("un token malformato deve dare 401")
