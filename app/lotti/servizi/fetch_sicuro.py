"""Scaricare una pagina da un indirizzo che arriva da fuori, senza aprire la rete interna.

Lo scraper delle schede produttore, le fonti catalogo e il proxy PDF di SAIMA
ricevono un URL da un utente (o da una sitemap di terzi) e lo scaricano dal
server. Senza controlli quell'URL può puntare a ``127.0.0.1``, alla rete
privata di Render o ai metadati del cloud (``169.254.169.254``): è un SSRF.

Regole, uguali per tutti i chiamanti:

- solo ``https``, porta standard;
- l'host si risolve e **ogni** indirizzo deve essere pubblico (niente
  loopback, privati, link-local, multicast, riservati);
- se il chiamante dà una lista di domini, l'host deve starci (o esserne un
  sottodominio);
- i reindirizzamenti non si seguono alla cieca: ognuno si rivalida con le
  stesse regole, al massimo ``MAX_REDIRECT``;
- la risposta ha un tetto di dimensione.

Resta il rischio del DNS che cambia risposta fra la verifica e la
connessione (rebinding): è mitigato dalla verifica a ogni salto, non annullato.
"""
from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from typing import Iterable, Optional
from urllib.parse import urljoin, urlparse

import httpx

MAX_REDIRECT = 3
MAX_BYTES_DEFAULT = 5 * 1024 * 1024
TIMEOUT_DEFAULT = 20.0


class UrlNonAmmesso(ValueError):
    """L'indirizzo non si può scaricare: il messaggio dice perché."""


@dataclass
class Risposta:
    url: str
    status_code: int
    content: bytes
    content_type: str

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", "replace")


def _host_in_domini(host: str, domini: Iterable[str]) -> bool:
    host = host.lower().rstrip(".")
    for d in domini:
        d = d.lower().strip().rstrip(".")
        if d and (host == d or host.endswith("." + d)):
            return True
    return False


def _ip_pubblico(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return addr.is_global and not (addr.is_multicast or addr.is_reserved)


def _risolvi(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UrlNonAmmesso(f"host non risolvibile: {host}") from exc
    return sorted({info[4][0] for info in infos})


def controlla_forma(url: str, domini: Optional[Iterable[str]] = None) -> str:
    """Controlli che non richiedono la rete: schema, porta, credenziali, domini, IP letterali."""
    parsed = urlparse(str(url or "").strip())
    if parsed.scheme != "https":
        raise UrlNonAmmesso("solo indirizzi https")
    host = parsed.hostname
    if not host:
        raise UrlNonAmmesso("indirizzo senza host")
    if parsed.username or parsed.password:
        raise UrlNonAmmesso("credenziali nell'indirizzo non ammesse")
    if parsed.port not in (None, 443):
        raise UrlNonAmmesso("porta non ammessa")
    if domini is not None and not _host_in_domini(host, domini):
        raise UrlNonAmmesso(f"dominio non autorizzato: {host}")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        if not _ip_pubblico(host):
            raise UrlNonAmmesso("indirizzo di rete interna")
    return host


async def valida_url(url: str, domini: Optional[Iterable[str]] = None) -> str:
    """Solleva ``UrlNonAmmesso`` se l'URL non si può scaricare; altrimenti lo restituisce."""
    host = controlla_forma(url, domini)
    indirizzi = await asyncio.to_thread(_risolvi, host)
    if not indirizzi or not all(_ip_pubblico(ip) for ip in indirizzi):
        raise UrlNonAmmesso("indirizzo di rete interna")
    return str(url).strip()


async def scarica(
    url: str,
    *,
    domini: Optional[Iterable[str]] = None,
    headers: Optional[dict] = None,
    timeout: float = TIMEOUT_DEFAULT,
    max_bytes: int = MAX_BYTES_DEFAULT,
    client: Optional[httpx.AsyncClient] = None,
) -> Risposta:
    """GET con i reindirizzamenti rivalidati uno per uno e un tetto di dimensione."""
    domini = list(domini) if domini is not None else None
    proprio = client is None
    client = client or httpx.AsyncClient(timeout=timeout, follow_redirects=False)
    try:
        corrente = url
        for _ in range(MAX_REDIRECT + 1):
            await valida_url(corrente, domini)
            async with client.stream("GET", corrente, headers=headers, timeout=timeout,
                                     follow_redirects=False) as r:
                if r.is_redirect:
                    destinazione = r.headers.get("location")
                    if not destinazione:
                        raise UrlNonAmmesso("reindirizzamento senza destinazione")
                    corrente = urljoin(corrente, destinazione)
                    continue
                dati = bytearray()
                async for blocco in r.aiter_bytes():
                    dati.extend(blocco)
                    if len(dati) > max_bytes:
                        raise UrlNonAmmesso("risposta troppo grande")
                return Risposta(url=corrente, status_code=r.status_code, content=bytes(dati),
                                content_type=r.headers.get("content-type", ""))
        raise UrlNonAmmesso("troppi reindirizzamenti")
    finally:
        if proprio:
            await client.aclose()
