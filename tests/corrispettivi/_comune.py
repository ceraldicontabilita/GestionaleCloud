"""Attrezzi comuni dei collaudi funzionali di corrispettivi, POS e versamenti.

Niente logica di prova qui: solo costruttori di documenti (XML COR10, CSV AdE),
un archivio in memoria e due istantanee per confrontare «prima» e «dopo».
Gli importi si confrontano in ``Decimal`` (mai ``float``).
"""
from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.database import Database
from app.routers import documenti
from app.services.archivio_documenti_memoria import ClientArchivioMemoria

PIVA = "04523831214"
MATRICOLA = "99MEY026532"

REGISTRI = (
    "corrispettivi", "prima_nota_cassa", "prima_nota_banca", "movimenti_contabili",
    "chiusure_pos_manuali",
)


def D(valore: Any) -> Decimal:
    """Importo come Decimal, dal testo (mai da un float)."""
    return Decimal(str(valore)).quantize(Decimal("0.01"))


def run(coro):
    return asyncio.run(coro)


ANNO_ATTIVO = 2026


def nuovo_db(nome: str = "scenari"):
    """Archivio in memoria con l'anno di import attivo fissato a 2026: gli scenari
    non dipendono dall'anno in cui girano."""
    db = ClientArchivioMemoria()[nome]
    run(db["sistema_stato"].insert_one({"chiave": "config_import_anno_attivo", "anno": ANNO_ATTIVO}))
    return db


def xml_chiusura(*, data: str = "2026-09-10", progressivo: str = "2700",
                 matricola: str = MATRICOLA, contanti: str = "300.00",
                 elettronico: str = "700.00", imponibile: str = "909.09",
                 imposta: str = "90.91", importo_parziale: Optional[str] = None,
                 documenti_n: int = 40) -> str:
    """Chiusura RT COR10 reale (solo gli elementi che il parser legge)."""
    parziale = f"<ImportoParziale>{importo_parziale}</ImportoParziale>" if importo_parziale else ""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<n1:DatiCorrispettivi xmlns:n1="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/'
        'corrispettivi/dati/v1.0" versione="COR10">'
        f"<Trasmissione><Progressivo>{progressivo}</Progressivo><Formato>COR10</Formato>"
        f"<Dispositivo><Tipo>RT</Tipo><IdDispositivo>{matricola}</IdDispositivo></Dispositivo>"
        f"<CodiceFiscaleEsercente>{PIVA}</CodiceFiscaleEsercente><PIVAEsercente>{PIVA}</PIVAEsercente>"
        f"<DataOraTrasmissione>{data}T20:51:23+02:00</DataOraTrasmissione></Trasmissione>"
        f"<DataOraRilevazione>{data}T20:50:47+02:00</DataOraRilevazione>"
        "<DatiRT><Riepilogo>"
        f"<IVA><AliquotaIVA>10.00</AliquotaIVA><Imposta>{imposta}</Imposta></IVA>"
        f"<Ammontare>{imponibile}</Ammontare>{parziale}</Riepilogo>"
        f"<Totali><NumeroDocCommerciali>{documenti_n}</NumeroDocCommerciali>"
        f"<PagatoContanti>{contanti}</PagatoContanti>"
        f"<PagatoElettronico>{elettronico}</PagatoElettronico></Totali>"
        "</DatiRT></n1:DatiCorrispettivi>"
    )


def parsed_chiusura(**kwargs) -> Dict[str, Any]:
    from app.parsers.corrispettivi_parser import parse_corrispettivo_xml

    parsed = parse_corrispettivo_xml(xml_chiusura(**kwargs))
    assert not parsed.get("error"), parsed
    return parsed


class Importatore:
    """Documenti > Import, come lo usa l'utente: anteprima, poi conferma."""

    def __init__(self, db, monkeypatch):
        monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))
        self.db = db
        app = FastAPI()
        app.include_router(documenti.router, prefix="/api/documenti")
        self._client = TestClient(app)

    def importa(self, nome: str, contenuto: bytes | str) -> Dict[str, Any]:
        if isinstance(contenuto, str):
            contenuto = contenuto.encode("utf-8")
        anteprima = self._client.post(
            "/api/documenti/upload-auto/preview",
            files={"file": (nome, contenuto, "application/octet-stream")})
        assert anteprima.status_code == 200, anteprima.text
        risposta = self._client.post(
            "/api/documenti/upload-auto",
            files={"file": (nome, contenuto, "application/octet-stream")},
            headers={"X-Document-Preview-Token": anteprima.json()["confirmation_token"]})
        assert risposta.status_code == 200, risposta.text
        return risposta.json()


async def righe(db, collezione: str, filtro: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    return await db[collezione].find(filtro or {}, {"_id": 0}).to_list(None)


async def attive(db, collezione: str, filtro: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Righe non cancellate ne' archiviate (le ritirate restano per l'audit)."""
    return [r for r in await righe(db, collezione, filtro)
            if r.get("status") not in ("deleted", "archived", "archiviata")
            and r.get("entity_status") != "deleted"]


async def istantanea(db, collezioni: Iterable[str] = REGISTRI) -> Dict[str, List[Any]]:
    """Per ogni registro, l'elenco ordinato degli id: due istantanee uguali =
    nessuna scrittura nuova e nessuna riga rimpiazzata."""
    return {c: sorted(str(r.get("id")) for r in await righe(db, c)) for c in collezioni}


def somma(valori: Iterable[Any]) -> Decimal:
    return sum((D(v) for v in valori), Decimal("0.00"))


def totali_scrittura(movimento: Dict[str, Any]) -> tuple[Decimal, Decimal]:
    dare = somma(r.get("dare") or 0 for r in movimento["righe"])
    avere = somma(r.get("avere") or 0 for r in movimento["righe"])
    return dare, avere


def importo_conto(movimento: Dict[str, Any], conto: str, lato: str) -> Decimal:
    return somma(r.get(lato) or 0 for r in movimento["righe"] if r["conto_codice"] == conto)
