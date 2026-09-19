"""Lettura della busta paga per formato — re-export del modulo unico.

La logica vive in `app.utils.busta_paga_parser`. Fino al 19/09/2026 qui c'era una copia
**identica byte a byte** al lato ERP: nessuna divergenza da classificare,
solo due file da tenere allineati a mano.

Un modulo che non contiene logica non puo' divergere: e' questo il punto del
re-export. Il fork `app/hr` non nasceva per avere due comportamenti, ma per
avere due percorsi di import, e quelli restano.
"""
from app.utils.busta_paga_parser import (  # noqa: F401
    MESI_MAP,
    detect_format,
    extract_busta_paga_data,
    extract_lordo_mese,
    get_latest_progressivi,
    parse_format_csc_2017,
    parse_format_teamsystem_2022,
    parse_format_zucchetti_2023,
    parse_italian_number,
    scan_all_dipendenti,
    scan_dipendente_folder,
)

__all__ = [
    "MESI_MAP",
    "detect_format",
    "extract_busta_paga_data",
    "extract_lordo_mese",
    "get_latest_progressivi",
    "parse_format_csc_2017",
    "parse_format_teamsystem_2022",
    "parse_format_zucchetti_2023",
    "parse_italian_number",
    "scan_all_dipendenti",
    "scan_dipendente_folder",
]
