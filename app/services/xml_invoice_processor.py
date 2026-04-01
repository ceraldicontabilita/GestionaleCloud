"""
Processore Fatture XML (FatturaPA)
Analizza le fatture elettroniche XML, estrae dati fornitore e
inserisce automaticamente in Prima Nota Banca per pagamenti SEPA/banca/carta.
"""
import xml.etree.ElementTree as ET
import logging
from datetime import datetime, timezone
from uuid import uuid4

logger = logging.getLogger(__name__)

# Codici ModalitaPagamento FatturaPA che indicano pagamento bancario
PAGAMENTO_BANCARIO_CODES = {
    "MP05": "Bonifico",
    "MP08": "Carta di pagamento",
    "MP12": "RIBA",
    "MP13": "MAV",
    "MP16": "Domiciliazione bancaria",
    "MP19": "SEPA Direct Debit",
    "MP20": "SEPA Direct Debit CORE",
    "MP21": "SEPA Direct Debit B2B",
    "MP23": "PagoPA",
}


def parse_fattura_xml(xml_content: bytes) -> dict:
    """Analizza una fattura XML FatturaPA ed estrae i dati principali."""
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as e:
        logger.error(f"Errore parsing XML: {e}")
        return None

    # Namespace FatturaPA
    ns = ""
    for prefix in [
        "{http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2}",
        "{http://www.fatturapa.gov.it/sdi/fatturapa/v1.1}",
    ]:
        if root.tag.startswith(prefix) or root.find(f".//{prefix}FatturaElettronicaHeader") is not None:
            ns = prefix
            break

    # Fallback: cerca senza namespace
    def find(path):
        el = root.find(f".//{ns}{path}")
        if el is None:
            el = root.find(f".//{path}")
        return el

    def find_text(path, default=""):
        el = find(path)
        return el.text.strip() if el is not None and el.text else default

    # Cedente/Prestatore (Fornitore)
    fornitore = {
        "denominazione": find_text("CedentePrestatore/DatiAnagrafici/Anagrafica/Denominazione"),
        "nome": find_text("CedentePrestatore/DatiAnagrafici/Anagrafica/Nome"),
        "cognome": find_text("CedentePrestatore/DatiAnagrafici/Anagrafica/Cognome"),
        "partita_iva": find_text("CedentePrestatore/DatiAnagrafici/IdFiscaleIVA/IdCodice"),
        "codice_fiscale": find_text("CedentePrestatore/DatiAnagrafici/CodiceFiscale"),
        "paese": find_text("CedentePrestatore/DatiAnagrafici/IdFiscaleIVA/IdPaese"),
        "indirizzo": find_text("CedentePrestatore/Sede/Indirizzo"),
        "cap": find_text("CedentePrestatore/Sede/CAP"),
        "comune": find_text("CedentePrestatore/Sede/Comune"),
        "provincia": find_text("CedentePrestatore/Sede/Provincia"),
    }
    if not fornitore["denominazione"] and fornitore["nome"]:
        fornitore["denominazione"] = f"{fornitore['nome']} {fornitore['cognome']}".strip()

    # Dati Generali Documento
    numero = find_text("FatturaElettronicaBody/DatiGenerali/DatiGeneraliDocumento/Numero")
    data = find_text("FatturaElettronicaBody/DatiGenerali/DatiGeneraliDocumento/Data")
    importo_totale = find_text("FatturaElettronicaBody/DatiGenerali/DatiGeneraliDocumento/ImportoTotaleDocumento")
    divisa = find_text("FatturaElettronicaBody/DatiGenerali/DatiGeneraliDocumento/Divisa", "EUR")
    tipo_doc = find_text("FatturaElettronicaBody/DatiGenerali/DatiGeneraliDocumento/TipoDocumento")

    # Condizioni di pagamento
    modalita_pagamento = find_text("FatturaElettronicaBody/DatiPagamento/DettaglioPagamento/ModalitaPagamento")
    importo_pagamento = find_text("FatturaElettronicaBody/DatiPagamento/DettaglioPagamento/ImportoPagamento")
    data_scadenza = find_text("FatturaElettronicaBody/DatiPagamento/DettaglioPagamento/DataScadenzaPagamento")
    iban = find_text("FatturaElettronicaBody/DatiPagamento/DettaglioPagamento/IBAN")

    # Riepilogo IVA
    imponibile = find_text("FatturaElettronicaBody/DatiBeniServizi/DatiRiepilogo/ImponibileImporto")
    imposta = find_text("FatturaElettronicaBody/DatiBeniServizi/DatiRiepilogo/Imposta")
    aliquota = find_text("FatturaElettronicaBody/DatiBeniServizi/DatiRiepilogo/AliquotaIVA")

    # Determina se il pagamento è bancario
    is_pagamento_bancario = modalita_pagamento in PAGAMENTO_BANCARIO_CODES
    desc_pagamento = PAGAMENTO_BANCARIO_CODES.get(modalita_pagamento, modalita_pagamento)

    def safe_float(val):
        try:
            return float(val.replace(",", ".")) if val else 0
        except (ValueError, AttributeError):
            return 0

    return {
        "fornitore": fornitore,
        "numero_fattura": numero,
        "data_fattura": data,
        "tipo_documento": tipo_doc,
        "importo_totale": safe_float(importo_totale) or safe_float(importo_pagamento),
        "imponibile": safe_float(imponibile),
        "imposta": safe_float(imposta),
        "aliquota_iva": safe_float(aliquota),
        "divisa": divisa,
        "modalita_pagamento": modalita_pagamento,
        "descrizione_pagamento": desc_pagamento,
        "is_pagamento_bancario": is_pagamento_bancario,
        "data_scadenza": data_scadenza,
        "iban": iban,
    }


async def process_xml_invoice(db, xml_content: bytes, filename: str) -> dict:
    """
    Processa una fattura XML:
    1. Analizza il contenuto
    2. Inserisce/aggiorna i dati fornitore
    3. Se il metodo di pagamento è SEPA/banca/carta, inserisce in Prima Nota Banca
    """
    parsed = parse_fattura_xml(xml_content)
    if not parsed:
        return {"success": False, "error": "Impossibile analizzare il file XML"}

    fornitore = parsed["fornitore"]
    now = datetime.now(timezone.utc).isoformat()

    # 1. Inserisci/aggiorna fornitore in dati_provvisori/suppliers
    if fornitore["partita_iva"] or fornitore["codice_fiscale"]:
        supplier_filter = {}
        if fornitore["partita_iva"]:
            supplier_filter["partita_iva"] = fornitore["partita_iva"]
        else:
            supplier_filter["codice_fiscale"] = fornitore["codice_fiscale"]

        await db["fornitori"].update_one(
            supplier_filter,
            {"$set": {
                "denominazione": fornitore["denominazione"],
                "partita_iva": fornitore["partita_iva"],
                "codice_fiscale": fornitore["codice_fiscale"],
                "indirizzo": fornitore["indirizzo"],
                "cap": fornitore["cap"],
                "comune": fornitore["comune"],
                "provincia": fornitore["provincia"],
                "paese": fornitore["paese"],
                "updated_at": now,
            }, "$setOnInsert": {
                "id": str(uuid4()),
                "created_at": now,
            }},
            upsert=True
        )

    # 2. Se pagamento bancario, inserisci in Prima Nota Banca
    prima_nota_id = None
    if parsed["is_pagamento_bancario"] and parsed["importo_totale"] > 0:
        dedup_key = f"{fornitore['partita_iva']}_{parsed['numero_fattura']}_{parsed['data_fattura']}"
        existing = await db["prima_nota_banca"].find_one(
            {"dedup_key": dedup_key}, {"_id": 0, "id": 1}
        )
        if not existing:
            prima_nota_id = str(uuid4())
            try:
                anno = int(parsed["data_fattura"][:4]) if parsed["data_fattura"] else datetime.now().year
            except (ValueError, IndexError):
                anno = datetime.now().year

            movimento = {
                "id": prima_nota_id,
                "data": parsed["data_fattura"] or now[:10],
                "tipo": "uscita",
                "importo": parsed["importo_totale"],
                "descrizione": f"Fattura {parsed['numero_fattura']} - {fornitore['denominazione']}",
                "categoria": "fattura_fornitore",
                "metodo_pagamento": parsed["descrizione_pagamento"],
                "modalita_pagamento_codice": parsed["modalita_pagamento"],
                "fornitore": fornitore["denominazione"],
                "partita_iva_fornitore": fornitore["partita_iva"],
                "numero_fattura": parsed["numero_fattura"],
                "iban": parsed["iban"],
                "anno": anno,
                "status": "attivo",
                "source": "email_xml_auto",
                "dedup_key": dedup_key,
                "created_at": now
            }
            await db["prima_nota_banca"].insert_one(movimento)
            logger.info(f"Auto-inserito in Prima Nota Banca: {fornitore['denominazione']} - {parsed['importo_totale']}€")

    return {
        "success": True,
        "fornitore": fornitore["denominazione"],
        "numero_fattura": parsed["numero_fattura"],
        "importo": parsed["importo_totale"],
        "pagamento_bancario": parsed["is_pagamento_bancario"],
        "metodo": parsed["descrizione_pagamento"],
        "prima_nota_id": prima_nota_id,
        "filename": filename
    }
