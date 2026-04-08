"""Ceraldi ERP v2 — Parsers."""

from .fattura_xml import parse_fattura_xml
from .cedolino_zucchetti import parse_cedolino_pdf
from .estratto_conto_bpm import parse_estratto_conto_pdf
from .f24 import parse_f24_pdf
from .corrispettivi_xml import parse_corrispettivo_xml
from .distinta_bpm import parse_distinta_pdf
from .verbale import parse_verbale_pdf, parse_verbale_text

