"""
Parser per Fatture Elettroniche Italiane (FatturaPA)
Supporta il formato XML FPR12 dell'Agenzia delle Entrate
Gestisce tutti i formati: con namespace, con prefissi, senza namespace.
Include estrazione intelligente lotti e scadenze dalla descrizione.
"""
import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging
import re

logger = logging.getLogger(__name__)


def estrai_lotto_fornitore(descrizione: str) -> Optional[str]:
    """
    Estrae il codice lotto del fornitore dalla descrizione della riga fattura.
    Cerca pattern comuni: 'Lotto:', 'L.', 'Batch:', 'LOT:', etc.
    
    Returns:
        Codice lotto estratto o None se non trovato
    """
    if not descrizione:
        return None
    
    # Pattern comuni per lotti fornitori (case-insensitive)
    patterns = [
        r'LOTTO[:\s]+([A-Z0-9\-\/\.]+)',          # LOTTO: ABC123
        r'LOT[:\s]+([A-Z0-9\-\/\.]+)',             # LOT: ABC123
        r'L\.\s*([A-Z0-9\-\/\.]+)',                # L. ABC123
        r'L[:\s]+([A-Z0-9\-\/\.]+)',               # L: ABC123
        r'BATCH[:\s]+([A-Z0-9\-\/\.]+)',           # BATCH: ABC123
        r'N\.?\s*LOTTO[:\s]+([A-Z0-9\-\/\.]+)',    # N.LOTTO: ABC123
        r'LOTTO\s+N\.?\s*([A-Z0-9\-\/\.]+)',       # LOTTO N. ABC123
        r'\bLOT\s*([A-Z0-9]{4,})\b',               # LOT ABC123 (almeno 4 caratteri)
        r'\(L[:\s]*([A-Z0-9\-\/\.]+)\)',           # (L: ABC123)
        r'\[LOTTO[:\s]*([A-Z0-9\-\/\.]+)\]',       # [LOTTO: ABC123]
        r'PARTITA[:\s]+([A-Z0-9\-\/\.]+)',         # PARTITA: ABC123
        r'\b(L\d{2}[A-Z]\d{3,})\b',                # L25A001 (formato comune)
        r'\b([A-Z]{2,3}\d{6,}[A-Z]?)\b',           # AB123456 o AB123456A
    ]
    
    descrizione_upper = descrizione.upper()
    
    for pattern in patterns:
        match = re.search(pattern, descrizione_upper)
        if match:
            lotto = match.group(1).strip()
            # Valida che il lotto abbia almeno 3 caratteri alfanumerici
            if len(lotto) >= 3 and re.search(r'[A-Z0-9]', lotto):
                return lotto
    
    return None


def estrai_scadenza_prodotto(descrizione: str) -> Optional[str]:
    """
    Estrae la data di scadenza dalla descrizione della riga fattura.
    Cerca pattern comuni: 'Scad:', 'Exp:', date in vari formati.
    
    Returns:
        Data scadenza in formato ISO (YYYY-MM-DD) o None se non trovata
    """
    if not descrizione:
        return None
    
    descrizione_upper = descrizione.upper()
    
    # Pattern per date con prefisso (SCAD, EXP, etc.)
    patterns_prefisso = [
        r'SCAD[A-Z]*[:\.\s]+(\d{1,2}[\-/\.]\d{1,2}[\-/\.]\d{2,4})',
        r'EXP[A-Z]*[:\.\s]+(\d{1,2}[\-/\.]\d{1,2}[\-/\.]\d{2,4})',
        r'SCADENZA[:\.\s]+(\d{1,2}[\-/\.]\d{1,2}[\-/\.]\d{2,4})',
        r'TMC[:\.\s]+(\d{1,2}[\-/\.]\d{1,2}[\-/\.]\d{2,4})',
        r'BEST\s*BEFORE[:\.\s]+(\d{1,2}[\-/\.]\d{1,2}[\-/\.]\d{2,4})',
        r'BB[:\.\s]+(\d{1,2}[\-/\.]\d{1,2}[\-/\.]\d{2,4})',
    ]
    
    for pattern in patterns_prefisso:
        match = re.search(pattern, descrizione_upper)
        if match:
            try:
                data_str = match.group(1)
                return normalizza_data(data_str)
            except (ValueError, IndexError):
                continue
    
    # Pattern per date standalone (DD/MM/YYYY o simili)
    patterns_date = [
        r'\b(\d{2}[\-/\.]\d{2}[\-/\.]\d{4})\b',  # DD/MM/YYYY o DD-MM-YYYY
        r'\b(\d{2}[\-/\.]\d{2}[\-/\.]\d{2})\b',  # DD/MM/YY
    ]
    
    for pattern in patterns_date:
        matches = re.findall(pattern, descrizione_upper)
        for match in matches:
            try:
                data_normalizzata = normalizza_data(match)
                # Verifica che sia una data futura (probabile scadenza)
                if data_normalizzata:
                    data_obj = datetime.strptime(data_normalizzata, "%Y-%m-%d")
                    if data_obj > datetime.now():
                        return data_normalizzata
            except (ValueError, IndexError):
                continue
    
    return None


def normalizza_data(data_str: str) -> Optional[str]:
    """
    Converte una data in formato ISO (YYYY-MM-DD).
    Supporta: DD/MM/YYYY, DD-MM-YYYY, DD.MM.YYYY, DD/MM/YY
    """
    if not data_str:
        return None
    
    # Sostituisce tutti i separatori con /
    data_str = data_str.replace('-', '/').replace('.', '/')
    parts = data_str.split('/')
    
    if len(parts) != 3:
        return None
    
    try:
        giorno = int(parts[0])
        mese = int(parts[1])
        anno = int(parts[2])
        
        # Gestisce anno a 2 cifre
        if anno < 100:
            anno = 2000 + anno if anno < 50 else 1900 + anno
        
        # Valida la data
        if 1 <= giorno <= 31 and 1 <= mese <= 12 and 2000 <= anno <= 2100:
            return f"{anno:04d}-{mese:02d}-{giorno:02d}"
    except (ValueError, IndexError):
        pass
    
    return None


def clean_xml_namespaces(xml_content: str) -> str:
    """
    Rimuove completamente tutti i namespace e prefissi dall'XML.
    Risolve l'errore "unbound prefix".
    """
    # Rimuovi BOM
    if xml_content.startswith('\ufeff'):
        xml_content = xml_content[1:]
    
    # Rimuovi caratteri nulli e whitespace iniziale
    xml_content = xml_content.replace('\x00', '').strip()
    
    # Rimuovi tutte le dichiarazioni xmlns (anche con prefisso)
    xml_content = re.sub(r'\s+xmlns(:[a-zA-Z0-9_-]+)?="[^"]*"', '', xml_content)
    xml_content = re.sub(r"\s+xmlns(:[a-zA-Z0-9_-]+)?='[^']*'", '', xml_content)
    
    # Rimuovi xsi:... attributes
    xml_content = re.sub(r'\s+xsi:[a-zA-Z]+="[^"]*"', '', xml_content)
    xml_content = re.sub(r"\s+xsi:[a-zA-Z]+='[^']*'", '', xml_content)
    
    # Rimuovi prefissi dai tag: <p:TagName> -> <TagName>
    xml_content = re.sub(r'<([a-zA-Z0-9_-]+):([a-zA-Z0-9_-]+)', r'<\2', xml_content)
    xml_content = re.sub(r'</([a-zA-Z0-9_-]+):([a-zA-Z0-9_-]+)', r'</\2', xml_content)
    
    # Rimuovi prefissi dagli attributi
    xml_content = re.sub(r'\s+[a-zA-Z0-9_-]+:([a-zA-Z0-9_-]+)=', r' \1=', xml_content)
    
    return xml_content


def parse_fattura_xml(xml_content: str) -> Dict[str, Any]:
    """
    Parse una fattura elettronica XML italiana.
    
    Args:
        xml_content: Contenuto XML della fattura
        
    Returns:
        Dict con i dati della fattura estratti
    """
    try:
        # Pulisci XML da namespace e prefissi
        xml_content = clean_xml_namespaces(xml_content)
        
        # Parse XML - prova diverse codifiche
        root = None
        for encoding in ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252']:
            try:
                root = ET.fromstring(xml_content.encode(encoding))
                break
            except (ET.ParseError, UnicodeEncodeError, UnicodeDecodeError):
                continue
        
        if root is None:
            try:
                root = ET.fromstring(xml_content)
            except ET.ParseError as e:
                return {"error": f"Errore parsing XML: {str(e)}", "raw_xml_parsed": False}
        
        # Funzione helper per trovare elementi indipendentemente dal namespace
        def find_element(parent, tag_name):
            """Trova elemento ignorando namespace."""
            if parent is None:
                return None
            # Prima prova direttamente
            el = parent.find('.//' + tag_name)
            if el is not None:
                return el
            # Cerca in tutti i figli
            for child in parent.iter():
                local_name = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                if local_name == tag_name:
                    return child
            return None
        
        def find_all_elements(parent, tag_name):
            """Trova tutti gli elementi con un certo nome locale."""
            results = []
            if parent is None:
                return results
            for child in parent.iter():
                local_name = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                if local_name == tag_name:
                    results.append(child)
            return results
        
        def get_text(parent, tag_name, default=""):
            """Ottieni il testo di un elemento."""
            el = find_element(parent, tag_name)
            return el.text if el is not None and el.text else default
        
        def get_nested_text(parent, *path, default=""):
            """Ottieni testo da path annidato."""
            current = parent
            for tag in path:
                current = find_element(current, tag)
                if current is None:
                    return default
            return current.text if current is not None and current.text else default
        
        # Trova header e body
        header = find_element(root, 'FatturaElettronicaHeader')
        body = find_element(root, 'FatturaElettronicaBody')
        
        # Estrai dati fornitore (CedentePrestatore)
        cedente = find_element(header, 'CedentePrestatore')
        fornitore = {
            "denominazione": get_nested_text(cedente, 'Anagrafica', 'Denominazione') or 
                           get_nested_text(cedente, 'DatiAnagrafici', 'Anagrafica', 'Denominazione'),
            "partita_iva": get_nested_text(cedente, 'IdFiscaleIVA', 'IdCodice') or
                          get_nested_text(cedente, 'DatiAnagrafici', 'IdFiscaleIVA', 'IdCodice'),
            "codice_fiscale": get_nested_text(cedente, 'CodiceFiscale') or
                             get_nested_text(cedente, 'DatiAnagrafici', 'CodiceFiscale'),
            "indirizzo": get_nested_text(cedente, 'Sede', 'Indirizzo'),
            "cap": get_nested_text(cedente, 'Sede', 'CAP'),
            "comune": get_nested_text(cedente, 'Sede', 'Comune'),
            "provincia": get_nested_text(cedente, 'Sede', 'Provincia'),
            "nazione": get_nested_text(cedente, 'Sede', 'Nazione'),
            "telefono": get_nested_text(cedente, 'Contatti', 'Telefono'),
            "email": get_nested_text(cedente, 'Contatti', 'Email'),
        }
        
        # Estrai dati cliente (CessionarioCommittente)
        cessionario = find_element(header, 'CessionarioCommittente')
        cliente = {
            "denominazione": get_nested_text(cessionario, 'Anagrafica', 'Denominazione') or
                           get_nested_text(cessionario, 'DatiAnagrafici', 'Anagrafica', 'Denominazione'),
            "partita_iva": get_nested_text(cessionario, 'IdFiscaleIVA', 'IdCodice') or
                          get_nested_text(cessionario, 'DatiAnagrafici', 'IdFiscaleIVA', 'IdCodice'),
            "codice_fiscale": get_nested_text(cessionario, 'CodiceFiscale') or
                             get_nested_text(cessionario, 'DatiAnagrafici', 'CodiceFiscale'),
            "indirizzo": get_nested_text(cessionario, 'Sede', 'Indirizzo'),
            "cap": get_nested_text(cessionario, 'Sede', 'CAP'),
            "comune": get_nested_text(cessionario, 'Sede', 'Comune'),
            "provincia": get_nested_text(cessionario, 'Sede', 'Provincia'),
        }
        
        # Estrai dati generali documento
        dati_generali = find_element(body, 'DatiGeneraliDocumento')
        numero_fattura = get_text(dati_generali, 'Numero')
        data_fattura = get_text(dati_generali, 'Data')
        tipo_documento = get_text(dati_generali, 'TipoDocumento')
        divisa = get_text(dati_generali, 'Divisa', 'EUR')
        importo_totale = get_text(dati_generali, 'ImportoTotaleDocumento', '0')
        
        # Estrai causali
        causali = []
        for causale_el in find_all_elements(dati_generali, 'Causale'):
            if causale_el.text:
                causali.append(causale_el.text)
        
        # Estrai linee dettaglio con estrazione intelligente lotto/scadenza
        linee = []
        for linea in find_all_elements(body, 'DettaglioLinee'):
            descrizione = get_text(linea, 'Descrizione')
            
            # Estrai lotto fornitore dalla descrizione
            lotto_fornitore = estrai_lotto_fornitore(descrizione)
            
            # Estrai data scadenza dalla descrizione
            scadenza_prodotto = estrai_scadenza_prodotto(descrizione)
            
            linea_data = {
                "numero_linea": get_text(linea, 'NumeroLinea'),
                "descrizione": descrizione,
                "quantita": get_text(linea, 'Quantita', '1'),
                "unita_misura": get_text(linea, 'UnitaMisura'),
                "prezzo_unitario": get_text(linea, 'PrezzoUnitario', '0'),
                "prezzo_totale": get_text(linea, 'PrezzoTotale', '0'),
                "aliquota_iva": get_text(linea, 'AliquotaIVA', '0'),
                "natura": get_text(linea, 'Natura'),
                # Dati estratti per tracciabilità HACCP
                "lotto_fornitore": lotto_fornitore,
                "scadenza_prodotto": scadenza_prodotto,
                "lotto_estratto_automaticamente": lotto_fornitore is not None,
            }
            linee.append(linea_data)
        
        # Estrai riepilogo IVA
        riepilogo_iva = []
        for riepilogo in find_all_elements(body, 'DatiRiepilogo'):
            riepilogo_data = {
                "aliquota_iva": get_text(riepilogo, 'AliquotaIVA', '0'),
                "natura": get_text(riepilogo, 'Natura'),
                "imponibile": get_text(riepilogo, 'ImponibileImporto', '0'),
                "imposta": get_text(riepilogo, 'Imposta', '0'),
                "riferimento_normativo": get_text(riepilogo, 'RiferimentoNormativo'),
            }
            riepilogo_iva.append(riepilogo_data)
        
        # Estrai dati pagamento
        dati_pagamento = find_element(body, 'DatiPagamento')
        dettaglio_pagamento = find_element(dati_pagamento, 'DettaglioPagamento') if dati_pagamento else None
        pagamento = {
            "condizioni": get_text(dati_pagamento, 'CondizioniPagamento') if dati_pagamento else "",
            "modalita": get_text(dettaglio_pagamento, 'ModalitaPagamento') if dettaglio_pagamento else "",
            "data_scadenza": get_text(dettaglio_pagamento, 'DataScadenzaPagamento') if dettaglio_pagamento else "",
            "importo": get_text(dettaglio_pagamento, 'ImportoPagamento', '0') if dettaglio_pagamento else "0",
            "istituto_finanziario": get_text(dettaglio_pagamento, 'IstitutoFinanziario') if dettaglio_pagamento else "",
            "iban": get_text(dettaglio_pagamento, 'IBAN') if dettaglio_pagamento else "",
        }
        
        # Calcola totali
        try:
            total_amount = float(importo_totale) if importo_totale else 0
        except ValueError:
            total_amount = 0
        
        # Calcola imponibile e IVA totali
        imponibile_totale = 0
        iva_totale = 0
        for r in riepilogo_iva:
            try:
                imponibile_totale += float(r.get("imponibile", 0))
                iva_totale += float(r.get("imposta", 0))
            except ValueError:
                pass
        
        # Calcola somma righe per verifica coerenza
        somma_righe = 0
        for linea in linee:
            try:
                somma_righe += float(linea.get("prezzo_totale", 0))
            except ValueError:
                pass
        
        # Verifica coerenza totali
        totale_calcolato = round(imponibile_totale + iva_totale, 2)
        differenza_totali = abs(total_amount - totale_calcolato)
        totali_coerenti = differenza_totali < 0.05  # Tolleranza 5 centesimi
        
        # Estrai allegati (PDF in base64)
        allegati = []
        for allegato in find_all_elements(body, 'Allegati'):
            nome_attachment = get_text(allegato, 'NomeAttachment')
            formato = get_text(allegato, 'FormatoAttachment')
            attachment_data = get_text(allegato, 'Attachment')
            descrizione_allegato = get_text(allegato, 'DescrizioneAttachment')
            
            if attachment_data:
                allegati.append({
                    "nome": nome_attachment,
                    "formato": formato or "PDF",
                    "descrizione": descrizione_allegato,
                    "base64_data": attachment_data,
                    "size_kb": round(len(attachment_data) * 3 / 4 / 1024, 2)  # Stima dimensione
                })
        
        # Mappa tipo documento
        tipo_doc_map = {
            "TD01": "Fattura",
            "TD02": "Acconto/Anticipo su fattura",
            "TD03": "Acconto/Anticipo su parcella",
            "TD04": "Nota di Credito",
            "TD05": "Nota di Debito",
            "TD06": "Parcella",
            "TD16": "Integrazione fattura reverse charge interno",
            "TD17": "Integrazione/autofattura per acquisto servizi dall'estero",
            "TD18": "Integrazione per acquisto di beni intracomunitari",
            "TD19": "Integrazione/autofattura per acquisto di beni ex art.17 c.2 DPR 633/72",
            "TD20": "Autofattura per regolarizzazione e integrazione delle fatture",
            "TD21": "Autofattura per splafonamento",
            "TD22": "Estrazione beni da Deposito IVA",
            "TD23": "Estrazione beni da Deposito IVA con versamento dell'IVA",
            "TD24": "Fattura differita di cui all'art.21, comma 4, lett. a)",
            "TD25": "Fattura differita di cui all'art.21, comma 4, terzo periodo lett. b)",
            "TD26": "Cessione di beni ammortizzabili e per passaggi interni",
            "TD27": "Fattura per autoconsumo o per cessioni gratuite senza rivalsa",
        }
        
        result = {
            "invoice_number": numero_fattura,
            "invoice_date": data_fattura,
            "tipo_documento": tipo_documento,
            "tipo_documento_desc": tipo_doc_map.get(tipo_documento, tipo_documento),
            "divisa": divisa,
            "total_amount": total_amount,
            "imponibile": imponibile_totale,
            "iva": iva_totale,
            "causali": causali,
            "fornitore": fornitore,
            "cliente": cliente,
            "linee": linee,
            "riepilogo_iva": riepilogo_iva,
            "pagamento": pagamento,
            "supplier_name": fornitore.get("denominazione", ""),
            "supplier_vat": fornitore.get("partita_iva", ""),
            "allegati": allegati,
            "has_pdf": len([a for a in allegati if a.get("formato", "").upper() == "PDF"]) > 0,
            "totali_coerenti": totali_coerenti,
            "differenza_totali": differenza_totali,
            "somma_righe": somma_righe,
            "raw_xml_parsed": True
        }
        
        return result
        
    except ET.ParseError as e:
        logger.error(f"Errore parsing XML: {e}")
        return {"error": f"Errore parsing XML: {str(e)}", "raw_xml_parsed": False}
    except Exception as e:
        logger.error(f"Errore generico parsing fattura: {e}")
        return {"error": f"Errore parsing: {str(e)}", "raw_xml_parsed": False}


def parse_multiple_fatture(xml_contents: List[str]) -> List[Dict[str, Any]]:
    """
    Parse multiple fatture XML.
    
    Args:
        xml_contents: Lista di contenuti XML
        
    Returns:
        Lista di dict con i dati delle fatture
    """
    results = []
    for i, xml_content in enumerate(xml_contents):
        try:
            result = parse_fattura_xml(xml_content)
            result["file_index"] = i
            results.append(result)
        except Exception as e:
            results.append({
                "error": str(e),
                "file_index": i,
                "raw_xml_parsed": False
            })
    return results
