"""
XML Parser for Italian Electronic Invoices (FatturaPA).
Handles standard FatturaPA format (1.2.1/1.2.2).
"""
from typing import Dict, Any, Optional
from datetime import datetime
import logging
from lxml import etree

logger = logging.getLogger(__name__)

class InvoiceXMLParser:
    """Parser for Fattura Elettronica XML."""
    
    def __init__(self, xml_content: bytes):
        self.xml_content = xml_content
        self.root = None
        self.namespaces = {}
        self._parse()
    
    def _parse(self):
        """Parse XML content."""
        try:
            self.root = etree.fromstring(self.xml_content)
            # Extract namespaces
            self.namespaces = self.root.nsmap
            # Normalize namespaces (sometimes they are None)
            if None in self.namespaces:
                del self.namespaces[None]
        except Exception as e:
            logger.error(f"Error parsing XML: {e}")
            raise ValueError(f"Invalid XML format: {e}")

    def _xpath(self, element, path):
        """Helper to execute xpath ignoring namespaces if needed."""
        # Try with local-name() to ignore namespaces which change between versions
        # This is a robust way to find tags regardless of namespace prefix (p:FatturaElettronica vs FatturaElettronica)
        clean_path = "/".join([f"*[local-name()='{tag}']" for tag in path.split("/")])
        return element.xpath(clean_path)

    def _get_text(self, element, path) -> Optional[str]:
        """Get text content of a node."""
        nodes = self._xpath(element, path)
        if nodes and nodes[0].text:
            return nodes[0].text.strip()
        return None

    def parse(self) -> Dict[str, Any]:
        """
        Parse the invoice and return structured data.
        """
        header = self._xpath(self.root, "FatturaElettronicaHeader")[0]
        body = self._xpath(self.root, "FatturaElettronicaBody")[0]
        
        # 1. Supplier (CedentePrestatore)
        supplier_node = self._xpath(header, "CedentePrestatore")[0]
        supplier_data = self._parse_supplier(supplier_node)
        
        # 2. Invoice General Data (DatiGeneraliDocumento)
        general_data_node = self._xpath(body, "DatiGenerali/DatiGeneraliDocumento")[0]
        invoice_data = self._parse_general_data(general_data_node)
        
        # 3. Lines (DettaglioLinee)
        # Handle multiple DettaglioLinee
        lines_nodes = self._xpath(body, "DatiBeniServizi/DettaglioLinee")
        products = []
        for line_node in lines_nodes:
            product = self._parse_line(line_node)
            if product:
                products.append(product)
                
        # 4. Payment Info (DatiPagamento) - Optional
        payment_nodes = self._xpath(body, "DatiPagamento")
        payment_data = None
        if payment_nodes:
            payment_data = self._parse_payment(payment_nodes[0])

        return {
            "supplier": supplier_data,
            "invoice": invoice_data,
            "products": products,
            "payment": payment_data,
            "xml_content": self.xml_content.decode('utf-8', errors='ignore')
        }

    def _parse_supplier(self, node) -> Dict[str, Any]:
        """Parse supplier info."""
        anagrafica = self._xpath(node, "DatiAnagrafici/Anagrafica")[0]
        
        # Name: Denominazione OR Nome + Cognome
        denominazione = self._get_text(anagrafica, "Denominazione")
        if not denominazione:
            nome = self._get_text(anagrafica, "Nome") or ""
            cognome = self._get_text(anagrafica, "Cognome") or ""
            denominazione = f"{nome} {cognome}".strip()
            
        # VAT
        vat = self._get_text(node, "DatiAnagrafici/IdFiscaleIVA/IdCodice")
        country = self._get_text(node, "DatiAnagrafici/IdFiscaleIVA/IdPaese") or "IT"
        
        # Address
        sede = self._xpath(node, "Sede")[0]
        address = self._get_text(sede, "Indirizzo")
        city = self._get_text(sede, "Comune")
        zip_code = self._get_text(sede, "CAP")
        province = self._get_text(sede, "Provincia")
        
        return {
            "name": denominazione,
            "vat_number": vat,
            "country": country,
            "address": address,
            "city": city,
            "zip_code": zip_code,
            "province": province
        }

    def _parse_general_data(self, node) -> Dict[str, Any]:
        """Parse general invoice data."""
        date_str = self._get_text(node, "Data")
        invoice_date = None
        if date_str:
            try:
                invoice_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                pass
                
        number = self._get_text(node, "Numero")
        total_amount = self._get_text(node, "ImportoTotaleDocumento")
        
        # Causale (optional)
        description = self._get_text(node, "Causale")
        
        return {
            "date": invoice_date,
            "number": number,
            "total_amount": float(total_amount) if total_amount else 0.0,
            "description": description
        }

    def _parse_line(self, node) -> Optional[Dict[str, Any]]:
        """Parse a single product line."""
        desc = self._get_text(node, "Descrizione")
        if not desc:
            return None
            
        qty = self._get_text(node, "Quantita") or "1.0"
        price = self._get_text(node, "PrezzoUnitario") or "0.0"
        total = self._get_text(node, "PrezzoTotale") or "0.0"
        vat_rate = self._get_text(node, "AliquotaIVA") or "22.00"
        
        return {
            "description": desc,
            "quantity": float(qty),
            "unit_price": float(price),
            "total_price": float(total),
            "vat_rate": float(vat_rate)
        }

    def _parse_payment(self, node) -> Dict[str, Any]:
        """Parse payment terms."""
        condizioni = self._get_text(node, "CondizioniPagamento") # TP01, TP02...
        
        # Payment details (DettaglioPagamento)
        details = self._xpath(node, "DettaglioPagamento")
        methods = []
        due_date = None
        
        for detail in details:
            method = self._get_text(detail, "ModalitaPagamento") # MP01 (Cash), MP05 (Bonifico)...
            amount = self._get_text(detail, "ImportoPagamento")
            due_date_str = self._get_text(detail, "DataScadenzaPagamento")
            
            if due_date_str and not due_date:
                try:
                    due_date = datetime.strptime(due_date_str, "%Y-%m-%d").date()
                except:
                    pass
            
            methods.append({
                "method": method,
                "amount": float(amount) if amount else 0.0
            })
            
        return {
            "conditions": condizioni,
            "methods": methods,
            "due_date": due_date
        }
