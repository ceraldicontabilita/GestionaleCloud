# Accounting Module - Contabilità e Prima Nota
from . import accounting_main
from . import accounting_extended
from . import accounting_f24
from . import accounting_engine_api
# NOTA: prima_nota è stato modularizzato in /app/app/routers/prima_nota_module/
from . import prima_nota_automation
# NOTA: prima_nota_salari integrato in prima_nota_module
from . import piano_conti
from . import bilancio
from . import centri_costo
from . import contabilita_avanzata
from . import regole_categorizzazione
from . import iva_calcolo
from . import liquidazione_iva
from . import riconciliazione_automatica
from . import contabilita_gestionale

__all__ = [
    'accounting_main',
    'accounting_extended',
    'accounting_f24',
    'accounting_engine_api',
    'prima_nota_automation',
    'piano_conti',
    'bilancio',
    'centri_costo',
    'contabilita_avanzata',
    'regole_categorizzazione',
    'iva_calcolo',
    'liquidazione_iva',
    'riconciliazione_automatica',
    'contabilita_gestionale'
]
