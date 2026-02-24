"""
FatturaPA XML parser.
Parse Italian electronic invoices (FatturaPA format v1.2).
"""
from typing import Dict, Any, List, Optional
from datetime import date
import logging
from lxml import etree

from app.models.invoice import InvoiceCreate
from app.exceptions import ValidationError

logger = logging.getLogger(__name__)


class FatturaPAParser:
    """Parser for FatturaPA XML format v1.2."""
    
    # XML namespaces
    NAMESPACES = {
        'p': 'http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2',
        'ds': 'http://www.w3.org/2000/09/xmldsig#'
    }
    
    def parse_xml(self, xml_content: str) -> InvoiceCreate:
        """
        Parse FatturaPA XML and return InvoiceCreate model.
        
        Args:
            xml_content: XML string content
            
        Returns:
            InvoiceCreate model with parsed data
            
        Raises:
            ValidationError: If XML is invalid or required fields missing
        """
        try:
            root = etree.fromstring(xml_content.encode('utf-8'))
        except etree.XMLSyntaxError as e:
            logger.error(f"Invalid XML syntax: {e}")
            raise ValidationError("Invalid XML format", "xml_content")
        
        try:
            # Parse supplier (CedentePrestatore)
            supplier_data = self._parse_supplier(root)
            
            # Parse invoice body
            body = root.find('.//p:FatturaElettronicaBody', self.NAMESPACES)
            if body is None:
                raise ValidationError("Missing FatturaElettronicaBody", "xml")
            
            # Parse general data
            general_data = self._parse_general_data(body)
            
            # Parse products
            products = self._parse_products(body)
            
            # Parse payment data
            payment_data = self._parse_payment(body)
            
            # Build InvoiceCreate model
            invoice_create = InvoiceCreate(
                supplier_id=supplier_data['vat_number'],  # Will need supplier lookup
                supplier_name=supplier_data['name'],
                invoice_number=general_data['number'],
                date=general_data['date'],
                due_date=payment_data.get('due_date'),
                total_amount=general_data['total_amount'],
                vat_amount=self._calculate_total_vat(products),
                notes=general_data.get('notes'),
                products=products,
                payment_status='unpaid',
                payment_method=payment_data.get('method', 'bonifico')
            )
            
            logger.info(
                f"Parsed FatturaPA: {invoice_create.invoice_number} "
                f"from {supplier_data['name']}"
            )
            
            return invoice_create
            
        except Exception as e:
            logger.error(f"Error parsing FatturaPA: {e}")
            raise ValidationError(f"Error parsing invoice: {str(e)}", "xml")
    
    def _parse_supplier(self, root: etree.Element) -> Dict[str, Any]:
        """Parse supplier (CedentePrestatore) data."""
        cedente = root.find('.//p:CedentePrestatore', self.NAMESPACES)
        if cedente is None:
            raise ValidationError("Missing CedentePrestatore", "xml")
        
        # P.IVA
        id_fiscale = cedente.find('.//p:IdFiscaleIVA', self.NAMESPACES)
        id_paese = self._get_text(id_fiscale, 'p:IdPaese')
        id_codice = self._get_text(id_fiscale, 'p:IdCodice')
        vat_number = f"{id_paese}{id_codice}"
        
        # Name
        anagrafica = cedente.find('.//p:Anagrafica', self.NAMESPACES)
        denominazione = self._get_text(anagrafica, 'p:Denominazione')
        
        # Address
        sede = cedente.find('.//p:Sede', self.NAMESPACES)
        indirizzo = self._get_text(sede, 'p:Indirizzo')
        cap = self._get_text(sede, 'p:CAP')
        comune = self._get_text(sede, 'p:Comune')
        provincia = self._get_text(sede, 'p:Provincia')
        
        address = f"{indirizzo}, {cap} {comune} ({provincia})"
        
        return {
            'vat_number': vat_number,
            'name': denominazione,
            'address': address
        }
    
    def _parse_general_data(self, body: etree.Element) -> Dict[str, Any]:
        """Parse DatiGeneraliDocumento."""
        dati_gen = body.find('.//p:DatiGeneraliDocumento', self.NAMESPACES)
        if dati_gen is None:
            raise ValidationError("Missing DatiGeneraliDocumento", "xml")
        
        # Invoice number
        numero = self._get_text(dati_gen, 'p:Numero')
        if not numero:
            raise ValidationError("Missing invoice number", "numero")
        
        # Date
        data_str = self._get_text(dati_gen, 'p:Data')
        invoice_date = date.fromisoformat(data_str)
        
        # Total amount
        importo = self._get_text(dati_gen, 'p:ImportoTotaleDocumento')
        total_amount = float(importo) if importo else 0.0
        
        # Notes (Causale)
        causale = self._get_text(dati_gen, 'p:Causale')
        
        return {
            'number': numero,
            'date': invoice_date,
            'total_amount': total_amount,
            'notes': causale
        }
    
    def _parse_products(self, body: etree.Element) -> List[Dict[str, Any]]:
        """Parse DettaglioLinee (product lines)."""
        products = []
        
        linee = body.findall('.//p:DettaglioLinee', self.NAMESPACES)
        
        for linea in linee:
            # Description
            descrizione = self._get_text(linea, 'p:Descrizione')
            
            # Quantity
            quantita_str = self._get_text(linea, 'p:Quantita')
            quantita = float(quantita_str) if quantita_str else 1.0
            
            # Unit price
            prezzo_unitario_str = self._get_text(linea, 'p:PrezzoUnitario')
            prezzo_unitario = float(prezzo_unitario_str) if prezzo_unitario_str else 0.0
            
            # VAT rate
            aliquota_iva_str = self._get_text(linea, 'p:AliquotaIVA')
            aliquota_iva = float(aliquota_iva_str) if aliquota_iva_str else 0.0
            
            # Total line
            prezzo_totale_str = self._get_text(linea, 'p:PrezzoTotale')
            prezzo_totale = float(prezzo_totale_str) if prezzo_totale_str else (quantita * prezzo_unitario)
            
            # Unit of measure
            unita_misura = self._get_text(linea, 'p:UnitaMisura') or 'nr'
            
            product = {
                'description': descrizione,
                'quantity': quantita,
                'unit': unita_misura,
                'unit_price': prezzo_unitario,
                'vat_rate': aliquota_iva,
                'total': prezzo_totale
            }
            
            products.append(product)
        
        logger.info(f"Parsed {len(products)} product lines")
        
        return products
    
    def _parse_payment(self, body: etree.Element) -> Dict[str, Any]:
        """Parse DatiPagamento."""
        payment_data = {}
        
        dati_pagamento = body.find('.//p:DatiPagamento', self.NAMESPACES)
        if dati_pagamento is None:
            return payment_data
        
        # Payment conditions
        condizioni = self._get_text(dati_pagamento, 'p:CondizioniPagamento')
        
        # Payment method
        modalita = self._get_text(dati_pagamento, 'p:ModalitaPagamento')
        
        # Map FatturaPA payment codes to our system
        payment_method_map = {
            'MP01': 'contanti',
            'MP02': 'assegno',
            'MP05': 'bonifico',
            'MP08': 'carta',
            'MP12': 'riba',
            'MP19': 'sepa'
        }
        
        payment_data['method'] = payment_method_map.get(modalita, 'bonifico')
        
        # Due date
        dettaglio_pagamento = dati_pagamento.find('.//p:DettaglioPagamento', self.NAMESPACES)
        if dettaglio_pagamento is not None:
            scadenza_str = self._get_text(dettaglio_pagamento, 'p:DataScadenzaPagamento')
            if scadenza_str:
                payment_data['due_date'] = date.fromisoformat(scadenza_str)
        
        return payment_data
    
    def _calculate_total_vat(self, products: List[Dict[str, Any]]) -> float:
        """Calculate total VAT from products."""
        total_vat = 0.0
        
        for product in products:
            vat_rate = product.get('vat_rate', 0.0)
            total = product.get('total', 0.0)
            vat_amount = (total * vat_rate) / (100 + vat_rate)
            total_vat += vat_amount
        
        return round(total_vat, 2)
    
    def _get_text(
        self,
        element: Optional[etree.Element],
        tag: str
    ) -> Optional[str]:
        """Get text content from XML element."""
        if element is None:
            return None
        
        child = element.find(tag, self.NAMESPACES)
        if child is not None and child.text:
            return child.text.strip()
        
        return None
    
    def extract_metadata(self, xml_content: str) -> Dict[str, Any]:
        """
        Extract metadata without full parsing.
        Useful for quick preview/validation.
        """
        try:
            root = etree.fromstring(xml_content.encode('utf-8'))
            
            # Version
            versione = root.get('versione')
            
            # Transmission data
            trasmissione = root.find('.//p:DatiTrasmissione', self.NAMESPACES)
            progressivo = self._get_text(trasmissione, 'p:ProgressivoInvio')
            
            # Supplier name
            cedente = root.find('.//p:CedentePrestatore', self.NAMESPACES)
            anagrafica = cedente.find('.//p:Anagrafica', self.NAMESPACES)
            denominazione = self._get_text(anagrafica, 'p:Denominazione')
            
            # Invoice number
            body = root.find('.//p:FatturaElettronicaBody', self.NAMESPACES)
            dati_gen = body.find('.//p:DatiGeneraliDocumento', self.NAMESPACES)
            numero = self._get_text(dati_gen, 'p:Numero')
            data_str = self._get_text(dati_gen, 'p:Data')
            
            return {
                'versione': versione,
                'progressivo_invio': progressivo,
                'fornitore': denominazione,
                'numero_fattura': numero,
                'data_fattura': data_str,
                'valid': True
            }
            
        except Exception as e:
            logger.error(f"Error extracting metadata: {e}")
            return {
                'valid': False,
                'error': str(e)
            }
