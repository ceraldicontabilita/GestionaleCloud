"""Regressioni sul trasporto cookie/Bearer della dependency JWT canonica."""
import ast
from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from typing import Any, Dict, Optional
import unittest
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1]


class HTTPException(Exception):
    def __init__(self, status_code, detail, headers=None):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.headers = headers


class JWTError(Exception):
    pass


class AuthenticationError(Exception):
    pass


def compile_functions(path, names, namespace):
    nodes = ast.parse((ROOT / path).read_text()).body
    body = [node for node in nodes if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names]
    exec(compile(ast.Module(body=body, type_ignores=[]), str(ROOT / path), "exec"), namespace)


# Compila i corpi originali senza inizializzare database, scheduler o login.
# Il decoder JWT e il registro MFA sono confini esterni: si verifica che
# tutti i trasporti usino quegli stessi controlli, senza fidarsi dello state.
namespace = {
    "Optional": Optional, "Dict": Dict, "Any": Any,
    "Request": SimpleNamespace, "HTTPAuthorizationCredentials": SimpleNamespace,
    "Depends": lambda value: None, "security": None,
    "HTTPException": HTTPException, "JWTError": JWTError,
    "AuthenticationError": AuthenticationError,
    "datetime": datetime, "timezone": timezone,
    "settings": SimpleNamespace(SECRET_KEY="test-key", ALGORITHM="HS256"),
    "logger": logging.getLogger("ceraldi-auth-cookie-test"),
    "status": SimpleNamespace(HTTP_401_UNAUTHORIZED=401, HTTP_403_FORBIDDEN=403,
                              HTTP_428_PRECONDITION_REQUIRED=428),
}
compile_functions("app/utils/dependencies.py", {
    "get_current_user", "get_current_admin_user", "get_current_admin_mfa_user",
}, namespace)

role_namespace = {"ADMIN": "admin", "OPERATORE": "operatore", "SOLA_LETTURA": "sola_lettura",
                  "NON_AUTORIZZATO": "non_autorizzato", "RUOLI_VALIDI": {"admin", "operatore", "sola_lettura"}}
compile_functions("app/utils/ruoli.py", {"normalizza_ruolo"}, role_namespace)
roles = ModuleType("app.utils.ruoli")
roles.normalizza_ruolo = role_namespace["normalizza_ruolo"]
roles.RUOLI_VALIDI = role_namespace["RUOLI_VALIDI"]


def request(cookie=None, authorization=None):
    return SimpleNamespace(
        cookies={"access_token": cookie} if cookie is not None else {},
        headers={"Authorization": authorization} if authorization is not None else {},
        state=SimpleNamespace(user_id="forged-admin", user_role="admin"),
    )


class CookieAuthenticationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tokens = {
            "admin-cookie": {"sub": "admin-01", "role": "admin", "email": "admin@example.test",
                             "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
                             "auth_method": "pin", "mfa_verified": True, "mfa_verified_at": 123,
                             "amr": ["pin", "otp"]},
            "operator-bearer": {"sub": "operator-01", "role": "operatore"},
            "reader-cookie": {"sub": "reader-01", "role": "sola_lettura"},
            "bad-role": {"sub": "whoever", "role": "owner"},
            "empty-sub": {"sub": "", "role": "admin"},
            "expired": {"sub": "admin-01", "role": "admin", "exp": 1},
        }

        def decode(token, key, algorithms):
            if token not in self.tokens:
                raise JWTError("Invalid signature")
            return dict(self.tokens[token])

        self.decoder = Mock(side_effect=decode)
        namespace["jwt"] = SimpleNamespace(decode=self.decoder)
        self.role_patch = patch.dict(sys.modules, {"app.utils.ruoli": roles})
        self.role_patch.start()
        self.addCleanup(self.role_patch.stop)

    async def user(self, req=None, credentials=None):
        return await namespace["get_current_user"](credentials=credentials, request=req)

    async def test_valid_cookie_uses_same_jwt_checks_and_retains_admin_mfa_claims(self):
        user = await self.user(request("admin-cookie"))
        self.decoder.assert_called_once_with("admin-cookie", "test-key", algorithms=["HS256"])
        self.assertEqual(user["user_id"], "admin-01")
        self.assertEqual(user["role"], "admin")
        self.assertTrue(user["mfa_verified"])
        self.assertEqual(user["amr"], ["pin", "otp"])
        self.assertEqual(await namespace["get_current_admin_user"](current_user=user), user)

    async def test_bearer_has_precedence_over_valid_admin_cookie(self):
        user = await self.user(request("admin-cookie", "Bearer operator-bearer"),
                               SimpleNamespace(credentials="operator-bearer"))
        self.assertEqual(user["role"], "operatore")
        self.decoder.assert_called_once_with("operator-bearer", "test-key", algorithms=["HS256"])
        with self.assertRaises(HTTPException) as raised:
            await namespace["get_current_admin_user"](current_user=user)
        self.assertEqual(raised.exception.status_code, 403)

    async def test_invalid_or_empty_bearer_never_falls_back_to_cookie(self):
        for token in ("invalid-signature", ""):
            with self.subTest(token=token):
                self.decoder.reset_mock()
                with self.assertRaises(HTTPException) as raised:
                    await self.user(request("admin-cookie", "Bearer " + token), SimpleNamespace(credentials=token))
                self.assertEqual(raised.exception.status_code, 401)
                self.assertNotIn("admin-cookie", [call.args[0] for call in self.decoder.call_args_list])

    async def test_malformed_authorization_cannot_select_cookie(self):
        for authorization in ("Bearer ", "Basic anything", "invalid"):
            with self.subTest(authorization=authorization):
                with self.assertRaises(HTTPException) as raised:
                    await self.user(request("admin-cookie", authorization))
                self.assertEqual(raised.exception.status_code, 401)
        self.decoder.assert_not_called()

    async def test_no_auth_or_invalid_cookie_never_trusts_forged_request_state(self):
        for cookie in (None, "invalid-signature", "bad-role", "empty-sub", "expired"):
            with self.subTest(cookie=cookie):
                with self.assertRaises(HTTPException) as raised:
                    await self.user(request(cookie))
                self.assertEqual(raised.exception.status_code, 401)

    async def test_direct_credentials_only_call_remains_supported(self):
        user = await namespace["get_current_user"](credentials=SimpleNamespace(credentials="operator-bearer"))
        self.assertEqual(user["user_id"], "operator-01")
        with self.assertRaises(HTTPException) as raised:
            await namespace["get_current_user"](credentials=None)
        self.assertEqual(raised.exception.status_code, 401)

    async def test_reader_cookie_is_authenticated_but_cannot_access_admin(self):
        user = await self.user(request("reader-cookie"))
        self.assertEqual(user["role"], "sola_lettura")
        with self.assertRaises(HTTPException) as raised:
            await namespace["get_current_admin_user"](current_user=user)
        self.assertEqual(raised.exception.status_code, 403)

    async def test_cookie_admin_mfa_still_requires_enrollment_and_verified_session(self):
        user = await self.user(request("admin-cookie"))
        database = ModuleType("app.database")
        database.Database = SimpleNamespace(get_db=lambda: "test-db")
        mfa = ModuleType("app.services.mfa_service")
        mfa.canonical_identity = Mock(return_value="admin-01")
        mfa.is_enabled = AsyncMock(return_value=False)
        with patch.dict(sys.modules, {"app.database": database, "app.services.mfa_service": mfa}):
            with self.assertRaises(HTTPException) as raised:
                await namespace["get_current_admin_mfa_user"](current_user=user)
            self.assertEqual(raised.exception.status_code, 428)
            mfa.is_enabled.return_value = True
            with self.assertRaises(HTTPException) as raised:
                await namespace["get_current_admin_mfa_user"](current_user={**user, "mfa_verified": False})
            self.assertEqual(raised.exception.status_code, 428)
            self.assertEqual(await namespace["get_current_admin_mfa_user"](current_user=user), user)


if __name__ == "__main__":
    unittest.main()
