"""Ingresso compatibile per gli estratti BNL (conto corrente e carta BNL Business).

Il conto corrente ha **un solo lettore**, ``app.services.estratto_conto_bnl_parser``:
verso dalla colonna, Decimal, saldi verificati. Questo modulo lo richiama e
restituisce il dizionario storico (``success``/``transazioni``/``metadata``)
che i chiamanti esistenti (sync documenti, monitor email, endpoint import)
si aspettano. Fino al 07/10/2026 qui viveva un lettore a espressioni
regolari che indovinava il verso dalla causale ABI e perdeva righe (sul
trimestre 1/2022: 11 righe su 17, uscite 1.143,78 su 2.460,00).

Resta qui soltanto la lettura dell'estratto della carta BNL Business, che
ha un'impaginazione propria e non e' un movimento del conto corrente.
"""
import logging
import re
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class EstrattoContoBNLParser:
    """Parser per estratti BNL: conto corrente (motore canonico) e carta."""

    def __init__(self):
        self.transactions: List[Dict[str, Any]] = []
        self.metadata: Dict[str, Any] = {}
        self.tipo_documento = "unknown"  # "conto_corrente" o "carta_credito"

    def parse_pdf(self, pdf_content: bytes) -> Dict[str, Any]:
        """Legge un estratto BNL dal PDF.

        Il conto corrente passa dal lettore canonico: un estratto che non
        quadra torna come ``success=False`` con il motivo, mai come righe
        parziali.
        """
        from app.services.estratto_conto_bnl_parser import (
            EstrattoBNLNonValido,
            e_estratto_bnl_pdf,
            leggi_estratto_bnl,
        )

        if e_estratto_bnl_pdf(pdf_content):
            self.tipo_documento = "conto_corrente"
            try:
                estratto = leggi_estratto_bnl(pdf_content)
            except EstrattoBNLNonValido as exc:
                return {
                    "success": False,
                    "error": str(exc),
                    "tipo_documento": "estratto_conto_bnl_cc",
                }
            self.metadata = {
                "numero_estratto": estratto.numero_estratto,
                "periodo_da": estratto.periodo_dal,
                "periodo_a": estratto.periodo_al,
                "numero_conto": estratto.conto,
                "iban": estratto.iban,
                "saldo_iniziale": float(estratto.saldo_iniziale),
                "saldo_finale": float(estratto.saldo_finale),
                "totale_entrate": float(estratto.totale_entrate),
                "totale_uscite": float(estratto.totale_uscite),
            }
            self.transactions = [
                {
                    "data_contabile": riga.data_contabile,
                    "data_valuta": riga.data_valuta,
                    "causale_abi": riga.causale_abi,
                    "descrizione": riga.descrizione,
                    "importo": float(riga.importo_netto),
                    "tipo": riga.tipo,
                    "banca": "BNL",
                }
                for riga in estratto.righe
            ]
            return {
                "success": True,
                "tipo_documento": "estratto_conto_bnl_cc",
                "banca": "BNL",
                "metadata": self.metadata,
                "transazioni": self.transactions,
                "totale_transazioni": len(self.transactions),
                "totale_entrate": float(estratto.totale_entrate),
                "totale_uscite": float(estratto.totale_uscite),
            }

        try:
            import fitz  # PyMuPDF

            doc = fitz.open(stream=pdf_content, filetype="pdf")
            full_text = ""
            for page in doc:
                full_text += page.get_text() + "\n"
            doc.close()
        except Exception as e:
            logger.exception(f"Errore parsing estratto conto BNL: {e}")
            return {
                "success": False,
                "error": str(e),
                "tipo_documento": "estratto_conto_bnl",
            }

        if "CARTA BNL BUSINESS" in full_text or "CARTE DI CREDITO" in full_text:
            self.tipo_documento = "carta_credito"
            return self._parse_carta_credito(full_text)
        return {
            "success": False,
            "error": "Non e' un estratto BNL (conto corrente o carta BNL Business)",
            "tipo_documento": "estratto_conto_bnl",
        }

    def _parse_carta_credito(self, text: str) -> Dict[str, Any]:
        """Parse estratto conto carta di credito BNL Business."""
        self._extract_metadata_carta(text)
        self._extract_transactions_carta(text)
        return {
            "success": True,
            "tipo_documento": "estratto_conto_bnl_carta",
            "banca": "BNL",
            "metadata": self.metadata,
            "transazioni": self.transactions,
            "totale_transazioni": len(self.transactions),
            "totale_importo": sum(t.get("importo", 0) for t in self.transactions)
        }

    def _extract_metadata_carta(self, text: str) -> None:
        """Estrae metadata dall'estratto conto carta di credito."""

        # Numero posizione carta
        match = re.search(r'Numero posizione\s*(\d+)', text)
        if match:
            self.metadata["numero_posizione"] = match.group(1)

        # Codice azienda
        match = re.search(r'Codice azienda\s*(\d+)', text)
        if match:
            self.metadata["codice_azienda"] = match.group(1)

        # Data estratto
        match = re.search(r'Estratto Conto n\.\s*\d+\s+del\s+(\d{2}\.\d{2}\.\d{4})', text)
        if match:
            self.metadata["data_estratto"] = match.group(1).replace(".", "/")

        # Limite di utilizzo
        match = re.search(r'Limite di utilizzo\s*([\d.,]+)\s*euro', text, re.IGNORECASE)
        if match:
            self.metadata["limite_utilizzo"] = self._parse_amount(match.group(1))

        # IBAN domiciliazione
        match = re.search(r'N\. conto corrente\s*(\d+)', text)
        if match:
            self.metadata["conto_addebito"] = match.group(1)

        # Valuta addebito
        match = re.search(r'Valuta di addebito in C/C\s*(\d{2}\.\d{2}\.\d{4})', text)
        if match:
            self.metadata["data_addebito"] = match.group(1).replace(".", "/")

    def _extract_transactions_carta(self, text: str) -> None:
        """Estrae le transazioni dall'estratto conto carta di credito BNL Business."""

        lines = text.split('\n')
        in_dettaglio = False
        current_carta = None
        current_titolare = None

        i = 0
        while i < len(lines):
            line_clean = lines[i].strip()

            # Rileva inizio sezione DETTAGLIO OPERAZIONI
            if "DETTAGLIO OPERAZIONI" in line_clean:
                in_dettaglio = True
                i += 1
                continue

            # Rileva carta attiva
            if "CARTA BNL BUSINESS n." in line_clean:
                match = re.search(r'CARTA BNL BUSINESS n\.\s*([\d\*\s]+)', line_clean)
                if match:
                    current_carta = match.group(1).strip()
                    # Il titolare è sulla riga successiva
                    if i + 1 < len(lines):
                        next_line = lines[i + 1].strip()
                        if next_line and not re.match(r'\d{2}\.\d{2}\.\d{4}', next_line):
                            current_titolare = next_line
                i += 1
                continue

            # Fine sezione - Saldo carta
            if in_dettaglio and line_clean.startswith("Saldo CARTA"):
                in_dettaglio = False
                i += 1
                continue

            if in_dettaglio:
                # Cerca pattern: data operazione (DD.MM.YYYY)
                if re.match(r'^\d{2}\.\d{2}\.\d{4}$', line_clean):
                    data_operazione = line_clean

                    # Leggi le righe successive
                    data_contabile = None
                    num_riferimento = None
                    descrizione = None
                    importo = None

                    # Riga +1: data contabile
                    if i + 1 < len(lines):
                        next_line = lines[i + 1].strip()
                        if re.match(r'^\d{2}\.\d{2}\.\d{4}$', next_line):
                            data_contabile = next_line

                    # Riga +2: numero riferimento
                    if i + 2 < len(lines):
                        next_line = lines[i + 2].strip()
                        if re.match(r'^\d+$', next_line):
                            num_riferimento = next_line

                    # Riga +3: descrizione
                    if i + 3 < len(lines):
                        descrizione = lines[i + 3].strip()

                    # Riga +4: importo
                    if i + 4 < len(lines):
                        next_line = lines[i + 4].strip()
                        if re.match(r'^[\d.,]+$', next_line):
                            importo = self._parse_amount(next_line)

                    # Se abbiamo i dati essenziali, crea transazione
                    if data_operazione and descrizione and importo is not None:
                        self.transactions.append({
                            "data": self._parse_date(data_operazione.replace(".", "/")),
                            "data_contabile": self._parse_date(data_contabile.replace(".", "/")) if data_contabile else None,
                            "numero_riferimento": num_riferimento,
                            "descrizione": descrizione,
                            "importo": -abs(importo),  # Sempre negativo per carta
                            "tipo": "addebito",
                            "banca": "BNL",
                            "tipo_carta": "BNL Business",
                            "carta_numero": current_carta,
                            "carta_titolare": current_titolare
                        })
                        i += 4  # Salta le righe già processate
                        continue

            i += 1

    def _parse_date(self, date_str: str) -> str:
        """Converte una data in formato ISO."""
        try:
            # Supporta DD/MM/YYYY e DD/MM/YY
            parts = date_str.replace(".", "/").split('/')
            if len(parts) == 3:
                day = parts[0].zfill(2)
                month = parts[1].zfill(2)
                year = parts[2]
                if len(year) == 2:
                    year = "20" + year if int(year) < 50 else "19" + year
                return f"{year}-{month}-{day}"
        except Exception:
            pass
        return date_str

    def _parse_amount(self, amount_str: str) -> float:
        """Converte un importo stringa in float."""
        try:
            # Rimuovi spazi e gestisci formato italiano
            amount_str = amount_str.replace(' ', '').replace('.', '').replace(',', '.')
            return float(amount_str)
        except Exception:
            return 0.0


def parse_estratto_conto_bnl(pdf_content: bytes) -> Dict[str, Any]:
    """Ingresso storico: dizionario ``success``/``transazioni``/``metadata``."""
    parser = EstrattoContoBNLParser()
    return parser.parse_pdf(pdf_content)


async def parse_estratto_conto_bnl_from_file(file_path: str) -> Dict[str, Any]:
    """Legge un estratto conto BNL da un file su disco."""
    with open(file_path, "rb") as f:
        return parse_estratto_conto_bnl(f.read())
