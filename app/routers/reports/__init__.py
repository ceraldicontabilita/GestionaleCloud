# Reports Module - Report e Esportazioni
# NB: exports.py rimosso (audit mappa lug 2026): duplicava simple_exports.py con
# uno stub /excel vuoto e alias repository. Canonico = simple_exports.py.
from . import report_pdf
from . import simple_exports
from . import dashboard

__all__ = [
    'report_pdf',
    'simple_exports',
    'dashboard'
]
