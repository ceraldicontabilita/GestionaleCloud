"""Fatture emesse: archivio, clienti e aggancio al corrispettivo dello scontrino.

Il bar fattura **dopo** aver battuto lo scontrino: il cliente paga al banco,
l'RT registra l'incasso nel corrispettivo del giorno, e la fattura arriva dopo,
a richiesta, con la causale «iva gia' in corrispettivi». Decisione del
titolare (27/09/2026): queste fatture **non aumentano le entrate**. Il ricavo
e l'IVA a debito stanno gia' nel corrispettivo, e l'incasso e' avvenuto al
banco. Contarle di nuovo raddoppierebbe ricavi e IVA. Non sono nemmeno crediti,
perche' nessuno ci deve niente.

Quindi una fattura emessa:

* si riconosce **dal contenuto**, cioe' dal cedente che e' la nostra P.IVA
  (``settings.FISCAL_COMPANY_ID``), mai dal nome del file. Prima finiva fra le
  fatture passive: «FPR 7/26» era un costo con 4,09 EUR di IVA a credito;
* vive in ``fatture_emesse`` (la collezione canonica), col cliente in
  ``clienti`` (identita' P.IVA, poi codice fiscale);
* porta lo scontrino che la copre, letto dalla causale («scontrino ... del
  10-06-2026 numero 2586-0352»). Se la causale non lo dice vale la data della
  fattura;
* si aggancia al corrispettivo **di quel giorno** solo se e' uno solo. Se sono
  piu' d'uno o manca, resta da scegliere (``DA_VERIFICARE`` / ``ATTESO``) e non
  si inventa niente.
"""
from __future__ import annotations

import hashlib
import io
import logging
import re
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict, List, Optional

from app.config import settings

logger = logging.getLogger(__name__)

COLL = "fatture_emesse"
COLL_CLIENTI = "clienti"
STATI_CORRISPETTIVO_ESCLUSI = ["deleted", "archived", "archiviata", "eliminato"]
# Stato del documento: gia' incassata al banco con lo scontrino. I lettori dei
# crediti (bilancio, flusso di cassa) cercano le fatture «non pagate»: questa
# non lo e' mai.
STATO_INCASSATA = "incassata_con_scontrino"

_MESI = {m: i for i, m in enumerate((
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
    "agosto", "settembre", "ottobre", "novembre", "dicembre"), start=1)}
_DATA_NUMERICA = re.compile(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})\b")
_DATA_A_PAROLE = re.compile(r"\b(\d{1,2})\s+(" + "|".join(_MESI) + r")\s+(\d{4})\b", re.IGNORECASE)
_NUMERO_SCONTRINO = re.compile(r"(\d{4})\s*-\s*(\d{4})")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _piva(valore: Any) -> str:
    testo = re.sub(r"\s+", "", str(valore or "")).upper()
    return testo[2:] if testo.startswith("IT") and testo[2:].isdigit() else testo


def e_fattura_emessa(parsed: Dict[str, Any]) -> bool:
    """Il cedente e' la nostra societa': la fattura l'abbiamo emessa noi."""
    nostra = _piva(settings.FISCAL_COMPANY_ID)
    fornitore = parsed.get("fornitore") or {}
    cedente = _piva(parsed.get("supplier_vat") or fornitore.get("partita_iva"))
    return bool(nostra) and cedente == nostra


def filtro_escludi_emesse() -> Dict[str, Any]:
    """Filtro di query su `invoices`: fuori le fatture con cedente = noi.

    Stesso criterio di `e_fattura_emessa`, sul campo `supplier_vat` (con e
    senza prefisso IT). Senza P.IVA configurata non esclude niente, invece di
    escludere tutto.
    """
    nostra = _piva(settings.FISCAL_COMPANY_ID)
    if not nostra:
        return {}
    return {"supplier_vat": {"$nin": [nostra, f"IT{nostra}"]}}


def _euro(valore: Any) -> float:
    try:
        return float(Decimal(str(valore or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    except Exception:  # noqa: BLE001 - un importo illeggibile resta vuoto, non zero inventato
        return 0.0


def scontrino_da_causale(causali: Any) -> Dict[str, Optional[str]]:
    """Data e numero dello scontrino scritti nella causale, se ci sono."""
    testo = " ".join(causali) if isinstance(causali, (list, tuple)) else str(causali or "")
    testo = re.sub(r"\s+", " ", testo)
    data = None
    m = _DATA_NUMERICA.search(testo)
    if m:
        giorno, mese, anno = (int(x) for x in m.groups())
        data = f"{anno:04d}-{mese:02d}-{giorno:02d}"
    else:
        m = _DATA_A_PAROLE.search(testo)
        if m:
            data = f"{int(m.group(3)):04d}-{_MESI[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"
    if data:
        try:
            datetime.strptime(data, "%Y-%m-%d")
        except ValueError:
            data = None
    numero = None
    # «scontino» senza la r c'e' nelle causali vere (FPR 7/26, FPR 8/26).
    if re.search(r"scontr?in", testo, re.IGNORECASE):
        n = _NUMERO_SCONTRINO.search(testo)
        if n:
            numero = f"{n.group(1)}-{n.group(2)}"
    return {"data": data, "numero": numero}


def id_fattura_emessa(numero: str, data: str) -> str:
    """Stabile: la stessa fattura ricaricata da un'altra copia ha lo stesso id."""
    chiave = f"{_piva(settings.FISCAL_COMPANY_ID)}|{str(numero).strip().upper()}|{str(data)[:10]}"
    return "FE-" + hashlib.sha256(chiave.encode("utf-8")).hexdigest()[:24]


def id_cliente(piva: str, codice_fiscale: str, denominazione: str) -> Optional[str]:
    """Identita' del cliente: P.IVA, poi codice fiscale. Senza nessuno dei due
    non si crea un'anagrafica: un nome da solo non e' un'identita'."""
    for tipo, valore in (("piva", _piva(piva)), ("cf", str(codice_fiscale or "").strip().upper())):
        if valore:
            return f"CLI-{tipo}-{valore}"
    return None


async def salva_cliente(db, dati: Dict[str, Any], fonte: str) -> Optional[str]:
    """Crea o completa un cliente. Non sovrascrive un valore gia' presente."""
    cid = id_cliente(dati.get("partita_iva"), dati.get("codice_fiscale"), dati.get("denominazione"))
    if not cid:
        return None
    esistente = await db[COLL_CLIENTI].find_one({"id": cid}, {"_id": 0}) or {}
    patch: Dict[str, Any] = {}
    for campo, valore in dati.items():
        if valore in (None, "", [], {}):
            continue
        if esistente.get(campo) in (None, "", [], {}):
            patch[campo] = valore
    if not esistente:
        patch.update({"id": cid, "created_at": _now(), "fonti": [fonte]})
    elif fonte not in (esistente.get("fonti") or []):
        patch["fonti"] = list(esistente.get("fonti") or []) + [fonte]
    if patch:
        patch["updated_at"] = _now()
        await db[COLL_CLIENTI].update_one({"id": cid}, {"$set": patch}, upsert=True)
    return cid


def _cliente_da_fattura(parsed: Dict[str, Any]) -> Dict[str, Any]:
    c = parsed.get("cliente") or {}
    return {
        "denominazione": str(c.get("denominazione") or "").strip().strip('"') or None,
        "partita_iva": _piva(c.get("partita_iva")) or None,
        "codice_fiscale": str(c.get("codice_fiscale") or "").strip().upper() or None,
        "indirizzo": c.get("indirizzo") or None,
        "cap": c.get("cap") or None,
        "comune": c.get("comune") or None,
        "provincia": c.get("provincia") or None,
        "nazione": c.get("nazione") or None,
    }


async def corrispettivi_del_giorno(db, data: str) -> List[Dict[str, Any]]:
    return await db["corrispettivi"].find(
        {"data": data, "status": {"$nin": STATI_CORRISPETTIVO_ESCLUSI}},
        {"_id": 0, "id": 1, "data": 1, "totale": 1, "status": 1},
    ).to_list(20)


async def aggancia_corrispettivo(db, fattura: Dict[str, Any]) -> Dict[str, Any]:
    """Collega la fattura al corrispettivo del giorno dello scontrino.

    Una scelta fatta a mano (``scelto_da_titolare``) non si tocca mai."""
    stato = fattura.get("corrispettivo") or {}
    if stato.get("scelto_da_titolare"):
        return stato
    giorno = (fattura.get("scontrino") or {}).get("data") or fattura.get("data_fattura")
    candidati = await corrispettivi_del_giorno(db, giorno) if giorno else []
    if len(candidati) == 1:
        nuovo = {"stato": "SODDISFATTO", "corrispettivo_id": candidati[0].get("id"),
                 "data": giorno, "totale_corrispettivo": candidati[0].get("totale"),
                 "motivo": "unico corrispettivo del giorno dello scontrino"}
    elif candidati:
        nuovo = {"stato": "DA_VERIFICARE", "data": giorno,
                 "candidati": [c.get("id") for c in candidati],
                 "motivo": f"{len(candidati)} corrispettivi lo stesso giorno: scegli quale"}
    else:
        nuovo = {"stato": "ATTESO", "data": giorno,
                 "motivo": "corrispettivo del giorno non ancora in archivio"}
    if nuovo != stato:
        nuovo["aggiornato_at"] = _now()
        await db[COLL].update_one({"id": fattura["id"]}, {"$set": {"corrispettivo": nuovo}})
    return nuovo


async def scegli_corrispettivo(db, fattura_id: str, corrispettivo_id: str) -> Dict[str, Any]:
    """La scelta del titolare fra i candidati: vince su ogni aggancio automatico."""
    fattura = await db[COLL].find_one({"id": fattura_id}, {"_id": 0, "id": 1})
    if not fattura:
        return {"success": False, "errore": "fattura emessa non trovata"}
    corr = await db["corrispettivi"].find_one(
        {"id": corrispettivo_id, "status": {"$nin": STATI_CORRISPETTIVO_ESCLUSI}},
        {"_id": 0, "id": 1, "data": 1, "totale": 1})
    if not corr:
        return {"success": False, "errore": "corrispettivo non trovato"}
    stato = {"stato": "SODDISFATTO", "corrispettivo_id": corr["id"], "data": corr.get("data"),
             "totale_corrispettivo": corr.get("totale"), "scelto_da_titolare": True,
             "motivo": "scelto dal titolare", "aggiornato_at": _now()}
    await db[COLL].update_one({"id": fattura_id}, {"$set": {"corrispettivo": stato}})
    return {"success": True, "corrispettivo": stato}


async def registra_fattura_emessa(db, parsed: Dict[str, Any], *, xml_raw: str,
                                  filename: str, source: str) -> Dict[str, Any]:
    """Archivia una fattura emessa (idempotente per numero e data)."""
    numero = str(parsed.get("invoice_number") or "").strip()
    data = str(parsed.get("invoice_date") or "")[:10]
    if not numero or not data:
        return {"status": "error", "error": "fattura emessa senza numero o data"}
    fid = id_fattura_emessa(numero, data)
    esistente = await db[COLL].find_one({"id": fid}, {"_id": 0, "id": 1, "corrispettivo": 1,
                                                       "scontrino": 1, "data_fattura": 1})
    if esistente:
        await aggancia_corrispettivo(db, esistente)
        return {"status": "duplicate", "fattura_emessa_id": fid, "numero": numero}

    cliente = _cliente_da_fattura(parsed)
    cliente_id = await salva_cliente(db, cliente, "fattura_emessa")
    scontrino = scontrino_da_causale(parsed.get("causali"))
    scontrino["fonte"] = "causale" if scontrino.get("data") else "data_fattura"
    documento = {
        "id": fid,
        "numero_fattura": numero,
        "data_fattura": data,
        "anno": int(data[:4]),
        "tipo_documento": parsed.get("tipo_documento"),
        "cliente": cliente,
        "cliente_id": cliente_id,
        "cliente_nome": cliente.get("denominazione"),
        "imponibile": _euro(parsed.get("imponibile")),
        "iva": _euro(parsed.get("iva")),
        "totale": _euro(parsed.get("total_amount")),
        "righe": parsed.get("linee") or [],
        "riepilogo_iva": parsed.get("riepilogo_iva") or [],
        "causale": " ".join(parsed.get("causali") or []),
        "pagamento_modalita": (parsed.get("pagamento") or {}).get("modalita"),
        "scontrino": scontrino,
        # Ricavo e IVA sono gia' nel corrispettivo, l'incasso e' avvenuto al banco.
        "gia_in_corrispettivi": True,
        "incide_su_ricavi": False,
        "stato": STATO_INCASSATA,
        # Pagata al banco: per bilancio, flusso di cassa e crediti non e' un credito.
        "pagato": True,
        "stato_pagamento": "pagata",
        "xml_raw": xml_raw,
        "content_sha256": hashlib.sha256(xml_raw.encode("utf-8")).hexdigest(),
        "filename": filename,
        "source": source,
        "created_at": _now(),
    }
    await db[COLL].insert_one(dict(documento))
    documento["corrispettivo"] = await aggancia_corrispettivo(db, documento)
    logger.info("[fatture-emesse] %s del %s a %s: archiviata (%s)",
                numero, data, cliente.get("denominazione"), documento["corrispettivo"]["stato"])
    return {"status": "fattura_emessa", "fattura_emessa_id": fid, "numero": numero,
            "cliente": cliente.get("denominazione"), "corrispettivo": documento["corrispettivo"]}


async def togli_dalle_passive(db) -> Dict[str, Any]:
    """Le fatture emesse finite fra le passive (prima che esistesse questo
    riconoscimento) passano in ``fatture_emesse``; in ``invoices`` la copia si
    archivia, mai si cancella, la scrittura si storna e partite e scadenze
    sparite dagli elenchi dei debiti. Idempotente."""
    from app.parsers.fattura_elettronica_parser import parse_fattura_xml
    from app.services.registrazione_contabile import storna_registrazione_fattura

    nostra = _piva(settings.FISCAL_COMPANY_ID)
    candidate = await db["invoices"].find(
        {"supplier_vat": {"$in": [nostra, f"IT{nostra}"]},
         "status": {"$nin": ["archived", "archiviata", "deleted"]}},
        {"_id": 0, "id": 1, "invoice_number": 1, "filename": 1, "source": 1},
    ).to_list(500)
    spostate, errori = [], []
    for inv in candidate:
        fid = inv.get("id")
        try:
            completo = await db["invoices"].find_one({"id": fid}, {"_id": 0, "xml_raw": 1})
            xml = (completo or {}).get("xml_raw")
            if xml:
                parsed = parse_fattura_xml(xml)
                if not parsed.get("error") and e_fattura_emessa(parsed):
                    await registra_fattura_emessa(db, parsed, xml_raw=xml,
                                                  filename=inv.get("filename") or "",
                                                  source="correzione_da_passive")
            ora = _now()
            await db["invoices"].update_one({"id": fid}, {"$set": {
                "status": "archived", "entity_status": "archived",
                "deleted_reason": "fattura_emessa_non_passiva", "archived_at": ora}})
            await storna_registrazione_fattura(
                db, fid, "fattura emessa da Ceraldi Group, non e' un acquisto")
            for coll in ("prima_nota_cassa", "prima_nota_banca", "scadenziario_fornitori"):
                await db[coll].update_many(
                    {"fattura_id": fid, "status": {"$nin": ["deleted", "archived"]}},
                    {"$set": {"status": "archived", "entity_status": "archived",
                              "deleted_reason": "derivato_da_fattura_emessa", "archived_at": ora}})
            await db["partite_aperte"].update_many(
                {"documento_id": fid, "stato": {"$in": ["aperta", "parziale", "da_verificare"]}},
                {"$set": {"stato": "chiusa", "residuo": 0, "motivo_chiusura":
                          "documento non passivo: fattura emessa da Ceraldi Group", "updated_at": ora}})
            spostate.append(inv.get("invoice_number"))
        except Exception as exc:  # noqa: BLE001 - una fattura non ferma le altre, e resta scritta
            logger.error("[fatture-emesse] %s non tolta dalle passive: %s: %s",
                         fid, type(exc).__name__, exc)
            errori.append(f"{inv.get('invoice_number')}: {type(exc).__name__}")
    return {"spostate": spostate, "errori": errori}


async def riallinea(db) -> Dict[str, Any]:
    """Il giro di rete: passive sbagliate e agganci ancora aperti (il
    corrispettivo di quel giorno puo' arrivare dopo la fattura)."""
    esito = await togli_dalle_passive(db)
    aperte = await db[COLL].find(
        {"corrispettivo.stato": {"$in": ["ATTESO", "DA_VERIFICARE"]}},
        {"_id": 0, "id": 1, "corrispettivo": 1, "scontrino": 1, "data_fattura": 1},
    ).to_list(2000)
    agganciate = 0
    for f in aperte:
        agganciate += (await aggancia_corrispettivo(db, f)).get("stato") == "SODDISFATTO"
    return {**esito, "riesaminate": len(aperte), "agganciate": agganciate}


# ---------------------------------------------------------------------------
# Anagrafica clienti dal report del portale (ReportClienti.xls)
# ---------------------------------------------------------------------------

_COLONNE_CLIENTI = {
    "Tipo Cliente": "tipo_cliente", "Indirizzo telematico": "codice_destinatario",
    "Email": "email", "PEC": "pec", "Telefono": "telefono", "ID Paese": "id_paese",
    "Partita Iva": "partita_iva", "Codice Fiscale": "codice_fiscale",
    "Denominazione": "denominazione", "Nome": "nome", "Cognome": "cognome",
    "Nazione": "nazione", "CAP": "cap", "Provincia": "provincia", "Comune": "comune",
    "Indirizzo": "indirizzo", "Numero civico": "numero_civico",
    "Condizioni di pagamento": "condizioni_pagamento",
    "Metodo di pagamento": "metodo_pagamento", "Banca": "banca",
}
MARCATORI_REPORT_CLIENTI = ("CODICE CLIENTE", "TIPO CLIENTE", "PARTITA IVA", "DENOMINAZIONE")


def _testo_cella(valore: Any) -> Optional[str]:
    if valore is None:
        return None
    testo = str(valore).strip()
    if testo.lower() in ("", "nan", "none"):
        return None
    if re.fullmatch(r"\d+\.0", testo):  # numeri letti come float da Excel
        testo = testo[:-2]
    return testo.strip('"').strip() or None


async def importa_report_clienti(db, content: bytes, filename: str) -> Dict[str, Any]:
    """Crea o completa i clienti dal report dell'anagrafica (xls/xlsx).
    Idempotente: il secondo import non crea niente di nuovo."""
    import pandas as pd

    engine = "xlrd" if filename.lower().endswith(".xls") else "openpyxl"
    frame = pd.read_excel(io.BytesIO(content), engine=engine, dtype=str)
    nuovi = aggiornati = senza_identita = 0
    for riga in frame.to_dict(orient="records"):
        dati = {campo: _testo_cella(riga.get(colonna)) for colonna, campo in _COLONNE_CLIENTI.items()}
        if dati.get("partita_iva"):
            dati["partita_iva"] = _piva(dati["partita_iva"])
        if dati.get("codice_fiscale"):
            dati["codice_fiscale"] = dati["codice_fiscale"].upper()
        if not dati.get("denominazione"):
            nome = " ".join(x for x in (dati.get("nome"), dati.get("cognome")) if x)
            dati["denominazione"] = nome or None
        cid = id_cliente(dati.get("partita_iva"), dati.get("codice_fiscale"), dati.get("denominazione"))
        if not cid:
            senza_identita += 1
            continue
        esisteva = await db[COLL_CLIENTI].find_one({"id": cid}, {"_id": 0, "id": 1})
        await salva_cliente(db, dati, "report_clienti")
        if esisteva:
            aggiornati += 1
        else:
            nuovi += 1
    return {"success": True, "righe": len(frame), "nuovi": nuovi, "gia_presenti": aggiornati,
            "senza_identita": senza_identita}
