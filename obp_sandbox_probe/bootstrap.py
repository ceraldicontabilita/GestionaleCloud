import os
from typing import Any

import httpx

OBP_BASE_URL = os.getenv("OBP_BASE_URL", "https://apisandbox.openbankproject.com").rstrip("/")
OBP_VERSION = os.getenv("OBP_VERSION", "v7.0.0")
REDIRECT_URI = os.getenv(
    "OBP_REDIRECT_URI",
    "https://gestionalecloud-obp-sandbox-probe.onrender.com/callback",
)
DEMO_USERNAME = os.getenv("OBP_DEMO_USERNAME", "katja.fi.29@example.com")
DEMO_PASSWORD = os.getenv("OBP_DEMO_PASSWORD", "ca0317")
MANUAL_CONSUMER_KEY = os.getenv("OBP_CONSUMER_KEY", "")

runtime: dict[str, Any] = {
    "ready": False,
    "public_api": {},
    "oidc": {},
    "client": {},
    "direct_login": {},
    "accounts": {},
    "transactions": {},
}


def sanitized() -> dict[str, Any]:
    return runtime


async def _json_or_text(response: httpx.Response) -> Any:
    try:
        return response.json()
    except Exception:
        return response.text[:2000]


async def bootstrap() -> dict[str, Any]:
    global runtime
    result: dict[str, Any] = {
        "ready": False,
        "public_api": {},
        "oidc": {},
        "client": {},
        "direct_login": {},
        "accounts": {},
        "transactions": {},
    }

    async with httpx.AsyncClient(timeout=25.0, follow_redirects=True) as client:
        # 1) Public API reachability.
        for name, path in {
            "root": f"/obp/{OBP_VERSION}/root",
            "banks": f"/obp/{OBP_VERSION}/banks",
        }.items():
            try:
                r = await client.get(f"{OBP_BASE_URL}{path}")
                result["public_api"][name] = {
                    "ok": r.status_code < 400,
                    "status_code": r.status_code,
                }
            except Exception as exc:
                result["public_api"][name] = {
                    "ok": False,
                    "error": type(exc).__name__,
                    "detail": str(exc),
                }

        # 2) OIDC discovery. Try both paths used by current OBP-OIDC deployments.
        discovery_urls = [
            f"{OBP_BASE_URL}/obp-oidc/.well-known/openid-configuration",
            f"{OBP_BASE_URL}/.well-known/openid-configuration",
        ]
        discovery: dict[str, Any] | None = None
        discovery_url = None
        for url in discovery_urls:
            try:
                r = await client.get(url)
                body = await _json_or_text(r)
                if r.status_code < 400 and isinstance(body, dict) and body.get("token_endpoint"):
                    discovery = body
                    discovery_url = url
                    break
            except Exception:
                pass

        if discovery:
            result["oidc"] = {
                "ok": True,
                "discovery_url": discovery_url,
                "issuer": discovery.get("issuer"),
                "authorization_endpoint": discovery.get("authorization_endpoint"),
                "token_endpoint": discovery.get("token_endpoint"),
                "registration_endpoint": discovery.get("registration_endpoint"),
                "refresh_token_supported": "refresh_token" in (
                    discovery.get("grant_types_supported") or []
                ),
            }
        else:
            result["oidc"] = {
                "ok": False,
                "message": "OIDC discovery not exposed on the public API host; Direct Login fallback will be used if a consumer key is available.",
            }

        # 3) Try RFC 7591 Dynamic Client Registration when advertised.
        consumer_key = MANUAL_CONSUMER_KEY
        if not consumer_key and discovery and discovery.get("registration_endpoint"):
            registration_endpoint = discovery["registration_endpoint"]
            registration_payload = {
                "client_name": "GestionaleCloud OBP Sandbox Probe",
                "redirect_uris": [REDIRECT_URI],
                "grant_types": ["authorization_code", "refresh_token", "client_credentials"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "client_secret_post",
            }
            try:
                r = await client.post(registration_endpoint, json=registration_payload)
                body = await _json_or_text(r)
                if r.status_code < 300 and isinstance(body, dict) and body.get("client_id"):
                    consumer_key = body["client_id"]
                    result["client"] = {
                        "ok": True,
                        "source": "dynamic_registration",
                        "client_id_present": True,
                        "client_secret_present": bool(body.get("client_secret")),
                    }
                    # Keep volatile runtime credentials in private fields for the login route.
                    result["_client_id"] = body["client_id"]
                    result["_client_secret"] = body.get("client_secret", "")
                    result["_authorization_endpoint"] = discovery.get("authorization_endpoint", "")
                    result["_token_endpoint"] = discovery.get("token_endpoint", "")
                else:
                    result["client"] = {
                        "ok": False,
                        "source": "dynamic_registration",
                        "status_code": r.status_code,
                        "response": body,
                    }
            except Exception as exc:
                result["client"] = {
                    "ok": False,
                    "source": "dynamic_registration",
                    "error": type(exc).__name__,
                    "detail": str(exc),
                }
        elif consumer_key:
            result["client"] = {
                "ok": True,
                "source": "environment",
                "client_id_present": True,
            }
        else:
            result["client"] = {
                "ok": False,
                "message": "No dynamic registration endpoint and no OBP_CONSUMER_KEY configured.",
            }

        # 4) Sandbox-only Direct Login using official OBP demo account.
        if consumer_key:
            auth_header = (
                f'DirectLogin username="{DEMO_USERNAME}",'
                f'password="{DEMO_PASSWORD}",'
                f'consumer_key="{consumer_key}"'
            )
            try:
                r = await client.post(
                    f"{OBP_BASE_URL}/my/logins/direct",
                    headers={"Authorization": auth_header, "Accept": "application/json"},
                )
                body = await _json_or_text(r)
                token = body.get("token") if isinstance(body, dict) else None
                result["direct_login"] = {
                    "ok": bool(r.status_code in (200, 201) and token),
                    "status_code": r.status_code,
                    "demo_user": DEMO_USERNAME,
                    "token_present": bool(token),
                }

                if token:
                    result["_direct_token"] = token
                    headers = {"Authorization": f'DirectLogin token="{token}"'}

                    # 5) Read current user + account list.
                    user_r = await client.get(
                        f"{OBP_BASE_URL}/obp/{OBP_VERSION}/users/current",
                        headers=headers,
                    )
                    accounts_r = await client.get(
                        f"{OBP_BASE_URL}/obp/{OBP_VERSION}/my/accounts",
                        headers=headers,
                    )
                    accounts_body = await _json_or_text(accounts_r)
                    account_list = (
                        accounts_body.get("accounts", [])
                        if isinstance(accounts_body, dict)
                        else []
                    )
                    result["accounts"] = {
                        "ok": accounts_r.status_code < 400,
                        "status_code": accounts_r.status_code,
                        "current_user_status": user_r.status_code,
                        "count": len(account_list),
                    }

                    # 6) Read a few transactions from first accessible account.
                    if account_list:
                        account = account_list[0]
                        bank_id = account.get("bank_id")
                        account_id = account.get("id") or account.get("account_id")
                        view_id = "owner"
                        views = account.get("views_available") or []
                        if views:
                            owner = next((v for v in views if v.get("id") == "owner"), None)
                            if owner:
                                view_id = owner.get("id", "owner")
                            elif views[0].get("id"):
                                view_id = views[0]["id"]

                        if bank_id and account_id:
                            tx_r = await client.get(
                                f"{OBP_BASE_URL}/obp/{OBP_VERSION}/banks/{bank_id}/accounts/{account_id}/{view_id}/transactions",
                                headers=headers,
                                params={"limit": 10},
                            )
                            tx_body = await _json_or_text(tx_r)
                            txs = (
                                tx_body.get("transactions", [])
                                if isinstance(tx_body, dict)
                                else []
                            )
                            result["transactions"] = {
                                "ok": tx_r.status_code < 400,
                                "status_code": tx_r.status_code,
                                "count": len(txs),
                                "bank_id": bank_id,
                                "account_id": account_id,
                                "view_id": view_id,
                            }
            except Exception as exc:
                result["direct_login"] = {
                    "ok": False,
                    "error": type(exc).__name__,
                    "detail": str(exc),
                }

    result["ready"] = bool(
        result["public_api"].get("root", {}).get("ok")
        and result["accounts"].get("ok")
    )
    runtime = result
    return result
