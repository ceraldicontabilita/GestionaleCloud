"""SumUp — secondo gestore POS accanto a Nexi.

Per ora espone solo la verifica della configurazione: dice se la chiave e'
presente e se SumUp la accetta davvero, senza scaricare nulla e senza
scrivere in contabilita'. La chiave non viene mai restituita in chiaro.
"""
from typing import Any, Dict

import httpx
from fastapi import APIRouter, Depends

from app.config import settings
from app.utils.dependencies import get_current_admin_user
from app.utils.error_handler import handle_errors

router = APIRouter()

TIMEOUT = 20.0


def _mascherata(chiave: str) -> str:
    """Ultime 4 cifre soltanto: serve a riconoscerla, non a riusarla."""
    chiave = (chiave or "").strip()
    return f"...{chiave[-4:]}" if len(chiave) >= 4 else ""


@router.get("/stato")
@handle_errors
async def stato_sumup(
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Verifica che la chiave API sia configurata e accettata da SumUp."""
    chiave = (settings.SUMUP_API_KEY or "").strip()
    merchant = (settings.SUMUP_MERCHANT_CODE or "").strip()

    stato: Dict[str, Any] = {
        "chiave_configurata": bool(chiave),
        "chiave_visibile": _mascherata(chiave),
        "merchant_code": merchant,
        "connessione_ok": False,
        "messaggio": "",
    }

    if not chiave:
        stato["messaggio"] = (
            "Chiave API non configurata: aggiungi SUMUP_API_KEY tra le "
            "variabili d'ambiente e riavvia il servizio."
        )
        return stato
    if not merchant:
        stato["messaggio"] = (
            "Manca SUMUP_MERCHANT_CODE: senza il codice esercente non si "
            "possono leggere le transazioni."
        )
        return stato

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            risposta = await client.get(
                f"{settings.SUMUP_API_BASE}/v0.1/me",
                headers={"Authorization": f"Bearer {chiave}"},
            )
    except httpx.HTTPError as exc:
        stato["messaggio"] = f"SumUp non raggiungibile: {type(exc).__name__}"
        return stato

    if risposta.status_code == 200:
        profilo = risposta.json() or {}
        conto = profilo.get("merchant_profile") or {}
        stato["connessione_ok"] = True
        stato["esercente"] = conto.get("company_name") or profilo.get("account", {}).get("username")
        merchant_reale = conto.get("merchant_code") or ""
        stato["merchant_code_reale"] = merchant_reale
        if merchant_reale and merchant_reale != merchant:
            # Chiave valida ma di un altro conto: leggeremmo le transazioni
            # sbagliate senza accorgercene.
            stato["connessione_ok"] = False
            stato["messaggio"] = (
                f"La chiave appartiene all'esercente {merchant_reale}, "
                f"ma e' configurato {merchant}. Correggi SUMUP_MERCHANT_CODE."
            )
        else:
            stato["messaggio"] = "Connessione a SumUp riuscita."
        return stato

    if risposta.status_code in (401, 403):
        stato["messaggio"] = (
            "SumUp rifiuta la chiave. Verifica di aver copiato la chiave "
            "creata e non la chiave pubblica mostrata in pagina."
        )
    else:
        stato["messaggio"] = f"SumUp ha risposto {risposta.status_code}."
    return stato
