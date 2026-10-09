"""Strumenti comuni dei collaudi funzionali (`test_scenari_funzionali_*.py`).

Un archivio in memoria vero (`ArchivioDocumenti`, lo stesso dei test di runtime), l'event bus con
**tutti** gli handler registrati come in `app/main.py`, e i motori reali: niente finti sul percorso
sotto prova. Qui stanno solo i costruttori di dati (XML, righe d'estratto) e il collegamento
dell'archivio a `Database`.
"""
from __future__ import annotations

import asyncio
import json
from decimal import Decimal
from typing import Any, Dict, List, Optional

import pytest

PIVA_FORNITORE = "01234567890"
PIVA_CLIENTE = "09876543210"
INGRESSI = ("drive", "documenti")


def esegui(coro):
    """Un test sincrono, un loop: i motori sono tutti coroutine."""
    return asyncio.run(coro)


def cent(valore: Any) -> int:
    """Importo in centesimi interi, senza passare dal float."""
    return int((Decimal(str(valore)) * 100).quantize(Decimal("1")))


@pytest.fixture(params=INGRESSI)
def ingresso(request):
    return request.param


@pytest.fixture
def archivio_scenari(monkeypatch):
    """Archivio vuoto collegato a `Database`, bus eventi con gli handler di produzione."""
    from app.database import Database
    from app.services import event_bus
    from app.services.archivio_documenti_memoria import ArchivioDocumenti

    db = ArchivioDocumenti("scenari_funzionali")
    monkeypatch.setattr(Database, "db", db, raising=False)
    monkeypatch.setattr(Database, "client", db, raising=False)
    monkeypatch.setattr(event_bus, "_handlers", {})
    event_bus.register_all_handlers()

    # Le fatture di prova sono del 2026: l'anno attivo non dipende dal giorno in cui gira il collaudo.
    from app.services import config_import

    async def _anno_attivo(_db):
        return 2026

    monkeypatch.setattr(config_import, "get_anno_importazione_attivo", _anno_attivo)
    return db


def xml_fattura(
    numero: str = "123", data: str = "2026-09-10", imponibile: str = "100.00",
    iva: str = "22.00", totale: str = "122.00", tipo: str = "TD01",
    piva: str = PIVA_FORNITORE, nome: str = "FORNITORE TEST SRL",
    descrizione: str = "Farina 00", ritenuta: Optional[str] = None,
    ritenuta_aliquota: str = "20.00", netto_a_pagare: Optional[str] = None,
    fattura_collegata: Optional[str] = None,
) -> bytes:
    """FatturaPA minima ma completa (cedente, cessionario, una riga, riepilogo IVA)."""
    blocco_ritenuta = ""
    if ritenuta:
        blocco_ritenuta = (
            "<DatiRitenuta><TipoRitenuta>RT01</TipoRitenuta>"
            f"<ImportoRitenuta>{ritenuta}</ImportoRitenuta>"
            f"<AliquotaRitenuta>{ritenuta_aliquota}</AliquotaRitenuta>"
            "<CausalePagamento>A</CausalePagamento></DatiRitenuta>"
        )
    blocco_collegata = ""
    if fattura_collegata:
        blocco_collegata = (f"<DatiFattureCollegate><IdDocumento>{fattura_collegata}</IdDocumento>"
                            "</DatiFattureCollegate>")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<p:FatturaElettronica xmlns:p="ns"><FatturaElettronicaHeader><CedentePrestatore><DatiAnagrafici>
<IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>{piva}</IdCodice></IdFiscaleIVA>
<Anagrafica><Denominazione>{nome}</Denominazione></Anagrafica></DatiAnagrafici></CedentePrestatore>
<CessionarioCommittente><DatiAnagrafici><IdFiscaleIVA><IdCodice>{PIVA_CLIENTE}</IdCodice></IdFiscaleIVA>
</DatiAnagrafici></CessionarioCommittente></FatturaElettronicaHeader>
<FatturaElettronicaBody><DatiGenerali><DatiGeneraliDocumento><TipoDocumento>{tipo}</TipoDocumento>
<Divisa>EUR</Divisa><Data>{data}</Data><Numero>{numero}</Numero>{blocco_ritenuta}
<ImportoTotaleDocumento>{totale}</ImportoTotaleDocumento></DatiGeneraliDocumento>{blocco_collegata}</DatiGenerali>
<DatiBeniServizi><DettaglioLinee><NumeroLinea>1</NumeroLinea><Descrizione>{descrizione}</Descrizione>
<PrezzoUnitario>{imponibile}</PrezzoUnitario><PrezzoTotale>{imponibile}</PrezzoTotale>
<AliquotaIVA>22.00</AliquotaIVA></DettaglioLinee>
<DatiRiepilogo><AliquotaIVA>22.00</AliquotaIVA><ImponibileImporto>{imponibile}</ImponibileImporto>
<Imposta>{iva}</Imposta></DatiRiepilogo></DatiBeniServizi></FatturaElettronicaBody>
</p:FatturaElettronica>""".encode("utf-8")


async def crea_fornitore(db, *, metodo: Optional[str] = "bonifico", piva: str = PIVA_FORNITORE,
                         nome: str = "FORNITORE TEST SRL", id_: Any = "forn-1",
                         **extra) -> Dict[str, Any]:
    doc = {"id": id_, "partita_iva": piva, "ragione_sociale": nome,
           "iban": "IT60X0542811101000000123456", **extra}
    if metodo is not None:
        doc["metodo_pagamento"] = metodo
    await db["fornitori"].insert_one(dict(doc))
    return doc


async def importa_xml(db, contenuto: bytes, nome_file: str = "fattura.xml",
                      sorgente: str = "drive") -> Dict[str, Any]:
    """L'ingresso reale delle fatture: la stessa pipeline della cartella unica Drive."""
    from app.routers.invoices.fatture_upload import process_xml_bytes

    return await process_xml_bytes(db, contenuto, nome_file, source=sorgente)


async def importa(db, contenuto: bytes, ingresso: str = "drive", nome_file: str = "fattura.xml") -> Dict[str, Any]:
    """Una fattura XML per ognuno dei due ingressi reali, con lo stesso esito normalizzato.

    * ``drive``: `process_xml_bytes` (cartella unica via Drive, upload bulk, posta);
    * ``documenti``: `Documenti > Import` (`upload_documento_automatico` -> `process_fattura_to_db`).

    Esito: ``status`` in {imported, duplicate, error} e, se importata, ``id`` della fattura.
    """
    if ingresso == "drive":
        esito = await importa_xml(db, contenuto, nome_file)
        return {"status": esito["status"], "id": esito.get("id"), "grezzo": esito}

    import io

    from fastapi import UploadFile

    from app.routers import documenti

    prima = {str(f.get("id")) for f in await db["invoices"].find({}, {"_id": 0, "id": 1}).to_list(None)}
    esito = await documenti.upload_documento_automatico(
        file=UploadFile(filename=nome_file, file=io.BytesIO(contenuto)))
    nuove = [f for f in await db["invoices"].find({}, {"_id": 0, "id": 1}).to_list(None)
             if str(f.get("id")) not in prima]
    if esito.get("duplicate"):
        stato = "duplicate"
    elif esito.get("imported") and nuove:
        stato = "imported"
    else:
        stato = "error"
    return {"status": stato, "id": nuove[0]["id"] if nuove else None, "grezzo": esito}


async def fattura(db, fattura_id: Any) -> Dict[str, Any]:
    trovata = await db["invoices"].find_one({"id": {"$in": [fattura_id, str(fattura_id)]}}, {"_id": 0})
    assert trovata is not None, f"fattura {fattura_id!r} assente"
    trovata.pop("xml_raw", None)
    return trovata


async def tutti(db, collezione: str, filtro: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    return await db[collezione].find(filtro or {}, {"_id": 0}).to_list(None)


# ── estratto conto ───────────────────────────────────────────────────────────

INTESTAZIONE_CSV = ("Ragione Sociale;Data contabile;Data valuta;Banca;Rapporto;"
                    "Importo;Divisa;Descrizione;Categoria/sottocategoria;Hashtag")


class FileCsv:
    """Un upload CSV dell'export operativo della banca (evidenza «provvisoria»)."""
    skip_duplicate_repairs = True

    def __init__(self, righe: List[str], nome: str = "ElencoEntrateUsciteAndamento_30-09-2026.csv"):
        self.filename = nome
        self._contenuto = ("\r\n".join([INTESTAZIONE_CSV, *righe]) + "\r\n").encode("utf-8")

    async def read(self):
        return self._contenuto


def riga_csv(descrizione: str, importo: str, giorno: str = "15/09/2026") -> str:
    return f"CERALDI GROUP S.R.L.;{giorno};{giorno};BPM;5462;{importo};EUR;{descrizione};;"


class FilePdf:
    """Un upload PDF dell'estratto ufficiale: il contenuto lo restituisce il parser sostituito."""
    skip_duplicate_repairs = True

    def __init__(self, nome: str = "Estratto conto corrente_30-09-2026.pdf"):
        self.filename = nome

    async def read(self):
        return b"%PDF-1.4 finto"


def parser_pdf_con(monkeypatch, transazioni: List[Dict[str, Any]]) -> None:
    """Il PDF BPM «letto» e' quello che si dichiara: il parser per coordinate ha i suoi test."""
    from app.parsers import estratto_conto_bpm_parser as parser_bpm

    monkeypatch.setattr(parser_bpm, "parse_estratto_conto_bpm", lambda _contenuto: {
        "success": True, "tipo_documento": "estratto_conto_banco_bpm",
        "totale_transazioni": len(transazioni), "transazioni": transazioni,
    })
    # l'endpoint prova in ordine BPM, BNL, Nexi: gli altri due non devono nemmeno aprire il finto PDF
    from app.parsers import estratto_conto_bnl_parser, estratto_conto_nexi_parser

    monkeypatch.setattr(estratto_conto_bnl_parser, "parse_estratto_conto_bnl",
                        lambda _contenuto: {"success": False, "error": "non BNL"})
    monkeypatch.setattr(estratto_conto_nexi_parser.EstrattoContoNexiParser, "parse_pdf",
                        lambda self, _contenuto: {"success": False, "error": "non Nexi"})


def transazione_pdf(data: str, descrizione: str, importo: float, tipo: Optional[str] = None) -> Dict[str, Any]:
    return {"data": data, "data_valuta": data, "descrizione": descrizione, "importo": importo,
            "tipo": tipo or ("uscita" if importo < 0 else "entrata"), "banca": "Banco BPM", "divisa": "EUR"}


async def importa_estratto(file) -> Dict[str, Any]:
    """L'ingresso reale dell'estratto conto, poi si attende il ripasso accodato in sottofondo."""
    from app.routers.bank import estratto_conto
    from app.services.reconciliation_orchestrator import attendi_riconciliazione_estratti

    esito = await estratto_conto.import_estratto_conto(file)
    await attendi_riconciliazione_estratti()
    return esito


def ripulisci(valore: Any) -> str:
    return json.dumps(valore, default=str, ensure_ascii=False)


# ── HTTP ─────────────────────────────────────────────────────────────────────

def app_con(*montaggi):
    """Un'app FastAPI con i router veri, ognuno col suo prefisso: `app_con((router, "/api/x"), ...)`."""
    from fastapi import FastAPI

    app = FastAPI()
    for router, prefisso in montaggi:
        app.include_router(router, prefix=prefisso)
    return app


async def richiesta(app, metodo: str, url: str, **kw):
    """Una chiamata HTTP vera (TestClient) dentro un test asincrono: gira in un thread, l'archivio e' lo stesso."""
    from fastapi.testclient import TestClient

    def _chiama():
        return TestClient(app).request(metodo, url, **kw)

    return await asyncio.to_thread(_chiama)


def app_prima_nota():
    from app.routers.prima_nota_module import router

    return app_con((router, "/api/prima-nota"))


def app_assegni():
    from app.routers.bank.assegni import router

    return app_con((router, "/api/assegni"))


def e_pagata_su_ogni_campo(fattura: Dict[str, Any]) -> bool:
    """Vero se `e_pagata` e nessuno dei cinque campi di stato dice «da pagare»."""
    from app.services.stato_pagamento_fattura import (
        CAMPI_BOOLEANI, CAMPI_STATO, PAROLE_DA_PAGARE, e_pagata,
    )

    if not e_pagata(fattura):
        return False
    for campo in CAMPI_STATO:
        if str(fattura.get(campo) or "").strip().lower() in PAROLE_DA_PAGARE:
            return False
    return not any(fattura.get(c) is False for c in CAMPI_BOOLEANI)


async def righe_che_contano(db, collezione: str, fattura_id: Any) -> List[Dict[str, Any]]:
    """Le righe di Prima Nota di una fattura che pesano davvero (non provvisorie, non cancellate)."""
    righe = await tutti(db, collezione)
    return [
        r for r in righe
        if str(r.get("fattura_id")) == str(fattura_id)
        and r.get("status") not in ("deleted", "archived")
        and r.get("in_attesa_estratto_ufficiale") is not True
        and r.get("stato") != "DA_VERIFICARE"
    ]
