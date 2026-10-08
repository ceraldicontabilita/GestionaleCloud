"""
Processore Fatture XML (FatturaPA)
Helper di estrazione P7M/CMS e riconoscimento filename, condivisi dalla
pipeline unica di importazione fatture (app.routers.invoices.fatture_upload).
"""
import logging
import base64

logger = logging.getLogger(__name__)

# File da ignorare (non sono FatturaPA)
FILENAME_SKIP_PATTERNS = ["daticert", "_MT_", "receipt", "segnatura"]


def is_fatturapa_filename(filename: str) -> bool:
    """Verifica che il filename sia una FatturaPA (non metadati/ricevute)."""
    fn_lower = filename.lower()
    for pattern in FILENAME_SKIP_PATTERNS:
        if pattern.lower() in fn_lower:
            return False
    # Accetta se il filename contiene il pattern FatturaPA (IT + PIVA + _HASH + .xml/.p7m)
    import re
    if re.search(r'IT\d{11}_[A-Za-z0-9]+\.xml', fn_lower):
        return True
    if fn_lower.endswith('.xml') or fn_lower.endswith('.p7m'):
        return True
    return False


def is_p7m_content(filename: str) -> bool:
    """Verifica se il file è un .p7m (anche se rinominato con .pdf)."""
    return '.xml.p7m' in filename.lower() or filename.lower().endswith('.p7m')


def _extract_cms_payload(data: bytes):
    """Estrae il contenuto firmato dalla busta CMS/PKCS#7 con un vero parser ASN.1.

    Indispensabile per i P7M con contenuto BER "a blocchi" (OCTET STRING
    multipli, es. firme ArubaPEC): il vecchio taglio testuale lasciava i byte
    dei separatori DENTRO l'XML, corrompendolo (parse impossibile).
    """
    try:
        from asn1crypto import cms
        info = cms.ContentInfo.load(data)
        if info["content_type"].native != "signed_data":
            return None
        content = info["content"]["encap_content_info"]["content"]
        if content is None:
            return None
        payload = content.native
        return payload if isinstance(payload, bytes) else None
    except Exception:
        return None


def extract_xml_from_p7m(data: bytes) -> bytes:
    """
    Estrae l'XML FatturaPA embedded in un file .p7m (PKCS#7/CMS SignedData).
    Prima con il parser CMS (ricompone anche i contenuti a blocchi), poi con
    il fallback testuale storico.
    """
    payload = _extract_cms_payload(data)
    if payload is None and data[:1] != b"\x30":
        # P7M ri-codificato in base64 (capita via email/PEC)
        try:
            payload = _extract_cms_payload(base64.b64decode(data, validate=False))
        except Exception:
            payload = None
    if payload is not None:
        idx = payload.find(b"<?xml")
        return payload[idx:] if idx > 0 else payload

    # Fallback testuale storico (P7M non parsabili come CMS)
    idx = data.find(b'<?xml')
    if idx >= 0:
        xml_bytes = data[idx:]
        # Cerca la fine del documento XML - l'ultimo tag di chiusura
        for closing_tag in [b'</FatturaElettronica>', b'</ns2:FatturaElettronica>', b'</p:FatturaElettronica>']:
            end_idx = xml_bytes.rfind(closing_tag)
            if end_idx >= 0:
                return xml_bytes[:end_idx + len(closing_tag)]
        # Se non trova il tag di chiusura, restituisce tutto dal <?xml
        return xml_bytes
    return None


def decode_content(raw_content) -> bytes:
    """Decodifica il contenuto da base64 o bytes."""
    if raw_content is None:
        return None
    if isinstance(raw_content, bytes):
        return raw_content
    if isinstance(raw_content, str):
        try:
            return base64.b64decode(raw_content)
        except Exception:
            return raw_content.encode("utf-8")
    return None
