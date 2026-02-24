"""
Parser per Corrispettivi Elettronici (Trasmissione Telematica)
Formato COR10 dell'Agenzia delle Entrate.
Estrae: dati trasmissione, riepilogo IVA, pagamento contanti e elettronico.
"""
import xml.etree.ElementTree as ET
from typing import Dict, Any
from datetime import datetime, timezone
import logging
import re
import hashlib

logger = logging.getLogger(__name__)


def clean_xml_namespaces(xml_content: str) -> str:
    """
    Rimuove completamente tutti i namespace e prefissi dall'XML.
    Supporta: n1:, p:, ns:, e qualsiasi altro prefisso.
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
    
    # Rimuovi prefissi dai tag: <n1:TagName> -> <TagName>, </n1:TagName> -> </TagName>
    # Supporta qualsiasi prefisso: n1, p, ns, ds, etc.
    xml_content = re.sub(r'<([a-zA-Z0-9_]+):([a-zA-Z0-9_]+)', r'<\2', xml_content)
    xml_content = re.sub(r'</([a-zA-Z0-9_]+):([a-zA-Z0-9_]+)', r'</\2', xml_content)
    
    # Rimuovi prefissi dagli attributi
    xml_content = re.sub(r'\s+[a-zA-Z0-9_]+:([a-zA-Z0-9_]+)=', r' \1=', xml_content)
    
    return xml_content


def parse_corrispettivo_xml(xml_content: str) -> Dict[str, Any]:
    """
    Parse un file XML di corrispettivi elettronici formato COR10.
    Estrae tutti i dati incluso il pagamento elettronico.
    
    Args:
        xml_content: Contenuto XML dei corrispettivi
        
    Returns:
        Dict con i dati dei corrispettivi estratti
    """
    try:
        # Pulisci XML da namespace e prefissi
        xml_cleaned = clean_xml_namespaces(xml_content)
        
        # Parse XML - prova diverse codifiche
        root = None
        for encoding in ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252']:
            try:
                root = ET.fromstring(xml_cleaned.encode(encoding))
                break
            except (ET.ParseError, UnicodeEncodeError, UnicodeDecodeError) as e:
                logger.debug(f"Tentativo parsing con {encoding} fallito: {e}")
                continue
        
        if root is None:
            try:
                root = ET.fromstring(xml_cleaned)
            except ET.ParseError as e:
                logger.error(f"Parsing XML fallito: {e}")
                logger.debug(f"XML pulito (primi 500 char): {xml_cleaned[:500]}")
                return {"error": f"Errore parsing XML: {str(e)}", "raw_xml_parsed": False}
        
        def find_element(parent, tag_name):
            """Trova elemento per nome locale."""
            if parent is None:
                return None
            el = parent.find(f".//{tag_name}")
            if el is not None:
                return el
            for child in parent.iter():
                local_name = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                if local_name == tag_name:
                    return child
            return None
        
        def find_all_elements(parent, tag_name):
            """Trova tutti gli elementi con un certo nome."""
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
            if el is not None and el.text:
                return el.text.strip()
            return default
        
        def get_float(parent, tag_name, default=0.0):
            """Ottieni un float da un elemento."""
            text = get_text(parent, tag_name)
            if text:
                try:
                    return float(text.replace(',', '.'))
                except ValueError:
                    pass
            return default
        
        # ========== ESTRAZIONE DATI TRASMISSIONE ==========
        trasmissione = find_element(root, 'Trasmissione')
        
        progressivo = get_text(trasmissione, 'Progressivo')
        formato = get_text(trasmissione, 'Formato')
        
        # Dispositivo
        dispositivo = find_element(trasmissione, 'Dispositivo')
        tipo_dispositivo = get_text(dispositivo, 'Tipo')  # RT
        id_dispositivo = get_text(dispositivo, 'IdDispositivo')  # Matricola RT
        
        # Dati esercente
        codice_fiscale_esercente = get_text(trasmissione, 'CodiceFiscaleEsercente')
        piva_esercente = get_text(trasmissione, 'PIVAEsercente')
        
        # Data ora trasmissione
        data_ora_trasmissione = get_text(trasmissione, 'DataOraTrasmissione')
        
        # ========== DATA ORA RILEVAZIONE ==========
        data_ora_rilevazione = get_text(root, 'DataOraRilevazione')
        
        # Estrai solo la data (YYYY-MM-DD)
        data_operazione = ""
        for dt_field in [data_ora_rilevazione, data_ora_trasmissione]:
            if dt_field:
                # Formato: 2025-01-16T20:14:42+01:00
                if 'T' in dt_field:
                    data_operazione = dt_field.split('T')[0]
                else:
                    data_operazione = dt_field[:10]
                break
        
        if not data_operazione:
            data_operazione = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        
        # ========== DATI RT - RIEPILOGO IVA ==========
        dati_rt = find_element(root, 'DatiRT')
        
        riepilogo_iva = []
        totale_imponibile = 0.0
        totale_imposta = 0.0
        totale_ammontare_lordo = 0.0  # Per scorporo IVA se necessario
        
        for riepilogo in find_all_elements(dati_rt, 'Riepilogo'):
            iva_el = find_element(riepilogo, 'IVA')
            aliquota = get_text(iva_el, 'AliquotaIVA', '0')
            imposta = get_float(iva_el, 'Imposta')
            ammontare = get_float(riepilogo, 'Ammontare')
            importo_parziale = get_float(riepilogo, 'ImportoParziale')
            natura = get_text(riepilogo, 'Natura')
            
            # Calcola importo lordo del riepilogo
            importo_lordo = importo_parziale if importo_parziale > 0 else (ammontare + imposta)
            
            if ammontare > 0 or imposta > 0 or importo_parziale > 0:
                riepilogo_iva.append({
                    "aliquota_iva": aliquota,
                    "imposta": imposta,
                    "ammontare": ammontare,  # Imponibile
                    "importo_parziale": importo_parziale,
                    "importo_lordo": importo_lordo,
                    "natura": natura,
                })
                totale_imponibile += ammontare
                totale_imposta += imposta
                totale_ammontare_lordo += importo_lordo
        
        # ========== TOTALI - PAGAMENTI ==========
        totali = find_element(dati_rt, 'Totali')
        
        numero_doc_commerciali = int(get_text(totali, 'NumeroDocCommerciali', '0') or '0')
        pagato_contanti = get_float(totali, 'PagatoContanti')
        pagato_elettronico = get_float(totali, 'PagatoElettronico')
        
        # Estrai TotaleAmmontareAnnulli
        totale_ammontare_annulli = get_float(totali, 'TotaleAmmontareAnnulli')
        
        # Totale corrispettivi = contanti + elettronico
        totale_corrispettivi = pagato_contanti + pagato_elettronico
        
        # Se totale è 0, prova a calcolarlo dai riepiloghi
        if totale_corrispettivi == 0:
            totale_corrispettivi = totale_ammontare_lordo
        
        # ========== CALCOLO PAGATO NON RISCOSSO ==========
        # Pagato Non Riscosso = (Ammontare + ImportoParziale) - (PagatoContanti + PagatoElettronico)
        # In pratica: somma degli importi dai riepiloghi meno quanto effettivamente incassato
        totale_ammontare_riepiloghi = sum(r.get('ammontare', 0) for r in riepilogo_iva)
        totale_importo_parziale_riepiloghi = sum(r.get('importo_parziale', 0) for r in riepilogo_iva)
        totale_lordo_riepiloghi = totale_ammontare_riepiloghi + totale_importo_parziale_riepiloghi
        
        # Se ImportoParziale include già Ammontare, usa solo ImportoParziale
        if totale_importo_parziale_riepiloghi > 0 and totale_ammontare_riepiloghi > 0:
            # Verifica se ImportoParziale è già il totale lordo
            if abs(totale_importo_parziale_riepiloghi - totale_corrispettivi) < 1:
                totale_lordo_riepiloghi = totale_importo_parziale_riepiloghi
        
        pagato_non_riscosso = max(0, totale_lordo_riepiloghi - totale_corrispettivi)
        
        # ========== CALCOLO IVA SE NON PRESENTE ==========
        # Se l'IVA totale è 0 ma abbiamo un totale > 0, applichiamo scorporo al 10%
        # Ristorazione tipicamente ha IVA al 10%
        if totale_imposta == 0 and totale_corrispettivi > 0:
            # Scorporo IVA al 10%: IVA = Totale - (Totale / 1.10)
            totale_imposta = totale_corrispettivi - (totale_corrispettivi / 1.10)
            totale_imponibile = totale_corrispettivi / 1.10
            
            # Aggiungi al riepilogo
            if not riepilogo_iva:
                riepilogo_iva.append({
                    "aliquota_iva": "10.00",
                    "imposta": round(totale_imposta, 2),
                    "ammontare": round(totale_imponibile, 2),
                    "importo_parziale": round(totale_corrispettivi, 2),
                    "importo_lordo": round(totale_corrispettivi, 2),
                    "natura": "",
                    "calcolato_scorporo": True  # Flag che indica calcolo automatico
                })
            else:
                # Aggiorna primo riepilogo con IVA calcolata
                for riep in riepilogo_iva:
                    if riep.get("imposta", 0) == 0:
                        importo_lordo = riep.get("importo_lordo", 0) or riep.get("importo_parziale", 0)
                        if importo_lordo > 0:
                            riep["imposta"] = round(importo_lordo - (importo_lordo / 1.10), 2)
                            riep["ammontare"] = round(importo_lordo / 1.10, 2)
                            riep["aliquota_iva"] = "10.00"
                            riep["calcolato_scorporo"] = True
        
        # ========== GENERA CHIAVE UNIVOCA ==========
        # Formato: piva_data_idDispositivo_progressivo
        piva = piva_esercente or codice_fiscale_esercente or ""
        corrispettivo_key = f"{piva}_{data_operazione}_{id_dispositivo}_{progressivo}"
        corrispettivo_key = corrispettivo_key.replace(" ", "").replace("/", "-").upper()
        
        # Se chiave troppo corta, usa hash
        if len(corrispettivo_key.replace("_", "")) < 8:
            corrispettivo_key = hashlib.md5(xml_content.encode('utf-8', errors='ignore')).hexdigest()[:20]
        
        # ========== COSTRUISCI RISULTATO ==========
        result = {
            "corrispettivo_key": corrispettivo_key,
            "data": data_operazione,
            "data_ora_rilevazione": data_ora_rilevazione,
            "data_ora_trasmissione": data_ora_trasmissione,
            
            # Dispositivo / Matricola
            "matricola_rt": id_dispositivo,
            "tipo_dispositivo": tipo_dispositivo,
            "numero_documento": progressivo,
            "formato": formato,
            
            # Esercente
            "partita_iva": piva_esercente,
            "codice_fiscale": codice_fiscale_esercente,
            "esercente": {
                "partita_iva": piva_esercente,
                "codice_fiscale": codice_fiscale_esercente,
            },
            
            # Totali pagamenti
            "totale_corrispettivi": totale_corrispettivi,
            "totale": totale_corrispettivi,
            "pagato_contanti": pagato_contanti,
            "pagato_elettronico": pagato_elettronico,
            "numero_documenti": numero_doc_commerciali,
            
            # Annulli e Non Riscosso
            "totale_ammontare_annulli": totale_ammontare_annulli,
            "pagato_non_riscosso": pagato_non_riscosso,
            
            # IVA
            "totale_imponibile": totale_imponibile,
            "totale_iva": totale_imposta,
            "riepilogo_iva": riepilogo_iva,
            
            # Metadata
            "raw_xml_parsed": True,
            "versione": get_text(root, 'versione') or "COR10"
        }
        
        return result
        
    except ET.ParseError as e:
        logger.error(f"Errore parsing XML corrispettivi: {e}")
        return {"error": f"Errore parsing XML: {str(e)}", "raw_xml_parsed": False}
    except Exception as e:
        logger.error(f"Errore generico parsing corrispettivi: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {"error": f"Errore parsing: {str(e)}", "raw_xml_parsed": False}


def generate_corrispettivo_key(partita_iva: str, data: str, matricola: str = "", numero_doc: str = "") -> str:
    """Genera chiave univoca per corrispettivo."""
    key = f"{partita_iva}_{data}_{matricola}_{numero_doc}"
    return key.replace(" ", "").replace("/", "-").upper()
