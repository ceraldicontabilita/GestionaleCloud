"""
Parser Fattura Elettronica (FatturaPA) — Ceraldi Group
=======================================================
Estrae i dati essenziali da un XML FatturaPA per popolare la collezione
``invoices``. Gestisce:
- .xml             (FatturaPA testuale)
- .p7m / .xml.p7m  (firmato CAdES: estrazione best-effort dell'XML interno)
- .zip             (contenente più fatture)

Un singolo file può contenere più ``FatturaElettronicaBody`` (fattura
cumulativa): viene restituita una riga per ciascun body.
"""
import io
import re
import zipfile
import logging
import unicodedata
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


def _norm(s: Optional[str]) -> str:
    s = (s or "").strip()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).upper()


def _strip_ns(root: ET.Element) -> ET.Element:
    """Rimuove i namespace dai tag così le ricerche sono semplici."""
    for el in root.iter():
        if isinstance(el.tag, str) and "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    return root


def _text(el: Optional[ET.Element], path: str) -> str:
    if el is None:
        return ""
    found = el.find(path)
    return (found.text or "").strip() if found is not None and found.text else ""


def _to_float(s: str) -> Optional[float]:
    if not s:
        return None
    try:
        return round(float(s.replace(",", ".")), 2)
    except ValueError:
        return None


def _extract_xml_from_p7m(raw: bytes) -> Optional[bytes]:
    """Best-effort: trova l'XML FatturaPA dentro un involucro p7m/CAdES."""
    # 1) XML testuale contiguo
    for marker in (b"<?xml", b"<p:FatturaElettronica", b"<FatturaElettronica"):
        idx = raw.find(marker)
        if idx != -1:
            end = raw.rfind(b"FatturaElettronica>")
            if end != -1:
                return raw[idx:end + len(b"FatturaElettronica>")]
    return None


def parse_xml_bytes(raw: bytes, filename: str = "") -> List[Dict[str, Any]]:
    """Parsa un singolo XML/p7m e ritorna 0..n fatture.

    Ritorna lista vuota (senza eccezione) se il file NON è una fattura
    (metadati SDI ``*_MT_*.xml`` con root ``FileMetadati``, ``daticert.xml``
    con root ``postacert``, ecc.): vanno ignorati, non contati come errore.
    """
    fn = (filename or "").lower()
    data = raw
    if fn.endswith(".p7m"):
        data = _extract_xml_from_p7m(raw) or raw
    try:
        root = _strip_ns(ET.fromstring(data))
    except ET.ParseError:
        # ultimo tentativo: forse era p7m senza estensione
        rec = _extract_xml_from_p7m(raw)
        if not rec:
            raise
        root = _strip_ns(ET.fromstring(rec))

    # Solo le fatture vere (root "FatturaElettronica"). Tutto il resto
    # (FileMetadati, postacert/daticert) viene ignorato silenziosamente.
    if root.tag != "FatturaElettronica":
        return []

    header = root.find("FatturaElettronicaHeader")
    cedente = header.find("CedentePrestatore/DatiAnagrafici") if header is not None else None
    den = _text(cedente, "Anagrafica/Denominazione")
    if not den:
        nome = _text(cedente, "Anagrafica/Nome")
        cognome = _text(cedente, "Anagrafica/Cognome")
        den = f"{cognome} {nome}".strip()
    piva = _text(cedente, "IdFiscaleIVA/IdCodice")
    cf = _text(cedente, "CodiceFiscale")

    fatture: List[Dict[str, Any]] = []
    for body in root.findall("FatturaElettronicaBody"):
        dg = body.find("DatiGenerali/DatiGeneraliDocumento")
        numero = _text(dg, "Numero")
        data_doc = _text(dg, "Data")
        tipo = _text(dg, "TipoDocumento") or "TD01"
        totale = _to_float(_text(dg, "ImportoTotaleDocumento"))

        imponibile = iva = 0.0
        for rip in body.findall("DatiBeniServizi/DatiRiepilogo"):
            imponibile += _to_float(_text(rip, "ImponibileImporto")) or 0.0
            iva += _to_float(_text(rip, "Imposta")) or 0.0
        imponibile = round(imponibile, 2)
        iva = round(iva, 2)
        if totale is None:
            totale = round(imponibile + iva, 2)

        iban = _text(body, "DatiPagamento/DettaglioPagamento/IBAN")
        scadenza = _text(body, "DatiPagamento/DettaglioPagamento/DataScadenzaPagamento")

        anno = int(data_doc[:4]) if len(data_doc) >= 4 and data_doc[:4].isdigit() else None
        fid = f"XML_{_norm(piva or cf)}_{_norm(numero)}_{data_doc}".replace(" ", "_")[:120]

        fatture.append({
            "_id": fid, "id": fid,
            "numero": numero, "data": data_doc, "data_documento": data_doc, "anno": anno,
            "tipo_documento": tipo,
            "fornitore": den, "fornitore_ragione_sociale": den, "forn_norm": _norm(den),
            "piva": piva, "codice_fiscale": cf,
            "imponibile": imponibile, "iva": iva,
            "totale": totale, "importo_totale": totale,
            "iban": iban or "", "data_scadenza": scadenza or "",
            "stato_pagamento": "da_pagare",
            "fonte": "import_xml",
        })
    return fatture


def parse_upload(raw: bytes, filename: str = "") -> List[Dict[str, Any]]:
    """Parsa un upload che può essere .xml, .p7m o .zip (più fatture)."""
    fn = (filename or "").lower()
    if fn.endswith(".zip"):
        out: List[Dict[str, Any]] = []
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            for name in z.namelist():
                nl = name.lower().rsplit("/", 1)[-1]
                if name.endswith("/") or not nl.endswith((".xml", ".p7m")):
                    continue
                if "_mt_" in nl or nl.startswith("daticert") or "metadat" in nl:
                    continue  # metadati SDI / certificazione PEC: non sono fatture
                try:
                    out.extend(parse_xml_bytes(z.read(name), name))
                except Exception as e:
                    logger.warning("Fattura XML non parsata (%s): %s", name, e)
        return out
    return parse_xml_bytes(raw, filename)
