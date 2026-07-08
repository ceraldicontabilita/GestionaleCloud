"""
Parser per Fatture Elettroniche Italiane (FatturaPA)
Supporta il formato XML FPR12 dell'Agenzia delle Entrate
Gestisce tutti i formati: con namespace, con prefissi, senza namespace.
"""
import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging
import re

logger = logging.getLogger(__name__)

# Codici TipoDocumento noti dello standard FatturaPA (tabella Agenzia Entrate).
# Modulo-level (non solo dentro parse_fattura_xml) così può essere riusato per
# rilevare un tipo_documento non riconosciuto senza duplicare l'elenco altrove
# (es. app/routers/invoices/fatture_upload.py per l'alert FAT_TIPO_AMBIGUO).
TIPO_DOC_MAP = {
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
        
        def get_denominazione_o_persona_fisica(parent):
            """Denominazione, oppure Nome+Cognome per persona fisica/ditta individuale."""
            denominazione = (
                get_nested_text(parent, 'Anagrafica', 'Denominazione')
                or get_nested_text(parent, 'DatiAnagrafici', 'Anagrafica', 'Denominazione')
            )
            if denominazione:
                return denominazione
            nome = (
                get_nested_text(parent, 'Anagrafica', 'Nome')
                or get_nested_text(parent, 'DatiAnagrafici', 'Anagrafica', 'Nome')
            )
            cognome = (
                get_nested_text(parent, 'Anagrafica', 'Cognome')
                or get_nested_text(parent, 'DatiAnagrafici', 'Anagrafica', 'Cognome')
            )
            return " ".join(p for p in (nome, cognome) if p)

        # Estrai dati fornitore (CedentePrestatore)
        cedente = find_element(header, 'CedentePrestatore')
        fornitore = {
            "denominazione": get_denominazione_o_persona_fisica(cedente),
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
            "denominazione": get_denominazione_o_persona_fisica(cessionario),
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
        
        # Estrai DatiFattureCollegate (riferimenti NC↔Fattura)
        # In FatturaPA, DatiFattureCollegate è dentro DatiGenerali (non DatiGeneraliDocumento)
        dati_generali_parent = find_element(body, 'DatiGenerali')
        dati_fatture_collegate = []
        collegate_elements = find_all_elements(dati_generali_parent or body, 'DatiFattureCollegate')
        for dfc in collegate_elements:
            riferimento = {
                "id_documento": get_text(dfc, 'IdDocumento'),
                "data": get_text(dfc, 'Data'),
                "num_item": get_text(dfc, 'NumItem'),
                "codice_commessa": get_text(dfc, 'CodiceCommessaConvenzione'),
                "codice_cup": get_text(dfc, 'CodiceCUP'),
                "codice_cig": get_text(dfc, 'CodiceCIG'),
            }
            # Pulisci: rimuovi campi vuoti
            riferimento = {k: v for k, v in riferimento.items() if v}
            if riferimento:
                dati_fatture_collegate.append(riferimento)
        
        # Estrai anche DatiOrdineAcquisto per riferimenti aggiuntivi
        dati_ordine = []
        for dao in find_all_elements(dati_generali_parent or body, 'DatiOrdineAcquisto'):
            ordine = {
                "id_documento": get_text(dao, 'IdDocumento'),
                "data": get_text(dao, 'Data'),
                "num_item": get_text(dao, 'NumItem'),
                "codice_commessa": get_text(dao, 'CodiceCommessaConvenzione'),
            }
            ordine = {k: v for k, v in ordine.items() if v}
            if ordine:
                dati_ordine.append(ordine)

        # Estrai DatiContratto (es. numero contratto di noleggio/leasing)
        dati_contratto = []
        for dc in find_all_elements(dati_generali_parent or body, 'DatiContratto'):
            contratto = {
                "id_documento": get_text(dc, 'IdDocumento'),
                "data": get_text(dc, 'Data'),
                "num_item": get_text(dc, 'NumItem'),
                "codice_commessa": get_text(dc, 'CodiceCommessaConvenzione'),
                "codice_cup": get_text(dc, 'CodiceCUP'),
                "codice_cig": get_text(dc, 'CodiceCIG'),
            }
            contratto = {k: v for k, v in contratto.items() if v}
            if contratto:
                dati_contratto.append(contratto)
        
        # Estrai linee dettaglio
        linee = []
        for linea in find_all_elements(body, 'DettaglioLinee'):
            descrizione = get_text(linea, 'Descrizione')

            # AltriDatiGestionali: campi liberi TipoDato/RiferimentoTesto usati da
            # molti fornitori (es. Leasys, ALD) per veicolare dati strutturati
            # (codice cliente, contratto, targa, telaio, causali reali) che non
            # trovano posto nei campi standard e altrimenti andrebbero persi.
            altri_dati_gestionali = []
            for adg in find_all_elements(linea, 'AltriDatiGestionali'):
                voce = {
                    "tipo_dato": get_text(adg, 'TipoDato'),
                    "riferimento_testo": get_text(adg, 'RiferimentoTesto'),
                    "riferimento_numero": get_text(adg, 'RiferimentoNumero'),
                    "riferimento_data": get_text(adg, 'RiferimentoData'),
                }
                voce = {k: v for k, v in voce.items() if v}
                if voce:
                    altri_dati_gestionali.append(voce)

            linea_data = {
                "numero_linea": get_text(linea, 'NumeroLinea'),
                "descrizione": descrizione,
                "quantita": get_text(linea, 'Quantita', '1'),
                "unita_misura": get_text(linea, 'UnitaMisura'),
                "prezzo_unitario": get_text(linea, 'PrezzoUnitario', '0'),
                "prezzo_totale": get_text(linea, 'PrezzoTotale', '0'),
                "aliquota_iva": get_text(linea, 'AliquotaIVA', '0'),
                "natura": get_text(linea, 'Natura'),
                "data_inizio_periodo": get_text(linea, 'DataInizioPeriodo'),
                "data_fine_periodo": get_text(linea, 'DataFinePeriodo'),
                "altri_dati_gestionali": altri_dati_gestionali,
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
        
        result = {
            "invoice_number": numero_fattura,
            "invoice_date": data_fattura,
            "tipo_documento": tipo_documento,
            "tipo_documento_desc": TIPO_DOC_MAP.get(tipo_documento, tipo_documento),
            "divisa": divisa,
            "total_amount": total_amount,
            "imponibile": imponibile_totale,
            "iva": iva_totale,
            "causali": causali,
            "dati_fatture_collegate": dati_fatture_collegate,
            "dati_ordine_acquisto": dati_ordine,
            "dati_contratto": dati_contratto,
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
