"""Colazioni B&B: il titolare entra con la sessione del gestionale.

L'app Colazioni B&B (`/convenzioni/`, pagina statica) parla con Supabase solo
tramite funzioni RPC `bb_*`. Per il titolare non esiste un PIN separato: chi e'
gia' entrato nel gestionale (PIN amministratore `PIN_HASH_ADMIN`, con MFA se
attiva) chiede qui un token di sessione. Il token lo emette il database, dietro
la stessa chiave di runtime `x-gc-api-key` che protegge le altre RPC del
gruppo (`gc_assert_runtime_secret`): senza quella chiave, che ha solo questo
backend, `bb_tit_sessione_apri` risponde «accesso negato».

Il PIN degli albergatori, invece, e' loro: lo scelgono con l'invito e lo
recuperano con il codice di recupero (vedi CLAUDE.md, «Colazioni B&B»).
"""
import asyncio
import logging
import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Mapping, Optional
from urllib.parse import urlsplit

import aiohttp
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.config import settings
from app.lotti.servizi.catalogo_acquaviva_hotel import (
    descrizione_breve as descrizione_breve_acquaviva,
    digest_identita,
    identita_riga,
    presentazione_fattura,
)
from app.services.colazioni_ordini_notifiche import avvisa_in_background
from app.utils.dependencies import get_current_admin_user

logger = logging.getLogger(__name__)

router = APIRouter()

ORE_SESSIONE = 12

_FORNITORE_VANDEMOORTELE = re.compile(r"vand(?:e)?moo?rte?le|vandermortel", re.IGNORECASE)
_RIGA_FATTURA_NON_PRODOTTO = re.compile(
    r"\b(?:LIQUIDAZ(?:IONE)?|SCONTO|ABBUONO|CONTRIBUTO)\b", re.IGNORECASE
)
class RigaOrdineHotel(BaseModel):
    chiave: str = Field(min_length=1, max_length=180)
    quantita: int = Field(ge=1, le=200)


class OrdineHotelRequest(BaseModel):
    sid: str = Field(min_length=1, max_length=80)
    p: str = Field(min_length=1, max_length=300)
    data_consegna: date
    ora_ritiro: str = Field(min_length=4, max_length=5)
    pagamento_metodo: str = Field(default="in_loco", max_length=20)
    righe: List[RigaOrdineHotel]
    nota: str = Field(default="", max_length=500)
    idempotenza: str = Field(default="", max_length=80)


class ElencoOrdiniHotelRequest(BaseModel):
    sid: str = Field(min_length=1, max_length=80)
    p: str = Field(min_length=1, max_length=300)


class RicaricaSumUpRequest(ElencoOrdiniHotelRequest):
    importo: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    idempotenza: str = Field(min_length=8, max_length=80)


class AggiornaOrdineHotelRequest(BaseModel):
    stato: Optional[str] = None
    pagamento: Optional[str] = None


class ProdottoAcquavivaRequest(BaseModel):
    prodotto_id: int = Field(gt=0)
    attivo: bool


class MenuOspiteRequest(BaseModel):
    codice: str = Field(min_length=4, max_length=80)
    giorno: date


class RigaMenuOspite(BaseModel):
    prodotto_id: int = Field(gt=0)
    quantita: int = Field(ge=1, le=20)


class OrdineMenuOspiteRequest(MenuOspiteRequest):
    righe: List[RigaMenuOspite] = Field(max_length=40)


def _testo_normalizzato(valore: Any) -> str:
    testo = unicodedata.normalize("NFKD", str(valore or ""))
    testo = "".join(c for c in testo if not unicodedata.combining(c))
    return " ".join(re.findall(r"[A-Z0-9]+", testo.upper()))


def _decimale_positivo(valore: Any) -> Optional[Decimal]:
    try:
        numero = Decimal(str(valore or "0"))
    except (InvalidOperation, ValueError):
        return None
    return numero if numero > 0 else None


def costruisci_catalogo_prodotti_hotel(
    fatture: Iterable[Mapping[str, Any]],
    prodotti_vendita: Iterable[Mapping[str, Any]],
    prodotti_acquaviva: Iterable[Mapping[str, Any]] = (),
) -> List[Dict[str, Any]]:
    """Catalogo verificabile per gli hotel, senza modificare i dati sorgente."""

    prodotti = [p for p in prodotti_vendita if p.get("attivo", True)]
    catalogo_acquaviva = [p for p in prodotti_acquaviva if p.get("attivo", True)]
    fonti_collegabili = [*prodotti, *catalogo_acquaviva]
    risultato: List[Dict[str, Any]] = []

    # Tutto cio' che produciamo: il legame alla ricetta e' la prova, non il nome.
    for prodotto in prodotti:
        if not prodotto.get("ricetta_id"):
            continue
        nome = str(prodotto.get("nome") or "").strip()
        if not nome:
            continue
        risultato.append(
            {
                "chiave": f"interno:{prodotto.get('id')}",
                "origine": "produzione_interna",
                "nome": nome,
                "descrizione": str(prodotto.get("descrizione") or "").strip(),
                "allergeni": list(prodotto.get("allergeni") or []),
                "immagine": prodotto.get("immagine_url") or None,
                "prezzo": _decimale_positivo(prodotto.get("prezzo_vendita")),
                "categoria": str(prodotto.get("categoria") or "Produzione interna").strip()
                or "Produzione interna",
                "prova": "ricetta",
            }
        )

    # Vandemoortele: una riga entra soltanto se compare davvero in fattura.
    acquistati: Dict[str, Dict[str, Any]] = {}
    for fattura in fatture:
        fornitore = " ".join(
            str(fattura.get(campo) or "")
            for campo in ("fornitore", "fornitore_ragione_sociale", "supplier_name")
        )
        if not _FORNITORE_VANDEMOORTELE.search(fornitore):
            continue
        for riga in fattura.get("prodotti") or []:
            descrizione = str(
                riga.get("descrizione") or riga.get("description") or riga.get("nome") or ""
            ).strip()
            if (
                not descrizione
                or _RIGA_FATTURA_NON_PRODOTTO.search(descrizione)
                or not _decimale_positivo(riga.get("quantita"))
            ):
                continue
            identita = _testo_normalizzato(descrizione)
            if not identita:
                continue
            voce = acquistati.setdefault(
                identita,
                {
                    "descrizione_fattura": descrizione,
                    "quantita": Decimal("0"),
                    "riga": riga,
                },
            )
            voce["quantita"] += _decimale_positivo(riga.get("quantita")) or Decimal("0")

    referenze: Dict[str, Dict[str, Any]] = {}
    for _identita_fattura, voce in acquistati.items():
        riga = voce["riga"]
        identita, collegato = identita_riga(
            voce["descrizione_fattura"], riga, fonti_collegabili
        )
        aggregata = referenze.setdefault(
            identita,
            {
                "quantita": Decimal("0"),
                "descrizioni_fattura": [],
                "righe": [],
                "collegato": collegato,
            },
        )
        aggregata["quantita"] += voce["quantita"]
        aggregata["righe"].append(riga)
        if voce["descrizione_fattura"] not in aggregata["descrizioni_fattura"]:
            aggregata["descrizioni_fattura"].append(voce["descrizione_fattura"])

    for identita, voce in referenze.items():
        collegato = voce["collegato"]
        descrizioni_fattura = voce["descrizioni_fattura"]
        descrizione_fattura = descrizioni_fattura[0]
        nome_fattura, descrizione_fallback = presentazione_fattura(descrizione_fattura)
        nome = str(
            (collegato or {}).get("nome_verificato")
            or (collegato or {}).get("nome_display")
            or (collegato or {}).get("nome")
            or nome_fattura
        ).strip()
        descrizione = (
            descrizione_breve_acquaviva(collegato)
            if collegato
            else descrizione_fallback
        )
        digest = digest_identita(identita)
        risultato.append(
            {
                "chiave": f"vandemoortele:{digest}",
                "origine": "vandemoortele",
                "nome": nome,
                "descrizione": descrizione,
                "allergeni": list((collegato or {}).get("allergeni") or []),
                "immagine": (
                    (collegato or {}).get("immagine_prodotto")
                    or (collegato or {}).get("immagine_url")
                    or (collegato or {}).get("foto_url")
                    or None
                ),
                "prezzo": _decimale_positivo((collegato or {}).get("prezzo_vendita")),
                "categoria": str(
                    (collegato or {}).get("categoria")
                    or (collegato or {}).get("categoria_aqv")
                    or "Acquaviva"
                ).strip() or "Acquaviva",
                "prova": "fattura",
                "descrizione_fattura": descrizione_fattura,
                "descrizioni_fattura": descrizioni_fattura,
                "quantita_acquistata": voce["quantita"],
                "collegamento_catalogo": bool(collegato),
                "fonte_catalogo": (collegato or {}).get("link_prodotto") or None,
            }
        )

    ordine_origine = {"vandemoortele": 0, "produzione_interna": 1}
    return sorted(
        risultato,
        key=lambda p: (
            ordine_origine.get(p["origine"], 9),
            _testo_normalizzato(p.get("categoria")),
            _testo_normalizzato(p["nome"]),
        ),
    )


async def _apri_sessione_supabase() -> Dict[str, Any]:
    url = (settings.SUPABASE_URL or "").strip().rstrip("/")
    chiave = (settings.SUPABASE_PUBLISHABLE_KEY or "").strip()
    segreto = (settings.SUPABASE_RUNTIME_SECRET or "").strip()
    if not (url and chiave and segreto):
        raise HTTPException(status_code=503, detail="Supabase non configurato sul server")
    intestazioni = {
        "apikey": chiave,
        "x-gc-api-key": segreto,
        "Content-Type": "application/json",
    }
    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=20), headers=intestazioni
        ) as sessione:
            async with sessione.post(
                f"{url}/rest/v1/rpc/bb_tit_sessione_apri", json={"pore": ORE_SESSIONE}
            ) as risposta:
                corpo = await risposta.json(content_type=None)
                if risposta.status >= 400:
                    logger.error("bb_tit_sessione_apri: %s %s", risposta.status, str(corpo)[:200])
                    raise HTTPException(status_code=502, detail="Colazioni B&B non raggiungibile")
                return corpo
    except aiohttp.ClientError as exc:
        logger.error("bb_tit_sessione_apri: %s", exc)
        raise HTTPException(status_code=502, detail="Colazioni B&B non raggiungibile") from exc


@router.post("/accesso", summary="Sessione del titolare per Colazioni B&B")
async def accesso_titolare(_admin: Dict[str, Any] = Depends(get_current_admin_user)) -> Dict[str, Any]:
    """Token per le RPC del titolare: vale 12 ore ed e' emesso solo a un admin."""
    esito = await _apri_sessione_supabase()
    token = esito.get("token") if isinstance(esito, dict) else None
    if not token:
        raise HTTPException(status_code=502, detail="Colazioni B&B non raggiungibile")
    return {"token": token, "scade": esito.get("scade")}


@router.get("/catalogo-prodotti", summary="Prodotti verificati per i menu degli hotel")
async def catalogo_prodotti_hotel(
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Prodotti acquistati da Vandemoortele e prodotti delle ricette interne.

    La rotta e' amministrativa: descrizioni, foto e allergeni arrivano dalle
    fonti canoniche di Lotti, mentre la prova di acquisto resta la fattura.
    Non assegna prezzi e non pubblica nulla: la scelta per struttura viene
    salvata dalle RPC ``bb_tit_prodotti_*``.
    """

    from app.lotti.db import database as db

    fatture = await db.fatture.find(
        {
            "$or": [
                {"fornitore": {"$regex": "vandemoortele|vandermoortel|vandermortel", "$options": "i"}},
                {
                    "fornitore_ragione_sociale": {
                        "$regex": "vandemoortele|vandermoortel|vandermortel",
                        "$options": "i",
                    }
                },
            ]
        },
        {
            "_id": 0,
            "fornitore": 1,
            "fornitore_ragione_sociale": 1,
            "prodotti": 1,
            "data_fattura": 1,
            "numero_fattura": 1,
        },
    ).to_list(500)
    prodotti = await db.prodotti_vendita.find(
        {"attivo": True},
        {
            "_id": 0,
            "id": 1,
            "nome": 1,
            "descrizione": 1,
            "categoria": 1,
            "ricetta_id": 1,
            "fonte": 1,
            "allergeni": 1,
            "immagine_url": 1,
            "prezzo_vendita": 1,
            "codice_prodotto": 1,
            "codice_articolo": 1,
            "codice_aqv_2026": 1,
            "codice_aqv_2025": 1,
            "acquaviva_id": 1,
            "attivo": 1,
        },
    ).to_list(2000)
    prodotti_acquaviva = await db.acquaviva_prodotti.find(
        {"fonte": {"$in": ["acquaviva", "vandemoortele"]}, "attivo": {"$ne": False}},
        {
            "_id": 0,
            "id": 1,
            "nome": 1,
            "nome_display": 1,
            "nome_verificato": 1,
            "descrizione": 1,
            "descrizione_breve": 1,
            "descrizione_lunga": 1,
            "categoria": 1,
            "categoria_aqv": 1,
            "allergeni": 1,
            "allergeni_fonte": 1,
            "immagine_url": 1,
            "immagine_prodotto": 1,
            "foto_url": 1,
            "link_prodotto": 1,
            "prezzo_vendita": 1,
            "codice": 1,
            "codice_articolo": 1,
            "codice_aqv_2026": 1,
            "codice_aqv_2025": 1,
            "codici_alias": 1,
            "alias_fattura": 1,
            "attivo": 1,
        },
    ).to_list(5000)
    catalogo = costruisci_catalogo_prodotti_hotel(
        fatture, prodotti, prodotti_acquaviva
    )
    return {
        "prodotti": catalogo,
        "totale": len(catalogo),
        "vandemoortele": sum(p["origine"] == "vandemoortele" for p in catalogo),
        "produzione_interna": sum(p["origine"] == "produzione_interna" for p in catalogo),
    }


async def _rpc_bb(fn: str, args: Mapping[str, Any]) -> Any:
    """Chiama una RPC bb_* dal backend senza esporre segreti applicativi."""
    url = (settings.SUPABASE_URL or "").strip().rstrip("/")
    chiave = (settings.SUPABASE_PUBLISHABLE_KEY or "").strip()
    if not (url and chiave):
        raise HTTPException(status_code=503, detail="Colazioni B&B non configurato")
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as sessione:
            async with sessione.post(
                f"{url}/rest/v1/rpc/{fn}",
                json=dict(args),
                headers={"apikey": chiave, "Authorization": f"Bearer {chiave}",
                         "Content-Type": "application/json"},
            ) as risposta:
                corpo = await risposta.json(content_type=None)
                if risposta.status >= 400:
                    logger.warning("%s rifiutata: HTTP %s", fn, risposta.status)
                    raise HTTPException(status_code=401, detail="Sessione albergatore non valida")
                return corpo
    except aiohttp.ClientError as exc:
        logger.error("%s non raggiungibile: %s", fn, exc)
        raise HTTPException(status_code=502, detail="Colazioni B&B non raggiungibile") from exc


async def _rpc_runtime_bb(fn: str, args: Mapping[str, Any]) -> Any:
    """RPC riservata al backend, protetta dal segreto di runtime."""
    url = (settings.SUPABASE_URL or "").strip().rstrip("/")
    chiave = (settings.SUPABASE_PUBLISHABLE_KEY or "").strip()
    segreto = (settings.SUPABASE_RUNTIME_SECRET or "").strip()
    if not (url and chiave and segreto):
        raise HTTPException(status_code=503, detail="Portafoglio hotel non configurato")
    headers = {
        "apikey": chiave,
        "x-gc-api-key": segreto,
        "Content-Type": "application/json",
    }
    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=20), headers=headers
        ) as sessione:
            async with sessione.post(
                f"{url}/rest/v1/rpc/{fn}", json=dict(args)
            ) as risposta:
                corpo = await risposta.json(content_type=None)
                if risposta.status >= 400:
                    logger.error("%s: HTTP %s", fn, risposta.status)
                    raise HTTPException(status_code=502, detail="Portafoglio hotel non raggiungibile")
                return corpo
    except aiohttp.ClientError as exc:
        logger.error("%s non raggiungibile: %s", fn, exc)
        raise HTTPException(status_code=502, detail="Portafoglio hotel non raggiungibile") from exc


def _url_ricariche() -> tuple[str, str]:
    pubblica = (settings.COLAZIONI_PUBLIC_URL or "").strip()
    parti = urlsplit(pubblica)
    if parti.scheme != "https" or not parti.netloc:
        raise HTTPException(status_code=503, detail="Indirizzo pubblico colazioni non configurato")
    origine = f"{parti.scheme}://{parti.netloc}"
    return (
        f"{origine}/convenzioni/#/albergatore/borsellino",
        f"{origine}/api/colazioni/ricariche/sumup/webhook",
    )


async def _applica_checkout_sumup(checkout_id: str) -> Dict[str, Any]:
    from app.services.colazioni_sumup import leggi_checkout

    esito = await leggi_checkout(checkout_id)
    return await _rpc_runtime_bb(
        "bb_ricarica_applica_sumup",
        {
            "pcheckout": esito["checkout_id"],
            "preference": esito["riferimento"],
            "pamount": str(esito["importo"]),
            "pcurrency": esito["valuta"],
            "pmerchant": esito["merchant_code"],
            "pstatus": esito["stato"],
            "ptransaction_id": esito["transaction_id"],
            "ptransaction_code": esito["transaction_code"],
            "prefunded": str(esito["rimborsato"]),
            "praw": esito["audit"],
        },
    )


@router.post("/ricariche/sumup", summary="Crea una ricarica SumUp per l'hotel")
async def crea_ricarica_sumup(richiesta: RicaricaSumUpRequest) -> Dict[str, Any]:
    preparata = await _rpc_bb(
        "bb_alb_ricarica_prepara",
        {
            "sid": richiesta.sid,
            "p": richiesta.p,
            "imp": str(richiesta.importo),
            "pidempotenza": richiesta.idempotenza,
        },
    )
    if not isinstance(preparata, dict) or not preparata.get("id"):
        raise HTTPException(status_code=502, detail="Ricarica non preparata")
    if preparata.get("url"):
        return {"url": preparata["url"], "riferimento": preparata.get("riferimento")}

    from app.services.colazioni_sumup import (
        SumUpRicaricheErrore,
        SumUpRicaricheNonConfigurato,
        crea_checkout,
    )

    redirect_url, webhook_url = _url_ricariche()
    try:
        checkout = await crea_checkout(
            riferimento=str(preparata["riferimento"]),
            importo=Decimal(str(preparata["importo"])),
            struttura=str(preparata.get("struttura") or "Struttura partner"),
            redirect_url=redirect_url,
            webhook_url=webhook_url,
        )
        await _rpc_runtime_bb(
            "bb_ricarica_collega_checkout",
            {
                "prid": preparata["id"],
                "pcheckout": checkout["id"],
                "purl": checkout["url"],
                "pmerchant": checkout["merchant_code"],
                "pstatus": checkout["status"],
            },
        )
    except (SumUpRicaricheErrore, SumUpRicaricheNonConfigurato) as exc:
        await _rpc_runtime_bb(
            "bb_ricarica_errore", {"prid": preparata["id"], "perrore": str(exc)}
        )
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"url": checkout["url"], "riferimento": preparata["riferimento"]}


@router.post("/ricariche/sumup/sincronizza", summary="Aggiorna le ricariche dell'hotel")
async def sincronizza_ricariche_hotel(richiesta: ElencoOrdiniHotelRequest) -> Dict[str, Any]:
    # La RPC albergatore valida il token prima di consentire una verifica mirata.
    await _rpc_bb("bb_alb_portafoglio", {"sid": richiesta.sid, "p": richiesta.p})
    checkout_ids = await _rpc_runtime_bb(
        "bb_sumup_ricariche_da_verificare",
        {"plimite": 20, "psid": richiesta.sid},
    )
    aggiornate = 0
    for checkout_id in checkout_ids or []:
        try:
            await _applica_checkout_sumup(str(checkout_id))
            aggiornate += 1
        except Exception as exc:
            logger.warning("Verifica ricarica %s: %s", checkout_id, type(exc).__name__)
    portafoglio = await _rpc_bb(
        "bb_alb_portafoglio", {"sid": richiesta.sid, "p": richiesta.p}
    )
    return {"aggiornate": aggiornate, "portafoglio": portafoglio}


@router.post("/ricariche/sumup/webhook", summary="Webhook ricariche SumUp", status_code=204)
async def webhook_ricariche_sumup(request: Request) -> Response:
    payload = await request.json()
    if str(payload.get("event_type") or "") != "CHECKOUT_STATUS_CHANGED":
        return Response(status_code=204)
    checkout_id = str(payload.get("id") or "").strip()
    if not checkout_id or len(checkout_id) > 100:
        return Response(status_code=204)
    # Il payload non e' fidato: lo stato viene sempre riletto dall'API SumUp.
    await _applica_checkout_sumup(checkout_id)
    return Response(status_code=204)


@router.post("/menu-ospite/catalogo", summary="Menu unico con i prezzi dell'hotel")
async def catalogo_menu_ospite(richiesta: MenuOspiteRequest) -> Dict[str, Any]:
    """Restituisce la carta pubblica filtrata dal listino assegnato al voucher.

    Foto, descrizioni, sezioni e allergeni arrivano dal Menu digitale canonico;
    Supabase aggiunge soltanto il prezzo concordato per la struttura.
    """
    assegnati = await _rpc_bb(
        "bb_menu_ospite",
        {"vid": richiesta.codice, "pgiorno": richiesta.giorno.isoformat()},
    )
    if not isinstance(assegnati, dict) or assegnati.get("errore"):
        raise HTTPException(status_code=404, detail=(assegnati or {}).get("errore", "Codice non valido"))
    from app.menu.carta_menu import carta_pubblica

    carta = await carta_pubblica(destinazione="bb")
    prezzi = {
        int(p["prodotto_id"]): int(Decimal(str(p["prezzo"])) * 100)
        for p in assegnati.get("prodotti", [])
        if p.get("prodotto_id") is not None and _decimale_positivo(p.get("prezzo"))
    }
    items = [{**i, "p": prezzi[i["id"]], "fp": prezzi[i["id"]]} for i in carta["items"] if i["id"] in prezzi]
    categorie = {i["c"] for i in items}
    cats = [c for c in carta["cats"] if c["id"] in categorie]
    menu_ids = {c["m"] for c in cats}
    return {
        "menus": [m for m in carta["menus"] if m["id"] in menu_ids],
        "cats": cats,
        "items": items,
        "bb": {
            "codice": richiesta.codice.upper().strip(),
            "giorno": richiesta.giorno.isoformat(),
            "struttura": assegnati.get("struttura", ""),
        },
    }


@router.post("/menu-ospite/ordine", summary="Salva il carrello del cliente B&B")
async def salva_menu_ospite(richiesta: OrdineMenuOspiteRequest) -> Dict[str, Any]:
    risultato = await _rpc_bb(
        "bb_ospite_menu_salva",
        {
            "vid": richiesta.codice,
            "pgiorno": richiesta.giorno.isoformat(),
            "righe": [r.model_dump() for r in richiesta.righe],
        },
    )
    if not isinstance(risultato, dict) or risultato.get("errore"):
        raise HTTPException(status_code=422, detail=(risultato or {}).get("errore", "Ordine non salvato"))
    return risultato


async def _contesto_ordine_albergatore(sid: str, token: str) -> tuple[dict[str, Any], dict[str, Any]]:
    prodotti, stato = await asyncio.gather(
        _rpc_bb("bb_alb_prodotti", {"sid": sid, "p": token}),
        _rpc_bb("bb_alb_stato", {"sid": sid, "p": token}),
    )
    if not isinstance(prodotti, list) or not isinstance(stato, dict):
        raise HTTPException(status_code=502, detail="Dati della struttura non disponibili")
    return {str(x.get("chiave") or ""): x for x in prodotti}, stato


def _importo_cents(importo: Decimal) -> Decimal:
    return importo.quantize(Decimal("0.01"))


async def _movimento_borsellino(fn: str, sid: str, importo: Decimal, ordine_id: str) -> Dict[str, Any]:
    risultato = await _rpc_runtime_bb(
        fn, {"psid": sid, "pimporto": str(_importo_cents(importo)), "priferimento": ordine_id})
    if not isinstance(risultato, dict):
        raise HTTPException(status_code=502, detail="Borsellino non raggiungibile")
    return risultato


async def _fasce_ritiro() -> tuple[str, ...]:
    """Fasce di ritiro del titolare (bb_config); se mancano o il database non risponde, quelle predefinite."""
    from app.lotti.servizi.ordini_hotel import fasce_valide
    try:
        configurate = await _rpc_bb("bb_ordini_fasce_ritiro", {})
    except HTTPException as exc:
        logger.warning("Fasce di ritiro non lette (%s): uso le predefinite", exc.detail)
        configurate = []
    return fasce_valide(configurate if isinstance(configurate, list) else [])


@router.post("/ordini-prodotti/albergatore", summary="Invia un ordine mattutino dall'hotel")
async def crea_ordine_prodotti_hotel(richiesta: OrdineHotelRequest) -> Dict[str, Any]:
    from app.lotti.servizi.ordini_hotel import crea_ordine, verifica_termini
    catalogo, stato = await _contesto_ordine_albergatore(richiesta.sid, richiesta.p)
    try:
        verifica_termini(richiesta.data_consegna, richiesta.ora_ritiro, fasce=await _fasce_ritiro())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not richiesta.righe or len(richiesta.righe) > 100:
        raise HTTPException(status_code=422, detail="Il carrello deve contenere da 1 a 100 prodotti")
    struttura = stato.get("struttura") or {}
    saldo_dopo: Dict[str, Any] = {}

    async def addebita(ordine_id: str, totale: Decimal) -> None:
        esito = await _movimento_borsellino("bb_ordine_prodotti_addebita", richiesta.sid, totale, ordine_id)
        if esito.get("errore"):
            raise ValueError(str(esito["errore"]))
        saldo_dopo["saldo"] = esito.get("saldo")

    async def storna(ordine_id: str, totale: Decimal) -> None:
        try:
            esito = await _movimento_borsellino("bb_ordine_prodotti_rimborsa", richiesta.sid, totale, ordine_id)
            saldo_dopo["saldo"] = esito.get("saldo")
        except HTTPException as exc:
            logger.error("Rimborso borsellino non riuscito per l'ordine %s: %s", ordine_id, exc.detail)

    try:
        ordine = await crea_ordine(
            struttura_id=richiesta.sid,
            struttura_nome=str(struttura.get("nome") or "Struttura partner"),
            data_consegna=richiesta.data_consegna.isoformat(),
            catalogo=catalogo,
            righe=[r.model_dump() if hasattr(r, "model_dump") else r.dict() for r in richiesta.righe],
            nota=richiesta.nota,
            idempotenza=richiesta.idempotenza,
            ora_ritiro=richiesta.ora_ritiro,
            pagamento_metodo=richiesta.pagamento_metodo,
            addebita=addebita,
            storna=storna,
            su_creato=avvisa_in_background,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"ok": True, "ordine": ordine, "saldo": saldo_dopo.get("saldo")}


@router.post("/ordini-prodotti/albergatore/elenco", summary="Storico ordini mattutini dell'hotel")
async def elenco_ordini_prodotti_hotel(richiesta: ElencoOrdiniHotelRequest) -> Dict[str, Any]:
    await _contesto_ordine_albergatore(richiesta.sid, richiesta.p)
    from app.lotti.servizi.ordini_hotel import lista_ordini
    from app.lotti.servizi.ordini_hotel import ORA_LIMITE_ORDINE, prima_consegna_possibile
    ordini = await lista_ordini({"struttura_id": richiesta.sid}, 100)
    return {
        "ordini": ordini,
        "termini": {
            "prima_consegna": prima_consegna_possibile().isoformat(),
            "ora_limite": f"{ORA_LIMITE_ORDINE}:00",
            "fasce_ritiro": list(await _fasce_ritiro()),
        },
    }


@router.get("/ordini-prodotti", summary="Ordini mattutini ricevuti dagli hotel")
async def elenco_ordini_prodotti_titolare(
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    from app.lotti.servizi.ordini_hotel import lista_ordini
    ordini = await lista_ordini({}, 300)
    da_lavorare = sum(o.get("stato") not in ("consegnato", "annullato") for o in ordini)
    da_incassare = sum(float(o.get("totale") or 0) for o in ordini if o.get("pagamento") != "incassato" and o.get("stato") != "annullato")
    return {"ordini": ordini, "da_lavorare": da_lavorare, "da_incassare": round(da_incassare, 2)}


@router.patch("/ordini-prodotti/{ordine_id}", summary="Aggiorna stato o incasso ordine hotel")
async def aggiorna_ordine_prodotti_titolare(
    ordine_id: str,
    richiesta: AggiornaOrdineHotelRequest,
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    from app.lotti.servizi.ordini_hotel import aggiorna_ordine, lista_ordini
    if richiesta.stato == "annullato":
        # Il rimborso viene prima dell'annullo: se il borsellino non risponde l'ordine resta com'e'.
        attuali = await lista_ordini({"id": ordine_id}, 1)
        attuale = attuali[0] if attuali else None
        if attuale and attuale.get("pagamento_metodo") == "borsellino" and attuale.get("stato") != "annullato":
            esito = await _movimento_borsellino(
                "bb_ordine_prodotti_rimborsa", str(attuale["struttura_id"]),
                Decimal(str(attuale.get("totale") or 0)), ordine_id)
            if esito.get("errore"):
                raise HTTPException(status_code=502, detail="Rimborso sul borsellino non riuscito")
    try:
        ordine = await aggiorna_ordine(
            ordine_id, stato=richiesta.stato, pagamento=richiesta.pagamento, da="titolare_convenzioni")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not ordine:
        raise HTTPException(status_code=404, detail="Ordine non trovato")
    return {"ok": True, "ordine": ordine}


@router.get("/prodotti-acquaviva", summary="Prodotti del Menu segnati come Acquaviva")
async def elenco_prodotti_acquaviva(
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    from app.lotti.servizi.lotto_acquaviva import prodotti_acquaviva
    return {"prodotti": sorted(await prodotti_acquaviva(), key=int)}


@router.put("/prodotti-acquaviva", summary="Segna o toglie il fornitore Acquaviva a un prodotto del Menu")
async def segna_prodotto_acquaviva(
    richiesta: ProdottoAcquavivaRequest,
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    from app.lotti.servizi.lotto_acquaviva import imposta_prodotto_acquaviva
    await imposta_prodotto_acquaviva(richiesta.prodotto_id, richiesta.attivo, da="titolare_convenzioni")
    return {"ok": True, "prodotto_id": richiesta.prodotto_id, "attivo": richiesta.attivo}
