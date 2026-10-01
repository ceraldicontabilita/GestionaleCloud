"""Distinta bonifici fornitori: un file SEPA da caricare in banca, niente di piu'.

Il gestionale non paga: scrive l'ordine (``pain.001.001.03``) che il titolare
carica a mano nell'home banking. Nessuna fattura cambia stato qui; la prova
del pagamento resta l'addebito sull'estratto conto, che i motori di
riconciliazione trovano da soli (i numeri di fattura sono nella causale).

- Un bonifico per fornitore, con i numeri delle fatture in causale.
- L'IBAN si cerca in quest'ordine: anagrafica del fornitore, XML della
  fattura (``pagamento`` e rate), un'altra fattura dello stesso fornitore.
  Ogni IBAN passa il check digit MOD 97: uno sbagliato scarta il fornitore,
  non si «corregge».
- Note di credito, fatture pagate o non attive, residuo zero e IBAN mancante
  sono scarti dichiarati con il motivo, mai silenziosi.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Iterable, List, Optional, Tuple
from xml.sax.saxutils import escape

from app.services.fattura_attiva import e_fattura_attiva, e_nota_credito
from app.services.prima_nota_integrity import totale_pagabile_al_fornitore
from app.services.stato_pagamento_fattura import e_annullata, e_pagata
from app.utils.iban import iban_mod97_valido
from app.utils.id_fattura import filtro_id

CENT = Decimal("0.01")
CAUSALE_MAX = 140
NOME_MAX = 70
_NON_SEPA = re.compile(r"[^A-Za-z0-9/\-?:().,'+ ]")


def testo_sepa(valore: Any, massimo: int) -> str:
    """Il set di caratteri SEPA: niente accenti, niente simboli, spazi singoli."""
    testo = unicodedata.normalize("NFKD", str(valore or "")).encode("ascii", "ignore").decode()
    testo = _NON_SEPA.sub(" ", testo.replace("&", "e"))
    return " ".join(testo.split())[:massimo].strip()


def _iban(valore: Any) -> str:
    return "".join(c for c in str(valore or "") if c.isalnum()).upper()


def _decimale(valore: Any) -> Decimal:
    try:
        return Decimal(str(valore)).quantize(CENT, rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal("0.00")


def residuo_da_pagare(fattura: Dict[str, Any]) -> Decimal:
    """Netto al fornitore (ritenuta esclusa) meno quanto gia' pagato."""
    if fattura.get("importo_residuo") not in (None, ""):
        return max(_decimale(fattura["importo_residuo"]), Decimal("0.00"))
    pagabile = _decimale(totale_pagabile_al_fornitore(dict(fattura)))
    pagato = _decimale(fattura.get("importo_pagato") or 0)
    return max(pagabile - pagato, Decimal("0.00"))


def _piva(fattura: Dict[str, Any]) -> str:
    return re.sub(r"\W", "", str(fattura.get("supplier_vat") or fattura.get("cedente_piva") or "")).upper()


def iban_dalla_fattura(fattura: Dict[str, Any]) -> str:
    """Il primo IBAN scritto nell'XML: ``pagamento`` o una delle rate."""
    candidati = [((fattura.get("pagamento") or {}).get("iban") if isinstance(fattura.get("pagamento"), dict) else None)]
    for rata in fattura.get("pagamento_rate") or []:
        if isinstance(rata, dict):
            candidati.append(rata.get("iban"))
    for candidato in candidati:
        if _iban(candidato):
            return _iban(candidato)
    return ""


async def risolvi_iban(
    db, fattura: Dict[str, Any], cache: Optional[Dict[str, Tuple[str, str]]] = None,
) -> Tuple[str, str]:
    """``(iban, fonte)``; ``("", motivo)`` se nessuna fonte ne ha uno valido.

    Un IBAN presente ma col check digit sbagliato non fa cercare oltre: e'
    un dato da correggere nell'anagrafica, non da scavalcare.
    """
    cache = {} if cache is None else cache
    piva = _piva(fattura)
    chiave = piva or f"fattura:{fattura.get('id')}"
    if chiave in cache:
        return cache[chiave]

    trovati: List[Tuple[str, str]] = []
    if piva:
        varianti = list(dict.fromkeys([piva, re.sub(r"^IT(?=\d{11}$)", "", piva)]))
        fornitore = await db["fornitori"].find_one(
            {"$or": [{"partita_iva": {"$in": varianti}}, {"piva": {"$in": varianti}}]},
            {"_id": 0, "iban": 1},
        )
        if fornitore and _iban(fornitore.get("iban")):
            trovati.append((_iban(fornitore["iban"]), "anagrafica_fornitore"))
    if iban_dalla_fattura(fattura):
        trovati.append((iban_dalla_fattura(fattura), "xml_fattura"))
    if not trovati and piva:
        async for altra in db["invoices"].find(
            {"supplier_vat": piva},
            {"_id": 0, "pagamento": 1, "pagamento_rate": 1, "invoice_date": 1},
        ).sort("invoice_date", -1):
            iban = iban_dalla_fattura(altra)
            if iban:
                trovati.append((iban, "fattura_precedente"))
                break

    esito: Tuple[str, str] = ("", "iban_mancante")
    if trovati:
        iban, fonte = trovati[0]
        esito = (iban, fonte) if iban_mod97_valido(iban) else ("", f"iban_non_valido:{fonte}")
    cache[chiave] = esito
    return esito


def _numero(fattura: Dict[str, Any]) -> str:
    return str(fattura.get("invoice_number") or fattura.get("numero_documento") or "").strip()


def causale_bonifico(numeri: Iterable[str]) -> str:
    """«Saldo fatture 386, 738»: i numeri interi, cosi' la riconciliazione li
    ritrova; se non entrano nei 140 caratteri si dice quante sono."""
    numeri = [n for n in numeri if n]
    etichetta = "Saldo fattura" if len(numeri) == 1 else "Saldo fatture"
    causale = testo_sepa(f"{etichetta} {', '.join(numeri)}", 1000)
    if len(causale) <= CAUSALE_MAX:
        return causale
    presi: List[str] = []
    for numero in numeri:
        prova = testo_sepa(f"Saldo fatture {', '.join(presi + [numero])} e altre", 1000)
        if len(prova) > CAUSALE_MAX:
            break
        presi.append(numero)
    return testo_sepa(f"Saldo fatture {', '.join(presi)} e altre {len(numeri) - len(presi)}", CAUSALE_MAX)


async def componi_bonifici(db, fattura_ids: List[str]) -> Dict[str, Any]:
    """Raggruppa le fatture scelte in un bonifico per fornitore."""
    cache: Dict[str, Tuple[str, str]] = {}
    gruppi: Dict[str, Dict[str, Any]] = {}
    scartate: List[Dict[str, Any]] = []
    for fid in dict.fromkeys(str(i) for i in fattura_ids if i):
        fattura = await db["invoices"].find_one(filtro_id(fid), {"_id": 0, "xml_content": 0})
        if not fattura:
            scartate.append({"id": fid, "motivo": "fattura_non_trovata"})
            continue
        base = {"id": fid, "numero": _numero(fattura), "fornitore": fattura.get("supplier_name")}
        if not e_fattura_attiva(fattura):
            scartate.append({**base, "motivo": "fattura_non_attiva"})
            continue
        if e_nota_credito(fattura):
            scartate.append({**base, "motivo": "nota_di_credito"})
            continue
        if e_pagata(fattura) or e_annullata(fattura):
            scartate.append({**base, "motivo": "gia_pagata_o_annullata"})
            continue
        importo = residuo_da_pagare(fattura)
        if importo <= 0:
            scartate.append({**base, "motivo": "residuo_zero"})
            continue
        iban, fonte = await risolvi_iban(db, fattura, cache)
        if not iban:
            scartate.append({**base, "motivo": fonte})
            continue
        chiave = _piva(fattura) or iban
        gruppo = gruppi.setdefault(chiave, {
            "fornitore": testo_sepa(fattura.get("supplier_name"), NOME_MAX) or "Fornitore",
            "partita_iva": _piva(fattura),
            "iban": iban,
            "fonte_iban": fonte,
            "fatture": [],
            "importo": Decimal("0.00"),
        })
        gruppo["fatture"].append({**base, "importo": str(importo),
                                  "data": str(fattura.get("invoice_date") or "")[:10]})
        gruppo["importo"] += importo

    bonifici = []
    for gruppo in sorted(gruppi.values(), key=lambda g: g["fornitore"]):
        gruppo["fatture"].sort(key=lambda f: (f["data"], f["numero"]))
        gruppo["causale"] = causale_bonifico(f["numero"] for f in gruppo["fatture"])
        gruppo["importo"] = str(gruppo["importo"])
        bonifici.append(gruppo)
    totale = sum((Decimal(b["importo"]) for b in bonifici), Decimal("0.00"))
    return {"bonifici": bonifici, "scartate": scartate, "totale": str(totale),
            "numero_bonifici": len(bonifici)}


def xml_pain001(
    bonifici: List[Dict[str, Any]], *, iban_ordinante: str, nome_ordinante: str,
    data_esecuzione: str, adesso: Optional[datetime] = None,
) -> str:
    """``pain.001.001.03`` con un solo lotto (PmtInf) e un bonifico per riga."""
    iban_ordinante = _iban(iban_ordinante)
    if not iban_mod97_valido(iban_ordinante):
        raise ValueError("IBAN ordinante non valido")
    nome = testo_sepa(nome_ordinante, NOME_MAX)
    if not nome:
        raise ValueError("Nome ordinante obbligatorio")
    datetime.strptime(data_esecuzione, "%Y-%m-%d")
    if not bonifici:
        raise ValueError("Nessun bonifico da mettere in distinta")
    adesso = adesso or datetime.now(timezone.utc)
    msg_id = "DIST" + adesso.strftime("%Y%m%d%H%M%S")
    totale = sum((Decimal(b["importo"]) for b in bonifici), Decimal("0.00"))
    righe = []
    for indice, b in enumerate(bonifici, start=1):
        righe.append(f"""      <CdtTrfTxInf>
        <PmtId><InstrId>{indice}</InstrId><EndToEndId>{escape(msg_id)}-{indice}</EndToEndId></PmtId>
        <Amt><InstdAmt Ccy="EUR">{Decimal(b['importo']):.2f}</InstdAmt></Amt>
        <Cdtr><Nm>{escape(testo_sepa(b['fornitore'], NOME_MAX))}</Nm></Cdtr>
        <CdtrAcct><Id><IBAN>{escape(_iban(b['iban']))}</IBAN></Id></CdtrAcct>
        <RmtInf><Ustrd>{escape(testo_sepa(b['causale'], CAUSALE_MAX))}</Ustrd></RmtInf>
      </CdtTrfTxInf>""")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:pain.001.001.03">
  <CstmrCdtTrfInitn>
    <GrpHdr>
      <MsgId>{msg_id}</MsgId>
      <CreDtTm>{adesso.strftime('%Y-%m-%dT%H:%M:%S')}</CreDtTm>
      <NbOfTxs>{len(bonifici)}</NbOfTxs>
      <CtrlSum>{totale:.2f}</CtrlSum>
      <InitgPty><Nm>{escape(nome)}</Nm></InitgPty>
    </GrpHdr>
    <PmtInf>
      <PmtInfId>{msg_id}-1</PmtInfId>
      <PmtMtd>TRF</PmtMtd>
      <NbOfTxs>{len(bonifici)}</NbOfTxs>
      <CtrlSum>{totale:.2f}</CtrlSum>
      <PmtTpInf><SvcLvl><Cd>SEPA</Cd></SvcLvl></PmtTpInf>
      <ReqdExctnDt>{data_esecuzione}</ReqdExctnDt>
      <Dbtr><Nm>{escape(nome)}</Nm></Dbtr>
      <DbtrAcct><Id><IBAN>{iban_ordinante}</IBAN></Id></DbtrAcct>
      <DbtrAgt><FinInstnId><Othr><Id>NOTPROVIDED</Id></Othr></FinInstnId></DbtrAgt>
      <ChrgBr>SLEV</ChrgBr>
{chr(10).join(righe)}
    </PmtInf>
  </CstmrCdtTrfInitn>
</Document>
"""


async def candidate(db) -> List[Dict[str, Any]]:
    """Fatture attive non pagate con residuo, per la scelta nella pagina."""
    from app.document_repository import metadata_projection
    from app.services.fattura_attiva import FILTRO_FATTURA_ATTIVA
    from app.services.stato_pagamento_fattura import FILTRO_NON_PAGATE

    righe = await db["invoices"].find(
        {"$and": [FILTRO_FATTURA_ATTIVA, FILTRO_NON_PAGATE]},
        metadata_projection("invoices"),
    ).to_list(None)
    cache: Dict[str, Tuple[str, str]] = {}
    out = []
    for fattura in righe:
        if e_nota_credito(fattura) or e_annullata(fattura) or e_pagata(fattura):
            continue
        importo = residuo_da_pagare(fattura)
        if importo <= 0:
            continue
        iban, fonte = await risolvi_iban(db, fattura, cache)
        out.append({
            "id": fattura.get("id"), "numero": _numero(fattura),
            "data": str(fattura.get("invoice_date") or "")[:10],
            "fornitore": fattura.get("supplier_name"), "partita_iva": _piva(fattura),
            "importo": str(importo), "iban": iban, "fonte_iban": fonte,
            "metodo_pagamento": fattura.get("metodo_pagamento"),
        })
    out.sort(key=lambda r: (r["data"], r["numero"]), reverse=True)
    return out
