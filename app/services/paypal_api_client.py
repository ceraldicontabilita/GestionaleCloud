"""
Client API PayPal Reporting (OAuth2 client_credentials).
Docs: https://developer.paypal.com/docs/api/transaction-search/v1/
"""
import httpx
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
from app.config import settings

logger = logging.getLogger(__name__)
PAYPAL_BASE = "https://api.paypal.com"


class PayPalAPIClient:
    def __init__(self):
        self._token: Optional[str] = None
        self._expires: Optional[datetime] = None

    async def _ensure_token(self):
        if self._token and self._expires and datetime.now(timezone.utc) < self._expires:
            return
        if not settings.PAYPAL_CLIENT_ID or not settings.PAYPAL_CLIENT_SECRET:
            raise RuntimeError("PAYPAL_CLIENT_ID/SECRET mancanti in .env")
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{PAYPAL_BASE}/v1/oauth2/token",
                auth=(settings.PAYPAL_CLIENT_ID, settings.PAYPAL_CLIENT_SECRET),
                headers={"Accept": "application/json"},
                data={"grant_type": "client_credentials"},
            )
            resp.raise_for_status()
            d = resp.json()
            self._token = d["access_token"]
            self._expires = datetime.now(timezone.utc) + timedelta(seconds=int(d["expires_in"]) - 60)
            logger.info("Token PayPal rinnovato, scade %s", self._expires.isoformat())

    async def list_transactions(
        self, start: datetime, end: datetime,
        transaction_status: str = "S", page_size: int = 500,
    ) -> List[Dict[str, Any]]:
        await self._ensure_token()
        out: List[Dict[str, Any]] = []
        page = 1
        async with httpx.AsyncClient(timeout=60) as client:
            while True:
                resp = await client.get(
                    f"{PAYPAL_BASE}/v1/reporting/transactions",
                    headers={"Authorization": f"Bearer {self._token}"},
                    params={
                        "start_date": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "end_date": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "transaction_status": transaction_status,
                        "page": page,
                        "page_size": page_size,
                        "fields": "all",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                out.extend(data.get("transaction_details", []))
                total_pages = data.get("total_pages", 1)
                if page >= total_pages:
                    break
                page += 1
        return out

    async def sync_period(self, start: datetime, end: datetime) -> List[Dict[str, Any]]:
        result = []
        cursor = start
        while cursor < end:
            window_end = min(cursor + timedelta(days=30), end)
            result.extend(await self.list_transactions(cursor, window_end))
            cursor = window_end + timedelta(seconds=1)
        return result


paypal_client = PayPalAPIClient()
