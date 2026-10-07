"""A-Cube API — fatture passive dallo SdI e dal Cassetto fiscale.

Un solo modulo per il canale A-Cube: accesso (token JWT di 24 ore), registro
delle fatture ricevute (``acube_fatture``), webhook ``supplier-invoice`` e
controllo giornaliero di riserva.

Regole:

- Il webhook non si fida del corpo: ne prende solo l'``uuid`` e rilegge la
  fattura da A-Cube con la propria credenziale (come il webhook SumUp).
- In **sandbox** le fatture sono simulate: si registrano e si vedono, ma non
  entrano MAI nella contabilità (nessun dato inventato).
- In **produzione** l'originale entra dallo smistatore dei documenti, lo stesso
  della cartella unica Drive: deduplica, fornitore, prima nota restano quelli
  di sempre. Nessun secondo writer delle fatture.
- Il giro automatico lavora solo sugli ultimi giorni, mai sullo storico.

Variabili (dashboard Render, servizio GestionaleCloud):
``ACUBE_EMAIL``, ``ACUBE_PASSWORD``, ``ACUBE_ENV`` (``sandbox`` | ``production``).
Il segreto del webhook nasce qui e resta nel database (``sistema_stato``).
"""
from __future__ import annotations

import asyncio
import hmac
import logging
import os
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

REGISTRO = "acube_fatture"
CHIAVE_WEBHOOK = "acube_webhook"
CHIAVE_STATO = "acube_ultimo_controllo"
CANALE = "acube"
EVENTO = "supplier-invoice"
TIMEOUT = 30.0
GIORNI_CONTROLLO = 5

API = {
    "sandbox": "https://api-sandbox.acubeapi.com",
    "production": "https://api.acubeapi.com",
}
LOGIN = {
    "sandbox": ("https://common-sandbox.api.acubeapi.com/login", "https://common.api.acubeapi.com/login"),
    "production": ("https://common.api.acubeapi.com/login",),
}
URL_PUBBLICO = "https://gestionalecloud.onrender.com"
PERCORSO_WEBHOOK = "/api/acube/webhook"

ACCETTA = {
    "json": "application/json",
    "xml": "application/xml",
    "html": "text/html",
    "pdf": "application/pdf",
    "originale": "application/octet-stream",
}


class AcubeErrore(Exception):
    """Errore parlante verso l'utente: niente dettagli di credenziali."""

    def __init__(self, messaggio: str, stato: int = 502):
        super().__init__(messaggio)
        self.stato = stato


# ---------------------------------------------------------------- configurazione

def ambiente() -> str:
    valore = (os.environ.get("ACUBE_ENV") or "sandbox").strip().lower()
    return "production" if valore in ("production", "produzione", "prod") else "sandbox"


def in_sandbox() -> bool:
    return ambiente() == "sandbox"


def partita_iva() -> str:
    from app.config import settings

    return (os.environ.get("ACUBE_FISCAL_ID") or settings.FISCAL_COMPANY_ID or "").strip()


def configurato() -> bool:
    return bool((os.environ.get("ACUBE_EMAIL") or "").strip() and (os.environ.get("ACUBE_PASSWORD") or ""))


def import_attivo() -> bool:
    """In sandbox mai. In produzione acceso salvo ``ACUBE_IMPORT=false``."""
    if in_sandbox():
        return False
    return (os.environ.get("ACUBE_IMPORT") or "true").strip().lower() not in ("false", "0", "no")


def url_webhook() -> str:
    base = (os.environ.get("ACUBE_WEBHOOK_BASE") or URL_PUBBLICO).rstrip("/")
    return base + PERCORSO_WEBHOOK


def base_api() -> str:
    return API[ambiente()]


# ---------------------------------------------------------------- accesso

_token: Dict[str, Any] = {"valore": None, "scade": 0.0, "ambiente": None}
_lock = asyncio.Lock()


async def _login(client: httpx.AsyncClient) -> str:
    if not configurato():
        raise AcubeErrore("Credenziali A-Cube assenti: ACUBE_EMAIL e ACUBE_PASSWORD su Render.", 503)
    corpo = {
        "email": os.environ["ACUBE_EMAIL"].strip(),
        "password": os.environ["ACUBE_PASSWORD"],
        "environment": ambiente(),
    }
    ultimo = None
    for url in LOGIN[ambiente()]:
        try:
            r = await client.post(url, json=corpo, headers={"Accept": "application/json"})
        except httpx.HTTPError as exc:
            ultimo = f"{type(exc).__name__}"
            continue
        if r.status_code == 200:
            token = (r.json() or {}).get("token")
            if token:
                return token
        ultimo = f"HTTP {r.status_code}"
    raise AcubeErrore(f"Accesso ad A-Cube rifiutato ({ultimo}): controllare email e password su Render.", 502)


async def token(client: httpx.AsyncClient, *, nuovo: bool = False) -> str:
    async with _lock:
        if (not nuovo and _token["valore"] and _token["ambiente"] == ambiente()
                and time.time() < _token["scade"]):
            return _token["valore"]
        valore = await _login(client)
        # Il token vale 24 ore: si rinnova un'ora prima.
        _token.update(valore=valore, scade=time.time() + 23 * 3600, ambiente=ambiente())
        return valore


async def chiama(metodo: str, percorso: str, *, accetta: str = "application/json",
                 client: Optional[httpx.AsyncClient] = None, **kwargs) -> httpx.Response:
    """Richiesta autenticata; un 401 rinnova il token una volta sola."""
    proprio = client is None
    client = client or httpx.AsyncClient(timeout=TIMEOUT)
    extra = kwargs.pop("headers", None) or {}
    try:
        r: Optional[httpx.Response] = None
        for tentativo in (0, 1):
            t = await token(client, nuovo=bool(tentativo))
            headers = {"Authorization": f"Bearer {t}", "Accept": accetta, **extra}
            r = await client.request(metodo, base_api() + percorso, headers=headers, **kwargs)
            if r.status_code != 401:
                return r
        return r
    except httpx.HTTPError as exc:
        raise AcubeErrore(f"A-Cube non raggiungibile: {type(exc).__name__}", 502) from exc
    finally:
        if proprio:
            await client.aclose()


def _controlla(r: httpx.Response, cosa: str) -> None:
    if r.status_code >= 400:
        try:
            dettaglio = r.json()
            dettaglio = dettaglio.get("detail") or dettaglio.get("hydra:description") or dettaglio.get("title")
        except Exception:
            dettaglio = r.text[:200]
        raise AcubeErrore(f"{cosa}: A-Cube ha risposto {r.status_code} ({dettaglio})", 502)


# ---------------------------------------------------------------- lettura fattura

_RE_TOTALE = re.compile(r"<(?:\w+:)?ImportoTotaleDocumento>\s*([^<]+?)\s*</", re.S)


def riepilogo_da_xml(xml: bytes) -> Dict[str, Any]:
    """Numero, data, fornitore, totale letti dal parser canonico delle fatture."""
    from app.parsers.fattura_elettronica_parser import parse_fattura_xml

    testo = xml.decode("utf-8", errors="replace")
    try:
        p = parse_fattura_xml(testo)
    except Exception as exc:
        return {"errore_lettura": f"{type(exc).__name__}"}
    totale = _RE_TOTALE.search(testo)
    return {
        "numero": (p.get("invoice_number") or None),
        "data": (p.get("invoice_date") or None),
        "tipo_documento": p.get("tipo_documento") or None,
        "fornitore": p.get("supplier_name") or None,
        "fornitore_piva": p.get("supplier_vat") or None,
        # Il totale e' quello scritto nell'XML, come stringa: mai uno zero inventato.
        "totale": totale.group(1).strip() if totale else None,
    }


async def leggi(uuid: str, formato: str = "json", client: Optional[httpx.AsyncClient] = None) -> httpx.Response:
    if formato not in ACCETTA:
        raise AcubeErrore(f"Formato sconosciuto: {formato}", 400)
    r = await chiama("GET", f"/invoices/{uuid}", accetta=ACCETTA[formato], client=client)
    _controlla(r, "Lettura fattura")
    return r


def _nome_file(meta: Dict[str, Any], uuid: str) -> str:
    nome = (meta.get("sdi_file_name") or "").strip()
    return nome or f"acube_{uuid}.xml"


# ---------------------------------------------------------------- acquisizione

async def acquisisci(db, uuid: str, *, via: str) -> Dict[str, Any]:
    """Rilegge la fattura da A-Cube, la registra e (solo in produzione) la importa.

    Idempotente: una fattura gia' importata non si reimporta.
    """
    uuid = str(uuid or "").strip()
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", uuid):
        raise AcubeErrore("uuid della fattura non valido", 400)

    esistente = await db[REGISTRO].find_one({"uuid": uuid}, {"_id": 0})
    if esistente and esistente.get("stato") in ("importata", "simulata"):
        return {"uuid": uuid, "stato": esistente["stato"], "gia_presente": True}

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        meta = (await leggi(uuid, "json", client)).json()
        destinatario = ((meta.get("recipient") or {}).get("business_vat_number_code") or "").upper()
        if destinatario.replace("IT", "") not in ("", partita_iva()):
            raise AcubeErrore("La fattura non e' intestata alla societa'", 422)
        xml = (await leggi(uuid, "xml", client)).content
        originale = (await leggi(uuid, "originale", client)).content

    ora = datetime.now(timezone.utc).isoformat()
    nome = _nome_file(meta, uuid)
    sender = meta.get("sender") or {}
    riga: Dict[str, Any] = {
        "id": uuid,
        "uuid": uuid,
        "ambiente": ambiente(),
        "canale": CANALE,
        "via": via,
        "sdi_file_name": nome,
        "sdi_file_id": meta.get("sdi_file_id"),
        "marking": meta.get("marking"),
        "notice": meta.get("notice"),
        "ricevuta_da_acube_il": meta.get("created_at"),
        "fornitore": sender.get("business_name"),
        "fornitore_piva": sender.get("business_vat_number_code"),
        **{k: v for k, v in riepilogo_da_xml(xml).items() if v is not None},
        "aggiornato_il": ora,
    }
    if not esistente:
        riga["registrata_il"] = ora

    if meta.get("marking") == "quarantena":
        riga["stato"] = "quarantena"
    elif not import_attivo():
        riga["stato"] = "simulata" if in_sandbox() else "registrata"
    else:
        riga.update(await _importa(nome, originale, uuid))
    await db[REGISTRO].update_one({"uuid": uuid}, {"$set": riga}, upsert=True)
    return {"uuid": uuid, "stato": riga["stato"], "numero": riga.get("numero"),
            "fornitore": riga.get("fornitore")}


async def _importa(nome: str, originale: bytes, uuid: str) -> Dict[str, Any]:
    """Lo smistatore unico dei documenti, come per la cartella Drive."""
    import hashlib

    from app.services.drive_cartella_unica import _smista, esito_del_risultato

    contesto = {"channel": "acube", "acube_uuid": uuid,
                "source_sha256": hashlib.sha256(originale).hexdigest()}
    try:
        risultato = await _smista(nome, originale, contesto)
    except Exception as exc:
        logger.exception("[acube] import %s fallito", uuid)
        return {"stato": "errore_import", "esito_import": f"{type(exc).__name__}: {exc}"[:300]}
    from app.services.drive_cartella_unica import ARCHIVIO, riferimenti_del_risultato

    destinazione, motivo = esito_del_risultato(risultato)
    if risultato.get("rinviato"):
        stato = "da_importare"
    elif destinazione == ARCHIVIO:
        stato = "importata"
    else:
        stato = "errore_import"
    return {"stato": stato, "esito_import": motivo or ("gia' presente" if risultato.get("duplicate") else "importata"),
            "riferimenti": riferimenti_del_risultato(risultato)}


# ---------------------------------------------------------------- webhook

async def segreto_webhook(db, *, crea: bool = False) -> Optional[str]:
    riga = await db["sistema_stato"].find_one({"chiave": CHIAVE_WEBHOOK}, {"_id": 0})
    valore = ((riga or {}).get("valore") or {}).get("segreto") if isinstance((riga or {}).get("valore"), dict) else None
    if valore or not crea:
        return valore
    valore = secrets.token_urlsafe(32)
    ora = datetime.now(timezone.utc).isoformat()
    await db["sistema_stato"].update_one(
        {"chiave": CHIAVE_WEBHOOK},
        {"$set": {"chiave": CHIAVE_WEBHOOK, "valore": {"segreto": valore, "creato_il": ora}, "updated_at": ora}},
        upsert=True,
    )
    return valore


async def webhook_autorizzato(db, authorization: Optional[str]) -> bool:
    atteso = await segreto_webhook(db)
    if not atteso or not authorization:
        return False
    ricevuto = authorization.strip()
    if ricevuto.lower().startswith("bearer "):
        ricevuto = ricevuto[7:].strip()
    return hmac.compare_digest(ricevuto.encode(), atteso.encode())


def uuid_dal_corpo(corpo: Any) -> Optional[str]:
    """Dal corpo si prende solo l'identificativo: il resto si rilegge da A-Cube."""
    if isinstance(corpo, list):
        corpo = corpo[0] if corpo else {}
    if not isinstance(corpo, dict):
        return None
    for contenitore in (corpo.get("invoice"), corpo):
        if isinstance(contenitore, dict) and contenitore.get("uuid"):
            return str(contenitore["uuid"])
    return None


async def registra_webhook(db) -> Dict[str, Any]:
    """Crea o aggiorna su A-Cube il webhook ``supplier-invoice`` verso il gestionale
    e lo collega alla scheda della societa'. Il segreto nasce qui e non esce."""
    segreto = await segreto_webhook(db, crea=True)
    piva = partita_iva()
    corpo = {"event": EVENTO, "target_url": url_webhook(), "authentication_type": "header",
             "authentication_key": "Bearer", "authentication_token": segreto}
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        r = await chiama("GET", "/api-configurations", client=client)
        _controlla(r, "Elenco webhook")
        esistenti = r.json()
        if isinstance(esistenti, dict):
            esistenti = esistenti.get("hydra:member") or esistenti.get("member") or []
        mio = next((c for c in esistenti if c.get("event") == EVENTO
                    and c.get("target_url") == corpo["target_url"]), None)
        if mio:
            r = await chiama("PUT", f"/api-configurations/{mio['uuid']}", client=client, json=corpo)
            _controlla(r, "Aggiornamento webhook")
        else:
            r = await chiama("POST", "/api-configurations", client=client, json=corpo)
            _controlla(r, "Creazione webhook")
        config = r.json()
        iri = f"/api-configurations/{config.get('uuid')}"

        r = await chiama("GET", f"/business-registry-configurations/{piva}", client=client)
        _controlla(r, "Lettura scheda societa'")
        brc = r.json()
        collegati = []
        for c in brc.get("api_configurations") or []:
            ident = c if isinstance(c, str) else (c.get("@id") or (f"/api-configurations/{c['uuid']}" if c.get("uuid") else None))
            if ident:
                collegati.append(ident)
        if iri not in collegati:
            collegati.append(iri)
            campi = {k: brc.get(k) for k in ("fiscal_id", "name", "email", "customer_invoice_enabled",
                                             "supplier_invoice_enabled", "receipts_enabled",
                                             "apply_signature", "apply_legal_storage") if k in brc}
            campi["api_configurations"] = collegati
            r = await chiama("PUT", f"/business-registry-configurations/{piva}", client=client, json=campi)
            _controlla(r, "Collegamento webhook alla societa'")
    return {"registrato": True, "target_url": corpo["target_url"], "uuid": config.get("uuid"),
            "ambiente": ambiente(), "partita_iva": piva}


# ---------------------------------------------------------------- controllo giornaliero

async def elenco_remoto(giorni: int = GIORNI_CONTROLLO) -> List[Dict[str, Any]]:
    dopo = (datetime.now(timezone.utc) - timedelta(days=giorni)).strftime("%Y-%m-%d")
    righe: List[Dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for pagina in range(1, 40):
            r = await chiama("GET", "/invoices", client=client, params={
                "page": pagina, "itemsPerPage": 30, "created_at[after]": dopo,
                "recipient.business_vat_number_code": partita_iva(),
            })
            _controlla(r, "Elenco fatture")
            dati = r.json()
            membri = dati.get("hydra:member", dati.get("member", [])) if isinstance(dati, dict) else dati
            righe.extend(membri or [])
            if not membri or len(membri) < 30:
                break
    return righe


async def controlla(db, giorni: int = GIORNI_CONTROLLO) -> Dict[str, Any]:
    """Riserva del webhook: le fatture degli ultimi giorni non ancora registrate."""
    esito: Dict[str, Any] = {"ambiente": ambiente(), "giorni": giorni, "trovate": 0,
                             "acquisite": 0, "gia_presenti": 0, "errori": []}
    for meta in await elenco_remoto(giorni):
        uuid = meta.get("uuid")
        if not uuid:
            continue
        esito["trovate"] += 1
        try:
            r = await acquisisci(db, uuid, via="controllo")
            esito["gia_presenti" if r.get("gia_presente") else "acquisite"] += 1
        except AcubeErrore as exc:
            esito["errori"].append({"uuid": uuid, "errore": str(exc)})
    ora = datetime.now(timezone.utc).isoformat()
    await db["sistema_stato"].update_one(
        {"chiave": CHIAVE_STATO},
        {"$set": {"chiave": CHIAVE_STATO, "valore": ora, "updated_at": ora, "last_result": esito}},
        upsert=True,
    )
    return esito


# ---------------------------------------------------------------- sandbox

def xml_di_prova(numero: str) -> bytes:
    """Fattura FatturaPA dichiaratamente finta, per la sola sandbox."""
    oggi = datetime.now().strftime("%Y-%m-%d")
    piva = partita_iva()
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<p:FatturaElettronica versione="FPR12" xmlns:p="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2">
  <FatturaElettronicaHeader>
    <DatiTrasmissione>
      <IdTrasmittente><IdPaese>IT</IdPaese><IdCodice>01234567890</IdCodice></IdTrasmittente>
      <ProgressivoInvio>{numero[-5:]}</ProgressivoInvio>
      <FormatoTrasmissione>FPR12</FormatoTrasmissione>
      <CodiceDestinatario>0000000</CodiceDestinatario>
    </DatiTrasmissione>
    <CedentePrestatore>
      <DatiAnagrafici>
        <IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>01234567890</IdCodice></IdFiscaleIVA>
        <Anagrafica><Denominazione>FORNITORE DI PROVA SANDBOX</Denominazione></Anagrafica>
        <RegimeFiscale>RF01</RegimeFiscale>
      </DatiAnagrafici>
      <Sede><Indirizzo>VIA DI PROVA 1</Indirizzo><CAP>80100</CAP><Comune>NAPOLI</Comune><Provincia>NA</Provincia><Nazione>IT</Nazione></Sede>
    </CedentePrestatore>
    <CessionarioCommittente>
      <DatiAnagrafici>
        <IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>{piva}</IdCodice></IdFiscaleIVA>
        <Anagrafica><Denominazione>CERALDI GROUP SRL</Denominazione></Anagrafica>
      </DatiAnagrafici>
      <Sede><Indirizzo>VIA DI PROVA 2</Indirizzo><CAP>80100</CAP><Comune>NAPOLI</Comune><Provincia>NA</Provincia><Nazione>IT</Nazione></Sede>
    </CessionarioCommittente>
  </FatturaElettronicaHeader>
  <FatturaElettronicaBody>
    <DatiGenerali>
      <DatiGeneraliDocumento>
        <TipoDocumento>TD01</TipoDocumento><Divisa>EUR</Divisa><Data>{oggi}</Data><Numero>{numero}</Numero>
        <ImportoTotaleDocumento>12.20</ImportoTotaleDocumento>
        <Causale>FATTURA DI PROVA SANDBOX A-CUBE - NON CONTABILIZZARE</Causale>
      </DatiGeneraliDocumento>
    </DatiGenerali>
    <DatiBeniServizi>
      <DettaglioLinee>
        <NumeroLinea>1</NumeroLinea><Descrizione>Articolo di prova sandbox</Descrizione>
        <Quantita>1.00</Quantita><PrezzoUnitario>10.00</PrezzoUnitario><PrezzoTotale>10.00</PrezzoTotale><AliquotaIVA>22.00</AliquotaIVA>
      </DettaglioLinee>
      <DatiRiepilogo><AliquotaIVA>22.00</AliquotaIVA><ImponibileImporto>10.00</ImponibileImporto><Imposta>2.20</Imposta><EsigibilitaIVA>I</EsigibilitaIVA></DatiRiepilogo>
    </DatiBeniServizi>
  </FatturaElettronicaBody>
</p:FatturaElettronica>""".encode("utf-8")


async def simula_fattura_passiva() -> Dict[str, Any]:
    if not in_sandbox():
        raise AcubeErrore("La simulazione esiste solo in sandbox.", 409)
    numero = "PROVA-" + datetime.now().strftime("%Y%m%d%H%M%S")
    r = await chiama("POST", "/simulate/supplier-invoice", content=xml_di_prova(numero),
                     headers={"Content-Type": "application/xml"})
    _controlla(r, "Simulazione fattura passiva")
    try:
        dati = r.json()
    except Exception:
        dati = {}
    return {"inviata": True, "numero": numero, "uuid": (dati or {}).get("uuid")}


# ---------------------------------------------------------------- stato

async def stato(db) -> Dict[str, Any]:
    ultimo = await db["sistema_stato"].find_one({"chiave": CHIAVE_STATO}, {"_id": 0})
    return {
        "configurato": configurato(),
        "ambiente": ambiente(),
        "import_attivo": import_attivo(),
        "partita_iva": partita_iva(),
        "webhook_url": url_webhook(),
        "webhook_segreto_presente": bool(await segreto_webhook(db)),
        "ultimo_controllo": (ultimo or {}).get("valore"),
        "ultimo_esito": (ultimo or {}).get("last_result"),
    }


async def verifica_accesso() -> Tuple[bool, str]:
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            await token(client, nuovo=True)
        return True, "Accesso ad A-Cube riuscito"
    except AcubeErrore as exc:
        return False, str(exc)
