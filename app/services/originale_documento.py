"""Apertura dell'originale: un servizio solo (DRV-04).

Prima un PDF o un XML si apriva da una ventina di strade, ognuna con il suo
modo di cercare i byte (``documenti.py``, ``fiscal_control.py``,
``f24-public``, ``cedolini``, PagoPA, bonifici, atti, estratti...). Qui c'e'
la sola risposta alla domanda «dov'e' l'originale di questo documento?»:

* si indica **tipo + id** (la collezione la sceglie il tipo) oppure un
  ``drive_id`` / uno SHA-256;
* i byte si cercano nell'ordine ``payload sul record`` (``pdf_data`` e
  parenti, che il runtime idrata da ``gestionale.blobs``), ``blob_key``,
  Drive per id (``drive_download.scarica_originale``: la credenziale provata
  sulla cartella unica);
* se non si trova niente la risposta e' ``OriginaleNonDisponibile`` con
  l'elenco di cio' che si e' provato: **mai** un 200 vuoto, mai un file
  inventato.

Un lettore specifico per famiglia (atti, estratti, cartelle, verbali, XML
delle fatture) resta dov'e': qui lo si **chiama**, non lo si ricopia.
Solo lettura: niente si scrive, niente si sposta.
"""
from __future__ import annotations

import base64
import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

__all__ = [
    "Originale", "OriginaleErrore", "OriginaleNonDisponibile", "TipoNonValido", "TIPI",
    "apri", "apri_per_drive_id", "apri_per_impronta", "url_originale", "mime_dai_byte",
]

# Campi del record che portano il contenuto, nell'ordine in cui si provano.
CAMPI_BASE64 = ("pdf_data", "contenuto_b64", "content_base64", "file_data")
CAMPI_TESTO = ("xml_raw", "xml_content")
CAMPI_DRIVE = ("drive_file_id",)


class OriginaleErrore(Exception):
    """Errore col contratto dell'API: ``code``, ``message``, ``details``."""

    stato = 500
    code = "ORIGINALE_ERRORE"

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class TipoNonValido(OriginaleErrore):
    stato = 400
    code = "TIPO_ORIGINALE_NON_VALIDO"


class DocumentoNonTrovato(OriginaleErrore):
    stato = 404
    code = "DOCUMENTO_NON_TROVATO"


class OriginaleNonDisponibile(OriginaleErrore):
    """Il documento c'e', ma nessuna fonte ha i suoi byte."""

    stato = 404
    code = "ORIGINALE_NON_DISPONIBILE"


class OriginaleNonCorrispondente(OriginaleErrore):
    """I byte trovati non hanno lo SHA-256 registrato: non si servono."""

    stato = 409
    code = "ORIGINALE_NON_CORRISPONDENTE"


@dataclass
class Originale:
    contenuto: bytes
    nome: str
    mime: str
    fonte: str  # payload | blob | drive | registro | xml | allegato_xml
    sha256: str = field(default="")

    def __post_init__(self):
        if not self.sha256:
            self.sha256 = hashlib.sha256(self.contenuto).hexdigest()


# ── byte, nome e tipo ──────────────────────────────────────────────────────

_MAGIC = ((b"%PDF", "application/pdf"), (b"\x89PNG", "image/png"), (b"\xff\xd8\xff", "image/jpeg"),
          (b"PK\x03\x04", "application/zip"), (b"GIF8", "image/gif"))
_ESTENSIONI = {"pdf": "application/pdf", "xml": "application/xml", "png": "image/png", "jpg": "image/jpeg",
               "jpeg": "image/jpeg", "zip": "application/zip", "txt": "text/plain", "html": "text/html",
               "htm": "text/html", "csv": "text/csv", "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
               "p7m": "application/pkcs7-mime"}


def mime_dai_byte(contenuto: bytes, nome: str = "", dichiarato: Optional[str] = None) -> str:
    """Il tipo guarda prima i byte (un PDF resta PDF anche con un nome sbagliato)."""
    for firma, mime in _MAGIC:
        if contenuto.startswith(firma):
            return mime
    testa = contenuto[:512].lstrip(b"\xef\xbb\xbf \r\n\t")
    if testa.startswith(b"<?xml") or testa.startswith(b"<p:FatturaElettronica") or testa.startswith(b"<ns"):
        return "application/xml"
    estensione = nome.rsplit(".", 1)[-1].lower() if "." in nome else ""
    if estensione in _ESTENSIONI:
        return _ESTENSIONI[estensione]
    return (dichiarato or "application/octet-stream").split(";")[0].strip() or "application/octet-stream"


def _nome_pulito(nome: Any, predefinito: str) -> str:
    testo = re.sub(r"[\r\n\"]+", " ", str(nome or "")).strip()
    testo = re.sub(r"[\\/]+", "-", testo)
    return testo or predefinito


def _decodifica(dati: Any, campo: str) -> bytes:
    if isinstance(dati, (bytes, bytearray)):
        return bytes(dati)
    try:
        return base64.b64decode(str(dati), validate=False)
    except (ValueError, TypeError) as exc:
        raise OriginaleNonDisponibile(
            "Originale non disponibile: il contenuto salvato non si decodifica",
            {"campo": campo, "errore": type(exc).__name__}) from exc


def _archivio_blob():
    from app.database import Database
    from app.services.blob_store import blob_store_per_runtime

    return blob_store_per_runtime(Database.db)


async def byte_dal_record(doc: Dict[str, Any], tentati: List[str]) -> Optional[Tuple[bytes, str]]:
    """(byte, fonte) dai campi di un record, o ``None``. Aggiunge a ``tentati``."""
    for campo in CAMPI_BASE64:
        dati = doc.get(campo)
        if dati:
            contenuto = _decodifica(dati, campo)
            if contenuto:
                return contenuto, "payload"
        tentati.append(campo)
    for campo in CAMPI_TESTO:
        testo = doc.get(campo)
        if testo:
            if isinstance(testo, str):
                testo = re.sub(r'encoding\s*=\s*(["\'])[^"\']*\1', 'encoding="UTF-8"', testo, count=1).encode("utf-8")
            return bytes(testo), "xml"
        tentati.append(campo)
    if doc.get("blob_key"):
        dati = await _archivio_blob().get(doc["blob_key"])
        if dati:
            contenuto = _decodifica(dati, "blob_key")
            if contenuto:
                return contenuto, "blob"
        tentati.append("blob_key")
    for campo in CAMPI_DRIVE:
        if doc.get(campo):
            from app.services.drive_download import scarica_originale

            contenuto = await scarica_originale(str(doc[campo]), md5=doc.get("drive_md5") or doc.get("md5"))
            if contenuto:
                return contenuto, "drive"
            tentati.append(f"{campo}:{doc[campo]}")
    return None


def _nome_record(doc: Dict[str, Any], predefinito: str) -> str:
    for campo in ("filename", "file_name", "nome", "pdf_filename", "nome_file", "source_file"):
        if doc.get(campo):
            return _nome_pulito(doc[campo], predefinito)
    return predefinito


def _mime_record(doc: Dict[str, Any]) -> Optional[str]:
    return doc.get("content_type") or doc.get("mime") or doc.get("mime_type")


def estrai_pdf_da_p7s(firmato: bytes) -> Optional[bytes]:
    """Il PDF dentro una busta firmata P7S/P7M (cerca %PDF- ... %%EOF), o ``None``."""
    inizio = firmato.find(b"%PDF-")
    if inizio == -1:
        return None
    fine = firmato.rfind(b"%%EOF")
    fine = fine + 5 if fine != -1 else len(firmato)
    contenuto = firmato[inizio:fine]
    return contenuto if contenuto.startswith(b"%PDF") else None


async def _da_record(doc: Dict[str, Any], *, predefinito: str, tipo: str, ident: str,
                     impronta: Optional[str] = None) -> Originale:
    tentati: List[str] = []
    trovato = await byte_dal_record(doc, tentati)
    if not trovato:
        raise OriginaleNonDisponibile(
            "Originale non disponibile", {"tipo": tipo, "id": ident, "provato": tentati})
    contenuto, fonte = trovato
    if impronta and hashlib.sha256(contenuto).hexdigest() != impronta.lower():
        raise OriginaleNonCorrispondente(
            "Il file trovato non e' quello registrato (SHA-256 diverso): non si apre",
            {"tipo": tipo, "id": ident, "fonte": fonte})
    nome = _nome_record(doc, predefinito)
    if nome.lower().endswith((".p7s", ".p7m", ".p7c")):
        interno = estrai_pdf_da_p7s(contenuto)
        if interno:
            contenuto, nome = interno, nome.rsplit(".", 1)[0]
            nome = nome if nome.lower().endswith(".pdf") else nome + ".pdf"
    return Originale(contenuto, nome, mime_dai_byte(contenuto, nome, _mime_record(doc)), fonte)


# ── lettori per tipo ───────────────────────────────────────────────────────

Caricatore = Callable[[Any, str, int], Awaitable[Originale]]


def _per_collezioni(collezioni: Tuple[str, ...], predefinito: str, *, campo_id: str = "id",
                    solo_pdf: bool = False):
    """Lettore generico: record per id in una o piu' collezioni."""

    async def carica(db, ident: str, indice: int, _tipo: str = "") -> Originale:
        for collezione in collezioni:
            doc = await db[collezione].find_one({campo_id: ident}, {"_id": 0})
            if doc:
                if doc.get("entity_status") == "deleted":
                    continue
                return await _da_record(doc, predefinito=predefinito.format(id=ident[-12:]),
                                        tipo=collezione, ident=ident)
        raise DocumentoNonTrovato("Documento non trovato", {"id": ident, "collezioni": list(collezioni)})

    return carica


async def _f24(db, ident: str, indice: int) -> Originale:
    """Modello F24 del commercialista, poi quietanza: l'id e' unico fra i due."""
    from app.db_collections import COLL_F24
    from app.services.f24_canonico import COLL_QUIETANZE
    from app.services.f24_originale import carica_originale

    for collezione, tipo in ((COLL_F24, "f24"), (COLL_QUIETANZE, "quietanza")):
        doc = await db[collezione].find_one({"id": ident})
        if doc:
            return await _f24_da_record(doc, tipo, ident, carica_originale)
    raise DocumentoNonTrovato("F24 non trovato", {"id": ident})


async def _quietanza(db, ident: str, indice: int) -> Originale:
    from app.services.f24_canonico import COLL_QUIETANZE
    from app.services.f24_originale import carica_originale

    doc = await db[COLL_QUIETANZE].find_one({"id": ident})
    if not doc:
        raise DocumentoNonTrovato("Quietanza non trovata", {"id": ident})
    return await _f24_da_record(doc, "quietanza", ident, carica_originale)


async def _f24_da_record(doc, tipo, ident, carica_originale) -> Originale:
    try:
        contenuto = await carica_originale(doc, tipo=tipo)
    except ValueError as exc:
        raise OriginaleNonDisponibile(
            f"Originale non disponibile: {exc}", {"tipo": tipo, "id": ident, "errore": type(exc).__name__}) from exc
    if not contenuto:
        raise OriginaleNonDisponibile("Originale non disponibile", {
            "tipo": tipo, "id": ident, "provato": ["pdf_data", "drive_file_id"]})
    nome = _nome_record(doc, f"{tipo.upper()}_{ident[-12:]}.pdf")
    return Originale(contenuto, nome, "application/pdf", "drive" if doc.get("drive_file_id") and not doc.get("pdf_data") else "payload")


async def _cedolino(db, ident: str, indice: int) -> Originale:
    from app.services.f24_originale import carica_originale

    doc = await db["cedolini"].find_one({"id": ident}, {"_id": 0})
    if not doc:
        raise DocumentoNonTrovato("Busta paga non trovata", {"id": ident})
    return await _f24_da_record({**doc, "file_name": doc.get("filename") or doc.get("pdf_filename") or "cedolino.pdf"},
                                "cedolino", ident, carica_originale)


async def _documento_fiscale(db, ident: str, indice: int) -> Originale:
    """Documento fiscale: l'originale e' nel deposito Documenti (``documents_inbox``)."""
    from app.config import settings

    azienda = settings.FISCAL_COMPANY_ID
    documento = await db["fiscal_documents"].find_one({"company_id": azienda, "id": ident}, {"_id": 0})
    if not documento:
        raise DocumentoNonTrovato("Documento fiscale non trovato", {"id": ident})
    inbox_id = (documento.get("metadata") or {}).get("documents_inbox_id")
    filtro = ({"id": inbox_id, "company_id": azienda} if inbox_id
              else {"company_id": azienda, "fiscal_document_id": documento.get("id")})
    sorgente = await db["documents_inbox"].find_one(filtro, {"_id": 0})
    for candidato in (sorgente, documento):
        if candidato:
            try:
                return await _da_record(candidato, predefinito="documento.pdf", tipo="documento_fiscale", ident=ident)
            except OriginaleNonDisponibile:
                continue
    raise OriginaleNonDisponibile("Originale non disponibile", {
        "tipo": "documento_fiscale", "id": ident, "provato": ["documents_inbox", "fiscal_documents"]})


async def _atto(db, ident: str, indice: int) -> Originale:
    from app.services.atti_giudiziari import contenuto

    trovato = await contenuto(db, ident)
    if not trovato:
        raise OriginaleNonDisponibile("Originale non disponibile", {"tipo": "atto", "id": ident, "provato": ["blob_key", "contenuto_b64"]})
    dati, nome = trovato
    return Originale(dati, _nome_pulito(nome, "atto.pdf"), "application/pdf", "blob")


async def _cartella(db, ident: str, indice: int) -> Originale:
    from app.services.cartelle_pagamento import contenuto

    trovato = await contenuto(db, ident)
    if not trovato:
        raise OriginaleNonDisponibile("Originale non disponibile", {"tipo": "cartella", "id": ident, "provato": ["blob_key", "contenuto_b64"]})
    dati, nome = trovato
    return Originale(dati, _nome_pulito(nome, "cartella.pdf"), "application/pdf", "blob")


async def _estratto(db, ident: str, indice: int) -> Originale:
    from app.services.estratti_originali import contenuto

    trovato = await contenuto(db, ident)
    if not trovato:
        raise OriginaleNonDisponibile("Originale non disponibile", {"tipo": "estratto", "id": ident, "provato": ["blob_key", "contenuto_b64", "estratto_conto_nexi"]})
    dati, nome, mime = trovato
    return Originale(dati, _nome_pulito(nome, "estratto"), mime_dai_byte(dati, nome, mime), "blob")


async def _verbale(db, ident: str, indice: int) -> Originale:
    from app.services.verbali_pdf_service import collect_verbale_pdfs

    verbale = await db["verbali_noleggio"].find_one(
        {"$or": [{"numero_verbale": ident}, {"numero_verbale_old": ident}, {"id": ident}]}, {"_id": 0})
    if not verbale:
        raise DocumentoNonTrovato("Verbale non trovato", {"id": ident})
    pdf = next((p for p in await collect_verbale_pdfs(db, verbale) if p.get("indice") == indice), None)
    if not pdf or not pdf.get("content_base64"):
        raise OriginaleNonDisponibile("Originale non disponibile", {
            "tipo": "verbale", "id": ident, "indice": indice, "provato": ["pdf_allegati", "pdf_data", "documents_inbox"]})
    dati = _decodifica(pdf["content_base64"], "content_base64")
    nome = _nome_pulito(pdf.get("filename"), "verbale.pdf")
    return Originale(dati, nome, mime_dai_byte(dati, nome), "payload")


async def _fattura(db, ident: str, indice: int) -> Originale:
    """XML della fattura ricevuta cosi' com'e' arrivato (busta .p7m tolta)."""
    from app.routers.fatture_module.crud import _trova_fattura_e_xml_originale

    fattura, xml = await _trova_fattura_e_xml_originale(ident)
    if fattura is None:
        raise DocumentoNonTrovato("Fattura non trovata", {"id": ident})
    if not xml:
        raise OriginaleNonDisponibile("Originale non disponibile", {
            "tipo": "fattura", "id": ident, "provato": ["xml_file_path", "xml_raw", "xml_content"]})
    numero = fattura.get("invoice_number") or fattura.get("numero_fattura") or ident
    return Originale(xml, f"fattura_{re.sub(r'[^A-Za-z0-9._-]+', '-', str(numero)).strip('-') or 'sconosciuto'}.xml",
                     "application/xml", "xml")


async def _allegato_fattura(db, ident: str, indice: int) -> Originale:
    """L'allegato ``indice`` (PDF di cortesia, ecc.) dentro l'XML della fattura."""
    from app.routers.fatture_module.crud import _MIME_ALLEGATO, _trova_fattura_e_xml_originale, allegati_da_xml

    fattura, xml = await _trova_fattura_e_xml_originale(ident)
    if fattura is None:
        raise DocumentoNonTrovato("Fattura non trovata", {"id": ident})
    allegati = allegati_da_xml(xml) if xml else []
    if not 0 <= indice < len(allegati):
        raise OriginaleNonDisponibile("Originale non disponibile", {
            "tipo": "allegato_fattura", "id": ident, "indice": indice, "allegati": len(allegati)})
    allegato = allegati[indice]
    dati = _decodifica(re.sub(r"\s+", "", allegato["_base64"]), "Attachment")
    formato = "PDF" if dati[:4] == b"%PDF" else (allegato.get("formato") or "")
    nome = re.sub(r"[^A-Za-z0-9._-]+", "-", allegato["nome"]).strip("-") or f"allegato_{indice}"
    if formato == "PDF" and not nome.lower().endswith(".pdf"):
        nome += ".pdf"
    return Originale(dati, nome, _MIME_ALLEGATO.get(formato) or mime_dai_byte(dati, nome), "allegato_xml")


async def _fattura_emessa(db, ident: str, indice: int) -> Originale:
    doc = await db["fatture_emesse"].find_one({"id": ident}, {"_id": 0})
    if not doc:
        raise DocumentoNonTrovato("Fattura emessa non trovata", {"id": ident})
    numero = re.sub(r"[^A-Za-z0-9._-]+", "-", str(doc.get("numero_fattura") or "")).strip("-")
    return await _da_record(doc, predefinito=f"fattura_emessa_{numero or 'senza-numero'}_{doc.get('data_fattura') or ''}.xml",
                            tipo="fattura_emessa", ident=ident)


async def _bonifico(db, ident: str, indice: int) -> Originale:
    """PDF del bonifico: sul record, poi allegato di posta con lo stesso nome file."""
    doc = await db["bonifici_transfers"].find_one({"id": ident}, {"_id": 0})
    if not doc:
        raise DocumentoNonTrovato("Bonifico non trovato", {"id": ident})
    try:
        return await _da_record(doc, predefinito=f"bonifico_{ident[-12:]}.pdf", tipo="bonifico", ident=ident)
    except OriginaleNonDisponibile as primo:
        nome = doc.get("source_file")
        for collezione in _ALLEGATI_BONIFICI:
            allegato = await db[collezione].find_one({"filename": nome}, {"_id": 0}) if nome else None
            if allegato:
                return await _da_record(allegato, predefinito=nome, tipo="bonifico", ident=ident)
        raise primo


async def _protocollo(db, ident: str, indice: int) -> Originale:
    """Originale di una riga del protocollo personale (``AAAA/NNNNNN``).

    Si apre solo se lo SHA-256 e' registrato e i byte lo rispettano: un file
    diverso con lo stesso numero e' un conflitto, non un originale. Prima
    ``drive_file_id`` (con la credenziale della cartella unica), poi l'impronta
    fra i documenti gia' in archivio.
    """
    from app.services import protocollo_personale as pp

    canonico = pp.numero_canonico(ident)
    if not canonico:
        raise DocumentoNonTrovato("Numero di protocollo non valido", {"id": ident})
    riga = await db[pp.COLL].find_one({"id": canonico[0]}, {"_id": 0, "testo_ocr": 0, "testo_indice": 0})
    if not riga:
        raise DocumentoNonTrovato("Protocollo non trovato", {"id": ident})
    impronta = (riga.get("sha256") or "").lower()
    if not impronta:
        # Senza SHA-256 registrato non c'e' modo di provare che il file sia quello: non si apre.
        raise OriginaleNonDisponibile("Originale non disponibile: il registro non porta l'impronta SHA-256", {
            "tipo": "protocollo", "id": canonico[0], "nome_file": riga.get("nome_file"),
            "provato": ["sha256_non_registrato"]})
    provato: List[str] = []
    if riga.get("drive_file_id"):
        from app.services.drive_download import scarica_originale

        contenuto = await scarica_originale(str(riga["drive_file_id"]))
        if contenuto:
            if hashlib.sha256(contenuto).hexdigest() != impronta:
                raise OriginaleNonCorrispondente(
                    "Il file su Drive non e' quello registrato (SHA-256 diverso): non si apre",
                    {"tipo": "protocollo", "id": canonico[0], "drive_file_id": riga["drive_file_id"]})
            nome = _nome_pulito(riga.get("nome_file"), f"protocollo_{canonico[0].replace('/', '-')}.pdf")
            return Originale(contenuto, nome, mime_dai_byte(contenuto, nome), "drive")
        provato.append(f"drive_file_id:{riga['drive_file_id']}")
    try:
        trovato = await apri_per_impronta(db, impronta)
    except OriginaleNonDisponibile as exc:
        provato += list(exc.details.get("provato") or [])
    else:
        if riga.get("nome_file"):
            trovato.nome = _nome_pulito(riga["nome_file"], trovato.nome)
        return trovato
    raise OriginaleNonDisponibile("Originale non disponibile", {
        "tipo": "protocollo", "id": canonico[0], "nome_file": riga.get("nome_file"), "provato": provato})


async def _drive(db, ident: str, indice: int) -> Originale:
    return await apri_per_drive_id(db, ident)


_ALLEGATI_BONIFICI = ("bonifici_email_attachments",)

# I record con payload proprio: (collezioni, nome predefinito).
_DOCUMENTI_INBOX = (
    "documents_inbox", "documenti_non_associati", "f24_email_attachments", "fatture_email_attachments",
    "cedolini_email_attachments", "estratti_email_attachments", "quietanze_email_attachments",
    "bonifici_email_attachments", "verbali_email_attachments", "certificati_email_attachments",
    "cartelle_email_attachments", "avvisi_bonari_email_attachments", "dichiarazioni_iva_email_attachments",
)

TIPI: Dict[str, Any] = {
    "f24": _f24,
    "quietanza": _quietanza,
    "cedolino": _cedolino,
    "ricevuta_pagopa": _per_collezioni(("ricevute_pagopa",), "ricevuta_{id}.pdf"),
    "cartella": _cartella,
    "documento": _per_collezioni(_DOCUMENTI_INBOX, "documento_{id}.pdf"),
    "documento_fiscale": _documento_fiscale,
    "atto": _atto,
    "estratto": _estratto,
    "verbale": _verbale,
    "fattura": _fattura,
    "allegato_fattura": _allegato_fattura,
    "fattura_emessa": _fattura_emessa,
    "bonifico": _bonifico,
    "protocollo": _protocollo,
    "drive": _drive,
}


# ── per id Drive e per impronta ────────────────────────────────────────────

async def apri_per_drive_id(db, drive_id: str) -> Originale:
    """Un originale della cartella unica (ELABORATE), per id Drive."""
    from app.services import drive_cartella_unica as cu

    provato = ["cartella_unica:ELABORATE"]
    try:
        trovato = await cu.originale(db, drive_file_id=drive_id)
    except RuntimeError as exc:
        raise OriginaleNonDisponibile("Originale non disponibile: Drive non raggiungibile", {
            "tipo": "drive", "id": drive_id, "errore": type(exc).__name__}) from exc
    if trovato and trovato.get("contenuto"):
        nome = _nome_pulito(trovato.get("nome"), f"{drive_id}")
        return Originale(trovato["contenuto"], nome, mime_dai_byte(trovato["contenuto"], nome, trovato.get("mime")), "drive")
    # Un file noto al protocollo Drive (inventario) si apre per id: il file non
    # registrato non si scarica mai da un id qualunque.
    riga = None
    try:
        from app.services import drive_protocollo

        riga = await drive_protocollo.documento(drive_id)
    except Exception as exc:  # protocollo spento o database non raggiungibile
        logger.warning("Originale %s: protocollo Drive non letto (%s)", drive_id, type(exc).__name__)
        provato.append(f"protocollo_drive:{type(exc).__name__}")
    if riga and str(riga.get("status") or riga.get("stato") or "").upper() not in ("RIMOSSO",):
        from app.services.drive_download import scarica_originale

        contenuto = await scarica_originale(drive_id, md5=riga.get("md5"))
        if contenuto:
            nome = _nome_pulito(riga.get("filename"), drive_id)
            return Originale(contenuto, nome, mime_dai_byte(contenuto, nome), "drive")
        provato.append("protocollo_drive:file_non_scaricabile")
    elif riga is None and not any(p.startswith("protocollo_drive:") for p in provato):
        provato.append("protocollo_drive:non_registrato")
    raise OriginaleNonDisponibile("Originale non disponibile", {"tipo": "drive", "id": drive_id, "provato": provato})


# collezione dei documenti gia' in archivio -> (campi con lo SHA-256 del file, tipo)
_PER_IMPRONTA: Tuple[Tuple[str, Tuple[str, ...], str], ...] = (
    ("documents_inbox", ("sha256",), "documento"),
    ("cartelle_pagamento", ("sha256",), "cartella"),
    ("ricevute_pagopa", ("pdf_hash", "source_sha256"), "ricevuta_pagopa"),
    ("quietanze_f24", ("pdf_hash",), "quietanza"),
    ("f24_unificato", ("pdf_hash",), "f24"),
    ("verbali_noleggio", ("source_sha256",), "verbale"),
)


async def apri_per_impronta(db, sha256: str) -> Originale:
    """L'originale con quello SHA-256: cartella unica, poi i documenti in archivio.

    I byte trovati si **ricalcolano**: se l'impronta non torna non si servono.
    """
    impronta = str(sha256 or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", impronta):
        raise TipoNonValido("SHA-256 non valido", {"sha256": sha256})
    provato: List[str] = []
    from app.services import drive_cartella_unica as cu

    try:
        trovato = await cu.originale(db, sha256=impronta)
    except RuntimeError as exc:
        provato.append(f"cartella_unica:{type(exc).__name__}")
        trovato = None
    if trovato and trovato.get("contenuto") and hashlib.sha256(trovato["contenuto"]).hexdigest() == impronta:
        nome = _nome_pulito(trovato.get("nome"), impronta[:12])
        return Originale(trovato["contenuto"], nome, mime_dai_byte(trovato["contenuto"], nome, trovato.get("mime")), "drive")
    provato.append("cartella_unica:ELABORATE")
    for collezione, campi, tipo in _PER_IMPRONTA:
        try:
            doc = await db[collezione].find_one({"$or": [{c: impronta} for c in campi]}, {"_id": 0, "id": 1})
        except Exception as exc:
            logger.warning("Originale per impronta: lettura di %s non riuscita (%s)", collezione, type(exc).__name__)
            continue
        if not doc or not doc.get("id"):
            continue
        try:
            originale = await TIPI[tipo](db, str(doc["id"]), 0)
        except OriginaleErrore:
            provato.append(collezione)
            continue
        if originale.sha256 == impronta:
            return originale
        provato.append(f"{collezione}:sha256_diverso")
    raise OriginaleNonDisponibile("Originale non disponibile", {"tipo": "impronta", "sha256": impronta, "provato": provato})


# ── ingresso unico ─────────────────────────────────────────────────────────

async def apri(db, tipo: str, ident: str, indice: int = 0) -> Originale:
    """L'originale di ``tipo`` + ``ident``; solleva ``OriginaleErrore`` col suo codice."""
    caricatore = TIPI.get(str(tipo or "").strip().lower())
    if caricatore is None:
        raise TipoNonValido("Tipo di documento non valido", {"tipo": tipo, "ammessi": sorted(TIPI)})
    ident = str(ident or "").strip()
    if not ident:
        raise TipoNonValido("Indicare l'id del documento", {"tipo": tipo})
    originale = await caricatore(db, ident, max(int(indice or 0), 0))
    if not originale.contenuto:
        raise OriginaleNonDisponibile("Originale non disponibile", {"tipo": tipo, "id": ident})
    return originale


def url_originale(tipo: str, ident: Any, *, indice: Optional[int] = None) -> str:
    """L'indirizzo canonico: i servizi che scrivono un link lo costruiscono qui."""
    from urllib.parse import quote

    base = f"/api/originale/{quote(str(tipo), safe='')}/{quote(str(ident), safe='')}"
    return f"{base}?indice={int(indice)}" if indice else base
