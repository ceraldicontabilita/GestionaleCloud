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
import hashlib
import logging
import re
import unicodedata
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Mapping, Optional
from zoneinfo import ZoneInfo

import aiohttp
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.config import settings
from app.utils.dependencies import get_current_admin_user

logger = logging.getLogger(__name__)

router = APIRouter()

ORE_SESSIONE = 12

_FORNITORE_VANDEMOORTELE = re.compile(r"vand(?:e)?moo?rte?le|vandermortel", re.IGNORECASE)
_CAMPI_CODICE_PRODOTTO = (
    "codice_prodotto",
    "codice_articolo",
    "codice_aqv_2026",
    "codice_aqv_2025",
    "acquaviva_id",
)


class RigaOrdineHotel(BaseModel):
    chiave: str = Field(min_length=1, max_length=180)
    quantita: int = Field(ge=1, le=200)


class OrdineHotelRequest(BaseModel):
    sid: str = Field(min_length=1, max_length=80)
    p: str = Field(min_length=1, max_length=300)
    data_consegna: date
    righe: List[RigaOrdineHotel]
    nota: str = Field(default="", max_length=500)
    idempotenza: str = Field(default="", max_length=80)


class ElencoOrdiniHotelRequest(BaseModel):
    sid: str = Field(min_length=1, max_length=80)
    p: str = Field(min_length=1, max_length=300)


class AggiornaOrdineHotelRequest(BaseModel):
    stato: Optional[str] = None
    pagamento: Optional[str] = None


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


def _codici_prodotto(prodotto: Mapping[str, Any]) -> set[str]:
    return {
        _testo_normalizzato(prodotto.get(campo)).replace(" ", "")
        for campo in _CAMPI_CODICE_PRODOTTO
        if prodotto.get(campo)
    }


def _prodotto_certo_da_riga(
    descrizione: str,
    riga: Mapping[str, Any],
    prodotti: Iterable[Mapping[str, Any]],
) -> Optional[Mapping[str, Any]]:
    """Collega la fattura al catalogo solo con una prova univoca.

    Non usa somiglianze o parole in comune: valgono un codice esplicito oppure
    l'uguaglianza del nome/descrizione normalizzati. In caso di ambiguita' la
    riga resta senza foto e allergeni, invece di inventare un'associazione.
    """

    codici_riga = {
        _testo_normalizzato(riga.get(campo)).replace(" ", "")
        for campo in ("codice", "codice_articolo", "codice_prodotto", "sku")
        if riga.get(campo)
    }
    testo_riga = _testo_normalizzato(descrizione)
    candidati: List[Mapping[str, Any]] = []
    for prodotto in prodotti:
        codici = _codici_prodotto(prodotto)
        codice_nel_testo = any(
            len(codice) >= 4 and re.search(rf"(?:^|\s){re.escape(codice)}(?:\s|$)", testo_riga)
            for codice in codici
        )
        stesso_testo = testo_riga and testo_riga in {
            _testo_normalizzato(prodotto.get("nome")),
            _testo_normalizzato(prodotto.get("descrizione")),
        }
        if (codici_riga and codici_riga & codici) or codice_nel_testo or stesso_testo:
            candidati.append(prodotto)
    return candidati[0] if len(candidati) == 1 else None


def costruisci_catalogo_prodotti_hotel(
    fatture: Iterable[Mapping[str, Any]],
    prodotti_vendita: Iterable[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """Catalogo verificabile per gli hotel, senza modificare i dati sorgente."""

    prodotti = [p for p in prodotti_vendita if p.get("attivo", True)]
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
            if not descrizione or not _decimale_positivo(riga.get("quantita")):
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

    for identita, voce in acquistati.items():
        riga = voce["riga"]
        collegato = _prodotto_certo_da_riga(voce["descrizione_fattura"], riga, prodotti)
        nome = str((collegato or {}).get("nome") or voce["descrizione_fattura"]).strip()
        digest = hashlib.sha256(identita.encode("utf-8")).hexdigest()[:24]
        risultato.append(
            {
                "chiave": f"vandemoortele:{digest}",
                "origine": "vandemoortele",
                "nome": nome,
                "descrizione": str((collegato or {}).get("descrizione") or voce["descrizione_fattura"]).strip(),
                "allergeni": list((collegato or {}).get("allergeni") or []),
                "immagine": (collegato or {}).get("immagine_url") or None,
                "prezzo": _decimale_positivo((collegato or {}).get("prezzo_vendita")),
                "categoria": str((collegato or {}).get("categoria") or "Vandemoortele").strip()
                or "Vandemoortele",
                "prova": "fattura",
                "descrizione_fattura": voce["descrizione_fattura"],
                "quantita_acquistata": voce["quantita"],
                "collegamento_catalogo": bool(collegato),
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
    catalogo = costruisci_catalogo_prodotti_hotel(fatture, prodotti)
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


async def _contesto_ordine_albergatore(sid: str, token: str) -> tuple[dict[str, Any], dict[str, Any]]:
    prodotti, stato = await asyncio.gather(
        _rpc_bb("bb_alb_prodotti", {"sid": sid, "p": token}),
        _rpc_bb("bb_alb_stato", {"sid": sid, "p": token}),
    )
    if not isinstance(prodotti, list) or not isinstance(stato, dict):
        raise HTTPException(status_code=502, detail="Dati della struttura non disponibili")
    return {str(x.get("chiave") or ""): x for x in prodotti}, stato


@router.post("/ordini-prodotti/albergatore", summary="Invia un ordine mattutino dall'hotel")
async def crea_ordine_prodotti_hotel(richiesta: OrdineHotelRequest) -> Dict[str, Any]:
    oggi = datetime.now(ZoneInfo("Europe/Rome")).date()
    if richiesta.data_consegna < oggi or richiesta.data_consegna > oggi + timedelta(days=30):
        raise HTTPException(status_code=422, detail="La consegna deve essere tra oggi e i prossimi 30 giorni")
    if not richiesta.righe or len(richiesta.righe) > 100:
        raise HTTPException(status_code=422, detail="Il carrello deve contenere da 1 a 100 prodotti")
    catalogo, stato = await _contesto_ordine_albergatore(richiesta.sid, richiesta.p)
    struttura = stato.get("struttura") or {}
    from app.lotti.servizi.ordini_hotel import crea_ordine
    try:
        ordine = await crea_ordine(
            struttura_id=richiesta.sid,
            struttura_nome=str(struttura.get("nome") or "Struttura partner"),
            data_consegna=richiesta.data_consegna.isoformat(),
            catalogo=catalogo,
            righe=[r.model_dump() if hasattr(r, "model_dump") else r.dict() for r in richiesta.righe],
            nota=richiesta.nota,
            idempotenza=richiesta.idempotenza,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"ok": True, "ordine": ordine}


@router.post("/ordini-prodotti/albergatore/elenco", summary="Storico ordini mattutini dell'hotel")
async def elenco_ordini_prodotti_hotel(richiesta: ElencoOrdiniHotelRequest) -> Dict[str, Any]:
    await _contesto_ordine_albergatore(richiesta.sid, richiesta.p)
    from app.lotti.servizi.ordini_hotel import lista_ordini
    ordini = await lista_ordini({"struttura_id": richiesta.sid}, 100)
    return {"ordini": ordini}


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
    from app.lotti.servizi.ordini_hotel import aggiorna_ordine
    try:
        ordine = await aggiorna_ordine(
            ordine_id, stato=richiesta.stato, pagamento=richiesta.pagamento, da="titolare_convenzioni")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not ordine:
        raise HTTPException(status_code=404, detail="Ordine non trovato")
    return {"ok": True, "ordine": ordine}
