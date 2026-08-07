"""SumUp — secondo circuito POS accanto a Nexi/Numia.

Espone la verifica della configurazione (la chiave non viene mai restituita
in chiaro) e la sincronizzazione delle transazioni, che aggiorna la chiusura
giornaliera del circuito SumUp passando dal motore unico di scrittura.
"""
from datetime import date, timedelta
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException

from app.config import settings
from app.database import Database
from app.services import sumup_sync
from app.utils.dependencies import get_current_admin_user, get_current_user
from app.utils.error_handler import handle_errors

router = APIRouter()

TIMEOUT = 20.0
# Recupero prudente: SumUp puo' consolidare una transazione con qualche ora di
# ritardo, quindi la sincronizzazione automatica rilegge anche il giorno prima.
GIORNI_RECUPERO = 1


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


def _intervallo_predefinito() -> tuple:
    """Ieri e oggi: copre la giornata in corso e rilegge quella appena chiusa."""
    oggi = date.today()
    return (oggi - timedelta(days=GIORNI_RECUPERO)).isoformat(), oggi.isoformat()


@router.post("/sincronizza")
@handle_errors
async def sincronizza_sumup(
    payload: Optional[Dict[str, Any]] = Body(None),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Scarica le transazioni SumUp e riallinea le chiusure del circuito.

    E' idempotente: rieseguirla sullo stesso intervallo non duplica ne'
    transazioni ne' movimenti di Prima Nota. Non crea ricavi — il ricavo e'
    gia' quello del corrispettivo XML, qui si stabilisce solo quanta parte
    e' passata dal terminale SumUp.
    """
    payload = payload or {}
    dal_predefinito, al_predefinito = _intervallo_predefinito()
    dal = str(payload.get("dal") or dal_predefinito)[:10]
    al = str(payload.get("al") or al_predefinito)[:10]
    for etichetta, valore in (("dal", dal), ("al", al)):
        try:
            date.fromisoformat(valore)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Data '{etichetta}' non valida: {valore!r} (attesa AAAA-MM-GG)",
            )
    if dal > al:
        raise HTTPException(status_code=400, detail="'dal' successivo ad 'al'")

    try:
        esito = await sumup_sync.sincronizza(
            Database.get_db(), dal, al, actor=current_user
        )
    except sumup_sync.SumUpNonConfigurato as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"SumUp non raggiungibile: {type(exc).__name__}",
        ) from exc

    giornate = esito.get("giornate") or []
    esito["message"] = (
        f"SumUp sincronizzato dal {dal} al {al}: {len(giornate)} giornate, "
        f"EUR {esito.get('totale_netto', 0):.2f} netti."
    )
    return esito


@router.get("/bonifica-pos-xml")
@handle_errors
async def analizza_bonifica_pos_xml(
    anno: Optional[int] = None,
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Quante righe POS in Prima Nota derivano dall'XML. Sola lettura."""
    from app.services import bonifica_pos_xml

    return await bonifica_pos_xml.analizza(Database.get_db(), anno)


@router.post("/bonifica-pos-xml")
@handle_errors
async def applica_bonifica_pos_xml(
    payload: Optional[Dict[str, Any]] = Body(None),
    admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Marca come non attendibili le righe POS ricavate dall'XML.

    Non cancella nulla: sono scritture reali gia' in Prima Nota. Le
    riclassifica e riporta in attesa le giornate senza dato del terminale,
    che verranno corrette dalla chiusura reale o dall'API.

    Va confermata esplicitamente con ``{"conferma": true}``: tocca la
    contabilita' esistente e non deve poter partire per sbaglio.
    """
    from app.services import bonifica_pos_xml

    payload = payload or {}
    if payload.get("conferma") is not True:
        raise HTTPException(
            status_code=400,
            detail="Serve {\"conferma\": true}: la bonifica modifica righe di "
                   "Prima Nota gia' registrate. Usa prima la GET per vedere "
                   "quante sono.",
        )
    return await bonifica_pos_xml.applica(
        Database.get_db(), payload.get("anno"), actor=admin
    )


@router.post("/normalizza-descrizioni-pos")
@handle_errors
async def normalizza_descrizioni_pos(
    payload: Optional[Dict[str, Any]] = Body(None),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Porta le descrizioni storiche in formato italiano (gg/mm/aaaa).

    Correzione di sola forma: cambia il testo che si legge in Prima Nota, mai
    importi, date o fonti. Senza ``{"conferma": true}`` restituisce solo
    l'anteprima di cosa cambierebbe.
    """
    from app.services import bonifica_pos_xml

    payload = payload or {}
    return await bonifica_pos_xml.normalizza_descrizioni(
        Database.get_db(), payload.get("anno"),
        applica=payload.get("conferma") is True,
    )
