"""Parser PDF dei cedolini — re-export del modulo unico.

La logica vive in `app.services.payslip_pdf_parser`. Fino al 19/09/2026 qui c'era una copia
**identica byte a byte** al lato ERP: nessuna divergenza da classificare,
solo due file da tenere allineati a mano.

Un modulo che non contiene logica non puo' divergere: e' questo il punto del
re-export. Il fork `app/hr` non nasceva per avere due comportamenti, ma per
avere due percorsi di import, e quelli restano.
"""
from app.services.payslip_pdf_parser import (  # noqa: F401
    PayslipPDFParser,
    parse_all_payslips,
)

__all__ = [
    "PayslipPDFParser",
    "parse_all_payslips",
]
