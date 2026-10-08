"""Livelli di evidenza delle fonti bancarie.

Gli export CSV/XLSX sono utili per allineare il gestionale durante il
trimestre, ma non sono l'estratto conto ufficiale.  Il PDF periodico della
banca e' invece la prova che consente di chiudere una riconciliazione.
"""
from pathlib import Path
from typing import Any, Dict


EVIDENZA_PROVVISORIA = "provvisoria"
EVIDENZA_UFFICIALE = "ufficiale"
STATO_ATTESA_UFFICIALE = "in_attesa_estratto_bancario_ufficiale"


def livello_evidenza_da_filename(filename: str) -> str:
    return (
        EVIDENZA_UFFICIALE
        if Path(str(filename or "")).suffix.lower() == ".pdf"
        else EVIDENZA_PROVVISORIA
    )


def campi_evidenza(filename: str) -> Dict[str, Any]:
    livello = livello_evidenza_da_filename(filename)
    ufficiale = livello == EVIDENZA_UFFICIALE
    return {
        "fonte_documento": (
            "estratto_conto_ufficiale_pdf"
            if ufficiale else "export_bancario_operativo"
        ),
        "livello_evidenza": livello,
        "evidenza_bancaria_ufficiale": ufficiale,
        "in_attesa_estratto_ufficiale": not ufficiale,
        "stato_riconciliazione": None if ufficiale else STATO_ATTESA_UFFICIALE,
    }


def filtro_solo_evidenza_ufficiale() -> Dict[str, Any]:
    """I documenti storici senza metadato restano fonti ufficiali legacy."""
    return {
        "$or": [
            {"livello_evidenza": {"$exists": False}},
            {"livello_evidenza": EVIDENZA_UFFICIALE},
            {"evidenza_bancaria_ufficiale": True},
        ]
    }
