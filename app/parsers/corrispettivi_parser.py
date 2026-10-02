"""
Parser per Corrispettivi Elettronici (Trasmissione Telematica)
Formato COR10 dell'Agenzia delle Entrate.
Estrae: dati trasmissione, riepilogo IVA, pagamento contanti e elettronico.
"""
import defusedxml.ElementTree as ET  # sicurezza: blocca XXE/entity expansion su XML esterni
from typing import Dict, Any, Optional
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


#: Motivo di scarto di una chiusura il cui lordo (imponibile + IVA dei
#: riepiloghi) supera contanti + POS senza che l'RT dichiari un non riscosso.
MOTIVO_NON_RISCOSSO_NON_DICHIARATO = "non_riscosso_non_dichiarato"
#: Il non riscosso e' dichiarato ma contanti + POS + non riscosso non fanno il lordo.
MOTIVO_NON_RISCOSSO_NON_QUADRATO = "non_riscosso_non_quadrato"

#: Nomi locali delle voci con cui il tracciato COR10 dichiara il non riscosso.
_VOCI_NON_RISCOSSO = ("NonRiscossoServizi", "NonRiscossoFatture", "NonRiscossoDCRaSSN",
                      "NonRiscossoOmaggio", "PagatoNonRiscosso")


def _cents(valore: Any) -> int:
    """Centesimi interi da un importo letto dall'XML (testo o float gia' letto)."""
    from decimal import Decimal, InvalidOperation

    try:
        return int((Decimal(str(valore or 0).replace(",", ".")) * 100).to_integral_value())
    except (InvalidOperation, ValueError):
        return 0


def _non_riscosso_dichiarato(totali, dati_rt) -> tuple:
    """(centesimi, voci) del non riscosso **scritto** nel documento.

    Si cerca nel blocco `Totali`; se li' non c'e' nessuna voce, nei riepiloghi
    (tracciati che lo spezzano per aliquota). Mai in entrambi: lo stesso
    importo si conterebbe due volte. Nessuna voce = non dichiarato.
    """
    for radice in (totali, dati_rt):
        if radice is None:
            continue
        voci = []
        for el in radice.iter():
            nome = el.tag.split('}')[-1] if '}' in el.tag else el.tag
            if nome in _VOCI_NON_RISCOSSO or nome.startswith("NonRiscosso"):
                voci.append({"voce": nome, "importo_cents": _cents(el.text)})
        if voci:
            return sum(v["importo_cents"] for v in voci), voci
    return 0, []


def _motivo_scarto_giornata(*, lordo_riepiloghi: float, contanti: float, elettronico: float,
                            non_riscosso_cents: int, dichiarato: bool) -> Optional[str]:
    """Il motivo per cui la giornata non si registra, oppure None.

    Vale solo quando il documento ripartisce il pagamento (contanti o POS
    letti): una chiusura legacy senza `Totali` resta com'era. Con la
    ripartizione, contanti + POS + non riscosso dichiarato devono fare il
    lordo dei riepiloghi al centesimo: lo scarto non e' un non riscosso.
    """
    incassato = _cents(contanti) + _cents(elettronico)
    if incassato <= 0:
        return None
    lordo = _cents(round(lordo_riepiloghi, 2))
    if lordo <= 0:
        return None
    if incassato + non_riscosso_cents == lordo:
        return None
    return MOTIVO_NON_RISCOSSO_NON_QUADRATO if dichiarato else MOTIVO_NON_RISCOSSO_NON_DICHIARATO


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
        if not id_dispositivo:
            id_dispositivo = get_text(root, 'IdDispositivo')
        
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
            imposta_raw = get_text(iva_el, 'Imposta', '')
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
                    "imposta_presente": bool(imposta_raw),
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

        # Compatibilita con ricevute RT semplificate/legacy che espongono
        # ImportoTotale e una lista Pagamento invece del blocco Totali COR10.
        # Non applicare il fallback "tutto contanti" ai PeriodoInattivo:
        # in quel caso lo zero e' il valore fiscale reale del documento.
        totale_generico = get_float(root, 'ImportoTotale') or get_float(root, 'Totale')
        if pagato_contanti == 0 and pagato_elettronico == 0:
            for pagamento in find_all_elements(root, 'Pagamento'):
                tipo = get_text(pagamento, 'Tipo').upper()
                importo = get_float(pagamento, 'Importo')
                if any(token in tipo for token in ('POS', 'CARTA', 'ELETTRONICO')):
                    pagato_elettronico += importo
                else:
                    pagato_contanti += importo
            if pagato_contanti == 0 and pagato_elettronico == 0 and totale_generico > 0:
                pagato_contanti = totale_generico
        
        # Estrai TotaleAmmontareAnnulli
        totale_ammontare_annulli = get_float(totali, 'TotaleAmmontareAnnulli')

        # ========== NON RISCOSSO: SOLO SE IL DOCUMENTO LO DICHIARA ==========
        # Fino al 02/10/2026 era `lordo dei riepiloghi − (contanti + POS)`:
        # una differenza qualunque (riga mancante, resi, un centesimo di
        # arrotondamento) diventava un credito verso clienti e la giornata
        # entrava quadrata d'ufficio. Ora si leggono solo le voci che l'RT
        # scrive (`NonRiscossoServizi`, `NonRiscossoFatture`,
        # `NonRiscossoDCRaSSN`, `NonRiscossoOmaggio`, `PagatoNonRiscosso`);
        # lo scarto che resta e' un motivo di scarto, mai un importo.
        non_riscosso_cents, voci_non_riscosso = _non_riscosso_dichiarato(totali, dati_rt)
        pagato_non_riscosso = non_riscosso_cents / 100

        # Totale corrispettivi = incassato (contanti + elettronico) piu' il non
        # riscosso dichiarato: e' il lordo della giornata e deve coincidere
        # con imponibile + IVA dei riepiloghi.
        totale_corrispettivi = round(pagato_contanti + pagato_elettronico + pagato_non_riscosso, 2)

        # Se totale è 0, prova a calcolarlo dai riepiloghi
        if totale_corrispettivi == 0:
            totale_corrispettivi = totale_ammontare_lordo or totale_generico

        totale_lordo_riepiloghi = sum(r.get('importo_lordo', 0) for r in riepilogo_iva)
        motivo_scarto = _motivo_scarto_giornata(
            lordo_riepiloghi=totale_lordo_riepiloghi,
            contanti=pagato_contanti, elettronico=pagato_elettronico,
            non_riscosso_cents=non_riscosso_cents, dichiarato=bool(voci_non_riscosso),
        )

        # L'IVA assente non viene inventata mediante scorporo. Il documento
        # resta importabile come evidenza RT, ma la quadratura IVA viene
        # marcata NON_VERIFICABILE finche non esiste un valore XML stampato.
        
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
            "non_riscosso_dichiarato": bool(voci_non_riscosso),
            "non_riscosso_voci": voci_non_riscosso,
            "lordo_riepiloghi": round(totale_lordo_riepiloghi, 2),
            # Valorizzato solo quando la giornata non si puo' registrare: il
            # motore unico la scarta con questo motivo, mai la fa quadrare.
            "motivo_scarto": motivo_scarto,
            
            # IVA
            "totale_imponibile": totale_imponibile,
            "totale_iva": totale_imposta,
            "riepilogo_iva": riepilogo_iva,
            "quadratura_iva_status": (
                "VERIFICATA"
                if riepilogo_iva and all(r.get("imposta_presente") for r in riepilogo_iva)
                else "NON_VERIFICABILE"
            ),
            
            # Metadata
            "raw_xml_parsed": True,
            "parser_version": "corrispettivi_xml_v2_cents",
            "versione": get_text(root, 'versione') or "COR10",
            "periodo_inattivo": find_element(root, 'PeriodoInattivo') is not None,
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
